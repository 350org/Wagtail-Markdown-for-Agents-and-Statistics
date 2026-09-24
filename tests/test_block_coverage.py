"""Block coverage report (#18): which path each block definition takes to Markdown.

Each entry must name the renderer export would use, so the walk goes through
``registry.resolve`` with the names export passes, and follows children only
where the built-in container renderers do.
"""

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from sandbox.testapp.models import ContentPage, FormPage
from wagtail import blocks
from wagtail.contrib.typed_table_block.blocks import TypedTableBlock
from wagtail.images.blocks import ImageBlock
from wagtail.models import Site

from tests.test_container_defaults import DividerBlock, PromoBlock
from wagtail_markdown_agents.rendering import registry
from wagtail_markdown_agents.rendering.context import render_context
from wagtail_markdown_agents.rendering.coverage import (
    BUILT_IN,
    CUSTOM_TEMPLATE,
    DEFAULT_TEMPLATE,
    HINT_DYNAMIC_INCLUDE,
    HINT_ELEMENTS,
    HINT_EMBED,
    HINT_HIDDEN,
    HINT_INCLUDE_BLOCK,
    HINT_REQUEST,
    PROJECT,
    CoverageReport,
    _render_stream,
    _scan,
    build_report,
    compare,
    render_blocks,
    template_hints,
    walk_streams,
)
from wagtail_markdown_agents.rendering.registry import register_renderer


class QuoteBlock(blocks.StructBlock):
    quote = blocks.TextBlock()
    attribution = blocks.CharBlock()


class CardBlock(blocks.StructBlock):
    heading = blocks.CharBlock()
    background = blocks.ChoiceBlock(choices=[("dark", "Dark")])


class MissingTemplateBlock(blocks.StructBlock):
    text = blocks.CharBlock()

    class Meta:
        template = "testapp/blocks/no_such_template.html"


class SignupBlock(blocks.StructBlock):
    heading = blocks.CharBlock()

    class Meta:
        template = "testapp/blocks/coverage/signup_block.html"


class BodyBlock(blocks.StreamBlock):
    promo = PromoBlock()
    signup = SignupBlock()
    divider = DividerBlock()
    quote = QuoteBlock()
    cards = blocks.ListBlock(CardBlock())
    templated_list = blocks.ListBlock(
        blocks.CharBlock(), template="testapp/blocks/section_block.html"
    )
    image = ImageBlock()
    raw = blocks.RawHTMLBlock()
    stats = TypedTableBlock([("number", blocks.IntegerBlock()), ("label", blocks.CharBlock())])
    broken = MissingTemplateBlock()


@pytest.fixture
def project_renderers(monkeypatch):
    monkeypatch.setattr(registry, "_name_renderers", {})
    monkeypatch.setattr(registry, "_class_renderers", dict(registry._class_renderers))

    @register_renderer(QuoteBlock)
    def render_quote(block, value, context):
        return f"> {value['quote']}"

    @register_renderer(block_name="background")
    def drop_background(block, value, context):
        return ""

    return render_quote, drop_background


def entries(*streams):
    return {
        (e.name, e.block_class.rsplit(".", 1)[-1]): e
        for e in walk_streams([(f"test.Page.{n}", BodyBlock()) for n in streams or ["body"]])
    }


def run(*args):
    output = StringIO()
    call_command("agentmd_blocks", *args, stdout=output)
    return output.getvalue()


def run_failing(*args, match):
    output = StringIO()
    with pytest.raises(CommandError, match=match):
        call_command("agentmd_blocks", *args, stdout=output)
    return output.getvalue()


def snapshot(*streams):
    """A JSON snapshot of BodyBlock-shaped streams, as ``--json`` writes one."""
    report = CoverageReport(["test.Page"], {}, walk_streams(streams))
    return json.loads(json.dumps(report.as_json()))


def changes(before, *after):
    return compare(before, CoverageReport(["test.Page"], {}, walk_streams(after)))


def test_templated_blocks_are_custom_template_and_their_children_are_not_listed():
    found = entries()
    promo = found["promo", "PromoBlock"]
    assert promo.path == CUSTOM_TEMPLATE
    assert promo.template == "testapp/blocks/promo_block.html"
    assert found["divider", "DividerBlock"].path == CUSTOM_TEMPLATE
    templated_list = found["templated_list", "ListBlock"]
    assert templated_list.path == CUSTOM_TEMPLATE
    # The templates render these children, so their renderers are never reached.
    assert all(
        "promo >" not in loc and "templated_list >" not in loc
        for e in found.values()
        for loc in e.locations
    )


