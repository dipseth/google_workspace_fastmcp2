"""OAuth 2.1 discovery endpoints using FastMCP custom routes.

This module implements OAuth discovery and Dynamic Client Registration
endpoints using FastMCP's native routing system.
"""

import html
import json
import logging
from datetime import UTC, datetime
from typing import Any, Dict, List

from auth.context import (
    get_session_context,
    set_session_context,
    set_user_email_context,
)
from auth.types import SessionKey
from config.enhanced_logging import setup_logger
from config.settings import settings

# Initialize logger early
logger = setup_logger()

# Import OAuth proxy at module level to ensure singleton behavior
from auth.oauth_proxy import handle_token_exchange, oauth_proxy, refresh_access_token

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
    "https://www.googleapis.com/auth/calendar.readonly",
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

            comprehensive_scopes = ScopeRegistry.resolve_scope_group(
                "oauth_comprehensive"
            )
            logger.info(
                f"📋 Using comprehensive OAuth scopes: {len(comprehensive_scopes)} scopes from registry"
            )
            return comprehensive_scopes
        except Exception as e:
            logger.warning(
                f"Error getting comprehensive OAuth scopes from registry, using compatibility fallback: {e}"
            )
            try:
                # Fallback to legacy OAuth endpoint scopes
                return CompatibilityShim.get_legacy_oauth_endpoint_scopes()
            except Exception as e2:
                logger.warning(
                    f"Error getting legacy OAuth endpoint scopes, using hardcoded fallback: {e2}"
                )
                return _FALLBACK_OAUTH_SCOPES
    else:
        logger.warning("Compatibility shim not available, using fallback scopes")
        return _FALLBACK_OAUTH_SCOPES


from config.enhanced_logging import setup_logger

logger = setup_logger()


async def _store_oauth_user_data_async(
    client_id: str, token_data: Dict[str, Any]
) -> None:
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
            logger.warning(
                f"⚠️ Proxy client not found for async user data storage: {client_id}"
            )
            return

        # Get user email from Google userinfo API using the new tokens

        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        from .dual_auth_bridge import get_dual_auth_bridge
        from .unified_session import UnifiedSession

        # Create credentials from token response
        credentials = Credentials(
            token=token_data.get("access_token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=proxy_client.real_client_id,
            client_secret=proxy_client.real_client_secret,
            scopes=(
                token_data.get("scope", "").split() if token_data.get("scope") else []
            ),
        )

        # Get user email from Google userinfo (run in thread pool to avoid blocking)
        import asyncio

        def get_user_info():
            userinfo_service = build("oauth2", "v2", credentials=credentials)
            return userinfo_service.userinfo().get().execute()

        user_info = await asyncio.to_thread(get_user_info)
        authenticated_email = user_info.get("email")

        if authenticated_email:
            # SECURITY: Validate user access before storing OAuth data
            from auth.access_control import validate_user_access

            if not validate_user_access(authenticated_email):
                logger.warning(
                    f"🚫 OAuth Proxy: Access denied for user: {authenticated_email}"
                )
                return  # Don't store authentication data for unauthorized users
            # INTEGRATE WITH EXISTING INFRASTRUCTURE
            # 1. Use DualAuthBridge to register OAuth Proxy authentication
            dual_bridge = get_dual_auth_bridge()
            dual_bridge.add_secondary_account(authenticated_email)

            # 2. Create UnifiedSession for this OAuth authentication
            unified_session = UnifiedSession()
            legacy_creds_data = {
                "token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "scopes": (
                    token_data.get("scope", "").split()
                    if token_data.get("scope")
                    else []
                ),
                "client_id": proxy_client.real_client_id,
                "client_secret": proxy_client.real_client_secret,
                "token_uri": "https://oauth2.googleapis.com/token",
                "expiry": datetime.now().isoformat(),  # Will be calculated properly
            }

            session_state = unified_session.create_session_from_legacy(
                authenticated_email, legacy_creds_data
            )

            # 3. Bridge credentials from OAuth Proxy to the unified system
            dual_bridge.bridge_credentials(authenticated_email, "memory")

            # 4. Save full credentials to .enc file for multi-client persistence
            # This ALSO updates .oauth_authentication.json automatically via _save_credentials
            from auth.google_auth import _save_credentials, _update_oauth_session_marker

            try:
                _save_credentials(authenticated_email, credentials)
                logger.info(
                    f"✅ Saved full credentials to .enc file for {authenticated_email}"
                )

                # Update .oauth_authentication.json with OAuth Proxy specific extra data
                # (client_id and session_id are OAuth Proxy specific)
                extra_data = {
                    "client_id": client_id,
                    "session_id": session_state.session_id,
                }
                _update_oauth_session_marker(
                    authenticated_email,
                    credentials,
                    auth_provider="oauth_proxy",
                    extra_data=extra_data,
                )
                logger.info(
                    "✅ Updated .oauth_authentication.json with OAuth Proxy metadata"
                )
            except Exception as save_error:
                logger.error(
                    f"❌ Failed to save credentials to .enc file: {save_error}"
                )
                # Continue anyway - at least we tried

            logger.info(
                f"✅ Integrated OAuth Proxy authentication for user: {authenticated_email}"
            )
            logger.info(f"   Session ID: {session_state.session_id}")
            logger.info("   Registered with DualAuthBridge as secondary account")
            logger.info("   Created UnifiedSession with legacy credentials")
            logger.info("   Saved persistent credentials for multi-client sharing")

            # Try to set context if available (won't work outside FastMCP request but worth trying)
            try:
                session_id = await get_session_context() or session_state.session_id
                await set_session_context(session_id)
                await set_user_email_context(authenticated_email)
                logger.info(
                    f"🔗 Set session context for OAuth proxy user: {authenticated_email}"
                )
            except RuntimeError:
                # Expected when not in FastMCP request context
                logger.info(
                    "📝 OAuth authentication integrated for later use (not in FastMCP context)"
                )
        else:
            logger.warning(
                "⚠️ Could not determine user email from OAuth token exchange (async)"
            )

    except Exception as e:
        logger.error(
            f"❌ Failed to integrate OAuth authentication data (async): {e}",
            exc_info=True,
        )
        # This is background processing, so we don't want to crash anything


