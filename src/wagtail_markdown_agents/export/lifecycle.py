"""Shared ID-based refresh and revocation helpers for CMS lifecycle events (#23)."""

import logging
from functools import partial

from django.core.exceptions import ImproperlyConfigured
from django.db import DEFAULT_DB_ALIAS, transaction
from django.utils import timezone
from wagtail.models import Page, Site

from .. import tasks
from ..models import ExportArtifact, ExportScope
from ..rendering.page import PageRenderError, unsupported_reason
from ..settings import get_setting
from .indexes import IndexBatch, IndexGenerator
from .llms_txt import LlmsTxtGenerator
from .policy import ExportPolicy
from .writer import FileWriter, _after_commit_required

logger = logging.getLogger(__name__)

#: The withdrawn page indexes one routine refresh rebuilds in the request. Each
#: rebuild reads the whole site twice; beyond this they wait for agentmd_generate.
INDEX_REPAIRS = 3


def write_database(instance=None, using=None):
    """Respect the signal's write alias and the managed writer's primary-only contract."""
    alias = using or (instance._state.db if instance is not None else None) or DEFAULT_DB_ALIAS
    if alias != DEFAULT_DB_ALIAS:
        raise ImproperlyConfigured(
            "The v0.1 export lifecycle requires CMS and export records on the default database"
        )
    return alias


def subtree_page_ids(page_id, *, using=DEFAULT_DB_ALIAS):
    """Capture identities before moves, restrictions or deletion alter the tree."""
    write_database(using=using)
    page = Page.objects.using(using).filter(pk=page_id).first()
    if page is None:
        return ()
    return tuple(page.get_descendants(inclusive=True).values_list("pk", flat=True))


def capture_scopes(page_ids, *, using=DEFAULT_DB_ALIAS):
    """Capture current/recorded sites and former page-index owners, never guessed paths.

    The writer retains actual paths and storage keys. Keep the former index IDs
    before revocation withdraws their pointers, so surviving parents can become
    leaves when their final live child disappears. Values contain only IDs.
    """
    write_database(using=using)
    page_ids = tuple(page_ids)
    site_ids = set(
        ExportArtifact.objects.filter(page_id__in=page_ids).values_list("scope__site_id", flat=True)
    )
    for page in Page.objects.using(using).filter(pk__in=page_ids).specific():
        site = page.get_site()
        if site is not None and ExportPolicy.site_enabled(site):
            site_ids.add(site.pk)
    return {
        site_id: tuple(
            ExportArtifact.objects.filter(
                scope__site_id=site_id,
                page_id__isnull=False,
                logical_path__endswith="/index.md",
            ).values_list("page_id", flat=True)
        )
        for site_id in sorted(site_ids)
    }


def revoke_pages(page_ids, *, using=DEFAULT_DB_ALIAS):
    """Withdraw owned files and dependencies synchronously; safe inside a transaction.

    Returns captured scopes for optional after-commit discovery repair. Revocation
    does not consult AUTO_GENERATE or enqueue a task, and failures propagate.
    """
    write_database(using=using)
    page_ids = tuple(dict.fromkeys(page_ids))
    scopes = capture_scopes(page_ids, using=using)
    if scopes:
        writer = FileWriter()
        for site_id in scopes:
            for page_id in page_ids:
                writer.delete_page(page_id, site_id=site_id)
    return scopes


def schedule_refresh(page_ids=(), *, scopes=None, using=DEFAULT_DB_ALIAS):
    """Queue identifiers only after successful commit; used by routine lifecycle events."""
    write_database(using=using)
    if not get_setting("AUTO_GENERATE"):
        return
    page_ids = tuple(dict.fromkeys(page_ids))
    captured = capture_scopes(page_ids, using=using) if scopes is None else scopes
    # Copy caller-owned containers before deferral; no model instances survive.
    captured = {site_id: tuple(owners) for site_id, owners in captured.items()}
    if captured:
        transaction.on_commit(partial(_enqueue_refresh, page_ids, captured, using), using=using)


def _enqueue_refresh(page_ids, scopes, using):
    try:
        tasks.enqueue(refresh_pages, page_ids=page_ids, scopes=scopes, using=using, automatic=True)
    except Exception:
        # The CMS transaction has committed. Never imply that it rolled back,
        # and never finalise a failed batch as a successful manifest publication.
        logger.exception(
            "Markdown lifecycle refresh failed for page IDs %s, scopes %s", page_ids, scopes
        )


