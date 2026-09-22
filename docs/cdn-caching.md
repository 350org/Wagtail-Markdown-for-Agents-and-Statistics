# CDN and cache guidance (#61)

How shared caches interact with Markdown negotiation on the same URL, what the
package sends to protect itself, what it cannot protect against, and how to
configure the layers in front of Django. A verification sequence and the results
measured on a live test deployment behind Cloudflare are at the end.

## Cloudflare quick checklist

The configuration below was measured on a controlled free-plan deployment on
21 September 2026. Check current account capabilities and agree security changes
with the site operator. A cache bypass does not bypass bot protection, WAF rules,
authentication or rate limits. These checks assume public, eligible pages with
current exports and the relevant negotiation settings enabled.

| # | Where in the dashboard | Setting | Why |
| --- | --- | --- | --- |
| 1 | Caching → Cache Rules | If HTML is cached with a "cache everything" rule: Edge TTL **use cache-control header if present**, never *ignore cache-control header* | Prevents storage of new negotiated Markdown when every cache layer respects the headers; does not remove old cached responses |
| 2 | Caching → Cache Rules | A **Bypass cache** rule matching `output_format=md` in the query string or a known agent User-Agent, ordered **after** rule 1 | Sends agents to the origin. The last matching rule wins; placed first, the rule does nothing |
| 3 | Security → Settings → Bot traffic | Review **Bot fight mode** with the operator; it was off for the controlled test | Challenges can prevent agent requests from reaching the origin |
| 4 | same → Configure AI bot policies | Allow the intended agent behaviours; Search and Training to suit the site's own policy | Blocked requests never reach the package |
| 5 | same dialog | **Bot Preference Sync** off, unless Cloudflare should manage `robots.txt` | It rewrites `robots.txt` at the edge over the origin's file |
| 6 | Security → Settings | Review **Browser integrity check** with the operator; it was off for the controlled test | It can block requests that look like bots |

An `Accept` clause was rejected by the tested free-plan account; do not assume it
is available without checking. Generate rule 2 from the deployed package's agent
list (substitute the hostname). This prints an expression without changing settings:

```bash
PYTHONPATH=src python3 -c '
import json
from wagtail_markdown_agents.data.agents import AGENT_UA_STRINGS as A
host = "www.example.org"
clauses = [f"http.request.uri.query contains {json.dumps(value)}"
           for value in ("output_format=md", "output_format=markdown")]
clauses += [f"http.user_agent contains {json.dumps(agent)}" for agent in sorted(set(A))]
print("(http.host eq " + json.dumps(host) + " and (" + " or ".join(clauses) + "))")'
```

The shipped dataset has 69 strings. Review the generated length against the
dashboard's expression limit. `contains` is case-sensitive where the package's
matching is not; check the actual UA spelling and query variants. Broad query
containment may bypass similar values without selecting Markdown. Regenerate the
rule after dataset changes and inspect the saved expression. The measured rule
used only the `md` query clause; the example also covers the supported `markdown`
alias and does not describe a further live settings change.

When measuring counters, review Speed Brain, Early Hints, Rocket Loader and Always
Online with the operator: extra traffic and HTML rewriting can affect the evidence.

What to expect once it is in place, on a URL whose HTML is already cached:

| Request | Response |
| --- | --- |
| Browser | cached HTML |
| Known agent User-Agent (`GPTBot`, `ClaudeBot`, …) | Markdown, from the origin |
| `?output_format=md` | Markdown when the query bypass reaches an eligible export |
| `Accept: text/markdown` from an unlisted User-Agent | cached HTML in the measured free-plan configuration |

