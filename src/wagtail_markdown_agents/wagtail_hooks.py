"""Native admin registration and the shared site-wide reporting permission."""

from django.contrib.auth.models import Permission
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.action_menu import ActionMenuItem
from wagtail.admin.menu import MenuItem

from .page_settings import can_manage_page_settings, page_settings
from .reports import REPORT_PERMISSION, AgentAccessReportView


class PageSettingsMenuItem(ActionMenuItem):
    name = "action-agentmd-settings"
    label = _("Markdown settings")
    icon_name = "doc-full"

    def is_shown(self, context):
        page = context.get("page")
        return bool(
            context["view"] == "edit"
            and page
            and page.pk
            and can_manage_page_settings(context["request"].user, page)
        )

    def get_url(self, context):
        return reverse("agentmd_page_settings", args=[context["page"].pk])


@hooks.register("register_page_action_menu_item")
def register_page_settings_menu_item():
    return PageSettingsMenuItem(order=100)


@hooks.register("register_admin_urls")
def register_page_settings_url():
    return [
        path("pages/<int:page_id>/markdown/", page_settings, name="agentmd_page_settings"),
    ]


class AgentAccessMenuItem(MenuItem):
    def is_shown(self, request):
        return (
            request.user.is_active
            and request.user.has_perm("wagtailadmin.access_admin")
            and REPORT_PERMISSION.user_has_permission(request.user, "view")
        )


@hooks.register("register_admin_urls")
def register_report_url():
    return [path("reports/agent-access/", AgentAccessReportView.as_view(), name="agentmd_report")]


@hooks.register("register_reports_menu_item")
def register_report_menu_item():
    return AgentAccessMenuItem(
        _("Agent access"),
        reverse("agentmd_report"),
        icon_name="globe",
        order=700,
    )


@hooks.register("register_permissions")
def register_permissions():
    return Permission.objects.filter(
        content_type__app_label="wagtail_markdown_agents",
        codename="view_agentaccess",
    )
