# Root and directory indexes

`IndexGenerator` (#20) builds managed root and directory `index.md` documents after
leaf pages have been exported. It uses the same writer, policy and public routes as
page exports; it neither lists storage directories nor generates files on requests.

```python
from wagtail_markdown_agents.export.indexes import IndexBatch, IndexGenerator

# After the CMS transaction commits:
with IndexBatch() as batch:
    for page in published_pages:
        batch.generate(page)
# Each dirty site's indexes, llms.txt and manifest.json are finalised once on successful exit.

# Rebuild indexes around an existing export corpus:
records = IndexGenerator().generate(site.pk)
```

An `IndexBatch` is an explicit Python integration API, also used by the
[publish lifecycle](publish-lifecycle.md) and [management commands](management-commands.md).
[`llms.txt` discovery](llms-txt.md) runs after indexes, followed
by the [manifest](manifest.md). Standalone `IndexGenerator.generate` returns only
index records. The batch does not implement the bulk link-rewriting second pass
described in [internal links](internal-links.md).

## Listing policy

Entries come only from current, readable **page-owned** exports in the owning site.
Every candidate passes the writer's fresh ExportPolicy/state checks and a storage
open bound to its exact file. Titles and search descriptions come from the live
revision, never a newer draft or the caller's instance. An entry uses `export_url`,
including any relocated path. `IndexGenerator(urlconf=...)` and
`IndexBatch(urlconf=...)` support offline generation with an explicit URLconf.

A directory lists its available page exports in case-insensitive title order, with
logical path and page ID as stable tie-breakers. A readable child page-owned index
represents its subtree. If that intermediate index is unavailable, descendants are
listed directly rather than hidden behind an invented link. Counts describe the
entries in that list, not all descendants recursively. Empty lists say
“No exported pages are available.” Titles and descriptions are escaped plain text.

Standalone indexes cover every directory needed by a readable page export, including
intermediate directories introduced by a path hook. Parent listings link directly
to page exports; standalone indexes are additional directory entry points and do not
introduce duplicate links to the same page. A standalone index uses the generic title
“Markdown exports”, a `count` and, at the physical root, `okf_version: '0.1'` from
`OKF_VERSION`. It never borrows an excluded or unsupported parent's metadata. Even
an empty enabled site gets this root index. Unneeded standalone directories are
pruned from the managed inventory, preserving unrelated discovery files and pages.

When a supported eligible page owns an index path, its document is rendered again
from the published revision, through the ordinary page and frontmatter hooks. The
navigation is appended once after its body. A root page-owned index also gets
`okf_version`; its other frontmatter is retained. Rebuilds never append to old stored
Markdown. Unsupported page types are not converted into partial page exports; a
standalone navigation document may occupy an otherwise unowned directory instead.
An empty supported page can render with navigation, as allowed by `render_page`.

Reserved `index` and `log` slugs use the policy allocator. Real escaped-name siblings
force the page-ID suffix; if a real sibling also owns that suffix, trailing underscores
are added until the path is distinct. A page can take over a standalone `index.md`
through the writer's checked `replace_index=True` publication option. It cannot
replace another page's index, and ordinary page publication retains its existing
collision checks.

## Customising navigation

```python
from wagtail import hooks


@hooks.register("markdown_index_content")
def customise_index(content, path, context):
    # path is site-relative, e.g. "campaigns/index.md".
    # context contains site, path, page (published owner or None),
    # entries (an immutable tuple of IndexEntry), and count.
    # Each entry exposes page_id, path (hostname-prefixed), url, title, description.
    if context["page"] and context["page"]._meta.label == "myapp.AuthoredIndexPage":
        return ""  # This project's page renderer already supplies its listing.
    return content.replace("## Pages (", "## Available pages (")
```

Hooks run in normal Wagtail order. Return a Markdown string to replace the navigation,
`None` to keep it, or `""` to suppress it. The hook receives only navigation, so it
cannot accidentally replace the parent's body or YAML. Invalid return types and hook
errors abort the affected build. Hooks must be deterministic and must not mutate CMS
or export records; publication checks still reject obsolete output if inputs change.

For the synthetic 350-style fixture, the chosen package order is hero, intro, body,
then a single generated title-ordered navigation list. It includes all 13 exported
children in [the golden file](../tests/golden/index.md), independently of the HTML
view's 12-item pagination. Projects may suppress generated navigation when they own
an authored listing; the generator does not guess by deleting matching body text.
The production 350.org mapping and presentation sign-off remain separate (#63/#65).

## Batch and revocation behaviour

`mark_dirty(site_id, page_ids=())` coalesces a site and remembers its existing page
index owners and other site-dependent page documents before writes can retire their
pointers. The next finalisation repairs
those pages as leaves or indexes using their current paths. Call it **before** any
external writer operation. For lifecycle code that has already withdrawn pointers,
pass affected old/new parent IDs explicitly. Moves between sites must dirty both
scopes; the batch does not infer deleted pages' ancestry.

`batch.delete_page(page_id, site_id=...)` captures those owners and immediately calls
the writer's revocation API. Inside a CMS transaction, capture/withdraw there and
schedule `batch.finalise` with `transaction.on_commit`; generation itself must run
after commit. Direct reads hide newly private dependent metadata even before cleanup
runs. A failing context manager does not finalise or undo completed revocations.

For an explicit artefact deletion that leaves the CMS page eligible, call
`batch.finalise(exclude_page_ids=deleted_ids)` to rebuild surviving discovery without
recreating those page documents. The same option is available on
`IndexGenerator.generate`. It applies only to that batch, not to later generation.
A generic directory listing can occupy a deleted page's former index path when
surviving descendants still need it. Scoped deletion commands use this option;
site/all deletion does not finalise the emptied scopes.

Finalisation repairs leaves first, then page indexes from deepest directory to root,
then standalone indexes and `llms.txt`. The [manifest](manifest.md) runs last; batch
results include both discovery records.
It is not a single atomic site-wide deployment: each file retains the writer's
complete-generation contract. CMS changes during finalisation
raise `StaleBuild`; competing publications invalidate the affected token. Failed sites
remain dirty on that batch object for an explicit fresh retry. Successfully finalised
sites are removed, and another `finalise()` without new work is a no-op.

Rebuilding all indexes in each dirty site is deliberately conservative in v0.1. The
batch is in-memory and synchronous; durable queues and narrower dependency tracking
remain future work. Private storage placement and checked routes are still required.
