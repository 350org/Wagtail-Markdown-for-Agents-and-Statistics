# Agent registry

Registry `2026-11-27.2` holds exactly the entries of the shared list in
`chancery-lane-project/agent-signals`, revision 6 (release v0.4.1): 52 active HTTP
identities, 25 of them served Markdown automatically, and 36 retired entries (#93).
Active entries are 37 `agent`, 9 `browser` and 6 `reference`. Retired entries no
longer match requests, but their labels keep their purpose and operator, so past
report rows still read.

Label, operator, purpose, `kind`, retirement and serving all follow agent-signals,
and a change starts there. This package adds only its own token aliases, sources,
review dates and notes. The one deliberate difference is how a header is matched:
by product token here, by substring there (see [matching](#matching)). The package
doesn't read agent-signals at runtime; a [drift check](#the-drift-check) compares the
two at each review.

See the [review record](contributing/agent-registry-review.md) for the matrix, sources and
each change. Absence from the registry does not mean that a bot does not exist.

## The rule for an active entry

An active entry is one of:

- **`agent`:** an AI agent, shown by its operator's statement or by logs, that fetches
  content for AI answers, search or training;
- **`browser`:** an AI browser or automation agent acting on the page for a person;
- **`reference`:** a reference crawler, meaning a search engine whose index feeds AI
  answers (Googlebot, bingbot, Applebot, PetalBot, GoogleOther, Bravebot).

It must also send a real HTTP token. Everything else is retired. `browser` and
`reference` entries are never served Markdown on their User-Agent: browsers need the
page they act on, and serving search engines by User-Agent risks looking like cloaking.
An `agent` is served only with evidence that it uses Markdown, such as logs showing it
following Markdown links or sending `Accept: text/markdown`. A test enforces the first
part. The report's "chose Markdown" figure gives the evidence for the second
([statistics](agent-access-stats.md#html-reads-by-registry-agents-61)).

## Source and serving policy

`src/wagtail_markdown_agents/data/agent-registry.json` is the source of truth. Each
record has a stable statistics `label`, operator, HTTP product `tokens`, one purpose
(a one-item `purposes` list), an explicit `auto_markdown` flag, evidence URLs, review
date and notes.
Sources are factual identity references; their prose is not imported. Prefer operator
documentation. Use [Cloudflare Radar](https://radar.cloudflare.com/bots/directory)
for discovery and documented identities when operator evidence is unavailable, and
record uncertainty or conflicting categories in the entry. Do not scrape the whole
directory into runtime configuration or fetch it during application requests.

The initial operator references include [OpenAI](https://developers.openai.com/api/docs/bots),
[Anthropic](https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler),
[Perplexity](https://docs.perplexity.ai/docs/resources/perplexity-crawlers),
[DuckDuckGo](https://duckduckgo.com/duckduckgo-help-pages/results/duckassistbot),
[Google](https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers)
and [Apple](https://support.apple.com/en-gb/119829). Entry-specific URLs are in the JSON.

Automatic serving is a package policy for a reviewed subset of `agent` entries; it is **not** an operator claim that the bot supports
Markdown. General search engines, broad collection tools, advertising checks and
browser-action agents keep HTML by default. Browser agents may require the normal
DOM to navigate or act. Any client can still explicitly request Markdown using
`?output_format=md`, `Accept: text/markdown` or the export URL, subject to eligibility
and cache configuration. `NEGOTIATE_USER_AGENT=False` disables all automatic serving
without disabling recognition on explicit Markdown requests.

## Identities

Each entry has one purpose, agent-signals' category: `on-demand`, `search`,
`training` or `unknown`. `unknown` is for an operator that describes none of the
three, such as SEO checks, uptime or compliance scanning, or automation. Purpose
describes possible use, not proof of what happened to a specific response.

Served automatically (25): `GPTBot`, `ChatGPT-User`, `ClaudeBot`, `Claude-User`,
`Claude-SearchBot`, `OAI-SearchBot`, `PerplexityBot`, `Perplexity-User`,
`meta-externalagent`, `meta-externalfetcher`, `meta-webindexer`, `MistralAI-User`,
`DuckAssistBot`, `KimiBot`, `Amzn-SearchBot`, `Cloudflare-AI-Search`, `LinerBot`,
`ShapBot`, `KernelSearchBot`, `Anomura`, `Kimi-User`, `Amzn-User`, `Shap-User`,
`KeenableBot` and `ClueWeb-Crawler`. Every other active entry is recognition-only. The
JSON has each entry's purpose, operator, sources and notes.

`2026-11-27.2` aligns the registry with agent-signals revision 6 (#93):

- Applebot, Googlebot and bingbot have one purpose, `search`, and
  CloudflareBrowserRenderingCrawler `training`. There is no Mixed purposes bucket.
- The `other` purpose becomes `unknown`, as in agent-signals.
- Eight labels lose their trailing slash: `ShapBot`, `ICC-Crawler`, `Cotoyogi`,
  `meta-externalfetcher`, and the retired `AdpResearchBot`, `Nava`, `Retool` and
  `SemrushBot-SWA`. Migration `0008` renames their rows.
- FacebookBot, Kimi-SearchBot and OAI-AdsBot are dropped, because agent-signals
  doesn't hold them. Migration `0008` moves their rows to unknown.
- agent-signals' retired WordPress-era labels are added as retired entries:
  Claude-Web, anthropic-ai, Google-Extended, Applebot-Extended, cohere-ai,
  amazon-kendra-, Anchor Browser, FishBot, Gemini-User and Google-NotebookLM. None
  of them sends a usable HTTP token.
- Retired entries take agent-signals' categories and operators.

Serving doesn't change, so the [Cloudflare expression](cdn-caching.md) is the same.

## Matching

`identify_agent(header)` returns a frozen record or `None`; `detect_agent(header)`
returns its canonical stored label. Only the first 2,048 characters of the header
are read, as agent-signals cuts every header to 2,048 bytes. Matching is ASCII
case-insensitive and requires a product boundary (start, whitespace, semicolon or
opening parenthesis), followed by a version slash, whitespace, semicolon, closing
parenthesis or end. This avoids matching `NotGPTBot`, `GPTBotFake` or a bot name
appearing only in a URL or contact address. It does not authenticate identities:
client headers remain spoofable.

agent-signals matches by substring instead, so a few of its entries match with a
trailing slash (`ClaudeBot/`, `Applebot/`, `bingbot/`, `Devin/`) to avoid names in
other agents' headers. The product-token matcher here gives those answers without
the slash. The two differ only for a name inside a longer product name, such as
`MyGPTBotClone/1.0`. That is the one entry in
`data/agent-signals-differences.json`.

Registry order is the documented tie-breaker when a header claims several identities.
The same selected record determines both serving and statistics. Aliases belong to
one record and must be listed explicitly: Google's image and video GoogleOther
products store `GoogleOther`, and `Googlebot` also matches `Googlebot-Image`,
`Googlebot-News` and `Googlebot-Video`. A token followed by `-` does not match, so
`Cloudflare-AI-Search-External` is a separate token.

A retired entry stays in `agent-registry.json` with `"retired": true` and no `kind`. It
never matches or serves, and isn't in the Cloudflare expression. Reports still read its
label with its purpose and operator. Retire an entry when agent-signals does; drop it
only when agent-signals doesn't hold it, with a migration for its rows. Unrecognised
clients share the anonymous unknown bucket.

Purposes are calculated at read time, so a change to an entry's purpose changes how
its past rows read. Exact label matches come before substring compatibility matches,
so Applebot-Extended rows don't read as Applebot. Project category hooks retain
ordered mutation; use exact canonical labels for overrides.

Apply migration `0008` before starting the updated application: older workers still
store the slashed labels. Like `0006`, it runs in batches and can be rerun after an
interruption.

## The drift check

`scripts/agent_signals_drift.py` compares the registry with an agent-signals
`agents.json`, and optionally its conformance cases:

```sh
uv run python scripts/agent_signals_drift.py ../agent-signals/data/agents.json \
    --cases ../agent-signals/tests/conformance/cases.json
```

It fails on any entry or operator that differs, on a conformance case that differs
without being listed in `data/agent-signals-differences.json` (or is listed and no
longer differs), and on a revision other than the one the differences file records.
It reads local files only. `tests/fixtures/agent-signals-conformance-cases.json` pins
the cases of the recorded release, so CI checks them offline. A weekly workflow waits
until agent-signals is public (#93).

## Reviewing a registry update

1. Start from the latest agent-signals revision: any change to an entry (a new
   agent, a retirement, a `kind`, an operator, a purpose or serving) is made there
   first. Run the [drift check](#the-drift-check) against that release. Reopen the
   operator or directory evidence. Verify an actual HTTP token separately from
   robots.txt directives, display names, hashes, IP lists and documentation URLs.
2. Add or revise the record with the review date, source URLs and uncertainty notes.
   Preserve canonical labels for the same identity. Record aliases explicitly.
3. Decide recognition and automatic serving separately; default new or ambiguous
   agents to `auto_markdown: false`, and set `kind`. Serve an `agent` only when logs
   show it choosing Markdown (the report's "chose Markdown" figure). Document any
   purpose correction and its effect on historical reports.
4. Retire entries that no longer meet [the rule](#the-rule-for-an-active-entry),
   including an `agent` with no operator statement that hasn't appeared in production
   logs since the last review. Set `"retired": true` and `auto_markdown: false`, drop
   `kind`, and record the reason in its notes. Never delete an entry.
5. Increment the registry version. Review the JSON diff for added/removed tokens,
   changed serving policy, label collisions and changed purposes. Update the drift
   check's recorded revision and pinned cases, this page, the changelog and any stated
   cardinality bounds. A label change needs a data migration, as `0008` is.
6. Add meaningful HTTP-header examples and negative matching cases. Run registry,
   negotiation, statistics/report, simulator and Cloudflare tests, then the project's
   full required checks. CI must remain offline with respect to source websites.
7. Generate the [Cloudflare cache-bypass expression](cdn-caching.md) from the deployed
   version. Coordinate package/rule rollout and verify browser, automatic-agent,
   recognition-only and explicit-Markdown requests on cold and warm URLs.

Review at each release and when an operator announces an identity change. Network
refreshes must produce a reviewable change; directory edits must not silently change
production routing or historical statistics. Per-site runtime agent management is a
separate future feature; the category hook changes reporting only.
