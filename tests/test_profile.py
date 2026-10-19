"""Site profiles and the generic settings they carry: FRONTMATTER_FIELDS,
EXCLUDE_WHEN and IMAGE_RENDITIONS."""

import datetime
import json

import pytest
from django.core.exceptions import ImproperlyConfigured
from sandbox.testapp.models import ArticlePage, NewsCategory, NewsPage
from wagtail import blocks
from wagtail.images import get_image_model
from wagtail.images.blocks import ImageChooserBlock
from wagtail.images.tests.utils import get_test_image_file
from wagtail.models import Locale, Site

from tests import profile_module, test_lifecycle
from tests.test_lifecycle import entries
from wagtail_markdown_agents import checks, profile
from wagtail_markdown_agents.export.policy import ExportPolicy
from wagtail_markdown_agents.export.snapshot import SiteSnapshot
from wagtail_markdown_agents.rendering import render_block
from wagtail_markdown_agents.rendering.blocks import enclosing
from wagtail_markdown_agents.rendering.frontmatter import build
from wagtail_markdown_agents.settings import get_setting

UTC = datetime.UTC
setup = test_lifecycle.setup
PROFILE = """\
version: 1
name: Test site
settings:
  include_owner: true
  exclude_when: [hide_from_search]
modules: [tests.profile_module]
"""


def write(tmp_path, text, name="profile.yaml"):
    path = tmp_path / name
    path.write_text(text)
    return str(path)


def configure(settings, **values):
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, **values}


# Loading


def test_profile_settings_sit_between_defaults_and_django_settings(settings, tmp_path):
    configure(settings, PROFILE=write(tmp_path, PROFILE))
    assert get_setting("INCLUDE_OWNER") is True
    assert get_setting("EXCLUDE_WHEN") == ["hide_from_search"]
    assert get_setting("INCLUDE_HIERARCHY") is False
    configure(settings, INCLUDE_OWNER=False)
    assert get_setting("INCLUDE_OWNER") is False


def test_without_a_profile_nothing_changes(settings):
    assert profile.configured() is None
    assert get_setting("EXCLUDE_WHEN") == []
    assert profile.profile_modules() == []


def test_relative_paths_resolve_against_base_dir(settings, tmp_path):
    write(tmp_path, PROFILE)
    settings.BASE_DIR = tmp_path
    configure(settings, PROFILE="profile.yaml")
    assert get_setting("INCLUDE_OWNER") is True


def test_json_profiles_are_read(settings, tmp_path):
    data = {"version": 1, "settings": {"exclude_when": ["hidden"]}}
    configure(settings, PROFILE=write(tmp_path, json.dumps(data), "profile.json"))
    assert get_setting("EXCLUDE_WHEN") == ["hidden"]


def test_a_package_name_reads_its_profile_yaml(settings, tmp_path, monkeypatch):
    package = tmp_path / "siteprofile"
    package.mkdir()
    (package / "__init__.py").write_text("")
    write(package, PROFILE)
    monkeypatch.syspath_prepend(str(tmp_path))
    configure(settings, PROFILE="siteprofile")
    assert get_setting("EXCLUDE_WHEN") == ["hide_from_search"]


def test_modules_are_imported_and_ready_is_called(settings, tmp_path):
    configure(settings, PROFILE=write(tmp_path, PROFILE))
    profile_module.READY_CALLS.clear()
    profile.import_modules()
    assert profile_module.READY_CALLS == [True]


def test_editing_the_setting_reloads_the_profile(settings, tmp_path):
    configure(settings, PROFILE=write(tmp_path, PROFILE))
    assert get_setting("INCLUDE_OWNER") is True
    other = write(tmp_path, "version: 1\nsettings: {include_owner: false}\n", "other.yaml")
    configure(settings, PROFILE=other)
    assert get_setting("INCLUDE_OWNER") is False


@pytest.mark.parametrize(
    "text, message",
    [
        ("settings: {}\n", "version: 1"),
        ("version: 2\n", "version: 1"),
        ("version: 1\nextra: true\n", "unknown keys: extra"),
        ("version: 1\nsettings: {no_such_setting: 1}\n", "unknown setting 'no_such_setting'"),
        ("version: 1\nsettings: {INCLUDE_OWNER: true}\n", "unknown setting 'INCLUDE_OWNER'"),
        ("version: 1\nsettings: {profile: other.yaml}\n", "cannot set 'profile'"),
        ("version: 1\nmodules: tests.profile_module\n", "list of dotted module names"),
        ("- version\n", "must be a mapping"),
        ("version: [1\n", "not valid YAML or JSON"),
    ],
)
def test_malformed_profiles_fail_loudly(settings, tmp_path, text, message):
    configure(settings, PROFILE=write(tmp_path, text))
    with pytest.raises(ImproperlyConfigured, match=message):
        get_setting("INCLUDE_OWNER")


