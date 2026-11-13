from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("wagtail_markdown_agents", "0006_anonymize_unknown_agents"),
    ]

    operations = [
        migrations.AddField(
            model_name="exportscope",
            name="stale_before",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="exportscope",
            name="finalised_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="exportartifact",
            name="lists",
            field=models.JSONField(blank=True, default=None, null=True),
        ),
    ]
