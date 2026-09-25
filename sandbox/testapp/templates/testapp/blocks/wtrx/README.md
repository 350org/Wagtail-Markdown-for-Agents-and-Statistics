# Synthetic template fixtures

These small, repository-owned templates model the content-bearing HTML shapes of
`350org/wagtail-wtr-350` at `199776652df68c8b74a51c0493f503228de23cd9`, reviewed
25 September 2026. They are behavioural test fixtures, not copies of the site's
full templates. CSS, responsive wrappers, preview helpers and row-balancing code
are omitted. Wagtail's real image/rich-text tags and template inclusion are used.

The matching source files are under
`wtrx/templates/wtrx/components/streamfield/blocks/*_block.html`, with the shared
button at `wtrx/templates/wtrx/components/button.html`. Field shapes come from
`wtrx/blocks/__init__.py`. Donation defaults come from
`wtrx/integrations/actblue.py` (`base_url`, `suggested_amounts`).

The fixtures preserve headings, image rendition filters/alt sources, content
order, link conditions, donation override precedence and the template's dollar
symbol. They do not establish output equivalence for every source-template
branch or client acceptance. Raw HTML's script/iframe loss and the feature
panel's fragment-only link are recorded limits, not silently repaired here.

See `tests/test_wtrx_fallback_golden.py`, `tests/test_wtrx_donate.py` and
`docs/acceptance/17-rendering-output-review.md` for reviewed examples and limits.