def test_missing_profile_and_module_fail_loudly(settings, tmp_path):
    configure(settings, PROFILE=str(tmp_path / "missing.yaml"))
    with pytest.raises(ImproperlyConfigured, match="cannot be read"):
        get_setting("INCLUDE_OWNER")
    configure(settings, PROFILE=write(tmp_path, "version: 1\nmodules: [no.such.module]\n"))
    with pytest.raises(ImproperlyConfigured, match="'no.such.module' cannot be imported"):
        profile.import_modules()


# FRONTMATTER_FIELDS


@pytest.fixture
def home(db):
    return Site.objects.get(is_default_site=True).root_page


@pytest.fixture
def news(home):
    locale = Locale.get_default()
    climate = NewsCategory.objects.create(name="Climate")
    climate.labels.create(locale=locale, name="Climate justice")
    energy = NewsCategory.objects.create(name="Energy")
    page = home.add_child(
        instance=NewsPage(
            title="Divest now",
            slug="divest-now",
            author_name="Sam Organiser",
            published_at=datetime.datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
            first_published_at=datetime.datetime(2026, 9, 1, 8, 30, tzinfo=UTC),
            canonical_url="https://campaign.example.org/divest",
        )
    )
    page.categories.set([energy, climate])
    page.save_revision().publish()
    return page


POST_FIELDS = {
    "*": {"canonical": "canonical_url"},
    "testapp.NewsPage": {
        "author": "byline",
        "date": "published_at",
        "categories": {"each": "categories", "label": "label_for(locale)"},
    },
}


def test_frontmatter_fields_map_page_attributes(settings, news):
    configure(settings, FRONTMATTER_FIELDS=POST_FIELDS)
    data = build(news)
    assert data["author"] == "Sam Organiser"
    assert data["date"] == "2026-03-01T09:00:00Z"
    assert data["categories"] == ["Climate justice", "Energy"]
    assert data["canonical"] == "https://campaign.example.org/divest"
    assert data["permalink"] == news.full_url
    keys = list(data)
    assert keys.index("date") == 1  # Replaced in place.
    assert keys.index("canonical") < keys.index("author") < keys.index("timestamp")


def test_empty_mapped_values_keep_the_built_in(settings, news):
    NewsPage.objects.filter(pk=news.pk).update(author_name="", published_at=None, canonical_url="")
    news.refresh_from_db()
    news.categories.set([])
    news.save_revision().publish()
    configure(settings, FRONTMATTER_FIELDS=POST_FIELDS)
    data = build(news)
    assert data["date"] == "2026-09-01T08:30:00Z"
    assert not {"author", "categories", "canonical"} & set(data)


def test_page_types_without_the_attribute_get_nothing(settings, home):
    article = home.add_child(instance=ArticlePage(title="Plain", slug="plain"))
    article.save_revision().publish()
    configure(settings, FRONTMATTER_FIELDS=POST_FIELDS)
    data = build(article)
    assert not {"author", "categories", "canonical"} & set(data)


def test_a_plain_method_is_never_called(settings, news):
    configure(settings, FRONTMATTER_FIELDS={"testapp.NewsPage": {"gone": "delete"}})
    with pytest.raises(ImproperlyConfigured, match="is a method on NewsPage"):
        build(news)
    assert NewsPage.objects.filter(pk=news.pk).exists()


def test_identity_keys_are_never_mapped(settings, news):
    configure(settings, FRONTMATTER_FIELDS={"*": {"permalink": "canonical_url"}})
    assert build(news)["permalink"] == news.full_url


# EXCLUDE_WHEN


def test_exclude_when_makes_pages_ineligible_in_both_policy_paths(settings, news):
    site = Site.objects.get(is_default_site=True)
    configure(settings, EXCLUDE_WHEN=["hide_from_search"])
    assert ExportPolicy().is_eligible(news)
    NewsPage.objects.filter(pk=news.pk).update(hide_from_search=True)
    page = NewsPage.objects.get(pk=news.pk)
    assert not ExportPolicy().is_eligible(page)
    snapshot = SiteSnapshot(site)
    assert not ExportPolicy(snapshot).is_eligible(snapshot.pages[news.pk])
    assert ExportPolicy(snapshot).is_eligible(snapshot.pages[site.root_page_id])


def test_exclude_when_reads_properties_as_well_as_fields(settings, news):
    site = Site.objects.get(is_default_site=True)
    configure(settings, EXCLUDE_WHEN=["byline"])
    assert not ExportPolicy().is_eligible(news)
    snapshot = SiteSnapshot(site)
    assert not ExportPolicy(snapshot).is_eligible(snapshot.pages[news.pk])
    assert ExportPolicy(snapshot).is_eligible(snapshot.pages[site.root_page_id])


