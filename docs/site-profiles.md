# Site profiles

A site profile keeps one site's Markdown configuration in a single YAML or JSON
file: which fields make up each page, which page attributes become frontmatter,
which pages are left out, the image sizes, and any Python renderers the site's
own blocks need. A site turns it on with one setting and removes it by deleting
that setting:

```python
WAGTAIL_MARKDOWN_AGENTS = {"PROFILE": "config/markdown-profile.yaml"}
```

`PROFILE` is a file path, resolved against `BASE_DIR` when relative, or the
dotted name of a Python package that contains a `profile.yaml`.

Everything a profile does can also be done with `WAGTAIL_MARKDOWN_AGENTS` and a
project's own `markdown_renderers.py` (see [custom blocks](custom-blocks.md)).
A profile is the same configuration in a form that is easy to read, copy to
another site and change.

## Format

```yaml
version: 1
name: Example campaign site     # for people; the package ignores it

settings:
  page_fields:
    campaigns.ContentPage: [intro, body]
    campaigns.Post: [body]
  frontmatter_fields:
    "*":
      canonical: canonical_url
    campaigns.Post:
      author: author_display
      date: published_at
      categories: {each: categories, label: label_for(locale)}
  exclude_when: [hide_from_search]
  image_renditions:
    campaigns.blocks.ImageBlock: width-1600
    campaigns.blocks.CalloutBlock: fill-1600x900

modules:
  - campaigns_markdown.renderers
```

`settings` takes any `WAGTAIL_MARKDOWN_AGENTS` key in lower case, except
`profile`. Precedence, lowest first: the package defaults, the profile, then
`WAGTAIL_MARKDOWN_AGENTS`. A key set in Django settings replaces the profile's
value as a whole, so a dictionary such as `renderers` is not merged.

`modules` are Python modules imported once at startup, after the built-in
renderers and before each installed app's `markdown_renderers` module, so a
project can still override a profile's renderer. A module registers renderers
with `@register_renderer` and Wagtail hooks with `@hooks.register` when it is
imported. If it defines a `ready()` function, that is called after the import,
for work such as connecting signal handlers.

A profile that cannot be read, has an unknown key or a missing `version`, or
names a module that cannot be imported, raises `ImproperlyConfigured` at
startup. The [system checks](system-checks.md) then validate each setting the
profile supplies, exactly as if it were in Django settings.

## Settings that are most useful in a profile

These three settings are ordinary `WAGTAIL_MARKDOWN_AGENTS` keys. They are
listed here because they describe a site's own models, which is what a profile
is for.

### `FRONTMATTER_FIELDS`

Adds page attributes to the frontmatter, per page type. `"*"` applies to every
page type, and a type's own entry wins key by key.

| Source | Meaning |
| --- | --- |
| `"published_at"` | A field, attribute or property of the page. |
| `"label_for(locale)"` | A method, called with the page's locale. |
| `{each: categories, label: "label_for(locale)"}` | A list: each related object's label, in order, without duplicates. Without `label`, the items themselves. |

A plain method is never called, so a misspelling can't run code with side
effects. A key that names a built-in field, such as `date`, replaces it in place;
other keys are added before `tags`. An empty value leaves the built-in value as it
is. The identity keys `id`, `type`, `permalink`, `status` and `timestamp` can't be
mapped. Editors' extra frontmatter and the `construct_markdown_frontmatter` hook
still apply afterwards.

Values are read from the published revision. A change to a related object, such
as a category's translated label, appears the next time the page is exported.
Check `W004` warns about page types and attributes that don't exist.

### `EXCLUDE_WHEN`

A list of page attribute names. A page with any of them set to a true value is
not exported, linked, listed or served, in the same way as a page an editor
excludes. A page type without the attribute is unaffected. Publishing a page
with the box newly ticked withdraws its export. After adding a name to this
list, run `agentmd_revoke_ineligible` to withdraw pages that were already
exported.

Pages with view restrictions (password, login or groups) are always left out;
that needs no setting.

### `IMAGE_RENDITIONS`

Which image size a block's images are exported at, as `{block class: filter
spec}`. The innermost listed block that encloses the image wins, and a key
matches its subclasses. Images are exported at their original size when no
enclosing block is listed. Use the same filter as the block's template, so
agents get the image visitors see. Blocks rendered through their own template
already use the template's image.

## Shipped profiles

`wagtail_markdown_agents/profiles/` holds profiles written for specific sites.
Each one describes **that site's** models and blocks and is not meant to be used
as it stands anywhere else. To start a profile for a new site, copy one,
remove what doesn't apply, and change the model, field and block names to your
own.
