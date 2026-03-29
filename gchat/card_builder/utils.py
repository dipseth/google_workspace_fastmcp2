"""
Utility functions and decorators for the card builder.
"""

import json
import re
import threading
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

from config.enhanced_logging import setup_logger

logger = setup_logger()

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

def coerce_json_param(value: Any, param_name: str = "params") -> Dict[str, Any]:
    """Coerce a JSON string parameter to a dict.

    MCP wire format sends complex objects as JSON strings. This handles:
        - Already a dict -> returned as-is
        - JSON string -> parsed to dict
        - None -> empty dict
        - Invalid JSON -> empty dict with warning

    Args:
        value: The parameter value (string, dict, or None).
        param_name: Name for logging on parse failure.

    Returns:
        Dict, always non-None.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
            logger.warning(
                f"{param_name} parsed to {type(parsed).__name__}, expected dict"
            )
            return {}
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Could not parse {param_name} as JSON: {value!r}")
            return {}
    if value is None:
        return {}
    logger.warning(f"Unexpected type for {param_name}: {type(value).__name__}")
    return {}

def extract_urls_from_text(
    text: str,
) -> Tuple[List[Dict[str, str]], Optional[str]]:
    """Extract URLs from text and return as button dicts.

    When text contains URLs, extracts them as button definitions with labels
    derived from URL paths, and returns the cleaned text (URLs removed).

    Args:
        text: Text potentially containing URLs

    Returns:
        Tuple of (list of button dicts [{text, url}], cleaned text or None)
    """
    urls = re.findall(r"https?://[^\s,\)]+", text)
    if not urls:
        return [], None

    buttons = []
    for url in urls:
        path_parts = url.rstrip("/").split("/")
        label = (
            path_parts[-1] if len(path_parts) > 3 else url.split("//")[1].split("/")[0]
        )
        buttons.append({"text": label, "url": url})

    # Clean text by removing URLs
    clean_text = re.sub(r"https?://[^\s,\)]+", "", text).strip()
    clean_text = re.sub(r"\s+", " ", clean_text).strip(" .,;:")

    return buttons, clean_text if clean_text else None

__all__ = [
    "fire_and_forget",
    "coerce_json_param",
    "extract_urls_from_text",
    "F",
]
