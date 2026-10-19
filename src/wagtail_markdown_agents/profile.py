"""Site profiles: one site's package settings and integration code in one file.

A profile is a YAML or JSON file that a site turns on with a single setting::

    WAGTAIL_MARKDOWN_AGENTS = {"PROFILE": "path/to/profile.yaml"}

``PROFILE`` is a file path (relative paths are resolved against ``BASE_DIR``)
or the dotted name of a package containing a ``profile.yaml``, such as a
profile shipped in ``wagtail_markdown_agents.profiles``. Removing the setting
removes everything the profile adds.

File format::

    version: 1
    name: Example site            # for people; not used by the package
    settings:                     # any WAGTAIL_MARKDOWN_AGENTS key, in lower case
      page_fields: {...}
      frontmatter_fields: {...}
      exclude_when: [...]
      image_renditions: {...}
      renderers: {...}
    modules:                      # optional Python modules imported at startup
      - myproject.markdown_profile

A setting in the profile replaces the package default, and the same key in
``WAGTAIL_MARKDOWN_AGENTS`` replaces the profile's value, whole. ``profile``
itself cannot be set from a profile.

``modules`` are imported during app startup, after the built-in renderers and
before each installed app's ``markdown_renderers`` module, so a project can
still override a profile's renderers. A module registers renderers and Wagtail
hooks at import time; if it defines ``ready()``, that is called once after the
import, for work such as connecting signal handlers.

An unreadable or malformed profile raises ``ImproperlyConfigured`` at startup.
"""

import importlib
import re
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from django.conf import settings as django_settings
from django.core.exceptions import ImproperlyConfigured
from django.core.signals import setting_changed

PROFILE_FILE = "profile.yaml"
TOP_LEVEL_KEYS = frozenset({"version", "name", "settings", "modules"})
VERSION = 1

_DOTTED = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*")


def configured() -> str | None:
    """The ``PROFILE`` value from Django settings, never from a profile."""
    overrides = getattr(django_settings, "WAGTAIL_MARKDOWN_AGENTS", {})
    if not isinstance(overrides, dict):
        return None
    return overrides.get("PROFILE")


def profile_settings() -> dict[str, Any]:
    """The active profile's settings with upper-case keys; empty without a profile."""
    reference = configured()
    return _load(reference)["settings"] if reference else {}


def profile_modules() -> list[str]:
    """Dotted names of the active profile's modules; empty without a profile."""
    reference = configured()
    return _load(reference)["modules"] if reference else []


def import_modules() -> None:
    """Import the active profile's modules and call each one's ``ready()``."""
    for name in profile_modules():
        try:
            module = importlib.import_module(name)
        except ImportError as exc:
            raise ImproperlyConfigured(
                f"Markdown profile module {name!r} cannot be imported: {exc}"
            ) from exc
        ready = getattr(module, "ready", None)
        if callable(ready):
            ready()


def resolve_path(reference: str) -> Path:
    """The profile file a ``PROFILE`` value names."""
    if not isinstance(reference, str) or not reference:
        raise ImproperlyConfigured("WAGTAIL_MARKDOWN_AGENTS['PROFILE'] must be a non-empty string")
    if _DOTTED.fullmatch(reference) and not reference.endswith((".yaml", ".yml", ".json")):
        try:
            return Path(str(resources.files(reference) / PROFILE_FILE))
        except (ImportError, TypeError) as exc:
            raise ImproperlyConfigured(
                f"Markdown profile package {reference!r} cannot be imported: {exc}"
            ) from exc
    path = Path(reference)
    if not path.is_absolute():
        path = Path(getattr(django_settings, "BASE_DIR", Path.cwd())) / path
    return path


@lru_cache(maxsize=8)
def _load(reference: str) -> dict[str, Any]:
    from .settings import DEFAULTS

    path = resolve_path(reference)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ImproperlyConfigured(f"Markdown profile {str(path)!r} cannot be read: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ImproperlyConfigured(
            f"Markdown profile {str(path)!r} is not valid YAML or JSON: {exc}"
        ) from exc
    where = f"Markdown profile {str(path)!r}"
    if not isinstance(data, dict):
        raise ImproperlyConfigured(f"{where} must be a mapping")
    unknown = sorted(set(data) - TOP_LEVEL_KEYS)
    if unknown:
        raise ImproperlyConfigured(f"{where} has unknown keys: {', '.join(map(str, unknown))}")
    if data.get("version") != VERSION:
        raise ImproperlyConfigured(f"{where} must declare 'version: {VERSION}'")

    raw_settings = data.get("settings") or {}
    if not isinstance(raw_settings, dict):
        raise ImproperlyConfigured(f"{where}: 'settings' must be a mapping")
    profile = {}
    for key, value in raw_settings.items():
        name = key.upper() if isinstance(key, str) else key
        if not isinstance(key, str) or key != key.lower() or name not in DEFAULTS:
            raise ImproperlyConfigured(f"{where}: unknown setting {key!r}")
        if name == "PROFILE":
            raise ImproperlyConfigured(f"{where}: a profile cannot set 'profile'")
        profile[name] = value

    modules = data.get("modules") or []
    if not isinstance(modules, list) or not all(
        isinstance(name, str) and _DOTTED.fullmatch(name) for name in modules
    ):
        raise ImproperlyConfigured(f"{where}: 'modules' must be a list of dotted module names")
    return {"settings": profile, "modules": list(modules)}


def _clear_cache(*, setting, **kwargs):
    if setting == "WAGTAIL_MARKDOWN_AGENTS":
        _load.cache_clear()


setting_changed.connect(_clear_cache, dispatch_uid="wagtail_markdown_agents.profile")
