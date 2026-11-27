"""The independent registry records evidence and separates identity from serving."""

from datetime import date

import pytest
from django.test import RequestFactory

from wagtail_markdown_agents.data.agents import (
    AGENTS,
    KINDS,
    MARKDOWN_UA_STRINGS,
    REGISTRY_VERSION,
    RETIRED_AGENTS,
    identify_agent,
)
from wagtail_markdown_agents.data.operators import operator_for_agent
from wagtail_markdown_agents.negotiation import detect, detect_agent
from wagtail_markdown_agents.stats import agent_label, categorise_agent


def test_registry_integrity_and_review_metadata():
    assert REGISTRY_VERSION
    entries = AGENTS + RETIRED_AGENTS
    assert len({a.label.casefold() for a in entries}) == len(entries)
    tokens = [token.casefold() for a in entries for token in a.tokens]
    assert len(set(tokens)) == len(tokens)
    for agent in entries:
        assert 0 < len(agent.label) <= 100
        assert agent.tokens and agent.notes and agent.sources
        # As in agent-signals, an operator that doesn't document the agent is left out.
        assert agent.operator or "operator" in agent.notes.casefold()
        assert all(source.startswith("https://") for source in agent.sources)
        assert date.fromisoformat(agent.reviewed) <= date.today()
        # One purpose per entry: agent-signals' category (#93).
        assert len(agent.purposes) == 1
        assert agent.category in {"on-demand", "search", "training", "unknown"}
        assert agent.label == agent.label.rstrip("/")
        assert type(agent.auto_markdown) is bool
        assert categorise_agent(agent.label) == agent.category
        assert operator_for_agent(agent.label) != "unattributed" or not agent.operator


def test_revision_6_shape_and_kinds():
    # Exactly agent-signals revision 6's entries, active and retired (#93).
    assert len(AGENTS) == 52
    assert len(RETIRED_AGENTS) == 36
    kinds = [agent.kind for agent in AGENTS]
    assert {kind: kinds.count(kind) for kind in KINDS} == {
        "agent": 37,
        "browser": 9,
        "reference": 6,
    }
    assert {a.label for a in AGENTS if a.kind == "reference"} == {
        "Applebot",
        "Bravebot",
        "GoogleOther",
        "Googlebot",
        "PetalBot",
        "bingbot",
    }
    for agent in AGENTS:
        if agent.kind != "agent":
            # Browsers need the page; serving search engines by UA risks cloaking.
            assert not agent.auto_markdown, agent.label
    for agent in RETIRED_AGENTS:
        assert not agent.kind and not agent.auto_markdown, agent.label


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


CLAUDE_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko; compatible; "
    "Claude-Agent/1.0) Chrome/154.0.0.0 Safari/537.36"
)


@pytest.mark.parametrize(
    "ua", ["Applebot/0.1", "bingbot/2.0", "Googlebot/2.1", "Googlebot-Image/1.0", CLAUDE_AGENT]
)
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
    assert detect_agent("meta-externalfetcher/1.1") == "meta-externalfetcher"
    assert detect_agent("GoogleOther-Image/1.0") == "GoogleOther"
    # Googlebot's products count as Googlebot, as in agent-signals revision 4.
    for product in ("Googlebot-Image/1.0", "Googlebot-News", "Googlebot-Video/1.0"):
        assert detect_agent(product) == "Googlebot"
    assert "Applebot" not in MARKDOWN_UA_STRINGS


@pytest.mark.django_db
def test_recognition_only_identity_is_recorded_on_explicit_markdown_access():
    from wagtail_markdown_agents.models import AgentAccess
    from wagtail_markdown_agents.stats import record_access

    record_access(page_id=123, user_agent="Applebot/0.1", access_method="export-url")
    row = AgentAccess.objects.get()
    assert row.agent == "Applebot"
    assert categorise_agent(row.agent) == "search"


# Served on the User-Agent: agent-signals revision 6's 25 (#93).
SERVED = {
    "GPTBot",
    "ChatGPT-User",
    "ClaudeBot",
    "Claude-User",
    "Claude-SearchBot",
    "OAI-SearchBot",
    "PerplexityBot",
    "Perplexity-User",
    "meta-externalagent",
    "meta-externalfetcher",
    "meta-webindexer",
    "MistralAI-User",
    "DuckAssistBot",
    "KimiBot",
    "Amzn-SearchBot",
    "Cloudflare-AI-Search",
    "LinerBot",
    "ShapBot",
    "KernelSearchBot",
    "Anomura",
    "Kimi-User",
    "Amzn-User",
    "Shap-User",
    "KeenableBot",
    "ClueWeb-Crawler",
}


def test_served_agents_are_agent_signals_served_set():
    assert {a.label for a in AGENTS if a.auto_markdown} == SERVED


