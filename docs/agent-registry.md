# Agent registry

Registry `2026-11-27.1` has 52 active HTTP identities and serves Markdown
automatically to 25 of them. Another 29 entries are retired: they no longer match
requests, but their labels keep their purposes and operators for past report rows.
The active set is the same as revision 4 of the shared list in
`chancery-lane-project/agent-signals` (#96, #60): 37 `agent`, 9 `browser` and 6
`reference` entries.

Every one of the 69 strings inherited from the WordPress plugin has a recorded
disposition:

- 35 are active;
- 26 were restored in `2026-09-28.1` and retired in `2026-11-27.1`;
- 4 are excluded with evidence (retired or robots.txt-only);
- 4 are deferred with a stated evidence gap.

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

Identity (label, tokens, operator, `kind`, retired) follows agent-signals, and a change
starts there. Serving (`auto_markdown`), the `other` purpose, sources and notes are
this package's own. The package doesn't read agent-signals at runtime. #93 tracks a
drift check against it.

## Source and serving policy

`src/wagtail_markdown_agents/data/agent-registry.json` is the source of truth. Each
record has a stable statistics `label`, operator, HTTP product `tokens`, one or more
purposes, an explicit `auto_markdown` flag, evidence URLs, review date and notes.
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

The table lists the 22 September baseline. The
[review](contributing/agent-registry-review.md#matrix) lists every restored identity. Of those, 7
serve Markdown automatically: `KimiBot` (training), and `Amzn-SearchBot`,
`Cloudflare-AI-Search`, `LinerBot`, `ShapBot/`, `KernelSearchBot` and `Anomura`
(search). The other 37 restored identities, including 14 whose operators describe
non-AI tooling (purpose `other`), are recognition-only. `2026-09-28.2` adds four
operator-documented siblings with automatic Markdown: `Kimi-User`, `Amzn-User` and
`Shap-User` (on-demand), and `Kimi-SearchBot` (search). See the
[review](contributing/agent-registry-review.md#additions-in-2026-09-282).
`2026-11-06.1` adds Anthropic's hosted browser, `Claude-Agent`, as recognition-only; see
[the review](contributing/agent-registry-review.md#additions-in-2026-11-061).
`2026-11-23.1` serves `meta-webindexer` automatically, now that Meta documents it as
its Meta AI search crawler; see
[the review](contributing/agent-registry-review.md#changes-in-2026-11-231).
`2026-11-27.1` adds nine agents, serving `KeenableBot` and `ClueWeb-Crawler`, and retires
29 entries, including `Kimi-SearchBot`, which was served; see
[the review](contributing/agent-registry-review.md#changes-in-2026-11-271).

| Stored label | Estimated purpose | Automatic Markdown |
| --- | --- | --- |
| `GPTBot` | training | Yes |
| `ChatGPT-User` | on-demand | Yes |
| `ClaudeBot` | training | Yes |
| `Claude-User` | on-demand | Yes |
| `Claude-SearchBot` | search | Yes |
| `OAI-SearchBot` | search | Yes |
| `PerplexityBot` | search | Yes |
| `Perplexity-User` | on-demand | Yes |
| `meta-externalagent` | training | Yes |
| `meta-externalfetcher/` | on-demand | Yes |
| `meta-webindexer` | search | Yes, from `2026-11-23.1` |
| `MistralAI-User` | on-demand | Yes |
| `DuckAssistBot` | on-demand | Yes |
| `Google-Agent` | on-demand | No |
| `Claude-Agent` | on-demand | No |
| `Amazonbot` | training | No |
| `CCBot` | training | No |
| `FacebookBot` | training | Retired in `2026-11-27.1` |
| `Applebot` | search, training | No |
| `Googlebot` | search, training | No |
| `bingbot` | search, training | No |
| `GoogleOther` | other | No |
| `CloudVertexBot` | search | Retired in `2026-11-27.1` |
| `OAI-AdsBot` | other | Retired in `2026-11-27.1` |

Purpose describes possible use, not proof of what happened to a specific response.
Multiple recognised intents contribute to the **Mixed purposes** bucket, counted
once. `other` maps to **Unknown** intent. Cloudflare's current taxonomy permits
multiple behaviours; the plugin deliberately avoids treating every bot as training.
Meta-WebIndexer is recognition-only because Radar's description says AI search
while its category says link preview. (Meta has since documented it, and `2026-11-23.1`
serves it.) CCBot and Amazonbot retain the reference's training estimate, with
recognition-only serving and explicit notes.

## Matching and history

`identify_agent(header)` returns a frozen record or `None`; `detect_agent(header)`
returns its canonical stored label. Matching is ASCII case-insensitive and requires
a product boundary (start, whitespace, semicolon or opening parenthesis), followed
by a version slash, whitespace, semicolon, closing parenthesis or end. This avoids
matching `NotGPTBot`, `GPTBotFake` or a bot name appearing only in a documentation
URL. It does not authenticate identities: client headers remain spoofable.

Registry order is the documented tie-breaker when a header claims several identities.
The same selected record determines both serving and statistics. Aliases belong to
one record, e.g. Google's image/video GoogleOther products store `GoogleOther`.
Some records keep their existing statistics labels while matching a different
product token:

- `meta-externalfetcher/` keeps its label, including the slash.
- The restored `ShapBot/`, `ICC-Crawler/` and `Cotoyogi/` keep their WordPress labels,
  including the slash, and match the token before it. So did the now-retired `Nava/`,
  `Retool/`, `AdpResearchBot/` and `SemrushBot-SWA/`.
- `Googlebot` also matches `Googlebot-Image`, `Googlebot-News` and `Googlebot-Video`,
  from `2026-11-27.1`.

agent-signals matches by substring, so revision 4 matches `ClaudeBot/` and `Applebot/`
with their slash: otherwise `+claudebot@anthropic.com` in a Claude-SearchBot header, or
`Applebot-Extended`, would be read as those agents. The product-token matcher here
already gives the same answers, and tests pin them.

Aliases must be listed explicitly. A token followed by `-` does not match, so
`Cloudflare-AI-Search-External` and the GoogleOther image and video products are
separate tokens.

`Google-Extended` and `Applebot-Extended` are robots.txt controls and never detect
an HTTP identity. `Gemini-User` remains historical category-only data without a
verified HTTP identity. Claude-Web and anthropic-ai are excluded because Anthropic
retired them. cohere-ai, FishBot, Anchor Browser and amazon-kendra- are deferred until
there is a usable, attributable HTTP token. Deferral is not a claim that they are
retired. Unrecognised clients share the existing anonymous unknown bucket.

A retired entry stays in `agent-registry.json` with `"retired": true` and no `kind`. It
never matches or serves, and isn't in the Cloudflare expression. Reports still read its
label with its recorded purposes and operator, so retiring an entry doesn't change past
rows. Never delete an entry: retire it.

`data/legacy_agents.py` freezes the WordPress categories and their source attribution.
The WordPress fixture verifies that snapshot, not active-list equality. Retired
labels remain readable without becoming detectable. Registry entries, active or
retired, take precedence over the frozen categories. Current active metadata owns
classification for continuing identities. The initial corrections are GoogleOther
(training → unknown) and CloudVertexBot (training → search). Registry
`2026-09-28.1` corrects 24 restored labels to match operator evidence; they are listed
in the [review](contributing/agent-registry-review.md#read-time-category-changes). These changes
affect historical report categorisation, because categories are calculated at read
time. Counts and
stored labels are unchanged. Exact category matches precede substring compatibility
matches, so historical Applebot-Extended does not become mixed merely because the
new Applebot identity exists. Project category hooks retain ordered mutation; use
exact canonical labels for overrides.

Apply existing migration `0006` before starting the updated application. Its frozen
known-label set is intentionally unchanged. There is no new data migration.

## Reviewing a registry update

1. Start from the latest agent-signals revision: an identity change (a new agent, a
   retirement, a `kind`, tokens or an operator) is made there first. Reopen the operator
   or directory evidence. Verify an actual HTTP token separately from robots.txt
   directives, display names, hashes, IP lists and documentation URLs.
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
   changed serving policy, label collisions and changed purposes. Update this table,
   the changelog and any stated cardinality bounds.
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
