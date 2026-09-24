"""Markdown syntax preservation and offline resolution against owned exports."""

from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from django.test import RequestFactory
from sandbox.testapp.models import ArticlePage
from wagtail import hooks
from wagtail.contrib.redirects.models import Redirect
from wagtail.models import PageViewRestriction

from tests import test_writer
from wagtail_markdown_agents.models import PageAgentSettings
from wagtail_markdown_agents.rendering import render_page
from wagtail_markdown_agents.rendering.links import LinkResolver, rewrite_links
from wagtail_markdown_agents.serving import serve_export
from wagtail_markdown_agents.signals import link_unresolved

URL = "http://example.org/markdown/target.md"
setup = test_writer.setup


@pytest.mark.parametrize(
    "source,expected",
    [
        ('[**Bold**](/target/ "Title")', f'[**Bold**]({URL} "Title")'),
        ("[Angle](</target/>)", f"[Angle](<{URL}>)"),
        ("<http://example.org/target/>", f"<{URL}>"),
        ("## [Heading](/target/) ##", f"## [Heading]({URL}) ##"),
        ("- [Item](/target/)\n  continuation", f"- [Item]({URL})\n  continuation"),
        ("> [First](/target/)\n> [Second](/target/)", f"> [First]({URL})\n> [Second]({URL})"),
        ("[One](/target/)\r\n[Two](/target/)\r\n", f"[One]({URL})\r\n[Two]({URL})\r\n"),
        (
            "[Label][id]\n\n[id]: /target/ 'Title'\n",
            f"[Label](<{URL}> \"Title\")\n\n[id]: /target/ 'Title'\n",
        ),
        (
            "[id][] and [id]\n\n[id]: /target/\n",
            f"[id](<{URL}>) and [id](<{URL}>)\n\n[id]: /target/\n",
        ),
        (
            "[link][id] ![image][id]\n\n[id]: /target/",
            f"[link](<{URL}>) ![image][id]\n\n[id]: /target/",
        ),
        ("[![alt](/image.png)](/target/)", f"[![alt](/image.png)]({URL})"),
        ("[a `]` b](/target/)", f"[a `]` b]({URL})"),
        ("[parentheses](/target/with\\(brackets\\))", f"[parentheses]({URL})"),
        ("| [Cell](/target/) |\n| --- |", f"| [Cell]({URL}) |\n| --- |"),
    ],
)
def test_edits_only_recognised_link_destinations(monkeypatch, source, expected):
    monkeypatch.setattr(LinkResolver, "resolve", lambda self, url: URL)
    assert (
        rewrite_links(source, SimpleNamespace(full_url="http://example.org/source/"), {})
        == expected
    )


@pytest.mark.parametrize(
    "source",
    [
        "`[Code](/target/)`",
        "``[Code](/target/) ` literal``",
        "```md\n[Code](/target/)\n```\n",
        "~~~\n[Code](/target/)\n~~~\n",
        "    [Code](/target/)\n",
        "> ```\n> [Code](/target/)\n> ```\n",
        "- ```\n  [Code](/target/)\n  ```\n",
        "![Image](/target/)",
        "![alt [nested](/target/)](/image.png)",
        r"\[Escaped](/target/)",
        "<div>\n[HTML block](/target/)\n</div>",
        "[Missing reference][absent]",
    ],
)
def test_code_images_and_nonlinks_are_untouched(monkeypatch, source):
    def forbidden(self, url):
        pytest.fail(f"Protected syntax resolved {url}")

    monkeypatch.setattr(LinkResolver, "resolve", forbidden)
    assert (
        rewrite_links(source, SimpleNamespace(full_url="http://example.org/source/"), {}) == source
    )


@pytest.fixture
def corpus(setup):
    writer, storage, site, source = setup
    target = site.root_page.add_child(
        instance=ArticlePage(
            title="Target",
            slug="target",
            body=[("paragraph", "<p>Target content</p>")],
        )
    )
    target.save_revision().publish()
    writer.generate(target)
    return writer, storage, site, source, target


