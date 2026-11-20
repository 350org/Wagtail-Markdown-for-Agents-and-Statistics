"""Markdown responses name the page as canonical (#79)."""
# ruff: noqa: F811 — the corpus fixture is imported from test_serving.

import pytest
from sandbox.testapp.models import ArticlePage
from wagtail import hooks

from tests import test_writer
from tests.test_serving import body, corpus  # noqa: F401 — shared fixtures
from wagtail_markdown_agents.public_urls import export_url

pytestmark = pytest.mark.django_db(transaction=True)
setup = test_writer.setup
CANONICAL = '<http://example.org/article/>; rel="canonical"'


def get(client, path, **kwargs):
    return client.get(path, HTTP_HOST="example.org", **kwargs)


def is_markdown(response):
    return response.status_code == 200 and response["Content-Type"].startswith("text/markdown")


@pytest.mark.parametrize(
    "path,headers",
    [
        ("/markdown/article.md", {}),
        ("/article/?output_format=md", {}),
        ("/article/", {"HTTP_ACCEPT": "text/markdown"}),
        ("/article/", {"HTTP_USER_AGENT": "Mozilla/5.0 (compatible; GPTBot/1.2)"}),
    ],
)
def test_page_markdown_names_the_page_as_canonical(corpus, client, path, headers):
    response = get(client, path, **headers)
    assert is_markdown(response)
    assert response["Link"] == CANONICAL
    body(response)


def test_head_sends_the_canonical_too(corpus, client):
    response = client.head("/markdown/article.md", HTTP_HOST="example.org")
    assert response.status_code == 200
    assert response["Link"] == CANONICAL


def test_unicode_canonical_is_percent_encoded(corpus, client):
    writer, site, _page, _record = corpus
    page = site.root_page.add_child(
        instance=ArticlePage(title="Café", slug="café", body=[("paragraph", "<p>Unicode</p>")])
    )
    page.save_revision().publish()
    writer.generate(page)
    response = get(client, "/caf%C3%A9/?output_format=md")
    assert is_markdown(response)
    assert response["Link"] == '<http://example.org/caf%C3%A9/>; rel="canonical"'
    body(response)


@pytest.mark.parametrize("path", ["llms.txt", "index.md"])
def test_aggregates_have_no_canonical(corpus, client, path):
    writer, site, _page, record = corpus
    writer.update_aggregate(site.pk, f"{site.hostname}/{path}", lambda _: export_url(record))
    response = get(client, f"/markdown/{path}")
    assert response.status_code == 200
    assert "Link" not in response
    body(response)


def test_header_hook_can_remove_canonical(corpus, client):
    def headers(values, request, context):
        assert values["Link"] == CANONICAL
        values["Link"] = None

    with hooks.register_temporarily("construct_markdown_response_headers", headers):
        response = get(client, "/markdown/article.md")
        assert is_markdown(response)
        assert "Link" not in response
        body(response)
