"""User and authentication resource templates for FastMCP2 Google Workspace Platform.

This module provides FastMCP resources and templates that expose authenticated user
information, eliminating the need for tools to manually require user_google_email parameters.
"""

import logging
from typing_extensions import Dict, Any, Optional, Annotated, TypedDict, NotRequired, List
from datetime import datetime
from pydantic import Field

from fastmcp import FastMCP, Context
from fastmcp.tools.tool_transform import ArgTransform, forward
from auth.context import (
    get_user_email_context,
    get_session_context,
    get_session_data,
    list_sessions
)
from auth.google_auth import get_valid_credentials

logger = logging.getLogger(__name__)


# ============================================================================
# TYPED DICT RESPONSE MODELS FOR USER RESOURCES
# ============================================================================

class AuthenticationStatus(TypedDict):
    """Authentication status information."""
    authenticated: bool
    credentials_valid: bool
    has_refresh_token: bool
    scopes: List[str]
    expires_at: Optional[str]


class UserEmailResponse(TypedDict):
    """Response for current user email resource."""
    email: NotRequired[Optional[str]]
    session_id: NotRequired[Optional[str]]
    timestamp: str
    authenticated: bool
    error: NotRequired[Optional[str]]
    suggestion: NotRequired[Optional[str]]


class UserProfileResponse(TypedDict):
    """Response for user profile resources."""
    email: NotRequired[Optional[str]]
    session_id: NotRequired[Optional[str]]
    auth_status: NotRequired[AuthenticationStatus]
    timestamp: str
    authenticated: NotRequired[bool]
    is_current_user: NotRequired[bool]
    error: NotRequired[Optional[str]]
    debug_info: NotRequired[Optional[Dict[str, Any]]]


class SessionInfoResponse(TypedDict):
    """Response for session information resources."""
    session_id: NotRequired[Optional[str]]
    user_email: NotRequired[Optional[str]]
    session_active: bool
    timestamp: str
    created_at: NotRequired[Optional[str]]
    last_accessed: NotRequired[Optional[str]]
    error: NotRequired[Optional[str]]


class SessionListResponse(TypedDict):
    """Response for active sessions list resource."""
    active_sessions: List[Dict[str, Any]]
    count: int
    current_session: NotRequired[Optional[str]]
    timestamp: str
    error: NotRequired[Optional[str]]


class CredentialStatusResponse(TypedDict):
    """Response for credential status resources."""
    email: str
    authenticated: bool
    credentials_valid: NotRequired[bool]
    expired: NotRequired[bool]
    has_refresh_token: NotRequired[bool]
    scopes: NotRequired[List[str]]
    client_id: NotRequired[Optional[str]]
    token_uri: NotRequired[Optional[str]]
    expires_at: NotRequired[Optional[str]]
    timestamp: str
    status: NotRequired[str]
    error: NotRequired[Optional[str]]
    time_until_expiry: NotRequired[Optional[str]]
    refresh_recommended: NotRequired[bool]


class ServiceScopesResponse(TypedDict):
    """Response for Google service scopes resource."""
    service: str
    default_scopes: List[str]
    version: str
    description: str
    timestamp: str
    error: NotRequired[Optional[str]]
    available_services: NotRequired[List[str]]


class ToolInfo(TypedDict):
    """Information about a single tool."""
    name: str
    description: str
    parameters: List[str]
    example: NotRequired[str]


class ToolParameterInfo(TypedDict):
    """Parameter information for a tool."""
    query: NotRequired[str]
    page_size: NotRequired[str]
    max_results: NotRequired[str]
    summary: NotRequired[str]
    start_time: NotRequired[str]
    end_time: NotRequired[str]
    description: NotRequired[str]
    attendees: NotRequired[str]
    calendar_id: NotRequired[str]


class EnhancedToolInfo(TypedDict):
    """Enhanced tool information with detailed parameters."""
    name: str
    description: str
    parameters: Dict[str, str]
    example: str


class EnhancedToolsResponse(TypedDict):
    """Response for enhanced tools collection."""
    enhanced_tools: List[EnhancedToolInfo]
    count: int
    benefit: str
    timestamp: str


class ToolCategoryInfo(TypedDict):
    """Information about a tool category."""
    description: str
    tool_count: int
    requires_email: NotRequired[bool]
    tools: NotRequired[List[ToolInfo]]


class ToolsDirectoryResponse(TypedDict):
    """Response for complete tools directory resource."""
    total_tools: int
    total_categories: int
    enhanced_tools_count: int
    tools_by_category: Dict[str, Any]
    timestamp: str
    resource_templating_available: bool
    migration_status: str
    error: NotRequired[Optional[str]]


class WorkflowExample(TypedDict):
    """Example workflow information."""
    drive: str
    gmail: str
    calendar: str
    status: str


class ToolUsageGuideResponse(TypedDict):
    """Response for tools usage guide resource."""
    quick_start: Dict[str, str]
    enhanced_tools_workflow: Dict[str, Any]
    legacy_tools_workflow: Dict[str, Any]
    migration_guide: Dict[str, str]
    error_handling: Dict[str, str]
    timestamp: str


class WorkspaceContentItem(TypedDict):
    """Individual workspace content item."""
    id: str
    name: str
    type: str
    modified_time: str
    web_view_link: str
    mime_type: NotRequired[str]


class WorkspaceContentResponse(TypedDict):
    """Response for workspace content resources."""
    user_email: str
    content_items: List[WorkspaceContentItem]
    count: int
    timestamp: str
    source: str
    error: NotRequired[Optional[str]]


class ContentSuggestion(TypedDict):
    """Content suggestion item."""
    type: str
    title: str
    description: str
    action: str
    priority: int


class GmailContentSuggestionsResponse(TypedDict):
    """Response for Gmail content suggestions resource."""
    user_email: str
    suggestions: List[ContentSuggestion]
    count: int
    categories: List[str]
    timestamp: str
    error: NotRequired[Optional[str]]


