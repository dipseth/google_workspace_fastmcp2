"""MCP Authentication Middleware implementing MCP spec 2025-06-18.

This middleware ensures proper WWW-Authenticate headers are returned
on 401 responses to trigger OAuth discovery flow in MCP clients.
"""

import logging
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext
from config.settings import settings

logger = logging.getLogger(__name__)


class MCPAuthMiddleware(Middleware):
    """Middleware to ensure MCP spec compliance for OAuth discovery."""
    
    def __init__(self):
        """Initialize MCP authentication middleware."""
        self.resource_metadata_url = f"http://{settings.server_host}:{settings.server_port}/.well-known/oauth-protected-resource"
        self.www_authenticate_header = f'Bearer realm="MCP", resource_metadata="{self.resource_metadata_url}"'
        logger.info(f"🔐 MCP Auth Middleware initialized with resource metadata: {self.resource_metadata_url}")
    
    async def on_request(self, context: MiddlewareContext, call_next):
        """Handle HTTP requests and add WWW-Authenticate header on 401 responses."""
        try:
            response = await call_next(context)
            
            # Check if this is a 401 response that needs WWW-Authenticate header
            if hasattr(response, 'status_code') and response.status_code == 401:
                logger.info("🔒 Adding WWW-Authenticate header to 401 response for MCP spec compliance")
                
                # Add the required WWW-Authenticate header
                if hasattr(response, 'headers'):
                    response.headers['WWW-Authenticate'] = self.www_authenticate_header
                    logger.debug(f"Added WWW-Authenticate: {self.www_authenticate_header}")
                else:
                    logger.warning("Cannot add WWW-Authenticate header: response has no headers attribute")
            
            return response
            
        except Exception as e:
            logger.error(f"Error in MCP auth middleware: {e}")
            raise
    
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """Handle tool calls and ensure proper authentication flow."""
        try:
            result = await call_next(context)
            return result
        except Exception as e:
            # If it's an authentication error, we let it bubble up to on_request
            # where it will be handled with proper WWW-Authenticate headers
            logger.debug(f"Authentication error in tool call: {e}")
            raise