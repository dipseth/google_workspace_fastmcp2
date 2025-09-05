"""FastMCP2 Google Drive Upload Server.

A focused MCP server for uploading files to Google Drive with OAuth authentication.
"""

import argparse
import os
from pathlib import Path

# Setup enhanced logging early - no defensive coding needed!
from config.enhanced_logging import setup_logger

logger = setup_logger()

# Now import the rest of the modules
from fastmcp import FastMCP
from fastmcp.server.auth.providers.google import GoogleProvider  # FastMCP 2.12.0 GoogleProvider
from config.settings import settings
from auth.middleware import AuthMiddleware, CredentialStorageMode
from auth.mcp_auth_middleware import MCPAuthMiddleware
from auth.google_oauth_auth import setup_google_oauth_auth, get_google_oauth_metadata
from auth.jwt_auth import setup_jwt_auth, create_test_tokens  # Keep for fallback
from auth.fastmcp_oauth_endpoints import setup_oauth_endpoints_fastmcp
from drive.upload_tools import setup_drive_tools, setup_oauth_callback_handler
from drive.drive_tools import setup_drive_comprehensive_tools
from gmail.gmail_tools import setup_gmail_tools
from gmail.template_tools import setup_template_tools
from docs.docs_tools import setup_docs_tools
from forms.forms_tools import setup_forms_tools
from slides.slides_tools import setup_slides_tools
from gcalendar.calendar_tools import setup_calendar_tools
from gchat.chat_tools import setup_chat_tools
# from delete_later.jwt_chat_tools import setup_jwt_chat_tools
from gchat.chat_app_tools import setup_chat_app_tools
from prompts.chat_app_prompts import setup_chat_app_prompts
from prompts.gmail_prompts import setup_gmail_prompts
from prompts.structured_response_demo_prompts import setup_structured_response_demo_prompts
from gchat.unified_card_tool import setup_unified_card_tool
from adapters.module_wrapper_mcp import setup_module_wrapper_middleware
from middleware.structured_response_middleware import setup_structured_response_middleware
from sheets.sheets_tools import setup_sheets_tools
from photos.photos_tools import setup_photos_tools
from photos.advanced_tools import setup_advanced_photos_tools
from middleware.qdrant_unified import QdrantUnifiedMiddleware, setup_enhanced_qdrant_tools
from middleware.template_middleware import setup_template_middleware
from resources.user_resources import setup_user_resources
from resources.tool_output_resources import setup_tool_output_resources
from resources.service_list_resources import setup_service_list_resources
from resources.service_recent_resources import setup_service_recent_resources
from tools.server_tools import setup_server_tools

# Authentication setup - choose between Google OAuth and custom JWT
use_google_oauth = os.getenv("USE_GOOGLE_OAUTH", "true").lower() == "true"
enable_jwt_auth = os.getenv("ENABLE_JWT_AUTH", "false").lower() == "true"

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

# Credential storage configuration
storage_mode_str = settings.credential_storage_mode.upper()
try:
    credential_storage_mode = CredentialStorageMode[storage_mode_str]
    logger.info(f"🔐 Credential storage mode: {credential_storage_mode.value}")
except KeyError:
    logger.warning(f"⚠️ Invalid CREDENTIAL_STORAGE_MODE '{storage_mode_str}', defaulting to FILE_ENCRYPTED")
    credential_storage_mode = CredentialStorageMode.FILE_ENCRYPTED

# Import contextlib for proper async context manager implementation
import contextlib

# Define a proper lifespan context manager for the FastMCP instance
@contextlib.asynccontextmanager
async def lifespan_manager(app: FastMCP):
    """Lifespan context manager for the FastMCP instance."""
    logger.info("🚀 Starting FastMCP server lifespan...")
    # Properly initialize the StreamableHTTPSessionManager task group
    # from fastmcp.server.http import get_session_manager
    # session_manager = get_session_manager()
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    session_manager = StreamableHTTPSessionManager(
        app=app._mcp_server,
        event_store=None,
        json_response=False,
        stateless=False,
    )    
    # Use a nested context manager to ensure proper cleanup
    async with session_manager.run():
        try:
            yield
        except Exception as e:
            logger.error(f"❌ Error in lifespan: {e}", exc_info=True)
    
    logger.info("🛑 Shutting down FastMCP server lifespan...")

