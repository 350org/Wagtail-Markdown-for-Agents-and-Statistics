# 14 — Page exclusion settings

Project-owner authorised implementation of #17 on 21 September 2026. These
scenarios cover the page action-menu view; the optional editor panel is #18.

- Given a saved page the user can edit, its action menu offers **Markdown
  settings**. Creation and revision-revert screens do not offer this action.
- Anonymous users and users without Wagtail admin access cannot open or submit
  the form. Users without edit permission for that page, or prevented from editing
  by a Wagtail lock, cannot see the action or change settings by direct URL.
- Opening the form shows the current exclusion value. An absent settings row
  means unchecked; opening or cancelling the form makes no database changes.
- Saving the checkbox changes only that page's exclusion value, preserves extra
  frontmatter, and returns to its editor with a success message. Submitted page
  IDs, frontmatter and redirect URLs cannot change the target or destination.
  Saving an unchanged value does not trigger export work.
- Mutations require POST and a valid CSRF token. Unknown pages return 404.
- Excluding a published page immediately withdraws its Markdown through the
  existing lifecycle, including when automatic generation is disabled. The HTML
  page and child-page exclusions are unchanged. Clearing exclusion restores only
  eligible published content when automatic generation is enabled; it does not
  publish draft edits or override access restrictions.

The form explains that changes apply immediately, only affect this page, and
that clearing the checkbox remains subject to export eligibility and automatic
generation settings. This is not a page revision or a publication action.

## Verification — 21 September 2026

- `tests/test_page_settings.py`: 19 passing cases, including real lifecycle
  transitions with filesystem and remote storage, with automatic generation on/off.
- Full pytest: 1,307 passed. Oldest tox environment
  (`py311-dj42-wagtail63`): 1,307 passed, with 10 dependency deprecation warnings.
- Ruff lint and formatting checks pass; no database migration is required.
- The tests render the editor action and settings form and exercise POST/redirect
  behaviour. A visual browser check was attempted against an isolated local
  database but could not complete because the browser automation connection failed.
