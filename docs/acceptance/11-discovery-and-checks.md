# 11 — HTML discovery headers, template tag and configuration checks

Project-owner authorised for #27, #28 and #29, with the #68 discovery/serving
boundary. Scenario S7 of [01-contentpage-end-to-end.md](01-contentpage-end-to-end.md)
describes the `Link` header for the 350.org fixture; these scenarios are the generic
package contract on the sandbox fixture.

## Discovery headers (#27)

- Given a published page with a current export, GET or HEAD at its canonical URL
  with a browser's headers returns HTML 200 with
  `Link: <canonical URL?output_format=md>; rel="alternate"; type="text/markdown"`
  and `Vary` containing `Accept` but not `User-Agent`. The negotiated Markdown
  response carries no discovery `Link`.
- An HTML response that already has `Link` and `Vary` values keeps them: the
  Markdown link is appended and `Accept` merged.
- With `NEGOTIATE_QUERY_PARAM` disabled the advertised URL is the page's explicit
  export route, including hook-relocated and `index.md` paths, which is the same
  choice the public `alternate_url` helper makes. Without the package URLconf in
  that configuration no header is added.
- A page with no export record, a deleted or withdrawn storage object, a private
  (own or inherited restriction), excluded or unpublished page, and a record whose
  path no longer matches policy are not advertised: no `Link`, no `Accept` in
  `Vary`, and the HTML response is otherwise unchanged.
- Only HTML 200 responses to GET/HEAD page-route requests at the page's canonical
  URL on the request's policy-enabled site are considered: admin, non-page,
  unknown and sub-route paths, redirects, other hosts and previews are untouched.
- Resolution is cached, hits and misses alike, for `DISCOVERY_CACHE_TIMEOUT`
  seconds (default 60; `0` disables). Generating, deleting or relocating an export
  is visible on the next request, in any process. Entries are scoped by site,
  request path and export storage identity.
- The cached advertisement never authorises a read: after a storage object
  disappears without a publication event the header may persist until expiry, but
  negotiated requests fall through to HTML and the explicit route returns 404.
- `LINK_HEADER = False` disables the response phase without affecting negotiated
  serving or the template tag.
- A `construct_markdown_html_headers(values, request, context)` hook can change,
  add or omit headers (`None`/`""` omits) with `site`, `path`, `alternate_url`,
  `export_path` and a lazily loaded `page` in context; omission never removes a
  header the HTML response already had; malformed names or values raise
  `ImproperlyConfigured`.
- Hostile request paths (`..`, encoded traversal, null bytes, backslashes,
  absolute paths, `.objects` keys, overlong segments) with any negotiation trigger
  never open storage, never serve Markdown and never gain a `Link` header (#68).
- Exercised with filesystem storage and a backend without filesystem APIs.

## Template tag (#28)

- `{% load wagtail_markdown_agents %}{% agent_markdown_link %}` renders
  `<link rel="alternate" type="text/markdown" href="…">` for the context page
  when the middleware would advertise it, with the same URL, and nothing otherwise
  — including previews, missing, revoked and ineligible exports, and pages without
  an export such as the home page. An explicit page argument is accepted; the
  href is HTML-escaped; a missing `request` resolves the page's own site.

## Configuration checks (#29)

- The sandbox configuration produces no package check messages.
- The middleware absent from `MIDDLEWARE` warns (W001); listed before
  `SecurityMiddleware` errors (E002); listed after `CommonMiddleware` errors
  (E003); both errors are reported together when both apply.
- A non-dict `WAGTAIL_MARKDOWN_AGENTS` errors (E004). Unknown keys warn (W002)
  naming the key and listing the known keys.
- Wrong shapes error (E005) naming the key: non-boolean toggles, a
  `CONTENT_SIGNAL` with control characters or not a string, a non-positive,
  boolean or string `STATS_RETENTION_DAYS`, a negative or string
  `DISCOVERY_CACHE_TIMEOUT`, and malformed `PAGE_TYPES`, `PAGE_FIELDS`,
  `RENDERERS`, `SITES` and `LLMS_TXT_DESCRIPTION`. Valid values, including `0`
  and fractional cache timeouts, pass.
- The package URLconf missing warns (W003), or errors (E006) when
  `NEGOTIATE_QUERY_PARAM` is also disabled; including it at any prefix passes.
- Checks never query the database or touch storage.
