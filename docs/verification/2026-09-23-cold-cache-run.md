# Bounded cold-cache verification — 23 September 2026

The selected public synthetic page passed the bounded cold-to-warm checks at the
observed Cloudflare LHR edge. Two operator-approved, single-URL purges were made,
one before each request order. Each purge was followed by a cacheable browser
`MISS` to the exact ordinary URL, a matching origin access record, then an HTML
`HIT`. This independently establishes cold state for the selected URL at the
observed edge on those first browser GETs. It does not establish absence of
traffic at every Cloudflare edge.

## Scope and preparation

The owner created a public, exportable StandardPage with page ID 89 for this
check. Its exact URL is retained privately. The first readiness GET, before any
purge, returned HTML with `CF-Cache-Status: HIT` and `Age: 124`; a newly published
page was therefore already warm. The advertised query-form export returned
Markdown with `Cache-Control: private, no-store, max-age=0` and `DYNAMIC`.
One further uniquely marked export request appeared exactly once in the origin
access log. All three successful readiness GETs preceded the baseline. One
initial local DNS attempt sent no public request.

The active Cloudflare rules were read back before execution: host cache-everything
first, agent/query bypass second, no custom cache-key setting in the host rule,
and tiered cache off. The existing origin access log recorded timestamp, path,
status and User-Agent. Unique per-request UA markers allowed correlation without
changing nginx configuration. No application deployment, cache-rule change,
full-zone purge or counter reset occurred.

The measured run used six of the twelve allowed GETs, three of six allowed
readiness GETs, two of two approved single-URL purges, sequential starts at no
more than one per second, zero retries, a 20-second timeout and an 8 MiB response
limit. The first purge was submitted at 09:57:09 UTC; the second at 09:58:14 UTC.
The dashboard completed each submission and closed the purge form, and displayed
the exact URL under Recently Purged after the first. It did not expose operation
IDs. Cloudflare's purge receipt alone is not the eviction proof; the first
cacheable browser response after each purge supplied that observation.

## Results

| Order | Measured GET sequence on the same ordinary URL | Origin evidence |
| --- | --- | --- |
| Agent first | Unlisted Accept-only Markdown `BYPASS`; browser HTML `MISS`; browser HTML `HIT` | First two unique markers matched origin records; the HIT did not |
| Browser first | Browser HTML `MISS`; browser HTML `HIT`; unlisted Accept-only HTML `HIT` | First marker matched an origin record; both HITs did not |

All six requests returned 200. The Markdown body matched the readiness export
SHA-256; all five HTML bodies had the same SHA-256. Markdown carried `no-store`,
and no browser received Markdown. The final Accept-only HTML `HIT` is the
previously documented Cloudflare free-plan limitation, not a Markdown success.
All six `CF-Ray` values identified LHR. In the measured two-minute window, the
origin access log contained exactly three requests to this page, all with the
expected unique markers; there were no unmarked origin requests to it.

The pre-run `AgentAccess` snapshot was captured at 09:57:01 UTC and the after
snapshot at 09:58:44 UTC. Exactly one bucket changed: 23 September, page 89,
unlabelled agent, `accept-header`, up by one. That is the first Markdown GET.
HTML responses and CDN hits contributed zero. Counter residual was zero.

The private evidence contains purge observations, client attempts and receipts,
body hashes and bodies, redacted origin access records, before/after snapshots
and the exact-bucket check. The adjacent [evidence manifest](2026-09-23-cold-cache-evidence.json)
records sizes and SHA-256 hashes without publishing the URL or private content.

The result is bounded to the exact page and observed LHR edge. The free-plan
dashboard did not provide complete request-level edge logs, so the report does
not claim that no intervening request occurred anywhere on Cloudflare's network.
The earlier fixture/registry run remains the evidence for those cases. Multi-day
behaviour and genuine vendor-origin fetches remain separate open work. The
owner-created test page remained published after this check; no page-retirement
instruction was supplied.
