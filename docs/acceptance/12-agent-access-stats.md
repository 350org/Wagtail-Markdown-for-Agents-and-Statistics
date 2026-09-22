# 12 — Daily agent access statistics

Implements the project-owner-authorised #32/#33 acceptance criteria and the
single-query increment in the v0.1 scope. Read-time classification (#34),
the report (#35), retention pruning (#36) and volume benchmarks (#66) are
implemented. See the [benchmark record](../agent-stats-benchmarks.md) for backend
coverage and limitations.

- Given repeated successful page Markdown GETs with the same page, agent, method
  and UTC date, one row accumulates every hit, including concurrent first hits.
  A different dimension creates a different row. Each ordinary hit executes one
  database statement, inserting one or atomically adding one to the stored count.
- Deleting a page retains its numeric identifier and historical counts. The
  unique daily key and a date index are present in the database.
- Query, Accept and User-Agent negotiation count with that precedence; direct
  page-export GETs count as `export-url`, even if negotiation headers are present.
  Reading or closing the response body does not count again.
- Known agents retain their dataset label with UA-triggered serving disabled.
  All other clients share `""` (unknown); arbitrary header fragments are never
  persisted. Varying an unknown User-Agent must not create extra daily rows.
  Migration `0006_anonymize_unknown_agents` merges legacy unknown labels while
  preserving counts by page, method and date. Methods fit 20 characters.
- HTML, missing-file fallback, errors, serving vetoes, HEAD, previews and
  aggregate-only exports do not create statistics. A page-owned `index.md` counts
  as a page export. Direct and negotiated reads share the same recording path.
- A statistics failure is logged and does not prevent the selected Markdown
  response from being returned or leave an enclosing transaction broken.
- UTC dates are independent of the active Django timezone. No IP address or full
  User-Agent header is stored. CDN/static responses that bypass Django cannot be
  counted; the counters measure response selection, not completed delivery.

## Admin report (#35 / A09)

- The initial range is today and the preceding 29 UTC dates, even when the active
  timezone is on the previous local day. Date presets and inclusive custom ranges
  exclude both earlier and later dates. Invalid ranges show errors, not data.
- Inclusive spans of 92/93 and 1,827/1,828 dates switch daily/monthly/yearly grain.
  Leap days, calendar transitions, partial periods and missing buckets preserve
  filtered counts. One bucket and flat series show neutral correlation.
- Page, agent (including empty/unknown), method (including export-url), intent and
  date filters combine with AND. Tiles, charts, bucket tables and all paginated
  records reconcile to the same filtered counts and category-hook snapshot.
  Hook changes relabel historical records consistently, including unknown fallback.
- Page deletion retains rows and the filter's numeric identity with a deleted-page
  label. Client-supplied labels and current page titles are HTML-escaped.
- Pagination has 50 records, preserves filters and does not shrink summary totals.
  Empty history and no matching results have distinct messages and zero tiles.
- Active users need Wagtail admin access and the view-agent-access permission,
  directly or through a group; superusers are allowed. Staff/editor status alone
  does not expose report data or its menu entry. Permission checks apply to direct
  URLs and crafted export parameters too.
- The on-demand tile and legend say estimate; trends say correlation, never
  percentage change. CDN/static bypasses, aggregate downloads and response-selection
  limits are stated in the report. `tests/test_report.py` exercises these reporting
  behaviours; pruning and volume coverage are documented below.

### Report verification — 15 September 2026

- Ruff lint and formatting checks passed. Full pytest: 1,263 passed. Oldest tox
  environment (`py311-dj42-wagtail63`): 1,263 passed, with 10 dependency deprecation
  warnings. This includes 43 focused report cases, not the deferred #66 benchmark
  suite.
- Safari visual inspection used actual sandbox-rendered report HTML and collected
  Wagtail 7.4.2 assets, generated with synthetic traffic in an isolated pytest
  database and served locally. Inspected the 350.org stacked chart in light/dark
  themes, filtered results, monthly grain, expanded bucket table, daily records
  and the empty state. Corrected the page title, pagination wording and empty-state
  contrast. Live authenticated browser navigation was not used; filter submission
  and pagination requests are exercised through Django's test client.
- The README sample-data snippet was executed twice in an isolated database:
  120 records and 2,480 requests, including 120 unknown/export-url requests, with
  no duplicates on the second run. No persistent QA account was created.

## Retention pruning (#36 / A09)

- Given counters dated today, 89, 90, 91 and 400 days before today's UTC date, when
  the operator runs the prune command with the default retention and confirms, then
  only the 91- and 400-day rows are deleted; today, the cutoff date and a
  future-dated row are retained. The cutoff uses the UTC date even when the active
  timezone is still on the previous local day.
- `--days` overrides `STATS_RETENTION_DAYS`; the default retention is 90 days in
  deployment settings and does not depend on runtime settings. `0`, negative,
  non-numeric, boolean or string values from either source fail with a message
  naming the source, before any deletion.
- Without `--yes`, the command reports the selected count and cutoff date and
  requires typing `yes`; `no`, `y`, EOF and absent input leave every row in place,
  and EOF states that `--yes` is required. `--yes` never prompts. An empty selection
  and `--dry-run` never prompt or delete. The summary reports `deleted` and
  `retained` counts.
- Pruning 600 counters across 40 pages and three agents executes one `DELETE`
  statement bounded by the date cutoff, with no row loading, regardless of volume.
  `tests/test_prune_stats.py` exercises these scenarios; #66 adds the 48,000-row
  checks documented below.

### Pruning verification — 15 September 2026

- Ruff lint and formatting checks passed. Full pytest: 1,274 passed, including 11
  focused pruning cases. Oldest tox environment (`py311-dj42-wagtail63`): 1,274
  passed, with 10 dependency deprecation warnings. Query capture confirmed one
  cutoff-bounded `DELETE` for 600 counters; the #66 volume benchmark suite is not
  included.

## Volume and query performance (#66 / A09)

`tests/test_stats_volume.py` exercises 960 and 48,000 counters, fixed report and
prune query budgets, independent filtered totals and exact pagination, concurrent
first/existing hits for all methods, actual streamed GETs, UTC retention boundaries
and installed indexes. The [benchmark record](../agent-stats-benchmarks.md) contains
reproduction commands, measured SQLite/PostgreSQL plans and timings, and the
MySQL write-only result and existing migration limitation. Latency is observational;
counts and query budgets are enforced in the normal suite.
