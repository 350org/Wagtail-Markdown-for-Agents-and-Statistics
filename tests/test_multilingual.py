"""Translated site roots share ownership but must retain distinct export trees."""

import json
from urllib.parse import urlsplit

import pytest
from django.core.management import call_command
from django.test import Client
from django.utils import translation
from wagtail.models import Locale, PageViewRestriction, Site

from tests import test_indexes
from tests.test_indexes import article, read
from wagtail_markdown_agents.export.policy import ExportPolicy
from wagtail_markdown_agents.export.snapshot import SiteSnapshot
from wagtail_markdown_agents.export.state import page_state
from wagtail_markdown_agents.models import ExportArtifact, PageAgentSettings
from wagtail_markdown_agents.rendering import render_page
from wagtail_markdown_agents.rendering.links import rewrite_links

pytestmark = pytest.mark.django_db(transaction=True)
setup = test_indexes.setup


@pytest.fixture
def translated(setup, settings):
    writer, site, home = setup
    settings.WAGTAIL_I18N_ENABLED = True
    settings.LANGUAGE_CODE = "en"
    settings.LANGUAGES = [("en", "English"), ("fr", "French")]
    settings.WAGTAIL_CONTENT_LANGUAGES = settings.LANGUAGES
    settings.ROOT_URLCONF = "tests.i18n_urls"
    settings.MIDDLEWARE = [
        "django.middleware.security.SecurityMiddleware",
        "django.middleware.locale.LocaleMiddleware",
        *settings.MIDDLEWARE[1:],
    ]
    # Fixture publications stay independent of automatic lifecycle generation.
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        **settings.WAGTAIL_MARKDOWN_AGENTS,
        "AUTO_GENERATE": False,
    }
    home.locale, _ = Locale.objects.get_or_create(language_code="en")
    home.save(update_fields=["locale"])
    home.save_revision().publish()
    french = Locale.objects.create(language_code="fr")
    page = article(home, "article")
    french_home = home.copy_for_translation(french)
    french_home.save_revision().publish()
    french_page = page.copy_for_translation(french)
    french_page.body = [("paragraph", "<p>Contenu français.</p>")]
    french_page.save_revision().publish()
    french_home.refresh_from_db()
    french_page.refresh_from_db()
    Site.clear_site_root_paths_cache()
    with translation.override("en"):
        yield writer, site, home, page, french_home, french_page


def test_generation_manifest_and_serving_include_both_languages(translated, client):
    writer, site, home, page, french_home, french_page = translated
    call_command("agentmd_generate", site=site.hostname)
    expected = {
        home.pk: "example.org/en/index.md",
        page.pk: "example.org/en/article.md",
        french_home.pk: "example.org/fr/index.md",
        french_page.pk: "example.org/fr/article.md",
    }
    assert (
        dict(ExportArtifact.objects.exclude(page_id=None).values_list("page_id", "logical_path"))
        == expected
    )
    manifest = json.loads(read(writer, "example.org/manifest.json"))
    assert {entry["id"]: entry["path"] for entry in manifest["documents"]} == expected
    assert "fr/index.md" in read(writer)
    assert "en/index.md" in read(writer)
    for path in ("/fr/article/?output_format=md", "/markdown/fr/article.md"):
        response = client.get(path, HTTP_HOST="example.org")
        try:
            assert response["Content-Type"].startswith("text/markdown")
            assert "Contenu français." in b"".join(response.streaming_content).decode()
        finally:
            response.close()
    assert "article body." in read(writer, expected[page.pk])


