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
from drive.drive_tools import setup_drive_comprehensive_tools
from gmail.gmail_tools import setup_gmail_tools
from docs.docs_tools import setup_docs_tools
from forms.forms_tools import setup_forms_tools
from slides.slides_tools import setup_slides_tools
from gcalendar.calendar_tools import setup_calendar_tools
from gchat.chat_tools import setup_chat_tools
from sheets.sheets_tools import setup_sheets_tools
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

# Register comprehensive Drive tools (search, list, get content, create)
setup_drive_comprehensive_tools(mcp)

# Register Gmail tools
setup_gmail_tools(mcp)

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

# Register Google Sheets tools
setup_sheets_tools(mcp)

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
            f"- `search_drive_files` - Search for files and folders in Drive\n"
            f"- `get_drive_file_content` - Retrieve file content from Drive\n"
            f"- `list_drive_items` - List files and folders in a directory\n"
            f"- `create_drive_file` - Create new files directly in Drive\n"
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
            f"**Docs Tools:**\n"
            f"- `search_docs` - Search for Google Docs by name\n"
            f"- `get_doc_content` - Get content of Google Doc or Drive file\n"
            f"- `list_docs_in_folder` - List Google Docs in a folder\n"
            f"- `create_doc` - Create a new Google Doc\n"
            f"**Forms Tools:**\n"
            f"- `create_form` - Create a new Google Form\n"
            f"- `add_questions_to_form` - Add questions to an existing form\n"
            f"- `get_form` - Get form details including questions\n"
            f"- `set_form_publish_state` - Update form publish state\n"
            f"- `publish_form_publicly` - Make form publicly accessible\n"
            f"- `get_form_response` - Get a single form response\n"
            f"- `list_form_responses` - List form responses\n"
            f"- `update_form_questions` - Update existing form questions\n"
            f"**Slides Tools:**\n"
            f"- `create_presentation` - Create new presentations with slides\n"
            f"- `get_presentation_info` - Get presentation details and metadata\n"
            f"- `add_slide` - Add new slides to presentations\n"
            f"- `update_slide_content` - Update slide content with batch operations\n"
            f"- `export_presentation` - Export presentations to various formats\n"
            f"**Calendar Tools:**\n"
            f"- `list_calendars` - List accessible calendars\n"
            f"- `get_events` - Get events with time range support\n"
            f"- `create_event` - Create events with attachments and attendees\n"
            f"- `modify_event` - Update existing events\n"
            f"- `delete_event` - Remove events from calendar\n"
            f"- `get_event` - Get single event details\n"
            f"**Chat Tools:**\n"
            f"- `list_spaces` - List Google Chat spaces and direct messages\n"
            f"- `get_messages` - Retrieve messages from a Chat space\n"
            f"- `send_message` - Send messages to Chat spaces\n"
            f"- `search_messages` - Search messages across Chat spaces\n"
            f"- `send_card_message` - Send rich card messages using Card Framework\n"
            f"- `send_simple_card` - Send simple cards with title, text, and image\n"
            f"- `send_interactive_card` - Send cards with interactive buttons\n"
            f"- `send_form_card` - Send form cards with input fields\n"
            f"- `send_rich_card` - Send advanced cards with complex layouts\n"
            f"- `get_card_framework_status` - Check Card Framework availability\n"
            f"- `get_adapter_system_status` - Check adapter system integration\n"
            f"- `list_available_card_types` - List supported card types\n"
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
        f"**`search_drive_files`**\n"
        f"- Search for files and folders using Google Drive query syntax\n"
        f"- Args: user_google_email, query, page_size (optional)\n"
        f"- Example: `search_drive_files('user@gmail.com', 'name contains \"report\"')`\n\n"
        f"**`get_drive_file_content`**\n"
        f"- Retrieve content of any Drive file (Docs, Sheets, Office files, etc.)\n"
        f"- Args: user_google_email, file_id\n"
        f"- Example: `get_drive_file_content('user@gmail.com', '1234fileId')`\n\n"
        f"**`list_drive_items`**\n"
        f"- List files and folders in a Drive directory\n"
        f"- Args: user_google_email, folder_id (default: 'root'), page_size (optional)\n"
        f"- Example: `list_drive_items('user@gmail.com', 'root')`\n\n"
        f"**`create_drive_file`**\n"
        f"- Create new files directly in Drive from content or URL\n"
        f"- Args: user_google_email, file_name, content/fileUrl, folder_id (optional)\n"
        f"- Example: `create_drive_file('user@gmail.com', 'notes.txt', content='My notes')`\n\n"
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
        f"**📄 Docs Tools:**\n\n"
        f"**`search_docs`**\n"
        f"- Search for Google Docs by name\n"
        f"- Args: user_google_email, query, page_size (optional)\n"
        f"- Example: `search_docs('user@gmail.com', 'meeting notes')`\n\n"
        f"**`get_doc_content`**\n"
        f"- Get content of a Google Doc or Drive file (e.g., .docx)\n"
        f"- Args: user_google_email, document_id\n"
        f"- Example: `get_doc_content('user@gmail.com', '1234docId')`\n\n"
        f"**`list_docs_in_folder`**\n"
        f"- List Google Docs within a specific folder\n"
        f"- Args: user_google_email, folder_id (default: 'root'), page_size (optional)\n"
        f"- Example: `list_docs_in_folder('user@gmail.com', 'folderId')`\n\n"
        f"**`create_doc`**\n"
        f"- Create a new Google Doc with optional initial content\n"
        f"- Args: user_google_email, title, content (optional)\n"
        f"- Example: `create_doc('user@gmail.com', 'Meeting Notes', 'Agenda: ...')`\n\n"
        f"**📋 Forms Tools:**\n\n"
        f"**`create_form`**\n"
        f"- Create a new Google Form with title and description\n"
        f"- Args: user_google_email, title, description (optional), document_title (optional)\n"
        f"- Example: `create_form('user@gmail.com', 'Customer Survey')`\n\n"
        f"**`add_questions_to_form`**\n"
        f"- Add questions to an existing form\n"
        f"- Args: user_google_email, form_id, questions, insert_at_index (optional)\n"
        f"- Example: `add_questions_to_form('user@gmail.com', 'formId', [{{'type': 'TEXT_QUESTION', 'title': 'Your name?'}}])`\n\n"
        f"**`get_form`**\n"
        f"- Get form details including questions and URLs\n"
        f"- Args: user_google_email, form_id\n"
        f"- Example: `get_form('user@gmail.com', 'formId')`\n\n"
        f"**`list_form_responses`**\n"
        f"- List responses to a form with pagination\n"
        f"- Args: user_google_email, form_id, page_size (optional), page_token (optional)\n"
        f"- Example: `list_form_responses('user@gmail.com', 'formId')`\n\n"
        f"**📊 Slides Tools:**\n\n"
        f"**`create_presentation`**\n"
        f"- Create new presentations with slides\n"
        f"- Args: user_google_email, title, slide_layouts (optional)\n"
        f"- Example: `create_presentation('user@gmail.com', 'Project Update')`\n\n"
        f"**`export_presentation`**\n"
        f"- Export presentations to various formats (PDF, PPTX, etc.)\n"
        f"- Args: user_google_email, presentation_id, export_format\n"
        f"- Example: `export_presentation('user@gmail.com', 'presentationId', 'PDF')`\n\n"
        f"**📅 Calendar Tools:**\n\n"
        f"**`list_calendars`**\n"
        f"- List accessible calendars with primary indicator\n"
        f"- Args: user_google_email\n"
        f"- Example: `list_calendars('user@gmail.com')`\n\n"
        f"**`create_event`**\n"
        f"- Create events with attachments and attendees\n"
        f"- Args: user_google_email, calendar_id, summary, start_time, end_time, attendees (optional)\n"
        f"- Example: `create_event('user@gmail.com', 'primary', 'Meeting', '2024-01-01T10:00:00Z', '2024-01-01T11:00:00Z')`\n\n"
        f"**💬 Chat Tools:**\n\n"
        f"**`list_spaces`**\n"
        f"- List Google Chat spaces and direct messages accessible to the user\n"
        f"- Args: user_google_email, page_size (optional), space_type (optional)\n"
        f"- Example: `list_spaces('user@gmail.com', space_type='room')`\n\n"
        f"**`get_messages`**\n"
        f"- Retrieve messages from a Google Chat space\n"
        f"- Args: user_google_email, space_id, page_size (optional), order_by (optional)\n"
        f"- Example: `get_messages('user@gmail.com', 'spaces/AAAA')`\n\n"
        f"**`send_message`**\n"
        f"- Send a text message to a Google Chat space\n"
        f"- Args: user_google_email, space_id, message_text, thread_key (optional)\n"
        f"- Example: `send_message('user@gmail.com', 'spaces/AAAA', 'Hello team!')`\n\n"
        f"**`send_rich_card`**\n"
        f"- Send rich cards with advanced formatting (supports webhook delivery)\n"
        f"- Args: user_google_email, space_id, title, subtitle, image_url, sections, webhook_url\n"
        f"- Example: `send_rich_card('user@gmail.com', 'spaces/AAAA', 'Status Update', webhook_url='https://...')`\n\n"
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
        f"**Gmail:** Search, read, send, draft, reply, labels, threads, batch operations\n"
        f"**Docs:** Search, read native Google Docs and Office files, create docs, list in folders\n"
        f"**Forms:** Create forms, add questions (all types), manage responses, update questions\n\n"
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