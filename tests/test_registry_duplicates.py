"""Replacing a registered renderer is never silent (#84; wp-mfa-plugin #20 class).

Two project modules claiming the same block class or name used to overwrite
each other without a trace. Overriding a built-in and the RENDERERS setting
are the documented override paths, so those stay quiet.
"""

import logging

import pytest
from wagtail import blocks

from wagtail_markdown_agents.rendering import registry
from wagtail_markdown_agents.rendering.blocks import render_plain_text
from wagtail_markdown_agents.rendering.registry import (
    apply_setting_overrides,
    register_renderer,
    resolve,
)

LOGGER = "wagtail_markdown_agents.rendering.registry"


@pytest.fixture(autouse=True)
def empty_registry(monkeypatch):
    monkeypatch.setattr(registry, "_class_renderers", {})
    monkeypatch.setattr(registry, "_name_renderers", {})


def render_first(block, value, context):
    return "first"


def render_second(block, value, context):
    return "second"


def warnings_from(caplog):
    return [r.getMessage() for r in caplog.records if r.name == LOGGER]


def test_replacing_a_class_renderer_warns_naming_both(caplog):
    register_renderer(blocks.CharBlock)(render_first)

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        register_renderer(blocks.CharBlock)(render_second)

    [message] = warnings_from(caplog)
    assert "wagtail.blocks.field_block.CharBlock" in message
    assert "tests.test_registry_duplicates.render_first" in message
    assert "tests.test_registry_duplicates.render_second" in message


def test_replacing_a_name_renderer_warns_naming_both(caplog):
    register_renderer(block_name="pull_quote")(render_first)

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        register_renderer(block_name="pull_quote")(render_second)

    [message] = warnings_from(caplog)
    assert "'pull_quote'" in message
    assert "render_first" in message
    assert "render_second" in message


def test_last_registration_still_wins(caplog):
    register_renderer(blocks.CharBlock)(render_first)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        register_renderer(blocks.CharBlock)(render_second)

    assert resolve(blocks.CharBlock()) is render_second


def test_registering_the_same_function_again_is_silent(caplog):
    register_renderer(blocks.CharBlock)(render_first)

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        register_renderer(blocks.CharBlock)(render_first)

    assert warnings_from(caplog) == []


def test_overriding_a_built_in_is_silent(caplog):
    register_renderer(blocks.CharBlock)(render_plain_text)

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        register_renderer(blocks.CharBlock)(render_first)

    assert warnings_from(caplog) == []
    assert resolve(blocks.CharBlock()) is render_first


def test_renderers_setting_override_is_silent(caplog, settings):
    register_renderer(blocks.CharBlock)(render_first)
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        "RENDERERS": {"wagtail.blocks.CharBlock": "tests.test_registry_duplicates.render_second"}
    }

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        apply_setting_overrides()

    assert warnings_from(caplog) == []
    assert resolve(blocks.CharBlock()) is render_second


def test_different_keys_do_not_warn(caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        register_renderer(blocks.CharBlock)(render_first)
        register_renderer(blocks.TextBlock)(render_second)
        register_renderer(block_name="pull_quote")(render_first)

    assert warnings_from(caplog) == []
