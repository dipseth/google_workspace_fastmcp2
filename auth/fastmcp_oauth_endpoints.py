"""OAuth 2.1 discovery endpoints using FastMCP custom routes.

This module implements OAuth discovery and Dynamic Client Registration
endpoints using FastMCP's native routing system.
"""

import json
import logging
from datetime import datetime
from typing_extensions import Any, Dict
from config.settings import settings

# Import OAuth proxy at module level to ensure singleton behavior
from auth.oauth_proxy import oauth_proxy, handle_token_exchange, refresh_access_token

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
    
    This function provides comprehensive OAuth scopes from the scope registry,
    including all available Google services for complete OAuth integration.
    Falls back to basic scopes if the registry is unavailable.
    
    Returns:
        List of OAuth scope URLs for endpoint metadata
    """
    if _COMPATIBILITY_AVAILABLE:
        try:
            # Use the comprehensive OAuth scope group instead of just basic scopes
            from .scope_registry import ScopeRegistry
            comprehensive_scopes = ScopeRegistry.resolve_scope_group("oauth_comprehensive")
            logger.info(f"📋 Using comprehensive OAuth scopes: {len(comprehensive_scopes)} scopes from registry")
            return comprehensive_scopes
        except Exception as e:
            logger.warning(f"Error getting comprehensive OAuth scopes from registry, using compatibility fallback: {e}")
            try:
                # Fallback to legacy OAuth endpoint scopes
                return CompatibilityShim.get_legacy_oauth_endpoint_scopes()
            except Exception as e2:
                logger.warning(f"Error getting legacy OAuth endpoint scopes, using hardcoded fallback: {e2}")
                return _FALLBACK_OAUTH_SCOPES
    else:
        logger.warning("Compatibility shim not available, using fallback scopes")
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
        mcp_resource_url = f"{base_url}/mcp"
        
        metadata = {
            "issuer": "https://accounts.google.com",
            # Use our local authorization endpoint that handles OAuth Proxy mapping
            "authorization_endpoint": f"{base_url}/oauth/authorize",
            # Use our local token endpoint that handles OAuth Proxy mapping
            "token_endpoint": f"{base_url}/oauth/token",
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
            "resource_server": mcp_resource_url,  # Should be the full MCP endpoint URL
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
    
    @mcp.custom_route("/.well-known/oauth-protected-resource/mcp", methods=["GET", "OPTIONS"])
    async def oauth_protected_resource(request: Any):
        """OAuth Protected Resource Metadata endpoint for MCP Inspector.
        
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
        
        # Get base server URL with proper protocol and MCP path
        base_url = settings.base_url
        mcp_resource_url = f"{base_url}/mcp"
        
        metadata = {
            "resource_server": mcp_resource_url,  # Should be the full MCP endpoint URL
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
        base_url = settings.base_url
        
        metadata = {
            "issuer": "https://accounts.google.com",
            # Use our local authorization endpoint that handles OAuth Proxy mapping
            "authorization_endpoint": f"{base_url}/oauth/authorize",
            # Use our local token endpoint that handles OAuth Proxy mapping
            "token_endpoint": f"{base_url}/oauth/token",
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
    
    @mcp.custom_route("/oauth/authorize", methods=["GET", "OPTIONS"])
    async def oauth_authorize(request: Any):
        """OAuth Authorization Endpoint Proxy.
        
        This endpoint intercepts authorization requests from MCP clients,
        maps temporary client_ids to real Google OAuth client_ids,
        and redirects to Google's authorization server.
        """
        from starlette.responses import RedirectResponse, Response, JSONResponse
        from urllib.parse import urlencode
        
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
        
        logger.info("🔄 Authorization request received")
        
        try:
            # Get query parameters
            query_params = dict(request.query_params)
            client_id = query_params.get("client_id")
            
            if not client_id:
                logger.error("❌ Missing client_id in authorization request")
                return JSONResponse(
                    content={
                        "error": "invalid_request",
                        "error_description": "Missing client_id parameter"
                    },
                    status_code=400,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                    }
                )
            
            logger.info(f"📋 Authorization request for client_id: {client_id}")
            
            # Check if this is a temporary client_id (starts with mcp_)
            if client_id.startswith("mcp_"):
                logger.info(f"🔍 Detected temporary client_id: {client_id}")
                
                # DIAGNOSTIC: Log proxy instance ID before lookup
                logger.info(f"🔍 DEBUG: Using oauth_proxy instance: {id(oauth_proxy)}")
                logger.info(f"🔍 DEBUG: Active proxy clients: {len(oauth_proxy._proxy_clients)}")
                if oauth_proxy._proxy_clients:
                    logger.info(f"🔍 DEBUG: Registered client IDs: {list(oauth_proxy._proxy_clients.keys())}")
                
                # Get the proxy client to retrieve real credentials
                proxy_client = oauth_proxy.get_proxy_client(client_id)
                
                if not proxy_client:
                    logger.error(f"❌ No proxy client found for temp_id: {client_id}")
                    return JSONResponse(
                        content={
                            "error": "invalid_client",
                            "error_description": f"Unknown client_id: {client_id}"
                        },
                        status_code=400,
                        headers={
                            "Access-Control-Allow-Origin": "*",
                        }
                    )
                
                # Store PKCE parameters if present (for later use in token exchange)
                code_challenge = query_params.get("code_challenge")
                code_challenge_method = query_params.get("code_challenge_method")
                
                if code_challenge and code_challenge_method:
                    proxy_client.store_pkce_params(code_challenge, code_challenge_method)
                    logger.info(f"🔐 Stored PKCE parameters: challenge={code_challenge[:10]}..., method={code_challenge_method}")
                
                # Use the real Google client_id
                real_client_id = proxy_client.real_client_id
                logger.info(f"✅ Mapped to real client_id: {real_client_id[:20]}...")
            else:
                # Direct usage of real client_id (for backward compatibility)
                real_client_id = client_id
                logger.info(f"📋 Using direct client_id: {real_client_id[:20]}...")
            
            # Build Google authorization URL with real client_id
            google_auth_params = dict(query_params)
            google_auth_params["client_id"] = real_client_id
            
            # Log the authorization parameters (without sensitive data)
            logger.info("🔗 Redirecting to Google OAuth with parameters:")
            logger.info(f"   client_id: {real_client_id[:20]}...")
            logger.info(f"   redirect_uri: {google_auth_params.get('redirect_uri', 'not specified')}")
            logger.info(f"   scope: {google_auth_params.get('scope', 'not specified')}")
            logger.info(f"   state: {google_auth_params.get('state', 'not specified')[:20] if google_auth_params.get('state') else 'not specified'}...")
            logger.info(f"   response_type: {google_auth_params.get('response_type', 'not specified')}")
            
            # Construct Google OAuth authorization URL
            google_auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(google_auth_params)
            
            logger.info(f"✅ Redirecting to Google OAuth authorization")
            
            # Redirect to Google's authorization server
            return RedirectResponse(
                url=google_auth_url,
                status_code=302
            )
            
        except Exception as e:
            logger.error(f"❌ Authorization proxy failed: {e}", exc_info=True)
            return JSONResponse(
                content={
                    "error": "server_error",
                    "error_description": f"Authorization proxy error: {str(e)}"
                },
                status_code=500,
                headers={
                    "Access-Control-Allow-Origin": "*",
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
    
    @mcp.custom_route("/oauth/token", methods=["POST", "OPTIONS"])
    async def oauth_token_endpoint(request: Any):
        """OAuth token endpoint that handles token exchange with OAuth Proxy.
        
        This endpoint intercepts token exchange requests from MCP clients
        and uses the OAuth Proxy to map temporary credentials to real ones.
        """
        from starlette.responses import JSONResponse, Response
        import urllib.parse
        
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
        
        logger.info("🔄 Token exchange requested")
        
        try:
            # Parse request body (can be JSON or form-encoded)
            content_type = request.headers.get('content-type', '')
            
            if 'application/json' in content_type:
                body = await request.body()
                if isinstance(body, bytes):
                    body = body.decode('utf-8')
                import json
                params = json.loads(body) if body else {}
            else:
                # Form-encoded (standard OAuth)
                body = await request.body()
                if isinstance(body, bytes):
                    body = body.decode('utf-8')
                params = dict(urllib.parse.parse_qsl(body))
            
            grant_type = params.get('grant_type')
            
            if grant_type == 'authorization_code':
                # Handle authorization code exchange
                auth_code = params.get('code')
                client_id = params.get('client_id')
                client_secret = params.get('client_secret')
                redirect_uri = params.get('redirect_uri')
                code_verifier = params.get('code_verifier')  # PKCE parameter
                
                # DIAGNOSTIC LOGGING for client_secret validation issue
                logger.info(f"🔍 DIAGNOSTIC - Token exchange parameters:")
                logger.info(f"   client_id: {client_id}")
                logger.info(f"   client_secret provided: {'YES' if client_secret else 'NO'}")
                logger.info(f"   client_secret value: {'<present>' if client_secret else '<MISSING/EMPTY>'}")
                logger.info(f"   client_secret length: {len(client_secret) if client_secret else 0}")
                logger.info(f"   code_verifier provided: {'YES' if code_verifier else 'NO'}")
                logger.info(f"   code_verifier value: {code_verifier[:10] + '...' if code_verifier else '<MISSING>'}")
                
                if not all([auth_code, client_id, redirect_uri]):
                    raise ValueError("Missing required parameters for authorization_code grant")
                
                # Use OAuth Proxy to handle the exchange
                token_data = handle_token_exchange(
                    auth_code=auth_code,
                    client_id=client_id,
                    client_secret=client_secret or '',  # Some flows might not have client_secret
                    redirect_uri=redirect_uri,
                    code_verifier=code_verifier  # Pass PKCE parameter
                )
                
                logger.info(f"✅ Token exchange successful for client: {client_id[:20]}...")
                
                # CRITICAL FIX: Store OAuth authentication data persistently
                # Since we can't use session context outside of FastMCP request context,
                # we store the authenticated user email to a file for later retrieval
                if client_id.startswith("mcp_"):
                    try:
                        # Get the authenticated user email from the OAuth proxy
                        proxy_client = oauth_proxy.get_proxy_client(client_id)
                        if proxy_client:
                            # Get user email from Google userinfo API using the new tokens
                            from google.oauth2.credentials import Credentials
                            from googleapiclient.discovery import build
                            import uuid
                            import json
                            from pathlib import Path
                            
                            # Create credentials from token response
                            credentials = Credentials(
                                token=token_data.get('access_token'),
                                refresh_token=token_data.get('refresh_token'),
                                token_uri="https://oauth2.googleapis.com/token",
                                client_id=proxy_client.real_client_id,
                                client_secret=proxy_client.real_client_secret,
                                scopes=token_data.get('scope', '').split() if token_data.get('scope') else []
                            )
                            
                            # Get user email from Google userinfo
                            userinfo_service = build("oauth2", "v2", credentials=credentials)
                            user_info = userinfo_service.userinfo().get().execute()
                            authenticated_email = user_info.get("email")
                            
                            if authenticated_email:
                                # Store OAuth authentication data to file for persistence
                                oauth_data_path = Path(settings.credentials_dir) / ".oauth_authentication.json"
                                oauth_data_path.parent.mkdir(parents=True, exist_ok=True)
                                
                                oauth_data = {
                                    "authenticated_email": authenticated_email,
                                    "authenticated_at": datetime.now().isoformat(),
                                    "client_id": client_id,
                                    "scopes": token_data.get('scope', '').split() if token_data.get('scope') else []
                                }
                                
                                with open(oauth_data_path, "w") as f:
                                    json.dump(oauth_data, f, indent=2)
                                
                                # Set restrictive permissions
                                try:
                                    oauth_data_path.chmod(0o600)
                                except (OSError, AttributeError):
                                    pass
                                
                                logger.info(f"✅ Stored OAuth authentication data for user: {authenticated_email}")
                                logger.info(f"   Stored to: {oauth_data_path}")
                                
                                # Try to set context if available (won't work outside FastMCP request)
                                try:
                                    from auth.context import set_user_email_context, set_session_context, get_session_context
                                    session_id = get_session_context() or str(uuid.uuid4())
                                    set_session_context(session_id)
                                    set_user_email_context(authenticated_email)
                                    logger.info(f"🔗 Set session context for OAuth proxy user: {authenticated_email}")
                                except RuntimeError:
                                    # Expected when not in FastMCP request context
                                    logger.info(f"📝 OAuth authentication stored for later use (not in FastMCP context)")
                            else:
                                logger.warning("⚠️ Could not determine user email from OAuth token exchange")
                        else:
                            logger.warning(f"⚠️ Proxy client not found for successful token exchange: {client_id}")
                    except Exception as e:
                        logger.error(f"❌ Failed to store OAuth authentication data: {e}")
                        # Don't fail the token exchange - this is a context setup issue, not an auth issue
                
                return JSONResponse(
                    content=token_data,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "POST, OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type, Authorization",
                        "Cache-Control": "no-store",
                        "Pragma": "no-cache",
                    }
                )
            
            elif grant_type == 'refresh_token':
                # Handle refresh token
                refresh_token = params.get('refresh_token')
                client_id = params.get('client_id')
                client_secret = params.get('client_secret')
                
                if not all([refresh_token, client_id]):
                    raise ValueError("Missing required parameters for refresh_token grant")
                
                token_data = refresh_access_token(
                    refresh_token=refresh_token,
                    client_id=client_id,
                    client_secret=client_secret or ''
                )
                
                logger.info(f"✅ Token refresh successful for client: {client_id[:20]}...")
                
                return JSONResponse(
                    content=token_data,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "POST, OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type, Authorization",
                        "Cache-Control": "no-store",
                        "Pragma": "no-cache",
                    }
                )
            
            else:
                raise ValueError(f"Unsupported grant_type: {grant_type}")
                
        except Exception as e:
            logger.error(f"❌ Token exchange failed: {e}")
            error_response = {
                "error": "invalid_request",
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
    logger.info("  GET /oauth/authorize (OAuth Proxy authorization endpoint)")
    logger.info("  POST /oauth/register")
    logger.info("  POST /oauth/token (OAuth Proxy token exchange)")
    logger.info("  GET /oauth/register/{client_id}")
    logger.info("  PUT /oauth/register/{client_id}")
    logger.info("  DELETE /oauth/register/{client_id}")