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

# MCPAuthMiddleware removed - deprecated due to architectural mismatch (see auth/mcp_auth_middleware.py)
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
    setup_enhanced_qdrant_tools,
    setup_qdrant_resources,
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
from lifespans import combined_server_lifespan

# ─── GoogleProvider Setup (OAuth 2.1 for Claude.ai / Desktop / MCP Inspector) ───
# When FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID and SECRET are set, we use FastMCP's
# built-in GoogleProvider with SSO credential interception (see auth/sso_google_provider.py).
# When those env vars are NOT set, we fall back to the legacy custom OAuth proxy system.
google_auth_provider = None

_fastmcp_google_client_id = settings.fastmcp_server_auth_google_client_id or os.getenv(
    "FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID", ""
)
_fastmcp_google_client_secret = (
    settings.fastmcp_server_auth_google_client_secret
    or os.getenv("FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET", "")
)

if _fastmcp_google_client_id and _fastmcp_google_client_secret:
    try:
        from auth.scope_registry import ScopeRegistry
        from auth.sso_google_provider import create_sso_google_provider

        _oauth_comprehensive_scopes = ScopeRegistry.resolve_scope_group(
            "oauth_comprehensive"
        )
        _mcp_api_key = os.getenv("MCP_API_KEY", "") or getattr(
            settings, "mcp_api_key", ""
        )

        google_auth_provider = create_sso_google_provider(
            client_id=_fastmcp_google_client_id,
            client_secret=_fastmcp_google_client_secret,
            base_url=settings.base_url,
            comprehensive_scopes=_oauth_comprehensive_scopes,
            mcp_api_key=_mcp_api_key,
            settings=settings,
        )
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
# When GITHUB_OAUTH_CLIENT_ID and SECRET are set, GitHub OAuth is used solely
# for star-gating (alpha access check). All bearer tokens on /mcp are still
# FastMCP JWTs issued via Google OAuth. GitHub never issues bearer tokens.
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

        # If both Google and GitHub are configured, set up dual OAuth routing.
        # GitHub is ONLY used for star-gating (alpha access check) — all actual
        # bearer tokens on /mcp must be FastMCP JWTs issued via Google OAuth.
        # We do NOT add GitHubTokenVerifier to MultiAuth because GitHub tokens
        # should never be used as bearer tokens for API requests.
        if google_auth_provider:
            logger.info("✅ GitHub configured for star-gating (Google handles all tokens)")

            # Set up dual OAuth router for provider selection
            from auth.dual_oauth_provider import DualOAuthRouter

            _dual_oauth_router = DualOAuthRouter(
                google_provider=google_auth_provider,
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
# Factory handles provider selection, lifespan registration, and session-aware wrapping
from middleware.session_sampling_handler import create_sampling_handler

_sampling_handler = create_sampling_handler(settings)

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
    import logging as _logging

    _logging.getLogger("uvicorn.access").setLevel(_logging.DEBUG)
    logger.info("  📝 Uvicorn access logging: DEBUG (traces all HTTP requests)")
else:
    logger.info("🔐 FastMCP running with legacy OAuth system (no GoogleProvider)")
    logger.info("  Custom OAuth endpoints will be registered below")

# ─── Register All Middleware ───
# Middleware ordering is critical — see middleware/server_middleware_setup.py for details.
from middleware.server_middleware_setup import setup_all_middleware

_mw = setup_all_middleware(
    mcp=mcp,
    settings=settings,
    google_auth_provider=google_auth_provider,
    github_auth_provider=github_auth_provider,
    dual_oauth_router=_dual_oauth_router,
    credential_storage_mode=credential_storage_mode,
    minimal_tools_startup=MINIMAL_TOOLS_STARTUP,
)
qdrant_middleware = _mw.qdrant_middleware
sampling_middleware = _mw.sampling_middleware

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

        # Qdrant wrapper is optional — only include if available
        qdrant_wrapper = None
        try:
            from middleware.qdrant_core.qdrant_models_wrapper import get_qdrant_models_wrapper
            qdrant_wrapper = get_qdrant_models_wrapper()
        except Exception as e:
            logger.debug(f"Qdrant models wrapper not available for skills: {e}")

        skill_wrappers = [card_wrapper, email_wrapper]
        skill_modules = ["card_framework", "gmail.mjml_types"]
        if qdrant_wrapper:
            skill_wrappers.append(qdrant_wrapper)
            skill_modules.append("qdrant_client.models")

        skills_path = setup_skills_provider(
            mcp=mcp,
            wrappers=skill_wrappers,
            enabled_modules=skill_modules,
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

# Setup attachment download endpoint (signed URL serving)
from tools.attachment_endpoints import setup_attachment_endpoints

setup_attachment_endpoints(mcp)
logger.info("Attachment download endpoint registered (/attachment-download)")

# Attachment cleanup task is started lazily on first download or via lifespan
# (asyncio.create_task requires a running event loop, so defer to runtime)

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
# Registers supplemental endpoints (GoogleProvider mode) or full legacy endpoints.
from auth.fastmcp_oauth_endpoints import setup_complete_oauth_endpoints

setup_complete_oauth_endpoints(
    mcp=mcp,
    google_auth_provider=google_auth_provider,
    settings=settings,
    use_google_oauth=use_google_oauth,
    enable_jwt_auth=enable_jwt_auth,
)


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