@pytest.fixture
def events():
    received = []

    def receiver(sender, url, reason, **kwargs):
        received.append((url, reason))

    link_unresolved.connect(receiver, weak=False)
    yield received
    link_unresolved.disconnect(receiver)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "url",
    [
        "/target/",
        "../target/",
        "http://example.org/target/",
        "//example.org/target/",
        "/target",
        "/target/?output_format=md",
    ],
)
def test_same_site_urls_use_current_public_export(corpus, url):
    writer, storage, site, source, target = corpus
    assert rewrite_links(f"[Target]({url}#section)", source) == f"[Target]({URL}#section)"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "url",
    [
        "https://external.org/target/",
        "http://example.org:8080/target/",
        "mailto:test@example.org",
        "/media/photo.jpg",
        "/static/style.css",
        "/documents/42/report.pdf",
        "/target/?page=2",
        "/target/?utm_source=newsletter",
        "/target/?output_format=html",
        "#local",
    ],
)
def test_external_assets_and_meaningful_queries_are_untouched(corpus, events, url):
    writer, storage, site, source, target = corpus
    text = f"[Link]({url})"
    assert rewrite_links(text, source) == text
    assert events == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "change,reason",
    [
        ("private", "ineligible"),
        ("ancestor", "ineligible"),
        ("excluded", "ineligible"),
        ("unpublished", "ineligible"),
        ("deleted", "not_found"),
        ("missing", "not_found"),
        ("stale", "not_found"),
    ],
)
def test_unavailable_target_is_reported_once_per_run(corpus, events, change, reason):
    writer, storage, site, source, target = corpus
    if change in {"private", "ancestor"}:
        PageViewRestriction.objects.create(
            page=target if change == "private" else site.root_page, restriction_type="login"
        )
    elif change == "excluded":
        PageAgentSettings.objects.create(page=target, excluded=True)
    elif change == "unpublished":
        target.unpublish()
    elif change == "deleted":
        target.delete()
    elif change == "missing":
        storage.files.clear()
    else:
        target.body = [("paragraph", "<p>New content</p>")]
        target.save_revision().publish()
    text = "[One](/target/) [Two](/target/)"
    # D6: a private target's links lose their URL; public ones keep the HTML URL.
    private = change in {"private", "ancestor", "unpublished"}
    assert rewrite_links(text, source) == ("One Two" if private else text)
    assert events == [("/target/", reason)]
    rewrite_links(text, source)
    assert events == [("/target/", reason)] * 2


@pytest.mark.django_db(transaction=True)
def test_relocated_export_and_published_revision(corpus):
    writer, storage, site, source, target = corpus
    with hooks.register_temporarily(
        "markdown_export_path",
        lambda path, page, site: "custom/target.md" if page.pk == target.pk else None,
    ):
        writer.generate(target)
        target.body = [("paragraph", "<p>Private draft</p>")]
        target.save_revision()
        assert (
            rewrite_links("[Target](/target/)", source)
            == "[Target](http://example.org/markdown/custom/target.md)"
        )


@pytest.mark.django_db(transaction=True)
def test_local_redirect_chain_and_fragments(corpus, events):
    writer, storage, site, source, target = corpus
    Redirect.add_redirect("/old/", "/older/", site=site)
    Redirect.add_redirect("/older/", target, site=site)
    assert rewrite_links("[Old](/old/#section)", source) == f"[Old]({URL}#section)"
    assert not events


@pytest.mark.django_db(transaction=True)
def test_redirect_loop_is_bounded(corpus, events):
    writer, storage, site, source, target = corpus
    Redirect.add_redirect("/old/", "/older/", site=site)
    Redirect.add_redirect("/older/", "/old/", site=site)
    assert rewrite_links("[Old](/old/)", source) == "[Old](/old/)"
    assert events == [("/old/", "not_found")]


@pytest.mark.django_db(transaction=True)
def test_page_hooks_and_navigation_are_rewritten_before_frontmatter(corpus, client):
    writer, storage, site, source, target = corpus
    with hooks.register_temporarily(
        "markdown_post_render", lambda text, page, context: text + "\n\n[Hook](/target/)"
    ):
        text = render_page(source, navigation="[Navigation](/target/#nav)")
        assert f"[Hook]({URL})" in text
        assert f"[Navigation]({URL}#nav)" in text
        assert f"permalink: {source.full_url}" in text
        record = writer.generate(source)
    request = RequestFactory().get("/article/", HTTP_HOST=site.hostname)
    canonical = serve_export(request, record.logical_path, access_method="accept-header")
    direct = client.get("/markdown/article.md", HTTP_HOST=site.hostname)
    try:
        assert b"".join(canonical.streaming_content) == b"".join(direct.streaming_content)
    finally:
        canonical.close()
        direct.close()
    target_response = client.get(urlsplit(URL).path, HTTP_HOST=site.hostname)
    try:
        assert b"Target content" in b"".join(target_response.streaming_content)
    finally:
        target_response.close()


@pytest.mark.django_db(transaction=True)
def test_root_parent_and_sibling_links(corpus):
    writer, storage, site, source, target = corpus
    site.root_page.save_revision().publish()
    child = target.add_child(
        instance=ArticlePage(
            title="Child",
            slug="child",
            body=[("paragraph", "<p>Child content</p>")],
        )
    )
    child.save_revision().publish()
    writer.generate(target)
    writer.generate(source)
    writer.publish(writer.begin(site.root_page), "Root index")
    assert rewrite_links("[Root](/) [Parent](../) [Sibling](../../article/)", child) == (
        "[Root](http://example.org/markdown/index.md) "
        "[Parent](http://example.org/markdown/target/index.md) "
        "[Sibling](http://example.org/markdown/article.md)"
    )


