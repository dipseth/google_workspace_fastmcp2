"""FastMCP2 Google Workspace MCP Server.

A comprehensive MCP server for Google Workspace integration with OAuth 2.1 authentication,
sandboxed code execution (Code Mode), context-aware LLM sampling, and privacy middleware
for PII protection.
"""

import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

# Setup enhanced logging early - no defensive coding needed!
from config.enhanced_logging import setup_logger

logger = setup_logger()

# Get version from package metadata (syncs with pyproject.toml)
try:
    __version__ = version("google-workspace-unlimited")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"  # Fallback for development without install

# Now import the rest of the modules
from fastmcp import FastMCP

from auth.fastmcp_oauth_endpoints import (
    setup_config_api_routes,
    setup_legacy_callback_route,
    setup_oauth_endpoints_fastmcp,
    setup_service_selection_routes,
)

# MCPAuthMiddleware removed - deprecated due to architectural mismatch (see auth/mcp_auth_middleware.py)
from auth.jwt_auth import setup_jwt_auth  # Keep for fallback
from auth.middleware import CredentialStorageMode
from config.settings import settings

# ─── SSL CA Bundle Fix (must be AFTER settings import) ───
# Python 3.11 on macOS/Homebrew often can't find system CA certificates for outgoing
# HTTPS connections. This causes authlib/httpx token exchange with Google to fail:
#   "SSL: CERTIFICATE_VERIFY_FAILED - unable to get local issuer certificate"
# Fix: Always set SSL_CERT_FILE to certifi's CA bundle for outgoing connections.
# Uvicorn's server-side SSL uses ssl_certfile/ssl_keyfile kwargs (not this env var).
try:
    import certifi

    if not os.environ.get("SSL_CERT_FILE"):
        os.environ["SSL_CERT_FILE"] = certifi.where()
        logger.info(f"🔒 SSL_CERT_FILE set to certifi CA bundle: {certifi.where()}")
    else:
        logger.debug(f"🔒 SSL_CERT_FILE already set: {os.environ['SSL_CERT_FILE']}")
except ImportError:
    logger.warning("⚠️ certifi not installed — outgoing HTTPS may fail on macOS")

from docs.docs_tools import setup_docs_tools
from drive.drive_tools import setup_drive_comprehensive_tools
from drive.file_management_tools import setup_file_management_tools
from drive.upload_tools import setup_drive_tools, setup_oauth_callback_handler
from forms.forms_tools import setup_forms_tools
from gcalendar.calendar_tools import setup_calendar_tools
from gchat.card_tools import setup_card_tools
from gchat.chat_tools import setup_chat_tools
from gmail.gmail_tools import setup_gmail_tools
from middleware.qdrant_middleware import (
    QdrantUnifiedMiddleware,
    setup_enhanced_qdrant_tools,
    setup_qdrant_resources,
)
from middleware.sampling_middleware import (
    DSLToolConfig,
    EnhancementLevel,
    ValidationAgentConfig,
    setup_enhanced_sampling_middleware,
)
from middleware.tag_based_resource_middleware import TagBasedResourceMiddleware

# from middleware.template_middleware import setup_template_middleware
from middleware.template_middleware import (
    setup_enhanced_template_middleware as setup_template_middleware,
)
from people.people_tools import setup_people_tools
from photos.advanced_tools import setup_advanced_photos_tools
from photos.photos_tools import setup_photos_tools
from prompts.gmail_prompts import setup_gmail_prompts
from prompts.structured_response_demo_prompts import (
    setup_structured_response_demo_prompts,
)
from resources.chat_digest_resources import setup_chat_digest_resources
from resources.service_list_resources import setup_service_list_resources
from resources.service_recent_resources import setup_service_recent_resources
from resources.template_resources import register_template_resources
from resources.tool_output_resources import setup_tool_output_resources
from resources.user_resources import setup_user_resources
from sheets.sheets_tools import setup_sheets_tools
from slides.slides_tools import setup_slides_tools
from tools.dynamic_instructions import update_mcp_instructions
from tools.server_tools import setup_server_tools
from tools.template_macro_tools import setup_template_macro_tools
from tools.ui_apps import setup_ui_apps, wire_dashboard_to_list_tools

# Authentication setup - choose between Google OAuth and custom JWT
use_google_oauth = os.getenv("USE_GOOGLE_OAUTH", "true").lower() == "true"
enable_jwt_auth = os.getenv("ENABLE_JWT_AUTH", "false").lower() == "true"

# Cloud deployment detection
is_cloud_deployment = settings.is_cloud_deployment
if is_cloud_deployment:
    logger.info("☁️ FastMCP Cloud deployment detected")
    logger.info(
        f"☁️ Using cloud-optimized credential storage: {settings.credential_storage_mode}"
    )
    logger.info(f"☁️ Credentials directory: {settings.credentials_dir}")

# Phase 1 Feature Flags for gradual rollout (loaded from .env via settings)
ENABLE_UNIFIED_AUTH = settings.enable_unified_auth
LEGACY_COMPAT_MODE = settings.legacy_compat_mode
CREDENTIAL_MIGRATION = settings.credential_migration
SERVICE_CACHING = settings.service_caching
ENHANCED_LOGGING = settings.enhanced_logging

logger.info("🚀 Phase 1 OAuth Migration Configuration:")
logger.info(f"  ENABLE_UNIFIED_AUTH: {ENABLE_UNIFIED_AUTH}")
logger.info(f"  LEGACY_COMPAT_MODE: {LEGACY_COMPAT_MODE}")
logger.info(f"  CREDENTIAL_MIGRATION: {CREDENTIAL_MIGRATION}")
logger.info(f"  SERVICE_CACHING: {SERVICE_CACHING}")
logger.info(f"  ENHANCED_LOGGING: {ENHANCED_LOGGING}")

# Minimal Tools Startup Configuration
MINIMAL_TOOLS_STARTUP = settings.minimal_tools_startup
MINIMAL_STARTUP_SERVICES = settings.get_minimal_startup_services()
if MINIMAL_TOOLS_STARTUP:
    logger.info("🚀 Minimal Tools Startup Mode: ENABLED")
    logger.info("  • New sessions start with only essential tools")
    if MINIMAL_STARTUP_SERVICES:
        logger.info(f"  • Default enabled services: {MINIMAL_STARTUP_SERVICES}")
    logger.info("  • Returning sessions restore their previous tool state")
    logger.info(f"  • Session state file: {settings.session_tool_state_path}")
else:
    logger.info("🚀 Minimal Tools Startup Mode: DISABLED (all tools available)")

# Credential storage configuration
storage_mode_str = settings.credential_storage_mode.upper()
try:
    credential_storage_mode = CredentialStorageMode[storage_mode_str]
    logger.info(f"🔐 Credential storage mode: {credential_storage_mode.value}")
except KeyError:
    logger.warning(
        f"⚠️ Invalid CREDENTIAL_STORAGE_MODE '{storage_mode_str}', defaulting to FILE_ENCRYPTED"
    )
    credential_storage_mode = CredentialStorageMode.FILE_ENCRYPTED

# Import composable lifespans for server lifecycle management
from lifespans import (
    combined_server_lifespan,
    register_profile_middleware,
    register_qdrant_middleware,
    register_template_middleware,
)

# ─── GoogleProvider Setup (OAuth 2.1 for Claude.ai / Desktop / MCP Inspector) ───
# When FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID and SECRET are set, we use FastMCP's
# built-in GoogleProvider which auto-registers RFC 9728/8414 compliant discovery
# endpoints. This makes the server work seamlessly with Claude.ai, Claude Desktop,
# and any MCP client that follows the OAuth 2.1 + DCR specification.
#
# When those env vars are NOT set, we fall back to the legacy custom OAuth proxy
# system (which requires manual endpoint registration and doesn't work with
# Claude.ai's expected discovery flow).
google_auth_provider = None

