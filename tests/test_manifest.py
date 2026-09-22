"""v0.1 manifests describe readable publications, with durable comparisons."""

import hashlib
import json

import pytest
from wagtail import hooks
from wagtail.models import PageViewRestriction

from tests import test_indexes
from tests.test_indexes import article
from tests.test_serving import body
from wagtail_markdown_agents.export.indexes import IndexBatch
from wagtail_markdown_agents.export.manifest import ManifestGenerator
from wagtail_markdown_agents.export.state import StaleBuild
from wagtail_markdown_agents.models import ExportScope

pytestmark = pytest.mark.django_db(transaction=True)
setup = test_indexes.setup


def read(writer):
    return json.loads(test_indexes.read(writer, "example.org/manifest.json"))


def generate(writer, site):
    ManifestGenerator(writer).generate(site.pk)
    return read(writer)


def test_manifest_hashes_actual_output_and_serves_json(setup, client):
    writer, site, home = setup
    child = article(home, "child")
    record = writer.generate(child)
    with writer.open(record.logical_path) as stream:
        exported = stream.read()
    data = generate(writer, site)
    entry = data["documents"][0]
    assert data["schema_version"] == "0.1"
    assert data["hash_version"] == 1
    assert entry["id"] == child.pk
    assert entry["path"] == record.logical_path
    assert entry["storage_key"] == record.file.storage_key
    assert entry["storage_alias"] == record.file.storage_alias
    assert entry["url"] == "http://example.org/markdown/child.md"
    assert entry["title"] == "Child" and entry["type"] == "testapp.ArticlePage"
    assert entry["full_hash"] == hashlib.sha256(exported).hexdigest()
    assert entry["change_status"] == "new"
    assert entry["word_count"] == 3
    response = client.get("/markdown/manifest.json", HTTP_HOST="example.org")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/json; charset=utf-8"
    assert json.loads(body(response)) == data
    head = client.head("/markdown/manifest.json", HTTP_HOST="example.org")
    assert head.status_code == 200 and body(head) == b""


def test_no_change_ignores_generation_timestamp_and_storage_object(setup):
    writer, site, home = setup
    child = article(home, "child")
    for timestamp in ["2026-09-14T12:00:00Z", "2026-09-14T12:01:00Z"]:

        def set_timestamp(data, *args, timestamp=timestamp):
            data["timestamp"] = timestamp

        with hooks.register_temporarily("construct_markdown_frontmatter", set_timestamp):
            writer.generate(child)
        current = generate(writer, site)["documents"][0]
        if timestamp.endswith("12:00:00Z"):
            first = current
        else:
            second = current
    assert first["full_hash"] != second["full_hash"]
    assert first["storage_key"] != second["storage_key"]
    assert second["change_status"] == "unchanged"
    assert first["metadata_hash"] == second["metadata_hash"]
    assert first["content_hash"] == second["content_hash"]


@pytest.mark.parametrize("change", ["body", "metadata", "configuration", "path", "link", "image"])
def test_output_changes_keep_page_identity(setup, change):
    writer, site, home = setup
    child = article(home, "child")
    writer.generate(child)
    first = generate(writer, site)["documents"][0]
    # Hooks model output changes without relying on publication timestamps.
    hook = "markdown_post_render"

    def callback(markdown, *args):
        return markdown + "\nExtra content"

    if change == "metadata":
        hook = "construct_markdown_frontmatter"

        def callback(data, *args):
            return data.update(tags=["new tag"])
    elif change == "configuration":
        hook = "construct_markdown_frontmatter"

        def callback(data, *args):
            return data.update(configured_field="changed")
    elif change == "path":
        hook = "markdown_export_path"

        def callback(*args):
            return "relocated/child.md"
    elif change == "link":

        def callback(markdown, *args):
            return markdown + "\n[Target](https://example.org/new/)"
    elif change == "image":

        def callback(markdown, *args):
            return markdown + "\n![Alt](https://example.org/new.png)"

    with hooks.register_temporarily(hook, callback):
        writer.generate(child)
        second = generate(writer, site)["documents"][0]
        assert second["id"] == first["id"] == child.pk
        assert second["change_status"] == "modified"
        if change in {"metadata", "configuration"}:
            assert second["content_hash"] == first["content_hash"]
            assert second["metadata_hash"] != first["metadata_hash"]
        elif change != "path":
            assert second["content_hash"] != first["content_hash"]
            assert second["metadata_hash"] == first["metadata_hash"]
        else:
            assert second["path"] == "example.org/relocated/child.md"
            assert not writer.exists(first["path"])


