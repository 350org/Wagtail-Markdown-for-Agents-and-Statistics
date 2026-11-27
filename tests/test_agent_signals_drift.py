"""The registry stays in step with agent-signals: one deliberate difference (#93)."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from wagtail_markdown_agents.data.agents import AGENTS, RETIRED_AGENTS
from wagtail_markdown_agents.data.operators import OPERATOR_NAMES

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("drift", ROOT / "scripts" / "agent_signals_drift.py")
drift = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drift)

PINNED = json.loads((ROOT / "tests/fixtures/agent-signals-conformance-cases.json").read_text())
DIFFERENCES = drift.load_differences()


def as_agent_signals():
    """The registry written in agent-signals' shape, as its agents.json would hold it."""
    keys = {name: key for key, name in OPERATOR_NAMES.items()}
    agents = []
    for agent in AGENTS + RETIRED_AGENTS:
        entry = {"label": agent.label, "category": agent.category}
        if agent.kind:
            entry["kind"] = agent.kind
        if agent.operator:
            entry["operator"] = keys[agent.operator]
        entry["serve_markdown"] = agent.auto_markdown
        if agent.retired:
            entry["retired"] = True
        agents.append(entry)
    return {
        "revision": DIFFERENCES["agent_signals"]["revision"],
        "operators": dict(OPERATOR_NAMES),
        "agents": agents,
    }


def test_matching_is_the_only_difference():
    assert [d["field"] for d in DIFFERENCES["differences"]] == ["matching"]
    assert PINNED["revision"] == DIFFERENCES["agent_signals"]["revision"]
    assert PINNED["release"] == DIFFERENCES["agent_signals"]["release"]


def test_pinned_conformance_cases_give_the_same_identity_except_listed_ones():
    assert len(PINNED["cases"]) == 169
    assert drift.compare_cases(PINNED["cases"], DIFFERENCES["differences"]) == []
    listed = {name for d in DIFFERENCES["differences"] for name in d["cases"]}
    for case in PINNED["cases"]:
        assert drift.case_differs(case) is (case["name"] in listed), case["name"]


def test_a_new_case_difference_or_a_stale_listing_is_reported():
    cases = copy.deepcopy(PINNED["cases"])
    cases.append(
        {
            "name": "made up: a name inside a URL",
            "headers": {"User-Agent": "Tool/1.0 (+https://example.com/gptbot)"},
            "expect": {
                "kind": "listed",
                "label": "GPTBot",
                "category": "training",
                "operator": "openai",
                "serves_markdown": True,
            },
        }
    )
    assert drift.compare_cases(cases, DIFFERENCES["differences"]) == [
        "case differs and isn't listed: made up: a name inside a URL"
    ]
    stale = [{**DIFFERENCES["differences"][0], "cases": ["list: GPTBot"]}]
    problems = drift.compare_cases(PINNED["cases"], stale)
    assert "listed case no longer differs: list: GPTBot" in problems
    assert "case differs and isn't listed: the match is a substring, not a token" in problems


def test_the_registry_in_agent_signals_shape_has_no_differences():
    assert drift.compare_list(as_agent_signals()) == []


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (
            lambda s: s["agents"][0].update(category="search"),
            "GPTBot: category ours 'training', theirs 'search'",
        ),
        (
            lambda s: s["agents"][0].update(serve_markdown=False),
            "GPTBot: serve ours True, theirs False",
        ),
        (
            lambda s: s["agents"][0].update(operator="anthropic"),
            "GPTBot: operator ours 'OpenAI', theirs 'Anthropic'",
        ),
        (
            lambda s: s["agents"].append(
                {"label": "NewBot", "category": "search", "serve_markdown": False}
            ),
            "NewBot: only in agent-signals",
        ),
        (lambda s: s["agents"].pop(0), "GPTBot: only in the registry"),
        (lambda s: s["operators"].update(xai="xAI"), "operator xai: ours None, theirs 'xAI'"),
    ],
)
def test_any_entry_or_operator_difference_is_reported(change, problem):
    signals = as_agent_signals()
    change(signals)
    assert problem in drift.compare_list(signals)


def test_a_retired_entry_marked_served_upstream_is_not_a_difference():
    # agent-signals before revision 6 kept serve_markdown true on retired entries.
    signals = as_agent_signals()
    next(a for a in signals["agents"] if a["label"] == "Claude-Web")["serve_markdown"] = True
    assert drift.compare_list(signals) == []


def test_another_revision_fails_until_the_differences_file_is_updated(tmp_path, capsys):
    signals = as_agent_signals()
    path = tmp_path / "agents.json"
    path.write_text(json.dumps(signals))
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps(PINNED["cases"]))
    assert drift.main([str(path), "--cases", str(cases)]) == 0
    signals["revision"] += 1
    path.write_text(json.dumps(signals))
    assert drift.main([str(path)]) == 1
    assert "the differences file was checked against revision" in capsys.readouterr().out
