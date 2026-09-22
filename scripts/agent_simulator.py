#!/usr/bin/env python3
"""Plan, run and reconcile bounded simulated agent traffic (see docs/agent-simulator.md)."""

import argparse
import hashlib
import json
import signal
from pathlib import Path

from scripts.traffic_simulator.planning import (  # noqa: F401 -- public test/programmatic API
    BROWSER_UA,
    UNLISTED_UA,
    RequestSpec,
    assess,
    build_plan,
    discover,
    fleet,
    safe_url,
    target_origin,
)
from scripts.traffic_simulator.reconciliation import read_jsonl, reconcile
from scripts.traffic_simulator.transport import (
    BudgetExhausted,
    CachePoisoning,
    FetchFailed,
    Runner,
)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    # Plans and reports may contain deployment URLs; keep them private by default.
    import os

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write("\n")


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    plan = commands.add_parser(
        "plan", help="Discover exports and write a deterministic bounded plan"
    )
    plan.add_argument("--target", required=True)
    plan.add_argument("--manifest-url", default="/markdown/manifest.json")
    plan.add_argument(
        "--manifest-file", type=Path, help="Offline manifest; canonical overrides required"
    )
    plan.add_argument("--fixtures", type=Path, help="JSON with canonical_urls and checks")
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument("--log", type=Path, help="Required for network discovery")
    plan.add_argument("--seed", type=int, default=59)
    plan.add_argument("--max-requests", type=int, default=1000)
    plan.add_argument("--duration", type=float, default=3600)
    plan.add_argument("--rate", type=float, default=1)
    plan.add_argument("--discovery-limit", type=int, default=200)
    plan.add_argument("--cache-profile", choices=["strict", "cloudflare-free"], default="strict")
    run = commands.add_parser(
        "run", help="Execute one reviewed plan; every retry consumes its budget"
    )
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--log", type=Path, required=True)
    run.add_argument("--retries", type=int, default=0)
    run.add_argument("--timeout", type=float, default=20)
    run.add_argument("--max-bytes", type=int, default=8 * 1024 * 1024)
    report = commands.add_parser(
        "reconcile", help="Compare client/nginx JSONL and counter snapshots"
    )
    report.add_argument("--log", type=Path, required=True)
    report.add_argument("--nginx", type=Path, required=True)
    report.add_argument("--before", type=Path, required=True)
    report.add_argument("--after", type=Path, required=True)
    report.add_argument("--output", type=Path, required=True)
    report.add_argument("--tolerance", type=int, default=0)
    return root


def plan_command(args):
    target = target_origin(args.target)
    fixture = read_json(args.fixtures) if args.fixtures else {}
    overrides = fixture.get("canonical_urls", {})
    manifest_url = safe_url(args.manifest_url, target)
    if args.manifest_file:

        def offline(spec):
            raise ValueError("Offline planning requires canonical_urls overrides for every page ID")

        pages = discover(read_json(args.manifest_file), target, offline, overrides)
    else:
        if not args.log:
            raise ValueError(
                "Network discovery requires --log; use --manifest-file for offline plans"
            )
        with Runner(
            args.log,
            target,
            max_requests=args.discovery_limit,
            rate=args.rate,
            duration=args.duration,
            phase="discovery",
            cache_profile=args.cache_profile,
        ) as runner:
            manifest = json.loads(
                runner.fetch(
                    RequestSpec(
                        manifest_url,
                        countable=False,
                        expected_type="application/json",
                        scenario="discovery",
                    )
                )
            )
            pages = discover(manifest, target, runner.fetch, overrides)
            if runner.failures:
                raise ValueError("Discovery assertions failed; inspect the log before planning")
    plan = build_plan(
        pages,
        target,
        fixtures=fixture.get("checks", []),
        seed=args.seed,
        max_requests=args.max_requests,
        duration=args.duration,
        rate=args.rate,
        cache_profile=args.cache_profile,
        manifest_url=manifest_url,
    )
    write_json(args.output, plan)
    print(json.dumps(plan["coverage"], sort_keys=True))
    return 0


def run_command(args):
    raw = args.plan.read_bytes()
    plan = json.loads(raw)
    if plan.get("schema_version") != 1:
        raise ValueError("Unsupported plan schema")
    specs = [RequestSpec.from_dict(row) for row in plan["requests"]]
    # Validate every destination before making the first request.
    for spec in specs:
        safe_url(spec.url, plan["target"])
    with Runner(
        args.log,
        plan["target"],
        max_requests=plan["max_requests"],
        duration=plan["duration"],
        rate=plan["rate"],
        cache_profile=plan["cache_profile"],
        retries=args.retries,
        timeout=args.timeout,
        max_bytes=args.max_bytes,
        metadata={"plan_sha256": hashlib.sha256(raw).hexdigest(), "coverage": plan["coverage"]},
    ) as runner:
        completed = 0
        for spec in specs:
            try:
                runner.fetch(spec)
                completed += 1
            except FetchFailed:
                continue
            except BudgetExhausted:
                runner.emit("budget-exhausted", remaining_plan_requests=len(specs) - completed)
                break
        runner.emit(
            "coverage",
            completed_plan_requests=completed,
            planned_requests=len(specs),
            suite=plan["coverage"],
        )
    print(
        json.dumps(
            {
                "run_id": runner.run_id,
                "attempts": runner.attempts,
                "failures": runner.failures,
                "known_limitations": runner.limitations,
            }
        )
    )
    return 1 if runner.failures else (2 if completed < len(specs) else 0)


def main(argv=None):
    cli = parser()
    args = cli.parse_args(argv)
    try:
        if args.command == "plan":
            return plan_command(args)
        if args.command == "run":
            return run_command(args)
        log, log_warnings = read_jsonl(args.log)
        origins, origin_warnings = read_jsonl(args.nginx)
        report = reconcile(
            log,
            origins,
            read_json(args.before),
            read_json(args.after),
            tolerance=args.tolerance,
            input_warnings=log_warnings + origin_warnings,
        )
        write_json(args.output, report)
        print(report["status"])
        return 0 if report["status"] == "matched" else 2
    except KeyboardInterrupt:
        return 130
    except (ValueError, KeyError, OSError, BudgetExhausted, FetchFailed, CachePoisoning) as exc:
        # Avoid echoing private URLs, file paths or arbitrary remote error bodies.
        print(
            f"{type(exc).__name__}: could not complete {args.command}; inspect inputs and event log"
        )
        return 1


def terminate(signum, frame):
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, terminate)
    raise SystemExit(main())
