# WordPress → Wagtail port audit

Audited 7 September 2026. This records behavioural requirements, not translated PHP.
Read alongside [design.md](design.md), the architecture authority, and the
[licensing and attribution policy](../CONTRIBUTING.md#licensing-and-attribution).

This is a historical audit: its pre-audit coverage and original verification counts
are not current implementation status. Use the [current matrix](wordpress-parity-status.md)
for implemented/planned scope and the [drift ledger](wordpress-drift-ledger.md) for
later WordPress changes and intentional differences. Keep this pinned reference
when advancing the release review revision.

**Product parity is not the v0.1 scope.** v0.1 does not cover the complete WordPress
feature set. In particular, OKF bundles and ARD catalogs are out of scope for v0.1,
alongside multi-site, runtime-editable agent lists and taxonomy exports. Roadmap gaps
below are not v0.1 release blockers.

Issue numbers in this historical audit refer to the original repository. They are
unlinked legacy references; new issue numbers must be mapped during migration.

## Baseline and result

The reference is **Markdown for Agents and Statistics 1.7.0**,
Git origin `chancery-lane-project/wp-mfa-plugin`, commit
[`8ad646e826ccbc836863aca30745abe0c5198a53`][wp]. The two uncommitted changes in
`Core/Options.php` and `Negotiate/AgentDetector.php` only add trailing commas.
The comparison includes those working files. No WordPress files were changed.

The Wagtail baseline is commit `1614b3415a240ce9e3a6f88a905aab14ce3069c3` plus the
working-tree documentation/comment changes from the preceding review. GitHub issues
#1–#71 were read, including their bodies and milestones. The coverage assessment below
describes that pre-audit snapshot; the GitHub sync record tracks the subsequent updates.

The core concept is captured, **but the previous plan did not capture the whole
plugin**. The largest omissions are public access to export artefacts, correct link
bases for negotiated responses, generation job management, editor preview/regenerate
controls, custom field/frontmatter extraction, settings-driven rebuilds, and several
extension points. Some smaller requirements were already in issues but absent from
the design. The amendments and backlog below make those requirements explicit.

Coverage in a plan is not implementation coverage. Wagtail currently has the package
and sandbox, `PageAgentSettings` and its migration, settings/data, the renderer
registration decorator, custom signal objects, an inline task seam and six smoke
tests. Renderer dispatch, frontmatter, export policy/writer, negotiation, management
commands and reporting are still stubs or absent. No end-to-end parity is claimed.

## Feature coverage

“Covered” means explicitly planned in the pre-audit design or issue bodies. “Partial”
means a feature heading exists but material behaviours are missing. “Gap” means no
explicit equivalent was found. The backlog IDs record the additions from this audit.

| WordPress behaviour and evidence | Coverage before audit | Wagtail disposition / tracking |
| --- | --- | --- |
| Query `md`/`markdown` → Accept → UA precedence; stable method labels ([negotiator][wp-neg]) | Covered | v0.1 legacy #25; properly parse Accept, including explicit ranges and `q=0`, rather than reproducing the WP substring check. |
| Case-insensitive, first-match UA detection; classification independent of the UA serving toggle ([detector][wp-agent]) | Partial | v0.1 legacy #25, legacy #33, legacy #34; A09/A11 specify labelling and data provenance. |
| Serve existing files only; missing files fall through; published/unrestricted/enabled/non-excluded checks; path containment ([negotiator][wp-neg], [policy][wp-policy]) | Covered | v0.1 legacy #16, legacy #26, legacy #30, legacy #68; apply policy to every public serving path. |
| Cache-bypass headers, configurable policy header, discovery in HTML headers and `<head>` ([negotiator][wp-neg]) | Partial | v0.1 legacy #26–#29, legacy #59; A01/A08 specify alternate URLs, header overrides and host-specific headers. |
| WP only negotiates frontend content, excluding AJAX/REST wiring ([plugin wiring][wp-plugin]) | Partial | A01: public page routes only; GET/HEAD semantics; exclude admin, previews, APIs and form submissions. |
| Public upload URLs expose the export corpus, indexes, manifests and bundle ([README][wp-readme]) | Gap | A01: explicit Wagtail artefact routes; storage outside media does not itself create public URLs. |
| HTML cleanup removes script/style contents; converter handles headings, emphasis, lists, entities, image spacing, tables/captions and code fences/language ([converter][wp-converter], [cleanup][wp-cleanup]) | Partial | v0.1 legacy #9–#15; A02 adds cleanup and output fixtures to block-type coverage. |
| Configured body fields replace the normal body, preserve order, and use field labels as headings; ACF groups/repeaters and relationship values ([generator][wp-gen], [field resolver][wp-fields]) | Partial | A03 extends v0.2 legacy #39; use declared Django/Wagtail fields and renderers, not an ACF interpreter. |
| Core YAML fields, taxonomy names, flat deduplicated tags, timestamps, hierarchy and author ([frontmatter][wp-fm]) | Covered | v0.1 legacy #13; A02/A09 clarify serialisation, public metadata and UTC. |
| Featured image URL and alt text; configured per-type frontmatter; optional relative image URLs ([frontmatter][wp-fm]) | Gap | A03: v0.1 frontmatter hook supports project mappings; declarative mappings in v0.2. Wagtail has no universal featured-image field. |
| Safe YAML scalar/list encoding and quoting ([YAML tests][wp-yaml-tests]) | Partial | A02: v0.1 legacy #13, legacy #15; parse output back to verify types and multiline values. |
| Internal links, fragments, query handling, old slugs, unresolved reasons, memoised resolution; images excluded ([rewriter][wp-links], [resolver][wp-resolver]) | Partial | A01/A02: v0.1 legacy #14; account for the URL used to retrieve the document, and honour relocated exports. |
| Auto-generation toggle; cleanup remains active with auto-generation disabled; deletion/status changes refresh dependent indexes ([plugin wiring][wp-plugin], [generator][wp-gen]) | Partial | A06: v0.1 legacy #23, legacy #69, legacy #70; explicit auto-generation setting and after-commit generation. |
| Root/type/taxonomy directory indexes, counts/excerpts, dirty-scope coalescing, empty corpus and reserved names ([index generator][wp-index]) | Partial | v0.1 legacy #20; type listings v1.0 legacy #45; A01/A10 cover page-body preservation, collisions and batch finalisation. |
| Taxonomy archive export/serve/delete, metadata, term counts, descriptions, eligible post listings, optional Topics section ([taxonomy][wp-tax], [generator][wp-gen]) | Deliberately deferred | legacy #49, outside milestones; grouped taxonomy metadata and Topics are recorded under A03, not silently equated with flat tags. |
| Per-type manifests with document IDs/paths/hashes/counts/status and export summaries ([manifest][wp-manifest]) | Covered at feature level | v0.1 legacy #22; A07 specifies which data is hashed and the actual successfully exported set. Wagtail manifests are per site. |
| Incremental generation, unchanged skips, deletion deltas and first-export marker ([CLI][wp-cli], [manifest][wp-manifest]) | Partial | A07: v1.0 legacy #41 plus command criteria in legacy #24; missing files, failed writes and partial-scope exports need tests. |
| Single-object/type/all generation/deletion, dry runs, progress, status, indexes, bundle and stats prune commands ([CLI][wp-cli]) | Partial | A07/A13 extend legacy #24, legacy #36, legacy #46; map every command/flag below. |
| Editor exclusion, export existence/time, single-page regenerate and no-write Markdown preview ([meta box][wp-metabox], [admin][wp-admin]) | Partial | Only exclusion is explicit in legacy #17/legacy #18; A04 adds the remaining controls in v0.2. |
| Admin bulk generation of all/type/taxonomy scopes with progress surviving tab closure ([admin][wp-admin], [jobs][wp-jobs]) | Gap | A05, v0.2; legacy #40 covers a backend, not a durable job model or admin workflow. |
| Cursor batches, per-item errors, bounded error history, exclusive locks, heartbeat, stale-job recovery and scheduling failure handling ([job tests][wp-job-tests]) | Gap | A05 extends legacy #40 with observable/resumable job behaviour using the chosen task system. |
| Settings sanitisation and tab preservation; notices flag types needing regeneration and clear after successful stages ([settings][wp-settings], [regen tracker][wp-regen]) | Partial | A03/A06, v0.2 legacy #38/legacy #75; v0.1 status covers basic counts, missing exports and errors. Configuration staleness is outside the engagement. |
| UTC daily hit counters, page/agent/method/date filters, pagination, presets, intent charts and trend tiles ([stats][wp-stats], [report][wp-report]) | Covered at feature level | v0.1 legacy #32–#36, legacy #66; A09 records precise semantics and missing acceptance cases. |
| Optional ZIP, stable filename/URL, relative internal links, long paths, manifests, stale detection and final rebuild after bulk generation ([bundle][wp-bundle]) | Covered at feature level | v1.0 legacy #42, legacy #43, legacy #46; A10 adds portable storage publication and privacy invalidation. |
| ARD catalog includes host, entry identity, display/description, type/mediaType and bundle URL; customisable; manual deployment ([catalog][wp-ard]) | Covered at feature level | v1.0 legacy #44; Django URL inclusion replaces manual placement, preserves existing host `.well-known` routes, advertises only an available bundle. |
| Deactivation clears jobs/locks; uninstall removes options/stats/events, retains Markdown, optionally removes bundle ([deactivation][wp-deactivate], [uninstall][wp-uninstall]) | Gap | A13: document explicit Django lifecycle operations; never tie destructive cleanup to importing/removing the package. |
| Public filters/actions ([source inventory](#public-extension-surface)) | Partial / incorrect count | A08, legacy #47: **17 filters + 5 actions = 22**, not 17 combined. Internal cron events are separate. |
| `llms.txt`, inherited restrictions, multi-site host trees, block registry and remote storage | Wagtail additions | Keep legacy #7–#12, legacy #19, legacy #21, legacy #37, legacy #70; these are not evidence of WP parity. |

## Settings and defaults

All 13 top-level keys in WordPress `Options::get_defaults()` are accounted for here.
Names for new Wagtail settings are design proposals until the corresponding feature
lands; the existing `settings.DEFAULTS` does not implement them yet.

| WordPress option / default | Wagtail equivalent or deliberate difference |
| --- | --- |
| `post_types = ['post', 'page']` | `PAGE_TYPES`; currently `None` means all non-root page types. This is a broader default and must be prominent in setup guidance. |
| `export_dir = 'wp-mfa-exports'` | `STORAGE` alias or `BASE_DIR / 'markdown_export'`; hostname-prefixed storage keys, plus explicit public routes (A01). |
| `auto_generate = false` | A06 proposes `AUTO_GENERATE = True` for the existing publish-driven Wagtail workflow, with a documented off switch. Revocation remains active. |
| `include_taxonomies = true` | Flat `tags` is already planned; grouped taxonomy/snippet metadata needs explicit project field mappings (A03). Disabling grouped metadata must not disable flat tags. |
| `include_hierarchy = false` | `INCLUDE_HIERARCHY = False`; do not expose restricted/excluded related-page metadata. |
| `include_author = false` | `INCLUDE_OWNER = False`; public display name only. Owner and editorial author are not universally the same field. |
| `relative_image_paths = false` | Absolute image/document URLs by default; custom renderer/frontmatter hook can opt into other URL policies. No automatic media copying is promised. |
| `include_taxonomy_topics = false` | Optional project renderer/post-render hook; general Topics/archive support follows legacy #49, outside milestones. |
| `bundle_enabled = false` | v1.0 opt-in bundle setting; no separate requirement to enable manifests, which are core in Wagtail. |
| `post_type_configs = {}` | `PAGE_FIELDS` for bodies plus frontmatter hooks/`extra_frontmatter`; A03 adds declarative frontmatter, labels, nested/repeated field and featured-image mappings in v0.2. |
| `delete_files_on_uninstall = false` | Explicit maintenance/removal instructions and commands (A13). WP actually retains the Markdown tree even when true; only the bundle is optionally deleted. |
| `ua_force_enabled = true` | `NEGOTIATE_USER_AGENT = True`; affects serving, not stats identification. Runtime editing in v0.2 legacy #38. |
| `ua_agent_strings = 69 entries` | Superseded on 22 September 2026 by the independent [agent registry](agent-registry.md). The pinned WordPress fixture now verifies historical categories only; active identities and serving policy are reviewed separately. |

WP also has filter-defined response headers and intent categories, and a CLI prune
default of 90 days. Wagtail must provide the retention default in deployment settings
for v0.1; runtime editing is a v0.2 enhancement, not a dependency of the prune command.

## Public extension surface

These are the **22 unique literal plugin-prefixed filter/action names invoked by the
source**. The WP README omits the export-path filter from its table. Cron callbacks
such as bundle rebuild and job processing/watchdog are implementation events, not
additional content customisation APIs. The core WordPress `the_content` hook is
accounted for by the field/block rendering pipeline rather than copied.

Each row specifies the data/context the Wagtail equivalent must expose. “Hook” names
not already in the design are descriptive roles, not newly implemented Python APIs.
Output-affecting hooks need deterministic ordering and a documented return contract.

| WordPress name (prefix `markdown_for_agents_`) | Kind and input/event | Wagtail equivalent / disposition |
| --- | --- | --- |
| `serve_enabled` | Filter: enabled, post | Export-policy hook with page context; deliberately unified across export, links, discovery and serving. A request-specific serving veto must remain separate from cacheable export eligibility. |
| `serve_post_types` | Filter: enabled types | `PAGE_TYPES` plus type-policy hook where dynamic control is needed; document unified policy instead of WP's serving-only scope. |
| `serve_taxonomies` | Filter: enabled | Deferred with legacy #49. |
| `frontmatter` | Filter: mapping, post | `construct_markdown_frontmatter`, including page context and side-model data. |
| `taxonomy_frontmatter` | Filter: mapping, term | Deferred with legacy #49. |
| `pre_convert` | Filter: HTML, post | Pre-conversion hook for rich-text/raw/template HTML, with page/block context; block renderers cover structured values. |
| `post_convert` | Filter: Markdown, post | Page post-render hook after body assembly and before final link processing/serialisation. |
| `converter_options` | Filter: options | Converter-options hook in legacy #12; markdownify options, not PHP library option names. |
| `export_path` | Filter: path, post | `export_path`; validate output and honour it in writing, serving, discovery, indexes, manifests, links and deletion. |
| `flat_tags` | Filter: tags, post | Flat-tags hook before final frontmatter hook; preserving this stage allows independent extensions. |
| `index_content` | Filter: content, relative path | Index-content hook with path/site context; no loss of parent page body. |
| `content_signal` | Filter: header string | `CONTENT_SIGNAL` and optional response hook; empty suppresses, invalid header values rejected. |
| `cache_headers` | Filter: header map, path, access method | Markdown-response hook with the same contextual information; empty values omit individual headers. |
| `html_headers` | Filter: header map, alternate URL | HTML discovery-header hook; preserve existing `Link`/`Vary`, permit selective omission. `LINK_HEADER` alone is not equivalent. |
| `agent_categories` | Filter: ordered category map | `construct_markdown_agent_categories` (legacy #34); historical label/category implications documented. |
| `ai_catalog` | Filter: catalog | Catalog hook legacy #44; support adding entries and modifying host metadata. |
| `tick_budget` | Filter: seconds, execution context | v0.2 task/job budget configuration with context, adapted to worker execution; never require WP's cron/nudge implementation. |
| `file_generated` | Action: path, post | `markdown_generated(page, path)` after successful publication of the file. |
| `file_deleted` | Action: path, post ID | `markdown_deleted(page_id, path)` after deletion; page object may already be gone. |
| `taxonomy_file_generated` | Action: path, term | Deferred with legacy #49. |
| `taxonomy_file_deleted` | Action: path, term | Deferred with legacy #49. |
| `unresolved_link` | Action: URL, reason | `link_unresolved(url, reason)`; `not_found` versus `ineligible`, once per unresolved URL per resolution run; no event for external links. |

## Command parity

The v0.1 generation, index, status and deletion commands are implemented in #24.
Their [operator guide](management-commands.md) and `tests/test_commands.py` cover
scope validation, working freshness/force behaviour, read-only dry runs/status,
owned deletion, dependent discovery repair and failure reporting (A07/A13).
Bundles, deltas, durable jobs and stats pruning remain in their own issues.

| WordPress command/flag | Wagtail requirement |
| --- | --- |
| `generate`, `--post-type`, `--post-id` | `agentmd_generate`, `--type`, `--page-id`, `--site`; include an explicit single-page scope in legacy #24. |
| `generate --dry-run` | Report eligible work, skips, failures and dependent artefacts; no export/manifest/delta/bundle/job mutation. Rendering checks may run, but preview/dry-run must not persist exports. |
| `generate --force` | Document a real override of unchanged skipping. WP advertises this flag but `generate()` does not read it; do not reproduce a no-op flag. |
| `generate --with-manifest` | Manifests are maintained automatically in Wagtail; a redundant flag is unnecessary. |
| `generate --incremental` | v1.0 hash-based unchanged skipping with missing-file repair, complete scope membership and deletion deltas (A07). |
| `status` | Counts by type/site, export location, missing/stale/error state; bundle status when enabled; job state in v0.2. |
| `delete --post-type/--post-id/--all/--yes` | Explicit type/page/site/all scopes, confirmation for broad deletion, policy-confined managed files only; refresh dependent artefacts. |
| `generate-indexes --dry-run` | `agentmd_generate_indexes --dry-run`; include root/directory listings and clear reporting. |
| `generate-taxonomies --taxonomy/--dry-run` | Deferred with legacy #49. |
| `bundle --if-stale` | `agentmd_bundle --if-stale` in v1.0, legacy #46. |
| `prune-stats --days/--yes` | `agentmd_prune_stats`, default 90 days, positive-days validation and confirmation legacy #36. |

## Additions and implementation backlog

The following requirements are captured by this audit and the amended design.
They still need acceptance tests and implementation. Existing issue references identify
the implementation work; the six new issues and their milestones are listed below.

### GitHub sync record

Synced on 7 September 2026: **52 existing issues updated and six new issues created**.
The existing issues retain their states, milestones and labels. New work is linked
from epics #52, #53 and #55; taxonomy export #49 remains outside the milestones.
Titles, complete bodies, milestones and labels were read back and verified after the
updates.

A second sync aligned **36 issue bodies** with the v0.1 scope and labelled **20
roadmap issues `out-of-sow`** (outside v0.1), including #42 and #44. #61 moved to
v0.1 under #53 because cache guidance supports the v0.1 deployment; #75 moved to v0.2
under #55 as a roadmap enhancement. #31 now distinguishes release-time criteria from
post-release #64 work. Vendor-fetch verification, intent-category filtering, data
minimisation and conditional custom-block coverage are recorded in their existing
issues. Read-back verification confirmed scope notices, labels, milestone moves and
epic links.

| New issue | Milestone | Parent epic | Audit requirements |
| --- | --- | --- | --- |
| legacy #72 — Public export routes | v0.1 | #53 | A01/A10 |
| legacy #73 — Editor preview, regeneration and status | v0.2 | #55 | A04 |
| legacy #74 — Durable bulk-generation jobs | v0.2 | #55 | A05 |
| legacy #75 — Configuration staleness | v0.2 (out of SOW) | #55 | A06/A07 |
| legacy #76 — Agent dataset provenance | v0.1 | #53 | A11 |
| legacy #77 — Lifecycle and removal documentation | v0.2 | #55 | A13 |

### A01 — Public artefact delivery and correct link bases (v0.1)

Extend legacy #14, legacy #20, legacy #21, legacy #26–#28, legacy #68.
Public artefact delivery is tracked in legacy #72.
Provide an explicitly included Django URLconf with named routes for managed exported
pages/indexes and site `llms.txt`/`manifest.json`; later add delta/bundle routes.
The storage key is not a public URL. Route resolution must use site and recorded
export identity, validate containment and recheck eligibility for page artefacts.
Never expose arbitrary files from the storage backend.

The old “relative within the export tree from the start” decision breaks negotiated
reads: `other.md` in `blog/post.md` resolves from `/blog/post/` to
`/blog/post/other.md`, not the intended sibling. Generate absolute public export URLs
in web-served files, including indexes/llms links; rewrite those URLs to file-relative
links when producing the offline bundle. Keep canonical HTML `permalink` metadata.
This replaces the previous relative-link decision and requires regeneration if the
public export URL configuration changes.

Discovery uses the canonical page URL plus `output_format=md` while query negotiation
is enabled, or the explicit Markdown route when it is disabled. Admin/API/preview
paths and non-read methods must never be intercepted. HEAD returns the same response
headers without a body; explicitly exclude it from page-read counters. Gate page
artefact GETs through the same serving logic and record the access method as
`export-url`, an intentional addition to WP's three labels. Index-only/discovery,
manifest and bundle downloads are excluded from page-read counters. Test following
links from negotiated and direct export URLs, and later from extracted bundles.

### A02 — Conversion, YAML and link acceptance cases (v0.1)

Extend legacy #9–#15 and legacy #63. Strip script/style nodes **and contents**
before every HTML fallback conversion. Preserve Unicode, entities, code whitespace
and language hints, table captions, empty/zero cells, pipes and image/text spacing.
Use a safe YAML serialiser and test strings resembling booleans/numbers, multiline
text, quotes/colons, empty lists, false and zero, dates and nested data.

Resolve same-site relative/absolute URLs and unambiguous redirects against the
published tree without making outbound HTTP requests. Preserve fragments; discard
query arguments only where the target represents the same canonical page, and leave
meaningful query-dependent routes unchanged. Leave image/media, external, unresolved,
inline-code and fenced-code content intact. Specify reference-link behaviour if a
custom renderer emits it. Verify path-hook relocation and use one shared policy.

### A03 — Custom extraction and metadata (v0.2; hook escape hatch in v0.1)

Extend legacy #39, legacy #13 and legacy #38. Separate body and frontmatter mappings;
preserve configured body order and optional human-readable headings. Define output
names explicitly for nested fields to prevent leaf-name collisions. Handle repeated
values, page/snippet relations, nulls, false and zero without arbitrary object dumps.
Add explicit image/alt mappings and distinguish editorial author from page owner.
Use registered extractors for project-specific relations; do not expose all model
fields automatically. Test configured fields even on pages that also have a StreamField.
Grouped taxonomy metadata/Topics remain project mappings or legacy #49.

### A04 — Editor export controls (v0.2, #73)

Build on legacy #17/legacy #18: show current export state/time, preview Markdown
without writing it, and regenerate the single published page. Apply Wagtail page
permissions and CSRF checks; present preview text safely; explain disabled controls
for ineligible pages. An explicit editor preview must never become a public export
or increment agent statistics. Initial parity previews the saved published version;
draft preview, if added, is a separate permission-checked mode.

### A05 — Durable bulk generation and operations (v0.2, #74)

Extend legacy #40 beyond swapping `enqueue()`: durable job identity, site/type/all
scope, bounded cursor batches, counters, progress and last-activity time, bounded
error details, item failure versus terminal failure, and restart/recovery semantics.
Prevent concurrent jobs from overwriting the same export generation; use expiring
leases/ownership checks or equivalent guarantees from the selected task backend.
Handle lost jobs, worker termination, retry exhaustion and overlapping writes. Finish
indexes/manifests once per affected scope and bundle once at the end. Preserve a
stale marker if edits arrive during finalisation. A successful stage clears its
settings-stale notice; a partial failure does not falsely mark the scope fresh.
Admin controls must survive tab closure and expose progress without internal tokens.
Document worker setup and explicit stop/recovery procedures. WP has no cancel button;
do not describe cancellation as existing parity.

### A06 — Generation controls and configuration invalidation (v0.1/v0.2)

Extend legacy #23, legacy #24, legacy #29, legacy #38, legacy #69, legacy #70.
Configuration fingerprint/staleness tracking is legacy #75, now v0.2 roadmap work
outside the SOW. Core generation, hashing and revocation remain v0.1 responsibilities.
Add `AUTO_GENERATE` with a documented default of true; setting it false stops routine
publish-time regeneration, never revocation for unpublish/delete/restriction/exclusion.
Use after-commit regeneration with fresh existence/eligibility checks. Draft edits
must not export unpublished content from a page whose previous revision is live.
The v0.2 enhancement records a generation configuration fingerprint. Changes to
fields/renderers/frontmatter/link bases mark affected exports stale; generation repairs
them. v0.1 status reports basic counts/missing/error state; general stale-scope reporting
and admin notices belong to v0.2. Unchanged detection must not trust timestamps
alone. Disabling page types must revoke their public exports and listing entries.

### A07 — Manifest, incremental and CLI semantics (v0.1 foundations; v1.0 deltas)

Extend legacy #22, legacy #24, legacy #41. Hash the rendered body and serialised
metadata actually exported, including tags, configured fields, image references and
link targets; record schema version and path changes. Configuration-fingerprint
tracking is roadmap work in legacy #75, not a v0.1 prerequisite. Do not reuse
WP's raw-body/title/modified-time hash as a complete content fingerprint.
Stable page identity survives moves; the old path must be removed and represented in
the delta. Retain unchanged documents in manifests, re-create missing files, and
publish successful-write metadata only. A failed write is not an unchanged success
or a genuine deletion. A type/page-only run must preserve other scopes. First run,
corrupt/missing prior state, content-only/metadata-only edits, restriction changes,
renames, deletion and no-change runs need explicit tests. `--dry-run` must not update
any persistent artefact, including when combined with manifest/incremental options.

### A08 — Complete extension contracts (v0.1 core hooks; v1.0 final audit)

Use the 22-row inventory above to expand legacy #47. Build each core hook alongside
its feature rather than waiting until v1.0 to create every extension point. Document
order, return value, page/site/request context, omission semantics and exceptions.
Preserve `Cache-Control: private, no-store, max-age=0`; expose optional
`X-Accel-Expires: 0` / `X-LiteSpeed-Cache-Control: no-cache` deployment settings through
the header hook. Those server-specific headers are not guaranteed substitutes for
CDN configuration. Test shared-cache traffic in both directions: HTML then agent and
agent then HTML. A cached HTML response varying only on Accept can bypass UA-based
negotiation, so legacy #59/legacy #61 must specify UA bypass/variant rules where enabled.

### A09 — Statistics contract (v0.1)

Extend legacy #32–#36, legacy #66. Count successful page Markdown GET response
selection, not just detection attempts or downstream delivery acknowledgement. Exclude
missing-file fallback, errors, HTML, HEAD, preview and aggregate downloads. Preserve
known-agent classification even when UA-triggered serving is disabled. Security
update (22 September 2026): all other clients now share the empty unknown bucket;
the original first-product-token rule is superseded to bound row growth and avoid
persisting personal data. Daily buckets use UTC, matching WP. First matching category wins;
unexpected categories display as unknown. Source thresholds are daily through a
92-day span, monthly through 1,827 days, yearly thereafter. The original default
was 30 days; dashboard issue #20 changes it to 7 days.
Trend tiles use correlation over time buckets, not a percentage-change claim; neutral
for flat/insufficient series. Preserve pagination, filters, total plus four intent
tiles, empty states and the on-demand estimate label.

Use a true atomic count increment under concurrent requests. Plain
`bulk_create(update_conflicts=True)` assigning `count=1` is insufficient: the existing
value must be incremented. Correct that wording in legacy #66. Decide deleted-page
history explicitly: retain a stable page identifier for historical counts with a
deleted-page display, rather than cascading away history accidentally. v0.1 retention
is a deployment setting, default 90 days; pruning remains explicit. Static/CDN bypass
traffic is outside application counters and must be stated in the report/soak results.

### A10 — Storage, index ownership and aggregate safety (v0.1/v1.0)

Extend legacy #19, legacy #20, legacy #42, legacy #43, legacy #70. A page occupying
`index.md` must retain its own body/frontmatter while adding a child listing; rebuilding
directory navigation must not overwrite it. Reserve both `index` and `log` and handle
collisions with actual `index_`/`log_` slugs deterministically, using page identity when
needed. Track owned paths, including prior hook paths, for deletion and publication.

`Storage.save()` may rename an existing key; save/open/delete/exists do not promise
atomic replacement or protect concurrent manifest updates. Specify a writer/backend
publication contract, stable logical URLs and serialised updates. Build ZIPs using
managed artefact records rather than requiring local directory traversal or storage
mtime APIs. Local temp-file rename is a local-backend capability, not an S3 guarantee.
Keep the previous complete bundle on ordinary build failure. Revocation is different:
a bundle/index containing newly private content must become unavailable immediately
until rebuilt safely, never remain public through a debounce window. Ensure deletion
callbacks cannot regenerate a cascade-deleted page. Exclude deltas, catalogs, temporary
and unrelated files from ZIPs at every directory depth; preserve canonical metadata
while rewriting body links. Test long Unicode paths, failed writes and concurrent reads.

### A11 — Agent dataset provenance (v0.1 verification)

Tracked in legacy #76; resolved 15 September 2026.

All WP detection entries and category entries are present with shared order preserved,
re-extracted from the pinned commit and compared exactly. The former Wagtail-only
`w4mwnpbXf3MFAbxOkJRw` entry is the `hash/` segment of the EchoboxBot User-Agent. WP
imported it from the Cloudflare Radar bot directory on 29 July 2026 (`bfb444d`) and
removed it on 11 August 2026 (`ed2ba29`), before 1.7.0; the Wagtail bootstrap copied
the intermediate list. #76 removes it to match the reference, before any release has
recorded statistics, and records the reasoning in
[the statistics guide](agent-access-stats.md#reviewed-dataset-baseline-76).
A data-only pinned fixture with an explicit, currently empty, `wagtail_additions`
block replaces the former `>=70` smoke threshold; tests verify membership, order,
no substring shadowing, full-header detection and category precedence. `Gemini-User`
occurs only in the WP category map, faithfully carried over. Robots-only tokens are
retained historically, not as evidence of observed crawler UAs.

### A12 — Corrections to existing issue bodies

The following corrections have been applied to existing issue bodies:

| Issue | Required correction |
| --- | --- |
| legacy #27 | Replace request-path-only/single-exists/no-routing requirements with site/page/policy resolution and discovery-only caching. It also contradicts legacy #68. |
| legacy #69 | Implemented: `page_slug_changed` uses `instance_before`; pre/post move receivers capture subtree/site identities and retire actual owned paths after commit, then refresh current published descendants and affected parents. Rollback, custom storage keys, disabled generation, cross-site/policy transitions and old URL handling are covered in `tests/test_path_lifecycle.py` (A06/A10/A12). |
| legacy #70 | After-commit regeneration, rollback/cascade tests, and revocation of listing/bundle artefacts as well as individual files. |
| legacy #71 | Django 5.2 minimum applies from Wagtail 7.4, not all 7.x. Also bound `wagtail7` to `<8` if CI is intended to test that major; `>=7.0` alone can select 8.x. |
| legacy #47 | Replace “17 filters/actions” with the 17-filter/5-action inventory. |
| legacy #66 | Specify an atomic increment, not an unconditional conflict-update assignment. |

### A13 — Lifecycle and removal (v0.1 command safety; v0.2 operations docs)

Extend legacy #24, legacy #40, legacy #60. Document disabling negotiation separately
from stopping generation, stopping workers and expiring/clearing job leases, keeping
or explicitly deleting exports, and retaining/removing stats through deliberate
maintenance/migration steps. `agentmd_delete` touches only owned artefacts in its
scope. Uninstalling the Python package must not trigger implicit file/table deletion.
Operational documentation is tracked in legacy #77.

## Verification and limits

- WordPress: `php vendor/bin/phpunit --no-configuration --bootstrap tests/bootstrap.php
  --do-not-cache-result tests/Unit` passed **622 tests, 6,181 assertions**. These use
  mocked WordPress APIs; they do not demonstrate live WordPress/CDN behaviour.
- Reviewed source wiring, README, options, public hook call sites and test inventory
  across generation/conversion, storage, negotiation, admin, jobs, stats, discovery,
  CLI and lifecycle. Not every line or third-party dependency was security-audited.
- Compared UA lists/category maps programmatically; counted unique literal public
  filter/action calls from source rather than relying on the README's list.
- Read all 71 original Wagtail issue records, then updated 52 existing issues and
  created #72–#77 at the user's request. Read-back verification covered all 58 changed
  issues, including preserved metadata and the new epic task links. No issues were
  closed and no separate issue comments were added.
- This is a local behavioural parity audit. It does not independently certify current
  OKF/ARD specifications or bot-directory classifications, and cannot validate
  project-specific 350.org models until the fixtures in legacy #65 are supplied.
- Acceptance coverage should be added under legacy #63 before implementation, including
  the new A01–A13 cases. The existing six Wagtail smoke tests establish installation
  only. A real multi-day deployment/cache/stats soak remains legacy #64.

[wp]: https://github.com/chancery-lane-project/wp-mfa-plugin/tree/8ad646e826ccbc836863aca30745abe0c5198a53
[wp-neg]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Negotiate/Negotiator.php
[wp-agent]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Negotiate/AgentDetector.php
[wp-policy]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Generator/ExportPolicy.php
[wp-plugin]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Core/Plugin.php
[wp-readme]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/README.md
[wp-converter]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Generator/Converter.php
[wp-cleanup]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Generator/ContentFilter.php
[wp-gen]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Generator/Generator.php
[wp-fields]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Generator/FieldResolver.php
[wp-fm]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Generator/FrontmatterBuilder.php
[wp-yaml-tests]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/tests/Unit/Generator/YamlFormatterTest.php
[wp-links]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Generator/LinkRewriter.php
[wp-resolver]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Generator/InternalUrlResolver.php
[wp-index]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Generator/IndexGenerator.php
[wp-tax]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Generator/TaxonomyArchiveGenerator.php
[wp-manifest]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Generator/ManifestGenerator.php
[wp-cli]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/CLI/Commands.php
[wp-metabox]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Admin/MetaBox.php
[wp-admin]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Admin/Admin.php
[wp-jobs]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Jobs/GenerationJob.php
[wp-job-tests]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/tests/Unit/Jobs/JobRunnerTest.php
[wp-settings]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Admin/SettingsPage.php
[wp-regen]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Core/NeedsRegenTracker.php
[wp-stats]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Stats/StatsRepository.php
[wp-report]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Stats/StatsPage.php
[wp-bundle]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Generator/BundleGenerator.php
[wp-ard]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Discovery/ArdCatalog.php
[wp-deactivate]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/src/Core/Deactivator.php
[wp-uninstall]: https://github.com/chancery-lane-project/wp-mfa-plugin/blob/8ad646e826ccbc836863aca30745abe0c5198a53/uninstall.php
