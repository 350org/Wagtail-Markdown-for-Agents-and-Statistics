"""Frontmatter builder and YAML serialisation (#13).

Guards the wp-mfa-plugin #20 / #21 failure classes (ledger #84): no silent
key collisions between sources, and one normaliser for scalars and list
items that raises on anything it does not handle.
"""

import datetime
import decimal
import logging
import uuid

import pytest
import yaml
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy
from sandbox.testapp.models import ArticlePage
from taggit.models import Tag
from wagtail import hooks
from wagtail.models import Locale, Page, Site

from wagtail_markdown_agents.models import PageAgentSettings
from wagtail_markdown_agents.rendering import frontmatter
from wagtail_markdown_agents.rendering.frontmatter import (
    FRONTMATTER_HOOK,
    TAGS_HOOK,
    FrontmatterValueError,
    build,
    normalise,
    serialise,
)

UTC = datetime.UTC
PLUS_ONE = datetime.timezone(datetime.timedelta(hours=1))
NOW = datetime.datetime(2026, 9, 11, 16, 0, tzinfo=UTC)


@pytest.fixture
def home(db):
    return Site.objects.get(is_default_site=True).root_page


@pytest.fixture
def article(home):
    return home.add_child(
        instance=ArticlePage(
            title="Fossil Free Future",
            slug="fossil-free-future",
            search_description="Why we campaign for a fossil-free future.",
            first_published_at=datetime.datetime(2026, 9, 1, 8, 30, tzinfo=UTC),
            last_published_at=datetime.datetime(2026, 9, 10, 9, 0, tzinfo=PLUS_ONE),
        )
    )


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    monkeypatch.setattr(frontmatter.timezone, "now", lambda: NOW)


@pytest.fixture
def hook(monkeypatch):
    """Register a hook for this test only."""

    def register(name, fn):
        monkeypatch.setitem(hooks._hooks, name, [*hooks._hooks.get(name, []), (fn, 0)])
        return fn

    return register


def load(text):
    assert text.startswith("---\n") and text.endswith("---\n")
    return yaml.safe_load(text[4:-4])


# Built-in fields


def test_built_in_fields_in_order(article):
    assert build(article) == {
        "title": "Fossil Free Future",
        "date": "2026-09-01T08:30:00Z",
        "modified": "2026-09-10T08:00:00Z",
        "permalink": "http://localhost/fossil-free-future/",
        "type": "testapp.ArticlePage",
        "status": "published",
        "excerpt": "Why we campaign for a fossil-free future.",
        "id": article.pk,
        "timestamp": "2026-09-11T16:00:00Z",
    }


def test_empty_built_ins_are_omitted_not_null(home):
    page = home.add_child(instance=Page(title="Bare", slug="bare"))

    output = build(page)

    assert "excerpt" not in output
    assert "tags" not in output
    assert "date" not in output
    assert "null" not in serialise(output)


def test_base_page_instance_is_resolved_to_its_specific_type(article):
    assert build(Page.objects.get(pk=article.pk))["type"] == "testapp.ArticlePage"


def test_hierarchy_and_owner_are_off_by_default(article):
    output = build(article)

    assert not {"parent", "ancestors", "children", "owner"} & set(output)


# Tags


def test_tags_are_flat_and_deduplicated_across_tag_fields(article):
    article.tags.add("Climate", "Divest")
    article.topics.add("Divest", "Energy")
    article.save()

    tags = build(article)["tags"]

    assert sorted(tags) == ["Climate", "Divest", "Energy"]
    assert len(tags) == 3


def test_tags_hook_runs_before_the_frontmatter_hook(article, hook):
    article.tags.add("Climate")
    article.save()
    seen = {}
    hook(TAGS_HOOK, lambda tags, page, context: tags.append("Hooked"))
    hook(FRONTMATTER_HOOK, lambda fm, page, context: seen.update(fm))

    output = build(article)

    assert output["tags"] == ["Climate", "Hooked"]
    assert seen["tags"] == ["Climate", "Hooked"]


# extra_frontmatter and the hook: precedence


def test_extra_frontmatter_adds_and_overrides_non_identity_keys(article):
    PageAgentSettings.objects.create(
        page=article, extra_frontmatter={"excerpt": "Editor summary", "campaign": "fossil-free"}
    )

    output = build(article)

    assert output["excerpt"] == "Editor summary"
    assert output["campaign"] == "fossil-free"