def schedule_relocation(page_ids, *, parent_ids=(), scopes=None, using=DEFAULT_DB_ALIAS):
    """Retire the old subtree after commit, then queue current published content.

    Cleanup runs inline even with AUTO_GENERATE disabled or a deferred task backend.
    The writer owns the actual previous paths/keys, including hook relocations.
    Parent IDs also cover leaf transitions when a hook does not use index.md.
    """
    write_database(using=using)
    page_ids = tuple(dict.fromkeys(page_ids))
    parent_ids = tuple(dict.fromkeys(parent_ids))
    captured = capture_scopes(page_ids, using=using) if scopes is None else scopes
    captured = {site_id: tuple(owners) for site_id, owners in captured.items()}
    transaction.on_commit(
        partial(_relocate_pages, page_ids, parent_ids, captured, using), using=using
    )


def _relocate_pages(page_ids, parent_ids, scopes, using):
    try:
        # Site roots may themselves be below a moved/renamed page. Resolve their
        # current URL paths before evaluating ownership or building discovery.
        Site.clear_site_root_paths_cache()
        captured = {site_id: set(owners) for site_id, owners in scopes.items()}
        for site_id, owners in revoke_pages(page_ids, using=using).items():
            captured.setdefault(site_id, set()).update(owners)
        schedule_refresh((*page_ids, *parent_ids), scopes=captured, using=using)
    except Exception:
        logger.exception("Markdown subtree relocation failed for page IDs %s", page_ids)


def schedule_eligibility_refresh(page_ids=(), *, scopes=None, using=DEFAULT_DB_ALIAS):
    """Restore privacy transitions inline after commit, never through a task backend.

    AUTO_GENERATE still controls automatic restoration/discovery repair. Withdrawal
    must already have happened synchronously, independently of this helper.
    """
    write_database(using=using)
    if not get_setting("AUTO_GENERATE"):
        return
    page_ids = tuple(dict.fromkeys(page_ids))
    captured = capture_scopes(page_ids, using=using) if scopes is None else scopes
    captured = {site_id: tuple(owners) for site_id, owners in captured.items()}
    if captured:
        transaction.on_commit(partial(_eligibility_refresh, page_ids, captured, using), using=using)


def _eligibility_refresh(page_ids, scopes, using):
    try:
        # Pages may be deleted after scheduling. Omit them after commit so shared
        # discovery repair can skip a prior repair by the deletion callback.
        existing = set(
            Page.objects.using(using).filter(pk__in=page_ids).values_list("pk", flat=True)
        )
        refresh_pages(
            [page_id for page_id in page_ids if page_id in existing],
            scopes=scopes,
            using=using,
            automatic=True,
        )
    except Exception:
        logger.exception(
            "Markdown eligibility refresh failed for page IDs %s, scopes %s", page_ids, scopes
        )


def revoke_ineligible(*, using=DEFAULT_DB_ALIAS):
    """Reconcile owned page IDs against current policy after deploy/bulk changes.

    Synchronous and revocation-only, regardless of AUTO_GENERATE. No startup DB
    queries, broad generation, storage traversal or configuration history required.
    Returns the IDs selected for withdrawal; storage failures retain retry inventory.
    """
    write_database(using=using)
    owned = set(ExportArtifact.objects.exclude(page_id=None).values_list("page_id", flat=True))
    policy = ExportPolicy()
    eligible = {
        page.pk
        for page in Page.objects.using(using).filter(pk__in=owned).specific()
        if policy.is_eligible(page)
    }
    revoked = tuple(sorted(owned - eligible))
    revoke_pages(revoked, using=using)
    return revoked


