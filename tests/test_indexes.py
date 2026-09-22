"""Root/directory navigation, publication ownership and batch finalisation (#20)."""

import datetime

import pytest
from sandbox.testapp.models import ArticlePage, ContentPage
from sandbox.testapp.page_markdown import render_hero
from wagtail import hooks
from wagtail.models import Locale, Page, PageViewRestriction, Site

from tests.test_golden import assert_matches_golden
from tests.test_page_rendering import split_document
from wagtail_markdown_agents import OKF_VERSION
from wagtail_markdown_agents.export.indexes import INDEX_CONTENT_HOOK, IndexBatch, IndexGenerator
from wagtail_markdown_agents.export.policy import ExportPolicy
from wagtail_markdown_agents.export.state import StaleBuild
from wagtail_markdown_agents.export.writer import FileWriter, StorageContractError
from wagtail_markdown_agents.models import ExportArtifact, PageAgentSettings
from wagtail_markdown_agents.rendering import frontmatter

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(params=["remote", "filesystem"])
def setup(request, settings, tmp_path):
    settings.ROOT_URLCONF = "sandbox.urls"
    settings.ALLOWED_HOSTS = ["example.org"]
    settings.BASE_DIR = tmp_path
    settings.STORAGES = {
        **settings.STORAGES,
        "exports": {"BACKEND": "tests.storage_backend.RemoteStorage"},
    }
    settings.WAGTAIL_MARKDOWN_AGENTS = {"STORAGE": "exports"} if request.param == "remote" else {}
    locale, _ = Locale.objects.get_or_create(language_code="en")
    root = Page.get_first_root_node() or Page.add_root(title="Root", slug="root", locale=locale)
    home = root.add_child(
        instance=ArticlePage(
            title="Home", slug="index-home", body=[("paragraph", "<p>Home body.</p>")]
        )
    )
    Site.objects.all().delete()
    site = Site.objects.create(hostname="example.org", root_page=home, is_default_site=True)
    home.save_revision().publish()
    yield FileWriter(), site, home
    Site.clear_site_root_paths_cache()


def article(parent, slug, title=None, **kwargs):
    page = parent.add_child(
        instance=ArticlePage(
            title=title or slug.title(),
            slug=slug,
            body=[("paragraph", f"<p>{slug} body.</p>")],
            **kwargs,
        )
    )
    page.save_revision().publish()
    return page


def read(writer, path="example.org/index.md"):
    with writer.open(path) as stream:
        return stream.read().decode()


def test_indexes_preserve_parent_and_use_current_public_urls(setup, client):
    writer, site, home = setup
    parent = article(home, "blog", search_description="Campaign news")
    child = article(parent, "story", title="A story", search_description="Read more.")
    writer.generate(child)
    IndexGenerator(writer).generate(site.pk)
    data, root = split_document(read(writer))
    assert data["okf_version"] == OKF_VERSION
    assert "Home body." in root
    assert "[Blog](http://example.org/markdown/blog/index.md) - Campaign news" in root
    assert "A story" not in root  # The parent index represents this subtree.
    path = "example.org/blog/index.md"
    data, body = split_document(read(writer, path))
    assert data["id"] == parent.pk
    assert "blog body." in body
    assert body.count("## Pages (1)") == 1
    assert "[A story](http://example.org/markdown/blog/story.md) - Read more." in body
    IndexGenerator(writer).generate(site.pk)
    assert split_document(read(writer, path))[1] == body
    response = client.get("/markdown/blog/index.md", HTTP_HOST="example.org")
    assert response.status_code == 200
    assert "blog body." in b"".join(response.streaming_content).decode()


def test_empty_corpus_has_generic_root_when_home_is_not_exportable(setup):
    writer, site, home = setup
    PageAgentSettings.objects.create(page=home, excluded=True)
    IndexGenerator(writer).generate(site.pk)
    data, body = split_document(read(writer))
    assert data["okf_version"] == OKF_VERSION
    assert data["count"] == 0
    assert "No exported pages are available." in body
    assert "Home" not in body and "Home body" not in body
    assert ExportArtifact.objects.get(logical_path="example.org/index.md").page_id is None


