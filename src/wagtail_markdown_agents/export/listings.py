"""Shared published entries and Markdown escaping for navigation/discovery."""

import re
from dataclasses import dataclass
from html import escape

from django.apps import apps
from wagtail.models import Page

from ..models import ExportArtifact
from ..public_urls import export_url, route_url
from ..rendering.page import PageRenderError, _published_page
from ..settings import get_setting
from .paths import ExportPathError, site_path
from .snapshot import _chunks
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
    # The scope's manifest_state holds an entry per page: decoding it for each
    # record made every listing quadratic in the size of the site (#69).
    records = (
        ExportArtifact.objects.filter(
            scope__site_id=site.pk, page_id__isnull=False, logical_path__startswith=prefix
        )
        .select_related("scope", "file")
        .defer("scope__manifest_state")
    )
    # The reading already holds each current page's export path and state, so
    # compare with those rather than digesting every page a second time.
    return [
        record
        for record in records
        if freshness.pages.get(record.page_id) == (record.logical_path, record.source_state)
    ]


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


def named_navigation_entries(site, path, *, extra=(), urlconf=None):
    """``(entries, freshness, page_ids)`` for the index at ``path``, reading
    only the pages it lists.

    Routine publication rebuilds an index inside the editor's request, so it
    must not read the whole site (#90). Which exports the index lists follows
    from their paths alone; only those pages, plus ``extra``, are read
    (``site_freshness(site, page_ids)``), and the reading checks each one is
    current. An index that is not current hides nothing, so the pages below
    it are listed in its place, as a whole-site listing would list them.
    The returned reading covers ``page_ids``: the listed pages and ``extra``.
    """
    rows = list(
        ExportArtifact.objects.filter(
            scope__site_id=site.pk,
            page_id__isnull=False,
            logical_path__startswith=path.removesuffix("index.md"),
        ).values_list("pk", "page_id", "logical_path", "source_state")
    )
    stale = set()
    while True:
        listed = directory_entries(
            [row for row in rows if row[0] not in stale], path, key=lambda row: row[2]
        )
        page_ids = sorted({row[1] for row in listed} | set(extra))
        freshness = site_freshness(site.pk, page_ids)
        outdated = {row[0] for row in listed if freshness.pages.get(row[1]) != (row[2], row[3])}
        if not outdated:
            break
        stale |= outdated
    records = []
    for chunk in _chunks([row[0] for row in listed]):
        records.extend(
            ExportArtifact.objects.filter(pk__in=chunk)
            .select_related("scope", "file")
            .defer("scope__manifest_state")
        )
    return sort_entries(_entries(records, urlconf, freshness)), freshness, page_ids


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
    indexes = {
        key(entry).removesuffix("index.md")
        for entry in descendants
        if key(entry).endswith("/index.md")
    }

    # A readable child page index represents its subtree. When absent,
    # promote the available exports, avoiding invented/missing targets.
    # Each entry checks only its own directories, so a site's root index
    # costs the number of exports, not exports times indexes (#90).
    def hidden(entry_path):
        own = entry_path.removesuffix("index.md") if entry_path.endswith("/index.md") else None
        directory = prefix
        for part in entry_path[len(prefix) :].split("/")[:-1]:
            directory += part + "/"
            if directory in indexes and directory != own:
                return True
        return False

    return [entry for entry in descendants if not hidden(key(entry))]


def newest_entries(entries, limit):
    """The newest ``limit`` of ``entries``, newest first, when there are more (#76).

    A list within the limit is returned unchanged. "Newest" is the date that
    ``LISTING_DATE_FIELDS`` names for the page's type (a site's own publication
    date), else Wagtail's ``first_published_at``. Dates are read in bulk, one
    query per configured type, so a blog index does not query each post.
    """
    entries = list(entries)
    if limit is None or len(entries) <= limit:
        return entries
    dates = listing_dates([entry.page_id for entry in entries])

    def newest(entry):
        date = dates.get(entry.page_id)
        return (date is not None, date or 0, entry.page_id)

    return sorted(entries, key=newest, reverse=True)[:limit]


def listing_dates(page_ids):
    """``{page_id: date}`` for ordering listings; pages without a date are left out."""
    dates = {}
    for chunk in _chunks(set(page_ids)):
        dates.update(
            Page.objects.filter(pk__in=chunk, first_published_at__isnull=False).values_list(
                "pk", "first_published_at"
            )
        )
    for label, field in (get_setting("LISTING_DATE_FIELDS") or {}).items():
        model = apps.get_model(label)
        for chunk in _chunks(set(page_ids)):
            dates.update(
                (pk, value)
                for pk, value in model.objects.filter(pk__in=chunk).values_list("pk", field)
                if value is not None
            )
    return dates
