"""Page hero assembly for the bounded 350.org page types (#14)."""

from django.core.exceptions import ImproperlyConfigured
from wagtail import hooks
from wagtail.blocks import CharBlock, RichTextBlock

from wagtail_markdown_agents.rendering import render_block
from wagtail_markdown_agents.rendering.page import selected_fields

from .markdown_renderers import join

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
    return join(
        render_block(CharBlock(), getattr(page, "hero_pre_header", ""), context),
        render_block(RichTextBlock(), getattr(page, "hero_copy", ""), context),
        render_block(cta.stream_block, cta, context) if cta is not None else "",
        render_block(CharBlock(), getattr(page, "hero_image_caption", ""), context),
        markdown,
    )