# Configure authentication based on feature flags
# During Phase 1, we configure GoogleProvider but don't immediately enforce it
# to maintain dual-flow compatibility
google_auth_provider = None

if ENABLE_UNIFIED_AUTH and settings.fastmcp_server_auth == "GOOGLE":
    # Use FastMCP 2.12.0's GoogleProvider with environment variables
    logger.info("🔑 Configuring FastMCP 2.12.0 GoogleProvider...")
    try:
        # GoogleProvider automatically reads from environment variables:
        # FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID
        # FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET
        # FASTMCP_SERVER_AUTH_GOOGLE_BASE_URL
        google_auth_provider = GoogleProvider()
        logger.info("✅ FastMCP 2.12.0 GoogleProvider configured from environment variables")
        logger.info(f"  Client ID: {settings.fastmcp_server_auth_google_client_id[:20] if settings.fastmcp_server_auth_google_client_id else 'Not set'}...")
        logger.info(f"  Base URL: {settings.fastmcp_server_auth_google_base_url or 'Not set'}")
        # Phase 1: Don't immediately enforce authentication to maintain backward compatibility
        logger.info("🔄 Phase 1: GoogleProvider configured but not enforced (dual-flow mode)")
    except Exception as e:
        logger.error(f"❌ Failed to configure GoogleProvider: {e}")
        logger.warning("⚠️ Falling back to legacy OAuth flow")
        google_auth_provider = None

# Create FastMCP2 instance WITHOUT immediate authentication enforcement during Phase 1
# This maintains backward compatibility while allowing us to test the new auth system
mcp = FastMCP(
    name=settings.server_name,
    version="1.0.0",
    auth=None,  # Phase 1: Keep auth=None for dual-flow compatibility
    lifespan=lifespan_manager  # Add lifespan manager to properly initialize StreamableHTTPSessionManager
)

# Log authentication status
if google_auth_provider:
    logger.info("🔐 GoogleProvider configured but not enforced (Phase 1 dual-flow mode)")
else:
    logger.info("⚠️ FastMCP running without GoogleProvider - using legacy flow only")

# Add enhanced authentication middleware with GoogleProvider integration
from auth.middleware import create_enhanced_auth_middleware
auth_middleware = create_enhanced_auth_middleware(
    storage_mode=credential_storage_mode,
    google_provider=google_auth_provider  # Pass the GoogleProvider instance
)
mcp.add_middleware(auth_middleware)

# Register the AuthMiddleware instance in context for tool access
from auth.context import set_auth_middleware
set_auth_middleware(auth_middleware)

# Add MCP spec-compliant auth middleware for WWW-Authenticate headers
mcp.add_middleware(MCPAuthMiddleware())

# Setup Template Parameter Middleware with Jinja2 support (MUST be before tools are registered)
logger.info("🎭 Setting up Template Parameter Middleware with Jinja2 support...")
template_middleware = setup_template_middleware(
    mcp,
    enable_debug=True,  # Force enable for testing
    enable_caching=True,
    cache_ttl_seconds=300
)
logger.info("✅ Template Parameter Middleware with Jinja2 support enabled - automatic resource templating + professional templates active")


# Initialize Qdrant unified middleware (completely non-blocking)
logger.info("🔄 Initializing Qdrant unified middleware...")
qdrant_middleware = QdrantUnifiedMiddleware()
mcp.add_middleware(qdrant_middleware)
logger.info("✅ Qdrant unified middleware enabled - will initialize on first use")


# Register drive upload tools
setup_drive_tools(mcp)

# Register comprehensive Drive tools (search, list, get content, create)
setup_drive_comprehensive_tools(mcp)

# Register Gmail tools
setup_gmail_tools(mcp)

# Register Email Template tools
setup_template_tools(mcp)

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

# Register Unified Card Tool with ModuleWrapper integration
setup_unified_card_tool(mcp)

# DEPRECATED: Smart Card Tool removed due to formatting issues with Google Chat Cards v2 API
# The send_smart_card function had structural problems that prevented proper card rendering
# Use the working card types instead: send_simple_card, send_interactive_card, send_form_card
# setup_smart_card_tool(mcp)

