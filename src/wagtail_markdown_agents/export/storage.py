"""Storage resolution and identity; never use media/default storage implicitly."""

import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import FileSystemStorage, storages

from ..settings import get_setting


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def resolve_storage(alias=None):
    """Return (backend, alias, config hash); empty alias denotes our default."""
    if alias is None:
        alias = get_setting("STORAGE")
    if alias is None:
        alias = ""
    if not isinstance(alias, str):
        raise ImproperlyConfigured("WAGTAIL_MARKDOWN_AGENTS['STORAGE'] must name a STORAGES alias")
    if alias:
        if alias not in settings.STORAGES:
            raise ImproperlyConfigured(
                f"Markdown export storage alias {alias!r} is not in STORAGES"
            )
        return storages[alias], alias, digest({"alias": alias, "config": settings.STORAGES[alias]})
    if not getattr(settings, "BASE_DIR", None):
        raise ImproperlyConfigured(
            "Markdown exports require BASE_DIR or WAGTAIL_MARKDOWN_AGENTS['STORAGE']; "
            "configure an explicit export storage alias"
        )
    location = Path(settings.BASE_DIR).resolve() / "markdown_export"
    return FileSystemStorage(location=location), "", digest({"location": str(location)})
