"""Simulator contracts: offline plans, recorded transport and conservative evidence."""

import hashlib
import json
from dataclasses import replace

import pytest
from scripts import agent_simulator as sim

from wagtail_markdown_agents.data.agents import AGENTS
from wagtail_markdown_agents.stats import agent_label

TARGET = "https://www.example.org"
BODY = b"---\nid: 999\npermalink: https://www.example.org/news/\n---\nHello\n"


def inventory():
    return [
        {
            "id": 7,
            "url": TARGET + "/news/",
            "export_url": TARGET + "/markdown/news.md",
            "full_hash": hashlib.sha256(BODY).hexdigest(),
            "links": [],
        }
    ]


def request(**kwargs):
    values = {
        "url": TARGET + "/news/",
        "page_id": 7,
        "ua": "GPTBot/1.4",
        "access_method": "ua",
        "expected_type": "text/markdown",
    }
    values.update(kwargs)
    return sim.RequestSpec(**values)


def test_manifest_identity_and_hooked_export_path():
    manifest = {
        "schema_version": "0.1",
        "documents": [
            {
                "id": 7,
                "url": TARGET + "/markdown/custom/location.md",
                "full_hash": hashlib.sha256(BODY).hexdigest(),
            }
        ],
    }
    pages = sim.discover(manifest, TARGET, lambda spec: BODY)
    assert pages[0]["id"] == 7  # Frontmatter hook must not replace manifest identity.
    assert pages[0]["url"] == TARGET + "/news/"
    assert pages[0]["export_url"].endswith("custom/location.md")


@pytest.mark.parametrize(
    "url",
    [
        "https://elsewhere.example/x",
        "file:///etc/passwd",
        "https://user:secret@www.example.org/x",
        TARGET + "/x?token=secret",
    ],
)
def test_discovery_rejects_unsafe_destinations(url):
    with pytest.raises(ValueError):
        sim.discover(
            {"schema_version": "0.1", "documents": [{"id": 7, "url": url}]},
            TARGET,
            lambda spec: BODY,
        )


def test_plan_is_seeded_bounded_and_reports_missing_fixtures():
    a = sim.build_plan(inventory(), TARGET, seed=59, max_requests=1000)
    assert a == sim.build_plan(inventory(), TARGET, seed=59, max_requests=1000)
    assert a != sim.build_plan(inventory(), TARGET, seed=60, max_requests=1000)
    assert len(a["requests"]) == 1000
    assert "preview" in a["coverage"]["missing_fixtures"]
    assert {r["access_method"] for r in a["requests"]} >= {
        "accept-header",
        "query-param",
        "ua",
        "export-url",
        "browser",
    }
    assert {r["ordering"] for r in a["requests"]} >= {"html-first", "agent-first"}
    assert {r["method"] for r in a["requests"]} == {"HEAD", "GET"}
    assert {agent.label for agent in AGENTS} <= {r["agent"] for r in a["requests"]}
    assert a["coverage"]["suite_complete"]
    short = sim.build_plan(inventory(), TARGET, max_requests=2)
    assert not short["coverage"]["suite_complete"]


def test_fleet_labels_match_application_and_claim_only_synthetic_traffic():
    for agent in sim.fleet():
        assert agent_label(agent["ua"]) == agent["agent"]
        assert agent["provenance"] in {"official-example", "synthetic-shape", "dataset-synthetic"}
        assert agent["traffic"] == "simulated"
    assert {a["category"] for a in sim.fleet()} >= {"training", "search", "on-demand"}


def test_export_links_are_followed_only_to_manifested_pages():
    pages = inventory()
    pages[0]["links"] = [TARGET + "/markdown/news.md", "https://elsewhere.example/x"]
    plan = sim.build_plan(pages, TARGET, max_requests=1000)
    links = [r for r in plan["requests"] if r["scenario"] == "follow-link"]
    assert links and all(r["url"] == pages[0]["export_url"] for r in links)