def test_scoped_updates_keep_other_documents_and_drafts_out(setup):
    writer, site, home = setup
    first, other = article(home, "first"), article(home, "other")
    writer.generate(first)
    writer.generate(other)
    generate(writer, site)
    other.title = "PRIVATE DRAFT"
    other.save_revision()
    writer.generate(first)
    data = generate(writer, site)
    assert {doc["id"] for doc in data["documents"]} == {first.pk, other.pk}
    assert all(doc["change_status"] == "unchanged" for doc in data["documents"])
    assert "PRIVATE DRAFT" not in json.dumps(data)


def test_missing_file_is_error_then_repaired_without_false_deletion(setup):
    writer, site, home = setup
    child = article(home, "child")
    record = writer.generate(child)
    generate(writer, site)
    writer._backend(record.file).delete(record.file.storage_key)
    data = generate(writer, site)
    assert data["documents"] == []
    assert data["errors"] == [{"id": child.pk, "reason": "unavailable_export"}]
    assert data["summary"]["removed"] == 0
    writer.generate(child)
    assert generate(writer, site)["documents"][0]["change_status"] == "unchanged"


def test_failed_batch_keeps_baseline_and_retry_reports_successes(setup, monkeypatch):
    writer, site, home = setup
    first, other = article(home, "first"), article(home, "other")
    writer.generate(first)
    writer.generate(other)
    generate(writer, site)
    baseline = ExportScope.objects.get(site_id=site.pk).manifest_state
    original = writer._upload

    def fail(file, text):
        if file.page_id == other.pk:
            raise OSError("Upload failed")
        original(file, text)

    monkeypatch.setattr(writer, "_upload", fail)
    with pytest.raises(OSError, match="Upload failed"), IndexBatch(writer) as batch:
        batch.generate(first)
        batch.generate(other)
    assert ExportScope.objects.get(site_id=site.pk).manifest_state == baseline
    assert not writer.exists("example.org/manifest.json")
    monkeypatch.setattr(writer, "_upload", original)
    batch.generate(other)
    batch.finalise()
    assert {doc["id"] for doc in read(writer)["documents"]} >= {first.pk, other.pk}


def test_revocation_removes_private_metadata_without_tombstones(setup, client):
    writer, site, home = setup
    child = article(home, "secret")
    writer.generate(child)
    generate(writer, site)
    PageViewRestriction.objects.create(page=child, restriction_type="login")
    assert client.get("/markdown/manifest.json", HTTP_HOST="example.org").status_code == 404
    data = generate(writer, site)
    assert data["documents"] == [] and data["errors"] == []
    assert data["summary"]["removed"] == 1
    assert "secret" not in json.dumps(data).lower()
    assert str(child.pk) not in ExportScope.objects.get(site_id=site.pk).manifest_state["documents"]