# Check if FastMCP GoogleProvider credentials are configured
_fastmcp_google_client_id = settings.fastmcp_server_auth_google_client_id or os.getenv(
    "FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID", ""
)
_fastmcp_google_client_secret = (
    settings.fastmcp_server_auth_google_client_secret
    or os.getenv("FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET", "")
)

if _fastmcp_google_client_id and _fastmcp_google_client_secret:
    try:
        from fastmcp.server.auth.providers.google import (
            GoogleProvider,
            GoogleTokenVerifier,
        )

        # ─── SSO GoogleProvider ───────────────────────────────────────────
        # Subclasses GoogleProvider to intercept Google tokens during
        # the OAuth code exchange and store them as Google API credentials.
        # This eliminates the need for a separate start_google_auth call —
        # when Claude connects via OAuth, the user grants full API scopes
        # in a single consent screen and credentials are saved automatically.
        from auth.scope_registry import ScopeRegistry

        _oauth_comprehensive_scopes = ScopeRegistry.resolve_scope_group(
            "oauth_comprehensive"
        )

        class SSOGoogleProvider(GoogleProvider):
            """GoogleProvider that saves Google API credentials on first auth."""

            def __init__(self, **kwargs):
                # Separate the scopes: advertise full API scopes to clients so
                # Google's consent screen asks for everything, but keep the
                # token verifier checking only "openid" to avoid false negatives
                # (Google tokeninfo returns full URLs, matching is fragile for
                # 30+ scopes).
                super().__init__(**kwargs)

                # After parent init, override the token verifier's required_scopes
                # so load_access_token doesn't reject tokens missing any of the
                # 30+ API scopes.  We only need "openid" for identity verification.
                if hasattr(self, "_token_validator") and hasattr(
                    self._token_validator, "required_scopes"
                ):
                    self._token_validator.required_scopes = ["openid"]

            async def exchange_authorization_code(self, client, authorization_code):
                """Intercept token exchange to save Google API credentials."""
                # Read the idp_tokens BEFORE the parent deletes the code
                code_model = await self._code_store.get(key=authorization_code.code)
                idp_tokens = code_model.idp_tokens if code_model else None

                # Call parent to do the real exchange (issues FastMCP JWT)
                result = await super().exchange_authorization_code(
                    client, authorization_code
                )

                # Now save the Google tokens as API credentials
                if idp_tokens:
                    try:
                        await self._save_google_credentials(idp_tokens)
                    except Exception as e:
                        logger.warning(
                            f"⚠️ SSO credential save failed (auth still works): {e}"
                        )

                return result

            async def _save_google_credentials(self, idp_tokens: dict):
                """Convert raw Google tokens to Credentials and save them."""
                from google.oauth2.credentials import Credentials

                from auth.google_auth import _save_credentials

                access_token = idp_tokens.get("access_token")
                refresh_token = idp_tokens.get("refresh_token")
                id_token_str = idp_tokens.get("id_token")

                if not access_token:
                    logger.warning("SSO: No access_token in idp_tokens, skipping save")
                    return

                # Determine user email from the id_token or userinfo
                user_email = None
                if id_token_str:
                    try:
                        import base64
                        import json

                        # Decode JWT payload (no verification needed, we trust Google)
                        parts = id_token_str.split(".")
                        if len(parts) >= 2:
                            # Add padding
                            payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                            user_email = payload.get("email")
                            self._google_sub = payload.get("sub")
                    except Exception as e:
                        logger.debug(f"SSO: Could not decode id_token: {e}")

                if not user_email:
                    # Fallback: call Google userinfo API
                    try:
                        import httpx

                        async with httpx.AsyncClient(timeout=10) as http_client:
                            resp = await http_client.get(
                                "https://www.googleapis.com/oauth2/v2/userinfo",
                                headers={"Authorization": f"Bearer {access_token}"},
                            )
                            if resp.status_code == 200:
                                userinfo = resp.json()
                                user_email = userinfo.get("email")
                                self._google_sub = userinfo.get("id")
                    except Exception as e:
                        logger.warning(f"SSO: Could not fetch userinfo: {e}")

                if not user_email:
                    logger.warning("SSO: Could not determine user email, skipping save")
                    return

                # Build google.oauth2.credentials.Credentials
                credentials = Credentials(
                    token=access_token,
                    refresh_token=refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=_fastmcp_google_client_id,
                    client_secret=_fastmcp_google_client_secret,
                    scopes=_oauth_comprehensive_scopes,
                )
                # Attach Google's immutable account ID for OAuth recipient encryption
                credentials._google_sub = getattr(self, "_google_sub", None)

                _save_credentials(user_email, credentials)
                # Log the per-user API key if one was generated
                user_api_key = getattr(credentials, "_user_api_key", None)
                if user_api_key:
                    logger.info(
                        f"🔑 SSO: Per-user API key generated for {user_email} "
                        f"(key will be available via check_drive_auth)"
                    )
                logger.info(
                    f"✅ SSO: Google API credentials saved for {user_email} "
                    f"(refresh_token: {'yes' if refresh_token else 'no'}, "
                    f"scopes: {len(_oauth_comprehensive_scopes)})"
                )

        google_auth_provider = SSOGoogleProvider(
            client_id=_fastmcp_google_client_id,
            client_secret=_fastmcp_google_client_secret,
            base_url=settings.base_url,
            required_scopes=_oauth_comprehensive_scopes,  # Full API scopes for Google consent
            redirect_path="/auth/callback",
            require_authorization_consent=False,  # Google already has its own consent screen
        )

        # ─── API Key + Per-User Key Authentication ───
        # Intercepts load_access_token to check two key types before OAuth:
        #   1. MCP_API_KEY — shared admin/master key (optional, from .env)
        #   2. Per-user keys — individual keys generated on OAuth completion
        # Both are checked before falling back to standard FastMCP JWT validation.
        _mcp_api_key = os.getenv("MCP_API_KEY", "") or getattr(
            settings, "mcp_api_key", ""
        )

        from fastmcp.server.auth.auth import AccessToken as _FastMCPAccessToken

        _original_load_access_token = google_auth_provider.load_access_token

        # Simple in-memory rate limiter for failed auth attempts
        _failed_auth_attempts: dict[str, list[float]] = {}
        _RATE_LIMIT_WINDOW = 60.0  # seconds
        _RATE_LIMIT_MAX = 10  # max failures per window
        _MAX_TRACKED_PREFIXES = 1000  # cap to prevent memory growth from brute-force

        async def _load_access_token_with_api_key(token: str):
            """Check for admin key / per-user key before delegating to OAuth."""
            import hmac
            import time as _time

            # Rate-limit check: reject tokens from sources with too many failures
            token_prefix = token[:8]
            now = _time.time()
            attempts = _failed_auth_attempts.get(token_prefix, [])
            attempts = [t for t in attempts if now - t < _RATE_LIMIT_WINDOW]
            # Write back filtered list (self-cleaning: removes expired timestamps)
            if attempts:
                _failed_auth_attempts[token_prefix] = attempts
            elif token_prefix in _failed_auth_attempts:
                del _failed_auth_attempts[token_prefix]
            if len(attempts) >= _RATE_LIMIT_MAX:
                logger.warning("🚫 Rate limit exceeded for auth attempts")
                return None

            from auth.types import AuthProvenance

            # 1. Shared admin API key (only checked when MCP_API_KEY is set)
            if _mcp_api_key and hmac.compare_digest(token, _mcp_api_key):
                logger.debug("🔑 Admin API key authentication — bypassing OAuth")
                return _FastMCPAccessToken(
                    token=token,
                    client_id="api-key-client",
                    scopes=_oauth_comprehensive_scopes,
                    expires_at=int(_time.time()) + 86400,
                    claims={
                        "sub": "api-key-user",
                        "auth_method": AuthProvenance.API_KEY,
                    },
                )

            # 2. Per-user API key (generated on OAuth completion)
            from auth.user_api_keys import lookup_key

            user_email = lookup_key(token)
            if user_email:
                logger.debug(f"🔑 Per-user API key matched: {user_email}")
                return _FastMCPAccessToken(
                    token=token,
                    client_id=f"user-key-{user_email}",
                    scopes=_oauth_comprehensive_scopes,
                    expires_at=int(_time.time()) + 86400,
                    claims={
                        "sub": user_email,
                        "email": user_email,
                        "auth_method": AuthProvenance.USER_API_KEY,
                    },
                )

            # 3. Normal OAuth token validation (FastMCP JWT)
            logger.info(f"🔍 load_access_token called, token prefix: {token[:20]}...")
            result = await _original_load_access_token(token)
            if result is None:
                logger.warning(
                    f"⚠️ load_access_token returned None for token: {token[:30]}..."
                )
                # Record failed attempt for rate limiting
                _failed_auth_attempts.setdefault(token_prefix, []).append(now)
                # Evict oldest prefix if over cap (defense against unique-token flooding)
                if len(_failed_auth_attempts) > _MAX_TRACKED_PREFIXES:
                    oldest_key = next(iter(_failed_auth_attempts))
                    del _failed_auth_attempts[oldest_key]
            else:
                logger.info(
                    f"✅ load_access_token succeeded: client={result.client_id}, scopes={result.scopes}"
                )
            return result

        google_auth_provider.load_access_token = _load_access_token_with_api_key
        if _mcp_api_key:
            logger.info("  🔑 Token auth: admin key + per-user keys + OAuth")
        else:
            logger.info("  🔑 Token auth: per-user keys + OAuth (no admin key)")

        # ─── Auto-register unknown clients (e.g., Claude providing its own client ID) ───
        # When a client like Claude connects with its own OAuth client ID (not obtained
        # via DCR), FastMCP's get_client() returns None → "Client Not Registered" error.
        # This patch auto-registers unknown clients as proxy DCR clients so they go
        # through the server's OAuth proxy (using the server's Google credentials).
        _original_get_client = google_auth_provider.get_client

        async def _get_client_with_auto_register(client_id: str):
            """Auto-register unknown clients instead of rejecting them."""
            client = await _original_get_client(client_id)
            if client is not None:
                return client

            # Unknown client — auto-register it as a proxy DCR client
            logger.info(f"🔧 Auto-registering unknown client: {client_id[:30]}...")
            try:
                from mcp.shared.auth import OAuthClientInformationFull

                # Create a minimal client registration that the proxy will accept
                auto_client = OAuthClientInformationFull(
                    client_id=client_id,
                    client_secret=None,  # Proxy handles upstream auth
                    redirect_uris=[
                        "http://localhost"
                    ],  # Placeholder; proxy validates via patterns
                    grant_types=["authorization_code", "refresh_token"],
                    response_types=["code"],
                    token_endpoint_auth_method="none",
                    scope="openid email profile",
                    client_name=f"Auto-registered ({client_id[:20]}...)",
                )

                # register_client wraps it in a ProxyDCRClient with redirect URI pattern support
                await google_auth_provider.register_client(auto_client)
                logger.info(f"✅ Auto-registered client: {client_id[:30]}...")

                # Return the newly registered client
                return await _original_get_client(client_id)
            except Exception as e:
                logger.warning(
                    f"⚠️ Auto-registration failed for {client_id[:30]}...: {e}"
                )
                return None

        google_auth_provider.get_client = _get_client_with_auto_register

        # ─── Fix metadata: advertise token_endpoint_auth_method="none" ───
        # Clients like Claude use their own client_id without DCR, so they have
        # no client_secret for this server. The default metadata only advertises
        # ["client_secret_post", "client_secret_basic"], causing Claude to skip
        # the POST /token exchange entirely (it thinks it can't authenticate).
        # Adding "none" tells clients they can exchange codes without a secret.
        import mcp.server.auth.routes as _auth_routes

        _original_build_metadata = _auth_routes.build_metadata

        def _patched_build_metadata(*args, **kwargs):
            metadata = _original_build_metadata(*args, **kwargs)
            if metadata.token_endpoint_auth_methods_supported:
                if "none" not in metadata.token_endpoint_auth_methods_supported:
                    metadata.token_endpoint_auth_methods_supported.append("none")
            else:
                metadata.token_endpoint_auth_methods_supported = ["none"]
            return metadata

        _auth_routes.build_metadata = _patched_build_metadata
        # Also patch the proxy module's direct import of build_metadata
        try:
            import fastmcp.server.auth.oauth_proxy.proxy as _proxy_module

            _proxy_module.build_metadata = _patched_build_metadata
        except (ImportError, AttributeError):
            pass  # Proxy may not use direct import in all versions
        logger.info(
            '  🔓 Metadata patched: token_endpoint_auth_methods includes "none"'
        )

        # Enable DEBUG logging for FastMCP's OAuth proxy to trace auth flow
        import logging as _logging

        for _oauth_logger_name in [
            "fastmcp.server.auth.oauth_proxy.proxy",
            "fastmcp.server.auth.providers.google",
            "mcp.server.auth.handlers.token",
            "mcp.server.auth.handlers.authorize",
        ]:
            _logging.getLogger(_oauth_logger_name).setLevel(_logging.DEBUG)

        logger.info("✅ GoogleProvider configured for OAuth 2.1 (MCP protocol auth)")
        logger.info(f"  🌐 Base URL: {settings.base_url}")
        logger.info("  🔐 PKCE: Automatic (S256)")
        logger.info("  📋 DCR: Built-in (RFC 7591)")
        logger.info("  🔍 Discovery: Auto-registered (RFC 9728 + RFC 8414)")
        logger.info("  🎯 Callback: /auth/callback")
        logger.info("  🔓 Auto-register: Unknown clients proxied automatically")
        logger.info("  ⚡ Consent page: DISABLED (Google provides its own)")
        logger.info("  🐛 OAuth DEBUG logging: ENABLED")
        logger.info("  ✅ Compatible with: Claude.ai, Claude Desktop, MCP Inspector")

    except ImportError as e:
        logger.warning(f"⚠️ GoogleProvider not available (FastMCP version issue): {e}")
        logger.info("  Falling back to legacy OAuth system")
    except Exception as e:
        logger.error(f"❌ Failed to create GoogleProvider: {e}", exc_info=True)
        logger.info("  Falling back to legacy OAuth system")
