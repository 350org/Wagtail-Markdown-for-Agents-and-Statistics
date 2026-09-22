"""Public routes use managed ownership and fresh policy on every request."""

from io import BytesIO
from urllib.parse import urlsplit

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory
from django.urls import reverse
from sandbox.testapp.models import ArticlePage
from wagtail import hooks
from wagtail.models import Page, PageViewRestriction, Site

from tests import test_writer
from wagtail_markdown_agents.models import PageAgentSettings
from wagtail_markdown_agents.public_urls import alternate_url, export_url
from wagtail_markdown_agents.serving import serve_export
from wagtail_markdown_agents.signals import markdown_served

pytestmark = pytest.mark.django_db(transaction=True)
setup = test_writer.setup


@pytest.fixture(params=["remote", "filesystem"])
def corpus(setup, settings, tmp_path, request):
    writer, storage, site, page = setup
    if request.param == "filesystem":
        settings.WAGTAIL_MARKDOWN_AGENTS = {}
        settings.BASE_DIR = tmp_path
    record = writer.generate(page)
    return writer, site, page, record


def body(response):
    try:
        return b"".join(response.streaming_content) if response.streaming else response.content
    finally:
        response.close()


def get(client, path, **kwargs):
    return client.get(path, HTTP_HOST="example.org", **kwargs)


@pytest.fixture
def events():
    received = []

    def receiver(sender, **kwargs):
        received.append(kwargs)

    markdown_served.connect(receiver, weak=False)
    yield received
    markdown_served.disconnect(receiver)


def test_direct_get_head_and_read_event(corpus, client, events):
    writer, site, page, record = corpus
    url = export_url(record)
    assert url == "http://example.org/markdown/article.md"
    assert (
        reverse("wagtail_markdown_agents:export", kwargs={"export_path": "article.md"})
        == urlsplit(url).path
    )
    response = get(client, urlsplit(url).path)
    assert response.status_code == 200
    assert response["Content-Type"] == "text/markdown; charset=utf-8"
    assert response["Cache-Control"] == "private, no-store, max-age=0"
    assert set(response["Vary"].split(", ")) == {"Accept", "User-Agent"}
    assert response["X-Markdown-Source"] == page.full_url
    assert response["Content-Signal"] == "ai-input=yes, search=yes"
    assert "attachment" not in response.get("Content-Disposition", "")
    assert b"Published" in body(response)
    head = client.head(urlsplit(url).path, HTTP_HOST="example.org")
    assert head.status_code == 200
    for header in (
        "Content-Type",
        "Content-Length",
        "Cache-Control",
        "Vary",
        "X-Markdown-Source",
        "Content-Signal",
    ):
        assert head.get(header) == response.get(header)
    assert body(head) == b""
    assert len(events) == 1
    assert events[0]["page_id"] == page.pk
    assert events[0]["site_id"] == site.pk
    assert events[0]["path"] == record.logical_path
    assert events[0]["access_method"] == "export-url"


@pytest.mark.parametrize(
    "name,path,content_type",
    [
        ("llms_txt", "llms.txt", "text/plain; charset=utf-8"),
        ("manifest", "manifest.json", "application/json; charset=utf-8"),
        ("export", "index.md", "text/markdown; charset=utf-8"),
    ],
)
def test_named_aggregates_traverse_to_page_and_revoke(
    corpus, client, events, name, path, content_type
):
    writer, site, page, record = corpus
    text = export_url(record)
    aggregate = writer.update_aggregate(site.pk, f"{site.hostname}/{path}", lambda previous: text)
    kwargs = {"export_path": path} if name == "export" else {}
    url = reverse(f"wagtail_markdown_agents:{name}", kwargs=kwargs)
    assert export_url(aggregate) == site.root_url + url
    response = get(client, url)
    assert response.status_code == 200
    assert response["Content-Type"] == content_type
    target = body(response).decode()
    assert events == []
    assert b"Published" in body(get(client, urlsplit(target).path))
    assert len(events) == 1
    PageViewRestriction.objects.create(page=page, restriction_type="login")
    assert get(client, url).status_code == 404


