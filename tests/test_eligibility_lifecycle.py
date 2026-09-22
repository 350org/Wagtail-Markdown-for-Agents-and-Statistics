"""Restriction/exclusion privacy transitions through real model signals (#70)."""

from io import StringIO

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from wagtail import hooks
from wagtail.models import Page, PageViewRestriction

from tests import test_lifecycle
from tests.test_indexes import article, read
from tests.test_lifecycle import entries
from wagtail_markdown_agents import handlers, tasks
from wagtail_markdown_agents.export.lifecycle import refresh_pages, revoke_ineligible
from wagtail_markdown_agents.export.policy import ExportPolicy
from wagtail_markdown_agents.export.snapshot import SiteSnapshot
from wagtail_markdown_agents.export.writer import FileWriter
from wagtail_markdown_agents.models import ExportArtifact, PageAgentSettings

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.export_lifecycle]
setup = test_lifecycle.setup


def configure(settings, auto):
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "AUTO_GENERATE": auto}


@pytest.mark.parametrize("auto", [False, True])
@pytest.mark.parametrize("kind", ["login", "password", "groups", "excluded"])
def test_immediate_revocation_with_deferred_backend(setup, settings, monkeypatch, auto, kind):
    writer, site, home = setup
    parent = article(home, "parent")
    child = article(parent, "child")
    unrelated = article(home, "unrelated")
    refresh_pages([child.pk])
    revoked = [parent.pk] if kind == "excluded" else [parent.pk, child.pk]
    files = list(ExportArtifact.objects.select_related("file").exclude(page_id=unrelated.pk))
    configure(settings, auto)
    queued = []
    monkeypatch.setattr(tasks, "enqueue", lambda *args, **kwargs: queued.append(kwargs))
    with transaction.atomic():
        if kind == "excluded":
            PageAgentSettings.objects.create(page=parent, excluded=True)
        else:
            PageViewRestriction.objects.create(page=parent, restriction_type=kind)
        assert not ExportArtifact.objects.filter(page_id__in=revoked).exists()
        assert not ExportArtifact.objects.filter(page_id__isnull=True).exists()
        for record in files:
            if record.page_id in revoked or record.dependency_state or record.page_id is None:
                assert not writer._backend(record.file).exists(record.file.storage_key)
        assert queued == []
    assert queued == []
    assert writer.exists("example.org/unrelated.md")
    assert writer.exists("example.org/parent/child.md") == (kind == "excluded")
    if auto:
        assert not set(revoked) & {entry["id"] for entry in entries(writer)}
        assert "Parent" not in read(writer)
    else:
        assert not writer.exists("example.org/manifest.json")


@pytest.mark.parametrize("change", ["remove", "relax", "include", "delete_settings"])
def test_restoration_is_inline_after_commit(setup, monkeypatch, change):
    writer, site, home = setup
    parent = article(home, "parent")
    child = article(parent, "child")
    if change in {"remove", "relax"}:
        row = PageViewRestriction.objects.create(page=parent, restriction_type="login")
    else:
        row = PageAgentSettings.objects.create(page=parent, excluded=True)
    monkeypatch.setattr(
        tasks, "enqueue", lambda *args, **kwargs: pytest.fail("Queued privacy work")
    )
    with transaction.atomic():
        if change in {"remove", "delete_settings"}:
            row.delete()
        elif change == "relax":
            row.restriction_type = "none"
            row.save(update_fields=["restriction_type"])
        else:
            row.excluded = False
            row.save(update_fields=["excluded"])
        assert not writer.exists("example.org/parent/index.md")
        parent.title = "PRIVATE DRAFT"
        parent.save_revision()
    assert writer.exists("example.org/parent/index.md")
    assert writer.exists("example.org/parent/child.md")
    assert "PRIVATE DRAFT" not in read(writer, "example.org/parent/index.md")
    assert {parent.pk, child.pk} <= {entry["id"] for entry in entries(writer)}


@pytest.mark.parametrize(
    "veto", ["ancestor", "own", "excluded", "type", "hook", "unpublish", "delete"]
)
def test_restoration_rechecks_full_policy(setup, settings, veto):
    writer, site, home = setup
    parent = article(home, "parent")
    child = article(parent, "child")
    child_id = child.pk
    restriction = PageViewRestriction.objects.create(page=parent, restriction_type="login")
    with hooks.register_temporarily(
        "markdown_export_eligible",
        lambda page, site: False if veto == "hook" and page.pk == child_id else None,
    ):
        with transaction.atomic():
            restriction.delete()
            if veto in {"ancestor", "own"}:
                PageViewRestriction.objects.create(
                    page=home if veto == "ancestor" else child, restriction_type="login"
                )
            elif veto == "excluded":
                PageAgentSettings.objects.create(page=child, excluded=True)
            elif veto == "type":
                settings.WAGTAIL_MARKDOWN_AGENTS = {
                    **settings.WAGTAIL_MARKDOWN_AGENTS,
                    "PAGE_TYPES": [],
                }
            elif veto == "unpublish":
                child.unpublish()
            elif veto == "delete":
                child.delete()
        assert not writer.exists("example.org/parent/child.md")
        assert child_id not in {entry["id"] for entry in entries(writer)}


