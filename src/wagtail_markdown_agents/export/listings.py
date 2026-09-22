"""Shared published entries and Markdown escaping for navigation/discovery."""

import re
from dataclasses import dataclass
from html import escape

from wagtail.models import Page

from ..models import ExportArtifact
from ..public_urls import export_url
from ..rendering.page import PageRenderError, _published_page
from .paths import ExportPathError


@dataclass(frozen=True)
class IndexEntry:
    page_id: int
    path: str
    url: str
    title: str
    description: str


def markdown_text(value):
    text = re.sub(r"([\\`*_\[\]~|#])", r"\\\1", " ".join(value.split()))
    return escape(text, quote=False)


def readable_page_entries(writer, site, *, urlconf=None):
    entries = []
    records = ExportArtifact.objects.filter(
        scope__site_id=site.pk, page_id__isnull=False
    ).select_related("scope", "file")
    for record in records:
        try:
            # Binding the exact file avoids mixing a replacement's bytes
            # with the old record's path or published-page metadata.
            with writer.open(record.logical_path, site_id=site.pk, file_id=record.file_id):
                pass
            page = _published_page(Page(pk=record.page_id))
            url = export_url(record, urlconf=urlconf)
        except (FileNotFoundError, ExportPathError, PageRenderError):
            continue
        entries.append(
            IndexEntry(
                record.page_id, record.logical_path, url, page.title, page.search_description
            )
        )
    return sorted(entries, key=lambda entry: (entry.title.casefold(), entry.path, entry.page_id))


def directory_entries(entries, path):
    prefix = path.removesuffix("index.md")
    descendants = [
        entry for entry in entries if entry.path.startswith(prefix) and entry.path != path
    ]
    indexes = [
        entry.path.removesuffix("index.md")
        for entry in descendants
        if entry.path.endswith("/index.md")
    ]
    # A readable child page index represents its subtree. When absent,
    # promote the available exports, avoiding invented/missing targets.
    return [
        entry
        for entry in descendants
        if not any(
            entry.path.startswith(directory) and entry.path != directory + "index.md"
            for directory in indexes
        )
    ]
