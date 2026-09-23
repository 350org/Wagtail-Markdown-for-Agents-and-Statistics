# Remaining deployed checks — 23 September 2026

Status: **reduced multi-day check started; paid vendor verification deferred**,
following the owner's go-ahead and request for a proportionate check. This replaces
the earlier nine-checkpoint proposal. The existing
[fixture evidence](2026-09-23-bounded-deployed-run.md) and
[cold-cache evidence](2026-09-23-cold-cache-run.md) remain valid within their
recorded scopes; neither needs repeating.

## Three small samples over 48 hours

Use the existing public synthetic page 89, unchanged since the cold-cache run.
Each sample makes five sequential GETs: browser, browser, listed synthetic UA,
explicit Markdown query, browser. This checks browser isolation, warm HTML,
Markdown content/cache policy and two daily counter increments. The ceiling is
**15 public requests total**, zero retries, at most one start per second, 20-second
request timeout and 8 MiB response limit. Readiness used database/configuration
inspection and sent no additional public requests.

| Sample | UTC | UK local time | Status |
| --- | --- | --- | --- |
| Initial | 23 September, 10:24:33–10:24:39 | 11:24am | Passed |
| Day 2 | 24 September, 10:30 | 11:30am | Scheduled |
| Day 3 | 25 September, 10:30 | 11:30am | Scheduled |

The final scheduled sample is more than 48 hours after the initial baseline.
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
The timers are transient: a server reboot can lose a pending sample, which must
be reported as missing rather than silently claimed as complete. The server,
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
not part of this run. To cancel the remaining samples, stop the two named timers
and any active matching services; preserve the evidence and counters.

After 25 September, retrieve both remaining results and `whole-window.json`, check
elapsed time, UTC buckets, response outcomes and zero residual, then record the
final result. Until that review, **multi-day verification remains in progress**.
The three samples cannot establish uninterrupted availability or every CDN edge.

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
passed Python compilation and a read-only host preflight, then its first actual
five-request sample passed all checks above. Later samples have not run yet.
D6/D9/D12, client presentation and release decisions remain separate.
