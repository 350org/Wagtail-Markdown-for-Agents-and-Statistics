"""Golden-file snapshots for the built-in renderers and frontmatter (#15).

Each golden file is the committed, reviewed output for one fixture. A change
in output fails the test with a diff; run ``UPDATE_GOLDEN=1 pytest`` to accept
it deliberately, then review the file in the pull request. The judgement
calls on ledger #84 (angle brackets kept, media embeds as links, heading
levels, decorative images omitted, table layout, embed titles from cache,
frontmatter precedence) are pinned here.

Containers are covered by test_container_defaults.py; full-page goldens follow
#78, and 350.org's blocks follow #65.
"""

import datetime
import difflib
import os
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.files.base import ContentFile
from sandbox.testapp.models import ArticlePage
from wagtail import blocks
from wagtail.contrib.table_block.blocks import TableBlock
from wagtail.contrib.typed_table_block.blocks import TypedTableBlock
from wagtail.documents import get_document_model
from wagtail.documents.blocks import DocumentChooserBlock
from wagtail.embeds.blocks import EmbedBlock
from wagtail.embeds.models import Embed
from wagtail.images import get_image_model
from wagtail.images.blocks import ImageBlock, ImageChooserBlock
from wagtail.images.tests.utils import get_test_image_file
from wagtail.models import Page, Site

from wagtail_markdown_agents.models import PageAgentSettings
from wagtail_markdown_agents.rendering import frontmatter
from wagtail_markdown_agents.rendering.blocks import render_stream
from wagtail_markdown_agents.rendering.frontmatter import build, serialise

GOLDEN_DIR = Path(__file__).parent / "golden"
UTC = datetime.UTC
VIDEO = "https://www.youtube.com/watch?v=abc123"
VIDEO_UNCACHED = "https://vimeo.com/987654"


def assert_matches_golden(name: str, output: str) -> None:
    path = GOLDEN_DIR / name
    text = output.rstrip("\n") + "\n"
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(text)
        return
    expected = path.read_text() if path.exists() else ""
    if text != expected:
        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(True),
                text.splitlines(True),
                f"{name} (golden)",
                f"{name} (now)",
            )
        )
        pytest.fail(f"Output differs from {path.name}; UPDATE_GOLDEN=1 accepts it.\n{diff}")


class DividerBlock(blocks.StaticBlock):
    class Meta:
        template = "testapp/blocks/divider_block.html"


class GoldenBlock(blocks.StreamBlock):
    """Every leaf built-in, plus the two fallback cases (raw HTML and a static template)."""

    heading = blocks.CharBlock()
    paragraph = blocks.RichTextBlock()
    char = blocks.CharBlock()
    text = blocks.TextBlock()
    url = blocks.URLBlock()
    email = blocks.EmailBlock()
    integer = blocks.IntegerBlock()
    float_ = blocks.FloatBlock()
    decimal = blocks.DecimalBlock()
    boolean = blocks.BooleanBlock(required=False, label="Accepts RSVPs")
    date = blocks.DateBlock()
    time = blocks.TimeBlock()
    datetime_ = blocks.DateTimeBlock()
    choice = blocks.ChoiceBlock(choices=[("dark", "Dark background"), ("light", "Light")])
    choices = blocks.MultipleChoiceBlock(choices=[("a", "Apples"), ("b", "Bananas")])
    page = blocks.PageChooserBlock()
    document = DocumentChooserBlock()
    image = ImageChooserBlock()
    image_block = ImageBlock()
    embed = EmbedBlock()
    table = TableBlock()
    typed_table = TypedTableBlock(
        [("text", blocks.CharBlock()), ("number", blocks.IntegerBlock(required=False))]
    )
    bullets = blocks.ListBlock(blocks.CharBlock())
    pages = blocks.ListBlock(blocks.PageChooserBlock())
    raw_html = blocks.RawHTMLBlock()
    divider = DividerBlock()


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.WAGTAILDOCS_SERVE_METHOD = "direct"  # a deterministic URL, without the document pk


@pytest.fixture
def article(db, media):
    home = Site.objects.get(is_default_site=True).root_page
    page = home.add_child(
        instance=ArticlePage(
            title="Fossil Free Future",
            slug="fossil-free-future",
            search_description="Why we campaign for a fossil-free future.",
            first_published_at=datetime.datetime(2026, 9, 1, 8, 30, tzinfo=UTC),
            last_published_at=datetime.datetime(2026, 9, 10, 9, 0, tzinfo=UTC),
        )
    )
    page.tags.add("Climate", "Divest")
    page.topics.add("Divest", "Energy")
    page.save()
    home.add_child(instance=Page(title="Get involved", slug="get-involved"))
    return page


