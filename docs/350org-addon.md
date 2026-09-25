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

It has no models or URLs. Its app label is `agentmd_wtrx`, because the
site's own app is `wtrx`. Check the result with `python manage.py agentmd_blocks`:
the blocks below show this app's renderers.

After enabling or upgrading the add-on, run `python manage.py agentmd_generate
--force` with the site's normal scope to refresh existing exports. Renderer and
integration-setting changes do not themselves publish a new page revision.

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
| `image` | The image, using the block's alt override or the image's description/title, then its authored caption. |
| `page_cards` | The content, then `[link text or "Read more"](index page)`. No child listing or child query. |
| `hero` | `## headline`, content and the authored image caption. The background image and colour are omitted. |
| `donate_fundraiseup` | Content, image and authored image caption. Designation IDs and advanced settings are omitted; no checkout URL is invented. |
| `signup_actionkit` | Eyebrow, content, image and authored caption, then `[Take action](campaign URL)`. No form fetch, success message or unavailable-form placeholder. |

Containers render their children through export's own dispatch
(`render_block`), so nested blocks get their renderers: a video inside a
timeline year or an accordion item is a link, not an oEmbed fetch. Styling fields
are omitted throughout.

## Campaign links and page heroes

ActionKit links use each block's `short_form_id` and the enabled ActionKit hostname
from the page site's `IntegrationSettings`, through the offline `settings` context.
For example, `campaigns.example.org` and `climate-action` produce
`https://campaigns.example.org/act/climate-action/`. This is the campaign endpoint
the site's embed integration already uses, without its form-only query parameters;
ActionKit also uses this route for [links to translated campaign pages](https://docs.actionkit.com/docs/manual/language.html).
The hero's compact ActionKit signup uses the same link. No credentials or remote
form content enter the export. With no hostname, short name, site or settings context, no
action link is emitted; authored body copy and captions remain. A malformed
hostname or short name raises a configuration error.

The add-on supplies default body fields through `markdown_page_fields` and assembles
the page hero through `markdown_post_render`:

| Page type | Body fields after the hero |
| --- | --- |
| HomePage, ContentPage | `body` |
| IndexPage | `intro`, then `body` |
| Post | `body` |
| Blogs | None; the hero and any navigation supplied by the index generator provide content. |

A visible page hero uses `hero_headline or title` as the document H1, followed by
the pre-header, copy, CTA links and authored caption, then the selected body fields.
Generated navigation retains the core's existing position after the body.
`hide_hero=True` omits the whole page hero, including its headline override, copy,
buttons, signup and caption. The document keeps the ordinary page title as its H1.
It does not hide separate hero blocks authored inside the body. These choices use
the published revision, so a newer draft cannot change the export.

Explicit `PAGE_FIELDS` configuration overrides the defaults for each model. Omit
`hero_copy` and `hero_cta` from such mappings: the add-on owns them and rejects
configurations that would duplicate them or bypass `hide_hero`.

These output decisions were agreed on 25 September 2026: campaign-specific
ActionKit destinations, index-only page cards, authored image/hero captions and
complete page-hero omission when hidden. A separately stored image `credit` is
not added automatically; that choice remains open.

## Integration settings and regeneration

With the add-on enabled, saving a changed `IntegrationSettings.integrations`
configuration schedules a rebuild of that site's pages after the database
transaction commits. The rebuild reads the latest settings and published page
revisions, so ActionKit hostname/enabled changes and template-based donation
defaults reach existing exports without republishing pages. It finishes the site's
indexes, `llms.txt` and manifest once. Nested sites are selected by their actual
routing owner and are not rebuilt with their parent site.

The selection covers the whole site because nested blocks and templates can use
integration settings without declaring individual dependencies. Unchanged saves
and edits to custom head/body HTML alone do not trigger regeneration. Creating
the empty settings row on first use does not trigger a recursive rebuild. Deleting
the settings row rebuilds with the default empty configuration; reassigning a row
to another site refreshes both sites.

`AUTO_GENERATE=False` disables this automatic work. The same switch and site policy
are checked again when a queued task executes. Rolled-back transactions discard
the callback. This uses the existing synchronous v0.1 task backend: an integration
save waits for regeneration after commit, and repeated changed saves are not
debounced. No new database tables or startup queries are introduced by the add-on.

Failures are logged after the settings save has committed; earlier page writes or
older exports may remain, and a failed batch is not finalised as a successful
manifest. Fix the cause and run
`python manage.py agentmd_generate --site example.org --force` to recover. This
explicit command also works when automatic generation is disabled. Bulk updates
and raw fixture loading bypass this receiver and require the same explicit refresh.

## Remaining coverage decisions

Logo grids still use linked images through their templates, and donation currency
formatting retains the template's output. Separate image credits, post metadata
mappings and full client acceptance remain open.

The other blocks export acceptably through their templates; see the matrix on #14.

## Tests

`tests/test_contrib_wtrx.py` runs the renderers against stand-ins in
`tests/wtrx_stub/`, which mirror the site's relevant block fields and nesting at
`1997766`. Synthetic page models exercise published hero assembly, field order
and `hide_hero`. Their migration belongs only to the test app; the add-on has no
database migration. The site itself isn't a test dependency. When the site's
blocks change, update the stand-ins to match. The manual
[block drift check](350org-block-drift.md) compares a chosen site revision against
the pinned real-site definition snapshot without database rows or rendering.

`tests/test_wtrx_settings_lifecycle.py` covers committed settings edits, real offline
configuration reads, unchanged page revisions, draft isolation, nested sites,
rollback, delayed tasks, disabled generation, storage failures and recovery on
filesystem and synthetic remote storage. Its synthetic settings model and migration
belong to the test app only.
