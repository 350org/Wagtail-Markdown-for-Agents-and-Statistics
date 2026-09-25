"""Reviewable full documents from the shipped add-on, using only synthetic data.

These pin current package output; they do not record 350.org presentation sign-off.
The ordinary page/lifecycle suites own the wider serving and revocation matrix.
"""

import datetime
from urllib.parse import urlsplit

import pytest
from django.apps import apps
from wagtail.contrib.settings.registry import Registry
from wagtail.images import get_image_model
from wagtail.images.tests.utils import get_test_image_file
from wagtail.models import Collection, Locale, Page, PageViewRestriction, Site
from wtrx.models import ContentPage, IndexPage, IntegrationSettings

from tests.test_golden import assert_matches_golden
from tests.test_indexes import read
from wagtail_markdown_agents.export.indexes import IndexGenerator
from wagtail_markdown_agents.export.writer import FileWriter
from wagtail_markdown_agents.rendering import frontmatter, render_page

pytestmark = pytest.mark.django_db(transaction=True)
NOW = datetime.datetime(2026, 9, 25, 12, tzinfo=datetime.UTC)


def published(parent, slug, **fields):
    for name in ("body", "hero_cta"):
        if name in fields:
            fields[name] = ContentPage._meta.get_field(name).stream_block.to_python(
                [{"type": kind, "value": value} for kind, value in fields[name]]
            )
    page = parent.add_child(instance=ContentPage(slug=slug, **fields))
    page.save_revision().publish()
    return page


def golden(name, page, output):
    # Only the database identity varies with test order. URLs, dates, metadata
    # and all authored text remain part of the reviewed comparison.
    assert_matches_golden(name, output.replace(f"id: {page.pk}\n", "id: <pk>\n"))


@pytest.fixture
def corpus(settings, tmp_path, monkeypatch):
    settings.BASE_DIR = tmp_path
    settings.MEDIA_ROOT = str(tmp_path / "media")
    settings.WAGTAILADMIN_BASE_URL = "https://example.org"
    settings.WAGTAIL_MARKDOWN_AGENTS = {"AUTO_GENERATE": False}
    monkeypatch.setattr(frontmatter.timezone, "now", lambda: NOW)

    def forbidden(*args, **kwargs):
        pytest.fail("The synthetic export must not fetch remote content")

    monkeypatch.setattr("socket.socket.connect", forbidden)
    monkeypatch.setattr("wagtail.embeds.finders.get_finders", forbidden)
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
    home = root.add_child(instance=Page(title="350", slug="golden-home", locale=locale))
    Site.objects.all().delete()
    site = Site.objects.create(hostname="example.org", root_page=home, is_default_site=True)
    IntegrationSettings.objects.create(
        site=site,
        integrations=[("actionkit", {"hostname": "campaigns.example.org", "enabled": True})],
    )
    target = published(
        home, "get-involved", title="Get involved", body=[("text", "<p>Join a local group.</p>")]
    )
    private = published(
        home, "organiser-handbook", title="Organiser handbook", body=[("text", "PRIVATE COPY")]
    )
    PageViewRestriction.objects.create(page=private, restriction_type=PageViewRestriction.LOGIN)
    if Collection.get_first_root_node() is None:
        Collection.add_root(name="Root")
    image = get_image_model().objects.create(title="Rally", file=get_test_image_file())
    page = published(
        home,
        "fossil-free-future",
        title="Fossil Free Future",
        search_description="Why we campaign for a fossil-free future.",
        hero_headline="Keep it in the ground",
        hero_pre_header="Our campaign",
        hero_copy="<p>Join the <b>global</b> movement.</p>",
        hero_image_caption="Photo: campaign volunteers",
        hero_cta=[("button", {"text": "Get involved", "link_page": target.pk})],
        body=[
            (
                "text",
                '<h2>Why now</h2><p>Read the <a href="https://www.ipcc.ch/">IPCC report</a> '
                f'and our <a linktype="page" id="{private.pk}">organiser handbook</a>.</p>',
            ),
            (
                "card_grid",
                {
                    "heading": "Take action",
                    "cards": [
                        {
                            "content": "<h3>Divest</h3><p>Move money out of fossil fuels.</p>",
                            "link_page": target.pk,
                        },
                        {"content": "<h3>Organise</h3><p>Start a local group.</p>"},
                    ],
                },
            ),
            (
                "accordion",
                {
                    "heading": "Our movement",
                    "items": [
                        {
                            "title": "In pictures",
                            "content": [
                                {
                                    "type": "image",
                                    "value": {
                                        "image": image.pk,
                                        "alt_text": "Marchers in Nairobi",
                                        "caption": "Together for a fossil-free future.",
                                    },
                                },
                                {
                                    "type": "video",
                                    "value": {
                                        "embed_url": "https://video.example.org/movement",
                                        "caption": "Watch our story",
                                    },
                                },
                            ],
                        }
                    ],
                },
            ),
            ("quote", {"content": "<p>There is no planet B.</p><p>— Campaigner</p>"}),
            (
                "signup_actionkit",
                {
                    "eyebrow": "Make your voice heard",
                    "content": "<p>Ask leaders to act.</p>",
                    "short_form_id": "fossil-free",
                    "success_message": [{"type": "text", "value": "SUCCESS MUST NOT LEAK"}],
                },
            ),
        ],
    )
    writer = FileWriter()
    writer.generate(target)
    yield writer, site, home, page, target
    Site.clear_site_root_paths_cache()


