"""A host-chosen prefix must work without replacing existing application routes."""

from django.http import HttpResponse
from django.urls import include, path

urlpatterns = [
    path("existing/", lambda request: HttpResponse("Existing route")),
    path("exports/v1/", include("wagtail_markdown_agents.urls")),
]