def test_editor_json_order_is_database_independent(article):
    PageAgentSettings.objects.create(
        page=article,
        extra_frontmatter={
            "zebra": {"z": 1, "a": 2},
            "alpha": [{"z": 3, "a": 4}, {"b": 5}],
        },
    )
    output = build(article)
    assert list(output)[-2:] == ["alpha", "zebra"]
    assert list(output["zebra"]) == ["a", "z"]
    assert list(output["alpha"][0]) == ["a", "z"]
    assert output["alpha"] == [{"a": 4, "z": 3}, {"b": 5}]


@pytest.mark.parametrize("key", ["id", "type", "permalink", "status", "timestamp"])
def test_extra_frontmatter_cannot_override_identity_keys_and_the_clash_is_logged(
    article, caplog, key
):
    PageAgentSettings.objects.create(page=article, extra_frontmatter={key: "spoofed"})
    expected = build(article)[key]

    with caplog.at_level(logging.WARNING, logger="wagtail_markdown_agents"):
        PageAgentSettings.objects.filter(page=article).update(extra_frontmatter={key: "spoofed"})
        output = build(article)

    assert output[key] == expected
    assert output[key] != "spoofed"
    assert any(
        key in record.getMessage() and str(article.pk) in record.getMessage()
        for record in caplog.records
    )


def test_hook_runs_last_and_overrides_every_other_source(article, hook):
    PageAgentSettings.objects.create(page=article, extra_frontmatter={"campaign": "editor"})

    def customise(fm, page, context):
        assert fm["campaign"] == "editor"  # extra_frontmatter has already been merged
        fm["campaign"] = "hook"
        fm["id"] = f"page-{page.pk}"

    hook(FRONTMATTER_HOOK, customise)

    output = build(article)

    assert output["campaign"] == "hook"
    assert output["id"] == f"page-{article.pk}"


def test_hook_receives_the_render_context(article, hook):
    seen = {}
    hook(FRONTMATTER_HOOK, lambda fm, page, context: seen.update(context))

    build(article)

    assert seen["page"] == article
    assert seen["site"] == Site.objects.get(is_default_site=True)


# Hierarchy and owner


def test_hierarchy_lists_only_eligible_relatives(article, home, settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"INCLUDE_HIERARCHY": True}
    article.add_child(instance=Page(title="Visible", slug="visible"))
    hidden = article.add_child(instance=Page(title="Hidden", slug="hidden"))
    draft = article.add_child(instance=Page(title="Draft", slug="draft", live=False))

    output = build(article, is_eligible=lambda page: page.pk not in {hidden.pk, draft.pk})

    assert output["parent"] == {"title": home.title, "permalink": "http://localhost/"}
    assert output["ancestors"] == [{"title": home.title, "permalink": "http://localhost/"}]
    assert output["children"] == [
        {"title": "Visible", "permalink": "http://localhost/fossil-free-future/visible/"}
    ]
    assert "Hidden" not in serialise(output)


def test_ineligible_parent_is_omitted(article, settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"INCLUDE_HIERARCHY": True}

    output = build(article, is_eligible=lambda page: False)

    assert "parent" not in output
    assert "ancestors" not in output
    assert "children" not in output


def test_hierarchy_uses_the_export_policy_by_default(article, home, settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"INCLUDE_HIERARCHY": True}
    article.add_child(instance=Page(title="Visible", slug="visible"))
    excluded = article.add_child(instance=Page(title="Excluded", slug="excluded"))
    PageAgentSettings.objects.create(page=excluded, excluded=True)
    article.add_child(instance=Page(title="Draft", slug="draft", live=False))

    output = build(article)

    assert output["parent"] == {"title": home.title, "permalink": "http://localhost/"}
    assert [c["title"] for c in output["children"]] == ["Visible"]


def test_owner_is_the_full_name(article, settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"INCLUDE_OWNER": True}
    article.owner = get_user_model().objects.create(
        username="rholman", email="rich@example.org", first_name="Rich", last_name="Holman"
    )

    assert build(article)["owner"] == "Rich Holman"


def test_owner_without_a_full_name_is_omitted_and_never_the_username(article, settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"INCLUDE_OWNER": True}
    article.owner = get_user_model().objects.create(username="rholman", email="rich@example.org")

    output = build(article)

    assert "owner" not in output
    assert "rholman" not in serialise(output)
    assert "rich@example.org" not in serialise(output)


# The normaliser: one rule for scalars and list items


