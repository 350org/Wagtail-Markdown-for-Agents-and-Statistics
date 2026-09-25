# Rendering output review — 25 September 2026

**Status: implementation evidence and review candidates; client sign-off remains
open.** This reconciles #4 against the existing tests and the bounded 350.org work
in #14. It does not reopen implemented subsystems or mark proposed scenario 01 as
accepted. D6 and D12 were agreed by the package owner on 24 September; D9 still
needs a client decision.

## Existing coverage, retained

| Checklist item | Evidence | Boundary |
| --- | --- | --- |
| HTML cleanup; entities and Unicode | [`test_text_renderers.py`](../../tests/test_text_renderers.py): `test_script_and_style_are_removed_with_their_content`, `test_template_content_is_omitted`, `test_entities_and_unicode_are_preserved`; [`built_ins.md`](../../tests/golden/built_ins.md) | Hidden/collapsed content other than `<template>` is intentionally retained; project renderers omit conditional success messages. |
| Code whitespace and languages | Same file: `test_code_block_keeps_whitespace_and_language_hint`; built-in golden | Link rewriting separately protects fenced/indented/inline code. |
| Table captions, pipes, zero/empty cells, line breaks | [`test_media_renderers.py`](../../tests/test_media_renderers.py): caption, zero-cell, pipe, ragged-row and typed-table tests; built-in golden | The renderer preserves authored headings; no inferred table semantics. |
| Image spacing, descriptions, alt overrides and decorative images | [`test_text_renderers.py`](../../tests/test_text_renderers.py): `test_inline_image_is_separated_from_text_by_one_space`, decorative-image tests; [`test_media_renderers.py`](../../tests/test_media_renderers.py): description/contextual-alt tests | Image URLs use `WAGTAILADMIN_BASE_URL` when configured; separately stored 350.org credits remain undecided. |
| False/zero and YAML typing | [`test_scalar_renderers.py`](../../tests/test_scalar_renderers.py); [`test_frontmatter.py`](../../tests/test_frontmatter.py): `test_values_round_trip_through_yaml`, `test_bool_like_editor_values_keep_their_types`; [`frontmatter.md`](../../tests/golden/frontmatter.md) | Numeric zero survives. A false BooleanBlock contributes no prose; YAML false remains a boolean. Strings, dates and empty lists retain their types. |
| Frontmatter precedence, collisions and owner privacy | [`test_frontmatter.py`](../../tests/test_frontmatter.py): identity-collision, hook-order, unsupported-value and owner tests | Optional owner means the owner's full name, not editorial author. 350.org Post mappings are still open. |
| Link traversal from canonical/direct documents | [`test_links.py`](../../tests/test_links.py): `test_page_hooks_and_navigation_are_rewritten_before_frontmatter`; [`test_middleware.py`](../../tests/test_middleware.py) | Body links use managed direct export URLs. Discovery's alternate URL can use query negotiation; these are distinct contracts. |
| Relocated export paths and code protection | [`test_links.py`](../../tests/test_links.py): `test_relocated_export_and_published_revision`, `test_code_images_and_nonlinks_are_untouched`; middleware's relocated/index case | Uses recorded owned paths, preserves fragments and leaves code examples untouched. |
| Private-target links (D6) | [`test_links.py`](../../tests/test_links.py): `test_links_to_private_pages_keep_only_their_label`, inherited restriction/unpublish cases | Private targets lose their link. Public pages outside the export keep their HTML link. Already implemented. |
| Dispatch and unknown templates (D12) | [`test_container_defaults.py`](../../tests/test_container_defaults.py), [`test_template_fallback.py`](../../tests/test_template_fallback.py): unregistered template, missing/broken template and nested error cases | Specialised renderer precedes a custom template; custom template precedes generic container recursion. Template failures are explicit, not empty success. |
| Offline context and embeds | [`test_template_fallback.py`](../../tests/test_template_fallback.py): page/site/locale and site-bound settings tests; [`test_offline_embeds.py`](../../tests/test_offline_embeds.py) | Supplies locale context; this alone does not prove translated default labels for every page language. No provider fetch during fallback. |
| Published revisions, optional fields and navigation | [`test_page_rendering.py`](../../tests/test_page_rendering.py), [`test_indexes.py`](../../tests/test_indexes.py); [`page.md`](../../tests/golden/page.md), [`index.md`](../../tests/golden/index.md) | Existing generic page goldens use a demonstration hero hook, not the shipped 350.org add-on. |
| Publish/rollback, restriction/exclusion, restoration and stale builds | [`test_lifecycle.py`](../../tests/test_lifecycle.py), [`test_eligibility_lifecycle.py`](../../tests/test_eligibility_lifecycle.py), [`test_writer.py`](../../tests/test_writer.py) | Shared package controls; no new revocation mechanism or duplicated lifecycle matrix needed here. |
| Settings changes, site isolation and drafts | [`test_wtrx_settings_lifecycle.py`](../../tests/test_wtrx_settings_lifecycle.py) | Actual settings reads and stored output on filesystem and synthetic remote storage; the donation case now invokes the real add-on renderer/template instead of constructing a synthetic link. |