@pytest.mark.parametrize("excluded", [False, True])
def test_rollback_and_generation_disabled(setup, settings, excluded):
    writer, site, home = setup
    child = article(home, "child")
    with pytest.raises(RuntimeError), transaction.atomic():
        if excluded:
            PageAgentSettings.objects.create(page=child, excluded=True)
        else:
            PageViewRestriction.objects.create(page=child, restriction_type="login")
        raise RuntimeError("rollback")
    assert ExportPolicy().is_eligible(child)
    assert not writer.exists("example.org/child.md")
    refresh_pages([child.pk])
    row = (
        PageAgentSettings.objects.create(page=child, excluded=True)
        if excluded
        else PageViewRestriction.objects.create(page=child, restriction_type="login")
    )
    with pytest.raises(RuntimeError), transaction.atomic():
        row.delete()
        raise RuntimeError("rollback")
    assert not writer.exists("example.org/child.md")
    configure(settings, False)
    model = PageAgentSettings if excluded else PageViewRestriction
    model.objects.filter(page=child).delete()
    assert not writer.exists("example.org/child.md")
    refresh_pages([child.pk])
    assert writer.exists("example.org/child.md")


def test_public_restriction_agrees_in_both_policy_paths(setup):
    writer, site, home = setup
    child = article(home, "child")
    row = PageViewRestriction.objects.create(page=home, restriction_type="none")
    assert ExportPolicy().is_eligible(child)
    assert ExportPolicy(SiteSnapshot(site)).is_eligible(child)
    row.restriction_type = "login"
    row.save()
    assert not ExportArtifact.objects.filter(page_id=child.pk).exists()


def test_exclusion_ignores_unsaved_value_and_unrelated_metadata(setup):
    writer, site, home = setup
    child = article(home, "child")
    row = PageAgentSettings.objects.create(page=child, excluded=False)
    refresh_pages([child.pk])
    file_id = ExportArtifact.objects.get(page_id=child.pk).file_id
    row.excluded = True
    row.extra_frontmatter = {"test": "changed"}
    row.save(update_fields=["extra_frontmatter"])
    assert ExportArtifact.objects.get(page_id=child.pk).file_id == file_id
    row.refresh_from_db()
    row.excluded = True
    row.save(update_fields=["excluded"])
    assert not ExportArtifact.objects.filter(page_id=child.pk).exists()
    manifest_id = ExportArtifact.objects.get(logical_path="example.org/manifest.json").file_id
    row.extra_frontmatter = {"test": "private metadata"}
    row.save(update_fields=["extra_frontmatter"])
    assert (
        ExportArtifact.objects.get(logical_path="example.org/manifest.json").file_id == manifest_id
    )


def test_deploy_reconciliation_revokes_disabled_types(setup, settings, monkeypatch):
    writer, site, home = setup
    child = article(home, "child")
    files = list(ExportArtifact.objects.select_related("file"))
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        **settings.WAGTAIL_MARKDOWN_AGENTS,
        "PAGE_TYPES": [],
        "AUTO_GENERATE": False,
    }
    monkeypatch.setattr(tasks, "enqueue", lambda *args, **kwargs: pytest.fail("Queued deploy work"))
    output = StringIO()
    call_command("agentmd_revoke_ineligible", stdout=output)
    assert not ExportArtifact.objects.exists()
    assert "2" in output.getvalue()
    for record in files:
        assert not writer._backend(record.file).exists(record.file.storage_key)
    assert Page.objects.filter(pk=child.pk).exists()
    call_command("agentmd_revoke_ineligible", stdout=StringIO())


def test_withdrawn_routes_and_html_access_controls(setup, settings, client):
    writer, site, home = setup
    child = article(home, "child")
    configure(settings, False)
    PageViewRestriction.objects.create(page=child, restriction_type="login")
    for path in ["child.md", "index.md", "llms.txt", "manifest.json"]:
        assert client.get(f"/markdown/{path}", HTTP_HOST="example.org").status_code == 404
    response = client.get(
        "/child/?output_format=md", HTTP_HOST="example.org", HTTP_ACCEPT="text/markdown"
    )
    assert response.status_code == 302
    assert "login" in response["Location"]