def test_plain_containers_recurse_with_the_names_export_passes():
    found = entries()
    assert found["quote", "QuoteBlock"].path == BUILT_IN
    assert found["quote", "TextBlock"].locations == ["test.Page.body > quote > quote"]
    assert found["cards", "ListBlock"].renderer.endswith("render_list")
    # ListBlock items are rendered without a name, as render_list does.
    assert found[None, "CardBlock"].locations == ["test.Page.body > cards > item"]
    assert found["background", "ChoiceBlock"].path == BUILT_IN


def test_typed_table_columns_are_walked_without_names():
    found = entries()
    assert found[None, "IntegerBlock"].locations == ["test.Page.body > stats > number"]
    assert found[None, "CharBlock"].locations == ["test.Page.body > stats > label"]


def test_specialised_renderers_are_leaves():
    found = entries()
    assert found["image", "ImageBlock"].renderer.endswith("render_image")
    assert not any(" > image > " in loc for e in found.values() for loc in e.locations)


def test_blocks_without_a_custom_template_fall_back_to_wagtail_html():
    raw = entries()["raw", "RawHTMLBlock"]
    assert raw.path == DEFAULT_TEMPLATE
    assert raw.template == ""


def test_a_missing_template_is_reported_as_custom_and_not_found():
    broken = entries()["broken", "MissingTemplateBlock"]
    assert broken.path == CUSTOM_TEMPLATE
    assert broken.template == "testapp/blocks/no_such_template.html (not found)"


def test_project_renderers_by_class_and_by_name(project_renderers):
    found = entries()
    quote = found["quote", "QuoteBlock"]
    assert quote.path == PROJECT
    assert quote.renderer == "tests.test_block_coverage.project_renderers.<locals>.render_quote"
    assert not quote.by_name
    # The project renderer is a leaf: its fields are no longer listed.
    assert ("attribution", "CharBlock") not in found
    background = found["background", "ChoiceBlock"]
    assert background.path == PROJECT and background.by_name


def test_entries_match_what_resolve_returns(project_renderers):
    body = BodyBlock()
    for name, child in body.child_blocks.items():
        entry = entries()[name, type(child).__name__]
        assert entry.renderer.endswith(registry.resolve(child, name).__qualname__)


def test_the_same_definition_merges_its_locations():
    promo = entries("body", "sidebar")["promo", "PromoBlock"]
    assert promo.locations == ["test.Page.body > promo", "test.Page.sidebar > promo"]


def test_report_covers_exportable_page_types_and_skips_form_pages():
    report = build_report()
    assert report.page_types == [
        "testapp.ArticlePage",
        "testapp.ContentPage",
        "testapp.MarkdownArticlePage",
    ]
    assert report.skipped == {"testapp.FormPage": "form page extraction is not supported"}


@override_settings(
    WAGTAIL_MARKDOWN_AGENTS={
        "PAGE_TYPES": ["testapp.ContentPage", "testapp.ArticlePage"],
        "PAGE_FIELDS": {"testapp.ContentPage": ["intro"]},
    }
)
def test_report_respects_page_types_and_page_fields():
    report = build_report()
    assert report.page_types == ["testapp.ArticlePage", "testapp.ContentPage"]
    locations = [loc for e in report.entries for loc in e.locations]
    assert locations and all(loc.startswith("testapp.ArticlePage.body") for loc in locations)


def test_command_groups_blocks_by_path_and_summarises():
    output = run()
    assert output.startswith("Block coverage for 3 page types: testapp.ArticlePage,")
    assert "Skipped testapp.FormPage: form page extraction is not supported" in output
    assert "\nWagtail default HTML (1)\n" in output
    assert "  raw_html  wagtail.blocks.field_block.RawHTMLBlock  -> no template\n" in output
    assert "    in testapp.ArticlePage.body > raw_html and 2 more\n" in output
    assert "-> render_rich_text\n" in output
    assert output.endswith("project=0 built_in=12 custom_template=0 default_html=1 with_hints=0\n")


def test_containers_the_walk_does_not_enter_record_their_fields(project_renderers):
    found = entries()
    assert found["promo", "PromoBlock"].fields == [
        "heading: wagtail.blocks.field_block.CharBlock",
        "text: wagtail.blocks.field_block.CharBlock",
    ]
    assert found["quote", "QuoteBlock"].fields == [
        "quote: wagtail.blocks.field_block.TextBlock",
        "attribution: wagtail.blocks.field_block.CharBlock",
    ]
    assert found["templated_list", "ListBlock"].fields == [
        "item: wagtail.blocks.field_block.CharBlock"
    ]
    # Children of recursed containers are entries of their own.
    assert found["cards", "ListBlock"].fields == []


