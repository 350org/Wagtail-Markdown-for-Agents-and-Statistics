"""Reviewed identities; recognition and automatic serving are independent.

No network access at import or request time. See docs/agent-registry.md for the
source policy, matching contract, historical labels and update procedure.
"""

import json
import re
from dataclasses import dataclass
from importlib.resources import files

from .legacy_agents import LEGACY_CATEGORIES

INTENT_CATEGORIES = ("on-demand", "search", "training", "mixed", "unknown")
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
        intents = set(self.purposes) & {"on-demand", "search", "training"}
        if len(intents) > 1:
            return "mixed"
        return next(iter(intents), "unknown")


_data = json.loads(files(__package__).joinpath("agent-registry.json").read_text())
REGISTRY_VERSION = _data["version"]
_entries = tuple(
    Agent(**{key: tuple(value) if isinstance(value, list) else value for key, value in row.items()})
    for row in _data["agents"]
)
# Active entries match requests. Retired entries never match or serve; they keep
# their label, purposes and operator so past report rows read as before (#96).
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
    return next((agent for agent, pattern in _MATCHERS if pattern.search(user_agent)), None)


# Registry metadata owns classifications: active entries, then retired ones, then
# the frozen WordPress labels. Retired labels remain readable; they do not return
# to detection or the CDN serving list. Exact-label matching in stats keeps
# historical Applebot-Extended separate from Applebot.
_registry_labels = {agent.label.casefold() for agent in _entries}
AGENT_CATEGORIES = {
    category: tuple(agent.label for agent in _entries if agent.category == category)
    + tuple(
        label
        for label in LEGACY_CATEGORIES.get(category, ())
        if label.casefold() not in _registry_labels
    )
    for category in INTENT_CATEGORIES
}
