"""Sandbox project renderers, autodiscovered at startup like wagtail_hooks.py (#8)."""

from wagtail_markdown_agents.rendering import register_renderer


@register_renderer(block_name="sandbox_autodiscovered")
def render_sandbox(block, value, context) -> str:
    return f"sandbox: {value}"
