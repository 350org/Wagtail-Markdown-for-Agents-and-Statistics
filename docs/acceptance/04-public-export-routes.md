# 04 — Public managed export routes

Project-owner authorised after the #72/#68 next-step recommendation. These package
contracts support v0.1 retrieval; they do not add customer deliverables.

- The host explicitly includes a namespaced URLconf before Wagtail's catch-all.
  The sandbox mounts it at `/markdown/`; projects may choose another prefix.
  Named routes expose page/directory Markdown, `llms.txt` and `manifest.json`.
- Given a current published export, GET returns its complete stored bytes with the
  correct UTF-8 content type. HEAD has the same headers and no body. Other methods
  return 405 and neither generate content nor record a page read.
- URLs use the configured site's origin and the included route prefix, including
  relocated exports. HTML permalinks remain unchanged. The alternate-URL helper
  chooses canonical HTML plus `output_format=md` while query negotiation is enabled,
  otherwise the explicit export route; negotiation itself remains #25/#26.
- A missing, obsolete, private, excluded, cross-site or unmanaged export returns
  404. Unknown hosts cannot use Wagtail's default-site fallback to retrieve exports.
  Raw object keys, traversal, encoded traversal, backslashes, nulls and overlong
  paths are rejected before storage lookup. Host validation uses ALLOWED_HOSTS.
- A restricted descendant immediately makes an old site listing or manifest
  unavailable, even before automatic lifecycle receivers are installed.
- Shared serving returns no response for a missing export so future negotiated
  requests can fall through to HTML. It binds the opened file to the record checked
  for site ownership and response metadata, including replacement races.
- Responses use private/no-store cache headers, Vary, a canonical HTML source for
  pages and configurable Content-Signal. A response-header hook may customise or
  omit headers; invalid values cannot reach the response.
- A request-specific hook may veto serving, including aggregates. It is evaluated
  on every request and cannot make an otherwise ineligible export available.
- Only successful page GET response selection emits the best-effort served signal
  with `access_method=export-url`; HEAD, aggregates, errors and vetoes do not. This
  supplies the integration point for #33; persistent statistics remain separate.
- Exercise named URLs, link traversal and all gates with filesystem storage and a
  backend without filesystem/mtime/listing APIs. Index/llms/manifest generators and
  automatic internal-link rewriting remain #14/#20–#22.
