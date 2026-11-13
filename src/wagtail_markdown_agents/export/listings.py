"""Shared published entries and Markdown escaping for navigation/discovery."""

import re
from dataclasses import dataclass
from html import escape

from wagtail.models import Page

from ..models import ExportArtifact
from ..public_urls import export_url, route_url
from ..rendering.page import PageRenderError, _published_page
from .paths import ExportPathError, site_path
from .state import StaleBuild, site_freshness


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


def current_page_records(writer, site, freshness, *, prefix=""):
    """The site's current page export records, optionally below ``prefix``.

    Currency comes from the database and one reading of the site; no export
    is opened, so listing a large site on remote storage costs no requests
    per export (#69). Serving still opens each file and treats a missing
    object as a miss.
    """
    records = ExportArtifact.objects.filter(
        scope__site_id=site.pk, page_id__isnull=False, logical_path__startswith=prefix
    ).select_related("scope", "file")
    return [record for record in records if writer.is_current(record, freshness, own=True)]


def readable_page_entries(writer, site, *, urlconf=None, freshness=None):
    """Every page export of ``site`` that is current and readable, sorted by title.

    Each export is checked against one reading of the site (``freshness``,
    read here when not given), not a fresh reading per export (#66).
    """
    if freshness is None:
        try:
            freshness = site_freshness(site.pk)
        except StaleBuild:
            return []
    return sort_entries(_entries(current_page_records(writer, site, freshness), urlconf, freshness))


def navigation_entries(writer, site, path, freshness, *, urlconf=None):
    """The entries the index at ``path`` lists, sorted by title.

    Only exports below the index are read, and a page is looked up only when
    it is listed, so rebuilding one index does not read the whole site (#69).
    """
    records = current_page_records(writer, site, freshness, prefix=path.removesuffix("index.md"))
    listed = directory_entries(records, path, key=lambda record: record.logical_path)
    return sort_entries(_entries(listed, urlconf, freshness))


def _entries(records, urlconf, freshness):
    """Listing entries for current page export records.

    Titles and descriptions come from the page rows the site reading already
    loaded: a live page's row is what Wagtail serves, since saving a draft never
    changes it. Looking each page up again cost a query and a revision parse
    per entry, and a blog index lists thousands of posts (#69).
    """
    entries = []
    for record in records:
        page = freshness.snapshot.pages.get(record.page_id)
        try:
            if page is None:
                entries.append(page_entry(record, urlconf=urlconf))
                continue
            # The record was just read and checked, so format its URL from
            # the site already in hand rather than re-reading both (#69).
            site = freshness.site
            site_path(record.logical_path, site.hostname)
            url = route_url(site, record.logical_path[len(site.hostname) + 1 :], urlconf=urlconf)
        except (ExportPathError, PageRenderError):
            continue
        title, description = page.title, page.search_description
        entries.append(IndexEntry(record.page_id, record.logical_path, url, title, description))
    return entries


def page_entry(record, *, urlconf=None):
    """The listing entry for a page export record; may raise ExportPathError or
    PageRenderError when the page or its URL is no longer available."""
    page = _published_page(Page(pk=record.page_id))
    url = export_url(record, urlconf=urlconf)
    return IndexEntry(record.page_id, record.logical_path, url, page.title, page.search_description)


def sort_entries(entries):
    return sorted(entries, key=lambda entry: (entry.title.casefold(), entry.path, entry.page_id))


def directory_entries(entries, path, *, key=lambda entry: entry.path):
    """The entries the index at ``path`` lists: the nearest index above an
    entry lists it. ``key`` gives an item's export path."""
    prefix = path.removesuffix("index.md")
    descendants = [
        entry for entry in entries if key(entry).startswith(prefix) and key(entry) != path
    ]
    indexes = [
        key(entry).removesuffix("index.md")
        for entry in descendants
        if key(entry).endswith("/index.md")
    ]
    # A readable child page index represents its subtree. When absent,
    # promote the available exports, avoiding invented/missing targets.
    return [
        entry
        for entry in descendants
        if not any(
            key(entry).startswith(directory) and key(entry) != directory + "index.md"
            for directory in indexes
        )
    ]
