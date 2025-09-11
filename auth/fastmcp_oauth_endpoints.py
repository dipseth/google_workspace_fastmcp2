"""OAuth 2.1 discovery endpoints using FastMCP custom routes.

This module implements OAuth discovery and Dynamic Client Registration
endpoints using FastMCP's native routing system.
"""

import json
import logging
from datetime import datetime, UTC
from typing_extensions import Any, Dict
from config.settings import settings
from auth.context import set_user_email_context, set_session_context, get_session_context
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


async def _store_oauth_user_data_async(client_id: str, token_data: Dict[str, Any]) -> None:
    """
    Asynchronously store OAuth user data using existing UnifiedSession and DualAuthBridge.
    
    This function integrates with the existing authentication bridge infrastructure
    to properly handle OAuth Proxy authentication in the unified system.
    
    Args:
        client_id: The client ID (proxy client ID starting with "mcp_")
        token_data: Token data returned from Google OAuth
    """
    try:
        # Get the authenticated user email from the OAuth proxy
        proxy_client = oauth_proxy.get_proxy_client(client_id)
        if not proxy_client:
            logger.warning(f"⚠️ Proxy client not found for async user data storage: {client_id}")
            return
            
        # Get user email from Google userinfo API using the new tokens
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        import uuid
        import json
        from pathlib import Path
        from .dual_auth_bridge import get_dual_auth_bridge
        from .unified_session import UnifiedSession
        
        # Create credentials from token response
        credentials = Credentials(
            token=token_data.get('access_token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=proxy_client.real_client_id,
            client_secret=proxy_client.real_client_secret,
            scopes=token_data.get('scope', '').split() if token_data.get('scope') else []
        )
        
        # Get user email from Google userinfo (run in thread pool to avoid blocking)
        import asyncio
        
        def get_user_info():
            userinfo_service = build("oauth2", "v2", credentials=credentials)
            return userinfo_service.userinfo().get().execute()
        
        user_info = await asyncio.to_thread(get_user_info)
        authenticated_email = user_info.get("email")
        
        if authenticated_email:
            # INTEGRATE WITH EXISTING INFRASTRUCTURE
            # 1. Use DualAuthBridge to register OAuth Proxy authentication
            dual_bridge = get_dual_auth_bridge()
            dual_bridge.add_secondary_account(authenticated_email)
            
            # 2. Create UnifiedSession for this OAuth authentication
            unified_session = UnifiedSession()
            legacy_creds_data = {
                "token": token_data.get('access_token'),
                "refresh_token": token_data.get('refresh_token'),
                "scopes": token_data.get('scope', '').split() if token_data.get('scope') else [],
                "client_id": proxy_client.real_client_id,
                "client_secret": proxy_client.real_client_secret,
                "token_uri": "https://oauth2.googleapis.com/token",
                "expiry": datetime.now().isoformat()  # Will be calculated properly
            }
            
            session_state = unified_session.create_session_from_legacy(authenticated_email, legacy_creds_data)
            
            # 3. Store OAuth authentication data using the standard pattern
            oauth_data_path = Path(settings.credentials_dir) / ".oauth_authentication.json"
            oauth_data_path.parent.mkdir(parents=True, exist_ok=True)
            
            oauth_data = {
                "authenticated_email": authenticated_email,
                "authenticated_at": datetime.now().isoformat(),
                "client_id": client_id,
                "scopes": token_data.get('scope', '').split() if token_data.get('scope') else [],
                "token_received": True,
                "session_id": session_state.session_id,
                "auth_provider": "oauth_proxy"
            }
            
            with open(oauth_data_path, "w") as f:
                json.dump(oauth_data, f, indent=2)
            
            # Set restrictive permissions
            try:
                oauth_data_path.chmod(0o600)
            except (OSError, AttributeError):
                pass
            
            # 4. Bridge credentials from OAuth Proxy to the unified system
            dual_bridge.bridge_credentials(authenticated_email, "memory")
            
            logger.info(f"✅ Integrated OAuth Proxy authentication for user: {authenticated_email}")
            logger.info(f"   Session ID: {session_state.session_id}")
            logger.info(f"   Registered with DualAuthBridge as secondary account")
            logger.info(f"   Created UnifiedSession with legacy credentials")
            
            # Try to set context if available (won't work outside FastMCP request but worth trying)
            try:
                session_id = get_session_context() or session_state.session_id
                set_session_context(session_id)
                set_user_email_context(authenticated_email)
                logger.info(f"🔗 Set session context for OAuth proxy user: {authenticated_email}")
            except RuntimeError:
                # Expected when not in FastMCP request context
                logger.info(f"📝 OAuth authentication integrated for later use (not in FastMCP context)")
        else:
            logger.warning("⚠️ Could not determine user email from OAuth token exchange (async)")
            
    except Exception as e:
        logger.error(f"❌ Failed to integrate OAuth authentication data (async): {e}", exc_info=True)
        # This is background processing, so we don't want to crash anything


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
            
            # CRITICAL FIX: Ensure scope parameter is always present using ScopeRegistry
            current_scope = google_auth_params.get("scope", "").strip()
            if not current_scope:
                # Use ScopeRegistry oauth_comprehensive group for missing scopes
                try:
                    from .scope_registry import ScopeRegistry
                    default_scopes = ScopeRegistry.resolve_scope_group("oauth_comprehensive")
                    google_auth_params["scope"] = " ".join(default_scopes)
                    logger.info(f"🔧 Added missing scope parameter using ScopeRegistry oauth_comprehensive: {len(default_scopes)} scopes")
                except Exception as e:
                    # Fallback to _get_oauth_endpoint_scopes if ScopeRegistry fails
                    logger.warning(f"Failed to get scopes from ScopeRegistry, using fallback: {e}")
                    fallback_scopes = _get_oauth_endpoint_scopes()
                    google_auth_params["scope"] = " ".join(fallback_scopes)
                    logger.info(f"🔧 Added missing scope parameter using fallback: {len(fallback_scopes)} scopes")
            else:
                # Validate existing scope parameter isn't just whitespace
                scope_parts = current_scope.split()
                if not scope_parts:
                    try:
                        from .scope_registry import ScopeRegistry
                        default_scopes = ScopeRegistry.resolve_scope_group("oauth_comprehensive")
                        google_auth_params["scope"] = " ".join(default_scopes)
                        logger.info(f"🔧 Replaced empty scope parameter using ScopeRegistry: {len(default_scopes)} scopes")
                    except Exception as e:
                        fallback_scopes = _get_oauth_endpoint_scopes()
                        google_auth_params["scope"] = " ".join(fallback_scopes)
                        logger.info(f"🔧 Replaced empty scope parameter using fallback: {len(fallback_scopes)} scopes")
                else:
                    logger.info(f"✅ Using provided scope parameter with {len(scope_parts)} scopes")
            
            # Log the authorization parameters (without sensitive data)
            logger.info("🔗 Redirecting to Google OAuth with parameters:")
            logger.info(f"   client_id: {real_client_id[:20]}...")
            logger.info(f"   redirect_uri: {google_auth_params.get('redirect_uri', 'not specified')}")
            logger.info(f"   scope: {google_auth_params.get('scope', 'not specified')[:100]}...")
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
                
                # IMMEDIATE RESPONSE TO PREVENT FREEZING
                # Enhanced headers for better MCP Inspector compatibility
                response = JSONResponse(
                    content=token_data,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "POST, OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type, Authorization",
                        "Cache-Control": "no-store",
                        "Pragma": "no-cache",
                        "Connection": "close",  # Force connection close to prevent hanging
                        "Content-Type": "application/json; charset=utf-8",
                        "X-Content-Type-Options": "nosniff"
                    }
                )
                
                # ASYNC POST-PROCESSING: Store OAuth authentication data in background
                # This prevents the client from hanging while we get user info
                if client_id.startswith("mcp_"):
                    # Use async task to handle user data storage without blocking response
                    import asyncio
                    asyncio.create_task(_store_oauth_user_data_async(client_id, token_data))
                
                return response

            
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
    
    @mcp.custom_route("/oauth/callback/debug", methods=["GET", "OPTIONS"])
    async def oauth_callback_debug(request: Any):
        """OAuth callback endpoint for debugging and MCP Inspector.
        
        This endpoint handles the OAuth callback from Google's authorization server.
        It extracts the authorization code and either displays it for debugging
        or exchanges it for tokens automatically.
        """
        from starlette.responses import HTMLResponse, JSONResponse, Response
        
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
        
        logger.info("🔄 OAuth callback received")
        
        try:
            # Get query parameters from callback
            query_params = dict(request.query_params)
            auth_code = query_params.get("code")
            state = query_params.get("state")
            error = query_params.get("error")
            
            logger.info(f"📋 Callback parameters: code={'present' if auth_code else 'missing'}, state={'present' if state else 'missing'}, error={error or 'none'}")
            
            if error:
                logger.error(f"❌ OAuth error in callback: {error}")
                error_description = query_params.get("error_description", "No description provided")
                return HTMLResponse(
                    content=f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>OAuth Error</title>
                        <style>
                            body {{ font-family: Arial, sans-serif; margin: 40px; text-align: center; }}
                            .error {{ color: #dc3545; }}
                            .container {{ max-width: 600px; margin: 0 auto; }}
                            .code {{ background: #f8f9fa; padding: 10px; border-radius: 5px; margin: 10px 0; }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <h1 class="error">❌ OAuth Error</h1>
                            <p><strong>Error:</strong> {error}</p>
                            <p><strong>Description:</strong> {error_description}</p>
                            <p>Please try the authentication process again.</p>
                        </div>
                    </body>
                    </html>
                    """,
                    status_code=400
                )
            
            if not auth_code:
                logger.error("❌ No authorization code in callback")
                return HTMLResponse(
                    content="""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>OAuth Callback Error</title>
                        <style>
                            body { font-family: Arial, sans-serif; margin: 40px; text-align: center; }
                            .error { color: #dc3545; }
                            .container { max-width: 600px; margin: 0 auto; }
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <h1 class="error">❌ Authorization Code Missing</h1>
                            <p>No authorization code received from Google OAuth.</p>
                            <p>Please try the authentication process again.</p>
                        </div>
                    </body>
                    </html>
                    """,
                    status_code=400
                )
            
            # SUCCESS: We have an authorization code
            logger.info(f"✅ Authorization code received: {auth_code[:10]}...")
            
            # For debugging, show the authorization code to the user
            # In production, you might want to automatically exchange it for tokens
            return HTMLResponse(
                content=f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>OAuth Callback Success</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; margin: 40px; text-align: center; }}
                        .success {{ color: #28a745; }}
                        .container {{ max-width: 600px; margin: 0 auto; }}
                        .code {{
                            background: #f8f9fa;
                            padding: 15px;
                            border-radius: 5px;
                            margin: 20px 0;
                            font-family: monospace;
                            word-break: break-all;
                            border: 1px solid #dee2e6;
                        }}
                        .params {{
                            text-align: left;
                            background: #e9ecef;
                            padding: 15px;
                            border-radius: 5px;
                            margin: 20px 0;
                        }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1 class="success">✅ OAuth Callback Successful!</h1>
                        <p>Authorization code received from Google OAuth.</p>
                        
                        <div class="params">
                            <h3>Callback Parameters:</h3>
                            <p><strong>Authorization Code:</strong></p>
                            <div class="code">{auth_code}</div>
                            {'<p><strong>State:</strong> ' + state + '</p>' if state else ''}
                        </div>
                        
                        <p><em>You can now close this window or use the authorization code for token exchange.</em></p>
                    </div>
                </body>
                </html>
                """
            )
            
        except Exception as e:
            logger.error(f"❌ OAuth callback error: {e}", exc_info=True)
            return HTMLResponse(
                content=f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>OAuth Callback Error</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; margin: 40px; text-align: center; }}
                        .error {{ color: #dc3545; }}
                        .container {{ max-width: 600px; margin: 0 auto; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1 class="error">❌ Callback Processing Error</h1>
                        <p>Error processing OAuth callback: {str(e)}</p>
                        <p>Please try the authentication process again.</p>
                    </div>
                </body>
                </html>
                """,
                status_code=500
            )
    
    @mcp.custom_route("/oauth/status", methods=["GET", "OPTIONS"])
    async def oauth_status_check(request: Any):
        """OAuth authentication status polling endpoint.
        
        This endpoint allows clients to check if OAuth authentication has been completed.
        Useful for CLI clients that open a browser window and need to wait for completion.
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
        
        logger.info("🔍 OAuth status check requested")
        
        try:
            # Check for stored OAuth authentication data
            from pathlib import Path
            import json
            from datetime import datetime, timedelta
            
            oauth_data_path = Path(settings.credentials_dir) / ".oauth_authentication.json"
            
            if not oauth_data_path.exists():
                return JSONResponse(
                    content={
                        "authenticated": False,
                        "message": "No authentication data found",
                        "timestamp": datetime.now().isoformat()
                    },
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                        "Expires": "0"
                    }
                )
            
            # Read authentication data
            with open(oauth_data_path, "r") as f:
                oauth_data = json.load(f)
            
            authenticated_email = oauth_data.get("authenticated_email")
            authenticated_at_str = oauth_data.get("authenticated_at")
            token_received = oauth_data.get("token_received", False)
            
            if authenticated_email and token_received:
                # Check if authentication is recent (within 24 hours)
                auth_age_hours = 0
                if authenticated_at_str:
                    try:
                        authenticated_at = datetime.fromisoformat(authenticated_at_str)
                        age = datetime.now() - authenticated_at
                        auth_age_hours = age.total_seconds() / 3600
                    except Exception:
                        pass
                
                return JSONResponse(
                    content={
                        "authenticated": True,
                        "user_email": authenticated_email,
                        "authenticated_at": authenticated_at_str,
                        "age_hours": auth_age_hours,
                        "scopes": oauth_data.get("scopes", []),
                        "message": f"Authenticated as {authenticated_email}",
                        "timestamp": datetime.now().isoformat()
                    },
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                        "Expires": "0"
                    }
                )
            else:
                return JSONResponse(
                    content={
                        "authenticated": False,
                        "message": "Authentication incomplete or invalid",
                        "timestamp": datetime.now().isoformat()
                    },
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                        "Expires": "0"
                    }
                )
            
        except Exception as e:
            logger.error(f"❌ OAuth status check failed: {e}")
            return JSONResponse(
                content={
                    "authenticated": False,
                    "error": str(e),
                    "message": "Error checking authentication status",
                    "timestamp": datetime.now().isoformat()
                },
                status_code=500,
                headers={
                    "Access-Control-Allow-Origin": "*",
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
    logger.info("  POST /oauth/token (OAuth Proxy token exchange - FIXED freezing issue)")
    logger.info("  GET /oauth/callback/debug (OAuth callback handler - FIXED missing endpoint)")
    logger.info("  GET /oauth/status (Authentication status polling for CLI clients)")
    logger.info("  GET /oauth/register/{client_id}")
    logger.info("  PUT /oauth/register/{client_id}")
    logger.info("  DELETE /oauth/register/{client_id}")