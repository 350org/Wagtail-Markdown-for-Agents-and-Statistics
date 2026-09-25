# WordPress parity: current implementation

Reviewed 22 September 2026 against Wagtail commit
`a89dab59a7c517ed619bcb26ab2ede1fd5e2deff` (`0.1.0.dev0`). Update this snapshot
when implementation changes. This is implementation coverage, not full product
parity or client acceptance.

The P16 dashboard row was updated on 24 September 2026 for the Top pages and
access-method tables; the earlier full-suite evidence below remains tied to the
22 September snapshot.

The [historical audit](wordpress-parity-audit.md) pins WordPress 1.7.0 at
`8ad646e826ccbc836863aca30745abe0c5198a53` and records the detailed behavioural
requirements. Its original coverage column describes planning in September's
pre-audit snapshot. Use this matrix for current implementation and the
[drift ledger](wordpress-drift-ledger.md) for subsequent upstream changes and
deliberate differences. [design.md](design.md) remains the design authority.

## Status definitions

- **Implemented**: the stated Wagtail scope has code and existing test coverage.
  It does not imply identical output, UI, deployment verification or WP internals.
- **Partial**: some behaviour exists; the missing part is stated explicitly.
- **Planned**: no complete implementation; the release is a roadmap target.
- **Outside milestones**: recorded scope without a release commitment.
- **Addition**: Wagtail-specific capability, not evidence of WordPress parity.

Evidence links identify maintained tests and contracts. They are not a claim that
every acceptance scenario, database or live deployment was rerun for this document.
Legacy issue numbers in the audit require mapping to the current repository;
matrix IDs below provide stable local tracking until that mapping is completed.

## Feature matrix

