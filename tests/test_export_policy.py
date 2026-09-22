"""ExportPolicy: eligibility rules and site-prefixed paths (#16).

One policy for writing, links, indexes, discovery and serving. Eligibility
is deterministic per page; paths mirror the URL tree under the hostname.
"""

import pytest
from sandbox.testapp.models import ArticlePage
from wagtail import hooks
from wagtail.models import Page, PageViewRestriction, Site

from wagtail_markdown_agents.export.policy import (
    ELIGIBLE_HOOK,
    EXPORT_PATH_HOOK,
    ExportPathError,
    ExportPolicy,
)
from wagtail_markdown_agents.models import PageAgentSettings


@pytest.fixture(autouse=True)
def clear_site_root_paths_cache():
    # Wagtail caches site root paths outside the test transaction; a site saved
    # here (port, second site) would otherwise leak into later tests.
    yield
    Site.clear_site_root_paths_cache()


@pytest.fixture
def site(db):
    return Site.objects.get(is_default_site=True)


@pytest.fixture
def home(site):
    return site.root_page


@pytest.fixture
def article(home):
    return home.add_child(
        instance=ArticlePage(title="Fossil Free Future", slug="fossil-free-future")
    )


@pytest.fixture
def hook(monkeypatch):
    def register(name, fn):
        monkeypatch.setitem(hooks._hooks, name, [*hooks._hooks.get(name, []), (fn, 0)])
        return fn

    return register


@pytest.fixture
def policy():
    return ExportPolicy()


def child(parent, title, **fields):
    return parent.add_child(instance=Page(title=title, slug=title.lower(), **fields))


# Eligibility


def test_a_live_page_in_the_default_site_is_eligible(policy, article):
    assert policy.is_eligible(article) is True


def test_the_site_root_page_is_eligible_but_the_tree_root_is_not(policy, home):
    assert policy.is_eligible(home) is True
    assert policy.is_eligible(Page.objects.get(depth=1)) is False


def test_an_unpublished_page_is_not_eligible(policy, home):
    assert policy.is_eligible(child(home, "Draft", live=False)) is False


@pytest.mark.parametrize(
    "restriction",
    [
        {"restriction_type": PageViewRestriction.PASSWORD, "password": "secret"},
        {"restriction_type": PageViewRestriction.LOGIN},
        {"restriction_type": PageViewRestriction.GROUPS},
    ],
    ids=["password", "login", "groups"],
)
def test_a_view_restriction_withdraws_the_page_and_lifting_it_restores(
    policy, article, restriction
):
    row = PageViewRestriction.objects.create(page=article, **restriction)
    assert policy.is_eligible(article) is False

    row.delete()
    assert policy.is_eligible(article) is True


def test_an_inherited_view_restriction_withdraws_descendants(policy, article):
    grandchild = child(child(article, "Team"), "Bios")
    PageViewRestriction.objects.create(page=article, restriction_type=PageViewRestriction.LOGIN)

    assert policy.is_eligible(grandchild) is False


def test_exclusion_withdraws_the_page_and_clearing_it_restores(policy, article):
    row = PageAgentSettings.objects.create(page=article, excluded=True)
    assert policy.is_eligible(article) is False

    row.excluded = False
    row.save()
    assert policy.is_eligible(article) is True


def test_page_types_restrict_eligibility_case_insensitively(policy, article, home, settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"PAGE_TYPES": ["testapp.articlepage"]}

    assert policy.is_eligible(article) is True
    assert policy.is_eligible(home) is False


def test_page_types_are_checked_on_the_base_page_instance(policy, article, settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"PAGE_TYPES": ["testapp.ArticlePage"]}

    assert policy.is_eligible(Page.objects.get(pk=article.pk)) is True


def test_hook_can_veto_but_never_grant(policy, article, hook):
    hook(ELIGIBLE_HOOK, lambda page, site: False)
    assert policy.is_eligible(article) is False


def test_hook_returning_true_or_none_leaves_the_rules_in_force(policy, article, home, hook):
    hook(ELIGIBLE_HOOK, lambda page, site: True)
    hook(ELIGIBLE_HOOK, lambda page, site: None)
    PageAgentSettings.objects.create(page=article, excluded=True)

    assert policy.is_eligible(home) is True
    assert policy.is_eligible(article) is False


def test_hook_receives_the_page_and_its_site(policy, article, site, hook):
    seen = {}
    hook(ELIGIBLE_HOOK, lambda page, site: seen.update(page=page, site=site))

    policy.is_eligible(article)

    assert seen == {"page": article, "site": site}


def test_a_page_outside_every_site_is_not_eligible(policy, db):
    orphan = Page.objects.get(depth=1).add_child(instance=Page(title="Orphan", slug="orphan"))

    assert policy.is_eligible(orphan) is False