def test_explicit_exclusion_fixtures_do_not_count():
    fixtures = [
        {
            "kind": "fallback",
            "url": "/empty/",
            "status": 200,
            "content_type": "text/html",
            "page_id": 8,
        },
        {
            "kind": "private-export",
            "url": "/markdown/private.md",
            "status": 404,
            "content_type": "text/html",
            "page_id": 9,
        },
    ]
    plan = sim.build_plan(inventory(), TARGET, fixtures=fixtures, max_requests=1000)
    checks = [r for r in plan["requests"] if r["scenario"] in {"fallback", "private-export"}]
    assert checks and all(not r["countable"] for r in checks)


@pytest.mark.parametrize(
    "spec,headers,expected",
    [
        (request(), {"content-type": "text/markdown"}, "pass"),
        (request(), {"content-type": "text/html", "cf-cache-status": "HIT"}, "failure"),
        (
            request(ua=sim.UNLISTED_UA, access_method="accept-header"),
            {"content-type": "text/html", "cf-cache-status": "HIT"},
            "known-limitation",
        ),
        (
            request(ua=sim.UNLISTED_UA, access_method="accept-header"),
            {"content-type": "text/html", "cf-cache-status": "MISS"},
            "failure",
        ),
        (
            request(access_method="browser", ua=sim.BROWSER_UA, expected_type="text/html"),
            {"content-type": "text/markdown"},
            "cache-poisoning",
        ),
    ],
)
def test_cache_assertions(spec, headers, expected):
    assert (
        sim.assess(spec, 200, headers, b"x", cache_profile="cloudflare-free")["outcome"] == expected
    )


def test_known_limitation_requires_explicit_profile_and_head_skips_body_hash():
    spec = request(ua=sim.UNLISTED_UA, access_method="accept-header")
    headers = {"content-type": "text/html", "cf-cache-status": "HIT"}
    assert sim.assess(spec, 200, headers, b"x")["outcome"] == "failure"
    assert (
        sim.assess(
            replace(spec, method="HEAD", full_hash="wrong"),
            200,
            {"content-type": "text/markdown"},
            b"",
        )["outcome"]
        == "pass"
    )


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Transport:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def __call__(self, spec, headers, timeout, max_bytes):
        self.calls.append((spec, headers))
        item = next(self.replies)
        if isinstance(item, BaseException):
            raise item
        return item


