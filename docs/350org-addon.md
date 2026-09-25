# 350.org blocks add-on

`wagtail_markdown_agents.contrib.wtrx` holds Markdown renderers for the 350.org
Wagtail site's blocks (the `wtrx` app). It uses the same public mechanism as any
project's renderers ([custom blocks guide](custom-blocks.md)), and the core never
imports it. The block contracts come from the matrix on #14, against
`350org/wagtail-wtr-350` branch `improvements` at `1997766`.

## Install

Add the app after the package itself:

```python
INSTALLED_APPS = [
    # ...
    "wtrx",
    "wagtail_markdown_agents",
    "wagtail_markdown_agents.contrib.wtrx",
]
```

It has no models, settings or URLs. Its app label is `agentmd_wtrx`, because the
site's own app is `wtrx`. Check the result with `python manage.py agentmd_blocks`:
the blocks below show this app's renderers.

## Blocks it renders

| Block | Markdown |
| --- | --- |
| `video` | `[caption](embed URL)`, else the title Wagtail has stored for the embed, else `<embed URL>`. A media file is `[title](absolute file URL)` then the caption. Never fetches the player. |
| `button` | `[text](page or URL)`. A button that only jumps to an anchor on the page is left out. |
| `button_group` | A list of its buttons. |
| `quote` | The content as a `>` blockquote, then `[link text](URL)`. The image or video is the background. |
| `card` | The content (its H3 heading first), the tag under the heading, the image, then `[link text or "Learn more"](page, URL or document)`. The icon is decorative. |
| `person_card` | `### name`, role, bio, then email, phone and website links. The bio dialog, which repeats the card, and the photo are left out. |
| `card_grid`, `person_card_grid` | `## heading` and each card. Nothing when there are no cards. |
| `card_carousel` | The content, its link, then each card. |
| `accordion` | `## heading`, then each item as `### title` over its content. |
| `section` | Its content in place. Background, padding, width and anchor are styling. |
| `timeline` | Each year as `## year` over its content. The year navigation links to anchors in the HTML page. |
| `signup_wagtail_forms` | The content, then `[button text or "Sign Up"](form page)`. The success message is left out. |
| `signup_action_network` | The content, then `[Sign Up](action URL)`. The success message stream is left out. |

Containers render their children through export's own dispatch
(`render_block`), so nested blocks get their renderers: a video inside a
timeline year or an accordion item is a link, not an oEmbed fetch. Styling fields
are omitted throughout.

## Not covered yet

- `signup_actionkit` and the hero's ActionKit signup still export "This signup
  form is temporarily unavailable": the link form is to be agreed on #14.
- `page_cards` still exports through its template, pending the choice between a
  link to the index page and a list of its newest children.
- `image`, `hero` and `donate_fundraiseup` export through their templates until
  the image credit and caption questions are answered.
- Page-level hero content (`hero_headline`, `hero_copy`, `hero_cta`) and
  `PAGE_FIELDS` per page type.

The other blocks export acceptably through their templates; see the matrix on #14.

## Tests

`tests/test_contrib_wtrx.py` runs the renderers against a stand-in for
`wtrx.blocks` in `tests/wtrx_stub/`, which mirrors the site's field names and
nesting at `1997766`. The site itself isn't a test dependency. When the site's
blocks change, update the stand-in to match.
