# WordPress drift ledger

This ledger records reviewed upstream changes and intentional Wagtail differences.
Use it with the [current implementation matrix](wordpress-parity-status.md) and
[release checklist](release-checklist.md). Review owner: the maintainer preparing
the Wagtail release; identify the reviewer in that release's review record.

## Reviewed baseline and follow-ups

- **Client rendering evidence, 25 September 2026:** the
  [output review](acceptance/17-rendering-output-review.md) maps existing generic
  contracts to tests and adds bounded 350.org goldens. Offline donation defaults
  now reach the site's existing template through the optional add-on. This is
  site-specific integration work, not a new WordPress interval audit or client
  presentation sign-off; P24 remains open. D6/D12 implementation is recorded in
  scenario 01, while D9 and the listed output choices remain unresolved.
- **Last complete behavioural audit:** WordPress 1.7.0, commit
  `8ad646e826ccbc836863aca30745abe0c5198a53`, audited 7 September 2026 in the
  [historical audit](wordpress-parity-audit.md). This baseline is unchanged.
- **Interval review cursor:** `8ad646e826ccbc836863aca30745abe0c5198a53`.
  No later complete interval review is recorded yet. Start the next release's
  comparison here, using the follow-ups below to avoid losing prior findings.
- **Wagtail implementation snapshot:** `a89dab59a7c517ed619bcb26ab2ede1fd5e2deff`,
  inspected 22 September 2026. Existing tests are evidence for specific contracts,
  not an automated cross-platform parity suite.
- **Local upstream follow-up inspected 22 September 2026:** local `main` at
  `fa59f1639741fc51dd22688bc805285c9979b3cd` (plugin files identify 1.7.1), plus
  `fix/stats-card-colours` at `7f1d96f29581fff3e5895a6be154058c3b278730`.
  These are local Git observations; no remote fetch, release publication or
  deployment check was performed. The colour fix is not contained in local `main`.
- **Review boundary:** the entries below seed change-by-change triage. They do not
  advance the complete-audit baseline or claim that all current WP features are
  implemented. Before a release, verify the actual upstream target and complete
  the interval review in the checklist.

## Dispositions

| Disposition | Required evidence and follow-up |
| --- | --- |
| Port required | Describe the missing behaviour, link a tracked task and target milestone, and add acceptance criteria. Record implementation and verification before closing it. |
| Already covered | Link the Wagtail implementation and relevant tests or manual evidence. State any narrower scope; a similar feature name is insufficient. |
| Intentional difference | Explain the rationale and user-visible effect, link the design/contract and record any effect on historical data. |
| Deferred | Link the feature/task and target milestone, or explicitly state outside milestones. Do not count deferred work as implemented. |

Do not assign one of these dispositions to an unreviewed change. List it as
**Awaiting review** until evidence exists. Group formatting/merge/release metadata
only when the represented behaviour is accounted for elsewhere. A security or
data-loss fix needs prompt review rather than waiting for the next release.

## Upstream follow-ups

All entries below were inspected on 22 September 2026. P/D identifiers link to the
matrix or differences register; legacy issue references are not current issue URLs.

