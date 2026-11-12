"""Index finalisation grows linearly with the number of exported pages (#66).

Finalising once listed every export for each index it built, and each listing
recomputed the whole site's state for every page-owned index. A site with
thousands of pages and hundreds of sections never finished. These tests count
work rather than time, so they are stable on any machine.
"""

import pytest
from django.db import connection

from tests import test_indexes
from tests.test_indexes import article
from wagtail_markdown_agents.export.indexes import IndexBatch, IndexGenerator
from wagtail_markdown_agents.export.snapshot import SiteSnapshot
from wagtail_markdown_agents.export.state import StaleBuild
from wagtail_markdown_agents.export.writer import FileWriter

pytestmark = pytest.mark.django_db(transaction=True)
setup = test_indexes.setup


def build(writer, home, sections, leaves):
    for number in range(sections):
        section = article(home, f"section-{number}")
        for leaf in range(leaves):
            writer.generate(article(section, f"s{number}-leaf-{leaf}"))


def measure(writer, site, monkeypatch):
    """Finalise the site, counting queries, storage opens and whole-site scans."""
    counts = {"queries": 0, "opens": 0, "site_scans": 0}

    def count_query(execute, sql, params, many, context):
        counts["queries"] += 1
        return execute(sql, params, many, context)

    original_open = FileWriter._open_file
    original_snapshot = SiteSnapshot.__init__

    def open_file(self, file):
        counts["opens"] += 1
        return original_open(self, file)

    def snapshot(self, site):
        # Every reading of a site's state (site_state, site_freshness) builds one.
        counts["site_scans"] += 1
        original_snapshot(self, site)

    monkeypatch.setattr(FileWriter, "_open_file", open_file)
    monkeypatch.setattr(SiteSnapshot, "__init__", snapshot)
    batch = IndexBatch(writer)
    batch.mark_dirty(site.pk)
    with connection.execute_wrapper(count_query):
        batch.finalise()
    monkeypatch.undo()
    return counts


@pytest.mark.parametrize("setup", ["filesystem"], indirect=True)
def test_finalise_reads_each_export_a_bounded_number_of_times(setup, monkeypatch):
    writer, site, home = setup
    build(writer, home, sections=6, leaves=2)
    exports = 1 + 6 + 6 * 2
    counts = measure(writer, site, monkeypatch)
    # One listing for the indexes, one for llms.txt and one for the manifest,
    # plus the few indexes and discovery files read back. Before #66 every
    # index and directory listed every export again.
    assert counts["opens"] <= 4 * exports, counts


@pytest.mark.parametrize("setup", ["filesystem"], indirect=True)
def test_site_scans_do_not_grow_with_listed_exports(setup, monkeypatch):
    writer, site, home = setup
    build(writer, home, sections=6, leaves=2)
    indexes = 1 + 6
    counts = measure(writer, site, monkeypatch)
    # The writer checks the site's state once when each index is committed;
    # the rest is a fixed cost per finalise (baseline, cleanup, one listing,
    # the root, llms.txt and the manifest). Before #66, listing exports added
    # a scan per page-owned index for every index built.
    assert counts["site_scans"] <= indexes + 14, counts


@pytest.mark.parametrize("setup", ["filesystem"], indirect=True)
def test_finalise_queries_grow_linearly_with_pages(setup, monkeypatch):
    writer, site, home = setup
    build(writer, home, sections=3, leaves=3)
    small = measure(writer, site, monkeypatch)["queries"]
    build_more = [article(home, f"more-{number}") for number in range(6)]
    for number, section in enumerate(build_more):
        for leaf in range(3):
            writer.generate(article(section, f"m{number}-leaf-{leaf}"))
    large = measure(writer, site, monkeypatch)["queries"]
    # Three times the sections and pages: linear work about triples, quadratic
    # work grows about ninefold.
    assert large <= 4 * small, (small, large)


@pytest.mark.parametrize("setup", ["filesystem"], indirect=True)
def test_export_republished_after_listing_aborts_the_index_build(setup, monkeypatch):
    writer, site, home = setup
    section = article(home, "section")
    leaf = article(section, "leaf")
    writer.generate(leaf)
    original_begin = FileWriter.begin
    calls = []

    def begin(self, page, **kwargs):
        if not calls:
            # Another process republishes the leaf after the exports were
            # listed. The site's state is unchanged, so only the scope's
            # content version shows the listing is out of date.
            calls.append(original_begin(self, leaf))
            self.publish(calls[0], "# Leaf\n\nRepublished.\n")
        return original_begin(self, page, **kwargs)

    monkeypatch.setattr(FileWriter, "begin", begin)
    with pytest.raises(StaleBuild, match="listed exports"):
        IndexGenerator(writer).generate(site.pk)
    assert not writer.exists("example.org/section/index.md")
