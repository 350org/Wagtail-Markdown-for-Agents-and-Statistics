"""Batched policy must agree with fresh per-page checks, including hook behaviour."""

import pytest
from sandbox.testapp.models import ArticlePage
from wagtail import hooks
from wagtail.models import Page, PageViewRestriction, Site

from tests import test_writer
from wagtail_markdown_agents.export.policy import ExportPolicy
from wagtail_markdown_agents.export.snapshot import SiteSnapshot
from wagtail_markdown_agents.export.state import StaleBuild, page_state
from wagtail_markdown_agents.models import PageAgentSettings

pytestmark = pytest.mark.django_db(transaction=True)
setup = test_writer.setup


@pytest.mark.parametrize("mode", ["plain", "restricted", "excluded", "nested", "hook", "types"])
def test_snapshot_matches_policy_and_state(setup, settings, mode):
    writer, storage, site, page = setup
    root = site.root_page
    section = root.add_child(instance=ArticlePage(title="Index", slug="index"))
    root.add_child(instance=Page(title="Index underscore", slug="index_"))
    leaf = section.add_child(instance=ArticlePage(title="Log", slug="log"))
    section.add_child(instance=Page(title="Draft", slug="draft", live=False))
    section.save_revision().publish()
    leaf.save_revision().publish()
    if mode == "restricted":
        PageViewRestriction.objects.create(page=root.get_parent(), restriction_type="login")
    elif mode == "excluded":
        PageAgentSettings.objects.create(page=leaf, excluded=True)
    elif mode == "nested":
        Site.objects.create(hostname="nested.org", root_page=section)
    elif mode == "types":
        settings.WAGTAIL_MARKDOWN_AGENTS = {
            "STORAGE": "exports",
            "PAGE_TYPES": ["testapp.ArticlePage"],
        }
    PageAgentSettings.objects.create(page=page, extra_frontmatter={"campaign": "public"})

    def veto(candidate, site):
        return False if mode == "hook" and candidate.pk == leaf.pk else None

    def relocate(path, candidate, site):
        return f"custom/{path}" if mode == "hook" else None

    with (
        hooks.register_temporarily("markdown_export_eligible", veto),
        hooks.register_temporarily("markdown_export_path", relocate),
    ):
        snapshot = SiteSnapshot(Site.objects.select_related("root_page").get(pk=site.pk))
        plain, batched = ExportPolicy(), ExportPolicy(snapshot)
        for candidate in root.get_descendants(inclusive=True).specific():
            assert batched.is_eligible(candidate) == plain.is_eligible(candidate)
            assert batched.relative_path(candidate) == plain.relative_path(candidate)
            try:
                expected = page_state(candidate.pk, site.pk)
            except StaleBuild:
                with pytest.raises(StaleBuild):
                    page_state(candidate.pk, site.pk, snapshot=snapshot)
            else:
                actual = page_state(candidate.pk, site.pk, snapshot=snapshot)
                assert actual[2:] == expected[2:]


def test_snapshot_preserves_project_site_override(setup, monkeypatch):
    writer, storage, site, page = setup
    monkeypatch.setattr(ArticlePage, "get_site", lambda self: site)
    snapshot = SiteSnapshot(site)
    assert page_state(page.pk, site.pk, snapshot=snapshot)[2:] == page_state(page.pk, site.pk)[2:]