@pytest.mark.parametrize("model", [PageAgentSettings, PageViewRestriction])
@pytest.mark.filterwarnings("error:Specific versions:RuntimeWarning")
def test_cascade_deleted_side_rows_never_restore_pages(setup, model):
    writer, site, home = setup
    parent = article(home, "parent")
    child = article(parent, "child")
    kwargs = {"excluded": True} if model is PageAgentSettings else {"restriction_type": "login"}
    model.objects.create(page=child, **kwargs)
    ids = {parent.pk, child.pk}
    parent.delete()
    assert not ExportArtifact.objects.filter(page_id__in=ids).exists()
    assert not ids & {entry["id"] for entry in entries(writer)}
    model.objects.create(page=home, **kwargs)
    home.delete()
    assert not ExportArtifact.objects.exists()


@pytest.mark.parametrize("model", [PageAgentSettings, PageViewRestriction])
def test_side_row_reassignment_restores_old_owner_and_revokes_new(setup, model):
    writer, site, home = setup
    first, second = article(home, "first"), article(home, "second")
    kwargs = {"excluded": True} if model is PageAgentSettings else {"restriction_type": "login"}
    row = model.objects.create(page=first, **kwargs)
    with transaction.atomic():
        row.page = second
        row.save(update_fields=["page"])
        assert not writer.exists("example.org/first.md")
        assert not ExportArtifact.objects.filter(page_id=second.pk).exists()
    assert writer.exists("example.org/first.md")
    assert not writer.exists("example.org/second.md")


def test_restriction_revokes_actual_old_hook_key(setup, settings):
    writer, site, home = setup
    with hooks.register_temporarily(
        "markdown_export_path", lambda path, page, site: f"custom/{page.pk}.md"
    ):
        child = article(home, "child")
        record = ExportArtifact.objects.select_related("file").get(page_id=child.pk)
    configure(settings, False)
    PageViewRestriction.objects.create(page=child, restriction_type="login")
    assert not writer._backend(record.file).exists(record.file.storage_key)
    assert not ExportArtifact.objects.filter(page_id=child.pk).exists()


def test_restoration_failure_is_logged_after_commit_and_explicit_retry_raises(
    setup, monkeypatch, caplog
):
    writer, site, home = setup
    child = article(home, "child")
    row = PageAgentSettings.objects.create(page=child, excluded=True)

    def fail(*args, **kwargs):
        raise OSError("Restoration upload failed")

    monkeypatch.setattr(FileWriter, "_upload", fail)
    row.delete()
    assert not PageAgentSettings.objects.filter(page=child).exists()
    assert not writer.exists("example.org/child.md")
    assert "Markdown eligibility refresh failed" in caplog.text
    with pytest.raises(OSError, match="Restoration upload failed"):
        refresh_pages([child.pk])


def test_restoration_disabled_between_scheduling_and_commit(setup, settings):
    writer, site, home = setup
    child = article(home, "child")
    row = PageAgentSettings.objects.create(page=child, excluded=True)
    with transaction.atomic():
        row.delete()
        configure(settings, False)
    assert not writer.exists("example.org/child.md")


@pytest.mark.parametrize("model", [PageAgentSettings, PageViewRestriction])
def test_receiver_database_raw_fixtures_and_idempotent_connections(setup, monkeypatch, model):
    writer, site, home = setup
    calls = []
    monkeypatch.setattr(
        handlers, "_eligibility_change", lambda *args, **kwargs: calls.append(kwargs)
    )
    handlers.connect()
    handlers.connect()
    kwargs = {"excluded": True} if model is PageAgentSettings else {"restriction_type": "login"}
    instance = model(page=home, **kwargs)
    for signal in (pre_save, post_save):
        signal.send(sender=model, instance=instance, raw=True, using="other")
        with pytest.raises(ImproperlyConfigured, match="default database"):
            signal.send(sender=model, instance=instance, raw=False, using="other")
    with pytest.raises(ImproperlyConfigured, match="default database"):
        post_delete.send(sender=model, instance=instance, using="other")
    assert calls == []
    instance.save()
    assert len(calls) == 1 and calls[0]["using"] == "default"
    instance._state.db = "other"
    post_save.send(sender=model, instance=instance, raw=False, using="default")
    assert len(calls) == 2


def test_bulk_revocation_reconciliation_preserves_eligible_leaf(setup, settings):
    writer, site, home = setup
    first, second = article(home, "first"), article(home, "second")
    configure(settings, False)
    row = PageAgentSettings.objects.create(page=first, excluded=False)
    refresh_pages([first.pk])
    PageAgentSettings.objects.filter(pk=row.pk).update(excluded=True)
    assert revoke_ineligible() == (first.pk,)
    assert writer.exists("example.org/second.md")
    assert not writer.exists("example.org/manifest.json")
    assert not ExportArtifact.objects.filter(page_id=first.pk).exists()
    assert Page.objects.filter(pk=second.pk).exists()
