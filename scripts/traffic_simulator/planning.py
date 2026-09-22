"""Deterministic traffic plans from the public manifest and explicit fixtures."""

import hashlib
import math
import random
from dataclasses import asdict, dataclass
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

import yaml
from markdown_it import MarkdownIt

from wagtail_markdown_agents.data.agents import AGENT_CATEGORIES, AGENTS, identify_agent

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
UNLISTED_UA = "MarkdownVerification/1.0"
OPENAI_SOURCE = "https://developers.openai.com/api/docs/bots"
ANTHROPIC_SOURCE = (
    "https://privacy.claude.com/en/articles/"
    "8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler"
)
REQUIRED_FIXTURES = (
    "fallback",
    "excluded",
    "preview",
    "missing-export",
    "private-export",
    "navigation-index",
)
METHODS = ("accept-header", "query-param", "ua", "export-url")


def label(ua):
    agent = identify_agent(ua)
    return agent.label if agent is not None else ""


def category(agent):
    for kind, entries in AGENT_CATEGORIES.items():
        if any(entry.lower() == agent.lower() for entry in entries):
            return kind
    return next(
        (
            kind
            for kind, entries in AGENT_CATEGORIES.items()
            if any(entry.lower() in agent.lower() for entry in entries)
        ),
        "unknown",
    )


def fleet():
    """Only OpenAI publishes full examples here; other full headers are synthetic.

    Sources checked 2026-09-22. Even an official example sent by this tool is
    simulated traffic. Only reviewed HTTP identities enter the fleet.
    """
    prefix = "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; "
    official = {
        "GPTBot": prefix + "GPTBot/1.4; +https://openai.com/gptbot",
        "ChatGPT-User": prefix + "ChatGPT-User/1.0; +https://openai.com/bot",
        "OAI-SearchBot": BROWSER_UA
        + "; compatible; OAI-SearchBot/1.4; +https://openai.com/searchbot",
    }
    representatives = (*official, "ClaudeBot", "Claude-User", "Claude-SearchBot")
    result = []
    for identity in sorted(AGENTS, key=lambda a: (a.label not in representatives,)):
        token = identity.label
        provenance = "dataset-synthetic"
        source = identity.sources[0]
        ua = f"Mozilla/5.0 (compatible; {identity.tokens[0]}/1.0)"
        if token in official:
            ua, provenance, source = official[token], "official-example", OPENAI_SOURCE
        elif token in representatives:
            ua = prefix + token + "/1.0"
            provenance, source = "synthetic-shape", ANTHROPIC_SOURCE
        result.append(
            {
                "agent": token,
                "ua": ua,
                "category": category(token),
                "provenance": provenance,
                "source": source,
                "traffic": "simulated",
                "auto_markdown": identity.auto_markdown,
            }
        )
    return result


def safe_url(value, target):
    """Keep evidence free of credentials and all traffic on the configured origin."""
    if not isinstance(value, str) or any(ord(char) < 32 for char in value):
        raise ValueError("URLs must be strings without control characters")
    parts = urlsplit(urljoin(target + "/", value))
    base = urlsplit(target)
    if (
        parts.scheme not in {"https", "http"}
        or parts.username
        or parts.password
        or (parts.scheme, parts.hostname, parts.port) != (base.scheme, base.hostname, base.port)
    ):
        raise ValueError("All URLs must use the configured HTTP(S) origin, without credentials")
    if any(
        key not in {"output_format", "preview"}
        or (key == "preview" and value not in {"1", "true", "false"})
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
    ):
        raise ValueError("Use public fixture URLs without private or unrecognised query parameters")
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~"),
            parts.query,
            "",
        )
    )


def target_origin(value):
    parts = urlsplit(value)
    if (
        not parts.hostname
        or parts.path not in {"", "/"}
        or parts.query
        or parts.fragment
        or parts.scheme not in {"http", "https"}
        or parts.username
        or parts.password
    ):
        raise ValueError("Target must be an HTTP(S) origin, without a path or credentials")
    return safe_url(value, value).rstrip("/")


def query_url(url):
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "output_format"]
    return urlunsplit(parts._replace(query=urlencode([*query, ("output_format", "md")])))


@dataclass(frozen=True)
class RequestSpec:
    url: str
    page_id: int | None = None
    ua: str = UNLISTED_UA
    method: str = "GET"
    access_method: str = "export-url"
    expected_status: int = 200
    expected_type: str = "text/markdown"
    countable: bool = True
    full_hash: str = ""
    scenario: str = "page"
    ordering: str = ""
    group: str = ""
    provenance: str = "synthetic-shape"
    delay: float = 1.0

    @property
    def accept(self):
        return "text/markdown" if self.access_method == "accept-header" else "text/html,*/*;q=0.8"

    def as_dict(self):
        return dict(
            asdict(self),
            agent=label(self.ua),
            category=category(label(self.ua)),
            traffic="simulated",
        )

    @classmethod
    def from_dict(cls, data):
        return cls(**{key: value for key, value in data.items() if key in cls.__dataclass_fields__})


