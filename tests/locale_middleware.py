"""A project's own language middleware, as sites with custom URL prefixes have."""

from django.middleware.locale import LocaleMiddleware


class ProjectLocaleMiddleware(LocaleMiddleware):
    pass
