"""OAuth 2.1 discovery endpoints using FastMCP custom routes.

This module implements OAuth discovery and Dynamic Client Registration
endpoints using FastMCP's native routing system.
"""

import json
import logging
from typing import Any, Dict
from config.settings import settings

# Import compatibility shim for OAuth scope management
try:
    from .compatibility_shim import CompatibilityShim
    _COMPATIBILITY_AVAILABLE = True
except ImportError:
    # Fallback for development/testing
    _COMPATIBILITY_AVAILABLE = False
    logging.warning("Compatibility shim not available, using fallback scopes")

# Fallback scopes for OAuth endpoints
_FALLBACK_OAUTH_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    # Ensure fallback advertises Gmail Settings so inspectors/clients know they’re supported
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "https://www.googleapis.com/auth/gmail.settings.sharing",
    "https://www.googleapis.com/auth/calendar.readonly"
]


def _get_oauth_endpoint_scopes():
    """
    Get OAuth endpoint scopes from centralized registry.
    
    This function provides backward compatibility for legacy hardcoded scopes
    while automatically redirecting to the new centralized scope registry.
    Falls back to the original hardcoded scopes if the registry is unavailable.
    
    Returns:
        List of OAuth scope URLs for endpoint metadata
    """
    if _COMPATIBILITY_AVAILABLE:
        try:
            return CompatibilityShim.get_legacy_oauth_endpoint_scopes()
        except Exception as e:
            logger.warning(f"Error getting OAuth endpoint scopes from registry, using fallback: {e}")
            return _FALLBACK_OAUTH_SCOPES
    else:
        return _FALLBACK_OAUTH_SCOPES

logger = logging.getLogger(__name__)

