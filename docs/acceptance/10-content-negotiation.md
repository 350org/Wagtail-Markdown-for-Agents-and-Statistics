# 10 — Content negotiation and middleware serving

Project-owner authorised for #25, #26 and #30. Scenario S7/S9 of
[01-contentpage-end-to-end.md](01-contentpage-end-to-end.md) describe the same
behaviour for the 350.org fixture; these scenarios are the generic package contract
on the sandbox fixture.

- Given a published page with a current export, GET at its canonical URL with
  `?output_format=md` (or `markdown`, any case), with `Accept` containing the
  explicit `text/markdown` media range, or with an automatic-serving agent User-Agent returns the
  stored Markdown with `text/markdown; charset=utf-8`, private/no-store cache
  headers, `Vary: Accept, User-Agent`, the canonical HTML source and Content-Signal.
- The access method label is the first matching trigger in the order query
  parameter, Accept header, User-Agent: `query-param`, `accept-header`, `ua`.
  Direct export routes keep `export-url`. Labels never change.
- `Accept: */*`, `text/*`, `text/markdown;q=0`, `text/x-markdown` and a browser's
  default Accept header receive HTML. Plain curl receives HTML.
- Known-agent matching is a case-insensitive product-token test returning the first
  identity in registry order. Automatic serving also requires its auto_markdown flag. It still labels agents when `NEGOTIATE_USER_AGENT`
  is off; the toggle only disables serving by that trigger. Each trigger can be
  disabled independently; disabled triggers fall through to the next.
- HEAD returns the GET headers and no body and records no page read. POST, PUT,
  PATCH, DELETE and OPTIONS are never intercepted, whatever their headers or query.
- Only requests routed to Wagtail's page-serving route at the page's canonical URL
  are candidates: admin, preview, document, explicit export and unknown routes and
  paths without a trailing slash pass through untouched. Another host cannot obtain
  the default site's exports through negotiation.
- A page with no export record, a deleted storage object, an object withdrawn or
  replaced between lookup and open, a private (own or inherited restriction),
  unpublished or excluded page and a request veto all return the normal HTML
  response. No 404 is produced for an existing page, nothing is generated during
  the request and no page read is recorded.
- Hook-relocated exports and page-owned directory indexes are served from their
  recorded paths at the page's canonical URL.
- The `markdown_serve_allowed` veto and `construct_markdown_response_headers` hooks
  apply to negotiated responses with the negotiated access method in context.
  `before_serve_page` hooks keep governing the HTML fallback only.
- Exercised with filesystem storage and a backend without filesystem APIs.