@pytest.fixture
def stream_value(article):
    image = get_image_model().objects.create(title="Rally", file=get_test_image_file())
    document = get_document_model().objects.create(
        title="Annual report", file=ContentFile(b"%PDF-1.4", name="report.pdf")
    )
    Embed.objects.create(url=VIDEO, hash="golden", type="video", title="Rally [live]", html="<x>")
    get_involved = Page.objects.get(slug="get-involved")
    block = GoldenBlock()
    return block, block.to_python(
        [
            {"type": "heading", "value": "Keep it in the ground"},
            {
                "type": "paragraph",
                "value": (
                    "<h2>Why now</h2>"
                    "<p>Join the <b>global</b> <i>movement</i> at "
                    '<a href="https://350.org/">350</a>. Caf&eacute; &amp; &lt;tag&gt; '
                    "— “quotes” 🌍</p>"
                    "<ul><li>one</li><li>two</li></ul><ol><li>a</li><li>b</li></ol>"
                    '<pre><code class="language-python">def f():\n    return 1</code></pre>'
                    '<script>alert("x")</script><style>p{color:red}</style>'
                    f'<embed embedtype="media" url="{VIDEO_UNCACHED}"/>'
                    f'<embed embedtype="image" id="{image.pk}" format="fullwidth" alt="A rally"/>'
                    f'<a linktype="page" id="{get_involved.pk}">Get involved</a>'
                ),
            },
            {"type": "char", "value": "5 * 3 = 15 in snake_case"},
            {"type": "text", "value": "one\ntwo\n\nthree"},
            {"type": "url", "value": "https://350.org/"},
            {"type": "email", "value": "hello@350.org"},
            {"type": "integer", "value": 0},
            {"type": "float_", "value": 1.5},
            {"type": "decimal", "value": Decimal("1.50")},
            {"type": "boolean", "value": True},
            {"type": "boolean", "value": False},
            {"type": "date", "value": "2026-09-11"},
            {"type": "time", "value": "09:05:00"},
            {"type": "datetime_", "value": "2026-09-11T15:30:00+01:00"},
            {"type": "choice", "value": "dark"},
            {"type": "choices", "value": ["b", "a"]},
            {"type": "page", "value": get_involved.pk},
            {"type": "document", "value": document.pk},
            {"type": "image", "value": image.pk},
            {
                "type": "image_block",
                "value": {
                    "image": image.pk,
                    "decorative": False,
                    "alt_text": "Marchers in Nairobi",
                },
            },
            {
                "type": "image_block",
                "value": {"image": image.pk, "decorative": True, "alt_text": ""},
            },
            {"type": "embed", "value": VIDEO},
            {"type": "embed", "value": VIDEO_UNCACHED},
            {
                "type": "table",
                "value": {
                    "table_caption": "Targets by country",
                    "first_row_is_table_header": True,
                    "first_col_is_header": False,
                    "data": [
                        ["Country", "Target | 2030"],
                        ["Kenya", "0"],
                        ["Peru", None],
                        ["line\nbreak", ""],
                    ],
                },
            },
            {
                "type": "typed_table",
                "value": {
                    "caption": "",
                    "columns": [
                        {"type": "text", "heading": "Country"},
                        {"type": "number", "heading": "Target"},
                    ],
                    "rows": [{"values": ["Kenya", 0]}, {"values": ["Peru", None]}],
                },
            },
            {"type": "bullets", "value": ["one", "two * three", ""]},
            {"type": "pages", "value": [get_involved.pk, None]},
            {"type": "raw_html", "value": "<p>Raw <em>HTML</em></p><script>x()</script>"},
            {"type": "divider", "value": None},
        ]
    )


def test_built_in_renderers_golden(stream_value, monkeypatch):
    block, value = stream_value

    output = render_stream(block, value, {})

    assert_matches_golden("built_ins.md", output)


def test_frontmatter_golden(article, monkeypatch):
    monkeypatch.setattr(
        frontmatter.timezone, "now", lambda: datetime.datetime(2026, 9, 11, 16, 0, tzinfo=UTC)
    )
    PageAgentSettings.objects.create(
        page=article,
        extra_frontmatter={
            "campaign": "fossil-free",
            "excerpt": "Editor summary: keep it in the ground",
            "priority": 0,
            "featured": False,
            "notes": "line one\nline two",
            "looks_like_bool": "yes",
            "looks_like_date": "2026-09-11",
            "empty": [],
            "id": "spoofed",
        },
    )

    output = serialise(build(article))

    # The pk depends on test order; everything else is deterministic.
    assert_matches_golden("frontmatter.md", output.replace(f"id: {article.pk}\n", "id: <pk>\n"))
