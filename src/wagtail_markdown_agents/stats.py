"""One atomic daily increment per selected page Markdown GET (#32/#33).

The shared serving signal records Markdown hits. The middleware's response
phase also records HTML page reads by registry agents (#61, ``COUNT_HTML``);
other clients' HTML is never counted. No full User-Agent, IP address, request
URL or intent category is persisted. Recording is best effort: failures are
logged and the response is still returned.
"""

import logging
import time
from contextlib import nullcontext
from datetime import UTC, datetime

from django.db import NotSupportedError, OperationalError, connections, router, transaction
from wagtail import hooks

from .data.agents import AGENT_CATEGORIES, INTENT_CATEGORIES, identify_agent
from .models import AgentAccess
from .negotiation import (
    METHOD_ACCEPT_HEADER,
    METHOD_EXPORT_URL,
    METHOD_HTML,
    METHOD_QUERY_PARAM,
    METHOD_USER_AGENT,
    detect_agent,
)
from .routing import routed_page
from .settings import get_setting
from .signals import markdown_served

logger = logging.getLogger(__name__)

MARKDOWN_METHODS = frozenset(
    {METHOD_QUERY_PARAM, METHOD_ACCEPT_HEADER, METHOD_USER_AGENT, METHOD_EXPORT_URL}
)
ACCESS_METHODS = MARKDOWN_METHODS | {METHOD_HTML}


def get_agent_categories() -> dict[str, list[str]]:
    """Build a fresh ordered map; hooks mutate it in Wagtail hook order.

    Return values are ignored. Hook exceptions propagate to the report caller.
    Neither the shipped map nor subsequent reads are changed by hook mutations.
    """
    categories = {category: list(labels) for category, labels in AGENT_CATEGORIES.items()}
    for hook in hooks.get_hooks("construct_markdown_agent_categories"):
        hook(categories)
    return categories


def categorise_agent(agent: str, *, categories=None) -> str:
    """Derive intent from a stored label, without querying or updating counters.

    Exact canonical labels win before compatibility substring matching for hooks.
    Within each pass, category order wins. An unexpected category still
    wins its match, but is returned as ``unknown`` for the fixed reporting keys.
    Pass a map from ``get_agent_categories`` to share one hook snapshot across
    an entire report. Omission builds a fresh map, preserving standalone usage.
    """
    if not isinstance(agent, str) or not agent.strip():
        return "unknown"
    label = agent.strip().lower()
    if categories is None:
        categories = get_agent_categories()
    for category, substrings in categories.items():
        if any(substring and substring.lower() == label for substring in substrings):
            return category if category in INTENT_CATEGORIES else "unknown"
    for category, substrings in categories.items():
        if any(substring and substring.lower() in label for substring in substrings):
            return category if category in INTENT_CATEGORIES else "unknown"
    return "unknown"


def agent_label(user_agent: str) -> str:
    """Return a canonical dataset label or the shared unknown bucket.

    Never persist arbitrary header fragments: they can contain personal data and
    allow a caller to create a new statistics dimension on every request.
    """
    if not isinstance(user_agent, str):
        return ""
    known = detect_agent(user_agent)
    if known:
        return known.strip()[:100]
    return ""


