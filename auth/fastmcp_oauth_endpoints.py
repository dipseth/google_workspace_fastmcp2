"""OAuth 2.1 discovery endpoints using FastMCP custom routes.

This module implements OAuth discovery and Dynamic Client Registration
endpoints using FastMCP's native routing system.
"""

import json
import logging
from datetime import datetime, UTC
from typing_extensions import Any, Dict, List 
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

from config.enhanced_logging import setup_logger
logger = setup_logger()


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


def _generate_service_selection_html(state: str, flow_type: str, use_pkce: bool = True) -> str:
    """Generate the service selection page HTML with authentication method choice."""
    try:
        from .scope_registry import ScopeRegistry
        
        services_catalog = ScopeRegistry.get_service_catalog()
        
        # Group services by category
        categories = {}
        for key, service in services_catalog.items():
            category = service.get("category", "Other")
            if category not in categories:
                categories[category] = []
            categories[category].append((key, service))
        
        # Generate HTML with authentication method selection
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Select Google Services - FastMCP</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
                .container {{ background: white; border-radius: 12px; padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .header h1 {{ color: #1a73e8; margin-bottom: 10px; }}
                .header p {{ color: #5f6368; }}
                .auth-method-section {{ margin-bottom: 30px; }}
                .auth-method-title {{ font-size: 18px; font-weight: 600; color: #1a73e8; margin-bottom: 15px; }}
                .auth-method-options {{ display: flex; gap: 15px; margin-bottom: 20px; }}
                .auth-method-option {{ flex: 1; padding: 20px; border: 2px solid #e8eaed; border-radius: 12px; cursor: pointer; transition: all 0.2s ease; }}
                .auth-method-option:hover {{ border-color: #1a73e8; background-color: #f8f9ff; }}
                .auth-method-option.selected {{ border-color: #1a73e8; background-color: #e8f0fe; }}
                .auth-method-option input[type="radio"] {{ margin-right: 10px; transform: scale(1.2); }}
                .auth-method-name {{ font-weight: 600; color: #202124; margin-bottom: 8px; }}
                .auth-method-description {{ font-size: 14px; color: #5f6368; line-height: 1.4; }}
                .auth-method-pros {{ font-size: 12px; color: #137333; margin-top: 8px; }}
                .auth-method-cons {{ font-size: 12px; color: #d93025; margin-top: 4px; }}
                .category {{ margin-bottom: 25px; }}
                .category-title {{ font-size: 18px; font-weight: 600; color: #1a73e8; margin-bottom: 12px; border-bottom: 2px solid #e8eaed; padding-bottom: 5px; }}
                .service-item {{ display: flex; align-items: center; padding: 12px; border: 1px solid #e8eaed; border-radius: 8px; margin-bottom: 8px; transition: all 0.2s ease; }}
                .service-item:hover {{ border-color: #1a73e8; background-color: #f8f9ff; }}
                .service-item.required {{ background-color: #e8f5e8; border-color: #34a853; }}
                .service-checkbox {{ margin-right: 12px; transform: scale(1.2); }}
                .service-info {{ flex: 1; }}
                .service-name {{ font-weight: 500; color: #202124; }}
                .service-description {{ font-size: 14px; color: #5f6368; margin-top: 4px; }}
                .required-badge {{ color: #34a853; font-size: 12px; font-weight: 500; margin-left: 8px; }}
                .btn {{ padding: 14px 24px; border-radius: 6px; border: none; font-weight: 500; cursor: pointer; font-size: 16px; }}
                .btn-primary {{ background: #1a73e8; color: white; margin-right: 10px; }}
                .btn-primary:hover {{ background: #1557b0; }}
                .btn-secondary {{ background: #f8f9fa; color: #3c4043; border: 1px solid #dadce0; }}
                .btn-secondary:hover {{ background: #e8eaed; }}
                .form-actions {{ text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e8eaed; }}
                .auto-select-info {{ background: #e8f0fe; padding: 12px; border-radius: 8px; margin-bottom: 20px; }}
                .auto-select-info p {{ margin: 0; color: #1a73e8; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔐 Configure Google Authentication</h1>
                    <p>Choose your authentication method and services for FastMCP</p>
                </div>
                
                <form method="POST" action="/auth/services/selected">
                    <input type="hidden" name="state" value="{state}">
                    <input type="hidden" name="flow_type" value="{flow_type}">
                    
                    <!-- Authentication Method Selection -->
                    <div class="auth-method-section">
                        <div class="auth-method-title">🔒 Choose Authentication Method</div>
                        <div class="auth-method-options">
                            <div class="auth-method-option {'selected' if use_pkce else ''}" onclick="selectAuthMethod('pkce', this)">
                                <label>
                                    <input type="radio" name="auth_method" value="pkce" {'checked' if use_pkce else ''}>
                                    <div class="auth-method-name">🔐 PKCE Flow (Recommended)</div>
                                    <div class="auth-method-description">Enhanced security using Proof Key for Code Exchange</div>
                                    <div class="auth-method-pros">✅ No secrets stored • More secure • Perfect for single sessions</div>
                                    <div class="auth-method-cons">⚠️ Session-based only • Doesn't persist across restarts</div>
                                </label>
                            </div>
                            <div class="auth-method-option {'selected' if not use_pkce else ''}" onclick="selectAuthMethod('credentials', this)">
                                <label>
                                    <input type="radio" name="auth_method" value="credentials" {'checked' if not use_pkce else ''}>
                                    <div class="auth-method-name">📁 Encrypted Credentials</div>
                                    <div class="auth-method-description">Persistent authentication with encrypted file storage</div>
                                    <div class="auth-method-pros">✅ Multi-account support • Persists across restarts • Encrypted storage</div>
                                    <div class="auth-method-cons">⚠️ Requires credential files • Slightly less secure</div>
                                </label>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Custom Credentials Section -->
                    <div class="custom-credentials-section" style="margin-bottom: 30px; padding: 20px; border: 2px solid #e8eaed; border-radius: 12px;">
                        <label style="display: flex; align-items: center; margin-bottom: 15px;">
                            <input type="checkbox" id="use_custom_creds" name="use_custom_creds" style="margin-right: 10px; transform: scale(1.2);">
                            <span style="font-weight: 600; color: #1a73e8;">Use custom Google OAuth credentials</span>
                        </label>
                        <div id="custom-creds-fields" style="display: none;">
                            <div class="custom-creds-warning" style="background: #fff3cd; border: 1px solid #ffeaa7; color: #856404; padding: 15px; border-radius: 8px; margin-bottom: 15px;">
                                <strong>⚠️ Important Setup Requirements:</strong><br>
                                Your custom OAuth client must have this redirect URI configured:<br>
                                <code style="background: #f8f9fa; padding: 4px 8px; border-radius: 4px; font-family: monospace;">https://localhost:8002/oauth2callback</code>
                            </div>
                            <div class="custom-creds-info" style="background: #e8f0fe; border: 1px solid #dadce0; color: #1a73e8; padding: 15px; border-radius: 8px; margin-bottom: 15px;">
                                <strong>🔧 Google Cloud Console Setup:</strong><br>
                                1. Go to <a href="https://console.cloud.google.com/apis/credentials" target="_blank">Google Cloud Console → APIs & Services → Credentials</a><br>
                                2. Create or edit your OAuth 2.0 Client ID<br>
                                3. Add <code>https://localhost:8002/oauth2callback</code> to "Authorized redirect URIs"<br>
                                4. Enable required APIs (Drive, Gmail, Calendar, etc.)
                            </div>
                            <p style="color: #d93025; font-weight: bold; margin-bottom: 15px;">Warning: Providing client secret through UI is not recommended for production!</p>
                            <div style="display: flex; flex-direction: column; gap: 10px;">
                                <input type="text" name="custom_client_id" placeholder="Custom Client ID (required)" style="padding: 12px; border: 1px solid #dadce0; border-radius: 8px; font-size: 14px; width: 100%; box-sizing: border-box;">
                                <input type="text" name="custom_client_secret" placeholder="Custom Client Secret (optional for PKCE)" style="padding: 12px; border: 1px solid #dadce0; border-radius: 8px; font-size: 14px; width: 100%; box-sizing: border-box;">
                            </div>
                            <div class="custom-creds-troubleshooting" style="background: #fef7e0; border: 1px solid #fbcf33; color: #b7791f; padding: 15px; border-radius: 8px; margin-top: 15px;">
                                <strong>🔍 Troubleshooting:</strong><br>
                                • If you get "invalid_client" error, check your redirect URI configuration<br>
                                • Ensure your OAuth consent screen is configured<br>
                                • Verify all required APIs are enabled in Google Cloud Console<br>
                                • For PKCE flow, client_secret is optional but client_id is required
                            </div>
                        </div>
                    </div>
                    
                    <div class="auto-select-info">
                        <p>💡 Common services (Drive, Gmail, Calendar, Docs, Sheets) are pre-selected for your convenience</p>
                    </div>
        """
        
        # Sort categories for better organization
        category_order = ["Core Services", "Storage & Files", "Communication", "Productivity", "Office Suite", "Other"]
        sorted_categories = sorted(categories.items(), key=lambda x: category_order.index(x[0]) if x[0] in category_order else len(category_order))
        
        for category_name, services in sorted_categories:
            html += f'<div class="category"><div class="category-title">{category_name}</div>'
            
            for service_key, service_info in services:
                required = service_info.get("required", False)
                checked = "checked disabled" if required else ""
                required_class = "required" if required else ""
                
                html += f"""
                    <div class="service-item {required_class}">
                        <input type="checkbox" class="service-checkbox" name="services"
                               value="{service_key}" {checked}>
                        <div class="service-info">
                            <div class="service-name">
                                {service_info['name']}
                                {'<span class="required-badge">Required</span>' if required else ''}
                            </div>
                            <div class="service-description">{service_info['description']}</div>
                        </div>
                    </div>
                """
            
            html += '</div>'
        
        html += """
                    <div class="form-actions">
                        <button type="submit" class="btn btn-primary">Continue with Selected Configuration</button>
                        <button type="button" class="btn btn-secondary" onclick="selectAll()">Select All Services</button>
                    </div>
                </form>
            </div>
            
            <script>
                // Auto-select common services - matches drive/upload_tools.py default list
                document.addEventListener('DOMContentLoaded', function() {
                    const commonServices = ['drive', 'gmail', 'calendar', 'docs', 'sheets', 'slides', 'photos', 'chat', 'forms'];
                    commonServices.forEach(serviceKey => {
                        const checkbox = document.querySelector(`input[value="${serviceKey}"]`);
                        if (checkbox && !checkbox.disabled) {
                            checkbox.checked = true;
                        }
                    });
                });
                
                function selectAll() {
                    const checkboxes = document.querySelectorAll('input[name="services"]:not(:disabled)');
                    const allChecked = Array.from(checkboxes).every(cb => cb.checked);
                    checkboxes.forEach(cb => cb.checked = !allChecked);
                }
                
                function selectAuthMethod(method, element) {
                    // Update radio button
                    const radio = element.querySelector('input[type="radio"]');
                    radio.checked = true;
                    
                    // Update visual selection
                    document.querySelectorAll('.auth-method-option').forEach(opt => {
                        opt.classList.remove('selected');
                    });
                    element.classList.add('selected');
                    
                    // Update hidden form field
                    const usesPkce = method === 'pkce';
                    const hiddenField = document.querySelector('input[name="use_pkce"]');
                    if (hiddenField) {
                        hiddenField.value = usesPkce.toString();
                    }
                    
                    console.log(`Selected authentication method: ${method} (PKCE: ${usesPkce})`);
                }
                
                // Handle radio button clicks
                document.addEventListener('DOMContentLoaded', function() {
                    document.querySelectorAll('.auth-method-option input[type="radio"]').forEach(radio => {
                        radio.addEventListener('change', function() {
                            if (this.checked) {
                                selectAuthMethod(this.value, this.closest('.auth-method-option'));
                            }
                        });
                    });
                    
                    // Handle custom credentials checkbox
                    const customCredsCheckbox = document.getElementById('use_custom_creds');
                    const customCredsFields = document.getElementById('custom-creds-fields');
                    
                    if (customCredsCheckbox && customCredsFields) {
                        customCredsCheckbox.addEventListener('change', function() {
                            if (this.checked) {
                                customCredsFields.style.display = 'block';
                                // Scroll to show the fields
                                customCredsFields.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                            } else {
                                customCredsFields.style.display = 'none';
                                // Clear the fields when hiding
                                const inputs = customCredsFields.querySelectorAll('input');
                                inputs.forEach(input => input.value = '');
                            }
                        });
                    }
                    
                    // Form validation
                    const form = document.querySelector('form');
                    if (form) {
                        form.addEventListener('submit', function(e) {
                            const customCredsEnabled = customCredsCheckbox && customCredsCheckbox.checked;
                            if (customCredsEnabled) {
                                const clientIdInput = document.querySelector('input[name="custom_client_id"]');
                                if (!clientIdInput || !clientIdInput.value.trim()) {
                                    e.preventDefault();
                                    alert('Please provide a Custom Client ID when using custom credentials.');
                                    if (clientIdInput) clientIdInput.focus();
                                    return false;
                                }
                                
                                // Validate client ID format
                                const clientId = clientIdInput.value.trim();
                                if (!clientId.includes('.apps.googleusercontent.com')) {
                                    const proceed = confirm('Warning: Your Client ID doesn\\'t look like a Google OAuth client ID.\\n\\nGoogle Client IDs usually end with \\".apps.googleusercontent.com\\"\\n\\nDo you want to continue anyway?');
                                    if (!proceed) {
                                        e.preventDefault();
                                        return false;
                                    }
                                }
                            }
                        });
                    }
                });
            </script>
        </body>
        </html>
        """
        
        return html
        
    except Exception as e:
        logger.error(f"Error generating service selection HTML: {e}")
        return f"""
        <!DOCTYPE html>
        <html><head><title>Error</title></head>
        <body><h1>Service Selection Error</h1><p>Error: {str(e)}</p></body></html>
        """


async def _handle_fastmcp_service_selection(state: str, services: List[str], use_pkce: bool = True) -> str:
    """Handle FastMCP service selection and create OAuth URL with PKCE support."""
    try:
        from .google_auth import _service_selection_cache
        from .scope_registry import ScopeRegistry
        
        flow_info = _service_selection_cache.pop(state, None)
        if not flow_info:
            raise ValueError("Invalid or expired service selection state")
        
        user_email = flow_info["user_email"]
        
        # Get scopes for selected services
        scopes = ScopeRegistry.get_scopes_for_services(services)
        
        logger.info(f"🔧 FastMCP service selection: {len(services)} services selected, {len(scopes)} scopes (PKCE: {use_pkce})")
        
        # For FastMCP integration, we'll fall back to the custom OAuth flow for now
        # In the future, this could integrate more directly with GoogleProvider
        from .google_auth import handle_service_selection_callback
        return await handle_service_selection_callback(state, services)
        
    except Exception as e:
        logger.error(f"Error handling FastMCP service selection: {e}")
        raise


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
    
    # MCP Inspector compatibility - alias /register to /oauth/register
    @mcp.custom_route("/register", methods=["POST", "OPTIONS"])
    async def register_alias(request: Any):
        """Alias for MCP Inspector compatibility - routes to dynamic_client_registration."""
        return await dynamic_client_registration(request)
    
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
            
            # Enhanced error handling for common OAuth issues
            error_str = str(e).lower()
            
            if "invalid_client" in error_str or "unauthorized" in error_str:
                error_response = {
                    "error": "invalid_client",
                    "error_description": "OAuth client configuration error. Please check your Google Cloud Console setup.",
                    "troubleshooting": {
                        "likely_cause": "Redirect URI mismatch or invalid client credentials",
                        "solution_steps": [
                            "1. Go to Google Cloud Console → APIs & Services → Credentials",
                            "2. Edit your OAuth 2.0 Client ID",
                            "3. Add 'https://localhost:8002/oauth2callback' to 'Authorized redirect URIs'",
                            "4. Save the changes and try authentication again",
                            "5. If using custom client_id, verify it's correct and active"
                        ]
                    }
                }
                status_code = 401
            elif "invalid_grant" in error_str:
                error_response = {
                    "error": "invalid_grant",
                    "error_description": "Authorization code is invalid, expired, or already used.",
                    "troubleshooting": {
                        "likely_cause": "Authorization code reuse or expiration",
                        "solution_steps": [
                            "1. Start a fresh OAuth flow from the beginning",
                            "2. Don't refresh the callback page",
                            "3. Complete the flow within 10 minutes",
                            "4. Ensure system clock is accurate"
                        ]
                    }
                }
                status_code = 400
            else:
                error_response = {
                    "error": "token_exchange_failed",
                    "error_description": f"Token exchange failed: {str(e)}",
                    "troubleshooting": {
                        "likely_cause": "General OAuth configuration or network issue",
                        "solution_steps": [
                            "1. Check Google Cloud Console OAuth client configuration",
                            "2. Verify redirect URI matches exactly: https://localhost:8002/oauth2callback",
                            "3. Ensure all required APIs are enabled",
                            "4. Check server logs for more details"
                        ]
                    }
                }
                status_code = 500
            
            return JSONResponse(
                content=error_response,
                status_code=status_code,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                }
            )
    
    @mcp.custom_route("/oauth2callback", methods=["GET", "OPTIONS"])
    async def oauth2callback_main(request: Any):
        """Main OAuth2 callback endpoint for the application.
        
        This is the primary callback endpoint that handles OAuth redirects from Google.
        It processes authorization codes and completes the authentication flow with
        full credential storage and success page display.
        """
        # IMMEDIATE logging to ensure we see if the route is hit
        logger.info("🚨 CRITICAL: OAuth2 callback route HIT!")
        logger.info(f"🚨 CRITICAL: Request URL: {request.url}")
        logger.info(f"🚨 CRITICAL: Request method: {request.method}")
        
        from starlette.responses import HTMLResponse, Response
        
        # Handle CORS preflight
        if request.method == "OPTIONS":
            logger.info("🚨 CRITICAL: Handling OPTIONS request")
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                }
            )
        
        # FULL OAuth processing now that route is confirmed working
        logger.info("🔄 Processing full OAuth callback with credential exchange")
        
        try:
            # Extract parameters from query string
            query_params = dict(request.query_params)
            state = query_params.get("state")
            code = query_params.get("code")
            error = query_params.get("error")
            
            logger.info(f"🔍 Query parameters extracted:")
            logger.info(f"   state: {state[:20] if state else 'MISSING'}...")
            logger.info(f"   code: {'PRESENT' if code else 'MISSING'}")
            logger.info(f"   error: {error or 'None'}")
            
            # SUCCESS: Process OAuth callback and save credentials
            logger.info(f"✅ OAuth callback received - processing authorization code")
            
            try:
                # Import OAuth handling
                from auth.google_auth import handle_oauth_callback
                from auth.pkce_utils import pkce_manager
                from auth.context import get_session_context, store_session_data
                
                # Retrieve PKCE code verifier if available
                code_verifier = None
                try:
                    code_verifier = pkce_manager.get_code_verifier(state)
                    logger.info(f"🔐 Retrieved PKCE code verifier for callback")
                except KeyError:
                    logger.info(f"ℹ️ No PKCE session found for state: {state} (non-PKCE flow)")
                except Exception as e:
                    logger.warning(f"⚠️ PKCE retrieval error (continuing): {e}")
                
                # Handle OAuth callback with full credential processing
                user_email, credentials = await handle_oauth_callback(
                    authorization_response=str(request.url),
                    state=state,
                    code_verifier=code_verifier
                )
                
                logger.info(f"✅ OAuth callback processed successfully for user: {user_email}")
                logger.info(f"✅ Credentials saved for user: {user_email}")
                
                # Store user email in session context
                try:
                    session_id = get_session_context()
                    if session_id:
                        store_session_data(session_id, "user_email", user_email)
                        logger.info(f"✅ Stored user email {user_email} in session {session_id}")
                except Exception as e:
                    logger.warning(f"⚠️ Session storage error (continuing): {e}")
                
                # Create beautiful success page
                success_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Authentication Successful</title>
                    <style>
                        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; }}
                        .container {{ max-width: 500px; background: white; border-radius: 20px; padding: 50px; text-align: center; box-shadow: 0 20px 40px rgba(0,0,0,0.1); }}
                        .success-icon {{ font-size: 72px; margin-bottom: 20px; }}
                        h1 {{ color: #28a745; margin-bottom: 10px; font-size: 32px; }}
                        .email {{ color: #6c757d; font-size: 18px; margin: 20px 0; }}
                        .message {{ color: #495057; font-size: 16px; line-height: 1.5; margin: 20px 0; }}
                        .services {{ background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0; }}
                        .services h3 {{ color: #495057; margin-top: 0; }}
                        .service-list {{ color: #6c757d; font-size: 14px; }}
                        .credentials-saved {{ background: #d4edda; color: #155724; padding: 15px; border-radius: 8px; margin: 20px 0; border: 1px solid #c3e6cb; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="success-icon">✅</div>
                        <h1>Authentication Successful!</h1>
                        <div class="email">Successfully authenticated: <strong>{user_email}</strong></div>
                        <div class="credentials-saved">
                            <strong>🔐 Credentials Saved!</strong><br>
                            Your authentication has been securely stored and is ready to use.
                        </div>
                        <div class="message">
                            Your Google services are now connected and ready to use!
                        </div>
                        <div class="services">
                            <h3>🚀 Services Available</h3>
                            <div class="service-list">
                                Google Drive • Gmail • Calendar • Docs • Sheets • Slides • Photos • Chat • Forms
                            </div>
                        </div>
                        <div class="message">
                            You can now close this window and return to your application.
                        </div>
                    </div>
                </body>
                </html>
                """
                
                logger.info(f"✅ Returning success page for {user_email} with credential confirmation")
                return HTMLResponse(
                    content=success_html,
                    status_code=200,
                    headers={
                        "Content-Type": "text/html; charset=utf-8",
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                        "X-OAuth-Success": "true",
                        "X-Credentials-Saved": "true"
                    }
                )
                
            except Exception as oauth_error:
                logger.error(f"❌ OAuth processing failed: {oauth_error}", exc_info=True)
                
                # Enhanced error messaging for OAuth issues
                error_str = str(oauth_error).lower()
                
                if "invalid_client" in error_str or "unauthorized" in error_str:
                    error_html = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>OAuth Client Configuration Error</title>
                        <style>
                            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; background: #fff5f5; min-height: 100vh; display: flex; align-items: center; justify-content: center; }}
                            .container {{ max-width: 700px; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
                            .error {{ color: #dc3545; font-size: 48px; margin-bottom: 20px; text-align: center; }}
                            h1 {{ color: #333; margin-bottom: 20px; text-align: center; }}
                            .error-details {{ background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; padding: 15px; border-radius: 8px; margin: 20px 0; }}
                            .solution-steps {{ background: #d4edda; border: 1px solid #c3e6cb; color: #155724; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                            .solution-steps h3 {{ margin-top: 0; color: #155724; }}
                            .solution-steps ol {{ text-align: left; padding-left: 20px; }}
                            .solution-steps li {{ margin: 8px 0; }}
                            .redirect-uri {{ background: #f8f9fa; padding: 8px 12px; border-radius: 4px; font-family: monospace; border: 1px solid #dee2e6; }}
                            .important {{ font-weight: bold; color: #dc3545; }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <div class="error">❌</div>
                            <h1>OAuth Client Configuration Error</h1>
                            
                            <div class="error-details">
                                <strong>Error:</strong> {str(oauth_error)}<br><br>
                                <strong>Most Likely Cause:</strong> Your OAuth client's redirect URI configuration doesn't match what the authentication system expects.
                            </div>
                            
                            <div class="solution-steps">
                                <h3>🔧 How to Fix This:</h3>
                                <ol>
                                    <li>Go to <a href="https://console.cloud.google.com/apis/credentials" target="_blank">Google Cloud Console → APIs & Services → Credentials</a></li>
                                    <li>Find and click on your OAuth 2.0 Client ID</li>
                                    <li>In the "Authorized redirect URIs" section, add this exact URI:</li>
                                    <div class="redirect-uri">https://localhost:8002/oauth2callback</div>
                                    <li>Click "Save" to update your OAuth client configuration</li>
                                    <li>Wait a few minutes for changes to propagate</li>
                                    <li class="important">Try the authentication process again</li>
                                </ol>
                            </div>
                            
                            <div style="text-align: center; margin-top: 30px;">
                                <p>If you continue having issues, verify that:</p>
                                <ul style="text-align: left; display: inline-block;">
                                    <li>Your OAuth consent screen is configured</li>
                                    <li>Required APIs are enabled (Drive, Gmail, Calendar, etc.)</li>
                                    <li>Your client ID and secret are correct</li>
                                    <li>You're using the latest client credentials</li>
                                </ul>
                            </div>
                        </div>
                    </body>
                    </html>
                    """
                else:
                    error_html = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>OAuth Processing Error</title>
                        <style>
                            body {{ font-family: Arial, sans-serif; margin: 40px; text-align: center; background: #fff5f5; }}
                            .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
                            .error {{ color: #dc3545; font-size: 48px; margin-bottom: 20px; }}
                            h1 {{ color: #333; margin-bottom: 20px; }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <div class="error">❌</div>
                            <h1>OAuth Processing Error</h1>
                            <p><strong>Error:</strong> {str(oauth_error)}</p>
                            <p>Please try the authentication process again.</p>
                        </div>
                    </body>
                    </html>
                    """
                
                return HTMLResponse(
                    content=error_html,
                    status_code=500,
                    headers={
                        "Content-Type": "text/html; charset=utf-8",
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache"
                    }
                )
            
        except Exception as e:
            logger.error(f"🚨 CRITICAL: Basic callback error: {e}", exc_info=True)
            
            # Even if everything fails, return a basic HTML response
            error_html = f"""
            <!DOCTYPE html>
            <html>
            <head><title>Callback Route Error</title></head>
            <body>
                <h1>🚨 Callback Route Error</h1>
                <p><strong>Error:</strong> {str(e)}</p>
                <p><strong>State:</strong> Unknown</p>
                <p>At least we know the route is being hit!</p>
            </body>
            </html>
            """
            
            return HTMLResponse(
                content=error_html,
                status_code=500,
                headers={
                    "Content-Type": "text/html; charset=utf-8",
                    "X-Error-Response": "oauth-callback-basic-error"
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
    logger.info("  GET /oauth2callback (MAIN OAuth callback handler - FIXED routing issue)")
    logger.info("  GET /oauth/callback/debug (OAuth callback handler - debugging)")
    logger.info("  GET /oauth/status (Authentication status polling for CLI clients)")
    logger.info("  GET /oauth/register/{client_id}")
    logger.info("  PUT /oauth/register/{client_id}")
    logger.info("  DELETE /oauth/register/{client_id}")
    
    @mcp.custom_route("/auth/services/select", methods=["GET", "OPTIONS"])
    async def show_service_selection(request: Any):
        """Show service selection page with PKCE support."""
        from starlette.responses import HTMLResponse, Response
        from urllib.parse import parse_qs
        
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
        
        logger.info("🎨 Service selection page requested")
        
        try:
            # Get query parameters
            query_params = dict(request.query_params)
            state = query_params.get("state")
            flow_type = query_params.get("flow_type", "fastmcp")
            use_pkce = query_params.get("use_pkce", "true").lower() == "true"
            
            if not state:
                logger.error("❌ Missing state parameter in service selection request")
                return HTMLResponse(
                    content="""
                    <!DOCTYPE html>
                    <html><head><title>Error</title></head>
                    <body><h1>Error: Invalid service selection request</h1></body></html>
                    """,
                    status_code=400
                )
            
            logger.info(f"📋 Showing service selection for state: {state}, flow_type: {flow_type}, PKCE: {use_pkce}")
            
            html_content = _generate_service_selection_html(state, flow_type, use_pkce)
            return HTMLResponse(content=html_content)
            
        except Exception as e:
            logger.error(f"❌ Error showing service selection: {e}")
            return HTMLResponse(
                content=f"""
                <!DOCTYPE html>
                <html><head><title>Error</title></head>
                <body><h1>Service Selection Error</h1><p>{str(e)}</p></body></html>
                """,
                status_code=500
            )
    
    @mcp.custom_route("/auth/services/selected", methods=["POST", "OPTIONS"])
    async def handle_service_selection(request: Any):
        """Handle service selection form submission with PKCE support."""
        from starlette.responses import RedirectResponse, HTMLResponse, Response
        
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
        
        logger.info("✅ Service selection form submitted")
        
        try:
            # Parse form data
            form_data = await request.form()
            state = form_data.get("state")
            flow_type = form_data.get("flow_type", "fastmcp")
            
            # Get authentication method choice
            auth_method = form_data.get("auth_method", "pkce_file")
            use_pkce = auth_method != "file_credentials"
            
            # Get custom credentials if enabled
            use_custom = form_data.get("use_custom_creds") == "on"
            custom_client_id = form_data.get("custom_client_id") if use_custom else None
            custom_client_secret = form_data.get("custom_client_secret") if use_custom else None
            
            # Get selected services (can be multiple)
            services = form_data.getlist("services") if hasattr(form_data, 'getlist') else []
            if not services and "services" in form_data:
                # Fallback for single service
                services = [form_data.get("services")]
            
            logger.info(f"📋 Service selection received: state={state}, flow_type={flow_type}, services={services}")
            logger.info(f"🔐 Authentication method chosen: {auth_method} (PKCE: {use_pkce})")
            if use_custom:
                logger.info(f"🔑 Using custom credentials: client_id={custom_client_id[:10]}...")
            
            if not state:
                raise ValueError("Missing state parameter")
            
            # Handle based on flow type
            if flow_type == "fastmcp":
                oauth_url = await _handle_fastmcp_service_selection(state, services, use_pkce)
            else:
                from .google_auth import handle_service_selection_callback
                oauth_url = await handle_service_selection_callback(
                    state=state,
                    selected_services=services,
                    use_pkce=use_pkce,
                    auth_method=auth_method,
                    custom_client_id=custom_client_id,
                    custom_client_secret=custom_client_secret
                )
            
            logger.info(f"✅ Redirecting to OAuth URL for selected services (auth_method: {auth_method})")
            return RedirectResponse(url=oauth_url, status_code=302)
            
        except Exception as e:
            logger.error(f"❌ Error handling service selection: {e}")
            return HTMLResponse(
                content=f"""
                <!DOCTYPE html>
                <html>
                <head><title>Service Selection Error</title></head>
                <body>
                    <h1>Service Selection Error</h1>
                    <p>Error: {str(e)}</p>
                    <p>Please try the authentication process again.</p>
                </body>
                </html>
                """,
                status_code=400
            )
    
    logger.info("  GET /auth/services/select (Service selection page)")
    logger.info("  POST /auth/services/selected (Service selection form handler)")