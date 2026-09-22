# 08 — Publish, unpublish and delete lifecycle

Project-owner authorised for #23 after completion of the v0.1 export artefacts.
These scenarios implement the issue's core lifecycle criteria. The representative
350.org dependency-refresh decisions under #63/#65 remain separate sample work.

- Given an eligible published page, publishing a revision generates its Markdown,
  affected page indexes, standalone indexes, llms.txt and manifest after commit,
  through `tasks.enqueue`. A rolled-back transaction generates nothing.
- Deferred callbacks contain IDs and captured scope/index-owner IDs, never page
  instances or rendered content. Execution re-fetches existence, current published
  revision, site and eligibility. Newer drafts cannot leak, obsolete callbacks
  cannot restore deleted/unpublished/private pages, and a newer publish wins.
- Given an unpublish or delete, owned page files and dependent aggregates are
  withdrawn synchronously before returning from the signal, regardless of
  AUTO_GENERATE or the task backend. Physical cleanup uses recorded storage keys,
  including old hook paths. Rollback may leave safe missing files until rebuilt.
- Pre-delete receivers see base Page rows for specific page types and descendants.
  Delete cascades must not recreate deleted pages. A surviving parent's final
  child deletion repairs its former index into a leaf after commit. A deleted site
  is never recreated. Non-Page deletes are ignored.
- AUTO_GENERATE defaults to True. False prevents routine lifecycle regeneration,
  while revocation and checked serving remain active. Toggling only this setting
  leaves otherwise current files readable. Re-enabling it does not implicitly
  rebuild historical missing files.
- Shared helpers accept multiple page IDs, capture current/recorded scopes and
  former page-index owners, and finalise each affected site once. Explicit bulk
  callers use those helpers or IndexBatch; signals do not introduce a durable
  queue, transaction-internal callback registry or automatic debounce.
- Unsupported/empty page bodies are logged as skipped, with no successful page
  export or manifest entry. Real render/storage failures abort finalisation and
  are logged at the after-commit signal boundary; direct refresh calls raise.
  The CMS commit is not misreported as rolled back after an export failure.
- Use the supplied write database alias, otherwise the instance's database.
  Preserve the writer's default-primary-database requirement: reject unsupported
  aliases before touching default-database export state.
- Ordinary related-content edits use an explicit after-commit refresh of chosen
  page IDs (a whole-site page selection is the conservative option). No automatic
  dependency graph or incoming-link repair after moves is claimed in #23.
- Verify real Wagtail signals, commit/rollback, newer drafts, deferred execution,
  unsupported content, cascades, generation disabled, old hook paths, filesystem
  and renamed remote storage, the support matrix and PostgreSQL.
