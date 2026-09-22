"""Join client evidence, verified nginx correlation fields and UTC counter deltas."""

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

from wagtail_markdown_agents.negotiation import accepts_markdown, detect_agent

from .planning import METHODS, label
from .transport import CACHE_HITS, CACHE_REVALIDATIONS


def timestamp(value):
    at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if at.utcoffset() is None:
        raise ValueError("Evidence timestamps must include a UTC offset")
    return at.astimezone(UTC)


def read_jsonl(path):
    rows, warnings = [], []
    with open(path, encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("Expected an object")
                rows.append(row)
            except ValueError:
                warnings.append(f"Invalid or truncated JSONL record at line {number}")
    return rows, warnings


def snapshot(data):
    captured = timestamp(data["captured_at"])
    result = {}
    for row in data["rows"]:
        key = (row["access_date"], row["page_id"], row["agent"], row["access_method"])
        datetime.strptime(key[0], "%Y-%m-%d")
        if (
            key in result
            or type(row["count"]) is not int
            or row["count"] < 0
            or type(key[1]) is not int
            or key[1] <= 0
        ):
            raise ValueError("Snapshot rows must have unique dimensions and non-negative counts")
        result[key] = row["count"]
    return captured, result


def uri(url):
    parts = urlsplit(url)
    return parts.path + ("?" + parts.query if parts.query else "")


def content_type(value):
    return value.split(";", 1)[0].strip().lower()


def origin_interval(row):
    end = timestamp(row["timestamp"])
    duration = float(row["request_time"])
    if not 0 <= duration <= 86400:
        raise ValueError("Invalid nginx request_time")
    return end - timedelta(seconds=duration), end


def origin_kind(row):
    if row["method"] != "GET":
        return "excluded"
    if int(row["status"]) == 499 or int(row["status"]) >= 500:
        return "uncertain"  # A disconnect/streaming failure can follow selection.
    if row.get("upstream_cache_status", "").upper() in CACHE_REVALIDATIONS:
        return "uncertain"  # Revalidation may have consulted the application.
    if int(row["status"]) != 200:
        return "excluded"
    if content_type(row["content_type"]) != "text/markdown":
        return "excluded"
    if row.get("upstream_cache_status", "").upper() in CACHE_HITS:
        return "origin_cache_hits"
    if row.get("upstream_status") in {"", "-"}:
        return "static_bypasses"
    if str(row.get("upstream_status")) != "200":
        return "uncertain"  # Multiple upstream attempts cannot imply one selection.
    return "selected"


def reconcile(log, origins, before, after, *, tolerance=0, input_warnings=()):
    if type(tolerance) is not int or tolerance < 0:
        raise ValueError("Tolerance must be a non-negative count per bucket")
    start, baseline = snapshot(before)
    end, final = snapshot(after)
    if end <= start:
        raise ValueError("The after snapshot must be later than the before snapshot")
    warnings = list(input_warnings)
    counts = Counter()
    expected, possible, background, vendor = Counter(), Counter(), Counter(), Counter()
    attempts, responses, terminals = {}, {}, set()
    duplicates = set()
    run_starts, run_ends = set(), set()
    for row in log:
        event = row.get("event")
        identity = (row.get("run_id"), row.get("request_id"))
        if event == "run-start":
            run_starts.add(row["run_id"])
            coverage = row.get("coverage")
            if coverage and (
                not coverage.get("suite_complete") or coverage.get("missing_fixtures")
            ):
                warnings.append(
                    "Plan has incomplete scenario coverage; matched counters are not acceptance"
                )
        elif event == "run-end":
            run_ends.add(row["run_id"])
            if row.get("reason", "complete") != "complete":
                warnings.append("Run ended early or was interrupted")
        elif event == "budget-exhausted" or (
            event == "coverage" and row["completed_plan_requests"] < row["planned_requests"]
        ):
            warnings.append("Execution did not complete the planned request coverage")
        elif event == "attempt":
            if not all(identity) or identity in attempts:
                duplicates.add(identity)
            attempts[identity] = row
        elif event in {"response", "error", "interrupted"}:
            if identity in terminals:
                duplicates.add(identity)
            terminals.add(identity)
            if event == "response":
                responses[identity] = row
    if duplicates:
        warnings.append("Duplicate or missing client identities; affected attempts are uncertain")
    if terminals - attempts.keys():
        warnings.append("Terminal events without matching attempts")
    if run_starts - run_ends:
        warnings.append("Run has no end event; execution may have been interrupted")
    origin_map = defaultdict(list)
    for row in origins:
        origin_map[row.get("run_id"), row.get("request_id")].append(row)
    correlated = 0
    lookup = {}
    cache_groups = defaultdict(list)

    def bucket(at, attempt):
        return (
            at.date().isoformat(),
            attempt["page_id"],
            label(attempt["ua"]),
            attempt["access_method"],
        )

    def uncertain(attempt, first, last):
        counts["uncertain"] += 1
        if attempt.get("page_id") is not None and attempt.get("countable", True):
            for offset in range((last.date() - first.date()).days + 1):
                day = first.date() + timedelta(days=offset)
                possible[
                    (
                        day.isoformat(),
                        attempt["page_id"],
                        label(attempt["ua"]),
                        attempt["access_method"],
                    )
                ] += 1

    for identity, attempt in attempts.items():
        began = timestamp(attempt["timestamp"])
        response = responses.get(identity)
        finished = timestamp(response["timestamp"]) if response else end
        if began < start or began > end:
            counts["outside_window"] += 1
            continue
        counts["attempts"] += 1
        if attempt.get("retry_of"):
            counts["retries"] += 1
        if response:
            counts["completed_responses"] += 1
            if response.get("outcome") in {"failure", "cache-poisoning"}:
                counts["assertion_failures"] += 1
            if response.get("outcome") == "known-limitation":
                counts["known_limitations"] += 1
        else:
            counts["incomplete_receipts"] += 1
        if attempt.get("page_id") is not None:
            lookup[uri(attempt["url"]).split("?", 1)[0]] = attempt
        if attempt.get("group"):
            cache_groups[attempt["group"]].append((attempt, response))
        matches = origin_map.get(identity, [])
        match = matches[0] if len(matches) == 1 else None
        valid = False
        first, last = began, min(finished, end)
        if match and identity not in duplicates:
            try:
                first, last = origin_interval(match)
                valid = (
                    match["method"] == attempt["method"]
                    and match["uri"] == uri(attempt["url"])
                    and match["user_agent"] == attempt["ua"]
                    and first >= began - timedelta(seconds=5)
                    and last <= end + timedelta(seconds=5)
                )
            except (KeyError, ValueError, TypeError):
                valid = False
            if valid:
                correlated += 1
        cache_hit = (
            response
            and response.get("headers", {}).get("cf-cache-status", "").upper() in CACHE_HITS
        )
        if (
            identity in duplicates
            or (matches and not valid)
            or (cache_hit and valid)
            or finished > end
        ):
            uncertain(attempt, began, min(finished, end))
            continue
        if cache_hit:
            counts["cdn_cache_hits"] += 1
            continue
        if attempt["method"] == "HEAD" or not attempt.get("countable", True):
            counts["excluded"] += 1
            continue
        if not valid:
            uncertain(attempt, began, min(finished, end))
            continue
        first = min(first, began)
        last = max(last, finished if response else last)
        if first < start or last > end or first.date() != last.date():
            uncertain(attempt, first, last)
            continue
        try:
            kind = origin_kind(match)
        except (KeyError, TypeError, ValueError):
            kind = "uncertain"
        if kind == "uncertain":
            uncertain(attempt, first, last)
        elif kind == "selected" and attempt.get("page_id") is not None:
            expected[bucket(first, attempt)] += 1
            counts["origin_selections"] += 1
        else:
            counts[kind] += 1

    # Uncorrelated rows may be background or separately verified vendor traffic.
    # Never relabel a broken simulator correlation as unrelated background.
    for row in origins:
        identity = (row.get("run_id"), row.get("request_id"))
        if identity in attempts:
            continue
        if identity[0] in run_starts or identity[0] in {key[0] for key in attempts}:
            counts["orphan_simulator_requests"] += 1
            warnings.append("Origin has simulator requests missing from the client log")
            continue
        try:
            first, last = origin_interval(row)
            if first < start or last > end:
                continue
            verified_vendor = row.get("traffic") == "vendor" and bool(row.get("verification"))
            name = "vendor" if verified_vendor else "background"
            counts[name] += 1
            path = row["uri"].split("?", 1)[0]
            kind = origin_kind(row)
            if kind == "uncertain":
                counts["background_uncertain"] += 1
                warnings.append("Background origin selections are uncertain")
                continue
            if kind != "selected":
                counts["background_excluded"] += 1
                continue
            template = lookup.get(path)
            if (
                not template
                and verified_vendor
                and type(row.get("page_id")) is int
                and row["page_id"] > 0
                and row.get("access_method") in METHODS
            ):
                template = row
            if not template or first.date() != last.date():
                counts["unmapped_background"] += 1
                continue
            query = parse_qs(urlsplit(row["uri"]).query)
            if template is row:
                access_method = row["access_method"]  # Independently verified page/method mapping.
            elif template["access_method"] == "export-url":
                access_method = "export-url"
            elif query.get("output_format", [""])[0].strip().lower() in {"md", "markdown"}:
                access_method = "query-param"
            elif accepts_markdown(row.get("accept", "")):
                access_method = "accept-header"
            elif detect_agent(row["user_agent"]):
                access_method = "ua"
            else:
                counts["unmapped_background"] += 1
                continue
            key = (
                first.date().isoformat(),
                template["page_id"],
                label(row["user_agent"]),
                access_method,
            )
            (vendor if verified_vendor else background)[key] += 1
        except (KeyError, ValueError, TypeError):
            warnings.append("Malformed origin row cannot be reconciled")
    if not correlated:
        warnings.append(
            "No matching nginx correlation headers verified; origin attribution is unproven"
        )
    keys = (
        baseline.keys()
        | final.keys()
        | expected.keys()
        | possible.keys()
        | background.keys()
        | vendor.keys()
    )
    buckets = []
    mismatch = False
    for key in sorted(keys):
        observed = final.get(key, 0) - baseline.get(key, 0)
        if observed < 0:
            warnings.append("Counter decreased: pruning, reset or mismatched snapshot scope")
        residual = observed - expected[key] - background[key] - vendor[key]
        mismatch |= residual < -tolerance or residual > possible[key] + tolerance
        buckets.append(
            {
                "access_date": key[0],
                "page_id": key[1],
                "agent": key[2],
                "access_method": key[3],
                "observed": observed,
                "expected": expected[key],
                "possible": possible[key],
                "background": background[key],
                "vendor": vendor[key],
                "residual": residual,
            }
        )
    orderings = []
    for name, pairs in cache_groups.items():
        warm = any(
            a["access_method"] == "browser"
            and r
            and r.get("headers", {}).get("cf-cache-status", "").upper() == "HIT"
            and content_type(r.get("headers", {}).get("content-type", "")) == "text/html"
            for a, r in pairs[:-1]
        )
        orderings.append(
            {
                "group": name,
                "completed": sum(r is not None for _, r in pairs),
                "warm_html_observed": warm,
                "cold_start_verified": False,
            }
        )
    status = "mismatch" if mismatch or counts["assertion_failures"] else "matched"
    if warnings or counts["uncertain"] or counts["unmapped_background"]:
        status = "inconclusive" if not counts["assertion_failures"] else "mismatch"
    return {
        "schema_version": 1,
        "status": status,
        "correlation_verified": bool(correlated),
        "matched_origin_requests": correlated,
        "counts": dict(counts),
        "buckets": buckets,
        "warnings": sorted(set(warnings)),
        "cache_orderings": orderings,
        "tolerance": tolerance,
        "meaning": "Expected counts describe origin response selection, not complete receipt",
    }
