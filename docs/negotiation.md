# Content negotiation

`AgentMarkdownMiddleware` implements the detection portion of #25 and the
request-phase serving portion of #26. An agent asking for a page at its normal URL
receives the page's current published Markdown export; everyone else receives HTML.
Missing exports fall through to HTML (#30). Nothing is generated during a request.
The response phase, which adds discovery headers to HTML, is described in the
[discovery guide](discovery-headers.md) (#27/#28).

## Install the middleware

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "wagtail_markdown_agents.middleware.AgentMarkdownMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    # …the rest of the site's middleware…
]
```

Place it after `SecurityMiddleware` and before `CommonMiddleware`, as the sandbox
does. A negotiated request is then answered before slash-appending redirects and
any downstream cache middleware. The [system checks](system-checks.md) enforce this
order (`E002`/`E003`) and warn when the middleware is absent (`W001`).

## Detection

Three triggers are checked in a fixed order; the first enabled match wins and
becomes the response's access method label. The labels are stable statistics
dimensions (#32/#33) and must never be renamed.

| Precedence | Trigger | Setting | Label |
| --- | --- | --- | --- |
| 1 | `?output_format=md` or `?output_format=markdown` (case-insensitive) | `NEGOTIATE_QUERY_PARAM` | `query-param` |
| 2 | `Accept` contains the explicit media range `text/markdown` with `q > 0` | `NEGOTIATE_ACCEPT_HEADER` | `accept-header` |
| 3 | `User-Agent` contains a known agent substring | `NEGOTIATE_USER_AGENT` | `ua` |

The explicit export routes keep their own `export-url` label (#72) and are not
affected by negotiation precedence.

The Accept rule parses media ranges rather than searching for a substring.
`text/markdown; charset=utf-8` and `text/html, text/markdown;q=0.1` match.
`text/*`, `*/*`, `text/markdown;q=0`, `text/x-markdown` and a browser's
`text/html,*/*;q=0.8` never match, so browsers and plain curl are never served
Markdown by accident. An unparsable `q` keeps the range: the client still asked
for Markdown explicitly.

Known agents come from the append-only dataset in `data/agents.py`. Matching is a
case-insensitive substring test in dataset order and returns the first matching
entry, so an agent's label stays the same as the list grows. `detect_agent()` runs
independently of `NEGOTIATE_USER_AGENT`; the toggle only decides whether a matched
agent is *served* Markdown, so statistics can still label a known agent that
arrived through another trigger. HTML responses are not counted.

All three settings default to `True`. Disabling every trigger leaves only the
explicit export routes.

## Which requests are candidates

Only requests that would otherwise reach Wagtail's page-serving route are
intercepted, and only when the routed page is requested at its canonical URL:

- GET and HEAD only. Form submissions and every other method pass straight through.
- The request path must resolve to the `wagtail_serve` route in the active URLconf.
  Admin, preview, API, document, static and the package's own explicit export routes
  are never candidates, whatever headers they carry.
- The routed page's own URL must equal the request path. RoutablePage sub-routes and
  paths without a trailing slash fall through (`CommonMiddleware` still redirects
  the latter afterwards).
- The request host must pass `ALLOWED_HOSTS` and match a policy-enabled Wagtail Site.
  Another host cannot borrow the default site's exports.

A matched request then looks up the page's recorded export by site and page ID.
That record holds the actual logical path, so hook-relocated exports and
`blog/index.md` versus `blog.md` are served correctly without deriving a path from
the URL. Serving goes through the same shared function as the direct routes: fresh
ownership, published-state and eligibility checks, the `markdown_serve_allowed`
veto hook and the `construct_markdown_response_headers` hook, all documented in
the [public route guide](public-export-routes.md).

Wagtail's `before_serve_page` hooks do not run for negotiated Markdown responses;
they continue to govern the HTML fallback. Request-specific gates for Markdown
belong in `markdown_serve_allowed`, which is evaluated on every request and never
cached.

## Responses and fallback

A successful response is the stored bytes with `Content-Type: text/markdown;
charset=utf-8`, `Cache-Control: private, no-store, max-age=0`, `Vary: Accept,
User-Agent`, `X-Markdown-Source` (the canonical HTML URL) and the configurable
`Content-Signal`. `CONTENT_SIGNAL` defaults to `ai-input=yes, search=yes`, an
operator policy statement that says nothing about `ai-train`; set it to `""` to omit
the header. Optional server-specific headers such as `X-Accel-Expires: 0` or
`X-LiteSpeed-Cache-Control: no-cache` are added through the header hook. None of
these replace CDN or shared-cache configuration; see the
[CDN and cache guide](cdn-caching.md).

HEAD returns GET's headers without a body and is never counted as a page read. Only a
successful page GET selection emits `markdown_served` with the access method.
The [statistics receiver](agent-access-stats.md) records one daily increment from
that signal for negotiated and direct page-export GETs.

Every miss returns the normal HTML response with a 200 status: no export record, a
deleted or replaced storage object, an object withdrawn between lookup and open, a
private, unpublished or excluded page, a request veto, a disabled site or a disabled
trigger. The middleware never returns 404 for a page that exists and never
generates content on request. The explicit export routes have the opposite
contract: a missing artefact there is a 404.

## Discovery headers

HTML 200 responses for pages with a current export gain `Link: <…>;
rel="alternate"; type="text/markdown"` and `Vary: Accept`, and the
`{% agent_markdown_link %}` template tag emits the matching `<link>` element. The
advertised URL is the canonical URL with `output_format=md` while query negotiation
is enabled, otherwise the explicit route. Resolution is cached and invalidated by
publication; the cache never authorises serving. See the
[discovery guide](discovery-headers.md).

## Caching note

Negotiated Markdown responses are private and uncacheable. HTML varies on `Accept`
only: a shared cache that stores HTML can still return it to a UA-only agent because
HTML deliberately does not vary on `User-Agent`. Deployments that rely on UA
negotiation need a cache bypass or variant rule for known agents, and deployment
tests must cover cached HTML followed by a UA-only fetch (#59). A cache that ignores
`Vary` altogether, as Cloudflare does for HTML, returns cached HTML to an
`Accept: text/markdown` request as well, and on Cloudflare's free plan no rule can
match `Accept` to prevent it; `?output_format=md` and the export URLs are the
triggers that work behind any shared cache. The
[CDN and cache guide](cdn-caching.md) covers both orderings, bypass rules per cache
layer, per-method header overrides, the statistics gaps and what was measured on
the live sandbox.
