"""Managed root/directory navigation and explicit batch finalisation (#20)."""

from pathlib import PurePosixPath

from django.db.models import Q
from wagtail import hooks
from wagtail.models import Page

from .. import OKF_VERSION
from ..models import ExportArtifact
from ..rendering import frontmatter, render_page
from ..rendering.page import PageRenderError, _published_page
from .listings import IndexEntry as IndexEntry
from .listings import directory_entries, markdown_text, readable_page_entries
from .llms_txt import LlmsTxtGenerator
from .manifest import ManifestGenerator
from .policy import ExportPolicy
from .snapshot import SiteSnapshot
from .state import StaleBuild, site_state
from .writer import FileWriter, _after_commit_required

INDEX_CONTENT_HOOK = "markdown_index_content"


class IndexGenerator:
    def __init__(self, writer=None, *, urlconf=None):
        self.writer = writer or FileWriter()
        self.urlconf = urlconf

    def generate(self, site_id, *, page_ids=(), exclude_page_ids=()):
        """Rebuild page indexes, then standalone directory indexes, after commit.

        Leaf exports must already exist. ``page_ids`` supplies former index owners
        whose pointers were withdrawn by lifecycle cleanup, so they can become
        leaves again. IndexBatch captures these IDs before its writes/deletions.
        Unsupported page types never become partial page exports.
        ``exclude_page_ids`` prevents an explicit deletion's discovery repair
        from recreating the selected page documents in this batch.
        A concurrent source change aborts; callers may schedule a fresh batch.
        """
        _after_commit_required()
        site, baseline = site_state(site_id)
        if not ExportPolicy.site_enabled(site):
            return []
        previous = dict(
            ExportArtifact.objects.filter(
                scope__site_id=site_id, page_id__isnull=False
            ).values_list("page_id", "logical_path")
        )
        self.writer.delete_stale(site_id)
        snapshot = SiteSnapshot(site)
        policy = ExportPolicy(snapshot)
        requested = set(page_ids)
        excluded = set(exclude_page_ids)
        candidates = []
        for page in snapshot.pages.values():
            if page.pk in excluded or not page.live_revision_id or not policy.is_eligible(page):
                continue
            owner = policy.site_for_page(page)
            if owner is None or owner.pk != site_id:
                continue
            path = policy.relative_path(page)
            old_path = previous.get(page.pk)
            if (
                path.endswith("/index.md")
                or page.pk in requested
                or (old_path is not None and old_path != path)
            ):
                candidates.append((path, page))
        # Children must be readable before their parent lists them. Relocated
        # paths follow the export directory tree, not HTML pagination or URLs.
        candidates.sort(
            key=lambda item: (
                item[0].endswith("/index.md"),
                -item[0].count("/"),
                item[0],
                item[1].pk,
            )
        )
        for path, page in candidates:
            token = self.writer.begin(page, depends_on_site=True)
            self._check_state(token.dependency_state, baseline)
            navigation = ""
            if path.endswith("/index.md"):
                navigation, _ = self._navigation(site, path, _published_page(page))
            try:
                content = render_page(
                    page,
                    site=site,
                    navigation=navigation,
                    root_index=path == f"{site.hostname}/index.md",
                )
            except PageRenderError as exc:
                if exc.reason not in {"unsupported_page", "empty_body"}:
                    raise
                continue
            self.writer.publish(token, content, replace_index=path.endswith("/index.md"))

        # Every synthetic directory is derived from a readable owned page path.
        # Never derive a title or excerpt from an unexported/private ancestor.
        entries = readable_page_entries(self.writer, site, urlconf=self.urlconf)
        directories = self._directories(site, entries)
        for directory in sorted(directories, key=lambda path: (-path.count("/"), path)):
            path = f"{directory}/index.md"
            if ExportArtifact.objects.filter(
                scope__site_id=site_id, logical_path=path, page_id__isnull=False
            ).exists():
                continue  # A page's complete document owns this slot.
            token = self.writer.begin_site(site_id, path)
            self._check_state(token.source_state, baseline)
            navigation, count = self._navigation(site, path, None)
            metadata = {"title": "Markdown exports", "count": count}
            if directory == site.hostname:
                metadata["okf_version"] = OKF_VERSION
            content = frontmatter.serialise(metadata) + "\n# Markdown exports\n"
            if navigation:
                content += "\n" + navigation.rstrip("\n") + "\n"
            self.writer.publish(token, content)
        token = self.writer.begin_site(site_id, f"{site.hostname}/index.md")
        self._check_state(token.source_state, baseline)
        directories = self._directories(
            site, readable_page_entries(self.writer, site, urlconf=self.urlconf)
        )
        self.writer.prune_indexes(token, {f"{directory}/index.md" for directory in directories})
        return list(
            ExportArtifact.objects.filter(
                scope__site_id=site_id, logical_path__endswith="/index.md"
            ).order_by("logical_path")
        )

    @staticmethod
    def _check_state(current, baseline):
        if current != baseline:
            raise StaleBuild("Site content changed during index finalisation")

    @staticmethod
    def _directories(site, entries):
        directories = {site.hostname}
        for entry in entries:
            parent = PurePosixPath(entry.path).parent
            while str(parent) != site.hostname:
                directories.add(str(parent))
                parent = parent.parent
        return directories

    def _navigation(self, site, path, page):
        entries = tuple(
            directory_entries(readable_page_entries(self.writer, site, urlconf=self.urlconf), path)
        )
        content = f"## Pages ({len(entries)})\n\n"
        if entries:
            lines = []
            for entry in entries:
                destination = entry.url.replace("(", "%28").replace(")", "%29")
                line = f"- [{markdown_text(entry.title)}]({destination})"
                if entry.description:
                    line += " - " + markdown_text(entry.description)
                lines.append(line)
            content += "\n".join(lines)
        else:
            content += "No exported pages are available."
        relative = path[len(site.hostname) + 1 :]
        context = {
            "site": site,
            "page": page,
            "path": relative,
            "entries": entries,
            "count": len(entries),
        }
        for hook in hooks.get_hooks(INDEX_CONTENT_HOOK):
            result = hook(content, relative, context)
            if result is not None:
                if not isinstance(result, str):
                    raise TypeError(f"{INDEX_CONTENT_HOOK} must return a Markdown string or None")
                content = result
        return content, len(entries)


