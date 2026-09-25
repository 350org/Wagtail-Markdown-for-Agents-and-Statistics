# Pre-transfer review — 21 September 2026

Rendering update, 25 September 2026: D6 and D12 were agreed and implemented on
24 September. The [output review](acceptance/17-rendering-output-review.md) now
maps the generic acceptance checklist to tests and supplies bounded add-on golden
files, including the offline donation-default correction. D9 and client output
sign-off remain open. Earlier dated verification paragraphs below are historical.

Licensing update, 22 September 2026: the project now uses GPL-3.0-or-later,
aligned with the original WordPress plugin, with copyright held by 350.org.
BSD references below describe the historical review and artifacts, not the
current licence; rebuild distribution artifacts before handover.

Verification update, 23 September 2026: the
[bounded deployed fixture run](verification/2026-09-23-bounded-deployed-run.md)
passed all twelve fixture GET/HEAD checks and matched 472 expected/observed
counter increments at zero tolerance. The 21 September gaps described below are
historical. A separate [bounded cold-cache run](verification/2026-09-23-cold-cache-run.md)
established the selected URL's cold state at the observed LHR edge. Multi-day
and genuine vendor-origin evidence remain open, as do D6/D9 and client
presentation decisions. The [remaining-checks review](verification/2026-09-23-remaining-checks-review.md)
records the started 48-hour observation: one sample passed and two are scheduled.
Paid vendor verification is deferred by the owner; neither remaining check is
claimed complete.

**Verdict: conditionally ready for repository handover as a development preview;
not fully accepted v0.1 delivery.** The accompanying fixes should be reviewed and
merged before choosing a transfer revision. Receiving ownership/access and a
usable private security contact still need confirmation. D9 and the remaining
verification must travel with the repository as explicit open work, not as passed
acceptance. No transfer, publication or hosted/deployment settings change was performed.

Reviewed baseline: `855831ac2d472f5905bbb87c286fa7b0fab0f399` on `main`, plus
the accompanying review fixes. Package version remains `0.1.0.dev0`.

## Concurrent work and repository state

Read-only GitHub and local checks preceded edits:

- Local `main`, its tracking ref and GitHub `main` matched the baseline; the
  working tree was initially clean, with one worktree and one local branch.
- No open pull requests or active Actions runs were returned. The process check
  showed this review's Codex session and no other test/build/Git process; this is
  a point-in-time observation, not a lock against later work.
- CI was `disabled_manually`; its sole trigger remains `workflow_dispatch`.
  No workflow was enabled or dispatched. Old successful hosted runs do not
  validate this revision. The final remote recheck still matched `855831a`,
  with no open PRs and CI still disabled.
- Historical remote feature refs still exist. They were not treated as active
  work or deleted. Repository visibility remains private.

## Issues resolved locally

| Area | Finding and resolution |
| --- | --- |
| Dependency bounds | `markdownify>=0.13` admitted 0.13.1, which failed 10 of 59 focused rendering/golden tests. Raised the minimum to the verified 1.2.3 baseline used throughout the matrix; all 59 focused tests pass on that baseline. |
| Installation/support | Documented specific Python/Django/Wagtail combinations, upstream security-support limits and the known MySQL migration limitation. |
| Removal | Added managed-export cleanup before dropping ownership tables, and removal of URL includes, template tags, mixins, hooks, scheduled commands and dependency declarations. |
| Packaging | Added installation/security/contribution guides, documentation, tests, sandbox and scripts to the source archive. Runtime wheel contents remain scoped to the package. |
| Manual CI | Removed the change-filter job, which lacked the checkout required for a manual event. An explicitly dispatched run now selects all validation jobs and has `contents: read` permissions. The workflow remains manual-only and disabled on GitHub. |
| Acceptance documentation | Restored missing D12, corrected D9's request-only hook advice, exposed the unresolved D6 link-policy difference, added scenario 09 to the index and removed stale middleware-stub wording. |
| Attribution/security guidance | Kept BSD-3-Clause and partner attribution; clarified that the WordPress reference retains its licence and third-party provenance requires review. Added the need to confirm a private vulnerability contact during onboarding. |

