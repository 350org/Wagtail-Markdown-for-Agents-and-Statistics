from django.apps import AppConfig


class WtrxMarkdownConfig(AppConfig):
    name = "wagtail_markdown_agents.contrib.wtrx"
    # The site's own app is labelled "wtrx".
    label = "agentmd_wtrx"
    verbose_name = "Markdown for Agents: 350.org blocks"
