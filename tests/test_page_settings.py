"""Page-scoped exclusion controls, permissions and real export transitions (#17)."""

import pytest
from django.contrib.auth.models import Group, Permission
from django.test import Client
from django.urls import reverse
from sandbox.testapp.models import ArticlePage
from wagtail.models import GroupPagePermission, Page, PageViewRestriction

from tests import test_lifecycle
from tests.test_indexes import article, read
from wagtail_markdown_agents.models import ExportArtifact, PageAgentSettings

pytestmark = pytest.mark.django_db
setup = test_lifecycle.setup


@pytest.fixture
def page():
    return Page.get_first_root_node().add_child(
        instance=ArticlePage(title="Settings page", slug="settings-page")
    )


def url(page):
    return reverse("agentmd_page_settings", args=[page.pk])


def test_get_cancel_and_unchanged_save_do_not_create_settings(client, admin_user, page):
    client.force_login(admin_user)
    response = client.get(url(page))
    assert response.status_code == 200
    assert not response.context["form"]["excluded"].value()
    assert reverse("wagtailadmin_pages:edit", args=[page.pk]) in response.content.decode()
    assert "csrfmiddlewaretoken" in response.content.decode()
    assert not PageAgentSettings.objects.filter(page=page).exists()
    assert client.post(url(page), {}).status_code == 302
    assert not PageAgentSettings.objects.filter(page=page).exists()


def test_save_preserves_metadata_and_ignores_other_fields(client, admin_user, page):
    client.force_login(admin_user)
    row = PageAgentSettings.objects.create(page=page, extra_frontmatter={"campaign": "public"})
    response = client.post(
        url(page),
        {"excluded": "on", "page": 1, "extra_frontmatter": "{}", "next": "https://evil.test/"},
    )
    assert response.status_code == 302
    assert response.url == reverse("wagtailadmin_pages:edit", args=[page.pk])
    row.refresh_from_db()
    assert row.excluded and row.extra_frontmatter == {"campaign": "public"}
    assert not PageAgentSettings.objects.filter(page_id=1).exists()
    response = client.get(url(page))
    assert response.context["form"]["excluded"].value() is True
    assert "Markdown settings saved" in response.content.decode()
    assert client.post(url(page), {}).status_code == 302
    row.refresh_from_db()
    assert not row.excluded and row.extra_frontmatter == {"campaign": "public"}


@pytest.mark.parametrize(
    "role,allowed",
    [
        ("anonymous", False),
        ("staff", False),
        ("admin_only", False),
        ("other_branch", False),
        ("publisher", False),
        ("editor", True),
        ("inactive", False),
        ("superuser", True),
    ],
)
def test_menu_and_direct_url_permissions(client, django_user_model, page, role, allowed):
    from wagtail_markdown_agents.wagtail_hooks import register_page_settings_menu_item

    user = django_user_model.objects.create_user(
        username=role,
        is_staff=role == "staff",
        is_superuser=role == "superuser",
        is_active=role != "inactive",
    )
    if role not in {"anonymous", "staff"}:
        user.user_permissions.add(Permission.objects.get(codename="access_admin"))
    if role in {"editor", "other_branch", "publisher", "inactive"}:
        group = Group.objects.create(name="Page settings editors")
        user.groups.add(group)
        target = page
        if role == "other_branch":
            target = page.get_parent().add_child(instance=Page(title="Other", slug="other"))
        GroupPagePermission.objects.create(
            group=group,
            page=target,
            permission=Permission.objects.get(
                content_type__app_label="wagtailcore",
                codename="publish_page" if role == "publisher" else "change_page",
            ),
        )
    if role != "anonymous":
        client.force_login(user)
    response = client.get(url(page))
    assert response.status_code == (200 if allowed else 302)
    if role in {"admin_only", "other_branch", "publisher"}:
        assert response.url == reverse("wagtailadmin_home")
    item = register_page_settings_menu_item()
    context = {"request": response.wsgi_request, "view": "edit", "page": page}
    assert item.is_shown(context) is allowed
    if allowed:
        assert item.get_url(context) == url(page)
    response = client.post(url(page), {"excluded": "on"})
    assert PageAgentSettings.objects.filter(page=page, excluded=True).exists() is allowed