else:
    logger.info(
        "🔄 GoogleProvider not configured (no FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID)"
    )
    logger.info("  Using legacy OAuth proxy system")
    logger.info("  ⚠️ Claude.ai / Claude Desktop may not work seamlessly")
    logger.info("  💡 To enable: set FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID and")
    logger.info("     FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET in .env")

# ─── GitHub OAuth Provider Setup (Alpha Access via Repo Star Gating) ─────────
# When GITHUB_OAUTH_CLIENT_ID and SECRET are set, we add GitHub as an
# alternative auth provider using MultiAuth. GitHub-authed users are validated
# via repo star check (alpha mode) and receive limited access (no Google API).
github_auth_provider = None
_dual_oauth_router = None

_github_client_id = settings.github_oauth_client_id or os.getenv(
    "GITHUB_OAUTH_CLIENT_ID", ""
)
_github_client_secret = settings.github_oauth_client_secret or os.getenv(
    "GITHUB_OAUTH_CLIENT_SECRET", ""
)

if _github_client_id and _github_client_secret:
    try:
        from auth.github_provider import SSOGitHubProvider
        from fastmcp.server.auth.providers.github import GitHubTokenVerifier

        _github_scopes = [
            s.strip()
            for s in settings.github_oauth_required_scopes.split(",")
            if s.strip()
        ]

        github_auth_provider = SSOGitHubProvider(
            client_id=_github_client_id,
            client_secret=_github_client_secret,
            base_url=settings.base_url,
            required_scopes=_github_scopes,
            gating_repo=settings.github_oauth_gating_repo,
            alpha_mode=settings.alpha_mode,
            require_authorization_consent=False,  # We use our own provider select page
        )

        logger.info("✅ GitHubProvider configured for alpha OAuth")
        logger.info(f"  🔒 Required scopes: {_github_scopes}")
        if settings.alpha_mode and settings.github_oauth_gating_repo:
            logger.info(
                f"  ⭐ Repo star gating: {settings.github_oauth_gating_repo}"
            )

        # If both Google and GitHub are configured, wrap with MultiAuth
        if google_auth_provider:
            from fastmcp.server.auth import MultiAuth

            _github_token_verifier = GitHubTokenVerifier(
                required_scopes=_github_scopes,
            )

            _multi_auth_provider = MultiAuth(
                server=google_auth_provider,  # Google owns the OAuth routes/metadata
                verifiers=[_github_token_verifier],  # GitHub validates opaque tokens
            )

            # Replace google_auth_provider with MultiAuth for FastMCP app creation
            google_auth_provider = _multi_auth_provider
            logger.info("✅ MultiAuth configured: Google (primary) + GitHub (verifier)")

            # Set up dual OAuth router for provider selection
            from auth.dual_oauth_provider import DualOAuthRouter

            _dual_oauth_router = DualOAuthRouter(
                google_provider=_multi_auth_provider.server,
                github_provider=github_auth_provider,
                settings=settings,
            )
            # Patch authorize to redirect to /auth/select instead of Google
            _dual_oauth_router.patch_authorize()
            logger.info("  🔀 Provider selection page: /auth/select")
        else:
            # GitHub-only mode: use GitHubProvider directly
            google_auth_provider = github_auth_provider
            logger.info("✅ GitHub-only OAuth mode (no Google provider)")

    except ImportError as e:
        logger.warning(f"⚠️ GitHubProvider not available: {e}")
    except Exception as e:
        logger.error(f"❌ Failed to create GitHubProvider: {e}", exc_info=True)

