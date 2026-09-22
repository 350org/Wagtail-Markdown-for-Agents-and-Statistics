# Publication and eligibility lifecycle

The package connects Wagtail's `page_published` and `page_unpublished` signals and
Django's `pre_delete` signal for the base `Page` model in `AppConfig.ready()` (#23).
Connections are idempotent. Specific page subclasses and cascade-deleted descendants
also have base Page rows, so deletion does not rely on registering every host model.
Restriction and exclusion receivers additionally connect `pre_save`, `post_save`
and `post_delete` for `PageViewRestriction` and `PageAgentSettings` (#70).
Moves connect `pre_page_move` and `post_page_move`; published slug changes connect
`page_slug_changed` (#69).

## Automatic generation

`WAGTAIL_MARKDOWN_AGENTS["AUTO_GENERATE"]` defaults to **True**, deliberately unlike
the WordPress plugin's default False. Together with the broad default `PAGE_TYPES`,
this means publishing eligible supported page types generates Markdown automatically.
Run migrations and include the [public routes](public-export-routes.md) before use.
Storage/rendering/URL configuration errors are logged if automatic export cannot finish.

Publication schedules work with `transaction.on_commit(using=...)`, using the signal's
write alias where supplied, otherwise the instance's database. Outside an atomic
transaction the callback runs immediately. It calls `tasks.enqueue`, whose v0.1
implementation runs inline. No job queue, background worker or configurable async
backend ships in this change.

The callback carries page IDs, site IDs and former page-index owner IDs. Execution
re-fetches the page and checks its current live revision, site and eligibility.
An old callback cannot export a deleted, unpublished, restricted or excluded page;
a newer publish is read instead of stale content. A newer draft is never rendered.
The managed writer still guards changes during rendering and storage publication.

A refresh publishes selected leaf documents, then complete page indexes, standalone
indexes, `llms.txt` and `manifest.json`. Page indexes retain their body/frontmatter
and receive navigation once. Captured former index owners allow a surviving parent
to become a leaf after its final live child is removed.

Set `AUTO_GENERATE=False` to stop routine lifecycle regeneration. This also applies
to previously queued automatic work when it eventually executes. The setting controls
scheduling only: changing it does not invalidate otherwise current content hashes or
publication guards. Re-enabling it does not automatically backfill missing exports;
use an explicit refresh for that work.

## Immediate withdrawal

Unpublish and pre-delete revoke the page's owned export, standalone site aggregates
and site-dependent page exports synchronously. This never goes through `enqueue`
and never consults `AUTO_GENERATE`. Recorded ownership supplies actual old paths and
storage keys, including hook relocations; no storage directory is swept.

With automatic generation enabled, dependent discovery is repaired after commit.
With it disabled, withdrawn artefacts remain unavailable until explicitly rebuilt.
A rollback discards the refresh callback but cannot undo physical storage deletion:
a restored pointer may safely refer to a missing file. Checked serving returns a
miss until a rebuild repairs it. Unrelated leaf files remain owned and readable
when their source state is still current.

Deletion callbacks run after the collector has removed pages and any cascaded Site
or restriction records. Missing pages/sites are skipped, so they are never recreated.
A surviving site's indexes and discovery are rebuilt from current readable exports.
Several signals in one transaction can each schedule a refresh. Later discovery-only
callbacks skip work if checked root/discovery files and captured former index owners
are already readable; this preserves a cascade's first manifest change summary.
This is not an automatically debounced transaction queue. Use the explicit multi-page API below to
coalesce bulk work. Immediate revocation is always independent of that coalescing.

Unpublishing
a parent alone follows Wagtail's own state changes: descendants are only unpublished
when Wagtail also unpublishes them. Their independent eligibility policy is unchanged.

## Moves and published slug changes

Before a move, the receiver captures subtree IDs, affected sites and former index
owners. Wagtail supplies a fresh page instance to the post-move signal; the shared
before-parent argument carries the operation's snapshot between phases. Both URL
paths identify the operation. A reorder with identical before/after paths does no
export work. The slug receiver uses Wagtail's `instance_before` argument; saving a
draft revision alone does not relocate the published exports.

After successful commit on the write database, cleanup withdraws the subtree's
owned files and dependent discovery artefacts inline. Actual old logical paths and
backend-returned storage keys come from managed ownership, including paths supplied
by hooks that have since changed. Cleanup never depends on `AUTO_GENERATE` or a task
queue. A rolled-back move/rename leaves its old physical files intact, unless another
event in that transaction separately revoked them.

With automatic generation enabled, one subtree refresh re-fetches current pages and
rebuilds eligible published descendants, affected parents, root/directory indexes,
`llms.txt` and the manifest. Former and new parent IDs cover leaf/index transitions,
including custom export paths. Deleted or newly ineligible pages are skipped, and a
later move or publish takes precedence over captured state. Site root URL caches are
cleared before rebuilding; export snapshots and link caches last only for one build.
Automatic failures are logged after the CMS transaction has committed.

Removed explicit export URLs return 404. Old canonical URLs remain subject to normal
Wagtail HTML/redirect handling, including requests with a Markdown Accept header or
query parameter. Content-negotiation middleware itself remains tracked separately;
the move receivers do not add redirects or serve old export bytes. Incoming links in
unrelated leaf exports require an explicit related-page refresh as described below.

## Restrictions and exclusions

Saving an active `PageViewRestriction` synchronously withdraws the page's subtree
and dependent site artefacts through `revoke_pages`. Login, password and group
restrictions are all private for exports; changing between them never grants access.
A restriction with type `none` is public. Other own/ancestor restrictions still
apply. Group membership changes cannot make a group-restricted page exportable.

Removing a restriction or changing it to `none` schedules subtree restoration with
`transaction.on_commit(using=...)`. This callback runs **inline**, bypassing
`tasks.enqueue`, even if a project replaces the task backend. Each page is re-fetched
and must still exist, have an eligible published revision, and pass the full policy.
Cascaded deletion cannot recreate a deleted page/site; rollback discards restoration.
The writer's publication guards also reject changes during rendering/upload.

`PageAgentSettings.excluded=True` withdraws the selected page and site dependencies;
exclusion is not inherited by descendants. Clearing the flag or deleting an excluded
settings row restores the page after commit under the same rules as restrictions.
Receivers compare persisted state, including `update_fields`, so unrelated metadata
edits do not accidentally restore a page. Reassigning a restriction/settings row
withdraws its new owner and schedules restoration of its former owner.

`AUTO_GENERATE=False` suppresses automatic restoration and discovery repair, including
a callback scheduled before the setting was disabled. It never suppresses immediate
withdrawal. Use explicit `refresh_pages` after commit to restore eligible content
with automatic generation disabled. Export failures at the automatic after-commit
boundary are logged; explicit callers receive exceptions for retry.

The direct page routes, aggregates and shared serving function check current policy
and ownership on every read. Withdrawn aggregates return 404 and expose no private
titles, descriptions or manifest entries. Canonical HTML still runs through Wagtail's
access controls when Markdown is missing. The [negotiation](negotiation.md) and
[discovery](discovery-headers.md) middleware phases (#26/#27) serve through the same
checked path; the discovery cache is keyed by the publication version these
receivers advance and is never a serving decision. Bundles/ARD remain outside this
change.

## Deploy and bulk eligibility changes

`PAGE_TYPES` is deployment configuration, with no model save signal. When disabling
types or tightening an eligibility hook, load the new configuration and run:

```bash
python manage.py agentmd_revoke_ineligible
```

Run this as a deployment step before returning traffic to workers running the new
configuration. Retire old workers too: they must not keep writing with the old policy.
Checked reads reject newly ineligible pages and stale listings as soon as the new
configuration is loaded; the command physically withdraws their owned files and site
dependencies. It always runs synchronously, regardless of `AUTO_GENERATE`, and never
generates content. Eligible leaf ownership is preserved, though configuration
fingerprints may require rebuilding those files before they are readable again.
After successful revocation, use explicit `refresh_pages` to rebuild the selected
eligible pages/discovery if needed. Re-enabling types likewise requires a refresh.

The reusable `revoke_ineligible(using="default")` helper checks all owned page IDs
against current full policy and returns IDs selected for withdrawal. It also handles
missing/unpublished pages. The operation is safe to repeat and uses recorded storage
keys; it never sweeps a directory. Backend cleanup failures retain managed retry
inventory and are logged, while the withdrawn pointers remain unavailable.
Database/policy errors propagate. The [management commands](management-commands.md)
provide scoped generation and status; the [system checks](system-checks.md) (#29)
never mutate exports or query the database at app startup. This is a
v0.1 revocation trigger, independent of #75's future general staleness workflow.

Django bulk updates (`update`, `bulk_update`, `bulk_create`) and raw fixture loading
bypass these receivers. Project code must explicitly call `revoke_ineligible` within
the write transaction for immediate withdrawal, then schedule `refresh_pages` for
any restoration after commit. Deleting querysets does emit the deletion signals.
Raw fixture handlers skip related queries while Django loads potentially incomplete
data; reconcile before serving that data.

## Explicit refresh and shared helpers

```python
from functools import partial
from django.db import transaction
from wagtail_markdown_agents.export.lifecycle import refresh_pages

# Within project-owned editing code, collect stable IDs and schedule after commit.
# Direct refreshes intentionally work even with AUTO_GENERATE=False.
page_ids = (first_page.pk, second_page.pk)
transaction.on_commit(partial(refresh_pages, page_ids, using="default"), using="default")
```

`refresh_pages(page_ids, *, scopes=None, using="default")` refreshes selected pages
and finalises each affected site's indexes/discovery once. It preserves other readable
page/type scopes through `IndexBatch`. It requires autocommit and raises real
render/storage/publication errors to explicit callers. Its result is a list of
published records; it is not a CLI counter/status report.

`subtree_page_ids(page_id)` returns current subtree IDs, including the root, or an
empty tuple for a missing page. `capture_scopes(page_ids)` records current and
previously owned sites plus their former page-index owners. `revoke_pages(page_ids)`
withdraws owned content immediately and returns that scope snapshot. These helpers
support subsequent #69/#70 work without reconstructing old paths. They retain the
writer's default-primary-database requirement; unsupported aliases are rejected.

`schedule_refresh(page_ids=(), scopes=None, using="default")` is the routine
AUTO_GENERATE-aware after-commit scheduling seam used by receivers. Explicit callers
can instead schedule `refresh_pages` directly when a rebuild is required regardless
of that setting. Copy or materialise page IDs before scheduling; never defer an
unevaluated page queryset whose scope might change.

## Related content and failures

In v0.1 ordinary edits to images, documents, snippets, donation settings or referenced
page fields require project-owned after-commit hooks selecting the affected page IDs.
An explicit full-site selection is the conservative fallback when dependencies are
unknown. HTML cache purges alone do not rebuild Markdown. Use the helper above or
`agentmd_generate --site example.org --force` for an explicit refresh. There is no persistent
dependency graph. The exact 350.org refresh selection/sample still needs agreement
under #63/#65; this core implementation does not settle those presentation decisions.
Incoming links in unrelated leaf exports require this explicit refresh after target moves. Changes to
eligibility are a separate privacy requirement and are never deferred as ordinary
freshness or configuration-staleness work.

Unsupported or empty leaf documents are logged as skipped, their old owned exports
are withdrawn, and no successful page entry is added to the manifest. An index may
still be renderable from its navigation. Other render/storage errors abort the batch
before discovery/manifest finalisation; earlier successful page writes may remain.
The after-commit signal boundary logs failures with page and scope IDs rather than
misreporting an already committed CMS publish as a rollback. Operators must fix the
cause and explicitly retry the affected refresh. Direct API calls propagate errors;
a future deferred task backend must provide its own failure reporting and retry policy.

Tests in `tests/test_lifecycle.py` and `tests/test_eligibility_lifecycle.py` exercise
actual Wagtail/model signals. Component tests
isolate their manual writer operations from these receivers using a test-only fixture;
the package has no production switch that disables revocation.
