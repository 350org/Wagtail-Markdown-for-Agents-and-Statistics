"""Detection precedence and Accept parsing; no database, no path or method checks."""

import pytest
from django.test import RequestFactory

from wagtail_markdown_agents.data.agents import AGENT_UA_STRINGS
from wagtail_markdown_agents.negotiation import (
    METHOD_ACCEPT_HEADER,
    METHOD_QUERY_PARAM,
    METHOD_USER_AGENT,
    accepts_markdown,
    detect,
    detect_agent,
)

BROWSER = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,*/*;q=0.8"
GPTBOT = "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2)"


def request(path="/article/", **headers):
    return RequestFactory().get(
        path, **{f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()}
    )


@pytest.mark.parametrize(
    "accept,expected",
    [
        ("text/markdown", True),
        ("TEXT/MARKDOWN", True),
        ("text/markdown; charset=utf-8", True),
        (" text/markdown ;q=0.5, text/html", True),
        ("text/html, text/markdown;q=0.1", True),
        ('text/markdown;q="0.5"', True),
        ('text/markdown;profile="a,b";q=0', False),
        ('text/markdown;profile="a;q=0";q=1', True),
        ("text/markdown;q=abc", True),
        ("text/markdown;q=0", False),
        ("text/markdown;q=0.000", False),
        ("text/markdown;q=-1", False),
        ("text/*", False),
        ("*/*", False),
        ("text/*, */*;q=0.8", False),
        (BROWSER, False),
        ("application/json", False),
        ("text/markdownx", False),
        ("text/x-markdown", False),
        ("application/text/markdown", False),
        ("", False),
        (",;;=,text/;q", False),
    ],
)
def test_accept_media_range_parsing(accept, expected):
    assert accepts_markdown(accept) is expected
    assert (detect(request(accept=accept)) == METHOD_ACCEPT_HEADER) is expected


@pytest.mark.parametrize(
    "query,expected",
    [
        ("?output_format=md", True),
        ("?output_format=markdown", True),
        ("?output_format=MD", True),
        ("?output_format=Markdown", True),
        ("?page=2&output_format=md", True),
        ("?output_format=html", False),
        ("?output_format=", False),
        ("?output_format", False),
        ("?format=md", False),
        ("?output_format=md5", False),
        ("", False),
    ],
)
def test_query_parameter_values(query, expected):
    assert (detect(request("/article/" + query)) == METHOD_QUERY_PARAM) is expected


@pytest.mark.parametrize(
    "user_agent,expected",
    [
        (GPTBOT, "GPTBot"),
        (GPTBOT.lower(), "GPTBot"),
        ("Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)", "ClaudeBot"),
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X) Chrome/128 Safari/537.36", None),
        ("curl/8.7.1", None),
        ("", None),
    ],
)
def test_known_agent_matching(user_agent, expected):
    assert detect_agent(user_agent) == expected
    assert (detect(request("/article/", user_agent=user_agent)) == METHOD_USER_AGENT) is (
        expected is not None
    )


def test_agent_match_is_first_in_dataset_order():
    first, second = AGENT_UA_STRINGS[0], AGENT_UA_STRINGS[1]
    assert detect_agent(f"{second} {first}") == first
    assert detect_agent(f"{first} {second}") == first


def test_precedence_query_then_accept_then_agent(settings):
    both = request("/article/?output_format=md", accept="text/markdown", user_agent=GPTBOT)
    assert detect(both) == METHOD_QUERY_PARAM
    assert detect(request("/article/", accept="text/markdown", user_agent=GPTBOT)) == (
        METHOD_ACCEPT_HEADER
    )
    settings.WAGTAIL_MARKDOWN_AGENTS = {"NEGOTIATE_QUERY_PARAM": False}
    assert detect(both) == METHOD_ACCEPT_HEADER
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        "NEGOTIATE_QUERY_PARAM": False,
        "NEGOTIATE_ACCEPT_HEADER": False,
    }
    assert detect(both) == METHOD_USER_AGENT
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        "NEGOTIATE_QUERY_PARAM": False,
        "NEGOTIATE_ACCEPT_HEADER": False,
        "NEGOTIATE_USER_AGENT": False,
    }
    assert detect(both) is None


def test_agent_labelling_survives_disabled_user_agent_serving(settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"NEGOTIATE_USER_AGENT": False}
    assert detect(request("/article/", user_agent=GPTBOT)) is None
    assert detect_agent(GPTBOT) == "GPTBot"


def test_detection_ignores_method_and_path():
    factory = RequestFactory()
    post = factory.post("/admin/pages/1/edit/?output_format=md", HTTP_ACCEPT="text/markdown")
    assert detect(post) == METHOD_QUERY_PARAM
