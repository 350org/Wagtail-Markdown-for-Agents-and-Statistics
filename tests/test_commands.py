"""Operator scopes, read-only planning and managed publication commands (#24)."""

import json
from io import StringIO

import pytest
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from sandbox.testapp.models import ArticlePage, ContentPage
from wagtail import hooks
from wagtail.models import Page, Site

from tests import test_indexes
from tests.test_indexes import article, read
from wagtail_markdown_agents.export.indexes import IndexBatch
from wagtail_markdown_agents.export.storage import resolve_storage
from wagtail_markdown_agents.export.writer import FileWriter
from wagtail_markdown_agents.models import (
    ExportArtifact,
    ExportFile,
    ExportScope,
    PageAgentSettings,
)

pytestmark = pytest.mark.django_db(transaction=True)
setup = test_indexes.setup


def run(name, *args, **kwargs):
    output = StringIO()
    call_command(name, *args, stdout=output, stderr=output, **kwargs)
    return output.getvalue()


def inventory():
    return [
        list(model.objects.order_by("pk").values())
        for model in (ExportScope, ExportFile, ExportArtifact)
    ]


def test_generate_scoped_pages_finalises_site_once_and_reports_counts(setup, monkeypatch):
    writer, site, home = setup
    first, second = article(home, "first"), article(home, "second")
    calls = []
    original = IndexBatch.finalise

    def finalise(self):
        calls.append(set(self.dirty))
        return original(self)

    monkeypatch.setattr(IndexBatch, "finalise", finalise)
    output = run("agentmd_generate", "--site", site.hostname)
    assert "generated=3" in output and "failed=0" in output
    assert calls == [{site.pk}]
    assert writer.exists("example.org/first.md")
    assert writer.exists("example.org/second.md")
    manifest = json.loads(read(writer, "example.org/manifest.json"))
    assert {entry["id"] for entry in manifest["documents"]} == {home.pk, first.pk, second.pk}


def test_generate_exports_lists_and_serves_live_pages_without_a_revision(setup, client):
    writer, site, home = setup
    imported = home.add_child(
        instance=ArticlePage(
            title="Imported", slug="imported", body=[("paragraph", "<p>Imported body.</p>")]
        )
    )
    assert imported.live_revision_id is None
    output = run("agentmd_generate", "--site", site.hostname)
    assert "failed=0" in output
    assert "Imported body." in read(writer, "example.org/imported.md")
    assert "imported.md" in read(writer, "example.org/index.md")
    manifest = json.loads(read(writer, "example.org/manifest.json"))
    assert imported.pk in {entry["id"] for entry in manifest["documents"]}
    output = run("agentmd_generate", "--page-id", str(imported.pk))
    assert "skipped=1" in output  # unchanged row state is current

    imported.save_revision().publish()  # a first publication supersedes the row state
    output = run("agentmd_generate", "--page-id", str(imported.pk))
    assert "generated=1" in output


def test_freshness_skip_force_and_missing_file_repair(setup):
    writer, site, home = setup
    page = article(home, "article")
    run("agentmd_generate", "--site", site.hostname)
    old = inventory()
    output = run("agentmd_generate", "--page-id", str(page.pk))
    assert "generated=0" in output and "skipped=1" in output
    assert inventory() == old
    output = run("agentmd_generate", "--page-id", str(page.pk), "--force")
    assert "generated=1" in output
    record = ExportArtifact.objects.select_related("file").get(page_id=page.pk)
    writer._backend(record.file).delete(record.file.storage_key)
    output = run("agentmd_generate", "--page-id", str(page.pk))
    assert "generated=1" in output
    assert writer.exists(record.logical_path)


@pytest.mark.parametrize(
    "command", ["agentmd_generate", "agentmd_generate_indexes", "agentmd_delete"]
)
@pytest.mark.parametrize("existing", [False, True])
def test_dry_run_never_writes_even_with_combined_flags(setup, monkeypatch, command, existing):
    writer, site, home = setup
    page = article(home, "article")
    if existing:
        run("agentmd_generate")
    before = inventory()

    def forbidden(*args, **kwargs):
        pytest.fail("Dry run attempted mutation")

    monkeypatch.setattr(FileWriter, "begin", forbidden)
    monkeypatch.setattr(FileWriter, "begin_site", forbidden)
    monkeypatch.setattr(FileWriter, "delete_page", forbidden)
    monkeypatch.setattr(FileWriter, "delete_site", forbidden)
    monkeypatch.setattr(IndexBatch, "finalise", forbidden)
    monkeypatch.setattr("builtins.input", forbidden)
    extra = ["--force"] if command == "agentmd_generate" else []
    output = run(
        command,
        "--page-id",
        str(page.pk),
        "--site",
        site.hostname,
        "--type",
        "testapp.ArticlePage",
        "--dry-run",
        *extra,
    )
    assert "Dry run" in output
    assert inventory() == before


