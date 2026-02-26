"""
Strict mode for card builder development.

When CARD_BUILDER_STRICT is enabled (env var set to 1/true/yes),
component resolution failures emit WARNING-level logs with full
tracebacks instead of silently returning None.

Production behavior is unchanged — cards still render what they can.

Usage:
    CARD_BUILDER_STRICT=1 uv run python my_script.py
"""

import logging
import os
import traceback

logger = logging.getLogger("card_builder.strict")

CARD_BUILDER_STRICT: bool = os.environ.get(
    "CARD_BUILDER_STRICT", ""
).lower() in ("1", "true", "yes")


def warn_strict(message: str) -> None:
    """Log a WARNING with traceback when strict mode is enabled."""
    if CARD_BUILDER_STRICT:
        stack = "".join(traceback.format_stack()[:-1])
        logger.warning(f"[STRICT] {message}\n{stack}")