## New review artifacts

All data are synthetic and repository-owned. Normal tests need neither the site
checkout nor its optional dependencies. The full-page fixtures use the existing
`tests/wtrx_stub` models and the shipped add-on. Their source basis is
`350org/wagtail-wtr-350` at `199776652df68c8b74a51c0493f503228de23cd9`.
Only database IDs are normalised in page goldens; dates are frozen and all URLs,
headings, text, metadata and whitespace are compared.

| Review file | Observable behaviour | Test |
| --- | --- | --- |
| [`wtrx-content.md`](../../tests/golden/wtrx-content.md) | One hero H1; pre-header/copy/CTA/caption before the body; card grid; accordion with an image/caption/video link; quotation; campaign-specific ActionKit destination; private-target label without its URL; no success message | [`test_wtrx_golden.py`](../../tests/test_wtrx_golden.py): `test_published_addon_document_golden_survives_newer_draft` also stores and retrieves the document by canonical query and direct route, follows the emitted target link, and verifies a newer draft appears only after publication. |
| [`wtrx-content-no-hero.md`](../../tests/golden/wtrx-content-no-hero.md) | Ordinary title H1 with body retained; no hero prose/caption/CTA | Two cases in `test_optional_hero_document_goldens`: a hidden populated hero, and cleared optional fields with an unlinked button. Both intentionally have the same expected output. |
| [`wtrx-index.md`](../../tests/golden/wtrx-index.md) | Real add-on hero → intro → body → one generated child listing | `test_addon_index_golden_has_one_generated_listing`; repeat generation must not duplicate the listing. |
| [`wtrx-template-fallbacks.md`](../../tests/golden/wtrx-template-fallbacks.md) | Heading, raw HTML, image grid, linked-logo grid, image/card list, image/text, feature panel and callout | [`test_wtrx_fallback_golden.py`](../../tests/test_wtrx_fallback_golden.py); each case verifies it reaches fallback. Reduced templates model content-bearing markup, not every site-template branch. Their [provenance and omissions](../../sandbox/testapp/templates/testapp/blocks/wtrx/README.md) are explicit. |
| [`wtrx-donate.md`](../../tests/golden/wtrx-donate.md) | Site-default destination/amounts; authored URL/amount/button overrides; prose retained without an enabled integration | [`test_wtrx_donate.py`](../../tests/test_wtrx_donate.py); also covers malformed defaults, missing site, active-language amount formatting, context isolation and explicit template failure. |

The full-page fixture is a bounded addition to scenario 01, not an exact copy of
its historical proposed tree. Its nested paths are card-grid → cards and
accordion → image/video. Section/timeline nesting remains covered by
`test_contrib_wtrx.py`. FormPage exclusion, every page subtype, all nine historical
fallbacks on the complete site, and a translated full-page corpus are not claimed
by these snapshots.

## Donation finding and correction