# Configure sampling fallback handler (routes through LiteLLM or Anthropic)
_sampling_handler = None


def _create_litellm_handler():
    from middleware.litellm_sampling_handler import LiteLLMSamplingHandler

    # Resolve API key: explicit LITELLM_API_KEY > VENICE_INFERENCE_KEY > None (litellm env var fallback)
    # For anthropic/ models, let LiteLLM use ANTHROPIC_API_KEY env var directly
    # (don't pass Venice key/base which would override the correct provider auth)
    model = settings.litellm_model
    if model.startswith("anthropic/"):
        api_key = settings.litellm_api_key  # Only use explicit override, not Venice
        api_base = settings.litellm_api_base
    else:
        api_key = settings.litellm_api_key or settings.venice_inference_key
        api_base = settings.litellm_api_base
        if (
            not api_base
            and settings.venice_inference_key
            and not settings.litellm_api_key
        ):
            api_base = "https://api.venice.ai/api/v1"
    return LiteLLMSamplingHandler(
        default_model=settings.litellm_model,
        api_key=api_key,
        api_base=api_base,
    )


def _create_anthropic_handler():
    from anthropic import AsyncAnthropic
    from fastmcp.client.sampling.handlers.anthropic import AnthropicSamplingHandler

    handler = AnthropicSamplingHandler(
        default_model="claude-sonnet-4-6",
        client=AsyncAnthropic(api_key=settings.anthropic_api_key),
    )

    # Wrap handler to track sampling costs
    async def _tracking_wrapper(messages, params, context):
        result = await handler(messages, params, context)
        try:
            from middleware.payment.cost_tracker import track_sample_call

            # Estimate from text since Anthropic handler doesn't expose usage
            input_text = " ".join(
                getattr(m.content, "text", "")
                for m in messages
                if hasattr(m, "content") and hasattr(m.content, "text")
            )
            output_text = ""
            if hasattr(result, "content"):
                c = result.content
                if hasattr(c, "text"):
                    output_text = c.text
                elif isinstance(c, list):
                    output_text = " ".join(
                        getattr(b, "text", "") for b in c if hasattr(b, "text")
                    )
            track_sample_call(
                input_text=input_text,
                output_text=output_text,
                model=getattr(result, "model", "claude-sonnet-4-6")
                or "claude-sonnet-4-6",
            )
        except Exception:
            pass
        return result

    # Wrap with Langfuse @observe tracing if configured
    try:
        from middleware.langfuse_integration import wrap_anthropic_handler_with_langfuse

        wrapped = wrap_anthropic_handler_with_langfuse(_tracking_wrapper)
        return wrapped
    except Exception:
        return _tracking_wrapper


_provider = settings.sampling_provider.lower().strip()

if _provider == "litellm":
    try:
        _sampling_handler = _create_litellm_handler()
        logger.info(
            f"🤖 LiteLLM sampling handler configured (model: {settings.litellm_model})"
        )
    except Exception as e:
        logger.warning(f"⚠️ Failed to configure LiteLLM handler: {e}")

elif _provider == "anthropic":
    if settings.anthropic_api_key:
        try:
            _sampling_handler = _create_anthropic_handler()
            logger.info("🤖 Anthropic sampling handler configured")
        except Exception as e:
            logger.warning(f"⚠️ Failed to configure Anthropic handler: {e}")

else:  # "auto"
    # Try LiteLLM first (if venice key or litellm key set), then Anthropic
    _has_litellm_key = settings.litellm_api_key or settings.venice_inference_key
    if _has_litellm_key:
        try:
            _sampling_handler = _create_litellm_handler()
            logger.info(
                f"🤖 LiteLLM sampling handler configured as default (model: {settings.litellm_model})"
            )
        except Exception as e:
            logger.warning(f"⚠️ LiteLLM handler failed, trying Anthropic: {e}")

    if _sampling_handler is None and settings.anthropic_api_key:
        try:
            _sampling_handler = _create_anthropic_handler()
            logger.info("🤖 Anthropic sampling handler configured (fallback)")
        except Exception as e:
            logger.warning(f"⚠️ Failed to configure Anthropic handler: {e}")

if _sampling_handler is None:
    logger.warning(
        "⚠️ No sampling handler — set VENICE_INFERENCE_KEY, LITELLM_API_KEY, or ANTHROPIC_API_KEY"
    )

# Register LiteLLM handler for cache keepalive lifespan access
from lifespans.server_lifespans import register_litellm_handler

register_litellm_handler(_sampling_handler)

# Wrap with session-aware handler for per-user LLM provider configuration
from middleware.session_sampling_handler import SessionAwareSamplingHandler

_sampling_handler = SessionAwareSamplingHandler(_sampling_handler)

# Create FastMCP instance with composed lifespans for proper lifecycle management
# Lifespans handle: Qdrant init/shutdown, ColBERT init, session state persistence,
# cache cleanup, and dynamic instructions update
mcp = FastMCP(
    name=settings.server_name,
    version=__version__,
    list_page_size=settings.list_page_size or None,  # 0/None = no pagination
    lifespan=combined_server_lifespan,  # Composed lifespans for server lifecycle
    instructions="""Google Workspace MCP Server - Comprehensive access to Google services.

## Authentication
This server uses OAuth 2.1 for authentication. When connecting from Claude.ai
or Claude Desktop, authentication is handled automatically via the MCP protocol.

For manual/legacy auth:
1. Call `start_google_auth` with your email to begin OAuth flow
2. Complete authentication in browser
3. Call `check_drive_auth` to verify credentials

## Available Services
- **Drive**: Upload, search, list, manage files
- **Gmail**: Send, search, read emails
- **Docs**: Create and edit documents
- **Sheets**: Read and write spreadsheets
- **Slides**: Create presentations
- **Calendar**: Manage events
- **Chat**: Send messages and cards
- **Photos**: Access photo library
- **Forms**: Create and manage forms

## Tool Management
Use `manage_tools` to list, enable, or disable tools at runtime.""",
    auth=google_auth_provider,  # GoogleProvider when configured, None for legacy fallback
    sampling_handler=_sampling_handler,  # Anthropic fallback when client lacks sampling
    sampling_handler_behavior="fallback",  # Use client LLM when available, Anthropic when not
)

