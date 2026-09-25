"""Renderers for the 350.org blocks whose templates don't export well (#14).

Containers render their children here with ``render_block``: their templates use
``{% include_block %}``, so child renderers were never reached. The others
leave out what the page shows only to a visitor with JavaScript, such as a
signup form's success message, "Loading form…" and the person card's bio
dialog, or what would fetch from the network, such as a video's oEmbed player.
Styling fields (style, size, layout, background, alignment, anchors) are
omitted throughout, and a button that only jumps to an anchor on the page is
left out, since the anchor doesn't exist in the Markdown.
"""

import re
from copy import copy
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured
from django.template.loader import render_to_string
from django.utils.translation import gettext
from wtrx.blocks import (
    AccordionBlock,
    ButtonBlock,
    ButtonGroupBlock,
    CardBlock,
    CardCarouselBlock,
    CardGridBlock,
    DonateBlock,
    DonateFundraiseUpBlock,
    HeroBlock,
    HeroSignupActionKitBlock,
    ImageBlock,
    PageCardsBlock,
    PersonCardBlock,
    PersonCardGridBlock,
    QuoteBlock,
    SectionBlock,
    SignupActionKitBlock,
    SignupActionNetworkBlock,
    SignupWagtailFormsBlock,
    TimelineBlock,
    VideoBlock,
)

from wagtail_markdown_agents.rendering import register_renderer, render_block
from wagtail_markdown_agents.rendering.html import absolute_url, convert_html
from wagtail_markdown_agents.rendering.offline import offline_embeds
from wagtail_markdown_agents.rendering.registry import BlockRenderError


def child(block, value, name, context):
    """Render one of a StructBlock's fields the way export renders any block."""
    return render_block(block.child_blocks[name], value.get(name), context, block_name=name)


def items(block, value, name, context):
    """Render a ListBlock field's items as separate blocks, never as bullets.

    The built-in list renderer bullets items that fit on one line, which would
    turn a card that is only a heading into ``- ### Title``.
    """
    item_block = block.child_blocks[name].child_block
    return join(*(render_block(item_block, item, context) for item in value.get(name) or []))


def join(*parts):
    return "\n\n".join(part for part in parts if part)


def heading(level, text):
    return f"{'#' * level} {text}" if text else ""


def link(text, url):
    if not url:
        return text
    if not text:
        return f"<{url}>"
    text = text.replace("[", "\\[").replace("]", "\\]")
    return f"[{text}]({url})"


def target(value, *fields):
    """The URL of the first link field set: a page, a URL or a document."""
    for name in fields:
        chosen = value.get(name)
        if not chosen:
            continue
        return chosen if isinstance(chosen, str) else getattr(chosen, "url", None)
    return None


@register_renderer(ImageBlock)
def render_image(block, value, context):
    image = value.get("image")
    if image and value.get("alt_text"):
        # Keep the override local to this occurrence of a shared image.
        image = copy(image)
        image.contextual_alt_text = value["alt_text"]
    return join(
        render_block(block.child_blocks["image"], image, context),
        child(block, value, "caption", context),
    )


@register_renderer(PageCardsBlock)
def render_page_cards(block, value, context):
    # A stable index link needs no child query or dependent rebuilds.
    url = target(value, "index_page")
    label = child(block, value, "link_text", context) or gettext("Read more")
    return join(child(block, value, "content", context), link(label, url) if url else "")


@register_renderer(HeroBlock)
def render_hero(block, value, context):
    # This is an authored body section; hide_hero applies to the page header.
    return join(
        heading(2, child(block, value, "headline", context)),
        child(block, value, "content", context),
        child(block, value, "image_caption", context),
    )


@register_renderer(DonateFundraiseUpBlock)
def render_donate_fundraiseup(block, value, context):
    # Checkout configuration is not a public donation URL.
    return join(
        child(block, value, "content", context),
        child(block, value, "image", context),
        child(block, value, "image_caption", context),
    )


@register_renderer(DonateBlock)
def render_donate(block, value, context):
    """Keep the site's donation template, supplying defaults without a request.

    The pinned site's get_context reads IntegrationSettings only through request.
    Override those two context values after it runs; the template still owns
    authored overrides, labels, amount formatting and the currency symbol.
    """
    if value is None:
        return ""
    settings = context.get("settings")
    config = None
    if settings is not None and context.get("site") is not None:
        config = settings["wtrx"]["IntegrationSettings"].get_integration_config("actblue")
    config = config or {}
    amounts = config.get("suggested_amounts") or ""
    try:
        amounts = [Decimal(part.strip()) for part in amounts.split(",") if part.strip()]
    except (InvalidOperation, AttributeError):
        amounts = []  # Same malformed-default behaviour as the site's block.
    parent_context = dict(context)
    parent_context.pop("request", None)
    try:
        with offline_embeds():
            template_context = block.get_context(value, parent_context=parent_context)
            template_context.update(
                donation_base_url=config.get("base_url") or "",
                donation_suggested_amounts_list=amounts,
            )
            html = render_to_string(
                block.get_template(value, context=template_context), template_context
            )
    except Exception as exc:
        raise BlockRenderError(block, exc) from exc
    return convert_html(html, block, context)


def actionkit_url(value, context):
    shortname = value.get("short_form_id")
    settings = context.get("settings")
    if not shortname or settings is None or context.get("site") is None:
        return ""
    config = settings["wtrx"]["IntegrationSettings"].get_integration_config("actionkit")
    hostname = (config.get("hostname", "") if config else "").strip().rstrip("/")
    if not hostname:
        return ""
    base = hostname if "://" in hostname else f"https://{hostname}"
    parsed = urlsplit(base)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or any(char.isspace() for char in base)
        or not re.fullmatch(r"[A-Za-z0-9_-]+", shortname)
    ):
        raise ImproperlyConfigured("ActionKit requires a public hostname and a page short name")
    # Same campaign endpoint used by the site's embed integration, without
    # form_only/abs_urls parameters. It resolves the campaign's action type.
    return f"{base}/act/{shortname}/"


