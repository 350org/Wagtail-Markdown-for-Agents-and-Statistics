"""Real Wagtail publication signals and after-commit export lifecycle (#23)."""

import json

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models.signals import pre_delete
from sandbox.testapp.models import ArticlePage
from wagtail import hooks
from wagtail.models import Locale, Page, PageViewRestriction, Site
from wagtail.signals import page_published

from tests.test_indexes import article, read
from wagtail_markdown_agents import handlers, tasks
from wagtail_markdown_agents.export.indexes import IndexBatch
from wagtail_markdown_agents.export.lifecycle import (
    refresh_pages,
    revoke_pages,
    schedule_refresh,
    subtree_page_ids,
)
from wagtail_markdown_agents.export.writer import FileWriter
from wagtail_markdown_agents.models import ExportArtifact
from wagtail_markdown_agents.settings import DEFAULTS

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.export_lifecycle]


@pytest.fixture(params=["remote", "filesystem"])
def setup(request, settings, tmp_path):
    settings.ROOT_URLCONF = "sandbox.urls"
    settings.ALLOWED_HOSTS = ["example.org"]
    settings.BASE_DIR = tmp_path
    settings.STORAGES = {
        **settings.STORAGES,
        "exports": {"BACKEND": "tests.storage_backend.RemoteStorage"},
    }
    config = {"STORAGE": "exports"} if request.param == "remote" else {}
    settings.WAGTAIL_MARKDOWN_AGENTS = {**config, "AUTO_GENERATE": False}
    locale, _ = Locale.objects.get_or_create(language_code="en")
    root = Page.get_first_root_node() or Page.add_root(title="Root", slug="root", locale=locale)
    home = root.add_child(
        instance=ArticlePage(
            title="Home", slug="lifecycle-home", body=[("paragraph", "<p>Home body.</p>")]
        )
    )
    Site.objects.all().delete()
    site = Site.objects.create(hostname="example.org", root_page=home, is_default_site=True)
    home.save_revision().publish()
    settings.WAGTAIL_MARKDOWN_AGENTS = config
    yield FileWriter(), site, home
    Site.clear_site_root_paths_cache()


def entries(writer):
    return json.loads(read(writer, "example.org/manifest.json"))["documents"]


def test_publish_generates_complete_discovery_and_manifest(setup):
    writer, site, home = setup
    child = article(home, "child")
    assert DEFAULTS["AUTO_GENERATE"] is True
    assert "child body." in read(writer, "example.org/child.md")
    assert "Child" in read(writer)
    assert "Child" in read(writer, "example.org/llms.txt")
    assert {entry["id"] for entry in entries(writer)} == {home.pk, child.pk}


def test_publish_waits_for_commit_and_rollback_discards_callback(setup, monkeypatch):
    writer, site, home = setup
    calls = []
    original = tasks.enqueue

    def enqueue(fn, *args, **kwargs):
        assert transaction.get_autocommit()
        calls.append(kwargs)
        return original(fn, *args, **kwargs)

    monkeypatch.setattr(tasks, "enqueue", enqueue)
    with transaction.atomic():
        child = article(home, "child")
        assert not ExportArtifact.objects.exists()
        assert calls == []
    assert len(calls) == 1
    assert writer.exists("example.org/child.md")
    with pytest.raises(RuntimeError), transaction.atomic():
        article(home, "rolled-back")
        raise RuntimeError("rollback")
    assert len(calls) == 1
    assert not writer.exists("example.org/rolled-back.md")
    assert Page.objects.filter(pk=child.pk).exists()


def test_newer_draft_never_replaces_published_content(setup):
    writer, site, home = setup
    with transaction.atomic():
        child = article(home, "child")
        child.title = "PRIVATE DRAFT"
        child.body = [("paragraph", "<p>PRIVATE DRAFT BODY</p>")]
        child.save_revision()
    output = read(writer, "example.org/child.md")
    assert "child body." in output and "PRIVATE DRAFT" not in output
    assert "PRIVATE DRAFT" not in json.dumps(entries(writer))