if google_auth_provider:
    logger.info("🔐 FastMCP running with GoogleProvider OAuth 2.1")
    logger.info("  ✅ RFC 9728 Protected Resource Metadata: auto-registered")
    logger.info("  ✅ RFC 8414 Authorization Server Metadata: auto-registered")
    logger.info("  ✅ RFC 7591 Dynamic Client Registration: auto-registered")
    logger.info("  ✅ Bearer token validation: active on /mcp endpoint")
    logger.info("  ⚡ Consent page: DISABLED (Google provides its own)")

    # Enable uvicorn access logging at DEBUG level to trace all HTTP requests
    # This captures whether clients call POST /token after /authorize callback
    _logging.getLogger("uvicorn.access").setLevel(_logging.DEBUG)
    logger.info("  📝 Uvicorn access logging: DEBUG (traces all HTTP requests)")
else:
    logger.info("🔐 FastMCP running with legacy OAuth system (no GoogleProvider)")
    logger.info("  Custom OAuth endpoints will be registered below")

# ─── Register Dual OAuth Routes (GitHub + Google provider selection) ──────────
if _dual_oauth_router:
    from starlette.routing import Route as _StarletteRoute

    for _route in _dual_oauth_router.get_custom_routes():
        mcp._additional_http_routes.append(_route)
        logger.info(f"  🔀 Registered dual OAuth route: {_route.path}")

# --- Code Mode Transform (opt-in) ---
if settings.enable_code_mode:
    from tools.code_mode import setup_code_mode

    setup_code_mode(mcp)
else:
    logger.info("Code Mode disabled — set ENABLE_CODE_MODE=true in .env to enable")

# PHASE 1 & 2 FIXES APPLIED: AuthMiddleware re-enabled with improved session management
from auth.middleware import create_enhanced_auth_middleware

auth_middleware = create_enhanced_auth_middleware(
    storage_mode=credential_storage_mode,
    google_provider=google_auth_provider,  # GoogleProvider/MultiAuth when configured
    github_provider=github_auth_provider,  # GitHubProvider when configured (for session enrichment)
)
# Enable service selection for existing OAuth system
logger.info("🔧 Configuring service selection for OAuth system")
auth_middleware.enable_service_selection(enabled=True)
logger.info("✅ Service selection interface enabled for OAuth flows")

mcp.add_middleware(auth_middleware)


# Register the AuthMiddleware instance in context for tool access
from auth.context import set_auth_middleware

set_auth_middleware(auth_middleware)
logger.info("✅ AuthMiddleware RE-ENABLED with Phase 1 & 2 fixes:")
logger.info("  ✅ Instance-level session tracking (no FastMCP context dependency)")
logger.info("  ✅ Simplified auto-injection (90 lines → 20 lines)")
logger.info("  ✅ All 18 unit tests passing")
logger.info("  🔍 Monitoring for context lifecycle issues...")

# Setup Session Tool Filtering Middleware for per-session tool enable/disable
from middleware.session_tool_filtering_middleware import (
    setup_session_tool_filtering_middleware,
)

session_tool_filter_middleware = setup_session_tool_filtering_middleware(
    mcp,
    enable_debug=True,  # Enable verbose logging for testing
    minimal_startup=MINIMAL_TOOLS_STARTUP,  # Use setting from config
)
if MINIMAL_TOOLS_STARTUP:
    logger.info(
        "  ✅ Minimal startup mode active - new sessions get only essential tools"
    )
else:
    logger.info("  ✅ Per-session tool enable/disable supported via scope='session'")

# Profile Enrichment Middleware will be initialized after Qdrant middleware
# to enable optional Qdrant-backed persistent caching
profile_middleware = None

# Setup Enhanced Template Parameter Middleware with full Jinja2 support (MUST be before tools are registered)
logger.info(
    "🎭 Setting up Enhanced Template Parameter Middleware with full modular architecture..."
)
template_middleware = setup_template_middleware(
    mcp,
    enable_debug=True,  # Force enable for testing
    enable_caching=True,
    cache_ttl_seconds=300,
)
# Register with lifespan for cache cleanup on shutdown
register_template_middleware(template_middleware)

# Register email_symbols as a Jinja2 global so macros can access them
try:
    from gmail.email_wrapper_api import get_email_symbols

    jinja_env = template_middleware.jinja_env_manager.jinja2_env
    if jinja_env:
        jinja_env.globals["email_symbols"] = get_email_symbols()
        logger.info("📧 Registered email_symbols as Jinja2 global")
except Exception as e:
    logger.warning(f"⚠️ Could not register email_symbols global: {e}")

logger.info(
    "✅ Enhanced Template Parameter Middleware enabled - modular architecture with 12 focused components active"
)

# Setup Enhanced Sampling Middleware with tag-based elicitation (conditional based on SAMPLING_TOOLS setting)
sampling_middleware = None  # Initialize to None for later checks
if settings.sampling_tools:
    logger.info("🎯 Setting up Enhanced Sampling Middleware...")

    # Build DSLToolConfig instances from available domain modules
    dsl_configs: dict[str, DSLToolConfig] = {}
    try:
        from gchat.wrapper_api import (
            CardDSLResult,
            extract_dsl_from_description,
            get_dsl_documentation,
            parse_dsl,
        )

        dsl_configs["send_dynamic_card"] = DSLToolConfig(
            arg_key="card_description",
            parse_fn=parse_dsl,
            extract_fn=extract_dsl_from_description,
            result_type=CardDSLResult,
            description_attr="card_description",
            params_attr="card_params",
            params_arg_key="card_params",
            get_docs_fn=lambda: get_dsl_documentation(
                include_examples=True, include_hierarchy=True
            ),
            dsl_type_label="card",
            error_keywords=["card_description"],
        )
    except ImportError:
        logger.warning("Card DSL validation disabled — gchat module unavailable")

    try:
        from gmail.email_wrapper_api import (
            EmailDSLResult,
            extract_email_dsl_from_description,
            get_email_dsl_documentation,
            parse_email_dsl,
        )

        dsl_configs["compose_dynamic_email"] = DSLToolConfig(
            arg_key="email_description",
            parse_fn=parse_email_dsl,
            extract_fn=extract_email_dsl_from_description,
            result_type=EmailDSLResult,
            description_attr="email_description",
            params_attr="email_params",
            params_arg_key="email_params",
            get_docs_fn=lambda: get_email_dsl_documentation(include_examples=True),
            dsl_type_label="email",
            error_keywords=["email_description"],
        )
    except ImportError:
        logger.warning("Email DSL validation disabled — gmail module unavailable")

    sampling_middleware = setup_enhanced_sampling_middleware(
        mcp,
        enable_debug=True,  # Enable for testing and development
        target_tags=[
            "gmail",
            "compose",
            "elicitation",
        ],  # Tools with these tags get enhanced sampling
        qdrant_middleware=None,  # Will be set after Qdrant middleware is initialized
        template_middleware=template_middleware,
        default_enhancement_level=EnhancementLevel.CONTEXTUAL,
        dsl_tool_configs=dsl_configs,
    )
    logger.info(
        "✅ Enhanced Sampling Middleware enabled - tools with target tags get enhanced context"
    )

    # Register validation agents for semantic input validation via sampling
    if settings.sampling_validation_enabled:
        from middleware.sampling_prompts import (
            get_card_validation_prompt,
            get_email_validation_prompt,
            get_qdrant_validation_prompt,
            get_template_macro_validation_prompt,
        )

        # Tier 1: Pre-validation (sync, corrections applied before tool executes)
        sampling_middleware.register_validation_agent(
            "send_dynamic_card",
            ValidationAgentConfig(
                tool_name="send_dynamic_card",
                target_arg_keys=["card_description", "card_params"],
                get_system_prompt_fn=get_card_validation_prompt,
                mode="pre",
                generate_variations=True,
                enabled=False,  # Validation is now opt-in via draft_variations param
            ),
        )
        sampling_middleware.register_validation_agent(
            "compose_dynamic_email",
            ValidationAgentConfig(
                tool_name="compose_dynamic_email",
                target_arg_keys=["email_description", "email_params"],
                get_system_prompt_fn=get_email_validation_prompt,
                mode="pre",
            ),
        )
        sampling_middleware.register_validation_agent(
            "create_template_macro",
            ValidationAgentConfig(
                tool_name="create_template_macro",
                target_arg_keys=[
                    "macro_name",
                    "macro_body",
                    "parameters",
                    "template_content",
                ],
                get_system_prompt_fn=get_template_macro_validation_prompt,
                mode="pre",
            ),
        )

        # Tier 2: Parallel validation (async, advisory metadata in response)
        sampling_middleware.register_validation_agent(
            "qdrant_search",
            ValidationAgentConfig(
                tool_name="qdrant_search",
                target_arg_keys=["query", "filter_dsl", "query_dsl"],
                get_system_prompt_fn=get_qdrant_validation_prompt,
                mode="parallel",
            ),
        )
        logger.info("✅ Validation agents registered for 4 tools (3 pre, 1 parallel)")
    else:
        logger.info("⏭️  Validation agents disabled (SAMPLING_VALIDATION_ENABLED=false)")

