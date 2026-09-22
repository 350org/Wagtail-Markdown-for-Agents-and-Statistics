"""Opt-in page editor integration, without fields on the host page model."""

from django import forms
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from wagtail.admin.forms import WagtailAdminPageForm
from wagtail.admin.panels import FieldPanel
from wagtail.models import Page

from .models import PageAgentSettings
from .page_settings import can_manage_page_settings, set_page_excluded

EXCLUSION_FIELD = "agent_markdown_excluded"


class AgentMarkdownPageForm(WagtailAdminPageForm):
    """Stage checkbox changes for a successful page revision, never for preview."""

    agent_markdown_excluded = forms.BooleanField(
        required=False,
        label=_("Exclude this page from Markdown export"),
        help_text=_(
            "Applies when you save, even as a draft. Only this page's Markdown is affected; "
            "its HTML and child pages are unchanged. Clearing this checkbox still requires "
            "eligible published content and an export generation run."
        ),
    )

    def __init__(self, *args, **kwargs):
        self._agentmd_user = kwargs.get("for_user")
        super().__init__(*args, **kwargs)
        if EXCLUSION_FIELD not in (self._meta.fields or ()):
            # A host's custom edit handler may deliberately omit the panel.
            self.fields.pop(EXCLUSION_FIELD, None)
            return

        self.initial[EXCLUSION_FIELD] = bool(
            self.instance.pk
            and PageAgentSettings.objects.filter(page_id=self.instance.pk, excluded=True).exists()
        )
        user = self._agentmd_user
        allowed = False
        if user and user.is_active and user.has_perm("wagtailadmin.access_admin"):
            if self.instance.pk:
                allowed = can_manage_page_settings(user, self.instance)
            elif self.parent_page:
                allowed = self.parent_page.permissions_for_user(user).can_add_subpage()
        self.fields[EXCLUSION_FIELD].disabled = not allowed

    def save(self, commit=True):
        page = super().save(commit=commit)
        field = self.fields.get(EXCLUSION_FIELD)
        if field and not field.disabled and EXCLUSION_FIELD in self.changed_data:
            page._agentmd_pending_exclusion = (
                self.cleaned_data[EXCLUSION_FIELD],
                self._agentmd_user,
            )
        return page


class AgentMarkdownPanelMixin:
    """Put before ``Page`` in a page model's bases to enable the Settings checkbox.

    Custom forms should inherit AgentMarkdownPageForm; custom Settings panels or
    edit handlers must include FieldPanel("agent_markdown_excluded").
    """

    base_form_class = AgentMarkdownPageForm
    settings_panels = Page.settings_panels + [FieldPanel(EXCLUSION_FIELD)]

    def save_revision(self, *args, **kwargs):
        pending = getattr(self, "_agentmd_pending_exclusion", None)
        if pending is None:
            return super().save_revision(*args, **kwargs)

        excluded, user = pending
        # Check persisted permissions/locks, not values from an edited revision.
        saved_page = Page.objects.get(pk=self.pk).specific
        if not can_manage_page_settings(user, saved_page):
            raise PermissionDenied

        with transaction.atomic():
            revision = super().save_revision(*args, **kwargs)
            set_page_excluded(saved_page, excluded)
        del self._agentmd_pending_exclusion
        return revision
