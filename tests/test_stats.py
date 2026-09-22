"""Persistent daily counters count selected page responses exactly once."""
# ruff: noqa: F811 — shared fixtures.

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from datetime import timezone as dt_timezone

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import RequestFactory
from django.utils import timezone
from wagtail import hooks
from wagtail.models import Page

from tests import test_writer
from tests.test_middleware import BROWSER, GPTBOT, MARKDOWN, get, is_html, is_markdown
from tests.test_serving import body, corpus  # noqa: F401
from wagtail_markdown_agents.models import AgentAccess
from wagtail_markdown_agents.serving import serve_export
from wagtail_markdown_agents.stats import agent_label, connect, record_access

pytestmark = pytest.mark.django_db(transaction=True)
setup = test_writer.setup


@pytest.mark.parametrize(
    "ua,label",
    [
        (GPTBOT, "GPTBot"),
        ("gptbot/1.0 ClaudeBot/2.0", "GPTBot"),
        ("  CuRL/8.7.1 extra data ", ""),
        ("SomeClient extra", ""),
        ("  CAFÉ/1.0  ", ""),
        ("機" * 101 + "/1.0", ""),
        ("İ" * 101 + "/1.0", ""),
        ("person@example.invalid/1.0", ""),
        ("person@example.invalid GPTBot/1.0", "GPTBot"),
        ("", ""),
        ("   ", ""),
        (None, ""),
        ("(comment only)", ""),
    ],
)
def test_agent_labels(ua, label):
    assert agent_label(ua) == label


def test_single_query_insert_and_increment(django_assert_num_queries):
    for _ in range(3):
        with django_assert_num_queries(1):
            record_access(page_id=123, user_agent="curl/8", access_method="export-url")
    row = AgentAccess.objects.get()
    assert (row.page_id, row.agent, row.access_method, row.count) == (123, "", "export-url", 3)


@pytest.mark.parametrize("ua", ["機" * 101 + "/1.0", "O'Reilly/1.0", "person@example.invalid/1.0"])
def test_arbitrary_header_values_are_not_persisted(ua):
    record_access(page_id=123, user_agent=ua, access_method="query-param")
    record_access(page_id=123, user_agent=ua, access_method="query-param")
    row = AgentAccess.objects.get()
    assert row.agent == "" and row.count == 2


@pytest.mark.parametrize("path", ["/markdown/article.md", "/article/?output_format=md"])
def test_public_requests_cannot_create_unbounded_agent_labels(corpus, client, path):
    for i in range(20):
        response = get(client, path, HTTP_USER_AGENT=f"person-{i}@example.invalid/1.0")
        assert is_markdown(response)
        body(response)
    row = AgentAccess.objects.get()
    assert (row.agent, row.count) == ("", 20)
    body(get(client, path, HTTP_USER_AGENT=GPTBOT))
    assert AgentAccess.objects.count() == 2
    assert AgentAccess.objects.get(agent="GPTBot").count == 1


@pytest.mark.parametrize("use_tz", [False, True])
def test_default_clock_uses_utc(settings, monkeypatch, use_tz):
    from wagtail_markdown_agents import stats

    settings.USE_TZ = use_tz
    settings.TIME_ZONE = "America/Los_Angeles"

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is UTC
            return datetime(2026, 9, 15, 0, 15, tzinfo=UTC)

    monkeypatch.setattr(stats, "datetime", Clock)
    record_access(page_id=123, access_method="export-url")
    assert AgentAccess.objects.get().access_date == date(2026, 9, 15)


@pytest.mark.parametrize(
    "changes",
    [
        {"page_id": None},
        {"page_id": True},
        {"access_method": "invalid"},
        {"at": datetime(2026, 9, 15)},
    ],
)
def test_invalid_dimensions_do_not_write(changes, django_assert_num_queries):
    values = {"page_id": 123, "access_method": "ua", **changes}
    with django_assert_num_queries(0), pytest.raises(ValueError):
        record_access(**values)


def test_dimensions_and_utc_buckets():
    midnight = datetime(2026, 9, 15, tzinfo=UTC)
    for page_id, ua, method, at in [
        (1, "", "ua", midnight),
        (2, "", "ua", midnight),
        (1, "GPTBot/1.0", "ua", midnight),
        (1, "", "export-url", midnight),
        (1, "", "ua", midnight - timedelta(microseconds=1)),
    ]:
        with timezone.override("Pacific/Honolulu"):
            record_access(page_id=page_id, user_agent=ua, access_method=method, at=at)
    assert AgentAccess.objects.count() == 5
    record_access(
        page_id=1,
        user_agent="",
        access_method="ua",
        at=datetime(2026, 9, 15, 1, tzinfo=dt_timezone(timedelta(hours=2))),
    )
    assert (
        AgentAccess.objects.get(
            page_id=1, agent="", access_method="ua", access_date=date(2026, 9, 14)
        ).count
        == 2
    )


def test_unique_key_and_date_index():
    values = {"page_id": 1, "agent": "", "access_method": "ua", "access_date": date(2026, 9, 15)}
    AgentAccess.objects.create(**values)
    with pytest.raises(IntegrityError), transaction.atomic():
        AgentAccess.objects.create(**values)
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, AgentAccess._meta.db_table)
    assert any(
        c["unique"] and c["columns"] == ["page_id", "agent", "access_method", "access_date"]
        for c in constraints.values()
    )
    assert any(c["index"] and c["columns"] == ["access_date"] for c in constraints.values())


