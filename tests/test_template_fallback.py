"""Template fallback, conversion hooks and offline render context (#12).

Unregistered blocks render their own template to HTML, which is converted
like rich text. Whether a custom-templated StructBlock reaches this fallback
before generic container recursion is decision D12 on #63; containers are not
registered yet, so every unregistered block falls back here.
"""

import pytest
from django.apps import apps
from wagtail import blocks, hooks
from wagtail.models import Page, Site

from wagtail_markdown_agents.rendering.blocks import render_block
from wagtail_markdown_agents.rendering.context import render_context
from wagtail_markdown_agents.rendering.html import (
    CONVERTER_OPTIONS_HOOK,
    PRE_CONVERT_HOOK,
)
from wagtail_markdown_agents.rendering.registry import BlockRenderError


class PromoBlock(blocks.StructBlock):
    heading = blocks.CharBlock()
    text = blocks.CharBlock()

    class Meta:
        template = "testapp/blocks/promo_block.html"


class HeadingBlock(blocks.StructBlock):
    """Shape of bakerydemo's HeadingBlock."""

    heading_text = blocks.CharBlock()
    size = blocks.ChoiceBlock(choices=[("h2", "H2"), ("h3", "H3"), ("h4", "H4")], required=False)

    class Meta:
        template = "testapp/blocks/heading_block.html"


class BrokenBlock(blocks.StructBlock):
    """Unregistered, so it reaches the fallback. A CharBlock subclass would not:
    it inherits the plain-text renderer, and class renderers win over templates."""

    label = blocks.CharBlock()

    class Meta:
        template = "testapp/blocks/broken_block.html"


@pytest.fixture
def page(db):
    home = Site.objects.get(is_default_site=True).root_page
    return home.add_child(instance=Page(title="Get involved", slug="get-involved"))


def promo(context):
    block = PromoBlock()
    value = block.to_python({"heading": "Keep it in the ground", "text": "Join us."})
    return render_block(block, value, context)


# The fallback


def test_unregistered_block_renders_through_its_template(page):
    output = promo(render_context(page))

    assert output == (
        "## Keep it in the ground\n\nJoin us.\n\nFrom localhost: [Get involved](/get-involved/)"
    )


def test_script_in_a_template_is_removed_with_its_content(page):
    assert "trackPromo" not in promo(render_context(page))


@pytest.mark.parametrize(
    ("size", "expected"),
    [("h3", "### Healthy bread"), ("h4", "#### Healthy bread"), ("", "## Healthy bread")],
)
def test_project_heading_block_keeps_its_level(size, expected):
    block = HeadingBlock()
    value = block.to_python({"heading_text": "Healthy bread", "size": size})

    assert render_block(block, value, {}) == expected


def test_template_less_struct_block_keeps_its_values_until_d12():
    class CardBlock(blocks.StructBlock):
        heading = blocks.CharBlock()
        body = blocks.CharBlock()

    block = CardBlock()
    output = render_block(block, block.to_python({"heading": "Divest", "body": "Move money"}), {})

    assert "Divest" in output
    assert "Move money" in output


def test_template_error_raises_block_render_error_naming_the_block():
    block = BrokenBlock()

    with pytest.raises(BlockRenderError, match="BrokenBlock") as excinfo:
        render_block(block, block.to_python({"label": "x"}), {})

    assert excinfo.value.__cause__ is not None


# Hooks


def test_pre_convert_hook_rewrites_html_with_block_and_context(page):
    seen = []

    def drop_promo_footer(html, block, context):
        seen.append((type(block), context["page"]))
        return html.replace("From ", "Via ")

    with hooks.register_temporarily(PRE_CONVERT_HOOK, drop_promo_footer):
        output = promo(render_context(page))

    assert output.endswith("Via localhost: [Get involved](/get-involved/)")
    assert seen == [(PromoBlock, page)]


def test_pre_convert_hook_returning_none_leaves_html_unchanged(page):
    context = render_context(page)
    expected = promo(context)

    with hooks.register_temporarily(PRE_CONVERT_HOOK, lambda html, block, context: None):
        assert promo(context) == expected


def test_pre_convert_hooks_run_in_order():
    calls = []

    def first(html, block, context):
        calls.append("first")

    def second(html, block, context):
        calls.append("second")

    block = blocks.RichTextBlock()

    with (
        hooks.register_temporarily(PRE_CONVERT_HOOK, second, order=10),
        hooks.register_temporarily(PRE_CONVERT_HOOK, first, order=-10),
    ):
        render_block(block, block.to_python("<p>x</p>"), {})

    assert calls == ["first", "second"]


def test_converter_options_hook_applies_to_every_html_path(page):
    def star_bullets(options, block, context):
        options["bullets"] = "*"

    rich = blocks.RichTextBlock()
    with hooks.register_temporarily(CONVERTER_OPTIONS_HOOK, star_bullets):
        rich_output = render_block(rich, rich.to_python("<ul><li>a</li></ul>"), {})
        raw = blocks.RawHTMLBlock()  # unregistered, so it reaches the HTML fallback
        fallback_output = render_block(raw, raw.to_python("<ul><li>b</li></ul>"), {})

    assert rich_output == "* a"
    assert fallback_output == "* b"


# Offline render context


def test_render_context_supplies_page_site_and_locale(page):
    context = render_context(page)

    assert context["page"] == page
    assert context["site"] == Site.objects.get(is_default_site=True)
    assert context["locale"] == page.locale


def test_render_context_accepts_an_explicit_site(page):
    other = Site.objects.create(hostname="example.org", root_page=page, is_default_site=False)

    assert render_context(page, site=other)["site"] == other


def test_render_context_omits_settings_without_contrib_settings(page):
    assert not apps.is_installed("wagtail.contrib.settings")
    assert "settings" not in render_context(page)


def test_render_context_binds_settings_to_the_site(page, monkeypatch):
    real = apps.is_installed
    monkeypatch.setattr(
        apps, "is_installed", lambda name: name == "wagtail.contrib.settings" or real(name)
    )

    context = render_context(page)

    assert context["settings"].request_or_site == context["site"]