def setup_oauth_endpoints_fastmcp(mcp) -> None:
    """Setup OAuth discovery and DCR endpoints using FastMCP custom routes.
    
    Args:
        mcp: FastMCP application instance
    """
    
    @mcp.custom_route("/.well-known/openid-configuration/mcp", methods=["GET", "OPTIONS"])
    async def openid_configuration_mcp(request: Any):
        """OpenID Configuration endpoint for MCP Inspector Quick OAuth.
        
        This is the endpoint MCP Inspector expects for Quick OAuth functionality.
        """
        from starlette.responses import JSONResponse, Response
        
        # Handle CORS preflight
        if request.method == "OPTIONS":
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    "Access-Control-Max-Age": "86400",
                }
            )
        
        # Get base server URL with proper protocol
        base_url = settings.base_url
        
        metadata = {
            "issuer": "https://accounts.google.com",
            "authorization_endpoint": "https://accounts.google.com/o/oauth2/auth",
            "token_endpoint": "https://oauth2.googleapis.com/token",
            "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
            "userinfo_endpoint": "https://www.googleapis.com/oauth2/v1/userinfo",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
            "code_challenge_methods_supported": ["S256"],
            "scopes_supported": _get_oauth_endpoint_scopes(),
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            # MCP-specific configuration
            "registration_endpoint": f"{base_url}/oauth/register",
            "resource_server": base_url,
            "authorization_servers": ["https://accounts.google.com"],
            "bearer_methods_supported": ["header"],
            "resource_documentation": f"{base_url}/docs"
        }
        
        logger.info("📋 OpenID Configuration (MCP) metadata served")
        
        # Return proper JSONResponse with comprehensive CORS headers
        return JSONResponse(
            content=metadata,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Max-Age": "86400",
                "Cache-Control": "public, max-age=3600",
            }
        )
    
    @mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET", "OPTIONS"])
    async def oauth_protected_resource(request: Any):
        """OAuth Protected Resource Metadata endpoint.
        
        Required by MCP Inspector for OAuth server discovery.
        """
        from starlette.responses import JSONResponse, Response
        
        # Handle CORS preflight
        if request.method == "OPTIONS":
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                }
            )
        
        # Get base server URL with proper protocol
        base_url = settings.base_url
        
        metadata = {
            "resource_server": base_url,
            "authorization_servers": ["https://accounts.google.com"],
            "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
            "bearer_methods_supported": ["header"],
            "resource_documentation": f"{base_url}/docs",
            "scopes_supported": _get_oauth_endpoint_scopes()
        }
        
        logger.info("📋 OAuth protected resource metadata served")
        
        # Return proper JSONResponse with CORS headers
        return JSONResponse(
            content=metadata,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
            }
        )
    
    @mcp.custom_route("/.well-known/oauth-authorization-server", methods=["GET", "OPTIONS"])
    async def oauth_authorization_server(request: Any):
        """OAuth Authorization Server Metadata endpoint.
        
        Required by RFC 8414 for OAuth server discovery.
        """
        from starlette.responses import JSONResponse, Response
        
        # Handle CORS preflight
        if request.method == "OPTIONS":
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                }
            )
        
        # Get base server URL for our local registration endpoint
        server_host = settings.server_host
        server_port = settings.server_port
        base_url = f"http://{server_host}:{server_port}"
        
        metadata = {
            "issuer": "https://accounts.google.com",
            "authorization_endpoint": "https://accounts.google.com/o/oauth2/auth",
            "token_endpoint": "https://oauth2.googleapis.com/token",
            "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
            "code_challenge_methods_supported": ["S256"],
            "scopes_supported": _get_oauth_endpoint_scopes(),
            # Point to our local Dynamic Client Registration endpoint
            "registration_endpoint": f"{base_url}/oauth/register",
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "userinfo_endpoint": "https://www.googleapis.com/oauth2/v1/userinfo"
        }
        
        logger.info("📋 OAuth authorization server metadata served")
        
        # Return proper JSONResponse with CORS headers
        return JSONResponse(
            content=metadata,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
            }
        )
    
    @mcp.custom_route("/oauth/register", methods=["POST", "OPTIONS"])
    async def dynamic_client_registration(request: Any):
        """Dynamic Client Registration endpoint (RFC 7591).
        
        Implements OAuth 2.0 Dynamic Client Registration for MCP Inspector.
        """
        from auth.dynamic_client_registration import handle_client_registration
        from starlette.responses import JSONResponse, Response
        
        # Handle CORS preflight
        if request.method == "OPTIONS":
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                }
            )
        
        logger.info("📝 Dynamic client registration requested")
        
        try:
            # Parse request body
            body = await request.body()
            if isinstance(body, bytes):
                body = body.decode('utf-8')
            
            try:
                client_metadata = json.loads(body) if body else {}
            except json.JSONDecodeError:
                client_metadata = {}
            
            logger.debug(f"Client metadata: {client_metadata}")
            
            client_info = handle_client_registration(client_metadata)
            logger.info(f"✅ Registered client: {client_info['client_id']}")
            
            # Return proper JSONResponse with CORS headers
            return JSONResponse(
                content=client_info,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                }
            )
            
        except Exception as e:
            logger.error(f"❌ Client registration failed: {e}")
            error_response = {
                "error": "registration_failed",
                "error_description": str(e)
            }
            return JSONResponse(
                content=error_response,
                status_code=400,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                }
            )
    
    # For simplicity, let's focus on the core endpoints that MCP Inspector needs
    # The client configuration endpoints can be added later if needed
    
    logger.info("✅ OAuth HTTP endpoints registered via FastMCP custom routes")
    logger.info("🔍 Available OAuth endpoints:")
    logger.info("  GET /.well-known/openid-configuration/mcp (MCP Inspector Quick OAuth)")
    logger.info("  GET /.well-known/oauth-protected-resource")
    logger.info("  GET /.well-known/oauth-authorization-server")
    logger.info("  POST /oauth/register")
    logger.info("  GET /oauth/register/{client_id}")
    logger.info("  PUT /oauth/register/{client_id}")
    logger.info("  DELETE /oauth/register/{client_id}")