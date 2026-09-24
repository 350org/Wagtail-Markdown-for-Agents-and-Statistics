import json

from django.core.management.base import BaseCommand, CommandError
from wagtail.models import Page

from ...export.policy import ExportPolicy
from ...rendering.coverage import (
    CUSTOM_TEMPLATE,
    DEFAULT_TEMPLATE,
    LABELS,
    build_report,
    compare,
    render_blocks,
)
from ...rendering.page import PageRenderError
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
        output.add_argument(
            "--page",
            type=int,
            metavar="ID",
            help="Render one published page block by block, with the same side effects as export.",
        )

    def handle(self, *args, **options) -> None:
        if options["page"] is not None:
            self._page(options["page"])
            return
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
                for hint in entry.hints:
                    self.stdout.write("    ! " + hint)
        self.stdout.write("")
        counts = {path: len(entries) for path, entries in grouped.items()}
        counts["with_hints"] = sum(1 for entry in coverage.entries if entry.hints)
        report(self, counts)

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

    def _page(self, page_id) -> None:
        page = Page.objects.filter(pk=page_id).first()
        if page is None:
            raise CommandError(f"Page {page_id} does not exist.")
        try:
            rendered = render_blocks(page)
        except PageRenderError as exc:
            raise CommandError(str(exc)) from exc
        # A live row keeps its published title while a newer draft is pending.
        self.stdout.write(f'Page {page_id} "{page.title}" ({page.specific_class._meta.label})')
        if not ExportPolicy().is_eligible(page):
            self.stdout.write(
                "Not exported under the current policy; rendered for inspection only."
            )
        self.stdout.write("Block output is shown before page hooks and link rewriting.")
        for block in rendered:
            self.stdout.write(f"\n{block.location}  -> {_target(block.entry)}")
            for hint in block.entry.hints:
                self.stdout.write("  ! " + hint)
            if block.error:
                self.stdout.write("  error: " + block.error)
            elif block.markdown.strip():
                for line in block.markdown.splitlines():
                    self.stdout.write(("  | " + line).rstrip())
            else:
                self.stdout.write("  (empty)")
        failed = sum(1 for block in rendered if block.error)
        empty = sum(1 for block in rendered if not block.error and not block.markdown.strip())
        self.stdout.write("")
        report(self, {"blocks": len(rendered), "empty": empty, "failed": failed})
        if failed:
            self.stdout.flush()
            raise CommandError(f"{failed} blocks on page {page_id} failed to render.")


def _describe(entry) -> str:
    return f"{entry.name or '(list item)'}  {entry.block_class}  -> {_target(entry)}"


def _target(entry) -> str:
    if not entry.path:
        return entry.block_class
    if entry.path in (CUSTOM_TEMPLATE, DEFAULT_TEMPLATE):
        return entry.template or "no template"
    return entry.renderer.removeprefix(BUILT_IN_PREFIX) + (" (by name)" if entry.by_name else "")


def _locations(locations) -> str:
    if len(locations) == 1:
        return f"in {locations[0]}"
    return f"in {locations[0]} and {len(locations) - 1} more"