@pytest.mark.parametrize("existing", [False, True])
def test_concurrent_hits_do_not_lose_counts(existing):
    values = {"page_id": 123, "user_agent": "GPTBot", "access_method": "ua"}
    if existing:
        record_access(**values)
    workers, hits = 6, 10
    barrier = threading.Barrier(workers)

    def record():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            for _ in range(hits):
                record_access(**values)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(record) for _ in range(workers)]
        for future in futures:
            future.result(timeout=20)
    assert AgentAccess.objects.get().count == workers * hits + int(existing)


@pytest.mark.parametrize(
    "path,extra,method",
    [
        ("/article/?output_format=md", {**MARKDOWN, "HTTP_USER_AGENT": GPTBOT}, "query-param"),
        ("/article/", {**MARKDOWN, "HTTP_USER_AGENT": GPTBOT}, "accept-header"),
        ("/article/", {"HTTP_USER_AGENT": GPTBOT}, "ua"),
        (
            "/markdown/article.md?output_format=md",
            {**MARKDOWN, "HTTP_USER_AGENT": GPTBOT},
            "export-url",
        ),
    ],
)
def test_successful_reads_count_once(corpus, client, path, extra, method):
    writer, site, page, record = corpus
    connect()  # Repeated app setup must not duplicate the receiver.
    response = get(client, path, **extra)
    assert is_markdown(response)
    row = AgentAccess.objects.get()
    assert (row.page_id, row.agent, row.access_method, row.count) == (page.pk, "GPTBot", method, 1)
    assert b"Published" in body(response)
    assert AgentAccess.objects.get().count == 1


def test_known_agent_label_with_ua_negotiation_disabled(corpus, client, settings):
    writer, site, page, record = corpus
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        **settings.WAGTAIL_MARKDOWN_AGENTS,
        "NEGOTIATE_USER_AGENT": False,
    }
    writer.generate(page)
    assert is_html(get(client, "/article/", HTTP_USER_AGENT=GPTBOT))
    assert not AgentAccess.objects.exists()
    body(get(client, "/article/?output_format=md", HTTP_USER_AGENT=GPTBOT))
    assert AgentAccess.objects.get().agent == "GPTBot"


def test_page_deletion_preserves_history(corpus, client):
    writer, site, page, record = corpus
    body(get(client, "/markdown/article.md"))
    page_id = page.pk
    page.delete()
    assert AgentAccess.objects.get().page_id == page_id
    assert AgentAccess.objects.get().agent == ""


def test_excluded_requests_do_not_count(corpus, client):
    writer, site, page, record = corpus
    assert is_html(get(client, "/article/", **BROWSER))
    body(client.head("/article/", HTTP_HOST="example.org", **MARKDOWN))
    body(client.head("/markdown/article.md", HTTP_HOST="example.org"))
    assert get(client, "/missing/", **MARKDOWN).status_code == 404
    assert client.post("/markdown/article.md", HTTP_HOST="example.org").status_code == 405
    with hooks.register_temporarily("markdown_serve_allowed", lambda *args: False):
        assert is_html(get(client, "/article/", **MARKDOWN))
        assert get(client, "/markdown/article.md").status_code == 404
    writer._backend(record.file).delete(record.file.storage_key)
    assert is_html(get(client, "/article/", **MARKDOWN))
    assert get(client, "/markdown/article.md").status_code == 404
    assert not AgentAccess.objects.exists()


def test_header_errors_and_previews_do_not_count(corpus, client):
    writer, site, page, record = corpus

    def bad_headers(values, request, context):
        values["Content-Signal"] = "bad\r\nheader"

    with (
        hooks.register_temporarily("construct_markdown_response_headers", bad_headers),
        pytest.raises(ImproperlyConfigured),
    ):
        get(client, "/article/", **MARKDOWN)
    request = RequestFactory().get("/markdown/article.md", HTTP_HOST="example.org")
    request.is_preview = True
    response = serve_export(request, record.logical_path)
    if response is not None:
        body(response)
    assert not AgentAccess.objects.exists()


def test_page_indexes_count_but_aggregates_do_not(corpus, client):
    writer, site, page, record = corpus
    child = page.add_child(instance=Page(title="Child", slug="child"))
    child.save_revision().publish()
    writer.generate(page)
    for path in ("index.md", "llms.txt", "manifest.json"):
        writer.update_aggregate(site.pk, f"{site.hostname}/{path}", lambda previous: "listing")
        body(get(client, f"/markdown/{path}"))
    assert not AgentAccess.objects.exists()
    body(get(client, "/markdown/article/index.md"))
    assert AgentAccess.objects.get().page_id == page.pk


def test_stats_database_failure_preserves_response_and_transaction(
    corpus, client, monkeypatch, caplog
):
    from wagtail_markdown_agents import stats

    def broken_sql(connection):
        return "INSERT INTO missing_agentmd_stats_table VALUES (%s, %s, %s, %s, %s)"

    monkeypatch.setattr(stats, "_upsert_sql", broken_sql)
    with transaction.atomic():
        response = get(client, "/article/", **MARKDOWN)
        assert is_markdown(response)
        assert not AgentAccess.objects.exists()  # Enclosing transaction is still usable.
    assert b"Published" in body(response)
    assert "receiver" in caplog.text and "failed" in caplog.text
