"""StreamField → Markdown rendering.

Public API: register_renderer (decorator), render_page and PageRenderError.
"""

from .registry import register_renderer

__all__ = ["PageRenderError", "register_renderer", "render_page"]


def __getattr__(name):
    # Projects import the decorator during AppConfig.ready() autodiscovery.
    # Load page/model-dependent orchestration only when it is requested.
    if name in {"render_page", "PageRenderError"}:
        from .page import PageRenderError, render_page

        return {"render_page": render_page, "PageRenderError": PageRenderError}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