class IndexBatch:
    """Coalesce indexes, llms.txt and manifest after explicit page operations.

    Use after the CMS transaction commits. Revocation runs immediately; context
    manager exit finalises only on success. Failed sites remain dirty for an
    explicit retry. An empty finalise call does no work.
    """

    def __init__(self, writer=None, *, urlconf=None):
        self.writer = writer or FileWriter()
        self.generator = IndexGenerator(self.writer, urlconf=urlconf)
        self.discovery = LlmsTxtGenerator(self.writer, urlconf=urlconf)
        self.manifest = ManifestGenerator(self.writer, urlconf=urlconf)
        self.dirty = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None:
            self.finalise()

    def mark_dirty(self, site_id, *, page_ids=()):
        owners = self.dirty.setdefault(site_id, set())
        owners.update(page_ids)
        owners.update(
            ExportArtifact.objects.filter(
                scope__site_id=site_id,
                page_id__isnull=False,
            )
            .filter(Q(logical_path__endswith="/index.md") | ~Q(dependency_state=""))
            .values_list("page_id", flat=True)
        )

    def generate(self, page):
        current = Page.objects.get(pk=page.pk).specific
        site = current.get_site()
        if site is None:
            raise StaleBuild(f"Page {current.pk} has no site")
        self.mark_dirty(site.pk)
        return self.writer.generate(current)

    def delete_page(self, page_id, *, site_id):
        self.mark_dirty(site_id)
        self.writer.delete_page(page_id, site_id=site_id)

    def finalise(self, *, exclude_page_ids=()):
        exclude_page_ids = tuple(exclude_page_ids)
        results = []
        for site_id in sorted(self.dirty):
            results.extend(
                self.generator.generate(
                    site_id, page_ids=self.dirty[site_id], exclude_page_ids=exclude_page_ids
                )
            )
            discovery = self.discovery.generate(site_id)
            if discovery is not None:
                results.append(discovery)
            manifest = self.manifest.generate(site_id)
            if manifest is not None:
                results.append(manifest)
            del self.dirty[site_id]
        return results