class GmailAllowListResponse(TypedDict):
    """Response for Gmail allow list resource."""
    user_email: str
    allow_list: List[str]
    count: int
    description: str
    last_updated: str
    timestamp: str
    error: NotRequired[Optional[str]]


def setup_user_resources(mcp: FastMCP) -> None:
    """Setup all user and authentication resources."""
    
    @mcp.resource(
        uri="user://current/email",
        name="Current User Email",
        description="Get the currently authenticated user's email address for session-based authentication",
        mime_type="application/json",
        tags={"authentication", "user", "email", "session", "template"},
        enabled=True,
        meta={
            "template_accessible": True, 
            "property_paths": ["email", "session_id", "timestamp"],
            "response_model": "UserEmailResponse",
            "enhanced": True
        }
    )
    async def get_current_user_email(ctx: Context) -> UserEmailResponse:
        """Internal implementation for current user email resource."""
        user_email = get_user_email_context()
        if not user_email:
            return UserEmailResponse(
                error="No authenticated user found in current session",
                suggestion="Use start_google_auth tool to authenticate first",
                authenticated=False,
                timestamp=datetime.now().isoformat()
            )
        
        return UserEmailResponse(
            email=user_email,
            session_id=get_session_context(),
            timestamp=datetime.now().isoformat(),
            authenticated=True
        )
    
    @mcp.resource(
        uri="user://current/profile",
        name="Current User Profile",
        description="Comprehensive profile information including authentication status, credential validity, and available Google services for the current session user",
        mime_type="application/json",
        tags={"authentication", "user", "profile", "credentials", "session", "google"},
        meta={
            "response_model": "UserProfileResponse",
            "enhanced": True,
            "includes_debug": True
        }
    )
    async def get_current_user_profile(ctx: Context) -> UserProfileResponse:
        """Internal implementation for current user profile resource."""
        user_email = get_user_email_context()
        session_id = get_session_context()
        
        # DIAGNOSTIC: Log context state for debugging OAuth vs start_google_auth disconnect
        logger.info(f"🔍 DEBUG: get_current_user_profile called")
        logger.info(f"   user_email_context: {user_email}")
        logger.info(f"   session_context: {session_id}")
        
        if not user_email:
            return UserProfileResponse(
                error="No authenticated user found in current session",
                authenticated=False,
                timestamp=datetime.now().isoformat(),
                debug_info={
                    "user_email_context": user_email,
                    "session_context": session_id,
                    "issue": "OAuth proxy authentication may not be setting session context"
                }
            )
        
        # Check credential validity
        credentials = get_valid_credentials(user_email)
        auth_status = AuthenticationStatus(
            authenticated=credentials is not None,
            credentials_valid=credentials is not None and not credentials.expired,
            has_refresh_token=credentials is not None and credentials.refresh_token is not None,
            scopes=credentials.scopes if credentials else [],
            expires_at=credentials.expiry.isoformat() if credentials and credentials.expiry else None
        )
        
        return UserProfileResponse(
            email=user_email,
            session_id=get_session_context(),
            auth_status=auth_status,
            timestamp=datetime.now().isoformat()
        )
    
    @mcp.resource(
        uri="user://profile/{email}",
        name="User Profile by Email",
        description="Get detailed profile information for a specific user email including authentication status, credential validity, and comparison with current session user",
        mime_type="application/json",
        tags={"user", "profile", "authentication", "credentials", "email", "lookup"},
        meta={
            "response_model": "UserProfileResponse",
            "enhanced": True,
            "supports_lookup": True
        }
    )
    async def get_user_profile_by_email(
        email: Annotated[str, Field(description="Email address of the user to get profile information for", pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')], 
        ctx: Context
    ) -> UserProfileResponse:
        """Internal implementation for user profile by email resource."""
        # Check credential validity for the specified user
        credentials = get_valid_credentials(email)
        auth_status = AuthenticationStatus(
            authenticated=credentials is not None,
            credentials_valid=credentials is not None and not credentials.expired,
            has_refresh_token=credentials is not None and credentials.refresh_token is not None,
            scopes=credentials.scopes if credentials else [],
            expires_at=credentials.expiry.isoformat() if credentials and credentials.expiry else None
        )
        
        return UserProfileResponse(
            email=email,
            auth_status=auth_status,
            is_current_user=email == get_user_email_context(),
            timestamp=datetime.now().isoformat()
        )
    
    @mcp.resource(
        uri="auth://session/current",
        name="Current Authentication Session",
        description="Detailed information about the current authentication session including token status, expiration times, and granted scopes",
        mime_type="application/json",
        tags={"authentication", "session", "oauth", "token", "security"},
        meta={
            "response_model": "SessionInfoResponse",
            "enhanced": True,
            "includes_metadata": True
        }
    )
    async def get_current_session_info(ctx: Context) -> SessionInfoResponse:
        """Internal implementation for current session info resource."""
        session_id = get_session_context()
        user_email = get_user_email_context()
        
        if not session_id:
            return SessionInfoResponse(
                error="No active session found",
                session_active=False,
                timestamp=datetime.now().isoformat()
            )
        
        # Get session metadata if available
        session_data = SessionInfoResponse(
            session_id=session_id,
            user_email=user_email,
            session_active=True,
            timestamp=datetime.now().isoformat()
        )
        
        # Add any additional session data stored
        try:
            created_at = get_session_data(session_id, "created_at")
            last_accessed = get_session_data(session_id, "last_accessed")
            
            if created_at:
                session_data["created_at"] = created_at.isoformat()
            if last_accessed:
                session_data["last_accessed"] = last_accessed.isoformat()
        except Exception as e:
            logger.debug(f"Could not retrieve session metadata: {e}")
        
        return session_data
    
    @mcp.resource(
        uri="auth://sessions/list",
        name="Active Authentication Sessions",
        description="Administrative view of all active authentication sessions with session details, user information, and expiration status for multi-user session management",
        mime_type="application/json",
        tags={"authentication", "sessions", "admin", "multi-user", "management", "security"},
        meta={
            "response_model": "SessionListResponse",
            "enhanced": True,
            "administrative": True
        }
    )
    async def list_active_sessions(ctx: Context) -> SessionListResponse:
        """Internal implementation for active sessions list resource."""
        try:
            active_sessions = list_sessions()
            
            return SessionListResponse(
                active_sessions=active_sessions,
                count=len(active_sessions),
                current_session=get_session_context(),
                timestamp=datetime.now().isoformat()
            )
        except Exception as e:
            logger.error(f"Error listing sessions: {e}")
            return SessionListResponse(
                error=f"Failed to list sessions: {str(e)}",
                active_sessions=[],
                count=0,
                timestamp=datetime.now().isoformat()
            )
    
    @mcp.resource(
        uri="auth://credentials/{email}/status",
        name="User Credential Status",
        description="Detailed credential status for a specific user including validity, expiration, refresh token availability, and granted scopes for authentication management",
        mime_type="application/json",
        tags={"authentication", "credentials", "status", "oauth", "tokens", "security", "user"},
        meta={
            "response_model": "CredentialStatusResponse",
            "enhanced": True,
            "supports_lookup": True
        }
    )
    async def get_credential_status(
        email: Annotated[str, Field(description="Email address to check credential status for", pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')],
        ctx: Context
    ) -> CredentialStatusResponse:
        """Internal implementation for credential status resource."""
        try:
            credentials = get_valid_credentials(email)
            
            if not credentials:
                return CredentialStatusResponse(
                    email=email,
                    status="no_credentials",
                    authenticated=False,
                    timestamp=datetime.now().isoformat(),
                    error="No stored credentials found for this user"
                )
            
            status_info = CredentialStatusResponse(
                email=email,
                authenticated=True,
                credentials_valid=not credentials.expired,
                expired=credentials.expired,
                has_refresh_token=credentials.refresh_token is not None,
                scopes=credentials.scopes or [],
                client_id=credentials.client_id[:10] + "..." if credentials.client_id else None,
                token_uri=credentials.token_uri,
                expires_at=credentials.expiry.isoformat() if credentials.expiry else None,
                timestamp=datetime.now().isoformat()
            )
            
            if credentials.expired:
                status_info["status"] = "expired"
                status_info["time_until_expiry"] = "Already expired"
                status_info["refresh_recommended"] = True
            else:
                status_info["status"] = "valid"
                if credentials.expiry:
                    time_remaining = credentials.expiry - datetime.now()
                    status_info["time_until_expiry"] = str(time_remaining)
                    status_info["refresh_recommended"] = time_remaining.total_seconds() < 3600  # < 1 hour
            
            return status_info
            
        except Exception as e:
            logger.error(f"Error checking credentials for {email}: {e}")
            return CredentialStatusResponse(
                email=email,
                status="error",
                authenticated=False,
                error=str(e),
                timestamp=datetime.now().isoformat()
            )
    
    @mcp.resource(
        uri="template://user_email",
        name="User Email Template",
        description="Simple template resource that returns just the user email string - the most basic resource for tools that need only the email address",
        mime_type="text/plain",
        tags={"template", "user", "email", "simple", "authentication", "string"}
    )
    async def get_template_user_email(ctx: Context) -> str:
        """Internal implementation for user email template resource."""
        user_email = get_user_email_context()
        if not user_email:
            # Return a helpful error message as string instead of raising exception
            # This follows FastMCP2 resource patterns - resources should return data gracefully
            return "❌ Authentication error: No authenticated user found in current session. Use start_google_auth tool first."
        
        return user_email
    
    @mcp.resource(
        uri="google://services/scopes/{service}",
        name="Google Service Scopes",
        description="Get the required OAuth scopes, API version, and configuration details for a specific Google service including Drive, Gmail, Calendar, and other Workspace APIs",
        mime_type="application/json",
        tags={"google", "services", "scopes", "oauth", "api", "configuration", "workspace"},
        meta={
            "response_model": "ServiceScopesResponse",
            "enhanced": True,
            "supports_lookup": True
        }
    )
    async def get_service_scopes(
        service: Annotated[str, Field(description="Google service name to get scope information for")],
        ctx: Context
    ) -> ServiceScopesResponse:
        """Internal implementation for Google service scopes resource."""
        # Import here to avoid circular imports
        from auth.service_helpers import SERVICE_DEFAULTS
        
        service_info = SERVICE_DEFAULTS.get(service.lower())
        if not service_info:
            return ServiceScopesResponse(
                service=service,
                error=f"Unknown Google service: {service}",
                available_services=list(SERVICE_DEFAULTS.keys()),
                default_scopes=[],
                version="unknown",
                description="Service not found",
                timestamp=datetime.now().isoformat()
            )
        
        return ServiceScopesResponse(
            service=service,
            default_scopes=service_info.get("default_scopes", []),
            version=service_info.get("version", "v1"),
            description=service_info.get("description", f"Google {service.title()} API"),
            timestamp=datetime.now().isoformat()
        )
    
    @mcp.resource(
        uri="tools://list/all",
        name="Complete Tools Directory",
        description="Comprehensive catalog of all available tools organized by category including Drive, Gmail, Calendar, Chat, Forms, Docs, Sheets, and authentication tools with detailed capability descriptions",
        mime_type="application/json",
        tags={"tools", "directory", "catalog", "discovery", "google", "workspace", "enhanced", "legacy"},
        meta={
            "response_model": "ToolsDirectoryResponse",
            "enhanced": True,
            "comprehensive": True,
            "dynamic": True
        }
    )
    async def get_all_tools_list(ctx: Context) -> ToolsDirectoryResponse:
        """Internal implementation for complete tools directory resource - dynamically discovers tools from FastMCP server."""
        try:
            # Access the FastMCP server instance through context
            fastmcp_server = ctx.fastmcp
            
            # Log FastMCP server structure for debugging
            await ctx.debug(f"FastMCP server type: {type(fastmcp_server)}")
            await ctx.debug(f"FastMCP server attributes: {dir(fastmcp_server)}")
            
            # Try to access tools via the documented fastmcp.tools attribute
            tools_list = None
            registered_tools = {}
            
            if hasattr(fastmcp_server, 'tools'):
                tools_list = fastmcp_server.tools
                await ctx.info(f"✅ Found fastmcp.tools attribute: {type(tools_list)}")
                await ctx.debug(f"Tools list length: {len(tools_list) if hasattr(tools_list, '__len__') else 'unknown'}")
                
                # Convert tools list to dictionary if it's a list
                if isinstance(tools_list, list):
                    for tool in tools_list:
                        if hasattr(tool, 'name'):
                            registered_tools[tool.name] = tool
                        else:
                            await ctx.warning(f"Tool in list has no name attribute: {tool}")
                elif hasattr(tools_list, 'items'):
                    # It's already a dict-like object
                    registered_tools = dict(tools_list.items())
                else:
                    await ctx.warning(f"Tools attribute is not list or dict: {type(tools_list)}")
            
            # Fallback to tool manager if tools attribute doesn't work
            if not registered_tools and hasattr(fastmcp_server, '_tool_manager'):
                await ctx.info("Falling back to _tool_manager")
                if hasattr(fastmcp_server._tool_manager, '_tools'):
                    registered_tools = fastmcp_server._tool_manager._tools
                    await ctx.info(f"✅ Found {len(registered_tools)} tools via _tool_manager")
                elif hasattr(fastmcp_server._tool_manager, 'tools'):
                    registered_tools = fastmcp_server._tool_manager.tools
                    await ctx.info(f"✅ Found {len(registered_tools)} tools via _tool_manager.tools")
            
            if not registered_tools:
                await ctx.warning("Could not access tools from FastMCP server - trying alternative methods")
                # Try other common attributes
                for attr_name in ['_tools', 'tool_registry', 'registry']:
                    if hasattr(fastmcp_server, attr_name):
                        attr_value = getattr(fastmcp_server, attr_name)
                        await ctx.debug(f"Found attribute {attr_name}: {type(attr_value)}")
                        if hasattr(attr_value, 'items'):
                            registered_tools = dict(attr_value.items())
                            break
                        elif hasattr(attr_value, '__len__') and len(attr_value) > 0:
                            # Convert list to dict
                            for item in attr_value:
                                if hasattr(item, 'name'):
                                    registered_tools[item.name] = item
                            break
            
            await ctx.info(f"🔍 Final tool count: {len(registered_tools)}")
            
            # Categorize tools dynamically based on their names and tags
            categories = {
                "enhanced_tools": {
                    "description": "New tools that use resource templating (no email params needed)",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": False
                },
                "drive_tools": {
                    "description": "Google Drive file management tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True
                },
                "gmail_tools": {
                    "description": "Gmail email management tools", 
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True
                },
                "docs_tools": {
                    "description": "Google Docs document management tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True
                },
                "forms_tools": {
                    "description": "Google Forms creation and management tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True
                },
                "calendar_tools": {
                    "description": "Google Calendar event management tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True
                },
                "slides_tools": {
                    "description": "Google Slides presentation tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True
                },
                "sheets_tools": {
                    "description": "Google Sheets spreadsheet tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True
                },
                "chat_tools": {
                    "description": "Google Chat messaging tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True
                },
                "photos_tools": {
                    "description": "Google Photos tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True
                },
                "auth_tools": {
                    "description": "Authentication and system tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": "mixed"
                },
                "qdrant_tools": {
                    "description": "Qdrant search and analytics tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": False
                },
                "module_tools": {
                    "description": "Module wrapper and introspection tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": False
                },
                "other_tools": {
                    "description": "Other utility and system tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": "mixed"
                }
            }
            
            # Categorize each tool
            for tool_name, tool_instance in registered_tools.items():
                await ctx.debug(f"Processing tool: {tool_name}")
                
                # Get tool metadata - be more defensive about accessing attributes
                tool_info = {
                    "name": tool_name,
                    "description": "No description available",
                    "tags": [],
                    "parameters": [],
                    "enhanced": False
                }
                
                # Safely get description
                if hasattr(tool_instance, 'description') and tool_instance.description:
                    tool_info["description"] = tool_instance.description
                elif hasattr(tool_instance, 'doc') and tool_instance.doc:
                    tool_info["description"] = tool_instance.doc
                
                # Safely get tags
                if hasattr(tool_instance, 'tags') and tool_instance.tags:
                    if isinstance(tool_instance.tags, (set, list, tuple)):
                        tool_info["tags"] = list(tool_instance.tags)
                    else:
                        tool_info["tags"] = [str(tool_instance.tags)]
                
                # Extract parameters from tool schema if available
                parameter_names = []
                if hasattr(tool_instance, 'schema') and tool_instance.schema:
                    schema = tool_instance.schema
                    if isinstance(schema, dict) and 'parameters' in schema:
                        params = schema['parameters']
                        if isinstance(params, dict) and 'properties' in params:
                            parameter_names = list(params['properties'].keys())
                            tool_info["parameters"] = parameter_names
                elif hasattr(tool_instance, 'parameters'):
                    # Some tools might have a direct parameters attribute
                    if hasattr(tool_instance.parameters, 'keys'):
                        parameter_names = list(tool_instance.parameters.keys())
                        tool_info["parameters"] = parameter_names
                
                # Check if it's an enhanced tool (no user_google_email parameter)
                is_enhanced = 'user_google_email' not in parameter_names
                tool_info["enhanced"] = is_enhanced
                
                # Categorize based on name patterns and tags
                categorized = False
                
                # Enhanced tools (no email parameter)
                if is_enhanced and any(keyword in tool_name for keyword in ['my_', '_my', 'get_my_']):
                    categories["enhanced_tools"]["tools"].append(tool_info)
                    categories["enhanced_tools"]["tool_count"] += 1
                    categorized = True
                
                # Service-specific tools
                elif any(keyword in tool_name for keyword in ['drive', 'file']):
                    categories["drive_tools"]["tools"].append(tool_info)
                    categories["drive_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ['gmail', 'email', 'message', 'draft']):
                    categories["gmail_tools"]["tools"].append(tool_info)
                    categories["gmail_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ['doc', 'document']):
                    categories["docs_tools"]["tools"].append(tool_info)
                    categories["docs_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ['form', 'response']):
                    categories["forms_tools"]["tools"].append(tool_info)
                    categories["forms_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ['calendar', 'event']):
                    categories["calendar_tools"]["tools"].append(tool_info)
                    categories["calendar_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ['slide', 'presentation']):
                    categories["slides_tools"]["tools"].append(tool_info)
                    categories["slides_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ['sheet', 'spreadsheet']):
                    categories["sheets_tools"]["tools"].append(tool_info)
                    categories["sheets_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ['chat', 'space', 'card']):
                    categories["chat_tools"]["tools"].append(tool_info)
                    categories["chat_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ['photo', 'album']):
                    categories["photos_tools"]["tools"].append(tool_info)
                    categories["photos_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ['auth', 'credential', 'session', 'oauth']):
                    categories["auth_tools"]["tools"].append(tool_info)
                    categories["auth_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ['qdrant', 'search', 'vector', 'embed']):
                    categories["qdrant_tools"]["tools"].append(tool_info)
                    categories["qdrant_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ['module', 'wrap', 'component']):
                    categories["module_tools"]["tools"].append(tool_info)
                    categories["module_tools"]["tool_count"] += 1
                    categorized = True
                
                # Uncategorized tools go to "other"
                if not categorized:
                    categories["other_tools"]["tools"].append(tool_info)
                    categories["other_tools"]["tool_count"] += 1
            
            # Calculate totals
            total_tools = len(registered_tools)
            enhanced_tools_count = categories["enhanced_tools"]["tool_count"]
            
            # Log discovery results
            await ctx.info(f"🔍 Dynamic tool discovery: Found {total_tools} tools, {enhanced_tools_count} enhanced")
            
            return ToolsDirectoryResponse(
                total_tools=total_tools,
                total_categories=len([cat for cat in categories.values() if cat["tool_count"] > 0]),
                enhanced_tools_count=enhanced_tools_count,
                tools_by_category=categories,
                timestamp=datetime.now().isoformat(),
                resource_templating_available=True,
                migration_status="✅ Resource templating implemented - enhanced tools available!"
            )
            
        except Exception as e:
            await ctx.error(f"Error during dynamic tool discovery: {e}")
            # Fallback to minimal response
            return ToolsDirectoryResponse(
                total_tools=0,
                total_categories=0,
                enhanced_tools_count=0,
                tools_by_category={},
                timestamp=datetime.now().isoformat(),
                resource_templating_available=False,
                migration_status="❌ Error during tool discovery",
                error=str(e)
            )
            
        except Exception as e:
            logger.error(f"Error generating tools list: {e}")
            return ToolsDirectoryResponse(
                total_tools=0,
                total_categories=0,
                enhanced_tools_count=0,
                tools_by_category={},
                timestamp=datetime.now().isoformat(),
                resource_templating_available=False,
                migration_status="❌ Error generating tools list",
                error=f"Failed to generate tools list: {str(e)}"
            )
    
    @mcp.resource(
        uri="tools://enhanced/list",
        name="Enhanced Tools Collection",
        description="Curated list of enhanced tools that use automatic resource templating - no user_google_email parameters required, seamless authentication through OAuth session context",
        mime_type="application/json",
        tags={"tools", "enhanced", "templating", "oauth", "seamless", "modern", "no-email"},
        meta={
            "response_model": "EnhancedToolsResponse",
            "enhanced": True,
            "oauth_enabled": True
        }
    )
    async def get_enhanced_tools_only(ctx: Context) -> EnhancedToolsResponse:
        """Internal implementation for enhanced tools collection resource - dynamically discovers enhanced tools."""
        try:
            # Access the FastMCP server instance through context
            fastmcp_server = ctx.fastmcp
            
            # Try to access tools via the documented fastmcp.tools attribute first
            tools_list = None
            registered_tools = {}
            
            if hasattr(fastmcp_server, 'tools'):
                tools_list = fastmcp_server.tools
                await ctx.debug(f"Found fastmcp.tools: {type(tools_list)}")
                
                # Convert tools list to dictionary if it's a list
                if isinstance(tools_list, list):
                    for tool in tools_list:
                        if hasattr(tool, 'name'):
                            registered_tools[tool.name] = tool
                elif hasattr(tools_list, 'items'):
                    # It's already a dict-like object
                    registered_tools = dict(tools_list.items())
            
            # Fallback to tool manager if tools attribute doesn't work
            if not registered_tools and hasattr(fastmcp_server, '_tool_manager'):
                if hasattr(fastmcp_server._tool_manager, '_tools'):
                    registered_tools = fastmcp_server._tool_manager._tools
                elif hasattr(fastmcp_server._tool_manager, 'tools'):
                    registered_tools = fastmcp_server._tool_manager.tools
            
            if not registered_tools:
                await ctx.warning("Could not access tools from FastMCP server")
                return EnhancedToolsResponse(
                    enhanced_tools=[],
                    count=0,
                    benefit="No user_google_email parameter required - uses OAuth session automatically",
                    timestamp=datetime.now().isoformat()
                )
            
            # Find enhanced tools (tools without user_google_email parameter)
            enhanced_tools = []
            
            for tool_name, tool_instance in registered_tools.items():
                # Get tool parameters safely
                parameters = {}
                parameter_names = []
                
                # Try to get parameters from schema
                if hasattr(tool_instance, 'schema') and tool_instance.schema:
                    schema = tool_instance.schema
                    if isinstance(schema, dict) and 'parameters' in schema:
                        params = schema['parameters']
                        if isinstance(params, dict) and 'properties' in params:
                            parameter_names = list(params['properties'].keys())
                            # Build parameter descriptions
                            for param_name, param_info in params['properties'].items():
                                if isinstance(param_info, dict):
                                    parameters[param_name] = param_info.get('description', f'{param_name} parameter')
                                else:
                                    parameters[param_name] = f'{param_name} parameter'
                
                # Check if it's an enhanced tool (no user_google_email parameter)
                is_enhanced = 'user_google_email' not in parameter_names
                
                # Include tools that are clearly "enhanced" based on naming or characteristics
                if is_enhanced and (
                    any(keyword in tool_name for keyword in ['my_', '_my', 'get_my_']) or
                    ('template' in getattr(tool_instance, 'tags', set())) or
                    ('enhanced' in getattr(tool_instance, 'tags', set()))
                ):
                    # Safely get description
                    description = "Enhanced tool with automatic authentication"
                    if hasattr(tool_instance, 'description') and tool_instance.description:
                        description = tool_instance.description
                    
                    # Create a more meaningful example
                    example = f"{tool_name}()"
                    if parameters:
                        # Create a basic example with parameter names
                        param_examples = []
                        for param_name in list(parameters.keys())[:3]:  # First 3 params
                            if 'query' in param_name:
                                param_examples.append(f'{param_name}="search term"')
                            elif 'summary' in param_name or 'title' in param_name:
                                param_examples.append(f'{param_name}="Example Title"')
                            elif 'time' in param_name:
                                param_examples.append(f'{param_name}="2025-02-01T10:00:00Z"')
                            else:
                                param_examples.append(f'{param_name}="value"')
                        
                        if param_examples:
                            example = f"{tool_name}({', '.join(param_examples)})"
                    
                    enhanced_tool = EnhancedToolInfo(
                        name=tool_name,
                        description=description,
                        parameters=parameters,
                        example=example
                    )
                    enhanced_tools.append(enhanced_tool)
            
            # Log discovery results
            await ctx.info(f"🔍 Enhanced tool discovery: Found {len(enhanced_tools)} enhanced tools out of {len(registered_tools)} total")
            
            return EnhancedToolsResponse(
                enhanced_tools=enhanced_tools,
                count=len(enhanced_tools),
                benefit="No user_google_email parameter required - uses OAuth session automatically",
                timestamp=datetime.now().isoformat()
            )
            
        except Exception as e:
            await ctx.error(f"Error during enhanced tool discovery: {e}")
            # Fallback to empty response
            return EnhancedToolsResponse(
                enhanced_tools=[],
                count=0,
                benefit="No user_google_email parameter required - uses OAuth session automatically",
                timestamp=datetime.now().isoformat()
            )
    
    @mcp.resource(
        uri="tools://usage/guide",
        name="Comprehensive Tools Usage Guide",
        description="Complete usage guide with examples, workflows, and best practices for both enhanced and legacy tools including authentication flows, migration examples, and error handling patterns",
        mime_type="application/json",
        tags={"tools", "guide", "usage", "examples", "workflows", "migration", "authentication", "best-practices"},
        meta={
            "response_model": "ToolUsageGuideResponse",
            "enhanced": True,
            "comprehensive": True
        }
    )
    async def get_tool_usage_guide(ctx: Context) -> ToolUsageGuideResponse:
        """Internal implementation for comprehensive tools usage guide resource."""
        return ToolUsageGuideResponse(
            quick_start={
                "step_1": "Authenticate with: start_google_auth('your.email@gmail.com')",
                "step_2": "Check status with: get_my_auth_status() (enhanced tool - no email needed!)",
                "step_3": "Use tools: list_my_drive_files() or search_my_gmail('your query')"
            },
            enhanced_tools_workflow={
                "description": "New tools that don't require email parameters",
                "authentication": "Automatic from OAuth session",
                "examples": {
                    "drive": "list_my_drive_files('name contains \"report\"')",
                    "gmail": "search_my_gmail('from:boss@company.com')",
                    "calendar": "create_my_calendar_event('Meeting', '2025-02-01T10:00:00Z', '2025-02-01T11:00:00Z')",
                    "status": "get_my_auth_status()"
                }
            },
            legacy_tools_workflow={
                "description": "Original tools that require email parameters",
                "authentication": "Manual email parameter required",
                "examples": {
                    "drive": "search_drive_files('user@gmail.com', 'name contains \"report\"')",
                    "gmail": "search_gmail_messages('user@gmail.com', 'from:boss@company.com')",
                    "docs": "search_docs('user@gmail.com', 'meeting notes')"
                }
            },
            migration_guide={
                "from": "search_drive_files('user@gmail.com', 'query')",
                "to": "list_my_drive_files('query')",
                "benefit": "No need to remember or type your email address"
            },
            error_handling={
                "no_auth": "Enhanced tools will show: '❌ Authentication error: No authenticated user found'",
                "solution": "Run start_google_auth('your.email@gmail.com') first"
            },
            timestamp=datetime.now().isoformat()
        )
    
    @mcp.resource(
        uri="workspace://content/recent",
        name="Recent Google Workspace Content",
        description="List of recently accessed Google Docs, Sheets, Drive files, and other Workspace content for dynamic email composition and content linking",
        mime_type="application/json",
        tags={"workspace", "content", "drive", "docs", "sheets", "recent", "gmail", "email"},
        meta={
            "response_model": "WorkspaceContentResponse",
            "enhanced": True,
            "requires_auth": True
        }
    )
    async def get_recent_workspace_content(ctx: Context) -> WorkspaceContentResponse:
        """Get recent Google Workspace content for email composition."""
        user_email = get_user_email_context()
        if not user_email:
            return {
                "error": "No authenticated user found in current session",
                "suggestion": "Use start_google_auth tool to authenticate first"
            }
        
        try:
            # Get recent Drive files (last 30 days) using forward() pattern
            recent_files = await forward(
                "search_drive_files",
                user_google_email=user_email,
                query="modifiedTime > '2025-01-01' and trashed=false",
                page_size=20
            )
            
            # Get recent Docs (if available) using forward() pattern
            try:
                recent_docs = await forward(
                    "search_docs",
                    user_google_email=user_email,
                    query="modified last month",
                    max_results=10
                )
            except Exception:
                recent_docs = []
            
            # Organize by type
            content_by_type = {
                "documents": [],
                "spreadsheets": [],
                "presentations": [],
                "folders": [],
                "other_files": []
            }
            
            for file_info in recent_files.get('files', []):
                mime_type = file_info.get('mimeType', '')
                file_entry = {
                    "id": file_info.get('id'),
                    "name": file_info.get('name'),
                    "web_view_link": file_info.get('webViewLink'),
                    "modified_time": file_info.get('modifiedTime'),
                    "mime_type": mime_type,
                    "size": file_info.get('size', 'N/A')
                }
                
                if 'document' in mime_type:
                    content_by_type["documents"].append(file_entry)
                elif 'spreadsheet' in mime_type:
                    content_by_type["spreadsheets"].append(file_entry)
                elif 'presentation' in mime_type:
                    content_by_type["presentations"].append(file_entry)
                elif 'folder' in mime_type:
                    content_by_type["folders"].append(file_entry)
                else:
                    content_by_type["other_files"].append(file_entry)
            
            return {
                "user_email": user_email,
                "content_summary": {
                    "total_files": len(recent_files.get('files', [])),
                    "documents": len(content_by_type["documents"]),
                    "spreadsheets": len(content_by_type["spreadsheets"]),
                    "presentations": len(content_by_type["presentations"]),
                    "folders": len(content_by_type["folders"]),
                    "other_files": len(content_by_type["other_files"])
                },
                "content_by_type": content_by_type,
                "timestamp": datetime.now().isoformat(),
                "usage_tips": [
                    "Use file IDs to create direct links in emails",
                    "Reference document names in email content",
                    "Include web_view_links for easy access",
                    "Check modified_time for freshness"
                ]
            }
            
        except Exception as e:
            logger.error(f"Error fetching workspace content: {e}")
            return {
                "error": f"Failed to fetch workspace content: {str(e)}",
                "user_email": user_email,
                "fallback_suggestion": "Use search_drive_files or list_my_drive_files tools manually",
                "timestamp": datetime.now().isoformat()
            }
    
    @mcp.resource(
        uri="workspace://content/search/{query}",
        name="Search Google Workspace Content",
        description="Search across Google Workspace content (Drive, Docs, Sheets) for specific topics or keywords to dynamically populate email content with relevant links and references",
        mime_type="application/json",
        tags={"workspace", "search", "drive", "docs", "sheets", "content", "gmail", "dynamic"}
    )
    async def search_workspace_content(
        query: Annotated[str, Field(description="Search query to find relevant workspace content")],
        ctx: Context
    ) -> dict:
        """Search Google Workspace content for email composition."""
        user_email = get_user_email_context()
        if not user_email:
            return {
                "error": "No authenticated user found in current session",
                "query": query
            }
        
        try:
            # Search Drive files using forward() pattern
            search_results = await forward(
                "search_drive_files",
                user_google_email=user_email,
                query=f"name contains '{query}' or fullText contains '{query}'",
                page_size=15
            )
            
            # Process and categorize results
            categorized_results = {
                "documents": [],
                "spreadsheets": [],
                "presentations": [],
                "pdfs": [],
                "images": [],
                "other": []
            }
            
            for file_info in search_results.get('files', []):
                mime_type = file_info.get('mimeType', '')
                file_entry = {
                    "id": file_info.get('id'),
                    "name": file_info.get('name'),
                    "web_view_link": file_info.get('webViewLink'),
                    "modified_time": file_info.get('modifiedTime'),
                    "relevance_score": "high" if query.lower() in file_info.get('name', '').lower() else "medium"
                }
                
                if 'document' in mime_type:
                    categorized_results["documents"].append(file_entry)
                elif 'spreadsheet' in mime_type:
                    categorized_results["spreadsheets"].append(file_entry)
                elif 'presentation' in mime_type:
                    categorized_results["presentations"].append(file_entry)
                elif 'pdf' in mime_type:
                    categorized_results["pdfs"].append(file_entry)
                elif 'image' in mime_type:
                    categorized_results["images"].append(file_entry)
                else:
                    categorized_results["other"].append(file_entry)
            
            return {
                "search_query": query,
                "user_email": user_email,
                "total_results": len(search_results.get('files', [])),
                "results_by_type": categorized_results,
                "suggested_email_content": {
                    "references": [f"📄 {file['name']}" for file in search_results.get('files', [])[:5]],
                    "links": [file.get('webViewLink') for file in search_results.get('files', [])[:3]],
                    "attachment_suggestions": [
                        file for file in search_results.get('files', [])
                        if file.get('mimeType', '').startswith('application/')
                    ][:3]
                },
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error searching workspace content: {e}")
            return {
                "error": f"Failed to search workspace content: {str(e)}",
                "search_query": query,
                "timestamp": datetime.now().isoformat()
            }
    
    @mcp.resource(
        uri="gmail://content/suggestions",
        name="Gmail Content Suggestions",
        description="Dynamic content suggestions for Gmail composition based on user's recent activity, workspace content, and email patterns",
        mime_type="application/json",
        tags={"gmail", "suggestions", "content", "dynamic", "workspace", "email", "composition"}
    )
    async def get_gmail_content_suggestions(ctx: Context) -> dict:
        """Generate dynamic content suggestions for Gmail composition."""
        user_email = get_user_email_context()
        if not user_email:
            return {
                "error": "No authenticated user found in current session"
            }
        
        try:
            # Get recent workspace content for suggestions
            workspace_content = await get_recent_workspace_content(ctx)
            
            # Generate suggestions based on available content
            suggestions = {
                "quick_links": {
                    "description": "Recent documents to reference in emails",
                    "items": []
                },
                "meeting_materials": {
                    "description": "Documents suitable for meeting agendas",
                    "items": []
                },
                "project_updates": {
                    "description": "Files that could be project-related",
                    "items": []
                },
                "shared_resources": {
                    "description": "Documents suitable for sharing",
                    "items": []
                }
            }
            
            # Process workspace content if available
            if not workspace_content.get('error'):
                content_by_type = workspace_content.get('content_by_type', {})
                
                # Add documents to quick links
                for doc in content_by_type.get('documents', [])[:5]:
                    suggestions["quick_links"]["items"].append({
                        "name": doc['name'],
                        "url": doc['web_view_link'],
                        "type": "document",
                        "modified": doc['modified_time']
                    })
                
                # Add presentations to meeting materials
                for pres in content_by_type.get('presentations', [])[:3]:
                    suggestions["meeting_materials"]["items"].append({
                        "name": pres['name'],
                        "url": pres['web_view_link'],
                        "type": "presentation",
                        "modified": pres['modified_time']
                    })
                
                # Add spreadsheets to project updates
                for sheet in content_by_type.get('spreadsheets', [])[:3]:
                    suggestions["project_updates"]["items"].append({
                        "name": sheet['name'],
                        "url": sheet['web_view_link'],
                        "type": "spreadsheet",
                        "modified": sheet['modified_time']
                    })
            
            # Add email composition templates
            email_templates = {
                "status_update": {
                    "subject_template": "Weekly Status Update - {date}",
                    "opening_lines": [
                        "Hope everyone is doing well. Here's this week's progress update:",
                        "Quick update on our current projects and milestones:",
                        "Here's where we stand on our key initiatives:"
                    ]
                },
                "meeting_follow_up": {
                    "subject_template": "Follow-up: {meeting_topic}",
                    "opening_lines": [
                        "Thank you for the productive meeting today. Here are the key takeaways:",
                        "Following up on our discussion about {topic}:",
                        "As discussed in today's meeting, here are the next steps:"
                    ]
                },
                "document_sharing": {
                    "subject_template": "Sharing: {document_name}",
                    "opening_lines": [
                        "Please find the attached/linked document for your review:",
                        "I've prepared the {document_type} we discussed:",
                        "Here's the document you requested:"
                    ]
                }
            }
            
            return {
                "user_email": user_email,
                "content_suggestions": suggestions,
                "email_templates": email_templates,
                "dynamic_variables": {
                    "current_date": datetime.now().strftime("%B %d, %Y"),
                    "current_week": f"Week of {datetime.now().strftime('%B %d, %Y')}",
                    "user_first_name": user_email.split('@')[0].split('.')[0].capitalize(),
                    "user_domain": user_email.split('@')[1] if '@' in user_email else 'company.com'
                },
                "workspace_integration": {
                    "available_docs": len(workspace_content.get('content_by_type', {}).get('documents', [])),
                    "available_sheets": len(workspace_content.get('content_by_type', {}).get('spreadsheets', [])),
                    "available_presentations": len(workspace_content.get('content_by_type', {}).get('presentations', []))
                },
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating Gmail content suggestions: {e}")
            return {
                "error": f"Failed to generate content suggestions: {str(e)}",
                "user_email": user_email,
                "timestamp": datetime.now().isoformat()
            }
    
    @mcp.resource(
        uri="gmail://allow-list",
        name="Gmail Allow List",
        description="Get the configured Gmail allow list for send_gmail_message tool - recipients on this list skip elicitation confirmation",
        mime_type="application/json",
        tags={"gmail", "allow-list", "security", "elicitation", "trusted", "recipients"},
        meta={
            "response_model": "GmailAllowListResponse",
            "enhanced": True,
            "security_related": True
        }
    )
    async def get_gmail_allow_list_resource(ctx: Context) -> GmailAllowListResponse:
        """Internal implementation for Gmail allow list resource."""
        from config.settings import settings
        
        user_email = get_user_email_context()
        if not user_email:
            return GmailAllowListResponse(
                error="No authenticated user found in current session",
                user_email="",
                allow_list=[],
                count=0,
                description="Authentication required",
                last_updated="unknown",
                timestamp=datetime.now().isoformat()
            )
        
        try:
            # Get the allow list from settings
            allow_list = settings.get_gmail_allow_list()
            
            # Check if the environment variable is configured
            raw_value = settings.gmail_allow_list
            is_configured = bool(raw_value and raw_value.strip())
            
            return GmailAllowListResponse(
                user_email=user_email,
                allow_list=allow_list,
                count=len(allow_list),
                description="Recipients in this list will skip elicitation confirmation when sending emails",
                last_updated=datetime.now().isoformat(),
                timestamp=datetime.now().isoformat()
            )
            
        except Exception as e:
            logger.error(f"Error retrieving Gmail allow list: {e}")
            return GmailAllowListResponse(
                error=f"Failed to retrieve Gmail allow list: {str(e)}",
                user_email=user_email,
                allow_list=[],
                count=0,
                description="Error occurred",
                last_updated="unknown",
                timestamp=datetime.now().isoformat()
            )
    
    logger.info("✅ User and authentication resources registered")


def get_current_user_email_simple() -> str:
    """Utility function to get current user email for tools.
    
    This is a synchronous helper that tools can use to get the current
    user's email without dealing with async resource access.
    
    Returns:
        The current user's email address
        
    Raises:
        ValueError: If no authenticated user is found
    """
    user_email = get_user_email_context()
    if not user_email:
        raise ValueError(
            "No authenticated user found in current session. "
            "Please ensure the user is authenticated with start_google_auth tool first."
        )
    return user_email