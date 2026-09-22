"""Publication and cleanup against a storage backend with no filesystem API."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import storages
from django.db import close_old_connections, router, transaction
from sandbox.testapp.models import ArticlePage
from wagtail import hooks
from wagtail.models import Locale, Page, PageViewRestriction, Site

from wagtail_markdown_agents.checks import check_export_storage
from wagtail_markdown_agents.export.policy import ExportPathError
from wagtail_markdown_agents.export.storage import resolve_storage
from wagtail_markdown_agents.export.writer import FileWriter, StaleBuild, StorageContractError
from wagtail_markdown_agents.models import ExportArtifact, ExportFile, PageAgentSettings
from wagtail_markdown_agents.signals import markdown_deleted, markdown_generated

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def setup(settings):
    settings.STORAGES = {
        **settings.STORAGES,
        "exports": {"BACKEND": "tests.storage_backend.RemoteStorage"},
    }
    settings.WAGTAIL_MARKDOWN_AGENTS = {"STORAGE": "exports"}
    locale, _ = Locale.objects.get_or_create(language_code="en")
    root = Page.get_first_root_node() or Page.add_root(title="Root", slug="root", locale=locale)
    home = root.add_child(instance=Page(title="Home", slug="storage-home", locale=locale))
    Site.objects.all().delete()
    site = Site.objects.create(hostname="example.org", root_page=home, is_default_site=True)
    page = home.add_child(
        instance=ArticlePage(
            title="Article", slug="article", body=[("paragraph", "<p>Published</p>")]
        )
    )
    page.save_revision().publish()
    yield FileWriter(), storages["exports"], site, page
    Site.clear_site_root_paths_cache()


def read(writer, path):
    with writer.open(path) as stream:
        return stream.read().decode()


def test_renamed_save_keeps_logical_path_and_published_content(setup):
    writer, storage, site, page = setup
    record = writer.generate(page)
    assert record.logical_path == "example.org/article.md"
    assert record.file.storage_key.endswith(".renamed")
    assert record.file.storage_key != record.logical_path
    assert "Published" in read(writer, record.logical_path)
    assert writer.exists(record.logical_path)
    assert not writer.exists(record.file.storage_key)


def test_failed_upload_preserves_previous_export_and_sends_no_signal(setup):
    writer, storage, site, page = setup
    old = writer.generate(page)
    events = []

    def generated(sender, **kwargs):
        events.append(kwargs)

    markdown_generated.connect(generated, weak=False)
    storage.fail_save = True
    try:
        with pytest.raises(OSError, match="upload failed"):
            writer.publish(writer.begin(page), "Replacement")
    finally:
        markdown_generated.disconnect(generated)
    assert ExportArtifact.objects.get(pk=old.pk).file_id == old.file_id
    assert "Published" in read(writer, old.logical_path)
    assert not events


def test_path_change_cleans_prior_hook_path_only(setup):
    writer, storage, site, page = setup
    storage.files["example.org/unmanaged.md"] = b"unmanaged"
    with hooks.register_temporarily("markdown_export_path", lambda *args: "old/place.md"):
        old = writer.generate(page)
    with hooks.register_temporarily("markdown_export_path", lambda *args: "new/place.md"):
        new = writer.generate(page)
        assert "Published" in read(writer, new.logical_path)
    assert old.file.storage_key not in storage.files
    assert not ExportArtifact.objects.filter(logical_path=old.logical_path).exists()
    assert storage.files["example.org/unmanaged.md"] == b"unmanaged"


@pytest.mark.parametrize("change", ["publish", "move", "restrict", "ancestor", "exclude", "delete"])
def test_paused_build_cannot_publish_obsolete_content(setup, change):
    writer, storage, site, page = setup
    old = writer.generate(page)
    token = writer.begin(page)
    if change == "publish":
        page.refresh_from_db()
        page.body = [("paragraph", "<p>New revision</p>")]
        page.save_revision().publish()
    elif change == "move":
        destination = site.root_page.add_child(
            instance=Page(title="Destination", slug="destination")
        )
        page.move(destination, pos="last-child")
    elif change in {"restrict", "ancestor"}:
        PageViewRestriction.objects.create(
            page=page if change == "restrict" else site.root_page, restriction_type="login"
        )
    elif change == "exclude":
        PageAgentSettings.objects.create(page=page, excluded=True)
    else:
        page.delete()
    with pytest.raises(StaleBuild):
        writer.publish(token, "OBSOLETE")
    assert not writer.exists(old.logical_path)
    assert not any(value == b"OBSOLETE" for value in storage.files.values())


def test_revocation_invalidates_a_token_even_when_no_file_exists(setup):
    writer, storage, site, page = setup
    token = writer.begin(page)
    writer.delete_page(page.pk, site_id=site.pk)
    with pytest.raises(StaleBuild):
        writer.publish(token, "Obsolete")
    assert not ExportArtifact.objects.exists()


def test_state_is_rechecked_after_storage_io(setup):
    writer, storage, site, page = setup
    token = writer.begin(page)
    storage.after_save = lambda: PageAgentSettings.objects.create(page=page, excluded=True)
    with pytest.raises(StaleBuild):
        writer.publish(token, "Private")
    assert not ExportArtifact.objects.exists()
    assert not storage.files


def test_cleanup_failure_retries_owned_files_without_restoring_pointer(setup):
    writer, storage, site, page = setup
    record = writer.generate(page)
    storage.fail_delete = True
    writer.delete_page(page.pk, site_id=site.pk)
    assert not writer.exists(record.logical_path)
    assert ExportFile.objects.filter(cleanup_pending=True).exists()
    assert record.file.storage_key in storage.files
    storage.fail_delete = False
    writer.cleanup(site.pk)
    assert not ExportFile.objects.exists()
    assert not storage.files


def test_signal_identifiers_follow_commit_and_physical_deletion(setup):
    writer, storage, site, page = setup
    events = []

    def generated(sender, **kwargs):
        assert not transaction.get_connection().in_atomic_block
        assert ExportArtifact.objects.filter(logical_path=kwargs["path"]).exists()
        events.append(("generated", kwargs["page_id"], kwargs["path"]))

    def deleted(sender, **kwargs):
        assert kwargs["storage_key"] not in storage.files
        events.append(("deleted", kwargs["page_id"], kwargs["path"]))

    markdown_generated.connect(generated, weak=False)
    markdown_deleted.connect(deleted, weak=False)
    try:
        record = writer.generate(page)
        writer.delete_page(page.pk, site_id=site.pk)
        writer.delete_page(page.pk, site_id=site.pk)
    finally:
        markdown_generated.disconnect(generated)
        markdown_deleted.disconnect(deleted)
    assert events == [
        ("generated", page.pk, record.logical_path),
        ("deleted", page.pk, record.logical_path),
    ]


@pytest.mark.parametrize(
    "path",
    [
        "../escape.md",
        "/escape.md",
        "safe/../escape.md",
        "safe\\escape.md",
        "%2e%2e/escape.md",
        "safe/%2fescape.md",
        ".objects/escape.md",
        "safe//escape.md",
    ],
)
def test_unsafe_hook_paths_are_rejected_before_upload(setup, path):
    writer, storage, site, page = setup
    with (
        hooks.register_temporarily("markdown_export_path", lambda *args: path),
        pytest.raises(ExportPathError),
    ):
        writer.generate(page)
    assert not storage.files


def test_backend_cannot_redirect_ownership_outside_allocated_directory(setup):
    writer, storage, site, page = setup
    storage.return_key = "someone-elses-object.md"
    with pytest.raises(StorageContractError):
        writer.generate(page)
    assert not ExportArtifact.objects.exists()
    # The contract-violating backend wrote here; never delete an unowned key.
    assert "someone-elses-object.md" in storage.files


def test_aggregate_cannot_overwrite_page_owned_index(setup):
    writer, storage, site, page = setup
    child = page.add_child(instance=Page(title="Child", slug="child"))
    record = writer.generate(page)
    with pytest.raises(StorageContractError, match="owned"):
        writer.update_aggregate(site.pk, record.logical_path, lambda previous: "Navigation only")
    assert "Published" in read(writer, record.logical_path)
    assert child.pk


def test_page_write_withdraws_aggregates_and_stale_site_build(setup):
    writer, storage, site, page = setup
    writer.generate(page)
    path = "example.org/manifest.json"
    writer.update_aggregate(site.pk, path, lambda previous: '{"pages": ["Article"]}')
    token = writer.begin_site(site.pk, path)
    writer.publish(writer.begin(page), "Fresh render")
    assert not writer.exists(path)
    with pytest.raises(StaleBuild):
        writer.publish(token, "Old manifest")


def test_restriction_hides_aggregate_before_lifecycle_wiring(setup):
    writer, storage, site, page = setup
    writer.update_aggregate(site.pk, "example.org/llms.txt", lambda previous: "Article")
    PageViewRestriction.objects.create(page=page, restriction_type="login")
    assert not writer.exists("example.org/llms.txt")


def test_mutating_writer_requires_after_commit(setup):
    writer, storage, site, page = setup
    with transaction.atomic(), pytest.raises(RuntimeError, match="after commit"):
        writer.generate(page)
    assert not storage.files


def test_readers_keep_complete_old_file_while_upload_is_paused(setup):
    writer, storage, site, page = setup
    old = writer.generate(page)
    token = writer.begin(page)
    started, release = threading.Event(), threading.Event()

    def pause():
        started.set()
        assert release.wait(10)

    storage.after_save = pause

    def publish():
        close_old_connections()
        try:
            return FileWriter().publish(token, "New complete file")
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(publish)
        try:
            assert started.wait(10)
            opened = writer.open(old.logical_path)
            assert b"Published" in opened.read()
        finally:
            release.set()
        future.result(timeout=10)
        opened.seek(0)
        assert b"Published" in opened.read()
        opened.close()
    assert read(writer, old.logical_path) == "New complete file"


def test_concurrent_aggregate_updates_do_not_lose_entries(setup):
    writer, storage, site, page = setup
    path = "example.org/manifest.json"

    def append(number):
        close_old_connections()
        try:
            FileWriter().update_aggregate(
                site.pk, path, lambda previous: (previous or "") + str(number)
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(append, [1, 2]))
    assert sorted(read(writer, path)) == ["1", "2"]


def test_child_revocation_withdraws_page_owned_index_and_rejects_its_paused_build(setup):
    writer, storage, site, page = setup
    child = page.add_child(
        instance=ArticlePage(title="Child", slug="child", body=[("paragraph", "<p>Child</p>")])
    )
    child.save_revision().publish()
    index = writer.generate(page, navigation="## Children\n\nChild")
    token = writer.begin(page)
    PageViewRestriction.objects.create(page=child, restriction_type="login")
    assert not writer.exists(index.logical_path)
    writer.delete_page(child.pk, site_id=site.pk)
    assert index.file.storage_key not in storage.files
    with pytest.raises(StaleBuild):
        writer.publish(token, "Obsolete parent listing")


def test_revocation_rollback_leaves_safe_missing_file(setup):
    writer, storage, site, page = setup
    record = writer.generate(page)
    with transaction.atomic():
        PageViewRestriction.objects.create(page=page, restriction_type="login")
        writer.delete_page(page.pk, site_id=site.pk)
        assert record.file.storage_key not in storage.files
        transaction.set_rollback(True)
    assert ExportArtifact.objects.filter(pk=record.pk).exists()
    assert not writer.exists(record.logical_path)
    writer.generate(page)
    assert writer.exists(record.logical_path)


def test_corrupt_save_is_rejected_before_pointer_switch(setup):
    writer, storage, site, page = setup
    old = writer.generate(page)

    def corrupt():
        newest = next(reversed(storage.files))
        storage.files[newest] = b"truncated"

    storage.after_save = corrupt
    with pytest.raises(StorageContractError, match="complete"):
        writer.publish(writer.begin(page), "Replacement")
    assert "Published" in read(writer, old.logical_path)


def test_database_publication_failure_cleans_candidate_and_keeps_old_file(setup, monkeypatch):
    writer, storage, site, page = setup
    old = writer.generate(page)

    def broken(*args):
        raise RuntimeError("database publication failed")

    monkeypatch.setattr(writer, "_swap", broken)
    with pytest.raises(RuntimeError, match="publication failed"):
        writer.publish(writer.begin(page), "Candidate")
    assert list(storage.files) == [old.file.storage_key]
    assert "Published" in read(writer, old.logical_path)


def test_default_storage_is_private_export_directory(setup, settings, tmp_path):
    writer, storage, site, page = setup
    settings.WAGTAIL_MARKDOWN_AGENTS = {}
    settings.BASE_DIR = tmp_path
    record = writer.generate(page)
    assert (tmp_path / "markdown_export" / record.file.storage_key).is_file()
    assert "Published" in read(writer, record.logical_path)
    writer.delete_site(site.pk)
    assert not (tmp_path / "markdown_export" / record.file.storage_key).exists()


def test_storage_config_changes_do_not_delete_from_rebound_alias(setup, settings):
    writer, storage, site, page = setup
    record = writer.generate(page)
    settings.STORAGES = {
        **settings.STORAGES,
        "exports": {
            "BACKEND": "tests.storage_backend.RemoteStorage",
            "OPTIONS": {"region": "different"},
        },
    }
    new_storage = storages["exports"]
    new_storage.files[record.file.storage_key] = b"Unrelated object in a different backend"
    writer.delete_page(page.pk, site_id=site.pk)
    assert ExportFile.objects.filter(pk=record.file_id, cleanup_pending=True).exists()
    assert new_storage.files[record.file.storage_key].startswith(b"Unrelated")


def test_missing_base_dir_has_a_clear_system_check(settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {}
    del settings.BASE_DIR
    errors = check_export_storage(None)
    assert len(errors) == 1
    assert errors[0].id == "wagtail_markdown_agents.E001"
    assert "BASE_DIR" in errors[0].msg and "STORAGE" in errors[0].msg
    with pytest.raises(ImproperlyConfigured, match="BASE_DIR"):
        resolve_storage()


@pytest.mark.parametrize("alias", ["missing", [], False, 42])
def test_invalid_storage_alias_has_a_clear_system_check(settings, alias):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"STORAGE": alias}
    assert check_export_storage(None)[0].id == "wagtail_markdown_agents.E001"


def test_receiver_failure_does_not_turn_committed_publication_into_a_failure(setup, caplog):
    writer, storage, site, page = setup

    def broken(sender, **kwargs):
        raise RuntimeError("receiver broke")

    markdown_generated.connect(broken, weak=False)
    try:
        record = writer.generate(page)
    finally:
        markdown_generated.disconnect(broken)
    assert writer.exists(record.logical_path)
    assert "receiver broke" in caplog.text


def test_new_draft_does_not_hide_the_published_export(setup):
    writer, storage, site, page = setup
    record = writer.generate(page)
    page.body = [("paragraph", "<p>Draft</p>")]
    page.save_revision()
    assert "Published" in read(writer, record.logical_path)


def test_site_deletion_only_removes_owned_objects_in_that_scope(setup, settings):
    writer, storage, site, page = setup
    settings.WAGTAIL_MARKDOWN_AGENTS = {"STORAGE": "exports", "SITES": "all"}
    first = writer.generate(page)
    other_root = Page.get_first_root_node().add_child(
        instance=Page(title="Other root", slug="other")
    )
    other_site = Site.objects.create(hostname="other.org", root_page=other_root)
    other = other_root.add_child(
        instance=ArticlePage(title="Other", slug="article", body=[("paragraph", "<p>Other</p>")])
    )
    other.save_revision().publish()
    second = writer.generate(other)
    storage.files["example.org/manual.txt"] = b"Unmanaged"
    writer.delete_site(site.pk)
    assert first.file.storage_key not in storage.files
    assert "Other" in read(writer, second.logical_path)
    assert storage.files["example.org/manual.txt"] == b"Unmanaged"
    assert second.scope.site_id == other_site.pk


def test_rebuilding_page_owned_indexes_preserves_each_authored_body(setup):
    writer, storage, site, page = setup
    other = site.root_page.add_child(
        instance=ArticlePage(
            title="Other index",
            slug="other-index",
            body=[("paragraph", "<p>Other authored body</p>")],
        )
    )
    other.save_revision().publish()
    page.add_child(instance=Page(title="Child one", slug="child"))
    other.add_child(instance=Page(title="Child two", slug="child"))
    first = writer.generate(page, navigation="Listing one")
    second = writer.generate(other, navigation="Listing two")
    assert "Published" in read(writer, first.logical_path)
    assert "Listing one" in read(writer, first.logical_path)
    assert "Other authored body" in read(writer, second.logical_path)
    assert "Listing two" in read(writer, second.logical_path)


def test_actual_revocation_during_paused_upload_cannot_be_undone(setup):
    writer, storage, site, page = setup
    old = writer.generate(page)
    token = writer.begin(page)
    started, release = threading.Event(), threading.Event()

    def pause():
        started.set()
        assert release.wait(10)

    storage.after_save = pause

    def publish():
        close_old_connections()
        try:
            return FileWriter().publish(token, "Obsolete upload")
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(publish)
        try:
            assert started.wait(10)
            with transaction.atomic():
                PageViewRestriction.objects.create(page=page, restriction_type="login")
                writer.delete_page(page.pk, site_id=site.pk)
            assert not writer.exists(old.logical_path)
        finally:
            release.set()
        with pytest.raises(StaleBuild):
            future.result(timeout=10)
    assert not ExportArtifact.objects.exists()
    assert not storage.files


@pytest.mark.parametrize("route", ["db_for_read", "db_for_write"])
def test_routed_databases_are_rejected_instead_of_using_an_unrelated_lock(monkeypatch, route):
    monkeypatch.setattr(router, route, lambda model: "replica")
    with pytest.raises(ImproperlyConfigured, match="default database"):
        FileWriter()


def test_hook_collision_cannot_replace_another_pages_file(setup):
    writer, storage, site, page = setup
    other = site.root_page.add_child(
        instance=ArticlePage(title="Other", slug="other", body=[("paragraph", "<p>Other</p>")])
    )
    other.save_revision().publish()
    with hooks.register_temporarily("markdown_export_path", lambda *args: "shared.md"):
        old = writer.generate(page)
        with pytest.raises(StorageContractError, match="owned"):
            writer.generate(other)
        assert "Published" in read(writer, old.logical_path)
        assert len(storage.files) == 1
