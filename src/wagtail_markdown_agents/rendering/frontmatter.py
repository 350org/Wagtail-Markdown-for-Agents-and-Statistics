"""Frontmatter builder (#13).

:func:`build` returns the frontmatter mapping for a published page and
:func:`serialise` renders a mapping as a YAML block between ``---`` lines.

Fields, in order: ``title``; ``date`` and ``modified`` (``first_published_at``
and ``last_published_at`` as ISO 8601 in UTC with a ``Z`` suffix);
``permalink`` (``page.full_url``); ``type`` (``app_label.ModelName``);
``status`` (``published`` — only published content is exported); ``excerpt``
(``search_description``); ``id`` (the page's pk); with ``INCLUDE_HIERARCHY``,
``parent``, ``ancestors`` and ``children`` limited to pages the export policy
finds eligible, each as ``{title, permalink}``; with ``INCLUDE_OWNER``,
``owner`` as the owner's full name (never a username or email address);
``tags``, flat and de-duplicated across every tag field on the page; and
``timestamp``, the generation time in UTC. Built-in fields with no value are
omitted rather than written as ``null`` or ``""``.

Sources and precedence, lowest first:

1. the built-in fields;
2. ``PageAgentSettings.extra_frontmatter`` — an editor's keys override the
   built-ins, except the identity keys ``id``, ``type``, ``permalink``,
   ``status`` and ``timestamp``, which are kept and the clash logged;
3. the ``construct_markdown_frontmatter`` hook — code overrides anything.

Hooks (Wagtail's ``hooks.register``; run by ``order``, then registration order):

``construct_markdown_tags(tags, page, context)``
    Mutate the list of tag names in place, before it enters the frontmatter.
``construct_markdown_frontmatter(frontmatter, page, context)``
    Mutate the frontmatter dict in place. Runs last; return value ignored.

Every value — built-in, editor-supplied or from a hook, scalar or inside a
list or mapping — passes through one normaliser, :func:`normalise`, that
handles an explicit set of types and raises :class:`FrontmatterValueError`
naming the key for anything else. A model instance or other object can never
reach the YAML as a repr, and no key is ever derived by discarding part of a
name (ledger #84; the wp-mfa-plugin #20 and #21 failure classes).
"""

import datetime
import decimal
import logging
import uuid
from collections.abc import Callable, Mapping

import yaml
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.functional import Promise
from taggit.managers import TaggableManager
from taggit.models import TagBase
from wagtail import hooks
from wagtail.models import Locale, Page, Site

from ..models import PageAgentSettings
from ..settings import get_setting
from .context import render_context

logger = logging.getLogger(__name__)

TAGS_HOOK = "construct_markdown_tags"
FRONTMATTER_HOOK = "construct_markdown_frontmatter"

#: Keys an editor's ``extra_frontmatter`` may not override.
IDENTITY_KEYS = frozenset({"id", "type", "permalink", "status", "timestamp"})


class FrontmatterValueError(TypeError):
    """A frontmatter value has a type the normaliser does not handle."""

    def __init__(self, key: str, value: object):
        cls = type(value)
        where = f"key {key!r}" if key else "value"
        super().__init__(
            f"Frontmatter {where} has an unsupported type "
            f"{cls.__module__}.{cls.__qualname__}; normalise it in your hook"
        )
        self.key = key
        self.value = value


def build(page, context: dict | None = None, *, is_eligible: Callable | None = None) -> dict:
    """Return the normalised frontmatter mapping for ``page``.

    ``page`` should be the published page (the specific instance is looked up
    if needed). ``context`` is the offline render context, built from the page
    when not given. ``is_eligible`` decides which related pages hierarchy
    metadata may mention; it defaults to the export policy (#16).
    """
    page = page.specific
    if context is None:
        context = render_context(page)

    data = {
        "title": page.title,
        "date": page.first_published_at,
        "modified": page.last_published_at,
        "permalink": page.full_url,
        "type": f"{page._meta.app_label}.{type(page).__name__}",
        "status": "published",
        "excerpt": page.search_description,
        "id": page.pk,
    }
    if get_setting("INCLUDE_HIERARCHY"):
        data.update(_hierarchy(page, is_eligible or _policy_is_eligible))
    if get_setting("INCLUDE_OWNER"):
        data["owner"] = _owner_name(page)
    data["tags"] = flat_tags(page, context)
    data["timestamp"] = timezone.now()

    frontmatter = {key: value for key, value in data.items() if not _is_empty(value)}
    _merge_extra_frontmatter(frontmatter, page)
    for hook in hooks.get_hooks(FRONTMATTER_HOOK):
        hook(frontmatter, page, context)
    return {key: normalise(value, key) for key, value in frontmatter.items()}