def test_only_readable_eligible_published_targets_are_listed(setup):
    writer, site, home = setup
    good = article(home, "good", search_description="Published description")
    private = article(home, "private", search_description="PRIVATE METADATA")
    excluded = article(home, "excluded")
    vetoed = article(home, "vetoed")
    missing = article(home, "missing")
    article(home, "ungenerated")
    for page in [good, private, excluded, vetoed, missing]:
        writer.generate(page)
    private_root = article(home, "private-parent")
    inherited = article(private_root, "inherited")
    writer.generate(inherited)
    PageViewRestriction.objects.create(page=private, restriction_type="login")
    PageViewRestriction.objects.create(page=private_root, restriction_type="login")
    PageAgentSettings.objects.create(page=excluded, excluded=True)
    record = ExportArtifact.objects.get(page_id=missing.pk)
    writer._backend(record.file).delete(record.file.storage_key)
    good.title = "DRAFT TITLE"
    good.search_description = "DRAFT DESCRIPTION"
    good.save_revision()
    with hooks.register_temporarily(
        "markdown_export_eligible", lambda page, site: page.pk != vetoed.pk
    ):
        IndexGenerator(writer).generate(site.pk)
        _, body = split_document(read(writer))
    assert "[Good]" in body and "Published description" in body
    for text in [
        "Private",
        "PRIVATE",
        "Excluded",
        "Vetoed",
        "Missing",
        "Ungenerated",
        "Inherited",
        "DRAFT",
    ]:
        assert text not in body


def test_relocated_files_get_directory_indexes_and_real_urls(setup):
    writer, site, home = setup
    child = article(home, "story")

    def relocate(path, page, site):
        return "archive/2026/story.md" if page.pk == child.pk else None

    with hooks.register_temporarily("markdown_export_path", relocate):
        writer.generate(child)
        IndexGenerator(writer).generate(site.pk)
        for path in ["index.md", "archive/index.md", "archive/2026/index.md"]:
            assert "[Story](http://example.org/markdown/archive/2026/story.md)" in read(
                writer, f"example.org/{path}"
            )
        PageAgentSettings.objects.create(page=child, excluded=True)
        assert not writer.exists("example.org/archive/index.md")
        IndexGenerator(writer).generate(site.pk)
        assert not ExportArtifact.objects.filter(
            logical_path__startswith="example.org/archive/"
        ).exists()


def test_index_hook_changes_navigation_only_and_can_suppress_it(setup):
    writer, site, home = setup
    child = article(home, "child")
    writer.generate(child)
    calls = []

    def custom(content, path, context):
        calls.append(path)
        assert context["site"].pk == site.pk
        assert context["page"].pk == home.pk
        assert context["count"] == 1
        assert context["entries"][0].page_id == child.pk
        assert "Home body" not in content
        return "## Custom navigation"

    with hooks.register_temporarily(INDEX_CONTENT_HOOK, custom):
        IndexGenerator(writer).generate(site.pk)
        assert "Home body.\n\n## Custom navigation" in read(writer)
    assert calls == ["index.md"]
    with hooks.register_temporarily(INDEX_CONTENT_HOOK, lambda *args: ""):
        IndexGenerator(writer).generate(site.pk)
        assert "Home body." in read(writer)
        assert "## Pages" not in read(writer)


def test_bad_hook_keeps_previous_complete_index(setup):
    writer, site, home = setup
    IndexGenerator(writer).generate(site.pk)
    old = read(writer)
    with (
        hooks.register_temporarily(INDEX_CONTENT_HOOK, lambda *args: {}),
        pytest.raises(TypeError, match=INDEX_CONTENT_HOOK),
    ):
        IndexGenerator(writer).generate(site.pk)
    assert read(writer) == old


