"""Block-renderer registry dispatch (#7).

Settled rules only: name override, then class dispatch walking the MRO, then
the fallback. Precedence between a block's custom template and generic
container recursion is decision D12 in docs/acceptance/01-contentpage-end-to-end.md
and is not tested until agreed.
"""

import pytest
from wagtail import blocks

from wagtail_markdown_agents.rendering import registry
from wagtail_markdown_agents.rendering.registry import register_renderer, resolve


@pytest.fixture(autouse=True)
def empty_registry(monkeypatch):
    monkeypatch.setattr(registry, "_class_renderers", {})
    monkeypatch.setattr(registry, "_name_renderers", {})


class QuoteBlock(blocks.StructBlock):
    quote = blocks.TextBlock()


class PullQuoteBlock(QuoteBlock):
    pass


def render_struct(block, value, context):
    return "struct"


def render_quote(block, value, context):
    return "quote"


def render_named(block, value, context):
    return "named"


def test_exact_class_registration():
    register_renderer(QuoteBlock)(render_quote)

    assert resolve(QuoteBlock()) is render_quote


def test_subclass_uses_base_class_renderer():
    register_renderer(QuoteBlock)(render_quote)

    assert resolve(PullQuoteBlock()) is render_quote


def test_nearest_class_in_mro_wins():
    register_renderer(blocks.StructBlock)(render_struct)
    register_renderer(QuoteBlock)(render_quote)

    assert resolve(PullQuoteBlock()) is render_quote
    assert resolve(blocks.StructBlock()) is render_struct


def test_registration_order_does_not_change_mro_result():
    register_renderer(QuoteBlock)(render_quote)
    register_renderer(blocks.StructBlock)(render_struct)

    assert resolve(PullQuoteBlock()) is render_quote


def test_name_override_wins_over_class():
    register_renderer(QuoteBlock)(render_quote)
    register_renderer(block_name="pull_quote")(render_named)

    assert resolve(QuoteBlock(), block_name="pull_quote") is render_named


def test_unmatched_name_falls_back_to_class():
    register_renderer(QuoteBlock)(render_quote)
    register_renderer(block_name="pull_quote")(render_named)

    assert resolve(QuoteBlock(), block_name="quote") is render_quote
    assert resolve(QuoteBlock()) is render_quote


def test_unregistered_block_gets_fallback():
    assert resolve(blocks.CharBlock()) is registry.render_fallback


def test_decorator_returns_function_unchanged():
    assert register_renderer(QuoteBlock)(render_quote) is render_quote


@pytest.mark.parametrize("kwargs", [{}, {"block_class": QuoteBlock, "block_name": "q"}])
def test_register_requires_exactly_one_key(kwargs):
    with pytest.raises(TypeError):
        register_renderer(**kwargs)
