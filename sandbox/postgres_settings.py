"""Isolated PostgreSQL test configuration; never used by the sandbox server."""

import os

from .settings import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("AGENTMD_TEST_DB", "agentmd_test"),
        "USER": os.environ.get("AGENTMD_TEST_USER", "postgres"),
        "PASSWORD": os.environ.get("AGENTMD_TEST_PASSWORD", "agentmd-test"),
        "HOST": os.environ.get("AGENTMD_TEST_HOST", "127.0.0.1"),
        "PORT": os.environ.get("AGENTMD_TEST_PORT", "5432"),
    }
}
