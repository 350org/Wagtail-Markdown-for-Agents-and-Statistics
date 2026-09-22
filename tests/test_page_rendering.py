"""Full-page output, published revisions, field selection and page hooks (#78)."""

import datetime

import pytest
import yaml
from django.core.exceptions import ImproperlyConfigured
from sandbox.testapp.models import ArticlePage, ContentPage, FormPage
from sandbox.testapp.page_markdown import render_hero
from wagtail import hooks
from wagtail.models import Page, Site

from tests.test_golden import assert_matches_golden
from wagtail_markdown_agents.rendering import frontmatter, render_page
from wagtail_markdown_agents.rendering.html import PRE_CONVERT_HOOK
from wagtail_markdown_agents.rendering.page import POST_RENDER_HOOK, PageRenderError

pytestmark = pytest.mark.django_db
NOW = datetime.datetime(2026, 9, 14, 12, tzinfo=datetime.UTC)


@pytest.fixture
def home():
    return Site.objects.get(is_default_site=True).root_page


@pytest.fixture
def page(home, monkeypatch):
    monkeypatch.setattr(frontmatter.timezone, "now", lambda: NOW)
    target = home.add_child(instance=ArticlePage(title="Get involved", slug="get-involved"))
    target.save_revision().publish()
    page = home.add_child(
        instance=ContentPage(
            title="Fossil Free Future",
            slug="fossil-free-future",
            search_description="Why we campaign.",
            hero_headline="Keep it in the ground",
            hero_copy="<p>Join the <b>global</b> movement.</p>",
            hero_link_text="Act now",
            hero_link_page=target,
            intro="<p>An introduction.</p>",
            body=[
                ("paragraph", "<h2>Why now</h2><p>Published body.</p>"),
                ("bullet_points", ["Divest", "Organise"]),
            ],
        )
    )
    page.save_revision().publish()
    return page


def split_document(output):
    _, metadata, body = output.split("---\n", 2)
    return yaml.safe_load(metadata), body.lstrip("\n")


@pytest.fixture
def hero_mapping(settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"PAGE_FIELDS": {"testapp.ContentPage": ["intro", "body"]}}
    with hooks.register_temporarily(POST_RENDER_HOOK, render_hero):
        yield


def test_complete_page_golden(page, hero_mapping):
    output = render_page(page)
    assert_matches_golden("page.md", output.replace(f"id: {page.pk}\n", "id: <pk>\n"))
    metadata, body = split_document(output)
    assert metadata["title"] == "Fossil Free Future"
    assert body.count("# Keep it in the ground") == 1
    assert "# Fossil Free Future" not in body
    assert "None" not in output


def test_auto_detects_fields_in_definition_order(page):
    _, body = split_document(render_page(page))
    assert body == (
        "# Fossil Free Future\n\nJoin the **global** movement.\n\nAn introduction.\n\n"
        "## Why now\n\nPublished body.\n\n- Divest\n- Organise\n"
    )
    assert "Keep it in the ground" not in body  # scalar fields are never auto-extracted
    assert "Act now" not in body


def test_explicit_order_and_omission(page, settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"PAGE_FIELDS": {"testapp.ContentPage": ["body", "intro"]}}
    _, body = split_document(render_page(page))
    assert body.index("Published body") < body.index("An introduction")
    assert "global" not in body


def test_unconfigured_type_still_auto_detects(page, settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"PAGE_FIELDS": {"testapp.ArticlePage": ["body"]}}
    assert "global" in render_page(page)


@pytest.mark.parametrize(
    "config",
    [
        [],
        {"missing.Model": ["body"]},
        {"testapp.ContentPage": "body"},
        {"testapp.ContentPage": ["missing"]},
        {"testapp.ContentPage": ["hero_headline"]},
        {"testapp.ContentPage": ["hero_link_page"]},
        {"testapp.ContentPage": ["hero_link_page.title"]},
        {"testapp.ContentPage": ["body", "body"]},
        {"testapp.ContentPage": [None]},
        {"testapp.ContentPage": ["body"], "testapp.contentpage": ["intro"]},
    ],
)
def test_bad_field_configuration_is_actionable(page, settings, config):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"PAGE_FIELDS": config}
    with pytest.raises(ImproperlyConfigured, match="PAGE_FIELDS"):
        render_page(page)


