# 02 — Page rendering orchestration

Implementation scope authorised by the project owner on 14 September 2026 after
the recommendation to implement #78. These cases define the generic package
behaviour and its tests; they do not record 350.org sign-off on scenario 01.

- Given a published page and a newer draft (including a draft instance supplied
  by the caller), rendering uses the database's live revision for all selected
  fields, tags and page hooks. Publishing the draft changes the next output.
- Given ordered `PAGE_FIELDS`, only those StreamField/RichTextField fields appear,
  in that order. An unconfigured type auto-detects them in model definition order.
  Unknown models, missing/duplicate field names and unsupported types are errors.
- Given an empty optional field, it contributes no text or extra separators. A page
  without rendered content raises an explicit error; its title alone is insufficient.
- Given a form page or a type without a StreamField, rendering reports unsupported
  output. A title, rich-text intro or page hook cannot silently turn it into a
  complete v0.1 export. Unsaved, deleted and unpublished pages also report errors.
- Given page hooks, they receive the assembled field body and the same published
  page/site/locale context used by conversion and frontmatter. Hooks run in order,
  chain string results, and may return `None` to keep the body. Exceptions propagate.
- The default heading is the page title. A project hook can replace or suppress it
  through `context["heading"]`; authored headings are preserved without guessing
  which ones are duplicates. YAML title remains independent of the body heading.
- A project-owned hero example orders heading, hero copy, CTA, then selected fields.
  Missing optional hero content is omitted; decorative hero media is omitted.
  This illustrates the proposed scenario 01 decisions, not accepted customer output.
- Given generated navigation supplied by the index generator, append it once
  after the authored body. The caller owns selecting one listing; assembly never
  invents child listings or discards authored text to deduplicate them.
- Frontmatter is serialised separately from body text. Final internal-link rewriting
  runs on the assembled body before YAML is joined, and generated navigation comes
  from the index generator. Command diagnostics report these rendering errors.
  Storage and serving are covered by their own acceptance scenarios.

The [25 September output review](17-rendering-output-review.md) maps generic cases
to existing tests and adds shipped-add-on goldens. It records current implementation
output while preserving the separate client sign-off boundary.
