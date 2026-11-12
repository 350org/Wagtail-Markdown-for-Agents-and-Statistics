# Agent access statistics

Successful page Markdown GETs record daily `AgentAccess` counters (#32/#33).
HTML page reads by agents in the registry are counted in the same table, as their
own access method (#61).
Apply migrations through `0006_anonymize_unknown_agents` with `python manage.py migrate` before serving
traffic. App startup connects the recorder automatically; no extra middleware or
settings are required.

## What is counted

The shared `markdown_served` signal records response selection once, after storage,
eligibility and response-header checks succeed. Negotiated requests use
`query-param`, `accept-header` or `ua` in that precedence. Direct page-export GETs
always use `export-url`, regardless of query or negotiation headers.

Missing-file fallback, errors, vetoes, HEAD and previews are excluded from
Markdown counts. HTML is counted separately, as below. Navigation-only indexes, `llms.txt` and manifests are excluded. An `index.md`
owned by a page is counted like any other page export. Consuming or closing the
stream does not increment again. Selecting a response is not proof that the client
received every byte, and a later streaming failure does not undo its count.

## HTML reads by registry agents (#61)

The middleware's response phase records `html` when it returns a successful HTML
page to a request whose User-Agent matches the [agent registry](agent-registry.md):

- **GET only, HTTP 200, `text/html`**, at a page's canonical URL on an enabled
  site (the same page-read rules as [discovery headers](discovery-headers.md)).
  HEAD, redirects, errors, previews and non-page routes are not counted.
- **Registry agents only.** Browsers, curl and every other client are never
  counted as HTML, so HTML counts can't become visitor analytics. The recorder
  refuses an `html` row without a registry label.
- **Every registry agent, whatever its serving policy.** That includes agents
  set to `auto_markdown: false`, such as `Claude-Agent`, which only ever read HTML,
  and agents that get Markdown but asked for a page with no export.
- **One count per response.** A request answered with Markdown is never also
  counted as HTML.

It's on by default, on the same footing as the Markdown counts: daily totals, no
IP addresses or User-Agent headers. Settings:

| Key | Default | Effect |
| --- | --- | --- |
| `COUNT_HTML` | `True` | `False` stops recording HTML reads. Counts already recorded stay until pruned. |
| `COUNT_HTML_EXCLUDE` | `[]` | Registry labels (`"GPTBot"`) or purposes (`"training"`, `"search"`, `"on-demand"`, `"mixed"`, `"unknown"`) whose HTML reads aren't recorded, case-insensitive. For busy sites that don't want a counter write for every crawler page view. |

Neither setting changes rendered documents, so changing them doesn't trigger
regeneration.

**HTML counts are a lower bound.** Pages answered by a page cache, Cloudflare (#50)
or another CDN never reach Django and aren't counted. Requests refused upstream
(HTTP 429) aren't counted either. On one WordPress site, about 42% of
ChatGPT-User's page loads were cache hits. Agents that don't name themselves in
the User-Agent (for example an `X-Agent` header or a Web Bot Auth
`Signature-Agent`) aren't recognised yet.

**Behind Cloudflare, a HEAD can count as a read.** Cloudflare forwards a HEAD that
misses its cache to Django as a GET, which is counted in either format. See
[statistics gaps](cdn-caching.md#statistics-gaps).

**Cost.** Each counted read is the same single upsert as a Markdown hit. Requests
from browsers and other clients only add a User-Agent match against the registry:
no routing work and no database query. Rows grow by at most one per page, registry
agent and UTC date, and `agentmd_prune_stats` removes them with the rest.

## Stored data

Each row contains `page_id`, `agent`, `access_method`, `access_date` and `count`.
The first four form a database-enforced unique key; dates have a separate index
for reporting and pruning. The page ID is a numeric value rather than a foreign
key, so deleting a page retains its history. Reports should resolve live pages
by ID and show a deleted-page label when that lookup is missing.

Dates are UTC, regardless of Django's active timezone or `USE_TZ`. Known agents
use the first matching entry from the dataset, preserving its canonical spelling.
Identification still runs with `NEGOTIATE_USER_AGENT = False`; that setting affects
serving only. All other clients, including curl and browsers, share the empty
label `""`, displayed as `unknown`. Arbitrary header fragments are never stored.
With registry `2026-11-06.1`, at most 73 labels can be newly recorded per page,
method and UTC date (72 identities plus unknown), regardless of how many different
User-Agent values arrive.
Methods are at most 20 characters.

No IP addresses, request URLs or full User-Agent headers are persisted. Known
labels are selected by matching client-supplied headers; they do not verify bot
identity. Intent categories are derived at read time (#34), not stored in counters.

Earlier versions retained unknown clients' first product tokens, which could
contain personal data. Migration `0006_anonymize_unknown_agents` merges those
historical rows into the unknown bucket, preserving counts for each page, method
and date and retaining canonical known-agent rows. It processes bounded batches;
restarting it is safe. Pause application workers during upgrade so older code
cannot continue writing arbitrary labels. The original labels cannot be recovered
by reversing the migration. Review any retained backups separately.

## Atomicity and failure handling

Each hit uses one parameterised SQL upsert: insert `count=1`, or atomically add
one to the existing count. PostgreSQL and SQLite use `ON CONFLICT`; MySQL/MariaDB
use `ON DUPLICATE KEY UPDATE`. The SQL never assigns `1` over an existing count.
The database write router is respected.

In normal autocommit operation this is one query. Inside a caller's transaction,
a savepoint isolates failures so the surrounding transaction remains usable.
The count participates in that transaction and is rolled back if the caller rolls
back. SQLite lock contention is retried for up to one second outside enclosing
transactions; other errors propagate to the serving signal's logging. Persistent
statistics failures are logged without preventing Markdown responses. Operators
must monitor those errors: the counters are best effort, not an audit ledger.

## Cache and reporting limits

Requests served by static hosting or a CDN without reaching Django cannot produce
application counters. A cached HTML response that bypasses negotiation likewise
does not count, as Markdown or as an HTML read. The [traffic simulator](agent-simulator.md) (#59) and live deployment reconciliation (#64) must
distinguish these requests using their own traffic and cache evidence; application
totals must not be presented as total edge traffic.

Volume checks and measured query budgets are documented in
[Agent statistics benchmarks](contributing/agent-stats-benchmarks.md) (#66).

## Retention pruning (#36)

Nothing deletes counters automatically. `python manage.py agentmd_prune_stats`
removes rows dated strictly before today's UTC date minus `--days`, defaulting to
`STATS_RETENTION_DAYS` (90): with the default, the 90 preceding UTC dates and today
are kept. Both values must be positive whole numbers. The command prints the selected
count and cutoff, prompts for `yes` unless `--yes` is given, and reports deleted and
retained counts; `--dry-run` only counts. Deletion is a single indexed `DELETE`, so
large tables are pruned without loading rows. See the
[command reference](management-commands.md#prune-statistics). Schedule it with `--yes`
if retention must be enforced routinely; runtime editing of the period is v0.2 ([old tracker #38](https://github.com/dogwonder/wagtail-markdown-for-agents/issues/38)).
For example, run `python manage.py agentmd_prune_stats --days 90 --yes` daily
through the host's scheduler. Apply appropriate request limits at the reverse
proxy/CDN: bounded labels limit row growth, but each served GET still performs a
counter write. This package does not configure a deployment's scheduler or proxy.

## Intent categories and overrides (#34)

Call `wagtail_markdown_agents.stats.categorise_agent(row.agent)` when reading a
counter. It returns `on-demand`, `search`, `training`, `mixed` or `unknown`.
No category is stored, and classification performs no database queries. Empty or unmatched labels
are unknown. Matching first checks case-insensitive exact labels in category-map
order, then
falls back to substring matching for compatibility with project hooks. Within each
pass, the first match wins. Exact labels distinguish Applebot from the historical
Applebot-Extended token. A match under an unexpected category returns `unknown` immediately. Empty substrings are
ignored. On-demand is an estimate of intent, not proof of a human-triggered fetch.
Classification is independent of `NEGOTIATE_USER_AGENT` and the detection list.

Projects can customise classification of retained known or historical labels in
`wagtail_hooks.py`. This does not add new detection labels or permit arbitrary
User-Agent values to be stored:

```python
from wagtail import hooks


@hooks.register("construct_markdown_agent_categories")
def customise_categories(categories):
    categories["on-demand"].append("GPTBot")
```

`stats.get_agent_categories()` supplies a fresh ordered dict of lists to hooks,
which mutate it in Wagtail hook order (then registration order for ties). Return
values are ignored and hook errors propagate to the caller. Hooks may clear and
repopulate the dict to change category precedence. Use string category keys and
lists of non-empty string substrings. Mutations do not change the shipped
`AGENT_CATEGORIES` or leak into later calls. The report takes one hook snapshot per
request and passes it to `categorise_agent(agent, categories=map)`, reusing each
label's result across intent filtering, rows, charts and totals. Standalone callers
can omit `categories` to build a fresh map as before.

## Admin report (#35)

Open **Reports → Agent access**, at `/admin/reports/agent-access/` when the Wagtail
admin is mounted at `/admin/`. The report uses Wagtail's `ReportView`, native admin
fields, Reports menu and pagination. The [README walkthrough](contributing/development.md#try-the-agent-access-report)
provides sandbox startup commands and optional synthetic traffic.

### Access and filters

Superusers have access. Other active users need both `wagtailadmin.access_admin`
and `wagtail_markdown_agents.view_agentaccess`. The latter appears as **Can view
agent access** in Wagtail's group permission editor. This grants site-wide
historical statistics, including current page titles regardless of page-edit
permissions. Grant it only to groups intended to see that reporting scope.
Menu visibility and the report URL enforce the same access; staff status alone
does not grant access. No counter edit/delete interface is registered.

Date presets are the last 7, 30, 90 or 365 days; the default is **7 inclusive UTC
dates**, today and the preceding 6 dates, independent of Django's active timezone.
Choose **Custom dates** to apply From/To; preset selection takes precedence over
those fields. A URL supplying dates without a preset also selects custom dates.
Invalid filters show field errors and no report, rather than silently widening it.

Page, agent, operator, access method, intent and date filters are combined with AND. Page
and agent choices include retained history outside the selected date range.
The operator dropdown narrows agent choices to that operator. Selecting an operator
with an incompatible agent selected clears the agent filter; clicking the active
operator card or Clear operator filter removes the operator filter. Cards and leader
links retain other applicable filters and start at the first records page.
Unknown/empty agent labels are selectable. All four methods are available:
`query-param`, `accept-header`, `ua`, `export-url`. Existing pages show current
titles and numeric IDs; missing pages show **Deleted page #ID**. Rows retain their
original numeric identities and counts after deletion.

The page filter is a text box with datalist suggestions rather than a dropdown, so
it stays usable as page history grows. It accepts a suggested **Title (#ID)** label,
a bare or `#`-prefixed page ID, or an exact title (case-insensitive) that matches
exactly one page. Anything else is a field error. The `page_id` URL parameter still
accepts a numeric ID, and the box then shows that page's label.

The daily-record table has 50 rows per page, newest date first and stable dimension
ordering within a date (page ID, agent, method, then row ID). A repeat request
increments its daily counter without moving the row; no last-access timestamp is
stored. Pagination preserves filters. The headline, operator cards, six purpose
tiles and chart cover **all matching rows**, independently of the current results page. There are
separate empty states for no recorded history and no matching records.

The headline shows total recorded requests and leading page, agent and attributed
operator. Tied leaders are labelled and list up to three names alphabetically;
page ties scan at most 50 pages and show 50+ when that cap is reached. Empty and
method-name labels cannot lead as agents; Unattributed cannot lead as an operator.
Operator cards show each represented operator's total and top five agents, ordered
by total then name. Unattributed is last and only appears when nonzero. The reviewed
operator map is applied to stored agent labels at read time, including retired labels;
it never authenticates a client or widens automatic Markdown serving. An unmatched
label is Unattributed even if its purpose is known. Conversely, Wagtail can attribute
a known operator while its independently reviewed purpose is Unknown.

### Buckets, charts and trends

Grain uses the inclusive number of selected dates: daily for 1–92 days, monthly
for 93–1,827 days and yearly thereafter. Calendar buckets are aligned to their
UTC day, month or year, with zeroes for missing periods. Only dates inside the
filter count, so first/last monthly or yearly buckets can be partial. SQL groups
counts by bucket and agent before Python applies the shared category snapshot;
the report does not load each daily record to draw charts or issue per-page queries.

Total plus on-demand, search, training, mixed purposes and unknown tiles show
counts and Pearson correlation **r** against successive time buckets. Positive/negative
values indicate rising/falling association with time, never percentage change or
statistical significance. Undefined correlation (flat or fewer than two buckets)
is neutral; values rounding to zero at two decimal places are also neutral.
The stacked bar chart uses the 350.org palette with labelled intent colours and
an expandable table of exact bucket counts. All five intents contribute to bar
heights, including unknown, so the chart reconciles to the total tile. The on-demand tile and legend explicitly say **estimate**.

The report states the CDN/static bypass and aggregate-download exclusions above.
It does not measure total edge traffic, verified bot identity, completed delivery
or a proven human-triggered request. Pruning is the explicit command above;
[volume benchmarks](contributing/agent-stats-benchmarks.md) document report and prune query
budgets (#66). The report does not schedule retention or add runtime settings.

### Historical classification versus serving policy

Treat the shipped category map and project overrides as append-only historical
classification data. Removing a substring can move existing counters to unknown;
changing its category or precedence can relabel all matching history. Even adding
an overlapping substring can reclassify old rows. Review these changes explicitly;
there is no stored category snapshot or migration to preserve the old result.

Which agents get automatic Markdown is decided per entry in the registry
(`auto_markdown`), not per site. There is deliberately no per-site agent list, so a
site cannot drift from the shipped registry; `NEGOTIATE_USER_AGENT = False` is the
only site-level switch. Turning an entry's `auto_markdown` off stops future
UA-triggered serving but must not erase existing labels or remove historical
category mappings. Runtime-editable settings are tracked in [old tracker #38](https://github.com/dogwonder/wagtail-markdown-for-agents/issues/38); the agent list
is not among them.

### Independent registry — 22 September 2026

The [agent registry](agent-registry.md) now owns active detection and automatic
serving policy. WordPress 1.7.0 remains a frozen historical reference, not the
required active list. Removed detection entries stay in historical classification;
existing counters are neither deleted nor rewritten. Active metadata is used when
reading reports, so reviewed purpose corrections affect earlier rows too. This
release moves `GoogleOther` from training to unknown and `CloudVertexBot` from
training to search. Googlebot, Applebot and bingbot use mixed purposes. A mixed
counter contributes once to the total and once to the mixed bucket.

All intent labels describe estimated purposes, not what a particular request will
actually do. Recognition does not verify identity. Recognition-only bots are counted
under a Markdown method when they explicitly obtain page Markdown, and as `html`
when they read a page as HTML (#61).

The frozen WordPress fixture and `data/legacy_agents.py` retain provenance and
historical categories. Migration `0006` keeps its original frozen labels; it must
run before the new application starts recording new identities. No new database
migration or deletion of existing counters is required.
