"""ExportPolicy — the single source of truth for eligibility and paths (#16).

Every consumer — writer, links, indexes, manifests, discovery, middleware and
the direct artefact routes — asks this class, so a page is either exported,
linked, listed and served, or none of those.

``is_eligible(page)`` is deterministic for a page: live and below the tree
root, in an exported site, of an enabled type (``PAGE_TYPES``), free of view
restrictions (password, login or groups, own or inherited), not excluded
through ``PageAgentSettings``, and not vetoed by the
``markdown_export_eligible`` hook. Any request-specific serving veto belongs
in shared serving and is never cached as export eligibility.

``relative_path(page)`` mirrors the URL tree under the site's hostname (never
its port): the site root is ``{hostname}/index.md``, a page with live children
``{hostname}/blog/index.md`` and a leaf ``{hostname}/blog/my-post.md``. The
names ``index`` and ``log`` are reserved at every level: a page slugged
``index`` is written as ``index_``; if a real sibling already owns that slug,
the page's id is appended (``index_42``), so the layout is deterministic and
two pages never share a path. The ``markdown_export_path`` hook may relocate a
page within its site tree.

Hooks (Wagtail's ``hooks.register``; run by ``order``, then registration order):

``markdown_export_eligible(page, site)``
    Return ``False`` to veto; anything else leaves eligibility unchanged. A
    hook can never make an ineligible page eligible.
``markdown_export_path(path, page, site)``
    ``path`` is the site-relative default (``blog/my-post.md``). Return a
    replacement path, or ``None`` to keep it. The result must be a relative
    path with no ``..`` segments ending in ``.md``; it is prefixed with the
    hostname, so a hook cannot move a page outside its site's tree.
"""

from __future__ import annotations

from wagtail import hooks
from wagtail.models import Page, PageViewRestriction, Site

from ..models import PageAgentSettings
from ..settings import get_setting
from .paths import ExportPathError, site_path, validate_path

ELIGIBLE_HOOK = "markdown_export_eligible"
EXPORT_PATH_HOOK = "markdown_export_path"

#: File names the export tree keeps for itself at every level.
RESERVED_NAMES = frozenset({"index", "log"})


class ExportPolicy:
    def __init__(self, snapshot=None):
        self.snapshot = snapshot

    def site_for_page(self, page):
        return self.snapshot.site_for_page(page) if self.snapshot else page.get_site()

    def is_eligible(self, page: Page) -> bool:
        """Whether ``page`` is exported, linked, listed and served as Markdown."""
        if not page.live or page.depth <= 1:
            return False
        site = self.site_for_page(page)
        if site is None or not self.site_enabled(site):
            return False
        if not self._type_enabled(page):
            return False
        restricted = (
            self.snapshot.is_restricted(page)
            if self.snapshot
            else page.get_view_restrictions()
            .exclude(restriction_type=PageViewRestriction.NONE)
            .exists()
        )
        if restricted:
            return False
        excluded = (
            self.snapshot.is_excluded(page)
            if self.snapshot
            else PageAgentSettings.objects.filter(page_id=page.pk, excluded=True).exists()
        )
        if excluded:
            return False
        return all(hook(page, site) is not False for hook in hooks.get_hooks(ELIGIBLE_HOOK))

    def relative_path(self, page: Page) -> str:
        """The page's path in the export tree, ``{hostname}/...md``.

        Computed for ineligible pages too, so a withdrawn page's file can be
        found and deleted.
        """
        site = self.site_for_page(page)
        if site is None:
            raise ExportPathError(f"Page {page.pk} is not within any site's page tree")
        path = self._default_path(page, site)
        for hook in hooks.get_hooks(EXPORT_PATH_HOOK):
            result = hook(path, page, site)
            if result is not None:
                path = _validate_hook_path(result, page)
        return site_path(f"{self.site_prefix(site)}/{path}", site.hostname)

    @staticmethod
    def site_prefix(site: Site) -> str:
        """The site's directory in the export tree: its hostname, never its port."""
        return site.hostname

    def _default_path(self, page: Page, site: Site) -> str:
        root_depth = site.root_page.depth
        lineage = (
            self.snapshot.lineage(page, root_depth)
            if self.snapshot
            else [
                ancestor
                for ancestor in page.get_ancestors(inclusive=True).order_by("path")
                if ancestor.depth > root_depth
            ]
        )
        segments = [_segment(ancestor, self.snapshot) for ancestor in lineage]
        has_children = (
            self.snapshot.has_live_children(page)
            if self.snapshot
            else page.get_children().live().exists()
        )
        if has_children:
            return "/".join([*segments, "index.md"]) if segments else "index.md"
        if not segments:
            return "index.md"
        return "/".join(segments) + ".md"

    @staticmethod
    def site_enabled(site: Site) -> bool:
        sites = get_setting("SITES")
        if sites == "default":
            return site.is_default_site
        if sites == "all":
            return True
        return site.hostname in sites

    @staticmethod
    def _type_enabled(page: Page) -> bool:
        return page_type_enabled(page.specific_class)


def page_type_enabled(model) -> bool:
    """Whether ``PAGE_TYPES`` enables pages of ``model`` (all types when unset)."""
    page_types = get_setting("PAGE_TYPES")
    if page_types is None:
        return True
    return model._meta.label_lower in {label.lower() for label in page_types}


def _segment(page: Page, snapshot=None) -> str:
    """The page's directory or file name: its slug, unless that name is reserved."""
    slug = page.slug
    if slug not in RESERVED_NAMES:
        return slug
    mangled = f"{slug}_"
    collision = (
        snapshot.has_sibling_slug(page, mangled)
        if snapshot
        else page.get_siblings(inclusive=False).filter(slug=mangled).exists()
    )
    if collision:
        mangled = f"{mangled}{page.pk}"
        while (
            snapshot.has_sibling_slug(page, mangled)
            if snapshot
            else page.get_siblings(inclusive=False).filter(slug=mangled).exists()
        ):
            mangled += "_"
    return mangled


def _validate_hook_path(result: object, page: Page) -> str:
    if not isinstance(result, str) or not result:
        raise ExportPathError(
            f"{EXPORT_PATH_HOOK} returned {result!r} for page {page.pk}; expected a relative path"
        )
    validate_path(result)
    if not result.endswith(".md") or result == ".md":
        raise ExportPathError(
            f"{EXPORT_PATH_HOOK} returned {result!r} for page {page.pk}; the path must be "
            "relative to the site's export directory, contain no '..' and end in '.md'"
        )
    return result
