"""Block-renderer registry dispatch (#7) and its precedence (D12, #1).

Name override, then the nearest specialised class renderer in the MRO, then a
custom template, then generic container recursion, then the fallback.
"""

import pytest
from wagtail import blocks
from wagtail.images.blocks import ImageBlock

from wagtail_markdown_agents.rendering import registry
from wagtail_markdown_agents.rendering.registry import (
    has_custom_template,
    register_renderer,
    resolve,
)

PROMO_TEMPLATE = "testapp/blocks/promo_block.html"


@pytest.fixture(autouse=True)
def empty_registry(monkeypatch):
    monkeypatch.setattr(registry, "_class_renderers", {})
    monkeypatch.setattr(registry, "_name_renderers", {})


class QuoteBlock(blocks.StructBlock):
    quote = blocks.TextBlock()


class PullQuoteBlock(QuoteBlock):
    pass


class PromoBlock(blocks.StructBlock):
    heading = blocks.CharBlock()

    class Meta:
        template = PROMO_TEMPLATE


class PromoQuoteBlock(QuoteBlock):
    class Meta:
        template = PROMO_TEMPLATE


def render_struct(block, value, context):
    return "struct"


def render_stream(block, value, context):
    return "stream"


def render_list(block, value, context):
    return "list"


@pytest.fixture
def containers():
    register_renderer(blocks.StructBlock)(render_struct)
    register_renderer(blocks.StreamBlock)(render_stream)
    register_renderer(blocks.ListBlock)(render_list)


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


def test_nearest_class_in_mro_wins(containers):
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


# Precedence (D12)


def test_name_override_wins_over_a_custom_template(containers):
    register_renderer(block_name="promo")(render_named)

    assert resolve(PromoBlock(), block_name="promo") is render_named


def test_specialised_class_renderer_wins_over_a_custom_template(containers):
    register_renderer(QuoteBlock)(render_quote)

    assert resolve(PromoQuoteBlock()) is render_quote


def test_scalar_subclass_with_a_template_keeps_its_class_renderer():
    class LeadBlock(blocks.CharBlock):
        class Meta:
            template = PROMO_TEMPLATE

    register_renderer(blocks.CharBlock)(render_named)

    assert resolve(LeadBlock()) is render_named


def test_custom_template_wins_over_generic_recursion(containers):
    class PromoStreamBlock(blocks.StreamBlock):
        heading = blocks.CharBlock()

        class Meta:
            template = PROMO_TEMPLATE

    assert resolve(PromoBlock()) is registry.render_fallback
    assert resolve(PromoStreamBlock()) is registry.render_fallback
    assert resolve(blocks.ListBlock(blocks.CharBlock(), template=PROMO_TEMPLATE)) is (
        registry.render_fallback
    )


def test_template_passed_to_the_block_instance_counts(containers):
    block = blocks.StructBlock([("heading", blocks.CharBlock())], template=PROMO_TEMPLATE)

    assert resolve(block) is registry.render_fallback


def test_plain_containers_recurse(containers):
    class CardBlock(blocks.StructBlock):
        heading = blocks.CharBlock()

    class BodyBlock(blocks.StreamBlock):
        card = CardBlock()

    assert resolve(CardBlock()) is render_struct
    assert resolve(BodyBlock()) is render_stream
    assert resolve(blocks.ListBlock(CardBlock())) is render_list


def test_unregistered_templated_container_without_containers_gets_fallback():
    assert resolve(PromoBlock()) is registry.render_fallback
    assert resolve(blocks.StructBlock()) is registry.render_fallback


def test_generic_container_registered_by_a_project_still_ranks_below_templates():
    # Registering StructBlock itself replaces generic recursion; it is not a
    # specialised renderer, so templated StructBlocks keep their template.
    register_renderer(blocks.StructBlock)(render_named)

    assert resolve(PromoBlock()) is registry.render_fallback
    assert resolve(QuoteBlock()) is render_named


def test_template_chosen_per_value_is_honoured(containers):
    class ChoosingBlock(blocks.StructBlock):
        heading = blocks.CharBlock()

        def get_template(self, value=None, context=None):
            return PROMO_TEMPLATE if value and value.get("heading") == "promo" else None

    block = ChoosingBlock()
    promo = block.to_python({"heading": "promo"})
    plain = block.to_python({"heading": "plain"})

    assert resolve(block, value=promo, context={}) is registry.render_fallback
    assert resolve(block, value=plain, context={}) is render_struct


# Custom versus inherited Wagtail templates


def test_wagtail_default_template_is_not_custom(containers):
    class ProjectImageBlock(ImageBlock):
        pass

    assert ProjectImageBlock().get_template()  # Wagtail's own image template
    assert not has_custom_template(ProjectImageBlock())
    assert resolve(ProjectImageBlock()) is render_struct


def test_project_template_is_custom():
    assert has_custom_template(PromoBlock())


def test_block_without_a_template_is_not_custom():
    assert not has_custom_template(QuoteBlock())
    assert not has_custom_template(blocks.CharBlock())


def test_project_override_of_a_wagtail_template_path_is_custom(settings, tmp_path):
    template = ImageBlock().get_template()
    (tmp_path / template).parent.mkdir(parents=True)
    (tmp_path / template).write_text("<figure>{{ value }}</figure>")
    settings.TEMPLATES = [{**settings.TEMPLATES[0], "DIRS": [tmp_path]}]

    assert has_custom_template(ImageBlock())


def test_missing_template_counts_as_custom_so_the_error_is_reported(containers):
    block = blocks.StructBlock([("heading", blocks.CharBlock())], template="missing.html")

    assert has_custom_template(block)
    assert resolve(block) is registry.render_fallback