@pytest.mark.parametrize(
    "command", ["agentmd_generate", "agentmd_generate_indexes", "agentmd_status"]
)
@pytest.mark.parametrize(
    "args",
    [
        ["--page-id", "999999"],
        ["--page-id", "0"],
        ["--type", "bad.Type"],
        ["--type", "auth.User"],
        ["--site", "missing.org"],
    ],
)
def test_invalid_scopes_fail_before_writing(setup, command, args):
    before = inventory()
    with pytest.raises(CommandError):
        run(command, *args)
    assert inventory() == before


def test_unsupported_explicit_generation_is_rejected_but_bulk_skips(setup):
    writer, site, home = setup
    unsupported = home.add_child(instance=Page(title="Unsupported", slug="unsupported"))
    unsupported.save_revision().publish()
    with pytest.raises(CommandError, match="unsupported"):
        run("agentmd_generate", "--page-id", str(unsupported.pk))
    with pytest.raises(CommandError, match="unsupported"):
        run("agentmd_generate", "--type", "wagtailcore.Page")
    output = run("agentmd_generate")
    assert "skipped=1" in output and "generated=1" in output
    assert not ExportArtifact.objects.filter(page_id=unsupported.pk).exists()


def test_filters_intersect_and_preserve_other_types_and_sites(setup, settings):
    writer, site, home = setup
    page = article(home, "article")
    content = home.add_child(
        instance=ContentPage(title="Content", slug="content", body=[("paragraph", "<p>Body</p>")])
    )
    content.save_revision().publish()
    other_home = article(home.get_parent(), "other-home")
    Site.objects.create(hostname="other.org", root_page=other_home)
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "SITES": "all"}
    other_page = article(other_home, "other")
    run("agentmd_generate")
    retained = list(
        ExportArtifact.objects.filter(page_id__in=[content.pk, other_page.pk]).select_related(
            "file"
        )
    )
    assert len(retained) == 2
    run("agentmd_generate", "--type", "testapp.ArticlePage", "--site", site.hostname, "--force")
    for record in retained:
        assert ExportArtifact.objects.get(pk=record.pk).file_id == record.file_id
        assert writer.exists(record.logical_path)
    with pytest.raises(CommandError, match="match"):
        run("agentmd_generate", "--page-id", str(page.pk), "--site", "other.org")


def test_failed_page_reports_nonzero_and_does_not_finalise_failed_site(setup, monkeypatch):
    writer, site, home = setup
    first, second = article(home, "first"), article(home, "second")
    original = FileWriter._upload

    def upload(self, file, text):
        if file.page_id == second.pk:
            raise OSError("Upload failed")
        return original(self, file, text)

    monkeypatch.setattr(FileWriter, "_upload", upload)
    output = StringIO()
    with pytest.raises(CommandError):
        call_command("agentmd_generate", stdout=output, stderr=output)
    assert "failed=" in output.getvalue() and "Upload failed" in output.getvalue()
    assert writer.exists("example.org/first.md")
    assert not writer.exists("example.org/manifest.json")
    assert not ExportArtifact.objects.filter(page_id=second.pk).exists()
    assert first.pk != second.pk


def test_status_reports_current_missing_ineligible_and_storage_errors_without_writes(
    setup, monkeypatch
):
    writer, site, home = setup
    current, missing, private = (
        article(home, "current"),
        article(home, "missing"),
        article(home, "private"),
    )
    PageAgentSettings.objects.create(page=private, excluded=True)
    run("agentmd_generate", "--page-id", str(current.pk))
    before = inventory()
    output = run("agentmd_status")
    assert f"Page {current.pk}: current" in output
    assert f"Page {missing.pk}: missing" in output
    assert f"Page {private.pk}: ineligible" in output
    assert inventory() == before

    def fail(*args, **kwargs):
        raise OSError("Storage unavailable")

    monkeypatch.setattr(FileWriter, "open", fail)
    output = StringIO()
    with pytest.raises(CommandError):
        call_command("agentmd_status", page_id=current.pk, stdout=output, stderr=output)
    assert "Storage unavailable" in output.getvalue()
    assert inventory() == before


def test_generate_indexes_repairs_discovery_without_generating_unowned_leaves(setup):
    writer, site, home = setup
    child, missing = article(home, "child"), article(home, "missing")
    writer.generate(child)
    output = run("agentmd_generate_indexes", "--site", site.hostname)
    assert "failed=0" in output
    assert "child.md" in read(writer)
    assert writer.exists("example.org/llms.txt")
    assert writer.exists("example.org/manifest.json")
    assert not ExportArtifact.objects.filter(page_id=missing.pk).exists()


