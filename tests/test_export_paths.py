"""Pages that share a slug keep separate exports.

Regression coverage for the export-path collision fixed in the WordPress
plugin: files named only by slug made pages with the same slug under different
parents (or in different languages) overwrite each other, so every URL served
one page's Markdown. Here the path mirrors the whole URL tree. The language
case is covered end to end by
``test_multilingual.test_generation_manifest_and_serving_include_both_languages``.
"""

import json

import pytest
from django.core.management import call_command
from sandbox.testapp.models import ArticlePage
from wagtail.models import Site

from tests import test_indexes
from tests.test_indexes import read
from wagtail_markdown_agents import checks
from wagtail_markdown_agents.export.writer import StorageContractError
from wagtail_markdown_agents.models import ExportArtifact

pytestmark = pytest.mark.django_db(transaction=True)
setup = test_indexes.setup


def published(parent, slug, text):
    page = parent.add_child(
        instance=ArticlePage(title=slug.title(), slug=slug, body=[("paragraph", f"<p>{text}</p>")])
    )
    page.save_revision().publish()
    return page


def body(client, url):
    response = client.get(url, HTTP_HOST="example.org")
    try:
        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/markdown")
        return b"".join(response.streaming_content).decode()
    finally:
        response.close()


def test_same_slug_under_different_parents_keeps_separate_exports(setup, client):
    writer, site, home = setup
    city = published(home, "city", "Cities.")
    trends = {}
    for town in ("london", "boston", "paris"):
        parent = published(city, town, f"About {town}.")
        trends[town] = published(parent, "trends", f"Trends in {town}.")
    call_command("agentmd_generate", site=site.hostname)

    expected = {page.pk: f"example.org/city/{town}/trends.md" for town, page in trends.items()}
    paths = dict(
        ExportArtifact.objects.filter(page_id__in=expected).values_list("page_id", "logical_path")
    )
    assert paths == expected
    # One file per page: nothing collapsed into a shared file.
    files = ExportArtifact.objects.exclude(page_id=None).values_list("file_id", flat=True)
    assert len(set(files)) == len(files)

    manifest = json.loads(read(writer, "example.org/manifest.json"))
    listed = {entry["id"]: entry["path"] for entry in manifest["documents"]}
    assert {pk: listed[pk] for pk in expected} == expected

    for town in trends:
        for url in (f"/city/{town}/trends/?output_format=md", f"/markdown/city/{town}/trends.md"):
            text = body(client, url)
            assert f"Trends in {town}." in text
            assert all(f"Trends in {other}." not in text for other in trends if other != town)


@pytest.fixture
def same_hostname(setup, settings):
    """A second exported Site on the same hostname, another port."""
    writer, site, home = setup
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "SITES": "all"}
    other_home = home.get_parent().add_child(
        instance=ArticlePage(
            title="Other", slug="other-home", body=[("paragraph", "<p>Other.</p>")]
        )
    )
    other_home.save_revision().publish()
    other = Site.objects.create(hostname="example.org", port=8080, root_page=other_home)
    Site.clear_site_root_paths_cache()
    return writer, site, home, other, other_home


def test_sites_sharing_a_hostname_never_overwrite_each_other(same_hostname):
    writer, site, home, other, other_home = same_hostname
    first = writer.generate(home)
    assert first.logical_path == "example.org/index.md"
    with pytest.raises(StorageContractError, match="another site's export"):
        writer.generate(other_home)
    assert "Home body." in read(writer, "example.org/index.md")


def test_exported_sites_sharing_a_hostname_are_warned_about(same_hostname, settings):
    messages = checks.check_shared_hostnames(None, databases=["default"])
    assert [message.id for message in messages] == ["wagtail_markdown_agents.W005"]
    assert "example.org:80" in messages[0].msg and "example.org:8080" in messages[0].msg
    # Database checks run only when asked for.
    assert checks.check_shared_hostnames(None) == []
    # Exporting one of them is fine.
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "SITES": "default"}
    assert checks.check_shared_hostnames(None, databases=["default"]) == []