def events(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_attempts_retries_completed_receipts_and_rate_are_explicit(tmp_path):
    path = tmp_path / "run.jsonl"
    clock = Clock()
    transport = Transport(
        [
            TimeoutError("secret must not be logged"),
            (200, {"content-type": "text/markdown", "set-cookie": "secret"}, b"ok"),
        ]
    )
    runner = sim.Runner(
        path, TARGET, max_requests=2, rate=2, retries=1, transport=transport, clock=clock
    )
    with runner:
        runner.fetch(request())
    log = events(path)
    attempts = [e for e in log if e["event"] == "attempt"]
    assert len(attempts) == 2
    assert attempts[1]["retry_of"] == attempts[0]["request_id"]
    assert len({e["request_id"] for e in attempts}) == 2
    assert clock.now >= 0.5
    assert transport.calls[0][1]["X-Sim-Run"] == runner.run_id
    assert transport.calls[0][1]["X-Sim-Request"] == attempts[0]["request_id"]
    complete = next(e for e in log if e["event"] == "response")
    assert complete["body_sha256"] == hashlib.sha256(b"ok").hexdigest()
    assert complete["received_bytes"] == 2
    assert "secret" not in path.read_text()
    assert all(e["timestamp"].endswith("Z") for e in log)


def test_interruption_and_budget_are_not_completed_responses(tmp_path):
    path = tmp_path / "run.jsonl"
    runner = sim.Runner(path, TARGET, transport=Transport([KeyboardInterrupt()]))
    with pytest.raises(KeyboardInterrupt), runner:
        runner.fetch(request())
    log = events(path)
    assert [e["event"] for e in log] == ["run-start", "attempt", "interrupted", "run-end"]
    assert log[-1]["reason"] == "interrupted"
    runner = sim.Runner(
        tmp_path / "limited.jsonl",
        TARGET,
        max_requests=1,
        retries=2,
        transport=Transport([TimeoutError()]),
    )
    with runner, pytest.raises(sim.BudgetExhausted):
        runner.fetch(request())
    assert runner.attempts == 1


def evidence():
    spec = request().as_dict()
    attempt = dict(
        event="attempt", run_id="run", request_id="r1", timestamp="2026-09-21T12:00:00Z", **spec
    )
    response = {
        "event": "response",
        "run_id": "run",
        "request_id": "r1",
        "timestamp": "2026-09-21T12:00:01Z",
        "status": 200,
        "headers": {"content-type": "text/markdown", "cf-cache-status": "DYNAMIC"},
    }
    origin = {
        "run_id": "run",
        "request_id": "r1",
        "timestamp": "2026-09-21T12:00:01Z",
        "method": "GET",
        "uri": "/news/",
        "user_agent": "GPTBot/1.4",
        "accept": "text/html",
        "status": 200,
        "content_type": "text/markdown",
        "upstream_status": "200",
        "upstream_cache_status": "",
        "request_time": "1.0",
    }
    row = {
        "page_id": 7,
        "agent": "GPTBot",
        "access_method": "ua",
        "access_date": "2026-09-21",
        "count": 1,
    }
    before = {"captured_at": "2026-09-21T11:59:00Z", "rows": []}
    after = {"captured_at": "2026-09-21T12:01:00Z", "rows": [row]}
    return [attempt, response], [origin], before, after


def test_reconcile_exact_and_origin_selection_despite_interrupted_client():
    log, origin, before, after = evidence()
    result = sim.reconcile(log, origin, before, after)
    assert result["correlation_verified"]
    assert result["buckets"][0]["expected"] == 1
    assert result["buckets"][0]["residual"] == 0
    result = sim.reconcile(log[:1], origin, before, after)
    assert result["counts"]["incomplete_receipts"] == 1
    assert result["buckets"][0]["expected"] == 1


def test_reconcile_no_correlation_is_uncertain_not_zero_or_exact():
    log, _, before, after = evidence()
    result = sim.reconcile(log, [], before, after)
    assert not result["correlation_verified"]
    assert result["counts"]["uncertain"] == 1
    assert result["buckets"][0]["expected"] == 0
    assert result["buckets"][0]["possible"] == 1
    assert result["status"] == "inconclusive"


@pytest.mark.parametrize(
    "mutation,classification",
    [
        ({"upstream_status": "-"}, "static_bypasses"),
        ({"upstream_cache_status": "HIT"}, "origin_cache_hits"),
        ({"status": 404, "content_type": "text/html"}, "excluded"),
    ],
)
def test_reconcile_origin_exclusions(mutation, classification):
    log, origins, before, after = evidence()
    origins[0].update(mutation)
    after["rows"] = []
    result = sim.reconcile(log, origins, before, after)
    assert result["counts"][classification] == 1
    assert not any(b["expected"] for b in result["buckets"])


def test_reconcile_edge_hits_and_background_are_separate():
    log, origins, before, after = evidence()
    log[1]["headers"]["cf-cache-status"] = "HIT"
    origins[0].update(run_id="", request_id="")
    result = sim.reconcile(log, origins, before, after)
    assert result["counts"]["cdn_cache_hits"] == 1
    assert result["counts"]["background"] == 1
    assert result["buckets"][0]["background"] == 1


def test_reconcile_midnight_and_resets_cannot_pass():
    log, origins, before, after = evidence()
    log[0]["timestamp"] = "2026-09-20T23:59:59Z"
    origins[0]["timestamp"] = "2026-09-21T00:00:01Z"
    origins[0]["request_time"] = "2.0"
    before["captured_at"] = "2026-09-20T23:00:00Z"
    result = sim.reconcile(log, origins, before, after)
    assert result["counts"]["uncertain"] == 1
    before["rows"] = [dict(after["rows"][0], count=2)]
    result = sim.reconcile(log, origins, before, after)
    assert result["status"] == "inconclusive"
    assert any("decreased" in warning for warning in result["warnings"])


def test_bad_correlation_and_truncated_log_are_not_silently_accepted(tmp_path):
    log, origins, before, after = evidence()
    origins[0]["uri"] = "/different/"
    result = sim.reconcile(log, origins, before, after)
    assert not result["correlation_verified"]
    assert result["counts"]["uncertain"] == 1
    path = tmp_path / "partial.jsonl"
    path.write_text(json.dumps(log[0]) + '\n{"event":')
    rows, warnings = sim.read_jsonl(path)
    assert rows == log[:1]
    assert warnings


@pytest.mark.parametrize("max_bytes,received", [(100, 7), (3, 4)])
def test_transport_partial_body_keeps_headers_without_claiming_receipt(
    tmp_path, max_bytes, received
):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown")
            self.send_header("Content-Length", "30")
            self.end_headers()
            self.wfile.write(b"partial")
            self.close_connection = True

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    target = f"http://127.0.0.1:{server.server_port}"
    path = tmp_path / "partial.jsonl"
    try:
        with (
            sim.Runner(path, target, timeout=1, max_bytes=max_bytes) as runner,
            pytest.raises(sim.FetchFailed),
        ):
            runner.fetch(request(url=target + "/page/"))
        error = next(e for e in events(path) if e["event"] == "error")
        assert error["status"] == 200
        assert error["received_bytes"] == received
        assert not error["receipt_complete"]
        assert not any(e["event"] == "response" for e in events(path))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_live_local_http_plan_run_and_reconciliation_inputs(tmp_path, capsys):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append((self.path, dict(self.headers)))
            if self.path == "/redirect/":
                self.send_response(302)
                self.send_header("Location", "/must-not-follow/")
                self.end_headers()
                return
            if self.path == "/poison/":
                body = b"markdown"
                content_type = "text/markdown"
            elif self.path.endswith("manifest.json"):
                body = json.dumps(
                    {
                        "schema_version": "0.1",
                        "documents": [{"id": 7, "url": target + "/markdown/news.md"}],
                    }
                ).encode()
                content_type = "application/json"
            elif self.path.endswith(".md"):
                body = (
                    "---\npermalink: " + target + "/news/\n---\n"
                    "[Self](" + target + "/markdown/news.md)\n"
                ).encode()
                content_type = "text/markdown"
            elif self.path.endswith("llms.txt"):
                body, content_type = b"Index", "text/plain"
            else:
                is_agent = (
                    "GPTBot" in self.headers.get("User-Agent", "")
                    or "ChatGPT-User" in self.headers.get("User-Agent", "")
                    or "OAI-SearchBot" in self.headers.get("User-Agent", "")
                    or "Claude" in self.headers.get("User-Agent", "")
                )
                md = (
                    is_agent
                    or self.headers.get("Accept") == "text/markdown"
                    or "output_format=md" in self.path
                )
                body, content_type = (
                    (b"markdown", "text/markdown") if md else (b"html", "text/html")
                )
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    target = f"http://127.0.0.1:{server.server_port}"
    plan, log = tmp_path / "plan.json", tmp_path / "events.jsonl"
    try:
        assert (
            sim.main(
                [
                    "plan",
                    "--target",
                    target,
                    "--output",
                    str(plan),
                    "--log",
                    str(log),
                    "--max-requests",
                    "4",
                    "--rate",
                    "1000",
                ]
            )
            == 0
        )
        data = json.loads(plan.read_text())
        assert data["requests"][0]["page_id"] == 7
        assert data["coverage"]["followed_links"] == 0  # Truncated budget is explicit.
        assert sim.main(["run", "--plan", str(plan), "--log", str(log)]) == 0
        with sim.Runner(log, target) as runner:
            runner.fetch(request(url=target + "/redirect/"))
        assert not any(path == "/must-not-follow/" for path, _ in calls)
        with pytest.raises(sim.CachePoisoning), sim.Runner(log, target) as runner:
            runner.fetch(request(url=target + "/poison/", access_method="browser"))
        assert all(
            headers.get("X-Sim-Run") and headers.get("X-Sim-Request") for _, headers in calls
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_duration_budget_and_byte_limit(tmp_path):
    clock = Clock()
    runner = sim.Runner(
        tmp_path / "duration.jsonl",
        TARGET,
        duration=0.2,
        rate=1,
        clock=clock,
        transport=Transport([(200, {}, b"")]),
    )
    with runner:
        runner.fetch(request())
        with pytest.raises(sim.BudgetExhausted):
            runner.fetch(request())
    assert runner.attempts == 1


def test_appending_preserves_prior_run_and_refuses_truncated_tail(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text('{"event":"previous"}\n')
    with sim.Runner(path, TARGET):
        pass
    assert events(path)[0] == {"event": "previous"}
    path.write_text('{"event":')
    with pytest.raises(ValueError), sim.Runner(path, TARGET):
        pass
    assert path.read_text() == '{"event":'


def test_reconcile_retries_each_count_and_duplicates_are_uncertain():
    log, origins, before, after = evidence()
    log.extend([dict(log[0], request_id="r2", retry_of="r1"), dict(log[1], request_id="r2")])
    origins.append(dict(origins[0], request_id="r2"))
    after["rows"][0]["count"] = 2
    result = sim.reconcile(log, origins, before, after)
    assert result["buckets"][0]["expected"] == 2
    assert result["counts"]["retries"] == 1
    origins.append(origins[0])
    result = sim.reconcile(log, origins, before, after)
    assert result["counts"]["uncertain"] == 1


def test_reconcile_background_accept_precedence_and_verified_vendor():
    log, origins, before, after = evidence()
    origins.append(
        dict(
            origins[0],
            run_id="",
            request_id="",
            accept="text/html, text/markdown",
            traffic="vendor",
            verification="independent-evidence-reference",
        )
    )
    after["rows"].append(dict(after["rows"][0], access_method="accept-header"))
    result = sim.reconcile(log, origins, before, after)
    assert result["counts"]["vendor"] == 1
    bucket = next(b for b in result["buckets"] if b["access_method"] == "accept-header")
    assert bucket["vendor"] == 1 and bucket["residual"] == 0


def test_reconcile_real_discrepancy_and_tolerance():
    log, origins, before, after = evidence()
    after["rows"][0]["count"] = 2
    assert sim.reconcile(log, origins, before, after)["status"] == "mismatch"
    assert sim.reconcile(log, origins, before, after, tolerance=1)["status"] == "matched"


@pytest.mark.parametrize("cache", ["REVALIDATED", "STALE", "UPDATING"])
def test_cache_revalidation_is_not_assumed_to_skip_origin(cache):
    log, origins, before, after = evidence()
    log[1]["headers"]["cf-cache-status"] = cache
    result = sim.reconcile(log, [], before, after)
    assert result["counts"]["uncertain"] == 1
    assert not result["counts"].get("cdn_cache_hits")
    origins[0]["upstream_cache_status"] = cache
    assert sim.reconcile(log, origins, before, after)["counts"]["uncertain"] == 1


@pytest.mark.parametrize("status", [499, 500, 502, 504])
def test_failed_origin_delivery_may_still_have_selected_markdown(status):
    log, origins, before, after = evidence()
    origins[0]["status"] = status
    result = sim.reconcile(log[:1], origins, before, after)
    assert result["counts"]["uncertain"] == 1
    assert result["buckets"][0]["possible"] == 1


def test_discovery_link_parsing_ignores_code_and_preserves_reference_links():
    source = (
        BODY + b"\n[Self][self]\n\n[self]: /markdown/news.md#heading\n\n```\n[No](/bad.md)\n```\n"
    )
    manifest = {
        "schema_version": "0.1",
        "documents": [{"id": 7, "url": TARGET + "/markdown/news.md"}],
    }
    pages = sim.discover(manifest, TARGET, lambda spec: source)
    assert pages[0]["links"] == [TARGET + "/markdown/news.md#heading"]
    plan = sim.build_plan(pages, TARGET, max_requests=1000)
    assert plan["coverage"]["followed_links"] == 1


def test_page_owned_navigation_fixture_is_rejected():
    with pytest.raises(ValueError, match="manifested index"):
        sim.build_plan(
            inventory(),
            TARGET,
            fixtures=[
                {
                    "kind": "navigation-index",
                    "url": "/markdown/news.md",
                    "status": 200,
                    "content_type": "text/markdown",
                }
            ],
        )


def test_cli_offline_plan_and_reconcile(tmp_path):
    manifest, fixtures, plan = [
        tmp_path / name for name in ("manifest.json", "fixtures.json", "plan.json")
    ]
    manifest.write_text(
        json.dumps(
            {"schema_version": "0.1", "documents": [{"id": 7, "url": TARGET + "/markdown/news.md"}]}
        )
    )
    fixtures.write_text(json.dumps({"canonical_urls": {"7": "/news/"}}))
    assert (
        sim.main(
            [
                "plan",
                "--target",
                TARGET,
                "--manifest-file",
                str(manifest),
                "--fixtures",
                str(fixtures),
                "--output",
                str(plan),
            ]
        )
        == 0
    )
    assert json.loads(plan.read_text())["coverage"]["suite_complete"]
    log, origins, before, after = evidence()
    paths = {name: tmp_path / name for name in ["client", "origin", "before", "after", "report"]}
    for name, rows in (("client", log), ("origin", origins)):
        paths[name].write_text("".join(json.dumps(row) + "\n" for row in rows))
    paths["before"].write_text(json.dumps(before))
    paths["after"].write_text(json.dumps(after))
    assert (
        sim.main(
            [
                "reconcile",
                "--log",
                str(paths["client"]),
                "--nginx",
                str(paths["origin"]),
                "--before",
                str(paths["before"]),
                "--after",
                str(paths["after"]),
                "--output",
                str(paths["report"]),
            ]
        )
        == 0
    )
    assert json.loads(paths["report"].read_text())["status"] == "matched"


def test_reconcile_runtime_coverage_cannot_be_hidden_by_matched_counters():
    log, origins, before, after = evidence()
    log.append({"event": "coverage", "completed_plan_requests": 1, "planned_requests": 20})
    result = sim.reconcile(log, origins, before, after)
    assert result["status"] == "inconclusive"
    assert any("coverage" in warning for warning in result["warnings"])


def test_unlisted_and_browser_stats_fallback_labels_match_application():
    from scripts.traffic_simulator.planning import label

    for ua in (sim.BROWSER_UA, sim.UNLISTED_UA, "", "  Example/1.2 (test)"):
        assert label(ua) == agent_label(ua)


def test_background_html_does_not_make_counter_attribution_uncertain():
    log, origins, before, after = evidence()
    origins.append(
        dict(origins[0], run_id="", request_id="", uri="/unrelated/", content_type="text/html")
    )
    result = sim.reconcile(log, origins, before, after)
    assert result["status"] == "matched"
    assert result["counts"]["background_excluded"] == 1


def test_verified_vendor_page_can_be_separate_from_simulated_inventory():
    log, origins, before, after = evidence()
    origins.append(
        dict(
            origins[0],
            run_id="",
            request_id="",
            uri="/vendor-nonce/",
            traffic="vendor",
            verification="verified-origin-reference",
            page_id=27,
            access_method="ua",
        )
    )
    after["rows"].append(dict(after["rows"][0], page_id=27))
    result = sim.reconcile(log, origins, before, after)
    assert result["status"] == "matched"
    assert next(b for b in result["buckets"] if b["page_id"] == 27)["vendor"] == 1


def test_missing_origin_during_multi_day_window_covers_intermediate_dates():
    log, _, before, after = evidence()
    after["captured_at"] = "2026-09-23T12:01:00Z"
    result = sim.reconcile(log[:1], [], before, after)
    assert {b["access_date"] for b in result["buckets"] if b["possible"]} == {
        "2026-09-21",
        "2026-09-22",
        "2026-09-23",
    }


def test_recognition_only_fleet_expects_html_and_does_not_hash_it_as_markdown():
    plan = sim.build_plan(inventory(), TARGET, max_requests=1000)
    controls = [
        r for r in plan["requests"] if r["scenario"] == "fleet" and r["agent"] == "Applebot"
    ]
    assert len(controls) == 4
    for row in controls:
        if row["access_method"] == "ua":
            assert row["expected_type"] == "text/html"
            assert not row["countable"] and not row["full_hash"]
            outcome = sim.assess(
                sim.RequestSpec.from_dict(row), 200, {"content-type": "text/html"}, b"normal HTML"
            )
            assert outcome["outcome"] == "pass"
        else:
            assert row["expected_type"] == "text/markdown" and row["countable"]


def test_recognised_accept_only_client_has_free_plan_cache_limit():
    spec = request(ua="Applebot/0.1", access_method="accept-header")
    outcome = sim.assess(
        spec,
        200,
        {"content-type": "text/html", "cf-cache-status": "HIT"},
        b"HTML",
        cache_profile="cloudflare-free",
    )
    assert outcome["outcome"] == "known-limitation"