def test_published_addon_document_golden_survives_newer_draft(corpus, client):
    writer, site, home, page, target = corpus
    output = render_page(page)
    golden("wtrx-content.md", page, output)
    assert output.count("\n# ") == 1
    assert "organiser handbook" in output and "/organiser-handbook/" not in output
    assert "SUCCESS MUST NOT LEAK" not in output

    page.hero_headline = "DRAFT HEADLINE"
    page.body = [("text", "<p>DRAFT BODY</p>")]
    draft = page.save_revision()
    assert render_page(draft.as_object()) == output
    record = writer.generate(page)
    assert read(writer, record.logical_path) == output
    for url in ("/fossil-free-future/?output_format=md", "/markdown/fossil-free-future.md"):
        response = client.get(url, HTTP_HOST=site.hostname)
        try:
            assert response.status_code == 200
            assert b"".join(response.streaming_content).decode() == output
        finally:
            response.close()

    # Follow the actual emitted target link; generic tests cover relocated paths.
    from markdown_it import MarkdownIt

    urls = [
        token.attrGet("href")
        for block in MarkdownIt().parse(output.split("---\n", 2)[2])
        for token in block.children or []
        if token.type == "link_open"
    ]
    target_url = next(url for url in urls if "/get-involved" in url)
    response = client.get(urlsplit(target_url).path, HTTP_HOST=site.hostname)
    try:
        assert response.status_code == 200
        assert b"Join a local group." in b"".join(response.streaming_content)
    finally:
        response.close()
    draft.publish()
    changed = render_page(page)
    assert "# DRAFT HEADLINE" in changed and "DRAFT BODY" in changed
    assert "## Our movement" not in changed


@pytest.mark.parametrize("variant", ["hidden", "empty"])
def test_optional_hero_document_goldens(corpus, variant):
    writer, site, home, page, target = corpus
    if variant == "hidden":
        page.hide_hero = True
    else:
        page.hero_headline = page.hero_pre_header = page.hero_copy = page.hero_image_caption = ""
        page.hero_cta = [("button", {"text": "An unlinked call to action"})]
    page.save_revision().publish()
    output = render_page(page)
    golden("wtrx-content-no-hero.md", page, output)
    assert "# Fossil Free Future\n" in output and "# Keep it in the ground" not in output
    assert "Our campaign" not in output and "An unlinked call to action" not in output


def test_addon_index_golden_has_one_generated_listing(corpus):
    writer, site, home, page, target = corpus
    index = home.add_child(
        instance=IndexPage(
            title="Campaigns",
            slug="campaigns",
            hero_headline="Act together",
            hero_copy="<p>Our hero copy.</p>",
            intro="<p>Our introduction.</p>",
            body=[("text", "<p>Our authored body.</p>")],
        )
    )
    index.save_revision().publish()
    child = published(
        index,
        "local-action",
        title="Local action",
        search_description="Organise in your community.",
        body=[("text", "<p>Join us.</p>")],
    )
    writer.generate(child)
    IndexGenerator(writer).generate(site.pk)
    output = read(writer, "example.org/campaigns/index.md")
    golden("wtrx-index.md", index, output)
    assert output.count("## Pages (1)") == 1
    assert output.count("[Local action]") == 1
    IndexGenerator(writer).generate(site.pk)
    assert read(writer, "example.org/campaigns/index.md") == output
