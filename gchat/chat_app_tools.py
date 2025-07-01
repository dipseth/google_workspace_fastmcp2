"""
Google Chat App Development Tools

This module provides comprehensive tools for creating, configuring, and managing Google Chat apps.
Uses service account authentication for app-level operations.
"""
import logging
import json
import os
from typing import Optional, Dict, Any, List
from datetime import datetime

from fastmcp import FastMCP
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.errors import HttpError

from config.settings import Settings

logger = logging.getLogger(__name__)

# Load settings
settings = Settings()

# Import compatibility shim for consolidated scope management
from auth.compatibility_shim import CompatibilityShim

def _get_chat_app_scopes():
    """Get Google Chat API scopes for app development using compatibility shim."""
    try:
        shim = CompatibilityShim()
        return shim.get_legacy_chat_app_scopes()
    except Exception as e:
        # Fallback to hardcoded scopes if shim fails
        return [
            'https://www.googleapis.com/auth/chat.bot',
            'https://www.googleapis.com/auth/chat.messages',
            'https://www.googleapis.com/auth/chat.spaces',
            'https://www.googleapis.com/auth/chat.apps',
            'https://www.googleapis.com/auth/cloud-platform'
        ]

# Google Chat API scopes for app development
CHAT_APP_SCOPES = _get_chat_app_scopes()

class GoogleChatAppManager:
    """Manager for Google Chat app operations using service account."""
    
    def __init__(self):
        self.service_account_file = settings.chat_service_account_file
        self.credentials = None
        self.chat_service = None
        self.project_id = None
        
    async def initialize(self):
        """Initialize service account credentials and Chat service."""
        try:
            if not self.service_account_file:
                raise ValueError(
                    "Service account file not configured. Please set CHAT_SERVICE_ACCOUNT_FILE "
                    "environment variable to the path of your Google Cloud service account JSON file."
                )
            
            if not os.path.exists(self.service_account_file):
                raise FileNotFoundError(f"Service account file not found: {self.service_account_file}")
            
            # Load service account credentials
            self.credentials = service_account.Credentials.from_service_account_file(
                self.service_account_file,
                scopes=CHAT_APP_SCOPES
            )
            
            # Get project ID from service account file
            with open(self.service_account_file, 'r') as f:
                sa_info = json.load(f)
                self.project_id = sa_info.get('project_id')
            
            # Build Chat service
            self.chat_service = build('chat', 'v1', credentials=self.credentials)
            
            logger.info(f"✅ Google Chat App Manager initialized for project: {self.project_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Chat App Manager: {e}")
            return False

# Lazy initialization - create manager instance when needed
chat_app_manager = None

def get_chat_app_manager():
    """Get or create the chat app manager instance."""
    global chat_app_manager
    if chat_app_manager is None:
        chat_app_manager = GoogleChatAppManager()
    return chat_app_manager

