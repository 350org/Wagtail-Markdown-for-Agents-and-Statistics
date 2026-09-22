"""Core Wagtail lifecycle receivers; connected idempotently by AppConfig.ready()."""

from django.db.models import QuerySet
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from wagtail.models import Page, PageViewRestriction
from wagtail.signals import (
    page_published,
    page_slug_changed,
    page_unpublished,
    post_page_move,
    pre_page_move,
)

from .export.lifecycle import (
    capture_scopes,
    revoke_pages,
    schedule_eligibility_refresh,
    schedule_refresh,
    schedule_relocation,
    subtree_page_ids,
    write_database,
)
from .models import PageAgentSettings


def published(sender, instance, using=None, **kwargs):
    using = write_database(instance, using)
    schedule_refresh([instance.pk], using=using)


def unpublished(sender, instance, using=None, **kwargs):
    using = write_database(instance, using)
    scopes = revoke_pages([instance.pk], using=using)
    schedule_refresh(scopes=scopes, using=using)


def deleting(sender, instance, using=None, **kwargs):
    using = write_database(instance, using)
    scopes = revoke_pages([instance.pk], using=using)
    schedule_refresh(scopes=scopes, using=using)


def moving(
    sender, instance, parent_page_before, url_path_before, url_path_after, using=None, **kwargs
):
    using = write_database(instance, using)
    if url_path_before == url_path_after:
        return
    ids = subtree_page_ids(instance.pk, using=using)
    # Wagtail replaces `instance` between phases, but passes the same before-parent
    # to both signals. Keep the snapshot on that operation-local object, avoiding
    # a global pending-moves registry that would leak on a failed/rolled-back move.
    parent_page_before._agentmd_move = (
        instance.pk,
        url_path_before,
        url_path_after,
        ids,
        capture_scopes(ids, using=using),
    )


def moved(
    sender,
    instance,
    parent_page_before,
    parent_page_after,
    url_path_before,
    url_path_after,
    using=None,
    **kwargs,
):
    using = write_database(instance, using)
    previous = parent_page_before.__dict__.pop("_agentmd_move", None)
    if url_path_before == url_path_after:
        return
    ids = subtree_page_ids(instance.pk, using=using)
    scopes = capture_scopes(ids, using=using)
    if previous and previous[:3] == (instance.pk, url_path_before, url_path_after):
        ids = (*previous[3], *ids)
        for site_id, owners in previous[4].items():
            scopes[site_id] = (*scopes.get(site_id, ()), *owners)
    schedule_relocation(
        ids,
        parent_ids=(parent_page_before.pk, parent_page_after.pk),
        scopes=scopes,
        using=using,
    )


def slug_changed(sender, instance, instance_before, using=None, **kwargs):
    using = write_database(instance, using)
    if instance_before.url_path == instance.url_path:
        return
    # Wagtail emits this after commit. Owned records still retain the old hook
    # paths and storage keys; the old URL cannot reconstruct those locations.
    ids = subtree_page_ids(instance.pk, using=using)
    # A later move in the same transaction can invalidate instance_before.path.
    # Its move callback captures the former parent; resolve this parent afresh.
    current = Page.objects.using(using).filter(pk=instance.pk).first()
    parent = current.get_parent() if current is not None else None
    schedule_relocation(ids, parent_ids=(parent.pk,) if parent else (), using=using)


def _eligibility_field(sender):
    return "restriction_type" if sender is PageViewRestriction else "excluded"


def _blocked(sender, state):
    return state[1] != PageViewRestriction.NONE if sender is PageViewRestriction else state[1]


def eligibility_saving(sender, instance, using=None, raw=False, **kwargs):
    if raw:
        return
    using = write_database(instance, using)
    instance._agentmd_previous_eligibility = (
        sender.objects.using(using)
        .filter(pk=instance.pk)
        .values_list("page_id", _eligibility_field(sender))
        .first()
    )


def _eligibility_change(sender, page_id, *, blocked, using):
    ids = subtree_page_ids(page_id, using=using) if sender is PageViewRestriction else (page_id,)
    if blocked:
        scopes = revoke_pages(ids, using=using)
        schedule_eligibility_refresh(scopes=scopes, using=using)
    else:
        schedule_eligibility_refresh(ids, using=using)


def eligibility_saved(sender, instance, using=None, raw=False, **kwargs):
    if raw:
        return
    using = write_database(instance, using)
    # The instance may contain unsaved eligibility/page values when update_fields
    # saved only metadata. Use the state actually persisted by this write.
    current = (
        sender.objects.using(using)
        .filter(pk=instance.pk)
        .values_list("page_id", _eligibility_field(sender))
        .first()
    )
    if current is None:
        return
    previous = getattr(instance, "_agentmd_previous_eligibility", None)
    if sender is PageAgentSettings and previous == current:
        return  # Ordinary frontmatter edits are not eligibility transitions.
    if _blocked(sender, current):
        _eligibility_change(sender, current[0], blocked=True, using=using)
    elif previous and _blocked(sender, previous) and previous[0] == current[0]:
        _eligibility_change(sender, current[0], blocked=False, using=using)
    # Reassigning the side row also lifts its restriction on the previous page.
    if previous and previous[0] != current[0] and _blocked(sender, previous):
        _eligibility_change(sender, previous[0], blocked=False, using=using)


def eligibility_deleted(sender, instance, using=None, origin=None, **kwargs):
    using = write_database(instance, using)
    if isinstance(origin, Page) or (
        isinstance(origin, QuerySet) and issubclass(origin.model, Page)
    ):
        # Page pre_delete already captured/revoked the scope and scheduled repair.
        # The collector may have removed specific rows before these side rows.
        return
    if _blocked(sender, (instance.page_id, getattr(instance, _eligibility_field(sender)))):
        _eligibility_change(sender, instance.page_id, blocked=False, using=using)


def connect() -> None:
    page_published.connect(published, dispatch_uid="agentmd.page_published")
    page_unpublished.connect(unpublished, dispatch_uid="agentmd.page_unpublished")
    pre_page_move.connect(moving, dispatch_uid="agentmd.pre_page_move")
    post_page_move.connect(moved, dispatch_uid="agentmd.post_page_move")
    page_slug_changed.connect(slug_changed, dispatch_uid="agentmd.page_slug_changed")
    # Django emits the base Page row too when collecting specific page models.
    # Restricting sender avoids duplicate subclass callbacks and non-Page deletes.
    pre_delete.connect(deleting, sender=Page, dispatch_uid="agentmd.page_pre_delete")
    for sender in (PageViewRestriction, PageAgentSettings):
        for signal, receiver, name in (
            (pre_save, eligibility_saving, "pre_save"),
            (post_save, eligibility_saved, "post_save"),
            (post_delete, eligibility_deleted, "post_delete"),
        ):
            signal.connect(
                receiver, sender=sender, dispatch_uid=f"agentmd.{sender.__name__}.{name}"
            )
