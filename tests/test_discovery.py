"""HTML responses advertise current exports; the discovery cache never authorises reads."""
# ruff: noqa: F811 — the corpus/events fixtures are imported from test_serving.

import pytest
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.template import Context, Template
from django.test import RequestFactory
from sandbox.testapp.models import ArticlePage
from wagtail import hooks
from wagtail.models import Page, PageViewRestriction

from tests import test_writer
from tests.test_middleware import BROWSER, MARKDOWN, get, is_html, is_markdown
from tests.test_serving import body, corpus, events  # noqa: F401 — shared fixtures
from wagtail_markdown_agents import discovery
from wagtail_markdown_agents.export.writer import FileWriter
from wagtail_markdown_agents.models import PageAgentSettings
from wagtail_markdown_agents.public_urls import alternate_url, export_url

pytestmark = pytest.mark.django_db(transaction=True)
setup = test_writer.setup

LINK = '<http://example.org/article/?output_format=md>; rel="alternate"; type="text/markdown"'
TAG = '<link rel="alternate" type="text/markdown" href="http://example.org/article/?output_format=md">'


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def probes(monkeypatch):
    """Count storage existence probes: the cache-miss signature."""
    calls = []
    original = FileWriter.object_exists

    def counted(self, record):
        calls.append(record.logical_path)
        return original(self, record)

    monkeypatch.setattr(FileWriter, "object_exists", counted)
    return calls


def vary(response):
    return {part.strip() for part in response.get("Vary", "").split(",") if part.strip()}


def render_tag(page=None, request=None, source="{% agent_markdown_link %}"):
    context = {"page": page}
    if request is not None:
        context["request"] = request
    return Template("{% load wagtail_markdown_agents %}" + source).render(Context(context))


def test_html_200_carries_link_and_vary_accept(corpus, client, events):
    writer, site, page, record = corpus
    for extra in (BROWSER, {}):
        response = get(client, "/article/", **extra)
        assert is_html(response)
        assert response["Link"] == LINK
        assert "Accept" in vary(response)
        assert "User-Agent" not in vary(response)
    head = client.head("/article/", HTTP_HOST="example.org", **BROWSER)
    assert head.status_code == 200 and head["Link"] == LINK
    assert alternate_url(record) == "http://example.org/article/?output_format=md"
    # The Markdown response itself is never given a discovery header.
    response = get(client, "/article/", **MARKDOWN)
    assert is_markdown(response) and not response.has_header("Link")
    body(response)
    assert len(events) == 1


def test_existing_link_and_vary_values_are_preserved(corpus, client):
    def gate(page, request, args, kwargs):
        response = HttpResponse("<html>Custom</html>")
        response["Link"] = '</style.css>; rel="preload"; as="style"'
        response["Vary"] = "Cookie"
        return response

    with hooks.register_temporarily("before_serve_page", gate):
        response = get(client, "/article/", **BROWSER)
    assert response["Link"] == f'</style.css>; rel="preload"; as="style", {LINK}'
    assert vary(response) == {"Cookie", "Accept"}


@pytest.mark.parametrize("change", ["missing", "private", "ancestor", "excluded", "deleted"])
def test_unavailable_exports_are_not_advertised(corpus, client, change):
    writer, site, page, record = corpus
    if change == "missing":
        writer.delete_page(page.pk, site_id=site.pk)
    elif change in {"private", "ancestor"}:
        PageViewRestriction.objects.create(
            page=page if change == "private" else site.root_page, restriction_type="login"
        )
    elif change == "excluded":
        PageAgentSettings.objects.create(page=page, excluded=True)
    else:
        writer._backend(record.file).delete(record.file.storage_key)
    response = get(client, "/article/", **BROWSER)
    if change in {"private", "ancestor"}:
        assert response.status_code != 200
    else:
        assert is_html(response)
    assert not response.has_header("Link")
    assert "Accept" not in vary(response)
    request = RequestFactory().get("/article/", HTTP_HOST="example.org")
    assert render_tag(page, request) == ""


def test_query_negotiation_disabled_advertises_explicit_route(corpus, client, settings):
    writer, site, page, record = corpus
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        **settings.WAGTAIL_MARKDOWN_AGENTS,
        "NEGOTIATE_QUERY_PARAM": False,
    }
    record = writer.generate(page)  # Configuration participates in publication state.
    response = get(client, "/article/", **BROWSER)
    assert (
        response["Link"]
        == '<http://example.org/markdown/article.md>; rel="alternate"; type="text/markdown"'
    )
    assert export_url(record) == "http://example.org/markdown/article.md"
    request = RequestFactory().get("/article/", HTTP_HOST="example.org")
    assert 'href="http://example.org/markdown/article.md"' in render_tag(page, request)
    # Without the explicit routes there is no URL to advertise at all.
    settings.ROOT_URLCONF = "tests.no_export_urls"
    response = get(client, "/article/", **BROWSER)
    assert is_html(response) and not response.has_header("Link")
    assert render_tag(page, request) == ""


