"""Read-time intent classification and the reviewed dataset contract (#34/#76)."""

import json
from datetime import date
from pathlib import Path

import pytest
from wagtail import hooks

from wagtail_markdown_agents.data.agents import AGENT_CATEGORIES, AGENT_UA_STRINGS
from wagtail_markdown_agents.models import AgentAccess
from wagtail_markdown_agents.negotiation import detect_agent
from wagtail_markdown_agents.stats import categorise_agent, get_agent_categories


@pytest.mark.parametrize(
    "agent,expected",
    [
        (" GPTBOT ", "training"),
        ("prefix cHaTgPt-UsEr suffix", "on-demand"),
        ("OAI-SearchBot", "search"),
        ("GPTBot ChatGPT-User", "on-demand"),
        ("ClaudeBot Claude-SearchBot", "search"),
        ("curl", "unknown"),
        ("", "unknown"),
        ("   ", "unknown"),
        (None, "unknown"),
        ("Gemini-User", "on-demand"),
    ],
)
def test_categories(agent, expected, settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"NEGOTIATE_USER_AGENT": False}
    assert categorise_agent(agent) == expected


@pytest.mark.parametrize("category,labels", AGENT_CATEGORIES.items())
def test_every_shipped_category(category, labels):
    for label in labels:
        assert categorise_agent(label.swapcase()) == category


def test_ordered_hook_mutations_are_isolated():
    original = get_agent_categories()

    def first(categories):
        categories["training"].append("CustomBot")
        return {"search": ["CustomBot"]}  # Mutation hook ignores returns.

    def second(categories):
        assert "CustomBot" in categories["training"]
        categories["on-demand"].append("Custom")

    with (
        hooks.register_temporarily("construct_markdown_agent_categories", second, order=10),
        hooks.register_temporarily("construct_markdown_agent_categories", first, order=-10),
    ):
        assert categorise_agent("CustomBot") == "on-demand"
        assert get_agent_categories()["training"].count("CustomBot") == 1
    assert get_agent_categories() == original
    assert categorise_agent("CustomBot") == "unknown"


@pytest.mark.parametrize(
    "first_category,expected", [("experimental", "unknown"), ("search", "search")]
)
def test_hook_can_replace_order_and_unknown_first_match_wins(first_category, expected):
    def override(categories):
        categories.clear()
        categories.update({first_category: ["Bot"], "training": ["GPTBot"]})

    with hooks.register_temporarily("construct_markdown_agent_categories", override):
        assert categorise_agent("GPTBot") == expected


def test_empty_substring_does_not_match():
    def override(categories):
        categories["on-demand"].append("")

    with hooks.register_temporarily("construct_markdown_agent_categories", override):
        assert categorise_agent("curl") == "unknown"


def test_hook_errors_propagate():
    def broken(categories):
        raise RuntimeError("broken category hook")

    with (
        hooks.register_temporarily("construct_markdown_agent_categories", broken),
        pytest.raises(RuntimeError, match="broken category hook"),
    ):
        categorise_agent("GPTBot")


@pytest.mark.django_db
def test_history_reclassified_without_database_writes(django_assert_num_queries, monkeypatch):
    row = AgentAccess.objects.create(
        page_id=123, agent="GPTBot", access_method="ua", access_date=date(2026, 9, 1), count=9
    )
    before = AgentAccess.objects.values().get()
    # Runtime detection changes do not remove historical classification entries.
    monkeypatch.setattr("wagtail_markdown_agents.negotiation.AGENT_UA_STRINGS", ())
    assert detect_agent(row.agent) is None
    with django_assert_num_queries(0):
        assert categorise_agent(row.agent) == "training"

    def remove(categories):
        categories["training"].remove("GPTBot")

    with (
        hooks.register_temporarily("construct_markdown_agent_categories", remove),
        django_assert_num_queries(0),
    ):
        assert categorise_agent(row.agent) == "unknown"
    assert AgentAccess.objects.values().get() == before


REFERENCE_FIXTURE = Path(__file__).with_name("fixtures") / "agents-wordpress-1.7.0.json"
STATS_GUIDE = Path(__file__).parents[1] / "docs" / "agent-access-stats.md"
ECHOBOX_UA = (
    "Mozilla/5.0 (compatible; EchoboxBot/1.0; hash/w4mwnpbXf3MFAbxOkJRw; +http://www.echobox.com)"
)


@pytest.fixture(scope="module")
def reference():
    return json.loads(REFERENCE_FIXTURE.read_text())


def test_dataset_equals_pinned_reference_plus_documented_additions(reference):
    additions = reference["wagtail_additions"]
    assert (*reference["detection"], *additions["detection"]) == AGENT_UA_STRINGS
    assert list(AGENT_CATEGORIES) == list(reference["categories"]) == list(additions["categories"])
    for category, labels in reference["categories"].items():
        assert AGENT_CATEGORIES[category] == (*labels, *additions["categories"][category])
    guide = STATS_GUIDE.read_text()
    category_additions = [label for labels in additions["categories"].values() for label in labels]
    documented = (*additions["detection"], *category_additions)
    for label in documented:
        assert f"`{label}`" in guide, f"Wagtail addition {label!r} is not documented in the guide"


def test_no_duplicate_or_shadowed_entries():
    assert len(set(AGENT_UA_STRINGS)) == len(AGENT_UA_STRINGS)
    lowered = [entry.lower() for entry in AGENT_UA_STRINGS]
    for entry in lowered:
        # Appending entries can never change which label an existing agent stores.
        assert [other for other in lowered if entry in other] == [entry]
    for labels in AGENT_CATEGORIES.values():
        assert len(set(labels)) == len(labels)


def test_first_match_precedence_over_full_headers():
    for entry in AGENT_UA_STRINGS:
        header = f"Mozilla/5.0 (compatible; {entry.swapcase()}; +https://example.com/bot)"
        assert detect_agent(header) == entry
        assert categorise_agent(entry) != "unknown"
    for category, labels in AGENT_CATEGORIES.items():
        for label in labels:
            assert categorise_agent(label.swapcase()) == category
    # Detection stores the first entry in dataset order; classification of the
    # stored label then checks on-demand, search and training in that order.
    assert detect_agent("ClaudeBot gptbot") == "GPTBot"
    assert detect_agent("Claude-User ClaudeBot") == "ClaudeBot"
    assert categorise_agent("Claude-User ClaudeBot") == "on-demand"
    assert categorise_agent(detect_agent("Claude-User ClaudeBot")) == "training"
    assert categorise_agent(detect_agent("ShapBot/1.0")) == "search"
    assert categorise_agent(detect_agent("meta-externalfetcher/1.1")) == "on-demand"


def test_category_only_robots_only_and_removed_tokens():
    assert "Gemini-User" in AGENT_CATEGORIES["on-demand"]
    assert "Gemini-User" not in AGENT_UA_STRINGS
    assert detect_agent("Gemini-User") is None
    assert categorise_agent("Gemini-User") == "on-demand"
    for token in ("Google-Extended", "Applebot-Extended"):
        assert token in AGENT_UA_STRINGS  # Historical robots.txt tokens, not observed UAs.
    # EchoboxBot's hash was imported from Cloudflare Radar and dropped upstream before 1.7.0.
    assert "w4mwnpbXf3MFAbxOkJRw" not in (*AGENT_UA_STRINGS, *AGENT_CATEGORIES["training"])
    assert detect_agent(ECHOBOX_UA) is None
    assert categorise_agent("w4mwnpbXf3MFAbxOkJRw") == "unknown"
