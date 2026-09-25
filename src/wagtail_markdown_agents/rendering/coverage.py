"""Block coverage: how each StreamField block on exportable page types renders (#18).

Walks block definitions, not page content, so it needs no database rows. The
renderer for each block comes from :func:`registry.resolve`, called with the
same block name export passes, so the report always matches export. Children
are followed only where export follows them: through the built-in Struct,
Stream, List and TypedTable renderers. A templated container's children are
rendered by its template, so they are not listed under it.

Templates chosen per value (``get_template(value)``) are reported for an empty
value; a block that switches templates by value can resolve differently in export.

Blocks exported through a template get hints from reading its source, and the
source of any template it includes by literal name: tags and markup that make
the converted Markdown wrong or incomplete. They are hints, not proof: data
fetched in ``get_context()`` or templates chosen at render time are only seen
by rendering.

:func:`render_blocks` renders one published page block by block instead, with
the same offline context and dispatch as export, to catch what reading
definitions and templates cannot.

A report serialises to a JSON snapshot (:meth:`CoverageReport.as_json`) that a
later run can be compared against (:func:`compare`). The snapshot also records
the fields inside each container the walk does not enter, so a field added to a
templated or project-rendered block shows up as a change.
"""

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from django.template import TemplateDoesNotExist
from django.template.loader import get_template, select_template
from wagtail.fields import StreamField
from wagtail.models import get_page_models

from ..export.policy import page_type_enabled
from . import blocks as built_ins
from . import registry
from .page import selected_fields, unsupported_reason
from .registry import _dotted, _is_built_in, has_custom_template, render_fallback, resolve

#: Resolved paths, in report order, with their display labels.
PROJECT = "project"
BUILT_IN = "built_in"
CUSTOM_TEMPLATE = "custom_template"
DEFAULT_TEMPLATE = "default_html"
LABELS = {
    PROJECT: "Project renderer",
    BUILT_IN: "Built-in renderer",
    CUSTOM_TEMPLATE: "Custom template",
    DEFAULT_TEMPLATE: "Wagtail default HTML",
}

SNAPSHOT_FORMAT = 1
_NOT_FOUND = " (not found)"

HINT_INCLUDE_BLOCK = (
    "{% include_block %}: child blocks render through their templates, never their "
    "Markdown renderers"
)
HINT_EMBED = "{% embed %}: fetches from the embed provider during export"
HINT_REQUEST = "uses request, which is absent during export"
HINT_HIDDEN = "hidden markup (hidden, class hidden, aria-hidden, display: none): text is exported"
HINT_ELEMENTS = {
    "noscript": "<noscript>: its fallback text is exported",
    "dialog": "<dialog>: its content is exported where it appears, often duplicating the page",
}
HINT_DYNAMIC_INCLUDE = "includes a template chosen at render time, which is not checked"