| ID / capability | Current state and scope | Evidence / remaining target |
| --- | --- | --- |
| P01 Negotiation | **Implemented:** query → Accept → reviewed automatic-UA policy; eligible existing exports; GET/HEAD behaviour and HTML fallback. Accept parsing and recognition deliberately differ from WP. | [Negotiation acceptance](acceptance/10-content-negotiation.md), [tests](../tests/test_negotiation.py), [middleware tests](../tests/test_middleware.py); D01/D07 in the ledger. |
| P02 Export eligibility and revocation | **Implemented:** published revisions, inherited restrictions, type/site policy, page exclusion, unpublish/delete/move and after-commit generation. Revocation stays active with generation disabled. | [Lifecycle](publish-lifecycle.md), [eligibility tests](../tests/test_eligibility_lifecycle.py), [path tests](../tests/test_path_lifecycle.py). Client `hide_from_search` policy remains open under P24. |
| P03 Page rendering | **Implemented for supported page types:** ordered StreamField/RichText fields, block renderers, HTML cleanup and golden output. Requires a StreamField; form pages and rich-text-only pages are unsupported. | [Contract](page-rendering.md), [page tests](../tests/test_page_rendering.py), [golden tests](../tests/test_golden.py). Client rendering choices remain P24. |
| P04 Frontmatter and YAML | **Implemented:** core metadata, optional hierarchy/owner, flat tags, explicit extra keys, hooks and recursive value normalisation. No automatic dotted ACF field extraction. | [Implementation](../src/wagtail_markdown_agents/rendering/frontmatter.py), [tests](../tests/test_frontmatter.py); D05/D06. |
| P05 Configured fields and images | **Partial:** ordered body fields, hooks and media renderers exist. Declarative nested/relationship extraction, field headings and per-type featured-image/frontmatter mappings remain **v0.2**. | [Rendering contract](page-rendering.md), [media tests](../tests/test_media_renderers.py); audit A03, legacy #39. |
| P06 Internal links | **Implemented:** current owned public export URLs, relocated paths, fragments, code preservation, unavailable-target fallback and unresolved-link events. | [Contract](internal-links.md), [tests](../tests/test_links.py); D07 and client D6 under P24. |
| P07 Storage and public routes | **Implemented:** managed publication over Django storage, host/path checks, public page/discovery routes and shared eligibility checks. Direct page GETs record `export-url`. | [Storage](storage-writer.md), [routes](public-export-routes.md), [writer tests](../tests/test_writer.py), [serving tests](../tests/test_serving.py); D04. |
| P08 Discovery and cache headers | **Implemented:** HTML alternate Link/Vary, template tag, response hooks and configuration checks. CDN configuration and origin/edge reconciliation are deployment work. | [Guide](discovery-headers.md), [tests](../tests/test_discovery.py), [cache guide](cdn-caching.md), [checks](../tests/test_checks.py). |
| P09 Indexes | **Partial:** root/directory indexes, page-body preservation, collisions and batched finalisation implemented. Type listings remain **v1.0**; taxonomy archives are P20. | [Guide](indexes.md), [tests](../tests/test_indexes.py); audit A10, legacy #45. |
| P10 Manifests and incremental work | **Partial:** per-site manifests hash actual output, preserve partial scopes and publish successful state. Generation supports freshness skipping, force and missing-file repair. Hash-based incremental commands and public `changes.json` remain **v1.0**. | [Manifest guide](manifest.md), [manifest tests](../tests/test_manifest.py), [command tests](../tests/test_commands.py); audit A07, legacy #41. |
| P11 Management commands | **Partial:** scoped generate/index/status/delete, dry runs, force and explicit statistics pruning implemented. Bundle, taxonomy and durable-job operations follow their features. | [Command contract](management-commands.md), [tests](../tests/test_commands.py), [prune tests](../tests/test_prune_stats.py); audit A07/A13. |
| P12 Editor controls | **Partial:** action-menu exclusion form and optional editor checkbox implemented. Export state/time, single-page regenerate and no-write Markdown preview remain **v0.2**. | [Exclusion acceptance](acceptance/14-page-exclusion-settings.md), [panel acceptance](acceptance/15-editor-exclusion-panel.md); audit A04. |
| P13 Background generation jobs | **Planned, v0.2:** only a synchronous enqueue seam exists. Durable bulk-job progress, locks, heartbeat, recovery, bounded errors and debouncing are not implemented. | [Current seam](../src/wagtail_markdown_agents/tasks.py); audit A05, legacy #40. |
| P14 Runtime settings and rebuild notices | **Partial:** deployment settings and system checks implemented. Runtime editing, settings UI and configuration-staleness/regeneration workflow remain **v0.2**. | [Settings](../src/wagtail_markdown_agents/settings.py), [checks](system-checks.md); audit A03/A06, legacy #38/#75. |
| P15 Daily access counters | **Implemented:** atomic UTC counters for successful page Markdown GET selection, bounded known/unknown labels, retained deleted-page history and explicit pruning. | [Contract](agent-access-stats.md), [tests](../tests/test_stats.py), [anonymisation tests](../tests/test_stats_anonymization.py); D01–D04. |
| P16 Statistics report | **Implemented:** 7-day default, combined date/page/agent/operator/method/intent filters, headline leaders, operator cards, ranked top pages, agents by access method, pagination, purpose chart, six trend tiles and daily records. Shared category colours drive purpose tiles, chart and legend. | [Report tests](../tests/test_report.py), [CSS](../src/wagtail_markdown_agents/static/wagtail_markdown_agents/report.css); D03/D08 and U01/U07 in the ledger. |
| P17 ZIP/OKF bundle | **Planned, v1.0:** no bundle builder, download or bundle lifecycle implementation. An `okf_version` frontmatter value does not establish bundle support. | [Design](design.md#bundle--ard--okf-v10); audit A10, legacy #42/#43/#46. |
| P18 ARD catalog | **Planned, v1.0:** no catalog generation, catalog hook or `.well-known` route. | [Design](design.md#bundle--ard--okf-v10); legacy #44. |
| P19 Public extension surface | **Partial:** core policy/path, rendering/frontmatter, response/discovery, index/category hooks and generation/deletion/link signals exist. Full 22-point equivalence requires the **v1.0** audit; taxonomy, catalog and job-budget counterparts depend on their features. | [Historical hook inventory](wordpress-parity-audit.md#public-extension-surface), [signals](../src/wagtail_markdown_agents/signals.py); audit A08, legacy #47. |
| P20 Taxonomy archives | **Outside milestones:** no general taxonomy export/serve/delete or Topics workflow. Flat tags and project hooks do not supply archive parity. | [Historical audit](wordpress-parity-audit.md); legacy #49. |
| P21 Multi-site operations | **Partial / Wagtail addition:** site-aware paths, policy, explicit command selection and cross-site tests exist. Full multi-site product support remains **v0.2** in the roadmap. | [Policy](../src/wagtail_markdown_agents/export/policy.py), [command tests](../tests/test_commands.py); legacy #37. |
| P22 Removal and operations | **Partial:** explicit managed deletion and installation/removal guidance exist. Worker/job cleanup follows P13; package removal does not trigger destructive cleanup. | [Installation/removal](../INSTALL.md), [commands](management-commands.md); audit A13. |
| P23 Additional discovery and verification | **Addition:** `llms.txt`, deployment traffic simulator and Cloudflare expression generator. These do not establish WP parity. | [llms.txt](llms-txt.md), [simulator](agent-simulator.md), [Cloudflare tests](../tests/test_cloudflare.py). |
| P24 Client and deployment acceptance | **Open v0.1 evidence/decisions:** D9 `hide_from_search`, client output sign-off and remaining live/cache evidence. D6 private-link handling and D12 precedence are implemented. Bounded add-on goldens and the donation-default correction are implementation evidence, not client acceptance. | [Output review and open decisions](acceptance/17-rendering-output-review.md), [transfer review](transfer-readiness.md), [scenario 01](acceptance/01-contentpage-end-to-end.md), [bounded live evidence](verification/2026-09-21-bounded-live-run.md). |

## Dashboard changes must preserve the reporting contract

Cloudflare is a presentation reference. WordPress remains the reviewed behavioural
reference, subject to the documented differences. The Wagtail dashboard implements
the [issue #20](https://github.com/350org/Wagtail-Markdown-for-Agents-and-Statistics/issues/20)
summary, operator cards and 7-day default based on the recorded WordPress #29
outcome. No release milestone is assigned.

For any dashboard change, preserve:

- Combined filters, inclusive UTC dates, bucket boundaries, pagination and separate
  empty/error states. Summaries must cover all matching records, not just one page.
- Successful page Markdown GET selection as the counting boundary; no inferred
  failure rate, byte consumption, completed delivery or total edge traffic.
- Existing intent chart, detailed records, trend semantics and the on-demand estimate
  label. Mixed and unknown counts must reconcile with the total.
- A single category mapping for chart, legend and purpose-tile colours, with text labels.
  The 350.org palette need not match the WordPress palette.

[Report tests](../tests/test_report.py) cover combined-filter consistency,
whole-report totals across pagination, shared classification snapshots and mixed
purposes. Visual changes also require a rendered check of category colours, labels
and responsive layout; those Python tests are not a visual comparison suite.

On 23 September 2026 the dashboard was rendered in the local Wagtail sandbox at
desktop and 390px widths. The narrow view had no page-level horizontal overflow;
selecting an OpenAI card changed the headline, purpose chart, agent choices and
records to the same filtered set. This was a local visual check, not a production
deployment check.

On 24 September 2026 the Top pages, access-method and Daily records sections were
rendered in the local sandbox at desktop and 390px widths. The three seeded pages
showed 75%, 25% and <1% shares, and the narrow page had no horizontal overflow.

## Verification of this documentation review

Source inspection and local checks by Codex, 22 September 2026, at the Wagtail
revision above with these documentation-only additions:

| Environment | Result |
| --- | --- |
| Python 3.12.9 / Django 6.0.8 / Wagtail 7.4.3 | 1,425 passed in the full run; three loopback-server tests were sandbox-blocked and then passed with loopback access. |
| Python 3.11.15 / Django 4.2.30 / Wagtail 6.3.8 (`py311-dj42-wagtail63`) | 1,425 passed in the full tox run; the same three sandbox-blocked tests passed on a targeted rerun in that environment. Ten dependency deprecation warnings in the full run. |

This is combined full-run and targeted-rerun evidence, not two uninterrupted green
suite runs. Ruff lint/format, documentation link/anchor checks and whitespace checks
passed. No runtime code changed, and no new browser, live deployment, PostgreSQL or
cross-platform execution was performed. These results do not advance the WP audit
baseline or resolve the client decisions under P24.
