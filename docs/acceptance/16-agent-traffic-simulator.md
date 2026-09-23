# Agent traffic simulator (#59)

Project-owner authorised, 21 September 2026. Local evidence is in
`tests/test_agent_simulator.py` and `tests/test_simulator_fixtures.py`; deployed
verification is a separate activity. The [repeatable local corpus](../agent-simulator.md#repeatable-local-corpus)
creates all six explicit fixtures using isolated sandbox settings.
The [22 September local verification](../verification/2026-09-22-local-fixtures.md)
records the separate loopback HTTP run and its counter comparison.
The [23 September bounded deployed run](../verification/2026-09-23-bounded-deployed-run.md)
passed all twelve fixture GET/HEAD checks and reconciled 472 expected and observed
counter increments at zero tolerance. Cold-cache, multi-day and genuine vendor
checks remain separate.

1. Given a manifest and canonical page locations, planning with the same seed
   produces the same bounded request sequence. IDs and direct URLs come from the
   manifest, including page-owned indexes. Canonical URLs come from downloaded
   frontmatter or explicit overrides, never from reversing an export path.
2. Given enough request budget, the plan covers Accept, query, UA-only and direct
   exports, browser controls, both cache orderings, HEAD, manifest and llms.txt.
   Explicit fixtures cover HTML fallback, excluded pages, previews, missing/private
   exports and navigation-only indexes. Missing fixtures and truncated coverage are
   reported, never represented as passing checks. Export links are followed only
   when they resolve to a current same-origin manifested document.
3. Production-shaped examples cover both vendors and all three intents. The entire
   shipped detection dataset is exercised separately with synthetic headers,
   including robots.txt-only tokens. Neither tier claims vendor-origin traffic.
4. Every HTTP attempt is durably appended before sending; each completed body,
   error, retry and interruption has its own event. UTC times, correlation IDs,
   method, URL, UA, selected response headers, body hash and elapsed time survive
   interruption. Redirects are recorded without silently following them. Limits
   include retries. No credentials, cookies, IPs or response bodies are logged.
5. Browser Markdown is a cache-poisoning failure and stops the run. Warm cached
   HTML for Accept-only from an unlisted UA is reported as the documented
   Cloudflare-free limitation, never Markdown success. A request ordering alone
   does not prove that the initial cache state was cold or warm.
6. Reconciliation compares before/after AgentAccess snapshots by UTC date, page,
   agent and access method. Matched nginx correlation fields must be verified
   against client requests before using origin evidence. CDN/proxy cache hits,
   static responses, exclusions, background traffic and uncertain delivery/selection
   are separate. A response selected at the origin may count despite client failure.
   Missing origin evidence, midnight boundaries, counter resets and malformed or
   unfinished logs cannot silently produce an exact match.
7. Genuine vendor verification has a separate, bounded procedure. A tool citation
   or a simulator UA alone does not prove a vendor fetch. The procedure records
   observed requests and capability limits, including inability to force training
   crawls, and requires an agreed configuration before paid calls.
