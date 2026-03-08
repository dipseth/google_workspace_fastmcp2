"""FastMCP2 Google Workspace MCP Server.

A comprehensive MCP server for Google Workspace integration with OAuth 2.1 authentication.
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
    EnhancementLevel,
    setup_enhanced_sampling_demo_tools,
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
        from fastmcp.server.auth.providers.google import GoogleProvider

        # The GoogleProvider handles:
        # - /.well-known/oauth-protected-resource (RFC 9728)
        # - /.well-known/oauth-authorization-server (RFC 8414)
        # - /authorize (OAuth authorization)
        # - /token (token exchange)
        # - /auth/callback (OAuth redirect)
        # - Dynamic Client Registration (RFC 7591)
        # - PKCE (S256) automatically
        # - Bearer token validation on /mcp endpoint
        google_auth_provider = GoogleProvider(
            client_id=_fastmcp_google_client_id,
            client_secret=_fastmcp_google_client_secret,
            base_url=settings.base_url,
            required_scopes=["openid", "email", "profile"],
            redirect_path="/auth/callback",  # FastMCP default
        )

        # ─── API Key Bypass for non-OAuth clients (e.g., Roo Code) ───
        # MCP_API_KEY allows pre-shared static tokens to bypass the full OAuth flow.
        # Clients send: Authorization: Bearer <MCP_API_KEY>
        # When matched, we return a synthetic AccessToken without calling Google.
        _mcp_api_key = os.getenv("MCP_API_KEY", "") or getattr(
            settings, "mcp_api_key", ""
        )
        if _mcp_api_key:
            from fastmcp.server.auth.auth import AccessToken as _FastMCPAccessToken

            _original_load_access_token = google_auth_provider.load_access_token

            async def _load_access_token_with_api_key(token: str):
                """Check for API key before delegating to OAuth validation."""
                if token == _mcp_api_key:
                    logger.debug("🔑 API key authentication — bypassing OAuth")
                    return _FastMCPAccessToken(
                        token=token,
                        client_id="api-key-client",
                        scopes=["openid", "email", "profile"],
                        expires_at=None,  # Never expires
                        claims={"sub": "api-key-user", "auth_method": "api_key"},
                    )
                return await _original_load_access_token(token)

            google_auth_provider.load_access_token = _load_access_token_with_api_key
            logger.info("  🔑 API key bypass: enabled (MCP_API_KEY set)")
        else:
            logger.info("  🔑 API key bypass: disabled (no MCP_API_KEY)")

        logger.info("✅ GoogleProvider configured for OAuth 2.1 (MCP protocol auth)")
        logger.info(f"  🌐 Base URL: {settings.base_url}")
        logger.info("  🔐 PKCE: Automatic (S256)")
        logger.info("  📋 DCR: Built-in (RFC 7591)")
        logger.info("  🔍 Discovery: Auto-registered (RFC 9728 + RFC 8414)")
        logger.info("  🎯 Callback: /auth/callback")
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
)

if google_auth_provider:
    logger.info("🔐 FastMCP running with GoogleProvider OAuth 2.1")
    logger.info("  ✅ RFC 9728 Protected Resource Metadata: auto-registered")
    logger.info("  ✅ RFC 8414 Authorization Server Metadata: auto-registered")
    logger.info("  ✅ RFC 7591 Dynamic Client Registration: auto-registered")
    logger.info("  ✅ Bearer token validation: active on /mcp endpoint")
else:
    logger.info("🔐 FastMCP running with legacy OAuth system (no GoogleProvider)")
    logger.info("  Custom OAuth endpoints will be registered below")

# --- Code Mode Transform (opt-in) ---
if settings.enable_code_mode:
    from fastmcp.experimental.transforms.code_mode import (
        CodeMode,
        GetSchemas,
        GetTags,
        Search,
    )

    code_mode = CodeMode(
        discovery_tools=[
            GetTags(),  # Stage 1: Browse by service category
            Search(default_limit=10),  # Stage 2: BM25 search names + descriptions
            GetSchemas(),  # Stage 3: Get param details for selected tools
        ],
    )
    mcp.add_transform(code_mode)
    logger.info("Code Mode enabled — LLMs will use BM25 search + sandboxed execution")
else:
    logger.info("Code Mode disabled — set ENABLE_CODE_MODE=true in .env to enable")

# PHASE 1 & 2 FIXES APPLIED: AuthMiddleware re-enabled with improved session management
from auth.middleware import create_enhanced_auth_middleware

auth_middleware = create_enhanced_auth_middleware(
    storage_mode=credential_storage_mode,
    google_provider=google_auth_provider,  # Pass GoogleProvider for unified auth when available
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
logger.info(
    "✅ Enhanced Template Parameter Middleware enabled - modular architecture with 12 focused components active"
)

# Setup Enhanced Sampling Middleware with tag-based elicitation (conditional based on SAMPLING_TOOLS setting)
sampling_middleware = None  # Initialize to None for later checks
if settings.sampling_tools:
    logger.info("🎯 Setting up Enhanced Sampling Middleware...")
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
    )
    logger.info(
        "✅ Enhanced Sampling Middleware enabled - tools with target tags get enhanced context"
    )
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

    # Register sampling demo tools
    logger.info("🎯 Registering enhanced sampling demo tools...")
    setup_enhanced_sampling_demo_tools(mcp)
    logger.info(
        "✅ Enhanced sampling demo tools registered (intelligent_email_composer, smart_workflow_assistant, template_rendering_demo, resource_discovery_assistant)"
    )

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

# 8. Add ResponseLimitingMiddleware for tool response size control
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
        from skills import setup_skills_provider

        card_wrapper = get_card_framework_wrapper()
        skills_path = setup_skills_provider(
            mcp=mcp,
            wrappers=[card_wrapper],
            enabled_modules=["card_framework"],
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
                with open(oauth_data_path, "r") as f:
                    oauth_data = json.load(f)
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
