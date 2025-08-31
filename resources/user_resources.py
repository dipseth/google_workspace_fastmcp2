"""User and authentication resource templates for FastMCP2 Google Workspace Platform.

This module provides FastMCP resources and templates that expose authenticated user
information, eliminating the need for tools to manually require user_google_email parameters.
"""

import logging
from typing_extensions import Dict, Any, Optional
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
        session_id = get_session_context()
        
        # DIAGNOSTIC: Log context state for debugging OAuth vs start_google_auth disconnect
        logger.info(f"🔍 DEBUG: get_current_user_profile called")
        logger.info(f"   user_email_context: {user_email}")
        logger.info(f"   session_context: {session_id}")
        
        if not user_email:
            return {
                "error": "No authenticated user found in current session",
                "authenticated": False,
                "debug_info": {
                    "user_email_context": user_email,
                    "session_context": session_id,
                    "issue": "OAuth proxy authentication may not be setting session context"
                }
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
            # Return a helpful error message as string instead of raising exception
            # This follows FastMCP2 resource patterns - resources should return data gracefully
            return "❌ Authentication error: No authenticated user found in current session. Use start_google_auth tool first."
        
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
                    "tool_count": 6,
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
    
    @mcp.resource(
        uri="workspace://content/recent",
        name="Recent Google Workspace Content",
        description="List of recently accessed Google Docs, Sheets, Drive files, and other Workspace content for dynamic email composition and content linking",
        mime_type="application/json",
        tags={"workspace", "content", "drive", "docs", "sheets", "recent", "gmail", "email"}
    )
    async def get_recent_workspace_content(ctx: Context) -> dict:
        """Get recent Google Workspace content for email composition."""
        user_email = get_user_email_context()
        if not user_email:
            return {
                "error": "No authenticated user found in current session",
                "suggestion": "Use start_google_auth tool to authenticate first"
            }
        
        try:
            # Import here to avoid circular imports
            from drive.drive_tools import search_drive_files
            from docs.docs_tools import search_docs
            from sheets.sheets_tools import get_spreadsheets
            
            # Get recent Drive files (last 30 days)
            recent_files = await search_drive_files(
                user_google_email=user_email,
                query="modifiedTime > '2025-01-01' and trashed=false",
                page_size=20
            )
            
            # Get recent Docs (if available)
            try:
                recent_docs = await search_docs(
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
    async def search_workspace_content(query: str, ctx: Context) -> dict:
        """Search Google Workspace content for email composition."""
        user_email = get_user_email_context()
        if not user_email:
            return {
                "error": "No authenticated user found in current session",
                "query": query
            }
        
        try:
            # Import here to avoid circular imports
            from drive.drive_tools import search_drive_files
            
            # Search Drive files
            search_results = await search_drive_files(
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
        tags={"gmail", "allow-list", "security", "elicitation", "trusted", "recipients"}
    )
    async def get_gmail_allow_list_resource(ctx: Context) -> dict:
        """Internal implementation for Gmail allow list resource."""
        from config.settings import settings
        
        user_email = get_user_email_context()
        if not user_email:
            return {
                "error": "No authenticated user found in current session",
                "authenticated": False,
                "allow_list": []
            }
        
        try:
            # Get the allow list from settings
            allow_list = settings.get_gmail_allow_list()
            
            # Check if the environment variable is configured
            raw_value = settings.gmail_allow_list
            is_configured = bool(raw_value and raw_value.strip())
            
            # Mask emails for privacy in the response
            masked_list = []
            if allow_list:
                for email in allow_list:
                    if '@' in email:
                        local, domain = email.split('@', 1)
                        if len(local) > 3:
                            masked = f"{local[:2]}***@{domain}"
                        else:
                            masked = f"***@{domain}"
                    else:
                        masked = email[:3] + "***" if len(email) > 3 else "***"
                    masked_list.append(masked)
            
            return {
                "authenticated_user": user_email,
                "is_configured": is_configured,
                "environment_variable": "GMAIL_ALLOW_LIST",
                "allow_list_count": len(allow_list),
                "allow_list": allow_list,  # Full list for internal use
                "masked_list": masked_list,  # Privacy-protected list for display
                "timestamp": datetime.now().isoformat(),
                "description": "Recipients in this list will skip elicitation confirmation when sending emails",
                "configuration_format": "Comma-separated email addresses in GMAIL_ALLOW_LIST environment variable"
            }
            
        except Exception as e:
            logger.error(f"Error retrieving Gmail allow list: {e}")
            return {
                "error": f"Failed to retrieve Gmail allow list: {str(e)}",
                "authenticated_user": user_email,
                "allow_list": [],
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