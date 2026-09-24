"""StreamField → Markdown rendering.

Public API: register_renderer (decorator), render_block (render a child block
from a renderer), render_page and PageRenderError. See docs/custom-blocks.md.
"""

from .registry import register_renderer

__all__ = ["PageRenderError", "register_renderer", "render_block", "render_page"]


def __getattr__(name):
    # Projects import the decorator during AppConfig.ready() autodiscovery.
    # Load block/page/model-dependent code only when it is requested.
    if name == "render_block":
        from .blocks import render_block

        return render_block
    if name in {"render_page", "PageRenderError"}:
        from .page import PageRenderError, render_page

        return {"render_page": render_page, "PageRenderError": PageRenderError}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
