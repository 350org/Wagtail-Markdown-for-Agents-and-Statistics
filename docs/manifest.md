# Content-hash manifest

`ManifestGenerator` (#22) publishes a per-site `manifest.json` through the managed
writer. It describes **successfully published, currently readable page documents**,
including page-owned root/directory indexes. Synthetic navigation indexes and
`llms.txt` are discovery artefacts, without page identities; they are not documents
in this manifest. The manifest never includes itself.

```python
from wagtail_markdown_agents.export.indexes import IndexBatch
from wagtail_markdown_agents.export.manifest import ManifestGenerator

# Run after the CMS transaction commits.
with IndexBatch() as batch:
    batch.generate(page)
# Indexes, llms.txt, then manifest.json are finalised once per dirty site.

# For callers that have already completed their page/index writes:
ManifestGenerator().generate(site.pk)
```

Include the package's [public routes](public-export-routes.md) to serve the file.
With the sandbox URLconf it is `/markdown/manifest.json`, with
`application/json; charset=utf-8`, GET/HEAD and the existing publication/serving
guards. `urlconf=` supports custom route configurations. Disabled sites return
`None`; requests never generate files. The [publish lifecycle](publish-lifecycle.md)
finalises manifests automatically after publish and repairs discovery after unpublish/delete. Commands and
restriction/move receivers remain #24/#69/#70.

## v0.1 schema

The top-level object contains `schema_version: "0.1"`, `hash_version: 1`, `site_id`,
`documents`, `summary` and `errors`. Documents are ordered by numeric page ID.
Each document has:

| Field | Meaning |
| --- | --- |
| `id` | Native stable Wagtail page ID, from ownership, even if a frontmatter hook overrides `id` |
| `path` | Actual owned logical path, including the hostname and any export-path hook relocation |
| `url` | Absolute checked public export URL, derived from the site's origin and included URLconf |
| `storage_alias`, `storage_key` | Recorded backend alias and actual immutable saved key, including backend renaming; these are identities, not download URLs |
| `title`, `type` | Values from the exported frontmatter, including hooks, never from a newer draft; empty strings if omitted |
| `content_hash` | SHA-256 of the UTF-8 Markdown body after the closing frontmatter delimiter, preserving whitespace, links, images and navigation |
| `metadata_hash` | SHA-256 of the exported frontmatter mapping as canonical JSON, excluding only the top-level generation `timestamp` |
| `full_hash` | SHA-256 of the complete exact UTF-8 file, including frontmatter and generation timestamp |
| `word_count` | Unicode word runs in Markdown text, code and image alt text; excludes link destinations and Markdown punctuation |
| `change_status` | `new`, `modified` or `unchanged`, compared with the last successful manifest publication |

Canonical metadata JSON uses sorted keys recursively, unescaped Unicode and compact
separators (`ensure_ascii=False, sort_keys=True, separators=(",", ":")`). Parsed YAML
values use the frontmatter normaliser before JSON encoding. Mapping order and YAML
presentation do not change the metadata hash; all metadata values other than the
reserved generation timestamp do. Publication `date` and `modified` remain included.
`hash_version` versions these hashing rules; it is not a fingerprint of project
configuration. Configuration changes that alter rebuilt output affect the hashes.
General configuration-fingerprint and stale-scope tooling remains #75.

An unchanged rebuild usually has a new storage key and may have a new `full_hash`
because of its generation timestamp. `change_status` compares content/metadata
hashes, logical path and public URL, excluding the raw checksum and physical object
identity. A move is `modified` on the same page ID. `full_hash` always allows clients
to verify the downloaded bytes independently of semantic change detection.

## Comparison state, failures and scope

Every finalisation reads the entire site's current managed page inventory. A
page/type-scoped caller does not discard other scopes or unchanged documents.
Unexported CMS pages are not inferred to be successful exports.

`summary` counts `new`, `modified`, `unchanged`, `removed` and `errors`. Removal
means a previously manifested page no longer has an eligible published revision
in this site (including deletion, restriction, exclusion or a move to another
site). Only the count is published: no old titles, paths or deletion tombstones
remain. Delta records and incremental CLI/hash skipping belong to #41.

An eligible page with missing/stale/unreadable managed ownership or a missing
storage object is omitted from `documents` and reported as
`{"id": 123, "reason": "unavailable_export"}` in `errors`. It is neither an
unchanged success nor a removal. Its private comparison hash survives so a later
successful repair can be compared correctly. This also applies when an eligible
page's export was explicitly withdrawn: rebuild it, or make it ineligible to remove
it from the corpus. Other storage errors and malformed exported frontmatter raise;
they never produce a successful manifest entry. Missing-file repair itself remains
a caller's job. Newly attempted writes that never published cannot be discovered
from storage ownership; callers must propagate generation failures.

`IndexBatch` finalises only after a successful context-manager body. A page failure
leaves any earlier page writes committed, the old manifest withdrawn and the site
dirty for an explicit retry. Manifest upload failure leaves comparison state intact;
an existing current manifest remains available if its source state is still valid.
Callers using direct generation must finish/retry their failed page work before
finalising, rather than interpreting an older successful export as that attempt's
success.

`ExportScope.manifest_state` stores only page IDs and opaque comparison hashes,
plus schema/hash versions. It survives public aggregate withdrawal and contains no
old titles, paths or storage keys. The writer's database-only `commit(scope, record)`
callback advances it in the same locked transaction as the manifest pointer. Failed
uploads, rejected stale builds and failed commits never advance the baseline.
Competing aggregate writes retry through `update_aggregate`; a concurrent page
publication or eligibility change aborts. Storage IO remains outside the site lock.
Revocation withdraws the public manifest immediately through the existing writer;
policy guards reject stale metadata even before lifecycle cleanup runs.

A fresh empty baseline produces `new` entries. A missing public manifest can be
rebuilt using the private baseline. Invalid/incompatible comparison state raises
`ValueError`; it is not silently treated as a first export. Restore the private
state from a valid backup, or explicitly reset that site's `manifest_state` to `{}`
if accepting a fresh comparison baseline. There is no public-manifest history or
migration between hash versions in v0.1. Apply the package migration before use.
