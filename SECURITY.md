# Security policy

## Supported versions

Pre-1.0: only the latest release receives security fixes. The package is currently
an unreleased development preview (`0.1.0.dev0`); deployments should pin a reviewed
commit. Compatibility tests for older frameworks do not extend their upstream
security support; see [installation requirements](INSTALL.md#requirements).

## Reporting a vulnerability

Please report vulnerabilities privately via
[GitHub security advisories](https://github.com/350org/Wagtail-Markdown-for-Agents-and-Statistics/security/advisories/new)
rather than public issues. You should receive a response within a week.

That link depends on repository visibility, permissions and reporting settings.
If unavailable, use the private maintainer contact agreed during onboarding; do
not put vulnerability details in a public issue. The receiving organisation must
confirm an accessible private reporting channel and its responder before handover.

Areas of particular interest: path traversal in export/serving paths, cache poisoning
via the negotiation headers, and header injection via configurable response headers.
