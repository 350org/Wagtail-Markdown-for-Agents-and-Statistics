# Next bounded deployed verification — prepared 22 September 2026

Status: prepared, not executed. The fixture implementation and local evidence are
already committed in `7f18b9c57590056e80d034a90483a4aaa563f78a`. The working tree
was clean when review began. The [local report](2026-09-22-local-fixtures.md)
does not replace the [21 September deployed evidence](2026-09-21-bounded-live-run.md).

## Objective and boundary

Verify the six explicit fixture kinds through the agreed deployment, with GET and
HEAD, alongside the existing negotiation, browser/cache controls and counter
reconciliation. Use the existing simulator and current deployed policy. This work
adds no product features, registry entries, ecosystem integrations or rendering
policy changes. D9/D12 and restricted-link policy remain separate.

This is one bounded session. Multi-day behaviour and genuine vendor fetches remain
separate acceptance work. No vendor API calls are included. Cold-cache verification
is included only if the operator can establish and retain independent evidence for
the selected ordinary URL; otherwise report it as unverified.

## Deployment information needed before live changes

The previous run's deployment and permissions are historical evidence, not a
confirmed configuration for this session.

The owner identified `a89dab59a7c517ed619bcb26ab2ede1fd5e2deff` as the likely
deployed revision; confirm it on the application host. This commit exists locally
and contains the independent registry update. Its `src/` package tree is unchanged
through reviewed fixture commit `7f18b9c`; the later simulator change corrects
GET/HEAD fixture coverage and the sandbox additions are local-only. If the running
package is confirmed to match, this fixture review alone requires no package
upgrade. The target URL and operator/access route are still unspecified.

Record the following privately:

| Information | Why it is needed |
| --- | --- |
| Exact public origin, manifest path, environment and responsible operator | Select the controlled target and establish the change window |
| Application checkout/service, settings module, access route and deployment/restart procedure | Prepare an exact deployment diff and rollback commands |
| Running package commit, simulator commit, registry version, Python/Django/Wagtail versions and export generation settings | Establish matching expectations; the previous run predates the independent registry |
| Site ID, root page, fixture parent, usable page models and existing fixture URLs/IDs | Map the six actual states without modifying unrelated content |
| Safe preview mechanism and its request lifecycle | Prove `request.is_preview` is set before negotiation and that only synthetic published content can be served |
| Current CDN plan, cache rules and order, origin/proxy cache behaviour, and route to review them | Choose `strict` or `cloudflare-free` and check the installed bypass against the deployed registry |
| Approved cold-state method, exact URL and any permitted purge scope | Support a cold-cache claim without an unplanned purge |
| nginx configuration/log locations, Django upstream mapping, correlation fields, retention/rotation and clock synchronisation | Obtain actual matched origin records |
| Counter snapshot access and scope, quiet window, background traffic and scheduled export/pruning jobs | Keep before/after deltas comparable and explain unrelated increments |
| Agreed request limits/window, private evidence directory, fixture retention and rollback owner | Make execution and cleanup concrete |

Once supplied, prepare the actual fixture/deployment/configuration diff and rollback
steps for review before applying live changes. Do not deploy `sandbox.simulator_settings`
or run the local seeding command on the deployment. Existing fixtures may satisfy
these requirements without an application deployment. If a safe preview route is
unavailable, record that case as missing; full fixture acceptance remains incomplete.

## Fixture readiness

