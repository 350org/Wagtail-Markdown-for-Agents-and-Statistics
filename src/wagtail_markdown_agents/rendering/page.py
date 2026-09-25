"""Published page assembly (#78); returns Markdown without writing an export.

The caller must apply ExportPolicy and publish storage changes after commit.
This function reloads the live revision (or, for a live page with no revision,
its row), never the caller's draft instance.
Final link rewriting runs after page hooks/navigation and before YAML is joined
to the body; canonical metadata URLs remain unchanged.
"""

from collections.abc import Mapping

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from wagtail import hooks
from wagtail.fields import RichTextField, StreamField
from wagtail.models import Page

from .. import OKF_VERSION
from ..settings import get_setting
from . import frontmatter
from .blocks import _join, render_plain_text, render_rich_text, render_stream
from .context import render_context
from .links import rewrite_links

POST_RENDER_HOOK = "markdown_post_render"
PAGE_FIELDS_HOOK = "markdown_page_fields"


class PageRenderError(ValueError):
    """A page cannot produce a complete document; commands can report ``reason``.

    Reasons: ``unpublished_page``, ``unsupported_page``, ``empty_body``. These
    are not successful exports and must not get export records or listings.
    Configuration and hook errors propagate separately.
    """

    def __init__(self, page, reason: str, message: str):
        self.page_id = page.pk
        self.reason = reason
        super().__init__(f"Cannot render {page._meta.label} page {page.pk}: {message}")


def render_page(page: Page, site=None, *, navigation: str = "", root_index: bool = False) -> str:
    """Render a published page as YAML frontmatter and a Markdown body.

    PAGE_FIELDS selects ordered StreamField/RichTextField body fields; absent
    entries use integration hook defaults, then auto-detection. v0.1 requires a StreamField and does
    not support form pages. No arbitrary fields or related objects are dumped.

    ``markdown_post_render(markdown, page, context)`` hooks receive the assembled
    field body. Return a string to replace it, or None to keep it. The shared
    offline context includes ``heading`` (initially the published title); hooks
    may replace it or set it to None/empty to supply their own authored heading.
    No headings in the authored body are removed or demoted automatically.

    ``navigation`` is already-rendered Markdown supplied by the index generator
    (#20), appended once after page hooks. The caller owns whether a listing is
    authored or generated. Empty body plus empty navigation raises, even when
    the page has a title. ``root_index=True`` adds the package OKF version to
    frontmatter after its hooks. Output ends with a single newline.
    """
    published = _published_page(page)
    fields = selected_fields(type(published))
    _require_supported_page(published)
    if not isinstance(navigation, str):
        raise TypeError("navigation must be rendered Markdown (a string)")

    context = render_context(published, site)
    context["heading"] = published.title
    body = _join(_render_field(field, published, context) for field in fields)
    for hook in hooks.get_hooks(POST_RENDER_HOOK):
        result = hook(body, published, context)
        if result is not None:
            if not isinstance(result, str):
                raise TypeError(f"{POST_RENDER_HOOK} must return a Markdown string or None")
            body = result
    body = _join([body, navigation])
    if not body.strip():
        raise PageRenderError(published, "empty_body", "selected fields and hooks produced no body")

    heading = context["heading"]
    if heading is not None and not isinstance(heading, str):
        raise TypeError(f"{POST_RENDER_HOOK} context['heading'] must be a string or None")
    if heading:
        heading = render_plain_text(None, " ".join(heading.splitlines()), context)
        body = _join([f"# {heading}", body])
    body = rewrite_links(body, published, context)
    metadata = frontmatter.build(published, context)
    if root_index:
        metadata["okf_version"] = OKF_VERSION
    return frontmatter.serialise(metadata) + "\n" + body.rstrip("\n") + "\n"


