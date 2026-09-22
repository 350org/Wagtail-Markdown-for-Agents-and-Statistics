"""Seed the isolated sandbox and print the simulator's explicit fixture configuration."""

import json

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError
from wagtail.models import Site

from sandbox.testapp.simulator_fixtures import create_fixtures


class Command(BaseCommand):
    help = "Create synthetic simulator fixtures using sandbox.simulator_settings (local only)."

    def handle(self, *args, **options):
        if not getattr(settings, "SIMULATOR_FIXTURES_ENABLED", False):
            raise CommandError("Use sandbox.simulator_settings")
        site = Site.objects.get(is_default_site=True)
        if site.hostname != "localhost":
            raise CommandError("The fixture sandbox must use the localhost site")
        site.port = 8000
        site.save(update_fields=["port"])
        Site.clear_site_root_paths_cache()
        try:
            fixtures = create_fixtures(site)
        except (ImproperlyConfigured, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(fixtures, indent=2))