@pytest.mark.parametrize("change", ["unpublish", "delete", "restrict", "newer_publish"])
def test_deferred_callback_refetches_current_state(setup, monkeypatch, change):
    writer, site, home = setup
    pending = []
    monkeypatch.setattr(
        tasks, "enqueue", lambda fn, *args, **kwargs: pending.append((fn, args, kwargs))
    )
    child = article(home, "child")
    if change == "unpublish":
        child.unpublish()
    elif change == "delete":
        child.delete()
    elif change == "restrict":
        PageViewRestriction.objects.create(page=child, restriction_type="login")
    else:
        child.body = [("paragraph", "<p>Newer published body</p>")]
        child.save_revision().publish()
    for fn, args, kwargs in pending:
        assert not any(isinstance(value, Page) for value in args)
        fn(*args, **kwargs)
    if change == "newer_publish":
        assert "Newer published body" in read(writer, "example.org/child.md")
    else:
        assert not writer.exists("example.org/child.md")
        assert child.pk not in {entry["id"] for entry in entries(writer)}


@pytest.mark.parametrize("event", ["unpublish", "delete"])
@pytest.mark.parametrize("auto", [False, True])
def test_revocation_is_immediate_even_with_deferred_backend(
    setup, settings, monkeypatch, event, auto
):
    writer, site, home = setup
    child = article(home, "child")
    record = ExportArtifact.objects.select_related("file").get(page_id=child.pk)
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "AUTO_GENERATE": auto}
    queued = []
    monkeypatch.setattr(tasks, "enqueue", lambda *args, **kwargs: queued.append((args, kwargs)))
    with transaction.atomic():
        if event == "unpublish":
            child.unpublish()
        else:
            child.delete()
        assert not ExportArtifact.objects.filter(page_id=record.page_id).exists()
        assert not writer._backend(record.file).exists(record.file.storage_key)
        assert not ExportArtifact.objects.filter(page_id__isnull=True).exists()
        assert queued == []
    assert bool(queued) == auto


def test_auto_generate_off_keeps_current_exports_but_does_not_publish_new_pages(setup, settings):
    writer, site, home = setup
    child = article(home, "child")
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "AUTO_GENERATE": False}
    assert writer.exists("example.org/child.md")
    assert writer.exists("example.org/manifest.json")
    article(home, "ungenerated")
    assert not writer.exists("example.org/ungenerated.md")
    child.unpublish()
    assert not ExportArtifact.objects.filter(page_id=child.pk).exists()
    assert not ExportArtifact.objects.filter(page_id__isnull=True).exists()


def test_delete_cascade_removes_descendants_and_repairs_parent_leaf(setup):
    writer, site, home = setup
    parent = article(home, "parent")
    child = article(parent, "child")
    grandchild = article(child, "grandchild")
    ids = [child.pk, grandchild.pk]
    assert writer.exists("example.org/parent/index.md")
    with transaction.atomic():
        child.delete()
        assert not ExportArtifact.objects.filter(page_id__in=ids).exists()
        assert not writer.exists("example.org/manifest.json")
    assert writer.exists("example.org/parent.md")
    assert not writer.exists("example.org/parent/index.md")
    assert not set(ids) & {entry["id"] for entry in entries(writer)}
    assert parent.pk in {entry["id"] for entry in entries(writer)}


def test_delete_site_root_does_not_recreate_site_or_exports(setup):
    writer, site, home = setup
    article(home, "child")
    home.delete()
    assert not Site.objects.filter(pk=site.pk).exists()
    assert not ExportArtifact.objects.filter(scope__site_id=site.pk).exists()


def test_rollback_of_revocation_leaves_safe_missing_files(setup):
    writer, site, home = setup
    child = article(home, "child")
    with pytest.raises(RuntimeError), transaction.atomic():
        child.unpublish()
        assert not writer.exists("example.org/child.md")
        raise RuntimeError("rollback")
    assert Page.objects.get(pk=child.pk).live
    assert not writer.exists("example.org/child.md")
    assert not writer.exists("example.org/manifest.json")
    refresh_pages([child.pk])
    assert writer.exists("example.org/child.md")


def test_revocation_uses_actual_old_hook_path(setup):
    writer, site, home = setup
    with hooks.register_temporarily(
        "markdown_export_path", lambda path, page, site: f"custom/{page.pk}.md"
    ):
        child = article(home, "child")
        record = ExportArtifact.objects.select_related("file").get(page_id=child.pk)
    child.unpublish()
    assert not ExportArtifact.objects.filter(page_id=child.pk).exists()
    assert not writer._backend(record.file).exists(record.file.storage_key)


