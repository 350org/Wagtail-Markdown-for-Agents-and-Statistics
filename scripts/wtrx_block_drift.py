#!/usr/bin/env python3
"""Run agentmd_blocks against an isolated checkout of the 350.org site.

Uses the site's base settings and real models, with no local settings, .env,
database rows or rendering. Install both projects' dependencies first.
"""

import argparse
import socket
import sys
from pathlib import Path
from unittest.mock import patch

BASELINE = Path(__file__).resolve().parents[1] / "docs/fixtures/wtrx-blocks.json"


def forbidden_network(*args, **kwargs):
    raise RuntimeError("The block drift check must not access the network.")


def forbidden_query(execute, sql, params, many, context):
    raise RuntimeError("The block drift check must not query a database.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path, help="Path to the wagtail-wtr-350 source checkout")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="Print a replacement snapshot")
    output.add_argument("--compare", type=Path, default=BASELINE, help="Snapshot to compare")
    args = parser.parse_args()
    site = args.site.resolve()
    if not (site / "wagtail_wtr/settings/base.py").is_file():
        parser.error(f"Not a wagtail-wtr-350 checkout: {site}")
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
        from wagtail_wtr.settings import base

        configuration = {name: getattr(base, name) for name in dir(base) if name.isupper()}
        configuration.update(
            SECRET_KEY="agentmd-block-drift-check-only",
            DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
            CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}},
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            WAGTAILADMIN_BASE_URL="https://example.org",
            WAGTAIL_MARKDOWN_AGENTS={"AUTO_GENERATE": False},
            INSTALLED_APPS=[
                *base.INSTALLED_APPS,
                "wagtail_markdown_agents",
                "wagtail_markdown_agents.contrib.wtrx",
            ],
        )
        settings.configure(**configuration)
        from django.db import connection

        with connection.execute_wrapper(forbidden_query):
            django.setup()
            options = {"json": True} if args.json else {"compare": str(args.compare)}
            try:
                call_command("agentmd_blocks", skip_checks=True, **options)
            except CommandError as exc:
                parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
