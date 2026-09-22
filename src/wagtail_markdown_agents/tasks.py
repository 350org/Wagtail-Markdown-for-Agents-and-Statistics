"""Task seam.

Every deferred-able unit of work goes through enqueue(). The default backend
runs inline (synchronous, v0.1); v0.2 adds a django-tasks/Celery backend with
coalescing keys to debounce bundle rebuilds (E6).
"""

from collections.abc import Callable
from typing import Any


def enqueue(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run ``fn`` via the configured backend. Default: inline."""
    return fn(*args, **kwargs)
