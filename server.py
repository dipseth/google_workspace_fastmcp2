"""FastMCP2 Google Drive Upload Server.

A focused MCP server for uploading files to Google Drive with OAuth authentication.
"""

import logging
import os
from pathlib import Path

from fastmcp import FastMCP
from config.settings import settings
from auth.middleware import AuthMiddleware
from drive.upload_tools import setup_drive_tools, setup_oauth_callback_handler
from gmail.gmail_tools import setup_gmail_tools
from middleware.qdrant_wrapper import QdrantMiddlewareWrapper

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastMCP2 instance
mcp = FastMCP(
    name=settings.server_name,
    version="1.0.0"
)

# Add authentication middleware
mcp.add_middleware(AuthMiddleware())

# Initialize Qdrant middleware wrapper (completely non-blocking)
logger.info("🔄 Initializing Qdrant middleware wrapper...")
qdrant_wrapper = QdrantMiddlewareWrapper()
mcp.add_middleware(qdrant_wrapper)
logger.info("✅ Qdrant middleware wrapper enabled - will initialize on first use")

# Register drive upload tools
setup_drive_tools(mcp)

# Register Gmail tools
setup_gmail_tools(mcp)

# Setup OAuth callback handler
setup_oauth_callback_handler(mcp)

# Register Qdrant tools if middleware is available
try:
    if qdrant_wrapper and hasattr(qdrant_wrapper, '_inner_middleware'):
        logger.info("📊 Registering Qdrant search tools...")
        from middleware.qdrant_enhanced import setup_enhanced_qdrant_tools
        
        # Create a proxy object that will use the wrapper's inner middleware
        class QdrantProxy:
            def __init__(self, wrapper):
                self.wrapper = wrapper
                
            async def search_responses(self, *args, **kwargs):
                if self.wrapper._inner_middleware:
                    return await self.wrapper._inner_middleware.search_responses(*args, **kwargs)
                return []
            
            async def get_analytics(self, *args, **kwargs):
                if self.wrapper._inner_middleware:
                    return await self.wrapper._inner_middleware.get_analytics(*args, **kwargs)
                return {"error": "Qdrant not initialized"}
            
            async def get_response_by_id(self, *args, **kwargs):
                if self.wrapper._inner_middleware:
                    return await self.wrapper._inner_middleware.get_response_by_id(*args, **kwargs)
                return None
        
        # Use the proxy for tools
        qdrant_proxy = QdrantProxy(qdrant_wrapper)
        setup_enhanced_qdrant_tools(mcp, qdrant_proxy)
        logger.info("✅ Qdrant search tools registered")
except Exception as e:
    logger.warning(f"⚠️ Could not register Qdrant tools: {e}")

# Add health check tool
@mcp.tool
async def health_check() -> str:
    """
    Check server health and configuration.
    
    Returns:
        str: Server health status
    """
    try:
        # Check credentials directory
        creds_dir = Path(settings.credentials_dir)
        creds_accessible = creds_dir.exists() and os.access(creds_dir, os.R_OK | os.W_OK)
        
        # Check OAuth configuration
        oauth_configured = bool(settings.google_client_id and settings.google_client_secret)
        
        # Basic session info
        from auth.context import get_session_count
        active_sessions = get_session_count()
        
        status = "✅ Healthy" if (creds_accessible and oauth_configured) else "⚠️ Configuration Issues"
        
        return (
            f"🏥 **Google Drive Upload Server Health Check**\n\n"
            f"**Status:** {status}\n"
            f"**Server:** {settings.server_name} v1.0.0\n"
            f"**Host:** {settings.server_host}:{settings.server_port}\n"
            f"**OAuth Configured:** {'✅' if oauth_configured else '❌'}\n"
            f"**Credentials Directory:** {'✅' if creds_accessible else '❌'} ({settings.credentials_dir})\n"
            f"**Active Sessions:** {active_sessions}\n"
            f"**Log Level:** {settings.log_level}\n\n"
            f"**Available Tools:**\n"
            f"**Drive Tools:**\n"
            f"- `upload_file_to_drive` - Upload local files to Google Drive\n"
            f"**Gmail Tools:**\n"
            f"- `search_gmail_messages` - Search Gmail messages\n"
            f"- `get_gmail_message_content` - Get single message content\n"
            f"- `get_gmail_messages_content_batch` - Get multiple messages content\n"
            f"- `send_gmail_message` - Send email via Gmail\n"
            f"- `draft_gmail_message` - Create email draft\n"
            f"- `get_gmail_thread_content` - Get conversation thread\n"
            f"- `list_gmail_labels` - List Gmail labels\n"
            f"- `manage_gmail_label` - Create/update/delete labels\n"
            f"- `modify_gmail_message_labels` - Add/remove message labels\n"
            f"- `reply_to_gmail_message` - Reply to messages\n"
            f"- `draft_gmail_reply` - Draft reply messages\n"
            f"**Qdrant Tools (Enhanced):**\n"
            f"- `search_tool_history` - Semantic search of historical tool responses\n"
            f"- `get_tool_analytics` - Get comprehensive tool usage analytics\n"
            f"- `get_response_details` - Get detailed response by ID\n"
            f"**Auth & System:**\n"
            f"- `start_google_auth` - Initiate OAuth authentication\n"
            f"- `check_drive_auth` - Check authentication status\n"
            f"- `health_check` - This health check\n\n"
            f"**OAuth Callback URL:** {settings.oauth_redirect_uri}"
        )
        
    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        return f"❌ Health check failed: {e}"


