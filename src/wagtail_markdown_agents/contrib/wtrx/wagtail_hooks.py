"""Page hero assembly and image credits for the 350.org page types (#14)."""

import posixpath
import re
from functools import reduce
from operator import or_
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q
from wagtail import hooks
from wagtail.blocks import CharBlock, RichTextBlock
from wagtail.images import get_image_model

from wagtail_markdown_agents.rendering import render_block
from wagtail_markdown_agents.rendering.page import selected_fields

from .markdown_renderers import credit, credit_text, join

PAGE_FIELDS = {
    "wtrx.homepage": ["body"],
    "wtrx.contentpage": ["body"],
    "wtrx.indexpage": ["intro", "body"],
    "wtrx.post": ["body"],
    "wtrx.blogs": [],
}


@hooks.register("markdown_page_fields")
def page_fields(page_model):
    return PAGE_FIELDS.get(page_model._meta.label_lower)


@hooks.register("markdown_post_render")
def page_hero(markdown, page, context):
    if page._meta.label_lower not in PAGE_FIELDS:
        return None
    selected = {field.name for field in selected_fields(type(page))}
    if selected & {"hero_copy", "hero_cta"}:
        raise ImproperlyConfigured(
            "The 350.org add-on owns hero_copy and hero_cta; omit them from PAGE_FIELDS "
            "so the hero appears once and hide_hero suppresses it completely."
        )
    if getattr(page, "hide_hero", False):
        return markdown
    context["heading"] = page.hero_headline or page.title
    cta = getattr(page, "hero_cta", None)
    page_image = getattr(page, "hero_image", None)
    return join(
        render_block(CharBlock(), getattr(page, "hero_pre_header", ""), context),
        render_block(RichTextBlock(), getattr(page, "hero_copy", ""), context),
        render_block(cta.stream_block, cta, context) if cta is not None else "",
        render_block(CharBlock(), getattr(page, "hero_image_caption", ""), context),
        # A hero video takes the image's place on the page.
        "" if getattr(page, "hero_video", None) else credit(page_image, context),
        markdown,
    )


# Wagtail names a rendition file <stem>.<filter spec>.<ext>, e.g.
# rally.2e16d0ba.fill-900x675.png or rally.width-500.format-webp.webp.
RENDITION_NAME = re.compile(
    r"\.(?:original|(?:width|height|scale)-\d+|(?:max|min|fill)-\d+x\d+(?:-c\d+)?)"
    r"(?:\.[a-z]+-\w+)*\.\w+$"
)


@hooks.register("markdown_pre_convert")
def image_credits(html, block, context):
    """Follow each template or rich-text image with its stored credit.

    The HTML only has the rendition URL, so the image is found through its
    rendition's file name. Other images, such as static files, are skipped
    without a query. Decorative images (alt="") are dropped in conversion, and
    their credits with them.
    """
    if "<img" not in html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    images = [img for img in soup.find_all("img") if img.get("src") and img.get("alt") != ""]
    names = {posixpath.basename(urlsplit(img["src"]).path) for img in images}
    names = {name for name in names if RENDITION_NAME.search(name)}
    if not names:
        return None
    renditions = (
        get_image_model()
        .get_rendition_model()
        .objects.filter(reduce(or_, (Q(file__endswith=f"/{name}") for name in names)))
        .select_related("image")
    )
    credits = {posixpath.basename(r.file.name): credit_text(r.image) for r in renditions}
    changed = False
    for img in images:
        text = credits.get(posixpath.basename(urlsplit(img["src"]).path))
        if not text:
            continue
        # After the link or picture around the image; inside a figure, at its end.
        anchor = img.parent if img.parent.name in {"a", "picture"} else img
        paragraph = soup.new_tag("p")
        paragraph.string = text
        if anchor.parent is not None and anchor.parent.name == "figure":
            anchor.parent.append(paragraph)
        else:
            # The newline keeps the image from reading as inline with the credit.
            anchor.insert_after("\n", paragraph)
        changed = True
    return str(soup) if changed else None
