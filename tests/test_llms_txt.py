"""A small managed discovery file, based only on current published exports (#21)."""

from urllib.parse import urlsplit

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from markdown_it import MarkdownIt
from wagtail import hooks
from wagtail.models import Page, PageViewRestriction, Site

from tests import test_indexes
from tests.test_golden import assert_matches_golden
from tests.test_indexes import article
from tests.test_serving import body
from wagtail_markdown_agents.export.indexes import IndexBatch, IndexGenerator
from wagtail_markdown_agents.export.llms_txt import LlmsTxtGenerator
from wagtail_markdown_agents.export.state import StaleBuild
from wagtail_markdown_agents.models import ExportArtifact, PageAgentSettings
from wagtail_markdown_agents.public_urls import export_url

pytestmark = pytest.mark.django_db(transaction=True)
setup = test_indexes.setup


def read(writer):
    return test_indexes.read(writer, "example.org/llms.txt")


def links(markdown):
    return [
        token.attrGet("href")
        for block in MarkdownIt().parse(markdown)
        for token in block.children or []
        if token.type == "link_open"
    ]


def test_llms_golden_and_http_traversal(setup, settings, client):
    writer, site, home = setup
    site.site_name = "Example Climate"
    site.save()
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        **settings.WAGTAIL_MARKDOWN_AGENTS,
        "LLMS_TXT_DESCRIPTION": "Campaigns and resources for a fossil-free future.",
    }
    campaigns = article(home, "campaigns", search_description="Explore our campaigns.")
    child = article(campaigns, "clean-energy", search_description="A local campaign.")
    about = article(home, "about", title="About us", search_description="Our purpose and approach.")
    for page in [child, about]:
        writer.generate(page)
    IndexGenerator(writer).generate(site.pk)
    record = LlmsTxtGenerator(writer).generate(site.pk)
    output = read(writer)
    assert_matches_golden("llms.txt", output)
    assert "Clean Energy" not in output
    assert record.page_id is None
    assert export_url(record) == "http://example.org/markdown/llms.txt"
    response = client.get("/markdown/llms.txt", HTTP_HOST="example.org")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/plain; charset=utf-8"
    assert "X-Markdown-Source" not in response
    assert body(response).decode() == output
    head = client.head("/markdown/llms.txt", HTTP_HOST="example.org")
    assert head.status_code == 200 and body(head) == b""
    for url in links(output):
        target = client.get(urlsplit(url).path, HTTP_HOST="example.org")
        assert target.status_code == 200
        assert body(target)
    LlmsTxtGenerator(writer).generate(site.pk)
    assert read(writer) == output


def test_empty_corpus_uses_hostname_and_no_private_root_metadata(setup):
    writer, site, home = setup
    PageAgentSettings.objects.create(page=home, excluded=True)
    LlmsTxtGenerator(writer).generate(site.pk)
    assert read(writer) == "# example.org\n\nNo exported pages are available.\n"
    IndexGenerator(writer).generate(site.pk)
    LlmsTxtGenerator(writer).generate(site.pk)
    output = read(writer)
    assert "[Site index](http://example.org/markdown/index.md)" in output
    assert "Home" not in output


def test_only_current_published_eligible_targets_are_listed(setup):
    writer, site, home = setup
    good = article(home, "good", search_description="Public summary")
    good_record = writer.generate(good)
    targets = {
        name: article(home, name)
        for name in ["restricted", "excluded", "vetoed", "missing", "stale"]
    }
    for page in targets.values():
        writer.generate(page)
    article(home, "ungenerated")
    private_parent = article(home, "private-parent")
    inherited = article(private_parent, "inherited")
    writer.generate(inherited)
    PageViewRestriction.objects.create(page=private_parent, restriction_type="login")
    PageViewRestriction.objects.create(page=targets["restricted"], restriction_type="login")
    PageAgentSettings.objects.create(page=targets["excluded"], excluded=True)
    missing = ExportArtifact.objects.get(page_id=targets["missing"].pk)
    writer._backend(missing.file).delete(missing.file.storage_key)
    targets["stale"].body = [("paragraph", "<p>New public version</p>")]
    targets["stale"].save_revision().publish()
    good.title = "DRAFT TITLE"
    good.search_description = "DRAFT DESCRIPTION"
    good.save_revision()
    with hooks.register_temporarily(
        "markdown_export_eligible", lambda page, site: page.pk != targets["vetoed"].pk
    ):
        LlmsTxtGenerator(writer).generate(site.pk)
        output = read(writer)
    assert links(output) == [export_url(good_record)]
    assert "[Good]" in output and ": Public summary" in output
    for text in [
        "DRAFT",
        "Restricted",
        "Excluded",
        "Vetoed",
        "Missing",
        "Stale",
        "Ungenerated",
        "Inherited",
    ]:
        assert text not in output


