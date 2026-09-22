# Managed export storage

`FileWriter` implements #19. It writes rendered pages and provides the publication
contract for the index, discovery and manifest generators. The
[public routes](public-export-routes.md) now provide checked direct retrieval.
The [publish lifecycle](publish-lifecycle.md) wires publish/unpublish/delete plus
restriction/exclusion revocation and restoration. Its `agentmd_revoke_ineligible`
command handles deploy/bulk eligibility changes. Move/slug receivers refresh changed
subtrees after commit. The [management commands](management-commands.md) expose scoped
generation, status, index rebuilds and owned-file deletion (#24/#69).

```python
from wagtail_markdown_agents.export.writer import FileWriter

writer = FileWriter()
record = writer.generate(page)
with writer.open(record.logical_path) as stream:
    markdown_bytes = stream.read()
```

Run the package migrations first. By default, objects live below
`BASE_DIR / "markdown_export"`, outside media/static. Set
`WAGTAIL_MARKDOWN_AGENTS["STORAGE"]` to an explicit Django `STORAGES` alias to use
another backend. Missing BASE_DIR/default configuration or an invalid alias is
reported by Django system check `wagtail_markdown_agents.E001` and at runtime.
The v0.1 writer requires CMS and export tables on the same default database and
rejects routers that send those reads or writes elsewhere, including replicas.

## Logical paths and publication

The URL tree describes **logical paths**, such as `example.org/blog/post.md`.
`ExportArtifact` maps each logical path and stable page ID to an `ExportFile` row.
The file row records its actual storage alias, configuration fingerprint and returned
key. Those records are the shared ownership source for future serving, links,
discovery, manifests and deletion; never infer a storage key from a request URL.

Every upload has a new private key such as
`example.org/.objects/<random-id>/content`. A backend may rename the final filename
within that allocated directory. The writer records the returned key, opens it to
verify the complete UTF-8 bytes, then switches the database record in a transaction.
It does not overwrite an existing storage object or require local atomic rename.
The public logical path remains stable even when the object key changes.

ExportPolicy and the writer use the same path validator. Paths must be canonical,
site-prefixed and free of traversal, backslashes, encoded separators, query/fragment
syntax and control characters. Hook results such as `a/../b.md`, `./b.md` and
`a//b.md` now raise `ExportPathError`; they are no longer silently normalised.
The `.objects` segment is reserved for private files. A backend returning a key
outside its allocation violates the contract: it is never published or automatically
deleted, because that key might belong to someone else.

## Concurrent builds and readers

`generate` captures a `BuildToken` before rendering. For custom pipelines:

```python
from wagtail_markdown_agents.rendering import render_page

token = writer.begin(page)
text = render_page(page)
record = writer.publish(token, text)
```

Before switching the record, the writer checks the current site generation,
published revision/dates, URL/export path, site identity, export settings and
eligibility. An obsolete token raises `StaleBuild`; its candidate is discarded.
Rebuild from fresh state rather than retrying the old text. Another publication or
revocation in the same site invalidates an in-flight token, even for a different
page. This is deliberately conservative; bulk generation should run sequentially.

An `ExportScope` row serialises publication and deletion using
a database UPDATE lock. This works across processes; it is not a Python thread lock
or SQLite's ineffective `select_for_update`. SQLite lock contention has a bounded
retry; other database failures propagate. `open(logical_path)` resolves the current
immutable file without that mutex, checks CMS source state, opens storage, then
rechecks the pointer and source state. A concurrent replacement is retried up to
three times; revoked or repeatedly superseded reads raise `FileNotFoundError`.
Already-open streams can finish reading their complete generation after deletion.
Callers may supply `site_id=` and `file_id=` to bind the opened file to previously
checked ownership/metadata. A different generation then raises `FileNotFoundError`.

Parent pages, pages with hierarchy metadata, and pages receiving `navigation=` also
capture the eligible site state. Set `depends_on_site=True` on `begin`/`generate`
when a project hook includes computed listings or other site-dependent content.
Such reads/builds fail closed when that state changes. Revocation withdraws these
page-owned indexes as well as standalone aggregates. Rebuilding one parent index
does not withdraw other parent indexes built from the same current CMS state.

The aggregate/site-dependency check loads fresh batched policy inputs for each
check: pages, sites, restrictions and export settings. Built-in policy queries stay
bounded as pages are added; CPU and memory still grow with site size. Custom hooks
and routing overrides may issue additional queries. A leaf publication with no site
dependencies avoids this scan. This is not a dependency graph or persistent cache.
Ordinary changes to images, snippets and external settings still need the rebuild
procedure in the [publish lifecycle guide](publish-lifecycle.md).

## Shared indexes and manifests

```python
record = writer.update_aggregate(
    site.pk,
    "example.org/manifest.json",
    lambda previous: build_manifest(previous),
)
```

The callback receives existing text, or `None` for a missing/expired file, and
returns the complete replacement. Capture and publication use the site mutex;
reading storage, running the callback and uploading happen outside it. A competing
aggregate publication causes a fresh read and retry, up to three attempts, so
simultaneous updates cannot lose each other's changes. Callbacks must be pure:
they may run repeatedly and must not mutate CMS data, cause external side effects
or recursively call the writer. Page publication, revocation or changed CMS inputs
abort with `StaleBuild` instead of retrying. A separate content generation counter
distinguishes these changes from aggregate-only updates. The underlying generator
must use successfully published records and retain other scopes when updating a
manifest. Full generation is also possible with `begin_site`/`publish` tokens.

Both `publish` and `update_aggregate` accept an optional `commit(scope, record)`
callback. It runs after the pointer swap inside the same database transaction and
may update private database state only, with no storage/network IO or recursive
publication. An exception rolls back both the pointer and the state. The manifest
uses it to advance `ExportScope.manifest_state` atomically; that private baseline
contains only page IDs and comparison hashes, surviving public aggregate withdrawal.

A standalone aggregate cannot overwrite a page-owned `index.md`. Supply generated
navigation to `writer.generate(page, navigation=...)` so its authored body and
frontmatter survive. Page publication withdraws standalone aggregates until rebuilt.
The lifecycle coordinator must rebuild all affected discovery files after its page
batch; scoped manifest generation must reconstruct other entries from owned records
when the previous aggregate has been withdrawn. The [index batch](indexes.md) now
finalises indexes, llms.txt and the [manifest](manifest.md) in that order.

## Revocation, transactions and cleanup

Publication (`generate`, `publish`, `update_aggregate`) requires autocommit: schedule
it with `transaction.on_commit()` after an editor's successful transaction.
`delete_page(page_id, site_id=...)` and `delete_site(site_id)` instead support
immediate withdrawal inside a revocation transaction. They increment the site
generation even if no file exists, preventing a paused build restoring deleted
content. `delete_page` withdraws that page plus site aggregates and dependent
page-owned indexes; it does not delete unrelated leaf exports or unowned files.

The lifecycle receivers invoke these operations synchronously on unpublish/delete
and restriction/exclusion changes, including descendants under inherited restrictions.
Restoration runs after commit with fresh policy checks. The #69 extension must also
cover old site scopes for moves; `open` already rejects obsolete paths while automatic
move cleanup remains unwired. Public routes must use this checked API and their
serving gates.

Retired object rows remain marked `cleanup_pending` until storage deletion succeeds.
`writer.cleanup(site_id)` retries only those rows, including prior hook paths and
old storage aliases. Backend deletion acquires no site mutex; concurrent cleaners
may repeat an idempotent delete, but only one removes the inventory row and emits
its notification. A caller's outer revocation transaction still retains its lock
until commit, including immediate physical cleanup. No directory listing, mtime,
local path or broad storage sweep is used. Changing an alias's backend/options
causes a fingerprint mismatch; cleanup
keeps its inventory instead of deleting from the newly bound backend. Restore the
old backend configuration to complete cleanup. IDs survive CMS page/site deletion
so ownership records are not lost in a cascade.

If a revocation transaction rolls back after physical deletion, its database pointer
may return while the file stays missing: reads safely fall back until rebuilt. Failed
ordinary writes leave the previous record intact. Cleanup failure after publication
is logged and retained for retry; it does not turn a committed publication into an
apparent failed upload.

## Backend and failure contract

Backends must confine keys to their configured private namespace, support
`save/open/delete/exists`, make successful writes immediately readable, keep
opened streams stable through deletion, and treat deleting a missing key as success.
An upload must not overwrite another allocation. Do not expose this directory or
bucket publicly: database withdrawal cannot revoke a raw public object URL. A local
backend uses the same immutable-object protocol; no rename capability is assumed.

The database and object store do not share a transaction. A process crash during
upload can leave an unreferenced candidate. Its requested allocation is recorded
before IO, but a crash after a backend renames the object and before the returned key
is recorded can leave an object requiring backend-specific operator recovery.
These candidates are inaccessible through the managed API. Cleanup deliberately
does not sweep active/abandoned allocations: that could delete a concurrent upload.
A failing backend must either leave no object or leave it at the requested key;
an exception after an unreported rename has the same recovery limitation.

`markdown_generated` is emitted after committed publication. `markdown_deleted`
follows successful physical deletion and database commit, including cleanup retries.
Both include `page_id` (None for aggregates), `site_id`, logical `path`, actual
`storage_key` and `storage_alias`; generated also includes `page` (None for aggregates).
Replacing bytes at the same path does not emit a logical deletion. Notification
preparation failures (including page lookup) and receiver failures are logged
without reversing committed work or skipping cleanup. These are best-effort notifications,
not a durable event queue: a process crash can occur between commit and notification.
