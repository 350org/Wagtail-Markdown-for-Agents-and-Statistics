"""Routine publication does work bounded by the change, not by the site (#69).

Publishing one page used to withdraw every index, llms.txt and the manifest,
then rebuild them all in the editor's request. On a site with thousands of
pages on remote storage that never finished before the web server's timeout:
the editor saw an error and every index stayed missing. These tests count
work rather than time, so they are stable on any machine.
"""

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection
from wagtail.models import Site

from tests import test_lifecycle
from tests.test_indexes import article, read
from wagtail_markdown_agents.export.indexes import IndexBatch
from wagtail_markdown_agents.export.lifecycle import request_refresh
from wagtail_markdown_agents.export.snapshot import SiteSnapshot
from wagtail_markdown_agents.export.writer import FileWriter
from wagtail_markdown_agents.models import ExportArtifact

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.export_lifecycle]
setup = test_lifecycle.setup

DISCOVERY = ("example.org/llms.txt", "example.org/manifest.json")


@pytest.fixture
def quiet(settings):
    """Build a site without lifecycle refreshes, then finalise it once."""

    def build(home, sections, leaves, *, prefix="section"):
        config = settings.WAGTAIL_MARKDOWN_AGENTS
        settings.WAGTAIL_MARKDOWN_AGENTS = {**config, "AUTO_GENERATE": False}
        writer = FileWriter()
        built = []
        for number in range(sections):
            section = article(home, f"{prefix}-{number}")
            pages = [article(section, f"{prefix}{number}-leaf-{leaf}") for leaf in range(leaves)]
            built.append((section, pages))
        batch = IndexBatch(writer)
        for page in [home] + [page for section, pages in built for page in (section, *pages)]:
            batch.generate(page)
        batch.finalise()
        settings.WAGTAIL_MARKDOWN_AGENTS = config
        return built

    return build


def measure(monkeypatch, action):
    """Run ``action``, counting queries, export opens, site scans and publications."""
    counts = {"queries": 0, "opens": 0, "site_scans": 0, "published": []}

    def count_query(execute, sql, params, many, context):
        counts["queries"] += 1
        return execute(sql, params, many, context)

    original_open = FileWriter._open_file
    original_snapshot = SiteSnapshot.__init__
    original_publish = FileWriter.publish

    def open_file(self, file):
        counts["opens"] += 1
        return original_open(self, file)

    def snapshot(self, site):
        counts["site_scans"] += 1
        original_snapshot(self, site)

    def publish(self, token, markdown, **kwargs):
        counts["published"].append(token.path)
        return original_publish(self, token, markdown, **kwargs)

    monkeypatch.setattr(FileWriter, "_open_file", open_file)
    monkeypatch.setattr(SiteSnapshot, "__init__", snapshot)
    monkeypatch.setattr(FileWriter, "publish", publish)
    with connection.execute_wrapper(count_query):
        action()
    monkeypatch.undo()
    return counts


def files(paths):
    return dict(
        ExportArtifact.objects.filter(logical_path__in=paths).values_list("logical_path", "file_id")
    )


def republish(page, title):
    page.refresh_from_db()
    page.title = title
    page.save_revision().publish()


def test_publishing_a_leaf_rewrites_only_that_page(setup, quiet, monkeypatch):
    writer, site, home = setup
    built = quiet(home, sections=3, leaves=3)
    leaf = built[0][1][0]
    kept = (*DISCOVERY, "example.org/index.md", "example.org/section-1/index.md")
    before = files(kept)
    assert set(before) == set(kept)
    counts = measure(monkeypatch, lambda: republish(leaf, "Renamed leaf"))
    assert counts["published"] == ["example.org/section-0/section0-leaf-0.md"]
    # No other export is opened and the site is never read as a whole.
    assert counts["opens"] == 0, counts
    assert counts["site_scans"] == 0, counts
    assert "Renamed leaf" in read(writer, "example.org/section-0/section0-leaf-0.md")
    # The indexes and discovery files keep their last build and stay served.
    assert files(kept) == before
    for path in kept:
        assert writer.exists(path), path


def test_leaf_publication_work_does_not_grow_with_the_site(setup, quiet, monkeypatch):
    writer, site, home = setup
    built = quiet(home, sections=2, leaves=2)
    leaf = built[0][1][0]
    small = measure(monkeypatch, lambda: republish(leaf, "Small site"))["queries"]
    quiet(home, sections=6, leaves=4, prefix="more")
    large = measure(monkeypatch, lambda: republish(leaf, "Large site"))["queries"]
    # Six times the pages; the publication's own queries stay the same.
    assert large <= small + 5, (small, large)


def test_publishing_a_section_rebuilds_only_its_own_index(setup, quiet, monkeypatch):
    writer, site, home = setup
    built = quiet(home, sections=3, leaves=3)
    section = built[0][0]
    others = files((*DISCOVERY, "example.org/index.md", "example.org/section-1/index.md"))
    counts = measure(monkeypatch, lambda: republish(section, "Renamed section"))
    assert counts["published"] == ["example.org/section-0/index.md"]
    assert counts["opens"] == 0, counts
    # One reading for the navigation and one when it is committed.
    assert counts["site_scans"] <= 2, counts
    output = read(writer, "example.org/section-0/index.md")
    assert "Renamed section" in output and "## Pages (3)" in output
    assert files(others) == others


def test_publishing_the_home_page_reads_no_other_export(setup, quiet, monkeypatch):
    writer, site, home = setup
    quiet(home, sections=3, leaves=3)
    counts = measure(monkeypatch, lambda: republish(home, "New home"))
    assert counts["published"] == ["example.org/index.md"]
    assert counts["opens"] == 0, counts
    assert counts["site_scans"] <= 2, counts
    output = read(writer)
    assert "New home" in output and "## Pages (3)" in output


