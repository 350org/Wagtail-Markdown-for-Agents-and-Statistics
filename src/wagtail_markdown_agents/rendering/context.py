"""Offline template context for block rendering (#12).

Generation runs from publish signals and management commands, so block
templates cannot rely on an editor's request or on whichever site happens to
be the default. The context is built from the published page and its site.
"""

from django.apps import apps


def render_context(page, site=None) -> dict:
    """Return the template context for rendering ``page``'s blocks without a request.

    Keys: ``page``, ``site`` (the page's own site unless one is given), ``locale``,
    and ``settings`` — Wagtail's settings proxy bound to that site, as the
    ``settings`` context processor would provide — when ``wagtail.contrib.settings``
    is installed. There is no ``request``; ``{% pageurl %}`` and ``{% image %}``
    work without one.
    """
    site = site or page.get_site()
    context = {"page": page, "site": site, "locale": page.locale}
    if apps.is_installed("wagtail.contrib.settings"):
        from wagtail.contrib.settings.context_processors import SettingProxy

        context["settings"] = SettingProxy(site)
    return context