## Local verification

All tests use synthetic/local data. Simulator HTTP tests use loopback only.

| Environment | Result |
| --- | --- |
| Python 3.12.9 / Django 6.0.7 / Wagtail 7.4.2 (development) | 1,372 passed; 3 sandbox-blocked loopback cases then passed on targeted rerun |
| Python 3.11.15 / Django 4.2.30 / Wagtail 6.3.8 | 1,372 passed; same 3 loopback cases then passed; 10 dependency deprecation warnings in the full run |
| Python 3.13.5 / Django 5.2.17 / Wagtail 7.0.9 | 1,372 passed; same 3 loopback cases then passed |
| Python 3.13.5 / Django 6.0.8 / Wagtail 7.4.3 | 1,372 passed; same 3 loopback cases then passed |
| Python 3.12.9 / Django 5.2.17 / Wagtail 7.4.3 | 1,375 passed in one full run |
| Python 3.13.5 / Django 5.2.17 / Wagtail 7.4.3 | 1,375 passed in one full run |

The initial four full runs exit nonzero because macOS sandboxing denied local
socket binding, not because an application assertion failed. Their three affected
cases were rerun with loopback access in each environment, and all passed. This
is combined full-suite and targeted-rerun evidence, not a claim that the initial
tox invocations were green. Missing cached dependencies for the other two matrix
environments were downloaded from the package registry before testing.

Additional checks:

- Ruff lint/format and `git diff --check` passed. Manual-workflow trigger,
  permissions, checkout steps and five-environment matrix checked structurally;
  no hosted execution was performed.
- Wheel and source archive built with Hatchling. All five migrations, three
  templates, report CSS and BSD licence are included. The source archive includes
  onboarding/test material and excludes local databases, media and cache files.
  Rebuilding a wheel from the extracted source archive produced identical contents.
- Installed the wheel into a separate temporary target, asserted imports came
  from that target, and used existing framework dependencies with a disposable
  SQLite host database: fresh migrations, no model/migration drift, template/CSS
  discovery, publish → Markdown GET, managed deletion and reverse migrations
  passed. This is an installed-artifact test, not a clean dependency-resolution
  test. The older development stack emits seven upstream Treebeard manager
  warnings; there were no package system-check errors.
- `pip-audit` examined the Python 3.13 / Django 6.0.8 / Wagtail 7.4.3 environment:
  43 dependencies audited (44 entries including the skipped package), with no
  known vulnerabilities returned. The unpublished
  package itself was skipped by the database. This does not establish that all
  permitted dependency versions or arbitrary host projects are vulnerability-free.
- Focused inspection covered checked public routes, host isolation, traversal
  rejection, current eligibility/revocation, response-header validation, report
  permissions/escaping, exclusion permissions/CSRF and statistics privacy. These
  have existing regression coverage. A tracked-file scan found no matching
  private-key, GitHub-token or AWS-access-key patterns; this was not a full-history
  secret audit or penetration test.
- PostgreSQL was not rerun for this review. The [15 September benchmark evidence](agent-stats-benchmarks.md)
  remains historical evidence. Full MySQL installation remains unsupported by
  the current 1,024-character unique-path migration on `utf8mb4`.

Test/build/audit scratch evidence is under `/tmp/agentmd-review-*` and `.tox/*/log/`; it is local
and temporary, not a durable handover archive.

## D9 unresolved; D6 and D12 implemented

**D9 — `hide_from_search`:** the core currently gives this project field no export
meaning. The proposed answer remains “no”, requiring explicit 350.org sign-off.
If the client chooses exclusion, use `markdown_export_eligible` with revocation
reconciliation so stored exports, listings and links are also withdrawn; a
request-only serving veto is insufficient. Agree and test the field-change
lifecycle before claiming that client policy is implemented.

