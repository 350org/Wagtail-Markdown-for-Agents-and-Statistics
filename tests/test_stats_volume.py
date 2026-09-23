"""Deterministic volume checks and observational benchmarks for #66.

Run with ``pytest -s tests/test_stats_volume.py`` to retain JSON measurements.
Counts, query budgets and index availability are assertions; elapsed times are
observations, never machine-dependent pass/fail thresholds.
"""

import json
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from io import StringIO
from statistics import median
from time import perf_counter

import django
import pytest
import wagtail
from django.core.management import call_command
from django.db import connection, connections
from django.db.models import Sum
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from wagtail.models import Locale, Page

from tests.test_writer import setup as export_setup  # noqa: F401
from wagtail_markdown_agents.models import AgentAccess
from wagtail_markdown_agents.serving import serve_export
from wagtail_markdown_agents.stats import record_access

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.stats_volume]
TODAY = date(2026, 9, 15)
OFFSETS = [-1, *range(19), 29, 30, 89, 90, 91, 92, 365, 1826, 1827, 1828]
AGENTS = {
    "ChatGPT-User": "on-demand",
    "OAI-SearchBot": "search",
    "GPTBot": "training",
    "": "unknown",
}
INTENTS = ("on-demand", "search", "training", "mixed", "unknown")
METHODS = ("query-param", "accept-header", "ua", "export-url")
TABLE = AgentAccess._meta.db_table


def measure(case, started, **values):
    print(
        json.dumps(
            {
                "case": case,
                "backend": connection.vendor,
                "database_version": str(connection.get_database_version()),
                "django": django.get_version(),
                "wagtail": wagtail.__version__,
                "seconds": round(perf_counter() - started, 6),
                **values,
            },
            sort_keys=True,
        )
    )


@pytest.fixture(autouse=True)
def utc_clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is UTC
            return datetime(2026, 9, 15, 0, 15, tzinfo=UTC)

    for module in ("stats", "reports", "management.commands.agentmd_prune_stats"):
        monkeypatch.setattr(f"wagtail_markdown_agents.{module}.datetime", Clock)


@pytest.fixture
def seed():
    def create(pages=100):
        started = perf_counter()
        locale, _ = Locale.objects.get_or_create(language_code="en")
        root = Page.get_first_root_node() or Page.add_root(
            instance=Page(title="Root", slug="root", locale=locale)
        )
        live = root.add_child(instance=Page(title="Volume live page", slug="volume-live"))
        deleted = root.add_child(instance=Page(title="Volume deleted page", slug="volume-deleted"))
        ids = [live.pk, deleted.pk, *range(10000, 10000 + pages - 2)]
        rows = [
            AgentAccess(
                page_id=pk,
                agent=agent,
                access_method=method,
                access_date=TODAY - timedelta(days=offset),
                count=1 + (p + d + a + m) % 17,
            )
            for p, pk in enumerate(ids)
            for d, offset in enumerate(OFFSETS)
            for a, agent in enumerate(AGENTS)
            for m, method in enumerate(METHODS)
        ]
        AgentAccess.objects.bulk_create(rows, batch_size=1000)
        deleted_id = deleted.pk
        deleted.delete()
        assert AgentAccess.objects.count() == len(rows) == pages * 480
        measure("seed", started, rows=len(rows), pages=pages)
        return rows, live.pk, deleted_id

    return create


def dimensions(row):
    return row.access_date, row.page_id, row.agent, row.access_method


