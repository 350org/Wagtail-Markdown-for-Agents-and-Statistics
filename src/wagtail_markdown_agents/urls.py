"""Include before Wagtail's catch-all, for example at ``markdown/``."""

from django.urls import path, re_path

from . import views

app_name = "wagtail_markdown_agents"
urlpatterns = [
    path("llms.txt", views.export, {"export_path": "llms.txt"}, name="llms_txt"),
    path("manifest.json", views.export, {"export_path": "manifest.json"}, name="manifest"),
    re_path(r"^(?P<export_path>.+\.md)$", views.export, name="export"),
]
