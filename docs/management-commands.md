# Export management commands

Run these commands from the host Wagtail project, after applying migrations and
including the [public export routes](public-export-routes.md). They operate directly
on managed export records and storage; `AUTO_GENERATE=False` does not disable them.
Writing commands require autocommit, so do not call them inside `transaction.atomic()`.

## Selection

The four export commands accept `--page-id ID`, `--type app_label.ModelName` and
`--site hostname`. Combined filters intersect. Page selection means that page only,
not its descendants; type selection matches the exact model. Generation still
refreshes affected parent/root navigation and discovery across that site's readable
exports, because those files are shared dependencies.

Generation, index generation and status default to sites enabled by `SITES`.
An explicit generation site must be enabled. An explicit hostname must identify
exactly one configured Wagtail site; ambiguous hosts, unknown pages/types/sites,
non-Page models and contradictory page filters raise `CommandError`.
Explicit generation of unsupported page types is rejected. In bulk runs,
unsupported or ineligible pages are reported as skipped. A valid type with no
matching pages produces an empty selection.

Deletion requires `--page-id`, `--type`, `--site` or `--all`; `--all` cannot be
combined with other scopes. It can clean up disabled sites. Deletion uses recorded
ownership in the selected site, even if the page has moved. A deleted page can still
be selected by ID while its storage inventory exists. `--all` also reaches records
whose Wagtail site no longer exists; type filters require surviving CMS page rows.

## Generate pages

```bash
python manage.py agentmd_generate --dry-run
python manage.py agentmd_generate --site example.org
python manage.py agentmd_generate --page-id 42
python manage.py agentmd_generate --type blog.BlogPage --site example.org --force
```

The command renders current published revisions, publishes leaf documents, then
finalises complete page indexes, directory indexes, `llms.txt` and the manifest once
per affected site. It never renders a newer draft. Missing or unavailable selected
exports are rebuilt. Existing owned exports for selected ineligible/unsupported pages
are withdrawn along with their dependent discovery artefacts.

