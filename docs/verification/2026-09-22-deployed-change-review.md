# Deployed fixture changes — prepared 22 September 2026

Status: prepared and tested on 22 September, then applied and restored during the
[23 September bounded run](2026-09-23-bounded-deployed-run.md). The owner authorised preparing the
fixture/logging changes for review after the
[deployment preflight](2026-09-22-next-deployed-verification.md). During preparation,
no public target requests, application/database changes, active nginx changes,
service restart or Cloudflare changes were made. Deployment-specific files remain
in the private review archive, outside version control.

## Proposed change

- Create five synthetic pages: a separate branch plus fallback, excluded, preview
  and private children, using the host's existing StandardPage model. Fallback
  also supplies the missing-export case. Reuse the existing ownerless blog index
  for the navigation fixture. Restrictions/exclusion are established before
  publication inside the creation transaction.
- Disable automatic generation only in the seeding process. Explicitly generate
  preview and refresh shared discovery; the branch also gains a page-owned index.
  Expect two additional manifest documents. Preserve unrelated leaf-export hashes
  and confirm the actual manifest/plan before baseline.
- Add a temporary host-only preview middleware before Markdown negotiation. Bind
  it to one fixed path, site/root/page, published revision and revision-content
  hash; expire it two hours after seeding. It sets `request.is_preview` before
  negotiation and calls Wagtail's real `serve_preview`. Drafts, restrictions,
  changed published revisions, mismatched identities and invalid query/method
  shapes are denied. Preview responses are private/no-store, with empty HEAD bodies.
- Extend the existing tagged log allowlist with four exact public paths and the
  simple preview query. Preserve the correlation format and 32-hex ID filter.
  Validate the combined active configuration, then restart the single application
  worker and reload nginx. Brief interruption during restart is possible.

Package, registry, rendering policy, URL configuration and Cloudflare cache/security
settings stay as inspected. No purge, vendor call or ecosystem feature is proposed.
Chrome inspection also confirmed Speed Brain, Early Hints and Rocket Loader off.

## Validation

The isolated rehearsal used the host's tracked bakerydemo source at `8e2b625`, real
StandardPage templates, real package lifecycle receivers, and fresh database/export
storage. Django 6.0.8 and Wagtail 7.4.3 matched the host. Local Python was 3.12.9;
the host uses 3.12.3. Other local dependency versions are retained privately.

All **23 tests passed**, covering all twelve fixture GET/HEAD responses without
counter increments; pre-negotiation preview marking; real preview rendering;
unpublished draft exclusion; page/ancestor restrictions; invalid, expired and
missing state; republished preview denial; normal Markdown/browser controls;
unrelated export preservation; partial generation failure; fixture retirement;
and guarded configuration installation/restoration that refuses unexpected edits.

The draft logging maps/format passed the host nginx binary's syntax test in an
isolated temporary configuration, removed afterward. An initial stdin-only attempt
was unsuitable because nginx needs a seekable configuration; the subsequent file
test passed. The combined active configuration must still be validated at apply
time. Ruff lint/format and documentation whitespace checks passed.

These tests do not establish CDN behaviour, live origin correlation, a cold cache
or deployed fixture acceptance. The existing package suite was not rerun for this
host-only bundle; no package source changed.

## Apply and cleanup boundary

The private bundle contains exact original/proposed settings and nginx files,
unified diffs, the adapter, guarded fixture/configuration tools, tests/results,
dependency versions, installed-package hashes and an apply/rollback runbook.
The tools refuse mismatched originals or installed package bytes. New fixture IDs
are recorded during creation, rather than guessed in advance.

The private `review-bundle.tar.gz` is 22,436 bytes, containing 16 reviewed files
and their checksum list. Its SHA-256 is
`6221d86fb9da13f575da0697bccf0becd472811ab45f27e254b9f26183057da2`.

Cleanup unpublishes and restricts the known fixture branch, withdraws its exports,
refreshes discovery and restores the reviewed configuration. It retains CMS rows,
revisions, counter history and evidence. It refuses unexpected descendants,
republished fixtures or configuration edits. Recovery copies are not a routine
database rollback: restoring the whole database could discard counters. No cache
purge is planned; harmless cached synthetic HTML may persist until its TTL expires.

The proposed run remains bounded by 40 discovery/readiness/correlation requests
and 1,000 measured requests at one start per second, seed 59, zero retries, a
20-second timeout, 8 MiB response limit and a 30-minute deadline per phase. Use
`cloudflare-free`, retain its Accept-only limitations, and leave cold-cache checks
unverified. Confirm a quiet operator window and cleanup/evidence ownership before
application. Prove actual origin correlation and finish readiness before baseline;
the complete live plan must fit the agreed limits before execution.
