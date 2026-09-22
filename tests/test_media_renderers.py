"""Built-in renderers for image, embed and table blocks (#10).

Images are ``![alt](url)`` with absolute URLs when ``WAGTAILADMIN_BASE_URL``
is set; embeds are links that never call a provider; tables are GFM pipe
tables. ``ImageBlock`` is registered ahead of its ``StructBlock`` ancestry so
it is never rendered as three concatenated fields.
"""

import pytest
from wagtail import blocks
from wagtail.contrib.table_block.blocks import TableBlock
from wagtail.contrib.typed_table_block.blocks import TypedTableBlock
from wagtail.embeds import blocks as embed_blocks
from wagtail.embeds.blocks import EmbedBlock
from wagtail.embeds.models import Embed
from wagtail.images import get_image_model
from wagtail.images.blocks import ImageBlock, ImageChooserBlock
from wagtail.images.tests.utils import get_test_image_file

from wagtail_markdown_agents.rendering import registry
from wagtail_markdown_agents.rendering.blocks import (
    render_block,
    render_embed,
    render_image,
    render_struct,
    render_table,
    render_typed_table,
)
from wagtail_markdown_agents.rendering.registry import resolve

VIDEO = "https://www.youtube.com/watch?v=abc123"


@pytest.fixture
def image(db, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return get_image_model().objects.create(title="Rally", file=get_test_image_file())


@pytest.fixture(autouse=True)
def no_oembed_requests(monkeypatch):
    def fetch(*args, **kwargs):
        raise AssertionError("rendering must never call a provider's oEmbed API")

    monkeypatch.setattr(embed_blocks, "embed_to_frontend_html", fetch)


def render(block, value):
    return render_block(block, value, {})


def image_block_value(image, **fields):
    data = {"image": image.pk, "decorative": False, "alt_text": "A rally in Nairobi", **fields}
    return ImageBlock().to_python(data)


# Registration


@pytest.mark.parametrize(
    ("block", "renderer"),
    [
        (ImageChooserBlock(), render_image),
        (ImageBlock(), render_image),
        (EmbedBlock(), render_embed),
        (TableBlock(), render_table),
        (TypedTableBlock([("text", blocks.CharBlock())]), render_typed_table),
    ],
    ids=lambda x: type(x).__name__ if isinstance(x, blocks.Block) else x.__name__,
)
def test_built_ins_are_registered_at_startup(block, renderer):
    assert resolve(block) is renderer


def test_image_block_wins_over_a_struct_block_renderer(monkeypatch):
    monkeypatch.setitem(registry._class_renderers, blocks.StructBlock, render_struct)

    assert resolve(ImageBlock()) is render_image


# Images


def test_image_chooser_renders_a_markdown_image_with_an_absolute_url(image):
    output = render(ImageChooserBlock(), image)

    assert output.startswith("![Rally](http://localhost:8000/media/images/")
    assert output.endswith(")")


def test_image_url_stays_site_relative_without_a_base_url(image, settings):
    del settings.WAGTAILADMIN_BASE_URL

    assert render(ImageChooserBlock(), image).startswith("![Rally](/media/images/")


def test_image_chooser_prefers_the_image_description_as_alt_text(image):
    image.description = "Crowd marching with banners"

    assert render(ImageChooserBlock(), image).startswith("![Crowd marching with banners](")


def test_image_block_uses_its_contextual_alt_text(image):
    assert render(ImageBlock(), image_block_value(image)).startswith("![A rally in Nairobi](")


def test_image_block_without_alt_text_falls_back_to_the_default(image):
    assert render(ImageBlock(), image_block_value(image, alt_text="")).startswith("![Rally](")


def test_decorative_image_renders_nothing(image):
    assert render(ImageBlock(), image_block_value(image, decorative=True, alt_text="")) == ""


def test_legacy_image_block_value_stored_as_an_id_still_renders(image):
    assert render(ImageBlock(), ImageBlock().to_python(image.pk)).startswith("![Rally](")


def test_alt_text_brackets_are_escaped(image):
    image.title = "Rally [2026]"

    assert render(ImageChooserBlock(), image).startswith("![Rally \\[2026\\]](")


@pytest.mark.parametrize("block", [ImageChooserBlock(required=False), ImageBlock(required=False)])
def test_empty_image_renders_nothing(block):
    assert render(block, None) == ""


# Embeds


@pytest.mark.django_db
def test_embed_without_a_cached_title_is_an_autolink():
    assert render(EmbedBlock(), EmbedBlock().to_python(VIDEO)) == f"<{VIDEO}>"


@pytest.mark.django_db
def test_embed_with_a_cached_title_is_a_titled_link():
    Embed.objects.create(url=VIDEO, hash="h1", type="video", title="Rally [live]", html="<x>")

    assert render(EmbedBlock(), EmbedBlock().to_python(VIDEO)) == f"[Rally \\[live\\]]({VIDEO})"


@pytest.mark.django_db
def test_embed_cached_without_a_title_is_an_autolink():
    Embed.objects.create(url=VIDEO, hash="h2", type="video", title="", html="<x>")

    assert render(EmbedBlock(), EmbedBlock().to_python(VIDEO)) == f"<{VIDEO}>"


def test_empty_embed_renders_nothing():
    assert render(EmbedBlock(required=False), None) == ""


# TableBlock


def table(**value):
    return render(TableBlock(), {"first_row_is_table_header": False, **value})


def test_first_row_can_be_the_header():
    assert table(data=[["Country", "Target"], ["Kenya", "0"]], first_row_is_table_header=True) == (
        "| Country | Target |\n| --- | --- |\n| Kenya | 0 |"
    )


def test_table_without_a_header_row_gets_an_empty_one():
    assert table(data=[["Kenya", "0"], ["Peru", "1"]]) == (
        "|  |  |\n| --- | --- |\n| Kenya | 0 |\n| Peru | 1 |"
    )


def test_caption_precedes_the_table():
    assert table(data=[["a"]], table_caption="Targets by *country*") == (
        "Targets by \\*country\\*\n\n|  |\n| --- |\n| a |"
    )


def test_first_column_header_renders_as_an_ordinary_cell():
    output = table(data=[["Kenya", "0"]], first_col_is_header=True)

    assert output == "|  |  |\n| --- | --- |\n| Kenya | 0 |"


def test_empty_none_and_zero_cells():
    assert table(data=[["", None, 0], ["x", "y", "z"]]) == (
        "|  |  |  |\n| --- | --- | --- |\n|  |  | 0 |\n| x | y | z |"
    )


def test_pipes_are_escaped_and_markdown_is_escaped_in_cells():
    assert table(data=[["a|b", "5 * 3"]]) == "|  |  |\n| --- | --- |\n| a\\|b | 5 \\* 3 |"


def test_line_breaks_within_a_cell_become_br():
    assert table(data=[["line one\nline two", "para\n\ntwo"]]) == (
        "|  |  |\n| --- | --- |\n| line one<br>line two | para<br>two |"
    )


def test_ragged_rows_are_padded_to_the_widest():
    assert table(data=[["a"], ["b", "c"]]) == "|  |  |\n| --- | --- |\n| a |  |\n| b | c |"


def test_html_renderer_cells_convert_like_rich_text():
    block = TableBlock(table_options={"renderer": "html"})
    value = {"data": [["<b>bold</b>", "a &amp; b"]], "first_row_is_table_header": False}

    assert render(block, value) == "|  |  |\n| --- | --- |\n| **bold** | a & b |"


@pytest.mark.parametrize("value", [None, {}, {"data": []}])
def test_empty_table_renders_nothing(value):
    assert render(TableBlock(required=False), value) == ""


# TypedTableBlock


def typed_table(columns, rows, caption=""):
    block = TypedTableBlock(
        [
            ("text", blocks.CharBlock(required=False)),
            ("number", blocks.IntegerBlock(required=False)),
            ("rich", blocks.RichTextBlock(required=False)),
        ]
    )
    value = block.to_python(
        {"columns": columns, "rows": [{"values": row} for row in rows], "caption": caption}
    )
    return render(block, value)


def test_typed_table_headings_and_cells_go_through_the_column_renderers():
    output = typed_table(
        [{"type": "text", "heading": "Country"}, {"type": "number", "heading": "Target"}],
        [["Kenya", 0], ["Peru", None]],
    )

    assert output == "| Country | Target |\n| --- | --- |\n| Kenya | 0 |\n| Peru |  |"


def test_typed_table_rich_text_cell_is_flattened_to_one_line():
    output = typed_table(
        [{"type": "rich", "heading": "Note"}],
        [["<p>Keep <b>it</b> in the</p><p>ground | now</p>"]],
    )

    assert output == "| Note |\n| --- |\n| Keep **it** in the<br>ground \\| now |"


def test_typed_table_caption_precedes_the_table():
    output = typed_table([{"type": "text", "heading": "H"}], [["x"]], caption="Targets")

    assert output == "Targets\n\n| H |\n| --- |\n| x |"


def test_empty_typed_table_renders_nothing():
    block = TypedTableBlock([("text", blocks.CharBlock())], required=False)

    assert render(block, block.to_python(None)) == ""
    assert render(block, None) == ""
