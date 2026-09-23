# Development guide

How to run the package locally, try it by hand and test it. For installing into a real
site, see [INSTALL.md](../INSTALL.md); for workflow and the licensing and attribution policy,
see [CONTRIBUTING.md](../CONTRIBUTING.md).

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/350org/Wagtail-Markdown-for-Agents-and-Statistics.git
cd Wagtail-Markdown-for-Agents-and-Statistics
uv sync                                   # install package + dev deps
uv run pytest                             # test suite (runs against sandbox/)
uv run ruff check .                       # lint
uv run sandbox/manage.py migrate          # set up the sandbox Wagtail site
uv run sandbox/manage.py runserver        # http://localhost:8000
```

The development group selects patched Wagtail 7.4 and Django 5.2/6.0 release
lines. Use `uv sync --upgrade` to refresh the ignored local lock, then rerun tests
and audit the resolved environment before deployment. `tox` separately checks
legacy compatibility; its older frameworks are not a production recommendation.
Never commit environment files, private keys or local database backups. Sanitised
`.env.example` / `.env.sample` files are allowed by the ignore rules.

## The sandbox site

`sandbox/` is a throwaway Wagtail project used as the test target and for local
manual checks. It uses SQLite (`sandbox/db.sqlite3`, git-ignored), `DEBUG=True` and
an insecure fixed secret key, so never deploy it. It installs the package the way a
host project would: the middleware, the app and the public export routes under
`/markdown/`. Example page models live in `sandbox/testapp/`.
`sandbox.postgres_settings` points the test suite at PostgreSQL through the
`AGENTMD_TEST_*` environment variables.

Start it from this checkout:

```bash
uv sync
uv run sandbox/manage.py migrate
uv run sandbox/manage.py createsuperuser  # choose your local admin login; skip if you have one
uv run sandbox/manage.py runserver 127.0.0.1:8000
```

The Wagtail admin is at <http://localhost:8000/admin/>. **Use `localhost`, not
`127.0.0.1`, for Markdown requests:** the sandbox's Wagtail site is registered as
`localhost`, and requests for any other hostname fall through to HTML and 404s.

## Try Markdown serving

A fresh sandbox contains only Wagtail's default home page, which is not exportable.
In a second terminal, publish an example article; its export is written automatically
on publish:

```bash
uv run sandbox/manage.py shell <<'PY'
from wagtail.models import Page
from sandbox.testapp.models import ArticlePage

home = Page.objects.get(depth=2)
page = home.add_child(instance=ArticlePage(
    title="Hello agents", slug="hello-agents",
    body=[("paragraph", "<p>This page is also served as Markdown.</p>")],
))
page.save_revision().publish()
print("Published", page.url)
PY
```

Then request it as an agent would:

```bash
curl -H "Accept: text/markdown" http://localhost:8000/hello-agents/   # Markdown
curl "http://localhost:8000/hello-agents/?output_format=md"            # Markdown
curl -A "Mozilla/5.0 (compatible; GPTBot/1.2)" http://localhost:8000/hello-agents/
curl -I http://localhost:8000/hello-agents/     # HTML, with Link: rel="alternate"
curl http://localhost:8000/markdown/llms.txt
curl http://localhost:8000/markdown/manifest.json
```

A plain browser request still gets HTML. Pages created in the admin behave the same
once published; `uv run sandbox/manage.py agentmd_status` lists which pages have
current exports.

## Try the agent access report

For a separate synthetic corpus covering all six simulator edge cases, see the
[simulator fixture setup](agent-simulator.md#repeatable-local-corpus). It uses its
own database and export directory and includes a published-only preview adapter.

Open <http://localhost:8000/admin/reports/agent-access/> and sign in, or choose
**Reports → Agent access** in the admin. The report is empty until page Markdown
requests have been recorded. Each Markdown response from the curl commands above
adds a row: the `GPTBot` request appears under that agent with the `ua` method,
and the others are labelled `unknown`.

To explore charts and pagination immediately, run this in a **second terminal**
from the same checkout. It adds synthetic traffic to the local sandbox database
only; this is sample data, not evidence of real bot visits. Existing daily keys
are left unchanged when rerun.

```bash
uv run sandbox/manage.py shell <<'PY'
from datetime import UTC, datetime, timedelta
from wagtail.models import Page
from wagtail_markdown_agents.models import AgentAccess

