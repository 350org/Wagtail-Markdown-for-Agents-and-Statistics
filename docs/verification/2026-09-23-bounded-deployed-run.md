# Bounded deployed fixture verification — 23 September 2026

The reviewed temporary fixture bundle was applied to the controlled deployment,
verified, and removed in one session. The full 1,000-request simulator run
completed without assertion or transport failures. Reconciliation returned
**matched** at zero tolerance: 472 expected origin selections and 472 observed
counter increments, with zero residual in every compared bucket and no warnings.
All six explicit fixture kinds passed both GET and HEAD checks. This establishes
the bounded deployed fixture and counter cases; it does not establish cold-cache,
multi-day or genuine vendor-origin behaviour.

## Change and readiness boundary

The private review archive matched its recorded SHA-256. The installed package's
68 files and the two active configuration files matched the reviewed originals;
nginx and the application worker were healthy. The installed package revision was
`a89dab59a7c517ed619bcb26ab2ede1fd5e2deff`, with registry
`2026-09-22.1`; the simulator checkout was
`6825cd96c7d95445cbe9c8c324e2b59e013ad6c6`.

The bundle created an isolated five-page synthetic branch for fallback, exclusion,
preview and private states; the fallback also supplied the missing-export case.
An existing ownerless navigation index supplied the sixth case. The temporary
preview adapter selected only the pinned published revision and denied the saved
draft canary. The existing package was unchanged. A recovery database copy and
export archive were captured privately before seeding. Django checks and active
nginx validation passed before the worker restart and nginx reload.

Thirteen tagged readiness probes passed: GET and HEAD for all six fixture kinds,
plus an ordinary preview-page Markdown control. HEAD bodies were empty, and the
draft canary was absent. Every probe had an actual nginx record matching its two
correlation IDs, method, URI, status and Django upstream; the largest observed
client/origin timestamp difference was under one second. Application-state checks
confirmed the fixture restrictions, exclusion, export ownership and ownerless
navigation index. Discovery used 21 requests, so the complete preflight used
34 of the agreed maximum 40 public requests.

The generated plan contained all 23 registry labels, all six GET/HEAD fixture
pairs, and a complete required suite of 707 requests within the 1,000-request
ceiling. Its retained SHA-256 is
`7942fd2c5ea5c5781bf9544c545d300393d6b314bb81f7a5e4764e75e52c75d8`.

## Measured window and result

| Boundary | UTC time |
| --- | --- |
| Before snapshot | 09:01:21.853697 |
| Simulator start | 09:01:34.766997 |
| Simulator end | 09:21:39.259780 |
| After snapshot | 09:22:00.796771 |

The single run used the `cloudflare-free` profile, seed 59, sequential starts at
no more than one per second, zero retries, a 20-second timeout, an 8 MiB response
limit and the agreed 30-minute deadline. The before and after snapshots had the
same counter scope; no fixture, configuration or counter-reset change occurred
inside that window.

| Check | Observed result |
| --- | --- |
| HTTP attempts and completed responses | 1,000 each: 912 GET, 88 HEAD |
| Assertions | 925 passes, 75 known Accept-only/Cloudflare limitations, zero failures |
| Explicit fixtures | All twelve GET/HEAD responses passed; no fixture selections counted |
| Origin evidence | 588 matched requests, 412 CDN cache hits; correlation verified |
| Counter selections | 472 expected and 472 observed; zero residual across 899 compared buckets |
| Reconciliation | `matched`, zero tolerance, no warnings; offline replay byte-identical |

The 75 known limitations are unlisted clients asking for Markdown through Accept
and receiving cached HTML on the free-plan shared cache. They are not counted as
Markdown successes. The report observed warm HTML cache hits in all 100
browser-first groups; it does not prove the initial cache state was cold. No
browser received Markdown. Tagged-only origin logging cannot fully attribute
unrelated background traffic, even though this window has no counter residual.

## Retention and cleanup

The complete plan, fixture state, discovery/readiness/client/origin logs,
before/after snapshots, reconciliation report, change archive, configuration
backups and recovery copies are retained privately. The adjacent
[evidence manifest](2026-09-23-evidence.json) records sizes and SHA-256 hashes
without publishing deployment URLs or private content. Offline reconciliation
reproduced the retained report byte for byte.

After evidence capture, the known synthetic branch was unpublished and restricted;
its exports were withdrawn and discovery refreshed. Original settings and nginx
files were restored to their reviewed hashes, the temporary preview adapter was
removed, nginx validation and Django checks passed, and the application worker
was running. CMS rows, revisions, counters and private evidence were retained.
No Cloudflare rule or cache purge was made. Harmless cached synthetic HTML may
remain until its TTL expires.

Cold-cache state was not independently established. Multi-day behaviour and
genuine vendor-origin fetches require separate bounded work. Client-specific
D6/D9/D12 decisions and presentation sign-off remain separate from this run.