def test_a_new_page_is_listed_after_the_next_finalise(setup, quiet):
    writer, site, home = setup
    built = quiet(home, sections=1, leaves=1)
    section = built[0][0]
    article(section, "fresh", title="Fresh page")
    assert "Fresh page" in read(writer, "example.org/section-0/fresh.md")
    assert "Fresh page" not in read(writer, "example.org/section-0/index.md")
    batch = IndexBatch(writer)
    batch.mark_dirty(site.pk)
    batch.finalise()
    assert "Fresh page" in read(writer, "example.org/section-0/index.md")
    manifest = json.loads(read(writer, "example.org/manifest.json"))
    assert "Fresh page" in {entry["title"] for entry in manifest["documents"]}


def test_a_parent_gaining_its_first_child_becomes_an_index(setup, quiet):
    writer, site, home = setup
    built = quiet(home, sections=1, leaves=1)
    leaf = built[0][1][0]
    assert writer.exists("example.org/section-0/section0-leaf-0.md")
    article(leaf, "grandchild")
    assert writer.exists("example.org/section-0/section0-leaf-0/grandchild.md")
    assert not writer.exists("example.org/section-0/section0-leaf-0.md")
    output = read(writer, "example.org/section-0/section0-leaf-0/index.md")
    assert "Grandchild" in output


def test_unpublishing_withdraws_discovery_and_rebuilds_only_listing_indexes(
    setup, quiet, monkeypatch
):
    writer, site, home = setup
    built = quiet(home, sections=3, leaves=3)
    leaf = built[0][1][0]
    sibling = files(("example.org/section-1/index.md",))
    counts = measure(monkeypatch, lambda: leaf.unpublish())
    assert not writer.exists("example.org/section-0/section0-leaf-0.md")
    # The discovery files could name the page, so they wait for a finalise.
    for path in DISCOVERY:
        assert not writer.exists(path), path
    # Only the indexes above the page are rebuilt, without it.
    assert sorted(counts["published"]) == [
        "example.org/index.md",
        "example.org/section-0/index.md",
    ]
    assert counts["opens"] == 0, counts
    assert "Section0-Leaf-0" not in read(writer, "example.org/section-0/index.md")
    assert files(("example.org/section-1/index.md",)) == sibling
    assert writer.exists("example.org/section-1/index.md")


def test_a_change_without_signals_hides_navigation_until_rebuilt(setup, quiet, settings):
    writer, site, home = setup
    built = quiet(home, sections=1, leaves=1)
    leaf = built[0][1][0]
    # A bulk update sends no lifecycle signal, so nothing withdraws the files.
    type(leaf).objects.filter(pk=leaf.pk).update(live=False)
    for path in (*DISCOVERY, "example.org/index.md", "example.org/section-0/index.md"):
        assert not writer.exists(path), path
    Site.clear_site_root_paths_cache()


def test_index_rebuild_queries_do_not_grow_with_the_pages_it_lists(setup, quiet, monkeypatch):
    writer, site, home = setup
    small = quiet(home, sections=1, leaves=2)[0][0]
    large = quiet(home, sections=1, leaves=12, prefix="blog")[0][0]
    few = measure(monkeypatch, lambda: republish(small, "Few pages"))
    many = measure(monkeypatch, lambda: republish(large, "Many pages"))
    assert "## Pages (12)" in read(writer, "example.org/blog-0/index.md")
    # Six times the listed pages: entries come from the page rows the site
    # reading already loaded, not a lookup per page.
    assert many["queries"] <= few["queries"] + 5, (few["queries"], many["queries"])


def test_a_moved_section_lists_its_pages_at_their_new_paths(setup, quiet):
    writer, site, home = setup
    built = quiet(home, sections=2, leaves=2)
    section, destination = built[0][0], built[1][0]
    section.refresh_from_db()
    section.move(destination, pos="last-child")
    path = "example.org/section-1/section-0/index.md"
    output = read(writer, path)
    assert "## Pages (2)" in output
    assert "/markdown/section-1/section-0/section0-leaf-0.md" in output


def generate(*args):
    output = StringIO()
    call_command("agentmd_generate", "--site", "example.org", *args, stdout=output)
    return output.getvalue()


def test_generate_without_force_catches_navigation_up(setup, quiet):
    writer, site, home = setup
    built = quiet(home, sections=1, leaves=1)
    article(built[0][0], "fresh", title="Fresh page")
    assert "Fresh page" not in read(writer, "example.org/llms.txt")
    output = generate()
    # Every page is current, so none is rendered again, but the navigation is
    # behind the new page's export and is rebuilt.
    assert "generated=0" in output and "discovery_scopes=1" in output, output
    assert "Fresh page" in read(writer, "example.org/section-0/index.md")
    manifest = json.loads(read(writer, "example.org/manifest.json"))
    assert "Fresh page" in {entry["title"] for entry in manifest["documents"]}
    # A second run finds nothing to do.
    assert "discovery_scopes=0" in generate()


def test_requested_refresh_rebuilds_older_exports_without_force(setup, quiet):
    writer, site, home = setup
    quiet(home, sections=1, leaves=2)
    exported = ExportArtifact.objects.filter(page_id__isnull=False).count()
    request_refresh([site.pk])
    status = StringIO()
    call_command("agentmd_status", "--site", "example.org", stdout=status)
    assert f"outdated={exported}" in status.getvalue()
    # The current exports stay served until the run.
    assert writer.exists("example.org/section-0/section0-leaf-0.md")
    output = generate()
    assert f"generated={exported}" in output, output
    assert "generated=0" in generate()
