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


@pytest.mark.parametrize(
    "html",
    [
        '<p>Before.</p><img src="https://350.org/a.png" alt="A"><p>After.</p>',
        '<h2>Before.</h2><img src="https://350.org/a.png" alt="A"><ul><li>After.</li></ul>',
    ],
    ids=["paragraphs", "heading-and-list"],
)
def test_image_between_blocks_gets_no_padding_space(html):
    assert rich(html).split("\n\n")[1] == "![A](https://350.org/a.png)"


def test_image_after_a_line_break_starts_its_line():
    assert rich('<p>Before<br><img src="https://350.org/a.png" alt="A"></p>') == (
        "Before  \n![A](https://350.org/a.png)"
    )


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


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        (
            '<p>See the map.</p><iframe src="https://www.google.com/maps/d/embed?mid=abc"'
            ' title="Campaign  map"></iframe>',
            "See the map.\n\n[Campaign map](https://www.google.com/maps/d/embed?mid=abc)",
        ),
        (
            '<div><iframe src="https://quiz.example.org/fr/"></iframe></div>',
            "[https://quiz.example.org/fr/](https://quiz.example.org/fr/)",
        ),
        (
            '<iframe src="/embed/map/" title="Map"></iframe>',
            "[Map](http://localhost:8000/embed/map/)",
        ),
        (
            '<iframe src="//player.example/v/1" title="Video"></iframe>',
            "[Video](https://player.example/v/1)",
        ),
        (
            '<iframe src="https://x.org/a b(1)" title="[Quiz] *now*"></iframe>',
            r"[\[Quiz\] \*now\*](https://x.org/a%20b%281%29)",
        ),
        (
            '<p>Before<iframe src="https://x.org/" title="X"></iframe>after</p>',
            "Before [X](https://x.org/) after",
        ),
    ],
    ids=["title", "no-title", "site-relative", "protocol-relative", "escaped", "inline"],
)
def test_iframe_becomes_a_link_to_its_source(html, expected):
    # An iframe has no text, so without this an agent loses the embed (#82).
    assert rich(html) == expected


@pytest.mark.parametrize(
    "src",
    [
        "",
        "   ",
        "about:blank",
        "javascript:alert(1)",
        "JavaScript:void(0)",
        "data:text/html,x",
        "#",
    ],
)
def test_iframe_without_a_fetchable_source_is_omitted(src):
    assert rich(f'<p>Before</p><iframe src="{src}" title="T"></iframe><p>After</p>') == (
        "Before\n\nAfter"
    )


def test_iframe_without_src_is_omitted():
    assert rich('<p>Before</p><iframe title="T"></iframe><p>After</p>') == "Before\n\nAfter"


def test_iframe_inside_a_link_gives_its_text_only():
    # Link text must stay inline: a link can't hold another link.
    html = (
        '<p><a href="https://350.org/act/">Act '
        '<iframe src="https://x.org/" title="X"></iframe>now</a></p>'
    )

    assert rich(html) == "[Act now](https://350.org/act/)"


def test_embed_after_a_dropped_script_gets_no_padding_space():
    html = '<p>Raw</p><script>x()</script><iframe src="https://x.org/" title="X"></iframe>'

    assert rich(html) == "Raw\n\n[X](https://x.org/)"


@pytest.mark.parametrize(
    "img",
    [
        '<img src="#" style="width:100%">',
        '<img src="#slide-1" alt="Slide">',
        '<img src="">',
        "<img alt='Gone'>",
    ],
    ids=["fragment", "named-fragment", "empty", "missing"],
)
def test_image_with_nothing_to_fetch_is_omitted(img):
    # A placeholder for a script to fill has no image an agent can fetch (#83).
    assert rich(f"<p>Before</p><div>{img}</div><p>After</p>") == "Before\n\nAfter"


@pytest.mark.parametrize(
    "link",
    [
        '<a class="prev" onclick="plusSlides(-1)">&#10094;</a>',
        '<a ONCLICK="go()">Next</a>',
        '<a onkeydown="go()" role="button">Open</a>',
    ],
    ids=["onclick", "upper-case", "other-event"],
)
def test_scripted_control_without_href_is_omitted(link):
    # A link with no href that only runs a script is a control, not content (#83).
    assert rich(f"<p>Before</p>{link}<p>After</p>") == "Before\n\nAfter"


def test_named_anchor_and_scripted_link_with_href_are_kept():
    html = (
        '<p><a id="x">Text</a> and <a name="y">more</a></p>'
        '<p><a href="/act/" onclick="track()">Act</a></p>'
    )

    assert rich(html) == "Text and more\n\n[Act](/act/)"


def test_slideshow_leaves_no_controls_or_gaps():
    html = (
        '<div class="slide-container"><img src="#" style="width:100%"></div>'
        '<a class="prev" onclick="plusSlides(-1)">&#10094;</a>'
        '<a class="next" onclick="plusSlides(1)">&#10095;</a>'
        '<div class="caption-container"><p id="caption"></p></div>'
        '<section class="thumbnail-container">'
        '<a class="thumbnail-prev" onclick="moveSwitcher(-1)">&#10094;</a>'
        '<div class="thumbnail"><img class="demo cursor" src="https://x.org/q.png" alt=""></div>'
        '<a class="thumbnail-next" onclick="moveSwitcher(1)">&#10095;</a>'
        "</section><p>After the slideshow.</p>"
    )

    assert rich(html) == "After the slideshow."
