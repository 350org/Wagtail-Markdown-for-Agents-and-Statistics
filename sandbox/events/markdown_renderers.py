from wagtail_markdown_agents.rendering import register_renderer, render_block

from .blocks import EventBlock, EventListBlock


def render_child(block, value, name, context):
    """Render one of a StructBlock's fields the way export renders any block."""
    return render_block(block.child_blocks[name], value[name], context, block_name=name)


@register_renderer(EventBlock)
def render_event(block, value, context):
    # "style" only changes how the card looks, so it is left out.
    title = render_child(block, value, "title", context)
    when = render_child(block, value, "date", context)
    where = render_child(block, value, "location", context)
    summary = render_child(block, value, "summary", context)
    details = " · ".join(part for part in (when, where) if part)
    return "\n\n".join(part for part in (f"### {title}", details, summary) if part)


@register_renderer(EventListBlock)
def render_event_list(block, value, context):
    heading = render_child(block, value, "heading", context)
    events = render_child(block, value, "events", context)
    return f"## {heading}\n\n{events}" if events else ""
