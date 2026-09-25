# Remaining deployed checks — 23 September 2026

Status: **bounded multi-day check passed; paid vendor verification deferred**,
following the owner's go-ahead and request for a proportionate check. This replaces
the earlier nine-checkpoint proposal. The existing
[fixture evidence](2026-09-23-bounded-deployed-run.md) and
[cold-cache evidence](2026-09-23-cold-cache-run.md) remain valid within their
recorded scopes; neither needs repeating.

## Three small samples over 48 hours

The run used the existing public synthetic page 89, unchanged since the cold-cache
run. Each sample made five sequential GETs: browser, browser, listed synthetic UA,
explicit Markdown query, browser. This checks browser isolation, warm HTML,
Markdown content/cache policy and two daily counter increments. The ceiling is
**15 public requests total**, zero retries, at most one start per second, 20-second
request timeout and 8 MiB response limit. Readiness used database/configuration
inspection and sent no additional public requests.

| Sample | UTC | UK local time | Status |
| --- | --- | --- | --- |
| Initial | 23 September, 10:24:33–10:24:39 | 11:24am | Passed |
| Day 2 | 24 September, 10:30:01–10:30:06 | 11:30am | Passed |
| Day 3 | 25 September, 10:30:03–10:30:08 | 11:30am | Passed |

The measured baseline-to-final window was 48 hours, 5 minutes, 34.766 seconds.
These are three samples across three UTC dates, not continuous monitoring or an
exact-midnight timing test. The full fixture suite, Accept-only limitation and
independent cold-state proof already have separate evidence.

The initial sample returned three HTML `HIT`s and two Markdown `DYNAMIC`
responses at LHR, all HTTP 200. Both Markdown hashes matched the cold-cache export
and carried `no-store`. Their unique UA markers each matched one origin access
record; browser HIT markers had none. Page-scoped counter snapshots showed exactly:

- 23 September, unlabelled agent, `query-param`: +1.
- 23 September, `GPTBot`, `ua`: +1 (synthetic, not genuine GPTBot traffic).

Every other page-89 bucket was unchanged. Residual was zero.

## Final read-only review — 25 September

The two one-off timers produced `sample-1/result.json` and `sample-2/result.json`.
All three sample results passed; `whole-window.json` reports no residual. No
`failure.json` or `STOP` was present in the retrieved directory. We copied the
existing evidence for offline review without replaying a sample or sending any
additional public requests.

| UTC date | GETs / HTTP 200 | Browser HTML cache status | Markdown cache status | Page-89 counter delta | Origin records |
| --- | --- | --- | --- | --- | --- |
| 23 September | 5 / 5 | `HIT`, `HIT`, `HIT` | `DYNAMIC`, `DYNAMIC` | +2 | 2 Markdown |
| 24 September | 5 / 5 | `EXPIRED`, `HIT`, `HIT` | `DYNAMIC`, `DYNAMIC` | +2 | 1 browser, 2 Markdown |
| 25 September | 5 / 5 | `EXPIRED`, `HIT`, `HIT` | `DYNAMIC`, `DYNAMIC` | +2 | 1 browser, 2 Markdown |

Every sample followed browser, browser, synthetic GPTBot UA, explicit Markdown
query, browser, with GET starts at least one second apart. All nine browser
responses were HTML; all six Markdown responses were `text/markdown` with
`private, no-store, max-age=0`. All Markdown body SHA-256 values matched the
[cold-cache export](2026-09-23-cold-cache-evidence.json). The browser body hash
was also stable across the window. Unique client markers matched each of the
eight origin records exactly once: six Markdown `DYNAMIC` requests and the two
browser `EXPIRED` requests. The seven browser `HIT`s had no origin record.
All matched origin responses were HTTP 200. The observed edge was LHR in all
three samples.

Each UTC date gained exactly one page-89 `GPTBot`/`ua` count and one unlabelled
`query-param` count. The first sample's final counter rows equalled the second
sample's initial rows, and likewise between the second and third samples. The
whole-window baseline-to-final page-scoped delta was exactly +6, with no other
page-89 bucket changing and zero residual. The available rotated origin logs
contained only the eight marked requests to this page over the window. Thus the
two extra origin records were expected browser cache refreshes, not unexplained
Markdown selections. This does not establish absence of unobserved CDN-served
traffic or requests to other pages.

## Execution and evidence

The private script runs as the application owner and takes before/after snapshots
of all page-89 counter buckets. It checks the published revision and selected host
configuration hashes against the initial sample before later requests. It records
durable attempts, response headers/hashes, redacted matching access records and
per-sample results. Unexpected content, lost correlation or counter discrepancies
stop the sequence; later samples require previous samples to have passed.

Two one-off systemd timers were created and their dates read back:
`wmfa-soak-20260923-day1.timer` and `wmfa-soak-20260923-day2.timer`.
Each service has a three-minute runtime limit. There is no recurring schedule.
The timers were transient: a server reboot could have lost a pending sample,
which would have been reported as missing. The server,
not this chat session or the local laptop, runs the samples.

The final sample also compares the complete page-scoped baseline/final delta
against all six expected increments and retains redacted page access records from
available rotated logs. Unexpected traffic between samples remains a residual
requiring review; no automatic attribution is invented. Existing combined access
logs support this narrow marker-based comparison, not full upstream or vendor
identity verification. This is a scoped result, not a full simulator CLI verdict.

Private evidence is on the host under its existing application-parent verification
directory and locally under `/private/tmp/wmfa-soak-20260923/`. The initial archive
and script have integrity references in the
[initial evidence manifest](2026-09-23-soak-evidence.json).
No application deployment, nginx change, cache purge, counter reset or content
change was made. Page 89 remains published through the observation; retirement is
not part of this run.

The final private host-evidence snapshot is retained outside version control;
the adjacent [evidence manifest](2026-09-23-soak-evidence.json) records SHA-256
and byte size for the archive and new artifacts. Raw responses, URLs, access
records and addresses are not published. The three samples cannot establish
uninterrupted availability or every CDN edge.

## Genuine vendor traffic: deferred

The owner chose to defer paid API verification. Neither provider key was available
in this session; no paid API call or replacement vendor fetch was attempted.
This is optional integration evidence, separate from proving the package serves
and counts Markdown correctly. It remains unverified, not failed.

If resumed, aim for one observed, authenticated fetch per provider before expanding
coverage. Use current [OpenAI web-search guidance](https://developers.openai.com/api/docs/guides/tools-web-search)
or [Anthropic web-fetch guidance](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-fetch-tool),
with a small explicit cost/tool budget. Match an actual request to the tool event
and verify its sender using [OpenAI's published crawler guidance](https://developers.openai.com/api/docs/bots)
or [Anthropic's published crawler guidance](https://privacy.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler).
A citation or vendor-shaped UA alone is insufficient; a CDN response also does not
prove a Django Markdown selection. API calls cannot stand in for unobserved
training or search crawlers. The existing reconciler trusts vendor annotations;
it does not authenticate them itself.

## Validation

The preceding review's 16 focused reconciliation tests passed. The private sampler
passed Python compilation and a read-only host preflight. Offline review of the
15 recorded attempts, receipts, origin markers, counter snapshots, unchanged
page/configuration state and whole-window evidence passed the checks above.
D6/D9/D12, client presentation and release decisions remain separate.