@pytest.mark.parametrize(
    "change",
    ["private", "ancestor", "excluded", "unpublished", "deleted", "moved", "slug", "missing"],
)
def test_direct_reads_reject_obsolete_exports(corpus, client, events, change):
    writer, site, page, record = corpus
    if change in {"private", "ancestor"}:
        PageViewRestriction.objects.create(
            page=page if change == "private" else site.root_page, restriction_type="login"
        )
    elif change == "excluded":
        PageAgentSettings.objects.create(page=page, excluded=True)
    elif change == "unpublished":
        page.unpublish()
    elif change == "deleted":
        page.delete()
    elif change == "moved":
        parent = site.root_page.add_child(instance=Page(title="Parent", slug="parent"))
        page.move(parent, pos="last-child")
    elif change == "slug":
        page.slug = "relocated"
        page.save_revision().publish()
    else:
        writer._backend(record.file).delete(record.file.storage_key)
    assert get(client, "/markdown/article.md").status_code == 404
    assert not events


@pytest.mark.parametrize(
    "path",
    [
        "../article.md",
        "%2e%2e/article.md",
        "%252e%252e/article.md",
        "x/../article.md",
        "x//article.md",
        "x\\article.md",
        "%00article.md",
        ".objects/secret/content",
        "example.net/article.md",
        "unmanaged.md",
        "asset.json",
        "a" * 1025 + ".md",
    ],
)
def test_unsafe_and_unmanaged_paths_do_not_touch_storage(setup, client, monkeypatch, path):
    writer, storage, site, page = setup
    writer.generate(page)

    def forbidden(*args, **kwargs):
        pytest.fail("Rejected path reached storage")

    monkeypatch.setattr(writer.__class__, "_open_file", forbidden)
    assert get(client, "/markdown/" + path).status_code == 404


def test_host_and_scope_isolation(setup, client, settings):
    writer, storage, site, page = setup
    writer.generate(page)
    root = page.get_root()
    other_home = root.add_child(instance=Page(title="Other", slug="other"))
    other = Site.objects.create(hostname="other.org", root_page=other_home)
    other_page = other_home.add_child(
        instance=ArticlePage(
            title="Other", slug="article", body=[("paragraph", "<p>Other site</p>")]
        )
    )
    other_page.save_revision().publish()
    settings.WAGTAIL_MARKDOWN_AGENTS = {"STORAGE": "exports", "SITES": "all"}
    # Configuration participates in publication state: regenerate the first scope.
    writer.generate(page)
    assert client.get("/markdown/article.md", HTTP_HOST=other.hostname).status_code == 404
    assert client.get("/markdown/article.md", HTTP_HOST="unknown.org").status_code == 404
    writer.generate(other_page)
    assert b"Other site" in body(client.get("/markdown/article.md", HTTP_HOST=other.hostname))
    assert b"Published" in body(get(client, "/markdown/article.md"))
    settings.ALLOWED_HOSTS = ["example.org"]
    assert client.get("/markdown/article.md", HTTP_HOST="unknown.org").status_code == 400


def test_relocated_parent_export_and_alternate_urls(corpus, client, settings):
    writer, site, page, record = corpus
    page.add_child(instance=Page(title="Child", slug="child"))
    with hooks.register_temporarily(
        "markdown_export_path", lambda path, page, site: "custom/parent/index.md"
    ):
        record = writer.generate(page)
        assert export_url(record) == "http://example.org/markdown/custom/parent/index.md"
        assert alternate_url(record) == page.full_url + "?output_format=md"
        assert b"Published" in body(get(client, "/markdown/custom/parent/index.md"))
        assert get(client, "/markdown/article.md").status_code == 404
        settings.WAGTAIL_MARKDOWN_AGENTS = {
            **settings.WAGTAIL_MARKDOWN_AGENTS,
            "NEGOTIATE_QUERY_PARAM": False,
        }
        assert alternate_url(record) == export_url(record)


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete", "options"])
def test_methods_never_read_or_count(corpus, client, events, method):
    response = getattr(client, method)("/markdown/article.md", HTTP_HOST="example.org")
    assert response.status_code == 405
    assert response["Allow"] == "GET, HEAD"
    assert not events


