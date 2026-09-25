"""Committed integration edits rebuild actual exports using fresh offline settings."""

import json

import pytest
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models.signals import post_save
from wagtail import hooks
from wagtail.contrib.settings.registry import Registry
from wagtail.models import Locale, Page, PageViewRestriction, Site
from wtrx.blocks import DonateBlock
from wtrx.models import ContentPage, HomePage, IntegrationSettings

from tests.test_indexes import read
from wagtail_markdown_agents import tasks
from wagtail_markdown_agents.contrib.wtrx import handlers
from wagtail_markdown_agents.export.indexes import IndexBatch
from wagtail_markdown_agents.export.state import StaleBuild
from wagtail_markdown_agents.export.writer import FileWriter
from wagtail_markdown_agents.models import ExportArtifact
from wagtail_markdown_agents.rendering import render_block

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.export_lifecycle]


def config(hostname, enabled=True):
    return [("actionkit", {"hostname": hostname, "enabled": enabled})]


@pytest.fixture(params=["filesystem", "remote"])
def setup(request, settings, tmp_path, monkeypatch):
    settings.BASE_DIR = tmp_path
    settings.STORAGES = {
        **settings.STORAGES,
        "exports": {"BACKEND": "tests.storage_backend.RemoteStorage"},
    }
    options = {"SITES": "all"}
    if request.param == "remote":
        options["STORAGE"] = "exports"
    settings.WAGTAIL_MARKDOWN_AGENTS = {**options, "AUTO_GENERATE": False}
    # Keep the base sandbox contract unchanged; this fixture enables the real
    # site-bound SettingProxy for the synthetic registered IntegrationSettings.
    installed = apps.is_installed
    monkeypatch.setattr(
        apps, "is_installed", lambda name: name == "wagtail.contrib.settings" or installed(name)
    )
    registry = Registry()
    registry.append(IntegrationSettings)
    monkeypatch.setattr("wagtail.contrib.settings.registry.registry", registry)
    monkeypatch.setattr("wagtail.contrib.settings.context_processors.registry", registry)
    locale, _ = Locale.objects.get_or_create(language_code="en")
    root = Page.get_first_root_node() or Page.add_root(title="Root", slug="root", locale=locale)
    home = root.add_child(
        instance=HomePage(
            title="Home",
            slug="settings-home",
            body=[("text", "<p>Home body.</p>")],
            hero_cta=[("signup", {"short_form_id": "home-campaign"})],
        )
    )
    Site.objects.all().delete()
    site = Site.objects.create(hostname="example.org", root_page=home, is_default_site=True)
    integration = IntegrationSettings.objects.create(
        site=site, integrations=config("old.example.org")
    )
    page = home.add_child(
        instance=ContentPage(
            title="Campaign",
            slug="campaign",
            body=[
                ("text", "<p>Published copy.</p>"),
                ("signup_actionkit", {"short_form_id": "campaign-one"}),
            ],
        )
    )
    home.save_revision().publish()
    page.save_revision().publish()
    page.refresh_from_db()
    settings.WAGTAIL_MARKDOWN_AGENTS = options
    handlers.refresh_sites(site_ids=(site.pk,))
    yield FileWriter(), site, home, page, integration
    Site.clear_site_root_paths_cache()


def test_committed_change_refreshes_leaf_hero_and_manifest_once(setup, monkeypatch):
    writer, site, home, page, integration = setup
    original_revision = page.live_revision_id
    old = writer.begin(page)
    finalised = []
    finalise = IndexBatch.finalise

    def record_finalise(batch):
        finalised.append(set(batch.dirty))
        return finalise(batch)

    monkeypatch.setattr(IndexBatch, "finalise", record_finalise)
    with transaction.atomic():
        integration.integrations = config("new.example.org")
        integration.save()
        assert "old.example.org/act/campaign-one/" in read(writer, "example.org/campaign.md")
        assert finalised == []
    assert "new.example.org/act/campaign-one/" in read(writer, "example.org/campaign.md")
    assert "new.example.org/act/home-campaign/" in read(writer, "example.org/index.md")
    assert finalised == [{site.pk}]
    assert Page.objects.get(pk=page.pk).live_revision_id == original_revision
    manifest = json.loads(read(writer, "example.org/manifest.json"))
    assert {entry["id"] for entry in manifest["documents"]} == {home.pk, page.pk}
    with pytest.raises(StaleBuild):
        writer.publish(old, "An obsolete settings-dependent render")


