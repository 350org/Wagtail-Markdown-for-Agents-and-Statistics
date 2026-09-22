# Acceptance scenarios

Given/when/then scenarios agreed **before** each piece of v0.1 work starts. Once
agreed, each scenario becomes one or more tests; the scenario text is the contract,
the tests are its evidence.
Tracked in legacy #63.

| File | Covers | Status |
| --- | --- | --- |
| [01-contentpage-end-to-end.md](01-contentpage-end-to-end.md) | One 350.org ContentPage: generation, retrieval, links, drafts, withdrawal | Proposed |
| [02-page-rendering.md](02-page-rendering.md) | Generic published-page assembly, selection, hooks and diagnostics (#78) | Project-owner authorised; tests in `tests/test_page_rendering.py`; 350.org presentation sign-off remains separate |
| [03-storage-writer.md](03-storage-writer.md) | Managed publication, concurrency, paths and cleanup (#19) | Project-owner authorised; tests in `tests/test_writer.py` |
| [04-public-export-routes.md](04-public-export-routes.md) | Direct retrieval, public URLs, site/path gates and shared serving (#72/#68) | Project-owner authorised; tests in `tests/test_serving.py`; middleware and statistics integration remain separate |
| [05-internal-links.md](05-internal-links.md) | Source-preserving internal links to current public exports (#14) | Project-owner authorised; tests in `tests/test_links.py`; negotiated HTTP entry points remain separate |
| [06-root-directory-indexes.md](06-root-directory-indexes.md) | Root/directory navigation, page preservation and batch finalisation (#20) | Project-owner authorised; tests in `tests/test_indexes.py`; 350.org presentation sign-off remains separate |
| [07-llms-txt.md](07-llms-txt.md) | Managed discovery, current public URLs and batch integration (#21) | Project-owner authorised; tests in `tests/test_llms_txt.py` |
| [08-publish-lifecycle.md](08-publish-lifecycle.md) | After-commit generation, immediate revocation, cascades and shared refresh helpers (#23) | Project-owner authorised; tests in `tests/test_lifecycle.py`; restriction/move receivers remain separate |
| [09-eligibility-lifecycle.md](09-eligibility-lifecycle.md) | Restriction/exclusion withdrawal and restoration, policy reconciliation (#70) | Project-owner authorised; tests in `tests/test_eligibility_lifecycle.py`; client D9 remains separate |
| [10-content-negotiation.md](10-content-negotiation.md) | Query/Accept/UA detection, middleware serving and HTML fallback (#25/#26/#30) | Project-owner authorised; tests in `tests/test_negotiation.py` and `tests/test_middleware.py` |
| [11-discovery-and-checks.md](11-discovery-and-checks.md) | HTML discovery headers, template tag, discovery cache boundary and configuration checks (#27/#28/#29/#68) | Project-owner authorised; tests in `tests/test_discovery.py`, `tests/test_checks.py` and `tests/test_middleware.py` |
| [12-agent-access-stats.md](12-agent-access-stats.md) | UTC daily atomic counters, shared successful-response recording, admin report and retention pruning (#32/#33/#35/#36) | Project-owner authorised; tests in `tests/test_stats.py`, `tests/test_report.py` and `tests/test_prune_stats.py` |
| [13-agent-dataset-provenance.md](13-agent-dataset-provenance.md) | Pinned WordPress 1.7.0 dataset, documented additions, precedence and the removed EchoboxBot token (#76) | Project-owner authorised; tests in `tests/test_categories.py` |
| [14-page-exclusion-settings.md](14-page-exclusion-settings.md) | Page action-menu exclusion form, permissions, locks, CSRF and export transitions (#17) | Project-owner authorised; tests in `tests/test_page_settings.py` |
| [15-editor-exclusion-panel.md](15-editor-exclusion-panel.md) | Optional editor checkbox, revision/preview behaviour, permissions and shared exclusion lifecycle (#18) | Project-owner authorised; tests in `tests/test_editor_panel.py` |
| [16-agent-traffic-simulator.md](16-agent-traffic-simulator.md) | Deterministic traffic, durable client evidence, cache assertions and UTC reconciliation (#59) | Project-owner authorised; local tests in `tests/test_agent_simulator.py`; deployed and genuine vendor verification remain separate |

## Status

- **Proposed** — drafted; open decisions listed with a recommendation. Not a contract.
- **Agreed** — decisions resolved and recorded with the date and who agreed. Tests may
  be written against it.
- **Covered** — every scenario has a passing test; the test names are listed.

## Conventions

- Scenarios describe observable behaviour — files, HTTP responses, Markdown text — not
  implementation. They must not name internal functions.
- Fixtures are small and synthetic. 350.org models come from the provisional
  reference notes on issue #65; the core package never imports `wtrx`, so
  350-specific mapping (such as the hero) is project-owned code exercised by the test
  project, not by the package.
- Out-of-SOW issues are never required by a v0.1 scenario.
- An open decision is written as **Decision D*n*** with a proposed answer. Agreement
  replaces the proposal with the agreed answer; it is not deleted.
