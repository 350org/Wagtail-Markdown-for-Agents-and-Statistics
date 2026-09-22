# 13 — Agent dataset provenance

Project-owner authorised for #76 (audit A11). Verifies the shipped User-Agent
dataset against the pinned WordPress 1.7.0 reference and settles the one entry that
was not in it. Runtime semantics of detection and classification are in
[12-agent-access-stats.md](12-agent-access-stats.md).

- Given `tests/fixtures/agents-wordpress-1.7.0.json`, extracted from WordPress
  commit `8ad646e826ccbc836863aca30745abe0c5198a53`, the shipped detection tuple
  equals the 69 reference strings in order, followed only by entries listed in the
  fixture's `wagtail_additions` block. The category map has the same keys in the
  same order with the same labels, plus only listed additions. Every addition must
  be named in `docs/agent-access-stats.md`. There is no minimum-count assertion.
- No shipped detection string is a case-insensitive substring of another, so
  appending entries can never change the label an existing agent stores. No
  detection entry or category label is duplicated.
- Each detection entry matches with its case changed and when embedded in a full
  User-Agent header, returns its canonical spelling and resolves to a category other
  than `unknown`. Each category label resolves to its own category under first-match
  precedence, including trailing-slash pairs such as `ShapBot/` and `ShapBot`.
- A header containing several known strings stores the first in dataset order
  (`ClaudeBot` before `Claude-User`); classifying a stored label checks
  `on-demand`, then `search`, then `training`.
- `Gemini-User` is category-only and is never detected. `Google-Extended` and
  `Applebot-Extended` stay in detection as historical robots.txt tokens.
- The former Wagtail-only entry `w4mwnpbXf3MFAbxOkJRw`, the EchoboxBot `hash/`
  segment imported from Cloudflare Radar and removed upstream before 1.7.0, is absent
  from detection and categories. The EchoboxBot header is not detected and the old
  label classifies as `unknown`.
- Removing an entry from the runtime detection list neither deletes nor relabels
  stored rows; category-map edits reclassify history at read time without writes.

## Verification — 15 September 2026

- The two WordPress source files were fetched from the pinned commit through the
  GitHub API, their arrays extracted with PHP and compared with the fixture: 69
  detection strings and 21/12/37 category labels, identical in order. The token's
  history was traced in the WordPress repository (`git log -S`) and its identity
  confirmed against public User-Agent directories and Cloudflare Radar.
- Ruff lint and formatting checks passed. Full pytest: 1,288 passed, including 23
  category and dataset cases. Oldest tox environment (`py311-dj42-wagtail63`): 1,288
  passed, with 10 dependency deprecation warnings.