@pytest.mark.django_db(transaction=True)
def test_existing_export_urls_and_aggregate_links(corpus, events):
    writer, storage, site, source, target = corpus
    writer.update_aggregate(site.pk, "example.org/index.md", lambda previous: "Index")
    text = f"[Page]({URL}#part) [Index](http://example.org/markdown/index.md)"
    assert rewrite_links(text, source) == text
    assert not events


@pytest.mark.django_db(transaction=True)
def test_no_export_keeps_html_url(corpus, events):
    writer, storage, site, source, target = corpus
    writer.delete_page(target.pk, site_id=site.pk)
    assert rewrite_links("[Target](/target/)", source) == "[Target](/target/)"
    assert events == [("/target/", "not_found")]


@pytest.mark.django_db(transaction=True)
def test_ambiguous_redirects_are_not_guessed(corpus, events):
    writer, storage, site, source, target = corpus
    Redirect.objects.create(old_path="/old", redirect_page=target)
    Redirect.objects.create(old_path="/old", redirect_page=source)
    assert rewrite_links("[Old](/old/)", source) == "[Old](/old/)"
    assert events == [("/old/", "not_found")]


@pytest.mark.django_db(transaction=True)
def test_site_specific_redirect_wins_over_global(corpus):
    writer, storage, site, source, target = corpus
    Redirect.add_redirect("/old/", "/missing/")
    Redirect.add_redirect("/old/", target, site=site)
    assert rewrite_links("[Old](/old/)", source) == f"[Old]({URL})"


@pytest.mark.django_db(transaction=True)
def test_private_redirect_target_is_ineligible(corpus, events):
    writer, storage, site, source, target = corpus
    Redirect.add_redirect("/old/", target, site=site)
    PageViewRestriction.objects.create(page=target, restriction_type="login")
    assert rewrite_links("[Old](/old/)", source) == "Old"
    assert events == [("/old/", "ineligible")]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("See [the **members** area](/target/#join).", "See the **members** area."),
        ('- [One](/target/ "Title")\n- [Two](</target/>)', "- One\n- Two"),
        # A reference use loses its link; definitions are never edited (documented).
        ("[Ref][members]\n\n[members]: /target/", "Ref\n\n[members]: /target/"),
        ("[![Logo](/media/logo.png)](/target/)", "![Logo](/media/logo.png)"),
        ("[](/target/)", ""),
        ("Visit <http://example.org/target/> now", "Visit  now"),
        ("`[Code](/target/)`", "`[Code](/target/)`"),
    ],
    ids=[
        "formatted-label",
        "titles-and-angles",
        "reference",
        "image-label",
        "empty",
        "autolink",
        "code",
    ],
)
def test_links_to_private_pages_keep_only_their_label(corpus, events, text, expected):
    writer, storage, site, source, target = corpus
    PageViewRestriction.objects.create(page=target, restriction_type="password", password="x")
    assert rewrite_links(text, source) == expected


@pytest.mark.django_db(transaction=True)
def test_link_to_public_page_outside_the_export_keeps_its_html_url(corpus, settings):
    writer, storage, site, source, target = corpus
    PageAgentSettings.objects.create(page=target, excluded=True)
    assert rewrite_links("[Target](/target/)", source) == "[Target](/target/)"


@pytest.mark.django_db(transaction=True)
def test_resolution_does_not_use_network(corpus, monkeypatch):
    import socket

    writer, storage, site, source, target = corpus

    def forbidden(*args, **kwargs):
        pytest.fail("Link resolution attempted a network connection")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    assert rewrite_links("[Target](/target/)", source) == f"[Target]({URL})"


@pytest.mark.django_db(transaction=True)
def test_link_rewrite_supports_filesystem_storage(corpus, settings, tmp_path):
    writer, storage, site, source, target = corpus
    settings.WAGTAIL_MARKDOWN_AGENTS = {}
    settings.BASE_DIR = tmp_path
    writer.generate(target)
    assert rewrite_links("[Target](/target/)", source) == f"[Target]({URL})"


@pytest.mark.django_db(transaction=True)
def test_repeated_target_with_fragments_opens_storage_once(corpus, monkeypatch):
    writer, storage, site, source, target = corpus
    original = writer.__class__.open
    calls = []

    def observed(self, path, **kwargs):
        calls.append(path)
        return original(self, path, **kwargs)

    monkeypatch.setattr(writer.__class__, "open", observed)
    rewrite_links("[A](/target/#a) [B](/target/#b) [Again](/target/#a)", source)
    assert calls == ["example.org/target.md"]