@pytest.mark.parametrize("change", ["restrict", "publish", "delete"])
def test_overlapping_publication_cannot_restore_stale_manifest(setup, monkeypatch, change):
    writer, site, home = setup
    child = article(home, "child")
    writer.generate(child)
    generate(writer, site)
    baseline = ExportScope.objects.get(site_id=site.pk).manifest_state
    original = writer._upload

    def upload(file, text):
        original(file, text)
        if change == "restrict":
            PageViewRestriction.objects.create(page=child, restriction_type="login")
        elif change == "publish":
            child.save_revision().publish()
        else:
            writer.delete_page(child.pk, site_id=site.pk)

    monkeypatch.setattr(writer, "_upload", upload)
    with pytest.raises(StaleBuild):
        ManifestGenerator(writer).generate(site.pk)
    assert ExportScope.objects.get(site_id=site.pk).manifest_state == baseline
    assert not writer.exists("example.org/manifest.json")


def test_manifest_upload_failure_preserves_pointer_and_baseline(setup, monkeypatch):
    writer, site, home = setup
    writer.generate(article(home, "child"))
    previous = generate(writer, site)
    baseline = ExportScope.objects.get(site_id=site.pk).manifest_state

    def fail(*args):
        raise OSError("Upload failed")

    monkeypatch.setattr(writer, "_upload", fail)
    with pytest.raises(OSError, match="Upload failed"):
        ManifestGenerator(writer).generate(site.pk)
    assert read(writer) == previous
    assert ExportScope.objects.get(site_id=site.pk).manifest_state == baseline


def test_corrupt_baseline_is_an_error(setup):
    writer, site, home = setup
    generate(writer, site)
    ExportScope.objects.filter(site_id=site.pk).update(manifest_state={"broken": True})
    with pytest.raises(ValueError, match="manifest comparison state"):
        ManifestGenerator(writer).generate(site.pk)


def test_configuration_only_change_is_hashed_from_rebuilt_output(setup, settings):
    writer, site, home = setup
    child = article(home, "child")
    writer.generate(child)
    first = generate(writer, site)["documents"][0]
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        **settings.WAGTAIL_MARKDOWN_AGENTS,
        "INCLUDE_HIERARCHY": True,
    }
    data = generate(writer, site)
    assert data["errors"] and data["summary"]["removed"] == 0
    writer.generate(child)
    second = generate(writer, site)["documents"][0]
    assert second["change_status"] == "modified"
    assert second["content_hash"] == first["content_hash"]
    assert second["metadata_hash"] != first["metadata_hash"]


def test_deleted_page_and_empty_corpus(setup):
    writer, site, home = setup
    assert generate(writer, site)["documents"] == []
    child = article(home, "child")
    writer.generate(child)
    generate(writer, site)
    child.delete()
    data = generate(writer, site)
    assert data["documents"] == [] and data["errors"] == []
    assert data["summary"]["removed"] == 1


def test_missing_public_manifest_preserves_private_comparison(setup):
    writer, site, home = setup
    writer.generate(article(home, "child"))
    record = ManifestGenerator(writer).generate(site.pk)
    writer._backend(record.file).delete(record.file.storage_key)
    assert generate(writer, site)["documents"][0]["change_status"] == "unchanged"


def test_competing_aggregate_update_retries_with_atomic_baseline(setup, monkeypatch):
    writer, site, home = setup
    writer.generate(article(home, "child"))
    original = writer._upload
    calls = []

    def upload(file, text):
        original(file, text)
        if file.logical_path.endswith("manifest.json"):
            calls.append(file.pk)
            if len(calls) == 1:
                writer.update_aggregate(site.pk, "example.org/llms.txt", lambda old: "# Site\n")

    monkeypatch.setattr(writer, "_upload", upload)
    data = generate(writer, site)
    assert len(calls) == 2
    assert data["documents"][0]["change_status"] == "new"
    assert generate(writer, site)["documents"][0]["change_status"] == "unchanged"


def test_commit_failure_rolls_back_pointer_and_private_state(setup):
    writer, site, home = setup
    previous = generate(writer, site)
    state = ExportScope.objects.get(site_id=site.pk).manifest_state

    def fail(scope, record):
        ExportScope.objects.filter(pk=scope.pk).update(manifest_state={"broken": True})
        raise RuntimeError("Commit failed")

    with pytest.raises(RuntimeError, match="Commit failed"):
        writer.update_aggregate(site.pk, "example.org/manifest.json", lambda old: "{}", commit=fail)
    assert read(writer) == previous
    assert ExportScope.objects.get(site_id=site.pk).manifest_state == state


