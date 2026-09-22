"""Move and published-slug subtree lifecycle, using real Wagtail actions (#69)."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from wagtail import hooks
from wagtail.models import Page, PageViewRestriction, Site
from wagtail.signals import page_slug_changed, pre_page_move

from tests import test_lifecycle
from tests.test_indexes import article, read
from tests.test_lifecycle import entries
from wagtail_markdown_agents import tasks
from wagtail_markdown_agents.models import ExportArtifact

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.export_lifecycle]
setup = test_lifecycle.setup


def rename(page, slug):
    page.slug = slug
    page.save_revision().publish()


@pytest.mark.parametrize("event", ["rename", "move"])
def test_subtree_paths_and_discovery_follow_current_identity(setup, event):
    writer, site, home = setup
    source = article(home, "source")
    destination = article(home, "destination")
    branch = article(source, "branch")
    child = article(branch, "child")
    old = list(
        ExportArtifact.objects.filter(page_id__in=[branch.pk, child.pk]).select_related("file")
    )
    if event == "rename":
        rename(branch, "renamed")
        prefix = "source/renamed"
    else:
        branch.move(destination, pos="last-child")
        prefix = "destination/branch"
        assert writer.exists("example.org/source.md")
        assert not writer.exists("example.org/source/index.md")
        assert writer.exists("example.org/destination/index.md")
        assert not writer.exists("example.org/destination.md")
    assert "branch body." in read(writer, f"example.org/{prefix}/index.md")
    output = read(writer, f"example.org/{prefix}/child.md")
    assert "child body." in output
    assert f"permalink: http://example.org/{prefix}/child/" in output
    for record in old:
        assert not writer.exists(record.logical_path)
        assert not writer._backend(record.file).exists(record.file.storage_key)
    documents = {entry["id"]: entry for entry in entries(writer)}
    assert set(documents) == {home.pk, source.pk, destination.pk, branch.pk, child.pk}
    assert documents[child.pk]["path"] == f"example.org/{prefix}/child.md"
    discovery = read(writer, "example.org/llms.txt")
    assert "/markdown/index.md" in discovery
    if event == "move":
        assert "/markdown/source.md" in discovery
        assert "/markdown/destination/index.md" in discovery
    assert f"/markdown/{prefix}/child.md" in read(writer, f"example.org/{prefix}/index.md")


@pytest.mark.parametrize("event", ["rename", "move"])
def test_path_changes_wait_for_commit_and_rollback_preserves_files(setup, monkeypatch, event):
    writer, site, home = setup
    destination = article(home, "destination")
    branch = article(home, "branch")
    child = article(branch, "child")
    records = list(ExportArtifact.objects.select_related("file"))
    pending = []
    original = tasks.enqueue

    def enqueue(fn, *args, **kwargs):
        assert transaction.get_autocommit()
        pending.append(kwargs)
        return original(fn, *args, **kwargs)

    monkeypatch.setattr(tasks, "enqueue", enqueue)
    with pytest.raises(RuntimeError, match="rollback"), transaction.atomic():
        if event == "rename":
            rename(branch, "renamed")
        else:
            branch.move(destination, pos="last-child")
        assert pending == []
        for record in records:
            assert writer._backend(record.file).exists(record.file.storage_key)
        raise RuntimeError("rollback")
    assert pending == []
    assert writer.exists("example.org/branch/child.md")
    assert Page.objects.get(pk=child.pk).url_path.endswith("/branch/child/")


@pytest.mark.parametrize("auto", [False, True])
@pytest.mark.parametrize("event", ["rename", "move"])
def test_cleanup_is_after_commit_and_independent_of_queue(
    setup, settings, monkeypatch, auto, event
):
    writer, site, home = setup
    destination = article(home, "destination")
    branch = article(home, "branch")
    child = article(branch, "child")
    old = ExportArtifact.objects.select_related("file").get(page_id=child.pk)
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "AUTO_GENERATE": auto}
    pending = []
    monkeypatch.setattr(tasks, "enqueue", lambda fn, **kwargs: pending.append((fn, kwargs)))
    with transaction.atomic():
        if event == "rename":
            rename(branch, "renamed")
            prefix = "renamed"
        else:
            branch.move(destination, pos="last-child")
            prefix = "destination/branch"
        assert writer._backend(old.file).exists(old.file.storage_key)
        assert pending == []
    assert not writer._backend(old.file).exists(old.file.storage_key)
    assert not writer.exists("example.org/manifest.json")
    assert bool(pending) == auto
    for fn, kwargs in pending:
        fn(**kwargs)
    assert writer.exists(f"example.org/{prefix}/child.md") == auto


@pytest.mark.parametrize("change", ["delete", "restrict", "unpublish", "draft"])
def test_move_callback_refetches_descendants(setup, monkeypatch, change):
    writer, site, home = setup
    destination = article(home, "destination")
    branch = article(home, "branch")
    child = article(branch, "child")
    child_id = child.pk
    pending = []
    monkeypatch.setattr(tasks, "enqueue", lambda fn, **kwargs: pending.append((fn, kwargs)))
    branch.move(destination, pos="last-child")
    child.refresh_from_db()
    if change == "delete":
        child.delete()
    elif change == "restrict":
        PageViewRestriction.objects.create(page=child, restriction_type="login")
    elif change == "unpublish":
        child.unpublish()
    else:
        child.body = [("paragraph", "<p>PRIVATE DRAFT</p>")]
        child.save_revision()
    for fn, kwargs in pending:
        fn(**kwargs)
    if change == "draft":
        output = read(writer, "example.org/destination/branch/child.md")
        assert "child body." in output and "PRIVATE DRAFT" not in output
    else:
        assert not ExportArtifact.objects.filter(page_id=child_id).exists()
        assert child_id not in {entry["id"] for entry in entries(writer)}


@pytest.mark.parametrize("event", ["rename", "move"])
def test_old_hook_paths_and_actual_storage_keys_are_retired(setup, event):
    writer, site, home = setup
    destination = article(home, "destination")
    with hooks.register_temporarily(
        "markdown_export_path", lambda path, page, site: f"archive/{page.pk}.md"
    ):
        branch = article(home, "branch")
        child = article(branch, "child")
        records = list(ExportArtifact.objects.select_related("file"))
    if event == "rename":
        rename(branch, "renamed")
        prefix = "renamed"
    else:
        branch.move(destination, pos="last-child")
        prefix = "destination/branch"
    for record in records:
        assert not writer._backend(record.file).exists(record.file.storage_key)
        if record.logical_path.startswith("example.org/archive/"):
            assert not writer.exists(record.logical_path)
    assert writer.exists(f"example.org/{prefix}/child.md")
    assert child.pk in {entry["id"] for entry in entries(writer)}


def test_draft_slug_does_not_relocate_published_subtree(setup):
    writer, site, home = setup
    branch = article(home, "branch")
    article(branch, "child")
    branch.slug = "draft-slug"
    branch.save_revision()
    assert writer.exists("example.org/branch/child.md")
    assert not writer.exists("example.org/draft-slug/child.md")


@pytest.mark.parametrize("event", ["rename", "move"])
def test_old_urls_use_html_redirects_and_removed_exports_are_404(setup, client, event):
    writer, site, home = setup
    destination = article(home, "destination")
    branch = article(home, "branch")
    article(branch, "child")
    if event == "rename":
        rename(branch, "renamed")
        prefix = "renamed"
    else:
        branch.move(destination, pos="last-child")
        prefix = "destination/branch"
    response = client.get("/branch/child/", HTTP_HOST="example.org", HTTP_ACCEPT="text/markdown")
    assert response.status_code == 301
    assert response["Location"].endswith(f"/{prefix}/child/")
    response = client.get("/branch/child/?output_format=md", HTTP_HOST="example.org")
    assert response.status_code == 301
    assert f"/{prefix}/child/" in response["Location"]
    assert client.get("/markdown/branch/child.md", HTTP_HOST="example.org").status_code == 404
    response = client.get(f"/markdown/{prefix}/child.md", HTTP_HOST="example.org")
    assert response.status_code == 200
    response.close()


def test_reorder_keeps_current_files_without_export_work(setup, monkeypatch):
    writer, site, home = setup
    first = article(home, "first")
    second = article(home, "second")
    previous = set(ExportArtifact.objects.values_list("file_id", flat=True))
    pending = []
    monkeypatch.setattr(tasks, "enqueue", lambda *args, **kwargs: pending.append(kwargs))
    second.move(first, pos="left")
    assert pending == []
    assert set(ExportArtifact.objects.values_list("file_id", flat=True)) == previous
    assert writer.exists("example.org/second.md")


@pytest.mark.parametrize("enabled", [False, True])
def test_cross_site_move_cleans_old_scope_and_checks_destination_policy(setup, settings, enabled):
    writer, site, home = setup
    # Build another root without generating it in the source site first.
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "AUTO_GENERATE": False}
    other_home = article(home.get_parent(), "other-home")
    other = Site.objects.create(hostname="other.org", root_page=other_home)
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        **settings.WAGTAIL_MARKDOWN_AGENTS,
        "AUTO_GENERATE": True,
        "SITES": "all" if enabled else "default",
    }
    branch = article(home, "branch")
    child = article(branch, "child")
    old = list(ExportArtifact.objects.filter(page_id=child.pk).select_related("file"))
    branch.move(other_home, pos="last-child")
    assert not ExportArtifact.objects.filter(scope__site_id=site.pk, page_id=child.pk).exists()
    for record in old:
        assert not writer._backend(record.file).exists(record.file.storage_key)
    assert child.pk not in {entry["id"] for entry in entries(writer)}
    assert writer.exists("other.org/branch/child.md") == enabled
    assert writer.exists("other.org/manifest.json") == enabled
    if enabled:
        assert ExportArtifact.objects.get(page_id=child.pk).scope.site_id == other.pk


def test_move_into_and_out_of_restricted_parent_rechecks_subtree(setup):
    writer, site, home = setup
    private = article(home, "private")
    PageViewRestriction.objects.create(page=private, restriction_type="login")
    branch = article(home, "branch")
    child = article(branch, "child")
    branch.move(private, pos="last-child")
    assert not ExportArtifact.objects.filter(page_id__in=[branch.pk, child.pk]).exists()
    branch.refresh_from_db()
    branch.move(home, pos="last-child")
    assert writer.exists("example.org/branch/child.md")
    assert child.pk in {entry["id"] for entry in entries(writer)}


def test_move_then_delete_in_one_transaction_never_recreates_subtree(setup):
    writer, site, home = setup
    destination = article(home, "destination")
    branch = article(home, "branch")
    child = article(branch, "child")
    ids = (branch.pk, child.pk)
    with transaction.atomic():
        branch.move(destination, pos="last-child")
        branch.refresh_from_db()
        branch.delete()
    assert not ExportArtifact.objects.filter(page_id__in=ids).exists()
    assert writer.exists("example.org/destination.md")
    assert writer.exists("example.org/manifest.json")


def test_multiple_moves_before_commit_only_export_final_location(setup):
    writer, site, home = setup
    first = article(home, "first")
    second = article(home, "second")
    branch = article(home, "branch")
    article(branch, "child")
    with transaction.atomic():
        branch.move(first, pos="last-child")
        branch.refresh_from_db()
        branch.move(second, pos="last-child")
    assert not writer.exists("example.org/branch/child.md")
    assert not writer.exists("example.org/first/branch/child.md")
    assert writer.exists("example.org/second/branch/child.md")
    assert writer.exists("example.org/first.md")


def test_rename_then_move_and_delete_former_parent_before_commit(setup):
    writer, site, home = setup
    source = article(home, "source")
    destination = article(home, "destination")
    branch = article(source, "branch")
    child = article(branch, "child")
    with transaction.atomic():
        rename(branch, "renamed")
        branch.refresh_from_db()
        branch.move(destination, pos="last-child")
        source.refresh_from_db()
        source.delete()
    assert writer.exists("example.org/destination/renamed/child.md")
    assert not writer.exists("example.org/source/branch/child.md")
    assert child.pk in {entry["id"] for entry in entries(writer)}


@pytest.mark.parametrize("signal", [pre_page_move, page_slug_changed])
def test_path_signals_reject_unsupported_write_database(setup, signal):
    writer, site, home = setup
    with pytest.raises(ImproperlyConfigured, match="default database"):
        signal.send(
            sender=type(home),
            instance=home,
            instance_before=home,
            parent_page_before=home.get_parent(),
            url_path_before=home.url_path,
            url_path_after="/changed/",
            using="other",
        )