def test_multiple_refreshes_finalise_each_site_once(setup, monkeypatch):
    writer, site, home = setup
    first, second = article(home, "first"), article(home, "second")
    calls = []
    original = IndexBatch.finalise

    def finalise(self):
        calls.append(set(self.dirty))
        return original(self)

    monkeypatch.setattr(IndexBatch, "finalise", finalise)
    refresh_pages([first.pk, second.pk])
    assert calls == [{site.pk}]
    assert {entry["id"] for entry in entries(writer)} == {home.pk, first.pk, second.pk}


def test_render_failure_is_logged_after_cms_commit_and_not_a_manifest_success(
    setup, monkeypatch, caplog
):
    writer, site, home = setup

    def fail(*args, **kwargs):
        raise OSError("Upload failed")

    monkeypatch.setattr(FileWriter, "_upload", fail)
    child = article(home, "child")
    assert Page.objects.get(pk=child.pk).live
    assert not writer.exists("example.org/child.md")
    assert not writer.exists("example.org/manifest.json")
    assert "Upload failed" in caplog.text
    with pytest.raises(OSError, match="Upload failed"):
        refresh_pages([child.pk])


def test_unsupported_page_is_skipped_without_breaking_discovery(setup, caplog):
    writer, site, home = setup
    child = home.add_child(instance=Page(title="Unsupported", slug="unsupported"))
    child.save_revision().publish()
    assert not ExportArtifact.objects.filter(page_id=child.pk).exists()
    assert writer.exists("example.org/manifest.json")
    assert "unsupported_page" in caplog.text


def test_connections_are_idempotent_and_unrelated_deletes_ignored(setup, monkeypatch):
    writer, site, home = setup
    calls = []
    original = tasks.enqueue
    monkeypatch.setattr(
        tasks, "enqueue", lambda *args, **kwargs: (calls.append(1), original(*args, **kwargs))
    )
    handlers.connect()
    handlers.connect()
    article(home, "child")
    assert len(calls) == 1
    pre_delete.send(sender=Site, instance=site, using="default")
    assert len(calls) == 1


def test_nondefault_signal_database_is_rejected_before_export_work(setup, monkeypatch):
    writer, site, home = setup
    calls = []
    monkeypatch.setattr(tasks, "enqueue", lambda *args, **kwargs: calls.append(1))
    with pytest.raises(ImproperlyConfigured, match="default database"):
        page_published.send(sender=type(home), instance=home, using="other")
    assert calls == []


def test_explicit_write_alias_wins_over_instance_database(setup, monkeypatch):
    writer, site, home = setup
    queued = []
    monkeypatch.setattr(tasks, "enqueue", lambda *args, **kwargs: queued.append(kwargs))
    home._state.db = "other"
    with pytest.raises(ImproperlyConfigured, match="default database"):
        page_published.send(sender=type(home), instance=home)
    with transaction.atomic():
        page_published.send(sender=type(home), instance=home, using="default")
        assert queued == []
    assert queued[0]["using"] == "default"


def test_delayed_automatic_job_honours_generation_disabled_later(setup, settings, monkeypatch):
    writer, site, home = setup
    pending = []
    monkeypatch.setattr(tasks, "enqueue", lambda fn, **kwargs: pending.append((fn, kwargs)))
    article(home, "child")
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "AUTO_GENERATE": False}
    for fn, kwargs in pending:
        assert fn(**kwargs) == []
    assert not ExportArtifact.objects.exists()


def test_subtree_helpers_capture_ids_and_coalesce_revocation_repair(setup, monkeypatch):
    writer, site, home = setup
    parent = article(home, "parent")
    child = article(parent, "child")
    ids = subtree_page_ids(parent.pk)
    assert set(ids) == {parent.pk, child.pk}
    assert subtree_page_ids(999999) == ()
    scopes = revoke_pages(ids)
    assert parent.pk in scopes[site.pk]
    assert not ExportArtifact.objects.filter(page_id__in=ids).exists()
    # Explicit operators can rebuild selected public content without CMS edits.
    refresh_pages(ids, scopes=scopes)
    assert writer.exists("example.org/parent/index.md")
    assert writer.exists("example.org/parent/child.md")