def test_action_only_appears_on_saved_page_editor(client, admin_user, page):
    from wagtail_markdown_agents.wagtail_hooks import register_page_settings_menu_item

    client.force_login(admin_user)
    response = client.get(reverse("wagtailadmin_pages:edit", args=[page.pk]))
    assert response.status_code == 200
    assert url(page) in response.content.decode()
    item = register_page_settings_menu_item()
    for view in ["create", "revisions_revert"]:
        assert not item.is_shown({"request": response.wsgi_request, "view": view, "page": page})


def test_lock_is_rechecked_on_submission(client, admin_user, django_user_model, page):
    from wagtail_markdown_agents.wagtail_hooks import register_page_settings_menu_item

    client.force_login(admin_user)
    assert client.get(url(page)).status_code == 200
    page.locked = True
    page.locked_by = django_user_model.objects.create_user(username="locker")
    page.save(update_fields=["locked", "locked_by"])
    response = client.post(url(page), {"excluded": "on"})
    assert response.status_code == 302 and response.url == reverse("wagtailadmin_home")
    assert not PageAgentSettings.objects.filter(page=page).exists()
    assert not register_page_settings_menu_item().is_shown(
        {"request": response.wsgi_request, "view": "edit", "page": page}
    )
    assert client.get(url(page)).url == reverse("wagtailadmin_home")


def test_csrf_missing_page_and_http_methods(admin_user, page):
    client = Client(enforce_csrf_checks=True)
    client.force_login(admin_user)
    assert client.post(url(page), {"excluded": "on"}).status_code == 403
    assert not PageAgentSettings.objects.filter(page=page).exists()
    assert client.get(url(page)).status_code == 200
    token = client.cookies["csrftoken"].value
    assert (
        client.post(url(page), {"excluded": "on", "csrfmiddlewaretoken": token}).status_code == 302
    )
    assert PageAgentSettings.objects.get(page=page).excluded
    assert client.get(reverse("agentmd_page_settings", args=[999999])).status_code == 404
    assert client.put(url(page), HTTP_X_CSRFTOKEN=token).status_code == 405


@pytest.mark.export_lifecycle
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("auto", [False, True])
def test_save_withdraws_and_restores_only_eligible_published_content(
    setup,
    client,
    admin_user,
    settings,
    auto,
):
    writer, site, home = setup
    page = article(home, "parent")
    child = article(page, "child")
    client.force_login(admin_user)
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "AUTO_GENERATE": auto}
    target = "example.org/parent/index.md"
    assert writer.exists(target)
    response = client.post(url(page), {"excluded": "on"}, HTTP_HOST="example.org")
    assert response.status_code == 302
    assert not ExportArtifact.objects.filter(page_id=page.pk).exists()
    if writer.exists(target):
        # Eligible children retain a directory index without the excluded page body.
        assert "parent body." not in read(writer, target)
    assert not PageAgentSettings.objects.filter(page=child, excluded=True).exists()
    assert client.get("/parent/", HTTP_HOST="example.org").status_code == 200
    page.title = "PRIVATE DRAFT"
    page.save_revision()
    assert client.post(url(page), {}, HTTP_HOST="example.org").status_code == 302
    assert writer.exists(target) is auto
    if auto:
        assert "PRIVATE DRAFT" not in read(writer, target)
    assert client.post(url(page), {"excluded": "on"}, HTTP_HOST="example.org").status_code == 302
    PageViewRestriction.objects.create(page=page, restriction_type="login")
    assert client.post(url(page), {}, HTTP_HOST="example.org").status_code == 302
    assert not writer.exists(target)


@pytest.mark.export_lifecycle
@pytest.mark.django_db(transaction=True)
def test_unchanged_save_does_not_regenerate(setup, client, admin_user, monkeypatch):
    writer, site, home = setup
    page = article(home, "unchanged")
    PageAgentSettings.objects.create(page=page, excluded=True)
    client.force_login(admin_user)
    monkeypatch.setattr(PageAgentSettings, "save", lambda *a, **kw: pytest.fail("Saved again"))
    assert client.post(url(page), {"excluded": "on"}, HTTP_HOST="example.org").status_code == 302