def _routine_refresh(page_ids, captured, *, using):
    """Refresh what a CMS event changed, never the whole site (#69).

    Runs inside the editor's request when tasks run inline, so it must not
    grow with the size of the site. It regenerates the given pages, then any
    parent or former index owner with no export at its current path: a parent
    that gained its first or lost its last child, or an index a revocation
    withdrew (at most ``INDEX_REPAIRS`` of them). Other indexes, llms.txt and
    the manifest keep their last build until ``agentmd_generate`` or an
    explicit refresh finalises the site.
    """
    writer = FileWriter()
    generator = IndexGenerator(writer)
    policy = ExportPolicy()
    results = []
    owners = {owner for owners in captured.values() for owner in owners}
    parents = set()
    done = set()
    # Deepest first, so a moved section's index lists its children at their
    # new paths.
    depths = dict(Page.objects.using(using).filter(pk__in=page_ids).values_list("pk", "depth"))
    for page_id in sorted(page_ids, key=lambda page_id: (-depths.get(page_id, 0), page_id)):
        page = Page.objects.using(using).filter(pk=page_id).specific().first()
        if page is None or not policy.is_eligible(page):
            for site_id in captured:
                _withdraw(writer, page_id, site_id)
            continue
        site = policy.site_for_page(page)
        for site_id in captured:
            if site_id != site.pk:
                _withdraw(writer, page_id, site_id)
        parent = page.get_parent()
        if parent is not None:
            parents.add(parent.pk)
        try:
            results.append(_regenerate(writer, generator, policy, page))
            done.add(page.pk)
        except PageRenderError as exc:
            if exc.reason not in {"unsupported_page", "empty_body"}:
                raise
            _withdraw(writer, page.pk, site.pk)
            logger.warning("Skipped Markdown page %s: %s", page.pk, exc.reason)
    # Former owners still holding an export kept their index: only one that
    # lost its last child or was moved loses it, through revocation. Checking
    # just the withdrawn ones keeps this independent of the number of indexes.
    owners.difference_update(
        ExportArtifact.objects.filter(page_id__in=owners).values_list("page_id", flat=True)
    )
    candidates = (owners | parents).difference(page_ids)
    repairs = sorted(
        _needs_repair(candidates, using=using), key=lambda page: (-page.depth, page.pk)
    )
    # A revocation withdraws the one index that listed the page, so a routine
    # event leaves an index or two to rebuild. More than that means the
    # revocation withdrew navigation wholesale: files from an earlier version
    # record no pages and count as naming them all, as does revoking the
    # site's root page. Rebuilding every index of the site cannot fit in a
    # request (#69), so those wait for agentmd_generate. A former owner that
    # is now a leaf is one page render, and is always repaired.
    indexes = [page for page in repairs if policy.relative_path(page).endswith("/index.md")]
    if len(indexes) > INDEX_REPAIRS:
        logger.warning(
            "Left %s withdrawn Markdown indexes for agentmd_generate to rebuild", len(indexes)
        )
        repairs = [page for page in repairs if page not in indexes]
    for page in repairs:
        try:
            results.append(_regenerate(writer, generator, policy, page))
            done.add(page.pk)
        except PageRenderError as exc:
            if exc.reason not in {"unsupported_page", "empty_body"}:
                raise
            logger.warning("Skipped Markdown page %s: %s", page.pk, exc.reason)
    for site in Site.objects.using(using).filter(pk__in=captured).select_related("root_page"):
        if ExportPolicy.site_enabled(site):
            results.extend(_refresh_top_level(writer, generator, policy, site, done, page_ids))
    return results


def _refresh_top_level(writer, generator, policy, site, done, page_ids):
    """Keep llms.txt and the root index current when the top level changes (#69).

    Both name only the site's top-level pages, so a post never changes them and
    this costs two small queries. When a top-level page was published, or a
    revocation withdrew llms.txt, both are rebuilt: a few entries, read from the
    database with one reading of the site.
    """
    host = site.hostname
    named = set()
    llms = None
    for path, lists in ExportArtifact.objects.filter(
        scope__site_id=site.pk, logical_path__in=[f"{host}/llms.txt", f"{host}/index.md"]
    ).values_list("logical_path", "lists"):
        named.update(lists or ())
        if path == f"{host}/llms.txt":
            llms = lists
    # A top-level page's path is host/page.md or host/page/index.md; the root
    # index itself is not one of llms.txt's entries.
    top_level = any(
        path != f"{host}/index.md"
        and (path.count("/") == 1 or path == f"{host}/{path.split('/')[1]}/index.md")
        for path in ExportArtifact.objects.filter(
            scope__site_id=site.pk, page_id__in=page_ids
        ).values_list("logical_path", flat=True)
    )
    # llms.txt links the root index under a fixed label, so editing the home
    # page leaves it as it is.
    named.discard(site.root_page_id)
    if llms is not None and not top_level and not named.intersection(page_ids):
        return []
    results = []
    home = site.root_page.specific
    if (
        home.pk not in done
        and policy.is_eligible(home)
        and policy.relative_path(home) == f"{host}/index.md"
    ):
        try:
            results.append(generator.regenerate(home))
        except PageRenderError as exc:
            if exc.reason not in {"unsupported_page", "empty_body"}:
                raise
    discovery = LlmsTxtGenerator(writer).generate(site.pk)
    if discovery is not None:
        results.append(discovery)
    return results


def _withdraw(writer, page_id, site_id):
    """Revoke a page's export, if it has one.

    Revocation withdraws the site's discovery files, which a routine refresh
    does not rebuild, so a page that was never exported (a form page, say)
    must not cost the site its llms.txt and manifest.
    """
    if ExportArtifact.objects.filter(scope__site_id=site_id, page_id=page_id).exists():
        writer.delete_page(page_id, site_id=site_id)


