"""Built-in renderers for RichTextBlock, CharBlock and TextBlock (#9).

Headings keep the level the HTML gives them, in ATX form. Project heading
blocks such as bakerydemo's HeadingBlock render through their own template
via the fallback (#12), so they need no special case here.
"""

import pytest
from wagtail import blocks
from wagtail.images import get_image_model
from wagtail.images.tests.utils import get_test_image_file
from wagtail.models import Page, Site

from wagtail_markdown_agents.rendering.blocks import (
    render_block,
    render_plain_text,
    render_rich_text,
)
from wagtail_markdown_agents.rendering.registry import resolve


def rich(html):
    block = blocks.RichTextBlock()
    return render_block(block, block.to_python(html), {})


def test_built_in_text_renderers_are_registered_at_startup():
    assert resolve(blocks.RichTextBlock()) is render_rich_text
    assert resolve(blocks.CharBlock()) is render_plain_text
    assert resolve(blocks.TextBlock()) is render_plain_text


# Rich text: conversion


def test_inline_formatting_and_links():
    html = '<p>Join the <b>global</b> <i>movement</i> at <a href="https://350.org/">350</a>.</p>'

    assert rich(html) == "Join the **global** *movement* at [350](https://350.org/)."


def test_headings_keep_their_level_in_atx_form():
    assert rich("<h2>Why now</h2><h3>Detail</h3><p>Text</p>") == "## Why now\n\n### Detail\n\nText"


def test_lists():
    assert rich("<ul><li>one</li><li>two</li></ul><ol><li>a</li><li>b</li></ol>") == (
        "- one\n- two\n\n1. a\n2. b"
    )


def test_script_and_style_are_removed_with_their_content():
    html = '<p>Keep</p><script>alert("x")</script><style>p{color:red}</style><p>me</p>'

    assert rich(html) == "Keep\n\nme"


def test_entities_and_unicode_are_preserved():
    assert rich("<p>Caf&eacute; &amp; &lt;tag&gt; — “quotes” 🌍 naïve</p>") == (
        "Café & <tag> — “quotes” 🌍 naïve"
    )


def test_code_block_keeps_whitespace_and_language_hint():
    html = '<pre><code class="language-python">def f():\n    return 1\n</code></pre>'

    assert rich(html) == "```python\ndef f():\n    return 1\n```"


@pytest.mark.parametrize(
    "html",
    [
        '<p>Before<img src="https://350.org/a.png" alt="A">after</p>',
        '<p>Before <img src="https://350.org/a.png" alt="A"> after</p>',
    ],
    ids=["unspaced", "already-spaced"],
)
def test_inline_image_is_separated_from_text_by_one_space(html):
    assert rich(html) == "Before ![A](https://350.org/a.png) after"


def test_site_relative_image_src_becomes_absolute():
    assert rich('<p><img src="/a.png" alt="A"></p>') == "![A](http://localhost:8000/a.png)"


def test_external_and_protocol_relative_image_src_are_left_alone():
    html = '<p><img src="//cdn.example/a.png" alt="A"> <img src="https://x.org/b.png" alt="B"></p>'

    assert rich(html) == "![A](//cdn.example/a.png) ![B](https://x.org/b.png)"


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ('<p><img src="/icon.svg" alt=""></p>', ""),
        ('<p><a href="https://350.org/"><img src="/icon.svg" alt=""></a></p>', ""),
        (
            '<p><a href="https://350.org/"><img src="/i.svg" alt=""> Act</a></p>',
            "[Act](https://350.org/)",
        ),
        ('<figure><img src="/bg.jpg" alt=""><figcaption>Credit</figcaption></figure>', "Credit"),
        ('<p><img src="/a.png"></p>', "![](http://localhost:8000/a.png)"),
    ],
    ids=["decorative", "decorative-only-link", "decorative-in-link", "caption", "missing-alt"],
)
def test_decorative_empty_alt_images_are_omitted(html, expected):
    # alt="" marks an image decorative (WCAG); a missing alt is unknown, so kept.
    assert rich(html) == expected


def test_template_content_is_omitted():
    # <template> is inert: a browser never renders it.
    html = '<p>Before</p><template><p>Row</p><a href="/x">Link</a></template><p>After</p>'

    assert rich(html) == "Before\n\nAfter"


def test_hidden_markup_other_than_template_is_kept():
    # Collapsed panels and <noscript> links are content; renderers decide.
    html = (
        '<div class="hidden"><p>Answer</p></div><div hidden><p>Tab</p></div>'
        '<noscript><a href="/form/">Sign up</a></noscript>'
    )

    assert rich(html) == "Answer\n\nTab\n\n[Sign up](/form/)"


def test_empty_rich_text_renders_empty():
    assert rich("") == ""


# Rich text: expanding Wagtail's stored references


@pytest.mark.django_db
def test_internal_page_link_expands_to_the_page_url():
    home = Site.objects.get(is_default_site=True).root_page
    target = home.add_child(instance=Page(title="Get involved", slug="get-involved"))

    html = f'<p>Please <a linktype="page" id="{target.pk}">get involved</a>.</p>'

    assert rich(html) == "Please [get involved](/get-involved/)."


@pytest.mark.django_db
def test_link_to_a_missing_page_keeps_only_its_text():
    assert rich('<p>See <a linktype="page" id="999999">the handbook</a>.</p>') == (
        "See the handbook."
    )


@pytest.mark.django_db
def test_media_embed_becomes_a_link_without_fetching(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("oEmbed lookup attempted during rendering")

    monkeypatch.setattr("wagtail.embeds.embeds.get_embed", no_network)
    url = "https://www.youtube.com/watch?v=abc123"

    assert rich(f'<embed embedtype="media" url="{url}"/>') == f"<{url}>"


@pytest.mark.django_db
def test_image_embed_becomes_a_markdown_image(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    image = get_image_model().objects.create(title="Rally", file=get_test_image_file())

    output = rich(f'<embed embedtype="image" id="{image.pk}" format="fullwidth" alt="A rally"/>')

    # Absolute, because the sandbox sets WAGTAILADMIN_BASE_URL (#10).
    assert output.startswith("![A rally](http://localhost:8000/media/images/")
    assert output.endswith(")")


@pytest.mark.django_db
def test_image_embed_stays_site_relative_without_a_base_url(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    del settings.WAGTAILADMIN_BASE_URL
    image = get_image_model().objects.create(title="Rally", file=get_test_image_file())

    output = rich(f'<embed embedtype="image" id="{image.pk}" format="fullwidth" alt="A rally"/>')

    assert output.startswith("![A rally](/media/images/")


@pytest.mark.django_db
def test_decorative_image_embed_is_omitted(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    image = get_image_model().objects.create(title="Rally", file=get_test_image_file())

    embed = f'<embed embedtype="image" id="{image.pk}" format="fullwidth" alt=""/>'
    assert rich(f"<p>Before</p>{embed}<p>After</p>") == "Before\n\nAfter"


# CharBlock and TextBlock


def test_char_block_text_escapes_markdown_emphasis():
    block = blocks.CharBlock()

    assert render_block(block, "5 * 3 = 15 in snake_case", {}) == "5 \\* 3 = 15 in snake\\_case"


def test_text_block_keeps_line_breaks_and_paragraphs():
    block = blocks.TextBlock()

    assert render_block(block, "one\ntwo\n\nthree", {}) == "one  \ntwo\n\nthree"


@pytest.mark.parametrize("value", [None, ""])
def test_empty_plain_text_renders_empty(value):
    assert render_block(blocks.CharBlock(), value, {}) == ""
