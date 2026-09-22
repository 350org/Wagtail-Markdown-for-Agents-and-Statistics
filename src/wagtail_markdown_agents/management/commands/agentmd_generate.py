from django.core.management.base import BaseCommand, CommandError
from wagtail.models import Site

from ...export.indexes import IndexBatch
from ...export.writer import FileWriter
from ...models import ExportArtifact
from ...rendering.page import PageRenderError
from ..export_commands import add_scope_arguments, inspect_page, report, require_autocommit, select


class Command(BaseCommand):
    help = "Generate selected published pages and finalise each affected site's discovery once."

    def add_arguments(self, parser) -> None:
        add_scope_arguments(parser)
        parser.add_argument(
            "--force", action="store_true", help="Rebuild even current readable exports"
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Inspect the plan without writing"
        )

    def handle(self, *args, **options) -> None:
        selection = select(options, operation="generate")
        writer = FileWriter()
        dry_run = options["dry_run"]
        if not dry_run:
            require_autocommit()
        counts = {
            "generated": 0,
            "skipped": 0,
            "failed": 0,
            "failed_scopes": 0,
            "discovery_scopes": 0,
        }
        for site in Site.objects.filter(pk__in=selection.site_ids).order_by("pk"):
            batch = IndexBatch(writer)
            pending_indexes = []
            site_failed = False
            needs_discovery = False
            for page_id in selection.pages_by_site.get(site.pk, ()):
                try:
                    state, page, path = inspect_page(page_id, writer)
                    owner = page.get_site() if page is not None else None
                    if owner is None or owner.pk != site.pk:
                        counts["skipped"] += 1
                        self.stdout.write(
                            f"Page {page_id}: skipped (no longer in the selected site)"
                        )
                        continue
                    if state in {"ineligible", "unsupported"} or (
                        state == "current" and not options["force"]
                    ):
                        counts["skipped"] += 1
                        self.stdout.write(f"Page {page_id}: skipped ({state})")
                        if (
                            state != "current"
                            and ExportArtifact.objects.filter(
                                page_id=page_id, scope__site_id=site.pk
                            ).exists()
                        ):
                            needs_discovery = True
                            if dry_run:
                                self.stdout.write(f"Page {page_id}: would withdraw owned export")
                            else:
                                batch.delete_page(page_id, site_id=site.pk)
                        continue
                    needs_discovery = True
                    if dry_run:
                        counts["generated"] += 1
                        self.stdout.write(f"Page {page_id}: would generate {path}")
                        continue
                    batch.mark_dirty(site.pk)
                    if path.endswith("/index.md"):
                        pending_indexes.append(page_id)
                        continue
                    try:
                        batch.generate(page)
                    except PageRenderError as exc:
                        if exc.reason not in {"unsupported_page", "empty_body"}:
                            raise
                        batch.delete_page(page_id, site_id=site.pk)
                        counts["skipped"] += 1
                        self.stdout.write(f"Page {page_id}: skipped ({exc.reason})")
                    else:
                        counts["generated"] += 1
                        self.stdout.write(f"Page {page_id}: generated {path}")
                except Exception as exc:
                    counts["failed"] += 1
                    site_failed = True
                    self.stderr.write(f"Page {page_id}: failed ({exc})")
            if dry_run:
                try:
                    if needs_discovery or not all(
                        writer.exists(f"{site.hostname}/{name}")
                        for name in ("index.md", "llms.txt", "manifest.json")
                    ):
                        counts["discovery_scopes"] += 1
                        self.stdout.write(f"Site {site.hostname}: would refresh discovery")
                except Exception as exc:
                    counts["failed_scopes"] += 1
                    self.stderr.write(f"Site {site.hostname}: inspection failed ({exc})")
                continue
            if site_failed:
                counts["failed"] += len(pending_indexes)
                counts["failed_scopes"] += 1
                continue  # Never finalise a partially failed site's manifest.
            try:
                if not batch.dirty and not all(
                    writer.exists(f"{site.hostname}/{name}")
                    for name in ("index.md", "llms.txt", "manifest.json")
                ):
                    batch.mark_dirty(site.pk)
                if batch.dirty:
                    batch.finalise()
                    counts["discovery_scopes"] += 1
                for page_id in pending_indexes:
                    state, _, _ = inspect_page(page_id, writer)
                    result = "generated" if state == "current" else "skipped"
                    counts[result] += 1
                    self.stdout.write(f"Page {page_id}: {result}")
            except Exception as exc:
                counts["failed"] += len(pending_indexes)
                counts["failed_scopes"] += 1
                self.stderr.write(f"Site {site.hostname}: discovery failed ({exc})")
        report(self, counts, dry_run=dry_run)
        if counts["failed"] or counts["failed_scopes"]:
            raise CommandError("Export generation failed; see page/site results above.")