def test_relocated_targets_and_custom_route_prefix(setup):
    writer, site, home = setup
    child = article(home, "child")
    with hooks.register_temporarily("markdown_export_path", lambda *args: "custom/odd)name.md"):
        writer.generate(child)
        LlmsTxtGenerator(writer, urlconf="tests.serving_urls").generate(site.pk)
        output = read(writer)
    assert links(output) == ["http://example.org/exports/v1/custom/odd%29name.md"]


def test_escapes_configured_and_published_text(setup, settings):
    writer, site, home = setup
    site.site_name = "A [site](https://unwanted.org) <tag>\nSecond line"
    site.save()
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        **settings.WAGTAIL_MARKDOWN_AGENTS,
        "LLMS_TXT_DESCRIPTION": "Intro\n## Heading [link](https://unwanted.org) <script>",
    }
    child = article(
        home,
        "child",
        title="A [title](https://unwanted.org)",
        search_description="A <tag>\nDescription",
    )
    record = writer.generate(child)
    LlmsTxtGenerator(writer).generate(site.pk)
    output = read(writer)
    assert links(output) == [export_url(record)]
    assert output.count("\n## ") == 1
    assert "&lt;script&gt;" in output and "&lt;tag&gt; Description" in output


@pytest.mark.parametrize("value", [None, False, 42, {}, []])
def test_invalid_introduction_fails_before_publication(setup, settings, value):
    writer, site, home = setup
    original = LlmsTxtGenerator(writer).generate(site.pk)
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        **settings.WAGTAIL_MARKDOWN_AGENTS,
        "LLMS_TXT_DESCRIPTION": value,
    }
    with pytest.raises(ImproperlyConfigured, match="LLMS_TXT_DESCRIPTION"):
        LlmsTxtGenerator(writer).generate(site.pk)
    assert ExportArtifact.objects.get(pk=original.pk).file_id == original.file_id


@pytest.mark.parametrize("change", ["site_name", "description"])
def test_discovery_metadata_changes_invalidate_empty_corpus(setup, settings, change):
    writer, site, home = setup
    PageAgentSettings.objects.create(page=home, excluded=True)
    LlmsTxtGenerator(writer).generate(site.pk)
    if change == "site_name":
        site.site_name = "New name"
        site.save()
    else:
        settings.WAGTAIL_MARKDOWN_AGENTS = {
            **settings.WAGTAIL_MARKDOWN_AGENTS,
            "LLMS_TXT_DESCRIPTION": "New introduction",
        }
    assert not writer.exists("example.org/llms.txt")
    LlmsTxtGenerator(writer).generate(site.pk)
    assert ("New name" if change == "site_name" else "New introduction") in read(writer)


def test_description_change_keeps_leaf_exports_available(setup, settings):
    writer, site, home = setup
    child = article(home, "child")
    record = writer.generate(child)
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        **settings.WAGTAIL_MARKDOWN_AGENTS,
        "LLMS_TXT_DESCRIPTION": "New introduction",
    }
    assert writer.exists(record.logical_path)
    LlmsTxtGenerator(writer).generate(site.pk)
    assert links(read(writer)) == [export_url(record)]


def test_newly_private_metadata_is_hidden_then_removed_on_rebuild(setup, client):
    writer, site, home = setup
    child = article(home, "secret", search_description="Previously public metadata")
    writer.generate(child)
    LlmsTxtGenerator(writer).generate(site.pk)
    PageViewRestriction.objects.create(page=child, restriction_type="login")
    assert client.get("/markdown/llms.txt", HTTP_HOST="example.org").status_code == 404
    LlmsTxtGenerator(writer).generate(site.pk)
    assert "Secret" not in read(writer) and "Previously public" not in read(writer)