def test_delete_page_only_withdraws_owned_files_and_dependencies(setup):
    writer, site, home = setup
    child, unrelated = article(home, "child"), article(home, "unrelated")
    with hooks.register_temporarily(
        "markdown_export_path", lambda path, page, site: f"custom/{page.pk}.md"
    ):
        run("agentmd_generate")
        old = ExportArtifact.objects.select_related("file").get(page_id=child.pk)
        retained = ExportArtifact.objects.get(page_id=unrelated.pk)
    storage = resolve_storage()[0]
    unmanaged = storage.save("unmanaged.md", ContentFile(b"keep me"))
    with hooks.register_temporarily(
        "markdown_export_path", lambda path, page, site: f"custom/{page.pk}.md"
    ):
        output = run("agentmd_delete", "--page-id", str(child.pk))
        assert writer.exists("example.org/manifest.json")
        assert f"custom/{child.pk}.md" not in read(writer, "example.org/llms.txt")
    assert "deleted=1" in output
    assert not ExportArtifact.objects.filter(page_id=child.pk).exists()
    assert not writer._backend(old.file).exists(old.file.storage_key)
    assert ExportArtifact.objects.get(pk=retained.pk).file_id == retained.file_id
    assert storage.exists(unmanaged)


@pytest.mark.parametrize("args", [[], ["--all", "--site", "example.org"]])
def test_delete_requires_unambiguous_explicit_scope(setup, args):
    with pytest.raises(CommandError):
        run("agentmd_delete", *args)


def test_broad_delete_confirmation_and_yes(setup, monkeypatch):
    writer, site, home = setup
    article(home, "child")
    run("agentmd_generate")
    before = inventory()
    monkeypatch.setattr("builtins.input", lambda *args: "no")
    with pytest.raises(CommandError, match="cancelled"):
        run("agentmd_delete", "--site", site.hostname)
    assert inventory() == before
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("Unexpected prompt"))
    output = run("agentmd_delete", "--all", "--yes")
    assert "failed=0" in output
    assert not ExportArtifact.objects.exists()
    assert not ExportFile.objects.exists()


def test_delete_reports_pending_cleanup_and_can_retry(setup, monkeypatch):
    writer, site, home = setup
    page = article(home, "page")
    run("agentmd_generate")
    storage = resolve_storage()[0]
    original = type(storage).delete

    def fail_delete(*args):
        raise OSError("Busy")

    monkeypatch.setattr(type(storage), "delete", fail_delete)
    with pytest.raises(CommandError, match="cleanup"):
        run("agentmd_delete", "--all", "--yes")
    assert not ExportArtifact.objects.exists()
    assert ExportFile.objects.filter(cleanup_pending=True).exists()
    monkeypatch.setattr(type(storage), "delete", original)
    run("agentmd_delete", "--all", "--yes")
    assert not ExportFile.objects.exists()
    assert Page.objects.filter(pk=page.pk).exists()


def test_force_refreshes_hook_content_and_only_renders_published_revision(setup):
    writer, site, home = setup
    page = article(home, "page")
    related = {"text": "Initial related content"}
    with hooks.register_temporarily(
        "markdown_post_render", lambda markdown, page, context: markdown + "\n" + related["text"]
    ):
        run("agentmd_generate", "--page-id", str(page.pk))
        related["text"] = "Changed related content"
        page.body = [("paragraph", "<p>PRIVATE DRAFT</p>")]
        page.save_revision()
        run("agentmd_generate", "--page-id", str(page.pk))
        assert "Initial related content" in read(writer, "example.org/page.md")
        run("agentmd_generate", "--page-id", str(page.pk), "--force")
    text = read(writer, "example.org/page.md")
    assert "Changed related content" in text and "PRIVATE DRAFT" not in text


def test_scoped_delete_preserves_other_site_and_type_and_cms_content(setup, settings):
    writer, site, home = setup
    page = article(home, "page")
    other_type = home.add_child(
        instance=ContentPage(title="Content", slug="content", body=[("paragraph", "<p>Body</p>")])
    )
    other_type.save_revision().publish()
    other_home = article(home.get_parent(), "other-home")
    other_site = Site.objects.create(hostname="other.org", root_page=other_home)
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "SITES": "all"}
    article(other_home, "other")
    run("agentmd_generate")
    retained = list(ExportArtifact.objects.filter(scope__site_id=other_site.pk).values())
    other_record = ExportArtifact.objects.get(page_id=other_type.pk)
    run("agentmd_delete", "--site", site.hostname, "--type", "testapp.ArticlePage", "--yes")
    assert not ExportArtifact.objects.filter(page_id=page.pk).exists()
    assert ExportArtifact.objects.get(pk=other_record.pk).file_id == other_record.file_id
    assert list(ExportArtifact.objects.filter(scope__site_id=other_site.pk).values()) == retained
    assert Page.objects.filter(pk=page.pk, live=True).exists()
    assert writer.exists("example.org/manifest.json")
    assert not ExportArtifact.objects.filter(page_id__in=[home.pk, page.pk]).exists()