def test_shared_serving_miss_allows_html_fallback(setup):
    writer, storage, site, page = setup
    request = RequestFactory().get("/article/", HTTP_HOST="example.org")
    assert serve_export(request, "example.org/article.md", access_method="accept-header") is None


def test_request_veto_is_not_cached(corpus, client, events):
    writer, site, page, record = corpus

    def allowed(request, artifact, site):
        return request.GET.get("veto") != "yes"

    with hooks.register_temporarily("markdown_serve_allowed", allowed):
        assert get(client, "/markdown/article.md?veto=yes").status_code == 404
        assert b"Published" in body(get(client, "/markdown/article.md"))
        assert get(client, "/markdown/article.md?veto=yes").status_code == 404
    assert len(events) == 1


def test_response_header_customisation(corpus, client):
    def headers(values, request, context):
        assert context["access_method"] == "export-url"
        assert context["path"] == "example.org/article.md"
        values["Content-Signal"] = ""
        values["X-Accel-Expires"] = "0"
        values["X-LiteSpeed-Cache-Control"] = "no-cache"

    with hooks.register_temporarily("construct_markdown_response_headers", headers):
        response = get(client, "/markdown/article.md")
        assert "Content-Signal" not in response
        assert response["X-Accel-Expires"] == "0"
        assert response["X-LiteSpeed-Cache-Control"] == "no-cache"
        body(response)


def test_invalid_header_configuration_closes_stream(corpus, client, monkeypatch):
    writer, site, page, record = corpus
    stream = BytesIO(b"Public")
    monkeypatch.setattr(writer.__class__, "open", lambda *args, **kwargs: stream)

    def headers(values, request, context):
        values["Content-Signal"] = "safe\r\nInjected: yes"

    with (
        hooks.register_temporarily("construct_markdown_response_headers", headers),
        pytest.raises(ImproperlyConfigured),
    ):
        get(client, "/markdown/article.md")
    assert stream.closed


def test_failed_notification_does_not_fail_response(corpus, client, caplog):
    def broken(sender, **kwargs):
        raise RuntimeError("stats receiver unavailable")

    markdown_served.connect(broken, weak=False)
    try:
        assert b"Published" in body(get(client, "/markdown/article.md"))
    finally:
        markdown_served.disconnect(broken)
    assert "stats receiver unavailable" in caplog.text


def test_included_prefix_and_configured_https_origin(corpus, client, settings):
    writer, site, page, record = corpus
    settings.ROOT_URLCONF = "tests.serving_urls"
    site.port = 443
    site.save()
    record = writer.generate(page)
    assert export_url(record) == "https://example.org/exports/v1/article.md"
    assert b"Published" in body(
        client.get("/exports/v1/article.md", secure=True, HTTP_HOST="example.org")
    )
    assert get(client, "/existing/").content == b"Existing route"


def test_shared_serving_from_canonical_and_direct_urls(corpus, client, events):
    writer, site, page, record = corpus
    request = RequestFactory().get("/article/", HTTP_HOST="example.org")
    canonical = serve_export(request, record.logical_path, access_method="accept-header")
    direct = get(client, "/markdown/article.md")
    assert body(canonical) == body(direct)
    assert [event["access_method"] for event in events] == ["accept-header", "export-url"]


def test_replacement_between_route_lookup_and_open_is_a_miss(corpus, client, monkeypatch, events):
    writer, site, page, record = corpus
    original = writer.__class__.open

    def replace_then_open(self, path, **kwargs):
        writer.publish(writer.begin(page), "New generation")
        return original(self, path, **kwargs)

    monkeypatch.setattr(writer.__class__, "open", replace_then_open)
    assert get(client, "/markdown/article.md").status_code == 404
    assert not events


def test_writer_checks_scope_before_open(corpus, monkeypatch):
    writer, site, page, record = corpus

    def forbidden(*args):
        pytest.fail("Wrong scope reached storage")

    monkeypatch.setattr(writer, "_open_file", forbidden)
    with pytest.raises(FileNotFoundError):
        writer.open(record.logical_path, site_id=site.pk + 1)