@pytest.mark.parametrize("source", ["instance", "base", "draft", "database"])
def test_newer_draft_never_leaks_and_publish_updates_output(page, hero_mapping, source):
    page.title = "DRAFT TITLE"
    page.hero_headline = "DRAFT HEADLINE"
    page.hero_copy = "<p>DRAFT COPY</p>"
    page.intro = "<p>DRAFT INTRO</p>"
    page.body = [("paragraph", "<p>DRAFT BODY</p>")]
    draft = page.save_revision()
    supplied = {
        "instance": page,
        "base": Page.objects.get(pk=page.pk),
        "draft": draft.as_object(),
        "database": ContentPage.objects.get(pk=page.pk),
    }[source]
    output = render_page(supplied)
    assert "DRAFT" not in output
    assert "Published body" in output and "Keep it in the ground" in output

    draft.publish()
    output = render_page(supplied)  # even an old caller instance must see the new publication
    for text in ["DRAFT TITLE", "DRAFT HEADLINE", "DRAFT COPY", "DRAFT INTRO", "DRAFT BODY"]:
        assert text in output


def test_live_revision_wins_over_direct_model_edits(page):
    ContentPage.objects.filter(pk=page.pk).update(intro="UNPUBLISHED DATABASE EDIT")
    assert "UNPUBLISHED DATABASE EDIT" not in render_page(page)


def test_tags_are_from_the_published_revision(home):
    article = home.add_child(
        instance=ArticlePage(title="Tags", slug="tags", body=[("paragraph", "<p>Public</p>")])
    )
    article.tags.add("Published tag")
    article.save_revision().publish()
    article.tags.clear()
    article.tags.add("DRAFT TAG")
    draft = article.save_revision()

    metadata, _ = split_document(render_page(draft.as_object()))
    assert metadata["tags"] == ["Published tag"]


def test_publication_dates_are_not_taken_from_older_revision_json(page, monkeypatch):
    page.refresh_from_db()
    later = NOW + datetime.timedelta(days=1)
    monkeypatch.setattr(frontmatter.timezone, "now", lambda: later)
    page.intro = "<p>Updated.</p>"
    page.save_revision().publish()
    metadata, _ = split_document(render_page(page))
    assert metadata["date"] == "2026-09-14T12:00:00Z"
    assert metadata["modified"] == "2026-09-15T12:00:00Z"


def test_empty_optional_fields_do_not_make_a_document(home):
    empty = home.add_child(instance=ContentPage(title="Empty", slug="empty"))
    empty.save_revision().publish()
    with pytest.raises(PageRenderError) as excinfo:
        render_page(empty)
    assert excinfo.value.reason == "empty_body"


def test_missing_optional_hero_fields(page, hero_mapping):
    page.hero_headline = ""
    page.hero_copy = ""
    page.hero_link_page = None
    page.intro = ""
    page.save_revision().publish()
    _, body = split_document(render_page(page))
    assert body.startswith("# Fossil Free Future\n\n## Why now")
    assert "Act now" not in body
    assert "\n\n\n" not in body


