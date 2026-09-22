"""Isolated local simulator fixtures. Never deploy this sandbox configuration."""

from .settings import *  # noqa: F403
from .settings import BASE_DIR as SANDBOX_DIR
from .settings import MIDDLEWARE as BASE_MIDDLEWARE

BASE_DIR = SANDBOX_DIR / "simulator-data"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
MEDIA_ROOT = BASE_DIR / "media"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
SIMULATOR_FIXTURES_ENABLED = True
WAGTAIL_MARKDOWN_AGENTS = {"AUTO_GENERATE": False}
MIDDLEWARE = [
    BASE_MIDDLEWARE[0],
    "sandbox.testapp.simulator_fixtures.PublishedPreviewMiddleware",
    *BASE_MIDDLEWARE[1:],
]
