# Contributing

Thanks for helping build wagtail-markdown-for-agents. This project is a collaboration
between [Rich Holman](https://github.com/dogwonder) (contributor to the WordPress original),
[350.org](https://350.org), and
[The Chancery Lane Project](https://chancerylaneproject.org) (for whom the WordPress
original was built).

## Workflow

- Work is organised as **milestones** (releases: v0.1, v0.2, v1.0) containing **epics**
  (tracking issues labelled `epic` with task lists) containing ordinary issues.
- Pick an unassigned issue from the current milestone, comment to claim it, branch from
  `main`, open a PR referencing the issue. Issues labelled `350-collab` are flagged as
  good entry points for 350.org contributors.
- Validate locally before merge: ruff, the full pytest suite, and the oldest tox
  environment (`uv run tox -e py311-dj42-wagtail63`) at minimum. The GitHub Actions
  workflow is manual-only to conserve hosted minutes; run it with
  `gh workflow run CI --ref <branch>` (after `gh workflow enable CI`) when a change
  touches the support matrix or PostgreSQL locking.
- UK English in comments, docs, and user-facing strings.

## Development environment

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run sandbox/manage.py migrate && uv run sandbox/manage.py runserver
```

The `sandbox/` project is the test target; `scripts/bakerydemo-setup.sh` sets up
Wagtail's bakerydemo with this package installed for realistic manual testing.
The [script guide](scripts/README.md) lists maintenance entry points and their effects.

The manual CI workflow also runs the full suite against PostgreSQL 16 to exercise
publication locking on a production database. To do the same locally against a test
server with permission to create databases:

```bash
AGENTMD_TEST_PORT=5432 uv run --with 'psycopg[binary]>=3.1' pytest --ds=sandbox.postgres_settings
```

Override `AGENTMD_TEST_DB`, `AGENTMD_TEST_USER`, `AGENTMD_TEST_PASSWORD`,
`AGENTMD_TEST_HOST` and `AGENTMD_TEST_PORT` as needed. Defaults are in
`sandbox/postgres_settings.py` and are for isolated test servers only.

The normal suite includes 48,000-row statistics checks. For focused runs and
recorded database measurements, see [Agent statistics benchmarks](docs/contributing/agent-stats-benchmarks.md).

Files in `tests/golden/` are reviewed snapshots of rendered output (#15). When a change in
output is intended, run the relevant test module with `UPDATE_GOLDEN=1`; the
[test guide](tests/README.md#updating-golden-output) maps snapshots to their modules.
Review the golden diff in the pull request as carefully as the code: the files are the
record of what agents receive, and the judgement calls on the rendering ledger point at
them.

When changing behaviour, update the relevant package guide and link the tests or
other evidence in the pull request. Explain compatibility and migration effects.
Before each release, record validation using the
[release checklist](docs/contributing/release-checklist.md).

Project-specific integrations should use the documented hooks and live in their
own packages. Keep the core package independent of project models.

## Licensing and attribution

This package is a **behavioural port** of the GPL-licensed WordPress plugin
[markdown-for-agents-and-statistics](https://github.com/dogwonder/markdown-for-agents-and-statistics).
Both projects are distributed under **GPL-3.0-or-later**. This project's copyright
holder is **350.org**. Preserve applicable third-party copyright and licence notices
when adapting code or importing assets.

- Work from the behavioural specification in [docs/contributing/design.md](docs/contributing/design.md)
  and implement the behaviour using Django and Wagtail conventions.
- Keep the source revision and attribution for imported reference data. The agent
  registry's evidence, review procedure and historical fixture are documented in
  [agent registry](docs/agent-registry.md). Check the
  provenance and terms of new data or assets before importing them.
- Identify the source and any adaptations in the pull request when porting code
  from the WordPress plugin or another project.

## Design authority

[docs/contributing/design.md](docs/contributing/design.md) is the architecture record. If an implementation needs
to deviate from it, say so in the PR and update the document in the same PR.
The roadmap is wider than v0.1; issues labelled `out-of-sow` are
not v0.1 release dependencies.
