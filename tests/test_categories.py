"""Read-time intent classification and the reviewed dataset contract (#34/#76)."""

import json
from datetime import date
from pathlib import Path

import pytest
from wagtail import hooks

from wagtail_markdown_agents.data.agents import AGENT_CATEGORIES, AGENTS
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
        assert categorise_agent("CustomBot") == "training"  # Exact hook label wins over Custom.
        assert get_agent_categories()["training"].count("CustomBot") == 1
    assert get_agent_categories() == original
    assert categorise_agent("CustomBot") == "unknown"


@pytest.mark.parametrize(
    "first_category,expected", [("experimental", "unknown"), ("search", "search")]
)
def test_hook_can_replace_order_and_unknown_exact_match_wins(first_category, expected):
    def override(categories):
        categories.clear()
        categories.update({first_category: ["GPTBot"], "training": ["GPTBot"]})

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
    monkeypatch.setattr("wagtail_markdown_agents.data.agents._MATCHERS", ())
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


def test_retired_labels_keep_their_frozen_classification():
    from wagtail_markdown_agents.data.legacy_agents import LEGACY_CATEGORIES

    fixture = Path(__file__).with_name("fixtures") / "agents-wordpress-1.7.0.json"
    reference = json.loads(fixture.read_text())
    assert {k: list(v) for k, v in LEGACY_CATEGORIES.items()} == reference["categories"]
    active = {agent.label.lower() for agent in AGENTS}
    for category, labels in LEGACY_CATEGORIES.items():
        for label in labels:
            if label.lower() not in active:
                assert categorise_agent(label) == category


def test_current_metadata_reports_mixed_and_unspecified_purposes():
    assert categorise_agent("Applebot") == "mixed"
    assert categorise_agent("Googlebot") == "mixed"
    assert categorise_agent("bingbot") == "mixed"
    assert categorise_agent("GoogleOther") == "unknown"
    assert categorise_agent("CloudVertexBot") == "search"
    # Historical controls must not be caught by the shorter active identity.
    assert categorise_agent("Applebot-Extended") == "search"
    assert categorise_agent("Google-Extended") == "training"


def test_retired_or_robots_only_tokens_are_not_detected():
    for token in (
        "Gemini-User",
        "Google-Extended",
        "Applebot-Extended",
        "Claude-Web",
        "anthropic-ai",
        "Instapaper",
        "w4mwnpbXf3MFAbxOkJRw",
    ):
        assert detect_agent(token) is None
