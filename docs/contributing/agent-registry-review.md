# Agent registry review, 28 September 2026

This review accounts for all 69 detection strings inherited from the WordPress plugin
(1.7.0) and records the disposition of each in registry `2026-09-28.1` (#19). It
replaces the bounded `2026-09-22.1` baseline, which left 52 inherited strings
unreviewed. Omission in that baseline meant "not reviewed", not "retired".

## Outcome

| Disposition | Inherited strings |
| --- | --- |
| Continuing, unchanged (reviewed 22 September) | 12 |
| Continuing, re-checked and kept recognition-only | 5 |
| Restored with automatic Markdown | 7 |
| Restored as recognition-only | 37 |
| Excluded with evidence | 4 |
| Deferred with a stated evidence gap | 4 |
| **Total** | **69** |

The registry now recognises 67 identities (61 inherited strings plus the six
22 September additions) and serves Markdown automatically to 19. The Cloudflare
cache bypass is generated from those 19; see [CDN caching](../cdn-caching.md).

## Policy applied

These decisions were made by the package owner on 28 September 2026.

- **Recognition.** Recognise every inherited entry with an HTTP User-Agent token
  documented by its operator or by Cloudflare Radar. This includes tools that are not
  AI agents, such as monitors, SEO tools and automation platforms, with purpose
  `other`. Exclude only retired or robots.txt-only entries. Defer where there is no
  usable token or no verifiable operator.
- **Automatic Markdown.** Serve Markdown automatically only to public, dedicated AI
  search or training crawlers with an operator-documented token: KimiBot,
  Amzn-SearchBot, Cloudflare-AI-Search, LinerBot, ShapBot, KernelSearchBot and
  Anomura.
  - Crawlers a site owner connects (Element451Bot, atlassian-bot, CloudVertexBot) stay
    recognition-only.
  - So do general and broad crawlers, and browser or action agents, which may need the
    normal page to navigate or act.
- **Labels.** Restored records keep the exact WordPress string as the stored label,
  so historical counters continue, for example `ShapBot/` and `Nava/`. The HTTP token
  drops the trailing slash, because a version number follows it in real headers.
- **Aliases.** Aliases of the same identity are added explicitly:
  Cloudflare-AI-Search-External, OnirocoCrawler (Chathive's new name), Instaparser and
  the three Awario product tokens.
- **Sibling identities.** Separate sibling identities documented on the same operator
  pages were added afterwards in `2026-09-28.2`; see
  [Additions in 2026-09-28.2](#additions-in-2026-09-282).

## Evidence

Operator documentation was preferred. Cloudflare Radar pages return HTTP 403 to
automated fetches, so Radar records were read from the public
[microlinkhq/cloudflare-bot-directory](https://github.com/microlinkhq/cloudflare-bot-directory)
mirror of Radar's data, refreshed 2026-09-28, and from Wayback snapshots of Radar
pages. Links below labelled with a `radar.cloudflare.com` URL were checked this way,
not first-hand. Nothing in this review verifies that a request really comes from its
claimed operator, and nothing proves how a response is used.

Radar's AI categories often conflict with operators' own descriptions:

- WARDBot is an uptime monitor.
- magpie-crawler and Awario do social listening.
- ADP states that it does not train models.

Where they conflict, the purpose follows the operator and the conflict is noted.

## Matrix

| WordPress string | WordPress category | Disposition | HTTP tokens | Operator | Purpose | Reviewed | Evidence | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GPTBot` | training | Continuing | `GPTBot` | OpenAI | training | 2026-09-22 | [1](https://developers.openai.com/api/docs/bots) | Dedicated model-development crawler; serving is package policy, not proof of Markdown support. |
| `ChatGPT-User` | on-demand | Continuing | `ChatGPT-User` | OpenAI | on-demand | 2026-09-22 | [1](https://developers.openai.com/api/docs/bots) | User-directed retrieval, distinct from the search crawler. |
| `ClaudeBot` | training | Continuing | `ClaudeBot` | Anthropic | training | 2026-09-22 | [1](https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler) | Dedicated model-development crawler. |
| `Claude-Web` | on-demand | Excluded | — | Anthropic | — | 2026-09-28 | [1](https://www.theregister.com/2024/07/30/taming_ai_content_crawlers/) [2](https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler) | Retired by Anthropic |
| `anthropic-ai` | training | Excluded | — | Anthropic | — | 2026-09-28 | [1](https://www.theregister.com/2024/07/30/taming_ai_content_crawlers/) | Retired by Anthropic |
| `PerplexityBot` | search | Continuing | `PerplexityBot` | Perplexity | search | 2026-09-22 | [1](https://docs.perplexity.ai/docs/resources/perplexity-crawlers) | Operator distinguishes search indexing from foundation-model training. |
| `Google-Extended` | training | Excluded | — | Google | — | 2026-09-28 | [1](https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers) | robots.txt control only |
| `Amazonbot` | training | Continuing, recognise only; WordPress served it | `Amazonbot` | Amazon | training | 2026-09-28 | [1](https://developer.amazon.com/amazonbot) [2](https://radar.cloudflare.com/bots/directory/amazon-bot) | Radar training category is an estimate; general Amazon product crawler remains recognition-only. |
| `cohere-ai` | training | Deferred | — | Cohere (claimed) | — | 2026-09-28 | [1](https://docs.cohere.com/docs/cohere-web-crawlers) | Operator documents no such agent and denies training crawlers; UA only from third parties |
| `meta-externalagent` | training | Continuing | `meta-externalagent` | Meta | training | 2026-09-22 | [1](https://radar.cloudflare.com/bots/directory/meta-externalagent) | Radar training classification; description also mentions product indexing. Classification is an estimate. |
| `Bytespider` | training | Restored, recognise only | `Bytespider` | ByteDance | training | 2026-09-28 | [1](https://developers.cloudflare.com/ai-crawl-control/reference/bots/) [2](https://radar.cloudflare.com/bots/directory/bytedance-toutiao) | No reachable operator documentation. Cloudflare lists it as an AI crawler, while Radar attaches its user agents to Toutiao search. |
| `CCBot` | training | Continuing, recognise only; WordPress served it | `CCBot` | Common Crawl | training | 2026-09-28 | [1](https://commoncrawl.org/ccbot) [2](https://developers.cloudflare.com/ai-crawl-control/reference/bots/) | Radar training category is an estimate for a general corpus crawler; recognition only. |
| `Applebot-Extended` | search | Excluded | — | Apple | — | 2026-09-28 | [1](https://support.apple.com/en-us/119829) | robots.txt control only |
| `OAI-SearchBot` | search | Continuing | `OAI-SearchBot` | OpenAI | search | 2026-09-22 | [1](https://developers.openai.com/api/docs/bots) | Dedicated ChatGPT search crawler; downstream use cannot be proven from a request. |
| `Claude-User` | on-demand | Continuing | `Claude-User` | Anthropic | on-demand | 2026-09-22 | [1](https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler) | User-directed retrieval. |
| `Perplexity-User` | on-demand | Continuing | `Perplexity-User` | Perplexity | on-demand | 2026-09-22 | [1](https://docs.perplexity.ai/docs/resources/perplexity-crawlers) | User-directed retrieval. |
| `meta-externalfetcher/` | on-demand | Continuing | `meta-externalfetcher` | Meta | on-demand | 2026-09-22 | [1](https://radar.cloudflare.com/bots/directory/meta-externalfetcher) | Keep the historical stored label, including slash; match the actual product token. |
| `MistralAI-User` | on-demand | Continuing | `MistralAI-User` | Mistral AI | on-demand | 2026-09-22 | [1](https://radar.cloudflare.com/bots/directory/mistralai-user) | Radar identifies a user-directed agent. |
| `Google-Agent` | on-demand | Continuing, recognise only; WordPress served it | `Google-Agent` | Google | on-demand | 2026-09-28 | [1](https://developers.google.com/crawling/docs/crawlers-fetchers/google-user-triggered-fetchers) [2](https://radar.cloudflare.com/bots/directory/google-agent) | Browser navigation and actions on user request; recognise it but preserve HTML needed by browser workflows. |
| `DuckAssistBot` | on-demand | Continuing | `DuckAssistBot` | DuckDuckGo | on-demand | 2026-09-22 | [1](https://duckduckgo.com/duckduckgo-help-pages/results/duckassistbot) | Real-time retrieval for AI-assisted answers, not model training. |
| `Devin` | on-demand | Restored, recognise only | `Devin` | Cognition | on-demand | 2026-09-28 | [1](https://radar.cloudflare.com/bots/directory/devin) | Coding agent with a full browser. Token documented by Radar only. |
| `TwinAgent` | on-demand | Restored, recognise only | `TwinAgent` | Twin | on-demand | 2026-09-28 | [1](https://docs.twin.so/web-agent) [2](https://radar.cloudflare.com/bots/directory/twinagent) | Browser agent that automates user-defined workflows. Token documented by Radar only. |
| `ApifyWebsiteContentCrawler` | on-demand | Restored, recognise only | `ApifyWebsiteContentCrawler` | Apify | on-demand | 2026-09-28 | [1](https://radar.cloudflare.com/bots/directory/apify-website-content-crawler) [2](https://apify.com/apify/website-content-crawler) | Radar lists the token; the operator says the crawler does not currently use a specific user agent, so most runs will not match. |
| `ChathiveCrawler` | on-demand | Restored, recognise only | `ChathiveCrawler`, `OnirocoCrawler` | Oniroco | search | 2026-09-28 | [1](https://developers.chathive.app/crawler/overview) | Chathive is now Oniroco; the default is OnirocoCrawler/1.0 and customers can change it. Customer chatbot ingestion. WordPress estimated on-demand. |
| `CledaraBot` | on-demand | Restored, recognise only | `CledaraBot` | Cledara | on-demand | 2026-09-28 | [1](https://radar.cloudflare.com/bots/directory/cledara-saas-management-agent) | Automates customer-approved SaaS admin tasks. Token documented by Radar only. |
| `EasyScan` | on-demand | Restored, recognise only | `EasyScan` | IT-Recht Kanzlei | other | 2026-09-28 | [1](https://radar.cloudflare.com/bots/directory/easyscan) [2](https://www.it-recht-kanzlei.de/website-scanner-fuer-mandanten.php) | Privacy-policy compliance scanner. WordPress estimated on-demand. |
| `HarkBot` | on-demand | Restored, recognise only | `HarkBot` | Hark | on-demand | 2026-09-28 | [1](https://app.hark.com/about/bot) [2](https://radar.cloudflare.com/bots/directory/harkbot) | User-requested research, form filling and account actions; operator says it requests HTML responses only. |
| `HIFIBot` | on-demand | Restored, recognise only | `HIFIBot` | HIFI | on-demand | 2026-09-28 | [1](https://radar.cloudflare.com/bots/directory/hifibot) | Logs in to royalty portals on behalf of clients. Not an AI content agent; recognised for continuity. |
| `QATechBot` | on-demand | Restored, recognise only | `QATechBot` | QA.tech | other | 2026-09-28 | [1](https://docs.qa.tech/bot) [2](https://radar.cloudflare.com/bots/directory/qatechbot) | Authorised end-to-end tests in a real browser; not crawling. WordPress estimated on-demand. |
| `Instapaper` | on-demand | Restored, recognise only | `Instapaper`, `Instaparser` | Instapaper | on-demand | 2026-09-28 | [1](https://radar.cloudflare.com/bots/directory/instapaper) | User-triggered read-later fetch that parses HTML. Radar lists Instapaper/4.0 and Instaparser/1.0. |
| `Nava/` | on-demand | Restored, recognise only | `Nava` | Nava | on-demand | 2026-09-28 | [1](https://dev.labs-asp.navateam.com/bot-disclosure) [2](https://radar.cloudflare.com/bots/directory/nava-labs-asp-dev) | Caseworker-directed browser agent that fills benefit forms. Keep historical label, including slash. |
| `Retool/` | on-demand | Restored, recognise only | `Retool` | Retool | other | 2026-09-28 | [1](https://radar.cloudflare.com/bots/directory/retool) [2](https://community.retool.com/t/how-does-the-user-agent-header-work/26238) | Requests from user-built internal tools. Keep historical label, including slash. WordPress estimated on-demand. |
| `Claude-SearchBot` | search | Continuing | `Claude-SearchBot` | Anthropic | search | 2026-09-22 | [1](https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler) | Dedicated Claude search indexing. |
| `Bravebot` | search | Restored, recognise only | `Bravebot` | Brave | search | 2026-09-28 | [1](https://radar.cloudflare.com/bots/directory/bravebot) [2](https://search.brave.com/help/brave-search-crawler) | Radar lists this verified token; Brave's own page says its crawler does not advertise a differentiated user agent. General search. |
| `Amzn-SearchBot` | search | Restored, auto Markdown | `Amzn-SearchBot` | Amazon | search | 2026-09-28 | [1](https://developer.amazon.com/amazonbot) [2](https://radar.cloudflare.com/bots/directory/amzn-searchbot) | Operator: improves Amazon search experiences and does not crawl for generative AI model training. |
| `Cloudflare-AI-Search` | search | Restored, auto Markdown | `Cloudflare-AI-Search`, `Cloudflare-AI-Search-External` | Cloudflare | search | 2026-09-28 | [1](https://developers.cloudflare.com/ai-search/configuration/data-source/website/parse-types/) [2](https://developers.cloudflare.com/ai-search/platform/release-note/) | AI Search (formerly AutoRAG) retrieval indexer. The -External alias is used outside the customer's account and needs its own token. |
| `Anomura` | search | Restored, auto Markdown | `Anomura` | Direqt | search | 2026-09-28 | [1](https://docs.direqt-search.com/direqt-bots/direqt-crawlers-and-user-agents) [2](https://radar.cloudflare.com/bots/directory/direqt-anomura) | Operator: search crawler, not used for model training. |
| `Element451Bot` | search | Restored, recognise only | `Element451Bot` | Element451 | search | 2026-09-28 | [1](https://help.element451.io/en/articles/10302715-getting-started-with-knowledge-hub) [2](https://radar.cloudflare.com/bots/directory/element451bot) | Knowledge-base ingestion for sites an Element451 customer connects; owner-connected, so recognition only. |
| `KernelSearchBot` | search | Restored, auto Markdown | `KernelSearchBot` | Kernel | search | 2026-09-28 | [1](https://www.kernel.sh/docs/bots) [2](https://radar.cloudflare.com/bots/directory/kernel-search) | Operator: builds search indexes and retrieval databases. Kernel's browser agent has no User-Agent token and is not covered. |
| `ShapBot/` | search | Restored, auto Markdown | `ShapBot` | Parallel Web Systems | search | 2026-09-28 | [1](https://docs.parallel.ai/resources/crawler) [2](https://parallel.ai/parallel-web-systems-bots) | Keep the historical stored label, including slash; match the product token. Shap-User is a separate record. |
| `alphalens-bot` | search | Restored, recognise only | `alphalens-bot` | Alphalens | search | 2026-09-28 | [1](https://alphalensbot.com) [2](https://radar.cloudflare.com/bots/directory/alphalens-bot) | Company and product discovery index; the operator does not describe AI use. |
| `KimiBot` | training | Restored, auto Markdown | `KimiBot` | Moonshot AI | training | 2026-09-28 | [1](https://www.kimi.com/policies/kimi-crawlers) [2](https://radar.cloudflare.com/bots/directory/kimibot) | Operator: content potentially used to train Kimi foundation models. Kimi-User and Kimi-SearchBot are separate records. |
| `PetalBot` | training | Restored, recognise only | `PetalBot` | Huawei | search | 2026-09-28 | [1](https://webmaster.petalsearch.com/site/petalbot) [2](https://radar.cloudflare.com/bots/directory/petalbot) | General Petal search engine crawler that also feeds Huawei AI search. WordPress estimated training; operator describes search. |
| `GoogleOther` | training | Continuing, recognise only; WordPress served it | `GoogleOther`, `GoogleOther-Image`, `GoogleOther-Video` | Google | other | 2026-09-28 | [1](https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers) | Generic research crawler; operator documentation does not establish training intent. Include documented image/video variants. |
| `CloudVertexBot` | training | Continuing, recognise only; WordPress served it | `Google-CloudVertexBot` | Google | search | 2026-09-28 | [1](https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers) | Site-owner-requested Vertex AI indexing. Retain historical stored label; require the full documented HTTP token. |
| `ICC-Crawler/` | training | Restored, recognise only | `ICC-Crawler` | NICT | training | 2026-09-28 | [1](https://ucri.nict.go.jp/en/icccrawler.html) [2](https://radar.cloudflare.com/bots/directory/icccrawler) | Research crawler for NICT's AI and translation R&D; may share data with third parties. Keep historical label, including slash. |
| `Cotoyogi/` | training | Restored, recognise only | `Cotoyogi` | ROIS-DS | training | 2026-09-28 | [1](https://ds.rois.ac.jp/center8/crawler/) [2](https://radar.cloudflare.com/bots/directory/cotoyogi) | Japanese-language data resource collection; AI framing is Radar's. Keep historical label, including slash. |
| `atlassian-bot` | training | Restored, recognise only | `atlassian-bot` | Atlassian | search | 2026-09-28 | [1](https://support.atlassian.com/organization-administration/docs/connect-custom-website-to-rovo/) [2](https://radar.cloudflare.com/bots/directory/atlassian-bot) | Rovo search and agent indexing of websites the customer owns; owner-connected, so recognition only. WordPress estimated training. |
| `LinerBot` | training | Restored, auto Markdown | `LinerBot` | Liner | search | 2026-09-28 | [1](https://docs.getliner.com/docs/linerbot) [2](https://radar.cloudflare.com/bots/directory/liner-bot) | Operator: indexes pages for Liner's AI search engine. WordPress estimated training; operator describes search. |
| `magpie-crawler` | training | Restored, recognise only | `magpie-crawler` | Brandwatch | other | 2026-09-28 | [1](https://www.brandwatch.com/legal/magpie-crawler/) [2](https://radar.cloudflare.com/bots/directory/magpiecrawler) | Social media monitoring index; the operator does not describe AI use. WordPress estimated training. |
| `bigsur.ai` | training | Restored, recognise only | `bigsur.ai` | Big Sur AI | search | 2026-09-28 | [1](https://radar.cloudflare.com/bots/directory/big-sur-ai) | Builds a corpus for a customer's own site agents. Token documented by Radar only; the operator says requests may go through a proxy service. |
| `QualifiedBot` | training | Restored, recognise only | `QualifiedBot` | Qualified | search | 2026-09-28 | [1](https://www.qualified.com/legal/qualified-crawler-user-agent) [2](https://radar.cloudflare.com/bots/directory/qualifiedbot) | Crawls customer websites to power Qualified AI features; may also use an unmarked Chromium user agent. WordPress estimated training. |
| `Awario` | training | Restored, recognise only | `AwarioBot`, `AwarioSmartBot`, `AwarioRssBot` | Awario | other | 2026-09-28 | [1](https://awario.com/bots.html) [2](https://radar.cloudflare.com/bots/directory/awario) | Brand-mention monitoring. Keep the historical label; match the three documented product tokens. WordPress estimated training. |
| `amazon-kendra-` | training | Deferred | — | AWS (Amazon Kendra) | — | 2026-09-28 | [1](https://docs.aws.amazon.com/kendra/latest/dg/stop-web-crawler.html) [2](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html) | Radar gives only templated, suffixed UAs that a product token cannot match; Kendra in maintenance mode since 30 June 2026 |
| `Anchor Browser` | training | Deferred | — | Anchor | — | 2026-09-28 | [1](https://docs.anchorbrowser.io/advanced/cloudflare-web-bot-auth) | No evidence any request carries this UA; operator identifies sessions by Web Bot Auth signature |
| `BorderxBot` | training | Restored, recognise only | `BorderxBot` | BorderX | other | 2026-09-28 | [1](https://www.nubestore.ai/borderxbot.html) [2](https://radar.cloudflare.com/bots/directory/borderxbot-2) | E-commerce product crawler. WordPress estimated training. |
| `CitibotSiteCrawler` | training | Restored, recognise only | `CitibotSiteCrawler` | Citibot | search | 2026-09-28 | [1](https://radar.cloudflare.com/bots/directory/citibotsitecrawler) | Collects government website data for Citibot civic AI tools. Token documented by Radar only. WordPress estimated training. |
| `CloudflareBrowserRenderingCrawler` | training | Restored, recognise only | `CloudflareBrowserRenderingCrawler` | Cloudflare | search, training, other | 2026-09-28 | [1](https://developers.cloudflare.com/browser-run/quick-actions/crawl-endpoint/) [2](https://radar.cloudflare.com/bots/directory/cloudflare-browser-rendering-crawler) | Customer-run /crawl service; declared purposes default to search, AI input and AI training. Renders pages and may request HTML output. |
| `netEstate NE Crawler` | training | Restored, recognise only | `netEstate NE Crawler` | netEstate | other | 2026-09-28 | [1](https://radar.cloudflare.com/bots/directory/datenbank) [2](https://www.netestate.de/informationsextraktion/software/impressums-crawler/) | Extracts contact details from imprint pages. The URL in its user agent no longer resolves. WordPress estimated training. |
| `FishBot` | training | Deferred | — | unverified (Radar: fish.audio) | — | 2026-09-28 | [1](https://github.com/microlinkhq/cloudflare-bot-directory) [2](https://fish.audio/robots.txt) | Radar-only bare token; operator attribution to fish.audio unverified |
| `make.com` | training | Restored, recognise only | `make.com` | Make | other | 2026-09-28 | [1](https://radar.cloudflare.com/bots/directory/make-com-2) | Workflow automation. Radar also lists Make/production and Integromat/production; those generic tokens are not added. WordPress estimated training. |
| `NavuBot` | training | Restored, recognise only | `NavuBot` | Navu | search | 2026-09-28 | [1](https://navu.co/ensuring-navu-has-access-to-your-site/) [2](https://radar.cloudflare.com/bots/directory/navu) | Indexes customer or prospect sites for their own AI chat. WordPress estimated training. |
| `Novellum` | training | Restored, recognise only | `Novellum` | Novellum | on-demand | 2026-09-28 | [1](https://radar.cloudflare.com/bots/directory/novellum-ai-crawl) | Radar describes an MCP crawl tool used by agents. Operator documentation and site were unreachable on 2026-09-28; status unknown, not retired. |
| `AdpResearchBot/` | training | Restored, recognise only | `AdpResearchBot` | ADP | other | 2026-09-28 | [1](https://payroll-bot.adp.com/docs) [2](https://radar.cloudflare.com/bots/directory/payroll-bot) | Collects payroll and legal documentation from government sites; operator says it does not train AI models. Keep historical label, including slash. |
| `SelectikaScraper` | training | Restored, recognise only | `SelectikaScraper` | Selectika | other | 2026-09-28 | [1](https://selectika.com/bot/) [2](https://radar.cloudflare.com/bots/directory/selectika-ai) | Retail catalogue ingestion arranged with partners. WordPress estimated training. |
| `SemrushBot-OCOB` | training | Restored, recognise only | `SemrushBot-OCOB` | Semrush | other | 2026-09-28 | [1](https://www.semrush.com/bot/) [2](https://radar.cloudflare.com/bots/directory/semrushbot-ocob) | Crawls for the Semrush Content Toolkit; operator does not mention training. WordPress estimated training. |
| `SemrushBot-SWA/` | training | Restored, recognise only | `SemrushBot-SWA` | Semrush | other | 2026-09-28 | [1](https://www.semrush.com/bot/) [2](https://radar.cloudflare.com/bots/directory/semrush-swa) | SEO Writing Assistant URL accessibility check. Keep historical label, including slash. WordPress estimated training. |
| `WARDBot` | training | Restored, recognise only | `WARDBot` | WEBSPARK | other | 2026-09-28 | [1](https://ward.ai/robot) [2](https://radar.cloudflare.com/bots/directory/wardbot) | Uptime monitoring of user-listed URLs. WordPress estimated training. |
| `ygs-scraper-bot` | training | Restored, recognise only | `ygs-scraper-bot` | YGS Group | other | 2026-09-28 | [1](https://radar.cloudflare.com/bots/directory/ygs-group-falconer-scraper) | Content-licensing scraper for partners that gave permission. Token documented by Radar only; operator page was behind a challenge. WordPress estimated training. |

`Gemini-User` appears only in the WordPress category map, not in its detection list,
and has no verified HTTP identity. It remains historical category data.

## Additions in 2026-09-28.2

Four identities that the WordPress list never included are documented on the same
operator pages as reviewed entries. They were added the same day with automatic
Markdown. Each is described by its operator as a dedicated AI retrieval or search
identity, and none as a browser that navigates, clicks or fills forms.

| Stored label | HTTP token | Operator | Purpose | Evidence | Operator description |
| --- | --- | --- | --- | --- | --- |
| `Kimi-User` | `Kimi-User` | Moonshot AI | on-demand | [1](https://www.kimi.com/policies/kimi-crawlers) | User-initiated actions such as summarising an article; not bulk crawling |
| `Kimi-SearchBot` | `Kimi-SearchBot` | Moonshot AI | search | [1](https://www.kimi.com/policies/kimi-crawlers) | Builds the Kimi search index |
| `Amzn-User` | `Amzn-User` | Amazon | on-demand | [1](https://developer.amazon.com/amazonbot) | Live fetches on a user's behalf, e.g. for Alexa queries |
| `Shap-User` | `Shap-User` | Parallel Web Systems | on-demand | [1](https://parallel.ai/parallel-web-systems-bots) | Accesses content on behalf of users; not automatic crawling |

Registry `2026-09-28.2` recognises 71 identities and serves Markdown automatically to
23. None of these labels has historical counters.

## Read-time category changes

Categories are calculated when reports are read, so these corrections apply to
existing counters for the restored labels. Stored labels and counts are unchanged.

| Stored label | WordPress category | Current category |
| --- | --- | --- |
| `ChathiveCrawler` | on-demand | search |
| `EasyScan` | on-demand | unknown |
| `QATechBot` | on-demand | unknown |
| `Retool/` | on-demand | unknown |
| `PetalBot` | training | search |
| `atlassian-bot` | training | search |
| `LinerBot` | training | search |
| `magpie-crawler` | training | unknown |
| `bigsur.ai` | training | search |
| `QualifiedBot` | training | search |
| `Awario` | training | unknown |
| `BorderxBot` | training | unknown |
| `CitibotSiteCrawler` | training | search |
| `CloudflareBrowserRenderingCrawler` | training | mixed |
| `netEstate NE Crawler` | training | unknown |
| `make.com` | training | unknown |
| `NavuBot` | training | search |
| `Novellum` | training | on-demand |
| `AdpResearchBot/` | training | unknown |
| `SelectikaScraper` | training | unknown |
| `SemrushBot-OCOB` | training | unknown |
| `SemrushBot-SWA/` | training | unknown |
| `WARDBot` | training | unknown |
| `ygs-scraper-bot` | training | unknown |

## Open evidence gaps

- **cohere-ai, FishBot, Anchor Browser, amazon-kendra-:** reconsider when the operator
  documents a concrete HTTP User-Agent. Kendra would also need prefix matching, which
  the product-token matcher deliberately does not support.
- **Radar-only tokens:** Devin, TwinAgent, CledaraBot, HIFIBot, EasyScan, bigsur.ai,
  CitibotSiteCrawler, Novellum, ygs-scraper-bot and make.com are recognised on Radar
  evidence alone.
- **Bravebot:** Radar lists a verified token, while Brave's own page says it does not
  send a differentiated user agent.
- **ApifyWebsiteContentCrawler:** the operator says the crawler does not currently use
  a specific user agent, so most of its runs will not match.
- **Novellum:** operator documentation and site were unreachable on 28 September 2026.
  Status unknown, not retired.
