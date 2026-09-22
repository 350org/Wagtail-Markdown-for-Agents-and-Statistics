# Optional editor exclusion checkbox

The action-menu **Markdown settings** screen works with unmodified page models.
To also show a checkbox in a page editor's **Settings** tab, opt that model into
`AgentMarkdownPanelMixin`:

```python
from wagtail.models import Page

from wagtail_markdown_agents.panels import AgentMarkdownPanelMixin


class ArticlePage(AgentMarkdownPanelMixin, Page):
    # Your existing fields and content_panels go here.
    pass
```

Put the mixin before `Page` (or your project's base page class). It supplies the
base form and default Settings panels; it adds no database field to your page.
Both editor surfaces use the same `PageAgentSettings.excluded` record, preserving
`extra_frontmatter`. No row means included.

The checkbox applies when a valid page revision is saved, including **Save draft**,
**Publish** and initial page creation. Preview, invalid forms and merely opening
an editor do not change exclusion. The value is independent of page revisions:
opening or reverting an older revision reads the current exclusion, not a historic
value. It does not publish draft text or change the page's HTML or children's
exclusions.

As with the action-menu screen, the user needs admin access and permission to edit
that page, with no applicable Wagtail lock. New pages require permission to add
under their parent. The form disables the checkbox when the user cannot change it;
the revision save checks the persisted page's permissions and lock again. Exclusion
withdraws the page's Markdown immediately even with `AUTO_GENERATE=False`. Clearing
it restores only eligible published content, automatically when generation is
on, or after the next generation run when it is off.

## Existing custom forms and panels

Preserve a custom page form by composing it with `AgentMarkdownPageForm`. Existing
form methods must cooperate with `super()`, as normal for Wagtail custom forms:

```python
from wagtail.admin.panels import FieldPanel

from wagtail_markdown_agents.panels import (
    AgentMarkdownPageForm,
    AgentMarkdownPanelMixin,
)


class ArticleForm(AgentMarkdownPageForm, ExistingArticleForm):
    pass


class ArticlePage(AgentMarkdownPanelMixin, ProjectPage):
    base_form_class = ArticleForm
    settings_panels = ProjectPage.settings_panels + [
        FieldPanel("agent_markdown_excluded"),
    ]
```

`ExistingArticleForm` and `ProjectPage` above stand for your existing project
classes. If you override `settings_panels`, preserve your existing panels and add
`FieldPanel("agent_markdown_excluded")` once. A custom `edit_handler` must include
that field panel and use `AgentMarkdownPageForm` (or your composed subclass) as its
base form. If the panel is omitted, submitting the page form leaves exclusion
unchanged.

A project override of `save_revision()` must call `super().save_revision()` so the
mixin participates. Form `save()` stages the requested value on the in-memory page;
the mixin persists it only after the revision succeeds, in the same transaction,
before subsequent publish processing. Calling `form.save(commit=False)` alone does
not change the database. Programmatic revisions with no staged checkbox value leave
exclusion untouched; programmatic exclusion changes should use `PageAgentSettings`
directly so the normal lifecycle signals run.

The sandbox's `MarkdownArticlePage` demonstrates the opt-in alongside the unchanged
`ArticlePage` baseline. The new sandbox migration creates that test page type;
the reusable package needs no database migration for this feature.