@register_renderer(SignupActionKitBlock)
def render_signup_actionkit(block, value, context):
    url = actionkit_url(value, context)
    return join(
        child(block, value, "eyebrow", context),
        child(block, value, "content", context),
        child(block, value, "image", context),
        child(block, value, "image_caption", context),
        link(gettext("Take action"), url) if url else "",
    )


@register_renderer(HeroSignupActionKitBlock)
def render_hero_signup_actionkit(block, value, context):
    # The compact hero strip has no content field or displayed image/eyebrow.
    url = actionkit_url(value, context)
    return link(gettext("Take action"), url) if url else ""


@register_renderer(VideoBlock)
def render_video(block, value, context):
    # Never {% embed %}: that fetches the player from the provider.
    caption = child(block, value, "caption", context)
    if value.get("embed_url"):
        url = value["embed_url"]
        return link(caption or _stored_embed_title(url), url)
    media = value.get("media_file")
    if media:
        return join(link(media.title, absolute_url(media.url)), caption)
    return ""


def _stored_embed_title(url):
    from wagtail.embeds.models import Embed

    titles = Embed.objects.filter(url=url).exclude(title="").values_list("title", flat=True)
    return titles.first() or ""


@register_renderer(ButtonBlock)
def render_button(block, value, context):
    # A button with only an anchor jumps within the HTML page: left out.
    url = target(value, "link_page", "link_url")
    if not url:
        return ""
    return link(child(block, value, "text", context), url)


@register_renderer(ButtonGroupBlock)
def render_button_group(block, value, context):
    return child(block, value, "buttons", context)


@register_renderer(QuoteBlock)
def render_quote(block, value, context):
    # The image and video are the quote's background.
    content = child(block, value, "content", context)
    quote = "\n".join(f"> {line}".rstrip() for line in content.splitlines())
    url = target(value, "link_page", "link_url")
    return join(quote, link(child(block, value, "link_text", context), url) if url else "")


@register_renderer(CardBlock)
def render_card(block, value, context):
    # The icon is decorative. The tag follows the card's heading, which editors
    # type as an H3 at the top of the content.
    content = child(block, value, "content", context)
    tag = child(block, value, "tag", context)
    if tag and content.startswith("#"):
        title, _, rest = content.partition("\n\n")
        content = join(title, tag, rest)
    elif tag:
        content = join(tag, content)
    url = target(value, "link_page", "link_url", "link_document")
    label = child(block, value, "link_text", context) or gettext("Learn more")
    return join(content, child(block, value, "image", context), link(label, url) if url else "")


@register_renderer(PersonCardBlock)
def render_person_card(block, value, context):
    # The bio dialog repeats the card, and the photo is a portrait.
    contacts = [
        link(value["email"], f"mailto:{value['email']}") if value.get("email") else "",
        link(value["phone"], f"tel:{value['phone']}") if value.get("phone") else "",
        link(gettext("Website"), value["website"]) if value.get("website") else "",
    ]
    return join(
        heading(3, child(block, value, "name", context)),
        child(block, value, "role", context),
        child(block, value, "bio", context),
        " · ".join(contact for contact in contacts if contact),
    )


@register_renderer(PersonCardGridBlock)
def render_person_card_grid(block, value, context):
    people = items(block, value, "people", context)
    return join(heading(2, child(block, value, "heading", context)), people) if people else ""


@register_renderer(CardGridBlock)
def render_card_grid(block, value, context):
    cards = items(block, value, "cards", context)
    return join(heading(2, child(block, value, "heading", context)), cards) if cards else ""


@register_renderer(CardCarouselBlock)
def render_card_carousel(block, value, context):
    url = target(value, "link_page", "link_url")
    return join(
        child(block, value, "content", context),
        link(child(block, value, "link_text", context), url) if url else "",
        items(block, value, "cards", context),
    )


@register_renderer(AccordionBlock)
def render_accordion(block, value, context):
    item_block = block.child_blocks["items"].child_block
    items = [
        join(
            heading(3, child(item_block, item, "title", context)),
            child(item_block, item, "content", context),
        )
        for item in value.get("items") or []
    ]
    items = [item for item in items if item]
    return join(heading(2, child(block, value, "heading", context)), *items) if items else ""


@register_renderer(SectionBlock)
def render_section(block, value, context):
    # Background, padding, width and anchor only style the section.
    return child(block, value, "content", context)


@register_renderer(TimelineBlock)
def render_timeline(block, value, context):
    # The year navigation links to anchors in the HTML page: left out.
    year_block = block.child_blocks["years"].child_block
    return join(
        *(
            join(
                heading(2, child(year_block, year, "year", context)),
                child(year_block, year, "content", context),
            )
            for year in value.get("years") or []
        )
    )


@register_renderer(SignupWagtailFormsBlock)
def render_signup_wagtail_forms(block, value, context):
    # The form loads with JavaScript; its success message is never shown first.
    url = target(value, "form_page")
    label = child(block, value, "button_text", context) or gettext("Sign Up")
    return join(child(block, value, "content", context), link(label, url) if url else "")


@register_renderer(SignupActionNetworkBlock)
def render_signup_action_network(block, value, context):
    # The success message stream is shown only after a visitor signs up.
    url = value.get("action_url")
    return join(
        child(block, value, "content", context), link(gettext("Sign Up"), url) if url else ""
    )
