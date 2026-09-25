"""Keep export off the network when block templates use embeds (#14).

A block template's ``{% embed %}`` tag, or ``{{ value }}`` for an
``EmbedBlock``, asks Wagtail for the embed. Wagtail returns an embed it has
stored and otherwise calls the provider's oEmbed API, so export would depend on
a third party and could hang a publish. While the template fallback renders,
:func:`offline_embeds` leaves Wagtail no embed finders, so the provider
lookup fails as an unsupported provider: an unexpired stored embed still
renders, and Wagtail's tag renders nothing for any other. A video player's
iframe converts to nothing anyway; an embed whose HTML carries text, such as a
quoted post, is exported only once Wagtail has stored it. A block renderer
that links the URL is how media reliably reaches the export.

Wagtail's own page rendering is unaffected: the guard applies only inside
:func:`offline_embeds`, in the current thread or task.
"""

from contextlib import contextmanager
from contextvars import ContextVar

from django.apps import apps

_offline = ContextVar("wagtail_markdown_agents_offline_embeds", default=False)


@contextmanager
def offline_embeds():
    """Within this block, embeds come only from Wagtail's stored embeds."""
    token = _offline.set(True)
    try:
        yield
    finally:
        _offline.reset(token)


def install() -> None:
    """Guard Wagtail's embed finders; called once from ``AppConfig.ready``.

    ``wagtail.embeds.embeds`` looks up ``get_finders`` when it is called in
    every supported Wagtail version, whereas ``get_finder_for_embed`` is bound
    as a default argument in some, so the finder list is the point to guard.
    """
    if not apps.is_installed("wagtail.embeds"):
        return
    from wagtail.embeds import embeds, finders

    if getattr(embeds.get_finders, "_agentmd_offline", False):
        return

    def get_finders():
        if _offline.get():
            return []
        return finders.get_finders()

    get_finders._agentmd_offline = True
    embeds.get_finders = get_finders
