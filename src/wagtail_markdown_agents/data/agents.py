"""Reviewed identities; recognition and automatic serving are independent.

The registry holds exactly the entries of agent-signals (active and retired), with
their labels, operators, categories, kinds and serving, plus local tokens, sources
and notes (#93). No network access at import or request time. See
docs/agent-registry.md for the source policy, matching contract and update procedure.
"""

import json
import re
from dataclasses import dataclass
from importlib.resources import files

# agent-signals' categories. Each entry has exactly one, as its only purpose (#93).
INTENT_CATEGORIES = ("on-demand", "search", "training", "unknown")
# agent-signals cuts every header to 2,048 bytes before matching, so that no pattern
# runs over unbounded input. WSGI hands headers over decoded as latin-1, one
# character per byte, so the cut is by character.
HEADER_LIMIT = 2048
# agent: fetches content for AI answers, search or training. browser: acts on the
# page for a person. reference: a search engine whose index feeds AI answers.
# browser and reference are never served Markdown on the User-Agent (#96).
KINDS = ("agent", "browser", "reference")


@dataclass(frozen=True)
class Agent:
    label: str
    operator: str
    tokens: tuple[str, ...]
    purposes: tuple[str, ...]
    auto_markdown: bool
    sources: tuple[str, ...]
    reviewed: str
    notes: str
    kind: str = ""  # Set on every active entry; a retired entry has none.
    retired: bool = False

    @property
    def category(self) -> str:
        return self.purposes[0]


_data = json.loads(files(__package__).joinpath("agent-registry.json").read_text())
REGISTRY_VERSION = _data["version"]
_entries = tuple(
    Agent(**{key: tuple(value) if isinstance(value, list) else value for key, value in row.items()})
    for row in _data["agents"]
)
# Active entries match requests. Retired entries never match or serve; their label
# keeps its purpose and operator, so past report rows still read (#96).
AGENTS = tuple(agent for agent in _entries if not agent.retired)
RETIRED_AGENTS = tuple(agent for agent in _entries if agent.retired)
AGENT_UA_STRINGS = tuple(token for agent in AGENTS for token in agent.tokens)
MARKDOWN_UA_STRINGS = tuple(
    token for agent in AGENTS if agent.auto_markdown for token in agent.tokens
)

# Match product tokens, not incidental URL fragments or longer product names.
# A version may follow a slash; bare tokens are accepted too. Registry order
# breaks ties when a header claims several identities, for both serving and stats.
_MATCHERS = tuple(
    (
        agent,
        re.compile(
            r"(?:^|[\s;(])(?:" + "|".join(map(re.escape, agent.tokens)) + r")(?=/|[\s;)]|$)",
            re.IGNORECASE | re.ASCII,
        ),
    )
    for agent in AGENTS
)


def identify_agent(user_agent: str) -> Agent | None:
    """Recognise a claimed identity; this does not authenticate the client."""
    if not isinstance(user_agent, str) or not user_agent:
        return None
    user_agent = user_agent[:HEADER_LIMIT]
    return next((agent for agent, pattern in _MATCHERS if pattern.search(user_agent)), None)


# Every registry label, active or retired, by category. Retired labels stay
# readable without returning to detection or the CDN serving list. Exact-label
# matching in stats keeps Applebot-Extended separate from Applebot.
AGENT_CATEGORIES = {
    category: tuple(agent.label for agent in _entries if agent.category == category)
    for category in INTENT_CATEGORIES
}
