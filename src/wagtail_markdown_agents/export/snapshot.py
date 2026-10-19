"""Batched policy inputs for one fresh site-state calculation, never a persistent cache."""

from django.conf import settings
from django.db.models import BooleanField, Q
from wagtail.models import Page, PageViewRestriction, Site

from ..models import PageAgentSettings
from .policy import excluded_by_attribute


class SiteSnapshot:
    def __init__(self, site):
        root = site.root_page
        roots = (
            list(root.get_translations(inclusive=True))
            if getattr(settings, "WAGTAIL_I18N_ENABLED", False)
            else [root]
        )
        tree_filter = Q()
        related_filter = Q()
        for tree_root in roots:
            tree_filter |= Q(path__startswith=tree_root.path)
            related_filter |= Q(page__path__startswith=tree_root.path)
        self.pages = {}
        for page in Page.objects.filter(tree_filter).select_related("locale").order_by("pk"):
            specific = page.specific_deferred
            # Deferred specific instances do not retain the base row's related
            # field cache on every supported Wagtail version.
            specific.locale = page.locale
            self.pages[page.pk] = specific
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
            for row in PageAgentSettings.objects.filter(related_filter).values(
                "page_id", "excluded", "extra_frontmatter"
            )
        }
        ancestors = [
            tree_root.path[:length]
            for tree_root in roots
            for length in range(Page.steplen, len(tree_root.path), Page.steplen)
        ]
        self._attribute_names = None
        self._attribute_excluded = set()
        self.restricted_paths = set(
            PageViewRestriction.objects.filter(related_filter | Q(page__path__in=ancestors))
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

    def is_excluded_by_attribute(self, page, names):
        """``EXCLUDE_WHEN``, reading boolean fields in one query per page type."""
        names = tuple(names)
        if self._attribute_names != names:
            self._attribute_names = names
            self._attribute_excluded = self._pages_with_flags_set(names)
        if page.pk in self._attribute_excluded:
            return True
        flags = _boolean_fields(type(page))
        return excluded_by_attribute(page, [name for name in names if name not in flags])

    def _pages_with_flags_set(self, names):
        by_model = {}
        for page in self.pages.values():
            by_model.setdefault(type(page), []).append(page.pk)
        pks = set()
        for model, model_pks in by_model.items():
            condition = Q()
            for name in set(names) & _boolean_fields(model):
                condition |= Q(**{name: True})
            if condition:
                rows = model.objects.filter(condition, pk__in=model_pks)
                pks.update(rows.values_list("pk", flat=True))
        return pks

    def has_live_children(self, page):
        return page.path in self.live_parents

    def lineage(self, page, root_depth):
        return [
            self.by_path[page.path[:length]]
            for length in range((root_depth + 1) * Page.steplen, len(page.path) + 1, Page.steplen)
        ]

    def ancestors(self, page):
        return [
            self.by_path[path]
            for length in range(Page.steplen, len(page.path) + 1, Page.steplen)
            if (path := page.path[:length]) in self.by_path
        ]

    def has_sibling_slug(self, page, slug):
        return (page.path[: -Page.steplen], slug) in self.sibling_slugs


def _boolean_fields(model):
    return {
        field.name
        for field in model._meta.concrete_fields
        if isinstance(field, BooleanField) and not field.null
    }