def test_revocation_during_index_render_rejects_obsolete_metadata(setup):
    writer, site, home = setup
    child = article(home, "secret")
    writer.generate(child)
    IndexGenerator(writer).generate(site.pk)

    def revoke(content, path, context):
        PageViewRestriction.objects.create(page=child, restriction_type="login")
        return content

    with hooks.register_temporarily(INDEX_CONTENT_HOOK, revoke), pytest.raises(StaleBuild):
        IndexGenerator(writer).generate(site.pk)
    assert not writer.exists("example.org/index.md")


def test_batch_coalesces_sites_and_repairs_leaf_index_transitions(setup, monkeypatch):
    writer, site, home = setup
    parent = article(home, "parent")
    writer.generate(parent)
    child = article(parent, "child")
    calls = []
    original = IndexGenerator.generate

    def generate(self, site_id, **kwargs):
        calls.append(site_id)
        return original(self, site_id, **kwargs)

    monkeypatch.setattr(IndexGenerator, "generate", generate)
    with IndexBatch(writer) as batch:
        batch.generate(child)
        batch.mark_dirty(site.pk)
        batch.mark_dirty(site.pk)
        assert not writer.exists("example.org/parent.md")
    assert calls == [site.pk]
    assert "[Child]" in read(writer, "example.org/parent/index.md")
    with IndexBatch(writer) as batch:
        child.unpublish()
        batch.delete_page(child.pk, site_id=site.pk)
        assert not writer.exists("example.org/parent/index.md")
    assert calls == [site.pk, site.pk]
    assert "parent body." in read(writer, "example.org/parent.md")
    assert not ExportArtifact.objects.filter(logical_path="example.org/parent/index.md").exists()
    assert "[Parent](http://example.org/markdown/parent.md)" in read(writer)


def test_failed_batch_does_not_finalise_or_undo_revocation(setup):
    writer, site, home = setup
    child = article(home, "child")
    writer.generate(child)
    IndexGenerator(writer).generate(site.pk)
    with pytest.raises(RuntimeError, match="failed"), IndexBatch(writer) as batch:
        PageAgentSettings.objects.create(page=child, excluded=True)
        batch.delete_page(child.pk, site_id=site.pk)
        raise RuntimeError("failed")
    assert not writer.exists("example.org/index.md")


def test_page_can_take_over_standalone_root_without_losing_body(setup):
    writer, site, home = setup
    excluded = PageAgentSettings.objects.create(page=home, excluded=True)
    IndexGenerator(writer).generate(site.pk)
    excluded.delete()
    IndexGenerator(writer).generate(site.pk)
    assert "Home body." in read(writer)
    assert ExportArtifact.objects.get(logical_path="example.org/index.md").page_id == home.pk


def test_page_index_takes_over_current_standalone_index(setup):
    writer, site, home = setup
    writer.update_aggregate(site.pk, "example.org/index.md", lambda _: "Navigation only")
    IndexGenerator(writer).generate(site.pk)
    assert "Home body." in read(writer)


def test_reserved_names_and_identity_suffix_collisions(setup):
    writer, site, home = setup
    reserved = article(home, "index")
    escaped = article(home, "index_")
    suffixed = article(home, f"index_{reserved.pk}")
    for page in [reserved, escaped, suffixed]:
        writer.generate(page)
    paths = {ExportPolicy().relative_path(page) for page in [reserved, escaped, suffixed]}
    assert len(paths) == 3
    IndexGenerator(writer).generate(site.pk)
    assert "## Pages (3)" in read(writer)


def test_disabled_site_does_not_generate(setup, settings):
    writer, site, home = setup
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "SITES": []}
    assert IndexGenerator(writer).generate(site.pk) == []
    assert not ExportArtifact.objects.exists()