@pytest.mark.parametrize("pages", [2, 100])
def test_report_volume(seed, client, admin_user, pages):
    rows, live_id, deleted_id = seed(pages)
    client.force_login(admin_user)
    url = reverse("agentmd_report")
    # Warm framework template/content-type caches outside the measured requests.
    assert client.get(url).status_code == 200
    cases = [
        {},
        {"p": 2},
        {"p": 999999},
        *({"preset": str(days)} for days in (7, 30, 90, 365)),
        *({"method": method} for method in METHODS),
        *({"intent": intent} for intent in INTENTS),
        *({"agent": f"label:{agent}"} for agent in AGENTS),
        {"page_id": live_id},
        {"page_id": deleted_id},
        {"page_id": deleted_id, "agent": "label:", "method": "export-url", "intent": "unknown"},
        {"agent": "label:GPTBot", "intent": "search"},
        {"start": "2026-08-16", "end": "2026-08-17", "method": "export-url"},
        {"start": "2010-01-01", "end": "2010-01-01"},
        *(
            {"start": str(TODAY - timedelta(days=span - 1)), "end": str(TODAY)}
            for span in (92, 93, 1827, 1828)
        ),
    ]
    for params in cases:
        start = (
            date.fromisoformat(params["start"])
            if "start" in params
            else (TODAY - timedelta(days=int(params.get("preset", "7")) - 1))
        )
        end = date.fromisoformat(params.get("end", str(TODAY)))
        expected = [
            row
            for row in rows
            if start <= row.access_date <= end
            and ("page_id" not in params or row.page_id == params["page_id"])
            and ("agent" not in params or row.agent == params["agent"][6:])
            and ("method" not in params or row.access_method == params["method"])
            and ("intent" not in params or AGENTS[row.agent] == params["intent"])
        ]
        started = perf_counter()
        with CaptureQueriesContext(connection) as queries:
            response = client.get(url, params)
        elapsed = perf_counter() - started
        assert response.status_code == 200
        # Six counter queries: dimensions, count, rows, grouped totals and top pages.
        # Page queries include one title lookup and Wagtail admin navigation.
        data_queries = [q["sql"] for q in queries if TABLE in q["sql"]]
        assert len(data_queries) <= 6, data_queries
        page_queries = [q["sql"] for q in queries if "wagtailcore_page" in q["sql"]]
        assert len(page_queries) <= 4, page_queries
        # Bound the entire rendered/authenticated request too, allowing framework variation.
        assert len(queries) <= 25, [q["sql"] for q in queries]
        summary = response.context["summary"]
        span = (end - start).days + 1
        grain = "daily" if span <= 92 else "monthly" if span <= 1827 else "yearly"
        assert summary["grain"] == grain
        totals = {
            intent: sum(r.count for r in expected if AGENTS[r.agent] == intent)
            for intent in INTENTS
        }
        assert [tile["count"] for tile in summary["tiles"]] == [
            sum(totals.values()),
            *totals.values(),
        ]
        # Independent oracle over fixture records, using calendar label prefixes.
        width = {"daily": 10, "monthly": 7, "yearly": 4}[grain]
        buckets = Counter()
        for row in expected:
            buckets[row.access_date.isoformat()[:width], AGENTS[row.agent]] += row.count
        for bucket in summary["buckets"]:
            assert bucket["counts"] == [
                buckets[bucket["date"].isoformat()[:width], intent] for intent in INTENTS
            ]
        assert sum(bar["count"] for bar in summary["bars"]) == sum(totals.values())
        page = response.context["page_obj"]
        assert page.paginator.count == len(expected)
        ordered = sorted(
            expected,
            key=lambda r: (-r.access_date.toordinal(), r.page_id, r.agent, r.access_method),
        )
        offset = (page.number - 1) * 50
        assert [dimensions(r) for r in page] == [
            dimensions(r) for r in ordered[offset : offset + 50]
        ]
        assert len(page) <= 50
        if params.get("page_id") == deleted_id:
            assert f"Deleted page #{deleted_id}" in response.content.decode()
        if "p" in params:
            assert page.number == min(params["p"], page.paginator.num_pages)
        measure(
            "report",
            started,
            rows=len(rows),
            filters=params,
            seconds=round(elapsed, 6),
            queries=len(queries),
            data_queries=len(data_queries),
        )


def test_concurrent_served_gets_at_volume(seed, export_setup):  # noqa: F811
    rows, _, _ = seed()
    writer, _, _, page = export_setup
    export = writer.generate(page)
    workers, hits = 8, 20
    barrier = threading.Barrier(workers)

    def get():
        try:
            connections["default"].ensure_connection()
            barrier.wait(timeout=20)
            for _ in range(hits):
                request = RequestFactory().get(
                    "/markdown/article.md", HTTP_HOST="example.org", HTTP_USER_AGENT="GPTBot"
                )
                response = serve_export(request, export.logical_path)
                assert response.status_code == 200
                try:
                    assert b"Published" in b"".join(response.streaming_content)
                finally:
                    response.close()
        finally:
            connections.close_all()

    started = perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(get) for _ in range(workers)]
        for future in futures:
            future.result(timeout=60)
    row = AgentAccess.objects.get(page_id=page.pk)
    assert (row.count, row.agent, row.access_method, row.access_date) == (
        workers * hits,
        "GPTBot",
        "export-url",
        TODAY,
    )
    assert AgentAccess.objects.count() == len(rows) + 1
    measure("concurrent-served-get", started, rows=len(rows), workers=workers, hits=workers * hits)


