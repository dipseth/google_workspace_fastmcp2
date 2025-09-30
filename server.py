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
from sheets.sheets_tools import setup_sheets_tools
from photos.photos_tools import setup_photos_tools
from photos.advanced_tools import setup_advanced_photos_tools
from middleware.qdrant_middleware import QdrantUnifiedMiddleware, setup_enhanced_qdrant_tools, setup_qdrant_resources
# from middleware.template_middleware import setup_template_middleware
from middleware.template_middleware import setup_enhanced_template_middleware as setup_template_middleware
from middleware.sampling_middleware import setup_enhanced_sampling_middleware, EnhancementLevel
from middleware.tag_based_resource_middleware import TagBasedResourceMiddleware
from resources.user_resources import setup_user_resources
from resources.tool_output_resources import setup_tool_output_resources
from resources.service_list_resources import setup_service_list_resources
from resources.service_recent_resources import setup_service_recent_resources
from resources.template_resources import register_template_resources
from tools.server_tools import setup_server_tools
from tools.template_macro_tools import setup_template_macro_tools

# Authentication setup - choose between Google OAuth and custom JWT
use_google_oauth = os.getenv("USE_GOOGLE_OAUTH", "true").lower() == "true"
enable_jwt_auth = os.getenv("ENABLE_JWT_AUTH", "false").lower() == "true"

# Cloud deployment detection
is_cloud_deployment = settings.is_cloud_deployment
if is_cloud_deployment:
    logger.info("☁️ FastMCP Cloud deployment detected")
    logger.info(f"☁️ Using cloud-optimized credential storage: {settings.credential_storage_mode}")
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

# Credential storage configuration
storage_mode_str = settings.credential_storage_mode.upper()
try:
    credential_storage_mode = CredentialStorageMode[storage_mode_str]
    logger.info(f"🔐 Credential storage mode: {credential_storage_mode.value}")
except KeyError:
    logger.warning(f"⚠️ Invalid CREDENTIAL_STORAGE_MODE '{storage_mode_str}', defaulting to FILE_ENCRYPTED")
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
    version="1.0.0",
    auth=None  # No GoogleProvider - use legacy OAuth system
)

logger.info("🔐 FastMCP running with legacy OAuth system")
logger.info("  All existing OAuth endpoints active")
logger.info("  MCP Inspector discovery available")

from auth.middleware import create_enhanced_auth_middleware
auth_middleware = create_enhanced_auth_middleware(
    storage_mode=credential_storage_mode,
    google_provider=None  # No GoogleProvider - use legacy system
)
# Enable service selection for existing OAuth system
logger.info("🔧 Configuring service selection for legacy OAuth system")
auth_middleware.enable_service_selection(enabled=True)
logger.info("✅ Service selection interface enabled for OAuth flows")

mcp.add_middleware(auth_middleware)

# Register the AuthMiddleware instance in context for tool access
from auth.context import set_auth_middleware
set_auth_middleware(auth_middleware)

# 2. MCP spec-compliant auth middleware for WWW-Authenticate headers
mcp.add_middleware(MCPAuthMiddleware())

# Setup Enhanced Template Parameter Middleware with full Jinja2 support (MUST be before tools are registered)
logger.info("🎭 Setting up Enhanced Template Parameter Middleware with full modular architecture...")
template_middleware = setup_template_middleware(
    mcp,
    enable_debug=True,  # Force enable for testing
    enable_caching=True,
    cache_ttl_seconds=300
)
logger.info("✅ Enhanced Template Parameter Middleware enabled - modular architecture with 12 focused components active")

# Setup Enhanced Sampling Middleware with tag-based elicitation
logger.info("🎯 Setting up Enhanced Sampling Middleware...")
sampling_middleware = setup_enhanced_sampling_middleware(
    mcp,
    enable_debug=True,  # Enable for testing and development
    target_tags=["gmail", "compose", "elicitation"],  # Tools with these tags get enhanced sampling
    qdrant_middleware=None,  # Will be set after Qdrant middleware is initialized
    template_middleware=template_middleware,
    default_enhancement_level=EnhancementLevel.CONTEXTUAL
)
logger.info("✅ Enhanced Sampling Middleware enabled - tools with target tags get enhanced context")

# 5. Initialize Qdrant unified middleware (completely non-blocking)
logger.info("🔄 Initializing Qdrant unified middleware...")
qdrant_middleware = QdrantUnifiedMiddleware(
    qdrant_host=settings.qdrant_host,
    qdrant_port=settings.qdrant_port,
    qdrant_api_key=settings.qdrant_api_key,
    qdrant_url=settings.qdrant_url,
    collection_name="mcp_tool_responses",
    auto_discovery=True,  # Enable auto-discovery to find available Qdrant instances
    ports=[settings.qdrant_port, 6333, 6335, 6334]  # Try configured port first, then fallback
)
mcp.add_middleware(qdrant_middleware)
logger.info("✅ Qdrant unified middleware enabled - configured for cloud instance")
logger.info(f"🔧 Qdrant URL: {settings.qdrant_url}")
logger.info(f"🔧 API Key configured: {bool(settings.qdrant_api_key)}")

