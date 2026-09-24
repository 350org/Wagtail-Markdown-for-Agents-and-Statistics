"""The custom-block guide (#18): its example app works as documented.

``sandbox/events`` is an independent project app with its own blocks and a
``markdown_renderers.py``, autodiscovered like any project's. The guide shows
its files verbatim, and the outputs below are the ones the guide shows.
"""

import logging
import re
from pathlib import Path

import pytest
from sandbox.events import markdown_renderers
from sandbox.events.blocks import EventBlock, EventListBlock
from wagtail import blocks
from wagtail.models import Site

from wagtail_markdown_agents.rendering import register_renderer, registry, render_block
from wagtail_markdown_agents.rendering.context import render_context
from wagtail_markdown_agents.rendering.coverage import PROJECT, walk_streams
from wagtail_markdown_agents.rendering.registry import apply_setting_overrides, render_fallback

ROOT = Path(__file__).resolve().parent.parent
GUIDE = (ROOT / "docs" / "custom-blocks.md").read_text()
EVENTS = ROOT / "sandbox" / "events"

pytestmark = pytest.mark.django_db


def fenced(language):
    return [m.group(1) for m in re.finditer(rf"```{language}\n(.*?)```", GUIDE, re.S)]


@pytest.fixture
def context():
    return render_context(Site.objects.get(is_default_site=True).root_page.specific)


@pytest.fixture
def isolated_registry(monkeypatch):
    monkeypatch.setattr(registry, "_name_renderers", dict(registry._name_renderers))
    monkeypatch.setattr(registry, "_class_renderers", dict(registry._class_renderers))


def event_list():
    block = EventListBlock()
    value = block.to_python(
        {
            "heading": "Upcoming events",
            "events": [
                {
                    "title": "Climate strike",
                    "date": "2026-09-20",
                    "location": "Uhuru Park, Nairobi",
                    "summary": "<p>Bring a sign and <b>a friend</b>.</p>",
                    "style": "dark",
                },
                {"title": "Letter-writing evening", "date": "2026-10-02"},
            ],
        }
    )
    return block, value


@pytest.mark.parametrize(
    "path",
    ["blocks.py", "markdown_renderers.py", "templates/events/event_block.html"],
)
def test_the_guide_shows_the_example_app_verbatim(path):
    assert (EVENTS / path).read_text() in fenced("python") + fenced("html")


def test_the_renderers_are_autodiscovered():
    assert registry.resolve(EventBlock()) is markdown_renderers.render_event
    assert registry.resolve(EventListBlock()) is markdown_renderers.render_event_list


def test_the_template_fallback_leaks_the_button_label_as_the_guide_shows(context):
    block, value = event_list()
    before = render_fallback(EventBlock(), value["events"][0], context)
    assert f"```markdown\n{before}\n```" in GUIDE
    assert before.endswith("Add to calendar")


def test_the_renderers_produce_the_guide_output(context):
    block, value = event_list()
    output = render_block(block, value, context)
    assert f"```markdown\n{output}\n```" in GUIDE
    assert "dark" not in output and "Add to calendar" not in output


def test_the_guide_test_example_passes(context):
    block = EventBlock()
    value = block.to_python({"title": "Climate strike", "date": "2026-09-20", "style": "dark"})
    assert render_block(block, value, context) == "### Climate strike\n\n2026-09-20"
    assert '== "### Climate strike\\n\\n2026-09-20"' in GUIDE


def test_an_empty_list_leaves_the_container_out(context):
    block = EventListBlock()
    assert render_block(block, block.to_python({"heading": "None", "events": []}), context) == ""


def test_children_rendered_by_name_honour_name_registrations(context, isolated_registry):
    @register_renderer(block_name="location")
    def shout(block, value, context):
        return (value or "").upper()  # The second event has no location.

    block, value = event_list()
    assert "2026-09-20 · UHURU PARK, NAIROBI" in render_block(block, value, context)


def test_a_name_registration_applies_to_every_block_with_that_name(context, isolated_registry):
    register_renderer(block_name="background")(lambda block, value, context: "")

    class Banner(blocks.StructBlock):
        text = blocks.CharBlock()
        background = blocks.ChoiceBlock(choices=[("green", "Green")])

    class Card(blocks.StructBlock):
        heading = blocks.CharBlock()
        background = blocks.CharBlock()

    for block, value in (
        (Banner(), {"text": "Act now", "background": "green"}),
        (Card(), {"heading": "Join", "background": "#00ff00"}),
    ):
        output = render_block(block, block.to_python(value), context)
        assert "green" not in output.lower() and "#00ff00" not in output


def test_the_report_lists_the_container_as_a_project_renderer():
    stream = blocks.StreamBlock([("events", EventListBlock()), ("event", EventBlock())])
    found = {e.name: e for e in walk_streams([("site.Page.body", stream)])}
    assert set(found) == {"events", "event"}
    assert found["events"].path == found["event"].path == PROJECT


class MapBlock(blocks.StructBlock):
    """A reusable package's block, with the package's own renderer."""

    place = blocks.CharBlock()


def package_render_map(block, value, context):
    return f"Map of {value['place']}"


def project_render_map(block, value, context):
    return f"[{value['place']} on a map](https://maps.example/{value['place']})"


def test_a_project_overrides_a_package_renderer_in_settings(
    context, isolated_registry, settings, caplog
):
    register_renderer(MapBlock)(package_render_map)
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        "RENDERERS": {
            f"{__name__}.MapBlock": f"{__name__}.project_render_map",
        }
    }
    with caplog.at_level(logging.WARNING, logger=registry.__name__):
        apply_setting_overrides()
    block = MapBlock()
    assert render_block(block, block.to_python({"place": "Nairobi"}), context) == (
        "[Nairobi on a map](https://maps.example/Nairobi)"
    )
    assert caplog.records == []


def test_a_project_subclass_gets_its_own_renderer(context, isolated_registry):
    register_renderer(MapBlock)(package_render_map)

    class SiteMapBlock(MapBlock):
        pass

    register_renderer(SiteMapBlock)(project_render_map)
    assert registry.resolve(MapBlock()) is package_render_map
    assert registry.resolve(SiteMapBlock()) is project_render_map