def test_hooks_share_published_context_and_chain_before_frontmatter(page):
    events = []
    contexts = []

    def convert(html, block, context):
        events.append("conversion")
        contexts.append(context)
        assert context["page"].hero_headline == "Keep it in the ground"

    def first(markdown, published, context):
        events.append("first")
        contexts.append(context)
        assert published is context["page"]
        context["heading"] = "Public headline"
        return markdown + "\n\nFirst addition."

    def second(markdown, published, context):
        events.append("second")
        assert "First addition." in markdown
        return None

    def metadata(data, published, context):
        events.append("frontmatter")
        contexts.append(context)
        data["headline"] = context["heading"]

    site = page.get_site()
    with (
        hooks.register_temporarily(PRE_CONVERT_HOOK, convert),
        hooks.register_temporarily(POST_RENDER_HOOK, second, order=10),
        hooks.register_temporarily(POST_RENDER_HOOK, first, order=-10),
        hooks.register_temporarily(frontmatter.FRONTMATTER_HOOK, metadata),
    ):
        data, body = split_document(render_page(page, site=site))
    assert events.index("first") < events.index("second") < events.index("frontmatter")
    assert all(context is contexts[0] for context in contexts)
    assert contexts[0]["site"] is site
    assert contexts[0]["locale"] == page.locale
    assert "request" not in contexts[0]
    assert data["headline"] == "Public headline"
    assert body.startswith("# Public headline\n")


def test_hook_may_supply_authored_heading(page):
    def own_heading(markdown, published, context):
        context["heading"] = None
        return "# Authored heading\n\n" + markdown

    with hooks.register_temporarily(POST_RENDER_HOOK, own_heading):
        _, body = split_document(render_page(page))
    assert body.startswith("# Authored heading\n")
    assert "# Fossil Free Future" not in body


def test_navigation_is_appended_once_after_hook(page):
    def authored_listing(markdown, published, context):
        assert "Generated navigation" not in markdown
        return markdown + "\n\nAuthored listing."

    with hooks.register_temporarily(POST_RENDER_HOOK, authored_listing):
        _, body = split_document(render_page(page, navigation="## Generated navigation\n\nLinks."))
    assert body.endswith("Authored listing.\n\n## Generated navigation\n\nLinks.\n")
    assert body.count("## Generated navigation") == 1
    assert "Published body" in body


def test_hook_errors_propagate(page):
    def broken(*args):
        raise RuntimeError("Failed to render a public field")

    with (
        hooks.register_temporarily(POST_RENDER_HOOK, broken),
        pytest.raises(RuntimeError, match="public field"),
    ):
        render_page(page)


def test_invalid_hook_result_is_an_error(page):
    with (
        hooks.register_temporarily(POST_RENDER_HOOK, lambda *args: {"unexpected": "dict"}),
        pytest.raises(TypeError, match="markdown_post_render"),
    ):
        render_page(page)


@pytest.mark.parametrize("model", [Page, FormPage])
def test_unsupported_page_is_not_exported_as_title_or_intro(home, model):
    page = home.add_child(instance=model(title="Unsupported", slug="unsupported"))
    if isinstance(page, FormPage):
        page.intro = "<p>Intro alone is not a form.</p>"
        page.body = [("paragraph", "<p>This still is not the form.</p>")]
    page.save_revision().publish()
    with pytest.raises(PageRenderError) as excinfo:
        render_page(page)
    assert excinfo.value.reason == "unsupported_page"
    assert excinfo.value.page_id == page.pk


def test_empty_page_does_not_succeed_with_only_title(page, settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"PAGE_FIELDS": {"testapp.ContentPage": []}}
    with pytest.raises(PageRenderError) as excinfo:
        render_page(page)
    assert excinfo.value.reason == "empty_body"


@pytest.mark.parametrize("state", ["unsaved", "deleted", "unpublished", "no_revision"])
def test_no_published_content_is_an_explicit_error(home, page, state):
    if state == "unsaved":
        page = ContentPage(title="Unsaved")
    elif state == "deleted":
        ContentPage.objects.get(pk=page.pk).delete()
    elif state == "unpublished":
        ContentPage.objects.get(pk=page.pk).unpublish()
    else:
        page = home.add_child(instance=ContentPage(title="No revision", slug="no-revision"))
    with pytest.raises(PageRenderError) as excinfo:
        render_page(page)
    assert excinfo.value.reason == "unpublished_page"
