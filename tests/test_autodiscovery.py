"""Renderer autodiscovery and the RENDERERS setting (#8)."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from sandbox.testapp import markdown_renderers as sandbox_renderers
from wagtail import blocks

from wagtail_markdown_agents.rendering import registry
from wagtail_markdown_agents.rendering.registry import (
    apply_setting_overrides,
    register_renderer,
    resolve,
)

NOT_CALLABLE = "not a function"


class ShortBlock(blocks.CharBlock):
    pass


def render_shout(block, value, context):
    return str(value).upper()


def render_other(block, value, context):
    return "other"


@pytest.fixture
def empty_registry(monkeypatch):
    monkeypatch.setattr(registry, "_class_renderers", {})
    monkeypatch.setattr(registry, "_name_renderers", {})


def renderers_setting(settings, mapping):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"RENDERERS": mapping}


def test_app_markdown_renderers_modules_are_autodiscovered_at_startup():
    renderer = resolve(blocks.CharBlock(), block_name="sandbox_autodiscovered")

    assert renderer is sandbox_renderers.render_sandbox


def test_setting_registers_renderer_for_block_class(settings, empty_registry):
    renderers_setting(
        settings, {"wagtail.blocks.CharBlock": "tests.test_autodiscovery.render_shout"}
    )

    apply_setting_overrides()

    assert resolve(blocks.CharBlock()) is render_shout


def test_setting_covers_subclasses(settings, empty_registry):
    renderers_setting(
        settings, {"wagtail.blocks.CharBlock": "tests.test_autodiscovery.render_shout"}
    )

    apply_setting_overrides()

    assert resolve(ShortBlock()) is render_shout


def test_setting_overrides_decorator_registration(settings, empty_registry):
    register_renderer(blocks.CharBlock)(render_other)
    renderers_setting(
        settings, {"wagtail.blocks.CharBlock": "tests.test_autodiscovery.render_shout"}
    )

    apply_setting_overrides()

    assert resolve(blocks.CharBlock()) is render_shout


def test_empty_setting_changes_nothing(settings, empty_registry):
    register_renderer(blocks.CharBlock)(render_other)
    renderers_setting(settings, {})

    apply_setting_overrides()

    assert resolve(blocks.CharBlock()) is render_other


@pytest.mark.parametrize(
    ("mapping", "message"),
    [
        (
            {"wagtail.blocks.NoSuchBlock": "tests.test_autodiscovery.render_shout"},
            "wagtail.blocks.NoSuchBlock",
        ),
        (
            {"wagtail.blocks.CharBlock": "tests.test_autodiscovery.no_such_renderer"},
            "tests.test_autodiscovery.no_such_renderer",
        ),
        (
            {"tests.test_autodiscovery.render_shout": "tests.test_autodiscovery.render_shout"},
            "not a class",
        ),
        (
            {"wagtail.blocks.CharBlock": "tests.test_autodiscovery.NOT_CALLABLE"},
            "not callable",
        ),
    ],
    ids=["missing-block", "missing-renderer", "key-not-a-class", "value-not-callable"],
)
def test_invalid_setting_raises_improperly_configured(settings, empty_registry, mapping, message):
    renderers_setting(settings, mapping)

    with pytest.raises(ImproperlyConfigured, match="RENDERERS") as excinfo:
        apply_setting_overrides()

    assert message in str(excinfo.value)
