"""Built-in renderers for scalar, choice and chooser blocks (#85).

Guards against the wp-mfa-plugin #21 failure class (ledger #84): a value type
the code does not explicitly handle must never leak into the output as the
text ``None`` or an object repr, whether rendered alone or as a list item.
"""

import datetime
import re
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile
from wagtail import blocks
from wagtail.contrib.table_block.blocks import TableBlock
from wagtail.contrib.typed_table_block.blocks import TypedTableBlock
from wagtail.documents import get_document_model
from wagtail.documents.blocks import DocumentChooserBlock
from wagtail.embeds.blocks import EmbedBlock, EmbedValue
from wagtail.images import get_image_model
from wagtail.images.blocks import ImageBlock, ImageChooserBlock
from wagtail.images.tests.utils import get_test_image_file
from wagtail.models import Page, Site
from wagtail.snippets.blocks import SnippetChooserBlock

from wagtail_markdown_agents.rendering import blocks as built_ins
from wagtail_markdown_agents.rendering import registry
from wagtail_markdown_agents.rendering.blocks import render_block
from wagtail_markdown_agents.rendering.registry import resolve

CHOICES = [("dark", "Dark background"), ("light", "Light")]
GROUPED_CHOICES = [("Warm", [("red", "Red"), ("orange", "Orange")]), ("blue", "Blue")]
UTC_PLUS_ONE = datetime.timezone(datetime.timedelta(hours=1))


class DividerBlock(blocks.StaticBlock):
    class Meta:
        template = "testapp/blocks/divider_block.html"


class EventBlock(blocks.StructBlock):
    is_featured = blocks.BooleanBlock(required=False)
    rsvp = blocks.BooleanBlock(required=False, label="Accepts RSVPs")


@pytest.fixture
def page(db):
    home = Site.objects.get(is_default_site=True).root_page
    return home.add_child(instance=Page(title="Get involved", slug="get-involved"))