@pytest.mark.parametrize(
    ("ua", "label"),
    [
        # Verbatim examples from operator pages or Cloudflare Radar records.
        (
            "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ShapBot/0.1.0",
            "ShapBot",
        ),
        (
            "Mozilla/5.0 (compatible; Cotoyogi/4.0; +https://ds.rois.ac.jp/center8/crawler/)",
            "Cotoyogi",
        ),
        (
            "ICC-Crawler/3.0 (Mozilla-compatible; ; https://ucri.nict.go.jp/en/icccrawler.html)",
            "ICC-Crawler",
        ),
        (
            "Cloudflare-AI-Search-External (https://developers.cloudflare.com/ai-search; "
            "ai-search@cloudflare.com)",
            "Cloudflare-AI-Search",
        ),
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
        (
            "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; Kimi-User/1.0; "
            "+https://www.kimi.com/policies/kimi-crawlers",
            "Kimi-User",
        ),
        (
            "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Amzn-User/0.1)",
            "Amzn-User",
        ),
        (
            "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; Shap-User/0.1.0",
            "Shap-User",
        ),
    ],
)
def test_published_headers_match_restored_identities(ua, label):
    assert detect_agent(ua) == label


@pytest.mark.parametrize(
    ("ua", "label", "purpose", "operator"),
    [
        # Headers that matched before 2026-11-27.1 retired their entries (#96).
        (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36 (Nava/1.0)",
            "Nava",
            "on-demand",
            "nava",
        ),
        ("Retool/2.0 (+https://docs.tryretool.com/docs/apis)", "Retool", "unknown", "retool"),
        ("AdpResearchBot/1.0", "AdpResearchBot", "unknown", "adp"),
        (
            "Mozilla/5.0 (compatible; SemrushBot-SWA/0.1; +http://www.semrush.com/bot.html)",
            "SemrushBot-SWA",
            "unknown",
            "semrush",
        ),
        (
            "AwarioSmartBot/1.0 (+https://awario.com/bots.html; bots@awario.com)",
            "Awario",
            "unknown",
            "awario",
        ),
        (
            "netEstate NE Crawler (+http://www.website-datenbank.de/)",
            "netEstate NE Crawler",
            "unknown",
            "netestate",
        ),
        ("bigsur.ai (+https://www.bigsur.ai)", "bigsur.ai", "search", "big-sur-ai"),
        ("Make.com/production", "make.com", "unknown", "make"),
        ("OnirocoCrawler/1.0", "ChathiveCrawler", "search", "oniroco"),
        ("Instaparser/1.0", "Instapaper", "on-demand", "instapaper"),
        ("Google-CloudVertexBot/1.0", "CloudVertexBot", "search", "google"),
        # agent-signals' retired WordPress-era labels, held here from 2026-11-27.2 (#93).
        ("Claude-Web/1.0", "Claude-Web", "on-demand", "anthropic"),
        ("anthropic-ai", "anthropic-ai", "training", "anthropic"),
        ("Google-Extended", "Google-Extended", "training", "google"),
        ("Mozilla/5.0 (compatible; Applebot-Extended/1.0)", "Applebot-Extended", "search", "apple"),
        ("cohere-ai", "cohere-ai", "training", "cohere"),
        ("FishBot/1.0", "FishBot", "training", "unattributed"),
        ("Gemini-User", "Gemini-User", "on-demand", "google"),
        ("Google-NotebookLM", "Google-NotebookLM", "on-demand", "google"),
    ],
)
def test_retired_identities_stop_matching_and_keep_their_past_rows(ua, label, purpose, operator):
    assert identify_agent(ua) is None
    assert agent_label(ua) == ""
    assert detect(RequestFactory().get("/", HTTP_USER_AGENT=ua)) is None
    assert label in {agent.label for agent in RETIRED_AGENTS}
    assert not {token.casefold() for token in MARKDOWN_UA_STRINGS} & {label.casefold()}
    # A stored row keeps the purpose and operator it had before retirement.
    assert categorise_agent(label) == purpose
    assert operator_for_agent(label) == operator


