import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        # Deliberately an old wagtailcore migration so this app installs on
        # every supported Wagtail version (>= 6.3). We only need the Page
        # model to exist; do not let makemigrations "update" this to the
        # latest wagtailcore node.
        ("wagtailcore", "0069_log_entry_jsonfield"),
    ]

    operations = [
        migrations.CreateModel(
            name="PageAgentSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "excluded",
                    models.BooleanField(
                        default=False,
                        help_text="Exclude this page from Markdown export and agent serving.",
                    ),
                ),
                (
                    "extra_frontmatter",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Additional frontmatter keys merged into this page's export.",
                    ),
                ),
                (
                    "page",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agent_markdown_settings",
                        to="wagtailcore.page",
                    ),
                ),
            ],
            options={
                "verbose_name": "page agent Markdown settings",
                "verbose_name_plural": "page agent Markdown settings",
            },
        ),
    ]
