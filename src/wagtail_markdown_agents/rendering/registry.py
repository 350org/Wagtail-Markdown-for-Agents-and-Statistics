"""Block-renderer registry.

Dispatches on block class (walking the MRO), with block name as an override
key. Renderers are plain functions ``(block, value, context) -> str``,
registered via the decorator below — typically in a per-app
``markdown_renderers.py`` module, autodiscovered like ``wagtail_hooks.py``.

Renderers registered for Wagtail's generic containers (StructBlock, StreamBlock,
ListBlock) rank below a block's custom template, so a project's templated
container keeps its presentation; see :func:`resolve` (decision D12).

Implementation tracked in epic E2 (Markdown rendering engine).
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.template import TemplateDoesNotExist
from django.template.loader import select_template
from django.utils.module_loading import autodiscover_modules, import_string

from ..settings import get_setting

logger = logging.getLogger(__name__)

RendererFunc = Callable[..., str]

_class_renderers: dict[type, RendererFunc] = {}
_name_renderers: dict[str, RendererFunc] = {}


def register_renderer(
    block_class: type | None = None,
    *,
    block_name: str | None = None,
) -> Callable[[RendererFunc], RendererFunc]:
    """Register a Markdown renderer for a block class or block name.

    Name registrations win over class registrations; class dispatch walks
    the MRO so a renderer for a base block covers subclasses. The last
    registration for a key wins; replacing another project's renderer logs a
    warning naming both, so two apps claiming the same block is never silent.
    Overriding a built-in renderer is the documented path and stays quiet.
    """
    if (block_class is None) == (block_name is None):
        raise TypeError("Pass exactly one of block_class or block_name")

    def decorator(fn: RendererFunc) -> RendererFunc:
        if block_name is not None:
            _register(_name_renderers, block_name, fn, label=repr(block_name))
        else:
            _register(_class_renderers, block_class, fn, label=_dotted(block_class))
        return fn

    return decorator


class BlockRenderError(Exception):
    """A block's template failed to render, so its content would be lost.

    Raised rather than exporting a page with the block silently missing; the
    original exception is chained as ``__cause__``.
    """

    def __init__(self, block, exc: Exception):
        cls = type(block)
        super().__init__(f"Could not render {cls.__module__}.{cls.__qualname__}: {exc}")
        self.block = block


def render_fallback(block, value, context) -> str:
    """Render the block through its own template, then convert the HTML.

    Blocks without a template use Wagtail's basic HTML rendering. ``context``
    becomes the template's parent context; see ``rendering.context.render_context``.

    A block with no value renders nothing — Wagtail's basic rendering would
    otherwise print ``None`` (#85). StaticBlocks are the exception: they never
    have a value, and their template is their content.
    """
    from wagtail.blocks import StaticBlock

    from .html import convert_html

    if value is None and not isinstance(block, StaticBlock):
        return ""
    try:
        html = block.render(value, context=dict(context))
    except Exception as exc:
        raise BlockRenderError(block, exc) from exc
    return convert_html(str(html), block, context)


def resolve(block: object, block_name: str | None = None, value=None, context=None) -> RendererFunc:
    """Return the renderer for a block instance.

    Precedence (D12, agreed 24 September 2026):

    1. a renderer registered for ``block_name``;
    2. the nearest registered class in ``type(block).__mro__``, other than
       Wagtail's generic containers;
    3. :func:`render_fallback` when the block has a custom template;
    4. the nearest registered generic container (structural recursion);
    5. :func:`render_fallback`.

    ``value`` and ``context`` are passed to ``block.get_template()``, so a
    template chosen per value is honoured, as Wagtail does when rendering.
    """
    if block_name is not None and block_name in _name_renderers:
        return _name_renderers[block_name]
    mro = type(block).__mro__
    for cls in mro:
        if cls in _class_renderers and cls not in _generic_containers():
            return _class_renderers[cls]
    if has_custom_template(block, value, context):
        return render_fallback
    for cls in mro:
        if cls in _class_renderers:
            return _class_renderers[cls]
    return render_fallback


def has_custom_template(block, value=None, context=None) -> bool:
    """Whether the block renders through a template that is not Wagtail's own.

    A template that resolves to a file shipped inside the ``wagtail`` package,
    such as ``ImageBlock``'s default, is not custom. A project template, or a
    project copy overriding a Wagtail template path, is. A template that cannot
    be found counts as custom, so the fallback reports the error instead of
    the block's content silently changing shape.
    """
    template = block.get_template(value, context=None if context is None else dict(context))
    if not template:
        return False
    names = [template] if isinstance(template, str) else list(template)
    try:
        origin = select_template(names).origin.name
    except TemplateDoesNotExist:
        return True
    return not _is_wagtail_file(origin)


def _is_wagtail_file(path) -> bool:
    import wagtail

    try:
        return Path(path).resolve().is_relative_to(Path(wagtail.__file__).resolve().parent)
    except (OSError, TypeError, ValueError):
        return False


def _generic_containers() -> frozenset[type]:
    from wagtail import blocks

    return frozenset(
        {
            blocks.BaseStructBlock,
            blocks.StructBlock,
            blocks.BaseStreamBlock,
            blocks.StreamBlock,
            blocks.ListBlock,
        }
    )


def autodiscover() -> None:
    """Import every installed app's ``markdown_renderers`` module, then apply settings.

    Called from ``AppConfig.ready()``. Built-in renderers register first, then
    project modules, then settings, so each layer overrides the one before
    regardless of ``INSTALLED_APPS`` order.
    """
    from . import blocks  # noqa: F401 — importing registers the built-ins

    autodiscover_modules("markdown_renderers")
    apply_setting_overrides()


def apply_setting_overrides() -> None:
    """Register ``WAGTAIL_MARKDOWN_AGENTS["RENDERERS"]`` entries.

    Keys are dotted paths to block classes, values dotted paths to renderer
    functions. Class registrations cover subclasses, as with the decorator.
    """
    for block_path, renderer_path in get_setting("RENDERERS").items():
        block_class = _import_renderer_setting(block_path)
        if not isinstance(block_class, type):
            raise ImproperlyConfigured(
                f"WAGTAIL_MARKDOWN_AGENTS['RENDERERS'] key {block_path!r} is not a class"
            )
        renderer = _import_renderer_setting(renderer_path)
        if not callable(renderer):
            raise ImproperlyConfigured(
                f"WAGTAIL_MARKDOWN_AGENTS['RENDERERS'] value {renderer_path!r} "
                f"for {block_path!r} is not callable"
            )
        _class_renderers[block_class] = renderer


def _import_renderer_setting(path: str) -> Any:
    try:
        return import_string(path)
    except ImportError as exc:
        raise ImproperlyConfigured(
            f"WAGTAIL_MARKDOWN_AGENTS['RENDERERS'] cannot import {path!r}: {exc}"
        ) from exc


def _register(table: dict, key: Any, fn: RendererFunc, *, label: str) -> None:
    previous = table.get(key)
    if previous is not None and previous is not fn and not _is_built_in(previous):
        logger.warning(
            "Markdown renderer for %s registered by %s replaces %s",
            label,
            _dotted(fn),
            _dotted(previous),
        )
    table[key] = fn


def _is_built_in(fn: RendererFunc) -> bool:
    return getattr(fn, "__module__", "").startswith("wagtail_markdown_agents.")


def _dotted(obj: Any) -> str:
    return f"{obj.__module__}.{obj.__qualname__}"