@pytest.mark.parametrize("change", ["exclude", "restrict", "metadata", "publish"])
def test_translated_changes_invalidate_site_state_and_match_live_policy(translated, change):
    writer, site, home, page, french_home, french_page = translated
    call_command("agentmd_generate", site=site.hostname)
    if change == "exclude":
        PageAgentSettings.objects.create(page=french_page, excluded=True)
    elif change == "restrict":
        PageViewRestriction.objects.create(page=french_home, restriction_type="login")
    elif change == "metadata":
        PageAgentSettings.objects.create(page=french_page, extra_frontmatter={"language": "fr"})
    else:
        french_page.body = [("paragraph", "<p>Updated translation.</p>")]
        french_page.save_revision().publish()
    assert not writer.exists("example.org/manifest.json")
    snapshot = SiteSnapshot(site)
    plain, batched = ExportPolicy(), ExportPolicy(snapshot)
    for candidate in (home, page, french_home, french_page):
        assert candidate.pk in snapshot.pages
        assert batched.is_eligible(candidate) == plain.is_eligible(candidate)
        assert batched.relative_path(candidate) == plain.relative_path(candidate)
        if plain.is_eligible(candidate):
            assert (
                page_state(candidate.pk, site.pk, snapshot=snapshot)[2:]
                == page_state(candidate.pk, site.pk)[2:]
            )


@pytest.mark.export_lifecycle
def test_translated_publish_refreshes_indexes_and_manifest(translated, settings):
    writer, site, home, page, french_home, french_page = translated
    call_command("agentmd_generate", site=site.hostname)
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        **settings.WAGTAIL_MARKDOWN_AGENTS,
        "AUTO_GENERATE": True,
    }
    french_page.body = [("paragraph", "<p>Updated translation.</p>")]
    french_page.save_revision().publish()
    assert "Updated translation." in read(writer, "example.org/fr/article.md")
    manifest = json.loads(read(writer, "example.org/manifest.json"))
    assert {entry["id"] for entry in manifest["documents"]} == {
        home.pk,
        page.pk,
        french_home.pk,
        french_page.pk,
    }
    PageViewRestriction.objects.create(page=french_home, restriction_type="login")
    assert not writer.exists("example.org/fr/article.md")
    manifest = json.loads(read(writer, "example.org/manifest.json"))
    assert {entry["id"] for entry in manifest["documents"]} == {home.pk, page.pk}


def test_translated_root_at_different_depth_and_inherited_restriction(translated):
    from wagtail.models import Page

    writer, site, home, page, french_home, french_page = translated
    container = home.get_parent().add_child(instance=Page(title="Container", slug="container"))
    french_home.move(container, pos="last-child")
    french_home.refresh_from_db()
    french_page.refresh_from_db()
    Site.clear_site_root_paths_cache()
    snapshot = SiteSnapshot(site)
    assert ExportPolicy(snapshot).relative_path(french_page) == "example.org/fr/article.md"
    assert ExportPolicy().relative_path(french_page) == "example.org/fr/article.md"
    french_page.unpublish()
    assert ExportPolicy().relative_path(french_home) == "example.org/fr/index.md"
    PageViewRestriction.objects.create(page=container, restriction_type="login")
    snapshot = SiteSnapshot(site)
    assert not ExportPolicy(snapshot).is_eligible(french_home)
    assert not ExportPolicy().is_eligible(french_home)


def test_multilingual_site_state_queries_stay_bounded(translated):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from wagtail_markdown_agents.export.state import site_state

    writer, site, home, page, french_home, french_page = translated
    counts = []
    for size in (1, 10):
        if size > 1:
            for number in range(9):
                article(french_home, f"extra-{number}")
        site_state(site.pk)
        with CaptureQueriesContext(connection) as queries:
            site_state(site.pk)
        counts.append(len(queries))
    assert counts[1] <= counts[0] + 2, counts


AGENT = "wagtail_markdown_agents.middleware.AgentMarkdownMiddleware"
LOCALE = "django.middleware.locale.LocaleMiddleware"
TRIGGERS = {
    "query": ("?output_format=md", {}),
    "accept": ("", {"HTTP_ACCEPT": "text/markdown"}),
    "ua": ("", {"HTTP_USER_AGENT": "GPTBot/1.2"}),
}


