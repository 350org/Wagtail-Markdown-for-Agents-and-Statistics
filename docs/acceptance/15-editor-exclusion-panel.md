# 15 — Optional editor exclusion panel

Project-owner authorised implementation of #18 on 21 September 2026, following #17.

- Opting a page model into `AgentMarkdownPanelMixin` adds an exclusion checkbox
  to its Settings tab without adding database fields to that page model. Other
  page models retain the action-menu view only.
- The checkbox reads the current `PageAgentSettings` record, including when an
  older page revision is opened. It is not a revision field. No row means included.
- Saving a valid page revision applies the checkbox immediately to the same
  side-model as #17, preserving frontmatter. Draft save does not publish draft
  content; publish honours exclusion before export generation. Creation supports
  the checkbox once the page exists.
- Rendering a form, invalid submissions, previews and `form.save(commit=False)`
  without a saved revision do not change exclusion. Failed revision saves roll
  back exclusion. Unchanged values do not write side-model rows or regenerate.
- Page edit permissions, admin access and Wagtail locks apply as in #17; new
  pages require permission to add under the chosen parent. Permissions are checked
  again against the saved page before persisting exclusion. Forged submissions
  cannot change exclusion when the checkbox is unavailable.
- The existing export lifecycle withdraws excluded content even with automatic
  generation disabled. Clearing exclusion restores only eligible published content
  when generation is enabled. Children and HTML are unaffected.
- Custom page forms can compose with `AgentMarkdownPageForm`. Sites with custom
  Settings panels or edit handlers explicitly include the checkbox panel. An
  omitted panel must not silently clear an existing exclusion.

The editor explains that the checkbox applies on save, independently of page
publication; revision rollback cannot restore an old exclusion setting.

## Verification — 21 September 2026

- `tests/test_editor_panel.py`: 20 passing cases, covering real editor and preview
  requests, draft/create/publish flows, permission checks, custom forms, omitted
  panels and filesystem/remote lifecycle transitions with generation on/off.
- Full pytest on Django 6.0.7 / Wagtail 7.4.2: 1,327 passed.
- Oldest tox environment (`py311-dj42-wagtail63`): 1,327 passed, with 10 dependency
  deprecation warnings. The environment tests the built package wheel.
- Ruff lint/format checks pass; `makemigrations --check --dry-run` reports no
  missing migrations. Only the sandbox test page type needs a new migration.
