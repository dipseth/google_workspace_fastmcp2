"""
Resource Provider for Cloudflare Tunnel Integration.

This module provides MCP resources for accessing tunnel information.
"""

import logging
from typing_extensions import Any, Dict, List, Optional

from .tunnel_manager import TunnelManager

logger = logging.getLogger(__name__)


class TunnelResourceProvider:
    """Provider for tunnel-related MCP resources."""
    
    def __init__(self, mcp_server):
        """
        Initialize the tunnel resource provider.
        
        Args:
            mcp_server: The MCP server instance
        """
        self.mcp_server = mcp_server
        self.tunnel_manager = TunnelManager.get_instance()
        self._register_resources()
        logger.info("TunnelResourceProvider initialized")
    
    def _register_resources(self) -> None:
        """Register all tunnel-related resources with the MCP server."""
        # Register resource handlers
        self.mcp_server.register_resource_handler("tunnel://status", self._handle_status_resource)
        self.mcp_server.register_resource_handler("tunnel://url", self._handle_url_resource)
        self.mcp_server.register_resource_handler("tunnel://config", self._handle_config_resource)
        self.mcp_server.register_resource_handler("tunnel://metrics", self._handle_metrics_resource)
        
        logger.info("Registered tunnel resources")
    
    async def _handle_status_resource(self, uri: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle requests for the tunnel status resource.
        
        Args:
            uri: The resource URI
            params: Resource parameters
            
        Returns:
            Dict containing the tunnel status
        """
        status = self.tunnel_manager.get_status()
        return {
            "status": status["status"],
            "error": status["error"],
            "active": status["status"] == "active"
        }
    
    async def _handle_url_resource(self, uri: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle requests for the tunnel URL resource.
        
        Args:
            uri: The resource URI
            params: Resource parameters
            
        Returns:
            Dict containing the tunnel URL
        """
        status = self.tunnel_manager.get_status()
        return {
            "url": status["url"],
            "available": status["url"] is not None
        }
    
    async def _handle_config_resource(self, uri: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle requests for the tunnel configuration resource.
        
        Args:
            uri: The resource URI
            params: Resource parameters
            
        Returns:
            Dict containing the tunnel configuration
        """
        status = self.tunnel_manager.get_status()
        
        # Get process controller for additional details
        process_controller = self.tunnel_manager.process_controller
        
        return {
            "status": status["status"],
            "pid": status["pid"],
            "url": status["url"],
            "local_url": "http://localhost:8002/mcp",  # Default value, could be stored in process_controller
            "cloudflared_version": self._get_cloudflared_version()
        }
    
    async def _handle_metrics_resource(self, uri: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle requests for the tunnel metrics resource.
        
        Args:
            uri: The resource URI
            params: Resource parameters
            
        Returns:
            Dict containing the tunnel metrics
        """
        status = self.tunnel_manager.get_status()
        
        return {
            "status": status["status"],
            "uptime_seconds": status["uptime_seconds"] or 0,
            "active": status["status"] == "active"
        }
    
    def _get_cloudflared_version(self) -> Optional[str]:
        """
        Get the installed cloudflared version.
        
        Returns:
            The cloudflared version string, or None if not available
        """
        try:
            import subprocess
            result = subprocess.run(
                ["cloudflared", "version"],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                # Extract version from output
                version_line = result.stdout.strip()
                return version_line
            return None
        except Exception as e:
            logger.error(f"Error getting cloudflared version: {e}")
            return None


def register_resources(mcp_server) -> TunnelResourceProvider:
    """
    Register tunnel resources with the MCP server.
    
    Args:
        mcp_server: The MCP server instance
        
    Returns:
        The TunnelResourceProvider instance
    """
    provider = TunnelResourceProvider(mcp_server)
    return provider