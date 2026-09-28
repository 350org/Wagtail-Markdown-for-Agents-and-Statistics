"""The independent registry records evidence and separates identity from serving."""

import json
from datetime import date
from pathlib import Path

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


# Registry 2026-09-28.1 (#19): every inherited WordPress string has a recorded
# disposition. Active labels keep the exact historical spelling.
EXCLUDED = {"Claude-Web", "anthropic-ai", "Google-Extended", "Applebot-Extended"}
DEFERRED = {"cohere-ai", "FishBot", "Anchor Browser", "amazon-kendra-"}
RESTORED_AUTO = {
    "KimiBot",
    "Amzn-SearchBot",
    "Cloudflare-AI-Search",
    "LinerBot",
    "ShapBot/",
    "KernelSearchBot",
    "Anomura",
}


def test_every_inherited_string_is_active_excluded_or_deferred():
    fixture = Path(__file__).with_name("fixtures") / "agents-wordpress-1.7.0.json"
    inherited = json.loads(fixture.read_text())["detection"]
    active = {agent.label for agent in AGENTS}
    assert len(inherited) == 69
    assert not (EXCLUDED | DEFERRED) & active
    assert set(inherited) == (set(inherited) & active) | EXCLUDED | DEFERRED
    assert len(set(inherited) & active) == 61
    assert {a.label for a in AGENTS if a.auto_markdown} == {
        "GPTBot",
        "ChatGPT-User",
        "ClaudeBot",
        "Claude-User",
        "Claude-SearchBot",
        "OAI-SearchBot",
        "PerplexityBot",
        "Perplexity-User",
        "meta-externalagent",
        "meta-externalfetcher/",
        "MistralAI-User",
        "DuckAssistBot",
        *RESTORED_AUTO,
    }


@pytest.mark.parametrize(
    ("ua", "label"),
    [
        # Verbatim examples from operator pages or Cloudflare Radar records.
        (
            "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ShapBot/0.1.0",
            "ShapBot/",
        ),
        (
            "Mozilla/5.0 (compatible; Cotoyogi/4.0; +https://ds.rois.ac.jp/center8/crawler/)",
            "Cotoyogi/",
        ),
        (
            "ICC-Crawler/3.0 (Mozilla-compatible; ; https://ucri.nict.go.jp/en/icccrawler.html)",
            "ICC-Crawler/",
        ),
        (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36 (Nava/1.0)",
            "Nava/",
        ),
        ("Retool/2.0 (+https://docs.tryretool.com/docs/apis)", "Retool/"),
        ("AdpResearchBot/1.0", "AdpResearchBot/"),
        (
            "Mozilla/5.0 (compatible; SemrushBot-SWA/0.1; +http://www.semrush.com/bot.html)",
            "SemrushBot-SWA/",
        ),
        ("AwarioSmartBot/1.0 (+https://awario.com/bots.html; bots@awario.com)", "Awario"),
        ("netEstate NE Crawler (+http://www.website-datenbank.de/)", "netEstate NE Crawler"),
        ("bigsur.ai (+https://www.bigsur.ai)", "bigsur.ai"),
        ("Make.com/production", "make.com"),
        (
            "Cloudflare-AI-Search-External (https://developers.cloudflare.com/ai-search; "
            "ai-search@cloudflare.com)",
            "Cloudflare-AI-Search",
        ),
        ("OnirocoCrawler/1.0", "ChathiveCrawler"),
        ("Instaparser/1.0", "Instapaper"),
        (
            "Mozilla/5.0 (compatible;PetalBot;+https://webmaster.petalsearch.com/site/petalbot)",
            "PetalBot",
        ),
        (
            "Mozilla/5.0 (Linux; Android 5.0) AppleWebKit/537.36 (KHTML, like Gecko) Mobile "
            "Safari/537.36 (compatible; Bytespider; https://zhanzhang.toutiao.com/)",
            "Bytespider",
        ),
        (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/137.0.0.0 Safari/537.36; Devin/1.0; +https://devin.ai",
            "Devin",
        ),
        (
            "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; KimiBot/1.0; "
            "+https://www.kimi.com/policies/kimi-crawlers",
            "KimiBot",
        ),
    ],
)
def test_published_headers_match_restored_identities(ua, label):
    assert detect_agent(ua) == label


@pytest.mark.parametrize(
    "ua",
    [
        # Contact addresses, URLs and unreviewed sibling products are not identities.
        "CompetitorWatch/1.0 (+https://www.example.org/; contact devin@example.org)",
        "Tool/1.0 (+https://www.bigsur.ai)",
        "Make/production",
        "Integromat/production",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; Kimi-User/1.0",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; Shap-User/0.1.0",
        "Mozilla/5.0 (compatible; Amzn-User/0.1)",
        "Awario/1.0",
    ],
)
def test_unreviewed_or_incidental_strings_are_not_identities(ua):
    assert identify_agent(ua) is None


def test_restored_labels_correct_historical_categories_at_read_time():
    # Stored labels are unchanged; categories follow current operator evidence.
    assert categorise_agent("LinerBot") == "search"
    assert categorise_agent("AdpResearchBot/") == "unknown"
    assert categorise_agent("WARDBot") == "unknown"
    assert categorise_agent("Awario") == "unknown"
    assert categorise_agent("CloudflareBrowserRenderingCrawler") == "mixed"
    assert categorise_agent("ShapBot/") == "search"
    assert categorise_agent("Nava/") == "on-demand"
