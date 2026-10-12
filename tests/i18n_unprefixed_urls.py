"""Translated roots with the default language unprefixed: ``/article/`` and ``/fr/article/``."""

from django.conf.urls.i18n import i18n_patterns
from django.urls import include, path

urlpatterns = [path("markdown/", include("wagtail_markdown_agents.urls"))]
urlpatterns += i18n_patterns(path("", include("wagtail.urls")), prefix_default_language=False)