def _regenerate(writer, generator, policy, page):
    if policy.relative_path(page).endswith("/index.md"):
        return generator.regenerate(page)
    return writer.generate(page)


def _needs_repair(page_ids, *, using):
    """The live, eligible, supported pages among ``page_ids`` with no export
    at their path.

    A page has none when revocation withdrew its index or its path moved
    between a leaf and an index. An export that is merely out of date (after a
    settings change, say) is left for ``agentmd_generate``: repairing every
    such index here would rebuild the whole site inside one request.
    """
    pages = list(Page.objects.using(using).filter(pk__in=page_ids, live=True).specific())
    if not pages:
        return []
    recorded = {}
    for page_id, path in ExportArtifact.objects.filter(page_id__in=page_ids).values_list(
        "page_id", "logical_path"
    ):
        recorded.setdefault(page_id, set()).add(path)
    policy = ExportPolicy()
    return [
        page
        for page in pages
        if not unsupported_reason(type(page))
        and policy.is_eligible(page)
        and policy.relative_path(page) not in recorded.get(page.pk, ())
    ]


def request_refresh(site_ids, *, using=DEFAULT_DB_ALIAS):
    """Mark every page export of these sites for rebuilding, rendering nothing now.

    For a change that alters every page's Markdown without a page revision,
    such as a site setting the renderers read. Rebuilding thousands of pages
    cannot fit in the request that saved the setting (#69), so the current
    exports stay served and the next ``agentmd_generate`` rebuilds those
    published before this call, without ``--force``.
    """
    write_database(using=using)
    now = timezone.now()
    for site_id in sorted(set(site_ids)):
        ExportScope.objects.get_or_create(site_id=site_id)
        ExportScope.objects.filter(site_id=site_id).update(stale_before=now)


def navigation_behind(site):
    """Whether a page export is newer than the site's navigation.

    A routine publication leaves most indexes and the manifest as they were
    (#69). A finalisation records when it finished, so any page export
    published after that is missing from the navigation.
    """
    finalised = (
        ExportScope.objects.filter(site_id=site.pk).values_list("finalised_at", flat=True).first()
    )
    if finalised is None:
        return True
    return ExportArtifact.objects.filter(
        scope__site_id=site.pk, page_id__isnull=False, published_at__gt=finalised
    ).exists()


def refresh_pages(page_ids=(), *, scopes=None, using=DEFAULT_DB_ALIAS, automatic=False):
    """Refresh current published pages and finalise each affected site once.

    Direct callers run after commit and receive exceptions on real build errors.
    They can select related pages explicitly (or a whole subtree/site) for bounded
    v0.1 dependency refresh. Signal tasks set automatic=True to honour a later
    AUTO_GENERATE disable. Supplied scopes repair discovery after revocation even
    when every requested page has since been deleted.
    """
    write_database(using=using)
    _after_commit_required()
    if automatic and not get_setting("AUTO_GENERATE"):
        return []
    page_ids = tuple(dict.fromkeys(page_ids))
    captured = {site_id: set(owners) for site_id, owners in (scopes or {}).items()}
    for site_id, owners in capture_scopes(page_ids, using=using).items():
        captured.setdefault(site_id, set()).update(owners)
    if not captured:
        return []
    if automatic:
        return _routine_refresh(page_ids, captured, using=using)
    writer = FileWriter()
    batch = IndexBatch(writer)
    for site in Site.objects.filter(pk__in=captured):
        if ExportPolicy.site_enabled(site):
            batch.mark_dirty(site.pk, page_ids=captured[site.pk])
    if not batch.dirty and not page_ids:
        return []
    results = []
    policy = ExportPolicy()
    for page_id in page_ids:
        page = Page.objects.using(using).filter(pk=page_id).specific().first()
        if page is None or not policy.is_eligible(page):
            for site_id in captured:
                writer.delete_page(page_id, site_id=site_id)
            continue
        site = policy.site_for_page(page)
        for site_id in captured:
            if site_id != site.pk:
                writer.delete_page(page_id, site_id=site_id)
        if policy.relative_path(page).endswith("/index.md"):
            # IndexGenerator publishes complete page bodies plus navigation and
            # can safely take over a slot previously owned by a standalone index.
            batch.mark_dirty(site.pk, page_ids=[page_id])
            continue
        try:
            results.append(batch.generate(page))
        except PageRenderError as exc:
            if exc.reason not in {"unsupported_page", "empty_body"}:
                raise
            batch.delete_page(page_id, site_id=site.pk)
            logger.warning("Skipped Markdown page %s: %s", page_id, exc.reason)
    results.extend(batch.finalise())
    return results
