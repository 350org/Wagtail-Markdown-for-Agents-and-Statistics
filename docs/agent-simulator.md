# Agent traffic simulator (#59)

The repository CLI plans bounded traffic, records what the client actually receives,
and reconciles it with origin logs and `AgentAccess` snapshots. It does not need
Django settings or database access on the machine sending traffic. Run it from a
checkout with the package's dependencies installed:

```bash
PYTHONPATH=src python -m scripts.agent_simulator --help
```

Only use a target you control. Agree its request budget, duration, rate and any
vendor API costs before running extended verification. The CLI never changes CDN
rules, publishes pages, schedules traffic or invokes vendor APIs.

## Plan and run

This example creates a plan of at most 1,000 requests, with a one-hour deadline and
at most one request start per second. Planning performs discovery GETs, logged under
a separate run ID and `phase: discovery`. Discovery has its own limit of 200 requests
and the same rate/deadline. Those direct page-export GETs can increment counters:
complete discovery **before** taking the baseline snapshot for the run.

```bash
PYTHONPATH=src python -m scripts.agent_simulator plan \
  --target https://www.example.org \
  --fixtures verification-fixtures.json \
  --max-requests 1000 --duration 3600 --rate 1 --seed 59 \
  --cache-profile cloudflare-free \
  --log discovery.jsonl --output plan.json

# Inspect plan.json and its coverage before sending planned traffic.
# Capture before.json at the origin, using the snapshot procedure below.
PYTHONPATH=src python -m scripts.agent_simulator run \
  --plan plan.json --log client.jsonl --timeout 20 --retries 0
# Wait for in-flight origin requests to finish, then capture after.json.
```

`--target` is an HTTP(S) origin. `--manifest-url` defaults to
`/markdown/manifest.json`; customise it for the deployed URLconf. IDs and export
URLs come from that manifest; the simulator never guesses IDs from paths or uses
storage keys as URLs. It obtains canonical URLs from exported `permalink`
frontmatter. A frontmatter hook can override `id`, so only the manifest owns page
identity. Manifest full hashes check received page bodies; regenerate the plan if
content changes during verification.

For a completely offline plan, provide `--manifest-file manifest.json` and a
`canonical_urls` override for **every** manifested ID in the fixtures file. This
makes no requests; it cannot discover links inside export bodies. Online discovery
parses ordinary Markdown links, including reference links, and the plan follows
links to same-origin manifested documents. It does not crawl external links,
assets, unknown/private exports or links inside fenced code. Link fragments do not
change document identity. Offline plans therefore do not verify link traversal.

The JSON plan is deterministic for identical inputs and seed. A complete suite
covers every manifested page in agent→browser and browser→agent order for Accept,
query, UA-only and direct exports. Browser-first sequences include two browser
requests to give a shared cache an opportunity to warm. An independent unlisted
client tests Accept-only behaviour in both orders. HEAD covers all four access
methods; manifest and `llms.txt` GET/HEAD are non-page aggregates. Additional
traffic cycles every shipped detection label through all four methods. After that,
the seeded mix uses training bursts of three, single search/on-demand reads with
longer gaps, and browser controls. This is a reproducible workload model, not a
measured distribution of vendor traffic.

`coverage.suite_complete` says whether the request budget includes the entire
suite; `missing_fixtures`, `dataset_labels` and `followed_links` expose omissions.
Increase the request limit when the site requires a larger suite. A plan may be
truncated intentionally for a smoke test, but it cannot demonstrate full acceptance.
The deadline or retries may truncate execution further; the run writes actual
completion coverage. Requests are sequential and never exceed the configured start
rate; elapsed time includes reading responses. A request already in progress may
finish after the deadline while waiting for network IO, bounded by its socket
inactivity timeout. No further request starts after the deadline. An 8 MiB response
limit is configurable with `--max-bytes`; oversized and truncated bodies are errors.

