import django.db.models.deletion
import wagtail.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("wagtailcore", "0069_log_entry_jsonfield"),
        ("wtrx", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="IntegrationSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "integrations",
                    wagtail.fields.StreamField(
                        [("actionkit", 2), ("actblue", 4)],
                        blank=True,
                        block_lookup={
                            0: (
                                "wagtail.blocks.BooleanBlock",
                                (),
                                {"default": True, "required": False},
                            ),
                            1: ("wagtail.blocks.CharBlock", (), {"required": False}),
                            2: (
                                "wagtail.blocks.StructBlock",
                                [[("enabled", 0), ("hostname", 1)]],
                                {},
                            ),
                            3: ("wagtail.blocks.URLBlock", (), {"required": False}),
                            4: (
                                "wagtail.blocks.StructBlock",
                                [[("enabled", 0), ("page_url", 3)]],
                                {},
                            ),
                        },
                    ),
                ),
                ("custom_head_html", models.TextField(blank=True)),
                ("custom_body_html", models.TextField(blank=True)),
                (
                    "site",
                    models.OneToOneField(
                        editable=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="wagtailcore.site",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