@pytest.mark.parametrize(
    ("ua", "label", "operator", "served"),
    [
        # The nine agents of #60, from operator pages, logs or agent-signals cases.
        ("curl/7.81.0 Geminibot", "Geminibot", "google", False),
        (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36 Geminibot",
            "Geminibot",
            "google",
            False,
        ),
        (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/137.0.0.0 Safari/537.36 (compatible; Google-GeminiNotebook; "
            "+https://developers.google.com/crawling/docs/crawlers-fetchers/google-gemininotebook)",
            "Google-GeminiNotebook",
            "google",
            False,
        ),
        ("RiverBot/1.0 (+https://river.ai/bot)", "RiverBot", "unattributed", False),
        (
            "Mozilla/5.0 (compatible; ibou-search/2.0; +https://ibou.com/crawlers.html)",
            "ibou-search",
            "unattributed",
            False,
        ),
        (
            "Mozilla/5.0 (compatible; ibou-search/2.0; www.ibou.com)",
            "ibou-search",
            "unattributed",
            False,
        ),
        (
            "LinkupBot/1.0 (LinkupBot for web indexing; https://linkup.so/bot; bot@linkup.so)",
            "LinkupBot",
            "linkup",
            False,
        ),
        (
            "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; YouBot/1.0; "
            "+https://docs.you.com/youbot; env:prod) Chrome/142.0.0.0 Safari/537.36",
            "YouBot",
            "you-com",
            False,
        ),
        (
            "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; KeenableBot/1.0; "
            "+https://keenable.ai/bot)",
            "KeenableBot",
            "keenable",
            True,
        ),
        (
            "ClueWeb-Crawler/1.0 (+https://boston.lti.cs.cmu.edu/CMU-ClueWeb-Crawler/; "
            "mailto:cmu-clueweb-crawler@andrew.cmu.edu)",
            "ClueWeb-Crawler",
            "unattributed",
            True,
        ),
        (
            "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; "
            "AzureAI-SearchBot/1.0;",
            "AzureAI-SearchBot",
            "unattributed",
            False,
        ),
    ],
)
def test_agents_added_in_revision_4(ua, label, operator, served):
    agent = identify_agent(ua)
    assert agent.label == label and agent.kind == "agent"
    assert operator_for_agent(label) == operator
    assert agent.auto_markdown is served
    assert detect(RequestFactory().get("/", HTTP_USER_AGENT=ua)) == ("ua" if served else None)


@pytest.mark.parametrize(
    ("ua", "label"),
    [
        # agent-signals revision 4 matches ClaudeBot/ and Applebot/ with their slash.
        # The token matcher here gets the same answers without one (agent-signals#2).
        (
            "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-SearchBot/1.0; "
            "+claudebot@anthropic.com)",
            "Claude-SearchBot",
        ),
        (
            "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-User/1.0; "
            "+claudebot@anthropic.com)",
            "Claude-User",
        ),
        (
            "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; "
            "+claudebot@anthropic.com)",
            "ClaudeBot",
        ),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like "
            "Gecko) Chrome/131.0.0.0 Safari/537.36; ClaudeBot/1.0; +claudebot@anthropic.com)",
            "ClaudeBot",
        ),
        ("MOZILLA/5.0 (COMPATIBLE; CLAUDEBOT/1.0)", "ClaudeBot"),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1 "
            "(Applebot/0.1; +http://www.apple.com/go/applebot)",
            "Applebot",
        ),
        ("Mozilla/5.0 (compatible; Applebot-Extended/1.0; +https://example.com/bot)", None),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36",
            None,
        ),
    ],
)
def test_slash_matches_of_revision_4_give_the_same_identity(ua, label):
    assert detect_agent(ua) == label


@pytest.mark.parametrize(
    "ua",
    [
        # Contact addresses, URLs and unreviewed tokens are not identities.
        "CompetitorWatch/1.0 (+https://www.example.org/; contact devin@example.org)",
        "Tool/1.0 (+https://www.bigsur.ai)",
        "Make/production",
        "Integromat/production",
        "Awario/1.0",
    ],
)
def test_unreviewed_or_incidental_strings_are_not_identities(ua):
    assert identify_agent(ua) is None


def test_restored_labels_correct_historical_categories_at_read_time():
    # Stored labels are unchanged; categories follow current operator evidence.
    assert categorise_agent("LinerBot") == "search"
    assert categorise_agent("AdpResearchBot") == "unknown"
    assert categorise_agent("WARDBot") == "unknown"
    assert categorise_agent("Awario") == "unknown"
    assert categorise_agent("CloudflareBrowserRenderingCrawler") == "training"
    assert categorise_agent("ShapBot") == "search"
    assert categorise_agent("Nava") == "on-demand"


@pytest.mark.parametrize("label", ["FacebookBot", "Kimi-SearchBot", "OAI-AdsBot"])
def test_labels_agent_signals_does_not_hold_are_dropped(label):
    # Dropped in 2026-11-27.2 (#93); migration 0008 moves their rows to unknown.
    assert label.casefold() not in {a.label.casefold() for a in AGENTS + RETIRED_AGENTS}
    assert categorise_agent(label) == "unknown"
    assert operator_for_agent(label) == "unattributed"


def test_anthropics_hosted_browser_is_an_on_demand_agent_served_html():
    # Verbatim header from Anthropic's hosted-browser article (2026-11-06).
    agent = identify_agent(CLAUDE_AGENT)
    assert (agent.label, agent.operator, agent.category) == (
        "Claude-Agent",
        "Anthropic",
        "on-demand",
    )
    assert not agent.auto_markdown
    assert "Claude-Agent" not in MARKDOWN_UA_STRINGS
    assert operator_for_agent("Claude-Agent") == "anthropic"
    # Claude Code still counts as Claude-User.
    claude_code = "Claude-User (claude-code/2.1.284; +https://support.anthropic.com/)"
    assert detect_agent(claude_code) == "Claude-User"


def test_only_the_first_2048_bytes_are_matched():
    # As agent-signals cuts every header before matching (#93).
    padding = "Mozilla/5.0 " + "x" * 2020
    early = padding + " GPTBot/1.4"
    assert len(early) <= 2048 and identify_agent(early).label == "GPTBot"
    late = padding + "y" * 30 + " GPTBot/1.4"
    assert len(late) > 2048 and late.index("GPTBot") + len("GPTBot") > 2048
    assert identify_agent(late) is None
    assert detect(RequestFactory().get("/", HTTP_USER_AGENT=late)) is None
