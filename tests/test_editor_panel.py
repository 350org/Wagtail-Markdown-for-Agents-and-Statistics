"""Opt-in editor checkbox behaviour through real Wagtail page forms (#18)."""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from sandbox.testapp.models import ArticlePage, MarkdownArticlePage
from wagtail.admin.panels import ObjectList
from wagtail.models import Page

from tests import test_lifecycle
from wagtail_markdown_agents.models import PageAgentSettings
from wagtail_markdown_agents.panels import AgentMarkdownPageForm

pytestmark = pytest.mark.django_db
FIELD = "agent_markdown_excluded"
setup = test_lifecycle.setup


@pytest.fixture
def page():
    page = Page.get_first_root_node().add_child(
        instance=MarkdownArticlePage(title="Panel page", slug="panel-page", live=False)
    )
    page.save_revision()
    return page


def page_form(page, user, *, excluded=False, title="Updated", **kwargs):
    form_class = page.get_edit_handler().get_form_class()
    return form_class(
        data={
            "title": title,
            "slug": page.slug,
            "body-count": "0",
            FIELD: "on" if excluded else "",
        },
        instance=page,
        for_user=user,
        **kwargs,
    )


def test_opt_in_form_and_initial_value(page, admin_user):
    form_class = page.get_edit_handler().get_form_class()
    assert issubclass(form_class, AgentMarkdownPageForm)
    assert FIELD not in ArticlePage.get_edit_handler().get_form_class().base_fields
    assert not form_class(instance=page, for_user=admin_user)[FIELD].value()
    row = PageAgentSettings.objects.create(page=page, excluded=True)
    assert form_class(instance=page, for_user=admin_user)[FIELD].value()
    row.delete()
    assert FIELD not in {field.name for field in page._meta.get_fields()}


def test_preview_and_form_save_do_not_write_until_revision(page, admin_user):
    form = page_form(page, admin_user, excluded=True)
    assert form.is_valid(), form.errors
    edited = form.save(commit=False)
    assert not PageAgentSettings.objects.filter(page=page).exists()
    revision = edited.save_revision(user=admin_user)
    assert PageAgentSettings.objects.get(page=page).excluded
    assert FIELD not in revision.content


def test_failed_revision_and_invalid_form_do_not_change_exclusion(page, admin_user):
    # An invalid title is reliably rejected across supported Wagtail versions.
    invalid = page_form(page, admin_user, excluded=True, title="")
    assert not invalid.is_valid()
    assert not PageAgentSettings.objects.filter(page=page).exists()
    form = page_form(page, admin_user, excluded=True)
    assert form.is_valid(), form.errors
    edited = form.save(commit=False)
    edited.title = ""
    with pytest.raises(ValidationError):
        edited.save_revision(user=admin_user)
    assert not PageAgentSettings.objects.filter(page=page).exists()


def test_permissions_rechecked_at_revision_save(page, admin_user):
    form = page_form(page, admin_user, excluded=True)
    assert form.is_valid(), form.errors
    edited = form.save(commit=False)
    Page.objects.filter(pk=page.pk).update(locked=True)
    with pytest.raises(PermissionDenied):
        edited.save_revision(user=admin_user)
    assert not PageAgentSettings.objects.filter(page=page).exists()


def test_no_user_cannot_forge_checkbox(page):
    form = page_form(page, None, excluded=True)
    assert form.fields[FIELD].disabled
    assert form.is_valid(), form.errors
    form.save(commit=False).save_revision()
    assert not PageAgentSettings.objects.filter(page=page).exists()


def test_omitted_panel_does_not_clear_existing_exclusion(page, admin_user):
    PageAgentSettings.objects.create(page=page, excluded=True)
    form_class = (
        ObjectList(ArticlePage.content_panels, base_form_class=AgentMarkdownPageForm)
        .bind_to_model(MarkdownArticlePage)
        .get_form_class()
    )
    form = form_class(
        data={"title": "Updated", "body-count": "0"}, instance=page, for_user=admin_user
    )
    assert FIELD not in form.fields
    assert form.is_valid(), form.errors
    form.save(commit=False).save_revision(user=admin_user)
    assert PageAgentSettings.objects.get(page=page).excluded


def test_unchanged_and_programmatic_revisions_preserve_settings(page, admin_user, monkeypatch):
    row = PageAgentSettings.objects.create(
        page=page, excluded=True, extra_frontmatter={"campaign": "keep"}
    )
    form = page_form(page, admin_user, excluded=True)
    assert form.is_valid(), form.errors
    with monkeypatch.context() as patch:
        patch.setattr(PageAgentSettings, "save", lambda *a, **kw: pytest.fail("Unchanged save"))
        form.save(commit=False).save_revision(user=admin_user)
        page.save_revision()
    row.refresh_from_db()
    assert row.excluded and row.extra_frontmatter == {"campaign": "keep"}


def test_editor_get_post_and_action_menu_share_record(page, admin_user, client):
    client.force_login(admin_user)
    edit_url = reverse("wagtailadmin_pages:edit", args=[page.pk])
    assert FIELD in client.get(edit_url).content.decode()
    response = client.post(
        edit_url,
        {"title": page.title, "slug": page.slug, "body-count": "0", FIELD: "on", "action-save": ""},
    )
    assert response.status_code == 302
    assert PageAgentSettings.objects.get(page=page).excluded
    response = client.get(reverse("agentmd_page_settings", args=[page.pk]))
    assert response.context["form"]["excluded"].value()
    client.post(reverse("agentmd_page_settings", args=[page.pk]), {})
    assert not client.get(edit_url).context["form"][FIELD].value()