def test_compare_is_empty_for_an_unchanged_definition():
    assert changes(snapshot(("test.Page.body", BodyBlock())), ("test.Page.body", BodyBlock())) == []


def test_compare_reports_added_and_removed_blocks():
    class Smaller(blocks.StreamBlock):
        promo = PromoBlock()

    class Larger(blocks.StreamBlock):
        promo = PromoBlock()
        raw = blocks.RawHTMLBlock()

    before = snapshot(("test.Page.body", Smaller()))
    assert changes(before, ("test.Page.body", Larger())) == [
        "added: raw wagtail.blocks.field_block.RawHTMLBlock (Wagtail default HTML)"
    ]
    assert changes(snapshot(("test.Page.body", Larger())), ("test.Page.body", Smaller())) == [
        "removed: raw wagtail.blocks.field_block.RawHTMLBlock"
    ]


def test_compare_reports_a_new_renderer_and_a_new_field_in_a_rendered_block(monkeypatch):
    def stream():
        class Body(blocks.StreamBlock):
            promo = PromoBlock()

        return ("test.Page.body", Body())

    before = snapshot(stream())
    monkeypatch.setattr(registry, "_class_renderers", dict(registry._class_renderers))
    register_renderer(PromoBlock)(lambda block, value, context: "")
    monkeypatch.setitem(PromoBlock.base_blocks, "cta", blocks.URLBlock())
    assert changes(before, stream()) == [
        "changed: promo tests.test_container_defaults.PromoBlock: "
        "path Custom template -> Project renderer",
        "changed: promo tests.test_container_defaults.PromoBlock: renderer "
        "wagtail_markdown_agents.rendering.registry.render_fallback -> "
        "tests.test_block_coverage.test_compare_reports_a_new_renderer_and_a_new_field_in_"
        "a_rendered_block.<locals>.<lambda>",
        "changed: promo tests.test_container_defaults.PromoBlock: "
        "field added: cta: wagtail.blocks.field_block.URLBlock",
    ]


def test_compare_reports_moved_blocks_and_page_types():
    lines = changes(snapshot(("test.Page.body", BodyBlock())), ("test.Page.sidebar", BodyBlock()))
    assert (
        "changed: raw wagtail.blocks.field_block.RawHTMLBlock: "
        "location added: test.Page.sidebar > raw"
    ) in lines
    assert (
        "changed: raw wagtail.blocks.field_block.RawHTMLBlock: "
        "location removed: test.Page.body > raw"
    ) in lines


def test_compare_rejects_something_that_is_not_a_snapshot():
    with pytest.raises(ValueError, match="not an agentmd_blocks snapshot"):
        compare({"blocks": []}, build_report())


def test_json_snapshot_round_trips_through_compare(tmp_path):
    data = json.loads(run("--json"))
    assert data["format"] == 1
    assert data["page_types"][0] == "testapp.ArticlePage"
    raw = next(block for block in data["blocks"] if block["name"] == "raw_html")
    assert raw["path"] == DEFAULT_TEMPLATE and len(raw["locations"]) == 3
    path = tmp_path / "blocks.json"
    path.write_text(json.dumps(data))
    assert run("--compare", str(path)) == f"Block coverage matches {path}.\n"


def test_compare_prints_changes_and_fails(tmp_path):
    data = json.loads(run("--json"))
    data["blocks"] = [block for block in data["blocks"] if block["name"] != "raw_html"]
    data["page_types"].append("testapp.RetiredPage")
    path = tmp_path / "blocks.json"
    path.write_text(json.dumps(data))
    output = run_failing("--compare", str(path), match="changed since .*: 2 differences")
    assert output.splitlines() == [
        "page type removed: testapp.RetiredPage",
        "added: raw_html wagtail.blocks.field_block.RawHTMLBlock (Wagtail default HTML)",
    ]


@pytest.mark.parametrize("content", [None, "not json", '{"format": 99}'])
def test_compare_fails_on_a_missing_or_invalid_snapshot(tmp_path, content):
    path = tmp_path / "blocks.json"
    if content is not None:
        path.write_text(content)
    with pytest.raises(CommandError, match="Cannot compare with"):
        run("--compare", str(path))


def test_json_and_compare_cannot_be_combined(tmp_path):
    with pytest.raises(CommandError, match="not allowed with argument"):
        run("--json", "--compare", str(tmp_path / "blocks.json"))


VIDEO = "testapp/blocks/coverage/_video.html"


