"""A URLconf without the package routes: HTML routes and canonical page URLs only."""

from django.http import HttpResponse
from django.urls import include, path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls

urlpatterns = [
    path("existing/", lambda request: HttpResponse("<html>Existing route</html>")),
    path("admin/", include(wagtailadmin_urls)),
    path("", include(wagtail_urls)),
]
