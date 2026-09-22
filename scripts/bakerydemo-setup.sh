#!/usr/bin/env bash
# Set up Wagtail's bakerydemo as a sibling checkout with this package
# installed editable — realistic StreamField content for manual agent testing.
#
# bakerydemo is pinned to its last Wagtail 7.4 LTS commit: 350.org production
# runs Wagtail 7.x and this package supports wagtail<8. Newer bakerydemo
# requires Wagtail 8 and fails to import once uv resolves Wagtail back to 7.4.
#
# Usage: ./scripts/bakerydemo-setup.sh
# Then:  cd ../bakerydemo && .venv/bin/python manage.py runserver
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BAKERY_DIR="$(dirname "$REPO_DIR")/bakerydemo"
BAKERY_REF="8e2b625755d8942412d5b7627b146a795933b8b2"  # 2026-08-19, wagtail>=7.4,<7.5
MARKER="# wagtail-markdown-for-agents (added by bakerydemo-setup.sh)"
SETTINGS="bakerydemo/settings/dev.py"
URLS="bakerydemo/urls.py"

if [ ! -d "$BAKERY_DIR" ]; then
    echo "Cloning bakerydemo into $BAKERY_DIR"
    git clone https://github.com/wagtail/bakerydemo.git "$BAKERY_DIR"
fi

cd "$BAKERY_DIR"

if [ "$(git rev-parse HEAD)" != "$BAKERY_REF" ]; then
    # Undo only this script's own patches; any other local change stops the run.
    for f in "$SETTINGS" "$URLS"; do
        if grep -qF "$MARKER" "$f"; then
            git checkout -- "$f"
        fi
    done
    if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
        echo "bakerydemo has local changes; commit or stash them first." >&2
        exit 1
    fi
    if [ -f .git/shallow ]; then
        git fetch --unshallow
    fi
    git -c advice.detachedHead=false checkout "$BAKERY_REF"
fi

if [ ! -d .venv ]; then
    uv venv .venv
fi

REQS="requirements/development.txt"
[ -f "$REQS" ] || REQS="requirements/base.txt"
[ -f "$REQS" ] || REQS="requirements.txt"
uv pip install --python .venv -r "$REQS"
uv pip install --python .venv -e "$REPO_DIR"

if [ ! -f .env ] && [ -f .env.example ]; then
    cp .env.example .env
fi

if ! grep -qF "$MARKER" "$SETTINGS"; then
    cat >> "$SETTINGS" <<PYEOF

$MARKER
INSTALLED_APPS = INSTALLED_APPS + ["wagtail_markdown_agents"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware",
              "wagtail_markdown_agents.middleware.AgentMarkdownMiddleware"] + [
    m for m in MIDDLEWARE if m != "django.middleware.security.SecurityMiddleware"
]
PYEOF
    echo "Patched $SETTINGS"
fi

if ! grep -qF "$MARKER" "$URLS"; then
    cat >> "$URLS" <<PYEOF

$MARKER
urlpatterns.insert(0, path("markdown/", include("wagtail_markdown_agents.urls")))
PYEOF
    echo "Patched $URLS"
fi

.venv/bin/python manage.py migrate --noinput

# load_initial_data is not idempotent; only seed an empty page tree.
if [ "$(.venv/bin/python manage.py shell -c 'from wagtail.models import Page; print(Page.objects.count())' 2>/dev/null | tail -1)" -le 2 ]; then
    .venv/bin/python manage.py load_initial_data
fi

# Fixture loading does not publish pages, so build the exports explicitly.
.venv/bin/python manage.py agentmd_generate

HOST="$(.venv/bin/python manage.py shell -c 'from wagtail.models import Site; print(Site.objects.get(is_default_site=True).hostname)' 2>/dev/null | tail -1)"

echo
echo "Done. Start bakerydemo with:"
echo "  cd $BAKERY_DIR && .venv/bin/python manage.py runserver"
echo "Admin:     http://$HOST:8000/admin/ (admin / changeme)"
echo "Markdown:  curl -H 'Accept: text/markdown' http://$HOST:8000/blog/wild-yeast/"
echo "llms.txt:  curl http://$HOST:8000/markdown/llms.txt"
echo "Report:    http://$HOST:8000/admin/reports/agent-access/"
echo "Markdown is served only for the Wagtail site hostname ($HOST)."
