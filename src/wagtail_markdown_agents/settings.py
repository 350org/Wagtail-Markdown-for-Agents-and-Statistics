"""Package settings.

All configuration lives under a single ``WAGTAIL_MARKDOWN_AGENTS`` dict in the
host project's Django settings, merged over these defaults. Runtime-editable
settings (agent-list deltas, UA toggle) arrive in v0.2 via
``wagtail.contrib.settings``; see docs/design.md §Settings split.
"""

from typing import Any

from django.conf import settings as django_settings

DEFAULTS: dict[str, Any] = {
    # Page types eligible for export/serving. None = all non-root page types.
    "PAGE_TYPES": None,
    # Alias into Django's STORAGES dict used for the export tree. None = a
    # FileSystemStorage rooted at BASE_DIR / "markdown_export".
    "STORAGE": None,
    # {"app_label.Model": ["body", ...]} — body fields per page type.
    # None = auto-detect StreamField/RichTextField fields in definition order.
    "PAGE_FIELDS": None,
    # Optional plain-text introduction in llms.txt; no inferred homepage copy.
    "LLMS_TXT_DESCRIPTION": "",
    # Dotted-path overrides for block renderers: {"app.blocks.QuoteBlock": "path.to.fn"}.
    "RENDERERS": {},
    # Routine lifecycle regeneration; immediate revocation is always enforced.
    "AUTO_GENERATE": True,
    # Negotiation triggers.
    "NEGOTIATE_QUERY_PARAM": True,  # ?output_format=md|markdown
    "NEGOTIATE_ACCEPT_HEADER": True,  # Accept: text/markdown
    "NEGOTIATE_USER_AGENT": True,  # UA-substring match against data/agents.py
    # Content-Signal response header value; empty string suppresses the header.
    "CONTENT_SIGNAL": "ai-input=yes, search=yes",
    # HTML discovery: Link alternate + Vary: Accept on eligible HTML 200 responses.
    "LINK_HEADER": True,
    # Seconds to cache discovery resolution per site/path/storage; 0 disables.
    "DISCOVERY_CACHE_TIMEOUT": 60,
    # Days of agent access statistics kept by agentmd_prune_stats (#36).
    "STATS_RETENTION_DAYS": 90,
    # Frontmatter toggles (parity with the WordPress plugin).
    "INCLUDE_HIERARCHY": False,
    "INCLUDE_OWNER": False,
    # Sites to export: "default" (v0.1) | "all" | [hostname, ...] (v0.2).
    "SITES": "default",
}


#: Settings that never change rendered documents; excluded from content fingerprints.
NON_CONTENT_SETTINGS = frozenset(
    {
        "LLMS_TXT_DESCRIPTION",
        "AUTO_GENERATE",
        "LINK_HEADER",
        "DISCOVERY_CACHE_TIMEOUT",
        "STATS_RETENTION_DAYS",
    }
)


def get_setting(name: str) -> Any:
    """Return a package setting, falling back to DEFAULTS."""
    overrides = getattr(django_settings, "WAGTAIL_MARKDOWN_AGENTS", {})
    if name not in DEFAULTS:
        raise KeyError(f"Unknown WAGTAIL_MARKDOWN_AGENTS setting: {name!r}")
    if not isinstance(overrides, dict):
        # Allow app startup and the other checks to finish so E004 can report
        # the malformed container through Django's system-check framework.
        return DEFAULTS[name]
    return overrides.get(name, DEFAULTS[name])