**D12 — renderer precedence:** agreed by the package owner and implemented on
24 September 2026 (#1/#2): name override → specialised class MRO → custom template →
generic container recursion → fallback, excluding templates shipped inside Wagtail
from “custom”. StructBlock, StreamBlock and ListBlock recursion are default
registrations below custom templates. Generic tests do not settle client
presentation: 350.org's templated containers need their own renderers (#14). See
[design](design.md) and [scenario 01](acceptance/01-contentpage-end-to-end.md).

**D6 — restricted-target links:** agreed by the package owner and implemented on
24 September. Private targets lose their link while preserving the label; public
targets outside export keep their HTML URL. Generic link tests and the bounded
add-on content golden exercise this behaviour. They do not establish acceptance
of the whole scenario 01. The #14 fixture/output matrix and client sign-off remain
separate from receipt of provisional models and passing tests.

## Bounded live evidence is not full acceptance

The [existing live report](verification/2026-09-21-bounded-live-run.md) records
1,000 requests, 964 assertion passes, 36 known Accept-only/cache limitations,
zero assertion/transport failures, and exactly 603 expected/observed counter
increments. The reconciler still returned **inconclusive (exit 2)**.

Remaining evidence at the 21 September review was explicit. Items 1 and 2 now
have bounded deployed evidence; items 3 and 4 remain open:

1. Six fixtures: fallback, excluded pages, previews, missing exports, private
   exports and navigation-only indexes — completed 23 September 2026.
2. Independently proven cold-cache state — established for one selected ordinary
   URL at the observed LHR edge by [two exact-URL purges and first-request
   evidence](verification/2026-09-23-cold-cache-run.md). Complete edge-wide
   no-refill evidence was unavailable.
3. Multi-day behaviour and reconciliation, within the agreed maintenance scope.
4. Genuine vendor-origin fetches; simulated User-Agent strings cannot authenticate
   OpenAI/Anthropic traffic.

The run used an older origin revision with matching serving/statistics/dataset
code; newer editor controls were not deployed. Tagged logs do not establish
absence of unrelated background traffic. This review generated no new live-site
requests, vendor calls or deployment evidence.

## Client onboarding and remaining gates

Before an actual repository transfer:

- Confirm the destination organisation, receiving administrator, collaborator
  access and maintenance/security responder. The documented private-reporting
  endpoint returned HTTP 404 to the read-only API check, so availability could
  not be established. Confirm a usable private channel; do not silently enable
  features or publish a speculative contact address.
- Review and merge these fixes, then select the exact revision to transfer.
  Retain the licence, copyright and 350.org/TCLP attribution. The agent dataset
  has a pinned [provenance record](acceptance/13-agent-dataset-provenance.md);
  no comprehensive historical authorship clearance is claimed by this review.
- Give the recipient this open-work record and privately retained live artifacts
  referenced by the [evidence manifest](verification/2026-09-21-evidence.json).
  Confirm access to scope/POC material preserved at `pre-handover`, rather than
  relying on stale issue references to files removed from `main`.
- Agree how manual validation and review will be recorded. Branch protection is
  still tracked in legacy #6;
  do not require an automatic CI check that never runs. Any settings change needs
  separate agreement.

After an agreed transfer, update canonical repository/install/security links and
verify recipient access, deploy-key access and private reporting. No destination
has been guessed or hard-coded in this review.

Before claiming release/client acceptance, resolve D9 and agreed fixture/output
criteria, record the release-time verification boundary and remaining live work,
and complete the release/tag/TestPyPI actions in
legacy #31 when
separately authorised. Legacy #64
includes post-release work and is not a blanket prerequisite for starting the
release/maintenance window. Record its start/end dates and the shared 1.5-day
maintenance cap. Future v0.2/v1.0 features do not become transfer blockers merely
because they remain open.

The recipient's starting sequence is [INSTALL.md](../INSTALL.md) for the host
site, [development](development.md) for local contributions, and the
[cache guide](cdn-caching.md) before deployment checks. Production installation
on client infrastructure remains a separately agreed follow-on.