def discover(manifest, target, fetch, overrides=None):
    if manifest.get("schema_version") != "0.1" or not isinstance(manifest.get("documents"), list):
        raise ValueError("Expected a v0.1 public manifest")
    overrides = overrides or {}
    pages, seen = [], set()
    for document in manifest["documents"]:
        page_id = document["id"]
        if type(page_id) is not int or page_id <= 0 or page_id in seen:
            raise ValueError("Manifest page IDs must be unique positive integers")
        seen.add(page_id)
        export_url = safe_url(document["url"], target)
        canonical = overrides.get(str(page_id))
        links = []
        if canonical is None:
            body = fetch(
                RequestSpec(
                    export_url,
                    page_id=page_id,
                    full_hash=document.get("full_hash", ""),
                    scenario="discovery",
                )
            )
            lines = body.decode("utf-8").splitlines()
            if not lines or lines[0] != "---" or "---" not in lines[1:]:
                raise ValueError("Export has no frontmatter; supply a canonical URL override")
            end = lines.index("---", 1)
            try:
                metadata = yaml.safe_load("\n".join(lines[1:end]))
            except yaml.YAMLError:
                raise ValueError("Export frontmatter is not valid YAML") from None
            canonical = metadata.get("permalink") if isinstance(metadata, dict) else None
            if not canonical:
                raise ValueError("Export has no permalink; supply a canonical URL override")
            for block in MarkdownIt().parse("\n".join(lines[end + 1 :])):
                for token in block.children or []:
                    if token.type == "link_open":
                        links.append(urljoin(export_url, token.attrGet("href")))
        pages.append(
            {
                "id": page_id,
                "url": safe_url(canonical, target),
                "export_url": export_url,
                "full_hash": document.get("full_hash", ""),
                "links": links,
            }
        )
    if not pages:
        raise ValueError("The manifest contains no page documents")
    if len({p["url"] for p in pages}) != len(pages):
        raise ValueError("Canonical URLs must identify distinct pages")
    return sorted(pages, key=lambda page: page["id"])


