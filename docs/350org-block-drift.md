# 350.org block drift check

The **350.org block drift** workflow compares the real site's block definitions
and their Markdown renderer coverage with a reviewed snapshot. It runs only via
`workflow_dispatch`, at a chosen `350org/wagtail-wtr-350` branch, tag or commit.
It has no push, pull-request or scheduled trigger and is separate from package CI.

## Baseline

[`fixtures/wtrx-blocks.json`](fixtures/wtrx-blocks.json) was generated on
25 September 2026 from the site's `improvements` revision
[`199776652df68c8b74a51c0493f503228de23cd9`](https://github.com/350org/wagtail-wtr-350/commit/199776652df68c8b74a51c0493f503228de23cd9),
with the package's 350.org add-on enabled. The initial package basis was PR #32
(`82ddae695ec33c0f75909f1ba8fd14c9de732a6a`); the snapshot was then refreshed for
the [offline donation correction](acceptance/17-rendering-output-review.md#donation-finding-and-correction)
in #4/#14. Only donation's dispatch and renderer changed. It contains all 31 body block types
across HomePage, ContentPage, IndexPage, Post and Blogs. Blogs has no body blocks
under the add-on's page-field mapping.

The snapshot records definition metadata, not site content or a copy of the
site's implementation. Its source is the 350.org repository above. The comparison
uses `agentmd_blocks --compare` and the normal renderer registry: 20 block types
use the add-on, three use the core and eight use template fallback. The report
labels both core and bundled add-on renderers as `built_in`; the full renderer
paths distinguish them.

The checked environment is Python 3.13, Django 5.2.17, Wagtail 7.4.3,
wagtail-localize 1.14.5 and wagtailmedia 0.19.1. The four framework/media versions
are pinned in `scripts/wtrx-drift-constraints.txt`. Other dependencies follow
the selected site's requirements; each hosted run records their installed versions
and both repositories' exact commits. A dependency conflict requires review
rather than silently changing this baseline.

## Run on demand

The source repository is private. Configure the package repository secret
`WTRX_SOURCE_READ_TOKEN` with a fine-grained token that has **Contents: read**
access to `350org/wagtail-wtr-350`. The package repository's default Actions token
does not grant access to the other private repository. Neither checkout persists
credentials. Select only trusted source refs: installing dependencies and loading
models executes code from the selected repository.

From Actions, select **350.org block drift**, then **Run workflow**, and choose
the package branch and `site_ref`. The default site ref is the pinned baseline;
choose `improvements` to check that branch's current definitions. With GitHub CLI:

```bash
gh workflow run wtrx-block-drift.yml --ref main -f site_ref=improvements
```

The workflow must first exist on the repository's default branch. If it has been
disabled, a maintainer can enable it with
`gh workflow enable wtrx-block-drift.yml`. Adding this workflow does not enable
or dispatch the existing **CI** workflow.

No database, media, production settings or external-service credentials are needed.
The helper imports only the site's base settings, substitutes an empty in-memory
database and dummy cache, and enables the add-on. It does not load `.env` or local
settings, migrate, render pages or generate exports. Network connections and
database queries during setup/reporting raise an error. Installation and checkout
still need network access.

## Run locally and review changes

With a trusted source checkout available, from the package repository:

```bash
uv venv --python 3.13 /tmp/agentmd-wtrx-drift
uv pip install --python /tmp/agentmd-wtrx-drift/bin/python \
  -c scripts/wtrx-drift-constraints.txt . /path/to/wagtail-wtr-350
/tmp/agentmd-wtrx-drift/bin/python scripts/wtrx_block_drift.py /path/to/wagtail-wtr-350
```

The command exits zero for a match, non-zero for drift or setup failures.
It reports added/removed blocks, changed renderers, nested field changes and
reordering, template hints, block locations and exported page types. A deliberate
addition to a nested image block was verified to fail the check; an unchanged
checkout matches with both the existing environment and a fresh dependency install.

When it fails, inspect the selected source revision, adjust the add-on and
repository-owned fixtures as needed, and review the rendered output separately.
After those changes are accepted, generate a proposed snapshot into a temporary
file, then inspect its diff before replacing the baseline:

```bash
/tmp/agentmd-wtrx-drift/bin/python scripts/wtrx_block_drift.py \
  /path/to/wagtail-wtr-350 --json > /tmp/wtrx-blocks-proposed.json
diff -u docs/fixtures/wtrx-blocks.json /tmp/wtrx-blocks-proposed.json
```

Update the source revision and dependency evidence in this document with the
snapshot. Do not refresh it automatically on a failed comparison.

## Limits

This is a definition/dispatch check, not client rendering acceptance. It reads
selected body StreamFields and statically referenced template hints. It does not
compare template text byte-for-byte, ordinary field defaults/choices, page-level
hero hooks or non-StreamField metadata, and it does not execute rendering queries
or value-dependent template paths. The add-on's page mapping intentionally keeps
hero CTA fields outside this report. A match cannot establish that all site
behaviour or output is unchanged. Use the [add-on tests](350org-addon.md#tests)
and the agreed #14 fixture/output matrix for those checks.

The helper and dependency-install steps were exercised locally against the pinned
source, including successful unchanged comparisons and failed field-change,
database-access and network-access probes. The workflow passed `actionlint`.
No hosted run or private-repository secret configuration is claimed.