Run exit codes: `0` means the executed plan finished without assertion/transport
failures, `1` means a failure, `2` means the budget stopped execution, and `130`
means interruption. Exit `0` does not certify fixture coverage, cache state or
vendor identity. Known Cloudflare limitations are counted separately. Retry defaults
to zero; explicitly enabling it retries transport errors only, with a new request
ID and `retry_of`. Every retry consumes the same request budget and rate limit.
A timed-out attempt and its successful retry may **both** have selected Markdown
at the origin. HTTP errors and redirects are recorded, not retried or followed.

## Explicit fixtures

### Repeatable local corpus

The sandbox can create all six fixtures in a separate database and export directory.
From the repository root, start with a fresh `sandbox/simulator-data/` directory:

```bash
mkdir -p sandbox/simulator-data
uv run sandbox/manage.py migrate --settings=sandbox.simulator_settings
uv run sandbox/manage.py agentmd_simulator_fixtures --settings=sandbox.simulator_settings \
  > sandbox/simulator-data/fixtures.json
uv run sandbox/manage.py runserver 127.0.0.1:8000 --settings=sandbox.simulator_settings
```

In another terminal:

```bash
uv run python -m scripts.agent_simulator plan --target http://localhost:8000 \
  --fixtures sandbox/simulator-data/fixtures.json \
  --output sandbox/simulator-data/plan.json \
  --log sandbox/simulator-data/discovery.jsonl --max-requests 250 --rate 5
uv run python -m scripts.agent_simulator run \
  --plan sandbox/simulator-data/plan.json --log sandbox/simulator-data/run.jsonl
```

The command refuses to replace an existing `/simulator/` branch. To start again,
stop the server and move the entire `sandbox/simulator-data/` directory aside,
then repeat the setup. Do not run `agentmd_generate` against this corpus: two
published pages deliberately have no export. Normal sandbox data is separate.

| Fixture | Actual state | GET / HEAD expectation |
| --- | --- | --- |
| `fallback` | Published article with no generated export | 200 HTML |
| `excluded` | Published article with `PageAgentSettings.excluded=True` | 200 HTML |
| `preview` | Exportable synthetic article through Wagtail's preview renderer | 200 HTML |
| `missing-export` | Direct export URL for an ungenerated article | 404 HTML |
| `private-export` | Direct export URL for a login-restricted article | 404 HTML |
| `navigation-index` | Generated directory index with no page owner and a public child | 200 Markdown |

The preview adapter is enabled only by `sandbox.simulator_settings`. It marks the
fixed `/simulator/preview/?preview=1` request as a preview before negotiation and
calls `serve_preview` using the published revision. It cannot select a draft or
arbitrary page ID, and checks page and ancestor restrictions. The same page without
the preview flag serves Markdown. Never deploy this sandbox configuration.

`tests/test_simulator_fixtures.py` verifies each fixture's state, all twelve GET/HEAD
responses, no counter increments for fixtures, and a complete 250-request plan
against real Wagtail views and database counters. Reconciliation uses explicitly
modelled origin rows from the Django test transport. These are local integration
checks, not nginx/CDN evidence; the historical live run remains inconclusive until
equivalent deployed fixtures are independently verified.

### Fixtures on another controlled site

Use public, controlled fixtures, with expected status and content type. Example:

```json
{
  "canonical_urls": {"7": "/news/"},
  "checks": [
    {"kind": "fallback", "url": "/empty/", "page_id": 8,
     "status": 200, "content_type": "text/html"},
    {"kind": "excluded", "url": "/excluded/", "page_id": 9,
     "status": 200, "content_type": "text/html"},
    {"kind": "preview", "url": "/verification-preview/", "page_id": 10,
     "status": 200, "content_type": "text/html"},
    {"kind": "missing-export", "url": "/markdown/missing.md",
     "access_method": "export-url", "status": 404, "content_type": "text/html"},
    {"kind": "private-export", "url": "/markdown/private.md",
     "access_method": "export-url", "status": 404, "content_type": "text/html"},
    {"kind": "navigation-index", "url": "/markdown/navigation/index.md",
     "access_method": "export-url", "status": 200, "content_type": "text/markdown"}
  ]
}
```