def positive(value, name):
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def build_plan(
    pages,
    target,
    *,
    fixtures=(),
    seed=59,
    max_requests=1000,
    duration=3600,
    rate=1,
    cache_profile="strict",
    manifest_url=None,
):
    target = target_origin(target)
    for value, name in ((max_requests, "max_requests"), (duration, "duration"), (rate, "rate")):
        positive(value, name)
    if cache_profile not in {"strict", "cloudflare-free"}:
        raise ValueError("Unknown cache profile")
    if not pages:
        raise ValueError("At least one manifested page is required")
    rng = random.Random(seed)
    pages = list(pages)
    rng.shuffle(pages)
    agents = fleet()
    suite = []

    def page_request(page, agent, trigger, **extra):
        url = page["export_url"] if trigger == "export-url" else page["url"]
        if trigger == "query-param":
            url = query_url(url)
        full_hash = page.get("full_hash", "")
        if trigger == "ua" and not agent.get("auto_markdown", True):
            extra.update(expected_type="text/html", countable=False)
            full_hash = ""  # The manifest hash describes Markdown, not the HTML control.
        return RequestSpec(
            safe_url(url, target),
            page_id=page["id"],
            ua=agent["ua"],
            access_method=trigger,
            full_hash=full_hash,
            provenance=agent["provenance"],
            **extra,
        )

    # Intersperse pages and representatives; keep each cache sequence contiguous.
    for page in pages:
        for method in METHODS:
            agent = agents[(pages.index(page) + METHODS.index(method)) % 6]
            for ordering in ("agent-first", "html-first"):
                group = f"{page['id']}:{method}:{ordering}"
                browser = RequestSpec(
                    page["url"],
                    page_id=page["id"],
                    ua=BROWSER_UA,
                    access_method="browser",
                    expected_type="text/html",
                    countable=False,
                    ordering=ordering,
                    group=group,
                )
                agent_request = page_request(page, agent, method, ordering=ordering, group=group)
                suite.extend(
                    [agent_request, browser]
                    if ordering == "agent-first"
                    else [browser, browser, agent_request]
                )
        # An independent Accept-only client reveals the free-plan blind spot.
        for ordering in ("agent-first", "html-first"):
            group = f"{page['id']}:unlisted-accept:{ordering}"
            browser = RequestSpec(
                page["url"],
                page_id=page["id"],
                ua=BROWSER_UA,
                access_method="browser",
                expected_type="text/html",
                countable=False,
                ordering=ordering,
                group=group,
            )
            probe = page_request(
                page,
                {"ua": UNLISTED_UA, "provenance": "synthetic-shape"},
                "accept-header",
                scenario="unlisted-accept",
                ordering=ordering,
                group=group,
            )
            suite.extend(
                [probe, browser] if ordering == "agent-first" else [browser, browser, probe]
            )
        for method in METHODS:
            suite.append(
                page_request(
                    page, agents[0], method, method="HEAD", countable=False, scenario="head"
                )
            )
    manifest_url = safe_url(manifest_url or "/markdown/manifest.json", target)
    for url, content_type in (
        (manifest_url, "application/json"),
        (urljoin(manifest_url, "llms.txt"), "text/plain"),
    ):
        for method in ("GET", "HEAD"):
            suite.append(
                RequestSpec(
                    url,
                    method=method,
                    expected_type=content_type,
                    countable=False,
                    scenario="aggregate",
                )
            )
    fixture_kinds = set()
    for fixture in fixtures:
        kind = fixture["kind"]
        if kind not in REQUIRED_FIXTURES:
            raise ValueError(f"Unknown fixture kind: {kind}")
        fixture_kinds.add(kind)
        page_id = fixture.get("page_id")
        if kind == "navigation-index" and any(
            p["export_url"] == safe_url(fixture["url"], target) for p in pages
        ):
            raise ValueError("A manifested index belongs to a page, not a navigation-only fixture")
        for method in ("GET", "HEAD"):
            suite.append(
                RequestSpec(
                    safe_url(fixture["url"], target),
                    page_id=page_id,
                    ua=agents[0]["ua"],
                    method=method,
                    access_method=fixture.get("access_method", "ua"),
                    expected_status=fixture["status"],
                    expected_type=fixture["content_type"],
                    countable=False,
                    scenario=kind,
                )
            )
    by_export = {p["export_url"]: p for p in pages}
    for source in pages:
        for link in dict.fromkeys(source.get("links", [])):
            link = link.split("#", 1)[0]
            if link in by_export:
                suite.append(
                    page_request(by_export[link], agents[1], "export-url", scenario="follow-link")
                )
    # All active identities receive all triggers, including recognition-only HTML controls.
    for index, agent in enumerate(agents):
        for method in METHODS:
            suite.append(page_request(pages[index % len(pages)], agent, method, scenario="fleet"))
    required_count = len(suite)
    requests = suite[:max_requests]
    # Training comes in bounded bursts; search and on-demand are more sporadic.
    while len(requests) < max_requests:
        intent = rng.choices(["training", "search", "on-demand", "browser"], [4, 3, 2, 1])[0]
        page = rng.choice(pages)
        if intent == "browser":
            requests.append(
                RequestSpec(
                    page["url"],
                    page_id=page["id"],
                    ua=BROWSER_UA,
                    access_method="browser",
                    expected_type="text/html",
                    countable=False,
                    scenario="mixed",
                )
            )
            continue
        agent = rng.choice([agent for agent in agents if agent["category"] == intent])
        for _ in range(3 if intent == "training" else 1):
            if len(requests) == max_requests:
                break
            requests.append(
                page_request(
                    rng.choice(pages),
                    agent,
                    rng.choice(METHODS),
                    scenario="mixed",
                    delay=1 if intent == "training" else rng.uniform(2, 5),
                )
            )
    return {
        "schema_version": 1,
        "target": target,
        "seed": seed,
        "max_requests": max_requests,
        "duration": duration,
        "rate": rate,
        "cache_profile": cache_profile,
        "requests": [request.as_dict() for request in requests],
        "coverage": {
            "suite_complete": max_requests >= required_count,
            "suite_requests": required_count,
            "missing_fixtures": sorted(set(REQUIRED_FIXTURES) - fixture_kinds),
            "followed_links": sum(r.scenario == "follow-link" for r in requests),
            "dataset_labels": sorted({label(r.ua) for r in requests if r.scenario == "fleet"}),
        },
    }


def assess(spec, status, headers, body, *, cache_profile="strict"):
    content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if spec.access_method == "browser" and content_type == "text/markdown":
        return {"outcome": "cache-poisoning", "reason": "Browser received Markdown"}
    if (
        cache_profile == "cloudflare-free"
        and spec.expected_type == "text/markdown"
        and spec.access_method == "accept-header"
        and not (identify_agent(spec.ua) and identify_agent(spec.ua).auto_markdown)
        and status == 200
        and content_type == "text/html"
        and headers.get("cf-cache-status", "").upper() == "HIT"
    ):
        return {
            "outcome": "known-limitation",
            "reason": "Warm Accept-only request received cached HTML",
        }
    if status != spec.expected_status or content_type != spec.expected_type:
        return {"outcome": "failure", "reason": "Unexpected HTTP status or content type"}
    if (
        spec.method != "HEAD"
        and spec.full_hash
        and hashlib.sha256(body).hexdigest() != spec.full_hash
    ):
        return {"outcome": "failure", "reason": "Response differs from discovered manifest hash"}
    return {"outcome": "pass", "reason": "Expected representation received"}
