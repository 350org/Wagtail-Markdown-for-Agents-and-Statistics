"""Keep component tests' explicit export operations isolated from lifecycle IO."""

import pytest
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from wagtail.models import Page, PageViewRestriction
from wagtail.signals import (
    page_published,
    page_slug_changed,
    page_unpublished,
    post_page_move,
    pre_page_move,
)

from wagtail_markdown_agents import handlers
from wagtail_markdown_agents.models import PageAgentSettings


@pytest.fixture(autouse=True)
def isolate_lifecycle_receivers(request):
    if request.node.get_closest_marker("export_lifecycle"):
        yield
        return
    # Component fixtures publish/delete CMS pages to exercise guards directly.
    # Lifecycle integration tests opt into the real AppConfig connections.
    page_published.disconnect(dispatch_uid="agentmd.page_published")
    page_unpublished.disconnect(dispatch_uid="agentmd.page_unpublished")
    pre_page_move.disconnect(dispatch_uid="agentmd.pre_page_move")
    post_page_move.disconnect(dispatch_uid="agentmd.post_page_move")
    page_slug_changed.disconnect(dispatch_uid="agentmd.page_slug_changed")
    pre_delete.disconnect(sender=Page, dispatch_uid="agentmd.page_pre_delete")
    for sender in (PageViewRestriction, PageAgentSettings):
        for signal, name in (
            (pre_save, "pre_save"),
            (post_save, "post_save"),
            (post_delete, "post_delete"),
        ):
            signal.disconnect(sender=sender, dispatch_uid=f"agentmd.{sender.__name__}.{name}")
    try:
        yield
    finally:
        handlers.connect()


WTRX_PROFILE = "wagtail_markdown_agents.profiles.wtrx"


@pytest.fixture(scope="session", autouse=True)
def wtrx_profile_code():
    """Register the 350.org profile's renderers, hooks and handlers once, as startup does.

    The profile's settings stay off; tests that exercise the profile turn them
    on with the ``wtrx_profile`` fixture.
    """
    from django.test import override_settings

    from wagtail_markdown_agents import profile

    with override_settings(WAGTAIL_MARKDOWN_AGENTS={"PROFILE": WTRX_PROFILE}):
        profile.import_modules()


@pytest.fixture
def wtrx_profile(settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {**settings.WAGTAIL_MARKDOWN_AGENTS, "PROFILE": WTRX_PROFILE}