_DJANGO_COMMENT = re.compile(r"\{#[^\n]*?#\}|\{%\s*comment\b.*?%\}.*?\{%\s*endcomment\s*%\}", re.S)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_TAG = re.compile(r"\{\{(.*?)\}\}|\{%(.*?)%\}", re.S)
_INCLUDE = re.compile(r"^\s*(?:include|extends)\s+(\S+)")
_START_TAG = re.compile(r"<([a-zA-Z][\w-]*)((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>")
_CLASS = re.compile(r"\bclass\s*=\s*([\"'])(.*?)\1", re.S)
_QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'")
_HIDDEN_ATTR = re.compile(r"(?<![\w-])hidden(?![\w-])")
_ARIA_HIDDEN = re.compile(r"\baria-hidden\s*=\s*[\"']?true", re.I)
_DISPLAY_NONE = re.compile(r"display\s*:\s*none", re.I)
#: Elements that carry no text, so hiding them from assistive technology leaks nothing.
_TEXTLESS = {"svg", "img", "path", "use", "i", "picture", "source"}

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
    StreamBlock or StructBlock, ``None`` for a ListBlock item or table cell.
    ``fields`` lists the nested fields of a container the walk does not enter,
    as ``"parent > child: dotted.Class"`` lines in declared order.
    """

    name: str | None
    block_class: str
    path: str
    renderer: str
    by_name: bool = False
    template: str = ""
    fields: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)

    @property
    def key(self) -> tuple:
        return (self.name, self.block_class, self.renderer, self.template, tuple(self.fields))


@dataclass
class CoverageReport:
    page_types: list[str]
    skipped: dict[str, str]
    entries: list[BlockEntry]

    def by_path(self) -> dict[str, list[BlockEntry]]:
        grouped = {path: [] for path in LABELS}
        for entry in self.entries:
            grouped[entry.path].append(entry)
        return grouped

    def as_json(self) -> dict:
        return {
            "format": SNAPSHOT_FORMAT,
            "page_types": self.page_types,
            "skipped": self.skipped,
            "blocks": [asdict(entry) for entry in self.entries],
        }


def compare(snapshot: dict, report: CoverageReport) -> list[str]:
    """Describe how ``report`` differs from an earlier :meth:`~CoverageReport.as_json`.

    Blocks are matched by name and class. Returns one line per difference, so
    an empty list means the coverage is unchanged.
    """
    if not isinstance(snapshot, dict) or snapshot.get("format") != SNAPSHOT_FORMAT:
        raise ValueError(f"not an agentmd_blocks snapshot (format {SNAPSHOT_FORMAT})")
    current = report.as_json()
    changes = _set_changes("page type", snapshot["page_types"], current["page_types"])
    before, after = _by_identity(snapshot["blocks"]), _by_identity(current["blocks"])
    for identity in sorted(before.keys() | after.keys(), key=lambda i: (i[0] or "", i[1])):
        label = f"{identity[0] or '(list item)'} {identity[1]}"
        old, new = before.get(identity, []), after.get(identity, [])
        if not old:
            changes.append(f"added: {label} ({LABELS[new[0]['path']]})")
        elif not new:
            changes.append(f"removed: {label}")
        elif len(old) == len(new) == 1:
            changes.extend(f"changed: {label}: {line}" for line in _entry_changes(old[0], new[0]))
        elif sorted(old, key=repr) != sorted(new, key=repr):
            changes.append(f"changed: {label}: {len(old)} definitions -> {len(new)}")
    return changes


def _by_identity(blocks) -> dict[tuple, list[dict]]:
    grouped = {}
    for block in blocks:
        grouped.setdefault((block["name"], block["block_class"]), []).append(block)
    return grouped


def _entry_changes(old: dict, new: dict) -> list[str]:
    lines = []
    for key in ("path", "renderer", "by_name", "template"):
        if old[key] != new[key]:
            before, after = old[key], new[key]
            if key == "path":
                before, after = LABELS[before], LABELS[after]
            lines.append(f"{key} {before!s} -> {after!s}")
    lines.extend(_set_changes("field", old["fields"], new["fields"]))
    lines.extend(_set_changes("hint", old["hints"], new["hints"]))
    if old["fields"] != new["fields"] and sorted(old["fields"]) == sorted(new["fields"]):
        lines.append("fields reordered")
    lines.extend(_set_changes("location", old["locations"], new["locations"]))
    return lines


def _set_changes(noun: str, before, after) -> list[str]:
    return [f"{noun} added: {item}" for item in after if item not in before] + [
        f"{noun} removed: {item}" for item in before if item not in after
    ]


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


def _entry(block, name, renderer, value=None, context=None) -> BlockEntry:
    entry = BlockEntry(name, _dotted(type(block)), "", _dotted(renderer))
    entry.template = _template_name(block, value, context)
    if renderer is render_fallback:
        custom = has_custom_template(block, value, context)
        entry.path = CUSTOM_TEMPLATE if custom else DEFAULT_TEMPLATE
        if entry.template and not entry.template.endswith(_NOT_FOUND):
            entry.hints = template_hints(entry.template)
    else:
        entry.by_name = name is not None and registry._name_renderers.get(name) is renderer
        entry.path = BUILT_IN if _is_built_in(renderer) else PROJECT
    if renderer not in _RECURSING:
        entry.fields = list(_fields(block, "", ()))
    return entry


def _fields(block, prefix, ancestors):
    """Yield ``"a > b: dotted.Class"`` for every block nested inside ``block``."""
    if id(block) in ancestors:
        return
    ancestors = (*ancestors, id(block))
    if hasattr(block, "child_blocks"):
        children = block.child_blocks.items()
    elif hasattr(block, "child_block"):
        children = [("item", block.child_block)]
    else:
        return
    for name, child in children:
        yield f"{prefix}{name}: {_dotted(type(child))}"
        yield from _fields(child, f"{prefix}{name} > ", ancestors)


def _template_name(block, value=None, context=None) -> str:
    template = block.get_template(value, context=None if context is None else dict(context))
    if not template:
        return ""
    names = [template] if isinstance(template, str) else list(template)
    try:
        return select_template(names).origin.template_name
    except TemplateDoesNotExist:
        return f"{names[0]}{_NOT_FOUND}"


def template_hints(template_name: str) -> list[str]:
    """Hints from a template's source and the templates it includes by literal name.

    A hint found in an included template names that template.
    """
    hints: list[str] = []
    seen: set[str] = set()

    def scan(name, via):
        if name in seen:
            return
        seen.add(name)
        source = _source(name)
        if source is None:
            _add(hints, f"{{% include %}} of {name}: template not found (in {via})")
            return
        suffix = f" (in {name})" if via else ""
        found, includes = _scan(source)
        for hint in found:
            _add(hints, hint + suffix)
        for included in includes:
            if included is None:
                _add(hints, HINT_DYNAMIC_INCLUDE + suffix)
            else:
                scan(included, name)

    scan(template_name, None)
    return hints


def _add(hints, hint):
    if hint not in hints:
        hints.append(hint)


def _source(name) -> str | None:
    try:
        origin = get_template(name).origin
    except TemplateDoesNotExist:
        return None
    loader = getattr(origin, "loader", None)
    if loader is not None:
        return loader.get_contents(origin)
    return Path(origin.name).read_text(encoding="utf-8")


def _scan(source: str) -> tuple[list[str], list[str | None]]:
    """Hints in one template's source, and the names it includes (``None`` if dynamic)."""
    source = _DJANGO_COMMENT.sub("", source)
    hints, includes = [], []
    for match in _TAG.finditer(source):
        variable, tag = match.groups()
        content = variable if variable is not None else tag
        if tag is not None:
            words = tag.split()
            if words and words[0] == "include_block":
                _add(hints, HINT_INCLUDE_BLOCK)
            elif words and words[0] == "embed":
                _add(hints, HINT_EMBED)
            include = _INCLUDE.match(tag)
            if include:
                target = include.group(1)
                literal = target[0] in "\"'" and target[-1] == target[0] and len(target) > 1
                includes.append(target[1:-1] if literal else None)
        if re.search(r"\brequest\b", content):
            _add(hints, HINT_REQUEST)
    markup = _TAG.sub(" ", _HTML_COMMENT.sub("", source))
    for match in _START_TAG.finditer(markup):
        element, attrs = match.group(1).lower(), match.group(2)
        if element in HINT_ELEMENTS:
            _add(hints, HINT_ELEMENTS[element])
        if _is_hidden(element, attrs):
            _add(hints, HINT_HIDDEN)
    return hints, includes


