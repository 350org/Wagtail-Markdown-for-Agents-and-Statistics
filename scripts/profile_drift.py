#!/usr/bin/env python3
"""Compare a site's blocks with a site profile's snapshot, or write a new snapshot.

Loads the site's real models from a source checkout with the profile turned
on, then runs ``agentmd_blocks``: no database, cache, network or local
settings files are used, and nothing is rendered. Install the site's
dependencies and this package in the same environment first.

    python scripts/profile_drift.py SITE --settings mysite.settings.base \\
        --profile myprofile_package [--snapshot FILE | --json]

Without ``--snapshot``, a profile given as a package is compared against the
``blocks.json`` beside its ``profile.yaml``. The exit status is non-zero when
blocks, renderers, template hints or fields inside templated blocks differ.
"""

import argparse
import importlib
import socket
import sys
from pathlib import Path
from unittest.mock import patch


def forbidden_network(*args, **kwargs):
    raise RuntimeError("The drift check must not access the network.")


def forbidden_query(execute, sql, params, many, context):
    raise RuntimeError("The drift check must not query a database.")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("site", type=Path, help="Path to the site's source checkout")
    parser.add_argument("--settings", required=True, help="The site's settings module")
    parser.add_argument("--profile", required=True, help="PROFILE value: a package or file path")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="Print a replacement snapshot")
    output.add_argument("--snapshot", type=Path, help="Snapshot to compare against")
    args = parser.parse_args()
    site = args.site.resolve()
    if not site.is_dir():
        parser.error(f"Not a directory: {site}")
    sys.path.insert(0, str(site))

    with (
        patch.object(socket.socket, "connect", forbidden_network),
        patch.object(socket.socket, "connect_ex", forbidden_network),
        patch.object(socket, "create_connection", forbidden_network),
        patch.object(socket, "getaddrinfo", forbidden_network),
    ):
        import django
        from django.conf import settings
        from django.core.management import CommandError, call_command

        base = importlib.import_module(args.settings)
        configuration = {name: getattr(base, name) for name in dir(base) if name.isupper()}
        apps = list(configuration.get("INSTALLED_APPS", []))
        configuration.update(
            SECRET_KEY="agentmd-profile-drift-check-only",
            DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
            CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}},
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            WAGTAILADMIN_BASE_URL="https://example.org",
            WAGTAIL_MARKDOWN_AGENTS={"AUTO_GENERATE": False, "PROFILE": args.profile},
            INSTALLED_APPS=apps
            if "wagtail_markdown_agents" in apps
            else [*apps, "wagtail_markdown_agents"],
        )
        settings.configure(**configuration)
        from django.db import connection

        with connection.execute_wrapper(forbidden_query):
            django.setup()
            if args.json:
                options = {"json": True}
            else:
                snapshot = args.snapshot or default_snapshot(parser, args.profile)
                options = {"compare": str(snapshot)}
            try:
                call_command("agentmd_blocks", skip_checks=True, **options)
            except CommandError as exc:
                parser.exit(1, f"{exc}\n")


def default_snapshot(parser, profile):
    from wagtail_markdown_agents.profile import resolve_path

    snapshot = resolve_path(profile).with_name("blocks.json")
    if not snapshot.is_file():
        parser.error(f"No snapshot at {snapshot}; pass --snapshot or write one with --json")
    return snapshot


if __name__ == "__main__":
    main()