# Register ModuleWrapper middleware with custom collection name to match unified_card_tool.py
logger.info("🔄 Initializing ModuleWrapper middleware...")
middleware = setup_module_wrapper_middleware(mcp, modules_to_wrap=["card_framework.v2"])
# Override the collection name to match what unified_card_tool.py expects
if "card_framework.v2" in middleware.wrappers:
    wrapper = middleware.wrappers["card_framework.v2"]
    wrapper.collection_name = "card_framework_components_fastembed"
    logger.info("✅ Updated ModuleWrapper to use FastEmbed collection: card_framework_components_fastembed")
logger.info("✅ ModuleWrapper middleware initialized")

# Register JWT-enhanced Chat tools (demonstration)
# setup_jwt_chat_tools(mcp)

# Register Google Chat App Development tools
setup_chat_app_tools(mcp)

# Register Google Chat App Development prompts
setup_chat_app_prompts(mcp)

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

# Setup OAuth callback handler
setup_oauth_callback_handler(mcp)

# Setup user and authentication resources
setup_user_resources(mcp)

# Setup tool output resources (cached outputs and Qdrant integration)
setup_tool_output_resources(mcp, qdrant_middleware)

# Setup service list resources (dynamic discovery of list-based tools)
setup_service_list_resources(mcp)

# Setup service recent resources (recent files from Drive-based services)
setup_service_recent_resources(mcp)

# Register server management tools
logger.info("🔧 Registering server management tools...")
setup_server_tools(mcp)
logger.info("✅ Server management tools registered")


# Setup Structured Response Middleware (transforms existing tools to provide structured JSON responses)
logger.info("🔄 Setting up Structured Response Middleware...")
structured_middleware = setup_structured_response_middleware(
    mcp,
    enable_auto_transform=True,  # Automatically transform eligible tools
    preserve_originals=True,     # Keep original tools alongside structured variants
    generate_report=True         # Log transformation report
)
logger.info("✅ Structured Response Middleware enabled - tools now have structured JSON variants!")

# Register Qdrant tools if middleware is available
try:
    if qdrant_middleware:
        logger.info("📊 Registering Qdrant search tools...")
        setup_enhanced_qdrant_tools(mcp, qdrant_middleware)
        logger.info("✅ Qdrant search and diagnostic tools registered")
except Exception as e:
    logger.warning(f"⚠️ Could not register Qdrant tools: {e}")



# Setup OAuth discovery endpoints for MCP Inspector
# Setup OAuth discovery endpoints for MCP Inspector (always available)
logger.info("🔍 Setting up OAuth discovery endpoints for MCP Inspector...")
try:
    # Test imports before setting up endpoints
    logger.info("🔍 DIAGNOSTIC: Testing OAuth endpoint dependencies...")
    try:
        from auth.dynamic_client_registration import handle_client_registration
        logger.info("✅ DIAGNOSTIC: dynamic_client_registration import successful")
    except Exception as import_error:
        logger.error(f"❌ DIAGNOSTIC: dynamic_client_registration import failed: {import_error}")
        raise
    
    try:
        from auth.oauth_proxy import oauth_proxy
        logger.info("✅ DIAGNOSTIC: oauth_proxy import successful")
    except Exception as import_error:
        logger.error(f"❌ DIAGNOSTIC: oauth_proxy import failed: {import_error}")
        raise
    
    try:
        from auth.scope_registry import ScopeRegistry
        logger.info("✅ DIAGNOSTIC: scope_registry import successful")
    except Exception as import_error:
        logger.error(f"❌ DIAGNOSTIC: scope_registry import failed: {import_error}")
        raise
    
    logger.info("🔍 DIAGNOSTIC: All dependencies imported successfully, setting up endpoints...")
    setup_oauth_endpoints_fastmcp(mcp)
    logger.info("✅ OAuth discovery endpoints configured via FastMCP custom routes")
    
    logger.info("🔍 MCP Inspector can discover OAuth at:")
    logger.info(f"  {settings.base_url}/.well-known/oauth-protected-resource/mcp")
    logger.info(f"  {settings.base_url}/.well-known/oauth-authorization-server")
    logger.info(f"  {settings.base_url}/oauth/register")
    
    # DIAGNOSTIC: Test endpoint registration by accessing MCP routes
    logger.info("🔍 DIAGNOSTIC: Checking FastMCP route registration...")
    if hasattr(mcp, '_app') and hasattr(mcp._app, 'routes'):
        oauth_routes = [str(route) for route in mcp._app.routes if 'oauth' in str(route)]
        logger.info(f"🔍 DIAGNOSTIC: Found {len(oauth_routes)} OAuth routes: {oauth_routes}")
    else:
        logger.warning("⚠️ DIAGNOSTIC: Cannot access MCP routes for verification")
    
