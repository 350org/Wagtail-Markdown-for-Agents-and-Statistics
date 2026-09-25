"""Block templates never call an embed provider during export (#14, A3)."""

import threading

import pytest
from wagtail import blocks
from wagtail.embeds import embeds
from wagtail.embeds.blocks import EmbedBlock
from wagtail.embeds.exceptions import EmbedException
from wagtail.embeds.models import Embed

from wagtail_markdown_agents.rendering.blocks import render_block
from wagtail_markdown_agents.rendering.offline import offline_embeds

URL = "https://www.youtube.com/watch?v=abc123"


class TemplateEmbedBlock(blocks.StructBlock):
    """Shape of 350.org's VideoBlock: the template calls ``{% embed %}``."""

    url = blocks.URLBlock()
    caption = blocks.CharBlock(required=False)

    class Meta:
        template = "testapp/blocks/embed_block.html"


class TemplateEmbedChildBlock(blocks.StructBlock):
    """An EmbedBlock rendered through a parent template, as ``{{ value.video }}``."""

    video = EmbedBlock()

    class Meta:
        template = "testapp/blocks/embed_child_block.html"


@pytest.fixture
def finder_calls(monkeypatch):
    """Replace the network step behind the guard, recording each call."""
    calls = []

    def find_embed(url, max_width=None, max_height=None):
        calls.append(url)
        return {"type": "video", "html": "<p>Fetched</p>", "width": None, "height": None}

    # Behind the guard: wagtail.embeds.embeds calls this through it.
    monkeypatch.setattr("wagtail.embeds.finders.get_finders", lambda: [_Finder(find_embed)])
    return calls


class _Finder:
    def __init__(self, find):
        self.find_embed = find

    def accept(self, url):
        return True


def video(caption="Our story"):
    block = TemplateEmbedBlock()
    return block, block.to_python({"url": URL, "caption": caption})


@pytest.mark.django_db
def test_template_embed_is_not_fetched_during_export(finder_calls):
    block, value = video()

    assert render_block(block, value, {}) == "Our story"
    assert finder_calls == []


@pytest.mark.django_db
def test_a_stored_embed_is_still_used(finder_calls):
    Embed.objects.create(
        url=URL, hash=embeds.get_embed_hash(URL), type="rich", html="<p>Stored</p>"
    )
    block, value = video()

    assert render_block(block, value, {}) == "Stored\n\nOur story"
    assert finder_calls == []


@pytest.mark.django_db
def test_an_embed_block_rendered_inside_a_template_is_not_fetched(finder_calls):
    block = TemplateEmbedChildBlock()
    value = block.to_python({"video": URL})

    assert render_block(block, value, {}) == ""
    assert finder_calls == []


@pytest.mark.django_db
def test_wagtail_still_fetches_outside_export(finder_calls):
    assert embeds.get_embed(URL).html == "<p>Fetched</p>"
    assert finder_calls == [URL]


@pytest.mark.django_db
def test_the_guard_is_scoped_and_reset_after_errors(finder_calls):
    with pytest.raises(RuntimeError), offline_embeds():
        raise RuntimeError

    assert embeds.get_embed(URL).html == "<p>Fetched</p>"


@pytest.mark.django_db
def test_the_guard_does_not_reach_other_threads(finder_calls):
    results = []

    def fetch():
        # The provider lookup only: the test database can't be written from a thread.
        results.append(embeds.get_finder_for_embed(URL)["html"])

    with offline_embeds():
        with pytest.raises(EmbedException):
            embeds.get_finder_for_embed(URL)
        thread = threading.Thread(target=fetch)
        thread.start()
        thread.join()

    assert results == ["<p>Fetched</p>"]
