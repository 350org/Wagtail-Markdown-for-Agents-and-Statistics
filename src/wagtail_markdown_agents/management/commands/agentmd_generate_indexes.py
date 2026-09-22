from django.core.management.base import BaseCommand, CommandError
from wagtail.models import Site

from ...export.indexes import IndexBatch
from ..export_commands import add_scope_arguments, report, require_autocommit, select


class Command(BaseCommand):
    help = "Rebuild indexes, llms.txt and manifest for sites affected by the selection."

    def add_arguments(self, parser) -> None:
        add_scope_arguments(parser)
        parser.add_argument(
            "--dry-run", action="store_true", help="List affected sites without writing"
        )

    def handle(self, *args, **options) -> None:
        selection = select(options, operation="indexes")
        if not options["dry_run"]:
            require_autocommit()
        counts = {"generated": 0, "skipped": 0, "failed": 0}
        for site in Site.objects.filter(pk__in=selection.site_ids).order_by("pk"):
            if options["dry_run"]:
                self.stdout.write(
                    f"Site {site.hostname}: would rebuild indexes, llms.txt and manifest"
                )
                counts["generated"] += 1
                continue
            try:
                batch = IndexBatch()
                batch.mark_dirty(site.pk)
                batch.finalise()
                counts["generated"] += 1
            except Exception as exc:
                counts["failed"] += 1
                self.stderr.write(f"Site {site.hostname}: failed ({exc})")
        report(self, counts, dry_run=options["dry_run"])
        if counts["failed"]:
            raise CommandError("Index generation failed; see site results above.")
