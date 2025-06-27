"""User and authentication resource templates for FastMCP2 Google Workspace Platform.

This module provides FastMCP resources and templates that expose authenticated user
information, eliminating the need for tools to manually require user_google_email parameters.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from fastmcp import FastMCP, Context
from auth.context import (
    get_user_email_context,
    get_session_context,
    get_session_data,
    list_sessions
)
from auth.google_auth import get_valid_credentials

logger = logging.getLogger(__name__)


def setup_user_resources(mcp: FastMCP) -> None:
    """Setup all user and authentication resources."""
    
    @mcp.resource(
        uri="user://current/email",
        name="Current User Email",
        description="Get the currently authenticated user's email address for session-based authentication",
        mime_type="application/json",
        tags={"authentication", "user", "email", "session"}
    )
    async def get_current_user_email(ctx: Context) -> dict:
        """Internal implementation for current user email resource."""
        user_email = get_user_email_context()
        if not user_email:
            return {
                "error": "No authenticated user found in current session",
                "suggestion": "Use start_google_auth tool to authenticate first"
            }
        
        return {
            "email": user_email,
            "session_id": get_session_context(),
            "timestamp": datetime.now().isoformat()
        }
    
    @mcp.resource(
        uri="user://current/profile",
        name="Current User Profile",
        description="Comprehensive profile information including authentication status, credential validity, and available Google services for the current session user",
        mime_type="application/json",
        tags={"authentication", "user", "profile", "credentials", "session", "google"}
    )
    async def get_current_user_profile(ctx: Context) -> dict:
        """Internal implementation for current user profile resource."""
        user_email = get_user_email_context()
        if not user_email:
            return {
                "error": "No authenticated user found in current session",
                "authenticated": False
            }
        
        # Check credential validity
        credentials = get_valid_credentials(user_email)
        auth_status = {
            "authenticated": credentials is not None,
            "credentials_valid": credentials is not None and not credentials.expired,
            "has_refresh_token": credentials is not None and credentials.refresh_token is not None,
            "scopes": credentials.scopes if credentials else [],
            "expires_at": credentials.expiry.isoformat() if credentials and credentials.expiry else None
        }
        
        return {
            "email": user_email,
            "session_id": get_session_context(),
            "auth_status": auth_status,
            "timestamp": datetime.now().isoformat()
        }
    
    @mcp.resource(
        uri="user://profile/{email}",
        name="User Profile by Email",
        description="Get detailed profile information for a specific user email including authentication status, credential validity, and comparison with current session user",
        mime_type="application/json",
        tags={"user", "profile", "authentication", "credentials", "email", "lookup"}
    )
    async def get_user_profile_by_email(email: str, ctx: Context) -> dict:
        """Internal implementation for user profile by email resource."""
        # Check credential validity for the specified user
        credentials = get_valid_credentials(email)
        auth_status = {
            "authenticated": credentials is not None,
            "credentials_valid": credentials is not None and not credentials.expired,
            "has_refresh_token": credentials is not None and credentials.refresh_token is not None,
            "scopes": credentials.scopes if credentials else [],
            "expires_at": credentials.expiry.isoformat() if credentials and credentials.expiry else None
        }
        
        return {
            "email": email,
            "auth_status": auth_status,
            "is_current_user": email == get_user_email_context(),
            "timestamp": datetime.now().isoformat()
        }
    
    @mcp.resource(
        uri="auth://session/current",
        name="Current Authentication Session",
        description="Detailed information about the current authentication session including token status, expiration times, and granted scopes",
        mime_type="application/json",
        tags={"authentication", "session", "oauth", "token", "security"}
    )
    async def get_current_session_info(ctx: Context) -> dict:
        """Internal implementation for current session info resource."""
        session_id = get_session_context()
        user_email = get_user_email_context()
        
        if not session_id:
            return {
                "error": "No active session found",
                "session_active": False
            }
        
        # Get session metadata if available
        session_data = {
            "session_id": session_id,
            "user_email": user_email,
            "session_active": True,
            "timestamp": datetime.now().isoformat()
        }
        
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
        tags={"authentication", "sessions", "admin", "multi-user", "management", "security"}
    )
    async def list_active_sessions(ctx: Context) -> dict:
        """Internal implementation for active sessions list resource."""
        try:
            active_sessions = list_sessions()
            
            return {
                "active_sessions": active_sessions,
                "count": len(active_sessions),
                "current_session": get_session_context(),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error listing sessions: {e}")
            return {
                "error": f"Failed to list sessions: {str(e)}",
                "active_sessions": [],
                "count": 0
            }
    
    @mcp.resource(
        uri="auth://credentials/{email}/status",
        name="User Credential Status",
        description="Detailed credential status for a specific user including validity, expiration, refresh token availability, and granted scopes for authentication management",
        mime_type="application/json",
        tags={"authentication", "credentials", "status", "oauth", "tokens", "security", "user"}
    )
    async def get_credential_status(email: str, ctx: Context) -> dict:
        """Internal implementation for credential status resource."""
        try:
            credentials = get_valid_credentials(email)
            
            if not credentials:
                return {
                    "email": email,
                    "status": "no_credentials",
                    "authenticated": False,
                    "message": "No stored credentials found for this user"
                }
            
            status_info = {
                "email": email,
                "authenticated": True,
                "credentials_valid": not credentials.expired,
                "expired": credentials.expired,
                "has_refresh_token": credentials.refresh_token is not None,
                "scopes": credentials.scopes or [],
                "client_id": credentials.client_id[:10] + "..." if credentials.client_id else None,
                "token_uri": credentials.token_uri,
                "expires_at": credentials.expiry.isoformat() if credentials.expiry else None,
                "timestamp": datetime.now().isoformat()
            }
            
            if credentials.expired:
                status_info["status"] = "expired"
                status_info["message"] = "Credentials are expired but can be refreshed"
            else:
                status_info["status"] = "valid"
                status_info["message"] = "Credentials are valid and active"
            
            return status_info
            
        except Exception as e:
            logger.error(f"Error checking credentials for {email}: {e}")
            return {
                "email": email,
                "status": "error",
                "authenticated": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
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
            raise ValueError("No authenticated user found in current session. Use start_google_auth tool first.")
        
        return user_email
    
    @mcp.resource(
        uri="google://services/scopes/{service}",
        name="Google Service Scopes",
        description="Get the required OAuth scopes, API version, and configuration details for a specific Google service including Drive, Gmail, Calendar, and other Workspace APIs",
        mime_type="application/json",
        tags={"google", "services", "scopes", "oauth", "api", "configuration", "workspace"}
    )
    async def get_service_scopes(service: str, ctx: Context) -> dict:
        """Internal implementation for Google service scopes resource."""
        # Import here to avoid circular imports
        from auth.service_helpers import SERVICE_DEFAULTS
        
        service_info = SERVICE_DEFAULTS.get(service.lower())
        if not service_info:
            return {
                "error": f"Unknown Google service: {service}",
                "available_services": list(SERVICE_DEFAULTS.keys())
            }
        
        return {
            "service": service,
            "default_scopes": service_info.get("default_scopes", []),
            "version": service_info.get("version", "v1"),
            "description": service_info.get("description", f"Google {service.title()} API"),
            "timestamp": datetime.now().isoformat()
        }
    
    @mcp.resource(
        uri="tools://list/all",
        name="Complete Tools Directory",
        description="Comprehensive catalog of all 60+ available tools organized by category including Drive, Gmail, Calendar, Chat, Forms, Docs, Sheets, and authentication tools with detailed capability descriptions",
        mime_type="application/json",
        tags={"tools", "directory", "catalog", "discovery", "google", "workspace", "enhanced", "legacy"}
    )
    async def get_all_tools_list(ctx: Context) -> dict:
        """Internal implementation for complete tools directory resource."""
        try:
            tools_info = {
                "enhanced_tools": {
                    "description": "New tools that use resource templating (no email params needed)",
                    "tools": [
                        {
                            "name": "list_my_drive_files",
                            "description": "List Drive files (no email param needed!)",
                            "parameters": ["query", "page_size"]
                        },
                        {
                            "name": "search_my_gmail",
                            "description": "Search Gmail messages (auto-authenticated)",
                            "parameters": ["query", "max_results"]
                        },
                        {
                            "name": "create_my_calendar_event",
                            "description": "Create calendar events (seamless auth)",
                            "parameters": ["summary", "start_time", "end_time", "description", "attendees", "calendar_id"]
                        },
                        {
                            "name": "get_my_auth_status",
                            "description": "Check authentication status",
                            "parameters": []
                        }
                    ]
                },
                "drive_tools": {
                    "description": "Google Drive file management tools",
                    "tool_count": 5,
                    "requires_email": True
                },
                "gmail_tools": {
                    "description": "Gmail email management tools",
                    "tool_count": 11,
                    "requires_email": True
                },
                "docs_tools": {
                    "description": "Google Docs document management tools",
                    "tool_count": 4,
                    "requires_email": True
                },
                "forms_tools": {
                    "description": "Google Forms creation and management tools",
                    "tool_count": 8,
                    "requires_email": True
                },
                "calendar_tools": {
                    "description": "Google Calendar event management tools",
                    "tool_count": 6,
                    "requires_email": True
                },
                "slides_tools": {
                    "description": "Google Slides presentation tools",
                    "tool_count": 5,
                    "requires_email": True
                },
                "sheets_tools": {
                    "description": "Google Sheets spreadsheet tools",
                    "tool_count": 6,
                    "requires_email": True
                },
                "chat_tools": {
                    "description": "Google Chat messaging tools",
                    "tool_count": 12,
                    "requires_email": True
                },
                "auth_tools": {
                    "description": "Authentication and system tools",
                    "tool_count": 4,
                    "requires_email": "mixed"
                },
                "qdrant_tools": {
                    "description": "Qdrant search and analytics tools",
                    "tool_count": 3,
                    "requires_email": False
                }
            }
            
            # Calculate total tools (59 from original + 4 enhanced)
            total_tools = 63
            
            return {
                "total_tools": total_tools,
                "total_categories": len(tools_info),
                "enhanced_tools_count": len(tools_info["enhanced_tools"]["tools"]),
                "tools_by_category": tools_info,
                "timestamp": datetime.now().isoformat(),
                "resource_templating_available": True,
                "migration_status": "✅ Resource templating implemented - enhanced tools available!"
            }
            
        except Exception as e:
            logger.error(f"Error generating tools list: {e}")
            return {
                "error": f"Failed to generate tools list: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    @mcp.resource(
        uri="tools://enhanced/list",
        name="Enhanced Tools Collection",
        description="Curated list of enhanced tools that use automatic resource templating - no user_google_email parameters required, seamless authentication through OAuth session context",
        mime_type="application/json",
        tags={"tools", "enhanced", "templating", "oauth", "seamless", "modern", "no-email"}
    )
    async def get_enhanced_tools_only(ctx: Context) -> dict:
        """Internal implementation for enhanced tools collection resource."""
        enhanced_tools = [
            {
                "name": "list_my_drive_files",
                "description": "List files in your Google Drive without needing to specify email",
                "parameters": {
                    "query": "Google Drive query string (optional, default: list all)",
                    "page_size": "Number of files to return (optional, default: 25)"
                },
                "example": "list_my_drive_files('name contains \"report\"', 10)"
            },
            {
                "name": "search_my_gmail",
                "description": "Search your Gmail messages with automatic authentication",
                "parameters": {
                    "query": "Gmail search query (required)",
                    "max_results": "Maximum results to return (optional, default: 10)"
                },
                "example": "search_my_gmail('from:boss@company.com', 5)"
            },
            {
                "name": "create_my_calendar_event",
                "description": "Create calendar event with seamless authentication",
                "parameters": {
                    "summary": "Event title (required)",
                    "start_time": "Start time in RFC3339 format (required)",
                    "end_time": "End time in RFC3339 format (required)",
                    "description": "Event description (optional)",
                    "attendees": "List of attendee emails (optional)",
                    "calendar_id": "Calendar ID (optional, default: 'primary')"
                },
                "example": "create_my_calendar_event('Team Meeting', '2025-02-01T10:00:00Z', '2025-02-01T11:00:00Z')"
            },
            {
                "name": "get_my_auth_status",
                "description": "Check your authentication status across all Google services",
                "parameters": {},
                "example": "get_my_auth_status()"
            }
        ]
        
        return {
            "enhanced_tools": enhanced_tools,
            "count": len(enhanced_tools),
            "benefit": "No user_google_email parameter required - uses OAuth session automatically",
            "timestamp": datetime.now().isoformat()
        }
    
    @mcp.resource(
        uri="tools://usage/guide",
        name="Comprehensive Tools Usage Guide",
        description="Complete usage guide with examples, workflows, and best practices for both enhanced and legacy tools including authentication flows, migration examples, and error handling patterns",
        mime_type="application/json",
        tags={"tools", "guide", "usage", "examples", "workflows", "migration", "authentication", "best-practices"}
    )
    async def get_tool_usage_guide(ctx: Context) -> dict:
        """Internal implementation for comprehensive tools usage guide resource."""
        return {
            "quick_start": {
                "step_1": "Authenticate with: start_google_auth('your.email@gmail.com')",
                "step_2": "Check status with: get_my_auth_status() (enhanced tool - no email needed!)",
                "step_3": "Use tools: list_my_drive_files() or search_my_gmail('your query')"
            },
            "enhanced_tools_workflow": {
                "description": "New tools that don't require email parameters",
                "authentication": "Automatic from OAuth session",
                "examples": {
                    "drive": "list_my_drive_files('name contains \"report\"')",
                    "gmail": "search_my_gmail('from:boss@company.com')",
                    "calendar": "create_my_calendar_event('Meeting', '2025-02-01T10:00:00Z', '2025-02-01T11:00:00Z')",
                    "status": "get_my_auth_status()"
                }
            },
            "legacy_tools_workflow": {
                "description": "Original tools that require email parameters",
                "authentication": "Manual email parameter required",
                "examples": {
                    "drive": "search_drive_files('user@gmail.com', 'name contains \"report\"')",
                    "gmail": "search_gmail_messages('user@gmail.com', 'from:boss@company.com')",
                    "docs": "search_docs('user@gmail.com', 'meeting notes')"
                }
            },
            "migration_guide": {
                "from": "search_drive_files('user@gmail.com', 'query')",
                "to": "list_my_drive_files('query')",
                "benefit": "No need to remember or type your email address"
            },
            "error_handling": {
                "no_auth": "Enhanced tools will show: '❌ Authentication error: No authenticated user found'",
                "solution": "Run start_google_auth('your.email@gmail.com') first"
            },
            "timestamp": datetime.now().isoformat()
        }
    
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