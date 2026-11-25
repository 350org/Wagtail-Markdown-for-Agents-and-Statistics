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
from wagtail.models import PageViewRestriction, Site

from tests import test_lifecycle
from tests.test_indexes import article, read
from tests.test_page_rendering import split_document
from wagtail_markdown_agents.export.indexes import IndexBatch, IndexGenerator
from wagtail_markdown_agents.export.lifecycle import request_refresh
from wagtail_markdown_agents.export.snapshot import SiteSnapshot
from wagtail_markdown_agents.export.state import StaleBuild
from wagtail_markdown_agents.export.writer import FileWriter
from wagtail_markdown_agents.models import ExportArtifact, ExportScope

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
    """Run ``action``, counting queries, export opens, site readings and publications.

    ``site_scans`` counts readings of the whole site; ``named_scans`` readings
    of only some pages (``site_freshness(site, page_ids)``), whose cost follows
    the pages named, not the site (#90).
    """
    counts = {"queries": 0, "opens": 0, "site_scans": 0, "named_scans": 0, "published": []}

    def count_query(execute, sql, params, many, context):
        counts["queries"] += 1
        return execute(sql, params, many, context)

    original_open = FileWriter._open_file
    original_snapshot = SiteSnapshot.__init__
    original_publish = FileWriter.publish

    def open_file(self, file):
        counts["opens"] += 1
        return original_open(self, file)

    def snapshot(self, site, page_ids=None):
        counts["site_scans" if page_ids is None else "named_scans"] += 1
        original_snapshot(self, site, page_ids)

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


def test_publishing_a_top_level_section_refreshes_the_top_level(setup, quiet, monkeypatch):
    writer, site, home = setup
    built = quiet(home, sections=3, leaves=3)
    section = built[0][0]
    others = files(("example.org/manifest.json", "example.org/section-1/index.md"))
    counts = measure(monkeypatch, lambda: republish(section, "Renamed section"))
    # Its own index, then the root index and llms.txt, which name it.
    assert counts["published"] == [
        "example.org/section-0/index.md",
        "example.org/index.md",
        "example.org/llms.txt",
    ]
    assert counts["opens"] == 0, counts
    # The request never reads the whole site (#90): each file reads only the
    # pages it lists, then the pages it names at commit.
    assert counts["site_scans"] == 0, counts
    output = read(writer, "example.org/section-0/index.md")
    assert "Renamed section" in output and "## Pages (3)" in output
    assert "Renamed section" in read(writer, "example.org/llms.txt")
    assert "Renamed section" in read(writer)
    assert files(others) == others


def test_publishing_the_home_page_reads_no_other_export(setup, quiet, monkeypatch):
    writer, site, home = setup
    quiet(home, sections=3, leaves=3)
    counts = measure(monkeypatch, lambda: republish(home, "New home"))
    assert counts["published"] == ["example.org/index.md"]
    assert counts["opens"] == 0, counts
    assert counts["site_scans"] == 0, counts
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


def test_unpublishing_withdraws_only_the_files_that_name_the_page(setup, quiet, monkeypatch):
    writer, site, home = setup
    built = quiet(home, sections=3, leaves=3)
    leaf = built[0][1][0]
    kept = files(("example.org/llms.txt", "example.org/index.md", "example.org/section-1/index.md"))
    counts = measure(monkeypatch, lambda: leaf.unpublish())
    assert not writer.exists("example.org/section-0/section0-leaf-0.md")
    # The manifest names every page, so it waits for the next finalise.
    assert not writer.exists("example.org/manifest.json")
    # Only the index that named the page is rebuilt, without it; llms.txt and
    # the root index name only sections, so they stay as they were.
    assert counts["published"] == ["example.org/section-0/index.md"]
    assert counts["opens"] == 0, counts
    assert "Section0-Leaf-0" not in read(writer, "example.org/section-0/index.md")
    assert files(kept.keys()) == kept
    for path in kept:
        assert writer.exists(path), path


