# Release checklist

The maintainer preparing a release owns this checklist. Copy completed outcomes,
reviewer/date, exact revisions and verification results into the release PR or
review record. The checklist itself is not evidence that a release is ready.
Current release coordination is tracked in
[issue #5](https://github.com/350org/Wagtail-Markdown-for-Agents-and-Statistics/issues/5);
repository review/CI policy remains
[issue #16](https://github.com/350org/Wagtail-Markdown-for-Agents-and-Statistics/issues/16).

## WordPress drift review

- [ ] Read the [current matrix](wordpress-parity-status.md), [drift ledger](wordpress-drift-ledger.md)
  and [historical audit](wordpress-parity-audit.md). Identify the previous reviewed
  revision and the exact upstream branch/tag/commit being considered. Verify the
  source repository and current remote state; distinguish local branches from
  merged/released changes.
- [ ] Review commits and the net diff over the entire interval, including code,
  defaults, tests, public hooks, migrations, docs and release metadata. Recheck
  merge commits for changes not represented by their individual commits. A
  changelog alone is insufficient.
- [ ] Give every relevant change a ledger disposition with evidence. For required
  ports, link the task, milestone and behavioural acceptance criteria. For deferred
  changes, state the impact on this release. Recheck existing intentional differences
  instead of silently restoring WordPress defaults or its active bot list.
- [ ] Update the matrix's implementation revision, states and evidence. Keep client
  acceptance and live verification separate from unit-test coverage. Preserve the
  dashboard counting/filtering contract when adding presentation features.
- [ ] Record a completed interval review with reviewer/date, old and new upstream
  revisions, disposition IDs and remaining work. Only then advance the reviewed
  revision in the ledger. Preserve the original audit baseline and historical
  provenance fixtures; an advanced review revision does not mean full feature parity.

Useful read-only commands in the verified WordPress checkout (replace the revision
placeholders with the exact recorded hashes):

```bash
git log --reverse --oneline REVIEWED_REVISION..TARGET_REVISION
git diff --stat REVIEWED_REVISION..TARGET_REVISION
git diff REVIEWED_REVISION..TARGET_REVISION
git branch --all --contains FIX_REVISION
```

If upstream changed while work was in progress, review the additional interval
before selecting the final target. Do not infer remote freshness from cached refs.

## Behavioural verification

- [ ] Run the required local checks in [CONTRIBUTING.md](../CONTRIBUTING.md): full
  pytest suite, Ruff lint/format and the oldest tox environment. Record actual
  counts, failures, environment and exact tested revision. Follow its additional
  manual CI guidance for support-matrix or PostgreSQL-locking changes.
- [ ] For each port, link input/expected-output cases covering the shared behaviour.
  Reuse existing tests when they establish the contract; add missing regression
  coverage for behavioural changes. Shared fixtures need explicit platform-specific
  expectations for deliberate differences. There is currently no automated harness
  that runs both implementations against one fixture set.
- [ ] For report UI changes, inspect rendered labels, category colours and responsive
  layout, and verify filtered totals across chart/cards/records. Do not present
  Python report tests as browser verification.
- [ ] Review agent metadata changes using the [registry procedure](agent-registry.md#reviewing-a-registry-update),
  including effects on automatic serving, historical categories and CDN rules.
- [ ] Review remaining [client and deployment gates](transfer-readiness.md), including
  D6/D9/D12 and the limits of existing live evidence. State which gates apply to
  this release; future milestone features do not automatically block v0.1.

## Release record and artefacts

- [ ] Update version/changelog and installation/migration notes for the selected
  release. Clearly identify partial parity, deliberate differences and deferred work.
- [ ] Build and inspect the distribution artefacts; verify packaged migrations,
  templates, static assets, licence and installation against the supported setup.
  Record deployment/cache checks separately from local package tests.
- [ ] Confirm the selected revision, reviewer and remaining issues are recorded
  before the release/tag/publication step. Follow the project's agreed release
  workflow; completing this checklist does not itself publish or deploy anything.
