"""Synthetic content-bearing template shapes; see the fixture README for provenance."""

import pytest
from wagtail import blocks
from wagtail.images import get_image_model
from wagtail.images.blocks import ImageChooserBlock
from wagtail.images.tests.utils import get_test_image_file
from wagtail.models import Site

from tests.test_golden import assert_matches_golden
from wagtail_markdown_agents.rendering import render_block
from wagtail_markdown_agents.rendering.context import render_context
from wagtail_markdown_agents.rendering.registry import render_fallback, resolve

pytestmark = pytest.mark.django_db
PREFIX = "testapp/blocks/wtrx/"


def template_block(name, fields):
    return blocks.StructBlock(fields, template=f"{PREFIX}{name}.html")


def cases(image):
    """The eight remaining template paths; donation has its own context renderer."""
    image_field = ("image", ImageChooserBlock(required=False))
    rich = ("content", blocks.RichTextBlock(required=False))
    heading = ("heading", blocks.CharBlock(required=False))
    links = [
        ("link_text", blocks.CharBlock(required=False)),
        ("link_page", blocks.PageChooserBlock(required=False)),
        ("link_url", blocks.URLBlock(required=False)),
    ]
    yield "heading", template_block("heading", [heading]), {"heading": "Why now"}
    yield (
        "raw_html",
        blocks.RawHTMLBlock(template=PREFIX + "raw_html.html"),
        (
            "<h2>Raw HTML</h2><p>Visible <em>copy</em>.</p>"
            '<iframe src="https://video.example.org/player"></iframe>'
            "<script>DO NOT EXPORT</script><template>INERT CONTENT</template>"
        ),
    )
    yield (
        "image_grid",
        template_block(
            "image_grid",
            [
                heading,
                (
                    "images",
                    blocks.ListBlock(
                        blocks.StructBlock([image_field, ("alt_text", blocks.CharBlock())])
                    ),
                ),
            ],
        ),
        {
            "heading": "In pictures",
            "images": [{"image": image.pk, "alt_text": "Marchers"}, {"image": image.pk}],
        },
    )
    yield (
        "logo_grid",
        template_block(
            "logo_grid",
            [
                heading,
                (
                    "logos",
                    blocks.ListBlock(
                        blocks.StructBlock([image_field, ("name", blocks.CharBlock()), *links[1:]])
                    ),
                ),
            ],
        ),
        {
            "heading": "Partners",
            "logos": [
                {"image": image.pk, "name": "Climate group", "link_url": "https://partner.example"},
                {"image": image.pk, "name": "Local organisers"},
            ],
        },
    )
    yield (
        "image_card_list",
        template_block(
            "image_card_list",
            [heading, image_field, ("cards", blocks.ListBlock(blocks.StructBlock([rich])))],
        ),
        {
            "heading": "Our priorities",
            "image": image.pk,
            "cards": [
                {"content": "<h3>Divest</h3><p>Move the money.</p>"},
                {"content": "<h3>Organise</h3><p>Build local groups.</p>"},
            ],
        },
    )
    yield (
        "image_text",
        template_block("image_text", [image_field, rich, ("crop", blocks.BooleanBlock()), *links]),
        {
            "image": image.pk,
            "crop": True,
            "content": "<h2>People power</h2><p>Act together.</p>",
            "link_text": "Join us",
            "link_url": "https://example.org/join",
        },
    )
    yield (
        "feature_panel",
        template_block(
            "feature_panel",
            [
                image_field,
                rich,
                ("eyebrow", blocks.CharBlock()),
                ("anchor", blocks.CharBlock()),
                *links,
            ],
        ),
        {
            "image": image.pk,
            "eyebrow": "Campaign",
            "content": "<h2>A just transition</h2><p>Communities lead.</p>",
            "link_text": "Read more",
            "link_url": "https://example.org/transition",
        },
    )
    yield (
        "callout",
        template_block("callout", [image_field, rich, *links]),
        {
            "image": image.pk,
            "content": "<h2>Keep going</h2><p>Every action matters.</p>",
            "link_text": "Take action",
            "link_url": "https://example.org/action",
        },
    )


@pytest.fixture
def rendered_cases(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.WAGTAILADMIN_BASE_URL = "https://example.org"
    image = get_image_model().objects.create(title="Rally", file=get_test_image_file())
    context = render_context(Site.objects.get(is_default_site=True).root_page)
    rendered = {}
    for name, block, raw in cases(image):
        value = block.to_python(raw)
        assert resolve(block, value=value, context=context) is render_fallback
        rendered[name] = render_block(block, value, context)
    return rendered


def test_template_fallback_gallery_golden(rendered_cases):
    output = "\n\n".join(f"# {name}\n\n{text}" for name, text in rendered_cases.items())
    assert_matches_golden("wtrx-template-fallbacks.md", output)
    assert "![" not in rendered_cases["callout"]  # Decorative background only.
    assert "![Climate group]" in rendered_cases["logo_grid"]
    assert "player" not in rendered_cases["raw_html"]
    assert "DO NOT EXPORT" not in output and "INERT CONTENT" not in output


def test_feature_panel_fragment_is_a_recorded_fallback_limit(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    image = get_image_model().objects.create(title="Rally", file=get_test_image_file())
    _, block, raw = next(case for case in cases(image) if case[0] == "feature_panel")
    raw.update(link_url="", anchor="join", link_text="Join")
    # Unlike the explicit ButtonBlock renderer, this template keeps fragments.
    # The review ledger records this as unresolved, not accepted presentation.
    assert "[Join](#join)" in render_block(block, block.to_python(raw), {})