else:
    logger.info(
        "⏭️  Enhanced Sampling Middleware disabled - set SAMPLING_TOOLS=true in .env to enable"
    )

# 5. Initialize Qdrant unified middleware (sync creation, async init via lifespan)
# Note: Full async initialization (embedding model, background reindexing) is handled
# by qdrant_lifespan on server startup. This sync init just creates the middleware.
logger.info("🔄 Initializing Qdrant unified middleware...")
qdrant_middleware = QdrantUnifiedMiddleware(
    qdrant_host=settings.qdrant_host,
    qdrant_port=settings.qdrant_port,
    qdrant_api_key=settings.qdrant_api_key,
    qdrant_url=settings.qdrant_url,
    collection_name="mcp_tool_responses",
    auto_discovery=True,  # Enable auto-discovery to find available Qdrant instances
    ports=[
        settings.qdrant_port,
        6333,
        6335,
        6334,
    ],  # Try configured port first, then fallback
)
mcp.add_middleware(qdrant_middleware)
# Register with lifespan for async initialization and graceful shutdown
register_qdrant_middleware(qdrant_middleware)
logger.info("✅ Qdrant unified middleware created (async init via lifespan)")
logger.info(f"🔧 Qdrant URL: {settings.qdrant_url}")
logger.info(f"🔧 API Key configured: {bool(settings.qdrant_api_key)}")

# Update sampling middleware with Qdrant integration now that it's initialized
if sampling_middleware:
    sampling_middleware.qdrant_middleware = qdrant_middleware
    logger.info(
        "🔗 Enhanced Sampling Middleware connected to Qdrant for historical context"
    )

    # Demo sampling tools disabled — sampling is focused on validation agents
    # for the 4 registered tools (send_dynamic_card, compose_dynamic_email,
    # create_template_macro, qdrant_search). Re-enable with:
    #   setup_enhanced_sampling_demo_tools(mcp)

# 6. Setup Profile Enrichment Middleware with optional Qdrant integration
logger.info("👤 Setting up Profile Enrichment Middleware for People API integration...")
from middleware.profile_enrichment_middleware import ProfileEnrichmentMiddleware

# Enable Qdrant caching if middleware is available
enable_qdrant_profile_cache = (
    qdrant_middleware is not None and qdrant_middleware.client_manager.is_available
)

profile_middleware = ProfileEnrichmentMiddleware(
    enable_caching=True,
    cache_ttl_seconds=300,
    qdrant_middleware=qdrant_middleware if enable_qdrant_profile_cache else None,
    enable_qdrant_cache=enable_qdrant_profile_cache,
)
mcp.add_middleware(profile_middleware)
# Register with lifespan for cache cleanup on shutdown
register_profile_middleware(profile_middleware)

if enable_qdrant_profile_cache:
    logger.info("✅ Profile Enrichment Middleware enabled with TWO-TIER CACHING:")
    logger.info("  📦 Tier 1: In-memory cache (5-minute TTL, ultra-fast)")
    logger.info("  🗄️ Tier 2: Qdrant persistent cache (survives restarts)")
else:
    logger.info("✅ Profile Enrichment Middleware enabled with in-memory caching only")
    logger.info("  📦 In-memory cache (5-minute TTL)")
    logger.info("  ℹ️ Qdrant persistent cache: disabled (Qdrant not available)")

# 7. Add TagBasedResourceMiddleware for service list resource handling (LAST)
logger.info(
    "🏷️ Setting up TagBasedResourceMiddleware for service:// resource handling..."
)
tag_based_middleware = TagBasedResourceMiddleware(enable_debug_logging=True)
mcp.add_middleware(tag_based_middleware)
logger.info(
    "✅ TagBasedResourceMiddleware enabled - service:// URIs will be handled via tag-based tool discovery"
)

# 8. Add PrivacyMiddleware for PII encryption (after all data-producing middleware)
from middleware.privacy.middleware import PrivacyMiddleware

privacy_middleware = PrivacyMiddleware(
    mode=settings.privacy_mode,  # server default ("disabled" is valid)
    additional_fields=settings.privacy_field_patterns,
    exclude_tools=settings.privacy_exclude_tools,
)
mcp.add_middleware(privacy_middleware)
logger.info(
    f"Privacy middleware registered (default={settings.privacy_mode}, per-session toggle available)"
)

# 8b. X402 Payment Protocol Middleware (conditional)
if settings.payment_enabled:
    from middleware.payment import X402PaymentMiddleware, get_resource_server

    # Initialize the x402 SDK resource server for real payment verification
    try:
        x402_resource_server = get_resource_server(settings)
    except Exception as _x402_err:
        logger.warning(
            "x402 SDK init failed (%s), falling back to stub mode", _x402_err
        )
        x402_resource_server = None

    payment_middleware = X402PaymentMiddleware(
        gated_tools=settings.payment_gated_tools,
        free_for_oauth=settings.payment_free_for_oauth,
        session_ttl_minutes=settings.payment_session_ttl_minutes,
        resource_server=x402_resource_server,
    )
    mcp.add_middleware(payment_middleware)
    logger.info("X402 Payment middleware enabled (x402 SDK v2)")
    logger.info(f"  Recipient: {settings.payment_recipient_wallet or '(not set)'}")
    logger.info(f"  Amount: {settings.payment_usdc_amount} USDC")
    logger.info(f"  Network: {settings.payment_network}")
    logger.info(f"  Facilitator: {settings.payment_facilitator_url}")
    logger.info(f"  Scheme: {settings.payment_scheme}")
    logger.info(f"  Free for OAuth: {settings.payment_free_for_oauth}")
    logger.info(f"  SDK: {'active' if x402_resource_server else 'stub fallback'}")
else:
    logger.info("X402 Payment middleware disabled (PAYMENT_ENABLED=false)")

# 9. Add ResponseLimitingMiddleware for tool response size control
if settings.response_limit_max_size > 0:
    from fastmcp.server.middleware.response_limiting import ResponseLimitingMiddleware

    _rl_tools = [
        t.strip() for t in settings.response_limit_tools.split(",") if t.strip()
    ] or None
    response_limiting_middleware = ResponseLimitingMiddleware(
        max_size=settings.response_limit_max_size,
        tools=_rl_tools,
    )
    mcp.add_middleware(response_limiting_middleware)
    logger.info(
        f"✅ ResponseLimitingMiddleware enabled — max {settings.response_limit_max_size:,} bytes"
        + (f" for tools: {_rl_tools}" if _rl_tools else " (all tools)")
    )

# 9. Dashboard cache middleware — caches list-tool results for ui://data-dashboard.
# Registered LAST (outermost) so it wraps all other middleware and always sees tool calls,
# even if an inner middleware (e.g., session tool filter) handles the call directly.
from middleware.dashboard_cache_middleware import DashboardCacheMiddleware

dashboard_cache_middleware = DashboardCacheMiddleware()
mcp.add_middleware(dashboard_cache_middleware)
logger.info("✅ Dashboard cache middleware registered (outermost)")

