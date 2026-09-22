# 03 — Managed storage publication

Implementation of #19 authorised by the project owner after committing #78.
These are package storage contracts, not additional customer deliverables.

- A page's logical path comes from ExportPolicy. A storage backend may rename a
  saved object: record its returned key and keep the logical path stable.
- Every upload uses a fresh private object directory. Switch the database pointer
  only after a successful, readable save and fresh publication checks. Readers get
  a complete old or new file; ordinary write failures preserve the old pointer.
- A database mutex serialises publication per site
  across workers. A generation token becomes obsolete after another publication
  or revocation. Revision, path, site and eligibility are checked again after IO.
- Pause a build, then publish/move/restrict/exclude/delete its page: resuming the
  build raises a stale-build error and does not restore its export. Revocation
  increments the generation even if no export exists, invalidating paused work.
- Shared listings are withdrawn on page publication/deletion and rebuilt through
  optimistic aggregate updates with at most three attempts. Page changes and
  revocation abort retries. They must not overwrite a page-owned index.md.
  Aggregate reads also recheck their site source state against CMS changes.
- Aggregate uploads and retired-object cleanup acquire no site mutex during IO;
  unrelated readers can continue. Readers recheck ownership and eligibility after
  opening storage and close streams that became obsolete during IO.
- Site-state policy queries remain bounded as pages are added; fresh batched inputs
  agree with ordinary policy for restrictions, nested sites, hooks and reserved paths.
- Only owned records determine deletion, including earlier hook paths. Cleanup
  failure retains an inventory row for retry; unrelated files remain untouched.
- Reject traversal, encoded separators, malformed host prefixes and unsafe returned
  storage keys. Serving/discovery must resolve logical records, not raw storage URLs.
- Generated signals follow committed publication; deleted signals follow successful
  deletion. Notification preparation and receiver failures are logged without
  undoing a committed operation or skipping cleanup.
- Support a backend with only save/open/delete/exists and no filesystem/mtime/listing
  APIs. The default is BASE_DIR/markdown_export. Missing default configuration has
  a clear Django system check and runtime error.
- Database and object storage are not one transaction. Document abandoned upload
  windows and require private storage with read-after-write visibility and stable
  open handles. Writer publication is invoked after the caller's transaction commits;
  lifecycle signal wiring remains #23/#69/#70.
