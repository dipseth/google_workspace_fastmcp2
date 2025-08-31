"""
Tool Provider for Cloudflare Tunnel Integration.

This module provides MCP tools for managing Cloudflare tunnels.
Implements the FastMCP2 architecture with decorator-based tool registration.
"""

import logging
from typing_extensions import Dict, Optional, Union, Callable, Any

from fastmcp import FastMCP

from .tunnel_manager import TunnelManager

logger = logging.getLogger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _get_tunnel_manager():
    """Get the singleton TunnelManager instance."""
    return TunnelManager.get_instance()


# ============================================================================
# FUNCTION REFERENCES FOR BACKWARD COMPATIBILITY
# ============================================================================

# These will be populated by setup_tunnel_tools
start_tunnel: Callable = None
stop_tunnel: Callable = None
get_tunnel_status: Callable = None


# ============================================================================
# MAIN TOOL FUNCTIONS
# ============================================================================

def setup_tunnel_tools(mcp: FastMCP) -> None:
    """
    Setup and register all Cloudflare tunnel tools with the MCP server.
    
    Args:
        mcp: The FastMCP server instance to register tools with
    """
    logger.info("Setting up Cloudflare tunnel tools")
    
    # Make the functions available at module level for backward compatibility
    global start_tunnel, stop_tunnel, get_tunnel_status
    
    @mcp.tool(
        name="start_tunnel",
        description="Starts a Cloudflare tunnel pointing to the local MCP server",
        tags={"cloudflare", "tunnel", "networking", "expose"},
        annotations={
            "title": "Start Cloudflare Tunnel",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def start_tunnel_impl(
        port: Optional[int] = 8002,
        host: str = "localhost",
        path: str = "/mcp"
    ) -> Dict[str, Union[str, int]]:
        """
        Start a new Cloudflare tunnel pointing to the local MCP server.
        
        This tool starts a cloudflared process that creates a secure tunnel from
        the public internet to your local MCP server. The tunnel generates a random
        subdomain on trycloudflare.com that you can share with others to access your
        local MCP server.
        
        Args:
            port: The local port where the MCP server is running (default: 8002)
            host: The local host where the MCP server is running (default: localhost)
            path: The path to the MCP endpoint (default: /mcp)
            
        Returns:
            Dict containing tunnel information including status, URL, and process ID
            
        Example:
            ```python
            result = await start_tunnel(port=8002)
            print(f"Tunnel URL: {result['url']}")
            ```
        """
        # Construct the local URL
        local_url = f"http://{host}:{port}{path}"
        
        # Get the tunnel manager instance
        tunnel_manager = _get_tunnel_manager()
        
        try:
            # Start the tunnel
            result = await tunnel_manager.start_tunnel(local_url)
            
            # Enhance the result with user-friendly messages
            if result["status"] == "active":
                result["message"] = (
                    f"✅ Tunnel started successfully!\n"
                    f"📡 Your local MCP server is now accessible at: {result['url']}\n"
                    f"🔗 You can share this URL with others to access your local MCP server.\n"
                    f"⚠️ Note: This URL is temporary and will be deactivated when the tunnel is stopped."
                )
            
            return result
        except Exception as e:
            logger.error(f"Error starting tunnel: {e}")
            return {
                "status": "error",
                "message": f"Failed to start tunnel: {str(e)}",
                "error": str(e)
            }
    
    @mcp.tool(
        name="stop_tunnel",
        description="Stops a running Cloudflare tunnel",
        tags={"cloudflare", "tunnel", "networking", "terminate"},
        annotations={
            "title": "Stop Cloudflare Tunnel",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def stop_tunnel_impl() -> Dict[str, str]:
        """
        Stop the running Cloudflare tunnel.
        
        This tool stops the cloudflared process and terminates the tunnel,
        making your local MCP server inaccessible from the public internet.
        
        Returns:
            Dict containing status information
            
        Example:
            ```python
            result = await stop_tunnel()
            print(result["message"])
            ```
        """
        # Get the tunnel manager instance
        tunnel_manager = _get_tunnel_manager()
        
        try:
            # Stop the tunnel
            result = await tunnel_manager.stop_tunnel()
            
            # Enhance the result with user-friendly messages
            if result["status"] == "inactive":
                result["message"] = "✅ Tunnel stopped successfully. Your local MCP server is no longer accessible from the public internet."
            
            return result
        except Exception as e:
            logger.error(f"Error stopping tunnel: {e}")
            return {
                "status": "error",
                "message": f"Failed to stop tunnel: {str(e)}",
                "error": str(e)
            }
    
    @mcp.tool(
        name="get_tunnel_status",
        description="Gets the status of a Cloudflare tunnel",
        tags={"cloudflare", "tunnel", "networking", "status", "info"},
        annotations={
            "title": "Get Cloudflare Tunnel Status",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def get_tunnel_status_impl() -> Dict[str, Union[str, int, None]]:
        """
        Get the current status of the Cloudflare tunnel.
        
        This tool retrieves detailed information about the current state of the
        tunnel, including its status, URL, process ID, and uptime.
        
        Returns:
            Dict containing status information
            
        Example:
            ```python
            status = await get_tunnel_status()
            if status["status"] == "active":
                print(f"Tunnel is active at {status['url']}")
            else:
                print("No active tunnel")
            ```
        """
        # Get the tunnel manager instance
        tunnel_manager = _get_tunnel_manager()
        
        try:
            # Get the status
            status = tunnel_manager.get_status()
            
            # Enhance the result with user-friendly messages
            if status["status"] == "active":
                status["message"] = (
                    f"✅ Tunnel is active\n"
                    f"📡 URL: {status['url']}\n"
                    f"⏱️ Uptime: {status['uptime_seconds'] or 0} seconds"
                )
            elif status["status"] == "inactive":
                status["message"] = "❌ No active tunnel. Use start_tunnel to create a new tunnel."
            elif status["status"] == "error":
                status["message"] = f"❌ Tunnel error: {status['error']}"
            elif status["status"] == "starting":
                status["message"] = "🔄 Tunnel is starting..."
            elif status["status"] == "stopping":
                status["message"] = "🔄 Tunnel is stopping..."
            
            return status
        except Exception as e:
            logger.error(f"Error getting tunnel status: {e}")
            return {
                "status": "error",
                "message": f"Failed to get tunnel status: {str(e)}",
                "error": str(e)
            }
    
    # Assign the implementations to the module-level variables for backward compatibility
    start_tunnel = start_tunnel_impl
    stop_tunnel = stop_tunnel_impl
    get_tunnel_status = get_tunnel_status_impl
    
    # Log successful setup
    tool_count = 3  # Total number of tunnel tools
    logger.info(f"Successfully registered {tool_count} Cloudflare tunnel tools")