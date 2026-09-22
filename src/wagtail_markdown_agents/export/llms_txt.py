"""Concise llms.txt discovery from current managed exports (#21)."""

from django.core.exceptions import ImproperlyConfigured

from ..models import ExportArtifact
from ..public_urls import export_url
from ..settings import get_setting
from .listings import directory_entries, markdown_text, readable_page_entries
from .paths import ExportPathError
from .policy import ExportPolicy
from .state import StaleBuild, site_state
from .writer import FileWriter, _after_commit_required


class LlmsTxtGenerator:
    def __init__(self, writer=None, *, urlconf=None):
        self.writer = writer or FileWriter()
        self.urlconf = urlconf

    def generate(self, site_id):
        """Publish discovery after page/index writes, or return None for a disabled site.

        No content is generated on requests. A concurrent source/publication change
        raises StaleBuild; the caller can schedule a fresh batch from current state.
        """
        _after_commit_required()
        description = get_setting("LLMS_TXT_DESCRIPTION")
        if not isinstance(description, str):
            raise ImproperlyConfigured("LLMS_TXT_DESCRIPTION must be a plain-text string")
        site, baseline = site_state(site_id)
        if not ExportPolicy.site_enabled(site):
            return None
        token = self.writer.begin_site(site_id, f"{site.hostname}/llms.txt")
        if token.source_state != baseline:
            raise StaleBuild("Site content changed before discovery generation")
        parts = ["# " + markdown_text(site.site_name.strip() or site.hostname)]
        if description.strip():
            parts.append("> " + markdown_text(description))

        root_path = f"{site.hostname}/index.md"
        entries = directory_entries(
            readable_page_entries(self.writer, site, urlconf=self.urlconf), root_path
        )
        lines = []
        root_url = self._root_url(site, root_path)
        if root_url:
            lines.append(self._link("Site index", root_url, "Browse available content."))
        lines.extend(self._link(entry.title, entry.url, entry.description) for entry in entries)
        if lines:
            parts.append("## Explore\n\n" + "\n".join(lines))
        else:
            parts.append("No exported pages are available.")
        return self.writer.publish(token, "\n\n".join(parts) + "\n")

    def _root_url(self, site, path):
        record = (
            ExportArtifact.objects.filter(scope__site_id=site.pk, logical_path=path)
            .select_related("scope", "file")
            .first()
        )
        if record is None:
            return None
        try:
            with self.writer.open(path, site_id=site.pk, file_id=record.file_id):
                pass
            return export_url(record, urlconf=self.urlconf)
        except (FileNotFoundError, ExportPathError):
            return None

    @staticmethod
    def _link(title, url, description):
        destination = url.replace("(", "%28").replace(")", "%29")
        line = f"- [{markdown_text(title)}]({destination})"
        if description.strip():
            line += ": " + markdown_text(description)
        return line
