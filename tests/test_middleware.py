"""Negotiated page requests share the checked serving path; every miss is HTML."""
# ruff: noqa: F811 — the corpus/events fixtures are imported from test_serving.

import pytest
from django.http import HttpResponse
from sandbox.testapp.models import ArticlePage
from wagtail import hooks
from wagtail.models import Page, PageViewRestriction

from tests import test_writer
from tests.test_serving import body, corpus, events  # noqa: F401 — shared fixtures
from wagtail_markdown_agents.export.writer import FileWriter
from wagtail_markdown_agents.models import ExportArtifact, ExportFile, PageAgentSettings

pytestmark = pytest.mark.django_db(transaction=True)
setup = test_writer.setup

GPTBOT = "Mozilla/5.0 (compatible; GPTBot/1.2; +https://openai.com/gptbot)"
MARKDOWN = {"HTTP_ACCEPT": "text/markdown"}
BROWSER = {"HTTP_ACCEPT": "text/html,*/*;q=0.8", "HTTP_USER_AGENT": "Mozilla/5.0 Chrome/128"}


def get(client, path, **kwargs):
    return client.get(path, HTTP_HOST="example.org", **kwargs)


def is_markdown(response):
    return response.status_code == 200 and response["Content-Type"].startswith("text/markdown")


def is_html(response):
    return response.status_code == 200 and response["Content-Type"].startswith("text/html")