def test_unpublishing_after_an_upgrade_rebuilds_no_section_index(setup, quiet, monkeypatch):
    writer, site, home = setup
    built = quiet(home, sections=4, leaves=2)
    # Navigation files as an earlier version left them: no record of the pages
    # they name, so a revocation withdraws them all.
    ExportArtifact.objects.filter(page_id__isnull=False).exclude(dependency_state="").update(
        lists=None, dependency_state="0" * 64
    )
    ExportArtifact.objects.filter(page_id__isnull=True).update(lists=None, dependency_state="")
    counts = measure(monkeypatch, lambda: built[0][1][0].unpublish())
    # Only the root index and llms.txt come back in the request, never every
    # section index of the site.
    assert counts["published"] == ["example.org/index.md", "example.org/llms.txt"]
    for number in range(4):
        assert not writer.exists(f"example.org/section-{number}/index.md")
    assert "Section0-Leaf-0" not in read(writer)
    generate()
    for number in range(4):
        assert "Section0-Leaf-0" not in read(writer, f"example.org/section-{number}/index.md")


def test_listing_does_not_decode_the_manifest_state_per_record(setup, quiet, monkeypatch):
    writer, site, home = setup
    quiet(home, sections=1, leaves=6)
    decoded = []
    field = ExportScope._meta.get_field("manifest_state")
    original = type(field).from_db_value

    def from_db_value(self, value, expression, connection):
        if self is field:
            decoded.append(1)
        return original(self, value, expression, connection)

    monkeypatch.setattr(type(field), "from_db_value", from_db_value)
    republish(home, "New home")
    # It holds an entry per page, so decoding it once per listed record made
    # an index rebuild quadratic in the size of the site.
    assert len(decoded) <= 6, len(decoded)


def test_unpublishing_a_top_level_page_rebuilds_llms_txt_without_it(setup, quiet):
    writer, site, home = setup
    built = quiet(home, sections=2, leaves=1)
    section = built[0][0]
    assert "Section-0" in read(writer, "example.org/llms.txt")
    section.unpublish()
    output = read(writer, "example.org/llms.txt")
    assert "Section-0" not in output and "Section-1" in output
    assert "Section-0" not in read(writer)


def test_a_change_without_signals_hides_navigation_until_rebuilt(setup, quiet, settings):
    writer, site, home = setup
    built = quiet(home, sections=1, leaves=2)
    leaf = built[0][1][0]
    # A bulk update sends no lifecycle signal, so nothing withdraws the files.
    type(leaf).objects.filter(pk=leaf.pk).update(live=False)
    # The files that name the page are hidden; those that name only its
    # section are still served.
    for path in ("example.org/manifest.json", "example.org/section-0/index.md"):
        assert not writer.exists(path), path
    for path in ("example.org/llms.txt", "example.org/index.md"):
        assert writer.exists(path), path
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


def test_manifest_is_off_by_default(setup, quiet, settings, client):
    writer, site, home = setup
    built = quiet(home, sections=1, leaves=1)
    assert writer.exists("example.org/manifest.json")
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "MANIFEST": False}
    # The next run withdraws the existing manifest.
    assert "discovery_scopes=1" in generate()
    assert not writer.exists("example.org/manifest.json")
    article(built[0][0], "fresh", title="Fresh page")
    output = generate()
    assert "discovery_scopes=1" in output, output
    assert not writer.exists("example.org/manifest.json")
    assert client.get("/markdown/manifest.json", HTTP_HOST="example.org").status_code == 404
    assert "Fresh page" in read(writer, "example.org/section-0/index.md")
    # Navigation is current without a manifest, so another run does nothing.
    assert "discovery_scopes=0" in generate()


