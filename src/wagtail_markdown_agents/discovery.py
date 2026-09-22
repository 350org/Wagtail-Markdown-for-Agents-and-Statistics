"""HTML discovery of Markdown exports (#27/#28).

Browsers keep receiving HTML. When the routed page has a current, eligible
export whose storage object exists, the HTML 200 response gains
``Link: <…>; rel="alternate"; type="text/markdown"`` and ``Vary: Accept``, and
``{% agent_markdown_link %}`` emits the matching ``<link>`` element.

Resolution follows the export policy (site, eligibility and the hook-relocated
path) to the page's published record and checks that record's actual storage
key. The request path is never turned into a storage path: ``blog.md`` versus
``blog/index.md`` and relocated exports are read from the record. Results,
including misses, are cached for ``DISCOVERY_CACHE_TIMEOUT`` seconds under a
key that includes the site's publication version, so every generation,
deletion or relocation (parent leaf/index transitions included) invalidates
them immediately, in every process. The cache only advertises exports; serving
always re-runs the checked path in ``serving.serve_export``.
"""

import hashlib
from collections.abc import Callable

from django.core.cache import cache
from django.http import HttpRequest, HttpResponseBase
from django.urls import NoReverseMatch
from django.utils.cache import patch_vary_headers
from django.utils.functional import SimpleLazyObject
from wagtail import hooks
from wagtail.models import Page, Site

from .export.paths import ExportPathError
from .export.policy import ExportPolicy
from .export.storage import resolve_storage
from .export.writer import FileWriter
from .models import ExportArtifact, ExportScope
from .public_urls import query_alternate, route_url
from .routing import canonical_path, is_page_read, routed_page, routed_page_path
from .serving import request_site, validate_headers
from .settings import get_setting

HEADERS_HOOK = "construct_markdown_html_headers"
CACHE_PREFIX = "wagtail_markdown_agents.discovery"
_MISSING = object()


def add_discovery_headers(request: HttpRequest, response: HttpResponseBase) -> None:
    """Response phase: advertise the routed page's export on an HTML 200 response.

    ``construct_markdown_html_headers(values, request, context)`` hooks may
    change or add headers; setting a value to ``None`` or ``""`` omits it.
    Existing ``Link`` values are kept and ours appended; ``Vary`` is merged.
    """
    if not is_page_read(request) or response.status_code != 200:
        return
    if not response.get("Content-Type", "").lower().startswith("text/html"):
        return
    page_path = routed_page_path(request)
    if page_path is None:
        return
    site = request_site(request)
    if site is None:
        return
    path = canonical_path(request)
    resolved = resolve(site, path, lambda: _route(request, page_path))
    if resolved is None:
        return
    page_id, export_path = resolved
    url = alternate_url_for(site, path, export_path, urlconf=getattr(request, "urlconf", None))
    if url is None:
        return
    values = {"Link": f'<{url}>; rel="alternate"; type="text/markdown"', "Vary": "Accept"}
    context = {
        "site": site,
        "path": path,
        "alternate_url": url,
        "export_path": export_path,
        "page": SimpleLazyObject(lambda: Page.objects.filter(pk=page_id).specific().first()),
    }
    for hook in hooks.get_hooks(HEADERS_HOOK):
        hook(values, request, context)
    validate_headers(values)
    for name, value in values.items():
        if value is None or value == "":
            continue  # Omit ours; a header already on the HTML response is never removed.
        if name.lower() == "vary":
            parts = [part.strip() for part in value.split(",")]
            patch_vary_headers(response, [part for part in parts if part])
        elif name.lower() == "link" and response.has_header("Link"):
            response["Link"] = f"{response['Link']}, {value}"
        else:
            response[name] = value


def _route(request, page_path):
    routed = routed_page(request, page_path)
    return routed[1] if routed else None


def page_alternate_url(page: Page, request: HttpRequest | None = None) -> str | None:
    """The alternate URL advertised for ``page``, or ``None`` (the template tag)."""
    if not isinstance(page, Page) or page.pk is None:
        return None
    policy = ExportPolicy()
    site = policy.site_for_page(page)
    if site is None or not ExportPolicy.site_enabled(site):
        return None
    parts = page.get_url_parts(request=request)
    if parts is None or parts[0] != site.pk or not parts[2]:
        return None
    path = parts[2]
    resolved = resolve(site, path, lambda: page)
    if resolved is None:
        return None
    return alternate_url_for(site, path, resolved[1], urlconf=getattr(request, "urlconf", None))


def resolve(
    site: Site, path: str, resolve_page: Callable[[], Page | None]
) -> tuple[int, str] | None:
    """``(page id, site-relative export path)`` for the page at ``path``, else ``None``.

    Cached per site, canonical path, storage identity and site publication
    version. ``resolve_page`` runs only on a miss. Never use the result to
    authorise serving.
    """
    timeout = get_setting("DISCOVERY_CACHE_TIMEOUT")
    key = _cache_key(site, path) if timeout else None
    if key is not None:
        cached = cache.get(key, _MISSING)
        if cached is not _MISSING:
            return cached
    result = _resolve(site, resolve_page())
    if key is not None:
        cache.set(key, result, timeout)
    return result


def _cache_key(site, path):
    _, alias, fingerprint = resolve_storage()
    version = (
        ExportScope.objects.filter(site_id=site.pk).values_list("version", flat=True).first() or 0
    )
    identity = hashlib.sha256(f"{alias}\n{fingerprint}\n{path}".encode()).hexdigest()
    return f"{CACHE_PREFIX}:{site.pk}:{version}:{identity}"


def _resolve(site, page):
    if not isinstance(page, Page):
        return None
    page = page.specific
    policy = ExportPolicy()
    page_site = policy.site_for_page(page)
    if page_site is None or page_site.pk != site.pk or not policy.is_eligible(page):
        return None
    try:
        logical_path = policy.relative_path(page)
    except ExportPathError:
        return None
    record = (
        ExportArtifact.objects.filter(
            scope__site_id=site.pk, page_id=page.pk, logical_path=logical_path
        )
        .select_related("file", "scope")
        .first()
    )
    if record is None or not FileWriter().object_exists(record):
        return None
    return page.pk, logical_path[len(site.hostname) + 1 :]


def alternate_url_for(site: Site, path: str, export_path: str, *, urlconf=None) -> str | None:
    """Canonical URL plus ``output_format=md`` while query negotiation is on, else the route.

    Returns ``None`` when query negotiation is disabled and the package URLconf
    is not included (system check E006 reports that configuration).
    """
    if get_setting("NEGOTIATE_QUERY_PARAM"):
        return query_alternate(site.root_url + path)
    try:
        return route_url(site, export_path, urlconf=urlconf)
    except (NoReverseMatch, ExportPathError):
        return None
