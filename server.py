"""FastMCP2 Google Drive Upload Server.

A focused MCP server for uploading files to Google Drive with OAuth authentication.
"""

import argparse
import logging
import os
from pathlib import Path

from fastmcp import FastMCP
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
from gchat.jwt_chat_tools import setup_jwt_chat_tools
from gchat.chat_app_tools import setup_chat_app_tools
from gchat.chat_app_prompts import setup_chat_app_prompts
from prompts.gmail_prompts import setup_gmail_prompts
from prompts.gmail_showcase_prompts import setup_gmail_showcase_prompts
from gchat.unified_card_tool import setup_unified_card_tool
from gchat.smart_card_tool import setup_smart_card_tool
from adapters.module_wrapper_mcp import setup_module_wrapper_middleware
from sheets.sheets_tools import setup_sheets_tools
from middleware.qdrant_unified import QdrantUnifiedMiddleware, setup_enhanced_qdrant_tools
from resources.user_resources import setup_user_resources
from resources.tool_output_resources import setup_tool_output_resources
from tools.enhanced_tools import setup_enhanced_tools
from tunnel.tool_provider import setup_tunnel_tools

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Authentication setup - choose between Google OAuth and custom JWT
use_google_oauth = os.getenv("USE_GOOGLE_OAUTH", "true").lower() == "true"
enable_jwt_auth = os.getenv("ENABLE_JWT_AUTH", "false").lower() == "true"

# Credential storage configuration
storage_mode_str = settings.credential_storage_mode.upper()
try:
    credential_storage_mode = CredentialStorageMode[storage_mode_str]
    logger.info(f"🔐 Credential storage mode: {credential_storage_mode.value}")
except KeyError:
    logger.warning(f"⚠️ Invalid CREDENTIAL_STORAGE_MODE '{storage_mode_str}', defaulting to FILE_PLAINTEXT")
    credential_storage_mode = CredentialStorageMode.FILE_PLAINTEXT

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

# Create FastMCP2 instance WITHOUT authentication first (to avoid conflicts with OAuth discovery routes)
mcp = FastMCP(
    name=settings.server_name,
    version="1.0.0",
    auth=None,  # Will add auth later after custom OAuth routes are registered
    lifespan=lifespan_manager  # Add lifespan manager to properly initialize StreamableHTTPSessionManager
)

# Add authentication middleware with configured storage mode
auth_middleware = AuthMiddleware(storage_mode=credential_storage_mode)
mcp.add_middleware(auth_middleware)

# Register the AuthMiddleware instance in context for tool access
from auth.context import set_auth_middleware
set_auth_middleware(auth_middleware)

# Add MCP spec-compliant auth middleware for WWW-Authenticate headers
mcp.add_middleware(MCPAuthMiddleware())

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

# Register Smart Card Tool with content mapping integration
setup_smart_card_tool(mcp)

# Register ModuleWrapper middleware
logger.info("🔄 Initializing ModuleWrapper middleware...")
setup_module_wrapper_middleware(mcp, modules_to_wrap=["json", "card_framework.v2"])
logger.info("✅ ModuleWrapper middleware initialized")

# Register JWT-enhanced Chat tools (demonstration)
setup_jwt_chat_tools(mcp)

# Register Google Chat App Development tools
setup_chat_app_tools(mcp)

# Register Google Chat App Development prompts
setup_chat_app_prompts(mcp)

# Register Gmail prompts
setup_gmail_prompts(mcp)

# Register Gmail showcase prompts
setup_gmail_showcase_prompts(mcp)

# Register Google Sheets tools
setup_sheets_tools(mcp)

# Register Cloudflare Tunnel tools
setup_tunnel_tools(mcp)

# Setup OAuth callback handler
setup_oauth_callback_handler(mcp)

# Setup user and authentication resources
setup_user_resources(mcp)

# Setup tool output resources (cached outputs and Qdrant integration)
setup_tool_output_resources(mcp)

# Setup enhanced tools that use resource templating
setup_enhanced_tools(mcp)