today = datetime.now(UTC).date()
page_id = Page.objects.filter(depth=2).first().pk
rows = []
for i in range(30):
    for agent, method, count, pk in [
        ("ChatGPT-User", "query-param", 2 + i * 2, page_id),
        ("OAI-SearchBot", "accept-header", 40 - i, page_id),
        ("GPTBot", "ua", 15 + (i % 4) * 5, page_id),
        ("", "export-url", 4, 2147483600),  # missing page: retained-history display
    ]:
        rows.append(AgentAccess(
            page_id=pk, agent=agent, access_method=method,
            access_date=today - timedelta(days=29 - i), count=count,
        ))
AgentAccess.objects.bulk_create(rows, ignore_conflicts=True)
print("Sample traffic added. Refresh Reports → Agent access.")
PY
```

Refresh the report. With an initially empty statistics table, the default last 7 days
show **659 requests across 28 daily records** (plus any requests from the curl
examples above). Try combining the Unknown intent,
`export-url` method and deleted-page filters; this gives **28 requests** with a
neutral trend. Use Last 365 days for monthly buckets, or Custom dates spanning
more than 1,827 days for yearly buckets. **View time bucket counts** exposes the
chart's exact values, and pagination keeps the selected filters.

Superusers can view the report. For other users, grant Wagtail admin access and
**Can view agent access** through **Settings → Groups**. This permission covers
site-wide historical statistics, including page titles and deleted-page IDs; it
does not follow individual page-edit permissions. See the
[report guide](agent-access-stats.md#admin-report-35) for date rules, intent
overrides and counting limits. Stop the local server with Ctrl-C.

## Manual testing with bakerydemo

For realistic StreamField content, install the package into Wagtail's official demo site.
Run these commands from the **package repository root** (the directory containing
`scripts/`), not from `bakerydemo/bakerydemo`:

```bash
./scripts/bakerydemo-setup.sh   # clones ../bakerydemo, installs this package editable
cd ../bakerydemo && .venv/bin/python manage.py runserver
```

If bakerydemo is already set up, refresh its editable installation after moving or
renaming this checkout. From the **package repository root**:

```bash
uv pip install --python ../bakerydemo/.venv/bin/python -e .
cd ../bakerydemo
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

The path after `--python` is relative to your current directory. The final `.` is
required: it tells `-e` to install this checkout. If your prompt shows
`bakerydemo/bakerydemo`, return to this repository before running the install.
Stop a running demo server before migrating, then restart it. Migration `0006`
merges historical unrecognised agent labels into the empty unknown label while
preserving request counts.

The script pins bakerydemo to its last Wagtail 7.4 LTS commit (newer bakerydemo
requires Wagtail 8, which this package does not yet support). It adds the middleware
and `/markdown/` routes, loads the demo content, runs `agentmd_generate` and prints
URLs to try. bakerydemo's Wagtail site is registered as `127.0.0.1`, so use that
hostname here (the sandbox is the reverse and uses `localhost`):

```bash
curl -H "Accept: text/markdown" http://127.0.0.1:8000/blog/wild-yeast/
curl -A "GPTBot/1.2" http://127.0.0.1:8000/blog/wild-yeast/
curl http://127.0.0.1:8000/markdown/llms.txt
```

Sign in at <http://127.0.0.1:8000/admin/> (admin / changeme) and open
**Reports → Agent access** to see those requests counted. Not every page type
exports: the generate output lists skipped pages and why.
