# Release checklist

The maintainer preparing a release owns this checklist. Copy completed outcomes,
reviewer/date, exact revisions and verification results into the release PR or
review record. The checklist itself is not evidence that a release is ready.
Current release coordination is tracked in
[issue #5](https://github.com/350org/Wagtail-Markdown-for-Agents-and-Statistics/issues/5);
repository review/CI policy remains
[issue #16](https://github.com/350org/Wagtail-Markdown-for-Agents-and-Statistics/issues/16).

## Review the release changes

- [ ] Select the release revision and review all changes since the previous release,
  including defaults, public APIs, migrations, dependencies and package metadata.
- [ ] Update the affected guides and changelog. Explain breaking changes, migration
  steps and known limitations; distinguish implemented features from roadmap work.
- [ ] Check licensing and source attribution for imported code, data or assets.
  Preserve the provenance of retained fixtures and agent metadata.
- [ ] Record unresolved issues and whether they affect this release. Link the
  relevant tests and review evidence rather than relying on a feature checklist.

## Behavioural verification

- [ ] Run the required local checks in [CONTRIBUTING.md](../../CONTRIBUTING.md): full
  pytest suite, Ruff lint/format and the oldest tox environment. Record actual
  counts, failures, environment and exact tested revision. Follow its additional
  manual CI guidance for support-matrix or PostgreSQL-locking changes.
- [ ] For each behavioural change, link input/expected-output cases. Reuse existing
  tests when they establish the contract and add missing regression coverage.
  Check permissions, failure paths and backwards compatibility where affected.
- [ ] For report UI changes, inspect rendered labels, category colours and responsive
  layout, and verify filtered totals across chart/cards/records. Do not present
  Python report tests as browser verification.
- [ ] Review agent metadata changes using the [registry procedure](../agent-registry.md#reviewing-a-registry-update),
  including effects on automatic serving, historical categories and CDN rules.
- [ ] Verify the release wheel and source archive in a clean environment, including
  installation, migrations, generation, retrieval and managed removal. Record the
  exact revision and environment. Keep deployment-specific acceptance and evidence
  with that deployment; do not treat local tests as live cache or vendor verification.

## Release record and artefacts

- [ ] Update version/changelog and installation/migration notes for the selected
  release. Clearly identify supported features, known limitations and deferred work.
- [ ] Build and inspect the distribution artefacts; verify packaged migrations,
  templates, static assets, licence and installation against the supported setup.
  Record deployment/cache checks separately from local package tests.
- [ ] Confirm the selected revision, reviewer and remaining issues are recorded
  before the release/tag/publication step. Follow the project's agreed release
  workflow; completing this checklist does not itself publish or deploy anything.
