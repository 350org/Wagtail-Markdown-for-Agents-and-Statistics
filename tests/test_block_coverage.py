"""Block coverage report (#18): which path each block definition takes to Markdown.

Each entry must name the renderer export would use, so the walk goes through
``registry.resolve`` with the names export passes, and follows children only
where the built-in container renderers do.
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings
from wagtail import blocks
from wagtail.contrib.typed_table_block.blocks import TypedTableBlock
from wagtail.images.blocks import ImageBlock

from tests.test_container_defaults import DividerBlock, PromoBlock
from wagtail_markdown_agents.rendering import registry
from wagtail_markdown_agents.rendering.coverage import (
    BUILT_IN,
    CUSTOM_TEMPLATE,
    DEFAULT_TEMPLATE,
    PROJECT,
    build_report,
    walk_streams,
)
from wagtail_markdown_agents.rendering.registry import register_renderer


class QuoteBlock(blocks.StructBlock):
    quote = blocks.TextBlock()
    attribution = blocks.CharBlock()


class CardBlock(blocks.StructBlock):
    heading = blocks.CharBlock()
    background = blocks.ChoiceBlock(choices=[("dark", "Dark")])


class MissingTemplateBlock(blocks.StructBlock):
    text = blocks.CharBlock()

    class Meta:
        template = "testapp/blocks/no_such_template.html"


class BodyBlock(blocks.StreamBlock):
    promo = PromoBlock()
    divider = DividerBlock()
    quote = QuoteBlock()
    cards = blocks.ListBlock(CardBlock())
    templated_list = blocks.ListBlock(
        blocks.CharBlock(), template="testapp/blocks/section_block.html"
    )
    image = ImageBlock()
    raw = blocks.RawHTMLBlock()
    stats = TypedTableBlock([("number", blocks.IntegerBlock()), ("label", blocks.CharBlock())])
    broken = MissingTemplateBlock()


@pytest.fixture
def project_renderers(monkeypatch):
    monkeypatch.setattr(registry, "_name_renderers", {})
    monkeypatch.setattr(registry, "_class_renderers", dict(registry._class_renderers))

    @register_renderer(QuoteBlock)
    def render_quote(block, value, context):
        return f"> {value['quote']}"

    @register_renderer(block_name="background")
    def drop_background(block, value, context):
        return ""

    return render_quote, drop_background


def entries(*streams):
    return {
        (e.name, e.block_class.rsplit(".", 1)[-1]): e
        for e in walk_streams([(f"test.Page.{n}", BodyBlock()) for n in streams or ["body"]])
    }


def run(*args):
    output = StringIO()
    call_command("agentmd_blocks", *args, stdout=output)
    return output.getvalue()


def test_templated_blocks_are_custom_template_and_their_children_are_not_listed():
    found = entries()
    promo = found["promo", "PromoBlock"]
    assert promo.path == CUSTOM_TEMPLATE
    assert promo.template == "testapp/blocks/promo_block.html"
    assert found["divider", "DividerBlock"].path == CUSTOM_TEMPLATE
    templated_list = found["templated_list", "ListBlock"]
    assert templated_list.path == CUSTOM_TEMPLATE
    # The templates render these children, so their renderers are never reached.
    assert all(
        "promo >" not in loc and "templated_list >" not in loc
        for e in found.values()
        for loc in e.locations
    )


def test_plain_containers_recurse_with_the_names_export_passes():
    found = entries()
    assert found["quote", "QuoteBlock"].path == BUILT_IN
    assert found["quote", "TextBlock"].locations == ["test.Page.body > quote > quote"]
    assert found["cards", "ListBlock"].renderer.endswith("render_list")
    # ListBlock items are rendered without a name, as render_list does.
    assert found[None, "CardBlock"].locations == ["test.Page.body > cards > item"]
    assert found["background", "ChoiceBlock"].path == BUILT_IN


def test_typed_table_columns_are_walked_without_names():
    found = entries()
    assert found[None, "IntegerBlock"].locations == ["test.Page.body > stats > number"]
    assert found[None, "CharBlock"].locations == ["test.Page.body > stats > label"]


def test_specialised_renderers_are_leaves():
    found = entries()
    assert found["image", "ImageBlock"].renderer.endswith("render_image")
    assert not any(" > image > " in loc for e in found.values() for loc in e.locations)


def test_blocks_without_a_custom_template_fall_back_to_wagtail_html():
    raw = entries()["raw", "RawHTMLBlock"]
    assert raw.path == DEFAULT_TEMPLATE
    assert raw.template == ""


def test_a_missing_template_is_reported_as_custom_and_not_found():
    broken = entries()["broken", "MissingTemplateBlock"]
    assert broken.path == CUSTOM_TEMPLATE
    assert broken.template == "testapp/blocks/no_such_template.html (not found)"


def test_project_renderers_by_class_and_by_name(project_renderers):
    found = entries()
    quote = found["quote", "QuoteBlock"]
    assert quote.path == PROJECT
    assert quote.renderer == "tests.test_block_coverage.project_renderers.<locals>.render_quote"
    assert not quote.by_name
    # The project renderer is a leaf: its fields are no longer listed.
    assert ("attribution", "CharBlock") not in found
    background = found["background", "ChoiceBlock"]
    assert background.path == PROJECT and background.by_name


def test_entries_match_what_resolve_returns(project_renderers):
    body = BodyBlock()
    for name, child in body.child_blocks.items():
        entry = entries()[name, type(child).__name__]
        assert entry.renderer.endswith(registry.resolve(child, name).__qualname__)


def test_the_same_definition_merges_its_locations():
    promo = entries("body", "sidebar")["promo", "PromoBlock"]
    assert promo.locations == ["test.Page.body > promo", "test.Page.sidebar > promo"]


def test_report_covers_exportable_page_types_and_skips_form_pages():
    report = build_report()
    assert report.page_types == [
        "testapp.ArticlePage",
        "testapp.ContentPage",
        "testapp.MarkdownArticlePage",
    ]
    assert report.skipped == {"testapp.FormPage": "form page extraction is not supported"}


@override_settings(
    WAGTAIL_MARKDOWN_AGENTS={
        "PAGE_TYPES": ["testapp.ContentPage", "testapp.ArticlePage"],
        "PAGE_FIELDS": {"testapp.ContentPage": ["intro"]},
    }
)
def test_report_respects_page_types_and_page_fields():
    report = build_report()
    assert report.page_types == ["testapp.ArticlePage", "testapp.ContentPage"]
    locations = [loc for e in report.entries for loc in e.locations]
    assert locations and all(loc.startswith("testapp.ArticlePage.body") for loc in locations)


def test_command_groups_blocks_by_path_and_summarises():
    output = run()
    assert output.startswith("Block coverage for 3 page types: testapp.ArticlePage,")
    assert "Skipped testapp.FormPage: form page extraction is not supported" in output
    assert "\nWagtail default HTML (1)\n" in output
    assert "  raw_html  wagtail.blocks.field_block.RawHTMLBlock  -> no template\n" in output
    assert "    in testapp.ArticlePage.body > raw_html and 2 more\n" in output
    assert "-> render_rich_text\n" in output
    assert output.endswith("project=0 built_in=12 custom_template=0 default_html=1\n")