def fetch(path, **extra):
    # A new client per call: the handler keeps the middleware chain it first loads.
    response = Client().get(path, HTTP_HOST="example.org", **extra)
    try:
        body = b"".join(response.streaming_content) if response.streaming else response.content
        return response.status_code, response["Content-Type"].split(";")[0], body.decode()
    finally:
        response.close()


@pytest.fixture
def unprefixed(translated, settings):
    settings.ROOT_URLCONF = "tests.i18n_unprefixed_urls"
    return translated


@pytest.mark.parametrize("trigger", TRIGGERS)
def test_unprefixed_default_language_serves_each_tree(unprefixed, trigger):
    writer, site, home, page, french_home, french_page = unprefixed
    call_command("agentmd_generate", site=site.hostname)
    suffix, extra = TRIGGERS[trigger]
    # Whatever language the worker thread last served must not decide the result.
    translation.activate("en")
    status, content_type, body = fetch("/fr/article/" + suffix, **extra)
    assert (status, content_type) == (200, "text/markdown")
    assert "Contenu français." in body
    translation.activate("fr")
    status, content_type, body = fetch("/article/" + suffix, **extra)
    assert (status, content_type) == (200, "text/markdown")
    assert "article body." in body


@pytest.mark.parametrize("urlconf", ["tests.i18n_urls", "tests.i18n_unprefixed_urls"])
@pytest.mark.parametrize("trigger", TRIGGERS)
def test_middleware_before_locale_falls_back_to_html_never_404(
    translated, settings, urlconf, trigger
):
    writer, site, home, page, french_home, french_page = translated
    settings.ROOT_URLCONF = urlconf
    call_command("agentmd_generate", site=site.hostname)
    order = [name for name in settings.MIDDLEWARE if name != LOCALE]
    order.insert(order.index(AGENT) + 2, LOCALE)  # Security, Agent, Session, Locale
    settings.MIDDLEWARE = order
    suffix, extra = TRIGGERS[trigger]
    translation.activate("en")
    status, content_type, body = fetch("/fr/article/" + suffix, **extra)
    assert status == 200
    assert "Contenu français." in body


@pytest.mark.parametrize("urlconf", ["tests.i18n_urls", "tests.i18n_unprefixed_urls"])
@pytest.mark.parametrize("active", ["en", "fr"])
def test_translated_page_renders_in_its_own_language(translated, settings, urlconf, active):
    writer, site, home, page, french_home, french_page = translated
    settings.ROOT_URLCONF = urlconf
    call_command("agentmd_generate", site=site.hostname)
    french_home.body = [
        (
            "paragraph",
            f'<p><a linktype="page" id="{french_page.pk}">lien</a> and '
            f'<a linktype="page" id="{page.pk}">link</a></p>',
        )
    ]
    french_home.save_revision().publish()
    target = "http://example.org/markdown/fr/article.md"
    # Wagtail localises a page link to the active language, so the HTML page
    # links both to the French article. The export must not depend on the caller.
    with translation.override(active):
        assert f"[lien]({target}) and [link]({target})" in render_page(french_home)
        call_command("agentmd_generate", site=site.hostname)
    assert f"[lien]({target}) and [link]({target})" in read(writer, "example.org/fr/index.md")


@pytest.mark.parametrize("urlconf", ["tests.i18n_urls", "tests.i18n_unprefixed_urls"])
def test_links_across_language_trees_reach_the_right_export(translated, settings, urlconf):
    writer, site, home, page, french_home, french_page = translated
    settings.ROOT_URLCONF = urlconf
    call_command("agentmd_generate", site=site.hostname)
    english = page.full_url
    french = french_page.full_url
    assert urlsplit(english).path != urlsplit(french).path
    markdown = rewrite_links(
        f"[en]({english}) [fr]({urlsplit(french).path}) [missing](/fr/absent/)", french_home
    )
    assert markdown == (
        "[en](http://example.org/markdown/en/article.md) "
        "[fr](http://example.org/markdown/fr/article.md) [missing](/fr/absent/)"
    )
