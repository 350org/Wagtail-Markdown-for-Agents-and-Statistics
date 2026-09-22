"""Serve Wagtail content to AI agents as Markdown.

Static export, llms.txt, and HTTP content negotiation for Wagtail sites.
"""

__version__ = "0.1.0.dev0"

#: OKF spec pin, emitted in the root index frontmatter. Review against the
#: current OKF spec on every major release.
OKF_VERSION = "0.1"