# Register Qdrant tools if middleware is available
try:
    if qdrant_middleware:
        logger.info("📊 Registering Qdrant search tools...")
        setup_enhanced_qdrant_tools(mcp, qdrant_middleware)
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
            f"**🆕 Enhanced Tools (Resource Templating):**\n"
            f"- `list_my_drive_files` - List Drive files (no email param needed!)\n"
            f"- `search_my_gmail` - Search Gmail messages (auto-authenticated)\n"
            f"- `create_my_calendar_event` - Create calendar events (seamless auth)\n"
            f"- `get_my_auth_status` - Check authentication status\n"
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
            f"**Unified Card Tool (NEW!):**\n"
            f"- `send_dynamic_card` - Send any type of card using natural language description\n"
            f"- `list_available_card_components` - List available card components\n"
            f"- `get_card_component_info` - Get detailed information about card components\n"
            f"**Smart Card Tools (NEW!):**\n"
            f"- `send_smart_card` - Create and send a Google Chat card using natural language content description\n"
            f"- `create_card_from_template` - Create and send a card using a predefined template\n"
            f"- `preview_card_from_description` - Preview a card structure from natural language description without sending\n"
            f"- `optimize_card_layout` - Analyze and optimize a card layout based on engagement metrics\n"
            f"- `create_multi_modal_card` - Create and send a card with multi-modal content\n"
            f"**Qdrant Tools (Enhanced):**\n"
            f"- `search_tool_history` - Semantic search of historical tool responses\n"
            f"- `get_tool_analytics` - Get comprehensive tool usage analytics\n"
            f"- `get_response_details` - Get detailed response by ID\n"
            f"**Auth & System:**\n"
            f"- `start_google_auth` - Initiate OAuth authentication\n"
            f"- `check_drive_auth` - Check authentication status\n"
            f"- `manage_credentials` - Manage credential storage and security\n"
            f"- `health_check` - This health check\n\n"
            f"**🔐 Credential Security:**\n"
            f"- **Storage Mode:** {credential_storage_mode.value}\n"
            f"- **FILE_PLAINTEXT:** JSON files (backward compatible)\n"
            f"- **FILE_ENCRYPTED:** AES-256 with machine-specific keys\n"
            f"- **MEMORY_ONLY:** No disk storage, expires on restart\n"
            f"- **MEMORY_WITH_BACKUP:** Memory cache + encrypted backup\n\n"
            f"**🌟 Available Resources (NEW!):**\n"
            f"**User Resources:**\n"
            f"- `user://current/email` - Current user's email address\n"
            f"- `user://current/profile` - User profile with auth status\n"
            f"- `user://profile/{{email}}` - Profile for specific user\n"
            f"- `template://user_email` - Simple email template\n"
            f"**Auth Resources:**\n"
            f"- `auth://session/current` - Current session info\n"
            f"- `auth://sessions/list` - List active sessions\n"
            f"- `auth://credentials/{{email}}/status` - Credential status\n"
            f"**Service Resources:**\n"
            f"- `google://services/scopes/{{service}}` - Service scope info\n\n"
            f"**OAuth Callback URL:** {settings.dynamic_oauth_redirect_uri}"
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
        f"**`send_dynamic_card`** (NEW!)\n"
        f"- Send any type of card using natural language description with ModuleWrapper\n"
        f"- Args: user_google_email, space_id, card_description, card_params, thread_key, webhook_url\n"
        f"- Example: `send_dynamic_card('user@gmail.com', 'spaces/AAAA', 'simple card with title and text', {'title': 'Hello', 'text': 'World'})`\n\n"
        f"**Smart Card Tools (NEW!):**\n\n"
        f"**`send_smart_card`**\n"
        f"- Create and send a Google Chat card using natural language content description\n"
        f"- Args: user_google_email, space_id, content, style, auto_format, thread_key, webhook_url\n"
        f"- Example: `send_smart_card('user@gmail.com', 'spaces/AAAA', 'Title: Meeting Update | Text: Team standup at 2 PM')`\n\n"
        f"**`create_card_from_template`**\n"
        f"- Create and send a card using a predefined template with content substitution\n"
        f"- Args: template_name, content, user_google_email, space_id, thread_key, webhook_url\n"
        f"- Example: `create_card_from_template('status_report', {'title': 'Project Status', 'status': 'On Track'}, 'user@gmail.com', 'spaces/AAAA')`\n\n"
        f"**`preview_card_from_description`**\n"
        f"- Preview a card structure from natural language description without sending\n"
        f"- Args: description, auto_format\n"
        f"- Example: `preview_card_from_description('A card with a title saying Welcome and a button to Get Started')`\n\n"
        f"**`optimize_card_layout`**\n"
        f"- Analyze and optimize a card layout based on engagement metrics\n"
        f"- Args: card_id\n"
        f"- Example: `optimize_card_layout('card-123456')`\n\n"
        f"**`create_multi_modal_card`**\n"
        f"- Create and send a card with multi-modal content (text, data, images, video)\n"
        f"- Args: user_google_email, space_id, content, data, images, video_url, thread_key, webhook_url\n"
        f"- Example: `create_multi_modal_card('user@gmail.com', 'spaces/AAAA', 'Monthly Sales', data={'labels': ['Jan', 'Feb'], 'values': [100, 150]})`\n\n"
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
        f"- OAuth Callback: {settings.dynamic_oauth_redirect_uri}\n"
        f"- Credentials Directory: {settings.credentials_dir}"
    )


