# Bounded live verification — 21 September 2026

All 1,000 simulated requests completed through Cloudflare's free-plan shared cache
without assertion or transport failures. Origin counters increased by exactly the
603 expected Markdown selections, with zero residual in every counter bucket at
zero tolerance. This is initial live evidence for #59/#64, not full acceptance:
six fixture cases, independently verified cold-cache state, multi-day behaviour
and genuine vendor fetches remain unverified.

## Environment and approved limits

The target was a controlled bakerydemo deployment running Python 3.12.3, Django
6.0.8, Wagtail 7.4.3 and Gunicorn 23.0.0. The origin package revision was
`52e9022649154025d35bf146f5bf84846a6c8fc8`; the simulator was merged PR #120,
`7b72d01bc5be659b6dc10b4a1477470d9c23d473`. Their serving, statistics and agent
dataset code matched. Newer editor exclusion UI changes were not deployed.

The owner approved at most 40 discovery/probe requests and 1,000 simulated
requests, sequentially at a configured maximum of one request start per second,
with a 30-minute deadline per phase, zero retries, a 20-second timeout and an
8 MiB response limit. The plan used seed 59 and the `cloudflare-free` profile.

With separate approval, the active Cloudflare bypass expression was regenerated
from all 69 current UA substrings (3,050 characters), retaining the query trigger
and its position **after** cache-everything. Existing origin cache-control
behaviour was retained. No cache purge or application deployment was performed.

## Evidence window

A dedicated nginx JSONL log recorded both correlation headers for tagged public
GET/HEAD requests, omitting IP addresses and cookies. Its initial filter expected
hyphenated UUIDs; the simulator actually uses 32-character hexadecimal IDs. The
filter was corrected, nginx configuration validation passed, and nginx reloaded.
A subsequent direct-export probe produced an actual record matching both IDs,
method, URI, UA and timestamp, with a successful Django upstream Markdown response.

Discovery used 19 requests to find 18 exported documents; the correlation probe
used one more. These 20 requests finished before the baseline. The first 19 have
client evidence but no dedicated origin records because of the initial filter
error; none is included in the measured counter delta.

| Boundary | UTC time |
| --- | --- |
| Before snapshot | 14:37:41.708826 |
| Simulator start | 14:37:47.029643 |
| Simulator end | 14:56:36.760312 |
| After snapshot | 14:57:09.336122 |

Every attempt completed before the final snapshot. The dedicated origin log did
not rotate during the window. Deployment-specific plans, JSONL logs and snapshots
are retained privately; the adjacent [evidence manifest](2026-09-21-evidence.json)
records their hashes without publishing deployment URLs.

An offline follow-up verified all 12 recorded artifact sizes and SHA-256 hashes
against the retained archive. Replaying the reconciler at the simulator revision
reproduced `report.json` exactly, including its `inconclusive` status. This added
no live requests.

## Results

| Check | Observed result |
| --- | --- |
| HTTP responses | 1,000 complete responses, all status 200; 926 GET and 74 HEAD |
| Assertions | 964 passes, 36 known limitations, zero failures |
| Browser controls | 285 HTML responses; 269 cache hits; zero Markdown responses |
| Markdown responses | 675, including 603 GET and 72 HEAD |
| Markdown headers | All carried `private, no-store, max-age=0` and `Vary: Accept, User-Agent` |
| CDN status | 675 DYNAMIC, 305 HIT, 16 EXPIRED, 4 BYPASS |
| Origin correlation | 695 matched run requests; the other 305 were CDN hits |
| Expected counter selections | 603 |
| Actual counter delta | 603 (90 before, 693 after) |
| Counter residual | Zero in all 568 compared buckets; 498 buckets increased |

The 92 origin arrivals excluded from page counts were 72 page HEAD requests,
four aggregate requests and 16 browser HTML requests. No simulated selection
remained uncertain. There were no attributed vendor or background increments;
the logging limitation below still applies.

All 36 known limitations were unlisted clients requesting Markdown through
`Accept` and receiving cached HTML. They are not Markdown successes. Listed UA,
query and direct-export checks passed. The run exercised both request orders
across all 18 pages, 17 export-link traversals, all 69 agent labels through all
four methods, and 181 additional mixed-traffic requests. All 90 browser-first
groups included an observed warm HTML cache hit. Initial cold state was not proven.

## Remaining acceptance work

The reconciler returned `inconclusive` (exit 2) solely because explicit fixture
coverage was incomplete, despite exact counter agreement. Missing cases were
fallback, excluded pages, previews, missing exports, private exports and
navigation-only indexes. They must not be marked passed from this run.

The dedicated log contains only simulator-tagged public requests, so it cannot
fully attribute unrelated background traffic. Zero residual is evidence for this
window, not proof that no background requests occurred.

No genuine vendor API calls were made. Simulated UA strings do not authenticate
vendor origin, and this approximately 19-minute run does not establish multi-day
behaviour. #59/#64 therefore remain open. D9/D12, repository transfer and the
disabled/manual-only CI configuration are unchanged.
