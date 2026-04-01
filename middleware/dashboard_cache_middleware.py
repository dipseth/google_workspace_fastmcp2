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
from typing import Any, Dict, Optional, Set

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools import ToolResult
from mcp.types import TextContent

from config.enhanced_logging import setup_logger

logger = setup_logger()

# ---------------------------------------------------------------------------
# Module-level cache — shared between middleware and resource handler
# ---------------------------------------------------------------------------

_DASHBOARD_CACHE_TTL = 600  # 10 minutes TTL for Redis entries


@dataclass
class _CacheEntry:
    """Single cached tool result."""

    tool_name: str
    data: dict
    timestamp: float


# tool_name -> _CacheEntry (in-memory fallback, also used as L1 when Redis available)
_result_cache: Dict[str, _CacheEntry] = {}

# Optional Redis store — set from server.py when Redis is configured
_redis_store: Any = None

# Set of tool names we should intercept (populated from _DASHBOARD_CONFIGS keys)
_watched_tools: Set[str] = set()

# Tracks the most recently called dashboard tool (used by _latest resource)
_last_dashboard_tool: Optional[str] = None


def set_redis_store(store: Any) -> None:
    """Set the Redis store for dashboard cache offloading."""
    global _redis_store
    _redis_store = store
    logger.info("Dashboard cache: Redis store configured for offloading")


def register_watched_tools(tool_names: set) -> None:
    """Tell the middleware which tools to cache results for."""
    _watched_tools.update(tool_names)


def get_cached_result(tool_name: str) -> Optional[dict]:
    """Return the last cached result for *tool_name*, or ``None``.

    Checks in-memory cache first; Redis is populated asynchronously
    by the middleware's ``on_call_tool``.
    """
    entry = _result_cache.get(tool_name)
    return entry.data if entry else None


def set_last_dashboard_tool(tool_name: str) -> None:
    """Record the most recently called dashboard tool."""
    global _last_dashboard_tool
    _last_dashboard_tool = tool_name


def get_last_dashboard_tool() -> Optional[str]:
    """Return the most recently called dashboard tool name, or ``None``."""
    return _last_dashboard_tool


def get_cache_age(tool_name: str) -> Optional[float]:
    """Seconds since the result was cached, or ``None`` if not cached."""
    entry = _result_cache.get(tool_name)
    return (time.time() - entry.timestamp) if entry else None


def clear_dashboard_cache() -> int:
    """Clear the in-memory dashboard cache. Returns number of entries cleared."""
    count = len(_result_cache)
    _result_cache.clear()
    if count:
        logger.info(f"Dashboard cache: cleared {count} in-memory entries")
    return count


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
                set_last_dashboard_tool(tool_name)
                # Offload to Redis with TTL when available
                if _redis_store is not None:
                    try:
                        import asyncio

                        asyncio.ensure_future(self._store_to_redis(tool_name, data))
                    except Exception:
                        pass  # Best-effort Redis write

                # Embed a Prefab dashboard directly into the ToolResult's
                # structured_content so VS Code renders it inline — no
                # separate resource fetch (which races the tool execution).
                self._inject_prefab_dashboard(response, tool_name, data)

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
            logger.warning(
                f"📊 Dashboard cache: extraction error for {tool_name}: {exc}"
            )

        return response

    # ------------------------------------------------------------------

    @staticmethod
    async def _store_to_redis(tool_name: str, data: dict) -> None:
        """Best-effort write to Redis with TTL."""
        try:
            await _redis_store.put(
                f"dashboard:{tool_name}",
                {"data": data},
                ttl=_DASHBOARD_CACHE_TTL,
            )
        except Exception as exc:
            logger.debug(f"Dashboard cache Redis write failed for {tool_name}: {exc}")

    @staticmethod
    def _inject_prefab_dashboard(
        response: ToolResult, tool_name: str, data: dict
    ) -> None:
        """Best-effort: build a Prefab DataTable and set it as structured_content.

        This embeds the dashboard directly in the ToolResult so VS Code
        renders it inline alongside the text content.  The text content
        (JSON) is kept for the LLM; the structured_content is rendered
        by VS Code's Prefab renderer.
        """
        try:
            from tools.ui_apps import (
                _build_prefab_data_dashboard,
                get_data_dashboard_config,
            )

            config = get_data_dashboard_config(tool_name)
            prefab = _build_prefab_data_dashboard(tool_name, data, config)
            if prefab is not None:
                response.structured_content = prefab.to_json()
        except Exception as exc:
            logger.debug(
                f"📊 Prefab dashboard injection skipped for {tool_name}: {exc}"
            )

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