def test_old_revision_reads_current_exclusion(page, admin_user):
    old_revision = page.get_latest_revision()
    PageAgentSettings.objects.create(page=page, excluded=True)
    old_page = old_revision.as_object()
    form = old_page.get_edit_handler().get_form_class()(instance=old_page, for_user=admin_user)
    assert form[FIELD].value() is True
    old_page.save_revision(user=admin_user)
    assert PageAgentSettings.objects.get(page=page).excluded


def test_real_preview_and_invalid_post_do_not_save(page, client, admin_user):
    client.force_login(admin_user)
    data = {"title": page.title, "slug": page.slug, "body-count": "0", FIELD: "on"}
    count = page.revisions.count()
    response = client.post(reverse("wagtailadmin_pages:preview_on_edit", args=[page.pk]), data)
    assert response.status_code == 200
    assert response.json()["is_valid"]
    assert page.revisions.count() == count
    assert not PageAgentSettings.objects.filter(page=page).exists()
    data["slug"] = "not a valid slug"
    response = client.post(reverse("wagtailadmin_pages:edit", args=[page.pk]), data)
    assert response.status_code == 200
    assert response.context["form"].errors
    assert not PageAgentSettings.objects.filter(page=page).exists()


def test_custom_form_composition_preserves_validation(page, admin_user):
    from wagtail.admin.forms import WagtailAdminPageForm

    class HostForm(WagtailAdminPageForm):
        def clean_title(self):
            if self.cleaned_data["title"] == "Forbidden":
                raise ValidationError("Host validation")
            return self.cleaned_data["title"]

    class CombinedForm(AgentMarkdownPageForm, HostForm):
        pass

    form_class = (
        ObjectList(
            MarkdownArticlePage.content_panels + MarkdownArticlePage.settings_panels,
            base_form_class=CombinedForm,
        )
        .bind_to_model(MarkdownArticlePage)
        .get_form_class()
    )
    form = form_class(
        data={"title": "Forbidden", "body-count": "0", FIELD: "on"},
        instance=page,
        for_user=admin_user,
    )
    assert not form.is_valid()
    assert "Host validation" in form.errors["title"]
    assert not PageAgentSettings.objects.filter(page=page).exists()


@pytest.mark.parametrize("publish", [False, True])
def test_create_checkbox_applies_before_publish(client, admin_user, publish):
    from wagtail.signals import page_published

    parent = Page.get_first_root_node()
    client.force_login(admin_user)
    observed = []

    def on_publish(sender, instance, **kwargs):
        observed.append(PageAgentSettings.objects.get(page=instance).excluded)

    page_published.connect(on_publish)
    try:
        response = client.post(
            reverse("wagtailadmin_pages:add", args=["testapp", "markdownarticlepage", parent.pk]),
            {
                "title": "Created",
                "slug": "created",
                "body-count": "0",
                FIELD: "on",
                "action-publish" if publish else "action-save": "1",
            },
        )
    finally:
        page_published.disconnect(on_publish)
    assert response.status_code == 302
    created = MarkdownArticlePage.objects.get(slug="created")
    assert PageAgentSettings.objects.get(page=created).excluded
    assert created.live is publish
    assert observed == ([True] if publish else [])


@pytest.mark.parametrize(
    "role,allowed", [("editor", True), ("publisher", False), ("other_branch", False)]
)
def test_checkbox_obeys_page_permissions(page, django_user_model, role, allowed):
    from django.contrib.auth.models import Group, Permission
    from wagtail.models import GroupPagePermission

    user = django_user_model.objects.create_user(username=role)
    user.user_permissions.add(Permission.objects.get(codename="access_admin"))
    group = Group.objects.create(name=role)
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
    form = page_form(page, user, excluded=True)
    assert form.fields[FIELD].disabled is not allowed
    assert form.is_valid(), form.errors
    form.save(commit=False).save_revision(user=user)
    assert PageAgentSettings.objects.filter(page=page, excluded=True).exists() is allowed


@pytest.mark.export_lifecycle
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("auto", [False, True])
def test_editor_draft_exclusion_and_restoration_use_published_content(
    setup, client, admin_user, settings, auto
):
    from tests.test_indexes import read
    from wagtail_markdown_agents.models import ExportArtifact

    writer, site, home = setup
    page = home.add_child(
        instance=MarkdownArticlePage(
            title="Published panel page", slug="panel", body=[("paragraph", "<p>Public body</p>")]
        )
    )
    page.save_revision().publish()
    assert writer.exists("example.org/panel.md")
    client.force_login(admin_user)
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "AUTO_GENERATE": auto}
    edit_url = reverse("wagtailadmin_pages:edit", args=[page.pk])
    data = {"title": "PRIVATE DRAFT", "slug": "panel", "body-count": "0", FIELD: "on"}
    assert client.post(edit_url, data, HTTP_HOST="example.org").status_code == 302
    assert not ExportArtifact.objects.filter(page_id=page.pk).exists()
    data[FIELD] = ""
    assert client.post(edit_url, data, HTTP_HOST="example.org").status_code == 302
    assert writer.exists("example.org/panel.md") is auto
    if auto:
        text = read(writer, "example.org/panel.md")
        assert "Public body" in text and "PRIVATE DRAFT" not in text