Without `--force`, a selected export is skipped when its recorded source/dependency
state still matches and its exact owned storage object can be opened. This is a
publication-state check, not a new content-hash incremental mode. A changed live
revision or a missing file causes a rebuild. Pages without a revision are exported
from their live row; editing that row in code does not change the recorded state. `--force` bypasses that check, including
when project hooks or related content have changed without a new page revision.
The general configuration-staleness workflow (#75) and hash-based incremental/delta
commands (#41) remain separate work. No ignored flags or `--with-manifest` switch
are provided.

The summary reports `generated`, `skipped`, `failed`, `failed_scopes` and
`discovery_scopes`. Page counts refer to the selected pages; dependency refreshes
can additionally rewrite parent/root page indexes. Empty leaf bodies are skipped
with their reason, never counted as successful exports. Even if every selected page
is current, missing discovery files trigger a site finalisation.

A page failure is reported with its ID and does not stop independent sites. The
failed site's pending indexes and manifest are not finalised as a successful batch.
Already-published pages remain available when their state is current. Discovery
failures are reported separately; any page/site failure makes the command exit
nonzero. Fix the error and rerun the same selection to repair missing work.

[Link rewriting](internal-links.md#missing-targets-and-generation-order) checks
target availability while rendering. Initial generation can therefore retain HTML
links to pages generated later in the run. A subsequent `--force` run can rewrite
those links once the target records exist; there is no automatic second link pass.

## Rebuild discovery

```bash
python manage.py agentmd_generate_indexes --site example.org
python manage.py agentmd_generate_indexes --page-id 42 --dry-run
```

This explicitly rebuilds indexes, `llms.txt` and the manifest for each affected site;
its generated/failed counts are **site counts**. Page/type filters select affected
sites, not a partial version of a shared index. Existing page indexes retain their
complete published body. Former index owners can become leaves again when needed.
Missing, previously unowned leaf documents are not backfilled; use
`agentmd_generate` for those. Missing eligible documents remain manifest errors.

## Inspect status

```bash
python manage.py agentmd_status
python manage.py agentmd_status --type blog.BlogPage --site example.org
```

Status only reads database/storage state and reports each selected page:

- `current`: the checked owned export can be opened.
- `missing`: an eligible supported page has no export pointer in its current site.
- `unavailable`: a pointer exists, but its file is missing or its recorded state/path
  is no longer current.
- `ineligible` or `unsupported`: no export should be generated under current policy
  or the v0.1 renderer contract.

The summary includes eligible/current/missing/unavailable/skipped/failed counts and
owned files awaiting cleanup in the selection. Missing/unavailable exports are
inventory information, not command failures. Unexpected database, policy or storage
errors are reported and cause a nonzero exit. Status does not render pages, infer
past job results or persist a configuration-staleness report.

## Report block coverage

```bash
python manage.py agentmd_blocks
```

This lists every block that can appear in an exported StreamField and shows how
each one becomes Markdown. It reads block definitions only. It needs no pages,
renders nothing and writes nothing. It covers the page types that `PAGE_TYPES`
enables and the fields that `PAGE_FIELDS` selects. Form page types that have a
StreamField are listed as skipped.

Each block's path comes from the renderer that export itself resolves, so the
report always matches export:

- **Project renderer**: a renderer your project registered, by class or by name
  (`(by name)` marks a name registration).
- **Built-in renderer**: one of this package's renderers.
- **Custom template**: no renderer applies, and the block has its own template. The
  template is rendered and its HTML is converted. The template also renders the
  block's children, so they are not listed under it and their renderers are never
  used.
- **Wagtail default HTML**: no renderer and no custom template. Wagtail's basic HTML
  for the block is converted.

Children are listed only where export reaches them: inside StructBlocks,
StreamBlocks, ListBlocks and TypedTableBlocks that render through the built-in
renderers. A ListBlock item or a table cell has no name of its own, so it is listed
as `(list item)`. The same block used in several places is listed once, with the
first place it appears and a count of the others. Blocks that choose a template per
value are reported with the template chosen for an empty value.

Rows under "Custom template" and "Wagtail default HTML" are the ones to check: the
converted HTML may include presentation-only text, or content the template leaves
out. To give a block its own Markdown, register a renderer in a
`markdown_renderers.py` module, then run the report again.

## Delete exports

```bash
python manage.py agentmd_delete --page-id 42 --dry-run
python manage.py agentmd_delete --page-id 42
python manage.py agentmd_delete --type blog.BlogPage --site example.org
python manage.py agentmd_delete --site example.org --yes
python manage.py agentmd_delete --all --yes
```

Page deletion needs no additional prompt. Type/site/all deletion requires typing
`yes`, or supplying `--yes` for unattended use. The command reports the selected
artefact/site counts before prompting. EOF or absent input never implies consent.

Deletion withdraws owned pointers and deletes their recorded storage objects,
including prior hook paths and backend-renamed keys. It also withdraws standalone
discovery files and dependent page documents in affected scopes, so they cannot keep
listing deleted exports. Page/type deletion then refreshes surviving discovery once
per enabled site, excluding the selected page IDs from regeneration. Dependent
documents with hierarchy metadata are also rebuilt. Unrelated leaf exports, other
sites, unmanaged files and CMS content remain intact. It does not traverse a storage
directory or delete a filesystem tree. The summary separates selected `deleted`
artefacts from `dependent_withdrawn` artefacts and counts repaired `discovery_scopes`.

Site-wide and `--all` deletion leave their selected export trees empty. When a deleted
page formerly owned a directory index, scoped repair can replace its document with
a generic listing of surviving descendants. The deleted page's body is not restored.
Eligible pages whose exports were deleted remain missing-export errors in the manifest;
deletion does not change CMS eligibility. A subsequent generation/publish can restore
eligible exports, and a later index command can restore eligible page-owned indexes.
Use [exclusion settings](publish-lifecycle.md#restrictions-and-exclusions) when a page
must remain unexported.

Failed physical deletions retain their private ownership inventory for retry and
are reported as `cleanup_pending`; incomplete deletion/cleanup exits nonzero.
Rerun the same deletion scope after fixing storage to retry physical cleanup. Public
pointers to selected documents remain withdrawn. If discovery rebuilding failed,
repair it explicitly after fixing the reported cause. Private manifest comparison
hashes are retained for the next generation.

## Prune statistics

```bash
python manage.py agentmd_prune_stats --dry-run
python manage.py agentmd_prune_stats
python manage.py agentmd_prune_stats --days 30 --yes
```

`agentmd_prune_stats` deletes [daily agent access counters](agent-access-stats.md)
whose UTC date is older than the retention period: strictly before today's UTC date
minus `--days`, so the cutoff date itself is kept. `--days` defaults to
`STATS_RETENTION_DAYS` (90). Both must be a positive whole number; `0`, negatives,
booleans and strings are rejected before anything is deleted, and the message names
the offending source. The command reports the selected count and cutoff date, then
requires typing `yes` unless `--yes` is supplied; EOF or absent input never implies
consent. An empty selection exits without prompting. `--dry-run` never prompts or
deletes. The summary reports `deleted` and `retained` record counts.

Deletion is one indexed `DELETE` statement on `access_date`; rows are never loaded or
iterated, and no page, export or report state is touched. Pruning is explicit: nothing
schedules it, and the report keeps showing history until it is pruned. Run it from
cron or a scheduled job with `--yes` if retention should be enforced routinely. It does
not need autocommit and can run inside a caller transaction. The runtime-editable
retention setting remains v0.2 (#38); volume benchmarks remain #66.

## Dry runs

`agentmd_generate`, `agentmd_generate_indexes`, `agentmd_delete` and
`agentmd_prune_stats` support `--dry-run`, including combined scope/force/yes flags
where applicable. Dry runs
inspect selection, current policy, ownership and file availability, and report
planned work. They do not invoke rendering, create export records, take publication
locks, delete files, finalise discovery/manifests or enqueue tasks. Deletion dry runs
never prompt. Summary numbers after `Dry run:` describe planned operations.

A generation dry run cannot detect rendering/upload failures or an empty rendered
body; those require execution. As with every command, project policy/path hooks are
expected to obey their read-only inspection contract. No bundle, delta or durable
job state is created by these v0.1 commands.
