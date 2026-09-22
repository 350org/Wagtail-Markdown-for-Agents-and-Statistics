"""Django system checks (#19/#29): storage, middleware order, settings shape, routes.

Checks read configuration only. They never query the database, touch storage
or generate exports, so they are safe in every ``manage.py`` command.

Messages: ``E001`` unusable export storage; ``W001`` middleware not installed;
``E002``/``E003`` middleware before ``SecurityMiddleware`` or after
``CommonMiddleware``; ``E004`` ``WAGTAIL_MARKDOWN_AGENTS`` is not a dict;
``W002`` unknown key; ``E005`` a key with the wrong shape; ``W003`` public routes
not included; ``E006`` public routes not included while query negotiation is
disabled, so no Markdown URL exists.
"""

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register
from django.core.exceptions import ImproperlyConfigured
from django.urls import NoReverseMatch, reverse

from .export.storage import resolve_storage
from .public_urls import NAMESPACE
from .settings import DEFAULTS, get_setting

MIDDLEWARE = "wagtail_markdown_agents.middleware.AgentMarkdownMiddleware"
SECURITY_MIDDLEWARE = "django.middleware.security.SecurityMiddleware"
COMMON_MIDDLEWARE = "django.middleware.common.CommonMiddleware"
ROUTES_HINT = (
    "Include 'wagtail_markdown_agents.urls' before Wagtail's catch-all, for example "
    "path('markdown/', include('wagtail_markdown_agents.urls'))."
)
BOOLEAN_SETTINGS = (
    "AUTO_GENERATE",
    "NEGOTIATE_QUERY_PARAM",
    "NEGOTIATE_ACCEPT_HEADER",
    "NEGOTIATE_USER_AGENT",
    "LINK_HEADER",
    "INCLUDE_HIERARCHY",
    "INCLUDE_OWNER",
)


@register(Tags.files)
def check_export_storage(app_configs, **kwargs):
    try:
        resolve_storage()
    except (ImproperlyConfigured, TypeError, ValueError) as exc:
        return [Error(str(exc), id="wagtail_markdown_agents.E001")]
    return []


@register(Tags.compatibility)
def check_middleware_order(app_configs, **kwargs):
    middleware = list(getattr(settings, "MIDDLEWARE", None) or ())
    if MIDDLEWARE not in middleware:
        return [
            Warning(
                "AgentMarkdownMiddleware is not in MIDDLEWARE, so content negotiation at "
                "page URLs and HTML discovery headers are disabled.",
                hint=f"Add {MIDDLEWARE!r} after SecurityMiddleware and before CommonMiddleware.",
                id="wagtail_markdown_agents.W001",
            )
        ]
    messages = []
    position = middleware.index(MIDDLEWARE)
    if SECURITY_MIDDLEWARE in middleware and middleware.index(SECURITY_MIDDLEWARE) > position:
        messages.append(
            Error(
                "AgentMarkdownMiddleware must come after SecurityMiddleware.",
                hint="Security redirects and headers must apply before Markdown is served.",
                id="wagtail_markdown_agents.E002",
            )
        )
    if COMMON_MIDDLEWARE in middleware and middleware.index(COMMON_MIDDLEWARE) < position:
        messages.append(
            Error(
                "AgentMarkdownMiddleware must come before CommonMiddleware.",
                hint="Negotiated requests must be answered before slash-appending redirects.",
                id="wagtail_markdown_agents.E003",
            )
        )
    return messages


@register(Tags.compatibility)
def check_settings_shape(app_configs, **kwargs):
    config = getattr(settings, "WAGTAIL_MARKDOWN_AGENTS", {})
    if not isinstance(config, dict):
        return [Error("WAGTAIL_MARKDOWN_AGENTS must be a dict.", id="wagtail_markdown_agents.E004")]
    messages = [
        Warning(
            f"Unknown WAGTAIL_MARKDOWN_AGENTS key {key!r} is ignored.",
            hint=f"Known keys: {', '.join(sorted(DEFAULTS))}.",
            id="wagtail_markdown_agents.W002",
        )
        for key in config
        if key not in DEFAULTS
    ]
    for key in BOOLEAN_SETTINGS:
        if not isinstance(get_setting(key), bool):
            messages.append(_shape(key, "True or False"))
    if not _header_value(get_setting("CONTENT_SIGNAL")):
        messages.append(
            _shape("CONTENT_SIGNAL", "a header value without control characters ('' omits it)")
        )
    if not _positive_int(get_setting("STATS_RETENTION_DAYS")):
        messages.append(_shape("STATS_RETENTION_DAYS", "a positive whole number of days"))
    if not _non_negative_number(get_setting("DISCOVERY_CACHE_TIMEOUT")):
        messages.append(_shape("DISCOVERY_CACHE_TIMEOUT", "a number of seconds, 0 or more"))
    if not isinstance(get_setting("LLMS_TXT_DESCRIPTION"), str):
        messages.append(_shape("LLMS_TXT_DESCRIPTION", "a string"))
    if get_setting("PAGE_TYPES") is not None and not _labels(get_setting("PAGE_TYPES")):
        messages.append(_shape("PAGE_TYPES", "None or a list of 'app_label.ModelName' strings"))
    if get_setting("PAGE_FIELDS") is not None and not _field_map(get_setting("PAGE_FIELDS")):
        messages.append(
            _shape("PAGE_FIELDS", "None or {'app_label.ModelName': ['field', ...]} in body order")
        )
    if not _string_map(get_setting("RENDERERS")):
        messages.append(_shape("RENDERERS", "{'dotted.path.BlockClass': 'dotted.path.renderer'}"))
    sites = get_setting("SITES")
    if sites not in ("default", "all") and not _strings(sites):
        messages.append(_shape("SITES", "'default', 'all' or a list of hostnames"))
    return messages


@register(Tags.urls)
def check_export_routes(app_configs, **kwargs):
    try:
        reverse(f"{NAMESPACE}:export", kwargs={"export_path": "index.md"})
    except NoReverseMatch:
        if not get_setting("NEGOTIATE_QUERY_PARAM"):
            return [
                Error(
                    "NEGOTIATE_QUERY_PARAM is disabled and wagtail_markdown_agents.urls is not "
                    "included, so no Markdown URL can be advertised or retrieved.",
                    hint=ROUTES_HINT,
                    id="wagtail_markdown_agents.E006",
                )
            ]
        return [
            Warning(
                "wagtail_markdown_agents.urls is not included; the explicit export, llms.txt "
                "and manifest.json routes are unavailable.",
                hint=ROUTES_HINT,
                id="wagtail_markdown_agents.W003",
            )
        ]
    return []


def _shape(key, expected):
    return Error(
        f"WAGTAIL_MARKDOWN_AGENTS[{key!r}] must be {expected}.", id="wagtail_markdown_agents.E005"
    )


def _header_value(value):
    return isinstance(value, str) and not any(ord(char) < 32 or ord(char) == 127 for char in value)


def _positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _non_negative_number(value):
    return isinstance(value, int | float) and not isinstance(value, bool) and value >= 0


def _strings(value):
    return isinstance(value, list | tuple) and all(isinstance(item, str) for item in value)


def _labels(value):
    return _strings(value) and all(item.count(".") == 1 for item in value)


def _field_map(value):
    return isinstance(value, dict) and all(
        isinstance(label, str) and label.count(".") == 1 and _strings(names)
        for label, names in value.items()
    )


def _string_map(value):
    return isinstance(value, dict) and all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    )