def test_top_level_page_changing_between_leaf_and_index_keeps_links_live(setup, quiet, client):
    writer, site, home = setup
    built = quiet(home, sections=1, leaves=2)
    about = article(home, "about")
    generate()

    def linked(path):
        return [
            line.split("/markdown/")[1].rstrip(")")
            for line in read(writer, path).splitlines()
            if "[About]" in line
        ]

    def status(path):
        return client.get(f"/markdown/{path}", HTTP_HOST="example.org").status_code

    # Its first child moves the page from about.md to about/index.md. llms.txt
    # and the root index are rebuilt, so neither links the path that has gone.
    child = article(about, "team")
    for path in ("example.org/llms.txt", "example.org/index.md"):
        assert linked(path) == ["about/index.md"], path
    assert status("about/index.md") == 200 and status("about.md") == 404
    # Losing its last child moves it back.
    child.unpublish()
    for path in ("example.org/llms.txt", "example.org/index.md"):
        assert linked(path) == ["about.md"], path
    assert status("about.md") == 200 and status("about/index.md") == 404
    # A post below the top level still leaves both alone.
    kept = files(("example.org/llms.txt", "example.org/index.md"))
    built[0][1][0].unpublish()
    assert files(kept.keys()) == kept


def test_hierarchy_export_is_hidden_when_a_named_page_turns_private(setup, settings, client):
    writer, site, home = setup
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        **settings.WAGTAIL_MARKDOWN_AGENTS,
        "AUTO_GENERATE": False,
        "INCLUDE_HIERARCHY": True,
    }
    parent = article(home, "parent")
    child = article(parent, "child", title="Secret child")
    other = article(home, "other")
    # The child is named in the parent's metadata but has no export of its own.
    writer.generate(parent)
    writer.generate(other)

    def status(path):
        return client.get(f"/markdown/{path}", HTTP_HOST="example.org").status_code

    assert "Secret child" in read(writer, "example.org/parent/index.md")
    assert status("parent/index.md") == 200
    # A bulk change sends no signal, so only the check at serving can hide it.
    PageViewRestriction.objects.bulk_create(
        [PageViewRestriction(page=child, restriction_type="login")]
    )
    assert status("parent/index.md") == 404
    # An export that does not name the child is still served.
    assert status("other.md") == 200
    PageViewRestriction.objects.all().delete()
    assert status("parent/index.md") == 200
    # With signals, only the exports that name the page are withdrawn.
    PageViewRestriction.objects.create(page=child, restriction_type="login")
    assert not ExportArtifact.objects.filter(page_id=parent.pk).exists()
    assert ExportArtifact.objects.filter(page_id=other.pk).exists()


def test_cached_navigation_check_follows_publication_version(setup, settings, client):
    """The serving check is reused until the site's next publication (#74).

    A change through Wagtail withdraws what names the page at once; one that
    sends no signal stops being named within NAVIGATION_CACHE_TIMEOUT seconds.
    """
    from django.core.cache import cache

    writer, site, home = setup
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        **settings.WAGTAIL_MARKDOWN_AGENTS,
        "AUTO_GENERATE": False,
        "INCLUDE_HIERARCHY": True,
        "NAVIGATION_CACHE_TIMEOUT": 60,
    }
    parent = article(home, "parent")
    child = article(parent, "child", title="Secret child")
    other = article(home, "other")
    writer.generate(parent)

    def status(path):
        return client.get(f"/markdown/{path}", HTTP_HOST="example.org").status_code

    assert status("parent/index.md") == 200
    PageViewRestriction.objects.bulk_create(
        [PageViewRestriction(page=child, restriction_type="login")]
    )
    assert status("parent/index.md") == 200  # The cached answer, for now.
    writer.generate(other)  # Any publication in the site starts a new check.
    assert status("parent/index.md") == 404
    PageViewRestriction.objects.all().delete()
    cache.clear()  # As when the cached answer expires.
    assert status("parent/index.md") == 200
    # A change through Wagtail withdraws what names the page, cache or not.
    PageViewRestriction.objects.create(page=child, restriction_type="login")
    assert status("parent/index.md") == 404


