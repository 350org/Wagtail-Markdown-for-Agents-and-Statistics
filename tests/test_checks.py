"""Configuration checks report middleware order, settings shape and route inclusion."""

import pytest
from django.core.checks import run_checks

from wagtail_markdown_agents import checks
from wagtail_markdown_agents.rendering.registry import apply_setting_overrides

SECURITY = "django.middleware.security.SecurityMiddleware"
COMMON = "django.middleware.common.CommonMiddleware"
SESSION = "django.contrib.sessions.middleware.SessionMiddleware"


def ids(messages):
    return [message.id for message in messages]


def test_sandbox_configuration_passes_every_package_check():
    messages = [m for m in run_checks() if m.id.startswith("wagtail_markdown_agents.")]
    assert messages == []


@pytest.mark.parametrize(
    "middleware,expected",
    [
        ([SECURITY, checks.MIDDLEWARE, SESSION, COMMON], []),
        ([checks.MIDDLEWARE], []),
        ([SECURITY, SESSION, COMMON], ["wagtail_markdown_agents.W001"]),
        ([], ["wagtail_markdown_agents.W001"]),
        ([checks.MIDDLEWARE, SECURITY, COMMON], ["wagtail_markdown_agents.E002"]),
        ([SECURITY, COMMON, checks.MIDDLEWARE], ["wagtail_markdown_agents.E003"]),
        (
            [COMMON, checks.MIDDLEWARE, SECURITY],
            ["wagtail_markdown_agents.E002", "wagtail_markdown_agents.E003"],
        ),
    ],
)
def test_middleware_order(settings, middleware, expected):
    settings.MIDDLEWARE = middleware
    assert ids(checks.check_middleware_order(None)) == expected


def test_unknown_keys_warn_and_non_dict_errors(settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"LINK_HEADERS": True, "AUTO_GENERATE": False}
    messages = checks.check_settings_shape(None)
    assert ids(messages) == ["wagtail_markdown_agents.W002"]
    assert "'LINK_HEADERS'" in messages[0].msg and "LINK_HEADER" in messages[0].hint
    settings.WAGTAIL_MARKDOWN_AGENTS = ["AUTO_GENERATE"]
    assert ids(checks.check_settings_shape(None)) == ["wagtail_markdown_agents.E004"]


@pytest.mark.parametrize("config", [None, ["AUTO_GENERATE"], "invalid", 42])
@pytest.mark.parametrize("urlconf", ["sandbox.urls", "tests.no_export_urls"])
def test_non_dict_settings_survive_startup_and_all_checks(settings, config, urlconf):
    settings.WAGTAIL_MARKDOWN_AGENTS = config
    settings.ROOT_URLCONF = urlconf
    # AppConfig.ready() applies renderer settings before checks can run.
    apply_setting_overrides()
    assert "wagtail_markdown_agents.E004" in ids(run_checks())


@pytest.mark.parametrize(
    "key,value",
    [
        ("AUTO_GENERATE", "yes"),
        ("LINK_HEADER", 1),
        ("NEGOTIATE_QUERY_PARAM", None),
        ("NEGOTIATE_ACCEPT_HEADER", "true"),
        ("NEGOTIATE_USER_AGENT", 0),
        ("INCLUDE_HIERARCHY", "no"),
        ("INCLUDE_OWNER", []),
        ("CONTENT_SIGNAL", "ai-input=yes\r\nX-Injected: 1"),
        ("CONTENT_SIGNAL", None),
        ("STATS_RETENTION_DAYS", 0),
        ("STATS_RETENTION_DAYS", -1),
        ("STATS_RETENTION_DAYS", True),
        ("STATS_RETENTION_DAYS", "90"),
        ("DISCOVERY_CACHE_TIMEOUT", -1),
        ("DISCOVERY_CACHE_TIMEOUT", "60"),
        ("LLMS_TXT_DESCRIPTION", None),
        ("PAGE_TYPES", "testapp.ArticlePage"),
        ("PAGE_TYPES", ["ArticlePage"]),
        ("PAGE_FIELDS", ["body"]),
        ("PAGE_FIELDS", {"testapp.ArticlePage": "body"}),
        ("RENDERERS", ["x"]),
        ("RENDERERS", {"a.B": None}),
        ("SITES", "example.org"),
        ("SITES", [1]),
    ],
)
def test_wrong_shapes_error_and_name_the_key(settings, key, value):
    settings.WAGTAIL_MARKDOWN_AGENTS = {key: value}
    messages = checks.check_settings_shape(None)
    assert ids(messages) == ["wagtail_markdown_agents.E005"]
    assert f"[{key!r}]" in messages[0].msg


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"STATS_RETENTION_DAYS": 30, "DISCOVERY_CACHE_TIMEOUT": 0.5, "LINK_HEADER": False},
        {"PAGE_TYPES": ["testapp.ArticlePage"], "PAGE_FIELDS": {"testapp.ArticlePage": ["body"]}},
        {"RENDERERS": {"a.B": "c.d"}, "SITES": ["example.org"], "CONTENT_SIGNAL": ""},
        {"SITES": "all", "LLMS_TXT_DESCRIPTION": "Intro"},
    ],
)
def test_valid_shapes_pass(settings, config):
    settings.WAGTAIL_MARKDOWN_AGENTS = config
    assert checks.check_settings_shape(None) == []


def test_routes_missing_warns_or_errors_with_query_negotiation_off(settings):
    assert checks.check_export_routes(None) == []
    settings.ROOT_URLCONF = "tests.no_export_urls"
    assert ids(checks.check_export_routes(None)) == ["wagtail_markdown_agents.W003"]
    settings.WAGTAIL_MARKDOWN_AGENTS = {"NEGOTIATE_QUERY_PARAM": False}
    assert ids(checks.check_export_routes(None)) == ["wagtail_markdown_agents.E006"]
    settings.ROOT_URLCONF = "tests.serving_urls"
    assert checks.check_export_routes(None) == []