def setup_chat_app_tools(mcp: FastMCP) -> None:
    """
    Setup and register all Google Chat app development tools.
    
    Args:
        mcp: The FastMCP server instance to register tools with
    """
    logger.info("Setting up Google Chat App Development tools")

    @mcp.tool(
        name="initialize_chat_app_manager",
        description="Initialize the Google Chat App Manager with service account credentials",
        tags={"chat", "app", "development", "init", "service-account"},
    )
    async def initialize_chat_app_manager() -> str:
        """Initialize the Google Chat App Manager with service account credentials."""
        try:
            manager = get_chat_app_manager()
            success = await manager.initialize()
            
            if success:
                return f"""✅ Google Chat App Manager initialized successfully!

**Service Account Configuration:**
• Project ID: {manager.project_id}
• Service Account File: {settings.chat_service_account_file}
• Available Scopes: {', '.join(CHAT_APP_SCOPES)}

**Ready for:**
• Chat app creation and configuration
• Webhook handler generation
• Interactive card development
• App deployment and management

Use other chat app tools to start building your Google Chat app!"""
            else:
                return "❌ Failed to initialize Google Chat App Manager. Check service account file and permissions."
                
        except Exception as e:
            error_msg = f"❌ Error initializing Chat App Manager: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @mcp.tool(
        name="create_chat_app_manifest",
        description="Create a Google Chat app manifest with configuration",
        tags={"chat", "app", "manifest", "development", "config"},
    )
    async def create_chat_app_manifest(
        app_name: str,
        description: str,
        bot_endpoint: str,
        avatar_url: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        publishing_state: str = "DRAFT"
    ) -> str:
        """Create a Google Chat app manifest with the specified configuration."""
        try:
            manager = get_chat_app_manager()
            if not await manager.initialize():
                return "❌ Chat App Manager not initialized. Run 'initialize_chat_app_manager' first."
            
            # Default manifest structure
            manifest = {
                "name": app_name,
                "avatarUrl": avatar_url or "",
                "botEndpoint": bot_endpoint,
                "description": description,
                "addToSpacesDisabled": False,
                "useAppsScriptAuth": False,
                "enabledDomains": [],
                "publishingState": publishing_state,
                "permissions": {
                    "scopes": scopes or ["SPACE", "DM"]
                }
            }
            
            manifest_json = json.dumps(manifest, indent=2)
            
            # Save manifest to file
            manifest_file = f"chat_app_manifest_{app_name.lower().replace(' ', '_')}.json"
            with open(manifest_file, 'w') as f:
                f.write(manifest_json)
            
            return f"""✅ Google Chat App Manifest Created Successfully!

**App Configuration:**
• Name: {app_name}
• Description: {description}
• Bot Endpoint: {bot_endpoint}
• Scopes: {', '.join(scopes or ['SPACE', 'DM'])}
• Publishing State: {publishing_state}

**Manifest saved to:** {manifest_file}

**Next Steps:**
1. Review the manifest configuration
2. Create webhook handler templates
3. Deploy your app endpoint
4. Publish the app in Google Cloud Console"""
            
        except Exception as e:
            error_msg = f"❌ Error creating app manifest: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @mcp.tool(
        name="generate_webhook_template",
        description="Generate webhook handler template using existing card framework",
        tags={"chat", "app", "webhook", "template"},
    )
    async def generate_webhook_template(
        app_name: str,
        use_card_framework: bool = True,
        port: int = 8080
    ) -> str:
        """Generate webhook handler template that integrates with existing card framework."""
        try:
            from .app_templates.webhook_templates import WebhookTemplateGenerator
            
            generator = WebhookTemplateGenerator()
            if use_card_framework:
                template_code = generator.generate_basic_webhook(app_name, port)
            else:
                template_code = generator.generate_basic_webhook(app_name, port)
            
            # Save template to file
            template_file = f"webhook_{app_name.lower().replace(' ', '_')}.py"
            with open(template_file, 'w') as f:
                f.write(template_code)
            
            return f"""✅ Webhook Template Generated!

**Template Features:**
• Integrates with existing chat_cards_optimized.py
• Uses GoogleChatCardManager for rich cards
• Service account authentication
• Event handling for all Chat event types

**File Created:** {template_file}

**To Deploy:**
1. Customize the webhook for your specific needs
2. Install dependencies: fastapi, uvicorn, google-auth, google-api-python-client
3. Run: python {template_file}

**Card Framework Integration:**
• Uses existing card framework when available
• Graceful fallback to REST API format
• Leverages GoogleChatCardManager for rich interactions"""
            
        except ImportError:
            # Fallback if template generator not available
            basic_template = f'''"""
Google Chat App Webhook Handler - {app_name}
Generated on: {datetime.now().isoformat()}
Updated to use FastAPI
"""
import json
import logging
from fastapi import FastAPI, Request
from typing import Dict, Any
import uvicorn

# Import existing card framework
try:
    from gchat.chat_cards_optimized import GoogleChatCardManager
    card_manager = GoogleChatCardManager()
    CARD_FRAMEWORK_AVAILABLE = True
except ImportError:
    card_manager = None
    CARD_FRAMEWORK_AVAILABLE = False

app = FastAPI(title="{app_name} Chat Bot")
logger = logging.getLogger(__name__)

@app.post('/webhook')
async def handle_chat_event(request: Request):
    """Handle incoming Google Chat events."""
    try:
        event = await request.json()
        event_type = event.get('type')
        
        if event_type == 'ADDED_TO_SPACE':
            return handle_added_to_space(event)
        elif event_type == 'MESSAGE':
            return handle_message(event)
        elif event_type == 'CARD_CLICKED':
            return handle_card_interaction(event)
        else:
            return {{}}
    except Exception as e:
        logger.error(f"Error: {{e}}")
        return {{"text": "Error processing request"}}

def handle_added_to_space(event):
    """Handle app being added to a space."""
    if CARD_FRAMEWORK_AVAILABLE:
        card = card_manager.create_simple_card(
            title="Welcome to {app_name}!",
            text="I'm here to help you. Try sending me a message!",
        )
        return {{"cardsV2": [card]}}
    return {{"text": "👋 Welcome to {app_name}!"}}

def handle_message(event):
    """Handle incoming messages."""
    message_text = event.get('message', {{}}).get('text', '').strip()
    
    if message_text.lower() in ['help', '/help']:
        if CARD_FRAMEWORK_AVAILABLE:
            card = card_manager.create_interactive_card(
                title="Help - {app_name}",
                text="Available commands: help, hello",
                buttons=[{{"text": "Get Started", "action": {{"actionMethodName": "get_started"}}}}]
            )
            return card
        return {{"text": "Help: Available commands - help, hello"}}
    
    return {{"text": f"You said: {{message_text}}"}}

def handle_card_interaction(event):
    """Handle card interactions."""
    action = event.get('action', {{}}).get('actionMethodName', '')
    if action == 'get_started':
        return {{"text": "🎉 Welcome! You've successfully interacted with a card."}}
    return {{"text": f"Card action: {{action}}"}}

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port={port}, log_level="info")
'''
            
            template_file = f"webhook_{app_name.lower().replace(' ', '_')}.py"
            with open(template_file, 'w') as f:
                f.write(basic_template)
            
            return f"""✅ Basic Webhook Template Generated!

**File Created:** {template_file}
**Features:** Basic webhook with card framework integration

**Note:** Install app_templates for advanced features:
• Rich card templates
• Advanced webhook patterns
• Deployment configurations"""
        
        except Exception as e:
            error_msg = f"❌ Error generating webhook template: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @mcp.tool(
        name="list_chat_app_resources",
        description="List available Google Chat app development resources and examples",
        tags={"chat", "app", "resources", "examples", "documentation"},
    )
    async def list_chat_app_resources() -> str:
        """List available Google Chat app development resources and examples."""
        return """📚 Google Chat App Development Resources

**🛠️ Available Tools:**
• `initialize_chat_app_manager` - Set up service account authentication
• `create_chat_app_manifest` - Generate app configuration manifest
• `generate_webhook_template` - Create webhook handler with card framework

**📋 Card Framework Integration:**
• Uses existing chat_cards_optimized.py
• Leverages adapter system for enhanced functionality
• Supports both Card Framework v2 and fallback modes

**🔧 Event Types Handled:**
• `ADDED_TO_SPACE` - App added to space/DM
• `REMOVED_FROM_SPACE` - App removed from space
• `MESSAGE` - User sends message to app
• `CARD_CLICKED` - User interacts with card elements

**🚀 Deployment Options:**
• Google Cloud Run (recommended)
• Google App Engine
• Google Kubernetes Engine
• External hosting with HTTPS

**🔐 Authentication & Permissions:**
• Service account authentication configured
• Required scopes: chat.bot, chat.messages, chat.spaces
• Project ID: {get_chat_app_manager().project_id or 'Not initialized'}

**📚 Documentation Links:**
• Google Chat API: https://developers.google.com/chat
• Card Reference: https://developers.google.com/chat/api/guides/message-formats/cards
• Webhook Guide: https://developers.google.com/chat/how-tos/webhooks

**🔧 Development Workflow:**
1. Initialize the app manager
2. Create app manifest with configuration
3. Use existing card framework for rich interactions
4. Deploy to hosting platform
5. Test and iterate
6. Publish in Google Cloud Console"""


    logger.info("✅ Google Chat App Development tools setup complete")
