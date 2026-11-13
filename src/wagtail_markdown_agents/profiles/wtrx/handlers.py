"""Refresh site exports after committed 350.org integration-setting changes.

Donation defaults and the ActionKit hostname come from the site's
IntegrationSettings, so a change there changes every page that shows them.
The change marks the site's exports for the next ``agentmd_generate``.
"""

import logging
from functools import partial

from django.apps import apps
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from wagtail.models import Site

from wagtail_markdown_agents import tasks
from wagtail_markdown_agents.export.lifecycle import request_refresh, write_database
from wagtail_markdown_agents.export.policy import ExportPolicy
from wagtail_markdown_agents.export.storage import digest
from wagtail_markdown_agents.settings import get_setting

logger = logging.getLogger(__name__)


def _state(sender, instance, using):
    # Read persisted values: update_fields may leave the instance holding edits
    # that this save did not write. Retain a digest, never credential-bearing data.
    row = sender.objects.using(using).filter(pk=instance.pk).only("site", "integrations").first()
    if row is None:
        return None
    data = sender._meta.get_field("integrations").get_prep_value(row.integrations)
    return row.site_id, digest(data), bool(data)


def settings_saving(sender, instance, using=None, raw=False, **kwargs):
    if raw or not get_setting("AUTO_GENERATE"):
        return
    using = write_database(instance, using)
    instance._agentmd_integration_state = _state(sender, instance, using)


def settings_saved(sender, instance, using=None, raw=False, **kwargs):
    if raw or not get_setting("AUTO_GENERATE"):
        return
    using = write_database(instance, using)
    previous = instance.__dict__.pop("_agentmd_integration_state", None)
    current = _state(sender, instance, using)
    if current is None or previous == current:
        return
    # BaseSiteSetting.for_site() creates an empty row on first read, including
    # during rendering. It introduces no configuration change and must not recurse.
    if previous is None and not current[2]:
        return
    site_ids = {current[0]}
    if previous:
        site_ids.add(previous[0])
    _schedule(site_ids, using)


def settings_deleted(sender, instance, using=None, **kwargs):
    if get_setting("AUTO_GENERATE"):
        _schedule({instance.site_id}, write_database(instance, using))


def _schedule(site_ids, using):
    # Only identities cross the commit/task boundary. Reload pages and settings
    # at execution time, so a later committed edit wins over a queued snapshot.
    transaction.on_commit(partial(_enqueue, tuple(sorted(site_ids)), using), using=using)


def _enqueue(site_ids, using):
    try:
        tasks.enqueue(refresh_sites, site_ids=site_ids, using=using)
    except Exception:
        # The settings save is committed; never report it as a failed transaction.
        logger.exception("Markdown integration-settings refresh failed for site IDs %s", site_ids)


def refresh_sites(*, site_ids, using="default"):
    """Mark the sites' exports for the next ``agentmd_generate``, rendering nothing.

    Every page can show these settings, and re-rendering a large site's pages
    in the request that saved them cannot finish before the web server's
    timeout (#69). The current exports stay served until that run.
    """
    write_database(using=using)
    if not get_setting("AUTO_GENERATE"):
        return
    enabled = [
        site.pk
        for site in Site.objects.using(using).filter(pk__in=site_ids)
        if ExportPolicy.site_enabled(site)
    ]
    if enabled:
        request_refresh(enabled, using=using)


def ready():
    """Connect the handlers; the profile loader calls this once at startup."""
    model = apps.get_model("wtrx", "IntegrationSettings")
    for signal, receiver, name in (
        (pre_save, settings_saving, "pre_save"),
        (post_save, settings_saved, "post_save"),
        (post_delete, settings_deleted, "post_delete"),
    ):
        signal.connect(receiver, sender=model, dispatch_uid=f"agentmd.wtrx.settings.{name}")
