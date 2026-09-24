# Internal link rewriting

`render_page` now rewrites links in the assembled body after page hooks and supplied
navigation, before attaching YAML frontmatter. Canonical HTML metadata URLs are not
rewritten. For custom Markdown pipelines:

```python
from wagtail_markdown_agents.rendering.links import rewrite_links

markdown = rewrite_links(markdown, published_page)
```

The optional third argument is the shared render context (`page`, `site`, `locale`
and project context). Resolution uses the source page's canonical URL as its base
and the context site's configured hostname/port. It does not treat another origin
or port as a site alias.

## Targets and query strings

Same-site canonical page links resolve through the CMS tree, current ExportPolicy
and a successfully published ownership record. The writer checks the exact stored
generation before the resolver calls `export_url`. A relocated target therefore
uses its actual public route, such as `https://example.org/markdown/custom/page.md`.
Already-public export links, including aggregate links, are checked too. The URLconf
must be included in the host project before a managed target can supply its URL.

Fragments are preserved. Fragment-only links remain unchanged. The sole query
parameter with semantics owned by this package is `output_format`; `md`/`markdown`
may be removed while `NEGOTIATE_QUERY_PARAM` is enabled. All other query strings
remain untouched, including pagination, search, filters and tracking-looking keys.
The resolver does not guess that an unfamiliar query is safe to discard.

Root, parent and sibling links use the source page's canonical directory. Custom
query routes/subpages and non-Wagtail application routes retain their HTML URLs.
MEDIA_URL, STATIC_URL and the named Wagtail document-serving route are excluded.
Images and external links are never rewritten.

When a canonical page is absent, the resolver can follow Wagtail's stored redirects.
A site-specific redirect takes precedence over global redirects; multiple candidates
at the selected scope are ambiguous and remain unchanged. Chains are bounded to
eight resolution steps, with cycle detection. External redirects and meaningful
query/custom-subroute redirects stay as authored. Resolution makes no outbound HTTP
requests; remote storage may still perform IO through its configured backend.

## Markdown preservation

`markdown-it-py` identifies CommonMark link syntax. The implementation edits source
destinations instead of rendering the document again, preserving labels, inline
titles, whitespace and formatting. It supports ordinary links, angle destinations,
autolinks, nested image links and full/collapsed/shortcut reference links. Rewritten
reference **uses** become inline links; definitions remain unchanged so an image
sharing that definition keeps its original destination and alt text.

Inline code, fenced/indented code, images and raw HTML are excluded. List/blockquote
markers and heading syntax are mapped back to the original source before editing.
A construct that cannot be mapped exactly is left unchanged. Bare URLs outside
autolinks and raw HTML attributes are not rewritten by this API; ordinary rich-text
HTML has already been converted to Markdown by the page renderer.

## Missing targets and generation order

A link changes only when its target has a current, readable managed export. Missing,
stale and ungenerated targets retain their original HTML URLs. The `link_unresolved`
signal receives `url` and `reason`, once per parsed URL per rewrite run:

- `ineligible`: the page exists but is not live, is
  restricted/excluded, fails a policy hook, or belongs to another site scope.
- `not_found`: no page was found, the current export is absent/stale/missing from
  storage, or a redirect cannot be resolved unambiguously.

Ignored external, asset and query-dependent links produce no event. Receiver
exceptions are logged without dropping authored content. The resolver caches URL
and target results only for one run; a later run always checks fresh state.

This makes generation order visible: links to pages not exported yet remain HTML
links on the first pass. Bulk generation (#24) must establish target records before
its final link pass if every available target should use Markdown URLs, including
cycles and self-links. URL resolution checks availability at rendering time; direct
serving independently checks eligibility on every request. Lifecycle-driven rebuilds
after target changes remain #23/#69/#70. Offline bundle-relative conversion is #42.