def test_batch_finalises_discovery_once_after_indexes(setup, monkeypatch):
    writer, site, home = setup
    child = article(home, "child")
    calls = []
    original = LlmsTxtGenerator.generate

    def generate(self, site_id):
        assert writer.exists("example.org/index.md")
        calls.append(site_id)
        return original(self, site_id)

    monkeypatch.setattr(LlmsTxtGenerator, "generate", generate)
    with IndexBatch(writer) as batch:
        batch.generate(child)
        batch.mark_dirty(site.pk)
    assert calls == [site.pk]
    assert "[Child]" in read(writer)
    assert batch.finalise() == []
    assert calls == [site.pk]


def test_failed_discovery_keeps_batch_dirty_for_retry(setup, monkeypatch):
    writer, site, home = setup
    batch = IndexBatch(writer)
    batch.mark_dirty(site.pk)
    original = LlmsTxtGenerator.generate

    def fail(*args):
        raise OSError("Discovery failed")

    monkeypatch.setattr(LlmsTxtGenerator, "generate", fail)
    with pytest.raises(OSError, match="Discovery failed"):
        batch.finalise()
    assert site.pk in batch.dirty
    monkeypatch.setattr(LlmsTxtGenerator, "generate", original)
    batch.finalise()
    assert writer.exists("example.org/llms.txt")
    assert batch.dirty == {}


def test_disabled_sites_do_not_publish(setup, settings):
    writer, site, home = setup
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "SITES": []}
    assert LlmsTxtGenerator(writer).generate(site.pk) is None
    assert not ExportArtifact.objects.exists()


def test_other_sites_are_not_listed(setup, settings):
    writer, site, home = setup
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "SITES": "all"}
    own = article(home, "own")
    record = writer.generate(own)
    other_home = Page.get_first_root_node().add_child(instance=Page(title="Other", slug="other"))
    other_site = Site.objects.create(hostname="other.org", root_page=other_home)
    other = article(other_home, "other-content")
    other_record = writer.generate(other)
    LlmsTxtGenerator(writer).generate(other_site.pk)
    LlmsTxtGenerator(writer).generate(site.pk)
    assert links(read(writer)) == [export_url(record)]
    assert writer.exists(other_record.logical_path)
    assert writer.exists("other.org/llms.txt")


def test_generation_requires_after_commit(setup):
    writer, site, home = setup
    with transaction.atomic(), pytest.raises(RuntimeError, match="after commit"):
        LlmsTxtGenerator(writer).generate(site.pk)
    assert not ExportArtifact.objects.exists()


@pytest.mark.parametrize("change", ["restrict", "delete", "publish"])
def test_upload_superseded_by_revocation_or_publication_cannot_restore_discovery(
    setup, monkeypatch, change
):
    writer, site, home = setup
    child = article(home, "child", search_description="Old metadata")
    writer.generate(child)
    LlmsTxtGenerator(writer).generate(site.pk)
    original = writer._upload

    def upload(file, text):
        original(file, text)
        if change == "restrict":
            PageViewRestriction.objects.create(page=child, restriction_type="login")
        elif change == "delete":
            writer.delete_page(child.pk, site_id=site.pk)
        else:
            child.search_description = "New metadata"
            child.save_revision().publish()

    monkeypatch.setattr(writer, "_upload", upload)
    with pytest.raises(StaleBuild):
        LlmsTxtGenerator(writer).generate(site.pk)
    assert not writer.exists("example.org/llms.txt")


def test_failed_upload_preserves_previous_complete_file(setup, monkeypatch):
    writer, site, home = setup
    LlmsTxtGenerator(writer).generate(site.pk)
    previous = read(writer)

    def fail(*args):
        raise OSError("Upload failed")

    monkeypatch.setattr(writer, "_upload", fail)
    with pytest.raises(OSError, match="Upload failed"):
        LlmsTxtGenerator(writer).generate(site.pk)
    assert read(writer) == previous


def test_stale_root_index_is_omitted_and_available_descendants_are_promoted(setup):
    writer, site, home = setup
    parent = article(home, "parent")
    child = article(parent, "child")
    writer.generate(child)
    IndexGenerator(writer).generate(site.pk)
    # This changes site dependencies, leaving the child's leaf export current.
    PageAgentSettings.objects.create(page=parent, excluded=True)
    LlmsTxtGenerator(writer).generate(site.pk)
    output = read(writer)
    assert "Site index" not in output and "[Parent]" not in output
    assert "[Child](http://example.org/markdown/parent/child.md)" in output
