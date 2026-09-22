"""Explicit retention pruning of daily agent access counters (#36).

Nothing schedules this command. Deletion is one indexed ``DELETE`` on
``access_date``; rows are never loaded, iterated or cascaded.
"""

from datetime import UTC, datetime, timedelta

from django.core.management.base import BaseCommand, CommandError

from ...models import AgentAccess
from ...settings import get_setting
from ..export_commands import report


class Command(BaseCommand):
    help = (
        "Delete agent access statistics older than a number of days "
        "(default STATS_RETENTION_DAYS); nothing schedules this."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--days",
            type=int,
            help="Retain this many days of daily counters; defaults to STATS_RETENTION_DAYS (90)",
        )
        parser.add_argument("--yes", action="store_true", help="Confirm deletion without prompting")
        parser.add_argument(
            "--dry-run", action="store_true", help="Count prunable records without deleting"
        )

    def handle(self, *args, **options) -> None:
        days, source = options["days"], "--days"
        if days is None:
            days, source = get_setting("STATS_RETENTION_DAYS"), "STATS_RETENTION_DAYS"
        if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
            raise CommandError(f"{source} must be a positive whole number of days, not {days!r}.")
        cutoff = datetime.now(UTC).date() - timedelta(days=days)
        prunable = AgentAccess.objects.filter(access_date__lt=cutoff)
        selected = prunable.count()
        self.stdout.write(
            f"Selected {selected} agent access record(s) dated before {cutoff.isoformat()} "
            f"(older than {days} days, from {source})."
        )
        if options["dry_run"]:
            report(self, {"deleted": selected}, dry_run=True)
            return
        if selected and not options["yes"]:
            try:
                answer = input(f"Delete agent access records older than {days} days? [yes/no]: ")
            except (EOFError, OSError) as exc:
                raise CommandError(
                    "Pruning requires confirmation; use --yes for non-interactive use."
                ) from exc
            if answer.strip().lower() != "yes":
                raise CommandError("Pruning cancelled.")
        deleted = prunable.delete()[0] if selected else 0
        report(self, {"deleted": deleted, "retained": AgentAccess.objects.count()})
