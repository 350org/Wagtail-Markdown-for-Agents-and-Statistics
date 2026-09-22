# Installing wagtail-markdown-for-agents into a Wagtail site

These steps install the package into an existing Wagtail site (the **host site**),
configure it, and verify that it is serving Markdown. To work on the package itself,
see the [development guide](docs/development.md) instead.

Throughout, **site directory** means the host site (it contains `manage.py`). Run every
command with the host site's virtual environment activated.

## Requirements

- Package bounds: Python 3.11+ and Wagtail 6.3+ (below 8).
- Compatibility matrix in [tox.ini](tox.ini):

| Python | Django | Wagtail |
| --- | --- | --- |
| 3.11 | 4.2 | 6.3 |
| 3.12 | 5.2 | Latest compatible 7.x |
| 3.13 | 5.2 | 7.0 and latest compatible 7.x |
| 3.13 | 6.0 | 7.4+ below 8 |

These are specific combinations, not every permutation of those versions. For a
new deployment, use current patches of Wagtail 7.4 LTS with Django 5.2 LTS or 6.0
and a compatible Python version; check [Wagtail's compatibility table](https://docs.wagtail.org/en/stable-7.4.x/releases/upgrading.html).
The 4.2 environment is a legacy compatibility check: [Django 4.2 reached the end
of extended support on 7 April 2026](https://www.djangoproject.com/weblog/2026/apr/07/security-releases/).
Passing package tests does not extend upstream security support. Python versions
beyond 3.13 are allowed by metadata but are not covered by this package's matrix.

SQLite and PostgreSQL are the verified database backends. Full MySQL installation
is not verified; the [benchmark record](docs/agent-stats-benchmarks.md) documents
an existing migration limitation, despite successful isolated counter writes.

## 1. Install the package

The package is installed from its Git repository. Pin a tag or commit so deployments
are reproducible, and add the same line to the site's requirements file:

```bash
source /path/to/site/env/bin/activate
python -m pip install "wagtail-markdown-for-agents @ git+https://github.com/350org/Wagtail-Markdown-for-Agents-and-Statistics.git@TAG_OR_COMMIT"
```

Replace `TAG_OR_COMMIT` with a reviewed revision in the new repository. For a private
repository use the SSH form,
`git+ssh://git@github.com/350org/Wagtail-Markdown-for-Agents-and-Statistics.git@TAG_OR_COMMIT`,
with a deploy key on the server. For a host site managed by uv, use `uv add` with the
same URL.

To run the site against a local checkout while changing the package, install it
editable instead: `python -m pip install -e /absolute/path/to/wagtail-markdown-for-agents`.
Python then imports the code straight from that directory, and nothing is copied into
the site.

## 2. Configure the site

In the site's settings (for a standard Wagtail project, `<project>/settings/base.py`):

```python
INSTALLED_APPS = [
    # …the site's own apps…
    "wagtail_markdown_agents",
    # …Wagtail and Django apps…
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "wagtail_markdown_agents.middleware.AgentMarkdownMiddleware",
    # …the rest of the site's middleware…
]

# All keys optional; see src/wagtail_markdown_agents/settings.py for defaults.
WAGTAIL_MARKDOWN_AGENTS = {}
```

Place the middleware directly after `SecurityMiddleware` and before
`CommonMiddleware`; `manage.py check` reports a wrong order. Read
the [negotiation guide](docs/negotiation.md) for the triggers, the requests it
intercepts and the HTML fallback, and the [discovery guide](docs/discovery-headers.md)
for the `Link`/`Vary: Accept` headers and the `{% agent_markdown_link %}` tag.

Two defaults are deliberately broad, so decide on them before the first generation:
**every non-root page type is eligible** (`PAGE_TYPES = None`) and **generation runs
automatically on publish** (`AUTO_GENERATE = True`). Set `PAGE_TYPES` to an explicit
list on sites with page types that should stay HTML-only. The
[checks guide](docs/system-checks.md) lists every setting's expected shape.

Include `wagtail_markdown_agents.urls` before Wagtail's catch-all in the site's
URLconf, for example at `path("markdown/", include("wagtail_markdown_agents.urls"))`.
See the [public route guide](docs/public-export-routes.md) for the complete setup.

Automatic generation defaults to **True** (unlike the WordPress plugin's default
False). Publishing eligible supported page types refreshes Markdown and discovery
after commit. Set `WAGTAIL_MARKDOWN_AGENTS["AUTO_GENERATE"] = False` to disable
routine lifecycle regeneration while configuring a site. Unpublish/delete still
withdraw owned exports immediately. Read the [lifecycle guide](docs/publish-lifecycle.md)
for failure reporting, restrictions and subtree moves.

## 3. Migrate

From the site directory:

```bash
python manage.py migrate wagtail_markdown_agents
```

This creates the package's tables in the **site's** database; the package has no
database of its own. Do not run `makemigrations` just because you installed the
package — its migrations ship with it.

Apply all package migrations before serving traffic. `0005_agentaccess` adds the
[daily statistics](docs/agent-access-stats.md) table; `0006_anonymize_unknown_agents`
merges legacy arbitrary User-Agent labels into the unknown bucket without losing
request totals. Pause workers running the older code during upgrade. Recording is
connected automatically for successful page Markdown GETs. Counters are kept until you run
`python manage.py agentmd_prune_stats`; schedule it with `--yes` if the
`STATS_RETENTION_DAYS` period should be enforced routinely.

## 4. Verify

From the site directory:

```bash
# The package imports (from site-packages, or from the checkout if installed editable)
python -c "import wagtail_markdown_agents; print(wagtail_markdown_agents.__file__)"

# Migrations applied through [X] 0006_anonymize_unknown_agents
python manage.py showmigrations wagtail_markdown_agents

# Site loads cleanly: no wagtail_markdown_agents errors or warnings
# (see docs/system-checks.md for what each ID means)
python manage.py check

# Commands registered: agentmd_delete, agentmd_generate, agentmd_generate_indexes,
# agentmd_prune_stats, agentmd_revoke_ineligible, agentmd_status
python manage.py help | grep -A7 wagtail_markdown_agents

# The package's model and table exist
python manage.py shell -c "from wagtail_markdown_agents.models import PageAgentSettings; print(PageAgentSettings.objects.count(), 'rows')"
```

All five succeeding means the package is installed. Inspect and generate existing
content with:

```bash
python manage.py agentmd_status
python manage.py agentmd_generate --dry-run
python manage.py agentmd_generate
```

See the [command guide](docs/management-commands.md) for scopes, freshness checks,
`--force`, deletion confirmation and failure recovery.

## 5. Check what agents receive

With the site running and at least one eligible page published and generated, request
it the three ways an agent can, plus once as a browser:

```bash
curl -s -o /dev/null -w '%{content_type}\n' "https://www.example.org/a-published-page/?output_format=md"   # text/markdown
curl -s -o /dev/null -w '%{content_type}\n' -H 'Accept: text/markdown' https://www.example.org/a-published-page/   # text/markdown
curl -s -o /dev/null -w '%{content_type}\n' -A 'GPTBot/1.2' https://www.example.org/a-published-page/              # text/markdown
curl -sI https://www.example.org/a-published-page/ | grep -i -E '^(content-type|link|vary)'                        # text/html, with Link: rel="alternate"
```

Each Markdown response is counted in the Wagtail admin under **Reports → Agent
access** ([statistics guide](docs/agent-access-stats.md)). Editors can exclude an
individual page from the page editor's actions menu, **Markdown settings**.

## 6. Configure the cache in front of the site

If the site is behind a CDN or page cache, the checks in step 5 can pass against the
origin and still fail for real agents: a shared cache that already holds a page's HTML
answers agent requests itself, and the package is never consulted. This is the normal
state of a live site, not an edge case. Read the
[CDN and cache guide](docs/cdn-caching.md) before going live. It opens with a
Cloudflare checklist, covers Varnish/Fastly, nginx, LiteSpeed and Django's cache
middleware, and ends with a verification sequence to run through the cache.

For bounded deployment checks and counter reconciliation, see the repository
[agent traffic simulator](docs/agent-simulator.md). Its local tests do not replace
verification against your configured CDN or genuine vendor-origin requests.

## Upgrading

Install the new tag or commit, then from the site directory:

```bash
python manage.py migrate wagtail_markdown_agents
python manage.py check
python manage.py agentmd_revoke_ineligible   # after changes to enabled page types or eligibility hooks
python manage.py agentmd_status
```

[CHANGELOG.md](CHANGELOG.md) records what changed, including new migrations and
settings.

## Uninstalling

Back up any statistics or settings you need to retain. Stop serving requests and
pause publishing/export jobs during removal. While the package and its ownership
tables still exist, inspect and delete managed exports, then remove the tables:

```bash
python manage.py agentmd_delete --all --dry-run
python manage.py agentmd_delete --all  # prompts for confirmation
python manage.py migrate wagtail_markdown_agents zero
```

Resolve any deletion or pending-cleanup failures before reversing migrations;
dropping ownership tables first loses the information needed to clean storage.
The migration reversal deletes the package's settings, export metadata and counters.

1. Remove the package URLconf include, template tags, panel mixins and project
   renderer/hook imports, plus any scheduled package commands.
2. Delete `"wagtail_markdown_agents"` from `INSTALLED_APPS`, the middleware line, and
   `WAGTAIL_MARKDOWN_AGENTS`. Remove the dependency from the site's requirements or
   project file and update its lockfile.
3. `python -m pip uninstall wagtail-markdown-for-agents`
4. Run `python manage.py check`, collect static files as required by your deployment,
   restart workers and verify normal HTML routes before reopening traffic. Review
   any external export copies and CDN rules separately with the site operator.