The earlier #14 matrix said donation defaults worked offline. Inspection and a
direct rendering check against the pinned source disproved that: `DonateBlock`
reads `base_url` and `suggested_amounts` only through `request`, so a defaults-only
block lost its donation destination during export. The previous settings-lifecycle
test read an invented `page_url` through a synthetic hook and could not detect it.

The optional add-on now registers a donation renderer that obtains the enabled
ActBlue configuration from export's site-bound settings and replaces those two
template-context values. It still uses the site's template for content, override
precedence, labels, dollar symbol and amount formatting, with the same offline
embed guard and conversion hooks as fallback. No change is made to the site or
core dispatch. Invalid configured amount lists retain the site's empty-list
behaviour; the destination still renders. The default destination and amounts
were also verified with the **real pinned block and template**, independently of
the synthetic fixture.

The synthetic settings fixture now uses the actual `base_url` and
`suggested_amounts` names. Its migration is test-only; the add-on has no production
migration. The [drift snapshot](../fixtures/wtrx-blocks.json) changes only donation's
dispatch/renderer: the 31-type split is now 20 add-on renderers, three core renderers
and eight template fallbacks.

## Decisions still requiring review

| Decision | Current observable output | Required disposition |
| --- | --- | --- |
| D9: `hide_from_search` | No built-in export effect | Client must accept this or specify eligibility plus revocation/reconciliation. |
| Separate image credit | Not automatically added; authored captions remain | Client choice; compare the image/caption in the content golden before requesting a change. |
| Logo grid | Linked images, with the organisation name as the synthetic fallback alt text | Accept the gallery or request a reviewed text-list diff. |
| Donation currency and locale | Template's `$` retained; active-language decimal formatting retained | Currency-code policy and a broader language corpus remain open. This fix supplies defaults and does not choose a currency. |
| Post metadata and canonical override | Generic publication dates and permalink; no automatic custom Post author/date/category or `canonical_url` mapping | Agree field meanings and precedence before adding mappings or expected outputs. |
| Feature-panel fragment-only CTA | `[Join](#join)` survives its template, although Markdown contains no matching anchor | `test_feature_panel_fragment_is_a_recorded_fallback_limit` records the current limitation. Decide omission versus anchor preservation; the explicit ButtonBlock already omits fragment-only links. |
| Raw-HTML embedded player | Player iframe absent; surrounding authored text retained | Explicit fallback limit; use the video renderer when a media link is needed. |
| Full client presentation | The five files above pin implementation output | A named reviewer must accept each file or request a specific diff; passing tests alone do not close #4/#14/#15. No client approval is recorded here. |

To review an intentional output change, run the focused tests with
`UPDATE_GOLDEN=1`, inspect the Markdown diff, then rerun without that flag:

```bash
UPDATE_GOLDEN=1 uv run pytest tests/test_wtrx_golden.py tests/test_wtrx_fallback_golden.py tests/test_wtrx_donate.py
uv run pytest tests/test_wtrx_golden.py tests/test_wtrx_fallback_golden.py tests/test_wtrx_donate.py
```

Do not regenerate the generic goldens just to absorb unrelated changes. Record
the reviewer, date, exact golden revision and accepted/deferred decisions when
client review takes place. Hosted workflow execution and live deployment remain
separate from this local evidence.

## Local verification

| Environment / check | Result |
| --- | --- |
| Python 3.12.9 / Django 6.0.8 / Wagtail 7.4.3 / markdownify 1.2.3 | Full development suite: 1,647 passed. |
| Python 3.11.15 / Django 4.2.30 / Wagtail 6.3.8 / markdownify 1.2.3 | Full compatibility suite: 1,647 passed; 10 upstream deprecation warnings. The same committed goldens pass on both versions. |
| Real pinned site source, Python 3.13.5 / Django 5.2.17 / Wagtail 7.4.3 | Direct donation-default rendering and updated definition snapshot verified. This is not a full site acceptance suite. |
| Ruff lint/format, whitespace, migration drift and local review links | Passed. Core startup without the optional add-on also passed. |

The package suites use synthetic data and local storage/loopback only. No production
database, hosted Actions run, external form fetch or client sign-off was used as
verification evidence.
