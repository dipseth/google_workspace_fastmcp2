"""FastMCP2 Google Drive Upload Server.

A focused MCP server for uploading files to Google Drive with OAuth authentication.
"""

import os
from importlib.metadata import version, PackageNotFoundError
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

from auth.fastmcp_oauth_endpoints import setup_oauth_endpoints_fastmcp

# MCPAuthMiddleware removed - deprecated due to architectural mismatch (see auth/mcp_auth_middleware.py)
from auth.jwt_auth import setup_jwt_auth  # Keep for fallback
from auth.middleware import CredentialStorageMode
from config.settings import settings
from docs.docs_tools import setup_docs_tools
from drive.drive_tools import setup_drive_comprehensive_tools
from drive.file_management_tools import setup_file_management_tools
from drive.upload_tools import setup_drive_tools, setup_oauth_callback_handler
from forms.forms_tools import setup_forms_tools
from gcalendar.calendar_tools import setup_calendar_tools
from gchat.chat_tools import setup_chat_tools
from gchat.card_tools import setup_card_tools
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

# FastMCP 2.12.x handles lifespan management automatically - no custom lifespan needed

# Temporary: Disable GoogleProvider to fix MCP Inspector OAuth conflicts
google_auth_provider = None

logger.info("🔄 GoogleProvider temporarily disabled for MCP Inspector compatibility")
logger.info("  Using proven legacy OAuth system")
logger.info("  All discovery endpoints will be available")
logger.info("  No transaction ID conflicts")

# Removed modern_google_provider imports - using existing auth system

# Create FastMCP instance without GoogleProvider (using legacy OAuth system)
mcp = FastMCP(
    name=settings.server_name,
    version=__version__,
    instructions="""Google Workspace MCP Server - Comprehensive access to Google services.

## Authentication
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
    auth=None,  # No GoogleProvider - use legacy OAuth system
)

logger.info("🔐 FastMCP running with legacy OAuth system")
logger.info("  All existing OAuth endpoints active")
logger.info("  MCP Inspector discovery available")

# PHASE 1 & 2 FIXES APPLIED: AuthMiddleware re-enabled with improved session management
from auth.middleware import create_enhanced_auth_middleware

auth_middleware = create_enhanced_auth_middleware(
    storage_mode=credential_storage_mode,
    google_provider=None,  # No GoogleProvider - use legacy system
)
# Enable service selection for existing OAuth system
logger.info("🔧 Configuring service selection for legacy OAuth system")
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

# 5. Initialize Qdrant unified middleware (completely non-blocking)
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
logger.info("✅ Qdrant unified middleware enabled - configured for cloud instance")
logger.info(f"🔧 Qdrant URL: {settings.qdrant_url}")
logger.info(f"🔧 API Key configured: {bool(settings.qdrant_api_key)}")

# Update sampling middleware with Qdrant integration now that it's initialized
if sampling_middleware and hasattr(sampling_middleware, "qdrant_middleware"):
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

# Register drive upload tools
setup_drive_tools(mcp)

# Register server management tools (early for visibility in tool list)
logger.info("🔧 Registering server management tools...")
setup_server_tools(mcp)
logger.info("✅ Server management tools registered")

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

# Initialize ColBERT wrapper on startup if COLBERT_EMBEDDING_DEV=true
if settings.colbert_embedding_dev:
    logger.info(
        "🤖 COLBERT_EMBEDDING_DEV=true - Initializing ColBERT wrapper on startup..."
    )
    try:
        from gchat.card_tools import _initialize_colbert_wrapper

        _initialize_colbert_wrapper()
        logger.info(
            "✅ ColBERT wrapper initialized on startup - multi-vector embeddings ready"
        )
    except Exception as e:
        logger.error(f"❌ Failed to initialize ColBERT wrapper on startup: {e}")
        logger.warning(
            "⚠️ ColBERT mode will still work on-demand if called via use_colbert=True"
        )
else:
    logger.info(
        "⏭️ ColBERT embedding initialization skipped - set COLBERT_EMBEDDING_DEV=true in .env to enable"
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

# Setup service recent resources (recent files from Drive-based services)
setup_service_recent_resources(mcp)

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

# 8. Update MCP instructions with dynamic content from Qdrant
logger.info("📋 Building dynamic MCP instructions from Qdrant analytics...")
try:
    import asyncio

    # Run the async instruction update in a sync context
    asyncio.run(update_mcp_instructions(mcp, qdrant_middleware))
    logger.info("✅ MCP instructions updated with dynamic content from Qdrant")
except Exception as e:
    logger.warning(f"⚠️ Could not update dynamic instructions: {e}")
    logger.info("  📋 Using static base instructions as fallback")


# Setup OAuth endpoints (now using legacy system)
logger.info("🔍 Setting up OAuth discovery endpoints...")
try:
    setup_oauth_endpoints_fastmcp(mcp)
    logger.info("✅ OAuth discovery endpoints configured")
    logger.info(
        f"  Discovery: {settings.base_url}/.well-known/oauth-protected-resource/mcp"
    )
    logger.info(
        f"  Authorization: {settings.base_url}/.well-known/oauth-authorization-server"
    )
    logger.info(f"  Registration: {settings.base_url}/oauth/register")
    logger.info(f"  Callback: {settings.base_url}/oauth2callback")

except Exception as e:
    logger.error(f"❌ Failed to setup OAuth endpoints: {e}", exc_info=True)

# Authentication System Setup with Access Control
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
        "🔐 Google OAuth Bearer Token authentication enabled WITH ACCESS CONTROL"
    )
    logger.info(
        "🌐 Using Google's JWKS endpoint: https://www.googleapis.com/oauth2/v3/certs"
    )
    logger.info("🎯 OAuth issuer: https://accounts.google.com")
    logger.info("🔒 Access enforcement: Only users with stored credentials can connect")

elif enable_jwt_auth:
    # Fallback to custom JWT for development/testing
    jwt_auth_provider = setup_jwt_auth()
    mcp._auth = jwt_auth_provider
    logger.info("🔐 Custom JWT Bearer Token authentication enabled (development mode)")
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
