# Architecture design — wagtail-markdown-for-agents

Status: accepted (July 2026). This document is the design authority for the port; PRs
that deviate from it must update it in the same change.

This describes the product roadmap, which is wider than v0.1. The v0.1 milestone on
the issue tracker defines what the first release delivers; bundles, ARD catalogs and
other roadmap features are not v0.1 release dependencies.

The [WordPress parity audit](wordpress-parity-audit.md) records the 1.7.0 reference
behaviour, all settings and 22 public extension points, historical issue coverage and
remaining work. The [current matrix](wordpress-parity-status.md) records implementation
status; the [drift ledger](wordpress-drift-ledger.md) tracks subsequent upstream changes
and deliberate differences. The audit's A01–A13 requirements supplement this design;
proposed new work still needs implementation and acceptance tests. The audit's
GitHub sync record links the implementation issues and milestones.

## Purpose

A behavioural port of the WordPress plugin
[Markdown for Agents and Statistics](https://github.com/dogwonder/markdown-for-agents-and-statistics)
to Wagtail: convert CMS content to Markdown, write static `.md` files, serve them to AI
agents via HTTP content negotiation, and log agent access statistics. Developed
in collaboration with 350.org.

The 350.org reference notes on issue #65 (page models, the 18 StreamField block
names and their nesting) supply concrete integration examples. Resolve their open
acceptance decisions through #63 before implementation; they do not make that schema
a core dependency.

Ecosystem check (July 2026): no existing Wagtail/PyPI package does this. Wagtail 7.3's
llms.txt work covers only wagtail.org's own documentation sites, not user sites.

## Package identity

- PyPI / repo: `wagtail-markdown-for-agents`; import package `wagtail_markdown_agents`;
  settings key `WAGTAIL_MARKDOWN_AGENTS`.
