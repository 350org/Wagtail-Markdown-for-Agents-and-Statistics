# 13 — Agent registry provenance and policy

The project owner authorised an independent baseline on 22 September 2026,
superseding the WordPress active-list parity requirement from legacy #76.
See [agent registry](../agent-registry.md) for the evidence, initial scope and review
procedure; [statistics](../agent-access-stats.md) for counter semantics.

- Active identities carry source URLs, review dates, purposes, HTTP tokens and an
  independently reviewed automatic-Markdown flag. They load offline from package data.
- Matching uses case-insensitive product boundaries, documented aliases and registry
  order for conflicting identity claims. Negative cases cover longer unrelated names
  and incidental documentation URLs. Only canonical bounded labels can be stored.
- Recognition-only bots receive HTML under the User-Agent trigger; query/Accept
  triggers remain available and those Markdown accesses record their recognised label.
- Robots.txt-only controls and unreviewed inherited entries do not detect. Historical
  classification is retained separately and does not re-enable serving or CDN bypass.
- Multiple intents report as mixed, counted once. General-purpose activity can have
  unknown intent despite a recognised identity. Report filters, rows, charts and
  totals use the same classification snapshot.
- Frozen WordPress categories still equal the attributed 1.7.0 reference fixture.
  Active corrections are documented, including their read-time effect on older rows.
  No counters are deleted or rewritten and migration 0006 remains frozen.
- Cloudflare bypass output uses only automatic-serving HTTP tokens, scoped to a
  validated hostname, plus enabled explicit request triggers. It is a conservative
  superset of origin parsing; it never changes bot security or access permissions.
- Simulator plans share identity matching and expect HTML for recognition-only UA
  requests. The free-plan Accept-only cache limitation applies to recognised clients
  outside the serving subset too.

## Historical verification — 15 September 2026

The earlier audit verified 69 ordered detection strings and 21/12/37 category
entries from WordPress 1.7.0 commit `8ad646e826ccbc836863aca30745abe0c5198a53`.
`tests/fixtures/agents-wordpress-1.7.0.json` retains that reference and attribution.
The EchoboxBot hash fragment `w4mwnpbXf3MFAbxOkJRw` was excluded then and remains
excluded. That audit established parity, not current accuracy or active-list scope.

## Verification — 22 September 2026

- Ruff lint, formatting (180 Python files) and `git diff --check` passed.
- Python 3.12.9 / Django 6.0.8 / Wagtail 7.4.3: full run completed with 1,424
  passing and two volume-test expectations still assuming four intent buckets.
  After updating the independent test oracle for mixed purposes, all 96 affected
  volume, simulator and report cases passed. A separate final registry/category/
  Cloudflare/simulator run passed 111 cases (three loopback cases excluded there
  and included in the 96-case run).
- Python 3.11.15 / Django 4.2.30 / Wagtail 6.3.8, installed wheel via tox: full run
  completed with 1,425 passing and three stale test expectations; the same final
  96-case rerun passed after those fixes. The only rerun warning was an upstream
  locale deprecation. Together these checks cover the final 1,428 collected cases.
- Confirmed the built wheel contains the JSON registry, historical category module
  and standalone Cloudflare expression generator.
- Generated the host-scoped bypass for the supplied test domain: 722 characters
  and 12 automatic identities. Live deployment and Cloudflare saving/verification
  were not performed. Apply the matching application before narrowing the edge rule.