def record_access(*, page_id, user_agent="", access_method, at=None, using=None):
    """Insert one hit or add one to a daily counter in a single SQL statement.

    ``at`` may be an aware datetime; defaults to the current UTC instant even
    when Django's USE_TZ is false. ``using`` otherwise follows the write router.
    Failures propagate to the serving signal's best-effort error handling.
    """
    if access_method not in ACCESS_METHODS:
        raise ValueError(f"Unknown access method: {access_method!r}")
    if not isinstance(page_id, int) or isinstance(page_id, bool) or page_id <= 0:
        raise ValueError("Statistics require a positive page identifier")
    at = datetime.now(UTC) if at is None else at
    if at.utcoffset() is None:
        raise ValueError("Statistics require an aware datetime")
    label = agent_label(user_agent)
    if access_method == METHOD_HTML and not label:
        # The scope line of #61: HTML counts never become visitor analytics.
        raise ValueError("HTML reads are counted for registry agents only")
    alias = using or router.db_for_write(AgentAccess)
    connection = connections[alias]
    date_field = AgentAccess._meta.get_field("access_date")
    values = [
        page_id,
        label,
        access_method,
        date_field.get_db_prep_save(at.astimezone(UTC).date(), connection),
        1,
    ]
    sql = _upsert_sql(connection)
    deadline = time.monotonic() + 1
    while True:
        try:
            # Isolate a failed write when direct serving runs under ATOMIC_REQUESTS
            # or a caller transaction; the normal autocommit path is just one query.
            guard = transaction.atomic(using=alias) if connection.in_atomic_block else nullcontext()
            with guard, connection.cursor() as cursor:
                cursor.execute(sql, values)
            return
        except OperationalError as exc:
            # SQLite shared-cache contention can fail immediately instead of
            # honouring busy_timeout. Retry only the rolled-back statement and
            # never wait while retaining an enclosing transaction's locks.
            if (
                connection.vendor != "sqlite"
                or "locked" not in str(exc).lower()
                or connection.in_atomic_block
                or time.monotonic() >= deadline
            ):
                raise
            time.sleep(0.01)


def _upsert_sql(connection):
    quote = connection.ops.quote_name
    table = quote(AgentAccess._meta.db_table)
    dimensions = ", ".join(
        quote(AgentAccess._meta.get_field(name).column)
        for name in ("page_id", "agent", "access_method", "access_date")
    )
    count = quote("count")
    insert = f"INSERT INTO {table} ({dimensions}, {count}) VALUES (%s, %s, %s, %s, %s)"
    if connection.vendor in {"postgresql", "sqlite"}:
        return f"{insert} ON CONFLICT ({dimensions}) DO UPDATE SET {count} = {table}.{count} + 1"
    if connection.vendor == "mysql":
        return f"{insert} ON DUPLICATE KEY UPDATE {count} = {count} + 1"
    raise NotSupportedError(f"Agent statistics do not support {connection.vendor!r}")


def _record_served(sender, *, request, page_id, access_method, **kwargs):
    if request.method != "GET" or getattr(request, "is_preview", False) or page_id is None:
        return
    record_access(
        page_id=page_id,
        user_agent=request.headers.get("User-Agent", ""),
        access_method=access_method,
    )


def counts_html(user_agent: str) -> bool:
    """Whether an HTML page read with this User-Agent is counted (#61).

    Only registry agents, while ``COUNT_HTML`` is on, and not left out by
    ``COUNT_HTML_EXCLUDE`` (agent labels or purposes, case-insensitive).
    """
    if not get_setting("COUNT_HTML"):
        return False
    agent = identify_agent(user_agent)
    if agent is None:
        return False
    excluded = {name.casefold() for name in get_setting("COUNT_HTML_EXCLUDE")}
    if not excluded:
        return True
    return agent.label.casefold() not in excluded and categorise_agent(agent.label) not in excluded


def record_html_read(request, response) -> None:
    """Response phase: count a registry agent's successful HTML page GET (#61).

    Same page-read rules as discovery (canonical Wagtail page route on an
    enabled site, outside previews), but GET only. Never raises: a failure is
    logged and the HTML response is returned unchanged.
    """
    try:
        if request.method != "GET" or getattr(request, "is_preview", False):
            return
        if response.status_code != 200 or getattr(response, "streaming", False):
            return
        if not response.get("Content-Type", "").lower().startswith("text/html"):
            return
        user_agent = request.headers.get("User-Agent", "")
        if not counts_html(user_agent):
            return
        routed = routed_page(request)
        if routed is None:
            return
        record_access(page_id=routed[1].pk, user_agent=user_agent, access_method=METHOD_HTML)
    except Exception:
        logger.exception("HTML page served, but its agent read was not recorded")


def connect():
    markdown_served.connect(_record_served, dispatch_uid="agentmd.record_access")