| ID / WordPress source | Disposition | Wagtail evidence and action |
| --- | --- | --- |
| U01 Card border colours: original local commit `e469b61`; rewritten branch commit `7f1d96f29581fff3e5895a6be154058c3b278730` | **Already covered** | [Report CSS](../src/wagtail_markdown_agents/static/wagtail_markdown_agents/report.css) shares `--agentmd-series` across purpose-tile borders, bars and legend. [Template](../src/wagtail_markdown_agents/templates/wagtail_markdown_agents/report_results.html) applies category classes. The earlier sparklines were removed after the 7-day dashboard made flat lines visually unhelpful; correlation labels remain. The two WP file versions were compared and match. Track merge/release status at the next review; do not call this released. P16/D08. |
| U02 GET-only counters and cache guidance: `041beeac189917733bb830067bd674e88fcb96f4` | **Already covered** | [Statistics tests](../tests/test_stats.py) exclude HEAD/HTML/errors/aggregates; [middleware tests](../tests/test_middleware.py) check HEAD headers without body/count. [Cache guide](cdn-caching.md#wordpress-cache-parity) already records this WP follow-up and the direct-export difference D04. Deployment evidence remains separate. |
| U03 Preserve colliding dotted frontmatter paths: `4e5622924ac0b7a9c83e0cdc94b2d15131496c8a` (WP #20) | **Already covered for current input model** | [Frontmatter](../src/wagtail_markdown_agents/rendering/frontmatter.py) preserves explicit keys rather than deriving leaf names; protected identity-key collisions are logged. [Tests](../tests/test_frontmatter.py) cover source precedence and key preservation. No ACF resolver exists. Carry the collision case into P05's v0.2 declarative-mapping acceptance; D05. |
| U04 Normalise taxonomy/post values in scalar and list positions: `e27b7d75f033d5460693aff8d784e77f03096f78` (WP #21) | **Already covered for supported Wagtail values** | One recursive [normaliser](../src/wagtail_markdown_agents/rendering/frontmatter.py) handles supported values; arbitrary objects fail explicitly. [Tests](../tests/test_frontmatter.py) include model-in-list round trips and unsupported objects. Wagtail Page values include title/permalink; this is not WP title-only output. D06. General taxonomy extraction remains P05/P20. |
| U05 LiteSpeed documentation: `41ea6be`, rewrap `e595b49` (WP #22) | **Already covered at contract level** | [Cache guide](cdn-caching.md) documents origin bypass, variation, optional LiteSpeed headers and verification in both request orders. WordPress-specific plugin settings and `.htaccess` snippets are not Wagtail defaults. No claim of equivalent live LiteSpeed verification. |
| U06 1.7.1 version/changelog `da2d63d`; WordPress tested-up-to metadata `e371ea3`; merge commits through local `fa59f16`; trailing-comma and documentation-ignore changes in the interval | **Intentional difference / metadata only** | Wagtail versions and supported frameworks are maintained independently in [pyproject.toml](../pyproject.toml) and [tox.ini](../tox.ini). Behaviour represented by these merges is tracked in U02–U05; formatting and PHP list trailing commas require no Python change. A WP tested-up-to edit is not evidence that Wagtail's support matrix passed. |
| U07 Dashboard, WordPress [#29](https://github.com/chancery-lane-project/wp-mfa-plugin/pull/29), reviewed in Wagtail [#20](https://github.com/350org/Wagtail-Markdown-for-Agents-and-Statistics/issues/20) on 23 September 2026 | **Implemented with deliberate differences** | [Wagtail report](../src/wagtail_markdown_agents/reports.py), [operator map](../src/wagtail_markdown_agents/data/operators.py) and [tests](../tests/test_report.py) implement the 7-day default, filtered leaders, operator cards and ranked top pages. The access-method breakdown now counts distinct pages. Wagtail retains mixed purposes and `export-url`; its independent registry also permits an attributed operator with Unknown purpose. Wagtail has custom dates but no separate All time preset. Maps remain separately maintained. Native Wagtail styling uses the 350.org palette. Merge and release status remain open. |

## Intentional differences register

These are existing documented decisions, not new behaviour introduced by this
ledger. Reconsidering one requires an explicit contract/design change and tests.

| ID / area | Decision and effect | Authority / evidence |
| --- | --- | --- |
| D01 Agent recognition and automatic serving | Independent reviewed registry, bounded product-token matching and separate `auto_markdown` policy. Robots.txt-only controls are not HTTP identities. The frozen WP list proves historical provenance, not active-list equality. | [Registry](agent-registry.md), [registry tests](../tests/test_agent_registry.py), [historical categories](../tests/test_categories.py). |
| D02 Unknown clients | All unrecognised clients share the empty unknown label; arbitrary UA fragments are not stored. Migration 0006 merges legacy unknown labels while preserving totals; originals cannot be recovered by reversing it. | [Statistics contract](agent-access-stats.md), [migration tests](../tests/test_stats_anonymization.py). |
| D03 Intent and history | Mixed purposes form a separate bucket counted once. Categories are derived at read time, so reviewed metadata changes can relabel history without changing stored counts. On-demand remains an estimate. | [Registry](agent-registry.md), [report tests](../tests/test_report.py), [category tests](../tests/test_categories.py). |
| D04 Direct exports and totals | Managed page-export GETs pass through Django and count as `export-url`. WordPress static uploads generally bypass its negotiator. Neither origin count includes CDN hits that bypass the application. Identical traffic need not give identical totals. | [Cross-platform counter table](cdn-caching.md#wordpress-cache-parity), [statistics tests](../tests/test_stats.py). |
| D05 Metadata keys and field extraction | Explicit metadata names are preserved; editor extras cannot replace identity keys, while trusted hooks have the documented final override. No automatic ACF dotted-path extraction; future mapping work must preserve collision handling. | [Frontmatter implementation](../src/wagtail_markdown_agents/rendering/frontmatter.py), [tests](../tests/test_frontmatter.py); P04/P05. |
| D06 Normalised values and authors | Supported Wagtail values have explicit conversions (Page → title/permalink, tag → name); unsupported objects raise instead of becoming class names. Optional owner is a public full name and is not assumed to be editorial author. | [Frontmatter implementation](../src/wagtail_markdown_agents/rendering/frontmatter.py), [tests](../tests/test_frontmatter.py). |
| D07 Serving, paths and defaults | Wagtail parses Accept quality values, applies a shared export policy, uses managed public URLs and hashes actual output. Generation defaults on; page-type selection defaults to all supported non-root types. These are documented adaptations, not an instruction to reproduce WP bugs. | [Design](design.md#known-wp-limitations-to-fix-not-inherit), [settings](../src/wagtail_markdown_agents/settings.py), [negotiation](negotiation.md), [manifest](manifest.md), audit settings table. |
| D08 Presentation | Native Wagtail UI and the 350.org palette. Category colours must be internally consistent; exact WordPress colours/layout are not required. Cloudflare-inspired additions must preserve P16's reporting contract and counting limits. | [Report CSS](../src/wagtail_markdown_agents/static/wagtail_markdown_agents/report.css), [dashboard contract](wordpress-parity-status.md#dashboard-changes-must-preserve-the-reporting-contract). |

## Adding and closing entries

The dashboard relationship and intentional differences are recorded in U07. Keep
both operator maps under separate review when either platform adds a label.

For each new entry record: stable ID, review date/reviewer, exact upstream commit
or version, behaviour, disposition, Wagtail evidence, linked task/milestone where
work remains, and merge/release status. Use a local P-ID while issue mapping is
pending; do not invent current GitHub issue links from legacy numbers.

When implementing a port, keep the original finding and append the resolving
commit and verification result. For a cherry-pick/rebase/squash, retain the original
and replacement commit identities and compare the relevant diff. Merely observing
a fix branch does not advance the upstream baseline. Planned features in the matrix
are deferred parity work even when no post-baseline upstream commit introduced them.
