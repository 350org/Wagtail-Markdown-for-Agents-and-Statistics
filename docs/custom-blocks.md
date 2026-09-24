# Exporting your own StreamField blocks

Every block in an exported StreamField becomes Markdown. Wagtail's own blocks have
built-in renderers. A project's own blocks export through their templates unless you
give them a renderer. This guide shows how to check your blocks, when a template is
good enough, and how to write, register and test a renderer. You don't need to
change this package.

## 1. See how your blocks export today

```bash
python manage.py agentmd_blocks            # every block, and how it becomes Markdown
python manage.py agentmd_blocks --page 42  # one real page, block by block
```

The [block coverage report](management-commands.md#report-block-coverage) lists
each block under the path export takes:

- **Project renderer**: a renderer you registered.
- **Built-in renderer**: this package's renderer for a Wagtail block.
- **Custom template**: the block's template is rendered and its HTML is converted.
- **Wagtail default HTML**: Wagtail's basic HTML for the block is converted.

Blocks under the two template paths may carry `!` hints, such as text that is hidden
on the page but would be exported. `--page` shows the Markdown each block of a real
page produces.

## 2. Decide whether the template is enough

The template fallback works well when the template is plain, meaningful HTML for the
block's content: headings, paragraphs, lists, links, images and tables all convert
cleanly.

Write a renderer when the template's HTML says something different from the content:

- it shows words that are only for the page, such as "Add to calendar", "Read more"
  or carousel controls;
- it hides text until a visitor acts, such as a success message, a `<dialog>` or an
  accordion;
- it depends on JavaScript, a `request` or a network call (`{% embed %}`);
- it renders child blocks with `{% include_block %}`, so renderers you register for
  those children are never used;
- the meaning lives in field values the template turns into styling, such as a
  colour, alignment or icon choice.

The fallback cannot infer what a block means. It converts what the template prints.

## 3. Write a renderer

This example is a small, independent app. The same code runs in this repository's
sandbox as `sandbox/events`, and a test keeps the two identical.

`events/blocks.py`:

```python
from wagtail import blocks


class EventBlock(blocks.StructBlock):
    title = blocks.CharBlock()
    date = blocks.DateBlock()
    location = blocks.CharBlock(required=False)
    summary = blocks.RichTextBlock(required=False)
    style = blocks.ChoiceBlock(choices=[("light", "Light"), ("dark", "Dark")], default="light")

    class Meta:
        template = "events/event_block.html"


class EventListBlock(blocks.StructBlock):
    heading = blocks.CharBlock()
    events = blocks.ListBlock(EventBlock())
```

`events/templates/events/event_block.html`, the block's HTML presentation:

```html
<article class="event event--{{ value.style }}">
    <h3>{{ value.title }}</h3>
    <p>{{ value.date|date:"j F Y" }}{% if value.location %} · {{ value.location }}{% endif %}</p>
    {{ value.summary }}
    <button type="button" data-add-to-calendar>Add to calendar</button>
</article>
```

Without a renderer, an event exports through that template, and the button's label
ends up in the Markdown:

```markdown
### Climate strike

20 September 2026 · Uhuru Park, Nairobi

Bring a sign and **a friend**.

Add to calendar
```

`events/markdown_renderers.py`:

```python
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
```

The module is found automatically: at startup, every installed app's
`markdown_renderers.py` is imported, as Wagtail does with `wagtail_hooks.py`. An
`EventListBlock` with two events now exports as:

```markdown
## Upcoming events

### Climate strike

2026-09-20 · Uhuru Park, Nairobi

Bring a sign and **a friend**.

### Letter-writing evening

2026-10-02
```

Run `agentmd_blocks` again. `EventListBlock` is now listed under "Project renderer",
and so is `EventBlock` wherever a StreamField uses it directly. Blocks inside a
project renderer's block aren't listed separately, because that renderer decides
how they're used.

## The renderer contract

A renderer is a function `(block, value, context) -> str`:

- `block` is the block instance, including its `child_blocks` and `meta`.
- `value` is the block's value as Wagtail gives it to templates: a `StructValue`
  (dict-like), a list for a `ListBlock`, a `StreamValue` of children (each with
  `block_type`, `value` and `block`), or a field's value. It can be `None` or empty.
- `context` is a dict: `page` (the published page), `site`, `locale`, `heading` (the
  page's title, used for the document heading) and, when `wagtail.contrib.settings`
  is installed, `settings`. Treat it as read-only.
- Return Markdown. Return `""` to leave the block out: empty results are dropped, so
  they leave no blank lines.

Export runs after publishing and from management commands, not during a visitor's
request. There is no `request`, no logged-in user and no session. Don't fetch from
the network: the output would depend on a third party at export time. Page URLs,
`{% pageurl %}`, `{% image %}` and site settings all work without a request.

The output is part of a larger document. Start headings at `##` or below, because
the page title is the document's `#` heading. Links to other pages are rewritten to
their Markdown exports after rendering, so link to the page's normal URL.

## Rendering child blocks

A renderer that contains other blocks should render them with `render_block`, as
`render_child` above does. `render_block(child_block, child_value, context,
block_name=name)` picks the renderer export would pick, so each child gets:

- its built-in renderer, such as rich text with its links and embeds expanded, dates
  in ISO 8601, and escaped plain text;
- any renderer registered for its class or name, including another project's;
- its template, when it has one and no renderer.

Pass `block_name` for a StructBlock field or a StreamBlock child, so name
registrations apply to it. `EventListBlock` shows the nesting: its renderer hands the
`events` ListBlock to `render_block`, the built-in list renderer renders each item,
and each item reaches `render_event`.

Containers without a template need no renderer at all. A StructBlock, StreamBlock or
ListBlock without its own template renders its children in order, each through
`render_block`. Register a renderer for a container when you want its fields shaped,
as `render_event_list` shapes its heading, or when the container has a template.

A container's template renders its own children. If `EventListBlock` had a template
using `{% include_block %}`, `render_event` would never run for its events, and
`agentmd_blocks` would hint at this. Give such a container a renderer that delegates
to `render_block`.

## How a renderer is chosen

For each block, export uses the first of these that applies:

1. a renderer registered for the block's name;
2. the nearest class renderer in the block's class hierarchy, other than Wagtail's
   generic containers (StructBlock, StreamBlock, ListBlock);
3. the block's own template, through the template fallback;
4. the generic container renderer, which renders children in order;
5. the template fallback, with Wagtail's default HTML.

A template counts as the block's own unless it is a file shipped inside Wagtail. A
class renderer (step 2) wins over the block's template, which is why `render_event`
replaces `event_block.html` for export but not for the page.

## Registering renderers

**By class**: `@register_renderer(EventBlock)`. This covers subclasses too: the
nearest registered class in the hierarchy wins, whatever order the registrations
ran in. Prefer class registration. It's precise, and it's the only safe choice for a
reusable package.

**By name**: `@register_renderer(block_name="style")`. This wins over any class
registration, but it applies to every block with that name: in any StreamBlock or
StructBlock, on any page type, from any app. It suits a site-wide convention, such as
dropping every presentation field called `background`:

```python
@register_renderer(block_name="background")
def omit_background(block, value, context):
    return ""
```

ListBlock items and table cells have no name, so name registrations never apply to
them.

**By setting**: map dotted paths in your Django settings. These apply after every
`markdown_renderers.py` module, so they always win for that class:

```python
WAGTAIL_MARKDOWN_AGENTS = {
    "RENDERERS": {"events.blocks.EventBlock": "events.exports.render_event_for_agents"},
}
```

**Collisions.** When two apps register a renderer for the same class or name, the
later registration wins and a warning names both functions. Modules are imported in
`INSTALLED_APPS` order. Replacing one of this package's built-in renderers is
expected, so it is silent, and so is a settings override.

### Reusable block packages

A package that ships blocks can ship their renderers too, in its own
`markdown_renderers.py`, registered by class. Its users get them automatically. A
project that wants different output for one of those blocks overrides it in
settings, which doesn't depend on app order:

```python
WAGTAIL_MARKDOWN_AGENTS = {
    "RENDERERS": {"wagtail_maps.blocks.MapBlock": "mysite.markdown.render_map"},
}
```

Or it subclasses the block in its own code and registers a renderer for the
subclass. A package should not register renderers by name, because generic names
such as `title` or `items` would change other apps' blocks.

## When rendering fails

If a renderer raises an error, or a block's template fails to render, the page is not
exported. A template failure is raised as `BlockRenderError`, with the template's
error attached, so a block's content never silently disappears.

- On publish, the page still publishes. The error is logged, and the page's Markdown
  is not updated.
- `agentmd_generate` reports the page as failed, with the error, and exits
  non-zero.
- `agentmd_blocks --page ID` shows which block failed and renders the rest.

## Testing a renderer

Render the block directly, with a context built the way export builds it:

```python
from wagtail.models import Site

from wagtail_markdown_agents.rendering import render_block
from wagtail_markdown_agents.rendering.context import render_context

from events.blocks import EventBlock


def test_event_leaves_out_presentation(db):
    page = Site.objects.get(is_default_site=True).root_page.specific
    block = EventBlock()
    value = block.to_python({"title": "Climate strike", "date": "2026-09-20", "style": "dark"})
    assert render_block(block, value, render_context(page)) == "### Climate strike\n\n2026-09-20"
```

Then check a real page with `agentmd_blocks --page`, and keep a snapshot of your
blocks with `agentmd_blocks --json`. When `--compare` reports a block change, such
as a new field, you'll know which renderers to review.

## Scope and limits

- The package's core imports no project code. It works with Wagtail's optional apps
  (images, documents, embeds, snippets) installed or not. Their built-in renderers
  register only when the app is installed.
- Renderers cover StreamField blocks and RichTextFields. Other page fields, such as a
  hero image or a summary, are added with the page-level hook; see
  [Rendering a complete page](page-rendering.md#project-owned-hero-content).
- Form pages are not exported.
