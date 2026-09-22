"""Remove arbitrary historical UA fragments while preserving daily hit totals."""

from collections import Counter

from django.db import migrations, transaction
from django.db.models import F

# Freeze the canonical labels at this migration; later dataset edits must not
# change which historical rows this migration retains.
KNOWN_LABELS = (
    "GPTBot",
    "ChatGPT-User",
    "ClaudeBot",
    "Claude-Web",
    "anthropic-ai",
    "PerplexityBot",
    "Google-Extended",
    "Amazonbot",
    "cohere-ai",
    "meta-externalagent",
    "Bytespider",
    "CCBot",
    "Applebot-Extended",
    "OAI-SearchBot",
    "Claude-User",
    "Perplexity-User",
    "meta-externalfetcher/",
    "MistralAI-User",
    "Google-Agent",
    "DuckAssistBot",
    "Devin",
    "TwinAgent",
    "ApifyWebsiteContentCrawler",
    "ChathiveCrawler",
    "CledaraBot",
    "EasyScan",
    "HarkBot",
    "HIFIBot",
    "QATechBot",
    "Instapaper",
    "Nava/",
    "Retool/",
    "Claude-SearchBot",
    "Bravebot",
    "Amzn-SearchBot",
    "Cloudflare-AI-Search",
    "Anomura",
    "Element451Bot",
    "KernelSearchBot",
    "ShapBot/",
    "alphalens-bot",
    "KimiBot",
    "PetalBot",
    "GoogleOther",
    "CloudVertexBot",
    "ICC-Crawler/",
    "Cotoyogi/",
    "atlassian-bot",
    "LinerBot",
    "magpie-crawler",
    "bigsur.ai",
    "QualifiedBot",
    "Awario",
    "amazon-kendra-",
    "Anchor Browser",
    "BorderxBot",
    "CitibotSiteCrawler",
    "CloudflareBrowserRenderingCrawler",
    "netEstate NE Crawler",
    "FishBot",
    "make.com",
    "NavuBot",
    "Novellum",
    "AdpResearchBot/",
    "SelectikaScraper",
    "SemrushBot-OCOB",
    "SemrushBot-SWA/",
    "WARDBot",
    "ygs-scraper-bot",
)


def anonymize_unknown_agents(apps, schema_editor):
    access = apps.get_model("wagtail_markdown_agents", "AgentAccess")
    alias = schema_editor.connection.alias
    rows = access.objects.using(alias)
    last_pk = 0
    while True:
        # Each batch commits its counts and deletions together and is safe to
        # retry after interruption. Pause older application workers for upgrade.
        with transaction.atomic(using=alias):
            batch = list(
                rows.select_for_update()
                .filter(pk__gt=last_pk)
                .exclude(agent__in=("", *KNOWN_LABELS))
                .order_by("pk")
                .values("pk", "page_id", "access_method", "access_date", "count")[:500]
            )
            if not batch:
                return
            totals = Counter()
            for row in batch:
                totals[row["page_id"], row["access_method"], row["access_date"]] += row["count"]
            for (page_id, method, day), count in totals.items():
                unknown, _ = rows.get_or_create(
                    page_id=page_id,
                    access_method=method,
                    access_date=day,
                    agent="",
                    defaults={"count": 0},
                )
                rows.filter(pk=unknown.pk).update(count=F("count") + count)
            rows.filter(pk__in=[row["pk"] for row in batch]).delete()
        last_pk = batch[-1]["pk"]


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("wagtail_markdown_agents", "0005_agentaccess")]
    operations = [
        migrations.RunPython(anonymize_unknown_agents, migrations.RunPython.noop),
    ]
