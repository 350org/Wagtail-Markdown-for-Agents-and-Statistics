"""Built-in block renderers.

Coverage: RichTextBlock (expand internal page/embed refs, then HTML→Markdown
via markdownify), CharBlock/TextBlock, the scalar, choice and chooser blocks
(#85), ImageBlock/ImageChooserBlock (#10), EmbedBlock (#10),
TableBlock/TypedTableBlock as GFM pipe tables (#10), and structural recursion
for StructBlock/ListBlock/StreamBlock. RawHTMLBlock and heading blocks render
through the template fallback, which converts their HTML like rich text.

The built-in renderers are registered when this module is imported, which
``registry.autodiscover()`` does before project ``markdown_renderers``
modules, so projects override them. The StructBlock, StreamBlock and ListBlock
renderers are generic: a container with its own template renders through that
template instead, so its presentation-only fields do not leak (decision D12,
see ``registry.resolve``).
"""

from collections.abc import Iterable

from django.apps import apps
from django.utils.html import linebreaks
from wagtail import blocks as wagtail_blocks
from wagtail.contrib.table_block.blocks import TableBlock
from wagtail.contrib.typed_table_block.blocks import TypedTableBlock

from .html import absolute_url, convert_html, expand_rich_text
from .registry import register_renderer, resolve


def render_block(block, value, context, block_name: str | None = None) -> str:
    """Render one block value with the renderer :func:`resolve` selects."""
    return resolve(block, block_name, value, context)(block, value, context)


def _join(parts: Iterable[str]) -> str:
    """Join rendered parts with blank lines, dropping parts that render empty.

    Only surrounding blank lines are trimmed, so indentation (code, nested
    lists) inside a part is preserved. Emptiness is judged on the rendered
    text, never the value, so ``False`` and ``0`` survive.
    """
    return "\n\n".join(_parts(parts))


def _parts(parts: Iterable[str]) -> list[str]:
    """Trim surrounding blank lines from each rendered part and drop empty ones."""
    return [p for p in (part.strip("\n") for part in parts) if p.strip()]


def render_struct(block, value, context) -> str:
    """Render a StructBlock's children in declared order."""
    return _join(
        render_block(child, value.get(name), context, block_name=name)
        for name, child in block.child_blocks.items()
    )


def render_list(block, value, context) -> str:
    """Render a ListBlock's items in order.

    When every item renders to a single line (text, numbers, links) the result is
    a Markdown bullet list, as Wagtail's own ``<ul>`` rendering is. When any item
    spans several lines (cards, rich text, nested blocks) items are separated by
    blank lines instead. Items that render empty are dropped.
    """
    parts = _parts(render_block(block.child_block, item, context) for item in value)
    if parts and all("\n" not in part for part in parts):
        return "\n".join(f"- {part}" for part in parts)
    return "\n\n".join(parts)


def render_stream(block, value, context) -> str:
    """Render a StreamBlock's children in order, keyed by their block type name."""
    return _join(
        render_block(child.block, child.value, context, block_name=child.block_type)
        for child in value
    )


def render_rich_text(block, value, context) -> str:
    """Expand stored page/document/image/media references, then convert to Markdown."""
    source = getattr(value, "source", value) or ""
    return convert_html(expand_rich_text(source), block, context)


def render_plain_text(block, value, context) -> str:
    """Render CharBlock/TextBlock text: escaped, line breaks and paragraphs kept."""
    if value is None or value == "":
        return ""
    return convert_html(linebreaks(str(value), autoescape=True), block, context)


def render_url(block, value, context) -> str:
    """Render a URL as a Markdown autolink."""
    return f"<{value}>" if value else ""


def render_email(block, value, context) -> str:
    """Render an email address as a Markdown autolink."""
    return f"<{value}>" if value else ""


def render_number(block, value, context) -> str:
    """Render a number as written: ``0`` is kept, a Decimal keeps its precision."""
    return "" if value is None else str(value)