@pytest.fixture
def document(db, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return get_document_model().objects.create(
        title="Annual report", file=ContentFile(b"%PDF-1.4", name="report.pdf")
    )


@pytest.fixture
def image(db, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return get_image_model().objects.create(title="Rally", file=get_test_image_file())


def render(block, value):
    return render_block(block, value, {})


# Registration


@pytest.mark.parametrize(
    ("block", "renderer"),
    [
        (blocks.URLBlock(), "render_url"),
        (blocks.EmailBlock(), "render_email"),
        (blocks.RegexBlock(regex=r".*"), "render_plain_text"),
        (blocks.IntegerBlock(), "render_number"),
        (blocks.FloatBlock(), "render_number"),
        (blocks.DecimalBlock(), "render_number"),
        (blocks.BooleanBlock(), "render_boolean"),
        (blocks.DateBlock(), "render_temporal"),
        (blocks.TimeBlock(), "render_temporal"),
        (blocks.DateTimeBlock(), "render_temporal"),
        (blocks.ChoiceBlock(choices=CHOICES), "render_choice"),
        (blocks.MultipleChoiceBlock(choices=CHOICES), "render_multiple_choice"),
        (blocks.PageChooserBlock(), "render_chooser_link"),
        (DocumentChooserBlock(), "render_chooser_link"),
        (SnippetChooserBlock("wagtailcore.Site"), "render_chooser_link"),
        (blocks.ListBlock(blocks.CharBlock()), "render_list"),
    ],
    ids=lambda x: type(x).__name__ if isinstance(x, blocks.Block) else x,
)
def test_built_ins_are_registered_at_startup(block, renderer):
    assert resolve(block) is getattr(built_ins, renderer)


def test_struct_and_stream_blocks_still_reach_the_fallback():
    # D12 pending on #63: a project's templated StructBlock must reach its template.
    class CardBlock(blocks.StructBlock):
        heading = blocks.CharBlock()

    class BodyBlock(blocks.StreamBlock):
        card = CardBlock()

    assert resolve(CardBlock()) is registry.render_fallback
    assert resolve(BodyBlock()) is registry.render_fallback


# Empty values render as nothing


@pytest.mark.parametrize(
    ("block", "value"),
    [
        (blocks.URLBlock(required=False), None),
        (blocks.URLBlock(required=False), ""),
        (blocks.EmailBlock(required=False), None),
        (blocks.RegexBlock(regex=r".*", required=False), None),
        (blocks.IntegerBlock(required=False), None),
        (blocks.FloatBlock(required=False), None),
        (blocks.DecimalBlock(required=False), None),
        (blocks.BooleanBlock(required=False), None),
        (blocks.DateBlock(required=False), None),
        (blocks.TimeBlock(required=False), None),
        (blocks.DateTimeBlock(required=False), None),
        (blocks.ChoiceBlock(choices=CHOICES, required=False), None),
        (blocks.ChoiceBlock(choices=CHOICES, required=False), ""),
        (blocks.MultipleChoiceBlock(choices=CHOICES, required=False), []),
        (blocks.PageChooserBlock(required=False), None),
        (DocumentChooserBlock(required=False), None),
        (SnippetChooserBlock("wagtailcore.Site", required=False), None),
    ],
    ids=lambda x: type(x).__name__ if isinstance(x, blocks.Block) else repr(x),
)
def test_empty_values_render_as_nothing(block, value):
    assert render(block, value) == ""


# Numbers, dates and times


@pytest.mark.parametrize(
    ("block", "value", "expected"),
    [
        (blocks.IntegerBlock(), 0, "0"),
        (blocks.IntegerBlock(), 350, "350"),
        (blocks.FloatBlock(), 0.0, "0.0"),
        (blocks.FloatBlock(), 1.5, "1.5"),
        (blocks.DecimalBlock(), Decimal("0"), "0"),
        (blocks.DecimalBlock(), Decimal("1.50"), "1.50"),
    ],
)
def test_numbers_keep_zero_and_their_precision(block, value, expected):
    assert render(block, value) == expected


@pytest.mark.parametrize(
    ("block", "value", "expected"),
    [
        (blocks.DateBlock(), datetime.date(2026, 9, 11), "2026-09-11"),
        (blocks.TimeBlock(), datetime.time(9, 5), "09:05:00"),
        (
            blocks.DateTimeBlock(),
            datetime.datetime(2026, 9, 11, 15, 30, tzinfo=UTC_PLUS_ONE),
            "2026-09-11T15:30:00+01:00",
        ),
    ],
)
def test_dates_and_times_render_as_iso_8601(block, value, expected):
    assert render(block, value) == expected


# Booleans (decided on #85: label or "Yes" when true, nothing when false)


def test_true_boolean_renders_its_label():
    block = EventBlock().child_blocks["rsvp"]

    assert render(block, True) == "Accepts RSVPs"


def test_true_boolean_uses_the_label_derived_from_its_name():
    block = EventBlock().child_blocks["is_featured"]

    assert render(block, True) == "Is featured"


def test_true_unlabelled_boolean_renders_yes():
    assert render(blocks.BooleanBlock(), True) == "Yes"


def test_false_boolean_renders_nothing():
    assert render(blocks.BooleanBlock(required=False, label="Accepts RSVPs"), False) == ""


# Choices


def test_choice_renders_its_display_label():
    assert render(blocks.ChoiceBlock(choices=CHOICES), "dark") == "Dark background"


def test_grouped_choice_renders_its_display_label():
    assert render(blocks.ChoiceBlock(choices=GROUPED_CHOICES), "orange") == "Orange"


def test_choice_value_missing_from_choices_renders_the_stored_value():
    assert render(blocks.ChoiceBlock(choices=CHOICES), "purple") == "purple"


def test_multiple_choice_renders_labels_in_order():
    block = blocks.MultipleChoiceBlock(choices=[("a", "Apples"), ("b", "Bananas")])

    assert render(block, ["b", "a"]) == "Bananas, Apples"


# Text-like values


def test_url_renders_as_an_autolink():
    assert render(blocks.URLBlock(), "https://350.org/") == "<https://350.org/>"


def test_email_renders_as_an_autolink():
    assert render(blocks.EmailBlock(), "hello@350.org") == "<hello@350.org>"


def test_regex_block_text_is_escaped_like_plain_text():
    assert render(blocks.RegexBlock(regex=r".*"), "5 * 3") == "5 \\* 3"


# Choosers


def test_page_chooser_renders_a_link(page):
    assert render(blocks.PageChooserBlock(), page) == "[Get involved](/get-involved/)"


def test_document_chooser_renders_a_link(document):
    assert render(DocumentChooserBlock(), document) == f"[Annual report]({document.url})"


def test_snippet_with_a_url_renders_a_link(page):
    assert render(SnippetChooserBlock("wagtailcore.Page"), page) == (
        "[Get involved](/get-involved/)"
    )


@pytest.mark.django_db
def test_snippet_without_a_url_renders_its_text():
    site = Site.objects.get(is_default_site=True)

    assert render(SnippetChooserBlock("wagtailcore.Site"), site) == str(site)


def test_link_text_brackets_are_escaped(page):
    page.title = "Get [more] involved"

    assert render(blocks.PageChooserBlock(), page) == "[Get \\[more\\] involved](/get-involved/)"


# Template fallback with no value


def test_unregistered_block_without_a_value_renders_nothing():
    assert render(EmbedBlock(required=False), None) == ""


def test_static_block_template_still_renders():
    assert render(DividerBlock(), None) == "---"


# Guard: never "None", never an object repr — alone or as a list item

NONE_OR_REPR = re.compile(r"\bNone\b|<[A-Za-z_][\w.]*: [^>]*>|<[\w.]+ object at 0x")


def guard_cases(page, document, image):
    site = Site.objects.get(is_default_site=True)
    typed_table = TypedTableBlock([("text", blocks.CharBlock(required=False))], required=False)
    return [
        (blocks.CharBlock(required=False), ["text", "", None]),
        (blocks.TextBlock(required=False), ["text", "", None]),
        (blocks.RichTextBlock(required=False), ["<p>text</p>", ""]),
        (blocks.URLBlock(required=False), ["https://350.org/", "", None]),
        (blocks.EmailBlock(required=False), ["hello@350.org", None]),
        (blocks.RegexBlock(regex=r".*", required=False), ["123", None]),
        (blocks.IntegerBlock(required=False), [0, 7, None]),
        (blocks.FloatBlock(required=False), [0.0, None]),
        (blocks.DecimalBlock(required=False), [Decimal("1.50"), None]),
        (blocks.BooleanBlock(required=False), [True, False, None]),
        (blocks.DateBlock(required=False), [datetime.date(2026, 9, 11), None]),
        (blocks.TimeBlock(required=False), [datetime.time(9, 5), None]),
        (blocks.DateTimeBlock(required=False), [datetime.datetime(2026, 9, 11, 9, 5), None]),
        (blocks.ChoiceBlock(choices=CHOICES, required=False), ["dark", "", None]),
        (blocks.MultipleChoiceBlock(choices=CHOICES, required=False), [["dark"], []]),
        (blocks.PageChooserBlock(required=False), [page, None]),
        (DocumentChooserBlock(required=False), [document, None]),
        (SnippetChooserBlock("wagtailcore.Site", required=False), [site, None]),
        (ImageChooserBlock(required=False), [image, None]),
        (ImageBlock(required=False), [ImageBlock().to_python(image.pk), None]),
        (EmbedBlock(required=False), [EmbedValue("https://www.youtube.com/watch?v=abc"), None]),
        (TableBlock(required=False), [{"data": [["a", None], [None, "0"]]}, {"data": []}, None]),
        (
            typed_table,
            [
                typed_table.to_python(
                    {
                        "columns": [{"type": "text", "heading": "H"}],
                        "rows": [{"values": [None]}],
                        "caption": "",
                    }
                ),
                typed_table.to_python(None),
                None,
            ],
        ),
        (DividerBlock(), [None]),
    ]


def test_no_block_renders_none_or_an_object_repr(page, document, image):
    for block, values in guard_cases(page, document, image):
        for value in values:
            output = render(block, value)
            assert not NONE_OR_REPR.search(output), (type(block).__name__, value, output)


def test_no_list_item_renders_none_or_an_object_repr(page, document, image):
    # Through a real ListBlock, so this covers what a page actually renders.
    for block, values in guard_cases(page, document, image):
        output = render(blocks.ListBlock(block), values)
        assert not NONE_OR_REPR.search(output), (type(block).__name__, values, output)
