"""
FastMCP Lifespans for Server Lifecycle Management.

This package provides composable lifespans for managing middleware lifecycle
in the FastMCP server. Each lifespan handles initialization on startup and
cleanup on shutdown for a specific middleware or group of middleware.

Lifespan Composition Order (enter left-to-right, exit right-to-left):
1. qdrant_lifespan → Initialize Qdrant, start background reindexing
2. colbert_lifespan → Initialize ColBERT wrapper (if enabled)
3. session_state_lifespan → Setup session filtering middleware
4. cache_middleware_lifespan → Setup template & profile middleware
5. dynamic_instructions_lifespan → Update MCP instructions with Qdrant data

Context Available to Tools:
After lifespan composition, ctx.lifespan_context will contain:
- qdrant_middleware: QdrantUnifiedMiddleware
- colbert_wrapper: ColBERT wrapper (if enabled)
- session_state_managed: True
- cache_middleware_refs: Dict with template_middleware, profile_middleware
- instructions_updated: True/False
"""

from .server_lifespans import (
    cache_middleware_lifespan,
    colbert_lifespan,
    combined_server_lifespan,
    dynamic_instructions_lifespan,
    get_lifespan_state,
    qdrant_lifespan,
    register_profile_middleware,
    register_qdrant_middleware,
    register_template_middleware,
    session_state_lifespan,
)

__all__ = [
    "qdrant_lifespan",
    "colbert_lifespan",
    "session_state_lifespan",
    "cache_middleware_lifespan",
    "dynamic_instructions_lifespan",
    "combined_server_lifespan",
    "register_qdrant_middleware",
    "register_profile_middleware",
    "register_template_middleware",
    "get_lifespan_state",
]