def _generate_service_selection_html(
    state: str, flow_type: str, use_pkce: bool = True
) -> str:
    """Generate the service selection page HTML with authentication method choice."""
    from config.settings import settings as _settings

    _env_client_id = (
        _settings.google_client_id or _settings.fastmcp_server_auth_google_client_id
    )
    _env_client_secret = (
        _settings.google_client_secret
        or _settings.fastmcp_server_auth_google_client_secret
    )
    _env_has_creds = bool(_env_client_id and _env_client_secret)
    _env_client_id_display = (_env_client_id[:20] + "...") if _env_client_id else ""
    _redirect_uri = getattr(
        _settings, "dynamic_oauth_redirect_uri", "https://localhost:8002/oauth2callback"
    )
    _sa_file_configured = bool(_settings.chat_service_account_file)

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

        # Build env-configured credentials banner or empty state
        if _env_has_creds:
            creds_status_html = f"""
                <div style="display:flex;align-items:center;gap:10px;background:rgba(52,168,83,0.08);
                            border:1px solid rgba(52,168,83,0.3);border-radius:10px;padding:12px 16px;margin-bottom:12px;">
                    <span style="font-size:20px">✅</span>
                    <div>
                        <div style="font-size:13px;font-weight:600;color:#137333">Environment credentials configured</div>
                        <div style="font-size:11px;color:#5f6368;font-family:monospace;margin-top:2px">{_env_client_id_display}</div>
                    </div>
                    <div style="margin-left:auto;font-size:11px;color:#137333;background:rgba(52,168,83,0.12);
                                padding:3px 10px;border-radius:12px;font-weight:600">AUTO</div>
                </div>"""
            creds_hint = "Override below only if you need different credentials for this session."
        else:
            creds_status_html = f"""
                <div style="display:flex;align-items:center;gap:10px;background:rgba(234,67,53,0.06);
                            border:1px solid rgba(234,67,53,0.2);border-radius:10px;padding:12px 16px;margin-bottom:12px;">
                    <span style="font-size:20px">⚠️</span>
                    <div>
                        <div style="font-size:13px;font-weight:600;color:#c5221f">No environment credentials found</div>
                        <div style="font-size:11px;color:#5f6368;margin-top:2px">Set GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET or enter below</div>
                    </div>
                </div>"""
            creds_hint = "Enter your Google OAuth credentials to continue."

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Google Authentication — FastMCP</title>
    <style>
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: flex-start;
            justify-content: center;
            padding: 40px 20px;
        }}
        .card {{
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.18);
            width: 100%;
            max-width: 680px;
            overflow: hidden;
        }}
        /* Header — matches success screen gradient treatment */
        .card-header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 36px 40px 30px;
            text-align: center;
            color: white;
        }}
        .card-header .icon {{ font-size: 52px; margin-bottom: 12px; }}
        .card-header h1 {{ font-size: 26px; font-weight: 700; margin-bottom: 6px; }}
        .card-header p {{ font-size: 14px; opacity: 0.85; }}
        .card-body {{ padding: 32px 40px 40px; }}

        /* Section panels */
        .panel {{
            border: 1.5px solid #e8eaed;
            border-radius: 12px;
            margin-bottom: 20px;
            overflow: hidden;
        }}
        .panel-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 14px 18px;
            background: #f8f9fa;
            border-bottom: 1px solid #e8eaed;
            cursor: pointer;
            user-select: none;
        }}
        .panel-header .panel-icon {{ font-size: 18px; }}
        .panel-header .panel-title {{ font-size: 14px; font-weight: 600; color: #202124; flex: 1; }}
        .panel-header .panel-badge {{
            font-size: 11px; font-weight: 600; padding: 2px 10px;
            border-radius: 12px; background: #e8f0fe; color: #1a73e8;
        }}
        .panel-header .panel-badge.green {{ background: rgba(52,168,83,0.1); color: #137333; }}
        .panel-header .chevron {{
            font-size: 12px; color: #9aa0a6; transition: transform 0.2s;
        }}
        .panel-header.collapsed .chevron {{ transform: rotate(-90deg); }}
        .panel-body {{ padding: 18px; }}

        /* Auth method cards */
        .auth-options {{ display: flex; gap: 12px; }}
        .auth-option {{
            flex: 1; padding: 16px; border: 2px solid #e8eaed; border-radius: 10px;
            cursor: pointer; transition: all 0.15s ease; background: white;
        }}
        .auth-option:hover {{ border-color: #764ba2; background: #f8f5ff; }}
        .auth-option.selected {{ border-color: #667eea; background: #f0eeff; }}
        .auth-option input[type="radio"] {{ display: none; }}
        .auth-option-name {{ font-size: 13px; font-weight: 600; color: #202124; margin-bottom: 5px; }}
        .auth-option-desc {{ font-size: 12px; color: #5f6368; line-height: 1.4; }}
        .auth-option-pros {{ font-size: 11px; color: #137333; margin-top: 6px; }}
        .auth-option-cons {{ font-size: 11px; color: #d93025; margin-top: 3px; }}

        /* Service chips */
        .services-grid {{ display: flex; flex-wrap: wrap; gap: 6px; }}
        .service-chip {{
            display: flex; align-items: center; gap: 5px;
            padding: 5px 10px; border: 1.5px solid #e8eaed; border-radius: 20px;
            cursor: pointer; transition: all 0.15s ease; background: white;
            font-size: 12px; color: #202124;
        }}
        .service-chip:hover {{ border-color: #764ba2; background: #f8f5ff; }}
        .service-chip.checked {{ border-color: #667eea; background: #f0eeff; color: #4527a0; }}
        .service-chip.required {{ border-color: #34a853; background: #e8f5e9; color: #1b5e20; cursor: default; }}
        .service-chip input {{ display: none; }}
        .service-chip .chip-check {{ font-size: 11px; }}
        .category-label {{
            font-size: 10px; font-weight: 600; text-transform: uppercase;
            letter-spacing: 0.8px; color: #9aa0a6; margin: 10px 0 5px;
        }}
        .category-label:first-child {{ margin-top: 0; }}

        /* Credential inputs */
        .field-group {{ display: flex; flex-direction: column; gap: 10px; }}
        .field-input {{
            width: 100%; padding: 11px 14px; border: 1.5px solid #dadce0;
            border-radius: 8px; font-size: 13px; color: #202124;
            transition: border-color 0.15s; outline: none; font-family: monospace;
        }}
        .field-input:focus {{ border-color: #667eea; box-shadow: 0 0 0 3px rgba(102,126,234,0.12); }}
        .field-label {{ font-size: 12px; color: #5f6368; margin-bottom: 4px; font-weight: 500; }}
        .field-hint {{ font-size: 11px; color: #9aa0a6; margin-top: 4px; }}
        .redirect-uri {{
            font-family: monospace; font-size: 12px; background: #f8f9fa;
            padding: 8px 12px; border-radius: 6px; border: 1px solid #e8eaed;
            color: #5f6368; word-break: break-all;
        }}

        /* Toggle row */
        .toggle-row {{
            display: flex; align-items: center; gap: 12px; padding: 4px 0;
        }}
        .toggle-label {{ font-size: 13px; color: #202124; flex: 1; }}
        .toggle-desc {{ font-size: 11px; color: #9aa0a6; margin-top: 2px; }}
        /* Native checkbox styled */
        .toggle-row input[type="checkbox"] {{ transform: scale(1.25); accent-color: #667eea; cursor: pointer; }}

        /* Passphrase field */
        .passphrase-wrap {{ margin-top: 14px; padding-top: 14px; border-top: 1px solid #f1f3f4; }}

        /* Info/warning boxes */
        .info-box {{
            border-radius: 8px; padding: 12px 14px; font-size: 12px; line-height: 1.5;
            margin-bottom: 12px;
        }}
        .info-box.blue {{ background: #e8f0fe; color: #1a56a0; border: 1px solid #c5d8f8; }}
        .info-box.amber {{ background: #fff8e1; color: #795700; border: 1px solid #ffe08a; }}
        .info-box.red {{ background: #fce8e6; color: #c5221f; border: 1px solid #f5c6c3; }}
        .info-box a {{ color: inherit; }}

        /* Hint bar */
        .hint-bar {{
            display: flex; align-items: center; gap: 8px;
            background: #f0eeff; border-radius: 8px; padding: 10px 14px;
            margin-bottom: 20px; font-size: 12px; color: #4527a0;
        }}

        /* Actions */
        .actions {{
            display: flex; align-items: center; gap: 12px;
            padding-top: 24px; border-top: 1px solid #f1f3f4; margin-top: 4px;
        }}
        .btn-primary {{
            flex: 1; padding: 14px; border: none; border-radius: 10px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; font-size: 15px; font-weight: 600; cursor: pointer;
            transition: opacity 0.15s; letter-spacing: 0.2px;
        }}
        .btn-primary:hover {{ opacity: 0.92; }}
        .btn-secondary {{
            padding: 14px 18px; border: 1.5px solid #dadce0; border-radius: 10px;
            background: white; color: #3c4043; font-size: 14px; font-weight: 500;
            cursor: pointer; transition: background 0.15s; white-space: nowrap;
        }}
        .btn-secondary:hover {{ background: #f8f9fa; }}
    </style>
</head>
<body>
<div class="card">
    <div class="card-header">
        <div class="icon">🔐</div>
        <h1>Google Authentication</h1>
        <p>Select services and configure your auth method for FastMCP</p>
    </div>
    <div class="card-body">
        <form method="POST" action="/auth/services/selected" id="auth-form">
            <input type="hidden" name="state" value="{state}">
            <input type="hidden" name="flow_type" value="{flow_type}">

            <!-- Auth Method -->
            <div class="panel">
                <div class="panel-header" onclick="togglePanel('auth-method-body', this)">
                    <span class="panel-icon">🔒</span>
                    <span class="panel-title">Authentication Method</span>
                    <span class="panel-badge">{"PKCE (Recommended)" if use_pkce else "Legacy OAuth"}</span>
                    <span class="chevron">▼</span>
                </div>
                <div class="panel-body" id="auth-method-body">
                    <div class="auth-options">
                        <div class="auth-option {"selected" if use_pkce else ""}" onclick="selectAuthMethod('pkce', this)">
                            <input type="radio" name="auth_method" value="pkce" {"checked" if use_pkce else ""}>
                            <div class="auth-option-name">🔐 PKCE Flow</div>
                            <div class="auth-option-desc">OAuth 2.1 with Proof Key for Code Exchange — enhanced security</div>
                            <div class="auth-option-pros">✅ Best security · Code verifier protection · Encrypted storage</div>
                            <div class="auth-option-cons">⚠️ Requires client secret for web apps</div>
                        </div>
                        <div class="auth-option {"selected" if not use_pkce else ""}" onclick="selectAuthMethod('credentials', this)">
                            <input type="radio" name="auth_method" value="credentials" {"checked" if not use_pkce else ""}>
                            <div class="auth-option-name">📁 Legacy OAuth 2.0</div>
                            <div class="auth-option-desc">Traditional OAuth flow with encrypted credential storage</div>
                            <div class="auth-option-pros">✅ Multi-account support · Persists across restarts</div>
                            <div class="auth-option-cons">⚠️ No PKCE enhancement</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- OAuth Credentials (optional override) -->
            <div class="panel">
                <div class="panel-header" onclick="togglePanel('creds-body', this)">
                    <span class="panel-icon">🔑</span>
                    <span class="panel-title">OAuth Credentials</span>
                    <span class="panel-badge {"green" if _env_has_creds else ""}">{"Env configured" if _env_has_creds else "Manual entry"}</span>
                    <span class="chevron">▼</span>
                </div>
                <div class="panel-body" id="creds-body">
                    {creds_status_html}
                    <label style="display:flex;align-items:center;gap:10px;margin-bottom:14px;cursor:pointer;">
                        <input type="checkbox" id="use_custom_creds" name="use_custom_creds"
                               style="transform:scale(1.2);accent-color:#667eea;">
                        <span style="font-size:13px;color:#202124;font-weight:500;">
                            Override with custom credentials
                        </span>
                    </label>
                    <div id="custom-creds-fields" style="display:none;">
                        <div class="info-box amber" style="margin-bottom:12px;">
                            <strong>Redirect URI required in Google Cloud Console:</strong><br>
                            <div class="redirect-uri" style="margin-top:6px;">{_redirect_uri}</div>
                        </div>
                        <div class="field-group">
                            <div>
                                <div class="field-label">Client ID</div>
                                <input type="text" name="custom_client_id" class="field-input"
                                       placeholder="xxxxxx.apps.googleusercontent.com"
                                       value="{_env_client_id if _env_has_creds else ""}">
                                <div class="field-hint">From Google Cloud Console → APIs &amp; Services → Credentials</div>
                            </div>
                            <div>
                                <div class="field-label">Client Secret</div>
                                <input type="text" name="custom_client_secret" class="field-input"
                                       placeholder="GOCSPX-..."
                                       value="{_env_client_secret if _env_has_creds else ""}">
                                <div class="field-hint">Optional for PKCE flow · Not recommended to enter in production UI</div>
                            </div>
                        </div>
                        <div class="info-box blue" style="margin-top:12px;">
                            <strong>🔧 Cloud Console setup:</strong>
                            <a href="https://console.cloud.google.com/apis/credentials" target="_blank">
                                APIs &amp; Services → Credentials
                            </a> · Create/edit OAuth 2.0 Client ID · Add redirect URI above · Enable required APIs
                        </div>
                    </div>
                    <div style="font-size:11px;color:#9aa0a6;margin-top:4px;">{creds_hint}</div>
                </div>
            </div>

            <!-- Cross-OAuth Linkage -->
            <div class="panel">
                <div class="panel-header" onclick="togglePanel('linkage-body', this)">
                    <span class="panel-icon">🔗</span>
                    <span class="panel-title">Cross-OAuth Account Access</span>
                    <span class="panel-badge green">Enabled</span>
                    <span class="chevron">▼</span>
                </div>
                <div class="panel-body" id="linkage-body">
                    <div class="toggle-row">
                        <div>
                            <div class="toggle-label">Allow cross-OAuth access to this account</div>
                            <div class="toggle-desc">Linked accounts can access credentials without a per-user API key</div>
                        </div>
                        <input type="checkbox" id="oauth_linkage_enabled" name="oauth_linkage_enabled" checked
                               onchange="document.getElementById('oauth-password-field').style.display=this.checked?'block':'none';">
                    </div>
                    <div id="oauth-password-field" class="passphrase-wrap">
                        <div class="field-label">Optional passphrase (alphanumeric, _, - only)</div>
                        <input type="text" name="oauth_linkage_password" class="field-input"
                               placeholder="Leave blank for no passphrase"
                               pattern="[0-9A-Za-z_-]*"
                               title="Only 0-9, A-Z, a-z, underscore, and hyphen allowed"
                               style="max-width:320px;margin-top:6px;">
                        <div class="field-hint">If set, OAuth sessions require this passphrase to access your credentials.</div>
                    </div>
                </div>
            </div>

            <!-- Chat Bot Service Account (Optional) -->
            <div class="panel">
                <div class="panel-header collapsed" onclick="togglePanel('chat-sa-body', this)">
                    <span class="panel-icon">🤖</span>
                    <span class="panel-title">Chat Bot Service Account</span>
                    <span class="panel-badge {"green" if _sa_file_configured else ""}" id="chat-sa-badge">{"Env configured" if _sa_file_configured else "Optional"}</span>
                    <span class="chevron">▼</span>
                </div>
                <div class="panel-body" id="chat-sa-body" style="display:none;">
                    {"" if not _sa_file_configured else '<div style="display:flex;align-items:center;gap:10px;background:rgba(52,168,83,0.08);border:1px solid rgba(52,168,83,0.3);border-radius:10px;padding:12px 16px;margin-bottom:12px;"><span style="font-size:20px">✅</span><div><div style="font-size:13px;font-weight:600;color:#137333">Global service account configured via environment</div><div style="font-size:11px;color:#5f6368;margin-top:2px">Upload below only to use a different SA for your account</div></div></div>'}
                    <div class="info-box blue" style="line-height:1.7;">
                        <strong>What is this?</strong><br>
                        A Google Chat service account lets the MCP server act as a Chat bot &mdash;
                        sending messages, managing spaces, and performing reactions via Domain-Wide
                        Delegation (DWD).
                        <br><br>
                        <strong>Setup steps:</strong>
                        <ol style="margin:6px 0 0 16px;padding:0;">
                            <li>Create a service account in
                                <a href="https://console.cloud.google.com/iam-admin/serviceaccounts/create"
                                   target="_blank" rel="noopener">Cloud Console &rarr; Service Accounts</a></li>
                            <li>Enable the
                                <a href="https://console.cloud.google.com/apis/library/chat.googleapis.com"
                                   target="_blank" rel="noopener">Google Chat API</a></li>
                            <li>Create &amp; download a JSON key from
                                <a href="https://console.cloud.google.com/apis/credentials"
                                   target="_blank" rel="noopener">APIs &amp; Services &rarr; Credentials</a></li>
                            <li>In <a href="https://admin.google.com/ac/owl/domainwidedelegation"
                                      target="_blank" rel="noopener">Admin Console &rarr; Domain-wide Delegation</a>,
                                add the SA client ID with these scopes:</li>
                        </ol>
                        <div style="position:relative;margin-top:8px;">
                            <div id="dwd-scopes-display" style="background:rgba(0,0,0,0.04);border-radius:6px;padding:8px 10px 8px 10px;
                                        font-family:monospace;font-size:10px;word-break:break-all;">
                                https://www.googleapis.com/auth/chat.spaces,<br>
                                https://www.googleapis.com/auth/chat.spaces.create,<br>
                                https://www.googleapis.com/auth/chat.delete,<br>
                                https://www.googleapis.com/auth/chat.app.delete,<br>
                                https://www.googleapis.com/auth/chat.memberships,<br>
                                https://www.googleapis.com/auth/chat.memberships.readonly,<br>
                                https://www.googleapis.com/auth/chat.memberships.app,<br>
                                https://www.googleapis.com/auth/chat.messages,<br>
                                https://www.googleapis.com/auth/chat.messages.readonly,<br>
                                https://www.googleapis.com/auth/chat.messages.create,<br>
                                https://www.googleapis.com/auth/chat.app.memberships,<br>
                                https://www.googleapis.com/auth/chat.app.spaces,<br>
                                https://www.googleapis.com/auth/chat.app.spaces.create,<br>
                                https://www.googleapis.com/auth/chat.messages.reactions,<br>
                                https://www.googleapis.com/auth/chat.messages.reactions.create,<br>
                                https://www.googleapis.com/auth/chat.messages.reactions.readonly
                            </div>
                            <button type="button" onclick="copyDwdScopes(this)"
                                    style="position:absolute;top:6px;right:6px;background:#fff;border:1px solid #dadce0;
                                           border-radius:6px;padding:4px 10px;font-size:11px;cursor:pointer;
                                           color:#1a73e8;font-weight:500;transition:all 0.15s;">
                                📋 Copy scopes
                            </button>
                        </div>
                    </div>
                    <div style="margin-top:14px;">
                        <div class="field-label">Service Account JSON Key</div>
                        <textarea name="chat_sa_json" id="chat_sa_json"
                                  class="field-input" rows="6"
                                  placeholder="Paste the full JSON key here, or use the file picker below..."
                                  style="font-family:monospace;font-size:11px;resize:vertical;"></textarea>
                        <div style="margin-top:8px;display:flex;align-items:center;gap:10px;">
                            <label class="btn-secondary" style="padding:8px 14px;font-size:12px;cursor:pointer;">
                                📁 Choose JSON file
                                <input type="file" id="chat_sa_file" accept=".json"
                                       style="display:none;"
                                       onchange="handleSAFileUpload(this)">
                            </label>
                            <span id="chat-sa-filename" style="font-size:11px;color:#5f6368;"></span>
                        </div>
                        <div class="field-hint">
                            The JSON key will be encrypted and bound to the email you authenticate with.
                            It is never stored in plaintext.
                        </div>
                    </div>
                </div>
            </div>

            <!-- Service Selection -->
            <div class="panel">
                <div class="panel-header collapsed" onclick="togglePanel('services-body', this)">
                    <span class="panel-icon">🚀</span>
                    <span class="panel-title">Google Services</span>
                    <span class="panel-badge" id="services-badge">Loading...</span>
                    <span class="chevron">▼</span>
                </div>
                <div class="panel-body" id="services-body" style="display:none;">
                    <div class="hint-bar" style="font-size:11px;padding:8px 12px;">
                        💡 Common services pre-selected — expand to change
                    </div>
                    <div class="services-grid" id="services-grid">
"""

        # Sort categories
        category_order = [
            "Core Services",
            "Storage & Files",
            "Communication",
            "Productivity",
            "Office Suite",
            "Other",
        ]
        sorted_categories = sorted(
            categories.items(),
            key=lambda x: category_order.index(x[0])
            if x[0] in category_order
            else len(category_order),
        )

        for category_name, services in sorted_categories:
            html += (
                f'<div class="category-label" style="width:100%">{category_name}</div>'
            )
            for service_key, service_info in services:
                required = service_info.get("required", False)
                chip_class = "service-chip required" if required else "service-chip"
                disabled_attr = "disabled" if required else ""
                check_icon = "✅" if required else "◻"
                html += f"""
                        <label class="{chip_class}" title="{service_info["description"]}">
                            <input type="checkbox" name="services" value="{service_key}" {disabled_attr}
                                   onchange="updateChip(this);updateBadge();">
                            <span class="chip-check">{check_icon}</span>
                            <span>{service_info["name"]}{"&nbsp;🔒" if required else ""}</span>
                        </label>"""

        html += f"""
                    </div>
                    <div style="display:flex;gap:6px;margin-top:10px;">
                        <button type="button" onclick="selectAll()" class="btn-secondary" style="font-size:11px;padding:6px 12px;">Toggle All</button>
                        <button type="button" onclick="selectCommon()" class="btn-secondary" style="font-size:11px;padding:6px 12px;">Reset to Common</button>
                    </div>
                </div>
            </div>

            <div class="actions">
                <button type="submit" class="btn-primary">Continue with Selected Configuration</button>
                <button type="button" class="btn-secondary" onclick="selectCommon()">Reset</button>
            </div>
        </form>
    </div>
</div>

<script>
    const COMMON_SERVICES = ['drive','gmail','calendar','docs','sheets','slides','photos','chat','forms','people'];

    function copyDwdScopes(btn) {{
        const scopes = 'https://www.googleapis.com/auth/chat.spaces,https://www.googleapis.com/auth/chat.spaces.create,https://www.googleapis.com/auth/chat.delete,https://www.googleapis.com/auth/chat.app.delete,https://www.googleapis.com/auth/chat.memberships,https://www.googleapis.com/auth/chat.memberships.readonly,https://www.googleapis.com/auth/chat.memberships.app,https://www.googleapis.com/auth/chat.messages,https://www.googleapis.com/auth/chat.messages.readonly,https://www.googleapis.com/auth/chat.messages.create,https://www.googleapis.com/auth/chat.app.memberships,https://www.googleapis.com/auth/chat.app.spaces,https://www.googleapis.com/auth/chat.app.spaces.create,https://www.googleapis.com/auth/chat.messages.reactions,https://www.googleapis.com/auth/chat.messages.reactions.create,https://www.googleapis.com/auth/chat.messages.reactions.readonly';
        navigator.clipboard.writeText(scopes).then(function() {{
            btn.textContent = '✅ Copied!';
            btn.style.color = '#137333';
            btn.style.borderColor = '#34a853';
            setTimeout(function() {{
                btn.textContent = '📋 Copy scopes';
                btn.style.color = '#1a73e8';
                btn.style.borderColor = '#dadce0';
            }}, 2000);
        }});
    }}

    function handleSAFileUpload(input) {{
        const file = input.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = function(e) {{
            try {{
                const parsed = JSON.parse(e.target.result);
                if (!parsed.type || parsed.type !== 'service_account') {{
                    alert('This does not appear to be a Google service account JSON key (missing "type": "service_account").');
                    return;
                }}
                document.getElementById('chat_sa_json').value = e.target.result;
                document.getElementById('chat-sa-filename').textContent = file.name;
                const badge = document.getElementById('chat-sa-badge');
                if (badge) {{ badge.textContent = 'Provided'; badge.classList.add('green'); }}
            }} catch(err) {{
                alert('Invalid JSON file: ' + err.message);
            }}
        }};
        reader.readAsText(file);
    }}

    function updateChip(checkbox) {{
        const chip = checkbox.closest('.service-chip');
        if (!chip || chip.classList.contains('required')) return;
        const icon = chip.querySelector('.chip-check');
        if (checkbox.checked) {{
            chip.classList.add('checked');
            if (icon) icon.textContent = '✅';
        }} else {{
            chip.classList.remove('checked');
            if (icon) icon.textContent = '◻';
        }}
    }}

    function updateBadge() {{
        const checked = document.querySelectorAll('input[name="services"]:checked').length;
        const badge = document.getElementById('services-badge');
        if (badge) badge.textContent = checked + ' selected';
    }}

    function selectCommon() {{
        document.querySelectorAll('input[name="services"]:not(:disabled)').forEach(cb => {{
            cb.checked = COMMON_SERVICES.includes(cb.value);
            updateChip(cb);
        }});
        updateBadge();
    }}

    function selectAll() {{
        const boxes = document.querySelectorAll('input[name="services"]:not(:disabled)');
        const allChecked = Array.from(boxes).every(cb => cb.checked);
        boxes.forEach(cb => {{ cb.checked = !allChecked; updateChip(cb); }});
        updateBadge();
    }}

    function selectAuthMethod(method, element) {{
        document.querySelectorAll('.auth-option').forEach(o => o.classList.remove('selected'));
        element.classList.add('selected');
        element.querySelector('input[type="radio"]').checked = true;
        // Update badge
        const badge = element.closest('.panel').querySelector('.panel-badge');
        if (badge) badge.textContent = method === 'pkce' ? 'PKCE (Recommended)' : 'Legacy OAuth';
    }}

    function togglePanel(bodyId, headerEl) {{
        const body = document.getElementById(bodyId);
        if (!body) return;
        const hidden = body.style.display === 'none';
        body.style.display = hidden ? '' : 'none';
        if (headerEl) headerEl.classList.toggle('collapsed', !hidden);
    }}

    document.addEventListener('DOMContentLoaded', function() {{
        // Pre-select common services
        selectCommon();
        // Required checkboxes always checked
        document.querySelectorAll('input[name="services"]:disabled').forEach(cb => {{
            cb.checked = true; updateChip(cb);
        }});
        updateBadge();

        // Custom creds toggle
        const customCheck = document.getElementById('use_custom_creds');
        const customFields = document.getElementById('custom-creds-fields');
        if (customCheck && customFields) {{
            customCheck.addEventListener('change', function() {{
                customFields.style.display = this.checked ? 'block' : 'none';
                if (!this.checked) {{
                    customFields.querySelectorAll('input[type="text"]').forEach(i => i.value = '');
                }}
            }});
        }}

        // Form validation
        document.getElementById('auth-form').addEventListener('submit', function(e) {{
            const useCustom = customCheck && customCheck.checked;
            if (useCustom) {{
                const clientId = document.querySelector('input[name="custom_client_id"]');
                if (!clientId || !clientId.value.trim()) {{
                    e.preventDefault();
                    alert('Please provide a Client ID when using custom credentials.');
                    if (clientId) clientId.focus();
                    return;
                }}
                if (!clientId.value.includes('.apps.googleusercontent.com')) {{
                    if (!confirm('Client ID doesn\\'t look like a Google OAuth ID (should end in .apps.googleusercontent.com). Continue anyway?')) {{
                        e.preventDefault();
                    }}
                }}
            }}
            // Validate Chat SA JSON if provided
            const saJson = document.getElementById('chat_sa_json');
            if (saJson && saJson.value.trim()) {{
                try {{
                    const parsed = JSON.parse(saJson.value.trim());
                    if (parsed.type !== 'service_account') {{
                        e.preventDefault();
                        alert('The Chat service account JSON must have "type": "service_account". Please check the file.');
                        saJson.focus();
                        return;
                    }}
                }} catch(err) {{
                    e.preventDefault();
                    alert('The Chat service account JSON is not valid JSON: ' + err.message);
                    saJson.focus();
                    return;
                }}
            }}
        }});

        // Auth method click handlers
        document.querySelectorAll('.auth-option').forEach(opt => {{
            opt.addEventListener('click', function() {{
                selectAuthMethod(this.querySelector('input').value, this);
            }});
        }});
    }});
</script>
</body>
</html>"""

        return html

    except Exception as e:
        logger.error(f"Error generating service selection HTML: {e}")
        return f"""<!DOCTYPE html>
<html><head><title>Error</title></head>
<body style="font-family:sans-serif;padding:40px">
<h1>Service Selection Error</h1><p>{html.escape(str(e))}</p>
</body></html>"""


async def _handle_fastmcp_service_selection(
    state: str, services: List[str], use_pkce: bool = True
) -> str:
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

        logger.info(
            f"🔧 FastMCP service selection: {len(services)} services selected, {len(scopes)} scopes (PKCE: {use_pkce})"
        )

        # For FastMCP integration, we'll fall back to the custom OAuth flow for now
        # In the future, this could integrate more directly with GoogleProvider
        from .google_auth import handle_service_selection_callback

        return await handle_service_selection_callback(state, services)

    except Exception as e:
        logger.error(f"Error handling FastMCP service selection: {e}")
        raise


def setup_service_selection_routes(mcp) -> None:
    """Register /auth/services/select and /auth/services/selected routes.

    These are needed by the ``start_google_auth`` scope-upgrade flow regardless
    of whether GoogleProvider or the legacy OAuth system is active.  Extracted
    so that ``server.py`` can call this independently.
    """

    @mcp.custom_route("/auth/services/select", methods=["GET", "OPTIONS"])
    async def show_service_selection(request: Any):
        """Show service selection page with PKCE support."""
        from starlette.responses import HTMLResponse, Response

        if request.method == "OPTIONS":
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                },
            )

        logger.info("🎨 Service selection page requested")
        try:
            query_params = dict(request.query_params)
            state = query_params.get("state")
            flow_type = query_params.get("flow_type", "fastmcp")
            use_pkce = query_params.get("use_pkce", "true").lower() == "true"

            if not state:
                logger.error("❌ Missing state parameter in service selection request")
                return HTMLResponse(
                    content="<!DOCTYPE html><html><head><title>Error</title></head>"
                    "<body><h1>Error: Invalid service selection request</h1></body></html>",
                    status_code=400,
                )

            logger.info(
                f"📋 Showing service selection for state: {state}, "
                f"flow_type: {flow_type}, PKCE: {use_pkce}"
            )
            html_content = _generate_service_selection_html(state, flow_type, use_pkce)
            return HTMLResponse(content=html_content)

        except Exception as e:
            logger.error(f"❌ Error showing service selection: {e}")
            return HTMLResponse(
                content=f"<!DOCTYPE html><html><head><title>Error</title></head>"
                f"<body><h1>Service Selection Error</h1><p>{html.escape(str(e))}</p></body></html>",
                status_code=500,
            )

    @mcp.custom_route("/auth/services/selected", methods=["POST", "OPTIONS"])
    async def handle_service_selection(request: Any):
        """Handle service selection form submission with PKCE support."""
        from starlette.responses import HTMLResponse, RedirectResponse, Response

        if request.method == "OPTIONS":
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                },
            )

        logger.info("✅ Service selection form submitted")
        try:
            form_data = await request.form()
            state = form_data.get("state")
            flow_type = form_data.get("flow_type", "fastmcp")
            auth_method = form_data.get("auth_method", "pkce_file")
            use_pkce = auth_method != "file_credentials"
            use_custom = form_data.get("use_custom_creds") == "on"
            custom_client_id = form_data.get("custom_client_id") if use_custom else None
            custom_client_secret = (
                form_data.get("custom_client_secret") if use_custom else None
            )
            services = (
                form_data.getlist("services") if hasattr(form_data, "getlist") else []
            )
            if not services and "services" in form_data:
                services = [form_data.get("services")]

            # Cross-OAuth linkage preference
            oauth_linkage_enabled = form_data.get("oauth_linkage_enabled") == "on"
            oauth_linkage_password = (
                form_data.get("oauth_linkage_password") or ""
            ).strip()

            # Chat service account JSON (optional)
            chat_sa_json = None
            chat_sa_json_raw = (form_data.get("chat_sa_json") or "").strip()
            if chat_sa_json_raw:
                try:
                    import json as _json

                    parsed_sa = _json.loads(chat_sa_json_raw)
                    if parsed_sa.get("type") != "service_account":
                        logger.warning(
                            "Chat SA JSON rejected: missing 'type': 'service_account'"
                        )
                    else:
                        chat_sa_json = chat_sa_json_raw
                        logger.info("🤖 Chat service account JSON provided")
                except Exception as sa_err:
                    logger.warning(f"Chat SA JSON rejected: invalid JSON: {sa_err}")

            logger.info(
                f"📋 Service selection received: state={state}, "
                f"flow_type={flow_type}, services={services}"
            )
            logger.info(
                f"🔐 Authentication method chosen: {auth_method} (PKCE: {use_pkce})"
            )
            logger.info(
                f"🔗 Cross-OAuth linkage: enabled={oauth_linkage_enabled}, "
                f"password={'set' if oauth_linkage_password else 'none'}"
            )
            if use_custom and custom_client_id:
                logger.info(
                    f"🔑 Using custom credentials: client_id={custom_client_id[:10]}..."
                )

            if not state:
                raise ValueError("Missing state parameter")

            # Store cross-OAuth preference immediately.  The password is persisted
            # per-email so _save_credentials can pick it up after OAuth redirects.
            from .google_auth import _service_selection_cache

            if state in _service_selection_cache:
                user_email_for_linkage = _service_selection_cache[state].get(
                    "user_email", ""
                )
                if user_email_for_linkage:
                    from .user_api_keys import set_oauth_linkage

                    set_oauth_linkage(
                        user_email_for_linkage,
                        enabled=oauth_linkage_enabled,
                    )
                # Stash password in cache — it flows through to _save_credentials
                # in-memory only, never persisted to disk
                _service_selection_cache[state]["oauth_linkage_password"] = (
                    oauth_linkage_password
                )
                # Stash Chat SA JSON — encrypted after OAuth completes
                if chat_sa_json:
                    _service_selection_cache[state]["chat_sa_json"] = chat_sa_json

            if flow_type == "fastmcp":
                oauth_url = await _handle_fastmcp_service_selection(
                    state, services, use_pkce
                )
            else:
                from .google_auth import handle_service_selection_callback

                oauth_url = await handle_service_selection_callback(
                    state=state,
                    selected_services=services,
                    use_pkce=use_pkce,
                    auth_method=auth_method,
                    custom_client_id=custom_client_id,
                    custom_client_secret=custom_client_secret,
                )

            logger.info(
                f"✅ Redirecting to OAuth URL for selected services "
                f"(auth_method: {auth_method})"
            )
            return RedirectResponse(url=oauth_url, status_code=302)

        except Exception as e:
            logger.error(f"❌ Error handling service selection: {e}")
            return HTMLResponse(
                content=f"<!DOCTYPE html><html><head><title>Service Selection Error</title></head>"
                f"<body><h1>Service Selection Error</h1>"
                f"<p>Error: {html.escape(str(e))}</p>"
                f"<p>Please try the authentication process again.</p></body></html>",
                status_code=400,
            )

    logger.info("  GET /auth/services/select (Service selection page)")
    logger.info("  POST /auth/services/selected (Service selection form handler)")


def setup_legacy_callback_route(mcp) -> None:
    """Register only the /oauth2callback route.

    This is needed when GoogleProvider is active so the legacy
    ``start_google_auth`` tool flow can still complete Google OAuth
    and store real Google API credentials.  The full
    ``setup_oauth_endpoints_fastmcp`` is NOT called in that mode
    because GoogleProvider already provides /authorize, /token, etc.
    """

    @mcp.custom_route("/oauth2callback", methods=["GET", "OPTIONS"])
    async def oauth2callback_legacy(request: Any):
        """OAuth2 callback for the legacy start_google_auth flow.

        Delegates to the same handler logic used by the full endpoint set.
        """
        from starlette.responses import HTMLResponse, Response

        from auth.access_control import validate_user_access
        from auth.context import get_session_context, store_session_data
        from auth.google_auth import handle_oauth_callback
        from auth.pkce_utils import pkce_manager

        logger.info("🚨 /oauth2callback hit (legacy route, GoogleProvider mode)")

        if request.method == "OPTIONS":
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                },
            )

        try:
            query_params = dict(request.query_params)
            state = query_params.get("state")
            code = query_params.get("code")
            error = query_params.get("error")

            logger.info(
                f"🔍 oauth2callback params: state={state[:20] if state else 'MISSING'}... "
                f"code={'PRESENT' if code else 'MISSING'} error={error or 'None'}"
            )

            # Retrieve PKCE code verifier if available
            code_verifier = None
            try:
                code_verifier = pkce_manager.get_code_verifier(state)
                logger.info("🔐 Retrieved PKCE code verifier for callback")
            except KeyError:
                logger.info(f"ℹ️ No PKCE session for state (non-PKCE flow)")
            except Exception as e:
                logger.warning(f"⚠️ PKCE retrieval error (continuing): {e}")

            user_email, credentials = await handle_oauth_callback(
                authorization_response=str(request.url),
                state=state,
                code_verifier=code_verifier,
            )
            logger.info(f"✅ OAuth callback processed for user: {user_email}")

            if not validate_user_access(user_email):
                logger.warning(f"🚫 Access denied for user: {user_email}")
                return HTMLResponse(
                    content=f"""<!DOCTYPE html><html><head><title>Access Denied</title>
                    <style>body{{font-family:sans-serif;text-align:center;padding:60px}}
                    h1{{color:#dc3545}}</style></head><body>
                    <h1>Access Denied</h1><p>User <b>{html.escape(user_email)}</b> is not authorized.</p>
                    </body></html>""",
                    status_code=403,
                )

            # Register as secondary account in dual auth bridge
            try:
                from auth.dual_auth_bridge import get_dual_auth_bridge

                dual_bridge = get_dual_auth_bridge()
                dual_bridge.add_secondary_account(user_email)
                logger.info(f"✅ Registered {user_email} as secondary account")
            except Exception as e:
                logger.warning(
                    f"⚠️ Dual auth bridge registration error (continuing): {e}"
                )

            # Store in session
            try:
                session_id = await get_session_context()
                if session_id:
                    store_session_data(session_id, SessionKey.USER_EMAIL, user_email)
            except Exception as e:
                logger.warning(f"⚠️ Session storage error (continuing): {e}")

            # Retrieve per-user API key if one was generated during credential save
            user_api_key = getattr(credentials, "_user_api_key", None)
            user_api_key_exists = getattr(credentials, "_user_api_key_exists", False)
            api_key_section = ""

            # Gather envelope info for security visualization
            security_viz_section = ""
            _num_recipients = 0
            _has_hmac = False
            _is_encrypted = False
            try:
                from pathlib import Path

                from auth.google_auth import _normalize_email

                safe_email = (
                    _normalize_email(user_email).replace("@", "_at_").replace(".", "_")
                )
                enc_path = (
                    Path(settings.credentials_dir) / f"{safe_email}_credentials.enc"
                )
                if enc_path.exists():
                    _is_encrypted = True
                    import json as _json

                    try:
                        _env = _json.load(open(enc_path))
                        _num_recipients = len(_env.get("recipients", {}))
                        _has_hmac = "hmac" in _env
                    except (ValueError, KeyError):
                        # Legacy format (raw Fernet bytes) — still encrypted
                        _num_recipients = 1
                        _has_hmac = False
            except Exception:
                pass

            # Build linked-accounts section (shown for both new and existing keys)
            accessible_section = ""
            if user_api_key or user_api_key_exists:
                try:
                    from auth.user_api_keys import get_accessible_emails

                    accessible = get_accessible_emails(user_email)
                    linked = sorted(
                        e for e in accessible if e != user_email.lower().strip()
                    )
                    if linked:
                        linked_items = "".join(
                            f"<li>{html.escape(e)}</li>" for e in linked
                        )
                        accessible_section = f"""
                        <div class="linked-accounts">
                            <b>🔗 Linked Accounts</b>
                            <small>This key can also access credentials for:</small>
                            <ul>{linked_items}</ul>
                        </div>"""
                    else:
                        accessible_section = """
                        <div class="linked-accounts solo">
                            <b>🔒 Single Account</b>
                            <small>This key only has access to the email above.<br>
                            Authenticate additional emails in the same session to link them.</small>
                        </div>"""
                except Exception:
                    pass

            if user_api_key:
                api_key_section = f"""
                <div class="api-key">
                    <b>🔑 Your Personal API Key</b><br>
                    <small>Use this as a Bearer token to connect without re-authenticating.<br>
                    This key is shown <b>once</b> — save it now!</small>
                    <div class="key-value hidden" id="apiKey">{html.escape(user_api_key)}</div>
                    <button id="revealBtn" onclick="document.getElementById('apiKey').classList.remove('hidden');this.style.display='none';document.getElementById('copyBtn').style.display=''">
                        Click to Reveal Key
                    </button>
                    <button id="copyBtn" style="display:none" onclick="navigator.clipboard.writeText(document.getElementById('apiKey').textContent).then(()=>this.textContent='Copied!')">
                        Copy to Clipboard
                    </button>
                </div>
                {accessible_section}"""
            elif user_api_key_exists:
                api_key_section = f"""
                <div class="api-key" style="background:#d1ecf1;color:#0c5460;border-color:#bee5eb">
                    <b>🔑 API Key Active</b><br>
                    <small>Your existing per-user API key is still valid.<br>
                    Credentials have been refreshed — no need to update your key.</small>
                </div>
                {accessible_section}"""

            # Build security visualization
            if _is_encrypted:
                # Build recipient nodes with linkage method badges
                _cur = user_email.lower().strip()
                _all_emails = [_cur]
                try:
                    _all_emails = sorted(get_accessible_emails(_cur))
                except Exception:
                    pass

                try:
                    from auth.user_api_keys import get_link_method
                except Exception:

                    def get_link_method(a, b):
                        return ""

                _recipient_nodes = ""
                for em in _all_emails:
                    _is_current = em == _cur
                    _highlight = "current" if _is_current else ""
                    _method_badge = ""
                    if not _is_current:
                        _m = get_link_method(_cur, em)
                        if _m == "oauth":
                            _method_badge = (
                                '<span class="sec-method oauth">via OAuth</span>'
                            )
                        elif _m == "api_key":
                            _method_badge = (
                                '<span class="sec-method api_key">via API key</span>'
                            )
                        elif _m == "session":
                            _method_badge = (
                                '<span class="sec-method session">via session</span>'
                            )
                        elif _m == "both":
                            _method_badge = (
                                '<span class="sec-method both">multiple methods</span>'
                            )
                        else:
                            _method_badge = '<span class="sec-method">linked</span>'
                    _recipient_nodes += f'<div class="sec-node sec-user {_highlight}"><span class="sec-icon">👤</span><span class="sec-label">{html.escape(em)}</span>{_method_badge}</div>'

                _key_lines = ""
                for em in _all_emails:
                    _cls = "current" if (em == _cur) else ""
                    _key_lines += f'<div class="sec-flow-row {_cls}"><div class="sec-key-badge">🔑 Key</div><svg class="sec-arrow" viewBox="0 0 40 12"><path d="M0 6h32l-5-4M32 6l-5 4" stroke="currentColor" stroke-width="1.5" fill="none"/></svg><div class="sec-cek-wrap">Wrapped CEK</div></div>'

                _subtitle = (
                    "Your Google Workspace credentials are protected by multi-recipient envelope encryption"
                    if _num_recipients > 1
                    else "Your Google Workspace credentials are protected by split-key encryption"
                )

                security_viz_section = f"""
                <div class="sec-panel">
                    <div class="sec-title">🛡️ Credential Security Model</div>
                    <div class="sec-subtitle">{_subtitle}</div>
                    <div class="sec-diagram">
                        <div class="sec-col sec-col-users">
                            <div class="sec-col-label">Authorized Users</div>
                            {_recipient_nodes}
                        </div>
                        <div class="sec-col sec-col-keys">
                            <div class="sec-col-label">Key Wrapping</div>
                            {_key_lines}
                        </div>
                        <div class="sec-col sec-col-envelope">
                            <div class="sec-col-label">Encrypted Envelope</div>
                            <div class="sec-envelope">
                                <div class="sec-env-header">Sealed Envelope</div>
                                <div class="sec-env-row"><span class="sec-env-badge rec">🔐 {_num_recipients} Wrapped CEK(s)</span></div>
                                <div class="sec-env-row"><span class="sec-env-badge data">🔒 Gmail · Drive · Calendar · Docs · Sheets</span></div>
                                <div class="sec-env-row"><span class="sec-env-badge hmac">{"✅" if _has_hmac else "⚠️"} HMAC Integrity Seal</span></div>
                            </div>
                        </div>
                    </div>
                    <div class="sec-features">
                        <div class="sec-feat"><span>🔀</span> Split-Key: requires <b>your key + server secret</b></div>
                        <div class="sec-feat"><span>🚫</span> Server alone <b>cannot</b> decrypt your credentials</div>
                        <div class="sec-feat"><span>🔗</span> Link accounts via <b>OAuth</b>, <b>session</b>, or <b>API key</b> (30 min window)</div>
                        <div class="sec-feat"><span>🛡️</span> HMAC detects tampering or unauthorized changes</div>
                    </div>
                </div>"""

            success_html = f"""<!DOCTYPE html><html><head><title>Authentication Successful</title>
            <style>
                body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
                      margin:0;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);
                      min-height:100vh;display:flex;align-items:center;justify-content:center}}
                .container{{max-width:560px;background:white;border-radius:20px;padding:50px;
                           text-align:center;box-shadow:0 20px 40px rgba(0,0,0,0.1)}}
                .success-icon{{font-size:72px;margin-bottom:20px}}
                h1{{color:#28a745;margin-bottom:10px;font-size:32px}}
                .email{{color:#6c757d;font-size:18px;margin:20px 0}}
                .saved{{background:#d4edda;color:#155724;padding:15px;border-radius:8px;margin:20px 0;border:1px solid #c3e6cb}}
                .api-key{{background:#fff3cd;color:#856404;padding:15px;border-radius:8px;margin:20px 0;border:1px solid #ffc107;text-align:left}}
                .api-key small{{display:block;margin-bottom:10px}}
                .key-value{{font-family:monospace;font-size:13px;background:#f8f9fa;padding:10px;border-radius:4px;
                           word-break:break-all;margin:10px 0;user-select:all;border:1px solid #dee2e6}}
                .key-value.hidden{{filter:blur(8px);user-select:none;pointer-events:none}}
                .api-key button{{background:#856404;color:white;border:none;padding:8px 16px;border-radius:4px;cursor:pointer;font-size:13px}}
                .api-key button:hover{{background:#6c5200}}
                .linked-accounts{{background:#e8f4fd;color:#0c5460;padding:15px;border-radius:8px;margin:20px 0;border:1px solid #bee5eb;text-align:left}}
                .linked-accounts small{{display:block;margin-bottom:8px}}
                .linked-accounts ul{{margin:8px 0 0 0;padding-left:20px}}
                .linked-accounts li{{margin:4px 0;font-family:monospace;font-size:14px}}
                .linked-accounts.solo{{background:#f8f9fa;color:#6c757d;border-color:#dee2e6}}
                .services{{background:#f8f9fa;padding:20px;border-radius:10px;margin:20px 0}}
                /* Security visualization */
                .sec-panel{{background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);color:#e0e0e0;
                           padding:24px;border-radius:12px;margin:24px 0;text-align:left}}
                .sec-title{{font-size:16px;font-weight:700;color:#fff;margin-bottom:4px}}
                .sec-subtitle{{font-size:11px;color:#8892b0;margin-bottom:16px}}
                .sec-diagram{{display:flex;gap:8px;align-items:stretch;margin-bottom:16px}}
                .sec-col{{flex:1;display:flex;flex-direction:column;gap:6px}}
                .sec-col-label{{font-size:9px;text-transform:uppercase;letter-spacing:1px;color:#64ffda;
                               font-weight:600;margin-bottom:4px;text-align:center}}
                .sec-node{{background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);
                          border-radius:8px;padding:8px 6px;text-align:center;display:flex;
                          flex-direction:column;align-items:center;gap:2px}}
                .sec-node.current{{border-color:#64ffda;background:rgba(100,255,218,0.08)}}
                .sec-icon{{font-size:18px}}
                .sec-label{{font-size:9px;font-family:monospace;word-break:break-all;line-height:1.2;color:#ccd6f6}}
                .sec-method{{font-size:7px;padding:1px 5px;border-radius:3px;margin-top:2px;
                            background:rgba(255,255,255,0.08);color:#8892b0}}
                .sec-method.oauth{{background:rgba(100,255,218,0.12);color:#64ffda}}
                .sec-method.session{{background:rgba(255,183,77,0.12);color:#ffb74d}}
                .sec-method.both{{background:rgba(129,212,250,0.12);color:#81d4fa}}
                .sec-method.api_key{{background:rgba(206,147,255,0.12);color:#ce93ff}}
                .sec-col-keys{{flex:0.7;justify-content:center;gap:8px}}
                .sec-flow-row{{display:flex;align-items:center;gap:3px;justify-content:center}}
                .sec-flow-row.current .sec-key-badge{{background:#64ffda;color:#1a1a2e}}
                .sec-key-badge{{background:rgba(255,255,255,0.12);color:#ccd6f6;font-size:8px;font-weight:600;
                              padding:3px 6px;border-radius:4px;white-space:nowrap}}
                .sec-arrow{{width:28px;height:12px;color:#64ffda;flex-shrink:0}}
                .sec-cek-wrap{{font-size:8px;color:#8892b0;white-space:nowrap}}
                .sec-col-envelope{{flex:1.1}}
                .sec-envelope{{background:rgba(255,255,255,0.04);border:1.5px solid #64ffda;
                              border-radius:10px;padding:10px;display:flex;flex-direction:column;gap:5px}}
                .sec-env-header{{font-size:10px;font-weight:700;color:#64ffda;text-align:center;
                                letter-spacing:1px;text-transform:uppercase}}
                .sec-env-row{{text-align:center}}
                .sec-env-badge{{display:inline-block;font-size:9px;padding:3px 8px;border-radius:4px;
                              font-weight:500}}
                .sec-env-badge.rec{{background:rgba(255,183,77,0.15);color:#ffb74d}}
                .sec-env-badge.data{{background:rgba(100,255,218,0.1);color:#64ffda}}
                .sec-env-badge.hmac{{background:rgba(129,212,250,0.1);color:#81d4fa}}
                .sec-features{{display:grid;grid-template-columns:1fr 1fr;gap:6px}}
                .sec-feat{{font-size:10px;color:#8892b0;display:flex;align-items:start;gap:5px;line-height:1.3}}
                .sec-feat span:first-child{{flex-shrink:0}}
                .sec-feat b{{color:#ccd6f6}}
            </style></head><body><div class="container">
                <div class="success-icon">✅</div>
                <h1>Authentication Successful!</h1>
                <div class="email">Authenticated: <b>{html.escape(user_email)}</b></div>
                <div class="saved"><b>🔐 Credentials Saved!</b><br>Ready to use.</div>
                {api_key_section}
                {security_viz_section}
                <div class="services"><h3>🚀 Services Available</h3>
                    <div>Drive · Gmail · Calendar · Docs · Sheets · Slides · Photos · Chat · Forms</div>
                </div>
                <p>You can close this window and return to your application.</p>
            </div></body></html>"""

            return HTMLResponse(content=success_html, status_code=200)

        except Exception as e:
            logger.error(f"❌ Legacy oauth2callback error: {e}", exc_info=True)
            return HTMLResponse(
                content=f"""<!DOCTYPE html><html><head><title>OAuth Error</title>
                <style>body{{font-family:sans-serif;text-align:center;padding:60px}}
                .error{{color:#dc3545;font-size:48px}}</style></head><body>
                <div class="error">❌</div><h1>OAuth Error</h1>
                <p>{html.escape(str(e))}</p><p>Please try again.</p></body></html>""",
                status_code=500,
            )

    logger.info("  ✅ Legacy /oauth2callback route registered (GoogleProvider mode)")


def setup_oauth_endpoints_fastmcp(mcp) -> None:
    """Setup OAuth discovery and DCR endpoints using FastMCP custom routes.

    Args:
        mcp: FastMCP application instance
    """

    @mcp.custom_route(
        "/.well-known/openid-configuration/mcp", methods=["GET", "OPTIONS"]
    )
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
                },
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
            "token_endpoint_auth_methods_supported": [
                "client_secret_post",
                "client_secret_basic",
            ],
            "code_challenge_methods_supported": ["S256"],
            "scopes_supported": _get_oauth_endpoint_scopes(),
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            # MCP-specific configuration
            "registration_endpoint": f"{base_url}/oauth/register",
            "resource_server": mcp_resource_url,  # Should be the full MCP endpoint URL
            "authorization_servers": ["https://accounts.google.com"],
            "bearer_methods_supported": ["header"],
            "resource_documentation": f"{base_url}/docs",
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
            },
        )

    @mcp.custom_route(
        "/.well-known/oauth-protected-resource/mcp", methods=["GET", "OPTIONS"]
    )
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
                },
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
            "scopes_supported": _get_oauth_endpoint_scopes(),
        }

        logger.info("📋 OAuth protected resource metadata served")

        # Return proper JSONResponse with CORS headers
        return JSONResponse(
            content=metadata,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
            },
        )

    @mcp.custom_route(
        "/.well-known/oauth-authorization-server", methods=["GET", "OPTIONS"]
    )
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
                },
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
            "token_endpoint_auth_methods_supported": [
                "client_secret_post",
                "client_secret_basic",
            ],
            "code_challenge_methods_supported": ["S256"],
            "scopes_supported": _get_oauth_endpoint_scopes(),
            # Point to our local Dynamic Client Registration endpoint
            "registration_endpoint": f"{base_url}/oauth/register",
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "userinfo_endpoint": "https://www.googleapis.com/oauth2/v1/userinfo",
        }

        logger.info("📋 OAuth authorization server metadata served")

        # Return proper JSONResponse with CORS headers
        return JSONResponse(
            content=metadata,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
            },
        )

    @mcp.custom_route("/oauth/authorize", methods=["GET", "OPTIONS"])
    async def oauth_authorize(request: Any):
        """OAuth Authorization Endpoint Proxy.

        This endpoint intercepts authorization requests from MCP clients,
        maps temporary client_ids to real Google OAuth client_ids,
        and redirects to Google's authorization server.
        """
        from urllib.parse import urlencode

        from starlette.responses import JSONResponse, RedirectResponse, Response

        # Handle CORS preflight
        if request.method == "OPTIONS":
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                },
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
                        "error_description": "Missing client_id parameter",
                    },
                    status_code=400,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                    },
                )

            logger.info(f"📋 Authorization request for client_id: {client_id}")

            # Check if this is a temporary client_id (starts with mcp_)
            if client_id.startswith("mcp_"):
                logger.info(f"🔍 Detected temporary client_id: {client_id}")

                # DIAGNOSTIC: Log proxy instance ID before lookup
                logger.info(f"🔍 DEBUG: Using oauth_proxy instance: {id(oauth_proxy)}")
                logger.info(
                    f"🔍 DEBUG: Active proxy clients: {len(oauth_proxy._proxy_clients)}"
                )
                if oauth_proxy._proxy_clients:
                    logger.info(
                        f"🔍 DEBUG: Registered client IDs: {list(oauth_proxy._proxy_clients.keys())}"
                    )

                # Get the proxy client to retrieve real credentials
                proxy_client = oauth_proxy.get_proxy_client(client_id)

                if not proxy_client:
                    logger.warning(f"⚠️ Proxy client not registered: {client_id}")
                    logger.info(
                        "🔧 AUTO-REGISTERING proxy client for Quick OAuth Flow compatibility"
                    )

                    # MCP Inspector's Quick OAuth Flow may skip /oauth/register
                    # Auto-register this client on-the-fly using default credentials
                    try:
                        from config.settings import settings

                        # Get default OAuth credentials
                        if not settings.is_oauth_configured():
                            raise ValueError(
                                "OAuth not configured - cannot auto-register client"
                            )

                        oauth_config = settings.get_oauth_client_config()
                        real_client_id = oauth_config.get("client_id")
                        real_client_secret = oauth_config.get("client_secret")

                        if not real_client_id or not real_client_secret:
                            raise ValueError("OAuth configuration incomplete")

                        # Auto-register with minimal metadata
                        auto_metadata = {
                            "client_name": "MCP Inspector (Auto-Registered)",
                            "redirect_uris": [
                                query_params.get(
                                    "redirect_uri",
                                    "http://localhost:6274/oauth/callback/debug",
                                )
                            ],
                            "grant_types": ["authorization_code", "refresh_token"],
                            "response_types": ["code"],
                            "token_endpoint_auth_method": "client_secret_post",  # Will be updated if PKCE
                            "scope": query_params.get("scope", ""),
                        }

                        # Register the proxy client with the EXACT client_id from the request
                        # This requires modifying oauth_proxy to accept custom temp_client_id
                        import secrets
                        from datetime import datetime, timezone

                        from auth.oauth_proxy import ProxyClient

                        proxy_client = ProxyClient(
                            temp_client_id=client_id,  # Use the exact client_id from request
                            temp_client_secret=secrets.token_urlsafe(32),
                            real_client_id=real_client_id,
                            real_client_secret=real_client_secret,
                            client_metadata=auto_metadata,
                            created_at=datetime.now(timezone.utc),
                        )

                        # Store directly in oauth_proxy
                        oauth_proxy._proxy_clients[client_id] = proxy_client

                        logger.info(f"✅ Auto-registered proxy client: {client_id}")
                        logger.info(
                            f"   Proxy clients count now: {len(oauth_proxy._proxy_clients)}"
                        )

                    except Exception as reg_error:
                        logger.error(f"❌ Auto-registration failed: {reg_error}")
                        return JSONResponse(
                            content={
                                "error": "invalid_client",
                                "error_description": f"Client not registered and auto-registration failed: {str(reg_error)}",
                            },
                            status_code=400,
                            headers={
                                "Access-Control-Allow-Origin": "*",
                            },
                        )

                # Store PKCE parameters if present (for later use in token exchange)
                code_challenge = query_params.get("code_challenge")
                code_challenge_method = query_params.get("code_challenge_method")

                if code_challenge and code_challenge_method:
                    proxy_client.store_pkce_params(
                        code_challenge, code_challenge_method
                    )
                    logger.info(
                        f"🔐 Stored PKCE parameters: challenge={code_challenge[:10]}..., method={code_challenge_method}"
                    )

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

                    default_scopes = ScopeRegistry.resolve_scope_group(
                        "oauth_comprehensive"
                    )
                    google_auth_params["scope"] = " ".join(default_scopes)
                    logger.info(
                        f"🔧 Added missing scope parameter using ScopeRegistry oauth_comprehensive: {len(default_scopes)} scopes"
                    )
                except Exception as e:
                    # Fallback to _get_oauth_endpoint_scopes if ScopeRegistry fails
                    logger.warning(
                        f"Failed to get scopes from ScopeRegistry, using fallback: {e}"
                    )
                    fallback_scopes = _get_oauth_endpoint_scopes()
                    google_auth_params["scope"] = " ".join(fallback_scopes)
                    logger.info(
                        f"🔧 Added missing scope parameter using fallback: {len(fallback_scopes)} scopes"
                    )
            else:
                # Validate existing scope parameter isn't just whitespace
                scope_parts = current_scope.split()
                if not scope_parts:
                    try:
                        from .scope_registry import ScopeRegistry

                        default_scopes = ScopeRegistry.resolve_scope_group(
                            "oauth_comprehensive"
                        )
                        google_auth_params["scope"] = " ".join(default_scopes)
                        logger.info(
                            f"🔧 Replaced empty scope parameter using ScopeRegistry: {len(default_scopes)} scopes"
                        )
                    except Exception:
                        fallback_scopes = _get_oauth_endpoint_scopes()
                        google_auth_params["scope"] = " ".join(fallback_scopes)
                        logger.info(
                            f"🔧 Replaced empty scope parameter using fallback: {len(fallback_scopes)} scopes"
                        )
                else:
                    logger.info(
                        f"✅ Using provided scope parameter with {len(scope_parts)} scopes"
                    )

            # Log the authorization parameters (without sensitive data)
            logger.info("🔗 Redirecting to Google OAuth with parameters:")
            logger.info(f"   client_id: {real_client_id[:20]}...")
            logger.info(
                f"   redirect_uri: {google_auth_params.get('redirect_uri', 'not specified')}"
            )
            logger.info(
                f"   scope: {google_auth_params.get('scope', 'not specified')[:100]}..."
            )
            logger.info(
                f"   state: {google_auth_params.get('state', 'not specified')[:20] if google_auth_params.get('state') else 'not specified'}..."
            )
            logger.info(
                f"   response_type: {google_auth_params.get('response_type', 'not specified')}"
            )

            # Construct Google OAuth authorization URL
            google_auth_url = (
                "https://accounts.google.com/o/oauth2/v2/auth?"
                + urlencode(google_auth_params)
            )

            logger.info("✅ Redirecting to Google OAuth authorization")

            # Redirect to Google's authorization server
            return RedirectResponse(url=google_auth_url, status_code=302)

        except Exception as e:
            logger.error(f"❌ Authorization proxy failed: {e}", exc_info=True)
            return JSONResponse(
                content={
                    "error": "server_error",
                    "error_description": f"Authorization proxy error: {str(e)}",
                },
                status_code=500,
                headers={
                    "Access-Control-Allow-Origin": "*",
                },
            )

    @mcp.custom_route("/oauth/register", methods=["POST", "OPTIONS"])
    async def dynamic_client_registration(request: Any):
        """Dynamic Client Registration endpoint (RFC 7591).

        Implements OAuth 2.0 Dynamic Client Registration for MCP Inspector.
        """
        from starlette.responses import JSONResponse, Response

        from auth.dynamic_client_registration import handle_client_registration

        # Handle CORS preflight
        if request.method == "OPTIONS":
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                },
            )

        logger.info("📝 Dynamic client registration requested")

        try:
            # Parse request body
            body = await request.body()
            if isinstance(body, bytes):
                body = body.decode("utf-8")

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
                },
            )

        except Exception as e:
            logger.error(f"❌ Client registration failed: {e}")
            error_response = {
                "error": "registration_failed",
                "error_description": str(e),
            }
            return JSONResponse(
                content=error_response,
                status_code=400,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                },
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
        import urllib.parse

        from starlette.responses import JSONResponse, Response

        # Handle CORS preflight
        if request.method == "OPTIONS":
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                },
            )

        logger.info("🔄 Token exchange requested")

        try:
            # Parse request body (can be JSON or form-encoded)
            content_type = request.headers.get("content-type", "")

            if "application/json" in content_type:
                body = await request.body()
                if isinstance(body, bytes):
                    body = body.decode("utf-8")
                import json

                params = json.loads(body) if body else {}
            else:
                # Form-encoded (standard OAuth)
                body = await request.body()
                if isinstance(body, bytes):
                    body = body.decode("utf-8")
                params = dict(urllib.parse.parse_qsl(body))

            # CRITICAL FIX: Extract client credentials from Authorization header (HTTP Basic Auth)
            # Per RFC 6749, clients can send credentials via Authorization header OR request body
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Basic "):
                try:
                    import base64

                    # Decode Basic auth: "Basic base64(client_id:client_secret)"
                    encoded_credentials = auth_header[6:]  # Remove "Basic " prefix
                    decoded = base64.b64decode(encoded_credentials).decode("utf-8")

                    # Split on first colon (client_secret may contain colons)
                    if ":" in decoded:
                        header_client_id, header_client_secret = decoded.split(":", 1)

                        # Use header credentials if not already in body
                        if not params.get("client_id"):
                            params["client_id"] = header_client_id
                            logger.info(
                                f"✅ Extracted client_id from Authorization header: {header_client_id[:20]}..."
                            )

                        if not params.get("client_secret"):
                            params["client_secret"] = header_client_secret
                            logger.info(
                                "✅ Extracted client_secret from Authorization header"
                            )
                    else:
                        logger.warning(
                            "⚠️ Invalid Basic auth format in Authorization header (no colon)"
                        )
                except Exception as e:
                    logger.warning(f"⚠️ Failed to parse Authorization header: {e}")

            grant_type = params.get("grant_type")

            if grant_type == "authorization_code":
                # Handle authorization code exchange
                auth_code = params.get("code")
                client_id = params.get("client_id")
                client_secret = params.get("client_secret")
                redirect_uri = params.get("redirect_uri")
                code_verifier = params.get("code_verifier")  # PKCE parameter

                # DIAGNOSTIC LOGGING for client_secret validation issue
                logger.info("🔍 DIAGNOSTIC - Token exchange parameters:")
                logger.info(f"   client_id: {client_id}")
                logger.info(
                    f"   client_secret provided: {'YES' if client_secret else 'NO'}"
                )
                logger.info(
                    f"   client_secret value: {'<present>' if client_secret else '<MISSING/EMPTY>'}"
                )
                logger.info(
                    f"   client_secret length: {len(client_secret) if client_secret else 0}"
                )
                logger.info(
                    f"   code_verifier provided: {'YES' if code_verifier else 'NO'}"
                )
                logger.info(
                    f"   code_verifier value: {code_verifier[:10] + '...' if code_verifier else '<MISSING>'}"
                )

                if not all([auth_code, client_id, redirect_uri]):
                    raise ValueError(
                        "Missing required parameters for authorization_code grant"
                    )

                # Use OAuth Proxy to handle the exchange
                token_data = handle_token_exchange(
                    auth_code=auth_code,
                    client_id=client_id,
                    client_secret=client_secret
                    or "",  # Some flows might not have client_secret
                    redirect_uri=redirect_uri,
                    code_verifier=code_verifier,  # Pass PKCE parameter
                )

                logger.info(
                    f"✅ Token exchange successful for client: {client_id[:20]}..."
                )

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
                        "X-Content-Type-Options": "nosniff",
                    },
                )

                # ASYNC POST-PROCESSING: Store OAuth authentication data in background
                # This prevents the client from hanging while we get user info
                if client_id.startswith("mcp_"):
                    # Use async task to handle user data storage without blocking response
                    import asyncio

                    asyncio.create_task(
                        _store_oauth_user_data_async(client_id, token_data)
                    )

                return response

            elif grant_type == "refresh_token":
                # Handle refresh token
                refresh_token = params.get("refresh_token")
                client_id = params.get("client_id")
                client_secret = params.get("client_secret")

                if not all([refresh_token, client_id]):
                    raise ValueError(
                        "Missing required parameters for refresh_token grant"
                    )

                token_data = refresh_access_token(
                    refresh_token=refresh_token,
                    client_id=client_id,
                    client_secret=client_secret or "",
                )

                logger.info(
                    f"✅ Token refresh successful for client: {client_id[:20]}..."
                )

                return JSONResponse(
                    content=token_data,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "POST, OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type, Authorization",
                        "Cache-Control": "no-store",
                        "Pragma": "no-cache",
                    },
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
                            "5. If using custom client_id, verify it's correct and active",
                        ],
                    },
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
                            "4. Ensure system clock is accurate",
                        ],
                    },
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
                            "4. Check server logs for more details",
                        ],
                    },
                }
                status_code = 500

            return JSONResponse(
                content=error_response,
                status_code=status_code,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                },
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
                },
            )

        # FULL OAuth processing now that route is confirmed working
        logger.info("🔄 Processing full OAuth callback with credential exchange")

        try:
            # Extract parameters from query string
            query_params = dict(request.query_params)
            state = query_params.get("state")
            code = query_params.get("code")
            error = query_params.get("error")

            logger.info("🔍 Query parameters extracted:")
            logger.info(f"   state: {state[:20] if state else 'MISSING'}...")
            logger.info(f"   code: {'PRESENT' if code else 'MISSING'}")
            logger.info(f"   error: {error or 'None'}")

            # SUCCESS: Process OAuth callback and save credentials
            logger.info("✅ OAuth callback received - processing authorization code")

            try:
                # Import OAuth handling and access control
                from auth.access_control import validate_user_access
                from auth.context import get_session_context, store_session_data
                from auth.google_auth import handle_oauth_callback
                from auth.pkce_utils import pkce_manager

                # Retrieve PKCE code verifier if available
                code_verifier = None
                try:
                    code_verifier = pkce_manager.get_code_verifier(state)
                    logger.info("🔐 Retrieved PKCE code verifier for callback")
                except KeyError:
                    logger.info(
                        f"ℹ️ No PKCE session found for state: {state} (non-PKCE flow)"
                    )
                except Exception as e:
                    logger.warning(f"⚠️ PKCE retrieval error (continuing): {e}")

                # Handle OAuth callback with full credential processing
                user_email, credentials = await handle_oauth_callback(
                    authorization_response=str(request.url),
                    state=state,
                    code_verifier=code_verifier,
                )

                logger.info(
                    f"✅ OAuth callback processed successfully for user: {user_email}"
                )

                # SECURITY: Validate user access before saving credentials
                if not validate_user_access(user_email):
                    logger.warning(f"🚫 Access denied for user: {user_email}")

                    # Return access denied page
                    denied_html = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>Access Denied</title>
                        <style>
                            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; background: #fff5f5; min-height: 100vh; display: flex; align-items: center; justify-content: center; }}
                            .container {{ max-width: 600px; background: white; border-radius: 20px; padding: 50px; text-align: center; box-shadow: 0 20px 40px rgba(0,0,0,0.1); }}
                            .error-icon {{ font-size: 72px; margin-bottom: 20px; }}
                            h1 {{ color: #dc3545; margin-bottom: 10px; font-size: 32px; }}
                            .email {{ color: #6c757d; font-size: 18px; margin: 20px 0; }}
                            .message {{ color: #495057; font-size: 16px; line-height: 1.5; margin: 20px 0; }}
                            .info {{ background: #fff3cd; color: #856404; padding: 15px; border-radius: 8px; margin: 20px 0; border: 1px solid #ffeaa7; }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <div class="error-icon">🚫</div>
                            <h1>Access Denied</h1>
                            <div class="email">User: <strong>{html.escape(user_email)}</strong></div>
                            <div class="message">
                                You are not authorized to access this MCP server.
                            </div>
                            <div class="info">
                                <strong>ℹ️ Access Restricted</strong><br>
                                This server requires pre-authorization. Please contact the server administrator
                                to request access for your email address.
                            </div>
                        </div>
                    </body>
                    </html>
                    """

                    return HTMLResponse(
                        content=denied_html,
                        status_code=403,
                        headers={
                            "Content-Type": "text/html; charset=utf-8",
                            "X-Access-Denied": "true",
                        },
                    )

                logger.info(
                    f"✅ Access granted - credentials saved for user: {user_email}"
                )

                # Store user email in session context
                try:
                    session_id = await get_session_context()
                    if session_id:
                        store_session_data(
                            session_id, SessionKey.USER_EMAIL, user_email
                        )
                        logger.info(
                            f"✅ Stored user email {user_email} in session {session_id}"
                        )
                except Exception as e:
                    logger.warning(f"⚠️ Session storage error (continuing): {e}")

                # Retrieve per-user API key if one was generated
                user_api_key = getattr(credentials, "_user_api_key", None)
                user_api_key_exists = getattr(
                    credentials, "_user_api_key_exists", False
                )
                api_key_section = ""

                # Build linked-accounts section (shown for both new and existing keys)
                accessible_section = ""
                if user_api_key or user_api_key_exists:
                    try:
                        from auth.user_api_keys import get_accessible_emails

                        accessible = get_accessible_emails(user_email)
                        linked = sorted(
                            e for e in accessible if e != user_email.lower().strip()
                        )
                        if linked:
                            linked_items = "".join(
                                f"<li>{html.escape(e)}</li>" for e in linked
                            )
                            accessible_section = f"""
                            <div class="linked-accounts">
                                <b>🔗 Linked Accounts</b>
                                <small>This key can also access credentials for:</small>
                                <ul>{linked_items}</ul>
                            </div>"""
                        else:
                            accessible_section = """
                            <div class="linked-accounts solo">
                                <b>🔒 Single Account</b>
                                <small>This key only has access to the email above.<br>
                                Authenticate additional emails in the same session to link them.</small>
                            </div>"""
                    except Exception:
                        pass

                if user_api_key:
                    api_key_section = f"""
                    <div class="api-key">
                        <b>🔑 Your Personal API Key</b><br>
                        <small>Use this as a Bearer token to connect without re-authenticating.<br>
                        This key is shown <b>once</b> — save it now!</small>
                        <div class="key-value hidden" id="apiKey">{html.escape(user_api_key)}</div>
                        <button id="revealBtn" onclick="document.getElementById('apiKey').classList.remove('hidden');this.style.display='none';document.getElementById('copyBtn').style.display=''">
                            Click to Reveal Key
                        </button>
                        <button id="copyBtn" style="display:none" onclick="navigator.clipboard.writeText(document.getElementById('apiKey').textContent).then(()=>this.textContent='Copied!')">
                            Copy to Clipboard
                        </button>
                    </div>
                    {accessible_section}"""
                elif user_api_key_exists:
                    api_key_section = f"""
                    <div class="api-key" style="background:#d1ecf1;color:#0c5460;border-color:#bee5eb">
                        <b>🔑 API Key Active</b><br>
                        <small>Your existing per-user API key is still valid.<br>
                        Credentials have been refreshed — no need to update your key.</small>
                    </div>
                    {accessible_section}"""

                # Build privacy mode toggle section
                privacy_section = ""
                _privacy_session_id = ""
                try:
                    _privacy_session_id = session_id or ""
                except Exception:
                    pass
                if _privacy_session_id:
                    privacy_section = f"""
                    <div class="privacy-toggle">
                        <div class="privacy-header">
                            <b>🛡️ Privacy Mode</b>
                            <label class="toggle-switch">
                                <input type="checkbox" id="privacyToggle"
                                       onchange="togglePrivacy(this.checked)">
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                        <small class="privacy-desc">
                            When enabled, tool responses have personal information
                            (emails, names, phone numbers) replaced with
                            <code>[PRIVATE:token]</code> placeholders before the AI sees them.
                            Your data stays encrypted on the server and can be revealed
                            when needed. Disabled by default.
                        </small>
                        <div id="privacyStatus" class="privacy-status"></div>
                    </div>
                    <script>
                    function togglePrivacy(enabled) {{
                        var mode = enabled ? 'auto' : 'disabled';
                        var statusEl = document.getElementById('privacyStatus');
                        statusEl.textContent = 'Updating...';
                        statusEl.className = 'privacy-status';
                        fetch('/api/privacy-mode', {{
                            method: 'POST',
                            headers: {{'Content-Type': 'application/json'}},
                            body: JSON.stringify({{
                                session_id: '{_privacy_session_id}',
                                mode: mode
                            }})
                        }})
                        .then(function(r) {{ return r.json(); }})
                        .then(function(data) {{
                            if (data.success) {{
                                statusEl.textContent = enabled
                                    ? 'Privacy mode active — PII will be masked in tool responses'
                                    : 'Privacy mode off — tool responses show full data';
                                statusEl.className = 'privacy-status ' + (enabled ? 'active' : 'off');
                            }} else {{
                                statusEl.textContent = 'Error: ' + (data.error || 'unknown');
                                statusEl.className = 'privacy-status error';
                                document.getElementById('privacyToggle').checked = !enabled;
                            }}
                        }})
                        .catch(function(err) {{
                            statusEl.textContent = 'Network error';
                            statusEl.className = 'privacy-status error';
                            document.getElementById('privacyToggle').checked = !enabled;
                        }});
                    }}
                    </script>"""

                # Gather envelope info for security visualization
                security_viz_section = ""
                _num_recipients = 0
                _has_hmac = False
                _is_encrypted = False
                try:
                    from pathlib import Path

                    from auth.google_auth import _normalize_email

                    safe_email = (
                        _normalize_email(user_email)
                        .replace("@", "_at_")
                        .replace(".", "_")
                    )
                    enc_path = (
                        Path(settings.credentials_dir) / f"{safe_email}_credentials.enc"
                    )
                    if enc_path.exists():
                        _is_encrypted = True
                        import json as _json

                        try:
                            _env = _json.load(open(enc_path))
                            _num_recipients = len(_env.get("recipients", {}))
                            _has_hmac = "hmac" in _env
                        except (ValueError, KeyError):
                            # Legacy format (raw Fernet bytes) — still encrypted
                            _num_recipients = 1
                            _has_hmac = False
                except Exception:
                    pass

                # Build security visualization
                if _is_encrypted:
                    _cur = user_email.lower().strip()
                    _all_emails = [_cur]
                    try:
                        _all_emails = sorted(get_accessible_emails(_cur))
                    except Exception:
                        pass

                    try:
                        from auth.user_api_keys import get_link_method
                    except Exception:

                        def get_link_method(a, b):
                            return ""

                    _recipient_nodes = ""
                    for em in _all_emails:
                        _is_current = em == _cur
                        _highlight = "current" if _is_current else ""
                        _method_badge = ""
                        if not _is_current:
                            _m = get_link_method(_cur, em)
                            if _m == "oauth":
                                _method_badge = (
                                    '<span class="sec-method oauth">via OAuth</span>'
                                )
                            elif _m == "session":
                                _method_badge = '<span class="sec-method session">via session</span>'
                            elif _m == "both":
                                _method_badge = '<span class="sec-method both">OAuth + session</span>'
                            else:
                                _method_badge = '<span class="sec-method">linked</span>'
                        _recipient_nodes += f'<div class="sec-node sec-user {_highlight}"><span class="sec-icon">👤</span><span class="sec-label">{html.escape(em)}</span>{_method_badge}</div>'

                    _key_lines = ""
                    for em in _all_emails:
                        _cls = "current" if (em == _cur) else ""
                        _key_lines += f'<div class="sec-flow-row {_cls}"><div class="sec-key-badge">🔑 Key</div><svg class="sec-arrow" viewBox="0 0 40 12"><path d="M0 6h32l-5-4M32 6l-5 4" stroke="currentColor" stroke-width="1.5" fill="none"/></svg><div class="sec-cek-wrap">Wrapped CEK</div></div>'

                    _subtitle = (
                        "Your Google Workspace credentials are protected by multi-recipient envelope encryption"
                        if _num_recipients > 1
                        else "Your Google Workspace credentials are protected by split-key encryption"
                    )

                    security_viz_section = f"""
                    <div class="sec-panel">
                        <div class="sec-title">🛡️ Credential Security Model</div>
                        <div class="sec-subtitle">{_subtitle}</div>
                        <div class="sec-diagram">
                            <div class="sec-col sec-col-users">
                                <div class="sec-col-label">Authorized Users</div>
                                {_recipient_nodes}
                            </div>
                            <div class="sec-col sec-col-keys">
                                <div class="sec-col-label">Key Wrapping</div>
                                {_key_lines}
                            </div>
                            <div class="sec-col sec-col-envelope">
                                <div class="sec-col-label">Encrypted Envelope</div>
                                <div class="sec-envelope">
                                    <div class="sec-env-header">Sealed Envelope</div>
                                    <div class="sec-env-row"><span class="sec-env-badge rec">🔐 {_num_recipients} Wrapped CEK(s)</span></div>
                                    <div class="sec-env-row"><span class="sec-env-badge data">🔒 Gmail · Drive · Calendar · Docs · Sheets</span></div>
                                    <div class="sec-env-row"><span class="sec-env-badge hmac">{"✅" if _has_hmac else "⚠️"} HMAC Integrity Seal</span></div>
                                </div>
                            </div>
                        </div>
                        <div class="sec-features">
                            <div class="sec-feat"><span>🔀</span> Split-Key: requires <b>your key + server secret</b></div>
                            <div class="sec-feat"><span>🚫</span> Server alone <b>cannot</b> decrypt your credentials</div>
                            <div class="sec-feat"><span>🔗</span> Linked accounts share access via separate key wraps</div>
                            <div class="sec-feat"><span>🛡️</span> HMAC detects tampering or unauthorized changes</div>
                        </div>
                    </div>"""

                # Create beautiful success page
                success_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Authentication Successful</title>
                    <style>
                        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; }}
                        .container {{ max-width: 560px; background: white; border-radius: 20px; padding: 50px; text-align: center; box-shadow: 0 20px 40px rgba(0,0,0,0.1); }}
                        .success-icon {{ font-size: 72px; margin-bottom: 20px; }}
                        h1 {{ color: #28a745; margin-bottom: 10px; font-size: 32px; }}
                        .email {{ color: #6c757d; font-size: 18px; margin: 20px 0; }}
                        .message {{ color: #495057; font-size: 16px; line-height: 1.5; margin: 20px 0; }}
                        .services {{ background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0; }}
                        .services h3 {{ color: #495057; margin-top: 0; }}
                        .service-list {{ color: #6c757d; font-size: 14px; }}
                        .credentials-saved {{ background: #d4edda; color: #155724; padding: 15px; border-radius: 8px; margin: 20px 0; border: 1px solid #c3e6cb; }}
                        .api-key {{ background: #fff3cd; color: #856404; padding: 15px; border-radius: 8px; margin: 20px 0; border: 1px solid #ffc107; text-align: left; }}
                        .api-key small {{ display: block; margin-bottom: 10px; }}
                        .key-value {{ font-family: monospace; font-size: 13px; background: #f8f9fa; padding: 10px; border-radius: 4px; word-break: break-all; margin: 10px 0; user-select: all; border: 1px solid #dee2e6; }}
                        .key-value.hidden {{ filter: blur(8px); user-select: none; pointer-events: none; }}
                        .api-key button {{ background: #856404; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; }}
                        .api-key button:hover {{ background: #6c5200; }}
                        .linked-accounts {{ background: #e8f4fd; color: #0c5460; padding: 15px; border-radius: 8px; margin: 20px 0; border: 1px solid #bee5eb; text-align: left; }}
                        .linked-accounts small {{ display: block; margin-bottom: 8px; }}
                        .linked-accounts ul {{ margin: 8px 0 0 0; padding-left: 20px; }}
                        .linked-accounts li {{ margin: 4px 0; font-family: monospace; font-size: 14px; }}
                        .linked-accounts.solo {{ background: #f8f9fa; color: #6c757d; border-color: #dee2e6; }}
                        /* Privacy mode toggle */
                        .privacy-toggle {{ background: #f0f4ff; border: 1px solid #c5cae9; padding: 15px; border-radius: 8px; margin: 20px 0; text-align: left; }}
                        .privacy-header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }}
                        .privacy-desc {{ display: block; color: #495057; line-height: 1.5; }}
                        .privacy-desc code {{ background: #e8eaf6; padding: 1px 5px; border-radius: 3px; font-size: 12px; }}
                        .privacy-status {{ font-size: 12px; margin-top: 8px; min-height: 16px; }}
                        .privacy-status.active {{ color: #2e7d32; }}
                        .privacy-status.off {{ color: #6c757d; }}
                        .privacy-status.error {{ color: #c62828; }}
                        .toggle-switch {{ position: relative; display: inline-block; width: 48px; height: 26px; flex-shrink: 0; }}
                        .toggle-switch input {{ opacity: 0; width: 0; height: 0; }}
                        .toggle-slider {{ position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background: #ccc; border-radius: 26px; transition: 0.3s; }}
                        .toggle-slider:before {{ content: ""; position: absolute; height: 20px; width: 20px; left: 3px; bottom: 3px; background: white; border-radius: 50%; transition: 0.3s; }}
                        .toggle-switch input:checked + .toggle-slider {{ background: #5c6bc0; }}
                        .toggle-switch input:checked + .toggle-slider:before {{ transform: translateX(22px); }}
                        /* Security visualization */
                        .sec-panel {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: #e0e0e0; padding: 24px; border-radius: 12px; margin: 24px 0; text-align: left; }}
                        .sec-title {{ font-size: 16px; font-weight: 700; color: #fff; margin-bottom: 4px; }}
                        .sec-subtitle {{ font-size: 11px; color: #8892b0; margin-bottom: 16px; }}
                        .sec-diagram {{ display: flex; gap: 8px; align-items: stretch; margin-bottom: 16px; }}
                        .sec-col {{ flex: 1; display: flex; flex-direction: column; gap: 6px; }}
                        .sec-col-label {{ font-size: 9px; text-transform: uppercase; letter-spacing: 1px; color: #64ffda; font-weight: 600; margin-bottom: 4px; text-align: center; }}
                        .sec-node {{ background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 8px 6px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 2px; }}
                        .sec-node.current {{ border-color: #64ffda; background: rgba(100,255,218,0.08); }}
                        .sec-icon {{ font-size: 18px; }}
                        .sec-label {{ font-size: 9px; font-family: monospace; word-break: break-all; line-height: 1.2; color: #ccd6f6; }}
                        .sec-method {{ font-size: 7px; padding: 1px 5px; border-radius: 3px; margin-top: 2px; background: rgba(255,255,255,0.08); color: #8892b0; }}
                        .sec-method.oauth {{ background: rgba(100,255,218,0.12); color: #64ffda; }}
                        .sec-method.session {{ background: rgba(255,183,77,0.12); color: #ffb74d; }}
                        .sec-method.both {{ background: rgba(129,212,250,0.12); color: #81d4fa; }}
                        .sec-method.api_key {{ background: rgba(206,147,255,0.12); color: #ce93ff; }}
                        .sec-col-keys {{ flex: 0.7; justify-content: center; gap: 8px; }}
                        .sec-flow-row {{ display: flex; align-items: center; gap: 3px; justify-content: center; }}
                        .sec-flow-row.current .sec-key-badge {{ background: #64ffda; color: #1a1a2e; }}
                        .sec-key-badge {{ background: rgba(255,255,255,0.12); color: #ccd6f6; font-size: 8px; font-weight: 600; padding: 3px 6px; border-radius: 4px; white-space: nowrap; }}
                        .sec-arrow {{ width: 28px; height: 12px; color: #64ffda; flex-shrink: 0; }}
                        .sec-cek-wrap {{ font-size: 8px; color: #8892b0; white-space: nowrap; }}
                        .sec-col-envelope {{ flex: 1.1; }}
                        .sec-envelope {{ background: rgba(255,255,255,0.04); border: 1.5px solid #64ffda; border-radius: 10px; padding: 10px; display: flex; flex-direction: column; gap: 5px; }}
                        .sec-env-header {{ font-size: 10px; font-weight: 700; color: #64ffda; text-align: center; letter-spacing: 1px; text-transform: uppercase; }}
                        .sec-env-row {{ text-align: center; }}
                        .sec-env-badge {{ display: inline-block; font-size: 9px; padding: 3px 8px; border-radius: 4px; font-weight: 500; }}
                        .sec-env-badge.rec {{ background: rgba(255,183,77,0.15); color: #ffb74d; }}
                        .sec-env-badge.data {{ background: rgba(100,255,218,0.1); color: #64ffda; }}
                        .sec-env-badge.hmac {{ background: rgba(129,212,250,0.1); color: #81d4fa; }}
                        .sec-features {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }}
                        .sec-feat {{ font-size: 10px; color: #8892b0; display: flex; align-items: start; gap: 5px; line-height: 1.3; }}
                        .sec-feat span:first-child {{ flex-shrink: 0; }}
                        .sec-feat b {{ color: #ccd6f6; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="success-icon">✅</div>
                        <h1>Authentication Successful!</h1>
                        <div class="email">Authenticated: <strong>{html.escape(user_email)}</strong></div>
                        <div class="credentials-saved">
                            <strong>🔐 Credentials Saved!</strong><br>
                            Ready to use.
                        </div>
                        {api_key_section}
                        {privacy_section}
                        {security_viz_section}
                        <div class="services">
                            <h3>🚀 Services Available</h3>
                            <div class="service-list">
                                Drive · Gmail · Calendar · Docs · Sheets · Slides · Photos · Chat · Forms
                            </div>
                        </div>
                        <p>You can close this window and return to your application.</p>
                    </div>
                </body>
                </html>
                """

                logger.info(
                    f"✅ Returning success page for {user_email} with credential confirmation"
                )
                return HTMLResponse(
                    content=success_html,
                    status_code=200,
                    headers={
                        "Content-Type": "text/html; charset=utf-8",
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                        "X-OAuth-Success": "true",
                        "X-Credentials-Saved": "true",
                    },
                )

            except Exception as oauth_error:
                logger.error(
                    f"❌ OAuth processing failed: {oauth_error}", exc_info=True
                )

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
                        "Pragma": "no-cache",
                    },
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
                    "X-Error-Response": "oauth-callback-basic-error",
                },
            )

    @mcp.custom_route("/oauth/callback/debug", methods=["GET", "OPTIONS"])
    async def oauth_callback_debug(request: Any):
        """OAuth callback endpoint for debugging and MCP Inspector.

        This endpoint handles the OAuth callback from Google's authorization server.
        It extracts the authorization code and either displays it for debugging
        or exchanges it for tokens automatically.
        """
        from starlette.responses import HTMLResponse, Response

        # Handle CORS preflight
        if request.method == "OPTIONS":
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                },
            )

        logger.info("🔄 OAuth callback received")

        try:
            # Get query parameters from callback
            query_params = dict(request.query_params)
            auth_code = query_params.get("code")
            state = query_params.get("state")
            error = query_params.get("error")

            logger.info(
                f"📋 Callback parameters: code={'present' if auth_code else 'missing'}, state={'present' if state else 'missing'}, error={error or 'none'}"
            )

            if error:
                logger.error(f"❌ OAuth error in callback: {error}")
                error_description = query_params.get(
                    "error_description", "No description provided"
                )
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
                    status_code=400,
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
                    status_code=400,
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
                            {"<p><strong>State:</strong> " + state + "</p>" if state else ""}
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
                status_code=500,
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
                },
            )

        logger.info("🔍 OAuth status check requested")

        try:
            # Check for stored OAuth authentication data
            import json
            from datetime import datetime
            from pathlib import Path

            oauth_data_path = (
                Path(settings.credentials_dir) / ".oauth_authentication.json"
            )

            if not oauth_data_path.exists():
                return JSONResponse(
                    content={
                        "authenticated": False,
                        "message": "No authentication data found",
                        "timestamp": datetime.now().isoformat(),
                    },
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                        "Expires": "0",
                    },
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
                        "timestamp": datetime.now().isoformat(),
                    },
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                        "Expires": "0",
                    },
                )
            else:
                return JSONResponse(
                    content={
                        "authenticated": False,
                        "message": "Authentication incomplete or invalid",
                        "timestamp": datetime.now().isoformat(),
                    },
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                        "Expires": "0",
                    },
                )

        except Exception as e:
            logger.error(f"❌ OAuth status check failed: {e}")
            return JSONResponse(
                content={
                    "authenticated": False,
                    "error": str(e),
                    "message": "Error checking authentication status",
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                status_code=500,
                headers={
                    "Access-Control-Allow-Origin": "*",
                },
            )

    # ── Per-session privacy mode toggle (called from OAuth success page) ──
    @mcp.custom_route("/api/privacy-mode", methods=["POST", "OPTIONS"])
    async def privacy_mode_api(request: Any):
        """Set per-session privacy mode from the OAuth success page."""
        from starlette.responses import JSONResponse, Response

        if request.method == "OPTIONS":
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type",
                },
            )

        try:
            body = await request.json()
            target_session = body.get("session_id")
            mode = body.get("mode")

            if mode not in ("disabled", "auto", "strict"):
                return JSONResponse(
                    {"success": False, "error": f"Invalid mode: {mode}"},
                    status_code=400,
                )

            if not target_session:
                return JSONResponse(
                    {"success": False, "error": "Missing session_id"},
                    status_code=400,
                )

            from auth.context import get_session_data, store_session_data
            from auth.types import AuthProvenance, SessionKey

            # Reject shared API key sessions (no identity binding)
            provenance = get_session_data(
                target_session, SessionKey.AUTH_PROVENANCE, default=None
            )
            if provenance == AuthProvenance.API_KEY:
                return JSONResponse(
                    {
                        "success": False,
                        "error": "Privacy mode requires authenticated session (not shared API key)",
                    },
                    status_code=403,
                )

            previous = get_session_data(
                target_session, SessionKey.PRIVACY_MODE, default=None
            )
            store_session_data(target_session, SessionKey.PRIVACY_MODE, mode)

            logger.info(
                "Privacy mode set via API: session=%s, %s -> %s",
                target_session[:8] + "...",
                previous or "default",
                mode,
            )

            return JSONResponse(
                {
                    "success": True,
                    "previous_mode": previous or "disabled",
                    "current_mode": mode,
                }
            )
        except Exception as e:
            logger.exception("Privacy mode API error")
            return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    # For simplicity, let's focus on the core endpoints that MCP Inspector needs
    # The client configuration endpoints can be added later if needed

    logger.info("✅ OAuth HTTP endpoints registered via FastMCP custom routes")
    logger.info("🔍 Available OAuth endpoints:")
    logger.info(
        "  GET /.well-known/openid-configuration/mcp (MCP Inspector Quick OAuth)"
    )
    logger.info("  GET /.well-known/oauth-protected-resource")
    logger.info("  GET /.well-known/oauth-authorization-server")
    logger.info("  GET /oauth/authorize (OAuth Proxy authorization endpoint)")
    logger.info("  POST /oauth/register")
    logger.info(
        "  POST /oauth/token (OAuth Proxy token exchange - FIXED freezing issue)"
    )
    logger.info(
        "  GET /oauth2callback (MAIN OAuth callback handler - FIXED routing issue)"
    )
    logger.info("  GET /oauth/callback/debug (OAuth callback handler - debugging)")
    logger.info("  GET /oauth/status (Authentication status polling for CLI clients)")
    logger.info("  GET /oauth/register/{client_id}")
    logger.info("  PUT /oauth/register/{client_id}")
    logger.info("  DELETE /oauth/register/{client_id}")

    # Register service selection routes (shared with GoogleProvider path)
    setup_service_selection_routes(mcp)
