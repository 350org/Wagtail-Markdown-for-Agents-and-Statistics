"""The cache bypass is generated only from reviewed automatic serving identities."""

import pytest

from wagtail_markdown_agents.cloudflare import cache_bypass_expression
from wagtail_markdown_agents.data.agents import AGENTS


def test_expression_covers_serving_tokens_but_not_recognition_only_identities():
    expression = cache_bypass_expression("WWW.Example.org")
    assert expression.startswith('(http.host eq "www.example.org" and (')
    for agent in AGENTS:
        for token in agent.tokens:
            clause = f'lower(http.user_agent) contains "{token.lower()}"'
            assert (clause in expression) == agent.auto_markdown
    assert 'lower(url_decode(http.request.uri.query)) contains "output_format"' in expression
    assert 'headers["accept"]' not in expression
    assert len(expression) < 4096


def test_disabled_triggers_and_optional_accept():
    expression = cache_bypass_expression("example.org", user_agent=False, include_accept=True)
    assert "http.user_agent" not in expression
    assert 'headers["accept"]' in expression
    assert "http.request.uri.query" not in cache_bypass_expression("example.org", query_param=False)
    with pytest.raises(ValueError, match="trigger"):
        cache_bypass_expression("example.org", user_agent=False, query_param=False)


@pytest.mark.parametrize(
    "host",
    ["", "https://example.org", "example.org/x", "*.example.org", 'x" or true', "a..b", "a:443"],
)
def test_invalid_host_cannot_expand_rule_scope(host):
    with pytest.raises(ValueError, match="hostname"):
        cache_bypass_expression(host)