def serialise(frontmatter: Mapping) -> str:
    """Render a frontmatter mapping as a YAML block between ``---`` lines.

    Safe YAML only: strings that look like booleans, numbers, dates or nulls
    are quoted so they read back as strings; multi-line strings use literal
    blocks; key order is kept.
    """
    body = yaml.dump(
        dict(frontmatter),
        Dumper=_Dumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=float("inf"),
    )
    return f"---\n{body}---\n"


def flat_tags(page, context: dict | None = None) -> list[str]:
    """Tag names from every tag field on ``page``, de-duplicated in field then tag order."""
    names: list[str] = []
    for field in page._meta.get_fields():
        if isinstance(field, TaggableManager):
            for tag in getattr(page, field.name).all():
                if tag.name not in names:
                    names.append(tag.name)
    for hook in hooks.get_hooks(TAGS_HOOK):
        hook(names, page, context)
    return names


def normalise(value, key: str = ""):
    """Return ``value`` as YAML-safe data, or raise :class:`FrontmatterValueError`.

    Handled: ``None``, ``bool``, ``int``, ``float``, ``str`` (lazy strings
    included), ``Decimal`` (as a string, keeping its precision), ``date``,
    ``time`` and ``datetime`` (ISO 8601; datetimes in UTC with ``Z``),
    ``UUID``, tags (their name), ``Page`` (``{title, permalink}``), ``Site``
    (its root URL), ``Locale`` (its language code), mappings with string keys,
    and lists, tuples, sets (sorted) and querysets — each item normalised with
    the same rules, so a scalar and a list item can never differ.
    """
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str | Promise):
        return str(value)
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, datetime.datetime):
        return _iso_utc(value)
    if isinstance(value, datetime.date | datetime.time):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, TagBase):
        return value.name
    if isinstance(value, Page):
        return {"title": value.title, "permalink": value.full_url}
    if isinstance(value, Site):
        return value.root_url
    if isinstance(value, Locale):
        return value.language_code
    if isinstance(value, Mapping):
        return {_mapping_key(k, key): normalise(v, _path(key, f".{k}")) for k, v in value.items()}
    if isinstance(value, set | frozenset):
        value = sorted(value, key=str)
    if isinstance(value, list | tuple | QuerySet):
        return [normalise(item, _path(key, f"[{index}]")) for index, item in enumerate(value)]
    raise FrontmatterValueError(key, value)


def _path(key: str, part: str) -> str:
    """Join a key path: ``links[1]``, ``meta.inner``, or just ``inner`` at the top level."""
    if key:
        return key + part
    return part[1:] if part.startswith(".") else part


def _mapping_key(candidate, parent_key: str) -> str:
    if isinstance(candidate, str):
        return candidate
    raise FrontmatterValueError(_path(parent_key, f".{candidate!r}"), candidate)


def _is_empty(value) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _merge_extra_frontmatter(frontmatter: dict, page) -> None:
    extra = (
        PageAgentSettings.objects.filter(page_id=page.pk)
        .values_list("extra_frontmatter", flat=True)
        .first()
    )
    if not extra:
        return
    if not isinstance(extra, Mapping):
        raise FrontmatterValueError("extra_frontmatter", extra)
    # JSON object order is not preserved by every database (notably JSONB).
    # Canonicalise editor data only; built-in and hook field order stays explicit.
    for key, value in _ordered_json(extra).items():
        if key in IDENTITY_KEYS and key in frontmatter:
            logger.warning(
                "extra_frontmatter on page %s sets identity key %r; the built-in value is kept",
                page.pk,
                key,
            )
            continue
        frontmatter[key] = value


def _ordered_json(value):
    if isinstance(value, Mapping):
        return {key: _ordered_json(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_ordered_json(item) for item in value]
    return value


def _hierarchy(page, is_eligible: Callable) -> dict:
    parent = page.get_parent()
    ancestors = [
        ancestor
        for ancestor in page.get_ancestors().specific()
        if ancestor.depth > 1 and is_eligible(ancestor)
    ]
    children = [child for child in page.get_children().live().specific() if is_eligible(child)]
    return {
        "parent": parent.specific
        if parent is not None and parent.depth > 1 and is_eligible(parent.specific)
        else None,
        "ancestors": ancestors,
        "children": children,
    }


def _policy_is_eligible(page) -> bool:
    from ..export.policy import ExportPolicy

    return ExportPolicy().is_eligible(page)


def _owner_name(page) -> str | None:
    """The owner's full name, or nothing: a username or email is not public."""
    owner = page.owner
    if owner is None:
        return None
    get_full_name = getattr(owner, "get_full_name", None)
    name = get_full_name().strip() if get_full_name else ""
    return name or None


def _iso_utc(value: datetime.datetime) -> str:
    if timezone.is_naive(value):
        value = timezone.make_aware(value)
    return value.astimezone(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class _Dumper(yaml.SafeDumper):
    pass


def _represent_str(dumper, data: str):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _represent_str)
