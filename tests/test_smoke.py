"""Bootstrap smoke tests: the app installs, wires, and migrates cleanly.

Real behaviour tests arrive with epics E2–E4.
"""

import pytest
from django.apps import apps

from wagtail_markdown_agents import OKF_VERSION, __version__
from wagtail_markdown_agents.settings import DEFAULTS, get_setting


def test_app_is_installed():
    assert apps.is_installed("wagtail_markdown_agents")


def test_version_and_okf_pin():
    assert __version__
    assert OKF_VERSION == "0.1"


def test_settings_defaults_roundtrip():
    for name in DEFAULTS:
        get_setting(name)
    with pytest.raises(KeyError):
        get_setting("NOT_A_SETTING")


@pytest.mark.django_db
def test_middleware_is_wired_and_passes_through(client):
    response = client.get("/admin/login/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_page_agent_settings_model():
    from wagtail.models import Page

    from wagtail_markdown_agents.models import PageAgentSettings

    root = Page.objects.get(depth=1)
    settings_row = PageAgentSettings.objects.create(page=root, excluded=True)
    assert settings_row.excluded is True
    assert root.agent_markdown_settings.pk == settings_row.pk