def test_rollback_noop_and_unsaved_integration_edits_do_not_enqueue(setup, monkeypatch):
    writer, site, home, page, integration = setup
    queued = []
    monkeypatch.setattr(tasks, "enqueue", lambda *args, **kwargs: queued.append(kwargs))
    integration.save()
    assert queued == []
    integration.integrations = config("unsaved.example.org")
    integration.custom_head_html = "<!-- changed chrome -->"
    integration.save(update_fields=["custom_head_html"])
    assert queued == []
    with pytest.raises(RuntimeError), transaction.atomic():
        integration.save(update_fields=["integrations"])
        raise RuntimeError("rollback")
    assert queued == []
    assert "old.example.org" in read(writer, "example.org/campaign.md")


def test_disable_and_delete_remove_campaign_links_without_recursive_creation(setup, monkeypatch):
    writer, site, home, page, integration = setup
    queued = []
    enqueue = tasks.enqueue

    def record(fn, **kwargs):
        queued.append(kwargs)
        return enqueue(fn, **kwargs)

    monkeypatch.setattr(tasks, "enqueue", record)
    integration.integrations = config("old.example.org", enabled=False)
    integration.save()
    assert "/act/" not in read(writer, "example.org/campaign.md")
    integration.integrations = config("new.example.org")
    integration.save()
    assert "new.example.org" in read(writer, "example.org/campaign.md")
    integration.delete()
    assert "/act/" not in read(writer, "example.org/campaign.md")
    assert "Published copy." in read(writer, "example.org/campaign.md")
    assert len(queued) == 3
    assert not IntegrationSettings.for_site(site).integrations


def test_nested_site_and_unpublished_draft_are_not_changed(setup, settings):
    writer, site, home, page, integration = setup
    options = settings.WAGTAIL_MARKDOWN_AGENTS
    settings.WAGTAIL_MARKDOWN_AGENTS = {**options, "AUTO_GENERATE": False}
    nested = home.add_child(
        instance=HomePage(
            title="Nested site",
            slug="nested",
            body=[("text", "<p>Other site.</p>")],
            hero_cta=[("signup", {"short_form_id": "nested-campaign"})],
        )
    )
    other = Site.objects.create(hostname="nested.example.org", root_page=nested)
    IntegrationSettings.objects.create(site=other, integrations=config("other-action.example.org"))
    nested.save_revision().publish()
    page.body = [("text", "<p>DRAFT MUST NOT LEAK</p>")]
    page.save_revision()
    settings.WAGTAIL_MARKDOWN_AGENTS = options
    handlers.refresh_sites(site_ids=(other.pk,))
    other_files = dict(
        ExportArtifact.objects.filter(scope__site_id=other.pk).values_list("pk", "file_id")
    )
    integration.integrations = config("new.example.org")
    integration.save()
    output = read(writer, "example.org/campaign.md")
    assert "Published copy." in output and "DRAFT MUST NOT LEAK" not in output
    assert other_files == dict(
        ExportArtifact.objects.filter(scope__site_id=other.pk).values_list("pk", "file_id")
    )
    assert "other-action.example.org" in read(writer, "nested.example.org/index.md")


def test_delayed_job_reloads_latest_settings_and_honours_policy(setup, settings, monkeypatch):
    writer, site, home, page, integration = setup
    pending = []
    monkeypatch.setattr(tasks, "enqueue", lambda fn, **kwargs: pending.append((fn, kwargs)))
    integration.integrations = config("intermediate.example.org")
    integration.save()
    integration.integrations = config("latest.example.org")
    integration.save()
    assert len(pending) == 2
    fn, kwargs = pending[0]
    assert kwargs == {"site_ids": (site.pk,), "using": "default"}
    fn(**kwargs)
    assert "latest.example.org" in read(writer, "example.org/campaign.md")
    # Restrictions applied before a delayed refresh are rechecked, not bypassed.
    PageViewRestriction.objects.create(page=page, restriction_type=PageViewRestriction.LOGIN)
    pending[1][0](**pending[1][1])
    assert not writer.exists("example.org/campaign.md")