def test_request_veto_cannot_allow_private_page(corpus, client, events):
    writer, site, page, record = corpus
    PageViewRestriction.objects.create(page=page, restriction_type="login")
    with hooks.register_temporarily("markdown_serve_allowed", lambda *args: True):
        assert get(client, "/markdown/article.md").status_code == 404
    assert not events


def test_aggregate_request_veto(corpus, client, events):
    writer, site, page, record = corpus
    writer.update_aggregate(site.pk, "example.org/manifest.json", lambda previous: "{}")
    with hooks.register_temporarily("markdown_serve_allowed", lambda *args: False):
        assert get(client, "/markdown/manifest.json").status_code == 404
    assert not events


@pytest.mark.parametrize("value", ["", "ai-input=no"])
def test_configured_content_signal(corpus, client, settings, value):
    writer, site, page, record = corpus
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "CONTENT_SIGNAL": value}
    writer.generate(page)
    response = get(client, "/markdown/article.md")
    assert response.get("Content-Signal") == (value or None)
    body(response)


@pytest.mark.parametrize(
    "name,value",
    [("Bad\nName", "x"), ("Bad Name", "x"), ("X-Test", 12), ("X-Test", "null\x00value")],
)
def test_invalid_hook_header_names_and_values(corpus, client, name, value):
    def headers(values, request, context):
        values[name] = value

    with (
        hooks.register_temporarily("construct_markdown_response_headers", headers),
        pytest.raises(ImproperlyConfigured),
    ):
        get(client, "/markdown/article.md")


def test_head_closes_storage_stream(corpus, client, monkeypatch, events):
    writer, site, page, record = corpus
    stream = BytesIO(b"Public")
    monkeypatch.setattr(writer.__class__, "open", lambda *args, **kwargs: stream)
    response = client.head("/markdown/article.md", HTTP_HOST="example.org")
    assert stream.closed
    assert response["Content-Length"] == "6"
    assert body(response) == b""
    assert not events


def test_disabled_site_with_empty_aggregate_is_not_served(corpus, client, settings):
    writer, site, page, record = corpus
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "SITES": []}
    # Even an empty aggregate captured after the site is disabled is not public.
    writer.update_aggregate(site.pk, "example.org/manifest.json", lambda previous: "{}")
    assert get(client, "/markdown/manifest.json").status_code == 404


def test_new_draft_never_appears_in_direct_response(corpus, client):
    writer, site, page, record = corpus
    page.body = [("paragraph", "<p>Confidential draft</p>")]
    page.save_revision()
    content = body(get(client, "/markdown/article.md"))
    assert b"Published" in content
    assert b"Confidential" not in content


def test_root_include_does_not_capture_html_routes(corpus, client, settings):
    writer, site, page, record = corpus
    settings.ROOT_URLCONF = "tests.root_serving_urls"
    assert export_url(record) == "http://example.org/article.md"
    assert b"Published" in body(get(client, "/article.md"))
    assert get(client, "/existing/").content == b"Existing HTML"


def test_superseded_record_cannot_supply_a_public_url(corpus):
    writer, site, page, record = corpus
    writer.generate(page)
    from wagtail_markdown_agents.export.paths import ExportPathError

    with pytest.raises(ExportPathError):
        export_url(record)


def test_nonseekable_backend_stream_never_uses_local_filename_metadata(
    corpus, client, monkeypatch, tmp_path
):
    writer, site, page, record = corpus
    unrelated = tmp_path / "unrelated"
    unrelated.write_bytes(b"Unrelated local data has a different length")

    class RemoteStream:
        name = str(unrelated)

        def __init__(self):
            self.buffer = BytesIO(b"Public remote bytes")

        def read(self, size=-1):
            return self.buffer.read(size)

        def tell(self):
            return self.buffer.tell()

        def seekable(self):
            return False

        def close(self):
            self.buffer.close()

    monkeypatch.setattr(writer.__class__, "open", lambda *args, **kwargs: RemoteStream())
    response = get(client, "/markdown/article.md")
    assert "Content-Length" not in response
    assert "Content-Disposition" not in response
    assert body(response) == b"Public remote bytes"
