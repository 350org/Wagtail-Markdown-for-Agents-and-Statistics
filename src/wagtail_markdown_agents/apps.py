from django.apps import AppConfig


class WagtailMarkdownAgentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "wagtail_markdown_agents"
    verbose_name = "Markdown for Agents"

    def ready(self) -> None:
        from . import (
            checks,  # noqa: F401 — register Django system checks
            handlers,
            stats,
        )
        from .rendering.registry import autodiscover

        handlers.connect()
        stats.connect()
        autodiscover()
