"""Isolated MySQL/MariaDB write benchmark settings, not a deployment target.

Full application migrations exceed MySQL path-index limits; see
docs/agent-stats-benchmarks.md. Only the scratch write runner uses these settings.
"""

import os

from .settings import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("AGENTMD_TEST_DB", "agentmd_test"),
        "USER": os.environ.get("AGENTMD_TEST_USER", "root"),
        "PASSWORD": os.environ.get("AGENTMD_TEST_PASSWORD", "agentmd-test"),
        "HOST": os.environ.get("AGENTMD_TEST_HOST", "127.0.0.1"),
        "PORT": os.environ.get("AGENTMD_TEST_PORT", "3306"),
        "OPTIONS": {"charset": "utf8mb4", "init_command": "SET sql_mode='STRICT_TRANS_TABLES'"},
        "TEST": {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_bin"},
    }
}