@pytest.fixture
def other_site(db):
    root = Page.objects.get(depth=1).add_child(instance=Page(title="Other", slug="other"))
    return Site.objects.create(hostname="other.example", root_page=root, is_default_site=False)


def test_only_the_default_site_is_exported_by_default(policy, other_site, home):
    assert policy.is_eligible(home) is True
    assert policy.is_eligible(other_site.root_page) is False


@pytest.mark.parametrize(
    ("sites", "expected"),
    [("all", True), (["other.example"], True), (["localhost"], False)],
    ids=["all", "listed", "not-listed"],
)
def test_sites_setting_selects_exported_sites(policy, other_site, settings, sites, expected):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"SITES": sites}

    assert policy.is_eligible(other_site.root_page) is expected


# Paths


def test_site_root_is_the_index_under_the_hostname(policy, home):
    assert policy.relative_path(home) == "localhost/index.md"


def test_the_hostname_prefix_never_includes_the_port(policy, site, home):
    site.port = 8000
    site.save()

    assert policy.relative_path(home) == "localhost/index.md"


def test_a_leaf_page_is_a_file(policy, article):
    assert policy.relative_path(article) == "localhost/fossil-free-future.md"


def test_a_page_with_live_children_is_a_directory_index(policy, article):
    visible = child(article, "Visible")

    assert policy.relative_path(article) == "localhost/fossil-free-future/index.md"
    assert policy.relative_path(visible) == "localhost/fossil-free-future/visible.md"


def test_a_draft_child_does_not_make_its_parent_a_directory(policy, article):
    child(article, "Draft", live=False)

    assert policy.relative_path(article) == "localhost/fossil-free-future.md"


def test_paths_are_computed_for_ineligible_pages_too(policy, home):
    draft = child(home, "Draft", live=False)

    assert policy.relative_path(draft) == "localhost/draft.md"


def test_a_page_outside_every_site_has_no_path(policy, db):
    orphan = Page.objects.get(depth=1).add_child(instance=Page(title="Orphan", slug="orphan"))

    with pytest.raises(ExportPathError):
        policy.relative_path(orphan)


@pytest.mark.parametrize("slug", ["index", "log"])
def test_reserved_slugs_get_a_trailing_underscore(policy, home, slug):
    page = home.add_child(instance=Page(title=slug, slug=slug))

    assert policy.relative_path(page) == f"localhost/{slug}_.md"


def test_a_reserved_slug_yields_to_a_real_sibling_using_the_page_id(policy, home):
    real = home.add_child(instance=Page(title="Real", slug="index_"))
    page = home.add_child(instance=Page(title="Index", slug="index"))

    assert policy.relative_path(real) == "localhost/index_.md"
    assert policy.relative_path(page) == f"localhost/index_{page.pk}.md"


def test_reserved_names_are_mangled_at_every_level(policy, home):
    section = home.add_child(instance=Page(title="Index", slug="index"))
    leaf = child(section, "Leaf")

    assert policy.relative_path(section) == "localhost/index_/index.md"
    assert policy.relative_path(leaf) == "localhost/index_/leaf.md"


# export_path hook


def test_export_path_hook_relocates_within_the_site(policy, article, hook):
    hook(EXPORT_PATH_HOOK, lambda path, page, site: f"campaigns/{page.slug}.md")

    assert policy.relative_path(article) == "localhost/campaigns/fossil-free-future.md"


def test_export_path_hook_receives_the_default_path_and_may_decline(policy, article, hook):
    seen = {}
    hook(EXPORT_PATH_HOOK, lambda path, page, site: seen.update(path=path) and None)

    assert policy.relative_path(article) == "localhost/fossil-free-future.md"
    assert seen == {"path": "fossil-free-future.md"}


def test_export_path_hooks_chain(policy, article, hook):
    hook(EXPORT_PATH_HOOK, lambda path, page, site: f"a/{path}")
    hook(EXPORT_PATH_HOOK, lambda path, page, site: f"b/{path}")

    assert policy.relative_path(article) == "localhost/b/a/fossil-free-future.md"


@pytest.mark.parametrize(
    "bad",
    ["/abs.md", "../escape.md", "x/../../escape.md", "no-extension", "", ".md", 42, "dir\\win.md"],
    ids=repr,
)
def test_export_path_hook_results_are_validated(policy, article, hook, bad):
    hook(EXPORT_PATH_HOOK, lambda path, page, site: bad)

    with pytest.raises(ExportPathError):
        policy.relative_path(article)


def test_export_path_hook_rejects_noncanonical_results(policy, article, hook):
    hook(EXPORT_PATH_HOOK, lambda path, page, site: "./campaigns//sub/../post.md")

    # Owned paths must mean the same thing to every storage/serving consumer.
    # #19 rejects traversal segments instead of silently collapsing them.
    with pytest.raises(ExportPathError):
        policy.relative_path(article)
