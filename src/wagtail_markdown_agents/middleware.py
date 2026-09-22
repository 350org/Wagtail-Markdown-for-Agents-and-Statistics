"""Agent Markdown middleware (#26/#27).

Request phase: when negotiation matches (query-param > Accept header >
User-Agent), serve the page's current published ``.md`` file through the
shared checked serving function. A missing file, an ineligible page, a veto or
any non-page route falls through to normal HTML rendering — never a 404, and
never generation during a request.

Response phase: on an HTML 200 response to a canonical page request whose page
has a current, stored, eligible export, append ``Link: <…>; rel="alternate";
type="text/markdown"`` and merge ``Vary: Accept`` (see ``discovery.py``).
``LINK_HEADER = False`` disables this phase.

Place it after ``SecurityMiddleware`` and before ``CommonMiddleware``, so
negotiated requests are answered before slash-appending redirects and cached
HTML processing; the system check in ``checks.py`` enforces that order.
"""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from .discovery import add_discovery_headers
from .models import ExportArtifact
from .negotiation import detect
from .routing import is_page_read, routed_page
from .serving import serve_export
from .settings import get_setting


class AgentMarkdownMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = negotiated_response(request)
        if response is not None:
            return response
        response = self.get_response(request)
        if get_setting("LINK_HEADER"):
            add_discovery_headers(request, response)
        return response


def negotiated_response(request: HttpRequest) -> HttpResponse | None:
    """The Markdown response for a negotiated canonical page request, else ``None``.

    Candidates are GET/HEAD requests resolving to Wagtail's page-serving route
    (never admin, API, document, preview, form-submission or explicit export
    routes) whose routed page is requested at its canonical URL. The page's
    recorded export is then served through the same site, ownership, policy
    and veto checks as the direct routes; every miss returns ``None``.
    """
    if not is_page_read(request):
        return None
    access_method = detect(request)
    if access_method is None:
        return None
    routed = routed_page(request)
    if routed is None:
        return None
    site, page = routed
    artifact = (
        ExportArtifact.objects.filter(scope__site_id=site.pk, page_id=page.pk)
        .only("logical_path")
        .first()
    )
    if artifact is None:
        return None
    return serve_export(request, artifact.logical_path, access_method=access_method)
