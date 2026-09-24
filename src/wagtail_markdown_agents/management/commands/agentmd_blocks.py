import json

from django.core.management.base import BaseCommand, CommandError

from ...rendering.coverage import CUSTOM_TEMPLATE, DEFAULT_TEMPLATE, LABELS, build_report, compare
from ..export_commands import report

BUILT_IN_PREFIX = "wagtail_markdown_agents.rendering.blocks."


class Command(BaseCommand):
    help = (
        "Report how each StreamField block on exportable page types renders to Markdown. "
        "Reads block definitions only; renders and writes nothing."
    )

    def add_arguments(self, parser):
        output = parser.add_mutually_exclusive_group()
        output.add_argument(
            "--json", action="store_true", help="Print the report as a JSON snapshot."
        )
        output.add_argument(
            "--compare",
            metavar="SNAPSHOT",
            help="Compare with a --json snapshot; exit non-zero if block coverage changed.",
        )

    def handle(self, *args, **options) -> None:
        coverage = build_report()
        if options["json"]:
            self.stdout.write(json.dumps(coverage.as_json(), indent=2))
        elif options["compare"]:
            self._compare(options["compare"], coverage)
        else:
            self._report(coverage)

    def _report(self, coverage) -> None:
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
            self.stdout.write(f"\n{LABELS[path]} ({len(entries)})")
            for entry in entries:
                self.stdout.write("  " + _describe(entry))
                self.stdout.write("    " + _locations(entry.locations))
        self.stdout.write("")
        report(self, {path: len(entries) for path, entries in grouped.items()})

    def _compare(self, path, coverage) -> None:
        try:
            with open(path, encoding="utf-8") as snapshot_file:
                snapshot = json.load(snapshot_file)
            changes = compare(snapshot, coverage)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CommandError(f"Cannot compare with {path}: {exc}") from exc
        if not changes:
            self.stdout.write(f"Block coverage matches {path}.")
            return
        for line in changes:
            self.stdout.write(line)
        self.stdout.flush()  # Keep the changes ahead of the error when piped (CI logs).
        raise CommandError(f"Block coverage changed since {path}: {len(changes)} differences.")


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
