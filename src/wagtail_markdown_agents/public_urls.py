"""Public URLs for owned records; callers still apply current export eligibility."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.urls import reverse
from wagtail.models import Page, Site

from .export.paths import ExportPathError, site_path
from .models import ExportArtifact
from .negotiation import QUERY_PARAM
from .settings import get_setting

NAMESPACE = "wagtail_markdown_agents"


def export_route(path):
    """The route name for a site-relative, publicly supported artefact path."""
    if path == "llms.txt":
        return "llms_txt"
    if path == "manifest.json":
        return "manifest"
    if path.endswith(".md") and path != ".md":
        return "export"
    raise ExportPathError("Only Markdown, site llms.txt and site manifest.json are public")


def route_url(site, path, *, urlconf=None):
    """Absolute URL for a site-relative artefact path through the included routes.

    Formats only: no ownership, eligibility or existence check. Raises
    ``NoReverseMatch`` when ``wagtail_markdown_agents.urls`` is not included.
    """
    name = export_route(path)
    kwargs = {"export_path": path} if name == "export" else {}
    return site.root_url + reverse(f"{NAMESPACE}:{name}", kwargs=kwargs, urlconf=urlconf)


def query_alternate(canonical):
    """The canonical HTML URL asking for Markdown through the query trigger."""
    parts = urlsplit(canonical)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key != QUERY_PARAM
    ]
    query.append((QUERY_PARAM, "md"))
    return urlunsplit(parts._replace(query=urlencode(query)))


def export_url(artifact, *, urlconf=None):
    """Absolute URL from the configured site origin and included named route.

    The record must still own its pointer. This formats URLs, not serving
    authorisation or a storage-existence check; readers always recheck state.
    ``urlconf`` supports offline generation for projects with a custom URLconf.
    """
    if not ExportArtifact.objects.filter(pk=artifact.pk, file_id=artifact.file_id).exists():
        raise ExportPathError("The export record no longer owns a published file")
    site = Site.objects.get(pk=artifact.scope.site_id)
    site_path(artifact.logical_path, site.hostname)
    return route_url(site, artifact.logical_path[len(site.hostname) + 1 :], urlconf=urlconf)


def alternate_url(artifact, *, urlconf=None):
    """Page alternate URL; aggregates always use their explicit export route."""
    direct = export_url(artifact, urlconf=urlconf)
    if artifact.page_id is None or not get_setting("NEGOTIATE_QUERY_PARAM"):
        return direct
    page = Page.objects.filter(pk=artifact.page_id).specific().first()
    canonical = page.full_url if page else None
    if not canonical:
        return direct
    return query_alternate(canonical)
