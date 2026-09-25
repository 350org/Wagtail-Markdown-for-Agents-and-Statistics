# 01 — One ContentPage, end to end

**Status: Proposed.** Not yet agreed with 350.org. Open decisions are marked
**D*n*** with a recommendation.

**Implementation review, 25 September 2026:** the
[rendering output review](17-rendering-output-review.md) maps these areas to tests
and supplies full documents from the shipped 350.org add-on. Its bounded fixture
uses the current hero CTA stream and nested block shapes. The tree and sample
below remain a proposed client scenario, not proof that every step has been
accepted end to end.

Proves one complete path before breadth: a published
350.org ContentPage with a hero and nested body → generated Markdown → negotiated and
direct retrieval → working links → withdrawal when restricted, with a newer draft never
leaking.

Exercises: page assembly legacy #78,
rendering legacy #7–#15,
export policy and paths (#16–#19), revocation (#70), negotiation (#25–#30), direct
export route (#72). Custom-block breadth stays in #65; bakerydemo remains the generic
baseline.

## Fixture

A small synthetic tree on site `localhost` (exports live under `localhost/`, the
hostname without the port). Models are the provisional 350.org `wtrx` ones.

```text
HomePage  "350"                            /
├── ContentPage "Fossil Free Future"       /fossil-free-future/     ← page under test
├── ContentPage "Get involved"             /get-involved/           public, CTA target
└── ContentPage "Organiser handbook"       /organiser-handbook/     private (login restriction)
```

**Page under test — published revision:**

| Field | Value |
| --- | --- |
| `title` | Fossil Free Future |
| `hero_headline` | Keep it in the ground |
| `hero_copy` | `<p>Join the <b>global</b> movement to end fossil fuels.</p>` |
| `hero_image` | a decorative photo (background in HTML) |
| `hero_cta` | one `button`: text "Get involved", `link_page` → "Get involved" page |
| `search_description` | Why we campaign for a fossil-free future. |
| `body[0]` `text` | `<h2>Why now</h2><p>Read the <a href="https://www.ipcc.ch/">IPCC report</a> and our <a linktype="page" id="…organiser handbook…">organiser handbook</a>.</p>` |
| `body[1]` `section` (background `dark`, padding `lg`) | contains a `card_grid` of two cards: "Divest" (description "Move money out of fossil fuels.", link → "Get involved") and "Organise" (description "Start a local group.", no link) |
| `body[2]` `quote` | `content`: `<p>There is no planet B.</p><p>— Campaigner</p>` (the current block has no separate attribution field) |

**Newer draft (saved, not published):** `hero_headline` "DRAFT HEADLINE" and an extra
`text` block "DRAFT PARAGRAPH".

## Expected Markdown

Stored at `localhost/fossil-free-future.md`. Frontmatter abridged to the fields this
scenario asserts; the full set is #13.

```markdown
---
title: Fossil Free Future
permalink: http://localhost/fossil-free-future/
type: wtrx.ContentPage
excerpt: Why we campaign for a fossil-free future.
---

# Keep it in the ground

Join the **global** movement to end fossil fuels.

[Get involved](http://localhost/markdown/get-involved.md)

## Why now

Read the [IPCC report](https://www.ipcc.ch/) and our organiser handbook.

### Divest

Move money out of fossil fuels.

[Learn more](http://localhost/markdown/get-involved.md)

### Organise

Start a local group.

> There is no planet B.
>
> — Campaigner
```

The exact whitespace, card heading level and quote attribution format are fixed by the
golden file once D1–D11 are agreed; the scenarios below assert structure, not bytes.

## Decisions to agree

| # | Question | Proposed answer | Why |
| --- | --- | --- | --- |
| D1 | Which heading is the page's `# H1`? | Exactly one H1: `hero_headline` if set, otherwise `title`. Frontmatter `title` is always `page.title`. | Matches the HTML, where the hero `<h1>` is `hero_headline or title`. Avoids a duplicate title heading. |
| D2 | Content order | H1 → hero copy → hero CTA → body blocks in stream order. | Matches the rendered HTML order (`hero.html` then `body`). |
| D3 | Hero image | Omitted. | HTML renders it as a background with `alt=""` and `role="presentation"`; it carries no content. A hero *video* is out of this fixture (see D8). |
| D4 | Hero CTA with text but no link | Omitted. | The template renders the button only when a page or URL is set. |
| D5 | Section block presentation fields | `background`, `padding`, `anchor_id` produce no output; the section's content renders in place, without an added heading. | Presentation only. Anchor preservation can be revisited if agents need fragment links. |
| D6 | Internal link to a **private** page (not live, or behind its own or an inherited view restriction) | **Agreed 24 September 2026:** keep the link text, drop the link. Links to public pages that are only outside the export (excluded, type disabled, hook veto, another site) keep their HTML URL. | Exporting the URL of a restricted page reveals it exists (design: "must not reveal restricted related pages"). A public page's URL reveals nothing, and agents keep a useful link. |
| D7 | Internal link to an **eligible** page | Absolute managed export URL for the target's current owned file, including a relocated path. | Implemented by link rewriting. HTML discovery may advertise the query URL; document-body links use the direct route. |
| D8 | Hero video | Out of this scenario; covered with #65 blocks. | Keeps 01 to one path. |
| D9 | Does `hide_from_search` exclude from Markdown? | **Proposed no.** It has no built-in export meaning; normal live/restriction/type checks and `PageAgentSettings.excluded` still apply. If 350.org wants it to exclude content, map it through the project `markdown_export_eligible` hook and reconcile existing exports. | A request-only serve gate does not remove stored exports, links or discovery listings. The core must not depend on `wtrx`. **Needs explicit 350.org sign-off.** |
| D10 | Card link text | `Learn more`, as in the HTML, without the `→` arrow; the card's `### heading` immediately above gives it context. Card `image` renders as `![image title](url)` when set (not in this fixture); the decorative `icon` is omitted. | The HTML link label is a fixed "Learn more →" whatever the card. Linking the heading instead reads better for agents but departs from the page; propose staying faithful and revisiting with #65. |
| D11 | Quote marks | A `quote` block's authored rich-text content becomes a Markdown blockquote. An attribution belongs in that content; no separate attribution field is read. | The current source block supplies `content`. The full-page golden shows an authored final `— Campaigner` paragraph. |
| D12 | Block dispatch precedence (#7/#11/#12) | **Agreed 24 September 2026:** name override → specialised class renderer (nearest in MRO) → custom presentation template → generic container recursion → fallback. Inherited Wagtail default templates do not count as custom. | Agreed as proposed on #63. A custom template wins over recursion so presentation-only fields do not leak. Implemented in #1/#2; see [design](../design.md). |

### Review of D9/D12 — 21 September 2026 (historical)

Neither decision is accepted by the bounded bakerydemo verification. D9 needs a
client policy decision and examples covering generation, direct/negotiated serving,
links and discovery after a flag change. If a project adopts the eligibility hook,
it must reconcile revocation when the field changes (bulk updates bypass signals)
and after configuration changes with `agentmd_revoke_ineligible`.

D12's dispatch question from that review was resolved on 24 September, as recorded
below. The earlier absence of default StructBlock/StreamBlock recursion is no
longer current. Local generic tests still do not constitute client presentation
sign-off.

### Decisions — 24 September 2026

D6 and D12 were agreed by the package owner. D6 is implemented: link rewriting
replaces a link to a private target with its label (see
[internal links](../internal-links.md)). D12 is implemented (#1/#2): StructBlock
and StreamBlock recursion are now default registrations alongside ListBlock, and
all three rank below a custom template. A container with its own template, as every
350.org container has, still renders through that template until a project renderer
is registered for it. D9 still needs 350.org sign-off.

## Scenarios

### Generation

**S1 — Generating a published page writes its Markdown**
- **Given** the fixture, with the page under test published
- **When** `python manage.py agentmd_generate` runs
- **Then** `localhost/fossil-free-future.md` exists in the export storage
- **And** it contains exactly one `# ` heading, "Keep it in the ground" (D1)
- **And** its content appears in the order of D2: headline, hero copy, CTA, "Why now",
  "Divest", "Organise", the quote
- **And** "global" is bold, the IPCC link is kept as an external link, and both cards'
  headings and descriptions are present (nested section → card grid → cards)
- **And** no section background, padding or image of the hero appears (D3, D5)
- **And** the frontmatter `title` is "Fossil Free Future" and `excerpt` is the search
  description

**S2 — Publishing generates without a command**
- **Given** the fixture with no export yet
- **When** an editor publishes the page under test
- **Then** after the transaction commits, `localhost/fossil-free-future.md` exists
- **And** if the publishing transaction rolls back, no file is written

**S3 — A newer draft never appears**
- **Given** the page under test is published and then has the newer draft saved
- **When** the Markdown is generated (by command or by publishing an unrelated page)
- **Then** the file contains "Keep it in the ground" and not "DRAFT HEADLINE" or
  "DRAFT PARAGRAPH"
- **When** the draft is then published
- **Then** the file contains "DRAFT HEADLINE" and "DRAFT PARAGRAPH"

**S4 — Missing optional hero fields**
- **Given** the page under test with `hero_headline`, `hero_copy` and the CTA cleared
- **When** it is generated
- **Then** the single H1 is "Fossil Free Future" and the first content after it is the
  "Why now" section (D1, D2, D4)

### Links

**S5 — Links resolve for agents**
- **Given** the generated file from S1
- **Then** the CTA and the "Divest" card's "Learn more" link (D10) point to the
  "Get involved" page's absolute Markdown URL (D7)
- **And** requesting that URL as an agent returns the "Get involved" Markdown
- **And** the external IPCC link is unchanged

**S6 — Links to restricted pages are not revealed**
- **Given** the generated file from S1
- **Then** "organiser handbook" appears as plain text
- **And** neither `/organiser-handbook/` nor its Markdown URL appears anywhere in the
  file, `llms.txt` or `manifest.json` (D6)

### Retrieval

**S7 — Agents negotiate Markdown; browsers get HTML**

| Request to `/fossil-free-future/` | Response |
| --- | --- |
| `?output_format=md` | 200, `Content-Type: text/markdown; charset=utf-8`, body is the S1 file |
| `Accept: text/markdown` | same as above |
| `Accept: text/html` (a browser) | 200 HTML, with `Link: <…fossil-free-future/?output_format=md>; rel="alternate"; type="text/markdown"` and `Vary` including `Accept` |
| `Accept: */*` (curl default) | 200 HTML — wildcards never select Markdown |
| `Accept: text/markdown;q=0` | 200 HTML |
| `HEAD` with `Accept: text/markdown` | same headers as the GET, no body |

- **And** every Markdown response carries `Cache-Control: private, no-store, max-age=0`
  and `Vary: Accept, User-Agent`

**S8 — Direct export URL**
- **Given** the generated file from S1 and the package's URLconf included by the host
- **When** the explicit Markdown route for the page (#72) is requested
- **Then** it returns the same Markdown as S7
- **And** a route for a page with no export returns 404

**S9 — No file yet falls back to HTML**
- **Given** the page under test is published but its export file has been deleted
- **When** it is requested with `Accept: text/markdown`
- **Then** the response is the normal HTML page (200), never a 404

**S10 — Discovery lists the page**
- **Given** the generated fixture
- **Then** `localhost/llms.txt` and `localhost/manifest.json` list the page under test
  and "Get involved", and do not list "Organiser handbook"

### Withdrawal

**S11 — Restricting the page withdraws it immediately**
- **Given** the page under test is generated and served as in S7
- **When** an editor adds a login restriction to it
- **Then** `localhost/fossil-free-future.md` is deleted without waiting for a rebuild
- **And** an agent request with `Accept: text/markdown` gets the same response as a
  browser would (Wagtail's login/restriction response), never the Markdown
- **And** the direct export URL returns 404
- **And** the page is no longer in `llms.txt`, `manifest.json` or the root `index.md`
- **And** HTML responses for it no longer carry the Markdown `Link` header
- **And** a generation that started before the restriction cannot write the file back
  afterwards (#19)

**S12 — Lifting the restriction restores it**
- **Given** S11
- **When** the restriction is removed
- **Then** after commit, the file, the discovery listings and the `Link` header return

**S13 — Excluding the page withdraws it**
- **Given** the page under test is generated
- **When** its `PageAgentSettings.excluded` is set to true
- **Then** the same withdrawal as S11 applies
- **When** `excluded` is set back to false
- **Then** the same restoration as S12 applies

**S14 — Unpublishing withdraws it**
- **Given** the page under test is generated
- **When** it is unpublished
- **Then** the same withdrawal as S11 applies, and agent requests get the normal 404

## Out of scope for 01

IndexPage listings and pagination (#20), FormPage and signup/donate blocks (#65, #39),
page moves and slug changes (#69), hero video (D8), localisation, statistics logging
(#32–#36, separate scenario), multi-site, bundles and every out-of-SOW issue.
