# Configuration checks

The package registers Django system checks (#19/#29). They run with
`python manage.py check`, at `runserver` start and before `migrate`; they read
configuration only and never query the database, touch storage or generate
exports.

| ID | Level | Condition | Fix |
| --- | --- | --- | --- |
| `wagtail_markdown_agents.E001` | Error | Export storage is unusable: `BASE_DIR` absent with no `STORAGE` alias, or the alias is not in `STORAGES`. | Set `WAGTAIL_MARKDOWN_AGENTS["STORAGE"]` to a `STORAGES` alias, or keep `BASE_DIR`. |
| `wagtail_markdown_agents.W001` | Warning | `AgentMarkdownMiddleware` is not in `MIDDLEWARE`. Negotiation at page URLs and discovery headers are off; the explicit routes still work. | Add it after `SecurityMiddleware` and before `CommonMiddleware`. |
| `wagtail_markdown_agents.E002` | Error | The middleware is listed before `SecurityMiddleware`. | Move it after `SecurityMiddleware`. |
| `wagtail_markdown_agents.E003` | Error | The middleware is listed after `CommonMiddleware`, so slash-appending redirects would run before negotiation. | Move it before `CommonMiddleware`. |
| `wagtail_markdown_agents.E004` | Error | `WAGTAIL_MARKDOWN_AGENTS` is not a dict. | Use a dict; every key is optional. |
| `wagtail_markdown_agents.W002` | Warning | A key in `WAGTAIL_MARKDOWN_AGENTS` is unknown and ignored (a misspelling such as `LINK_HEADERS`). The hint lists the known keys. | Correct or remove the key. |
| `wagtail_markdown_agents.E005` | Error | A known key has the wrong shape; the message names the key and the expected shape. | See the table below. |
| `wagtail_markdown_agents.W003` | Warning | `wagtail_markdown_agents.urls` is not included. Explicit export, `llms.txt` and `manifest.json` routes are unavailable. | Include the URLconf before Wagtail's catch-all. |
| `wagtail_markdown_agents.E006` | Error | The URLconf is not included **and** `NEGOTIATE_QUERY_PARAM` is disabled, so no Markdown URL can be advertised or retrieved. | Include the URLconf, or enable query negotiation. |

Silence a check you have deliberately chosen to ignore with Django's
`SILENCED_SYSTEM_CHECKS`.

## Expected setting shapes

| Key | Shape | Default |
| --- | --- | --- |
| `AUTO_GENERATE`, `LINK_HEADER`, `NEGOTIATE_QUERY_PARAM`, `NEGOTIATE_ACCEPT_HEADER`, `NEGOTIATE_USER_AGENT`, `INCLUDE_HIERARCHY`, `INCLUDE_OWNER` | `True` or `False` | `True`, `True`, `True`, `True`, `True`, `False`, `False` |
| `CONTENT_SIGNAL` | Header value without control characters; `""` omits the header | `"ai-input=yes, search=yes"` |
| `STATS_RETENTION_DAYS` | Positive whole number of days kept by `agentmd_prune_stats` (#36) | `90` |
| `DISCOVERY_CACHE_TIMEOUT` | Seconds, `0` or more; `0` disables the discovery cache | `60` |
| `LLMS_TXT_DESCRIPTION` | String | `""` |
| `PAGE_TYPES` | `None` or a list of `"app_label.ModelName"` | `None` |
| `PAGE_FIELDS` | `None` or `{"app_label.ModelName": ["field", …]}`; model and field names are validated when a page renders | `None` |
| `RENDERERS` | `{"dotted.BlockClass": "dotted.renderer"}` | `{}` |
| `SITES` | `"default"`, `"all"` or a list of hostnames | `"default"` |
| `STORAGE` | `None` or a `STORAGES` alias (checked by `E001`) | `None` |

## Defaults worth knowing before the first deploy

- **Every non-root page type is eligible by default.** `PAGE_TYPES = None`
  exports and serves all page types that pass the other policy checks. This is
  broader than the WordPress plugin's `post` and `page` default. Set an explicit
  list on sites with page types that should stay HTML-only, and run
  `agentmd_revoke_ineligible` after narrowing it.
- **Generation is on by default.** `AUTO_GENERATE = True` regenerates exports
  after every publish. Turning it off never turns off revocation on unpublish,
  delete, restriction or exclusion.
- **Discovery headers are on by default.** `LINK_HEADER = True` adds `Link` and
  `Vary: Accept` to eligible HTML responses; see the
  [discovery guide](discovery-headers.md) for the cache and the User-Agent trade-off.
