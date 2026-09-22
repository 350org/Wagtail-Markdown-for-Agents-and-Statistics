# Agent statistics volume and query benchmarks (#66)

`tests/test_stats_volume.py` is part of the normal pytest suite and the existing
SQLite compatibility matrix and PostgreSQL job. The `stats_volume` marker also
allows focused runs. It asserts correctness and fixed query budgets; elapsed
latency is recorded for comparison, without machine-dependent timing failures.

## Workload and guarantees

The deterministic fixture contains 48,000 daily counters: 100 page IDs × 30 UTC
dates × four agent labels × four access methods. Counts vary from 1 to 17. Dates
include future records, both sides of the 90-day retention cutoff, and the
92/93-day and 1,827/1,828-day grain transitions. One page is live, one is created
and then deleted, and the other IDs represent retained historical pages. A second
960-row fixture exercises the same report assertions with two page IDs.

The suite verifies:

- A first write stores 1. Each of 200 subsequent autocommit writes executes exactly
  one INSERT/upsert and increments a stored count of 1,000,000. No read/modify/write
  or replacement with 1 can satisfy these assertions.
- Eight independent database connections perform 50 hits each against the same
  page/agent/method/UTC-date key. All four methods run both a first-insert race and
  contention against an existing count of 1,000,000. Each run ends with exactly
  400 additional counts and one additional row.
- Eight workers each select and consume 20 actual streamed GET responses through
  the shared export-serving function. The 160 successful responses produce exactly
  160 `export-url` counts. This includes eligibility, storage and signal handling;
  it does not include a network HTTP server, middleware or a CDN.
- Both table sizes exercise 29 report requests: pagination, all date presets,
  every method/agent/intent, live and deleted page filters, combined filters,
  explicit custom endpoints, empty results, and grain transitions. Fixture-record
  sums independently reconcile tiles, chart bars, every bucket and the exact
  ordered page of records. Future and out-of-range dates are excluded.
- Reports use at most **five counter queries** (distinct pages, distinct agents,
  pagination count, at most 50 records, and SQL-grouped totals), **four page
  queries** (one title lookup plus admin navigation), and **25 queries overall**.
  These are ceilings at both volumes, including authentication and rendered admin
  HTML. The observed current stack uses 12–13 total queries. Empty results can omit
  the record query. Classification and displayed page titles never add per-row
  queries. The budget does not imply constant runtime: distinct dimensions, total
  aggregation, sorting and deep OFFSET pagination still depend on retained data.
- Pruning executes one counter COUNT in dry-run mode, or two COUNTs and one DELETE
  when confirmed, independently of volume. Transaction-control statements are
  excluded from this data-query budget. With `USE_TZ` both enabled and disabled and
  the active timezone on the previous local date, it deletes 9,600 rows strictly
  before the UTC cutoff, preserves the 1,600 cutoff-date rows, and reconciles
  retained row and request totals, including future records.
- Database introspection checks the compound unique index on
  `(page_id, agent, access_method, access_date)` and the date index. After ANALYZE,
  real EXPLAIN output is recorded for selective date, compound-dimension and prune
  predicates. Planner text/costs are observations, not brittle assertions.

## Reproduce on SQLite and PostgreSQL

From the project root, after installing development dependencies:

```bash
uv run pytest -q -s -m stats_volume | tee stats-volume-sqlite.log
AGENTMD_TEST_PORT=5432 uv run --with 'psycopg[binary]>=3.1' \
  pytest -q -s -m stats_volume --ds=sandbox.postgres_settings \
  | tee stats-volume-postgres.log
```

The PostgreSQL server must be an isolated test server with permission to create
and delete pytest's test database. Connection variables are documented in
[CONTRIBUTING.md](../CONTRIBUTING.md). Run the full suite normally after changes;
use `-m 'not stats_volume'` only for a quick development pass. No benchmark is
scheduled and the manual-only CI policy is unchanged.

To pin the recorded framework pair, add `--with Django==6.0.8 --with wagtail==7.4.3`
to `uv run`. Otherwise these commands use the locally resolved versions.

Each JSON output record includes the backend/version, Django/Wagtail versions,
workload size, case and elapsed seconds. Write measurements include median and
nearest-rank p95 latency for 200 increments. Report timings cover the authenticated
request and template rendering, with framework caches warmed; fixture generation
and the Python verification oracle are outside that timing. Prune timings cover
the command, excluding verification reads. Query capture itself adds overhead.

## Recorded run — 15 September 2026

[Raw measurements and query plans](benchmarks/agent-stats-2026-09-15.jsonl) record
Python 3.12.9, Django 6.0.8 and Wagtail 7.4.3 on macOS arm64. SQLite 3.47.1 used
pytest's in-memory database; PostgreSQL 16.15 and MySQL 8.4.11 ran in disposable
Docker containers over localhost. These runs used a shared development machine
and could overlap. They are a reproducible functional baseline, not a production
capacity estimate or a fair ranking of database engines.

| Measurement at 48,000 rows | SQLite | PostgreSQL |
| --- | ---: | ---: |
| Increment median / p95 | 0.031 / 0.053 ms | 0.492 / 0.668 ms |
| Report minimum / median / maximum (29 cases) | 49 / 70 / 167 ms | 30 / 49 / 106 ms |
| Maximum counter queries per report | 5 | 5 |
| Prune 9,600 rows (two timezone modes) | 19–20 ms | 11–12 ms |
| Concurrent streamed GETs | 160 / 160 counted | 160 / 160 counted |

Both planners used the date index for selective date/prune predicates and the
compound unique index for the fully specified daily key. No additional index or
production query change was justified by these results. A broad retention delete
can legitimately choose a sequential scan; a selective SELECT plan does not claim
that every DELETE or aggregate uses an index. Re-run against representative
production cardinality and distributions before making capacity decisions.

## MySQL write-only measurement and deployment limitation

The existing MySQL/MariaDB SQL branch uses `ON DUPLICATE KEY UPDATE`. MySQL 8.4.11
passed the isolated write benchmark: 201 sequential hits used 201 statements,
and all eight 400-hit concurrency runs (four methods, new/existing counters)
reconciled exactly. Median increment latency ranged from 1.03 to 1.34 ms and p95
from 1.74 to 2.87 ms. MariaDB was not measured in this run.

**This does not validate a full MySQL deployment.** Running the application
migrations on MySQL with `utf8mb4` fails in the existing ExportArtifact schema:
its unique `logical_path` has 1,024 characters, exceeding MySQL's 3,072-byte index
limit. The benchmark leaves that unrelated schema unchanged. Reporting, pruning
and serving measurements above cover SQLite and PostgreSQL only.

For a reproducible isolated write measurement, create a fresh disposable database
with a name beginning `agentmd_stats_benchmark_` and a binary `utf8mb4` collation,
then run:

```bash
AGENTMD_TEST_DB=agentmd_stats_benchmark_local AGENTMD_TEST_PORT=3306 \
  uv run --with mysqlclient python scripts/benchmark-stats-write.py
```

The test account needs table-creation rights in that scratch database. Set the
same `AGENTMD_TEST_USER`, `AGENTMD_TEST_PASSWORD` and `AGENTMD_TEST_HOST` variables
as appropriate. The script defaults to `sandbox.mysql_settings`, refuses any
other database-name prefix or a non-empty database, creates only the real
AgentAccess model, and removes its table in `finally`. It never runs application
migrations or changes existing tables. After interruption, remove the disposable
database yourself before repeating. The same runner can target PostgreSQL by
setting `DJANGO_SETTINGS_MODULE=sandbox.postgres_settings`.