def test_related_content_refresh_is_explicit_and_runs_after_commit(setup):
    writer, site, home = setup
    related = {"text": "Initial related content"}

    def render(markdown, page, context):
        return markdown + "\n" + related["text"]

    with hooks.register_temporarily("markdown_post_render", render):
        child = article(home, "child")
        related["text"] = "Updated related content"
        assert "Initial related content" in read(writer, "example.org/child.md")
        with transaction.atomic():
            schedule_refresh([child.pk])
            assert "Initial related content" in read(writer, "example.org/child.md")
        assert "Updated related content" in read(writer, "example.org/child.md")


def test_deleted_restriction_cascade_does_not_restore_page(setup):
    writer, site, home = setup
    parent = article(home, "parent")
    child = article(parent, "child")
    PageViewRestriction.objects.create(page=child, restriction_type="login")
    ids = [parent.pk, child.pk]
    parent.delete()
    assert not ExportArtifact.objects.filter(page_id__in=ids).exists()
    assert not set(ids) & {entry["id"] for entry in entries(writer)}


def test_delete_rollback_never_rebuilds_during_transaction(setup):
    writer, site, home = setup
    child = article(home, "child")
    page_id = child.pk
    with pytest.raises(RuntimeError), transaction.atomic():
        child.delete()
        assert not writer.exists("example.org/child.md")
        raise RuntimeError("rollback")
    assert Page.objects.filter(pk=page_id).exists()
    assert not writer.exists("example.org/child.md")
    refresh_pages([page_id])
    assert writer.exists("example.org/child.md")


def test_empty_page_body_does_not_become_successful_export(setup, caplog):
    writer, site, home = setup
    child = home.add_child(instance=ArticlePage(title="Empty", slug="empty", body=[]))
    child.save_revision().publish()
    assert not ExportArtifact.objects.filter(page_id=child.pk).exists()
    assert child.pk not in {entry["id"] for entry in entries(writer)}
    assert "empty_body" in caplog.text


def test_partial_bulk_failure_preserves_successful_page_but_does_not_finalise(setup, monkeypatch):
    writer, site, home = setup
    first, second = article(home, "first"), article(home, "second")
    old_file = ExportArtifact.objects.get(page_id=first.pk).file_id
    original = FileWriter._upload

    def upload(self, file, text):
        if file.page_id == second.pk:
            raise OSError("Second page failed")
        return original(self, file, text)

    monkeypatch.setattr(FileWriter, "_upload", upload)
    with pytest.raises(OSError, match="Second page failed"):
        refresh_pages([first.pk, second.pk])
    assert ExportArtifact.objects.get(page_id=first.pk).file_id != old_file
    assert writer.exists("example.org/first.md")
    assert not writer.exists("example.org/manifest.json")


def test_unpublish_during_upload_rejects_obsolete_lifecycle_build(setup, monkeypatch, caplog):
    writer, site, home = setup
    original = FileWriter._upload
    revoked = []

    def upload(self, file, text):
        original(self, file, text)
        if file.page_id != home.pk and file.page_id is not None and not revoked:
            revoked.append(file.page_id)
            Page.objects.get(pk=file.page_id).specific.unpublish()

    monkeypatch.setattr(FileWriter, "_upload", upload)
    child = article(home, "child")
    assert revoked == [child.pk]
    assert not Page.objects.get(pk=child.pk).live
    assert not writer.exists("example.org/child.md")
    assert child.pk not in {entry["id"] for entry in entries(writer)}
    assert "StaleBuild" in caplog.text


def test_cascade_finalises_discovery_once_and_preserves_removal_summary(setup, monkeypatch):
    writer, site, home = setup
    parent = article(home, "parent")
    article(parent, "child")
    calls = []
    original = IndexBatch.finalise

    def finalise(self):
        calls.append(set(self.dirty))
        return original(self)

    monkeypatch.setattr(IndexBatch, "finalise", finalise)
    parent.delete()
    assert calls == [{site.pk}]
    manifest = json.loads(read(writer, "example.org/manifest.json"))
    assert manifest["summary"]["removed"] == 2


def test_publish_callback_does_not_hide_pending_parent_leaf_repair(setup):
    writer, site, home = setup
    parent = article(home, "parent")
    child = article(parent, "child")
    with transaction.atomic():
        article(home, "another")  # Its callback runs before the deletion callback.
        child.delete()
    assert writer.exists("example.org/parent.md")
    assert not writer.exists("example.org/parent/index.md")
    assert parent.pk in {entry["id"] for entry in entries(writer)}