# Add server info tool
@mcp.tool
async def server_info() -> str:
    """
    Get detailed server information and usage instructions.
    
    Returns:
        str: Server information and usage guide
    """
    return (
        f"📁 **FastMCP2 Google Drive & Gmail Server**\n\n"
        f"**Version:** 1.0.0\n"
        f"**Purpose:** Comprehensive Google Drive and Gmail integration with middleware-based service injection\n\n"
        f"**🚀 Quick Start:**\n"
        f"1. Run `start_google_auth` with your Google email\n"
        f"2. Complete OAuth flow in browser\n"
        f"3. Use Drive and Gmail tools seamlessly\n\n"
        f"**📁 Drive Tools:**\n\n"
        f"**`upload_file_to_drive`**\n"
        f"- Upload local files to Google Drive\n"
        f"- Args: user_google_email, filepath, folder_id (optional), filename (optional)\n"
        f"- Example: `upload_file_to_drive('user@gmail.com', '/path/to/file.pdf')`\n\n"
        f"**📧 Gmail Tools:**\n\n"
        f"**`search_gmail_messages`**\n"
        f"- Search Gmail messages using Gmail query syntax\n"
        f"- Args: user_google_email, query, page_size (optional)\n"
        f"- Example: `search_gmail_messages('user@gmail.com', 'from:sender@example.com')`\n\n"
        f"**`get_gmail_message_content`**\n"
        f"- Get full content of a specific message\n"
        f"- Args: user_google_email, message_id\n"
        f"- Example: `get_gmail_message_content('user@gmail.com', '12345')`\n\n"
        f"**`send_gmail_message`**\n"
        f"- Send email via Gmail\n"
        f"- Args: user_google_email, to, subject, body\n"
        f"- Example: `send_gmail_message('user@gmail.com', 'friend@example.com', 'Hello', 'Message body')`\n\n"
        f"**`reply_to_gmail_message`**\n"
        f"- Reply to a specific message with proper threading\n"
        f"- Args: user_google_email, message_id, body\n"
        f"- Example: `reply_to_gmail_message('user@gmail.com', '12345', 'Thanks!')`\n\n"
        f"**🔐 Authentication:**\n"
        f"- Uses OAuth 2.0 with PKCE for security\n"
        f"- Multi-user support with session management\n"
        f"- Middleware-based service injection (no decorators!)\n"
        f"- Automatic token refresh and error handling\n"
        f"- Credentials stored securely per user\n\n"
        f"**✨ New Architecture Features:**\n"
        f"- Universal Google service support (Drive, Gmail, Calendar, etc.)\n"
        f"- Smart defaults for service configurations\n"
        f"- Automatic service caching and session management\n"
        f"- Clean separation of concerns\n"
        f"- Error handling with user-friendly messages\n\n"
        f"**🎯 Enhanced Qdrant Features:**\n"
        f"- Auto-discovery of Qdrant instances (ports 6333-6337)\n"
        f"- Gzip compression for large payloads\n"
        f"- Natural language semantic search\n"
        f"- Structured payload types (API, FILE, ERROR, DATA)\n"
        f"- Advanced analytics with performance metrics\n"
        f"- Intelligent response summarization\n\n"
        f"**📝 Supported Features:**\n"
        f"**Drive:** Upload to folders, custom filenames, all file types, progress tracking\n"
        f"**Gmail:** Search, read, send, draft, reply, labels, threads, batch operations\n\n"
        f"**Server Configuration:**\n"
        f"- Host: {settings.server_host}:{settings.server_port}\n"
        f"- OAuth Callback: {settings.oauth_redirect_uri}\n"
        f"- Credentials Directory: {settings.credentials_dir}"
    )


def main():
    """Main entry point for the server."""
    logger.info(f"Starting {settings.server_name}")
    logger.info(f"Configuration: {settings.server_host}:{settings.server_port}")
    logger.info(f"OAuth callback: {settings.oauth_redirect_uri}")
    logger.info(f"Credentials directory: {settings.credentials_dir}")
    
    # Ensure credentials directory exists
    Path(settings.credentials_dir).mkdir(parents=True, exist_ok=True)
    
    try:
        # Run the server in HTTP mode for OAuth callbacks
        mcp.run(
            transport="http",
            host=settings.server_host,
            port=settings.server_port
        )
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()