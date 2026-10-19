"""Test settings: the sandbox plus a stand-in for 350.org's ``wtrx`` app.

The 350.org site profile imports the site's blocks and models; its tests use
the stand-in in ``tests/wtrx_stub``. The profile itself is only turned on by
the tests that exercise it.
"""

import sys
from pathlib import Path

from sandbox.settings import *  # noqa: F403

sys.path.append(str(Path(__file__).resolve().parent / "wtrx_stub"))

INSTALLED_APPS = ["wtrx", *INSTALLED_APPS]  # noqa: F405
