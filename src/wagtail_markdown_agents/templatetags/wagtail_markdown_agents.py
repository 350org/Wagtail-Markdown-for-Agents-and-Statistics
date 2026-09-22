"""``{% load wagtail_markdown_agents %}`` provides ``{% agent_markdown_link %}`` (#28)."""

from django import template
from django.utils.html import format_html
from wagtail.models import Page

from ..discovery import page_alternate_url

register = template.Library()


@register.simple_tag(takes_context=True)
def agent_markdown_link(context, page=None):
    """``<link rel="alternate" type="text/markdown" href="…">``, or nothing.

    Uses ``page`` from the template context unless one is given. Shares the
    middleware's policy, record and storage resolution and its alternate-URL
    choice, so it emits nothing during previews and for pages whose export is
    missing, revoked or ineligible. The URL is HTML-escaped.
    """
    request = context.get("request")
    if page is None:
        page = context.get("page")
    if not isinstance(page, Page) or getattr(request, "is_preview", False):
        return ""
    url = page_alternate_url(page, request=request)
    if url is None:
        return ""
    return format_html('<link rel="alternate" type="text/markdown" href="{}">', url)
