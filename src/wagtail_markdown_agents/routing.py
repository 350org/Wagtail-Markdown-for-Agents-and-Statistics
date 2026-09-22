"""Which requests address a Wagtail page at its canonical URL (#26/#27).

Both middleware phases share this: the request phase to decide whether a
negotiated request may be answered with Markdown, the response phase to decide
whether an HTML response may advertise one. Only GET/HEAD requests outside
previews that resolve to Wagtail's page-serving route, on a policy-enabled site
matching the request host, at the routed page's own URL, are page reads.
"""

from django.http import HttpRequest
from django.urls import Resolver404, resolve
from django.utils.encoding import iri_to_uri
from wagtail.models import Page, Site

from .serving import request_site

#: Wagtail's catch-all page route; the only route the middleware considers.
PAGE_ROUTE_NAME = "wagtail_serve"
SAFE_METHODS = frozenset({"GET", "HEAD"})


def is_page_read(request: HttpRequest) -> bool:
    """GET or HEAD outside a preview: the only requests either phase considers."""
    return request.method in SAFE_METHODS and not getattr(request, "is_preview", False)


def canonical_path(request: HttpRequest) -> str:
    """The request path as Wagtail formats page URLs (percent-encoded)."""
    return iri_to_uri(request.path)


def routed_page_path(request: HttpRequest) -> str | None:
    """The ``path`` argument Wagtail's page route would receive, or ``None``."""
    try:
        match = resolve(request.path_info, urlconf=getattr(request, "urlconf", None))
    except Resolver404:
        return None
    if match.url_name != PAGE_ROUTE_NAME:
        return None
    if match.args:
        return match.args[0]
    return match.kwargs.get("path")


def routed_page(request: HttpRequest, page_path: str | None = None) -> tuple[Site, Page] | None:
    """The enabled site and the page a canonical page-route request addresses.

    Admin, API, document, preview, form-submission and explicit export routes
    never match. RoutablePage sub-routes and paths without a trailing slash do
    not match either: the routed page's own URL must equal the request path.
    Another host cannot borrow the default site's pages.
    """
    if page_path is None:
        page_path = routed_page_path(request)
        if page_path is None:
            return None
    site = request_site(request)
    if site is None:
        return None
    route = Page.route_for_request(request, page_path)
    if route is None:
        return None
    page = route[0]
    if not isinstance(page, Page) or page.get_url(request=request) != canonical_path(request):
        return None
    return site, page
