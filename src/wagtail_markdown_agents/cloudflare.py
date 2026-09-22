"""Generate a host-scoped Cache Rule expression without contacting Cloudflare."""

import argparse
import json
import re

from .data.agents import MARKDOWN_UA_STRINGS


def cache_bypass_expression(
    host: str, *, user_agent=True, query_param=True, include_accept=False
) -> str:
    """Return a conservative superset of enabled Markdown negotiation triggers.

    Contains clauses are deliberately broader than origin parsing. They may send
    extra requests to the origin, but never authorise serving or bypass security.
    Accept header fields require support from the deployment's Cloudflare plan.
    """
    if (
        not isinstance(host, str)
        or len(host) > 253
        or not all(
            re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
            for label in host.split(".")
        )
    ):
        raise ValueError("Supply a DNS hostname without scheme, port, path or wildcard")
    clauses = []
    if query_param:
        # url_decode handles percent-encoded parameter names and values; broad
        # matching also catches the whitespace accepted by origin query parsing.
        clauses.append('lower(url_decode(http.request.uri.query)) contains "output_format"')
    if user_agent:
        clauses.extend(
            f"lower(http.user_agent) contains {json.dumps(token.lower())}"
            for token in sorted(set(MARKDOWN_UA_STRINGS), key=str.lower)
        )
    if include_accept:
        clauses.append('any(lower(http.request.headers["accept"][*])[*] contains "text/markdown")')
    if not clauses:
        raise ValueError("At least one negotiation trigger must be enabled")
    return f"(http.host eq {json.dumps(host.lower())} and ({' or '.join(clauses)}))"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--no-user-agent", action="store_true")
    parser.add_argument("--no-query-param", action="store_true")
    parser.add_argument("--include-accept", action="store_true")
    args = parser.parse_args()
    try:
        expression = cache_bypass_expression(
            args.host,
            user_agent=not args.no_user_agent,
            query_param=not args.no_query_param,
            include_accept=args.include_accept,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(expression)


if __name__ == "__main__":
    main()
