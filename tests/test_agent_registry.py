"""The independent registry records evidence and separates identity from serving."""

from datetime import date

import pytest
from django.test import RequestFactory

from wagtail_markdown_agents.data.agents import (
    AGENTS,
    MARKDOWN_UA_STRINGS,
    REGISTRY_VERSION,
    identify_agent,
)
from wagtail_markdown_agents.negotiation import detect, detect_agent
from wagtail_markdown_agents.stats import agent_label, categorise_agent


def test_registry_integrity_and_review_metadata():
    assert REGISTRY_VERSION
    assert len({a.label.casefold() for a in AGENTS}) == len(AGENTS)
    tokens = [token.casefold() for a in AGENTS for token in a.tokens]
    assert len(set(tokens)) == len(tokens)
    for agent in AGENTS:
        assert 0 < len(agent.label) <= 100
        assert agent.operator and agent.tokens and agent.notes and agent.sources
        assert all(source.startswith("https://") for source in agent.sources)
        assert date.fromisoformat(agent.reviewed) <= date.today()
        assert set(agent.purposes) <= {"on-demand", "search", "training", "other"}
        assert agent.purposes
        assert type(agent.auto_markdown) is bool
        assert categorise_agent(agent.label) == agent.category


@pytest.mark.parametrize("agent", AGENTS, ids=lambda a: a.label)
def test_all_identities_have_bounded_matching_and_independent_serving(agent):
    for token in agent.tokens:
        for ua in (
            token,
            f"Mozilla/5.0 (compatible; {token.swapcase()}/1.2; +https://example.org)",
        ):
            assert detect_agent(ua) == agent.label
            assert agent_label(ua) == agent.label
            request = RequestFactory().get("/", HTTP_USER_AGENT=ua)
            assert detect(request) == ("ua" if agent.auto_markdown else None)
        for ua in (
            f"Not{token}/1.0",
            f"{token}Fake/1.0",
            f"Tool/1.0 (+https://example.org/{token})",
        ):
            assert identify_agent(ua) is None


@pytest.mark.parametrize("ua", ["Applebot/0.1", "bingbot/2.0", "Googlebot/2.1", "OAI-AdsBot/1.0"])
def test_recognition_only_agents_can_explicitly_request_markdown(ua, settings):
    assert detect_agent(ua)
    assert detect(RequestFactory().get("/", HTTP_USER_AGENT=ua)) is None
    assert detect(RequestFactory().get("/?output_format=md", HTTP_USER_AGENT=ua)) == "query-param"
    assert (
        detect(RequestFactory().get("/", HTTP_USER_AGENT=ua, HTTP_ACCEPT="text/markdown"))
        == "accept-header"
    )
    settings.WAGTAIL_MARKDOWN_AGENTS = {"NEGOTIATE_USER_AGENT": False}
    assert detect_agent(ua)


def test_one_identity_decision_drives_serving_and_statistics():
    # Registry order determines both decisions, not the location within a header.
    ua = "Googlebot/2.1 GPTBot/1.4"
    assert detect_agent(ua) == "GPTBot"
    assert detect(RequestFactory().get("/", HTTP_USER_AGENT=ua)) == "ua"
    ua = "Applebot/0.1 GoogleOther"
    assert detect_agent(ua) == "Applebot"
    assert detect(RequestFactory().get("/", HTTP_USER_AGENT=ua)) is None


def test_documented_aliases_keep_stable_labels():
    assert detect_agent("meta-externalfetcher/1.1") == "meta-externalfetcher/"
    assert detect_agent("Google-CloudVertexBot/1.0") == "CloudVertexBot"
    assert detect_agent("CloudVertexBot/1.0") is None
    assert detect_agent("GoogleOther-Image/1.0") == "GoogleOther"
    assert "Applebot" not in MARKDOWN_UA_STRINGS


@pytest.mark.django_db
def test_recognition_only_identity_is_recorded_on_explicit_markdown_access():
    from wagtail_markdown_agents.models import AgentAccess
    from wagtail_markdown_agents.stats import record_access

    record_access(page_id=123, user_agent="Applebot/0.1", access_method="export-url")
    row = AgentAccess.objects.get()
    assert row.agent == "Applebot"
    assert categorise_agent(row.agent) == "mixed"