@pytest.mark.parametrize(
    "command", ["agentmd_generate", "agentmd_generate_indexes", "agentmd_delete"]
)
def test_writing_commands_reject_caller_transaction_before_mutation(setup, command):
    writer, site, home = setup
    page = article(home, "page")
    run("agentmd_generate")
    before = inventory()
    with transaction.atomic(), pytest.raises(CommandError, match="after commit"):
        run(command, "--page-id", str(page.pk))
    assert inventory() == before


def test_all_delete_cleans_orphaned_site_and_page_ownership(setup):
    writer, site, home = setup
    page = article(home, "page")
    run("agentmd_generate")
    home.delete()  # Component fixture disconnects lifecycle revocation.
    assert not Site.objects.filter(pk=site.pk).exists()
    assert ExportArtifact.objects.filter(page_id=page.pk).exists()
    run("agentmd_delete", "--all", "--yes")
    assert not ExportArtifact.objects.exists()
    assert not ExportFile.objects.exists()


@pytest.mark.parametrize("command", ["agentmd_generate", "agentmd_generate_indexes"])
def test_discovery_failure_returns_nonzero_without_manifest_success(setup, monkeypatch, command):
    writer, site, home = setup
    page = article(home, "page")
    writer.generate(page)
    original = FileWriter._upload

    def fail_index(self, file, text):
        if file.logical_path.endswith("/index.md"):
            raise OSError("Index upload failed")
        return original(self, file, text)

    monkeypatch.setattr(FileWriter, "_upload", fail_index)
    output = StringIO()
    with pytest.raises(CommandError):
        call_command(command, stdout=output, stderr=output)
    assert "Index upload failed" in output.getvalue()
    assert not writer.exists("example.org/manifest.json")


def test_status_reports_missing_bytes_as_unavailable_and_dry_run_plans_discovery(setup):
    writer, site, home = setup
    page = article(home, "page")
    record = writer.generate(page)
    before = inventory()
    output = run("agentmd_generate", "--page-id", str(page.pk), "--dry-run")
    assert "generated=0" in output and "discovery_scopes=1" in output
    assert inventory() == before
    writer._backend(record.file).delete(record.file.storage_key)
    output = run("agentmd_status", "--page-id", str(page.pk))
    assert "unavailable=1" in output and "failed=0" in output


def test_empty_body_is_reported_as_skipped_not_success(setup):
    writer, site, home = setup
    page = article(home, "empty")
    page.body = []
    page.save_revision().publish()
    output = run("agentmd_generate", "--page-id", str(page.pk))
    assert "empty_body" in output and "generated=0" in output and "skipped=1" in output
    assert not ExportArtifact.objects.filter(page_id=page.pk).exists()


def test_delete_index_preserves_body_of_survivors_without_recreating_selected_page(setup, settings):
    writer, site, home = setup
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        **settings.WAGTAIL_MARKDOWN_AGENTS,
        "INCLUDE_HIERARCHY": True,
    }
    parent = article(home, "parent")
    child = article(parent, "child")
    sibling = article(home, "sibling")
    run("agentmd_generate")
    output = run("agentmd_delete", "--page-id", str(parent.pk))
    assert "discovery_scopes=1" in output
    assert not ExportArtifact.objects.filter(page_id=parent.pk).exists()
    assert "parent body." not in read(writer, "example.org/parent/index.md")
    assert "child body." in read(writer, "example.org/parent/child.md")
    assert "sibling body." in read(writer, "example.org/sibling.md")
    manifest = json.loads(read(writer, "example.org/manifest.json"))
    assert {entry["id"] for entry in manifest["documents"]} == {home.pk, child.pk, sibling.pk}


def test_all_delete_dry_run_with_yes_preserves_inventory_and_never_prompts(setup, monkeypatch):
    writer, site, home = setup
    article(home, "page")
    run("agentmd_generate")
    before = inventory()
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("Dry run prompted"))
    output = run("agentmd_delete", "--all", "--yes", "--dry-run")
    assert "Dry run" in output and "discovery_scopes=0" in output
    assert inventory() == before