def test_template_hints_follow_literal_includes_and_skip_comments():
    # The fixture's comments mention include_block, embed, request and <dialog>,
    # and its <script> is dropped by the converter: none of those are hints.
    assert template_hints("testapp/blocks/coverage/signup_block.html") == [
        HINT_REQUEST,
        HINT_HIDDEN,
        f"{HINT_EMBED} (in {VIDEO})",
        f"{HINT_ELEMENTS['noscript']} (in {VIDEO})",
        "{% include %} of testapp/blocks/coverage/_missing.html: "
        f"template not found (in {VIDEO})",
        HINT_DYNAMIC_INCLUDE,
    ]


def test_templates_without_problems_have_no_hints():
    # promo_block.html has a <script> and {% pageurl %}; both are fine offline.
    assert template_hints("testapp/blocks/promo_block.html") == []


@pytest.mark.parametrize(
    ("source", "hints"),
    [
        ("{% for c in value %}{% include_block c %}{% endfor %}", [HINT_INCLUDE_BLOCK]),
        ("{% embed value.url max_width=800 %}", [HINT_EMBED]),
        ("{% if request.user.is_authenticated %}Hi{% endif %}", [HINT_REQUEST]),
        ("<p>{{ request }}</p>", [HINT_REQUEST]),
        ("<p>We received your request.</p>", []),
        ("<dialog open>Bio</dialog>", [HINT_ELEMENTS["dialog"]]),
        ("<template><li>Row</li></template>", [HINT_ELEMENTS["template"]]),
        ("<div hidden>Thanks</div>", [HINT_HIDDEN]),
        ('<div class="msg hidden">Thanks</div>', [HINT_HIDDEN]),
        ('<div class="{% if x %}hidden{% endif %} msg">Thanks</div>', [HINT_HIDDEN]),
        ('<div style="display: none">Thanks</div>', [HINT_HIDDEN]),
        ('<span aria-hidden="true">&rarr;</span>', [HINT_HIDDEN]),
        ('<svg aria-hidden="true"></svg><img src="x" alt="" aria-hidden="true">', []),
        ('<div class="overflow-hidden md:hidden visually-hidden">Text</div>', []),
        ('<input type="hidden" name="a" value="b">', []),
        ("{# {% embed x %} #}{% comment %}<dialog>{% endcomment %}<!-- <noscript> -->", []),
    ],
)
def test_template_source_hints(source, hints):
    assert _scan(source)[0] == hints


def test_only_blocks_exported_through_a_template_get_hints(project_renderers):
    found = entries()
    assert found["templated_list", "ListBlock"].hints == [HINT_INCLUDE_BLOCK]
    assert HINT_REQUEST in found["signup", "SignupBlock"].hints
    assert found["promo", "PromoBlock"].hints == []
    assert found["broken", "MissingTemplateBlock"].hints == []
    register_renderer(SignupBlock)(lambda block, value, context: "")
    assert entries()["signup", "SignupBlock"].hints == []


def test_compare_reports_changed_hints():
    before = snapshot(("test.Page.body", BodyBlock()))
    signup = next(block for block in before["blocks"] if block["name"] == "signup")
    signup["hints"].remove(HINT_REQUEST)
    assert changes(before, ("test.Page.body", BodyBlock())) == [
        f"changed: signup tests.test_block_coverage.SignupBlock: hint added: {HINT_REQUEST}"
    ]


# --page: one published page, block by block, as export renders it.


@pytest.fixture
def home():
    return Site.objects.get(is_default_site=True).root_page


@pytest.fixture
def content_page(home):
    page = home.add_child(
        instance=ContentPage(
            title="Fossil Free Future",
            slug="fossil-free-future",
            intro="<p>An introduction.</p>",
            body=[
                ("paragraph", "<p>Published body.</p>"),
                (
                    "section",
                    {
                        "heading": "Why now",
                        "content": [
                            ("paragraph", "<p>Nested.</p>"),
                            ("callout", {"title": "", "body": "<p>Act.</p>"}),
                        ],
                    },
                ),
                ("bullet_points", ["Divest", "Organise"]),
                ("raw_html", "<p>Raw <b>HTML</b></p>"),
            ],
        )
    )
    page.save_revision().publish()
    return page


def rendered(page):
    return [(block.location, block.markdown or block.error) for block in render_blocks(page)]