def test_relocated_and_index_exports_are_advertised_from_records(corpus, client, settings):
    writer, site, page, record = corpus
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        **settings.WAGTAIL_MARKDOWN_AGENTS,
        "NEGOTIATE_QUERY_PARAM": False,
    }
    child = page.add_child(instance=Page(title="Child", slug="child"))
    child.save_revision().publish()
    writer.generate(page)
    assert "/markdown/article/index.md>" in get(client, "/article/", **BROWSER)["Link"]
    with hooks.register_temporarily(
        "markdown_export_path", lambda path, page, site: "custom/parent/index.md"
    ):
        writer.generate(page)
        assert "/markdown/custom/parent/index.md>" in get(client, "/article/", **BROWSER)["Link"]
    # Without the hook the recorded path no longer matches policy. Nothing was
    # published, so the entry lives until the timeout; a fresh resolution omits it.
    cache.clear()
    assert not get(client, "/article/", **BROWSER).has_header("Link")


def test_resolution_is_cached_and_invalidated_by_publication(corpus, client, probes):
    writer, site, page, record = corpus
    assert get(client, "/article/", **BROWSER)["Link"] == LINK
    assert get(client, "/article/", **BROWSER)["Link"] == LINK
    assert client.head("/article/", HTTP_HOST="example.org")["Link"] == LINK
    assert probes == ["example.org/article.md"]
    writer.delete_page(page.pk, site_id=site.pk)
    assert not get(client, "/article/", **BROWSER).has_header("Link")
    assert not get(client, "/article/", **BROWSER).has_header("Link")
    assert len(probes) == 1  # A miss is cached too, without probing storage.
    writer.generate(page)
    assert get(client, "/article/", **BROWSER)["Link"] == LINK
    assert len(probes) == 2


def test_cache_entries_are_scoped_by_path_site_and_storage(corpus, client, probes, settings):
    writer, site, page, record = corpus
    other = site.root_page.add_child(
        instance=ArticlePage(title="Other", slug="other", body=[("paragraph", "<p>Other</p>")])
    )
    other.save_revision().publish()
    writer.generate(other)
    assert get(client, "/article/", **BROWSER)["Link"] == LINK
    assert "/other/?output_format=md" in get(client, "/other/", **BROWSER)["Link"]
    assert probes == ["example.org/article.md", "example.org/other.md"]
    # A different storage configuration never reads another configuration's
    # entries: the same request resolves afresh against the records.
    settings.STORAGES = {**settings.STORAGES, "other": settings.STORAGES["exports"]}
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "STORAGE": "other"}
    get(client, "/article/", **BROWSER)
    assert probes == ["example.org/article.md", "example.org/other.md", "example.org/article.md"]


def test_cache_timeout_zero_disables_caching(corpus, client, probes, settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        **settings.WAGTAIL_MARKDOWN_AGENTS,
        "DISCOVERY_CACHE_TIMEOUT": 0,
    }
    for _ in range(2):
        assert get(client, "/article/", **BROWSER)["Link"] == LINK
    assert len(probes) == 2


@pytest.mark.parametrize("change", ["config", "revision", "dependency"])
def test_obsolete_publications_are_not_advertised(corpus, client, settings, change):
    writer, site, page, record = corpus
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        **settings.WAGTAIL_MARKDOWN_AGENTS,
        "DISCOVERY_CACHE_TIMEOUT": 0,
    }
    if change == "config":
        settings.WAGTAIL_MARKDOWN_AGENTS = {
            **settings.WAGTAIL_MARKDOWN_AGENTS,
            "INCLUDE_OWNER": True,
        }
    elif change == "revision":
        page.title = "Updated article"
        page.save_revision().publish()
    else:
        # Hierarchy exports depend on other published pages in the site.
        settings.WAGTAIL_MARKDOWN_AGENTS = {
            **settings.WAGTAIL_MARKDOWN_AGENTS,
            "INCLUDE_HIERARCHY": True,
        }
        record = writer.generate(page)
        assert record.dependency_state
        site.site_name = "Updated site"
        site.save()
    assert not writer.exists(record.logical_path)
    assert get(client, "/markdown/article.md").status_code == 404
    assert is_html(get(client, "/article/?output_format=md"))
    assert not get(client, "/article/", **BROWSER).has_header("Link")
    request = RequestFactory().get("/article/", HTTP_HOST="example.org")
    assert render_tag(page, request) == ""