# Add credential management tool
@mcp.tool
async def manage_credentials(
    email: str,
    action: str,
    new_storage_mode: str = None
) -> str:
    """
    Manage credential storage and security settings.
    
    Args:
        email: User's Google email address
        action: Action to perform ('status', 'migrate', 'summary', 'delete')
        new_storage_mode: Target storage mode for migration ('PLAINTEXT', 'ENCRYPTED', 'MEMORY_ONLY', 'HYBRID')
    
    Returns:
        str: Result of the credential management operation
    """
    try:
        from auth.context import get_auth_middleware
        
        # Get the AuthMiddleware instance
        auth_middleware = get_auth_middleware()
        if not auth_middleware:
            return "❌ AuthMiddleware not available"
        
        if action == "status":
            # Get credential status
            summary = await auth_middleware.get_credential_summary(email)
            if summary:
                return (
                    f"📊 **Credential Status for {email}**\n\n"
                    f"**Storage Mode:** {summary['storage_mode']}\n"
                    f"**File Path:** {summary['file_path']}\n"
                    f"**File Exists:** {'✅' if summary['file_exists'] else '❌'}\n"
                    f"**In Memory:** {'✅' if summary['in_memory'] else '❌'}\n"
                    f"**Is Encrypted:** {'✅' if summary['is_encrypted'] else '❌'}\n"
                    f"**Last Modified:** {summary.get('last_modified', 'Unknown')}\n"
                    f"**File Size:** {summary.get('file_size', 'Unknown')} bytes"
                )
            else:
                return f"❌ No credentials found for {email}"
        
        elif action == "migrate":
            if not new_storage_mode:
                return "❌ new_storage_mode is required for migration"
            
            try:
                target_mode = CredentialStorageMode[new_storage_mode.upper()]
            except KeyError:
                return f"❌ Invalid storage mode '{new_storage_mode}'. Valid options: FILE_PLAINTEXT, FILE_ENCRYPTED, MEMORY_ONLY, MEMORY_WITH_BACKUP"
            
            # Perform migration
            success = await auth_middleware.migrate_credentials(email, target_mode)
            if success:
                return f"✅ Successfully migrated credentials for {email} to {target_mode.value} mode"
            else:
                return f"❌ Failed to migrate credentials for {email} to {target_mode.value} mode"
        
        elif action == "summary":
            # Get summary of all credentials
            # This would require implementing a method to list all credential files
            return f"📋 **Credential Summary**\n\nCurrent storage mode: {auth_middleware.storage_mode.value}\n\nUse 'status' action with specific email for detailed information."
        
        elif action == "delete":
            # Delete credentials (this would need to be implemented in AuthMiddleware)
            return f"⚠️ Credential deletion not yet implemented. Please manually delete credential files if needed."
        
        else:
            return f"❌ Invalid action '{action}'. Valid actions: status, migrate, summary, delete"
    
    except Exception as e:
        logger.error(f"Credential management error: {e}", exc_info=True)
        return f"❌ Credential management failed: {e}"

# Setup OAuth discovery endpoints for MCP Inspector
# Setup OAuth discovery endpoints for MCP Inspector (always available)
logger.info("🔍 Setting up OAuth discovery endpoints for MCP Inspector...")
try:
    setup_oauth_endpoints_fastmcp(mcp)
    logger.info("✅ OAuth discovery endpoints configured via FastMCP custom routes")
    
    logger.info("🔍 MCP Inspector can discover OAuth at:")
    logger.info(f"  {settings.base_url}/.well-known/oauth-protected-resource")
    logger.info(f"  {settings.base_url}/.well-known/oauth-authorization-server")
    logger.info(f"  {settings.base_url}/oauth/register")
except Exception as e:
    logger.error(f"❌ Failed to setup OAuth discovery endpoints: {e}")

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