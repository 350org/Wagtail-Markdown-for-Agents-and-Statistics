# Maintenance scripts

Run these from the repository root after installing development dependencies with
`uv sync`. They support distinct workflows; none is a general cleanup command.

| Entry point | Purpose and effects | Guide |
| --- | --- | --- |
| `bash scripts/bakerydemo-setup.sh` | Creates or updates a sibling bakerydemo checkout, installs dependencies, patches its configuration, migrates/seeds its database and generates exports. | [Development](../docs/contributing/development.md) |
| `uv run python -m scripts.agent_simulator --help` | Traffic planning, execution and counter reconciliation. Planning can fetch public documents; `run` sends HTTP requests and writes evidence. Use the module entry point so helper imports resolve. | [Simulator procedures](../docs/agent-simulator.md) |
| `uv run python scripts/benchmark-stats-write.py` | Creates, exercises and drops the counter table in an empty scratch database named `agentmd_stats_benchmark_*`. Defaults to the sandbox MySQL settings; has no `--help` mode. | [Benchmark setup and limitations](../docs/contributing/agent-stats-benchmarks.md) |

`traffic_simulator/` contains the simulator's planning, transport and reconciliation
helpers.

Keep run logs and deployment evidence outside this repository. Committed fixtures
and golden files are reviewed test inputs and expectations; see the
[test guide](../tests/README.md).
