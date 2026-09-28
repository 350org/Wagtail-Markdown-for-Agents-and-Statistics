# Registry 2026-09-28.1 staging deployment and cache-bypass change (#19)

This record covers the controlled staging deployment of registry `2026-09-28.1` and
the replacement of its Cloudflare cache-bypass rule. The staging hostname is left
out, as in the earlier records. `HOST` stands for it below.

## Deployment

| Item | Value |
| --- | --- |
| Package revision | `42c758c` (branch `agent-registry-review-19`), installed from GitHub |
| Registry | `2026-09-28.1`: 67 identities, 19 automatic identities (20 tokens) |
| Previous registry | `2026-09-22.1` (package revision `a89dab5`) |
| Migrations | None |

The operator installed the revision, restarted the application workers and confirmed
the installed registry version on the host.

## Rule before the change (rollback)

The existing rule was read back from **Caching → Cache Rules** before any change. It
is byte-identical to the generator's output for registry `2026-09-22.1`:

```text
(http.host eq "HOST" and (lower(url_decode(http.request.uri.query)) contains "output_format" or lower(http.user_agent) contains "chatgpt-user" or lower(http.user_agent) contains "claude-searchbot" or lower(http.user_agent) contains "claude-user" or lower(http.user_agent) contains "claudebot" or lower(http.user_agent) contains "duckassistbot" or lower(http.user_agent) contains "gptbot" or lower(http.user_agent) contains "meta-externalagent" or lower(http.user_agent) contains "meta-externalfetcher" or lower(http.user_agent) contains "mistralai-user" or lower(http.user_agent) contains "oai-searchbot" or lower(http.user_agent) contains "perplexity-user" or lower(http.user_agent) contains "perplexitybot"))
```

The SHA-256 of the exact live text, with the real hostname and no trailing newline,
is `2b526dc5ea19a5bf324dd38f56ff517b28e7103cba7dc1defad65a11c456f825`. To regenerate
it for a rollback, check out `a89dab5` and run:

```bash
PYTHONPATH=src python -m wagtail_markdown_agents.cloudflare --host HOST
```

The rule was ordered after the host's cache-everything rule.

## Rule after the change

The replacement was generated from registry `2026-09-28.1`. It keeps the 12 previous
user-agent clauses and adds `amzn-searchbot`, `anomura`, `cloudflare-ai-search`,
`cloudflare-ai-search-external`, `kernelsearchbot`, `kimibot`, `linerbot` and
`shapbot`. The `-external` clause is redundant, because the shorter
`cloudflare-ai-search` clause already covers it; it is harmless.

```text
(http.host eq "HOST" and (lower(url_decode(http.request.uri.query)) contains "output_format" or lower(http.user_agent) contains "amzn-searchbot" or lower(http.user_agent) contains "anomura" or lower(http.user_agent) contains "chatgpt-user" or lower(http.user_agent) contains "claude-searchbot" or lower(http.user_agent) contains "claude-user" or lower(http.user_agent) contains "claudebot" or lower(http.user_agent) contains "cloudflare-ai-search" or lower(http.user_agent) contains "cloudflare-ai-search-external" or lower(http.user_agent) contains "duckassistbot" or lower(http.user_agent) contains "gptbot" or lower(http.user_agent) contains "kernelsearchbot" or lower(http.user_agent) contains "kimibot" or lower(http.user_agent) contains "linerbot" or lower(http.user_agent) contains "meta-externalagent" or lower(http.user_agent) contains "meta-externalfetcher" or lower(http.user_agent) contains "mistralai-user" or lower(http.user_agent) contains "oai-searchbot" or lower(http.user_agent) contains "perplexity-user" or lower(http.user_agent) contains "perplexitybot" or lower(http.user_agent) contains "shapbot"))
```

The SHA-256 of the exact text with the real hostname is
`b9784c44ea2387b0337e0fd5848aff460fafc9f973d5c3acab24d70660f9acb3`.

## Checks before the change

These requests ran on 28 September 2026 against the home page, the one page with an
advertised Markdown alternate. The new package was deployed and the old rule was
still live. Each User-Agent carried a unique marker.

| Request | Content type | `cf-cache-status` | Shows |
| --- | --- | --- | --- |
| Browser (first, warming the URL) | `text/html` | `MISS` | HTML cached for the URL |
| `KimiBot/1.0`, warm URL | `text/html` | `HIT` | Old rule does not bypass the new identity |
| `PetalBot`, warm URL | `text/html` | `HIT` | Recognition-only; not bypassed |
| `GPTBot/1.4`, warm URL | `text/markdown` | `DYNAMIC` | Existing identity bypassed and served Markdown |
| Browser again | `text/html` | `HIT` | No Markdown in the cache |
| `KimiBot/1.0`, unique cold query URL | `text/markdown` (`private, no-store`) | `BYPASS` | Origin runs the new registry |
| `PetalBot`, unique cold query URL | `text/html` | `MISS` | Origin keeps HTML for recognition-only identities |

The GPTBot and cold-URL KimiBot Markdown responses each added one counter increment
to the home page's statistics.

## Checks after the change

The operator replaced the expression in the existing bypass rule and saved it. These
requests then ran against the same home page. It was warm, as the first browser
request's `HIT` shows. Each User-Agent carried a new unique marker.

| Request | Content type | `cf-cache-status` | Shows |
| --- | --- | --- | --- |
| Browser | `text/html` | `HIT` | URL warm with cached HTML |
| `KimiBot/1.0` | `text/markdown` | `DYNAMIC` | New identity bypassed and served Markdown |
| `Amzn-SearchBot/0.1` in its documented header shape | `text/markdown` | `DYNAMIC` | New identity bypassed and served Markdown |
| `GPTBot/1.4` | `text/markdown` | `DYNAMIC` | Existing identity unchanged |
| `PetalBot` | `text/html` | `HIT` | Recognition-only identity keeps cached HTML |
| `?output_format=md`, browser User-Agent | `text/markdown` | `DYNAMIC` | Query trigger unchanged |
| Browser again | `text/html` | `HIT` | No Markdown in the cache |

New identities receiving Markdown on a warm URL shows two things. The saved rule is
in effect, and it is ordered after the cache-everything rule; placed first, it would
have been overridden and KimiBot would have received the cached `HIT`. These four
Markdown responses added four counter increments to the home page.

Not covered here: the Accept-only free-plan limitation, which is unchanged and
documented in the [CDN guide](../cdn-caching.md), multi-day behaviour and edges
other than the one that served these requests.
