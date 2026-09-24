"""Block coverage: how each StreamField block on exportable page types renders (#18).

Walks block definitions, not page content, so it needs no database rows. The
renderer for each block comes from :func:`registry.resolve`, called with the
same block name export passes, so the report always matches export. Children
are followed only where export follows them: through the built-in Struct,
Stream, List and TypedTable renderers. A templated container's children are
rendered by its template, so they are not listed under it.

Templates chosen per value (``get_template(value)``) are reported for an empty
value; a block that switches templates by value can resolve differently in export.
"""

from dataclasses import dataclass, field

from django.template import TemplateDoesNotExist
from django.template.loader import select_template
from wagtail.fields import StreamField
from wagtail.models import get_page_models

from ..export.policy import page_type_enabled
from . import blocks as built_ins
from . import registry
from .page import selected_fields, unsupported_reason
from .registry import _dotted, _is_built_in, has_custom_template, render_fallback, resolve

#: Resolved paths, in report order.
BUILT_IN = "built-in renderer"
PROJECT = "project renderer"
CUSTOM_TEMPLATE = "custom template"
DEFAULT_TEMPLATE = "Wagtail default HTML"
PATHS = (PROJECT, BUILT_IN, CUSTOM_TEMPLATE, DEFAULT_TEMPLATE)

_RECURSING = {
    built_ins.render_struct: "struct",
    built_ins.render_stream: "stream",
    built_ins.render_list: "list",
    built_ins.render_typed_table: "columns",
}


@dataclass
class BlockEntry:
    """One distinct block definition, merged across every place it is used.

    ``name`` is the name export dispatches with: the child's name in a
    StreamBlock or StructBlock, ``None`` for a ListBlock item.
    """

    name: str | None
    block_class: str
    path: str
    renderer: str
    by_name: bool = False
    template: str = ""
    locations: list[str] = field(default_factory=list)

    @property
    def key(self) -> tuple:
        return (self.name, self.block_class, self.renderer, self.template)


@dataclass
class CoverageReport:
    page_types: list[str]
    skipped: dict[str, str]
    entries: list[BlockEntry]

    def by_path(self) -> dict[str, list[BlockEntry]]:
        grouped = {path: [] for path in PATHS}
        for entry in self.entries:
            grouped[entry.path].append(entry)
        return grouped


def page_models() -> tuple[list, dict[str, str]]:
    """Exportable page models, and the enabled types skipped with their reason."""
    models, skipped = [], {}
    for model in get_page_models():
        if model._meta.abstract or not page_type_enabled(model):
            continue
        reason = unsupported_reason(model)
        if reason:
            if any(isinstance(f, StreamField) for f in model._meta.get_fields()):
                skipped[model._meta.label] = reason
            continue
        models.append(model)
    return sorted(models, key=lambda m: m._meta.label), skipped


def build_report(models=None) -> CoverageReport:
    """Walk every exported StreamField of ``models`` (default: :func:`page_models`)."""
    skipped = {}
    if models is None:
        models, skipped = page_models()
    streams = [
        (f"{model._meta.label}.{model_field.name}", model_field.stream_block)
        for model in models
        for model_field in selected_fields(model)
        if isinstance(model_field, StreamField)
    ]
    return CoverageReport([m._meta.label for m in models], skipped, walk_streams(streams))


def walk_streams(streams) -> list[BlockEntry]:
    """Entries for every block reachable from ``(location, stream_block)`` pairs."""
    entries: dict[tuple, BlockEntry] = {}
    for location, stream_block in streams:
        _walk_stream(stream_block, location, entries, ())
    return sorted(entries.values(), key=lambda e: (e.name or "", e.block_class, e.renderer))


def _walk_stream(stream_block, location, entries, ancestors):
    for name, child in stream_block.child_blocks.items():
        _visit(child, name, f"{location} > {name}", entries, ancestors)


def _visit(block, name, location, entries, ancestors):
    renderer = resolve(block, name)
    entry = _entry(block, name, renderer)
    entries.setdefault(entry.key, entry).locations.append(location)
    kind = _RECURSING.get(renderer)
    if kind is None or id(block) in ancestors:
        return
    ancestors = (*ancestors, id(block))
    if kind == "list":
        _visit(block.child_block, None, f"{location} > item", entries, ancestors)
    elif kind == "stream":
        _walk_stream(block, location, entries, ancestors)
    elif kind == "columns":
        # Table cells render through their column's block without a name.
        for column_name, child in block.child_blocks.items():
            _visit(child, None, f"{location} > {column_name}", entries, ancestors)
    else:
        for child_name, child in block.child_blocks.items():
            _visit(child, child_name, f"{location} > {child_name}", entries, ancestors)


def _entry(block, name, renderer) -> BlockEntry:
    entry = BlockEntry(name, _dotted(type(block)), "", _dotted(renderer))
    if renderer is render_fallback:
        entry.template = _template_name(block)
        entry.path = CUSTOM_TEMPLATE if has_custom_template(block) else DEFAULT_TEMPLATE
    else:
        entry.by_name = name is not None and registry._name_renderers.get(name) is renderer
        entry.path = BUILT_IN if _is_built_in(renderer) else PROJECT
    return entry


def _template_name(block) -> str:
    template = block.get_template(None, context=None)
    if not template:
        return ""
    names = [template] if isinstance(template, str) else list(template)
    try:
        return select_template(names).origin.template_name
    except TemplateDoesNotExist:
        return f"{names[0]} (not found)"