@pytest.mark.django_db(transaction=True)
@pytest.mark.export_lifecycle
def test_ticking_the_field_withdraws_an_existing_export(setup, settings):
    writer, site, home = setup
    configure(settings, EXCLUDE_WHEN=["hide_from_search"])
    page = home.add_child(
        instance=NewsPage(
            title="Hidden later",
            slug="hidden-later",
            body=[("paragraph", "<p>Soon hidden.</p>")],
        )
    )
    page.save_revision().publish()
    assert writer.exists("example.org/hidden-later.md")
    page.hide_from_search = True
    page.save_revision().publish()
    assert not writer.exists("example.org/hidden-later.md")
    assert page.pk not in {entry["id"] for entry in entries(writer)}


# IMAGE_RENDITIONS


@pytest.fixture
def image(db, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return get_image_model().objects.create(title="Rally", file=get_test_image_file())


class PhotoBlock(blocks.StructBlock):
    photo = ImageChooserBlock()


def test_images_use_the_outermost_listed_blocks_rendition(settings, image):
    photo = PhotoBlock()
    value = photo.to_python({"photo": image.pk})
    assert ".original." in render_block(photo, value, {})
    configure(settings, IMAGE_RENDITIONS={f"{__name__}.PhotoBlock": "fill-40x30"})
    assert ".fill-40x30." in render_block(photo, value, {})
    assert ".original." in render_block(ImageChooserBlock(), image, {})
    configure(
        settings,
        IMAGE_RENDITIONS={
            "wagtail.images.blocks.ImageChooserBlock": "width-20",
            f"{__name__}.PhotoBlock": "fill-40x30",
        },
    )
    assert ".fill-40x30." in render_block(photo, value, {})  # The block's own template.
    assert ".width-20." in render_block(ImageChooserBlock(), image, {})


def test_a_page_can_set_the_rendition_for_images_its_hooks_render(settings, image, news):
    configure(settings, IMAGE_RENDITIONS={"sandbox.testapp.models.NewsPage": "fill-40x30"})
    with enclosing(news):
        assert ".fill-40x30." in render_block(ImageChooserBlock(), image, {})
    assert ".original." in render_block(ImageChooserBlock(), image, {})


def test_rendition_keys_match_subclasses(settings, image):
    configure(settings, IMAGE_RENDITIONS={"wagtail.blocks.struct_block.StructBlock": "width-20"})
    photo = PhotoBlock()
    assert ".width-20." in render_block(photo, photo.to_python({"photo": image.pk}), {})


# Checks


@pytest.mark.parametrize(
    "key, value",
    [
        ("FRONTMATTER_FIELDS", {"testapp.NewsPage": {"id": "pk"}}),
        ("FRONTMATTER_FIELDS", {"testapp.NewsPage": {"author": "byline()"}}),
        ("FRONTMATTER_FIELDS", {"testapp.NewsPage": {"tags": {"each": "categories", "x": "y"}}}),
        ("FRONTMATTER_FIELDS", {"NewsPage": {"author": "byline"}}),
        ("EXCLUDE_WHEN", "hide_from_search"),
        ("EXCLUDE_WHEN", ["_private"]),
        ("IMAGE_RENDITIONS", {"app.blocks.Image": "fill-wide"}),
        ("IMAGE_RENDITIONS", {"app.blocks.Image": 600}),
    ],
)
def test_malformed_settings_are_reported(settings, key, value):
    configure(settings, **{key: value})
    errors = [
        m for m in checks.check_settings_shape(None) if m.id == "wagtail_markdown_agents.E005"
    ]
    assert [key in message.msg for message in errors] == [True]


def test_well_formed_settings_pass(settings):
    configure(
        settings,
        FRONTMATTER_FIELDS=POST_FIELDS,
        EXCLUDE_WHEN=["hide_from_search"],
        IMAGE_RENDITIONS={f"{__name__}.PhotoBlock": "fill-1600x900"},
    )
    assert checks.check_settings_shape(None) == []


def test_missing_page_types_and_attributes_are_warned(settings):
    configure(
        settings,
        FRONTMATTER_FIELDS={
            "testapp.NoSuchPage": {"author": "byline"},
            "testapp.NewsPage": {"author": "bylin", "categories": {"each": "categorys"}},
        },
    )
    messages = checks.check_settings_shape(None)
    assert {m.id for m in messages} == {"wagtail_markdown_agents.W004"}
    warnings = [m.msg for m in messages]
    assert len(warnings) == 3
    assert any("'testapp.NoSuchPage'" in msg for msg in warnings)
    assert any("testapp.NewsPage.bylin" in msg for msg in warnings)
    assert any("testapp.NewsPage.categorys" in msg for msg in warnings)
