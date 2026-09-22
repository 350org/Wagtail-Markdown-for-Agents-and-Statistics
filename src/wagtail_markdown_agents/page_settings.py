"""The page-scoped admin form for opting out of Markdown export."""

from django import forms
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
from wagtail.admin import messages
from wagtail.admin.auth import require_admin_access
from wagtail.models import Page

from .models import PageAgentSettings


class PageExclusionForm(forms.Form):
    excluded = forms.BooleanField(
        required=False,
        label=_("Exclude this page from Markdown export"),
        help_text=_("This affects only this page. Its HTML and child pages are unchanged."),
    )


def can_manage_page_settings(user, page):
    if not user.is_active or not user.has_perm("wagtailadmin.access_admin"):
        return False
    permissions = page.permissions_for_user(user)
    return permissions.can_edit() and not permissions.page_locked()


def set_page_excluded(page, excluded):
    """Change only exclusion, preserving metadata and avoiding no-op lifecycle work."""
    current = PageAgentSettings.objects.filter(page=page).values_list("excluded", flat=True).first()
    if bool(current) != excluded:
        PageAgentSettings.objects.update_or_create(page=page, defaults={"excluded": excluded})


@require_admin_access
@require_http_methods(["GET", "POST"])
def page_settings(request, page_id):
    page = get_object_or_404(Page, pk=page_id).specific
    if not can_manage_page_settings(request.user, page):
        raise PermissionDenied

    row = PageAgentSettings.objects.filter(page=page).first()
    form = PageExclusionForm(
        request.POST if request.method == "POST" else None,
        initial={"excluded": row.excluded if row else False},
    )
    if request.method == "POST" and form.is_valid():
        if form.has_changed():
            # Update only the checkbox, preserving concurrently edited frontmatter.
            # Model signals perform the existing immediate exclusion lifecycle.
            set_page_excluded(page, form.cleaned_data["excluded"])
        messages.success(request, _("Markdown settings saved."))
        return redirect("wagtailadmin_pages:edit", page.pk)

    return render(
        request,
        "wagtail_markdown_agents/page_settings.html",
        {"page": page, "form": form},
    )
