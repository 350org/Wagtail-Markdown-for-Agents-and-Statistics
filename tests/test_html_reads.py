"""HTML page reads by registry agents are counted next to Markdown (#61)."""
# ruff: noqa: F811 — shared fixtures.

import pytest
from django.core.checks import run_checks
from django.test import RequestFactory
from wagtail.models import Page

from tests import test_writer
from tests.test_middleware import BROWSER, GPTBOT, MARKDOWN, get, is_html, is_markdown
from tests.test_serving import body, corpus  # noqa: F401
from wagtail_markdown_agents import stats
from wagtail_markdown_agents.models import AgentAccess
from wagtail_markdown_agents.settings import NON_CONTENT_SETTINGS
from wagtail_markdown_agents.stats import counts_html, record_access, record_html_read

pytestmark = pytest.mark.django_db(transaction=True)
setup = test_writer.setup

CLAUDE_AGENT = "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-Agent/1.0)"


def configure(settings, **values):
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, **values}


def rows():
    return sorted(AgentAccess.objects.values_list("page_id", "agent", "access_method", "count"))


def test_browser_agent_html_read_counts_once_per_request(corpus, client):
    writer, site, page, record = corpus
    for _ in range(2):
        assert is_html(get(client, "/article/", HTTP_USER_AGENT=CLAUDE_AGENT))
    assert rows() == [(page.pk, "Claude-Agent", "html", 2)]


def test_markdown_agent_reading_a_page_without_an_export_counts_as_html(corpus, client):
    writer, site, page, record = corpus
    child = page.add_child(instance=Page(title="No export", slug="no-export"))
    child.save_revision().publish()
    assert is_html(get(client, "/article/no-export/", HTTP_USER_AGENT=GPTBOT))
    assert rows() == [(child.pk, "GPTBot", "html", 1)]


def test_negotiated_markdown_is_not_also_counted_as_html(corpus, client):
    writer, site, page, record = corpus
    assert is_markdown(get(client, "/article/", HTTP_USER_AGENT=GPTBOT))
    assert rows() == [(page.pk, "GPTBot", "ua", 1)]


def test_ua_negotiation_off_counts_the_html_the_agent_got(corpus, client, settings):
    writer, site, page, record = corpus
    configure(settings, NEGOTIATE_USER_AGENT=False)
    assert is_html(get(client, "/article/", HTTP_USER_AGENT=GPTBOT))
    assert rows() == [(page.pk, "GPTBot", "html", 1)]


def test_only_registry_agents_count(corpus, client):
    writer, site, page, record = corpus
    assert is_html(get(client, "/article/", **BROWSER))
    assert is_html(get(client, "/article/", HTTP_USER_AGENT="curl/8.7.1"))
    assert is_html(get(client, "/article/"))
    assert not AgentAccess.objects.exists()


def test_head_errors_and_non_page_routes_do_not_count(corpus, client):
    writer, site, page, record = corpus
    body(client.head("/article/", HTTP_HOST="example.org", HTTP_USER_AGENT=CLAUDE_AGENT))
    assert get(client, "/missing/", HTTP_USER_AGENT=CLAUDE_AGENT).status_code == 404
    # Not the canonical URL: Wagtail redirects to the trailing slash.
    assert get(client, "/article", HTTP_USER_AGENT=CLAUDE_AGENT).status_code == 301
    body(get(client, "/markdown/missing.md", HTTP_USER_AGENT=CLAUDE_AGENT))
    assert not AgentAccess.objects.exists()


def test_previews_do_not_count(corpus):
    writer, site, page, record = corpus
    request = RequestFactory().get("/article/", HTTP_HOST="example.org", HTTP_USER_AGENT=GPTBOT)
    response = page.specific.serve(request)
    response.render()
    request.is_preview = True  # Page.serve resets it; Wagtail's preview views set it.
    record_html_read(request, response)
    assert not AgentAccess.objects.exists()


def test_off_switch(corpus, client, settings):
    writer, site, page, record = corpus
    configure(settings, COUNT_HTML=False)
    assert is_html(get(client, "/article/", HTTP_USER_AGENT=CLAUDE_AGENT))
    assert not AgentAccess.objects.exists()
    # Markdown counting is unaffected.
    assert is_markdown(get(client, "/article/", **MARKDOWN, HTTP_USER_AGENT=GPTBOT))
    assert rows() == [(page.pk, "GPTBot", "accept-header", 1)]


@pytest.mark.parametrize(
    "exclude,counted",
    [
        ([], {"GPTBot", "Claude-Agent"}),
        (["gptbot"], {"Claude-Agent"}),
        (["Training"], {"Claude-Agent"}),
        (["on-demand"], {"GPTBot"}),
    ],
)
def test_exclusions_by_label_or_purpose(corpus, client, settings, exclude, counted):
    writer, site, page, record = corpus
    configure(settings, NEGOTIATE_USER_AGENT=False, COUNT_HTML_EXCLUDE=exclude)
    for ua in (GPTBOT, CLAUDE_AGENT):
        assert is_html(get(client, "/article/", HTTP_USER_AGENT=ua))
    assert set(AgentAccess.objects.values_list("agent", flat=True)) == counted


def test_unknown_clients_cannot_be_recorded_as_html():
    with pytest.raises(ValueError, match="registry agents only"):
        record_access(page_id=1, user_agent="curl/8", access_method="html")
    assert not counts_html("Mozilla/5.0 Chrome/128")
    assert not AgentAccess.objects.exists()


def test_browser_requests_never_route_or_query(corpus, client, monkeypatch):
    writer, site, page, record = corpus

    def forbidden(*args, **kwargs):
        pytest.fail("A browser request was routed for HTML counting")

    monkeypatch.setattr(stats, "routed_page", forbidden)
    request = RequestFactory().get("/article/", HTTP_HOST="example.org", **BROWSER)
    response = page.specific.serve(request)
    response.render()
    record_html_read(request, response)


def test_recording_failure_keeps_the_html_response(corpus, client, monkeypatch, caplog):
    writer, site, page, record = corpus

    def broken(**kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(stats, "record_access", broken)
    response = get(client, "/article/", HTTP_USER_AGENT=CLAUDE_AGENT)
    assert is_html(response)
    assert "agent read was not recorded" in caplog.text


@pytest.mark.parametrize("key,value", [("COUNT_HTML", "yes"), ("COUNT_HTML_EXCLUDE", "training")])
def test_setting_shapes_are_checked(settings, key, value):
    configure(settings, **{key: value})
    errors = [m for m in run_checks() if m.id == "wagtail_markdown_agents.E005"]
    assert any(key in m.msg for m in errors)


def test_counting_settings_do_not_change_rendered_documents():
    assert {"COUNT_HTML", "COUNT_HTML_EXCLUDE"} <= NON_CONTENT_SETTINGS


def test_a_counted_read_costs_one_query_and_a_browser_none(corpus, client, monkeypatch):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from wagtail_markdown_agents import middleware

    writer, site, page, record = corpus
    queries = []

    def measured(request, response):
        with CaptureQueriesContext(connection) as captured:
            record_html_read(request, response)
        queries.append([query["sql"] for query in captured])

    monkeypatch.setattr(middleware, "record_html_read", measured)
    for ua in (CLAUDE_AGENT, CLAUDE_AGENT, BROWSER["HTTP_USER_AGENT"]):
        assert is_html(get(client, "/article/", HTTP_USER_AGENT=ua))
    # Routing reuses Wagtail's cached lookup; only the upsert reaches the database.
    assert [len(run) for run in queries] == [1, 1, 0]
    assert all(run[0].startswith("INSERT") for run in queries[:2])
