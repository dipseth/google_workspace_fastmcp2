"""
Dashboard Cache Middleware — caches list-tool results for ``ui://data-dashboard``
resources so the generic data dashboard can serve live data without touching
individual tool files.

Usage in ``server.py``::

    from middleware.dashboard_cache_middleware import DashboardCacheMiddleware

    dashboard_mw = DashboardCacheMiddleware()
    mcp.add_middleware(dashboard_mw)

The companion resource handler in ``tools/ui_apps.py`` reads from the shared
cache via :func:`get_cached_result`.
"""

import json
import time
from dataclasses import dataclass
from typing import Dict, Optional, Set

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from config.enhanced_logging import setup_logger

logger = setup_logger()

# ---------------------------------------------------------------------------
# Module-level cache — shared between middleware and resource handler
# ---------------------------------------------------------------------------


@dataclass
class _CacheEntry:
    """Single cached tool result."""

    tool_name: str
    data: dict
    timestamp: float


# tool_name -> _CacheEntry
_result_cache: Dict[str, _CacheEntry] = {}

# Set of tool names we should intercept (populated from _DASHBOARD_CONFIGS keys)
_watched_tools: Set[str] = set()


def register_watched_tools(tool_names: set) -> None:
    """Tell the middleware which tools to cache results for."""
    _watched_tools.update(tool_names)


def get_cached_result(tool_name: str) -> Optional[dict]:
    """Return the last cached result for *tool_name*, or ``None``."""
    entry = _result_cache.get(tool_name)
    return entry.data if entry else None


def get_cache_age(tool_name: str) -> Optional[float]:
    """Seconds since the result was cached, or ``None`` if not cached."""
    entry = _result_cache.get(tool_name)
    return (time.time() - entry.timestamp) if entry else None


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class DashboardCacheMiddleware(Middleware):
    """Intercepts list-tool calls and caches results for the data dashboard.

    The cache is intentionally simple (last-result-per-tool, no TTL eviction)
    because the resource is only read when a user opens the dashboard, and a
    fresh tool call always overwrites the cache.
    """

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        tool_name = context.message.name

        # Fast path: not a watched tool
        if tool_name not in _watched_tools:
            return await call_next(context)

        # Execute the tool normally
        response = await call_next(context)

        # Extract the dict/JSON data from the ToolResult
        try:
            data = self._extract_data(response)
            if data is not None:
                _result_cache[tool_name] = _CacheEntry(
                    tool_name=tool_name,
                    data=data,
                    timestamp=time.time(),
                )
                logger.info(
                    f"📊 Dashboard cache updated for {tool_name} "
                    f"({len(str(data))} chars)"
                )
            else:
                logger.warning(
                    f"📊 Dashboard cache: _extract_data returned None for {tool_name}. "
                    f"response type={type(response).__name__}, "
                    f"content type={type(response.content).__name__}, "
                    f"structured_content type={type(response.structured_content).__name__}"
                )
        except Exception as exc:
            logger.warning(f"📊 Dashboard cache: extraction error for {tool_name}: {exc}")

        return response

    # ------------------------------------------------------------------

    @staticmethod
    def _extract_data(response: ToolResult) -> Optional[dict]:
        """Extract a JSON-serializable dict from a ToolResult.

        Tries structured_content first (FastMCP 3.0 output_schema), then
        falls back to parsing TextContent blocks as JSON.
        """
        # 1. structured_content is the cleanest path (FastMCP 3.0 output_schema)
        if isinstance(response.structured_content, dict):
            return response.structured_content

        # 2. content — list of content blocks; look for TextContent with JSON
        for block in response.content:
            if isinstance(block, TextContent) and block.text:
                try:
                    parsed = json.loads(block.text)
                    if isinstance(parsed, dict):
                        return parsed
                except (json.JSONDecodeError, ValueError):
                    continue

        return None
