"""Hide app-only tools from clients that cannot render MCP Apps.

FastMCP 4 lists every tool in ``tools/list`` and leaves ``meta.ui.visibility``
filtering to the host (the mcp-apps spec puts it there). Hosts without the UI
extension (Code Mode, plain MCP clients) never filter, so backend tools such as
the dashboard ``dashboard_rows`` fetcher would be offered to the model. This
middleware applies the app-visibility rule server-side whenever the connected
client does not advertise ``io.modelcontextprotocol/ui``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

from config.enhanced_logging import setup_logger

logger = setup_logger()


def is_app_only(tool: Any) -> bool:
    """True when ``meta.ui.visibility`` exists and does not include ``"model"``."""
    meta = getattr(tool, "meta", None) or {}
    ui = meta.get("ui") if isinstance(meta, dict) else None
    if not isinstance(ui, dict):
        return False
    visibility = ui.get("visibility")
    if not isinstance(visibility, list):
        return False
    return "model" not in visibility


def _client_renders_apps(context: MiddlewareContext) -> bool:
    try:
        from fastmcp.apps.config import UI_EXTENSION_ID

        ctx = context.fastmcp_context
        return bool(ctx and ctx.client_supports_extension(UI_EXTENSION_ID))
    except Exception:
        return False


class AppVisibilityMiddleware(Middleware):
    """Drop app-only tools from ``tools/list`` for non-UI clients."""

    async def on_list_tools(
        self, context: MiddlewareContext, call_next
    ) -> Sequence[Any]:
        tools = await call_next(context)
        if _client_renders_apps(context):
            return tools
        visible = [t for t in tools if not is_app_only(t)]
        hidden = len(tools) - len(visible)
        if hidden:
            logger.debug(f"AppVisibilityMiddleware: hid {hidden} app-only tool(s)")
        return visible


__all__ = ["AppVisibilityMiddleware", "is_app_only"]
