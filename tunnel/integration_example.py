"""
Integration Example for Cloudflare Tunnel Integration.

This module demonstrates how to integrate the Cloudflare tunnel components
with the FastMCP2 server.
"""

import logging
from typing import Dict, Any

# Import the FastMCP2 server
# from fastmcp2_drive_upload.server import app, mcp_server

# Import the tunnel integration
from tunnel import initialize_tunnel_integration, get_tunnel_health

logger = logging.getLogger(__name__)


def integrate_with_fastmcp2_server(mcp_server) -> Dict[str, Any]:
    """
    Integrate the Cloudflare tunnel with the FastMCP2 server.
    
    This function should be called during server initialization to set up
    the tunnel integration.
    
    Args:
        mcp_server: The MCP server instance
        
    Returns:
        Dict containing initialization status and information
    """
    # Initialize the tunnel integration
    result = initialize_tunnel_integration(mcp_server)
    
    # Add tunnel health check to server health endpoint
    if hasattr(mcp_server, 'add_health_check'):
        mcp_server.add_health_check('tunnel', get_tunnel_health)
        logger.info("Added tunnel health check to server health endpoint")
    
    return result


# Example usage in server.py:
"""
# In server.py or similar main file

import logging
from fastmcp2_drive_upload.tunnel.integration_example import integrate_with_fastmcp2_server

logger = logging.getLogger(__name__)

# Initialize the MCP server
app = FastMCP()
mcp_server = app.server

# ... other initialization code ...

# Initialize the tunnel integration
try:
    tunnel_result = integrate_with_fastmcp2_server(mcp_server)
    logger.info(f"Tunnel integration initialized: {tunnel_result['status']}")
    
    if not tunnel_result['cloudflared_installed']:
        logger.warning("cloudflared is not installed. Tunnel functionality will be limited.")
except Exception as e:
    logger.error(f"Error initializing tunnel integration: {e}")
    # Continue server startup even if tunnel integration fails

# ... rest of server initialization ...

# Start the server
app.run()
"""