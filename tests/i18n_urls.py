"""One Wagtail site serving translated roots at language-prefixed page URLs."""

from django.conf.urls.i18n import i18n_patterns
from django.urls import include, path

urlpatterns = [path("markdown/", include("wagtail_markdown_agents.urls"))]
urlpatterns += i18n_patterns(path("", include("wagtail.urls")))
