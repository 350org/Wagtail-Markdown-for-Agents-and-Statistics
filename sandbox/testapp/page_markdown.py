"""Project-owned example: register ``render_hero`` as ``markdown_post_render``.

Set PAGE_FIELDS for testapp.ContentPage to ["intro", "body"] so hero copy is
selected here only. This demonstrates the proposed hero order in scenario 01;
it is not a production mapping for 350.org's provisional models.
"""

from django.utils.html import format_html
from wagtail.blocks import RichTextBlock

from wagtail_markdown_agents.rendering.blocks import render_block
from wagtail_markdown_agents.rendering.html import convert_html

from .models import ContentPage


def render_hero(markdown, page, context):
    if not isinstance(page, ContentPage):
        return None
    context["heading"] = page.hero_headline or page.title
    parts = [render_block(RichTextBlock(), page.hero_copy, context)]
    # The sample's hero image is decorative, as in its HTML: no Markdown image.
    if page.hero_link_text and page.hero_link_page_id:
        from wagtail_markdown_agents.export.policy import ExportPolicy

        target = page.hero_link_page
        if ExportPolicy().is_eligible(target):
            # Escape project text/URLs before the shared HTML conversion path.
            html = format_html('<a href="{}">{}</a>', target.url, page.hero_link_text)
            parts.append(convert_html(html, None, context))
    parts.append(markdown)
    return "\n\n".join(part.strip("\n") for part in parts if part.strip())
