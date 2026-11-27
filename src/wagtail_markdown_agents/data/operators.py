"""Operator attribution for stored agent labels, active and retired.

This reporting map never participates in User-Agent detection or Markdown serving.
Keys and names are agent-signals' (#93).
"""

from .agents import AGENTS, RETIRED_AGENTS

# The same keys and names as agent-signals' operators (#93).
OPERATOR_NAMES = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "perplexity": "Perplexity",
    "meta": "Meta",
    "amazon": "Amazon",
    "apple": "Apple",
    "mistral": "Mistral AI",
    "bytedance": "ByteDance",
    "common-crawl": "Common Crawl",
    "cohere": "Cohere",
    "duckduckgo": "DuckDuckGo",
    "brave": "Brave",
    "cloudflare": "Cloudflare",
    "moonshot": "Moonshot AI",
    "huawei": "Huawei",
    "cognition": "Cognition",
    "semrush": "Semrush",
    "atlassian": "Atlassian",
    "microsoft": "Microsoft",
    "linkup": "Linkup",
    "you-com": "You.com",
    "keenable": "Keenable",
    "adp": "ADP",
    "alphalens": "Alphalens",
    "apify": "Apify",
    "awario": "Awario",
    "big-sur-ai": "Big Sur AI",
    "borderx": "BorderX",
    "brandwatch": "Brandwatch",
    "citibot": "Citibot",
    "cledara": "Cledara",
    "direqt": "Direqt",
    "element451": "Element451",
    "hark": "Hark",
    "hifi": "HIFI",
    "instapaper": "Instapaper",
    "it-recht-kanzlei": "IT-Recht Kanzlei",
    "kernel": "Kernel",
    "liner": "Liner",
    "make": "Make",
    "nava": "Nava",
    "navu": "Navu",
    "netestate": "netEstate",
    "nict": "NICT",
    "novellum": "Novellum",
    "oniroco": "Oniroco",
    "parallel": "Parallel Web Systems",
    "qa-tech": "QA.tech",
    "qualified": "Qualified",
    "retool": "Retool",
    "rois-ds": "ROIS-DS",
    "selectika": "Selectika",
    "twin": "Twin",
    "webspark": "WEBSPARK",
    "ygs": "YGS Group",
}

# An entry without an operator (as in agent-signals) is reported as unattributed.
# Its label still claims the exact match, so a substring of another operator's
# label can't attribute it.
_registry = tuple(
    (
        agent.label.casefold(),
        next(key for key, name in OPERATOR_NAMES.items() if name == agent.operator)
        if agent.operator
        else "unattributed",
    )
    for agent in AGENTS + RETIRED_AGENTS
)
OPERATOR_MATCHES = _registry


def operator_for_agent(agent: str) -> str:
    """Classify one stored label; never inspect an arbitrary request User-Agent."""
    if not isinstance(agent, str) or not agent.strip():
        return "unattributed"
    label = agent.strip().casefold()
    for token, key in OPERATOR_MATCHES:
        if token == label:
            return key
    for token, key in OPERATOR_MATCHES:
        if token in label:
            return key
    return "unattributed"