- Support matrix: Python 3.11–3.13 × Django 4.2 LTS/5.2 LTS/6.0 × Wagtail 6.3 LTS/7.x,
  tested in these CI pairings (`tox.ini`, #71): Python 3.11 + Django 4.2 + Wagtail 6.3;
  Python 3.12 and 3.13 + Django 5.2 + latest Wagtail 7.x; Python 3.13 + Django 5.2 +
  Wagtail 7.0.x, the combination the supplied 350.org reference declares; and Python
  3.13 + Django 6.0 + Wagtail 7.4+. Pairing Django 4.2 only with Wagtail 6.3 is
  this project's CI policy: upstream Wagtail 7.0–7.3 also support Django 4.2;
  Wagtail 7.4 requires Django ≥ 5.2 (see the
  [upstream compatibility table](https://docs.wagtail.org/en/stable/releases/upgrading.html#compatible-django-python-versions)).
  The `wagtail7` tox factor and the package dependency are both bounded below 8, so
  an untested major is never advertised or resolved into CI just because it installs.
- Licence: GPL-3.0-or-later; copyright (c) 2026, 350.org. See the attribution policy in CONTRIBUTING.md.

## Core decisions

### StreamField → Markdown: block-renderer registry

`BlockRendererRegistry` dispatches on **block class (walking the MRO)** with **block
name** as an override key. Registration:

```python
from wagtail_markdown_agents.rendering import register_renderer


@register_renderer(QuoteBlock)  # by class (MRO-aware)
@register_renderer(block_name="pull_quote")  # by name — wins over class
def render_quote(block, value, context) -> str: ...
```

Renderers live in a per-app `markdown_renderers.py`, autodiscovered like
`wagtail_hooks.py`. A `WAGTAIL_MARKDOWN_AGENTS["RENDERERS"]` dotted-path map exists for
settings-only overrides; the decorator is the documented path. A renderer renders
its child blocks with the public `render_block`. The
[custom blocks guide](custom-blocks.md) is the user-facing contract.

Built-ins: `RichTextBlock` (expand `<a linktype="page">`/`<embed>` refs, then
HTML→Markdown), `CharBlock`/`TextBlock`, heading conventions, `ImageBlock` and
`ImageChooserBlock` (`![alt](rendition-url)`), `EmbedBlock`, `TableBlock`/
`TypedTableBlock` (GFM pipe tables), `RawHTMLBlock`, `BlockQuoteBlock` (`> ` prefix),
`ChoiceBlock`/`MultipleChoiceBlock` (display labels, not stored values),
`PageChooserBlock`/`DocumentChooserBlock`/`SnippetChooserBlock` (Markdown links to
page URL / document URL / snippet `str()` + URL where available), and structural
recursion for `StructBlock`/`ListBlock`/`StreamBlock`.

`ImageBlock` (default image block since Wagtail 6.3) subclasses `StructBlock`, so
MRO dispatch alone would route it into structural recursion — it is registered
explicitly ahead of the `StructBlock` renderer (#10). Images render at their original
size with Wagtail's alt-text rule (contextual alt text, else description, else title);
a decorative `ImageBlock` image renders nothing. In converted HTML (rich text and
the template fallback) an `<img alt="">`, WCAG's decorative marker, is omitted the
same way, along with any link left empty; an image with no `alt` attribute is kept. Every image URL in the output —
block images and rich-text images alike — is absolute when `WAGTAILADMIN_BASE_URL`
is set, as `Rendition.full_url` is. `EmbedBlock` renders a link whose text is the
title from Wagtail's embed cache when one exists, else an autolink; generation never
calls a provider's oEmbed API. A block template's `{% embed %}` (or an `EmbedBlock`
rendered inside a template) uses only embeds Wagtail has stored while the fallback
renders, and renders nothing otherwise; Wagtail's own page rendering still fetches. `TableBlock`/`TypedTableBlock` render GFM pipe tables:
the caption precedes the table on its own line (where markdownify puts a
`<caption>`), a table with no header row gets an empty one because GFM requires it,
a first-column header renders as an ordinary cell, pipes are escaped and line breaks
inside a cell become `<br>`. `StaticBlock` has no value; the
fallback must tolerate value-less blocks. Scalar field blocks (`BooleanBlock`,
`IntegerBlock`, `FloatBlock`, `DecimalBlock`, `EmailBlock`, `URLBlock`, `RegexBlock`,
`DateBlock`/`TimeBlock`/`DateTimeBlock`) go through a generic stringify default,
with dates/times emitted as ISO 8601. Full built-in block inventory:
<https://docs.wagtail.org/en/latest/reference/streamfield/blocks.html.md> — one
renderer test per block type.

**Fallback**: render the block's own template to HTML, convert with **markdownify**
(chosen over html2text: cleaner GFM-ish output; its `MarkdownConverter` subclass API is
the seam for converter options). A block reaching the fallback with no value renders
nothing, because Wagtail's basic rendering would otherwise print `None` (#85);
`StaticBlock`s are the exception, since their template is their content. No built-in
block's output may contain `None` or an object repr, alone or as a list item — a guard
test enforces this (ledger #84, the wp-mfa-plugin #21 failure class).

A list whose items each render to one line becomes a `- ` bullet list; if any item
spans several lines (cards, rich text, nested blocks) items are separated by blank
lines.

**Dispatch precedence (D12, agreed 24 September 2026, #1/#2):**

1. a renderer registered for the block's name;
2. the nearest registered class in the block's MRO, other than Wagtail's generic
   containers (`StructBlock`, `StreamBlock`, `ListBlock` and their `Base*` classes);
3. the block's custom template, through the fallback below;
4. the nearest registered generic container: structural recursion;
5. the fallback.

A custom template is whatever `block.get_template(value, context)` returns, so
templates set in `Meta`, passed to the block instance or chosen per value all count,
unless the template resolves to a file shipped inside the `wagtail` package, such as
`ImageBlock`'s default. A project copy of a Wagtail template path is custom. A
template that cannot be found also counts, so the fallback raises `BlockRenderError`
rather than the block's content quietly changing shape. A custom template beats
recursion because a template decides which fields are content: recursion would print
presentation fields such as a background choice. A template-less container recurses,
and its presentation fields render unless the project maps them by name (D5). A
project that registers a renderer for `StructBlock` itself replaces generic recursion;
it still ranks below custom templates. Template rendering converts the resulting HTML
once: children reached through `include_block` render with Wagtail, never back through
the registry.

Page body fields: `WAGTAIL_MARKDOWN_AGENTS["PAGE_FIELDS"]` map
(`{"app.Model": ["body"]}`), defaulting to auto-detection of all
StreamField/RichTextField fields in definition order. Non-StreamField pages: v0.2.
The v0.2 extraction work also covers ordered/labelled custom body fields on pages
that have StreamFields, separate frontmatter mappings, nested/repeated values and
explicit featured-image/alt mappings. There is no universal featured-image field in
Wagtail. v0.1 projects can supply these through registered renderers and frontmatter
hooks; arbitrary model fields are never exported automatically.

Page assembly is implemented in #78: `rendering.render_page(page, site=None,
navigation="")` reloads the current live revision, selects ordered fields, runs
page hooks, appends supplied navigation, and serialises frontmatter plus body.
The return value is a Markdown string, not a stored export. The caller must apply
`ExportPolicy` and perform publication after commit, rechecking state when writing.
A live page with no revision (created in code) renders from its current row, which
is the content Wagtail serves. Publication timestamps come from the current page record.

`PAGE_FIELDS` is validated as a mapping of Page model labels to lists/tuples of
StreamField/RichTextField names. Unknown models/fields, other field types and
duplicate entries are configuration errors. Unconfigured types auto-detect fields
in definition order; `[]` intentionally selects none. v0.1 requires a StreamField
on the model; forms using Wagtail's `FormMixin` are unsupported even with renderable
fields. `PageRenderError.reason` is `unpublished_page`, `unsupported_page` or
`empty_body`; #24 must report these without recording a successful export. An empty
body plus empty navigation is an error: the title alone does not establish support.

The `markdown_post_render(markdown, page, context)` hook receives the assembled
field body without a generated title or navigation. It returns replacement Markdown,
or `None` to leave it unchanged, chaining in hook order. Hooks share the published
page/site/locale context with field conversion and frontmatter. `context["heading"]`
starts as the published title; a hook may replace it with a hero headline or set it
to `None`/empty when supplying an authored H1. The generated heading is escaped as
plain text. Authored headings are preserved; the package does not guess which to
deduplicate. Frontmatter title remains governed by the separate frontmatter builder.

Project code uses that hook for public hero fields; block renderers alone do not
extract page-level scalar fields. See [the page rendering guide](page-rendering.md)
and the synthetic project-owned hero mapping. The exact 350.org presentation remains
proposed under #63/#65. General declarative extraction and non-StreamField support
remain #39 in v0.2. Navigation generation (#20) appends its already-rendered output
once after the hook, with one listing source chosen by the project through the navigation hook.
Final link rewriting (#14) runs on the complete body before YAML is attached.
Current owned targets use absolute public export URLs; unavailable targets retain
their HTML links. See the [link contract](internal-links.md) for syntax preservation,
reference links, conservative query handling, redirects and generation order.

All HTML conversion paths remove script/style/template nodes and their contents
before conversion. Other hidden markup (`hidden`, `aria-hidden`, `<dialog>`,
`<noscript>`) is kept: the HTML alone can't tell a collapsed accordion panel or a
`<noscript>` signup link from a success message, so a block renderer decides. Output fixtures cover code whitespace/language, table captions and empty
cells, escaped pipes, entities, Unicode and image/text spacing as well as block types.
Expose pre-conversion, converter-options and page post-render hooks with documented
ordering; see the audit's [extension inventory](wordpress-parity-audit.md#public-extension-surface).

**Conversion hooks (implemented in #12).** Every HTML → Markdown conversion — rich
text, plain text and the template fallback — runs these Wagtail hooks by `order`, then
registration order:

- `markdown_pre_convert(html, block, context)` returns the HTML to convert, or `None`
  to leave it unchanged; hooks chain, each receiving the previous result.
- `construct_markdown_converter_options(options, block, context)` mutates the
  markdownify options dict in place; its return value is ignored.

Exceptions raised by a hook propagate. A block template that fails to render raises
`BlockRenderError` naming the block class, with the original exception chained, so
generation reports lost content instead of exporting a page with the block missing.
`rendering.context.render_context(page, site=None)` supplies the offline template
context: `page`, `site` (the page's own unless given), `locale`, and `settings` bound to
that site when `wagtail.contrib.settings` is installed. There is no `request`. The page
post-render hook is implemented in #78 as described above.

A block whose class, or a base class other than a generic container, has a
registered renderer uses that renderer even when it declares its own template — a
`CharBlock` subclass with a template still renders as plain text. See the D12
precedence above.

### Frontmatter

Implemented in #13 (`rendering/frontmatter.py`: `build(page, context)` and
`serialise(mapping)`). Fields, in order: `title`, `date`/`modified` (ISO 8601 in UTC
with `Z`, from `first_published_at`/`last_published_at`), `permalink` (`page.full_url`),
`type` (`app_label.ModelName`), `status` (`published` — only published content is
exported), `excerpt` (`search_description`), native `id` (pk), optional
`parent`/`ancestors`/`children` (each `{title, permalink}`, limited to pages the
`ExportPolicy` finds eligible — the site root is the first ancestor), optional `owner`
(the owner's full name; a username or email is never written, so an owner without a
full name is omitted), flat deduped `tags` from every tag field on the page, and
`timestamp` (generation time, UTC). Built-in fields with no value are omitted, never
`null` or `""`. Root index carries `okf_version: "0.1"` — centralised as a constant.

Sources and precedence, lowest first: built-ins; `PageAgentSettings.extra_frontmatter`,
whose keys override built-ins except the identity keys `id`, `type`, `permalink`,
`status` and `timestamp` (kept, and the clash logged with the page id); the
`construct_markdown_frontmatter(frontmatter, page, context)` hook, which mutates the
dict in place and runs last, so code overrides anything. `construct_markdown_tags(tags,
page, context)` mutates the tag list before it enters the frontmatter. No key is ever
derived by discarding part of a name (wp-mfa-plugin #20). Editor JSON object keys
are sorted recursively before merging so SQLite and PostgreSQL produce the same
output; list order is preserved. Built-in and hook field order remains explicit.

One normaliser handles every value, scalar or inside a list or mapping, identically:
`None`, bool, int, float, str and lazy strings, `Decimal` (as a string, keeping its
precision), date/time/datetime, `UUID`, tags (name), `Page` (`{title, permalink}`),
`Site` (root URL), `Locale` (language code), string-keyed mappings, lists, tuples,
sorted sets and querysets. Anything else raises `FrontmatterValueError` naming the key
path (`links[1]`, `meta.inner`), so a model instance can never reach the YAML as a repr
(wp-mfa-plugin #21). Serialisation is PyYAML's safe dumper with key order kept, Unicode
unescaped, multi-line strings as literal blocks, and strings that look like booleans,
numbers, dates or nulls quoted so they read back as strings; round-trip tests pin this.

### Exclusion / per-page settings: side-model

`PageAgentSettings` — OneToOne to `wagtailcore.Page` (`excluded` bool,
`extra_frontmatter` JSON). Absent row = included (opt-out, matching WP). Rationale: a
required mixin would force host projects to touch every page model before the package
does anything, and would rule out evaluating against stock bakerydemo. Editing surfaces:
a page action-menu item opening a small admin view, plus an **optional**
`AgentMarkdownPanelMixin` for an in-editor checkbox. `ExportPolicy` reads only the
side-model, so both converge.

The #17 action is **Markdown settings** in a saved page's edit action menu.
It requires Wagtail admin access, that page's `can_edit()` permission and no lock
preventing that user from editing. The direct GET/POST view repeats these checks.
Creation and revision-revert screens do not show it. The CSRF-protected form edits
only `excluded`, preserving `extra_frontmatter`; GET and unchanged saves make no
writes. Save/cancel return to that page's editor. Saving takes effect immediately
through the existing side-model signals, independently of page revisions. Clearing
exclusion remains subject to eligibility and `AUTO_GENERATE`.

The optional #18 `AgentMarkdownPanelMixin` and `AgentMarkdownPageForm` add a
non-model checkbox to the editor's Settings tab. The form stages changes; the mixin
persists them in the successful revision's transaction after checking permissions
and locks against the saved page. Publication follows this step, so generation
honours the new exclusion. Preview and invalid form submissions do not write it.
The side-model remains independent of page revisions, and custom edit handlers
omitting the panel leave exclusion unchanged. See the
[editor integration guide](editor-exclusion-panel.md) for custom forms and panels.

The remaining WordPress editor controls are v0.2 work: export state/time, no-write
preview of the saved published version, and single-page regeneration, all with page
permissions and CSRF protection. Public page requests never generate or preview.

### ExportPolicy + path scheme

`ExportPolicy` is the single source of truth (implemented in #16): `is_eligible(page)`
= live and below the tree root + in an exported site (`SITES`: `default`, `all` or a
hostname list) + type enabled (`PAGE_TYPES`, `app_label.Model`, case-insensitive) + no
view restrictions (password, login or groups, own or inherited) + not excluded via
`PageAgentSettings` + not vetoed by the `markdown_export_eligible(page, site)` hook,
which can only veto (return `False`), never grant. It also owns `relative_path(page)`,
computed for ineligible pages too so a withdrawn file can be found and deleted.
Export eligibility hooks are deterministic for a page/site; any request-specific
serving veto runs separately and must never be cached as export eligibility.

**Paths mirror the URL tree, prefixed per site hostname**:

```
{hostname}/index.md               # site root page
{hostname}/about/team.md          # leaf page
{hostname}/blog/index.md          # page with live children
{hostname}/blog/my-post.md
{hostname}/llms.txt
{hostname}/manifest.json
```

Rationale: Wagtail slugs are only unique per sibling, so `{type}/{slug}.md` collides;
`url_path` is unique per site and matches what an agent hitting the HTML URL expects.
The hostname prefix makes multi-site a config unlock (v0.2), not a layout migration.
The prefix is `Site.hostname` only — never the port — so `localhost:8000` exports under
`localhost/`; port-differentiated sites are unsupported for export.
Type-grouped indexes return in v1.0. Taxonomy/snippet term export is a **nice-to-have**
(no milestone): Wagtail has no native taxonomy system — only taggit and per-site snippet
conventions — so it stays out of the parity scope unless a concrete need (e.g. from
350.org's models) pulls it in. The `markdown_export_path(path, page, site)` hook
relocates a page within its site: it receives the site-relative default
(`blog/my-post.md`) and returns a replacement or `None`; results must be relative, free
of `..` and end in `.md`, and are always prefixed with the hostname, so a hook cannot
move a page outside its site's tree (`ExportPathError` otherwise).

Parent pages stored as `index.md` retain their own body/frontmatter alongside their
child listing; index rebuilds must not overwrite page content. `index` and `log` are
reserved at every level: a page with that slug is written as `index_`/`log_`, and when
a real sibling already owns that slug the page id is appended (`index_42`), so two pages
never share a path and the layout is deterministic. If a real sibling also owns
that identity suffix, append underscores until distinct. Record the actual owned paths,
including old hook paths, for later cleanup (#19).

**Implemented in #20:** root/directory navigation uses current readable page-owned
exports and their actual public URLs, with published titles/descriptions and entry
counts. Page-owned indexes retain their rendered body/frontmatter. Standalone indexes
use generic metadata; the root carries `OKF_VERSION`, even for an empty corpus.
`markdown_index_content` customises or suppresses navigation with path/site/page and
entry context. Explicit `IndexBatch` finalisation coalesces dirty sites, repairs
leaf/index transitions, and uses publication guards against concurrent revocation.
The [index guide](indexes.md) defines directory promotion, complete title-ordered
listings independent of HTML pagination, and the lifecycle integration boundary.

**Implemented in #21:** `llms.txt` contains a site-name heading (hostname fallback),
an optional plain-text `LLMS_TXT_DESCRIPTION` blockquote, and an Explore section.
It links the readable root index and the root directory's current page exports,
using the index generator's title ordering and subtree promotion rules. All entries
use published metadata and actual checked public URLs. `IndexBatch` publishes it
after indexes; direct generation is also available. Site-name/introduction changes
invalidate site-dependent documents even for empty corpora, while introduction-only
changes preserve ordinary leaf exports. See the [discovery guide](llms-txt.md).

### Storage & middleware

Everything through the Django storages API: `WAGTAIL_MARKDOWN_AGENTS["STORAGE"]` names
an alias in `STORAGES`, defaulting to `FileSystemStorage` rooted at
`BASE_DIR / "markdown_export"` — deliberately outside `MEDIA_ROOT` and staticfiles.
`BASE_DIR` is a `startproject` convention, not a Django setting: when it is absent and no
`STORAGE` alias is set, a system check fails with a clear message rather than guessing.
The writer uses `save/open/delete/exists` through a backend publication contract.
These methods alone do not guarantee stable-name overwrite or atomic replacement:
`save()` may choose a different name. Record returned storage keys, preserve stable
logical export URLs and serialise concurrent updates to shared manifests/indexes.
Local atomic rename is a backend capability, not a portable storage assumption.

Publication guards must also reject obsolete work: a render started before a newer
publish, path change or eligibility revocation cannot later republish stale page or
aggregate content. #19 covers an overlapping build/revocation test. Synchronous
execution still permits concurrent web workers and management commands; this safety
contract does not depend on the v0.2 job framework.

**Implemented in #19:** the tree above is a logical namespace backed by
`ExportArtifact` records, not a set of stable physical filenames. `ExportFile`
records track immutable uploads under `{hostname}/.objects/<id>/content`, including
backend-renamed keys and prior hook paths. A per-site `ExportScope` database lock
serialises pointer publication. Aggregate updates read and upload outside the mutex,
then retry competing aggregate publications up to three times; page publication or
revocation aborts retries. A separate content generation distinguishes these cases.
The writer verifies saved bytes and rechecks revision/path/eligibility and
generation before publication;
managed reads recheck the pointer and state after opening storage without the site
mutex. Site-state checks use fresh batched policy inputs; their built-in query count
stays bounded as pages are added. Retired objects remain in the cleanup inventory
until deletion succeeds. Hook paths now reject noncanonical/traversal segments
rather than normalising them. The default writer requires CMS/export records on
the default primary database; routed/replica deployments are rejected. Retired-object
cleanup acquires no site mutex for backend IO, though a caller's outer revocation
transaction retains its lock until commit. Post-commit notification failures are
logged without changing the reported publication result or skipping cleanup.

Page-owned indexes/hierarchy and explicit site-dependent page builds capture a
site-state guard; revocation withdraws them alongside standalone aggregates.
Publication is after commit; immediate revocation supports an enclosing transaction
and rollback can leave a safe missing file. Lifecycle receivers remain #23/#69/#70.
Backend assumptions, crash windows, signals and the API are documented in the
[storage writer guide](storage-writer.md). The BASE_DIR/STORAGE system check portion
of #29 ships with this writer; the middleware-order, settings-shape and route checks
are **implemented in #29** and listed in the [checks guide](system-checks.md).

Storage placement does not provide public URLs. Ship an explicitly included Django
URLconf with named routes for managed page/directory exports and site `llms.txt` and
`manifest.json`, adding delta/bundle endpoints when those features ship. Resolve
artefacts through the site's export records, validate containment and recheck current
eligibility for page files. Never serve an arbitrary storage key supplied by a client.
Hosts include these routes deliberately, preserving their existing URL configuration.

**Direct retrieval implemented in #72/#68:** include `wagtail_markdown_agents.urls`
before Wagtail's catch-all, at a chosen prefix (the sandbox uses `/markdown/`) or
the site root. The namespaced routes claim `.md` paths, `llms.txt` and `manifest.json`.
`export_url(record)` derives absolute URLs from the owning site's configured origin
and the included route, including hook relocations. `alternate_url(record)` implements
the query-enabled/explicit-route choice described below; negotiation is implemented (#25/#26).
Request hosts must pass ALLOWED_HOSTS and match the selected site's hostname; a
cross-host default-site fallback is rejected. `serve_export` binds each read to the
checked site's exact immutable file generation and supplies the shared response
function for #26, returning no response on a miss so middleware can fall through.
Direct routes map that miss to 404. GET/HEAD, header customisation, per-request vetoes
and the `markdown_served` statistics integration signal are documented in the
[public route guide](public-export-routes.md). The
[statistics receiver](agent-access-stats.md) implements persistent counting (#32/#33).

Web-served Markdown uses **absolute public export URLs** for internal links. A file
stored at `blog/post.md` can also be served at `/blog/post/`, so file-relative links
would have the wrong base on negotiated requests. The offline bundle converts those
export URLs to paths relative to each bundled file; canonical HTML `permalink`
metadata stays absolute. This supersedes the earlier relative-from-generation choice.
Image/document URLs stay absolute unless a project renderer explicitly overrides them.
The resolver preserves fragments, handles same-site relative URLs and unambiguous
redirects, honours `export_path`, and leaves meaningful query-dependent routes,
external/media links and code examples intact (audit A01/A02).

`AgentMarkdownMiddleware` — after `SecurityMiddleware`, before `CommonMiddleware`
(enforced by a system check):

- **Request phase**: detection precedence `?output_format=md|markdown` >
  `Accept: text/markdown` > reviewed automatic-serving UA identity (if enabled). The Accept rule requires
  `text/markdown` as an explicit media range (`text/*` and `*/*` never match, `q=0`
  excludes), so curl and browsers are never served Markdown by accident. Only public
  page GET/HEAD requests are candidates; skip admin, APIs, previews and submissions.
  On a hit, resolve site and routed page, recheck policy, and resolve its recorded
  export path; if the file exists, return a streaming `FileResponse` with
  `Content-Type: text/markdown; charset=utf-8`, `Cache-Control: private, no-store, max-age=0`,
  `Vary: Accept, User-Agent`, `X-Markdown-Source`, configurable `Content-Signal`
  (default `ai-input=yes, search=yes` for WP parity — an opt-in policy statement made on
  the operator's behalf, and silent on `ai-train`; document this prominently, `""`
  suppresses the header), plus a cache-headers hook. **Missing file → fall through to HTML, never 404.**
  **Implemented in #25/#26/#30:** detection lives in `negotiation.py` with parsed
  Accept media ranges, case-insensitive query values and first-match dataset-order
  agent labelling that ignores the UA serving toggle. The middleware intercepts only
  GET/HEAD requests resolving to `wagtail_serve` at the page's canonical URL, looks
  up the page's recorded export by site and page ID (so relocated and index paths need
  no URL-derived guess) and serves it through `serve_export`. Every miss, including
  withdrawal races, returns the ordinary HTML response; `before_serve_page` hooks
  govern only that fallback. See the [negotiation guide](negotiation.md).
- **Response phase**: on HTML 200s whose page has an eligible export, append
  `Link: <…>; rel="alternate"; type="text/markdown"` and merge `Vary: Accept` (only
  `Accept` here — `Vary: User-Agent` on HTML would be cache-hostile). On a cache miss,
  resolve the request's site and page, check `ExportPolicy.is_eligible(page)`, then
  use `ExportPolicy.relative_path(page)` (including the `export_path` hook) to find
  the published export record and check its actual storage key with `exists()`.
  The request path alone cannot distinguish `blog.md` from
  `blog/index.md` or locate a hook-relocated export. Cache the resolved export path
  and existence result, including misses, for 60 s by default, keyed by site, request
  path, and storage identity. Invalidate affected entries when exports are generated,
  deleted, or relocated, including parent paths whose leaf/index status changes.
  This cache is only for discovery headers; it must not authorize Markdown serving.
  Caching avoids repeated routing and S3-style HEAD requests per page view. The phase
  is toggleable via `LINK_HEADER` for hosts that cannot afford it. A
  `{% agent_markdown_link %}` template tag emits the `<link rel="alternate">` head tag.
  Both use the canonical page URL with `output_format=md` when query negotiation is
  enabled, otherwise the explicit Markdown route. A discovery-header hook permits
  individual overrides/omissions and preserves existing `Link`/`Vary` values.
  **Implemented in #27/#28:** `discovery.py` resolves the routed page through
  `ExportPolicy`, the published record at the policy's current path and that
  record's actual storage key, and caches the result (misses too) for
  `DISCOVERY_CACHE_TIMEOUT` seconds under a key that includes the site's export
  publication version, so writer-driven generation, deletion and relocation
  invalidate entries at once in every process. The `construct_markdown_html_headers`
  hook adjusts or omits headers; `{% agent_markdown_link %}` shares the same
  resolution. Serving never consults the cache. See the
  [discovery guide](discovery-headers.md).

HEAD has GET's headers and no body. Explicit page-export GETs share the policy and
logging path, with access method `export-url`; discovery/index-only, manifest and
bundle downloads do not count as page reads. Test both HTML→agent and agent→HTML
requests through the deployment's shared cache. HTML `Vary: Accept` alone cannot
guarantee UA negotiation when cached HTML bypasses Django; document UA bypass/variant
configuration for those hosts. Host-specific cache headers remain configurable.
**Documented in #61:** the [CDN and cache guide](cdn-caching.md) covers both request
orderings per trigger on `Vary`-honouring and `Vary`-blind caches, bypass-not-key
rules, per-layer configuration (Cloudflare, Varnish/Fastly, nginx, LiteSpeed, Django's
cache middleware, WhiteNoise), per-method header relaxation and the statistics gaps.

### Settings split

- `WAGTAIL_MARKDOWN_AGENTS` Django dict (deploy-shaped, code-level): enabled page types,
  storage alias, page-field map, renderer overrides, negotiation toggles, Content-Signal
  string, frontmatter toggles, `AUTO_GENERATE` (default true), discovery toggle and
  stats retention (default 90 days). Unlike WP's default-off auto-generation, Wagtail
  opts into publish-time generation; document this alongside the broad page-type default.
- `wagtail.contrib.settings` generic setting (v0.2, runtime-editable): UA detection
  toggle, agent-list deltas (the shipped list stays versioned in `data/agents.py`; the
  setting stores additions/removals), stats retention. Rationale: the agent list churns
  on editorial timescales; content teams shouldn't need a deploy to add a crawler.

Track a generation configuration fingerprint. Changes to extraction, renderer,
frontmatter or public link settings mark affected exports stale, exposed by status
and admin notices; successful rebuilds clear that state. This general staleness
workflow is v0.2 roadmap work (#75), outside v0.1. v0.1 still provides
content-hash manifests, basic export status and immediate eligibility revocation. Turning
off routine generation never turns off eligibility revocation. Settings newly named
here are requirements for implementation, not claims about the current defaults stub.

### Signals & tasks

**Implemented in #23:** the core receivers and shared ID-based refresh/revocation
helpers are described in the [publish lifecycle guide](publish-lifecycle.md).
`AUTO_GENERATE` defaults to True and controls routine regeneration only; immediate
unpublish/delete/restriction/exclusion revocation remains active when disabled. The
setting is excluded from content fingerprints. Explicit multi-page refreshes coalesce
dependent artefacts through `IndexBatch`; signals do not introduce transaction-wide debounce. Post-commit
export failures are logged, while direct refresh calls raise for operator retry.
Restriction/exclusion receivers are implemented in #70, with inline after-commit
restoration that bypasses the task queue and still honours AUTO_GENERATE. Public
`none` restrictions do not block exports. Persisted before/after eligibility values
also handle settings-row removal and reassignment. Deployments disabling PAGE_TYPES
run `agentmd_revoke_ineligible` under the new configuration before resuming traffic;
the same helper supports explicit bulk-update reconciliation, without startup DB
work or #75. The [lifecycle guide](publish-lifecycle.md) defines this trigger for
#16/#24/#29 and the boundary with future negotiation/discovery middleware.
Move/slug receivers are implemented in #69. They capture the old subtree/site
identities before a move, retire owned paths inline after commit (even with automatic
generation disabled), then queue the current published subtree and affected parents
through the same refresh helper. Rollback discards this cleanup as well as generation.
Reorders with unchanged URL paths do no export work. The lifecycle guide documents
the signal snapshot and the boundary with future negotiation middleware.

Receivers wired in `AppConfig.ready()`: `page_published`, `page_unpublished`, and
`pre_delete` on Page (pre-, so `url_path` is still available). On publish: regenerate
the page file, parent `index.md`, root `index.md`, `llms.txt`, upsert `manifest.json` —
synchronously in v0.1, all funnelled through `tasks.enqueue(fn, *args)` whose default
backend calls inline. Schedule regeneration with `transaction.on_commit()` on the
write database alias (`using` where supplied, otherwise the instance's database),
passing identifiers and re-fetching pages to check existence and eligibility when
the callback runs. Outside a transaction this runs immediately;
inside one it runs only after a successful commit. A rollback discards the callback.

Because paths mirror the URL tree, anything that changes a `url_path` or eligibility
without a publish must also be handled, or stale files keep being served:

- `page_slug_changed` supplies the old page as `instance_before`; moves use
  `pre_page_move`/`post_page_move` and their before/after paths. Capture old export
  identities, delete the old subtree files, then regenerate the page and every live
  descendant, plus affected indexes, after commit.
- `post_save`/`post_delete` on `PageViewRestriction`: a restriction added to a live page
  deletes its export and its descendants' exports immediately and invalidates discovery
  cache entries. Removal or relaxation schedules regeneration after commit, with the
  page and each descendant re-fetched and checked against the full export policy,
  including inherited restrictions. Skip pages that no longer exist: `post_delete`
  also fires when a restriction is cascade-deleted with its page, and must not recreate
  exports removed by the page's `pre_delete` handler. Restriction changes use synchronous
  deletion and synchronous after-commit regeneration even when a task backend is
  configured; they never wait for the background queue or debounce. If a transaction
  adding a restriction rolls back, a missing export safely falls through to HTML until
  a subsequent rebuild restores it. See
  [Django's after-commit guidance](https://docs.djangoproject.com/en/5.2/topics/db/transactions/#performing-actions-after-commit).
- `post_save`/`post_delete` on `PageAgentSettings`: toggling `excluded` or removing
  an excluded row deletes or regenerates. Exclusion applies to that page only.
- Old `.md` paths are not redirected: the file is simply gone and the middleware falls
  through to HTML on negotiated page requests, where `wagtail.contrib.redirects`
  applies as normal. Missing explicit export artefacts return 404.

All export work uses published content, including when an existing live page has a
newer draft revision. Revocation also removes private metadata from listings/manifests
and withdraws any bundle containing the revoked content until safely rebuilt; normal
bundle debounce must never keep such an archive publicly available.

For the representative site, agree a bounded related-content refresh policy in
#23/#63. Donation settings, media changes and referenced page titles/URLs can affect
exports without a publish of the containing page; HTML cache purges do not rebuild
Markdown. Ordinary changes may use project-owned refresh hooks or a documented
explicit rebuild procedure in v0.1. Incoming export links after target moves also
need a stated refresh scope. Eligibility revocation remains mandatory and separate
from ordinary freshness or the v0.2 configuration-staleness feature.

v0.2 adds a django-tasks/Celery backend with coalescing keys
(replacing WP's 5-minute bundle debounce). Custom signals: `markdown_generated`,
`markdown_deleted`, `link_unresolved`.

The backend seam alone is not bulk-generation parity. v0.2 also needs durable scoped
jobs with cursor batches, progress/counters, bounded error history, exclusive write
ownership, heartbeat/retry/recovery, and an admin start/status workflow that survives
tab closure. Finalise dependent artefacts once per scope; preserve staleness if edits
arrive during finalisation. Audit A05/A13 defines operational acceptance and explicit
stop/removal procedures; importing or uninstalling the package never deletes user data.

### Manifests and commands

v0.1 manifests describe successfully published files with stable page IDs, actual
paths, rendered-body/metadata/full hashes, word counts, schema version
and change summaries. Hash the output, including configured fields/tags/image/link
changes; raw CMS body/title/timestamp hashes are insufficient. Scoped runs preserve
other scopes, and write failures must not masquerade as success or deletion.
The general configuration-fingerprint/stale-scope workflow belongs to v0.2 (#75).

**Implemented in #22:** `ManifestGenerator` reads checked page-owned export bytes,
records actual storage identities and public URLs, and compares stable page IDs
against private hashes in `ExportScope.manifest_state`. `IndexBatch` finalises the
manifest after indexes and llms.txt. The private comparison state commits atomically
with the public pointer and survives aggregate withdrawal. Missing/stale eligible
exports are errors, not deletions; revoked metadata is omitted. Exact-file SHA-256
includes the generation timestamp, while semantic metadata/change detection omits
that timestamp so identical rebuilds remain unchanged. Schema/hash versioning,
canonicalisation and failure semantics are defined in the [manifest guide](manifest.md).

**Implemented in #24:** the [management commands](management-commands.md) use the
managed writer and `IndexBatch`. Generation skips readable exports with current
publication state unless forced, and finalises each affected site once. Status and
dry runs inspect without rendering or publication. Page/type deletion withdraws owned
files and refreshes surviving discovery, excluding selected page IDs from regeneration
in that batch. Site/all deletion leaves the selected export trees empty. Deletion
does not change CMS eligibility; later generation may restore eligible pages.

`agentmd_generate` and `agentmd_delete` support page/type/site scopes; broad deletion
requires explicit selection and confirmation. Dry runs do not persist any artefacts
or jobs. Status reports basic counts/missing/error state. Selected missing files are
repaired by v0.1 generation. v1.0 adds hash-based incremental generation and
`changes.json` with initial/full and subsequent
new/modified/deleted records, including old paths after moves. `--force` overrides
unchanged skipping; manifests are core so no separate `--with-manifest` flag is needed.
See the audit's [command matrix](wordpress-parity-audit.md#command-parity).

### Stats (v0.1, pulled forward)

Originally v0.2; pulled into v0.1 because the live deployment soak (#64) reconciles
`AgentAccess` rows against the traffic simulator's ground truth. The admin reporting
view and prune command ship with it.

`AgentAccess` model: (page_id, agent ≤100 chars, access_method ≤20, access_date), unique
together, daily upsert (`count = count + 1`). Intent categories (on-demand / search /
training / mixed / unknown) derived **at read time** from the registry and historical category map. Review classification changes
explicitly because they can relabel historical reports. Wagtail admin
reporting view: date presets, filters, chart by intent, stat tiles with trends. Prune
command + retention setting.
The report includes an intent-category filter as well as agent, method and date
filters. Statistics store no IP addresses or personal data.
Daily buckets are UTC. Count successful page Markdown GET response selection, not
HTML/fallback/error/HEAD/preview/aggregate requests or proof of full client receipt.
UA labelling still matches known agents with UA serving disabled; all other clients
share the empty unknown label. Do not persist arbitrary header fragments or allow
request-controlled labels to create unbounded daily rows.
Retain stable page identifiers for historical counts after deletion. Concurrent hits
must increment the existing count atomically; conflict-update assignment of `1` is
not sufficient. Audit A09 specifies reporting grain, trends, retention and cache
measurement limits.

**Implemented in #32/#33:** `AgentAccess` stores the daily key with a date index
and a numeric page ID that survives deletion. The `markdown_served` receiver uses
a single parameterised upsert to increment counts, with canonical known-agent
labels and one empty unknown bucket for other clients. Migration `0006` merges
legacy arbitrary labels without losing daily totals. The
[statistics guide](agent-access-stats.md) describes counting boundaries, UTC dates,
failure handling and CDN limits. **Implemented in #34:** `stats.categorise_agent`
derives intent at read time with ordered, case-insensitive first-match lookup.
`construct_markdown_agent_categories` mutates a fresh category map in hook order;
unexpected category keys classify as unknown. The statistics guide documents
historical reclassification and dataset verification. **Revised 22 September 2026:** the independent, versioned
[agent registry](agent-registry.md) supersedes the WordPress parity constraint.
Active records carry sources, review dates, HTTP tokens, purposes and a separate
`auto_markdown` flag. Recognition uses product-token boundaries; stats prefer exact
canonical labels before compatibility substring hooks. Frozen WordPress categories
remain for retired labels. Purpose corrections are explicit read-time changes,
not rewrites of stored counters. Robots.txt-only controls are not HTTP identities.
Generate CDN bypass rules from the serving subset. **Implemented in #35:**
the native Wagtail report combines page/agent/method/intent/date filters, 50-row
pagination, headline leaders, operator cards, six tiles and accessible intent charts.
It defaults to 7 inclusive UTC dates; grain is daily through 92 dates, monthly
through 1,827, yearly thereafter.
One hook snapshot supplies all classification within a request. Trends are Pearson
correlation with neutral flat/insufficient series; on-demand is labelled an estimate.
The existing `view_agentaccess` permission plus Wagtail admin access grants site-wide
reporting, independently of page-edit permissions. Deleted IDs and counting limits
are visible. The [report guide](agent-access-stats.md#admin-report-35) defines the
filter and aggregation contract. **Implemented in #36:** `agentmd_prune_stats`
deletes counters dated strictly before today's UTC date minus `--days` (default
`STATS_RETENTION_DAYS`, 90) with positive-days validation of either source, a typed
confirmation unless `--yes`, `--dry-run` and deleted/retained counts, in one indexed
`DELETE`. Nothing schedules it; runtime editing of the period stays #38.

### Deployment verification

**Implemented in #59:** the repository [agent traffic simulator](agent-simulator.md)
discovers manifest identities and exported canonical URLs, plans seeded bounded
traffic, records append-only client evidence and reconciles verified origin logs
with UTC counter snapshots. Cache limitations, uncertain selections and synthetic
UA coverage are explicit; genuine vendor verification has a separate procedure.
It adds no production middleware, rendering policy or statistics fields.

### Bundle / ARD / OKF (v1.0)

Opt-in OKF zip bundle (`application/okf-bundle+zip`, body links rewritten to relative
paths, complete publication via the storage backend), `changes.json` deltas from
manifest history, ARD `ai-catalog.json`
(`specVersion: "1.0"`, `urn:air:{host}:knowledge:markdown-bundle`) with a `.well-known`
serving route (the WP version deliberately leaves deployment to the operator;
Wagtail provides routes explicitly included by the host). The `okf_version: "0.1"`
pin is reviewed against the OKF spec each major release. Taxonomy export is explicitly
out of v1.0 scope (nice-to-have, above).
Enumerate owned artefacts from export records so remote storage requires neither
filesystem traversal nor mtime APIs. Exclude deltas/catalogs/temporary/unrelated files
at every depth. Preserve the previous complete bundle on ordinary build failure, but
withdraw it immediately for eligibility revocations. The catalog includes host and
entry metadata, `type` and `mediaType`, and the stable URL of an available bundle;
expose a catalog hook and avoid collisions with existing `.well-known` routes.

## WP → Wagtail concept map

| WordPress plugin | This package |
| --- | --- |
| `template_redirect` priority 1 | `AgentMarkdownMiddleware` request phase |
| `AgentDetector` | `negotiation.py` + `data/agents.py` |
| `ExportPolicy` | `export/policy.py` |
| `Generator`/`FrontmatterBuilder`/`Converter` | `rendering/` (registry, frontmatter, markdownify) |
| `FieldResolver` (ACF dot-notation) | typed model fields + `PAGE_FIELDS` setting |
| `LinkRewriter`/`InternalUrlResolver` | `rendering/links.py` via page routing |
| `FileWriter` (uploads dir) | `export/writer.py` over Django storages |
| `IndexGenerator`/`ManifestGenerator` | `export/` (`llms_txt.py`, `manifest.py`) |
| `_markdown_for_agents_excluded` meta | `PageAgentSettings` side-model |
| `save_post` / WP-Cron debounce | Wagtail signals + `tasks.enqueue` seam |
| WP-CLI `wp markdown-agents *` | `manage.py agentmd_*` commands |
| 17 filters + 5 public actions | [22-row hook/signal inventory](wordpress-parity-audit.md#public-extension-surface); implement core hooks with their features, final audit in v1.0 |
| Stats table + `Migrator` | `AgentAccess` model + Django migrations |
| Strauss vendor prefixing | not needed |

## Known WP limitations to fix (not inherit)

- Links inside fenced code blocks were rewritten — don't.
- Posts relocated via the export-path filter were invisible to the link resolver.
- Pages slugged `index`/`log` can shadow reserved names — allocate deterministic,
  collision-safe paths instead, including conflicts with escaped names.
- Export-relative links are unsafe when a file is served at a canonical page URL.
  Use absolute public export URLs for web delivery and file-relative links in bundles.
- Raw-body hashes miss custom extraction changes; hash rendered output and metadata.
- A normal rebuild failure may retain an old bundle, but a privacy revocation must
  withdraw it. The same distinction applies to dependent listings and manifests.
