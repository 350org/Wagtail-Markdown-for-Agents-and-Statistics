"""Synthetic fixture corpus and published-only preview adapter for local verification."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404
from wagtail.models import Page, PageViewRestriction

from wagtail_markdown_agents.export.indexes import IndexBatch
from wagtail_markdown_agents.export.writer import FileWriter
from wagtail_markdown_agents.models import ExportArtifact, PageAgentSettings
from wagtail_markdown_agents.public_urls import export_url
from wagtail_markdown_agents.routing import routed_page
from wagtail_markdown_agents.settings import get_setting

from .models import ArticlePage

PREVIEW_PATH = "/simulator/preview/"


class PublishedPreviewMiddleware:
    """Exercise the preview guard before negotiation, then Wagtail's preview renderer.

    Only the fixed synthetic page's published revision is available, never a draft
    or a user-selected page ID. This middleware is absent from normal settings.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            getattr(settings, "SIMULATOR_FIXTURES_ENABLED", False)
            and request.path_info == PREVIEW_PATH
            and request.GET.get("preview") == "1"
            and request.method in {"GET", "HEAD"}
        ):
            request.is_preview = True
            request._simulator_preview = True
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not getattr(request, "_simulator_preview", False):
            return None
        routed = routed_page(request)
        if routed is None:
            raise Http404
        _, page = routed
        if not page.live or not page.live_revision_id or page.get_view_restrictions().exists():
            raise Http404
        published = page.live_revision.as_object()
        if not isinstance(published, ArticlePage):
            raise Http404
        return published.serve_preview(request, "")


def create_fixtures(site):
    """Create once in an isolated sandbox; refuse to overwrite existing content."""
    if not getattr(settings, "SIMULATOR_FIXTURES_ENABLED", False) or get_setting("AUTO_GENERATE"):
        raise ImproperlyConfigured("Use sandbox.simulator_settings with automatic generation off")
    home = site.root_page
    if home.get_children().filter(slug="simulator").exists():
        raise ValueError("The simulator branch already exists; use a fresh fixture database")

    branch = home.add_child(instance=Page(title="Simulator fixtures", slug="simulator"))
    branch.save_revision().publish()

    def article(slug, parent=branch):
        page = parent.add_child(
            instance=ArticlePage(
                title=f"Simulator {slug}",
                slug=slug,
                body=[("paragraph", f"<p>Synthetic published {slug} content.</p>")],
            )
        )
        page.save_revision().publish()
        return page

    fallback = article("fallback")  # Deliberately never generated.
    excluded = article("excluded")
    preview = article("preview")
    missing = article("missing")
    private = article("private")
    navigation = branch.add_child(instance=Page(title="Navigation", slug="navigation"))
    navigation.save_revision().publish()
    child = article("public-child", navigation)

    PageAgentSettings.objects.create(page=excluded, excluded=True)
    PageViewRestriction.objects.create(page=private, restriction_type="login")
    writer = FileWriter()
    batch = IndexBatch(writer)
    for page in (preview, child):
        batch.generate(page)
    batch.finalise()
    nav_record = ExportArtifact.objects.get(
        scope__site_id=site.pk, logical_path=f"{site.hostname}/simulator/navigation/index.md"
    )
    if nav_record.page_id is not None:
        raise ValueError("Navigation fixture unexpectedly owns a page")

    def check(kind, url, page=None, status=200, content_type="text/html", method="ua"):
        return {
            "kind": kind,
            "url": url,
            "page_id": page.pk if page else None,
            "status": status,
            "content_type": content_type,
            "access_method": method,
        }

    return {
        "checks": [
            check("fallback", fallback.full_url, fallback),
            check("excluded", excluded.full_url, excluded),
            check("preview", preview.full_url + "?preview=1", preview),
            check(
                "missing-export",
                site.root_url + "/markdown/simulator/missing.md",
                missing,
                status=404,
                method="export-url",
            ),
            check(
                "private-export",
                site.root_url + "/markdown/simulator/private.md",
                private,
                status=404,
                method="export-url",
            ),
            check(
                "navigation-index",
                export_url(nav_record),
                content_type="text/markdown",
                method="export-url",
            ),
        ],
    }
