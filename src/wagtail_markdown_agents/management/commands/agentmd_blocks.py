from django.core.management.base import BaseCommand

from ...rendering.coverage import (
    BUILT_IN,
    CUSTOM_TEMPLATE,
    DEFAULT_TEMPLATE,
    PROJECT,
    build_report,
)
from ..export_commands import report

BUILT_IN_PREFIX = "wagtail_markdown_agents.rendering.blocks."
SUMMARY_KEYS = {
    PROJECT: "project",
    BUILT_IN: "built_in",
    CUSTOM_TEMPLATE: "custom_template",
    DEFAULT_TEMPLATE: "default_html",
}


class Command(BaseCommand):
    help = (
        "Report how each StreamField block on exportable page types renders to Markdown. "
        "Reads block definitions only; renders and writes nothing."
    )

    def handle(self, *args, **options) -> None:
        coverage = build_report()
        self.stdout.write(
            f"Block coverage for {len(coverage.page_types)} page types: "
            + (", ".join(coverage.page_types) or "none")
        )
        for label, reason in coverage.skipped.items():
            self.stdout.write(f"Skipped {label}: {reason}")
        grouped = coverage.by_path()
        for path, entries in grouped.items():
            if not entries:
                continue
            self.stdout.write(f"\n{path[0].upper()}{path[1:]} ({len(entries)})")
            for entry in entries:
                self.stdout.write("  " + _describe(entry))
                self.stdout.write("    " + _locations(entry.locations))
        self.stdout.write("")
        report(self, {SUMMARY_KEYS[path]: len(entries) for path, entries in grouped.items()})


def _describe(entry) -> str:
    name = entry.name or "(list item)"
    if entry.path in (CUSTOM_TEMPLATE, DEFAULT_TEMPLATE):
        target = entry.template or "no template"
    else:
        target = entry.renderer.removeprefix(BUILT_IN_PREFIX)
        target += " (by name)" if entry.by_name else ""
    return f"{name}  {entry.block_class}  -> {target}"


def _locations(locations) -> str:
    if len(locations) == 1:
        return f"in {locations[0]}"
    return f"in {locations[0]} and {len(locations) - 1} more"