@pytest.mark.parametrize("gate", ["automatic", "site", "deleted-site"])
def test_delayed_job_skips_disabled_or_deleted_scope(setup, settings, monkeypatch, gate):
    writer, site, home, page, integration = setup
    pending = []
    monkeypatch.setattr(tasks, "enqueue", lambda fn, **kwargs: pending.append((fn, kwargs)))
    integration.integrations = config("new.example.org")
    integration.save()
    if gate == "automatic":
        settings.WAGTAIL_MARKDOWN_AGENTS = {
            **settings.WAGTAIL_MARKDOWN_AGENTS,
            "AUTO_GENERATE": False,
        }
    elif gate == "site":
        settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "SITES": []}
    else:
        site.delete()
    monkeypatch.setattr(
        handlers, "refresh_pages", lambda *args, **kwargs: pytest.fail("must not rebuild")
    )
    fn, kwargs = pending[0]
    fn(**kwargs)


def test_failure_is_logged_after_commit_and_explicit_retry_works(setup, monkeypatch, caplog):
    writer, site, home, page, integration = setup
    original = FileWriter._upload

    def fail(*args, **kwargs):
        raise OSError("storage unavailable")

    monkeypatch.setattr(FileWriter, "_upload", fail)
    integration.integrations = config("new.example.org")
    integration.save()
    integration.refresh_from_db()
    assert integration.get_integration_config("actionkit")["hostname"] == "new.example.org"
    assert "integration-settings refresh failed" in caplog.text
    assert "storage unavailable" in caplog.text
    monkeypatch.setattr(FileWriter, "_upload", original)
    handlers.refresh_sites(site_ids=(site.pk,))
    assert "new.example.org" in read(writer, "example.org/campaign.md")


def test_raw_saves_idempotent_connections_and_primary_database_contract(setup, monkeypatch):
    writer, site, home, page, integration = setup
    pending = []
    monkeypatch.setattr(tasks, "enqueue", lambda fn, **kwargs: pending.append(kwargs))
    handlers.connect()
    handlers.connect()
    post_save.send(sender=IntegrationSettings, instance=integration, raw=True, using="default")
    assert pending == []
    with pytest.raises(ImproperlyConfigured, match="default database"):
        post_save.send(sender=IntegrationSettings, instance=integration, using="other")
    integration.integrations = config("new.example.org")
    integration.save()
    assert pending == [{"site_ids": (site.pk,), "using": "default"}]


def test_other_integration_changes_refresh_template_dependent_output(setup):
    writer, site, home, page, integration = setup
    block = DonateBlock()
    value = block.to_python({"content": "<h2>Support us</h2>", "override_amounts": []})

    def donation_copy(markdown, page, context):
        # Exercise the actual add-on renderer/template with the fresh settings
        # proxy, rather than constructing a link directly from a fake field.
        return markdown + "\n\n" + render_block(block, value, context)

    with hooks.register_temporarily("markdown_post_render", donation_copy):
        integration.integrations = [
            (
                "actblue",
                {
                    "enabled": True,
                    "base_url": "https://donate.example.org/campaign",
                    "suggested_amounts": "10,25",
                },
            )
        ]
        integration.save()
    assert "[Donate](https://donate.example.org/campaign)" in read(
        writer, "example.org/campaign.md"
    )
    assert "[$25](https://donate.example.org/campaign?amount=25)" in read(
        writer, "example.org/campaign.md"
    )


def test_disabled_generation_and_empty_initial_settings_do_not_enqueue(
    setup, settings, monkeypatch
):
    writer, site, home, page, integration = setup
    pending = []
    monkeypatch.setattr(tasks, "enqueue", lambda fn, **kwargs: pending.append(kwargs))
    options = settings.WAGTAIL_MARKDOWN_AGENTS
    settings.WAGTAIL_MARKDOWN_AGENTS = {**options, "AUTO_GENERATE": False}
    integration.integrations = config("disabled.example.org")
    integration.save()
    integration.delete()
    assert pending == []
    settings.WAGTAIL_MARKDOWN_AGENTS = options
    IntegrationSettings.for_site(site)
    assert pending == []


def test_creating_populated_settings_and_reassignment_schedule_affected_sites(setup, monkeypatch):
    writer, site, home, page, integration = setup
    pending = []
    monkeypatch.setattr(tasks, "enqueue", lambda fn, **kwargs: pending.append(kwargs))
    other = Site.objects.create(hostname="new.example.org", root_page=home)
    fresh = IntegrationSettings.objects.create(
        site=other, integrations=config("action.example.org")
    )
    assert pending == [{"site_ids": (other.pk,), "using": "default"}]
    fresh.delete()
    pending.clear()
    integration.site = other
    integration.save(update_fields=["site"])
    assert pending == [{"site_ids": tuple(sorted((site.pk, other.pk))), "using": "default"}]
