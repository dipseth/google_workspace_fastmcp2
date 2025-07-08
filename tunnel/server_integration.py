"""
Server Integration for Cloudflare Tunnel Integration.

This module provides functions for integrating the tunnel components with the
FastMCP2 server.
"""

import logging
from typing import Any, Dict, Optional

from .tunnel_manager import TunnelManager, initialize as initialize_manager
from .resource_provider import register_resources
from .tool_provider import setup_tunnel_tools
from .utils import check_cloudflared_installed, get_cloudflared_version

logger = logging.getLogger(__name__)


def initialize_tunnel_integration(mcp_server) -> Dict[str, Any]:
    """
    Initialize the Cloudflare tunnel integration with the FastMCP2 server.
    
    This function should be called during server startup to initialize all
    tunnel components, including the tunnel manager, resource provider, and
    tool provider.
    
    Args:
        mcp_server: The MCP server instance
        
    Returns:
        Dict containing initialization status and information
    """
    logger.info("Initializing Cloudflare tunnel integration")
    
    # Check if cloudflared is installed
    cloudflared_installed = check_cloudflared_installed()
    cloudflared_version = get_cloudflared_version() if cloudflared_installed else None
    
    # Initialize the tunnel manager
    tunnel_manager = initialize_manager()
    
    # Register resources
    resource_provider = register_resources(mcp_server)
    
    # Register tools using the new FastMCP2 pattern
    setup_tunnel_tools(mcp_server)
    
    # Log initialization status
    if cloudflared_installed:
        logger.info(f"Cloudflare tunnel integration initialized successfully (cloudflared version: {cloudflared_version})")
    else:
        logger.warning("Cloudflare tunnel integration initialized, but cloudflared is not installed")
    
    return {
        "status": "success",
        "cloudflared_installed": cloudflared_installed,
        "cloudflared_version": cloudflared_version,
        "components": {
            "tunnel_manager": tunnel_manager is not None,
            "resource_provider": resource_provider is not None,
            "tools_registered": True
        }
    }


def get_tunnel_health() -> Dict[str, Any]:
    """
    Get the health status of the tunnel integration.
    
    This function can be called by the server's health check endpoint to
    include tunnel status in the overall health report.
    
    Returns:
        Dict containing health status information
    """
    try:
        # Get the tunnel manager instance
        tunnel_manager = TunnelManager.get_instance()
        
        # Get the tunnel status
        status = tunnel_manager.get_status()
        
        # Check if cloudflared is installed
        cloudflared_installed = check_cloudflared_installed()
        cloudflared_version = get_cloudflared_version() if cloudflared_installed else None
        
        return {
            "status": "healthy",
            "tunnel_status": status["status"],
            "tunnel_active": status["status"] == "active",
            "tunnel_url": status["url"],
            "cloudflared_installed": cloudflared_installed,
            "cloudflared_version": cloudflared_version
        }
    except Exception as e:
        logger.error(f"Error getting tunnel health: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }