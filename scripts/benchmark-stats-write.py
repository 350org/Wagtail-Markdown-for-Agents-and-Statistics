"""Measure the real recorder on an empty, explicitly named scratch database.

This isolates AgentAccess from unrelated CMS migrations. It does not establish
that the whole application supports the selected database. See the benchmark doc.
"""

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from time import perf_counter

import django

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sandbox.mysql_settings")
django.setup()

from django.db import connection, connections  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402

from wagtail_markdown_agents.models import AgentAccess  # noqa: E402
from wagtail_markdown_agents.stats import record_access  # noqa: E402


def main():
    if not str(connection.settings_dict["NAME"]).startswith("agentmd_stats_benchmark_"):
        raise SystemExit("Set AGENTMD_TEST_DB to an empty agentmd_stats_benchmark_* database.")
    if connection.introspection.table_names():
        raise SystemExit("Refusing to benchmark a non-empty database.")
    at = datetime(2026, 9, 15, 0, 15, tzinfo=UTC)
    with connection.schema_editor() as editor:
        editor.create_model(AgentAccess)
    try:
        AgentAccess.objects.bulk_create(
            [
                AgentAccess(
                    page_id=page,
                    agent=agent,
                    access_method=method,
                    access_date=at.date() - timedelta(days=day),
                    count=7,
                )
                for page in range(1, 101)
                for day in range(30)
                for agent in ("ChatGPT-User", "OAI-SearchBot", "GPTBot", "")
                for method in ("query-param", "accept-header", "ua", "export-url")
            ],
            batch_size=1000,
        )
        assert AgentAccess.objects.count() == 48000
        for method in ("query-param", "accept-header", "ua", "export-url"):
            values = {"page_id": 999999, "user_agent": "GPTBot", "access_method": method, "at": at}
            AgentAccess.objects.filter(page_id=999999).delete()
            timings = []
            with CaptureQueriesContext(connection) as queries:
                for _ in range(201):
                    tick = perf_counter()
                    record_access(**values)
                    timings.append(perf_counter() - tick)
            assert len(queries) == 201
            assert all(q["sql"].startswith("INSERT INTO") for q in queries)
            assert AgentAccess.objects.get(page_id=999999).count == 201
            for initial in (0, 1000000):
                AgentAccess.objects.filter(page_id=999999).delete()
                if initial:
                    AgentAccess.objects.create(
                        page_id=999999,
                        agent="GPTBot",
                        access_method=method,
                        access_date=at.date(),
                        count=initial,
                    )
                workers, hits = 8, 50
                barrier = threading.Barrier(workers)

                def record(barrier=barrier, values=values, hits=hits):
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
                elapsed = perf_counter() - started
                assert AgentAccess.objects.get(page_id=999999).count == initial + workers * hits
                assert AgentAccess.objects.count() == 48001
                print(
                    json.dumps(
                        {
                            "backend": connection.vendor,
                            "database_version": str(connection.get_database_version()),
                            "django": django.get_version(),
                            "rows": 48000,
                            "method": method,
                            "initial": initial,
                            "workers": workers,
                            "concurrent_hits": workers * hits,
                            "concurrent_seconds": elapsed,
                            "sequential_queries": len(queries),
                            "sequential_hits": 201,
                            "insert_ms": timings[0] * 1000,
                            "increment_median_ms": median(timings[1:]) * 1000,
                            "increment_p95_ms": sorted(timings[1:])[189] * 1000,
                        },
                        sort_keys=True,
                    )
                )
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(AgentAccess)
        connections.close_all()


if __name__ == "__main__":
    main()