def _is_hidden(element: str, attrs: str) -> bool:
    classes = {token for m in _CLASS.finditer(attrs) for token in m.group(2).split()}
    if "hidden" in classes or _HIDDEN_ATTR.search(_QUOTED.sub("", attrs)):
        return True
    if _DISPLAY_NONE.search(attrs):
        return True
    return element not in _TEXTLESS and bool(_ARIA_HIDDEN.search(attrs))


@dataclass
class RenderedBlock:
    """One block of a page as export renders it: its entry, and Markdown or an error."""

    location: str
    entry: BlockEntry
    markdown: str = ""
    error: str = ""


def render_blocks(page) -> list[RenderedBlock]:
    """Render ``page``'s published body fields block by block, as export does.

    StructBlocks and StreamBlocks the built-in renderers recurse into are split
    into their children, as are ListBlocks of such containers; each result is a
    block that renders as a whole. A list of simple items stays one result, so
    its bullets match export. Output is before page hooks and link rewriting,
    which apply to the whole document. A block that raises is recorded and the
    walk continues. Rendering has the same side effects as export, such as
    template queries and embed fetches.
    """
    from .blocks import render_rich_text
    from .context import render_context
    from .page import _published_page, _require_supported_page

    published = _published_page(page)
    _require_supported_page(published)
    context = render_context(published)
    context["heading"] = published.title
    results: list[RenderedBlock] = []
    for model_field in selected_fields(type(published)):
        value = getattr(published, model_field.name)
        if isinstance(model_field, StreamField):
            _render_stream(value, model_field.name, context, results)
        else:
            entry = BlockEntry(
                None, _dotted(type(model_field)), BUILT_IN, _dotted(render_rich_text)
            )
            location = model_field.name
            _render_leaf(render_rich_text, model_field, value, context, location, entry, results)
    return results


def _render_stream(value, location, context, results):
    for index, child in enumerate(value):
        name = child.block_type
        _render(child.block, child.value, name, f"{location}[{index}] {name}", context, results)


def _render(block, value, name, location, context, results):
    try:
        renderer = resolve(block, name, value, context)
        entry = _entry(block, name, renderer, value, context)
    except Exception as exc:
        entry = BlockEntry(name, _dotted(type(block)), "", "")
        results.append(RenderedBlock(location, entry, error=_error(exc)))
        return
    kind = _RECURSING.get(renderer)
    if kind == "list" and _RECURSING.get(resolve(block.child_block)) not in {"struct", "stream"}:
        kind = None  # Items render as a whole list, so bullets match export.
    if kind == "struct":
        for child_name, child in block.child_blocks.items():
            child_location = f"{location} > {child_name}"
            _render(child, value.get(child_name), child_name, child_location, context, results)
    elif kind == "stream":
        _render_stream(value, location, context, results)
    elif kind == "list":
        for index, item in enumerate(value):
            _render(block.child_block, item, None, f"{location}[{index}]", context, results)
    else:
        _render_leaf(renderer, block, value, context, location, entry, results)


def _render_leaf(renderer, block, value, context, location, entry, results):
    try:
        markdown = renderer(block, value, context)
    except Exception as exc:
        results.append(RenderedBlock(location, entry, error=_error(exc)))
    else:
        results.append(RenderedBlock(location, entry, markdown=markdown.strip("\n")))


def _error(exc: Exception) -> str:
    cause = exc.__cause__ or exc
    return f"{type(cause).__name__}: {cause}"