@pytest.fixture
def no_generation(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Generation ran during a request")

    for name in ("generate", "begin", "publish", "update_aggregate"):
        monkeypatch.setattr(FileWriter, name, forbidden)


@pytest.mark.parametrize(
    "extra,method",
    [
        ({"QUERY_STRING": "output_format=md"}, "query-param"),
        (MARKDOWN, "accept-header"),
        ({"HTTP_USER_AGENT": GPTBOT}, "ua"),
        (
            {"QUERY_STRING": "output_format=md", **MARKDOWN, "HTTP_USER_AGENT": GPTBOT},
            "query-param",
        ),
        ({**MARKDOWN, "HTTP_USER_AGENT": GPTBOT}, "accept-header"),
    ],
)
def test_negotiated_get_serves_recorded_export(
    corpus, client, events, no_generation, extra, method
):
    writer, site, page, record = corpus
    response = get(client, "/article/", **extra)
    assert is_markdown(response)
    assert response["Content-Type"] == "text/markdown; charset=utf-8"
    assert response["Cache-Control"] == "private, no-store, max-age=0"
    assert set(response["Vary"].split(", ")) == {"Accept", "User-Agent"}
    assert response["X-Markdown-Source"] == "http://example.org/article/"
    assert response["Content-Signal"] == "ai-input=yes, search=yes"
    assert b"Published" in body(response)
    assert b"<article>" not in body(get(client, "/article/", **extra))
    assert [event["access_method"] for event in events] == [method, method]
    assert events[0]["page_id"] == page.pk
    assert events[0]["path"] == record.logical_path


def test_browsers_and_curl_get_html(corpus, client, events, no_generation):
    writer, site, page, record = corpus
    for extra in (BROWSER, {"HTTP_ACCEPT": "*/*", "HTTP_USER_AGENT": "curl/8.7.1"}, {}):
        response = get(client, "/article/", **extra)
        assert is_html(response)
        assert b"<article>" in response.content
    assert is_html(get(client, "/article/", HTTP_ACCEPT="text/markdown;q=0"))
    assert is_html(get(client, "/article/", HTTP_ACCEPT="text/*"))
    assert not events


def test_head_has_get_headers_without_body_or_count(corpus, client, events):
    response = get(client, "/article/", **MARKDOWN)
    head = client.head("/article/", HTTP_HOST="example.org", **MARKDOWN)
    assert head.status_code == 200
    for header in ("Content-Type", "Content-Length", "Cache-Control", "Vary", "X-Markdown-Source"):
        assert head[header] == response[header]
    assert body(head) == b""
    body(response)
    assert len(events) == 1


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete", "options"])
def test_non_read_methods_are_never_intercepted(corpus, client, events, no_generation, method):
    response = getattr(client, method)(
        "/article/?output_format=md", HTTP_HOST="example.org", **MARKDOWN
    )
    assert not response.get("Content-Type", "").startswith("text/markdown")
    assert not events


def test_missing_export_falls_through_to_html_without_generation(
    setup,
    client,
    events,
    no_generation,
):
    writer, storage, site, page = setup
    assert not ExportArtifact.objects.exists()
    response = get(client, "/article/", **MARKDOWN)
    assert is_html(response)
    assert b"Published" in response.content
    head = client.head("/article/", HTTP_HOST="example.org", **MARKDOWN)
    assert head.status_code == 200
    assert head["Content-Type"].startswith("text/html")
    assert not events
    assert not ExportArtifact.objects.exists()
    assert not ExportFile.objects.exists()


def test_deleted_object_falls_through_to_html(corpus, client, events, no_generation):
    writer, site, page, record = corpus
    writer._backend(record.file).delete(record.file.storage_key)
    assert is_html(get(client, "/article/", **MARKDOWN))
    assert is_html(get(client, "/article/?output_format=md"))
    assert not events


def test_missing_after_lookup_race_falls_through(corpus, client, monkeypatch, events):
    writer, site, page, record = corpus
    original = FileWriter.open

    def withdraw_then_open(self, path, **kwargs):
        writer._backend(record.file).delete(record.file.storage_key)
        return original(self, path, **kwargs)

    monkeypatch.setattr(FileWriter, "open", withdraw_then_open)
    assert is_html(get(client, "/article/", **MARKDOWN))
    assert not events


def test_replacement_between_lookup_and_open_falls_through(corpus, client, monkeypatch, events):
    writer, site, page, record = corpus
    original = FileWriter.open

    def replace_then_open(self, path, **kwargs):
        writer.publish(writer.begin(page), "New generation")
        return original(self, path, **kwargs)

    monkeypatch.setattr(FileWriter, "open", replace_then_open)
    assert is_html(get(client, "/article/", **MARKDOWN))
    assert not events


@pytest.mark.parametrize("change", ["private", "ancestor", "excluded", "unpublished"])
def test_ineligible_pages_never_serve_markdown(corpus, client, events, change):
    writer, site, page, record = corpus
    if change in {"private", "ancestor"}:
        PageViewRestriction.objects.create(
            page=page if change == "private" else site.root_page, restriction_type="login"
        )
    elif change == "excluded":
        PageAgentSettings.objects.create(page=page, excluded=True)
    else:
        page.unpublish()
    for extra in ({"QUERY_STRING": "output_format=md"}, MARKDOWN, {"HTTP_USER_AGENT": GPTBOT}):
        response = get(client, "/article/", **extra)
        assert not response.get("Content-Type", "").startswith("text/markdown")
        if change == "excluded":
            assert is_html(response)  # Exclusion withdraws Markdown only.
        else:
            assert response.status_code != 200
    assert not events


def test_only_canonical_page_routes_are_intercepted(corpus, client, events, settings):
    writer, site, page, record = corpus
    settings.ALLOWED_HOSTS = ["example.org", "testserver"]
    # No trailing slash: not a page route; CommonMiddleware still redirects afterwards.
    response = get(client, "/article?output_format=md")
    assert response.status_code == 301
    assert response["Location"].endswith("/article/?output_format=md")
    # Admin, documents and unknown routes are never candidates.
    for path in ("/admin/", "/admin/pages/", "/documents/1/x/", "/missing/page/"):
        response = get(client, path, **MARKDOWN)
        assert not response.get("Content-Type", "").startswith("text/markdown")
    # Explicit export routes keep their own contract and label.
    assert is_markdown(get(client, "/markdown/article.md", **MARKDOWN))
    assert [event["access_method"] for event in events] == ["export-url"]
    assert get(client, "/markdown/missing.md", **MARKDOWN).status_code == 404
    # Another host cannot borrow the default site's exports through negotiation.
    response = client.get("/article/", HTTP_HOST="testserver", **MARKDOWN)
    assert not response.get("Content-Type", "").startswith("text/markdown")
    assert len(events) == 1


@pytest.mark.parametrize(
    "path",
    [
        "/article/../article/",
        "/../article/",
        "/%2e%2e/article/",
        "/article/%2e%2e/",
        "/article/%00/",
        "/article%00/",
        "/article\\x/",
        "/example.org/article.md/",
        "/example.org/.objects/x/content/",
        "/" + "a" * 300 + "/article/",
    ],
)
def test_hostile_request_paths_never_reach_storage(corpus, client, events, monkeypatch, path):
    """#68: the request path is never turned into a storage path."""

    def forbidden(*args, **kwargs):
        pytest.fail("Storage was opened for a hostile request path")

    monkeypatch.setattr(FileWriter, "open", forbidden)
    for extra in ({"QUERY_STRING": "output_format=md"}, MARKDOWN, BROWSER):
        response = get(client, path, **extra)
        assert not response.get("Content-Type", "").startswith("text/markdown")
        assert not response.has_header("Link")
    assert not events


def test_disabled_triggers_fall_through(corpus, client, events, settings):
    writer, site, page, record = corpus
    settings.WAGTAIL_MARKDOWN_AGENTS = {
        **settings.WAGTAIL_MARKDOWN_AGENTS,
        "NEGOTIATE_QUERY_PARAM": False,
        "NEGOTIATE_USER_AGENT": False,
    }
    writer.generate(page)  # Configuration participates in publication state.
    assert is_html(get(client, "/article/?output_format=md"))
    assert is_html(get(client, "/article/", HTTP_USER_AGENT=GPTBOT))
    assert is_markdown(get(client, "/article/", **MARKDOWN))
    assert [event["access_method"] for event in events] == ["accept-header"]


def test_relocated_and_index_exports_serve_from_recorded_paths(corpus, client, events):
    writer, site, page, record = corpus
    child = page.add_child(instance=Page(title="Child", slug="child"))
    child.save_revision().publish()
    record = writer.generate(page)
    assert record.logical_path == "example.org/article/index.md"
    assert is_markdown(get(client, "/article/", **MARKDOWN))
    with hooks.register_temporarily(
        "markdown_export_path", lambda path, page, site: "custom/parent/index.md"
    ):
        record = writer.generate(page)
        assert record.logical_path == "example.org/custom/parent/index.md"
        response = get(client, "/article/", **MARKDOWN)
        assert is_markdown(response)
        assert b"Published" in body(response)
    assert [event["path"] for event in events] == [
        "example.org/article/index.md",
        "example.org/custom/parent/index.md",
    ]


def test_unicode_page_url_is_negotiated(corpus, client, events):
    writer, site, _page, _record = corpus
    page = site.root_page.add_child(
        instance=ArticlePage(title="Café", slug="café", body=[("paragraph", "<p>Unicode URL</p>")])
    )
    page.save_revision().publish()
    record = writer.generate(page)

    response = get(client, "/caf%C3%A9/", **MARKDOWN)

    assert is_markdown(response)
    assert b"Unicode URL" in body(response)
    assert events[-1]["path"] == record.logical_path


def test_request_veto_and_header_hook_apply_to_negotiation(corpus, client, events):
    def allowed(request, artifact, site):
        return request.GET.get("veto") != "yes"

    def headers(values, request, context):
        assert context["access_method"] == "accept-header"
        values["X-Accel-Expires"] = "0"

    with (
        hooks.register_temporarily("markdown_serve_allowed", allowed),
        hooks.register_temporarily("construct_markdown_response_headers", headers),
    ):
        assert is_html(get(client, "/article/?veto=yes", **MARKDOWN))
        response = get(client, "/article/", **MARKDOWN)
        assert is_markdown(response)
        assert response["X-Accel-Expires"] == "0"
        body(response)
    assert len(events) == 1


def test_before_serve_page_hooks_still_govern_html_fallback(corpus, client, events):
    def gate(page, request, args, kwargs):
        return HttpResponse("Gated", status=403)

    with hooks.register_temporarily("before_serve_page", gate):
        assert is_markdown(get(client, "/article/", **MARKDOWN))
        assert get(client, "/article/", **BROWSER).status_code == 403
    assert len(events) == 1
