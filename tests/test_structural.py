"""Structural recursion for StructBlock, ListBlock and StreamBlock (#11).

The container renderers are tested directly and registered explicitly where a
test needs nesting. Registering them as defaults would send every custom
templated StructBlock through generic recursion before template fallback —
decision D12 in docs/acceptance/01-contentpage-end-to-end.md — so that waits
until D12 is agreed.
"""

import pytest
from wagtail import blocks

from wagtail_markdown_agents.rendering import registry
from wagtail_markdown_agents.rendering.blocks import (
    render_block,
    render_list,
    render_stream,
    render_struct,
)
from wagtail_markdown_agents.rendering.registry import register_renderer


@pytest.fixture(autouse=True)
def empty_registry(monkeypatch):
    monkeypatch.setattr(registry, "_class_renderers", {})
    monkeypatch.setattr(registry, "_name_renderers", {})


def render_str(block, value, context):
    return str(value)


@pytest.fixture
def scalars():
    """Leaf renderer that stringifies, standing in for the built-ins (#8)."""
    for cls in (blocks.CharBlock, blocks.BooleanBlock, blocks.IntegerBlock):
        register_renderer(cls)(render_str)


@pytest.fixture
def containers():
    register_renderer(blocks.StructBlock)(render_struct)
    register_renderer(blocks.ListBlock)(render_list)
    register_renderer(blocks.StreamBlock)(render_stream)


# Synthetic shapes mirroring the 350.org section -> card grid -> cards nesting.


class CardBlock(blocks.StructBlock):
    heading = blocks.CharBlock()
    description = blocks.CharBlock(required=False)


class CardGridBlock(blocks.StructBlock):
    cards = blocks.ListBlock(CardBlock())


class SectionContentBlock(blocks.StreamBlock):
    text = blocks.CharBlock()
    card_grid = CardGridBlock()


class SectionBlock(blocks.StructBlock):
    content = SectionContentBlock()
    background = blocks.ChoiceBlock(choices=[("light", "Light"), ("dark", "Dark")])


class BodyBlock(blocks.StreamBlock):
    section = SectionBlock()
    quote = blocks.CharBlock()
    divider = blocks.StaticBlock()


# Which containers are registered by default is tested in test_scalar_renderers.py:
# this module empties the registry before every test, so it cannot see defaults.


def test_struct_renders_children_in_declared_order(scalars):
    block = CardBlock()
    value = block.to_python({"description": "Move money.", "heading": "Divest"})

    assert render_struct(block, value, {}) == "Divest\n\nMove money."


def test_struct_skips_children_that_render_empty(scalars):
    block = CardBlock()
    value = block.to_python({"heading": "Organise", "description": ""})

    assert render_struct(block, value, {}) == "Organise"


def test_struct_keeps_false_and_zero(scalars):
    class FlagsBlock(blocks.StructBlock):
        enabled = blocks.BooleanBlock(required=False)
        count = blocks.IntegerBlock()

    block = FlagsBlock()
    value = block.to_python({"enabled": False, "count": 0})

    assert render_struct(block, value, {}) == "False\n\n0"


def test_struct_child_name_selects_name_override(scalars):
    register_renderer(block_name="description")(lambda b, v, c: f"_{v}_")
    block = CardBlock()
    value = block.to_python({"heading": "Divest", "description": "Move money."})

    assert render_struct(block, value, {}) == "Divest\n\n_Move money._"


def test_list_of_one_line_items_renders_as_bullets_in_order(scalars):
    block = blocks.ListBlock(blocks.CharBlock())
    value = block.to_python(["one", "two", "three"])

    assert render_list(block, value, {}) == "- one\n- two\n- three"


def test_list_of_multi_line_items_renders_as_separate_blocks(scalars, containers):
    block = blocks.ListBlock(CardBlock())
    value = block.to_python(
        [
            {"heading": "Divest", "description": "Move money."},
            {"heading": "Organise", "description": ""},
        ]
    )

    assert render_list(block, value, {}) == "Divest\n\nMove money.\n\nOrganise"


def test_list_drops_items_that_render_empty(scalars):
    block = blocks.ListBlock(blocks.CharBlock(required=False))
    value = block.to_python(["one", "", "two"])

    assert render_list(block, value, {}) == "- one\n- two"


def test_stream_renders_children_in_order_by_type_name(scalars):
    register_renderer(block_name="quote")(lambda b, v, c: f"> {v}")
    block = BodyBlock()
    value = block.to_python(
        [
            {"type": "quote", "value": "No planet B."},
            {"type": "quote", "value": "Keep it in the ground."},
        ]
    )

    assert render_stream(block, value, {}) == "> No planet B.\n\n> Keep it in the ground."


def test_value_less_static_block_is_rendered(scalars):
    register_renderer(blocks.StaticBlock)(lambda b, v, c: "---" if v is None else "unexpected")
    block = BodyBlock()
    value = block.to_python([{"type": "divider", "value": None}])

    assert render_stream(block, value, {}) == "---"


def test_surrounding_blank_lines_are_trimmed(scalars):
    register_renderer(block_name="quote")(lambda b, v, c: f"\n\n{v}\n\n")
    block = BodyBlock()
    value = block.to_python([{"type": "quote", "value": "A"}, {"type": "quote", "value": "B"}])

    assert render_stream(block, value, {}) == "A\n\nB"


def test_context_is_passed_to_children(scalars):
    seen = []
    register_renderer(block_name="quote")(lambda b, v, c: seen.append(c) or v)
    context = {"page": object()}
    block = BodyBlock()
    value = block.to_python([{"type": "quote", "value": "A"}])

    render_stream(block, value, context)

    assert seen == [context]


def test_nested_section_card_grid_cards(scalars, containers):
    # Project code omits a presentation field by name; the container does not guess.
    register_renderer(block_name="background")(lambda b, v, c: "")
    register_renderer(blocks.StaticBlock)(lambda b, v, c: "---")
    block = BodyBlock()
    value = block.to_python(
        [
            {
                "type": "section",
                "value": {
                    "background": "dark",
                    "content": [
                        {"type": "text", "value": "Intro"},
                        {
                            "type": "card_grid",
                            "value": {
                                "cards": [
                                    {"heading": "Divest", "description": "Move money."},
                                    {"heading": "Organise", "description": ""},
                                ]
                            },
                        },
                    ],
                },
            },
            {"type": "divider", "value": None},
            {"type": "quote", "value": "No planet B."},
        ]
    )

    assert render_block(block, value, {}) == (
        "Intro\n\nDivest\n\nMove money.\n\nOrganise\n\n---\n\nNo planet B."
    )


def test_render_block_uses_resolve(scalars):
    assert render_block(blocks.CharBlock(), "hello", {}) == "hello"
    register_renderer(block_name="shout")(lambda b, v, c: v.upper())
    assert render_block(blocks.CharBlock(), "hello", {}, block_name="shout") == "HELLO"
