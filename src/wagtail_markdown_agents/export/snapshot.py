"""Batched policy inputs for one fresh site-state calculation, never a persistent cache."""

from django.conf import settings
from django.db.models import BooleanField, Q
from wagtail.models import Page, PageViewRestriction, Site

from ..models import PageAgentSettings
from .policy import RESERVED_NAMES, excluded_by_attribute

#: Values per ``IN (...)`` lookup, well inside every supported database's limit.
CHUNK = 2000


def _chunks(values):
    values = sorted(values)
    for start in range(0, len(values), CHUNK):
        yield values[start : start + CHUNK]


class SiteSnapshot:
    """Every page of a site's trees, or only the pages one check names.

    ``page_ids`` limits the reading to those pages and their ancestors, with
    just the children, siblings, restrictions and settings that eligibility
    and export paths read for them (#74). Policy answers for those pages are
    the same as from a whole-site reading; other pages are not in it.
    """

    def __init__(self, site, page_ids=None):
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
        ancestors = [
            tree_root.path[:length]
            for tree_root in roots
            for length in range(Page.steplen, len(tree_root.path), Page.steplen)
        ]
        self._attribute_names = None
        self._page_sites = {}
        self._attribute_excluded = set()
        self.sites = {item.pk: item for item in Site.objects.select_related("root_page")}
        if page_ids is None:
            self._read_site(tree_filter, related_filter, ancestors)
        else:
            self._read_pages(set(page_ids), roots, tree_filter, ancestors)

    def _keep(self, rows):
        for page in rows:
            specific = page.specific_deferred
            # Deferred specific instances do not retain the base row's related
            # field cache on every supported Wagtail version.
            specific.locale = page.locale
            self.pages[page.pk] = specific

    def _read_site(self, tree_filter, related_filter, ancestors):
        self.pages = {}
        self._keep(Page.objects.filter(tree_filter).select_related("locale").order_by("pk"))
        self.by_path = {page.path: page for page in self.pages.values()}
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
        self.restricted_paths = set(
            PageViewRestriction.objects.filter(related_filter | Q(page__path__in=ancestors))
            .exclude(restriction_type=PageViewRestriction.NONE)
            .values_list("page__path", flat=True)
        )

    def _read_pages(self, page_ids, roots, tree_filter, ancestors):
        self.pages = {}
        for chunk in _chunks(page_ids):
            self._keep(Page.objects.filter(tree_filter, pk__in=chunk).select_related("locale"))
        named = list(self.pages.values())
        root_paths = [tree_root.path for tree_root in roots]
        lineage = {
            page.path[:length]
            for page in named
            for length in range(Page.steplen, len(page.path), Page.steplen)
            if any(page.path[:length].startswith(path) for path in root_paths)
        } - {page.path for page in named}
        for chunk in _chunks(lineage):
            self._keep(Page.objects.filter(path__in=chunk).select_related("locale"))
        self.by_path = {page.path: page for page in self.pages.values()}
        # Only a named page's own children decide whether it is an index.
        parents = [page.path for page in named if page.numchild]
        self.live_parents = set()
        for path in parents:
            if Page.objects.filter(
                path__startswith=path, depth=len(path) // Page.steplen + 1, live=True
            ).exists():
                self.live_parents.add(path)
        # Siblings matter only where a reserved name has to be mangled.
        reserved = {
            page.path[: -Page.steplen]
            for page in self.pages.values()
            if page.slug in RESERVED_NAMES
        }
        self.sibling_slugs = set()
        for parent in reserved:
            self.sibling_slugs.update(
                (parent, slug)
                for slug in Page.objects.filter(
                    path__startswith=parent, depth=len(parent) // Page.steplen + 1
                ).values_list("slug", flat=True)
            )
        self.settings = {}
        for chunk in _chunks(page_ids):
            self.settings.update(
                (row.pop("page_id"), row)
                for row in PageAgentSettings.objects.filter(page_id__in=chunk).values(
                    "page_id", "excluded", "extra_frontmatter"
                )
            )
        self.restricted_paths = set()
        for chunk in _chunks(set(self.by_path) | set(ancestors)):
            self.restricted_paths.update(
                PageViewRestriction.objects.filter(page__path__in=chunk)
                .exclude(restriction_type=PageViewRestriction.NONE)
                .values_list("page__path", flat=True)
            )

    def site_for_page(self, page):
        # Preserve project routing overrides. Standard get_site merely looks up
        # get_url_parts()[0], so use the already-loaded site objects for that case.
        # Each page is asked several times in one reading (eligibility, path,
        # state), and every answer resolves the page's URL.
        if page.pk not in self._page_sites:
            if type(page).get_site is not Page.get_site:
                site = page.get_site()
            else:
                parts = page.get_url_parts()
                site = self.sites.get(parts[0]) if parts else None
            self._page_sites[page.pk] = site
        return self._page_sites[page.pk]

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