Verify with the [curl sequence](#verifying-a-deployment) below,
in both orderings.

## The problem in one paragraph

Negotiated Markdown is served at the page's canonical URL, the same URL as the HTML.
A shared cache stores responses by URL. Unless it also distinguishes the request
headers that chose the representation, it will store whichever response came first
and replay it to everyone: cached HTML to an agent, or, far worse, cached Markdown
to a browser. HTTP's answer is `Vary`, but caches may not honour these variants,
and keying on `User-Agent` would fragment the cache for every browser string.
So the package sends no-store for Markdown, makes HTML vary on `Accept`, and
leaves User-Agent-only negotiation to a cache bypass rule that only the deployment
can add.

## What the package sends

| Response | Headers | Effect on a cache |
| --- | --- | --- |
| Negotiated Markdown (`query-param`, `accept-header` or `ua`) | `Cache-Control: private, no-store, max-age=0`, `Vary: Accept, User-Agent`, `Content-Type: text/markdown` | Never stored by a cache that honours `Cache-Control`. `Vary` is a second line of defence for caches that store despite `no-store`. |
| Explicit export route (`/markdown/…`, access method `export-url`) | same as above | Same defaults; a distinct URL does not by itself make public caching safe after withdrawal or restriction. |
| HTML for a page with a current export | `Link: <canonical?output_format=md>; rel="alternate"; type="text/markdown"`, `Vary: Accept` merged | A `Vary`-honouring cache keeps separate HTML and Markdown entries per `Accept`. HTML deliberately does **not** vary on `User-Agent`. |
| HTML for anything else | unchanged | Cached however the deployment caches HTML. |

Discovery advertises the query form, but it gets a separate cache key only when
every cache preserves `output_format`. Otherwise a cache can collapse it onto the
HTML key. Preserve that parameter or bypass the request at every layer, including
hosting caches behind the CDN. Cloudflare's [cache-key documentation](https://developers.cloudflare.com/cache/how-to/cache-keys/)
describes configurations that ignore query strings.

The `construct_markdown_response_headers` hook receives `access_method` in its
context and can add or omit headers, including host-specific ones:

```python
from wagtail import hooks


@hooks.register("construct_markdown_response_headers")
def cache_headers(headers, request, context):
    headers["CDN-Cache-Control"] = "no-store"  # Cloudflare and other CDNs
    headers["X-Accel-Expires"] = "0"  # nginx proxy_cache
    headers["X-LiteSpeed-Cache-Control"] = "no-cache"  # LiteSpeed
```

This example retains the default private/no-store policy. Public caching requires
the additional checks under [relaxing headers](#relaxing-headers-per-method).

## The two request orderings

Both orderings must hold on every deployment, for every enabled trigger. "Blind"
means a cache that does not distinguish the relevant `Vary` headers. The measured
Cloudflare configuration behaved this way; check the actual cache configuration.

| Order | Trigger | `Vary`-honouring cache | `Vary`-blind cache |
| --- | --- | --- | --- |
| HTML first, then agent | `query-param` | Markdown if the query is preserved or bypassed | Markdown if the query is preserved or bypassed |
| | `accept-header` | Markdown (separate variant) | **cached HTML** |
| | `ua` | **cached HTML** (HTML has no `Vary: User-Agent`) | **cached HTML** |
| Agent first, then browser | any | HTML (Markdown was `no-store`) | HTML, **provided the cache honours `no-store`** |

Two conclusions. The agent-then-browser direction is safe as long as the cache
respects origin `Cache-Control`; a cache configured to ignore origin headers
("cache everything, override TTL") will store the Markdown and serve it to browsers,
and no application header can prevent that. The browser-then-agent direction is
reliable for the query trigger only if its query is preserved or bypassed; Accept
and UA negotiation need the cache to either bypass or key on those requests.

## Bypass, do not key

For Accept-header and User-Agent negotiation behind a blind cache, add a rule that
sends agent-shaped requests to the origin without consulting or filling the cache:

- request header `Accept` contains `text/markdown`, or
- `User-Agent` contains one of the known agent substrings (`data/agents.py`), or
- query string contains `output_format=md` or `output_format=markdown`.

Not every cache lets a rule read `Accept`: the tested free-plan account rejected it
(see the [measurements](#measured-on-cloudflares-free-plan)). An unlisted Accept-only
client therefore still received warm HTML in that configuration. Cloudflare's
[rule-order documentation](https://developers.cloudflare.com/cache/how-to/cache-rules/order/)
specifies that the last matching value for a setting wins: place cache bypass after
cache-everything.

Bypass, rather than adding `Accept` or `User-Agent` to the cache key. Keying on
`Accept` is only worthwhile on caches that normalise it (Varnish, Fastly, Cloudflare
Enterprise custom cache keys); keying on `User-Agent` fragments the cache for every
browser build. A bypass rule costs one origin hit per agent request, which is what
the statistics need anyway.

Bot protection is the other half. Cloudflare's Bot Fight Mode and AI-bot blocking,
WP Engine and similar hosts' bot rules, and WAF managed rules all challenge or block
AI User-Agents depending on deployment policy. An agent that receives a 403 or a
JavaScript challenge gets nothing, whatever the origin would have served. Agree
with the operator how to permit the intended agents on the relevant hostnames.

Note that the distinction this package draws between an agent fetching a page for a
person and a crawler collecting a corpus is now drawn at the CDN too. Cloudflare's
[accountable mixed-use crawlers](https://blog.cloudflare.com/accountable-mixed-use-ai-crawlers/)
announcement (15 September 2026) classifies crawler behaviour as **search**,
**training** or **agent** and lets each be allowed or refused separately, replacing
the single "Block AI bots" switch; a site can stay indexed for search and refuse
training without also turning away user-directed agents. Serving Markdown to agents
is the origin-side half of the same split: the CDN decides who may fetch, the origin
decides what they receive. The practical consequence for a deployment is that the
**agent** behaviour must be set to allow, or none of the triggers in this package are
ever reached.

## Layer by layer

**Cloudflare, free plan.** Cache Rules can match on hostname,
query and User-Agent in the tested account; its `Accept` condition was rejected
(see the measurements below). Two rules: "cache everything"
for the site with Edge TTL *use cache-control header if present, otherwise use this
TTL*, so HTML is cached and Markdown's `no-store` is honoured; and a "bypass cache"
rule **after** it for the agent-shaped conditions above. Order matters and runs
against intuition: when several Cache Rules match, the last one to set a setting
wins, so a bypass rule placed first is silently overridden by the cache-everything
rule below it. Never choose *ignore cache-control header*. Review security controls
and ownership of `robots.txt` separately, using the operator's intended access policy.
`CDN-Cache-Control: no-store` from the hook is honoured by Cloudflare on all plans
and supplements the origin header. Cloudflare's [current cache-control documentation](https://developers.cloudflare.com/cache/concepts/cache-control/)
describes default `Vary` limitations and configurable exceptions. Do not assume
this deployment varies on `Accept` or `User-Agent` without verifying it.

**Cloudflare, Enterprise.** Custom cache keys can include a normalised `Accept`
header, which turns the Accept trigger into a proper variant. UA still needs bypass.

**Varnish or Fastly.** Normalise `Accept` to two values in `vcl_recv` (contains
`text/markdown` or not) and hash on it, or `return (pass)` for agent-shaped
requests. Both honour `Vary`, but only usefully after normalisation.

**nginx `proxy_cache` or `fastcgi_cache`.** Add a `map` of `$http_accept`,
`$http_user_agent` and `$arg_output_format` to a `$markdown_bypass` variable and use
it in `proxy_cache_bypass` and `proxy_no_cache`. nginx honours `X-Accel-Expires: 0`
from the hook, which stops Markdown being stored even without the map.

**LiteSpeed.** `X-LiteSpeed-Cache-Control: no-cache` from the hook stops Markdown
being stored. Add a rewrite rule excluding agent-shaped requests from the page cache
for the Accept and UA triggers.

**Django's own cache middleware** (`UpdateCacheMiddleware` and
`FetchFromCacheMiddleware`). Django builds cache keys from the URL plus the response's
`Vary` headers and never stores `private` responses, so HTML varies on `Accept` and
Markdown is never stored. UA-only requests for a cached HTML page still receive the
cached HTML: place the package middleware **before** the cache middleware in
`MIDDLEWARE` so negotiated requests are answered before the cache is consulted.

**WhiteNoise.** WhiteNoise answers only `STATIC_URL` from `STATIC_ROOT` and never
sees a page URL, so it cannot interfere with negotiation, and its middleware
position relative to the package's does not matter. The export tree lives outside
`STATIC_ROOT` by default. Do not move it under static files or serve it with
`static()` or a web-server alias: those paths skip site, policy and freshness checks,
send WhiteNoise's or nginx's cache headers instead of the package's, and record no
statistics. The explicit export routes exist for direct retrieval.

**Reverse proxies you do not control** (managed WordPress-style hosts, PaaS edge
caches). Verify whether the provider preserves or bypasses `output_format` and
serves explicit export routes correctly. Discovery advertises the query trigger,
but it cannot guarantee the provider's cache key. Record any Accept/UA limitations.

## Relaxing headers per method

Keep the default private/no-store headers unless the deployment has verified both
representation separation and content withdrawal at every cache layer:

| Access method | Separate cache key? | Requirements before public caching |
| --- | --- | --- |
| `query-param` | Only if every cache preserves the query | Verify keys, bounded freshness and withdrawal |
| `export-url` | Distinct path, subject to cache rewrites | Verify keys, bounded freshness and withdrawal |
| `accept-header` | Shares the page URL | Every cache must distinguish Accept variants; UA-only requests still need bypass |
| `ua` | Shares the page URL | Keep private/no-store and bypass agent requests |

Public caching of the query and explicit routes has a cost: repeat requests are
answered by the cache and never reach Django, so they are not counted.

Cached copies also skip origin eligibility and freshness checks. Unpublishing,
restricting or excluding a page cannot retract a previously cached response. Agree
a bounded TTL and reliable invalidation on regeneration and withdrawal, including
browser caches and any permitted stale serving. If prompt withdrawal is required,
retain no-store. The package does not provide deployment-wide CDN invalidation.

## Statistics gaps

The daily counters record **response selection at the origin**: one increment when
Django chooses a Markdown response for a page GET. They cannot see:

- cache hits at any layer, for HTML or for Markdown you chose to make cacheable;
- requests blocked or challenged before the origin (bot rules, WAF, rate limits);
- exports served by WhiteNoise, a web-server alias or object storage directly;
- whether the client received the body (the count happens at selection, not delivery).

Quantify the gap from the CDN's side: Cloudflare's `cf-cache-status` header per
request, its analytics, or the origin access log versus a known set of test requests
(the traffic simulator, #59). The report states these limits; do not present counters
as total agent traffic.

## Verifying a deployment

Agree a request budget and use public, eligible pages with current exports. Run
from outside the origin network and confirm the requests traverse the intended CDN
and hosting caches. These are GET requests; `-D - -o /dev/null` discards the body,
unlike `curl -I`, which sends HEAD. Save bodies privately for content comparisons.

```bash
H=https://www.example.org/a-published-page/
# Browser first: repeat within the budget until headers demonstrate warm HTML.
curl -sS -D - -o /dev/null -A 'Mozilla/5.0' -H 'Accept: text/html' "$H"
curl -sS -D - -o /dev/null -A 'Mozilla/5.0' -H 'Accept: text/html' "$H"
curl -sS -D - -o /dev/null -A 'GPTBot/1.4' -H 'Accept: text/html' "$H"
curl -sS -D - -o /dev/null -A 'GPTBot/1.4' -H 'Accept: text/markdown' "$H"
curl -sS -D - -o /dev/null "$H?output_format=md"
# Unlisted Accept-only: cached HTML was the measured free-plan limitation.
curl -sS -D - -o /dev/null -A 'MarkdownVerification/1.0' -H 'Accept: text/markdown' "$H"
curl -sS -D - -o /dev/null -A 'Mozilla/5.0' -H 'Accept: text/html' "$H"
# Agent first: prepare and independently verify this URL is uncached before use.
H2=https://www.example.org/another-page/
curl -sS -D - -o /dev/null -H 'Accept: text/markdown' "$H2"
curl -sS -D - -o /dev/null -A 'Mozilla/5.0' -H 'Accept: text/html' "$H2"
```

Repeat agent-first checks for query and UA triggers on separately prepared uncached
URLs, or arrange specific purges with the operator. Request order alone does not
prove a cold start; cache-busting another URL does not test the ordinary warm key.
Check a real explicit export route and HEAD responses too. Inspect status, content
type, cache-control, Vary, source and cache-status headers, plus origin provenance.

A `text/markdown` body on a request without an agent trigger, at any point, is a
cache-poisoning failure: stop traffic and agree correction and purging before
continuing. HTML alone is not proof of a cache fault: confirm export eligibility
and response provenance. Page Markdown GET selections should increment statistics;
HEAD, HTML, aggregates and cache hits should not.

To test that a Cloudflare bypass rule is live independently of the origin's headers,
request an HTML URL that matches its query clause, twice, for example
`https://www.example.org/a-listing-page/?output_format=mdprobe`. With the rule working
both responses were `DYNAMIC` in the tested deployment. `MISS` then `HIT` indicates
that bypass did not apply as intended; inspect matching conditions and rule order.

Before taking the baseline, verify an actual origin record containing the exact
run and request IDs, method, URI, UA and compatible UTC time. Finish discovery and
probes first; wait for origin work to finish before the final snapshot. Preserve
per-bucket residuals and document any unlogged background traffic. The
[simulator guide](agent-simulator.md#snapshot-and-reconcile) describes the evidence
format and counter reconciliation.

## Measured on Cloudflare's free plan

Run against a live test deployment on 21 September 2026: Wagtail's bakerydemo with
this package behind
Cloudflare free, one "cache everything" Cache Rule (Edge TTL *use cache-control
header if present, cache with Cloudflare's default TTL for the response status if
not*; Browser TTL *respect origin TTL*). These are observations, not predictions.

**The observed failure was HTML reaching agents.** Initial probes returned origin
Markdown with `cf-cache-status: BYPASS`, followed by browser HTML. No browser
Markdown was observed. Those request orders did not independently prove cold cache
state. On warm HTML URLs without effective bypass, agent requests received `HIT`
and `text/html` without reaching the origin. Origin response headers cannot repair
a request already answered by the edge, or protect against rules that override them.

**The tested free-plan account rejected an `Accept` Cache Rule.** An expression
containing `any(http.request.headers["accept"][*] contains "text/markdown")` was
rejected on save with *"service identity is not authorized"*, while a query-string
expression saved. This records a dated account limitation; verify current
capabilities before promising header-based bypass or custom cache keys.

**The measured UA bypass used substring clauses**, without regex: 69
`http.user_agent contains "..."` clauses from the deployed dataset. Including its
hostname and query condition, the saved expression contained 3,050 characters.

**A bypass rule must come after the cache-everything rule.** With the bypass rule
ordered first, it had no effect at all: even an HTML URL matching its query clause
went `MISS` then `HIT`. Cache Rules do not stop at the first match; every matching
rule is applied in order and the last one to set cache eligibility wins, so the
cache-everything rule re-enabled caching for the requests the bypass rule had just
excluded. Moved below it, the same expression worked immediately: on a warm URL
`GPTBot` and `ClaudeBot` User-Agents received `text/markdown` with
`cf-cache-status: DYNAMIC` and appeared in the origin log, while browsers kept
receiving `HIT` and `text/html`. With the rule in place the remaining gap on the free
plan is exactly one trigger: `Accept: text/markdown` from a client with an
unlisted User-Agent still receives cached HTML on a warm URL.

The subsequent [bounded verification report](verification/2026-09-21-bounded-live-run.md)
records 1,000 simulated requests: 964 passes, 36 expected Accept-only limitations,
zero failures and 603 expected/observed counter selections. All 285 browser controls
received HTML. Six fixtures, cold-cache proof, multi-day behaviour and genuine
vendor fetches remain outstanding; the reconciler correctly returned `inconclusive`.

Use explicit export routes or query negotiation with verified query preservation
or bypass. Keep private/no-store defaults and test every cache layer. Record the
Accept-only limitation where the deployment cannot distinguish those requests.

## WordPress cache parity

The WordPress reference for this follow-up is commit
[`041beea`](https://github.com/chancery-lane-project/wp-mfa-plugin/commit/041beeac189917733bb830067bd674e88fcb96f4).
Both implementations now describe counters as origin page Markdown GET selections;
HEAD probes do not count. The live results above apply only to Wagtail.

| Behaviour | Wagtail | WordPress reference |
| --- | --- | --- |
| Canonical page Markdown GET | Counts an eligible page selection | Counts a singular-post selection |
| HEAD | No page increment | No page increment |
| Direct page export GET | Application route checks policy/freshness and counts `export-url` | Static uploads normally skip the negotiator and its counters |
| Aggregate downloads | No page increment; page-owned indexes remain page exports | Static indexes/manifests/bundles do not increment negotiator counters |
| CDN hits or blocked requests | Not visible to origin counters | Not visible to origin counters |

A WordPress verification adapter must account for its export format, static routes
and taxonomy behaviour. Do not reuse Wagtail's expected counts unchanged or present
this report as WordPress live verification. The [original parity audit](wordpress-parity-audit.md)
retains its historical baseline and broader feature scope.
