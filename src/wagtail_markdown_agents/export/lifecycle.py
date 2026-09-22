"""Shared ID-based refresh and revocation helpers for CMS lifecycle events (#23)."""

import logging
from functools import partial

from django.core.exceptions import ImproperlyConfigured
from django.db import DEFAULT_DB_ALIAS, transaction
from wagtail.models import Page, Site

from .. import tasks
from ..models import ExportArtifact
from ..rendering.page import PageRenderError
from ..settings import get_setting
from .indexes import IndexBatch
from .policy import ExportPolicy
from .writer import FileWriter, _after_commit_required

logger = logging.getLogger(__name__)


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
        if page.live_revision_id and policy.is_eligible(page)
    }
    revoked = tuple(sorted(owned - eligible))
    revoke_pages(revoked, using=using)
    return revoked


def _discovery_current(writer, site, owners):
    """A prior callback may already have repaired this cascade's shared artefacts.

    Check former index owners too: a publish callback could have finalised a
    manifest before a deletion callback repairs a missing parent leaf.
    """
    if not all(
        writer.exists(f"{site.hostname}/{name}")
        for name in ("index.md", "llms.txt", "manifest.json")
    ):
        return False
    records = list(ExportArtifact.objects.filter(scope__site_id=site.pk, page_id__in=owners))
    return len(records) == len(owners) and all(
        writer.exists(record.logical_path) for record in records
    )


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
    writer = FileWriter()
    batch = IndexBatch(writer)
    for site in Site.objects.filter(pk__in=captured):
        if ExportPolicy.site_enabled(site):
            if automatic and not page_ids and _discovery_current(writer, site, captured[site.pk]):
                continue
            batch.mark_dirty(site.pk, page_ids=captured[site.pk])
    if not batch.dirty and not page_ids:
        return []
    results = []
    policy = ExportPolicy()
    for page_id in page_ids:
        page = Page.objects.using(using).filter(pk=page_id).specific().first()
        if page is None or not page.live_revision_id or not policy.is_eligible(page):
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