Use harmless synthetic content and record page IDs, exact URLs, state and expected
responses in a private `fixtures.json`, following the
[existing schema](../agent-simulator.md#fixtures-on-another-controlled-site).

| Kind | Independently establish before the baseline | GET / HEAD |
| --- | --- | --- |
| `fallback` | Public published page, no export; export jobs will not recreate it during the window | 200 HTML |
| `excluded` | Public published page with an active exclusion record | 200 HTML |
| `preview` | Exportable public synthetic page using real Wagtail preview handling, with draft and restriction protections | 200 HTML |
| `missing-export` | Direct export route for a deliberately ungenerated page | 404 HTML |
| `private-export` | Anonymous direct export route for an actually restricted synthetic page | 404 HTML |
| `navigation-index` | Generated navigation index whose artifact has no page owner and links to a public child | 200 Markdown |

All twelve fixture requests must contribute zero page-counter increments. Verify
HEAD bodies are empty. A generic HTML URL does not establish preview coverage, and
a page-owned index cannot stand in for the navigation-only fixture. Confirm the
ordinary preview-page URL serves Markdown. Check fixture state via the application,
not solely from HTTP status. Complete readiness probes before the baseline snapshot.

## Proposed limits

These limits await agreement for the selected target:

- At most 40 total discovery/readiness/correlation requests, including manual probes.
  Allocate 24 to discovery and reserve 16 for readiness/correlation; stop if discovery
  needs more and revise the allocation within 40 before any additional requests.
- At most 1,000 measured requests, sequentially at one request start per second,
  seed 59, zero retries, 20-second timeout and 8 MiB response limit.
- A 30-minute deadline for each phase. The discovery/readiness deadline is shared
  across all tools, and must be tracked by the operator as well as CLI limits.
- Use `cloudflare-free` only for a confirmed applicable deployment; otherwise use
  `strict`. Retain documented Accept-only warm HTML limitations as limitations.

Review `suite_requests` after discovery. The complete required suite must fit within
1,000 requests, all six fixture kinds must have GET and HEAD, and all labels in the
pinned registry must be scheduled. If it does not fit, stop and revise the agreed
scope or budget; do not silently truncate coverage or raise limits. This ceiling
allows comparison with the previous deployed run; the 250-request local budget is
not assumed sufficient for a larger manifest.

## Execution after readiness is agreed

1. Record deployed revisions and fixture state. Complete any agreed changes, review
   cache rules against the deployed registry, and record rollback details. Keep
   exports and fixture state stable throughout discovery and the measured window.
2. Verify the dedicated origin log with an uncached direct-export probe. Inspect
   the actual record for both exact correlation IDs, method, URI, UA and timestamp,
   and confirm a Django upstream selection. Simulator IDs are 32 hexadecimal
   characters; retain complete rotation segments. Count all probes within 40.
3. Discover and generate the private plan using the command below. Inspect its
   target, request count, coverage, fixtures, hashes and cache profile. Discovery
   may increment counters and warm caches; it must finish before the baseline.
4. If cold-state evidence is available, establish it after all relevant warm-up
   traffic and immediately before the selected request. Retain the independent
   evidence and exact request association. Preserve contiguous cache sequences;
   request order alone does not prove cold state. Record warm state only from
   observed HTML cache hits.
5. Capture the before snapshot using the [documented schema](../agent-simulator.md#snapshot-and-reconcile).
   Start traffic only after it completes. Run away from UTC midnight for this
   single-session comparison. Do not prune/reset counters during the window.
6. Execute once. Browser Markdown stops the simulator automatically. For other
   assertion/transport failures, unexpected application errors or operator health
   concerns, interrupt and preserve the partial evidence; the CLI otherwise keeps
   going for ordinary failures. Do not restart within the same budget unnoticed.
7. Wait for outstanding origin work to finish, take the after snapshot with the
   same scope, collect logs, and reconcile at zero tolerance. Retain failures and
   uncertainty even when total counter deltas happen to agree.

The following templates use operator-supplied `VERIFY_TARGET`, `VERIFY_MANIFEST`,
`VERIFY_PROFILE` and `VERIFY_DIR`; the directory must be private and outside version
control. They are not commands to execute before the prerequisites above are met.
The simulator checkout and environment must be pinned for the run.

```bash
uv run python -m scripts.agent_simulator plan \
  --target "$VERIFY_TARGET" --manifest-url "$VERIFY_MANIFEST" \
  --fixtures "$VERIFY_DIR/fixtures.json" --output "$VERIFY_DIR/plan.json" \
  --log "$VERIFY_DIR/discovery.jsonl" --discovery-limit 24 \
  --max-requests 1000 --duration 1800 --rate 1 --seed 59 \
  --cache-profile "$VERIFY_PROFILE"

uv run python -m scripts.agent_simulator run \
  --plan "$VERIFY_DIR/plan.json" --log "$VERIFY_DIR/client.jsonl" \
  --retries 0 --timeout 20 --max-bytes 8388608

uv run python -m scripts.agent_simulator reconcile \
  --log "$VERIFY_DIR/client.jsonl" --nginx "$VERIFY_DIR/origin.jsonl" \
  --before "$VERIFY_DIR/before.json" --after "$VERIFY_DIR/after.json" \
  --tolerance 0 --output "$VERIFY_DIR/report.json"
```

## Evidence and completion criteria

Retain fixtures, the exact plan and its hash, discovery/probe/client/origin logs,
before/after snapshots, reconciliation report, deployed versions, fixture-state
checks and any independent cache evidence. Produce a sanitised evidence manifest
with artifact sizes and SHA-256 hashes and replay reconciliation offline. Publish
a durable summary without deployment URLs, credentials, raw IPs or private content.

A successful session requires complete planned execution, twelve passing fixture
checks with no counter increments, correct representations/hashes, no browser
Markdown, verified origin correlation and zero residual in every UTC-day/page/agent/
method bucket at zero tolerance. Require `matched` reconciliation with no unresolved
uncertainty; documented cache limitations remain explicit. A tagged-only origin log
cannot fully attribute unrelated traffic, even when residuals are zero.

Retain or remove synthetic fixtures and restore temporary configuration according
to the recorded operator plan after collecting evidence; preserve counter history.
Update acceptance only for the cases actually established. Multi-day, genuine vendor
and any unproven cold-cache checks remain open after this session.
