"""Concise llms.txt discovery from current managed exports (#21)."""

from django.core.exceptions import ImproperlyConfigured

from ..models import ExportArtifact
from ..public_urls import export_url
from ..settings import get_setting
from .listings import markdown_text, navigation_entries
from .paths import ExportPathError
from .policy import ExportPolicy
from .state import StaleBuild, site_freshness
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
        fresh = site_freshness(site_id)
        site, baseline = fresh.site, fresh.state
        if not ExportPolicy.site_enabled(site):
            return None
        token = self.writer.begin_site(site_id, f"{site.hostname}/llms.txt")
        if token.source_state != baseline:
            raise StaleBuild("Site content changed before discovery generation")
        parts = ["# " + markdown_text(site.site_name.strip() or site.hostname)]
        if description.strip():
            parts.append("> " + markdown_text(description))

        root_path = f"{site.hostname}/index.md"
        entries = navigation_entries(self.writer, site, root_path, fresh, urlconf=self.urlconf)
        lines = []
        root_url, root_page_id = self._root_url(site, root_path, fresh)
        named = [entry.page_id for entry in entries]
        if root_page_id is not None:
            named.append(root_page_id)  # It links to the home page's index.
        if root_url:
            lines.append(self._link("Site index", root_url, "Browse available content."))
        lines.extend(self._link(entry.title, entry.url, entry.description) for entry in entries)
        if lines:
            parts.append("## Explore\n\n" + "\n".join(lines))
        else:
            parts.append("No exported pages are available.")
        return self.writer.publish(token, "\n\n".join(parts) + "\n", lists=named)

    def _root_url(self, site, path, freshness):
        record = (
            ExportArtifact.objects.filter(scope__site_id=site.pk, logical_path=path)
            .select_related("scope", "file")
            .defer("scope__manifest_state")
            .first()
        )
        if record is None:
            return None, None
        # From database state, as the listing is: no storage request (#69).
        if not self.writer.is_current(record, freshness, own=True):
            return None, None
        try:
            return export_url(record, urlconf=self.urlconf), record.page_id
        except ExportPathError:
            return None, None

    @staticmethod
    def _link(title, url, description):
        destination = url.replace("(", "%28").replace(")", "%29")
        line = f"- [{markdown_text(title)}]({destination})"
        if description.strip():
            line += ": " + markdown_text(description)
        return line
