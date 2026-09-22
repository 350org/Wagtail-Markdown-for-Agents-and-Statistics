from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("wagtail_markdown_agents", "0004_exportscope_manifest_state"),
    ]

    operations = [
        migrations.CreateModel(
            name="AgentAccess",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("page_id", models.PositiveIntegerField()),
                ("agent", models.CharField(blank=True, max_length=100)),
                ("access_method", models.CharField(max_length=20)),
                ("access_date", models.DateField(db_index=True)),
                ("count", models.PositiveBigIntegerField(default=1)),
            ],
        ),
        migrations.AddConstraint(
            model_name="agentaccess",
            constraint=models.UniqueConstraint(
                fields=("page_id", "agent", "access_method", "access_date"),
                name="agentmd_access_daily_unique",
            ),
        ),
    ]
