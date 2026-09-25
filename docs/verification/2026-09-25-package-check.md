# Installed-package check — 25 September 2026

**Result: passed.** Built and installed commit
`769aba85c9f8d2093ae1a0a9db0429199bf4119e` from `main`. No packaging or
installation defects were found in this bounded check. The package remains
`0.1.0.dev0`; no version change, tag, publication or deployment was performed.

## Environment and isolation

- Python 3.13.5, Django 5.2.17, Wagtail 7.4.3, SQLite.
- markdownify 1.2.3, markdown-it-py 4.2.0, PyYAML 6.0.3.
- A new virtual environment installed the wheel and resolved dependencies, with
  Django and Wagtail pinned to the versions above. It did not inherit an existing
  environment's packages. `uv pip check` confirmed all 38 installed packages were
  compatible. The [evidence record](2026-09-25-package-check.json) lists them.
- The source came from `git archive HEAD` with a clean working tree. `uv build`
  built the source archive, then built the wheel from that archive.
- The synthetic host used the packaged `sandbox` fixtures copied from the source
  archive into a separate temporary directory. Its settings disabled `wtrx`, the
  optional add-on and the test event hooks, selected `testapp.ArticlePage`, and
  used an isolated database and export directory.
- Runtime imports and template/static discovery were asserted to come from the
  new environment's `site-packages`. Neither the repository nor its `src`
  directory supplied package imports.
- Requests used Django's test client. Socket connections were blocked during the
  smoke check; only dependency installation needed network access.

## Artifact inspection

All 79 runtime package files matched the exported source byte for byte. These
include all six migrations, four templates, the report stylesheet, the agent
registry and optional 350.org add-on. Wheel metadata declares
`GPL-3.0-or-later`, and its licence file matches the repository.

The wheel excludes the sandbox, tests and documentation. The source archive
includes installation/release guidance, the donation golden and its synthetic
template, and contains no SQLite databases, bytecode or virtual environment.

| Artifact | SHA-256 |
| --- | --- |
| `wagtail_markdown_for_agents-0.1.0.dev0-py3-none-any.whl` | `cd9785b12e0c10254bb91ace6e153d8d647f980408a04e5607a9c682bb9a41e2` |
| `wagtail_markdown_for_agents-0.1.0.dev0.tar.gz` | `4ff3148c6ac45c2fe5a88984a38622be05cf0a2665e3d9a64ac39ee50e8e654b` |

## Installed-wheel checks

All twelve checks passed:

| Check | Evidence |
| --- | --- |
| Isolated imports | Package loaded from the new environment with the optional add-on absent. |
| Fresh installation | All migrations through `0006_anonymize_unknown_agents` applied; system checks reported no issues; no migration drift. |
| Packaged assets | All four templates and the stylesheet resolved inside `site-packages`. |
| Automatic generation | Publishing a synthetic article created a readable managed export. |
| Installed commands | Forced generation succeeded; status reported one eligible, current export with no failures or pending cleanup. |
| Markdown retrieval | Query, Accept header, GPTBot header and direct-export requests returned identical Markdown. |
| HTML and discovery | Browser request returned HTML with an alternate HTTP Link; the frontend tag rendered exactly one Markdown alternate. |
| Statistics and navigation | Four page GETs produced four increments; HEAD, root index and `llms.txt` added none. Both discovery documents included the article. |
| Draft isolation | Forced generation after saving a newer draft retained the published output. |
| Withdrawal | A password restriction removed the export; direct requests returned 404 after restriction and after unpublishing. |
| Data upgrade | At schema 0005, seeded unknown and recognised labels; applying 0006 merged unknown labels and retained all 26 seeded hits. |
| Removal | Managed deletion cleared export ownership/files; reversing package migrations removed its database tables. |

## Evidence and limits

The [JSON record](2026-09-25-package-check.json) preserves checks, dependency
versions and artifact inventory/hashes. Temporary local artifacts, the smoke
script/settings and logs are in `/tmp/agentmd-rc-769aba8-95f87e/`; that directory
is disposable and is not a published artifact location.

This is installed-wheel evidence for one supported stack, with synthetic host
models and SQLite. The migration upgrade used the historical package schema on
the same framework versions; it was not an upgrade of a production database.
The optional add-on's files were inspected, but it was not enabled in this core
installation check. Its previously passing tests and output evidence are recorded
in the [rendering review](../acceptance/17-rendering-output-review.md).

The full 1,647-test suites on the development and oldest-supported environments
had already passed for this source revision; they were not repeated here. This
check does not establish PostgreSQL deployment, CDN behaviour, genuine vendor
fetching or client output acceptance. Remaining release coordination stays in
[issue #5](https://github.com/350org/Wagtail-Markdown-for-Agents-and-Statistics/issues/5).
