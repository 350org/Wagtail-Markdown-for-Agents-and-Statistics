#!/usr/bin/env python3
"""Compare the agent registry with agent-signals' list, allowing only listed differences.

The registry holds exactly agent-signals' entries, active and retired, with the same
labels, operators, categories, kinds, retirement and serving (#93). The differences
it may have are listed in src/wagtail_markdown_agents/data/agent-signals-differences.json,
with the agent-signals revision they were checked against.

    python scripts/agent_signals_drift.py path/to/agent-signals/data/agents.json \\
        [--cases path/to/agent-signals/tests/conformance/cases.json]

The exit status is non-zero when agents.json is a different revision from the one
the differences file records, when any entry or operator differs, or when a
conformance case differs without being listed (or is listed and no longer differs).
No network access: pass a local checkout or a downloaded release file.
"""

import argparse
import json
import sys
from pathlib import Path

from wagtail_markdown_agents.data.agents import AGENTS, RETIRED_AGENTS, identify_agent
from wagtail_markdown_agents.data.operators import OPERATOR_NAMES, operator_for_agent

DIFFERENCES = (
    Path(__file__).resolve().parent.parent
    / "src/wagtail_markdown_agents/data/agent-signals-differences.json"
)


def load_differences(path=DIFFERENCES):
    return json.loads(Path(path).read_text())


def compare_list(signals, entries=AGENTS + RETIRED_AGENTS, operator_names=OPERATOR_NAMES):
    """Every way the registry's entries and operators differ from agent-signals' list."""
    problems = []
    if signals["operators"] != operator_names:
        theirs, ours = signals["operators"], operator_names
        for key in sorted(set(theirs) | set(ours)):
            if theirs.get(key) != ours.get(key):
                problems.append(
                    f"operator {key}: ours {ours.get(key)!r}, theirs {theirs.get(key)!r}"
                )
    theirs = {agent["label"]: agent for agent in signals["agents"]}
    ours = {agent.label: agent for agent in entries}
    for label in sorted(set(theirs) - set(ours)):
        problems.append(f"{label}: only in agent-signals")
    for label in sorted(set(ours) - set(theirs)):
        problems.append(f"{label}: only in the registry")
    for label in sorted(set(theirs) & set(ours)):
        signal, agent = theirs[label], ours[label]
        retired = bool(signal.get("retired"))
        fields = {
            "operator": (agent.operator, signals["operators"].get(signal.get("operator"), "")),
            "category": (agent.category, signal["category"]),
            "purposes": (list(agent.purposes), [signal["category"]]),
            "retired": (agent.retired, retired),
            "kind": (agent.kind, signal.get("kind", "")),
            "serve": (agent.auto_markdown, signal["serve_markdown"] and not retired),
        }
        for field, (mine, other) in fields.items():
            if mine != other:
                problems.append(f"{label}: {field} ours {mine!r}, theirs {other!r}")
    return problems


def case_differs(case):
    """Whether this package identifies a case's User-Agent differently from agent-signals.

    Only the User-Agent is compared: this package doesn't read X-Agent or Web Bot
    Auth headers, so a case agent-signals labels by those is one with no listed
    User-Agent, here as there.
    """
    headers = {name.lower(): value for name, value in case["headers"].items()}
    agent = identify_agent(headers.get("user-agent", ""))
    expect = case["expect"]
    if expect["kind"] != "listed":
        return agent is not None
    if agent is None:
        return True
    return (agent.label, agent.category, operator_for_agent(agent.label), agent.auto_markdown) != (
        expect["label"],
        expect["category"],
        expect["operator"] or "unattributed",
        expect["serves_markdown"],
    )


def compare_cases(cases, differences):
    """Cases that differ without being listed, and listed cases that no longer differ."""
    allowed = {name for difference in differences for name in difference.get("cases", ())}
    names = {case["name"] for case in cases}
    problems = [f"listed case not in this cases.json: {name}" for name in sorted(allowed - names)]
    for case in cases:
        differs = case_differs(case)
        if differs and case["name"] not in allowed:
            problems.append(f"case differs and isn't listed: {case['name']}")
        elif not differs and case["name"] in allowed:
            problems.append(f"listed case no longer differs: {case['name']}")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("agents", type=Path, help="agent-signals' data/agents.json")
    parser.add_argument("--cases", type=Path, help="agent-signals' tests/conformance/cases.json")
    parser.add_argument("--differences", type=Path, default=DIFFERENCES, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    signals = json.loads(args.agents.read_text())
    differences = load_differences(args.differences)
    checked = differences["agent_signals"]["revision"]
    problems = []
    if signals["revision"] != checked:
        problems.append(
            f"agents.json is revision {signals['revision']}; the differences file was checked "
            f"against revision {checked}. Review the change, then update the registry, "
            "agent-signals or the differences file."
        )
    problems += compare_list(signals)
    if args.cases:
        problems += compare_cases(json.loads(args.cases.read_text()), differences["differences"])

    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} difference(s) from agent-signals revision {signals['revision']}.")
        return 1
    print(f"No unlisted differences from agent-signals revision {signals['revision']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