def render_boolean(block, value, context) -> str:
    """Render the block's label (or "Yes") when true, nothing when false (decided on #85)."""
    if not value:
        return ""
    return render_plain_text(block, block.label or "Yes", context)


def render_temporal(block, value, context) -> str:
    """Render a date, time or datetime as ISO 8601, keeping any UTC offset."""
    return "" if value is None else value.isoformat()


def render_choice(block, value, context) -> str:
    """Render a choice's display label; a value missing from the choices renders as stored."""
    if value is None or value == "":
        return ""
    label = _choice_labels(block).get(value, value)
    return render_plain_text(block, str(label), context)


def render_multiple_choice(block, value, context) -> str:
    """Render the display labels of the selected choices, comma-separated, in order."""
    if not value:
        return ""
    labels = _choice_labels(block)
    return render_plain_text(block, ", ".join(str(labels.get(v, v)) for v in value), context)


def render_chooser_link(block, value, context) -> str:
    """Render a chosen page, document or snippet as a link, or as text when it has no URL.

    Page URLs are the page's normal URL here; rewriting internal links to
    Markdown export URLs is #14.
    """
    if value is None:
        return ""
    text = render_plain_text(block, str(value), context)
    url = getattr(value, "url", None)
    if not url:
        return text
    return f"[{_escape_link_text(text)}]({url})"


def render_image(block, value, context) -> str:
    """Render a chosen image as ``![alt](url)`` at its original size.

    Alt text follows Wagtail's own rendition rule: an ``ImageBlock``'s contextual
    alt text when the editor wrote one, else the image's default alt text
    (description, then title). A decorative ``ImageBlock`` image renders nothing —
    an agent has nothing to read from it, the reasoning behind D3 for the hero
    background. The URL is absolute when ``WAGTAILADMIN_BASE_URL`` is set, the
    rule every image URL in the output follows.
    """
    from wagtail.images.shortcuts import get_rendition_or_not_found

    if value is None or getattr(value, "decorative", False):
        return ""
    alt = getattr(value, "contextual_alt_text", None) or value.default_alt_text
    rendition = get_rendition_or_not_found(value, "original")
    return f"![{_escape_link_text(str(alt))}]({absolute_url(rendition.url)})"


def render_embed(block, value, context) -> str:
    """Render a media embed as a link, never calling the provider's oEmbed API.

    The link text is the embed's title when Wagtail has already cached the
    embed (a page render or preview fetched it); otherwise the URL is an
    autolink, as media embeds in rich text are. ``value.html`` is never
    touched: evaluating it fetches from the provider.
    """
    from wagtail.embeds.models import Embed

    url = getattr(value, "url", None)
    if not url:
        return ""
    title = Embed.objects.filter(url=url).exclude(title="").values_list("title", flat=True).first()
    if title:
        return f"[{_escape_link_text(title)}]({url})"
    return f"<{url}>"


def render_table(block, value, context) -> str:
    """Render a TableBlock as a GFM pipe table.

    The first row is the header when the editor chose one; otherwise the header
    row is empty, since GFM requires one. A first-column header has no GFM
    equivalent and renders as an ordinary cell. Cells are plain text unless the
    block uses the HTML renderer, in which case they convert like rich text.
    """
    if not value or not value.get("data"):
        return ""
    if block.is_html_renderer():
        rows = [
            [_table_cell(convert_html(_cell_text(c), block, context)) for c in r]
            for r in value["data"]
        ]
    else:
        rows = [
            [_table_cell(render_plain_text(block, c, context)) for c in r] for r in value["data"]
        ]
    header = rows.pop(0) if value.get("first_row_is_table_header") else None
    return _pipe_table(header, rows, value.get("table_caption"), block, context)


def render_typed_table(block, value, context) -> str:
    """Render a TypedTableBlock as a GFM pipe table, each cell through its column's renderer."""
    if value is None or not value.columns:
        return ""
    header = [
        _table_cell(render_plain_text(block, col["heading"], context)) for col in value.columns
    ]
    rows = [
        [
            _table_cell(render_block(col["block"], cell, context))
            for col, cell in zip(value.columns, row["values"], strict=False)
        ]
        for row in value.row_data
    ]
    return _pipe_table(header, rows, value.caption, block, context)