Replace these with actual fixture locations and IDs; the CLI does not create them.
A preview fixture must really enter the site's preview path (`request.is_preview`),
for example through a controlled test adapter. Merely naming an HTML URL “preview”
does not test preview exclusion. Do not expose private drafts to enable verification;
leave that fixture missing when a safe public adapter is unavailable. Authenticated
admin previews are covered by the package's local integration tests. Missing/private
export fixtures are anonymous denied requests, not attempts to retrieve private data.

A navigation-only index has no page owner. A manifested `index.md` **does** have an
owner and must be counted; the planner rejects classifying it as a navigation-only
fixture. All fixtures run as GET and HEAD and are excluded from expected counters.
`missing_fixtures` includes any kind whose GET and HEAD checks do not both fit in
the request budget, even when that kind was supplied in the configuration.
Fixtures can specify `access_method` (`ua` by default). Use the corresponding query
URL explicitly when testing `query-param`. Current rendering-policy decisions are
outside this tool: fixtures test the deployed policy, not a proposed new policy.

Only same-origin public URLs are accepted. URLs with credentials or arbitrary query
parameters are rejected; supported query keys are `output_format` and a simple
`preview` flag. Signed preview links and authentication tokens do not belong in
plans. There is no cookie jar, Authorization option or ambient proxy configuration.

## Cache assertions and prerequisites

Apply the [CDN guidance](cdn-caching.md) before deployment verification. Regenerate
the bypass expression from the **current** dataset and compare every clause with
the installed rule. On Cloudflare the bypass must remain **after** cache-everything.
The CLI does not modify or purge a cache.

- Browser Markdown is a cache-poisoning failure and stops the run immediately.
- Known agents and query/direct-export requests must receive Markdown. Cached HTML
  for a listed UA is a failure, even on Cloudflare free.
- With `--cache-profile cloudflare-free`, a 200 HTML `CF-Cache-Status: HIT` for
  Accept-only from an unlisted UA is `known-limitation`, **not** Markdown success.
  With the default `strict` profile it is a failure. An uncached HTML response is
  a failure in either profile.
- A request ordering does not prove cache state. The report marks warm HTML evidence
  only when preceding browser traffic actually reports a HIT. Initial cold state
  remains unverified. For cold-start acceptance, use a separately prepared uncached
  URL or an agreed purge and retain independent evidence. Do not add random cache
  busters and then claim the site's ordinary warm URL was tested.
- Successful body hashes, cache headers and counters are different checks. Public
  caching of direct exports can return correct Markdown without incrementing a
  counter. A stale manifest hash is a retrieval failure, not proof of cache poisoning.

## Ground-truth JSONL

Each run appends `run-start`, `attempt`, `response` / `error` / `interrupted`,
coverage and `run-end` events. Each line is flushed and synced to disk. Existing
records are never rewritten. Use one writer per file. A truncated tail is refused
for appending; preserve it and start a new file. Reconciliation flags malformed
lines and missing run-end events instead of treating the remaining file as complete.

Attempts contain a UUID run/request pair, UTC timestamp, URL, method, full simulated
UA, expected access method, page ID and scenario. Every outgoing request carries
`X-Sim-Run` and `X-Sim-Request`. Responses contain status, an allowlist of relevant
headers, SHA-256 of the exact received bytes, received length, elapsed milliseconds
and the assertion result. The client requests identity content encoding. A partial
response records available status/headers, bytes and a **partial** hash on an error;
it never becomes a completed response. Exception messages and response bodies are
not retained. Cookies, credentials and IP addresses are not logged. Plans, new logs
and reports are created with owner-only permissions; protect existing files too.
Keep deployment-specific files out of version control.

## Origin evidence: verify correlation before relying on it

The usual nginx combined access log does **not** include these custom headers.
Sending them is not evidence that nginx recorded them. Arrange a dedicated JSONL
log with the site operator. This illustrative `http`-context format omits IPs and
cookies; attach it with `access_log` to the relevant server/location, following the
site's normal configuration review and reload process:

