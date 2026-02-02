"""
Utility functions and decorators for the card builder.
"""

import threading
from functools import wraps
from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable[..., None])


def fire_and_forget(func: F) -> F:
    """Run a method in a background daemon thread.

    The decorated function runs asynchronously and returns immediately.
    The original sync function is preserved as `.sync` for testing/direct calls.

    Usage:
        @fire_and_forget
        def _store_something(self, data):
            # This runs in background thread
            ...

        # Call async (fire-and-forget):
        obj._store_something(data)

        # Call sync (for testing):
        obj._store_something.sync(obj, data)
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        thread = threading.Thread(target=lambda: func(*args, **kwargs), daemon=True)
        thread.start()

    # Preserve sync version for testing
    wrapper.sync = func  # type: ignore[attr-defined]
    return wrapper  # type: ignore[return-value]


__all__ = [
    "fire_and_forget",
    "F",
]
