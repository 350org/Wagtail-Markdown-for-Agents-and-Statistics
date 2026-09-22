# Agent registry

Registry `2026-09-22.1` is an independent Wagtail baseline reviewed on 22 September
2026. It contains 23 recognised HTTP identities and enables automatic Markdown for
12. It is deliberately bounded: absence means unreviewed or outside this baseline,
not that a bot does not exist. The previous 69-entry WordPress list is retained only
as historical evidence and classification data.

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

Automatic serving is a package policy for a reviewed subset of dedicated content
retrieval/crawling identities; it is **not** an operator claim that the bot supports
Markdown. General search engines, broad collection tools, advertising checks and
browser-action agents keep HTML by default. Browser agents may require the normal
DOM to navigate or act. Any client can still explicitly request Markdown using
`?output_format=md`, `Accept: text/markdown` or the export URL, subject to eligibility
and cache configuration. `NEGOTIATE_USER_AGENT=False` disables all automatic serving
without disabling recognition on explicit Markdown requests.

## Initial identities

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
| `meta-webindexer` | search | No |
| `MistralAI-User` | on-demand | Yes |
| `DuckAssistBot` | on-demand | Yes |
| `Google-Agent` | on-demand | No |
| `Amazonbot` | training | No |
| `CCBot` | training | No |
| `FacebookBot` | training | No |
| `Applebot` | search, training | No |
| `Googlebot` | search, training | No |
| `bingbot` | search, training | No |
| `GoogleOther` | other | No |
| `CloudVertexBot` | search | No |
| `OAI-AdsBot` | other | No |

Purpose describes possible use, not proof of what happened to a specific response.
Multiple recognised intents contribute to the **Mixed purposes** bucket, counted
once. `other` maps to **Unknown** intent. Cloudflare's current taxonomy permits
multiple behaviours; the plugin deliberately avoids treating every bot as training.
Meta-WebIndexer is recognition-only because Radar's description says AI search
while its category says link preview. CCBot, Amazonbot and FacebookBot retain the
reference's training estimate, with recognition-only serving and explicit notes.

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
`meta-externalfetcher/` and `CloudVertexBot` retain their existing statistics labels;
the latter now matches only the documented `Google-CloudVertexBot` HTTP token.

`Google-Extended` and `Applebot-Extended` are robots.txt controls and never detect
an HTTP identity. `Gemini-User` remains historical category-only data without a
verified HTTP identity in this baseline. Legacy entries such as Claude-Web,
anthropic-ai, Bytespider, Instapaper and the long tail of directory imports are not
active without a fresh review. This does not assert that those identities are retired
by their operators. Unrecognised clients share the existing anonymous unknown bucket.

`data/legacy_agents.py` freezes the WordPress categories and their source attribution.
The WordPress fixture verifies that snapshot, not active-list equality. Retired
labels remain readable without becoming detectable. Current active metadata owns
classification for continuing identities. The initial corrections are GoogleOther
(training → unknown) and CloudVertexBot (training → search); these affect historical
report categorisation because categories are calculated at read time. Counts and
stored labels are unchanged. Exact category matches precede substring compatibility
matches, so historical Applebot-Extended does not become mixed merely because the
new Applebot identity exists. Project category hooks retain ordered mutation; use
exact canonical labels for overrides.

Apply existing migration `0006` before starting the updated application. Its frozen
known-label set is intentionally unchanged. There is no new data migration.

## Reviewing a registry update

1. Reopen the operator or directory evidence. Verify an actual HTTP token separately
   from robots.txt directives, display names, hashes, IP lists and documentation URLs.
2. Add or revise the record with the review date, source URLs and uncertainty notes.
   Preserve canonical labels for the same identity. Record aliases explicitly.
3. Decide recognition and automatic serving separately; default new or ambiguous
   agents to `auto_markdown: false`. Document any purpose correction and its effect
   on historical reports. Preserve removed labels in historical classification.
4. Increment the registry version. Review the JSON diff for added/removed tokens,
   changed serving policy, label collisions and changed purposes. Update this table,
   the changelog and any stated cardinality bounds.
5. Add meaningful HTTP-header examples and negative matching cases. Run registry,
   negotiation, statistics/report, simulator and Cloudflare tests, then the project's
   full required checks. CI must remain offline with respect to source websites.
6. Generate the [Cloudflare cache-bypass expression](cdn-caching.md) from the deployed
   version. Coordinate package/rule rollout and verify browser, automatic-agent,
   recognition-only and explicit-Markdown requests on cold and warm URLs.

Review at each release and when an operator announces an identity change. Network
refreshes must produce a reviewable change; directory edits must not silently change
production routing or historical statistics. Per-site runtime agent management is a
separate future feature; the category hook changes reporting only.
