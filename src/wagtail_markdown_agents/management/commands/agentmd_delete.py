from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from wagtail.models import Site

from ...export.indexes import IndexBatch
from ...export.policy import ExportPolicy
from ...export.writer import FileWriter
from ...models import ExportArtifact, ExportFile
from ..export_commands import add_scope_arguments, report, require_autocommit, select


class Command(BaseCommand):
    help = (
        "Delete selected owned exports and refresh surviving discovery; leave CMS content intact."
    )

    def add_arguments(self, parser) -> None:
        add_scope_arguments(parser)
        parser.add_argument(
            "--all", action="store_true", help="Delete all owned exports, including orphaned scopes"
        )
        parser.add_argument(
            "--yes", action="store_true", help="Confirm broad deletion without prompting"
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Show selected ownership without deleting"
        )

    def handle(self, *args, **options) -> None:
        selection = select(options, operation="delete")
        records, files = ExportArtifact.objects.all(), ExportFile.objects.all()
        if options["site"]:
            records = records.filter(scope__site_id__in=selection.site_ids)
            files = files.filter(scope__site_id__in=selection.site_ids)
        whole_sites = options["page_id"] is None and not options["type"]
        if not whole_sites:
            records = records.filter(page_id__in=selection.page_ids)
            files = files.filter(page_id__in=selection.page_ids)
        targets = list(records.values_list("pk", "scope__site_id", "page_id"))
        site_ids = set(files.values_list("scope__site_id", flat=True))
        target_ids = [pk for pk, _, _ in targets]
        owners_by_site = {}
        for _, site_id, page_id in targets:
            if page_id is not None:
                owners_by_site.setdefault(site_id, set()).add(page_id)
        dependent_ids = (
            list(
                ExportArtifact.objects.filter(scope__site_id__in=site_ids)
                .exclude(pk__in=target_ids)
                .filter(Q(page_id__isnull=True) | ~Q(dependency_state=""))
                .values_list("pk", flat=True)
            )
            if targets
            else []
        )
        counts = {
            "deleted": 0,
            "dependent_withdrawn": 0,
            "failed": 0,
            "cleanup_pending": 0,
            "discovery_scopes": 0,
        }
        repair_sites = {
            site.pk
            for site in Site.objects.filter(pk__in=site_ids)
            if not whole_sites and ExportPolicy.site_enabled(site)
        }
        self.stdout.write(
            f"Selected {len(targets)} owned artefact(s) across {len(site_ids)} site(s)."
        )
        if options["dry_run"]:
            counts["deleted"] = len(targets)
            counts["dependent_withdrawn"] = len(dependent_ids)
            counts["discovery_scopes"] = len(repair_sites) if targets else 0
            report(self, counts, dry_run=True)
            return
        require_autocommit()
        if options["page_id"] is None and site_ids and not options["yes"]:
            try:
                answer = input(
                    "Delete these owned exports and invalidate dependent discovery? [yes/no]: "
                )
            except (EOFError, OSError) as exc:
                raise CommandError(
                    "Deletion requires confirmation; use --yes for non-interactive use."
                ) from exc
            if answer.strip().lower() != "yes":
                raise CommandError("Deletion cancelled.")
        writer = FileWriter()
        for site_id in sorted(site_ids):
            try:
                if whole_sites:
                    writer.delete_site(site_id)
                else:
                    batch = IndexBatch(writer)
                    for page_id in sorted(owners_by_site.get(site_id, ())):
                        batch.delete_page(page_id, site_id=site_id)
                    writer.cleanup(site_id)
                    if site_id in repair_sites and batch.dirty:
                        batch.finalise(exclude_page_ids=selection.page_ids)
                        counts["discovery_scopes"] += 1
            except Exception as exc:
                counts["failed"] += 1
                self.stderr.write(f"Site {site_id}: deletion failed ({exc})")
        counts["deleted"] = len(targets) - ExportArtifact.objects.filter(pk__in=target_ids).count()
        counts["dependent_withdrawn"] = (
            len(dependent_ids) - ExportArtifact.objects.filter(pk__in=dependent_ids).count()
        )
        counts["cleanup_pending"] = ExportFile.objects.filter(
            scope__site_id__in=site_ids, cleanup_pending=True
        ).count()
        report(self, counts)
        if counts["failed"] or counts["cleanup_pending"]:
            raise CommandError(
                "Deletion/cleanup incomplete; owned pending files are retained for retry."
            )
