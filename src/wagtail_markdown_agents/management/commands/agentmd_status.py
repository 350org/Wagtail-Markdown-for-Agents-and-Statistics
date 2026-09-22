from django.core.management.base import BaseCommand, CommandError

from ...export.writer import FileWriter
from ...models import ExportFile
from ..export_commands import add_scope_arguments, inspect_page, report, select


class Command(BaseCommand):
    help = "Inspect selected pages' export availability without generating or deleting anything."

    def add_arguments(self, parser):
        add_scope_arguments(parser)

    def handle(self, *args, **options) -> None:
        selection = select(options, operation="status")
        writer = FileWriter()
        counts = dict.fromkeys(
            ("eligible", "current", "missing", "unavailable", "skipped", "failed"), 0
        )
        for page_id in selection.page_ids:
            try:
                state, page, path = inspect_page(page_id, writer)
                if state in {"current", "missing", "unavailable"}:
                    counts["eligible"] += 1
                    counts[state] += 1
                else:
                    counts["skipped"] += 1
                self.stdout.write(f"Page {page_id}: {state}" + (f" ({path})" if path else ""))
            except Exception as exc:
                counts["failed"] += 1
                self.stderr.write(f"Page {page_id}: failed ({exc})")
        pending = ExportFile.objects.filter(
            scope__site_id__in=selection.site_ids, cleanup_pending=True
        )
        if options["page_id"] is not None or options["type"]:
            pending = pending.filter(page_id__in=selection.page_ids)
        counts["cleanup_pending"] = pending.count()
        report(self, counts)
        if counts["failed"]:
            raise CommandError("Export status checks failed; see errors above.")
