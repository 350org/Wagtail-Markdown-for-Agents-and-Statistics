# 09 — Restriction and exclusion lifecycle

Project-owner authorised for #70, using the issue's v0.1 acceptance criteria.

- Saving an active view restriction withdraws the page and inherited subtree's
  owned files and site-dependent indexes, llms.txt and manifest synchronously,
  including actual hook/remote storage keys. AUTO_GENERATE and task backends never
  defer withdrawal. Public (`none`) rows do not restrict access.
- Removing/relaxing restrictions restores eligible subtree pages inline after
  commit on the write database, bypassing the task queue. Re-fetch existence,
  published revision and full policy, including other inherited restrictions,
  exclusions, disabled types and hook vetoes. AUTO_GENERATE=False leaves missing
  exports for an explicit refresh. New drafts must never be exported.
- Exclusion saves and removal follow the same rules for the selected page only;
  exclusion does not propagate to descendants. Unrelated frontmatter saves do
  not trigger an eligibility refresh. Use persisted values with update_fields.
- Rollback discards restoration; immediate deletion may leave safe missing files.
  Cascaded restriction/settings deletion never recreates deleted pages or sites.
- Managed direct routes and shared serving reject revoked pages and aggregates.
  Canonical requests still pass through Wagtail's HTML access controls. Implemented
  negotiation/discovery behaviour is covered separately in scenarios 10 and 11.
- A deploy runs `agentmd_revoke_ineligible` with the new configuration before
  returning traffic to workers. It synchronously reconciles owned page IDs against
  current policy, including PAGE_TYPES, without generation, AUTO_GENERATE, startup
  database IO, storage sweeps or #75 staleness tooling. Checked reads deny access
  as soon as the new policy is loaded. #24 can reuse this reconciliation helper.
- Bulk updates/raw fixture loading bypass receivers: project code must reconcile
  revocations explicitly and schedule any restoration after commit. Moves stay #69.
- Verify filesystem and renamed remote storage, commit/rollback, cascades,
  deferred task backends, fresh policy, support-matrix CI and PostgreSQL.
