# llms.txt discovery

`LlmsTxtGenerator` (#21) publishes a short introduction and links to the current
Markdown export tree. The format follows the [llms.txt proposal](https://llmstxt.org/#format):
one site heading, an optional blockquote, and an Explore section of Markdown links
with colon-separated descriptions. It contains no YAML or full page bodies.

```python
from wagtail_markdown_agents.export.llms_txt import LlmsTxtGenerator
from wagtail_markdown_agents.public_urls import export_url

# Run after page and index publication, outside the CMS transaction.
record = LlmsTxtGenerator().generate(site.pk)
if record is not None:  # Disabled sites produce no discovery file.
    url = export_url(record)
```

The default heading is Wagtail's `Site.site_name`, falling back to the hostname when
blank. Configure an optional **plain-text** introduction in Django settings:

```python
WAGTAIL_MARKDOWN_AGENTS = {
    "LLMS_TXT_DESCRIPTION": "Campaigns and resources for a fossil-free future.",
}
```

The setting defaults to `""`. It is one deployment-level string in v0.1, not an
editor-managed setting or generated summary. Whitespace is collapsed onto one line,
and Markdown/HTML syntax is escaped. Other types raise `ImproperlyConfigured` before
publication. Titles and descriptions are escaped using the same navigation helpers.

For the fixture in [the golden file](../tests/golden/llms.txt), output is:

```markdown
# Example Climate

> Campaigns and resources for a fossil-free future.

## Explore

- [Site index](http://example.org/markdown/index.md): Browse available content.
- [About us](http://example.org/markdown/about.md): Our purpose and approach.
- [Campaigns](http://example.org/markdown/campaigns/index.md): Explore our campaigns.
```

## Which links appear

The readable root index appears first when it exists, followed by the root directory's
available page exports in case-insensitive title order, with path and page ID as stable
tie-breakers. A child page-owned index represents its subtree; when that index is
unavailable, readable descendants appear directly. The generator shares the directory
selection used by [root/directory indexes](indexes.md). It does not invent topic
categories, inspect stored index text, or arbitrarily truncate a directory's entries.
An empty corpus without a readable root index gets the heading, optional introduction,
and “No exported pages are available.”

Every link uses the actual owned public URL, including path-hook relocations and host
URL prefixes. `LlmsTxtGenerator(urlconf=...)` supports an explicit offline URLconf.
Page entries pass the current ExportPolicy and writer availability checks; their titles
and search descriptions come from published revisions. The root index may be page-owned
or standalone, but must also pass a read bound to its current file. No metadata is drawn
from ungenerated, missing, stale, restricted, excluded or vetoed targets, nor from an
unexported root page. Other sites' exports are not included.

## Publication and integration

With the sandbox URLconf, `export_url(record)` resolves to `/markdown/llms.txt`.
Including the package routes at the site root instead exposes `/llms.txt`. The
[public routes](public-export-routes.md) serve stored bytes as UTF-8 `text/plain`,
including HEAD support, request gates and the existing cache headers. Generation
never happens on a request. This discovery document is an aggregate, so retrieving
it does not count as a page-read notification.

`IndexBatch` now finalises this file once per dirty site **after** root/directory
indexes. Its returned records include the discovery record. `IndexGenerator.generate`
still builds only indexes; if calling the APIs separately, call `LlmsTxtGenerator`
after page/index writes, then finalise the [manifest](manifest.md), because later
page writes retire aggregate publications. A failure keeps
the site dirty on the batch object for an explicit retry.

The generator captures site publication state before collecting targets. A change
during reading, rendering or upload rejects obsolete work with `StaleBuild`. New
restrictions/exclusions make prior dependent files unavailable immediately through
managed reads; a fresh build omits withdrawn metadata. Upload failures preserve the
previous complete file when it is still current. Unchanged inputs produce identical
bytes because this document has no generation timestamp.

The site-state fingerprint includes the configured introduction and site name, even
with no eligible pages. Changing either invalidates discovery and other site-dependent
indexes until they are rebuilt. Ordinary leaf exports stay available when only the
introduction changes. This uses the existing conservative site-dependency guard;
more granular dependency tracking remains future work.

The [publish lifecycle](publish-lifecycle.md) now regenerates discovery automatically.
Commands and restriction/move receivers remain #24/#69/#70.
The [content-hash manifest](manifest.md) is generated after llms.txt. This implementation adds no automatic crawling,
full-site concatenation file, editorial curation interface or new response headers.
