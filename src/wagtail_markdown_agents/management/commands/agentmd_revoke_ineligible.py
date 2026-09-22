from django.core.management.base import BaseCommand

from ...export.lifecycle import revoke_ineligible


class Command(BaseCommand):
    help = (
        "Withdraw owned exports disallowed by current policy; run after eligibility config changes."
    )

    def handle(self, *args, **options):
        revoked = revoke_ineligible()
        self.stdout.write(f"Revoked exports for {len(revoked)} ineligible page(s).")
