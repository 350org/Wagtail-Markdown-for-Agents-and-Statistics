"""Content-negotiation detection (#25).

Decides whether a request is asking for Markdown, and by which method.
Precedence matches the WordPress plugin: query-param > accept-header > ua.
Each trigger is toggleable through ``NEGOTIATE_QUERY_PARAM``,
``NEGOTIATE_ACCEPT_HEADER`` and ``NEGOTIATE_USER_AGENT``.

Detection never inspects the request path or method: the middleware decides
which requests are candidates for interception. The Accept rule parses media
ranges rather than searching for a substring, so browsers (``text/html,
*/*;q=0.8``) and plain curl (``*/*``) are never served Markdown by accident.
"""

from django.http import HttpRequest
from django.utils.http import parse_header_parameters

from .data.agents import identify_agent
from .settings import get_setting

#: Access-method labels, in precedence order. Stable values — they become
#: statistics dimensions (#32/#33); never rename them.
METHOD_QUERY_PARAM = "query-param"
METHOD_ACCEPT_HEADER = "accept-header"
METHOD_USER_AGENT = "ua"
METHOD_EXPORT_URL = "export-url"

QUERY_PARAM = "output_format"
QUERY_VALUES = frozenset({"md", "markdown"})
MARKDOWN_TYPE = "text/markdown"


def detect(request: HttpRequest) -> str | None:
    """Return the enabled access method that requested Markdown, or ``None``."""
    if get_setting("NEGOTIATE_QUERY_PARAM") and query_requests_markdown(request):
        return METHOD_QUERY_PARAM
    if get_setting("NEGOTIATE_ACCEPT_HEADER") and accepts_markdown(
        request.headers.get("Accept", "")
    ):
        return METHOD_ACCEPT_HEADER
    if get_setting("NEGOTIATE_USER_AGENT"):
        agent = identify_agent(request.headers.get("User-Agent", ""))
        if agent is not None and agent.auto_markdown:
            return METHOD_USER_AGENT
    return None


def query_requests_markdown(request: HttpRequest) -> bool:
    """``?output_format=md`` or ``markdown``; case-insensitive like WP's sanitize_key."""
    value = request.GET.get(QUERY_PARAM)
    return isinstance(value, str) and value.strip().lower() in QUERY_VALUES


def accepts_markdown(accept: str) -> bool:
    """Whether ``text/markdown`` appears as an explicit media range with q > 0.

    ``text/*`` and ``*/*`` never match. A range with ``q=0`` is an exclusion. An
    unparsable q-value keeps the range (the client still asked explicitly). A
    malformed header never raises; unrecognisable ranges are ignored.
    """
    if not isinstance(accept, str) or not accept:
        return False
    for media_range in _media_ranges(accept):
        try:
            media_type, parameters = parse_header_parameters(media_range)
        except (LookupError, UnicodeError, ValueError):
            continue
        if media_type.strip().lower() != MARKDOWN_TYPE:
            continue
        if _quality(parameters.get("q")) > 0:
            return True
    return False


def _media_ranges(accept: str):
    """Yield comma-separated ranges without splitting inside quoted parameters."""
    start = 0
    quoted = escaped = False
    for index, char in enumerate(accept):
        if escaped:
            escaped = False
        elif quoted and char == "\\":
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif char == "," and not quoted:
            yield accept[start:index]
            start = index + 1
    yield accept[start:]


def _quality(value: str | None) -> float:
    if value is None:
        return 1.0
    try:
        return float(value.strip())
    except ValueError:
        return 1.0


def detect_agent(user_agent: str) -> str | None:
    """Return a reviewed canonical label, independently of automatic serving."""
    agent = identify_agent(user_agent)
    return agent.label if agent is not None else None