def test_cached_discovery_never_authorises_serving(corpus, client, events, probes):
    writer, site, page, record = corpus
    assert get(client, "/article/", **BROWSER)["Link"] == LINK
    writer._backend(record.file).delete(record.file.storage_key)  # No publication event.
    assert get(client, "/article/", **BROWSER)["Link"] == LINK  # Stale for at most the timeout.
    assert len(probes) == 1
    assert is_html(get(client, "/article/", **MARKDOWN))
    assert is_html(get(client, "/article/?output_format=md"))
    assert get(client, "/markdown/article.md").status_code == 404
    assert not events


def test_link_header_setting_disables_the_response_phase_only(corpus, client, settings, probes):
    writer, site, page, record = corpus
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "LINK_HEADER": False}
    response = get(client, "/article/", **BROWSER)
    assert is_html(response) and not response.has_header("Link")
    assert "Accept" not in vary(response)
    assert not probes
    assert is_markdown(get(client, "/article/", **MARKDOWN))
    request = RequestFactory().get("/article/", HTTP_HOST="example.org")
    assert render_tag(page, request) == TAG


def test_header_hook_overrides_omits_and_is_validated(corpus, client):
    writer, site, page, record = corpus
    seen = {}

    def customise(values, request, context):
        seen.update(context)
        assert context["page"].pk == page.pk
        values["X-Robots-Tag"] = "noai"
        if request.GET.get("omit"):
            values["Link"] = None
        if request.GET.get("bad"):
            values["Link"] = "bad\r\nvalue"

    with hooks.register_temporarily("construct_markdown_html_headers", customise):
        response = get(client, "/article/", **BROWSER)
        assert response["Link"] == LINK and response["X-Robots-Tag"] == "noai"
        assert seen["alternate_url"] == "http://example.org/article/?output_format=md"
        assert seen["export_path"] == "article.md" and seen["path"] == "/article/"
        assert seen["site"] == site
        response = get(client, "/article/?omit=1", **BROWSER)
        assert not response.has_header("Link") and "Accept" in vary(response)
        with pytest.raises(ImproperlyConfigured):
            get(client, "/article/?bad=1", **BROWSER)


def test_only_canonical_page_routes_on_the_request_site_are_advertised(
    corpus, client, settings, probes
):
    writer, site, page, record = corpus
    settings.ALLOWED_HOSTS = ["example.org", "testserver"]
    settings.ROOT_URLCONF = "tests.no_export_urls"
    for path in ("/existing/", "/admin/login/", "/article/unknown/", "/missing/"):
        response = get(client, path, **BROWSER)
        assert not response.has_header("Link"), path
    assert not get(client, "/article", **BROWSER).has_header("Link")  # Redirect, not a 200.
    assert not client.get("/article/", HTTP_HOST="testserver", **BROWSER).has_header("Link")
    assert not probes
    assert get(client, "/article/", **BROWSER)["Link"] == LINK


def test_previews_are_not_advertised(corpus, client, monkeypatch):
    writer, site, page, record = corpus
    request = RequestFactory().get("/article/", HTTP_HOST="example.org")
    request.is_preview = True
    assert render_tag(page, request) == ""
    response = HttpResponse("<html></html>")
    discovery.add_discovery_headers(request, response)
    assert not response.has_header("Link")


def test_unicode_page_urls_are_advertised(corpus, client):
    writer, site, page, record = corpus
    page = site.root_page.add_child(
        instance=ArticlePage(title="Café", slug="café", body=[("paragraph", "<p>Unicode</p>")])
    )
    page.save_revision().publish()
    writer.generate(page)
    response = get(client, "/caf%C3%A9/", **BROWSER)
    assert response["Link"] == (
        '<http://example.org/caf%C3%A9/?output_format=md>; rel="alternate"; type="text/markdown"'
    )
    request = RequestFactory().get("/caf%C3%A9/", HTTP_HOST="example.org")
    assert 'href="http://example.org/caf%C3%A9/?output_format=md"' in render_tag(page, request)


def test_template_tag_uses_context_page_or_argument_and_escapes(corpus, monkeypatch):
    writer, site, page, record = corpus
    request = RequestFactory().get("/", HTTP_HOST="example.org")
    assert render_tag(page, request) == TAG
    assert render_tag(None, request) == ""
    assert render_tag(page) == TAG  # No request in context: the page's own site.
    assert render_tag(site.root_page, request) == ""  # No export for the home page.
    explicit = "{% agent_markdown_link article %}"
    context = Context({"page": site.root_page, "article": page, "request": request})
    assert Template("{% load wagtail_markdown_agents %}" + explicit).render(context) == TAG
    monkeypatch.setattr(
        "wagtail_markdown_agents.templatetags.wagtail_markdown_agents.page_alternate_url",
        lambda page, request=None: "http://x/?a=1&b=<2>",
    )
    assert render_tag(page, request) == (
        '<link rel="alternate" type="text/markdown" href="http://x/?a=1&amp;b=&lt;2&gt;">'
    )
