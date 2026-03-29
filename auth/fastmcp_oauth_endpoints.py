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
from config.settings import settings

# Initialize logger early

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

from config.enhanced_logging import redact_email, setup_logger

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
        )
        # This is background processing, so we don't want to crash anything

def _generate_service_selection_html(
    state: str, flow_type: str, use_pkce: bool = True
) -> str:
    """Generate the service selection page HTML with authentication method choice."""
    from auth.ui import generate_service_selection_html

    # Retrieve the requested email from the OAuth state map for THIS specific flow
    requested_email = ""
    try:
        from auth.google_auth import _oauth_state_map

        state_info = _oauth_state_map.get(state)
        if state_info:
            requested_email = state_info.get("user_email", "")
            if requested_email == "unknown@gmail.com":
                requested_email = ""
    except Exception:
        pass

    return generate_service_selection_html(
        state, flow_type, use_pkce, requested_email=requested_email
    )

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
                from auth.ui import generate_error_html

                return HTMLResponse(
                    content=generate_error_html(
                        "Error", "Invalid service selection request"
                    ),
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
            from auth.ui import generate_error_html

            return HTMLResponse(
                content=generate_error_html("Service Selection Error", str(e)),
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

            # Privacy mode and sampling config (submitted as form fields)
            privacy_mode = form_data.get("privacy_mode") == "on"
            sampling_model = (form_data.get("sampling_model") or "").strip()
            sampling_api_key = (form_data.get("sampling_api_key") or "").strip()
            sampling_api_base = (form_data.get("sampling_api_base") or "").strip()

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

                # Stash privacy mode and sampling config — applied after OAuth
                _service_selection_cache[state]["privacy_mode"] = privacy_mode
                if sampling_model or sampling_api_key:
                    _service_selection_cache[state]["sampling_config"] = {
                        "model": sampling_model,
                        "api_key": sampling_api_key,
                        "api_base": sampling_api_base,
                    }

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
            from auth.ui import generate_error_html

            return HTMLResponse(
                content=generate_error_html("Service Selection Error", str(e)),
                status_code=400,
            )

    logger.info("  GET /auth/services/select (Service selection page)")
    logger.info("  POST /auth/services/selected (Service selection form handler)")

async def _build_oauth_success_html(
    user_email: str, credentials: Any, session_id: str | None
) -> str:
    """Shared post-OAuth logic for both legacy and main callbacks.

    Applies intro-screen settings (privacy, sampling), handles per-user key
    force-regeneration, builds the API-key and security-viz sections, and
    returns the full success-page HTML.
    """
    from auth.context import get_auth_middleware, store_session_data
    from auth.types import SessionKey

    # ── Apply privacy mode and sampling config from intro screen ──
    _intro_privacy = getattr(credentials, "_privacy_mode", False)
    _intro_sampling = getattr(credentials, "_sampling_config", None)
    try:
        if session_id and _intro_privacy:
            store_session_data(session_id, SessionKey.PRIVACY_MODE, "auto")
            logger.info(f"🛡️ Privacy mode enabled from intro screen for {redact_email(user_email)}")
        if session_id and _intro_sampling and _intro_sampling.get("model"):
            auth_mw_sampling = get_auth_middleware()
            if auth_mw_sampling:
                _cfg = {k: v for k, v in _intro_sampling.items() if v}
                auth_mw_sampling.save_sampling_config(
                    user_email,
                    _cfg,
                    per_user_key=getattr(credentials, "_user_api_key", None),
                    google_sub=getattr(credentials, "_google_sub", None),
                )
                store_session_data(session_id, SessionKey.SAMPLING_CONFIG, _cfg)
                logger.info(
                    f"🤖 Sampling config saved from intro screen for {user_email}: "
                    f"model={_cfg.get('model', 'default')}"
                )
    except Exception as e:
        logger.warning(f"⚠️ Could not apply intro screen settings: {e}")

    # ── Handle API key retrieval and force-regen ──
    user_api_key = getattr(credentials, "_user_api_key", None)
    user_api_key_exists = getattr(credentials, "_user_api_key_exists", False)

    if not user_api_key and user_api_key_exists:
        try:
            from auth.user_api_keys import regenerate_unrevealed_key

            new_key = regenerate_unrevealed_key(user_email)
            if new_key:
                user_api_key = new_key
                user_api_key_exists = False
                try:
                    auth_mw = get_auth_middleware()
                    if auth_mw:
                        auth_mw.save_credentials(
                            user_email,
                            credentials,
                            per_user_key=new_key,
                            google_sub=getattr(credentials, "_google_sub", None),
                        )
                        logger.info(
                            f"🔑 Force-regenerated per-user key for {user_email}"
                        )
                except Exception as re_save_err:
                    logger.warning(f"Could not re-save with new key: {re_save_err}")
        except Exception as regen_err:
            logger.warning(f"Could not regenerate per-user key: {regen_err}")

    # ── Get originally-requested email from this specific OAuth flow ──
    requested_email = getattr(credentials, "_requested_email", "") or ""
    # Skip display if the request was a fallback/unknown value
    if requested_email in ("unknown@gmail.com", ""):
        requested_email = ""

    # ── Build success page HTML ──
    from auth.ui import (
        build_api_key_section,
        build_envelope_inventory_section,
        build_revoke_section,
        build_security_viz_section,
        generate_success_html,
    )

    api_key_section = build_api_key_section(
        user_email, user_api_key, user_api_key_exists
    )
    security_viz_section = build_security_viz_section(user_email)
    envelope_inventory_section = build_envelope_inventory_section(user_email)
    revoke_section = build_revoke_section(user_email, settings.base_url)

    return generate_success_html(
        user_email=user_email,
        api_key_section=api_key_section,
        security_viz_section=security_viz_section,
        envelope_inventory_section=envelope_inventory_section,
        revoke_section=revoke_section,
        requested_email=requested_email or "",
    )

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
            logger.info(f"✅ OAuth callback processed for user: {redact_email(user_email)}")

            if not validate_user_access(user_email):
                logger.warning(f"🚫 Access denied for user: {redact_email(user_email)}")
                from auth.ui import generate_access_denied_html

                return HTMLResponse(
                    content=generate_access_denied_html(user_email),
                    status_code=403,
                )

            # Register as secondary account in dual auth bridge
            try:
                from auth.dual_auth_bridge import get_dual_auth_bridge

                dual_bridge = get_dual_auth_bridge()
                dual_bridge.add_secondary_account(user_email)
                logger.info(f"✅ Registered {redact_email(user_email)} as secondary account")
            except Exception as e:
                logger.warning(
                    f"⚠️ Dual auth bridge registration error (continuing): {e}"
                )

            # Store in session (get_session_context returns None in HTTP context,
            # so also scan all sessions to fix any with a stale/wrong email)
            session_id = None
            try:
                session_id = await get_session_context()
                if session_id:
                    store_session_data(session_id, SessionKey.USER_EMAIL, user_email)
            except Exception as e:
                logger.warning(f"⚠️ Session storage error (continuing): {e}")

            # Fix 2: Update ALL sessions that have a wrong/missing email from this OAuth flow
            # TODO(security): This iterates ALL sessions — safe in single-user/dev mode,
            # but must be scoped to the originating session before multi-tenant deployment
            # to prevent Session A being rebound to Session B's email on concurrent auth.
            try:
                from auth.context import get_session_data, list_sessions

                _verified = user_email.lower().strip()
                for sid in list_sessions():
                    sid_email = get_session_data(sid, SessionKey.USER_EMAIL)
                    requested = get_session_data(sid, SessionKey.REQUESTED_EMAIL)
                    owned = set(get_session_data(sid, SessionKey.API_KEY_OWNED_ACCOUNTS) or [])
                    authed = set(get_session_data(sid, SessionKey.SESSION_AUTHED_EMAILS) or [])

                    # Determine the stale email to replace (from USER_EMAIL or REQUESTED_EMAIL)
                    old_email = (sid_email or requested or "").lower().strip()

                    # Skip if session already has the correct email
                    if sid_email and sid_email.lower().strip() == _verified:
                        # Still ensure owned accounts include the verified email
                        if _verified not in owned and owned:
                            owned.add(_verified)
                            store_session_data(sid, SessionKey.API_KEY_OWNED_ACCOUNTS, list(owned))
                        continue

                    # Update if: session had a wrong email, or had a requested email pending OAuth
                    if old_email and old_email != _verified:
                        store_session_data(sid, SessionKey.USER_EMAIL, user_email)
                        owned.discard(old_email)
                        owned.add(_verified)
                        store_session_data(sid, SessionKey.API_KEY_OWNED_ACCOUNTS, list(owned))
                        authed.discard(old_email)
                        authed.add(_verified)
                        store_session_data(sid, SessionKey.SESSION_AUTHED_EMAILS, sorted(authed))
                        logger.info(f"Updated session {sid} email from {redact_email(old_email)} to {redact_email(user_email)}")
                    elif not sid_email and owned:
                        # Session has no USER_EMAIL but has owned accounts — set the verified email
                        store_session_data(sid, SessionKey.USER_EMAIL, user_email)
                        owned.add(_verified)
                        store_session_data(sid, SessionKey.API_KEY_OWNED_ACCOUNTS, list(owned))
                        authed.add(_verified)
                        store_session_data(sid, SessionKey.SESSION_AUTHED_EMAILS, sorted(authed))
                        logger.info(f"Set session {sid} email to {redact_email(user_email)} (was empty)")
            except Exception as e:
                logger.warning(f"Could not update sessions after OAuth: {e}")

            success_html = await _build_oauth_success_html(
                user_email, credentials, session_id
            )
            return HTMLResponse(content=success_html, status_code=200)

        except Exception as e:
            logger.error(f"❌ Legacy oauth2callback error: {e}")
            from auth.ui import generate_error_html

            return HTMLResponse(
                content=generate_error_html("OAuth Error", str(e)),
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
            logger.error(f"❌ Authorization proxy failed: {e}")
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
                    f"✅ OAuth callback processed successfully for user: {redact_email(user_email)}"
                )

                # SECURITY: Validate user access before saving credentials
                if not validate_user_access(user_email):
                    logger.warning(f"🚫 Access denied for user: {redact_email(user_email)}")

                    # Return access denied page
                    from auth.ui import generate_access_denied_html

                    return HTMLResponse(
                        content=generate_access_denied_html(user_email),
                        status_code=403,
                        headers={
                            "Content-Type": "text/html; charset=utf-8",
                            "X-Access-Denied": "true",
                        },
                    )

                logger.info(
                    f"✅ Access granted - credentials saved for user: {redact_email(user_email)}"
                )

                # Store user email in session context (get_session_context returns
                # None in HTTP context, so also scan all sessions)
                session_id = None
                try:
                    session_id = await get_session_context()
                    if session_id:
                        store_session_data(
                            session_id, SessionKey.USER_EMAIL, user_email
                        )
                        logger.info(
                            f"✅ Stored user email {redact_email(user_email)} in session {session_id}"
                        )
                except Exception as e:
                    logger.warning(f"⚠️ Session storage error (continuing): {e}")

                # Fix 2: Update ALL sessions that have a wrong/missing email from this OAuth flow
                # TODO(security): Same cross-session concern as legacy callback above.
                try:
                    from auth.context import get_session_data, list_sessions

                    _verified = user_email.lower().strip()
                    for sid in list_sessions():
                        sid_email = get_session_data(sid, SessionKey.USER_EMAIL)
                        requested = get_session_data(sid, SessionKey.REQUESTED_EMAIL)
                        owned = set(get_session_data(sid, SessionKey.API_KEY_OWNED_ACCOUNTS) or [])
                        authed = set(get_session_data(sid, SessionKey.SESSION_AUTHED_EMAILS) or [])

                        # Determine the stale email to replace
                        old_email = (sid_email or requested or "").lower().strip()

                        # Skip if session already has the correct email
                        if sid_email and sid_email.lower().strip() == _verified:
                            if _verified not in owned and owned:
                                owned.add(_verified)
                                store_session_data(sid, SessionKey.API_KEY_OWNED_ACCOUNTS, list(owned))
                            continue

                        # Update if session had a wrong email or a requested email pending OAuth
                        if old_email and old_email != _verified:
                            store_session_data(sid, SessionKey.USER_EMAIL, user_email)
                            owned.discard(old_email)
                            owned.add(_verified)
                            store_session_data(sid, SessionKey.API_KEY_OWNED_ACCOUNTS, list(owned))
                            authed.discard(old_email)
                            authed.add(_verified)
                            store_session_data(sid, SessionKey.SESSION_AUTHED_EMAILS, sorted(authed))
                            logger.info(f"Updated session {sid} email from {redact_email(old_email)} to {redact_email(user_email)}")
                        elif not sid_email and owned:
                            store_session_data(sid, SessionKey.USER_EMAIL, user_email)
                            owned.add(_verified)
                            store_session_data(sid, SessionKey.API_KEY_OWNED_ACCOUNTS, list(owned))
                            authed.add(_verified)
                            store_session_data(sid, SessionKey.SESSION_AUTHED_EMAILS, sorted(authed))
                            logger.info(f"Set session {sid} email to {redact_email(user_email)} (was empty)")
                except Exception as e:
                    logger.warning(f"Could not update sessions after OAuth: {e}")

                success_html = await _build_oauth_success_html(
                    user_email, credentials, session_id
                )
                logger.info(
                    f"✅ Returning success page for {redact_email(user_email)} with credential confirmation"
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
                    f"❌ OAuth processing failed: {oauth_error}"
                )

                # Enhanced error messaging for OAuth issues
                error_str = str(oauth_error).lower()

                if "invalid_client" in error_str or "unauthorized" in error_str:
                    from auth.ui import generate_oauth_client_error_html

                    error_html = generate_oauth_client_error_html(str(oauth_error))
                else:
                    from auth.ui import generate_error_html

                    error_html = generate_error_html(
                        "OAuth Processing Error", str(oauth_error)
                    )

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
            logger.error(f"🚨 CRITICAL: Basic callback error: {e}")

            # Even if everything fails, return a basic HTML response
            from auth.ui import generate_error_html

            error_html = generate_error_html(
                "Callback Route Error",
                str(e) + "\nAt least we know the route is being hit!",
            )

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
                from auth.ui import generate_error_html

                return HTMLResponse(
                    content=generate_error_html(
                        "OAuth Error",
                        f"Error: {error}\nDescription: {error_description}",
                    ),
                    status_code=400,
                )

            if not auth_code:
                logger.error("❌ No authorization code in callback")
                from auth.ui import generate_error_html

                return HTMLResponse(
                    content=generate_error_html(
                        "Authorization Code Missing",
                        "No authorization code received from Google OAuth.",
                    ),
                    status_code=400,
                )

            # SUCCESS: We have an authorization code
            logger.info(f"✅ Authorization code received: {auth_code[:10]}...")

            # For debugging, show the authorization code to the user
            # In production, you might want to automatically exchange it for tokens
            from auth.ui import generate_debug_success_html

            return HTMLResponse(content=generate_debug_success_html(auth_code, state))

        except Exception as e:
            logger.error(f"❌ OAuth callback error: {e}")
            from auth.ui import generate_error_html

            return HTMLResponse(
                content=generate_error_html("Callback Processing Error", str(e)),
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

    # ── Per-session sampling configuration (called from OAuth success page) ──
    @mcp.custom_route("/api/sampling-config", methods=["POST", "OPTIONS"])
    async def sampling_config_api(request: Any):
        """Save or clear per-user sampling LLM configuration."""
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
            target_session = body.get("session_id") or ""
            fallback_email = (body.get("user_email") or "").strip()
            model = (body.get("model") or "").strip()
            api_key = (body.get("api_key") or "").strip()
            api_base = (body.get("api_base") or "").strip()
            action = body.get("action", "save")  # "save" or "clear"

            from auth.context import (
                get_auth_middleware,
                get_session_data,
                list_sessions,
                store_session_data,
            )
            from auth.types import AuthProvenance, SessionKey

            # If no session_id provided, find one by email
            if not target_session and fallback_email:
                for _sid in reversed(list_sessions()):
                    _sid_email = get_session_data(
                        _sid, SessionKey.USER_EMAIL, default=None
                    )
                    if (
                        _sid_email
                        and _sid_email.lower().strip() == fallback_email.lower()
                    ):
                        target_session = _sid
                        break

            if not target_session:
                return JSONResponse(
                    {
                        "success": False,
                        "error": "Missing session_id and could not find session for email",
                    },
                    status_code=400,
                )

            # Reject shared API key sessions (no identity binding)
            provenance = get_session_data(
                target_session, SessionKey.AUTH_PROVENANCE, default=None
            )
            if provenance == AuthProvenance.API_KEY:
                return JSONResponse(
                    {
                        "success": False,
                        "error": "Sampling config requires authenticated session (not shared API key)",
                    },
                    status_code=403,
                )

            user_email = (
                get_session_data(target_session, SessionKey.USER_EMAIL, default=None)
                or fallback_email
            )
            if not user_email:
                return JSONResponse(
                    {"success": False, "error": "No user email in session"},
                    status_code=400,
                )

            auth_middleware = get_auth_middleware()
            per_user_key = get_session_data(
                target_session, SessionKey.PER_USER_ENCRYPTION_KEY, default=None
            )
            google_sub = get_session_data(
                target_session, SessionKey.GOOGLE_SUB, default=None
            )

            if action == "clear" or not model:
                # Clear: remove from disk + session
                if auth_middleware:
                    auth_middleware.delete_sampling_config(user_email)
                store_session_data(target_session, SessionKey.SAMPLING_CONFIG, None)
                logger.info(
                    "Sampling config cleared via API: session=%s, user=%s",
                    target_session[:8] + "...",
                    user_email,
                )
                return JSONResponse({"success": True, "cleared": True})

            # Save config
            config_dict = {"model": model}
            if api_key:
                config_dict["api_key"] = api_key
            if api_base:
                config_dict["api_base"] = api_base

            if auth_middleware:
                auth_middleware.save_sampling_config(
                    user_email,
                    config_dict,
                    per_user_key=per_user_key,
                    google_sub=google_sub,
                )

            store_session_data(target_session, SessionKey.SAMPLING_CONFIG, config_dict)

            logger.info(
                "Sampling config saved via API: session=%s, model=%s",
                target_session[:8] + "...",
                model,
            )

            return JSONResponse(
                {
                    "success": True,
                    "model": model,
                    "has_api_key": bool(api_key),
                    "has_api_base": bool(api_base),
                }
            )
        except Exception as e:
            logger.exception("Sampling config API error")
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

    # Register status check routes (shared with GoogleProvider path)
    setup_status_check_routes(mcp)

    # Register config API routes (shared with GoogleProvider path)
    # In GoogleProvider mode these are registered separately via setup_config_api_routes()
    # Here they're already inline above, so no separate call needed.

def setup_config_api_routes(mcp) -> None:
    """Register /api/privacy-mode and /api/sampling-config routes.

    These are needed by the OAuth success page regardless of whether
    GoogleProvider or the legacy OAuth system is active.
    """

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

    @mcp.custom_route("/api/sampling-config", methods=["POST", "OPTIONS"])
    async def sampling_config_api(request: Any):
        """Save or clear per-user sampling LLM configuration."""
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
            target_session = body.get("session_id") or ""
            fallback_email = (body.get("user_email") or "").strip()
            model = (body.get("model") or "").strip()
            api_key = (body.get("api_key") or "").strip()
            api_base = (body.get("api_base") or "").strip()
            action = body.get("action", "save")

            from auth.context import (
                get_auth_middleware,
                get_session_data,
                list_sessions,
                store_session_data,
            )
            from auth.types import AuthProvenance, SessionKey

            if not target_session and fallback_email:
                for _sid in reversed(list_sessions()):
                    _sid_email = get_session_data(
                        _sid, SessionKey.USER_EMAIL, default=None
                    )
                    if (
                        _sid_email
                        and _sid_email.lower().strip() == fallback_email.lower()
                    ):
                        target_session = _sid
                        break

            if not target_session:
                return JSONResponse(
                    {
                        "success": False,
                        "error": "Missing session_id and could not find session for email",
                    },
                    status_code=400,
                )

            provenance = get_session_data(
                target_session, SessionKey.AUTH_PROVENANCE, default=None
            )
            if provenance == AuthProvenance.API_KEY:
                return JSONResponse(
                    {
                        "success": False,
                        "error": "Sampling config requires authenticated session (not shared API key)",
                    },
                    status_code=403,
                )

            user_email = (
                get_session_data(target_session, SessionKey.USER_EMAIL, default=None)
                or fallback_email
            )
            if not user_email:
                return JSONResponse(
                    {"success": False, "error": "No user email in session"},
                    status_code=400,
                )

            auth_middleware = get_auth_middleware()
            per_user_key = get_session_data(
                target_session, SessionKey.PER_USER_ENCRYPTION_KEY, default=None
            )
            google_sub = get_session_data(
                target_session, SessionKey.GOOGLE_SUB, default=None
            )

            if action == "clear" or not model:
                if auth_middleware:
                    auth_middleware.delete_sampling_config(user_email)
                store_session_data(target_session, SessionKey.SAMPLING_CONFIG, None)
                logger.info(
                    "Sampling config cleared via API: session=%s, user=%s",
                    target_session[:8] + "...",
                    user_email,
                )
                return JSONResponse({"success": True, "cleared": True})

            config_dict = {"model": model}
            if api_key:
                config_dict["api_key"] = api_key
            if api_base:
                config_dict["api_base"] = api_base

            # Validate: quick provider connectivity check if API key provided
            validation_ok = True
            validation_msg = ""
            if api_key:
                try:
                    import httpx

                    check_base = api_base or settings.litellm_api_base
                    if (
                        not check_base
                        and settings.venice_inference_key
                        and not settings.litellm_api_key
                    ):
                        check_base = "https://api.venice.ai/api/v1"
                    if check_base:
                        async with httpx.AsyncClient(
                            timeout=5.0, verify=False
                        ) as client:
                            resp = await client.get(
                                f"{check_base.rstrip('/')}/models",
                                headers={"Authorization": f"Bearer {api_key}"},
                            )
                            if resp.status_code == 401:
                                validation_ok = False
                                validation_msg = (
                                    "Invalid API key — authentication failed"
                                )
                            elif resp.status_code == 200:
                                validation_msg = "API key verified"
                            else:
                                validation_msg = f"Provider returned status {resp.status_code} (saved anyway)"
                except Exception as ve:
                    validation_msg = f"Could not reach provider (saved anyway): {ve}"
                    logger.debug("Sampling config validation warning: %s", ve)

            if not validation_ok:
                return JSONResponse(
                    {"success": False, "error": validation_msg},
                    status_code=400,
                )

            # Encrypt and save to disk
            num_recipients = 0
            if auth_middleware:
                auth_middleware.save_sampling_config(
                    user_email,
                    config_dict,
                    per_user_key=per_user_key,
                    google_sub=google_sub,
                )
                # Count recipients in the saved envelope
                try:
                    import json as _json
                    from pathlib import Path

                    from auth.google_auth import _normalize_email

                    safe_email = (
                        _normalize_email(user_email)
                        .replace("@", "_at_")
                        .replace(".", "_")
                    )
                    enc_path = (
                        Path(settings.credentials_dir)
                        / f"{safe_email}_sampling_config.enc"
                    )
                    if enc_path.exists():
                        _env = _json.loads(enc_path.read_text())
                        num_recipients = len(_env.get("recipients", {}))
                except Exception:
                    pass

            store_session_data(target_session, SessionKey.SAMPLING_CONFIG, config_dict)

            logger.info(
                "Sampling config saved via API: session=%s, model=%s, recipients=%d",
                target_session[:8] + "...",
                model,
                num_recipients,
            )

            return JSONResponse(
                {
                    "success": True,
                    "model": model,
                    "has_api_key": bool(api_key),
                    "has_api_base": bool(api_base),
                    "validated": validation_msg or None,
                    "encryption": {
                        "method": "split-key envelope (AES + HMAC-SHA256)",
                        "recipients": num_recipients,
                    }
                    if num_recipients
                    else None,
                }
            )
        except Exception as e:
            logger.exception("Sampling config API error")
            return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    @mcp.custom_route("/api/models", methods=["GET", "OPTIONS"])
    async def models_api(request: Any):
        """Return available LLM models for the sampling config dropdown."""
        from starlette.responses import JSONResponse, Response

        if request.method == "OPTIONS":
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type",
                },
            )

        models = []

        # Query Venice /models endpoint if key is configured
        try:
            api_key = settings.litellm_api_key or settings.venice_inference_key
            api_base = settings.litellm_api_base
            if (
                not api_base
                and settings.venice_inference_key
                and not settings.litellm_api_key
            ):
                api_base = "https://api.venice.ai/api/v1"

            if api_key and api_base:
                import httpx

                async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                    resp = await client.get(
                        f"{api_base.rstrip('/')}/models",
                        headers={"Authorization": f"Bearer {api_key}"},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        provider_prefix = (
                            "openai"  # LiteLLM provider prefix for OpenAI-compatible
                        )
                        for m in data.get("data", []):
                            model_id = m.get("id", "")
                            if model_id:
                                models.append(
                                    {
                                        "id": f"{provider_prefix}/{model_id}",
                                        "name": model_id,
                                        "owned_by": m.get("owned_by", ""),
                                    }
                                )
                        logger.debug(
                            "Models API: fetched %d models from %s",
                            len(models),
                            api_base,
                        )
        except Exception as e:
            logger.debug("Models API: provider query failed (non-fatal): %s", e)

        # Fallback: add common LiteLLM models if provider query returned nothing
        if not models:
            for m in [
                "openai/gpt-4o",
                "openai/gpt-4o-mini",
                "openai/gpt-4-turbo",
                "anthropic/claude-sonnet-4-20250514",
                "anthropic/claude-haiku-4-5-20251001",
                "groq/llama-3.1-70b-versatile",
                "groq/llama-3.1-8b-instant",
                "together_ai/meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
            ]:
                models.append(
                    {"id": m, "name": m.split("/", 1)[1], "owned_by": m.split("/")[0]}
                )

        return JSONResponse(
            {"data": models},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=300",
            },
        )

    @mcp.custom_route("/api/revoke", methods=["POST", "OPTIONS"])
    async def revoke_api(request: Any):
        """Revoke selected credentials and encrypted envelopes for a user."""
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
            user_email = (body.get("user_email") or "").strip()
            items = body.get("items", [])
            confirmation_email = (body.get("confirmation_email") or "").strip()

            if not user_email or not items:
                return JSONResponse(
                    {"success": False, "error": "Missing user_email or items"},
                    status_code=400,
                )

            if confirmation_email.lower() != user_email.lower():
                return JSONResponse(
                    {"success": False, "error": "Confirmation email does not match"},
                    status_code=400,
                )

            from auth.context import get_auth_middleware

            auth_mw = get_auth_middleware()
            revoked = []
            errors = []

            for item in items:
                try:
                    if item == "api_key":
                        from auth.user_api_keys import revoke_user_key

                        if revoke_user_key(user_email):
                            revoked.append("api_key")
                        else:
                            errors.append("api_key: not found")
                    elif item == "credentials" and auth_mw:
                        if auth_mw.delete_credential_file(user_email):
                            revoked.append("credentials")
                        else:
                            errors.append("credentials: not found")
                    elif item == "chat_sa" and auth_mw:
                        if auth_mw.delete_chat_service_account(user_email):
                            revoked.append("chat_sa")
                        else:
                            errors.append("chat_sa: not found")
                    elif item == "sampling_config" and auth_mw:
                        if auth_mw.delete_sampling_config(user_email):
                            revoked.append("sampling_config")
                        else:
                            errors.append("sampling_config: not found")
                    elif item == "backup" and auth_mw:
                        if auth_mw.delete_backup_file(user_email):
                            revoked.append("backup")
                        else:
                            errors.append("backup: not found")
                    elif item == "links":
                        from auth.user_api_keys import (
                            get_accessible_emails,
                            unlink_accounts,
                        )

                        accessible = get_accessible_emails(user_email)
                        linked = [
                            e for e in accessible if e != user_email.lower().strip()
                        ]
                        for linked_email in linked:
                            unlink_accounts(user_email, linked_email)
                        if linked:
                            revoked.append("links")
                        else:
                            errors.append("links: none found")
                    else:
                        errors.append(f"{item}: unknown or unavailable")
                except Exception as e:
                    errors.append(f"{item}: {e}")

            logger.info(
                "Revoke API: user=%s, revoked=%s, errors=%s",
                user_email,
                revoked,
                errors,
            )

            return JSONResponse(
                {"success": True, "revoked": revoked, "errors": errors},
                headers={"Access-Control-Allow-Origin": "*"},
            )
        except Exception as e:
            logger.exception("Revoke API error")
            return JSONResponse(
                {"success": False, "error": str(e)},
                status_code=500,
                headers={"Access-Control-Allow-Origin": "*"},
            )

    logger.info(
        "  ✅ Config API routes registered (/api/privacy-mode, /api/sampling-config, /api/models, /api/revoke)"
    )

def setup_status_check_routes(mcp) -> None:
    """Register /auth/status-check route for viewing credential status in browser."""

    @mcp.custom_route("/auth/status-check", methods=["GET", "OPTIONS"])
    async def status_check(request: Any):
        """Show credential status page with envelope inventory and revoke controls."""
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

        query_params = dict(request.query_params)
        email = (query_params.get("email") or "").strip()

        if not email:
            from auth.ui import generate_error_html

            return HTMLResponse(
                content=generate_error_html(
                    "Missing Email", "The 'email' query parameter is required."
                ),
                status_code=400,
            )

        # Verify credentials exist
        try:
            from auth.google_auth import get_valid_credentials

            creds = get_valid_credentials(email)
        except Exception:
            creds = None

        if not creds:
            from auth.ui import generate_error_html

            return HTMLResponse(
                content=generate_error_html(
                    "No Credentials Found",
                    f"No valid credentials found for {email}. "
                    "Please authenticate first using start_google_auth.",
                ),
                status_code=404,
            )

        from auth.ui import (
            build_api_key_section,
            build_envelope_inventory_section,
            build_revoke_section,
            build_security_viz_section,
            generate_success_html,
        )
        from auth.user_api_keys import was_key_revealed

        api_key_section = build_api_key_section(email, None, was_key_revealed(email))
        security_viz_section = build_security_viz_section(email)
        envelope_inventory_section = build_envelope_inventory_section(email)
        revoke_section = build_revoke_section(email, settings.base_url)

        page_html = generate_success_html(
            user_email=email,
            api_key_section=api_key_section,
            security_viz_section=security_viz_section,
            envelope_inventory_section=envelope_inventory_section,
            revoke_section=revoke_section,
            page_mode="status_check",
        )

        return HTMLResponse(content=page_html)

    logger.info("  ✅ Status check route registered (/auth/status-check)")


def setup_complete_oauth_endpoints(
    mcp,
    google_auth_provider,
    settings,
    use_google_oauth: bool,
    enable_jwt_auth: bool,
):
    """Register all OAuth endpoints — GoogleProvider supplemental or legacy.

    When GoogleProvider is active, registers only supplemental endpoints
    (status polling, service selection, legacy callback, config API, status check).
    When not active, registers full legacy OAuth discovery + operational endpoints
    and configures JWT-based authentication.
    """
    if google_auth_provider:
        # GoogleProvider is active — it already registered all discovery endpoints.
        logger.info(
            "🔍 GoogleProvider active — RFC-compliant OAuth endpoints auto-registered"
        )
        logger.info(
            f"  ✅ Protected Resource:  {settings.base_url}/.well-known/oauth-protected-resource"
        )
        logger.info(
            f"  ✅ Auth Server Metadata: {settings.base_url}/.well-known/oauth-authorization-server"
        )
        logger.info(f"  ✅ Authorization:        {settings.base_url}/authorize")
        logger.info(f"  ✅ Token Exchange:       {settings.base_url}/token")
        logger.info(f"  ✅ Callback:             {settings.base_url}/auth/callback")
        logger.info(f"  ✅ MCP Endpoint:         {settings.base_url}/mcp")

        try:
            @mcp.custom_route("/oauth/status", methods=["GET", "OPTIONS"])
            async def oauth_status_check_gp(request):
                """OAuth authentication status polling endpoint (supplemental)."""
                from starlette.responses import JSONResponse, Response

                if request.method == "OPTIONS":
                    return Response(
                        status_code=200, headers={"Access-Control-Allow-Origin": "*"}
                    )
                import json
                from pathlib import Path as _Path

                oauth_data_path = (
                    _Path(settings.credentials_dir) / ".oauth_authentication.json"
                )
                if oauth_data_path.exists():
                    try:
                        with open(oauth_data_path, "r") as f:
                            oauth_data = json.load(f)
                    except (json.JSONDecodeError, OSError):
                        oauth_data = {}
                    authenticated_email = oauth_data.get("authenticated_email")
                    if authenticated_email:
                        return JSONResponse(
                            content={
                                "authenticated": True,
                                "user_email": authenticated_email,
                            },
                            headers={
                                "Access-Control-Allow-Origin": "*",
                                "Cache-Control": "no-store",
                            },
                        )
                return JSONResponse(
                    content={
                        "authenticated": False,
                        "message": "No authentication data found",
                    },
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Cache-Control": "no-store",
                    },
                )

            logger.info("  ✅ Supplemental /oauth/status endpoint registered")

            setup_service_selection_routes(mcp)
            logger.info("  ✅ Service selection routes registered (/auth/services/select)")

            setup_legacy_callback_route(mcp)
            logger.info("  ✅ Legacy /oauth2callback registered for start_google_auth flow")

            setup_config_api_routes(mcp)
            logger.info("  ✅ Config API routes registered for OAuth success page")

            setup_status_check_routes(mcp)
            logger.info("  ✅ Status check route registered for credential status page")
        except Exception as e:
            logger.warning(f"⚠️ Could not register supplemental OAuth endpoints: {e}")

        # Do NOT set mcp._auth — GoogleProvider already handles Bearer token validation
        logger.info(
            "🔐 Authentication: Handled by GoogleProvider (no manual _auth override)"
        )

    else:
        # Legacy mode: register all custom OAuth discovery + operational endpoints
        logger.info("🔍 Setting up legacy OAuth discovery endpoints...")
        try:
            setup_oauth_endpoints_fastmcp(mcp)
            logger.info("✅ Legacy OAuth discovery endpoints configured")
            logger.info(
                f"  Discovery: {settings.base_url}/.well-known/oauth-protected-resource/mcp"
            )
            logger.info(
                f"  Authorization: {settings.base_url}/.well-known/oauth-authorization-server"
            )
            logger.info(f"  Registration: {settings.base_url}/oauth/register")
            logger.info(f"  Callback: {settings.base_url}/oauth2callback")
        except Exception as e:
            logger.error(
                f"❌ Failed to setup legacy OAuth endpoints: {e}", exc_info=True
            )

        # Legacy Authentication System Setup with Access Control
        if use_google_oauth:
            from auth.token_validator import create_access_controlled_auth_provider

            jwt_auth_provider = create_access_controlled_auth_provider(
                jwks_uri="https://www.googleapis.com/oauth2/v3/certs",
                issuer="https://accounts.google.com",
                required_scopes=["openid", "email"],
            )
            mcp._auth = jwt_auth_provider
            logger.info(
                "🔐 Legacy Google OAuth Bearer Token authentication enabled WITH ACCESS CONTROL"
            )
            logger.info(
                "🌐 Using Google's JWKS endpoint: https://www.googleapis.com/oauth2/v3/certs"
            )
            logger.info("🎯 OAuth issuer: https://accounts.google.com")
            logger.info(
                "🔒 Access enforcement: Only users with stored credentials can connect"
            )

        elif enable_jwt_auth:
            from auth.jwt_auth import setup_jwt_auth

            jwt_auth_provider = setup_jwt_auth()
            mcp._auth = jwt_auth_provider
            logger.info(
                "🔐 Custom JWT Bearer Token authentication enabled (development mode)"
            )
            logger.info("⚠️  No access control on JWT tokens - for testing only")

        else:
            logger.info("⚠️ Authentication DISABLED (for testing)")
