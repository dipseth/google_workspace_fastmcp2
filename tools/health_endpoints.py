"""Health check endpoints for Docker/Kubernetes monitoring.

This module provides HTTP endpoints for container orchestration health checks,
following Kubernetes best practices with liveness and readiness probes.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from config.settings import settings
from tools.server_tools import health_check as check_server_health

logger = logging.getLogger(__name__)


def setup_health_endpoints(
    mcp: FastMCP, google_auth_provider=None, credential_storage_mode=None
):
    """
    Setup health check endpoints for container orchestration.

    Provides two endpoints following Kubernetes best practices:
    - /health: Comprehensive liveness probe with detailed status
    - /ready: Simple readiness probe for traffic routing

    Args:
        mcp: FastMCP application instance
        google_auth_provider: Optional Google auth provider for health checks
        credential_storage_mode: Current credential storage mode
    """

    @mcp.custom_route("/health", methods=["GET"])
    async def health_endpoint(request: Any):
        """
        Comprehensive health check endpoint for container orchestration.
        Returns detailed server health status including OAuth flows and credentials.
        """
        from starlette.responses import JSONResponse

        logger.info("Health check endpoint called")

        try:
            # Use the comprehensive health check from server_tools
            health_status = await check_server_health(
                google_auth_provider=google_auth_provider,
                credential_storage_mode=credential_storage_mode,
                user_google_email=None,
            )

            # health_status is a HealthCheckResponse Pydantic model —
            # must call .model_dump() to get a JSON-serializable dict
            details = (
                health_status.model_dump()
                if hasattr(health_status, "model_dump")
                else str(health_status)
            )

            return JSONResponse(
                status_code=200,
                content={
                    "status": "healthy",
                    "service": settings.server_name,
                    "version": "1.0.0",
                    "details": details,
                },
            )
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "service": settings.server_name,
                    "error": str(e),
                },
            )

    @mcp.custom_route("/ready", methods=["GET"])
    async def readiness_endpoint(request: Any):
        """
        Readiness probe for Kubernetes - indicates if service can accept traffic.
        This is a lightweight check for container orchestration.
        """
        from starlette.responses import JSONResponse

        try:
            # Basic readiness check - is the server running?
            return JSONResponse(
                status_code=200,
                content={"status": "ready", "service": settings.server_name},
            )
        except Exception as e:
            logger.error(f"Readiness check failed: {e}")
            return JSONResponse(
                status_code=503, content={"status": "not_ready", "error": str(e)}
            )

    logger.info("✅ Health check endpoints registered:")
    logger.info("   • /health - Comprehensive health status (for liveness probe)")
    logger.info("   • /ready - Readiness check (for readiness probe)")
