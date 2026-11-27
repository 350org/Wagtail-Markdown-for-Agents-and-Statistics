"""Store agent-signals' labels: drop eight trailing slashes and fold unlisted labels (#93).

The registry holds exactly agent-signals revision 5's entries from 2026-11-27.2.
Eight stored labels ended in a slash that agent-signals' labels don't have, so their
rows move to the label without it, merging counts with any row already there. Rows
under a label that isn't in the list (FacebookBot, Kimi-SearchBot, OAI-AdsBot) move
to the shared unknown bucket, as 0006 does. Daily totals are unchanged.
"""

from collections import Counter

from django.db import migrations, transaction
from django.db.models import F

# Frozen at this migration: later registry edits must not change what it does.
RENAMES = {
    "ShapBot/": "ShapBot",
    "ICC-Crawler/": "ICC-Crawler",
    "Cotoyogi/": "Cotoyogi",
    "meta-externalfetcher/": "meta-externalfetcher",
    "AdpResearchBot/": "AdpResearchBot",
    "Nava/": "Nava",
    "Retool/": "Retool",
    "SemrushBot-SWA/": "SemrushBot-SWA",
}

# agent-signals revision 5: every label, active and retired.
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
    "meta-externalfetcher",
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
    "Nava",
    "Retool",
    "Claude-SearchBot",
    "Bravebot",
    "Amzn-SearchBot",
    "Cloudflare-AI-Search",
    "Anomura",
    "Element451Bot",
    "KernelSearchBot",
    "ShapBot",
    "alphalens-bot",
    "KimiBot",
    "PetalBot",
    "GoogleOther",
    "CloudVertexBot",
    "ICC-Crawler",
    "Cotoyogi",
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
    "AdpResearchBot",
    "SelectikaScraper",
    "SemrushBot-OCOB",
    "SemrushBot-SWA",
    "WARDBot",
    "ygs-scraper-bot",
    "Gemini-User",
    "Geminibot",
    "Google-NotebookLM",
    "Claude-Agent",
    "meta-webindexer",
    "LinkupBot",
    "RiverBot",
    "ibou-search",
    "YouBot",
    "KeenableBot",
    "ClueWeb-Crawler",
    "AzureAI-SearchBot",
    "Google-GeminiNotebook",
    "Kimi-User",
    "Amzn-User",
    "Shap-User",
    "Googlebot",
    "bingbot",
    "Applebot",
)


def store_agent_signals_labels(apps, schema_editor):
    access = apps.get_model("wagtail_markdown_agents", "AgentAccess")
    alias = schema_editor.connection.alias
    rows = access.objects.using(alias)
    last_pk = 0
    while True:
        # Each batch commits its counts and deletions together and is safe to
        # retry after interruption. Pause older application workers for upgrade:
        # they still store the slashed labels.
        with transaction.atomic(using=alias):
            batch = list(
                rows.select_for_update()
                .filter(pk__gt=last_pk)
                .exclude(agent__in=("", *KNOWN_LABELS))
                .order_by("pk")
                .values("pk", "page_id", "agent", "access_method", "access_date", "count")[:500]
            )
            if not batch:
                return
            totals = Counter()
            for row in batch:
                target = RENAMES.get(row["agent"], "")
                totals[row["page_id"], target, row["access_method"], row["access_date"]] += row[
                    "count"
                ]
            # Delete first: the targets are known labels, so never in this batch.
            rows.filter(pk__in=[row["pk"] for row in batch]).delete()
            for (page_id, agent, method, day), count in totals.items():
                target, _ = rows.get_or_create(
                    page_id=page_id,
                    access_method=method,
                    access_date=day,
                    agent=agent,
                    defaults={"count": 0},
                )
                rows.filter(pk=target.pk).update(count=F("count") + count)
        last_pk = batch[-1]["pk"]


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("wagtail_markdown_agents", "0007_refresh_and_listing_markers")]
    operations = [
        migrations.RunPython(store_agent_signals_labels, migrations.RunPython.noop),
    ]