except Exception as e:
    logger.error(f"❌ Failed to setup OAuth discovery endpoints: {e}", exc_info=True)

# NOW setup authentication AFTER custom routes are registered to avoid conflicts
logger.info("🔑 Setting up authentication...")
jwt_auth_provider = None

if use_google_oauth:
    # Setup real Google OAuth authentication
    jwt_auth_provider = setup_google_oauth_auth()
    logger.info("🔐 Google OAuth Bearer Token authentication enabled")
    logger.info("🌐 Using Google's JWKS endpoint: https://www.googleapis.com/oauth2/v3/certs")
    logger.info("🎯 OAuth issuer: https://accounts.google.com")
    
elif enable_jwt_auth:
    # Fallback to custom JWT for development/testing
    jwt_auth_provider = setup_jwt_auth()
    logger.info("🔐 Custom JWT Bearer Token authentication enabled (development mode)")
    
    # Generate test tokens for development
    logger.info("🎫 Generating test JWT tokens...")
    test_tokens = create_test_tokens()
    for email, token in test_tokens.items():
        logger.info(f"Test token for {email}: {token[:30]}...")
    
    # Save test tokens to file for tests to use
    import json
    test_tokens_file = "test_tokens.json"
    try:
        with open(test_tokens_file, "w") as f:
            json.dump(test_tokens, f, indent=2)
        logger.info(f"💾 Test tokens saved to {test_tokens_file}")
    except Exception as e:
        logger.error(f"❌ Failed to save test tokens: {e}")
else:
    logger.info("⚠️ Authentication DISABLED (for testing)")

# Apply the auth provider to the MCP instance
if jwt_auth_provider:
    mcp._auth = jwt_auth_provider
    logger.info("✅ Authentication provider applied to MCP instance")


def main():
    """Main entry point for the server."""
    logger.info(f"Starting {settings.server_name}")
    logger.info(f"Configuration: {settings.base_url}")
    logger.info(f"Protocol: {'HTTPS (SSL enabled)' if settings.enable_https else 'HTTP'}")
    logger.info(f"OAuth callback: {settings.dynamic_oauth_redirect_uri}")
    logger.info(f"Credentials directory: {settings.credentials_dir}")
    
    # Validate SSL configuration if HTTPS is enabled
    if settings.enable_https:
        try:
            settings.validate_ssl_config()
            logger.info(f"✅ SSL configuration validated")
            logger.info(f"SSL Certificate: {settings.ssl_cert_file}")
            logger.info(f"SSL Private Key: {settings.ssl_key_file}")
            if settings.ssl_ca_file:
                logger.info(f"SSL CA File: {settings.ssl_ca_file}")
        except ValueError as e:
            logger.error(f"❌ SSL configuration error: {e}")
            raise
    
    # Ensure credentials directory exists
    Path(settings.credentials_dir).mkdir(parents=True, exist_ok=True)
    
    try:
        # Prepare run arguments
        run_args = {
            "host": settings.server_host,
            "port": settings.server_port
        }
        
        # Configure transport and SSL based on HTTPS setting
        if settings.enable_https:
            ssl_config = settings.get_uvicorn_ssl_config()
            if ssl_config:
                run_args["transport"] = "http"  # FastMCP uses http transport with SSL via uvicorn_config
                run_args["uvicorn_config"] = ssl_config
                logger.info("🔒 Starting server with HTTPS/SSL support")
                logger.info(f"Transport: http (with SSL)")
                logger.info(f"SSL Certificate: {ssl_config['ssl_certfile']}")
                logger.info(f"SSL Private Key: {ssl_config['ssl_keyfile']}")
            else:
                logger.warning("⚠️ HTTPS enabled but SSL config unavailable, falling back to HTTP")
                run_args["transport"] = "http"
        else:
            run_args["transport"] = "http"
            logger.info("🌐 Starting server with HTTP support")
        
        # Run the server with appropriate transport and SSL configuration
        mcp.run(**run_args)
        
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()