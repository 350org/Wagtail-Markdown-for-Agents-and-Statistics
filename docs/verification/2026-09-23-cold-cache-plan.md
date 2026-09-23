# Bounded cold-cache verification plan — 23 September 2026

Status: executed on 23 September 2026. See the
[bounded cold-cache result](2026-09-23-cold-cache-run.md). The
[earlier deployed run](2026-09-23-bounded-deployed-run.md) established fixture
responses and zero-tolerance counter reconciliation. This follow-up addresses
only the previously unproven initial cache state. It does not repeat the
1,000-request suite or claim multi-day or genuine vendor verification.

## Target and limits

Prefer one dedicated synthetic page with a hard-to-guess path, published for the
window, publicly readable and exportable under the ordinary caching policy. Keep
it out of navigation where the deployment permits, and do not send its URL to
crawlers or other test clients during the window. The public export manifest may
still expose it, so obscurity is only a traffic-reduction measure. Record the
exact canonical HTTPS URL and page ID privately. An existing quiet public page
is acceptable if its traffic can be accounted for. Use the ordinary
URL with **no query string or random cache buster** for both cold and warm checks.
Confirm its HTML is eligible for Cloudflare caching and its Markdown remains
`private, no-store`. Freeze content, export, cache rules and origin configuration
for the window. Inspect the active Cloudflare cache key, URL normalization,
Workers, tiered cache and any other cache layer before choosing the purge form.
Create and verify the page and export before the measured baseline. Publishing a
new page is not itself cold-cache proof: its URL may have a cached 404 or may be
requested during preparation. Purge its exact ordinary key after readiness.

Budget: at most six readiness requests and twelve measured public GETs, two
single-URL purge operations, one request start per second, zero retries, 20-second
per-request timeout, 8 MiB response limit and a 30-minute window. Record every
attempt against the budget, including failed probes. Stop on browser Markdown,
unexpected response, missing correlation or exhausted budget. No full-zone purge,
rule change, application deployment, vendor call or statistics reset is in scope.
If a dedicated page is used, its creation, export and retirement are additional
controlled content changes. Agree its lifecycle and the two single-URL purges
with the deployment operator before execution.

## Independent cold-state proof

1. Before traffic, retain the active cache-key/rule configuration, selected URL,
   origin-cache inspection and clock synchronization. For a dedicated page,
   retain its creation/publication and export state. Verify the tagged nginx log
   with a separate URL; its record must contain the exact run/request IDs, URI,
   method, UA, UTC time and Django upstream. Finish all discovery and readiness
   requests before the first purge.
2. Purge **only the selected ordinary URL's effective Cloudflare cache key**.
   Include every required custom-key component if one exists. Save the exact
   request, response, operation ID and UTC time privately. A purge HTTP 200 is
   evidence of receipt, not proof of eviction.
3. Start the first GET immediately after the purge. Its client receipt must show
   `CF-Cache-Status` other than `HIT` and a `CF-Ray`; the origin access record
   must match its URI, unique probe marker in the UA, method and time. For the
   first browser GET, `MISS` plus the matched origin record directly establishes
   that this edge did not serve a cached HTML object for the exact URL. An agent
   Markdown response may instead be `BYPASS` or `DYNAMIC` because it is
   `no-store`; require the following browser GET to be `MISS` and to match an
   origin record as corroboration. Retain complete edge request records for the
   exact key if the deployment supplies them, to check for intervening traffic.
4. Repeat the exact-key purge and proof for the other request order. A previous
   warm sequence cannot supply the cold state for the next one. If the purge
   targets an uncertain key, the first browser GET is a `HIT`, origin correlation
   is missing, or the agent-first browser GET is not a `MISS`, record that order
   as **cold state unverified**. Do not infer it from request order or a different
   URL. Without complete edge records, make the narrower claim that the selected
   URL was cold at the observed edge on the first cacheable browser GET; do not
   claim that no intervening requests occurred anywhere on the CDN.

Cloudflare documents that [single-file purges accept a URL and custom-key
components](https://developers.cloudflare.com/cache/how-to/purge-cache/purge-cache-key/)
and that a [successful purge response alone does not verify eviction](https://developers.cloudflare.com/cache/how-to/purge-cache/).

## Measured sequence on the same URL

Use the existing simulator's correlation headers and receipt format, or an
equivalent bounded probe that logs full response headers and body SHA-256. Keep
each group contiguous. Use an unlisted synthetic UA for the Accept-only request
and a normal browser UA for HTML; send `Accept-Encoding: identity` in both.

| Order | After its own exact-URL purge | Expected result |
| --- | --- | --- |
| Agent first | 1. GET with `Accept: text/markdown`; 2. browser HTML GET; 3. repeat browser HTML GET | First request reaches origin and returns Markdown with `private, no-store`; browser receives HTML, then observed `HIT` for warm HTML |
| Browser first | 1. browser HTML GET; 2. repeat browser HTML GET; 3. GET with unlisted UA and `Accept: text/markdown` | First browser request is `MISS` and reaches origin; second is `HIT`; the final request reproduces the documented free-plan Accept-only cached-HTML limitation if it is `HIT` |

After these six GETs, use up to three more on the now-warm URL for a listed
automatic Markdown UA, `?output_format=md`, and a browser control. The UA/query
requests should reach origin and return Markdown; the browser must remain HTML.
These are supporting bypass and poisoning controls, not part of the cold proof.
Reserve the remaining three measured slots for a single failed/uncertain step;
never silently restart a group or exceed two purges. A failed cold proof remains
failed even if a later request returns the expected representation.

Capture scoped `AgentAccess` snapshots immediately before and after the measured
window and wait for in-flight origin work before the latter. Reconcile by UTC day,
page, agent and method at zero tolerance against the actual matched origin GETs:
Markdown page selections count, while browser HTML and CDN hits do not. HEAD,
fixtures and full registry coverage are already established by the earlier run.

## Evidence and decision

Retain privately the exact URL/cache-key assessment, purge requests and receipts,
edge records where available, tagged origin log, client attempt/response JSONL,
response body hashes, before/after snapshots, reconciliation and synchronized UTC
timeline. Publish a sanitized result with artifact sizes and SHA-256 hashes; omit
deployment URLs, tokens, raw IPs and private content. Check that the selected URL
and both purge records correspond to the same ordinary key used by all six GETs.
If a dedicated page was used, retire it using the recorded content/export cleanup
procedure after evidence capture; preserve the counter and evidence records.

Mark cold-cache verification passed only for an order with an exact-key purge
record, first cacheable browser `MISS`, matching origin record and expected
representation. Require both orders, a subsequent observed warm HTML
`HIT`, no browser Markdown and zero counter residual for the complete bounded
result. If any prerequisite is unavailable, report the observed behaviour and
keep the independently proven cold-cache acceptance item open.
