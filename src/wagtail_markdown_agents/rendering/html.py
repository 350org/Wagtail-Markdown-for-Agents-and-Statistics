"""HTML → Markdown conversion.

Every HTML path — rich text, plain text and the template fallback — goes
through :func:`convert_html`, so all produce the same headings, lists, code
fences and spacing, and the conversion hooks apply to each. markdownify drops
``<script>`` and ``<style>`` elements together with their contents; the tests
pin that behaviour.

Hooks (Wagtail's ``hooks.register``; run by ``order``, then registration order):

``markdown_pre_convert(html, block, context)``
    Return the HTML to convert, or ``None`` to leave it unchanged. Hooks chain:
    each receives the previous one's result.
``construct_markdown_converter_options(options, block, context)``
    Mutate the markdownify options dict in place; the return value is ignored.

Exceptions raised by a hook propagate.
"""

from django.conf import settings
from django.utils.html import escape
from markdownify import ATX, MarkdownConverter
from wagtail import hooks
from wagtail.rich_text import expand_db_html
from wagtail.rich_text.rewriters import FIND_EMBED_TAG, extract_attrs

PRE_CONVERT_HOOK = "markdown_pre_convert"
CONVERTER_OPTIONS_HOOK = "construct_markdown_converter_options"

_CODE_LANGUAGE_PREFIXES = ("language-", "lang-")


def convert_html(html: str, block, context) -> str:
    """Convert HTML produced for ``block`` to Markdown, applying the conversion hooks."""
    for hook in hooks.get_hooks(PRE_CONVERT_HOOK):
        result = hook(html, block, context)
        if result is not None:
            html = result

    options = {
        "heading_style": ATX,
        "bullets": "-",
        "code_language_callback": _code_language,
    }
    for hook in hooks.get_hooks(CONVERTER_OPTIONS_HOOK):
        hook(options, block, context)

    return _Converter(**options).convert(str(html)).strip()


def expand_rich_text(source: str) -> str:
    """Expand Wagtail's stored rich-text references to plain HTML.

    Page links, document links and image embeds expand as Wagtail renders them.
    Media embeds become links to their URL first: expanding them would call
    the provider's oEmbed API during generation, and an agent needs the URL,
    not a player.
    """
    return expand_db_html(FIND_EMBED_TAG.sub(_media_embed_to_link, source))


def _media_embed_to_link(match) -> str:
    attrs = extract_attrs(match.group(1))
    if attrs.get("embedtype") != "media" or not attrs.get("url"):
        return match.group(0)
    url = escape(attrs["url"])
    return f'<a href="{url}">{url}</a>'


def absolute_url(url: str) -> str:
    """Prefix a site-relative URL with ``WAGTAILADMIN_BASE_URL`` when it is set.

    Wagtail's ``Rendition.full_url`` rule, applied to every image URL in the
    output — block images and rich-text images alike — so an agent reading the
    export elsewhere can fetch them. Other URLs are left as they are.
    """
    base = getattr(settings, "WAGTAILADMIN_BASE_URL", "")
    if base and url.startswith("/") and not url.startswith("//"):
        return base.rstrip("/") + url
    return url


def _code_language(pre) -> str | None:
    """Read a language hint from ``class="language-x"`` on ``<pre>`` or its ``<code>``."""
    classes = list(pre.get("class") or [])
    code = pre.find("code")
    if code is not None:
        classes += code.get("class") or []
    for name in classes:
        for prefix in _CODE_LANGUAGE_PREFIXES:
            if name.startswith(prefix):
                return name[len(prefix) :]
    return None


class _Converter(MarkdownConverter):
    def convert_img(self, el, text, parent_tags):
        if el.get("src"):
            el["src"] = absolute_url(el["src"])
        markdown = super().convert_img(el, text, parent_tags)
        if not markdown:
            return markdown
        before = " " if _touches_text(el.previous_sibling, at_end=True) else ""
        after = " " if _touches_text(el.next_sibling, at_end=False) else ""
        return f"{before}{markdown}{after}"


def _touches_text(sibling, *, at_end: bool) -> bool:
    """Whether an image's neighbour would run into it without a space."""
    if sibling is None:
        return False
    if isinstance(sibling, str):
        text = str(sibling)
        if not text:
            return False
        return not (text[-1] if at_end else text[0]).isspace()
    return True
