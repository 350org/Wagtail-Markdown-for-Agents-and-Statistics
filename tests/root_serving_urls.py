"""The package can also share a root include with existing HTML routes."""

from django.http import HttpResponse
from django.urls import include, path

urlpatterns = [
    path("", include("wagtail_markdown_agents.urls")),
    path("existing/", lambda request: HttpResponse("Existing HTML")),
]