def _cell_text(cell) -> str:
    return "" if cell is None else str(cell)


def _table_cell(markdown: str) -> str:
    """Fit rendered Markdown into one pipe-table cell: pipes escaped, lines joined by ``<br>``."""
    lines = [line.strip() for line in markdown.splitlines()]
    return "<br>".join(line for line in lines if line).replace("|", "\\|")


def _pipe_table(header, rows, caption, block, context) -> str:
    """Lay out a GFM pipe table; ragged rows are padded to the widest row.

    The caption precedes the table on its own line, as markdownify places a
    ``<caption>``, so tables from both paths read the same.
    """
    width = max(len(header or []), *(len(row) for row in rows), 1)

    def line(cells):
        cells = list(cells) + [""] * (width - len(cells))
        return "| " + " | ".join(cells) + " |"

    lines = [line(header or []), line(["---"] * width), *(line(row) for row in rows)]
    table = "\n".join(lines)
    if caption:
        return f"{render_plain_text(block, caption, context)}\n\n{table}"
    return table


def _choice_labels(block) -> dict:
    """Map stored values to display labels, flattening grouped (optgroup) choices."""
    labels = {}
    for key, label in block.field.choices:
        if isinstance(label, list | tuple):
            labels.update(label)
        else:
            labels[key] = label
    return labels


def _escape_link_text(text: str) -> str:
    return text.replace("[", "\\[").replace("]", "\\]")


for block_class, renderer in (
    (wagtail_blocks.RichTextBlock, render_rich_text),
    (wagtail_blocks.CharBlock, render_plain_text),
    (wagtail_blocks.TextBlock, render_plain_text),
    (wagtail_blocks.RegexBlock, render_plain_text),
    (wagtail_blocks.URLBlock, render_url),
    (wagtail_blocks.EmailBlock, render_email),
    (wagtail_blocks.IntegerBlock, render_number),
    (wagtail_blocks.FloatBlock, render_number),
    (wagtail_blocks.DecimalBlock, render_number),
    (wagtail_blocks.BooleanBlock, render_boolean),
    (wagtail_blocks.DateBlock, render_temporal),
    (wagtail_blocks.TimeBlock, render_temporal),
    (wagtail_blocks.DateTimeBlock, render_temporal),
    (wagtail_blocks.ChoiceBlock, render_choice),
    (wagtail_blocks.MultipleChoiceBlock, render_multiple_choice),
    (wagtail_blocks.PageChooserBlock, render_chooser_link),
    (wagtail_blocks.StructBlock, render_struct),
    (wagtail_blocks.StreamBlock, render_stream),
    (wagtail_blocks.ListBlock, render_list),
    (TableBlock, render_table),
    (TypedTableBlock, render_typed_table),
):
    register_renderer(block_class)(renderer)

# Optional Wagtail apps: importing their blocks without the app installed fails.
# ImageBlock subclasses StructBlock, so it is registered explicitly: generic
# recursion would otherwise render its image, alt text and decorative flag as
# three fields.
if apps.is_installed("wagtail.images"):
    from wagtail.images.blocks import ImageBlock, ImageChooserBlock

    register_renderer(ImageChooserBlock)(render_image)
    register_renderer(ImageBlock)(render_image)

if apps.is_installed("wagtail.embeds"):
    from wagtail.embeds.blocks import EmbedBlock

    register_renderer(EmbedBlock)(render_embed)

if apps.is_installed("wagtail.documents"):
    from wagtail.documents.blocks import DocumentChooserBlock

    register_renderer(DocumentChooserBlock)(render_chooser_link)

if apps.is_installed("wagtail.snippets"):
    from wagtail.snippets.blocks import SnippetChooserBlock

    register_renderer(SnippetChooserBlock)(render_chooser_link)