@pytest.mark.django_db
def test_page_blocks_render_as_export_does(content_page):
    assert rendered(content_page) == [
        ("hero_copy", ""),
        ("intro", "An introduction."),
        ("body[0] paragraph", "Published body."),
        ("body[1] section > heading", "Why now"),
        ("body[1] section > content[0] paragraph", "Nested."),
        ("body[1] section > content[1] callout > title", ""),
        ("body[1] section > content[1] callout > body", "Act."),
        # A list of simple items stays whole, with export's bullets.
        ("body[2] bullet_points", "- Divest\n- Organise"),
        ("body[3] raw_html", "Raw **HTML**"),
    ]


@pytest.mark.django_db
def test_page_blocks_are_the_published_revision(content_page):
    content_page.body = [("paragraph", "<p>Draft only.</p>")]
    content_page.save_revision()
    assert ("body[0] paragraph", "Published body.") in rendered(content_page)


@pytest.mark.django_db
def test_a_failing_block_is_reported_and_the_rest_still_render(content_page, monkeypatch):
    monkeypatch.setattr(registry, "_name_renderers", {})

    @register_renderer(block_name="heading")
    def broken(block, value, context):
        raise RuntimeError("no heading today")

    blocks_ = rendered(content_page)
    assert ("body[1] section > heading", "RuntimeError: no heading today") in blocks_
    assert blocks_[-1] == ("body[3] raw_html", "Raw **HTML**")
    output = run_failing(
        "--page", str(content_page.pk), match="1 blocks on page .* failed to render"
    )
    assert "\nbody[1] section > heading  -> " in output
    assert "  error: RuntimeError: no heading today\n" in output
    assert "blocks=9 empty=2 failed=1" in output


def test_templated_blocks_show_hints_and_template_errors(db, home):
    value = BodyBlock().to_python(
        [
            {"type": "promo", "value": {"heading": "Join", "text": "Now"}},
            {"type": "signup", "value": {"heading": "Sign up"}},
        ]
    )
    results = []
    _render_stream(value, "body", render_context(home.specific), results)
    promo, signup = results
    assert promo.entry.path == CUSTOM_TEMPLATE and promo.entry.hints == []
    assert promo.markdown.startswith("## Join\n\nNow")
    assert signup.location == "body[1] signup"
    assert HINT_REQUEST in signup.entry.hints
    # The hint's missing include is a real failure once the block renders.
    assert signup.error == "TemplateDoesNotExist: testapp/blocks/coverage/_missing.html"


def test_the_template_chosen_for_the_value_is_reported(db, home):
    class PickBlock(blocks.StructBlock):
        text = blocks.CharBlock()

        def get_template(self, value=None, context=None):
            if value and value.get("text") == "section":
                return "testapp/blocks/section_block.html"
            return "testapp/blocks/promo_block.html"

    class Stream(blocks.StreamBlock):
        pick = PickBlock()

    value = Stream().to_python([{"type": "pick", "value": {"text": "section"}}])
    results = []
    _render_stream(value, "body", render_context(home.specific), results)
    assert results[0].entry.template == "testapp/blocks/section_block.html"
    assert results[0].entry.hints == [HINT_INCLUDE_BLOCK]


@pytest.mark.django_db
def test_page_command_prints_each_block(content_page):
    output = run("--page", str(content_page.pk))
    assert output.startswith(
        f'Page {content_page.pk} "Fossil Free Future" (testapp.ContentPage)\n'
        "Block output is shown before page hooks and link rewriting.\n"
    )
    assert "\nhero_copy  -> render_rich_text\n  (empty)\n" in output
    assert "\nbody[2] bullet_points  -> render_list\n  | - Divest\n  | - Organise\n" in output
    assert "\nbody[3] raw_html  -> no template\n  | Raw **HTML**\n" in output
    assert output.endswith("blocks=9 empty=2 failed=0\n")


@pytest.mark.django_db
def test_page_command_notes_pages_that_are_not_exported(content_page, settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"PAGE_TYPES": ["testapp.ArticlePage"]}
    output = run("--page", str(content_page.pk))
    assert "Not exported under the current policy; rendered for inspection only.\n" in output


@pytest.mark.django_db
def test_page_command_rejects_missing_unpublished_and_unsupported_pages(home, content_page):
    with pytest.raises(CommandError, match="Page 999999 does not exist"):
        run("--page", "999999")
    content_page.unpublish()
    with pytest.raises(CommandError, match="the page is not live"):
        run("--page", str(content_page.pk))
    form = home.add_child(instance=FormPage(title="Contact", slug="contact"))
    form.save_revision().publish()
    with pytest.raises(CommandError, match="form page extraction is not supported"):
        run("--page", str(form.pk))


def test_page_cannot_be_combined_with_json():
    with pytest.raises(CommandError, match="not allowed with argument"):
        run("--page", "1", "--json")
