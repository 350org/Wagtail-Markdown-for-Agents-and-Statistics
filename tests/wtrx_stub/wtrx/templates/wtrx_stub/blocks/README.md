# Synthetic template fixtures

These small, repository-owned templates model the content-bearing HTML shapes of
the matching templates in `350org/wagtail-wtr-350`, first reviewed on 25
September 2026 and checked against `main` on 19 October 2026. They are
behavioural test fixtures, not copies of the site's full templates. CSS,
responsive wrappers, preview helpers and row-balancing code are omitted.
Wagtail's real image/rich-text tags and template inclusion are used.

The matching source files are under
`wtrx/templates/wtrx/components/streamfield/blocks/*_block.html`, with the shared
button at `wtrx/templates/wtrx/components/button.html`. Field shapes come from
`wtrx/blocks/__init__.py`. Donation defaults come from
`wtrx/integrations/actblue.py` (`base_url`, `suggested_amounts`).

The fixtures preserve headings, image rendition filters/alt sources, content
order, link conditions, donation override precedence and the template's dollar
symbol, which the profile rewrites as "$10 USD". They do not establish output
equivalence for every source-template branch, or 350.org's acceptance. Raw
HTML's script/iframe loss is a recorded limit, not silently repaired here. The
feature panel's template is used through the profile's renderer, which drops
an anchor-only CTA before rendering it. The logo grid has its own renderer and
no reduced template.

See `tests/test_profile_wtrx_fallbacks.py` and `tests/test_profile_wtrx_donate.py`.
