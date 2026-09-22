# Local simulator fixtures — 22 September 2026

All six previously missing fixture kinds now have a repeatable synthetic sandbox
corpus. This is local evidence; it does not change the acceptance status of the
[21 September deployed run](2026-09-21-bounded-live-run.md).

## Local HTTP run

Used `sandbox.simulator_settings`, a fresh isolated SQLite database, Django 6.0.8,
Wagtail 7.4.3 and Python 3.12.9. The [documented setup](../agent-simulator.md#repeatable-local-corpus)
created the fixture branch and exported the configuration. The server listened
on loopback and was stopped after verification.

The plan used seed 59, a 250-request budget, five requests per second and the
strict cache profile. Its required suite contained 166 requests, with the rest
filled by deterministic mixed traffic. All 23 registry labels were scheduled.

| Check | Result |
| --- | --- |
| Complete HTTP run | 250 attempts, 250 assertion passes |
| Failures / known limitations | 0 / 0 |
| Explicit fixture coverage | All six kinds, GET and HEAD for each: 12 passes |
| Missing fixtures | None |
| Expected page-counter increments | 173 |
| Observed page-counter increments | 173 |
| Residuals by UTC day, page, agent and method | Zero in every bucket |

The request window was 15:23:15–15:24:15 UTC. Discovery completed before the baseline
snapshot. The HTTP counter comparison uses the local plan and before/after database
snapshots; it is not an nginx-correlated reconciliation. No CDN, authenticated vendor
traffic or multi-day behaviour was exercised. An initial sandbox-denied discovery
attempt is retained in the separate discovery log; it is outside this run's window.

Local scratch artifacts are retained under the ignored `sandbox/simulator-data/`
directory: `fixtures.json`, `plan.json`, `discovery.jsonl`, `run.jsonl`, `before.json`,
`after.json` and `summary.json`. This report is the durable summary, not a claim that
those local files form a published evidence archive.

## Automated contracts

`tests/test_simulator_fixtures.py` checks the actual page restrictions, exclusion
record, missing exports and ownerless navigation index. Every fixture request must
leave the entire statistics table unchanged. Preview tests call Wagtail's real
`serve_preview`, check `request.is_preview`, exclude a saved draft canary, deny page
and ancestor restrictions, and verify that the ordinary page still serves Markdown.

A complete 250-request integration plan passes through the Django test client and
real database counters, then returns `matched` from the reconciler using explicitly
modelled origin rows. These rows exercise the reconciliation contract and are not
presented as collected nginx logs. Truncated plans must report fixture kinds missing
unless both their GET and HEAD requests fit in the budget.

Regression verification:

| Environment | Full suite and targeted rerun |
| --- | --- |
| Python 3.12.9 / Django 6.0.8 / Wagtail 7.4.3 | 1,432 passed; three sandbox-blocked loopback tests passed with socket access |
| Python 3.11.15 / Django 4.2.30 / Wagtail 6.3.8 (oldest tox environment) | 1,432 passed; the same three loopback tests passed with socket access |

Both initial full invocations exited nonzero because macOS denied socket binding
in those three existing transport tests. This is combined full-suite and targeted
rerun evidence, not a claim that the original invocations were green. All seven
new fixture tests passed in both full runs. The older environment emitted upstream
deprecation warnings. Ruff lint/format and `git diff --check` also passed.

## Still required for deployed acceptance

Create equivalent controlled fixtures on the agreed deployment and retain correlated
origin logs plus counter snapshots. Independently establish cold-cache state and
complete the agreed multi-day and genuine vendor-fetch checks. Client decisions
D9/D12 and the restricted-link policy remain separate.
