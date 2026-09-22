# 05 — Internal links to managed exports

Project-owner authorised after committing the #72 public routes. Covers #14's
package contract; negotiated HTTP entry points still depend on #25/#26.

- Resolve relative, absolute, root, parent and sibling canonical page URLs within
  the configured site origin. Use current policy and the target's actual owned
  export record, including hook relocations; never invent an ungenerated `.md` URL.
- Rewrite to absolute named public export URLs, preserving fragments. Root-relative
  and canonical-URL response selection must produce the same stored Markdown, and
  following a rewritten link through the direct route returns the target's bytes.
- Only an enabled `output_format=md|markdown` query may be removed. Preserve other
  query-dependent links, including tracking-looking parameters whose meaning the
  package cannot establish. Fragment-only links stay local.
- Follow unambiguous Wagtail redirects from database records, preferring a site
  redirect over a global one. Detect cycles and bound chains; never request a URL
  over HTTP. Preserve external redirects and custom subroutes.
- Keep external links, media/static/document links, images, raw HTML, inline code,
  fenced code and indented code unchanged. Preserve link labels, titles and the
  surrounding Markdown source, including lists, blockquotes and line endings.
- Rewrite reference-link uses into inline links. Leave their definitions and all
  image uses untouched, including an image sharing a rewritten link's definition.
- Retain unavailable URLs and emit `link_unresolved` once per parsed URL per run:
  `ineligible` for an existing page failing policy/publication eligibility;
  `not_found` for an absent page, missing/stale export or unresolved redirect.
  Ignored external/assets/query-dependent links emit no event.
- Apply rewriting after page hooks and supplied navigation, before attaching
  frontmatter. Canonical HTML permalinks in metadata remain unchanged.
- Exercise the minimum supported Markdown parser and current parser, filesystem
  and non-filesystem storage, and SQLite/PostgreSQL. Resolution caches exist only
  within one rewrite run; repeated target fragments need only one storage check.
