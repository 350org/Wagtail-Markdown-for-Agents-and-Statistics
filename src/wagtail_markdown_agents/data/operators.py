"""Reviewed operator attribution for stored agent labels, including retired labels.

This reporting map never participates in User-Agent detection or Markdown serving.
Keep historical entries so old counters retain their attribution.
"""

from .agents import AGENTS

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
}

# Historical labels from the reviewed WordPress map. Active registry labels take
# precedence, so a future registry correction also updates historical reporting.
HISTORICAL_OPERATOR_LABELS = {
    "openai": ("ChatGPT-User", "OAI-SearchBot", "GPTBot"),
    "anthropic": ("Claude-User", "Claude-Web", "Claude-SearchBot", "ClaudeBot", "anthropic-ai"),
    "google": ("Gemini-User", "Google-Agent", "Google-Extended", "GoogleOther", "CloudVertexBot"),
    "perplexity": ("Perplexity-User", "PerplexityBot"),
    "meta": ("meta-externalfetcher", "meta-externalagent"),
    "amazon": ("Amzn-SearchBot", "Amazonbot", "amazon-kendra-"),
    "apple": ("Applebot-Extended",),
    "mistral": ("MistralAI-User",),
    "bytedance": ("Bytespider",),
    "common-crawl": ("CCBot",),
    "cohere": ("cohere-ai",),
    "duckduckgo": ("DuckAssistBot",),
    "brave": ("Bravebot",),
    "cloudflare": ("Cloudflare-AI-Search", "CloudflareBrowserRenderingCrawler"),
    "moonshot": ("KimiBot",),
    "huawei": ("PetalBot",),
    "cognition": ("Devin",),
    "semrush": ("SemrushBot-OCOB", "SemrushBot-SWA"),
    "atlassian": ("atlassian-bot",),
}

_active = tuple(
    (
        agent.label.casefold(),
        next(key for key, name in OPERATOR_NAMES.items() if name == agent.operator),
    )
    for agent in AGENTS
)
_active_labels = {label for label, _ in _active}
_historical = tuple(
    (label.casefold(), key)
    for key, labels in HISTORICAL_OPERATOR_LABELS.items()
    for label in labels
    if label.casefold() not in _active_labels
)
OPERATOR_MATCHES = _active + _historical


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