def test_single_statement_write_at_volume(seed):
    rows, _, _ = seed()
    values = {"page_id": 999999, "user_agent": "GPTBot", "access_method": "export-url"}
    started = perf_counter()
    with CaptureQueriesContext(connection) as queries:
        record_access(**values)
    assert len(queries) == 1 and queries[0]["sql"].startswith("INSERT INTO")
    assert AgentAccess.objects.get(page_id=999999).count == 1
    # A large stored count detects replacement with 1, or an application-side increment.
    AgentAccess.objects.filter(page_id=999999).update(count=1000000)
    durations = []
    with CaptureQueriesContext(connection) as queries:
        for _ in range(200):
            tick = perf_counter()
            record_access(**values)
            durations.append(perf_counter() - tick)
    assert len(queries) == 200
    assert all(q["sql"].startswith("INSERT INTO") for q in queries)
    assert AgentAccess.objects.get(page_id=999999).count == 1000200
    assert AgentAccess.objects.count() == len(rows) + 1
    measure(
        "write",
        started,
        rows=len(rows),
        hits=200,
        queries=len(queries),
        median_ms=1000 * median(durations),
        p95_ms=1000 * sorted(durations)[189],
    )


@pytest.mark.parametrize("method", METHODS)
def test_concurrent_identical_hits_at_volume(seed, method):
    rows, _, _ = seed()
    workers, hits = 8, 50
    values = {"page_id": 999999, "user_agent": "GPTBot", "access_method": method}
    # Each worker opens its own connection before the barrier. Both a first-insert
    # race and contention on an existing, large count must reconcile exactly.
    for initial in (0, 1000000):
        AgentAccess.objects.filter(page_id=999999).delete()
        if initial:
            AgentAccess.objects.create(
                page_id=999999,
                agent="GPTBot",
                access_method=method,
                access_date=TODAY,
                count=initial,
            )
        barrier = threading.Barrier(workers)

        def record(barrier=barrier):
            connections.close_all()
            try:
                connections["default"].ensure_connection()
                barrier.wait(timeout=20)
                for _ in range(hits):
                    record_access(**values)
            finally:
                connections.close_all()

        started = perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(record) for _ in range(workers)]
            for future in futures:
                future.result(timeout=60)
        assert AgentAccess.objects.get(page_id=999999).count == initial + workers * hits
        assert AgentAccess.objects.count() == len(rows) + 1
        measure(
            "concurrent-write",
            started,
            rows=len(rows),
            workers=workers,
            hits=workers * hits,
            initial=initial,
            method=method,
        )


@pytest.mark.parametrize("use_tz", [True, False])
def test_prune_at_volume(seed, settings, use_tz):
    rows, _, _ = seed()
    settings.USE_TZ = use_tz
    cutoff = TODAY - timedelta(days=90)
    retained = [row for row in rows if row.access_date >= cutoff]
    before = [row for row in rows if row.access_date < cutoff]
    for dry_run in (True, False):
        output = StringIO()
        started = perf_counter()
        with timezone.override("America/Los_Angeles"), CaptureQueriesContext(connection) as queries:
            call_command("agentmd_prune_stats", days=90, dry_run=dry_run, yes=True, stdout=output)
        elapsed = perf_counter() - started
        sql = [q["sql"] for q in queries if TABLE in q["sql"]]
        assert len(sql) == (1 if dry_run else 3), sql
        assert sum(q.startswith("DELETE") for q in sql) == (0 if dry_run else 1)
        assert all(q.startswith("DELETE") or "COUNT(" in q for q in sql)
        assert f"before {cutoff}" in output.getvalue()
        assert f"deleted={len(before)}" in output.getvalue()
        expected = rows if dry_run else retained
        assert AgentAccess.objects.count() == len(expected)
        assert AgentAccess.objects.aggregate(total=Sum("count"))["total"] == sum(
            r.count for r in expected
        )
        assert AgentAccess.objects.filter(access_date=cutoff).count() == 1600
        measure(
            "prune",
            started,
            rows=len(rows),
            dry_run=dry_run,
            seconds=round(elapsed, 6),
            use_tz=use_tz,
            queries=len(sql),
            deleted=len(before),
        )


def test_volume_indexes_and_plans(seed):
    rows, live_id, _ = seed()
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, TABLE)
        quote = connection.ops.quote_name
        cursor.execute(
            f"ANALYZE TABLE {quote(TABLE)}"
            if connection.vendor == "mysql"
            else f"ANALYZE {quote(TABLE)}"
        )
    assert any(
        c["unique"] and c["columns"] == ["page_id", "agent", "access_method", "access_date"]
        for c in constraints.values()
    )
    assert any(c["index"] and c["columns"] == ["access_date"] for c in constraints.values())
    for name, queryset in {
        "report-date": AgentAccess.objects.filter(access_date=TODAY),
        "report-dimensions": AgentAccess.objects.filter(
            page_id=live_id, agent="GPTBot", access_method="export-url", access_date=TODAY
        ),
        "prune-cutoff": AgentAccess.objects.filter(access_date__lt=TODAY - timedelta(days=1827)),
    }.items():
        started = perf_counter()
        plan = queryset.explain()
        # Do not force planner settings or assert unstable cost/plan text. The
        # installed indexes are a hard check; preserve real planner choices below.
        measure(name, started, rows=len(rows), plan=plan)