def test_batch_publishes_manifest_last_and_retries_failure(setup, monkeypatch):
    writer, site, home = setup
    batch = IndexBatch(writer)
    batch.generate(article(home, "child"))
    original = writer._upload

    def upload(file, text):
        if file.logical_path.endswith("manifest.json"):
            assert writer.exists("example.org/index.md")
            assert writer.exists("example.org/llms.txt")
            raise OSError("Manifest failed")
        original(file, text)

    monkeypatch.setattr(writer, "_upload", upload)
    with pytest.raises(OSError, match="Manifest failed"):
        batch.finalise()
    assert site.pk in batch.dirty
    monkeypatch.setattr(writer, "_upload", original)
    batch.finalise()
    assert batch.dirty == {} and read(writer)["documents"]


def test_disabled_site_is_not_published(setup, settings):
    writer, site, home = setup
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "SITES": []}
    assert ManifestGenerator(writer).generate(site.pk) is None


def test_competing_manifest_reloads_the_committed_comparison(setup, monkeypatch):
    writer, site, home = setup
    writer.generate(article(home, "child"))
    original = writer._upload
    competing = False

    def upload(file, text):
        nonlocal competing
        original(file, text)
        if not competing:
            competing = True
            assert generate(writer, site)["documents"][0]["change_status"] == "new"

    monkeypatch.setattr(writer, "_upload", upload)
    assert generate(writer, site)["documents"][0]["change_status"] == "unchanged"


def test_custom_public_url_and_owned_identity_override_frontmatter(setup):
    writer, site, home = setup
    child = article(home, "child")

    def metadata(data, *args):
        data.update(id=99999, title="Exported title", type="Custom type")

    with (
        hooks.register_temporarily("markdown_export_path", lambda *args: "custom/child.md"),
        hooks.register_temporarily("construct_markdown_frontmatter", metadata),
    ):
        writer.generate(child)
        ManifestGenerator(writer, urlconf="tests.serving_urls").generate(site.pk)
        entry = read(writer)["documents"][0]
    assert entry["id"] == child.pk
    assert entry["title"] == "Exported title" and entry["type"] == "Custom type"
    assert entry["url"] == "http://example.org/exports/v1/custom/child.md"


def test_other_site_inventory_and_baseline_are_preserved(setup, settings):
    from wagtail.models import Page, Site

    writer, site, home = setup
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "SITES": "all"}
    child = article(home, "child")
    writer.generate(child)
    other_home = Page.get_first_root_node().add_child(instance=Page(title="Other", slug="other"))
    other_site = Site.objects.create(hostname="other.org", root_page=other_home)
    other = article(other_home, "other-child")
    writer.generate(other)
    ManifestGenerator(writer).generate(other_site.pk)
    baseline = ExportScope.objects.get(site_id=other_site.pk).manifest_state
    first = generate(writer, site)
    assert [entry["id"] for entry in first["documents"]] == [child.pk]
    writer.generate(child)
    generate(writer, site)
    assert ExportScope.objects.get(site_id=other_site.pk).manifest_state == baseline
    assert writer.exists("other.org/manifest.json")


def test_site_change_before_update_cannot_publish_from_old_snapshot(setup, monkeypatch):
    writer, site, home = setup
    writer.generate(article(home, "child"))
    original = writer.update_aggregate

    def update(*args, **kwargs):
        site.site_name = "Changed before token capture"
        site.save()
        return original(*args, **kwargs)

    monkeypatch.setattr(writer, "update_aggregate", update)
    with pytest.raises(StaleBuild):
        ManifestGenerator(writer).generate(site.pk)
    assert not writer.exists("example.org/manifest.json")