@pytest.mark.django_db
def test_normalise_handles_each_supported_type(article, home):
    tag = Tag.objects.create(name="Climate")
    site = Site.objects.get(is_default_site=True)
    cases = [
        (None, None),
        (True, True),
        (False, False),
        (0, 0),
        (1.5, 1.5),
        ("text", "text"),
        (gettext_lazy("lazy"), "lazy"),
        (decimal.Decimal("1.50"), "1.50"),
        (datetime.date(2026, 9, 11), "2026-09-11"),
        (datetime.time(9, 5), "09:05:00"),
        (datetime.datetime(2026, 9, 11, 15, 30, tzinfo=PLUS_ONE), "2026-09-11T14:30:00Z"),
        (uuid.UUID(int=1), "00000000-0000-0000-0000-000000000001"),
        (tag, "Climate"),
        (
            article,
            {"title": "Fossil Free Future", "permalink": "http://localhost/fossil-free-future/"},
        ),
        (site, "http://localhost"),
        (Locale.get_default(), Locale.get_default().language_code),
        ((1, "two"), [1, "two"]),
        ({"b", "a"}, ["a", "b"]),
        (
            Page.objects.filter(pk=home.pk),
            [{"title": home.title, "permalink": "http://localhost/"}],
        ),
        ({"nested": {"list": [1, None, "x"]}}, {"nested": {"list": [1, None, "x"]}}),
    ]
    for value, expected in cases:
        assert normalise(value) == expected, value
        # The list path is the same path.
        assert normalise([value]) == [expected], value


def test_naive_datetimes_are_read_in_the_default_timezone():
    # Sandbox TIME_ZONE is Europe/London: 15:30 BST is 14:30 UTC.
    assert normalise(datetime.datetime(2026, 9, 11, 15, 30)) == "2026-09-11T14:30:00Z"


def test_unhandled_object_raises_naming_the_key(article, hook):
    hook(FRONTMATTER_HOOK, lambda fm, page, context: fm.update(campaign=object()))

    with pytest.raises(FrontmatterValueError, match="'campaign'"):
        build(article)


def test_unhandled_object_inside_a_list_raises_naming_the_item(article, hook):
    hook(FRONTMATTER_HOOK, lambda fm, page, context: fm.update(links=[1, object()]))

    with pytest.raises(FrontmatterValueError, match=r"'links\[1\]'"):
        build(article)


def test_unhandled_object_inside_a_mapping_raises_naming_the_path():
    with pytest.raises(FrontmatterValueError, match="'meta.inner'"):
        normalise({"meta": {"inner": object()}})


def test_non_string_mapping_keys_are_rejected():
    with pytest.raises(FrontmatterValueError, match="42"):
        normalise({42: "x"})


def test_model_instance_inside_a_list_round_trips(article, home, hook):
    hook(FRONTMATTER_HOOK, lambda fm, page, context: fm.update(related=[home]))

    output = load(serialise(build(article)))

    assert output["related"] == [{"title": home.title, "permalink": "http://localhost/"}]


# YAML serialisation and round trips


@pytest.mark.parametrize(
    "value",
    [
        "yes",
        "true",
        "no",
        "null",
        "~",
        "0123",
        "1e3",
        "12:30",
        "2026-09-11",
        "2026-09-11T08:30:00Z",
        "line one\nline two",
        "with: colon",
        "quote \"double\" and 'single'",
        "",
        "  leading",
        "trailing  ",
        "# not a comment",
        "- not a list",
        "🌍 naïve café",
        [],
        {},
        False,
        0,
        0.0,
        -1,
        ["a", 1, None],
        {"a": {"b": [1, "two", None, False]}},
    ],
    ids=repr,
)
def test_values_round_trip_through_yaml(value):
    assert load(serialise({"v": value}))["v"] == value


def test_multiline_strings_use_a_literal_block():
    assert "notes: |-\n  line one\n  line two\n" in serialise({"notes": "line one\nline two"})


def test_key_order_is_kept_and_unicode_is_not_escaped():
    assert serialise({"z": 1, "a": "🌍"}) == "---\nz: 1\na: 🌍\n---\n"


def test_dates_are_written_as_strings_not_yaml_timestamps(article):
    output = load(serialise(build(article)))

    assert output["date"] == "2026-09-01T08:30:00Z"
    assert output["timestamp"] == "2026-09-11T16:00:00Z"


def test_bool_like_editor_values_keep_their_types(article):
    PageAgentSettings.objects.create(
        page=article, extra_frontmatter={"flag": "yes", "count": 0, "off": False, "empty": []}
    )

    output = load(serialise(build(article)))

    assert output["flag"] == "yes"
    assert output["count"] == 0
    assert output["off"] is False
    assert output["empty"] == []
