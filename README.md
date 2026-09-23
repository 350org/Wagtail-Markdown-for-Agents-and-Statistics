# wagtail-markdown-for-agents

Serve your Wagtail content to AI agents as Markdown.

When an AI agent asks for a page with `Accept: text/markdown`, `?output_format=md`, or a
known AI User-Agent, this package serves a clean, pre-generated Markdown version of the
page instead of rendering HTML — cheaper for you, far fewer tokens for the agent. It also
exports your whole site as a browsable Markdown tree with `llms.txt` and a content-hash
manifest for incremental sync.

This is a Wagtail port of the WordPress plugin
[Markdown for Agents and Statistics](https://wordpress.org/plugins/markdown-for-agents-and-statistics/),
developed in collaboration with [350.org](https://350.org) and
[The Chancery Lane Project](https://chancerylaneproject.org).

> **Status: v0.1 in development** (`0.1.0.dev0`). Generation on publish, managed export
> routes, query/Accept/User-Agent negotiation, HTML discovery headers, configuration
> checks, per-page exclusion and daily agent access statistics with a Wagtail admin
> report are implemented and tested. A repository traffic simulator supports
> deployment verification and counter reconciliation. Remaining v0.1 work and the
> later roadmap are documented in the acceptance scenarios and historical issue
> references. New work belongs in the
> [350.org repository](https://github.com/350org/Wagtail-Markdown-for-Agents-and-Statistics/issues);
> legacy issue numbers require mapping as work is migrated.

## How it works

```python
INSTALLED_APPS = [
    "wagtail_markdown_agents",
    # …
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "wagtail_markdown_agents.middleware.AgentMarkdownMiddleware",
    # …
]

WAGTAIL_MARKDOWN_AGENTS = {
    # all optional — sensible defaults; see docs/design.md §3.5
}
```

```bash
python manage.py agentmd_generate     # export the site as Markdown
```

Then `curl -H "Accept: text/markdown" https://example.org/blog/my-post/` returns the
Markdown file; browsers keep getting HTML, which carries a
`Link: <…>; rel="alternate"; type="text/markdown"` header so agents can discover it.
Publishing a page refreshes its export automatically; unpublishing, deleting,
restricting or excluding a page withdraws it immediately.

**[INSTALL.md](INSTALL.md) is the place to start**: installation, settings, migrations,
verification, and the cache configuration a live site needs.

## Documentation

| To do this | Read |
| --- | --- |
| Install, configure, verify, upgrade, uninstall | [INSTALL.md](INSTALL.md) |
| Review handover readiness, verification limits and open client decisions | [Pre-transfer review](docs/transfer-readiness.md) |
| Review recognised agents and automatic Markdown policy | [Agent registry](docs/agent-registry.md) |
| Put the site behind Cloudflare, another CDN or a page cache | [CDN and cache guide](docs/cdn-caching.md) |
| Understand which requests get Markdown | [Content negotiation](docs/negotiation.md) |
| Let agents discover the Markdown from HTML | [Discovery headers and template tag](docs/discovery-headers.md) |
| Serve the export tree, `llms.txt` and the manifest over HTTP | [Public export routes](docs/public-export-routes.md), [llms.txt](docs/llms-txt.md), [manifest](docs/manifest.md), [indexes](docs/indexes.md) |
| Generate, inspect, delete and prune from the command line | [Management commands](docs/management-commands.md) |
| Know what happens on publish, unpublish, move, restrict and exclude | [Publication and eligibility lifecycle](docs/publish-lifecycle.md) |
| Read the agent access report and understand its limits | [Agent access statistics](docs/agent-access-stats.md), [benchmarks](docs/agent-stats-benchmarks.md) |
| Plan simulated traffic and reconcile deployment evidence | [Agent traffic simulator](docs/agent-simulator.md) |
| Review measured cache behaviour and counter reconciliation | [Bounded live verification, 21 September 2026](docs/verification/2026-09-21-bounded-live-run.md) |
| Fix a `manage.py check` message | [Configuration checks](docs/system-checks.md) |
| Control how a page type or block becomes Markdown | [Page rendering](docs/page-rendering.md), [internal links](docs/internal-links.md) |
| Add an exclusion checkbox to a page model's editor | [Editor exclusion panel](docs/editor-exclusion-panel.md) |
| Change where and how export files are stored | [Managed export storage](docs/storage-writer.md) |
| Work on the package | [Development guide](docs/development.md), [CONTRIBUTING.md](CONTRIBUTING.md), [architecture](docs/design.md), [acceptance scenarios](docs/acceptance/README.md), [WordPress parity audit](docs/wordpress-parity-audit.md) |
| Track WordPress parity and prepare a release | [Current implementation matrix](docs/wordpress-parity-status.md), [drift ledger](docs/wordpress-drift-ledger.md), [release checklist](docs/release-checklist.md) |

## Excluding a page

Open a saved page in the Wagtail editor, expand the actions menu beside **Save
draft**, and choose **Markdown settings**. Tick **Exclude this page from Markdown
export** and save. Changes apply immediately without republishing. The page's HTML
and child-page exclusions are unchanged; eligible children can still have a
directory index at the parent's export path.

You need permission to edit that page, and it must not be locked against you.
Clearing the checkbox restores eligible published content when automatic generation
is enabled. With `AUTO_GENERATE=False`, run `agentmd_generate` to restore it.
Exclusion still withdraws the page's export when automatic generation is disabled.

Projects can opt individual page models into an in-editor checkbox with
[`AgentMarkdownPanelMixin`](docs/editor-exclusion-panel.md), including guidance
for existing custom forms and Settings tabs.

## Roadmap

- **v0.1 — generate + serve**: StreamField→Markdown block-renderer registry, static
  export mirroring the URL tree, `llms.txt` + `manifest.json`, content-negotiation
  middleware, publish/unpublish/move signal wiring, management commands, agent access
  statistics with a Wagtail admin reporting view.
- **v0.2 — operational hardening**: multi-site export, runtime-editable agent list,
  task backend with debounced rebuilds, docs site.
- **v1.0 — parity + stable**: OKF zip bundle, ARD `ai-catalog.json`, `changes.json`
  deltas, full hook parity with the WordPress plugin. (Taxonomy export is a
  nice-to-have outside the milestones.)

## Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                   # install package + dev deps
uv run pytest                             # test suite (runs against sandbox/)
uv run ruff check .                       # lint
```

The [development guide](docs/development.md) covers the local sandbox site, trying
Markdown serving and the agent access report by hand, and [setting up or refreshing
Wagtail's bakerydemo](docs/development.md#manual-testing-with-bakerydemo).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), including the licensing and attribution policy.

## Licence

[GPL-3.0-or-later](LICENSE). Copyright (c) 2026, 350.org.