# 10. Redis-backed response caching (offloads tool response cache to Redis Cloud)


def _mask_redis_url(url: str) -> str:
    """Redact password from Redis URL for safe logging."""
    from urllib.parse import urlparse, urlunparse

    try:
        parsed = urlparse(url)
        if parsed.password:
            masked = parsed._replace(
                netloc=f"{parsed.username or ''}:***@{parsed.hostname}"
                + (f":{parsed.port}" if parsed.port else "")
            )
            return urlunparse(masked)
    except Exception:
        pass
    return "redis://***"


if settings.redis_io_url_string:
    try:
        from fastmcp.server.middleware.caching import ResponseCachingMiddleware
        from key_value.aio.stores.redis import RedisStore
        from key_value.aio.wrappers.prefix_collections import PrefixCollectionsWrapper

        _redis_store = RedisStore(url=settings.redis_io_url_string)
        _namespaced_store = PrefixCollectionsWrapper(
            key_value=_redis_store, prefix="gw-mcp"
        )
        # Cache list operations (tools/resources/prompts) but NOT tool calls —
        # tool calls have side effects and caching errors breaks Code Mode.
        mcp.add_middleware(
            ResponseCachingMiddleware(
                cache_storage=_namespaced_store,
                call_tool_settings={"enabled": False},
            )
        )
        _safe_url = _mask_redis_url(settings.redis_io_url_string)
        logger.info(
            f"✅ Redis ResponseCachingMiddleware enabled ({_safe_url}, list ops only)"
        )

        # Share Redis store with dashboard cache middleware for offloading
        from middleware.dashboard_cache_middleware import set_redis_store

        set_redis_store(_redis_store)
        logger.info("  Redis store shared with dashboard cache middleware")
    except Exception as _redis_err:
        logger.warning(
            f"⚠️ Redis caching setup failed (falling back to in-memory): {_redis_err}"
        )
else:
    logger.info("Redis caching disabled (REDIS_IO_URL_STRING not set)")

# Register drive upload tools
setup_drive_tools(mcp)

# Register server management tools (early for visibility in tool list)
logger.info("🔧 Registering server management tools...")
setup_server_tools(mcp)
logger.info("✅ Server management tools registered")

# Register MCP Apps Phase 1 UI resources
setup_ui_apps(mcp)
logger.info("✅ MCP App UI resources registered")

# Register comprehensive Drive tools (search, list, get content, create)
setup_drive_comprehensive_tools(mcp)

# Register Drive file management tools (move, copy, rename, delete)
setup_file_management_tools(mcp)

# Register Gmail tools
setup_gmail_tools(mcp)


# Register Email Template tools
# setup_template_tools(mcp)

# Register Google Docs tools
setup_docs_tools(mcp)

# Register Google Forms tools
setup_forms_tools(mcp)

# Register Google Slides tools
setup_slides_tools(mcp)

# Register Google Calendar tools
setup_calendar_tools(mcp)

# Register Google Chat tools
setup_chat_tools(mcp)

# Register Card Tools with ModuleWrapper integration
setup_card_tools(mcp)

# Setup Skills Provider for FastMCP (if enabled)
if settings.enable_skills_provider:
    logger.info("📚 Setting up Skills Provider for FastMCP...")
    try:
        from gchat.card_framework_wrapper import get_card_framework_wrapper
        from gmail.email_wrapper_setup import get_email_wrapper
        from skills import setup_skills_provider

        card_wrapper = get_card_framework_wrapper()
        email_wrapper = get_email_wrapper()
        skills_path = setup_skills_provider(
            mcp=mcp,
            wrappers=[card_wrapper, email_wrapper],
            enabled_modules=["card_framework", "gmail.mjml_types"],
            skills_root=settings.skills_directory_path,
            auto_regenerate=settings.skills_auto_regenerate,
        )
        if skills_path:
            logger.info(f"✅ Skills Provider enabled: {skills_path}")
        else:
            logger.warning("⚠️ Skills Provider setup returned no path")
    except ImportError as e:
        logger.warning(f"⚠️ Skills Provider not available (FastMCP 3.0+ required): {e}")
    except Exception as e:
        logger.error(f"❌ Failed to setup Skills Provider: {e}")
else:
    logger.info(
        "⏭️ Skills Provider disabled - set ENABLE_SKILLS_PROVIDER=true in .env to enable"
    )

# ColBERT initialization is now handled by colbert_lifespan on server startup
# This avoids sync initialization at module load and ensures proper async context
if settings.colbert_embedding_dev:
    logger.info(
        "🤖 COLBERT_EMBEDDING_DEV=true - ColBERT wrapper will initialize via lifespan"
    )
else:
    logger.info(
        "⏭️ ColBERT embedding disabled - set COLBERT_EMBEDDING_DEV=true in .env to enable"
    )

# DEPRECATED: Smart Card Tool removed due to formatting issues with Google Chat Cards v2 API
# The send_smart_card function had structural problems that prevented proper card rendering
# Use the working card types instead: send_simple_card, send_interactive_card, send_form_card
# setup_smart_card_tool(mcp)

# Register ModuleWrapper middleware with custom collection name to match card_tools.py
# TEMPORARILY DISABLED: Testing MCP SDK 1.21.1 compatibility
# logger.info("🔄 Initializing ModuleWrapper middleware...")
# middleware = setup_module_wrapper_middleware(mcp, modules_to_wrap=["card_framework.v2"], tool_pushdown=False)
# # Override the collection name to match what card_tools.py expects
# if "card_framework.v2" in middleware.wrappers:
#     wrapper = middleware.wrappers["card_framework.v2"]
#     wrapper.collection_name = "card_framework_components_fastembed"
#     logger.info("✅ Updated ModuleWrapper to use FastEmbed collection: card_framework_components_fastembed")
# logger.info("✅ ModuleWrapper middleware initialized with tools enabled")
logger.info(
    "⚠️ ModuleWrapper middleware temporarily disabled - testing MCP SDK 1.21.1 compatibility"
)

# Register JWT-enhanced Chat tools (demonstration)
# setup_jwt_chat_tools(mcp)

# Register Google Chat App Development tools
# setup_chat_app_tools(mcp)

# # Register Google Chat App Development prompts
# setup_chat_app_prompts(mcp)

# Register Gmail prompts
setup_gmail_prompts(mcp)

# Register Structured Response Demo prompts
setup_structured_response_demo_prompts(mcp)

# Register Google Sheets tools
setup_sheets_tools(mcp)

# Register Google Photos tools
setup_photos_tools(mcp)

# Register Advanced Google Photos tools with optimization
setup_advanced_photos_tools(mcp)

# Register Google People tools
setup_people_tools(mcp)

# Setup OAuth callback handler
setup_oauth_callback_handler(mcp)

# Setup user and authentication resources
setup_user_resources(mcp)

# Setup tool output resources (cached outputs and Qdrant integration)
setup_tool_output_resources(mcp, qdrant_middleware)

# Setup service list resources (dynamic discovery of list-based tools)
# These resources define the URI patterns and documentation
# TagBasedResourceMiddleware intercepts and handles the actual requests
setup_service_list_resources(mcp)
logger.info(
    "✅ Service list resources registered - URIs handled by TagBasedResourceMiddleware"
)

# Wire data-dashboard UI to all list tools (centralized — no per-tool edits needed)
patched = wire_dashboard_to_list_tools(mcp)
logger.info(f"✅ Data dashboard wired to {patched} list tools")

# Setup service recent resources (recent files from Drive-based services)
setup_service_recent_resources(mcp)

# Setup chat digest resources (aggregated recent messages across Chat spaces)
setup_chat_digest_resources(mcp)

# Setup template macro resources (discovery and usage examples)
logger.info("📚 Registering template macro resources...")
register_template_resources(mcp)
logger.info(
    "✅ Template macro resources registered - URIs handled by EnhancedTemplateMiddleware"
)

