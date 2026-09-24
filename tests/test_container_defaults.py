"""Plain containers through the default renderers (D12, #2).

A StructBlock, StreamBlock or ListBlock without a custom template recurses into
its children with the built-in renderers; a templated block met along the way
renders through its template. The shapes mirror 350.org's section, card grid
and accordion nesting, without depending on the site's code.
"""

import pytest
from wagtail import blocks
from wagtail.models import Page, Site

from wagtail_markdown_agents.rendering import registry
from wagtail_markdown_agents.rendering.blocks import render_block
from wagtail_markdown_agents.rendering.context import render_context
from wagtail_markdown_agents.rendering.registry import register_renderer


class DividerBlock(blocks.StaticBlock):
    class Meta:
        template = "testapp/blocks/divider_block.html"


class PromoBlock(blocks.StructBlock):
    heading = blocks.CharBlock()
    text = blocks.CharBlock()

    class Meta:
        template = "testapp/blocks/promo_block.html"


class CardBlock(blocks.StructBlock):
    heading = blocks.CharBlock()
    description = blocks.CharBlock(required=False)


class CardGridBlock(blocks.StructBlock):
    cards = blocks.ListBlock(CardBlock())


class AccordionItemBlock(blocks.StructBlock):
    title = blocks.CharBlock()
    content = blocks.RichTextBlock()


class AccordionBlock(blocks.StructBlock):
    items = blocks.ListBlock(AccordionItemBlock())


class SectionBlock(blocks.StructBlock):
    background = blocks.ChoiceBlock(choices=[("dark", "Dark"), ("light", "Light")])
    content = blocks.StreamBlock(
        [
            ("text", blocks.RichTextBlock()),
            ("card_grid", CardGridBlock()),
            ("accordion", AccordionBlock()),
            ("promo", PromoBlock()),
        ]
    )


class BodyBlock(blocks.StreamBlock):
    section = SectionBlock()
    divider = DividerBlock()
    stat = blocks.IntegerBlock()


@pytest.fixture
def project_mapping(monkeypatch):
    """A project drops its presentation field by name, as #2 asks projects to."""
    monkeypatch.setattr(registry, "_name_renderers", {})
    register_renderer(block_name="background")(lambda b, v, c: "")


def section(*content):
    return {"type": "section", "value": {"background": "dark", "content": list(content)}}


def render(*stream, context=None):
    block = BodyBlock()
    return render_block(block, block.to_python(list(stream)), context or {})


CARD_GRID = {
    "type": "card_grid",
    "value": {
        "cards": [
            {"heading": "Divest", "description": "Move money out of fossil fuels."},
            {"heading": "Organise", "description": ""},
        ]
    },
}
ACCORDION = {
    "type": "accordion",
    "value": {
        "items": [
            {"title": "Who can join?", "content": "<p>Anyone.</p>"},
            {"title": "Is it free?", "content": "<p>Yes, <b>always</b>.</p>"},
        ]
    },
}


def test_section_card_grid_and_accordion_recurse_in_order(project_mapping):
    output = render(section({"type": "text", "value": "<p>Intro</p>"}, CARD_GRID, ACCORDION))

    assert output == (
        "Intro\n\n"
        "Divest\n\nMove money out of fossil fuels.\n\nOrganise\n\n"
        "Who can join?\n\nAnyone.\n\nIs it free?\n\nYes, **always**."
    )


def test_presentation_choice_renders_unless_the_project_maps_it():
    # Generic recursion cannot tell presentation from content; D5 leaves that
    # to project mappings.
    assert render(section()) == "Dark"


def test_templated_child_of_a_plain_container_uses_its_template(project_mapping, db):
    home = Site.objects.get(is_default_site=True).root_page
    page = home.add_child(instance=Page(title="Get involved", slug="get-involved"))
    promo = {"type": "promo", "value": {"heading": "Keep it in the ground", "text": "Join us."}}

    output = render(
        section({"type": "text", "value": "<p>Intro</p>"}, promo), context=render_context(page)
    )

    # The template sees the page context passed down through the recursion.
    assert output == (
        "Intro\n\n## Keep it in the ground\n\nJoin us.\n\n"
        "From localhost: [Get involved](/get-involved/)"
    )


def test_repeated_blocks_zero_and_value_less_static_block_survive(project_mapping):
    output = render(
        {"type": "stat", "value": 0},
        {"type": "divider", "value": None},
        section({"type": "text", "value": "<p>One</p>"}),
        section({"type": "text", "value": "<p>Two</p>"}),
        {"type": "stat", "value": 0},
    )

    assert output == "0\n\n---\n\nOne\n\nTwo\n\n0"