# Update sampling middleware with Qdrant integration now that it's initialized
if hasattr(sampling_middleware, 'qdrant_middleware'):
    sampling_middleware.qdrant_middleware = qdrant_middleware
    logger.info("🔗 Enhanced Sampling Middleware connected to Qdrant for historical context")

# 6. Add TagBasedResourceMiddleware for service list resource handling (LAST)
logger.info("🏷️ Setting up TagBasedResourceMiddleware for service:// resource handling...")
tag_based_middleware = TagBasedResourceMiddleware(enable_debug_logging=True)
mcp.add_middleware(tag_based_middleware)
logger.info("✅ TagBasedResourceMiddleware enabled - service:// URIs will be handled via tag-based tool discovery")

# Register drive upload tools
setup_drive_tools(mcp)

# Register comprehensive Drive tools (search, list, get content, create)
setup_drive_comprehensive_tools(mcp)

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

# Register Unified Card Tool with ModuleWrapper integration
setup_unified_card_tool(mcp)

# DEPRECATED: Smart Card Tool removed due to formatting issues with Google Chat Cards v2 API
# The send_smart_card function had structural problems that prevented proper card rendering
# Use the working card types instead: send_simple_card, send_interactive_card, send_form_card
# setup_smart_card_tool(mcp)

# Register ModuleWrapper middleware with custom collection name to match unified_card_tool.py
logger.info("🔄 Initializing ModuleWrapper middleware...")
middleware = setup_module_wrapper_middleware(mcp, modules_to_wrap=["card_framework.v2"], tool_pushdown=True)
# Override the collection name to match what unified_card_tool.py expects
if "card_framework.v2" in middleware.wrappers:
    wrapper = middleware.wrappers["card_framework.v2"]
    wrapper.collection_name = "card_framework_components_fastembed"
    logger.info("✅ Updated ModuleWrapper to use FastEmbed collection: card_framework_components_fastembed")
logger.info("✅ ModuleWrapper middleware initialized with tools enabled")

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
logger.info("✅ Service list resources registered - URIs handled by TagBasedResourceMiddleware")

# Setup service recent resources (recent files from Drive-based services)
setup_service_recent_resources(mcp)

# Setup template macro resources (discovery and usage examples)
logger.info("📚 Registering template macro resources...")
register_template_resources(mcp)
logger.info("✅ Template macro resources registered - URIs handled by EnhancedTemplateMiddleware")

# Register server management tools
logger.info("🔧 Registering server management tools...")
setup_server_tools(mcp)
logger.info("✅ Server management tools registered")

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


# Setup OAuth endpoints (now using legacy system)
logger.info("🔍 Setting up OAuth discovery endpoints...")
try:
    setup_oauth_endpoints_fastmcp(mcp)
    logger.info("✅ OAuth discovery endpoints configured")
    logger.info(f"  Discovery: {settings.base_url}/.well-known/oauth-protected-resource/mcp")
    logger.info(f"  Authorization: {settings.base_url}/.well-known/oauth-authorization-server")
    logger.info(f"  Registration: {settings.base_url}/oauth/register")
    logger.info(f"  Callback: {settings.base_url}/oauth2callback")
    
except Exception as e:
    logger.error(f"❌ Failed to setup OAuth endpoints: {e}", exc_info=True)

# Legacy Authentication System Setup
if use_google_oauth:
    # Setup real Google OAuth authentication
    jwt_auth_provider = setup_google_oauth_auth()
    mcp._auth = jwt_auth_provider
    logger.info("🔐 Google OAuth Bearer Token authentication enabled")
    logger.info("🌐 Using Google's JWKS endpoint: https://www.googleapis.com/oauth2/v3/certs")
    logger.info("🎯 OAuth issuer: https://accounts.google.com")
    
elif enable_jwt_auth:
    # Fallback to custom JWT for development/testing
    jwt_auth_provider = setup_jwt_auth()
    mcp._auth = jwt_auth_provider
    logger.info("🔐 Custom JWT Bearer Token authentication enabled (development mode)")
    
else:
    logger.info("⚠️ Authentication DISABLED (for testing)")


def main():
    """Main entry point for the server."""
    logger.info(f"Starting {settings.server_name}")
    logger.info(f"Configuration: {settings.base_url}")
    logger.info(f"Protocol: {'HTTPS (SSL enabled)' if settings.enable_https else 'HTTP'}")
    logger.info(f"OAuth callback: {settings.dynamic_oauth_redirect_uri}")
    logger.info(f"Credentials directory: {settings.credentials_dir}")
    
    # Validate SSL configuration if HTTPS is enabled (skip for cloud deployment)
    if settings.enable_https and not settings.is_cloud_deployment:
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
    elif settings.is_cloud_deployment:
        logger.info("☁️ Skipping SSL validation - handled by FastMCP Cloud")
    
    # Ensure credentials directory exists
    Path(settings.credentials_dir).mkdir(parents=True, exist_ok=True)
    
    try:
        # Prepare run arguments
        run_args = {
            "host": settings.server_host,
            "port": settings.server_port
        }
        
        # Configure transport and SSL based on HTTPS setting and cloud deployment
        if settings.is_cloud_deployment:
            # FastMCP Cloud handles SSL automatically
            run_args["transport"] = "http"
            logger.info("☁️ Cloud deployment - FastMCP Cloud handles HTTPS/SSL automatically")
        elif settings.enable_https:
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
