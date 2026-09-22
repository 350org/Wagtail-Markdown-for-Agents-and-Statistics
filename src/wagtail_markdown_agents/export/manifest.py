"""Per-site v0.1 content manifests from checked, successfully published bytes."""

import hashlib
import json
import re

import yaml
from markdown_it import MarkdownIt

from ..models import ExportArtifact, ExportScope
from ..public_urls import export_url
from ..rendering.frontmatter import normalise
from .policy import ExportPolicy
from .snapshot import SiteSnapshot
from .state import StaleBuild, site_state
from .writer import FileWriter, _after_commit_required

SCHEMA_VERSION = "0.1"
HASH_VERSION = 1


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _document(text):
    """Split exported frontmatter; never re-render or consult draft metadata."""
    metadata, body = {}, text
    if text.startswith("---\n"):
        header, separator, body = text[4:].partition("\n---\n")
        if not separator:
            raise ValueError("Exported Markdown has unclosed frontmatter")
        metadata = normalise(yaml.safe_load(header))
        if not isinstance(metadata, dict):
            raise ValueError("Exported frontmatter must be a mapping")
    return metadata, body


def _word_count(body):
    # Count Unicode words in rendered text/code and image alt text, not URLs or
    # Markdown punctuation. No language-specific segmentation is implied.
    def words(tokens):
        for token in tokens:
            if token.children:
                yield from words(token.children)
            elif token.type in {"text", "code_inline", "code_block", "fence"}:
                yield token.content

    return len(re.findall(r"\w+(?:['’-]\w+)*", " ".join(words(MarkdownIt().parse(body)))))


def _baseline(state):
    if state == {}:
        return {}
    if (
        not isinstance(state, dict)
        or state.get("schema_version") != SCHEMA_VERSION
        or state.get("hash_version") != HASH_VERSION
        or not isinstance(state.get("documents"), dict)
        or any(
            not isinstance(key, str)
            or not key.isdecimal()
            or not isinstance(value, str)
            or re.fullmatch(r"[0-9a-f]{64}", value) is None
            for key, value in state["documents"].items()
        )
    ):
        raise ValueError("Invalid manifest comparison state; restore or explicitly reset it")
    return state["documents"]


class ManifestGenerator:
    def __init__(self, writer=None, *, urlconf=None):
        self.writer = writer or FileWriter()
        self.urlconf = urlconf

    def generate(self, site_id):
        """Finalise the entire site's current page inventory after successful writes.

        Includes unchanged pages from other page/type scopes. Missing or stale
        eligible exports are errors, never deletions. Failed page batches must
        propagate their exception before calling this finaliser (as IndexBatch
        does). No incremental skipping, repair or delta history is performed.
        """
        _after_commit_required()
        site, source_state = site_state(site_id)
        if not ExportPolicy.site_enabled(site):
            return None
        next_state = None

        def update(previous):
            nonlocal next_state
            if site_state(site_id)[1] != source_state:
                raise StaleBuild("Site content changed before manifest generation")
            # The public pointer is normally already withdrawn by page writes.
            # Read the private baseline inside each optimistic update attempt.
            baseline = _baseline(ExportScope.objects.get(site_id=site_id).manifest_state)
            snapshot = SiteSnapshot(site)
            policy = ExportPolicy(snapshot)
            eligible = {
                page.pk
                for page in snapshot.pages.values()
                if page.live_revision_id
                and policy.is_eligible(page)
                and policy.site_for_page(page).pk == site_id
            }
            records = {
                record.page_id: record
                for record in ExportArtifact.objects.filter(
                    scope__site_id=site_id, page_id__isnull=False
                ).select_related("scope", "file")
            }
            documents, errors, comparisons = [], [], {}
            summary = {"new": 0, "modified": 0, "unchanged": 0, "removed": 0, "errors": 0}
            for page_id in sorted(set(records) | {int(key) for key in baseline}):
                key = str(page_id)
                if page_id not in eligible:
                    if key in baseline:
                        summary["removed"] += 1
                    continue
                record = records.get(page_id)
                try:
                    if record is None:
                        raise FileNotFoundError
                    with self.writer.open(
                        record.logical_path, site_id=site_id, file_id=record.file_id
                    ) as stream:
                        text = stream.read().decode("utf-8")
                except FileNotFoundError:
                    errors.append({"id": page_id, "reason": "unavailable_export"})
                    # Keep only the private comparison hash for a later repair.
                    if key in baseline:
                        comparisons[key] = baseline[key]
                    continue
                metadata, body = _document(text)
                metadata.pop("timestamp", None)
                entry = {
                    "id": page_id,
                    "path": record.logical_path,
                    "url": export_url(record, urlconf=self.urlconf),
                    "storage_alias": record.file.storage_alias,
                    "storage_key": record.file.storage_key,
                    "title": metadata.get("title", ""),
                    "type": metadata.get("type", ""),
                    "content_hash": _hash(body),
                    "metadata_hash": _hash(_json(metadata)),
                    "full_hash": _hash(text),
                    "word_count": _word_count(body),
                }
                comparison = _hash(
                    _json(
                        {
                            name: entry[name]
                            for name in ("path", "url", "content_hash", "metadata_hash")
                        }
                    )
                )
                status = (
                    "new"
                    if key not in baseline
                    else ("unchanged" if baseline[key] == comparison else "modified")
                )
                entry["change_status"] = status
                summary[status] += 1
                comparisons[key] = comparison
                documents.append(entry)
            summary["errors"] = len(errors)
            next_state = {
                "schema_version": SCHEMA_VERSION,
                "hash_version": HASH_VERSION,
                "documents": comparisons,
            }
            return (
                json.dumps(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "hash_version": HASH_VERSION,
                        "site_id": site_id,
                        "documents": documents,
                        "summary": summary,
                        "errors": errors,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )

        def commit(scope, record):
            ExportScope.objects.filter(pk=scope.pk).update(manifest_state=next_state)

        return self.writer.update_aggregate(
            site_id, f"{site.hostname}/manifest.json", update, commit=commit
        )