def _published_page(page):
    if page.pk is None:
        raise PageRenderError(page, "unpublished_page", "save and publish the page first")
    current = Page.objects.filter(pk=page.pk).select_related("live_revision").first()
    if current is None or not current.live:
        raise PageRenderError(page, "unpublished_page", "the page is not live")
    if current.live_revision_id is None:
        # Programmatically created live pages (importers, add_child) have no
        # revision. Saving a draft never changes a live row's content fields,
        # so the row is exactly what Wagtail serves as HTML.
        return current.specific
    published = current.with_content_json(current.live_revision.content)
    # Revision JSON predates the publish operation. Use the publication's actual
    # dates and identity, not the previous publication's values in that JSON.
    published.first_published_at = current.first_published_at
    published.last_published_at = current.last_published_at
    published.live_revision_id = current.live_revision_id
    return published


def _require_supported_page(page):
    reason = unsupported_reason(type(page))
    if reason:
        raise PageRenderError(page, "unsupported_page", reason)


def unsupported_reason(model) -> str:
    """Why pages of ``model`` cannot be rendered, or an empty string when they can."""
    if apps.is_installed("wagtail.contrib.forms"):
        from wagtail.contrib.forms.models import FormMixin

        if issubclass(model, FormMixin):
            return "form page extraction is not supported"
    if not any(isinstance(field, StreamField) for field in model._meta.get_fields()):
        return "v0.1 requires a StreamField on the page type"
    return ""


def selected_fields(page_model):
    """Ordered body fields: explicit ``PAGE_FIELDS``, integration defaults, then auto-detection."""
    configured = get_setting("PAGE_FIELDS")
    if configured is None:
        configured = {}
    if not isinstance(configured, Mapping):
        raise ImproperlyConfigured(
            "PAGE_FIELDS must be a mapping of app.Model to ordered field names"
        )
    selection = {}
    # Validate the whole map so misspelled model keys cannot silently fall back
    # to auto-detection and export fields the project intended to omit.
    for label, names in configured.items():
        try:
            model = apps.get_model(label) if isinstance(label, str) else None
        except (LookupError, ValueError) as exc:
            raise ImproperlyConfigured(f"PAGE_FIELDS has an unknown page model {label!r}") from exc
        if model is None or not issubclass(model, Page):
            raise ImproperlyConfigured(f"PAGE_FIELDS key {label!r} must name a Page model")
        if model in selection:
            raise ImproperlyConfigured(f"PAGE_FIELDS configures {model._meta.label} more than once")
        selection[model] = _named_fields(model, names, f"PAGE_FIELDS[{label!r}]")
    if page_model in selection:
        return selection[page_model]
    # Integrations can supply defaults without mutating host settings.
    # Explicit PAGE_FIELDS wins; the first hook with a result owns defaults.
    for hook in hooks.get_hooks(PAGE_FIELDS_HOOK):
        names = hook(page_model)
        if names is not None:
            return _named_fields(page_model, names, PAGE_FIELDS_HOOK)
    return [
        field
        for field in page_model._meta.get_fields()
        if isinstance(field, StreamField | RichTextField)
    ]


def _named_fields(model, names, source):
    if not isinstance(names, list | tuple):
        raise ImproperlyConfigured(f"{source} must be an ordered list of names")
    fields = []
    seen = set()
    for name in names:
        if not isinstance(name, str) or name in seen:
            raise ImproperlyConfigured(f"{source} has invalid/duplicate name {name!r}")
        seen.add(name)
        try:
            field = model._meta.get_field(name)
        except FieldDoesNotExist as exc:
            raise ImproperlyConfigured(f"{source} has no field {name!r}") from exc
        if not isinstance(field, StreamField | RichTextField):
            raise ImproperlyConfigured(f"{source}[{name!r}] must be a StreamField or RichTextField")
        fields.append(field)
    return fields


def _render_field(field, page, context):
    value = getattr(page, field.name)
    if isinstance(field, StreamField):
        # The top-level field is an ordered sequence, not a presentation block.
        # Child dispatch still honours registry/name overrides and templates.
        return render_stream(field.stream_block, value, context)
    return render_rich_text(field, value, context)