def test_350_style_index_golden_has_one_complete_listing(setup, settings, monkeypatch):
    writer, site, home = setup
    now = datetime.datetime(2026, 9, 14, 12, tzinfo=datetime.UTC)
    monkeypatch.setattr(frontmatter.timezone, "now", lambda: now)
    parent = home.add_child(
        instance=ContentPage(
            title="Campaigns",
            slug="campaigns",
            hero_headline="Act together",
            hero_copy="<p>Our hero copy.</p>",
            intro="<p>Our introduction.</p>",
            body=[("paragraph", "<p>Our authored body.</p>")],
        )
    )
    parent.save_revision().publish()
    for n in reversed(range(13)):
        writer.generate(article(parent, f"campaign-{n:02}", title=f"Campaign {n:02}"))
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        **settings.WAGTAIL_MARKDOWN_AGENTS,
        "PAGE_FIELDS": {"testapp.ContentPage": ["intro", "body"]},
    }
    # The configuration is part of publication state: publish targets under it.
    for child in parent.get_children():
        writer.generate(child)
    with hooks.register_temporarily("markdown_post_render", render_hero):
        IndexGenerator(writer).generate(site.pk)
        output = read(writer, "example.org/campaigns/index.md")
    assert output.count("## Pages (13)") == 1
    assert output.count("- [Campaign ") == 13
    assert_matches_golden("index.md", output.replace(f"id: {parent.pk}\n", "id: <pk>\n"))


def test_missing_last_object_prunes_empty_synthetic_directories(setup):
    writer, site, home = setup
    PageAgentSettings.objects.create(page=home, excluded=True)
    child = article(home, "child")
    with hooks.register_temporarily("markdown_export_path", lambda *args: "nested/child.md"):
        record = writer.generate(child)
        IndexGenerator(writer).generate(site.pk)
        assert writer.exists("example.org/nested/index.md")
        writer._backend(record.file).delete(record.file.storage_key)
        IndexGenerator(writer).generate(site.pk)
        assert not ExportArtifact.objects.filter(
            logical_path="example.org/nested/index.md"
        ).exists()
        assert "## Pages (0)" in read(writer)


def test_listing_escapes_metadata_and_unbalanced_url_parentheses(setup):
    from markdown_it import MarkdownIt

    writer, site, home = setup
    child = article(
        home,
        "child",
        title="A [title](https://unwanted.org/) <tag>",
        search_description="A <tag>\nNew line",
    )
    with hooks.register_temporarily(
        "markdown_export_path",
        lambda path, page, site: "odd)name.md" if page.pk == child.pk else None,
    ):
        writer.generate(child)
        IndexGenerator(writer).generate(site.pk)
        _, body = split_document(read(writer))
    links = [
        token.attrGet("href")
        for block in MarkdownIt().parse(body)
        for token in block.children or []
        if token.type == "link_open"
    ]
    assert links == ["http://example.org/markdown/odd%29name.md"]
    assert "A &lt;tag&gt; New line" in body


def test_generator_never_overwrites_another_pages_index(setup):
    writer, site, home = setup
    child = article(home, "child")
    with hooks.register_temporarily("markdown_export_path", lambda *args: "index.md"):
        record = writer.generate(child)
        with pytest.raises(StorageContractError, match="owned"):
            IndexGenerator(writer).generate(site.pk)
        assert ExportArtifact.objects.get(pk=record.pk).page_id == child.pk
        assert "child body." in read(writer)


def test_pruning_rejects_inventory_obsoleted_by_another_publication(setup):
    writer, site, home = setup
    token = writer.begin_site(site.pk, "example.org/index.md")
    writer.update_aggregate(site.pk, "example.org/nested/index.md", lambda _: "Complete")
    with pytest.raises(StaleBuild):
        writer.prune_indexes(token, [])
    assert writer.exists("example.org/nested/index.md")


def test_finalise_is_noop_after_success_and_retains_dirty_site_on_error(setup):
    writer, site, home = setup
    batch = IndexBatch(writer)
    batch.mark_dirty(site.pk)
    with (
        hooks.register_temporarily(INDEX_CONTENT_HOOK, lambda *args: False),
        pytest.raises(TypeError),
    ):
        batch.finalise()
    assert site.pk in batch.dirty
    assert batch.finalise()
    assert batch.finalise() == []