# Publishing inside the editor's request never reads the whole site (#90).
# On a site of about 9,400 pages, publishing the home page did two whole-site
# readings and listed every export, and ran past the web server's timeout.


def test_home_publication_work_does_not_grow_with_the_site(setup, quiet, monkeypatch):
    writer, site, home = setup
    quiet(home, sections=2, leaves=2)
    small = measure(monkeypatch, lambda: republish(home, "Small site"))
    quiet(home, sections=1, leaves=20, prefix="blog")
    large = measure(monkeypatch, lambda: republish(home, "Large site"))
    assert small["site_scans"] == large["site_scans"] == 0, (small, large)
    # Four times the pages, all below the sections the home page lists.
    assert large["queries"] <= small["queries"] + 5, (small["queries"], large["queries"])
    assert "## Pages (3)" in read(writer)


def test_routine_home_index_matches_the_finalised_one(setup, quiet):
    writer, site, home = setup
    quiet(home, sections=3, leaves=2)
    finalised = split_document(read(writer))[1]
    republish(home, "Home")
    assert split_document(read(writer))[1] == finalised


def test_an_outdated_section_index_lists_its_pages_in_its_place(setup, quiet):
    writer, site, home = setup
    built = quiet(home, sections=2, leaves=2)
    # The section's export no longer matches its page, as after a change that
    # sent no signal: the root index lists the section's pages instead.
    ExportArtifact.objects.filter(logical_path="example.org/section-0/index.md").update(
        source_state="0" * 64
    )
    republish(home, "Home")
    output = read(writer)
    assert "/markdown/section-0/index.md" not in output
    for leaf in built[0][1]:
        assert f"[{leaf.title}]" in output, output
    assert "/markdown/section-1/index.md" in output


def test_a_named_page_turning_private_during_the_build_aborts_it(setup, quiet, monkeypatch):
    writer, site, home = setup
    built = quiet(home, sections=2, leaves=2)
    before = files(["example.org/index.md"])
    original = writer._upload

    def upload(file, text):
        original(file, text)
        # Without signals, as a bulk change or another process would make it.
        PageViewRestriction.objects.bulk_create(
            [PageViewRestriction(page=built[0][0], restriction_type="login")]
        )

    monkeypatch.setattr(writer, "_upload", upload)
    with pytest.raises(StaleBuild):
        IndexGenerator(writer).regenerate(home.specific)
    assert files(["example.org/index.md"]) == before


def test_a_page_the_index_does_not_name_does_not_abort_it(setup, quiet, monkeypatch):
    writer, site, home = setup
    built = quiet(home, sections=2, leaves=2)
    original = writer._upload

    def upload(file, text):
        original(file, text)
        # Below a section the root index lists: not a page it names.
        PageViewRestriction.objects.bulk_create(
            [PageViewRestriction(page=built[0][1][0], restriction_type="login")]
        )

    monkeypatch.setattr(writer, "_upload", upload)
    IndexGenerator(writer).regenerate(home.specific)
    assert "/markdown/section-0/index.md" in read(writer)


def test_a_leaf_linking_to_an_index_reads_no_whole_site(setup, quiet, monkeypatch):
    writer, site, home = setup
    built = quiet(home, sections=2, leaves=1)
    leaf = built[0][1][0]
    leaf.refresh_from_db()
    leaf.body = [
        (
            "paragraph",
            '<p>See <a href="/section-1/">the section</a>, <a href="/">home</a> and '
            '<a href="/markdown/llms.txt">the site list</a>.</p>',
        )
    ]
    counts = measure(monkeypatch, lambda: leaf.save_revision().publish())
    assert counts["site_scans"] == 0, counts
    output = read(writer, "example.org/section-0/section0-leaf-0.md")
    assert "](http://example.org/markdown/section-1/index.md)" in output, output
    assert "](http://example.org/markdown/index.md)" in output, output
    assert "](http://example.org/markdown/llms.txt)" in output, output