```nginx
log_format agent_verification escape=json
  '{"timestamp":"$time_iso8601","run_id":"$http_x_sim_run",'
  '"request_id":"$http_x_sim_request","method":"$request_method",'
  '"uri":"$request_uri","user_agent":"$http_user_agent","accept":"$http_accept",'
  '"status":$status,"content_type":"$sent_http_content_type",'
  '"upstream_status":"$upstream_status",'
  '"upstream_cache_status":"$upstream_cache_status","request_time":"$request_time"}';
```

Limit this dedicated log to public verification routes to avoid recording unrelated
private URLs or personal user agents. If normal traffic is excluded from the log,
background attribution will be incomplete; retain that limitation in the report.
Confirm this upstream is the Django application before interpreting its successful
Markdown responses as expected `AgentAccess` selections.

Send a short discovery/probe request to an uncached direct-export route, then inspect
the **actual** nginx record for both exact IDs, method, URI and UA. The reconciler
checks these against client attempts, along with compatible timestamps (up to five
seconds of log precision/clock skew). It refuses to infer origin arrival from a
missing record. A log without a valid matching pair reports
`correlation_verified: false`. Keep clocks synchronised and obtain complete log
rotation segments for the snapshot window. Static responses (`upstream_status: -`),
proxy-cache hits and multiple upstream attempts are distinguished. Revalidation,
background cache updates, disconnects and upstream failures can still involve
application selection and remain uncertain without stronger evidence.

## Snapshot and reconcile

Capture the same set of counter rows before and after the run. At a quiet boundary,
use a Django shell on the application host and write its result to a private JSON
file. This read-only snippet produces the expected schema:

```python
import json
from datetime import UTC, datetime
from wagtail_markdown_agents.models import AgentAccess

rows = list(AgentAccess.objects.values("access_date", "page_id", "agent", "access_method", "count"))
snapshot = {"captured_at": datetime.now(UTC).isoformat(), "rows": rows}
print(json.dumps(snapshot, default=str))
```

Start traffic only after the before snapshot completes. Wait for outstanding origin
work to finish before taking the after snapshot. Avoid pruning/resetting counters
inside the window. For busy deployments, arrange a consistent snapshot and record
concurrent traffic; a counter delta alone cannot identify which requester caused it.

```bash
PYTHONPATH=src python -m scripts.agent_simulator reconcile \
  --log client.jsonl --nginx origin.jsonl \
  --before before.json --after after.json --tolerance 0 --output report.json
```

The report uses `(UTC date, page ID, agent label, access method)` buckets and subtracts
before from after. It separates simulated origin selections, CDN hits, proxy-cache
hits, static bypasses, exclusions, background requests and independently verified
vendor requests. An origin selection can count despite an incomplete client receipt.
A client response without usable origin evidence remains uncertain. Request intervals
crossing UTC midnight contribute possible counts to each overlapping date, not a
fabricated exact date. These per-date upper bounds must **not** be summed as unique requests.

`residual = observed - expected - background - vendor`. `possible` is an upper bound
for uncertain simulated selections. Tolerance is an explicit absolute count **per
bucket**, defaults to zero and never removes uncertainty. Negative deltas indicate
pruning, reset or inconsistent snapshot scope. Missing correlation, malformed logs,
unmapped traffic or incomplete coverage make the result inconclusive. Retain all
bucket residuals even when a higher-level status is inconclusive. Reconciliation exits
`0` for matched evidence and `2` for a mismatch or inconclusive result.

Background attribution is limited to known page/export URLs and detectable access
methods; all other origin requests are reported separately. It cannot distinguish
a vendor from an unrelated sender by UA. A separately verified origin row may be
annotated `"traffic": "vendor", "verification": "evidence-reference"`; only use that
after the procedure below. The annotation is an operator assertion with a retained
reference, not something the CLI independently authenticates. Simulated run IDs
always stay simulated. For a separate vendor test page outside the simulated plan,
include its independently verified `page_id` and `access_method` in the annotated
origin row; these provide the counter dimensions for its unique test URL.

