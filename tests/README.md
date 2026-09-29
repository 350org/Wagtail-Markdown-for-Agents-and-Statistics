# Test suite

Run `uv run pytest` from the repository root. The sandbox is the Django test
project; pytest creates isolated test databases. See
[CONTRIBUTING.md](../CONTRIBUTING.md) for lint, compatibility and PostgreSQL checks.

| Area | Starting points |
| --- | --- |
| Rendering and reviewed output | `test_golden.py`, `test_page_rendering.py`, `golden/` |
| Ownership, paths and delivery | `test_writer.py`, `test_serving.py`, `test_multilingual.py`, `test_storage_reconfiguration.py` |
| CMS events and revocation | `test_lifecycle.py`, `test_eligibility_lifecycle.py`, `test_path_lifecycle.py` |
| Negotiation and discovery | `test_negotiation.py`, `test_middleware.py`, `test_discovery.py` |
| Statistics and report budgets | `test_stats.py`, `test_report.py`, `test_stats_volume.py` |
| Registry and simulated traffic | `test_agent_registry.py`, `test_categories.py`, `test_agent_simulator.py`, `test_simulator_fixtures.py` |

This is a navigation aid, not an exhaustive test inventory. Use the
[package guides](../docs/README.md) for supported behaviour and configuration.

## Fixtures and test isolation

- `conftest.py` disconnects automatic export lifecycle receivers for component
  tests. Use `@pytest.mark.export_lifecycle` when exercising the real receivers.
- `stats_volume` tests are included in the full suite. Use
  `uv run pytest -m stats_volume` to focus on them; measurements and query budgets
  are explained in the [benchmark guide](../docs/contributing/agent-stats-benchmarks.md).
- `fixtures/agents-wordpress-1.7.0.json` is retained provenance used by category
  tests, not the active HTTP agent registry. Update the registry through its
  [review procedure](../docs/contributing/agent-registry-review.md).
- The `*_urls.py` modules configure test routes, including translated URLs and
  missing export routes. They are support modules rather than collected tests.

## Updating golden output

Files in `golden/` are committed, reviewed output. Regenerate only the relevant
test module when the output change is intentional, then review the diff. For example:

```bash
UPDATE_GOLDEN=1 uv run pytest tests/test_page_rendering.py
```

`test_golden.py` covers built-in renderers and frontmatter. Other snapshots belong
to `test_page_rendering.py`, `test_indexes.py` and `test_llms_txt.py`.
Run those tests normally after reviewing updates. Golden output records current
behaviour for the reviewed fixtures.
