"""Batched policy inputs for one fresh site-state calculation, never a persistent cache."""

from django.db.models import Q
from wagtail.models import Page, PageViewRestriction, Site

from ..models import PageAgentSettings


class SiteSnapshot:
    def __init__(self, site):
        root = site.root_page
        self.pages = {
            page.pk: page
            for page in root.get_descendants(inclusive=True).order_by("pk").specific(defer=True)
        }
        self.by_path = {page.path: page for page in self.pages.values()}
        self.sites = {item.pk: item for item in Site.objects.select_related("root_page")}
        self.live_parents = {
            page.path[: -Page.steplen] for page in self.pages.values() if page.live
        }
        self.sibling_slugs = {
            (page.path[: -Page.steplen], page.slug) for page in self.pages.values()
        }
        self.settings = {
            row.pop("page_id"): row
            for row in PageAgentSettings.objects.filter(page__path__startswith=root.path).values(
                "page_id", "excluded", "extra_frontmatter"
            )
        }
        ancestors = [
            root.path[:length] for length in range(Page.steplen, len(root.path), Page.steplen)
        ]
        self.restricted_paths = set(
            PageViewRestriction.objects.filter(
                Q(page__path__startswith=root.path) | Q(page__path__in=ancestors)
            )
            .exclude(restriction_type=PageViewRestriction.NONE)
            .values_list("page__path", flat=True)
        )

    def site_for_page(self, page):
        # Preserve project routing overrides. Standard get_site merely looks up
        # get_url_parts()[0], so use the already-loaded site objects for that case.
        if type(page).get_site is not Page.get_site:
            return page.get_site()
        parts = page.get_url_parts()
        return self.sites.get(parts[0]) if parts else None

    def is_restricted(self, page):
        return any(
            page.path[:length] in self.restricted_paths
            for length in range(Page.steplen, len(page.path) + 1, Page.steplen)
        )

    def is_excluded(self, page):
        return self.settings.get(page.pk, {}).get("excluded", False)

    def has_live_children(self, page):
        return page.path in self.live_parents

    def lineage(self, page, root_depth):
        return [
            self.by_path[page.path[:length]]
            for length in range((root_depth + 1) * Page.steplen, len(page.path) + 1, Page.steplen)
        ]

    def has_sibling_slug(self, page, slug):
        return (page.path[: -Page.steplen], slug) in self.sibling_slugs