## Genuine vendor verification (separate procedure)

The simulator never claims that vendor-shaped traffic came from a vendor. Production
examples were checked on **21 September 2026** against [OpenAI's crawler
reference](https://developers.openai.com/api/docs/bots) and [Anthropic's bot
reference](https://privacy.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler).
OpenAI publishes complete examples: GPTBot 1.4, OAI-SearchBot 1.4 and ChatGPT-User 1.0.
Anthropic confirms ClaudeBot/training, Claude-SearchBot/search and Claude-User/user
retrieval; that page does not specify complete headers, so those full-header shapes
are explicitly synthetic. Other dataset entries are `dataset-synthetic`, including
Google-Extended and Applebot-Extended (robots.txt controls, not observed UAs).

1. Agree a small, cost-bounded run: supported vendor/model, maximum API/tool calls,
   public test URLs, time window, permitted bot behaviour and who operates it. Keep
   keys in environment variables or a secret store. Record tool/model versions and
   the agreed budget without keys, billing details or personal prompts.
2. Publish a harmless test page at a unique public path and record its manifest page
   ID. Keep its nonce out of simulator plans. Prepare canonical, `?output_format=md`
   and direct-export URLs. Confirm the relevant robots/CDN policy permits the intended
   fetch; any temporary policy changes need the operator's agreement.
3. Through the OpenAI API, use the Responses API's hosted `web_search` tool with live
   access enabled and an instruction containing the controlled URL. Record actual
   tool calls/actions and their result IDs. A search citation alone can come from
   indexed content and does not prove an origin fetch. Follow the current
   [OpenAI web-search documentation](https://developers.openai.com/api/docs/guides/tools-web-search).
4. Through the Anthropic API, use its server-side web fetch tool with the controlled
   URL in the user input and `max_uses` bounded by the agreed budget. Use an available
   supported model and tool version from the current [Anthropic web-fetch
   documentation](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-fetch-tool).
   Record whether a fetch actually ran and whether caching prevented a new request.
   Manual ChatGPT/Claude browsing can supplement this, but does not substitute for
   API-triggered evidence when that is the verification requirement.
5. Match the unique path and narrow UTC window to actual edge/origin evidence.
   Record observed UA, Accept, HTTP method, representation and application detection
   method; do not assume they equal the simulation. Validate vendor origin using the
   vendor's current published verification guidance/IP ranges or trustworthy edge
   verification. If IP inspection is necessary, perform it transiently and retain
   only the verification result/reference, not raw addresses. Never add IPs to
   `AgentAccess`. A nonce plus a UA is supporting evidence, not authentication.
6. Retain sanitised tool-event metadata and an origin-evidence reference. Annotate
   verified requests separately for reconciliation, count any additional vendor
   fetches, and report failures or unobserved fetches explicitly. Vendor tools may
   ignore a requested URL, use a cache, change UA, or not expose custom Accept
   headers. Test only the negotiation methods they actually support. You cannot
   force GPTBot/ClaudeBot training crawls or a particular search crawler through an
   on-demand API call; leave those genuine-origin cases unverified. Restore any
   agreed temporary policies and record the remaining capability limits.

Local tests cover planning, transport, cache assertions and evidence reconciliation.
They do not constitute deployed cache verification or genuine vendor-origin evidence.

## Independent registry update — 22 September 2026

Fleet identities and matching now come from the [agent registry](agent-registry.md).
Each identity is exercised through all triggers, but recognition-only User-Agent
requests expect HTML, no Markdown hash and no page counter. Explicit query/Accept
and export requests still expect Markdown. The free-plan warm-cache Accept-only
limitation also covers recognised agents that are outside the automatic-serving
subset. Historical run evidence retains the dataset and expectations used at the
time; regenerate plans when deploying a new registry version.