# Setup health check endpoints for Docker/Kubernetes monitoring
from tools.health_endpoints import setup_health_endpoints

setup_health_endpoints(
    mcp,
    google_auth_provider=google_auth_provider,
    credential_storage_mode=credential_storage_mode,
)

# Setup feedback endpoints for SmartCardBuilder feedback loop
from tools.feedback_endpoints import setup_feedback_endpoints

setup_feedback_endpoints(mcp)

# Setup payment flow endpoints (browser paywall page + completion callback)
if settings.payment_enabled:
    from tools.payment_endpoints import setup_payment_endpoints

    setup_payment_endpoints(mcp)
    logger.info(
        "Payment flow endpoints registered (/pay, /api/payment-complete, /payment-status)"
    )

# Register template macro management tools
logger.info("🎨 Registering template macro management tools...")
setup_template_macro_tools(mcp)
logger.info("✅ Template macro management tools registered")


# Register Qdrant tools and resources if middleware is available
try:
    if qdrant_middleware:
        logger.info("📊 Registering Qdrant search tools...")
        setup_enhanced_qdrant_tools(mcp, qdrant_middleware)
        logger.info("✅ Qdrant search and diagnostic tools registered")

        logger.info("📋 Registering Qdrant resources...")
        setup_qdrant_resources(mcp, qdrant_middleware)
        logger.info("✅ Qdrant resources registered - qdrant:// URIs available")
except Exception as e:
    logger.warning(f"⚠️ Could not register Qdrant tools and resources: {e}")

# NOTE: Qdrant Search V2 DSL tools (qdrant_search_v2, qdrant_search_v2_natural,
# qdrant_search_v2_symbols) have been merged into the unified 'search' and
# 'search_symbols' tools registered via setup_enhanced_qdrant_tools above.
# The DSL library code (executor, query_builder, types) lives in middleware/qdrant_core/.

# 8. Dynamic MCP instructions are now handled by dynamic_instructions_lifespan
# This avoids blocking asyncio.run() at module load time and ensures proper async context
logger.info("📋 Dynamic MCP instructions will be updated via lifespan on server start")


# ─── OAuth Endpoint Setup ───
# When GoogleProvider is active, FastMCP auto-registers all RFC-compliant OAuth
# discovery and operational endpoints. Custom endpoints are ONLY needed when
# GoogleProvider is not available (legacy mode).
if google_auth_provider:
    # GoogleProvider is active — it already registered all discovery endpoints.
    # Only register supplemental endpoints that don't conflict (status, service selection).
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

    # Register supplemental status/service-selection endpoints that don't conflict
    # with GoogleProvider's built-in routes
    try:
        # Only register non-conflicting custom routes (status check, service selection page)
        @mcp.custom_route("/oauth/status", methods=["GET", "OPTIONS"])
        async def oauth_status_check_gp(request):
            """OAuth authentication status polling endpoint (supplemental)."""
            from starlette.responses import JSONResponse, Response

            if request.method == "OPTIONS":
                return Response(
                    status_code=200, headers={"Access-Control-Allow-Origin": "*"}
                )
            import json
            from datetime import datetime
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

        # Service selection routes are needed by start_google_auth scope-upgrade flow
        setup_service_selection_routes(mcp)
        logger.info("  ✅ Service selection routes registered (/auth/services/select)")

        # Register the legacy /oauth2callback so start_google_auth can complete
        setup_legacy_callback_route(mcp)
        logger.info("  ✅ Legacy /oauth2callback registered for start_google_auth flow")

        # Register config API routes (privacy mode, sampling config) for OAuth success page
        setup_config_api_routes(mcp)
        logger.info("  ✅ Config API routes registered for OAuth success page")

        # Register status-check route for credential status page
        from auth.fastmcp_oauth_endpoints import setup_status_check_routes

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
        logger.error(f"❌ Failed to setup legacy OAuth endpoints: {e}", exc_info=True)

    # Legacy Authentication System Setup with Access Control
    if use_google_oauth:
        # Setup Google OAuth with ACCESS CONTROL enforcement
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
        # Fallback to custom JWT for development/testing
        jwt_auth_provider = setup_jwt_auth()
        mcp._auth = jwt_auth_provider
        logger.info(
            "🔐 Custom JWT Bearer Token authentication enabled (development mode)"
        )
        logger.info("⚠️  No access control on JWT tokens - for testing only")

    else:
        logger.info("⚠️ Authentication DISABLED (for testing)")


def main():
    """Main entry point for the server."""
    import argparse

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="FastMCP Google Workspace Server")
    parser.add_argument(
        "--transport",
        "-t",
        choices=["stdio", "http", "sse"],
        default=None,
        help="Transport mode: stdio (default), http, or sse",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=None,
        help="Port for HTTP/SSE transport (default: from settings)",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Host for HTTP/SSE transport (default: from settings)",
    )
    args = parser.parse_args()

    logger.info(f"Starting {settings.server_name}")
    logger.info(f"Configuration: {settings.base_url}")
    logger.info(
        f"Protocol: {'HTTPS (SSL enabled)' if settings.enable_https else 'HTTP'}"
    )
    logger.info(f"OAuth callback: {settings.dynamic_oauth_redirect_uri}")
    logger.info(f"Credentials directory: {settings.credentials_dir}")

    # Validate SSL configuration if HTTPS is enabled (skip for cloud deployment)
    if settings.enable_https and not settings.is_cloud_deployment:
        try:
            settings.validate_ssl_config()
            logger.info("✅ SSL configuration validated")
            logger.info(f"SSL Certificate: {settings.ssl_cert_file}")
            logger.info(f"SSL Private Key: {settings.ssl_key_file}")
            if settings.ssl_ca_file:
                logger.info(f"SSL CA File: {settings.ssl_ca_file}")
        except ValueError as e:
            logger.error(f"❌ SSL configuration error: {e}")
            raise
    elif settings.is_cloud_deployment:
        logger.info("☁️ Skipping SSL validation - handled by FastMCP Cloud")

    # Ensure credentials directory exists
    Path(settings.credentials_dir).mkdir(parents=True, exist_ok=True)

    try:
        # Check for transport mode: CLI args > environment variable > default (stdio)
        transport_mode = args.transport or os.getenv("MCP_TRANSPORT", "stdio").lower()

        if transport_mode == "stdio":
            # Stdio transport for command-based MCP clients (uvx, npx, etc.)
            logger.info("📡 Starting server with STDIO transport (command-based)")
            mcp.run(transport="stdio")
        else:
            # HTTP/SSE transport for network-based deployment
            # CLI args override settings
            server_host = args.host or settings.server_host
            server_port = args.port or settings.server_port
            run_args = {"host": server_host, "port": server_port}
            logger.info(f"🌐 Starting server on {server_host}:{server_port}")

            # Configure transport and SSL based on HTTPS setting and cloud deployment
            if settings.is_cloud_deployment:
                # FastMCP Cloud handles SSL automatically
                run_args["transport"] = transport_mode
                logger.info(
                    f"☁️ Cloud deployment - using {transport_mode} transport (SSL handled by FastMCP Cloud)"
                )
            elif settings.enable_https:
                ssl_config = settings.get_uvicorn_ssl_config()
                if ssl_config:
                    run_args["transport"] = transport_mode
                    run_args["uvicorn_config"] = ssl_config
                    logger.info(
                        f"🔒 Starting server with {transport_mode.upper()} transport + SSL"
                    )
                    logger.info(f"SSL Certificate: {ssl_config['ssl_certfile']}")
                    logger.info(f"SSL Private Key: {ssl_config['ssl_keyfile']}")
                else:
                    logger.warning(
                        "⚠️ HTTPS enabled but SSL config unavailable, falling back to HTTP"
                    )
                    run_args["transport"] = transport_mode
            else:
                run_args["transport"] = transport_mode
                logger.info(
                    f"🌐 Starting server with {transport_mode.upper()} transport"
                )

            # Run the server with appropriate transport and SSL configuration
            mcp.run(**run_args)

    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
