# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Fixed

- Bound stored agent labels to the known dataset plus one unknown bucket, avoiding
  arbitrary User-Agent fragments and unbounded daily statistics rows. Migration
  `0006_anonymize_unknown_agents` merges legacy labels without losing totals;
  pause older application workers during upgrade. Simulator reconciliation uses
  the same labelling rule.
- Ignore local environment secrets, keys, databases and backups, and select
  patched supported release lines for the development environment.
- Point canonical package, installation and security-reporting URLs at the
  350.org repository; retain old issue numbers as unlinked legacy references.

- Require `markdownify>=1.2.3`, the verified converter baseline. The previous
  `>=0.13` bound allowed releases that fail the rendering contract (including
  escaping, code whitespace and golden output).

### Changed

- Pre-transfer review: clarified compatibility versus security support and complete
  removal steps; restored the pending D12 proposal and corrected D9 hook guidance;
  included onboarding documentation and test sources in source distributions.
  Manual CI now validates the selected revision without a checkout-less change
  filter and uses read-only repository permissions. Hosted CI remains manual-only.

- Agent User-Agent dataset (#76): verified entry-for-entry against the pinned
  WordPress 1.7.0 reference, with an explicit `wagtail_additions` fixture block,
  substring-shadowing, full-header and category-precedence tests replacing the
  count-only check. The unreferenced `w4mwnpbXf3MFAbxOkJRw` entry, the EchoboxBot
  User-Agent hash that WordPress imported from Cloudflare Radar and dropped before
  1.7.0, is removed from detection and the training category.

- CDN and cache guide (#61), after measurement on a live deployment behind
  Cloudflare's free plan: agents receive cached HTML on warm URLs without the origin
  being consulted; the free plan rejects `Accept` in a Cache Rule; a bypass rule must
  be ordered after the cache-everything rule because the last matching rule wins. The
  guide opens with a Cloudflare quick checklist, the expected result per request and
  a snippet that generates the bypass expression from the agent list, and covers
  Cloudflare's per-behaviour search/training/agent controls and Bot Preference Sync.

- Documentation prepared for handover: README rewritten as an overview with a
  documentation index; INSTALL.md rewritten for installing from the repository, with
  serving checks, a cache-configuration step and upgrade notes; local development
  walkthroughs moved to `docs/development.md`. Project-delivery material (the hosted
  sandbox playbook and `scripts/sandbox/`, engagement scope, issue review)
  is removed and preserved under the `pre-handover` tag; the 350.org page-model and
  block reference moved to issue #65.

### Added

- Repository agent traffic simulator (#59): seeded plan/run/reconcile commands,
  manifest discovery, production-shaped and dataset-synthetic traffic, both cache
  orderings, append-only attempt/receipt logs, and UTC counter reconciliation with
  verified nginx correlation. Includes local tests and a separate genuine-vendor
  verification procedure; live execution is an independent step.

- Optional `AgentMarkdownPanelMixin` (#18): an editor Settings checkbox backed by
  the same exclusion record as the action-menu view. It applies on successful
  revision save, checks page permissions and locks, preserves frontmatter, and
  leaves preview, invalid forms and unmodified values free of exclusion writes.

- Page editor **Markdown settings** action (#17): a CSRF-protected exclusion form
  with page edit permissions and lock checks. Changes apply immediately through
  the export lifecycle, preserve frontmatter and leave HTML and child-page
  exclusions unchanged. Opening the form or saving unchanged settings makes no writes.

- CDN and cache guide (#61): the same-URL negotiation problem, the headers the
  package sends, both request orderings per trigger on `Vary`-honouring and
  `Vary`-blind caches, bypass-not-key rules, per-layer configuration for Cloudflare,
  Varnish/Fastly, nginx, LiteSpeed, Django's cache middleware and WhiteNoise,
  per-method header relaxation, the statistics gaps and a deployment verification sequence.

- Agent statistics volume suite (#66): 48,000-counter fixtures, atomic write and
  streamed-GET concurrency, fixed report/prune query budgets, UTC/filter/grain
  reconciliation and recorded SQLite/PostgreSQL plans and timings. Includes an
  isolated MySQL write benchmark and documents its existing migration limitation.

- `agentmd_prune_stats` (#36): explicit retention pruning of daily agent access
  counters older than `--days` (default `STATS_RETENTION_DAYS`, 90) before today's
  UTC date. Positive-days validation for both sources, a typed `yes` confirmation
  unless `--yes`, `--dry-run`, deleted/retained counts and a single indexed
  `DELETE`. Nothing schedules it.

- Wagtail Reports → Agent access (#35): combined page/agent/method/intent/date
  filters, UTC presets, adaptive time buckets, five count/correlation tiles,
  accessible charts and pagination. Preserves deleted-page IDs and direct-export
  reporting, shares category overrides across all results, and requires the
  site-wide view permission. Includes counting limits and a sandbox walkthrough.

- Read-time agent intent classification (#34), with an ordered category-map hook,
  unknown-category fallback and historical reclassification guidance.

- Daily agent access counters (#32/#33): one atomic upsert per successful page
  Markdown GET, keyed by stable page ID, agent, access method and UTC date.
  Counts survive page deletion. Negotiated and direct serving share a recorder;
  HTML, errors, fallbacks, HEAD, previews and aggregate-only exports are excluded.
  Agent labelling is independent of UA negotiation, and Unicode labels are bounded.
  Migration `0005_agentaccess` adds the unique key and date index. Reporting and
  pruning remain separate work.

- HTML discovery headers and template tag (#27/#28): eligible HTML 200 responses gain
  `Link: <…>; rel="alternate"; type="text/markdown"` and a merged `Vary: Accept`,
  preserving existing values, and `{% agent_markdown_link %}` emits the matching
  `<link>` element. Resolution follows export policy to the published record and its
  actual storage key, never a request-derived path, and is cached (misses included)
  for `DISCOVERY_CACHE_TIMEOUT` seconds under the site's publication version so
  generation, deletion and relocation invalidate it at once; serving never consults
  the cache. `LINK_HEADER` disables the response phase; the
  `construct_markdown_html_headers` hook overrides or omits headers. The request path
  is never turned into a storage path (#68).

- Configuration checks (#29): middleware absent (`W001`), before `SecurityMiddleware`
  (`E002`) or after `CommonMiddleware` (`E003`); non-dict settings (`E004`), unknown
  keys (`W002`) and wrong shapes (`E005`) for every key, including the new
  `LINK_HEADER`, `DISCOVERY_CACHE_TIMEOUT` and `STATS_RETENTION_DAYS` (default 90)
  settings; and the package URLconf missing (`W003`, or `E006` when query negotiation
  is disabled). Checks never query the database.

- Content negotiation at canonical page URLs (#25/#26/#30): `?output_format=md`,
  an explicit `Accept: text/markdown` media range (wildcards and `q=0` never match)
  or a known agent User-Agent, in that precedence, with stable `query-param`,
  `accept-header` and `ua` labels and independent toggles. The middleware intercepts
  only GET/HEAD page-route requests at the page's canonical URL, serves the recorded
  export through the shared checked path and falls through to HTML for every miss
  without generating content.

- Scoped generation, index/discovery rebuild, read-only status and owned-export
  deletion commands (#24), with dry runs, a working freshness override, broad-delete
  confirmation, per-page/site result reporting and retryable cleanup failures.

- After-commit subtree cleanup and regeneration for Wagtail moves and published
  slug changes (#69), including custom paths, parent leaf/index transitions and
  discovery refresh. Cleanup remains active with automatic generation disabled;
  rolled-back path changes preserve existing files.

- Synchronous restriction/subtree and per-page exclusion revocation, with inline
  after-commit restoration and fresh policy checks (#70). Public `none` restrictions
  are supported. `agentmd_revoke_ineligible` reconciles owned exports after deploy
  configuration or bulk eligibility changes, independently of automatic generation.

- Automatic after-commit generation on Wagtail publish, with synchronous owned-file
  and aggregate withdrawal on unpublish/delete (#23). `AUTO_GENERATE` defaults to
  true; disabling it never disables revocation. Shared ID-based refresh helpers
  handle cascades, former index owners and explicit bulk/dependency refreshes.

- Per-site content-hash manifests with stable page identities, public URLs, actual
  storage keys, word counts and change summaries (#22). Private comparison hashes
  commit atomically with publication; missing exports report errors and revoked
  metadata is omitted. Export batches finalise manifests after discovery.

- Managed `llms.txt` generation with a site heading, optional introduction and
  checked links into the Markdown tree (#21). Export batches now finalise discovery
  after indexes; published metadata and site-state guards prevent stale private listings.

- Root and directory index generation with preserved page bodies/frontmatter,
  checked public listing URLs, navigation customisation, empty-corpus handling
  and explicit batch finalisation (#20). Reserved-name allocation now also handles
  collisions with real siblings using the page-ID suffix.

- Source-preserving internal link rewriting to current owned public exports,
  including relative links, fragments, local redirects and reference links (#14).
  Code, images, external links and query-dependent routes remain intact.
- Explicit public export routes, absolute URL helpers and shared checked serving
  with GET/HEAD support, site/path isolation, response hooks and a best-effort
  page-response signal (#72/#68), shared by negotiation and statistics recording.
- PostgreSQL 16 CI coverage for the full suite, including publication concurrency.
- Deterministic ordering of editor-supplied frontmatter JSON keys across databases.
- Storage review hardening: batched site-policy queries, bounded aggregate retries
  with storage IO outside the site mutex, optimistic checked reads, and protection
  against post-commit notification lookup failures changing publication results.
- Managed storage publication with immutable uploads, actual-key ownership records,
  per-site concurrency guards, stale-build rejection, aggregate updates, retryable
  cleanup and export-storage configuration checks (#19). Hook paths now reject
  traversal and noncanonical segments instead of silently normalising them.
- Published page rendering with ordered field selection, a page post-render hook,
  heading control, frontmatter assembly and explicit unsupported/empty-page errors
  (#78). Includes a project-owned hero example and a full-page golden file.
- Project bootstrap: package skeleton, sandbox Wagtail project, CI matrix,
  bakerydemo setup script, architecture design document, issue/epic structure.
- Default AI agent User-Agent dataset and intent-category map, carried over from the
  WordPress plugin (Cloudflare Radar-derived, July 2026).
