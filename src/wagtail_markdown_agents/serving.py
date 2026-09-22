"""Checked response selection shared by direct routes and future negotiation."""

import logging
import re

from django.core.exceptions import ImproperlyConfigured
from django.http import FileResponse, HttpResponseNotAllowed
from django.http.request import split_domain_port
from wagtail import hooks
from wagtail.models import Page, Site

from .export.paths import ExportPathError, site_path
from .export.policy import ExportPolicy
from .export.writer import FileWriter
from .models import ExportArtifact
from .negotiation import METHOD_EXPORT_URL
from .public_urls import export_route
from .settings import get_setting
from .signals import markdown_served

logger = logging.getLogger(__name__)
SERVE_HOOK = "markdown_serve_allowed"
HEADERS_HOOK = "construct_markdown_response_headers"
HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9a-zA-Z-]+$")


class _ExportResponse(FileResponse):
    def set_headers(self, stream):
        # FileResponse's default may stat stream.name on the local filesystem
        # and expose its basename. Backend names are neither public nor local.
        # Content-Type is explicit; length is optional for nonseekable streams.
        if not hasattr(stream, "seek") or not hasattr(stream, "tell"):
            return
        if hasattr(stream, "seekable") and not stream.seekable():
            return
        position = stream.tell()
        try:
            stream.seek(0, 2)
            length = stream.tell() - position
        finally:
            stream.seek(position)
        self.headers["Content-Length"] = length


def request_site(request):
    """Validate the host, then reject Wagtail's cross-host default-site fallback."""
    hostname, _ = split_domain_port(request.get_host())  # Enforce ALLOWED_HOSTS too.
    site = Site.find_for_request(request)
    if site is None or site.hostname.lower() != hostname:
        return None
    if not ExportPolicy.site_enabled(site):
        return None
    return site


def serve_export(request, path, *, access_method=METHOD_EXPORT_URL):
    """Return a checked response, or None for a miss/veto (HTML fallback seam).

    ``path`` is a logical path, never a backend key. This function always verifies
    request site and current ownership. Only successful page GET selection emits
    ``markdown_served``; this is not evidence that the client received every byte.
    """
    if request.method not in {"GET", "HEAD"}:
        return HttpResponseNotAllowed(["GET", "HEAD"])
    site = request_site(request)
    if site is None:
        return None
    try:
        site_path(path, site.hostname)
        relative = path[len(site.hostname) + 1 :]
        route = export_route(relative)
    except ExportPathError:
        return None
    artifact = (
        ExportArtifact.objects.filter(scope__site_id=site.pk, logical_path=path)
        .select_related("scope", "file")
        .first()
    )
    if artifact is None:
        return None
    if any(hook(request, artifact, site) is False for hook in hooks.get_hooks(SERVE_HOOK)):
        return None
    # Pin metadata to the exact immutable generation that is opened. In particular,
    # a concurrent replacement must not attribute bytes to a different page/scope.
    try:
        stream = FileWriter().open(path, site_id=site.pk, file_id=artifact.file_id)
    except (FileNotFoundError, ExportPathError):
        return None
    try:
        page = (
            Page.objects.filter(pk=artifact.page_id).specific().first()
            if artifact.page_id is not None
            else None
        )
        if artifact.page_id is not None and page is None:
            stream.close()
            return None
        content_type = {
            "export": "text/markdown; charset=utf-8",
            "llms_txt": "text/plain; charset=utf-8",
            "manifest": "application/json; charset=utf-8",
        }[route]
        response = _ExportResponse(stream, content_type=content_type)
        context = {"page": page, "site": site, "path": path, "access_method": access_method}
        for name, value in _headers(request, context).items():
            if value is None or value == "":
                del response[name]
            else:
                response[name] = value
        if request.method == "HEAD":
            stream.close()
            response.streaming_content = ()
        elif page is not None:
            _notify_served(request, artifact, access_method)
        return response
    except Exception:
        stream.close()
        raise


def _headers(request, context):
    content_signal = get_setting("CONTENT_SIGNAL")
    if not isinstance(content_signal, str):
        raise ImproperlyConfigured("WAGTAIL_MARKDOWN_AGENTS CONTENT_SIGNAL must be a string")
    page = context["page"]
    values = {
        "Cache-Control": "private, no-store, max-age=0",
        "Vary": "Accept, User-Agent",
        "Content-Signal": content_signal,
        "X-Markdown-Source": page.full_url if page else None,
    }
    for hook in hooks.get_hooks(HEADERS_HOOK):
        hook(values, request, context)
    validate_headers(values)
    return values


def validate_headers(values):
    """Reject a hook-supplied header map that could not be sent as HTTP headers."""
    for name, value in values.items():
        if not isinstance(name, str) or not HEADER_NAME.fullmatch(name):
            raise ImproperlyConfigured("Markdown response header names must be HTTP tokens")
        if value is not None and (
            not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise ImproperlyConfigured(
                f"Markdown response header {name!r} must be a string without control characters"
            )


def _notify_served(request, artifact, access_method):
    try:
        for receiver, result in markdown_served.send_robust(
            sender=serve_export,
            request=request,
            page_id=artifact.page_id,
            site_id=artifact.scope.site_id,
            path=artifact.logical_path,
            access_method=access_method,
        ):
            if isinstance(result, Exception):
                logger.error("Markdown served receiver %r failed: %s", receiver, result)
    except Exception:
        logger.exception("Markdown response selected, but served notification failed")
