"""
Enhanced Dynamic Service List Resources for FastMCP2 - Refactored with Tag-Based Discovery.

This module provides dynamic resources that expose list-based tools from various Google services
through a standardized hierarchical resource pattern with comprehensive documentation and defaults.

Key Changes in this refactored version:
- Uses tool tags to identify list tools instead of complex type introspection
- Uses FastMCP's forward() pattern for calling tools
- Simplified tool configuration relying on tags
- Removed complex field mapping discovery

Resource Hierarchy:
1. service://{service}/lists - Returns available list types for the service
2. service://{service}/{list_type} - Returns all IDs/items for that list type  
3. service://{service}/{list_type}/{id} - Returns detailed data for a specific ID
4. service://{service}/path/{path*} - Hierarchical path access (wildcard)

Examples:
- service://forms/lists → ["form_responses"]
- service://forms/form_responses → [list of form IDs]
- service://forms/form_responses/abc123 → [actual form responses for form abc123]
"""

import logging
import json
import asyncio
from typing import Dict, List, Any, Optional, Set, Tuple, Union
from typing_extensions import TypedDict, NotRequired
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field, field_validator, ConfigDict, create_model
from fastmcp import FastMCP, Context
from fastmcp.tools import Tool
from fastmcp.tools.tool_transform import ArgTransform, forward

logger = logging.getLogger(__name__)

# Import from our centralized sources of truth
try:
    from auth.service_helpers import SERVICE_DEFAULTS
    from auth.scope_registry import ScopeRegistry, ServiceScopeManager
    logger.info("Successfully imported service configuration from auth module")
except ImportError as e:
    logger.warning(f"Could not import from auth module: {e}, using fallback")
    SERVICE_DEFAULTS = None
    ScopeRegistry = None

# Import authentication context functions
try:
    from auth.context import get_user_email_context, get_session_context
    from auth.google_auth import get_valid_credentials
    logger.info("Successfully imported authentication context functions")
except ImportError as e:
    logger.warning(f"Could not import authentication functions: {e}")
    get_user_email_context = None
    get_valid_credentials = None


# ============================================================================
# SERVICE METADATA AND DOCUMENTATION
# ============================================================================

class ServiceMetadata:
    """Comprehensive metadata for each Google service."""
    
    METADATA = {
        "gmail": {
            "display_name": "Gmail",
            "description": "Email service with powerful search, filtering, and organization features",
            "icon": "📧",
            "version": "v1",
            "categories": ["communication", "productivity"],
            "default_page_size": 25,
            "max_page_size": 100,
            "features": {
                "filters": "Automatic email filtering rules",
                "labels": "Organizational labels and categories",
                "threads": "Conversation threading",
                "search": "Advanced search capabilities"
            },
            "common_use_cases": [
                "Email automation",
                "Filter management",
                "Label organization",
                "Bulk operations"
            ]
        },
        "drive": {
            "display_name": "Google Drive",
            "description": "Cloud storage and file synchronization service",
            "icon": "📁",
            "version": "v3",
            "categories": ["storage", "collaboration"],
            "default_page_size": 50,
            "max_page_size": 1000,
            "features": {
                "folders": "Hierarchical folder structure",
                "sharing": "File and folder sharing",
                "versions": "File version history",
                "search": "Content and metadata search"
            },
            "common_use_cases": [
                "File organization",
                "Document collaboration",
                "Backup and sync",
                "Media storage"
            ]
        },
        "calendar": {
            "display_name": "Google Calendar",
            "description": "Time management and scheduling service",
            "icon": "📅",
            "version": "v3",
            "categories": ["scheduling", "productivity"],
            "default_page_size": 10,
            "max_page_size": 250,
            "features": {
                "events": "Event creation and management",
                "calendars": "Multiple calendar support",
                "reminders": "Event notifications",
                "sharing": "Calendar sharing and permissions"
            },
            "common_use_cases": [
                "Meeting scheduling",
                "Event management",
                "Team coordination",
                "Availability tracking"
            ]
        },
        "forms": {
            "display_name": "Google Forms",
            "description": "Survey and form creation service",
            "icon": "📝",
            "version": "v1",
            "categories": ["data-collection", "survey"],
            "default_page_size": 20,
            "max_page_size": 100,
            "features": {
                "responses": "Response collection and analysis",
                "questions": "Various question types",
                "validation": "Response validation rules",
                "collaboration": "Multi-user form editing"
            },
            "common_use_cases": [
                "Survey creation",
                "Data collection",
                "Event registration",
                "Feedback forms"
            ]
        },
        "sheets": {
            "display_name": "Google Sheets",
            "description": "Spreadsheet and data analysis service",
            "icon": "📊",
            "version": "v4",
            "categories": ["data", "productivity"],
            "default_page_size": 30,
            "max_page_size": 200,
            "features": {
                "formulas": "Advanced formula support",
                "charts": "Data visualization",
                "collaboration": "Real-time collaboration",
                "automation": "Macro and script support"
            },
            "common_use_cases": [
                "Data analysis",
                "Budget tracking",
                "Project management",
                "Report generation"
            ]
        },
        "docs": {
            "display_name": "Google Docs",
            "description": "Document creation and collaboration service",
            "icon": "📄",
            "version": "v1",
            "categories": ["documents", "collaboration"],
            "default_page_size": 20,
            "max_page_size": 100,
            "features": {
                "editing": "Real-time collaborative editing",
                "comments": "Commenting and suggestions",
                "revision": "Version history",
                "templates": "Document templates"
            },
            "common_use_cases": [
                "Document creation",
                "Team collaboration",
                "Report writing",
                "Content management"
            ]
        },
        "photos": {
            "display_name": "Google Photos",
            "description": "Photo and video storage service",
            "icon": "📷",
            "version": "v1",
            "categories": ["media", "storage"],
            "default_page_size": 50,
            "max_page_size": 100,
            "features": {
                "albums": "Photo album organization",
                "sharing": "Album and photo sharing",
                "search": "AI-powered photo search",
                "editing": "Basic photo editing"
            },
            "common_use_cases": [
                "Photo backup",
                "Album creation",
                "Media sharing",
                "Memory preservation"
            ]
        },
        "chat": {
            "display_name": "Google Chat",
            "description": "Team messaging and collaboration platform",
            "icon": "💬",
            "version": "v1",
            "categories": ["communication", "collaboration"],
            "default_page_size": 20,
            "max_page_size": 100,
            "features": {
                "spaces": "Team spaces and rooms",
                "messages": "Direct and group messaging",
                "bots": "Bot integration",
                "threads": "Threaded conversations"
            },
            "common_use_cases": [
                "Team communication",
                "Project discussions",
                "Bot automation",
                "Information sharing"
            ]
        },
        "slides": {
            "display_name": "Google Slides",
            "description": "Presentation creation and sharing service",
            "icon": "🎯",
            "version": "v1",
            "categories": ["presentations", "collaboration"],
            "default_page_size": 15,
            "max_page_size": 100,
            "features": {
                "themes": "Presentation themes",
                "animations": "Slide transitions",
                "collaboration": "Real-time editing",
                "presenter": "Presenter tools"
            },
            "common_use_cases": [
                "Presentation creation",
                "Team presentations",
                "Training materials",
                "Visual communication"
            ]
        }
    }
    
    @classmethod
    def get_service_info(cls, service: str) -> Dict[str, Any]:
        """Get comprehensive metadata for a service."""
        return cls.METADATA.get(service.lower(), {
            "display_name": service.title(),
            "description": f"{service.title()} service",
            "icon": "🔧",
            "version": "v1",
            "categories": ["general"],
            "default_page_size": 25,
            "max_page_size": 100,
            "features": {},
            "common_use_cases": []
        })
    
    @classmethod
    def get_all_services(cls) -> List[str]:
        """Get list of all documented services."""
        return list(cls.METADATA.keys())
    
    @classmethod
    def generate_service_documentation(cls, service: str) -> str:
        """Generate comprehensive documentation for a service."""
        info = cls.get_service_info(service)
        
        doc = f"""
# {info['icon']} {info['display_name']} Service

**Description:** {info['description']}  
**API Version:** {info['version']}  
**Categories:** {', '.join(info['categories'])}

## Features

"""
        for feature, description in info['features'].items():
            doc += f"- **{feature.title()}:** {description}\n"
        
        doc += "\n## Common Use Cases\n\n"
        for use_case in info['common_use_cases']:
            doc += f"- {use_case}\n"
        
        doc += f"""

## Default Settings

- **Default Page Size:** {info['default_page_size']} items
- **Maximum Page Size:** {info['max_page_size']} items
"""
        return doc


def _get_valid_services() -> List[str]:
    """
    Dynamically get the list of valid services from SERVICE_DEFAULTS.
    Falls back to ServiceMetadata if SERVICE_DEFAULTS is not available.
    """
    if SERVICE_DEFAULTS:
        return list(SERVICE_DEFAULTS.keys())
    else:
        # Fallback to documented services
        return ServiceMetadata.get_all_services()


# Dynamic service list with enhanced documentation
VALID_SERVICES = _get_valid_services()

# Create a type alias for supported services
SupportedService = str

def get_supported_service_documentation() -> str:
    """
    Generate documentation string for supported services.
    """
    service_docs = []
    for service in VALID_SERVICES:
        info = ServiceMetadata.get_service_info(service)
        service_docs.append(f"- **{service}** ({info['icon']}): {info['description']}")
    
    doc_string = f"""
Supported Google service identifier.

Available Services:
{chr(10).join(service_docs)}

Example: 'gmail', 'drive', 'calendar'
"""
    return doc_string


def get_supported_services() -> List[str]:
    """Get the list of supported services dynamically from SERVICE_DEFAULTS.
    
    Returns:
        List of supported service names with metadata
    """
    return list(VALID_SERVICES)


logger.info(f"SupportedService type created for services: {get_supported_services()}")


# ============================================================================
# PYDANTIC MODELS WITH ENHANCED DOCUMENTATION AND DEFAULTS
# ============================================================================

class ServiceRequest(BaseModel):
    """Request model for service parameter validation with rich defaults."""
    model_config = ConfigDict(
        json_schema_extra={
            "title": "Service Request",
            "description": "Request parameters for service operations",
            "examples": [
                {"service": "gmail"},
                {"service": "drive"},
                {"service": "calendar"}
            ]
        }
    )
    
    service: str = Field(
        ...,
        description=f"The Google service name. Supported services: {', '.join(get_supported_services())}",
        json_schema_extra={
            "example": "gmail",
            "enum": get_supported_services(),
            "documentation": get_supported_service_documentation()
        }
    )
    
    @field_validator('service')
    @classmethod
    def validate_service(cls, v: str) -> str:
        """Validate that the service is supported dynamically."""
        valid_services = get_supported_services()
        
        if v.lower() not in valid_services:
            available = ', '.join(sorted(valid_services))
            # Enhanced error message with suggestions
            suggestions = [s for s in valid_services if s.startswith(v[0].lower())]
            error_msg = f"Service '{v}' not supported. Available services: {available}"
            if suggestions:
                error_msg += f"\nDid you mean: {', '.join(suggestions)}?"
            raise ValueError(error_msg)
        return v.lower()


class ServiceListRequest(ServiceRequest):
    """Request model for service list type queries with pagination defaults."""
    list_type: str = Field(
        ..., 
        description="The type of list to retrieve (e.g., 'filters', 'labels', 'albums')",
        json_schema_extra={"example": "filters"}
    )
    
    # Add pagination with defaults
    page_size: int = Field(
        default=None,  # Will use service-specific default
        description="Number of items to return per page",
        ge=1,
        le=1000
    )
    
    page_token: Optional[str] = Field(
        default=None,
        description="Token for pagination to get next page of results"
    )
    
    @field_validator('list_type')
    @classmethod
    def validate_list_type(cls, v: str) -> str:
        """Normalize list type to lowercase."""
        return v.lower().strip()
    
    @field_validator('page_size')
    @classmethod
    def validate_page_size(cls, v: Optional[int], values) -> int:
        """Set service-specific default page size if not provided."""
        if v is None:
            # Get service from values
            service = values.data.get('service', 'gmail')
            info = ServiceMetadata.get_service_info(service)
            return info['default_page_size']
        return v


class ServiceItemRequest(ServiceListRequest):
    """Request model for service item detail queries."""
    item_id: str = Field(
        ..., 
        description="The unique identifier for the specific item",
        json_schema_extra={"example": "filter_123"}
    )
    
    # Add optional fields with defaults
    include_metadata: bool = Field(
        default=True,
        description="Include metadata in response"
    )
    
    include_raw: bool = Field(
        default=False,
        description="Include raw API response data"
    )
    
    @field_validator('item_id')
    @classmethod
    def validate_item_id(cls, v: str) -> str:
        """Validate item ID is not empty."""
        if not v or not v.strip():
            raise ValueError("Item ID cannot be empty")
        return v.strip()


# ============================================================================
# ENHANCED RESPONSE MODELS
# ============================================================================

class ServiceListTypeInfo(TypedDict):
    """Information about a service list type with enhanced metadata."""
    name: str
    description: str
    has_detail_view: bool
    supports_pagination: bool
    default_page_size: int
    example_ids: List[str]
    required_scopes: List[str]


class ServiceListTypesResponse(TypedDict):
    """Response for service list types resource with metadata."""
    service: str
    service_metadata: Dict[str, Any]
    list_types: List[ServiceListTypeInfo]
    documentation_url: str
    examples: List[str]


class ServiceListItemsResponse(TypedDict):
    """Response for service list items resource with pagination."""
    service: str
    list_type: str
    description: str
    count: Optional[int]
    items: Optional[List[Dict[str, Any]]]
    data: Optional[Any]
    next_page_token: Optional[str]
    has_more: bool
    metadata: Dict[str, Any]


class ServiceListItemDetailsResponse(TypedDict):
    """Response for service list item details resource."""
    service: str
    list_type: str
    item_id: str
    data: Optional[Any]
    metadata: Optional[Dict[str, Any]]
    raw_response: Optional[Dict[str, Any]]


class ServiceErrorResponse(TypedDict):
    """Enhanced error response structure with helpful information."""
    error: NotRequired[Optional[str]]  
    error_code: Optional[str] 
    service: Optional[str]
    list_type: Optional[str]
    available_services: Optional[List[str]]
    available_list_types: Optional[List[str]]
    suggestions: Optional[List[str]]
    documentation_url: Optional[str]


# ============================================================================
# AUTHENTICATION HELPERS
# ============================================================================

def _get_authenticated_user_email(ctx: Context) -> Optional[str]:
    """
    Get the authenticated user email using multiple fallback methods.
    
    This function tries various methods to find the authenticated user:
    1. Primary: Use centralized auth context from session
    2. Fallback: Check context metadata
    3. Last resort: Auto-detect from stored credentials
    
    Args:
        ctx: FastMCP context
        
    Returns:
        User email if found, None otherwise
    """
    user_email = None
    
    # Method 1: Use the centralized auth context (preferred)
    if get_user_email_context:
        try:
            user_email = get_user_email_context()
            if user_email:
                logger.debug(f"Got user email from auth context: {user_email}")
                return user_email
        except Exception as e:
            logger.debug(f"Could not get user email from auth context: {e}")
    
    # Method 2: Check context metadata
    if hasattr(ctx, 'metadata') and ctx.metadata:
        user_email = ctx.metadata.get("user_email")
        if user_email:
            logger.debug(f"Got user email from ctx.metadata: {user_email}")
            return user_email
    
    # Method 3: Check direct context attributes
    if hasattr(ctx, 'user_email'):
        user_email = ctx.user_email
        if user_email:
            logger.debug(f"Got user email from ctx.user_email: {user_email}")
            return user_email
    
    # Method 4: Check session attributes
    if hasattr(ctx, 'session') and hasattr(ctx.session, 'user_email'):
        user_email = ctx.session.user_email
        if user_email:
            logger.debug(f"Got user email from ctx.session.user_email: {user_email}")
            return user_email
    
    # Method 5: Auto-detect from stored credentials (last resort)
    if get_valid_credentials:
        try:
            import os
            creds_dir = os.path.expanduser("~/.fastmcp2/credentials")
            if os.path.exists(creds_dir):
                # First, try to find the most recently used credentials
                credentials_files = []
                for filename in os.listdir(creds_dir):
                    if filename.endswith(".json") and "@" in filename:
                        filepath = os.path.join(creds_dir, filename)
                        potential_email = filename.replace(".json", "")
                        credentials_files.append((filepath, potential_email))
                
                # Sort by modification time (most recent first)
                credentials_files.sort(key=lambda x: os.path.getmtime(x[0]), reverse=True)
                
                # Try to find a valid, non-expired credential
                for filepath, potential_email in credentials_files:
                    try:
                        credentials = get_valid_credentials(potential_email)
                        if credentials and not credentials.expired:
                            logger.info(f"Auto-detected authenticated user from credentials: {potential_email}")
                            return potential_email
                    except Exception as e:
                        logger.debug(f"Could not validate credentials for {potential_email}: {e}")
                        continue
        except Exception as e:
            logger.debug(f"Could not auto-detect authenticated user: {e}")
    
    return None

def _create_auth_error_response(service: str, list_type: str = None) -> ServiceErrorResponse:
    """
    Create a standardized authentication error response with helpful suggestions.
    
    Args:
        service: The service that was requested
        list_type: The list type that was requested (optional)
        
    Returns:
        ServiceErrorResponse with helpful suggestions
    """
    return ServiceErrorResponse(
        error="No authenticated user found. Please authenticate first.",
        error_code="AUTH_REQUIRED",
        service=service.lower() if service else None,
        list_type=list_type.lower() if list_type else None,
        available_services=None,
        available_list_types=None,
        suggestions=[
            "Run: start_google_auth('your.email@gmail.com')",
            "Check auth status: access user://profile/your.email@gmail.com",
            "View active sessions: access auth://sessions/list",
            "Get current user: access user://current/email"
        ],
        documentation_url="https://docs.fastmcp2.com/authentication"
    )

# ============================================================================
# SERVICE LIST DISCOVERY WITH TAG-BASED APPROACH
# ============================================================================

class ServiceListDiscovery:
    """
    Enhanced discovery and management of list-based tools across all services.
    Maps tools to hierarchical resource patterns with rich metadata.
    
    This refactored version uses tag-based discovery instead of type introspection.
    """
    
    # Enhanced tool configuration with metadata
    # Tools should be tagged with "list" to be discovered
    TOOL_CONFIGURATIONS = {
        "gmail": {
            "filters": {
                "tool": "list_gmail_filters",
                "list_field": "filters",  # Explicit field containing the list
                "id_field": None,
                "detail_tool": "get_gmail_filter",
                "description": "Gmail filter rules for automatic email processing",
                "supports_pagination": True,
                "default_page_size": 25,
                "example_ids": ["filter_123", "filter_456"],
                "required_scopes": ["gmail.settings.basic"],
                "required_tags": ["list", "gmail", "filters"]  # Tags to look for
            },
            "labels": {
                "tool": "list_gmail_labels",
                "list_field": "labels",  # Explicit field containing the list
                "id_field": None,
                "detail_tool": None,
                "description": "Gmail labels for email organization",
                "supports_pagination": False,
                "default_page_size": 100,
                "example_ids": ["INBOX", "SENT", "IMPORTANT"],
                "required_scopes": ["gmail.labels"],
                "supports_detail_from_list": True,
                "required_tags": ["list", "gmail", "labels"]
            }
        },
        "forms": {
            "form_responses": {
                "tool": "list_form_responses",
                "id_field": "form_id",
                "list_forms_tool": "get_form",
                "description": "Form submission responses with timestamps and data",
                "supports_pagination": True,
                "default_page_size": 20,
                "example_ids": ["form_abc123", "form_def456"],
                "required_scopes": ["forms.responses.readonly"],
                "required_tags": ["list", "forms", "responses"]
            }
        },
        "photos": {
            "albums": {
                "tool": "list_photos_albums",
                "id_field": None,
                "detail_tool": "list_album_photos",
                "description": "Photo albums with cover images and metadata",
                "supports_pagination": True,
                "default_page_size": 50,
                "example_ids": ["album_vacation2023", "album_family"],
                "required_scopes": ["photos.readonly"],
                "required_tags": ["list", "photos", "albums"]
            }
        },
        "calendar": {
            "calendars": {
                "tool": "list_calendars",
                "id_field": None,
                "detail_tool": None,
                "description": "Available calendars with access levels",
                "supports_pagination": False,
                "default_page_size": 50,
                "example_ids": ["primary", "holidays@group.v.calendar.google.com"],
                "required_scopes": ["calendar.readonly"],
                "required_tags": ["list", "calendar", "calendars"]
            },
            "events": {
                "tool": "list_events",
                "id_field": None,  # Allow list_events to be called without requiring calendar_id
                "description": "Calendar events with attendees and details",
                "supports_pagination": True,
                "default_page_size": 10,
                "example_ids": ["event_123abc", "recurring_456def"],
                "required_scopes": ["calendar.events"],
                "required_tags": ["list", "calendar", "events"]
            }
        },
        "sheets": {
            "spreadsheets": {
                "tool": "list_spreadsheets",
                "id_field": None,
                "detail_tool": "get_spreadsheet_info",
                "description": "Google Sheets spreadsheets with metadata",
                "supports_pagination": True,
                "default_page_size": 30,
                "example_ids": ["1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"],
                "required_scopes": ["sheets.readonly"],
                "required_tags": ["list", "sheets", "spreadsheets"]
            }
        },
        "drive": {
            "items": {
                "tool": "list_drive_items",
                "id_field": "folder_id",
                "description": "Drive files and folders with permissions",
                "supports_pagination": True,
                "default_page_size": 50,
                "example_ids": ["root", "folder_abc123"],
                "required_scopes": ["drive.readonly"],
                "required_tags": ["list", "drive", "items"]
            }
        },
        "chat": {
            "spaces": {
                "tool": "list_spaces",
                "id_field": None,
                "detail_tool": "list_messages",
                "description": "Chat spaces and rooms with member lists",
                "supports_pagination": True,
                "default_page_size": 20,
                "example_ids": ["spaces/AAAA1234", "spaces/BBBB5678"],
                "required_scopes": ["chat.spaces"],
                "required_tags": ["list", "chat", "spaces"]
            }
        },
        "docs": {
            "documents": {
                "tool": "list_docs_in_folder",
                "id_field": "folder_id",
                "detail_tool": "get_doc_content",
                "description": "Google Docs documents with content preview",
                "supports_pagination": True,
                "default_page_size": 20,
                "example_ids": ["doc_123abc", "template_456def"],
                "required_scopes": ["docs.readonly"],
                "required_tags": ["list", "docs", "documents"]
            }
        }
    }
    
    def __init__(self, mcp: FastMCP):
        """Initialize the enhanced service discovery system."""
        self.mcp = mcp
        self.discovered_tools: Dict[str, Tool] = {}
        self._generate_service_mappings()
        self._tools_discovered = False
        
    def _generate_service_mappings(self) -> None:
        """Generate SERVICE_MAPPINGS dynamically with enhanced metadata."""
        self.SERVICE_MAPPINGS = {}
        
        if SERVICE_DEFAULTS:
            for service in SERVICE_DEFAULTS.keys():
                service_lower = service.lower()
                tool_config = self.TOOL_CONFIGURATIONS.get(service_lower, {})
                if tool_config:
                    # Enhance with service metadata
                    service_info = ServiceMetadata.get_service_info(service_lower)
                    for list_type, config in tool_config.items():
                        config['service_metadata'] = service_info
                    self.SERVICE_MAPPINGS[service_lower] = tool_config
                    logger.debug(f"Added {service_lower} to SERVICE_MAPPINGS with metadata")
        else:
            # Fallback with metadata
            for service, config in self.TOOL_CONFIGURATIONS.items():
                service_info = ServiceMetadata.get_service_info(service)
                for list_type, list_config in config.items():
                    list_config['service_metadata'] = service_info
                self.SERVICE_MAPPINGS[service] = config
            logger.warning("SERVICE_DEFAULTS not available, using TOOL_CONFIGURATIONS with metadata")
        
        logger.info(f"Generated SERVICE_MAPPINGS for {len(self.SERVICE_MAPPINGS)} services with metadata")
        
    async def _discover_tools(self) -> None:
        """Discover and cache all available tools using tag-based discovery."""
        if self._tools_discovered:
            return  # Already discovered
            
        logger.info("Discovering tools from FastMCP instance using tag-based approach...")
        
        try:
            # Try using the public tools property/attribute
            if hasattr(self.mcp, 'tools'):
                tools_list = self.mcp.tools
                if tools_list:
                    for tool in tools_list:
                        if hasattr(tool, 'name'):
                            self.discovered_tools[tool.name] = tool
                            # Log tools with 'list' tag
                            if hasattr(tool, 'tags') and tool.tags and 'list' in tool.tags:
                                logger.debug(f"Discovered list tool: {tool.name} with tags: {tool.tags}")
                    
                    logger.info(f"Discovered {len(self.discovered_tools)} tools via public API")
                    
                    # Count list tools
                    list_tools = [
                        (name, tool) for name, tool in self.discovered_tools.items()
                        if hasattr(tool, 'tags') and tool.tags and 'list' in tool.tags
                    ]
                    logger.info(f"Found {len(list_tools)} tools tagged with 'list'")
                    self._tools_discovered = True
                    return
            
            # Fallback: Try looking for a get_tools() method
            if hasattr(self.mcp, 'get_tools'):
                get_tools_func = getattr(self.mcp, 'get_tools')
                # Check if it's async
                if asyncio.iscoroutinefunction(get_tools_func):
                    tools = await get_tools_func()
                else:
                    tools = get_tools_func()
                    
                if isinstance(tools, dict):
                    self.discovered_tools = tools
                    logger.info(f"Discovered {len(self.discovered_tools)} tools via get_tools()")
                    # Log sample tool structure for debugging
                    if self.discovered_tools:
                        sample_tool_name = next(iter(self.discovered_tools.keys()))
                        sample_tool = self.discovered_tools[sample_tool_name]
                        logger.debug(f"Sample tool '{sample_tool_name}' attributes: {dir(sample_tool)}")
                        if hasattr(sample_tool, '__dict__'):
                            logger.debug(f"Sample tool '__dict__': {sample_tool.__dict__}")
                elif isinstance(tools, list):
                    for tool in tools:
                        if hasattr(tool, 'name'):
                            self.discovered_tools[tool.name] = tool
                    logger.info(f"Discovered {len(self.discovered_tools)} tools via get_tools()")
                
                self._tools_discovered = True
                return
            
            # No standard discovery method found
            logger.info("No standard tool discovery method found, tools will be discovered on demand")
            self._tools_discovered = True
                
        except Exception as e:
            logger.error(f"Error discovering tools: {e}")
            logger.info("Tools will be discovered on demand during resource access")
            self._tools_discovered = True
            
    def get_service_lists(self, service: str) -> List[ServiceListTypeInfo]:
        """Get available list types for a service with enhanced metadata."""
        service = service.lower()
        if service not in self.SERVICE_MAPPINGS:
            return []
        
        list_types = []
        for list_type, config in self.SERVICE_MAPPINGS[service].items():
            # Check if has detail view
            has_detail = bool(
                config.get("detail_tool") or
                config.get("id_field") or
                config.get("supports_detail_from_list")
            )
            
            list_types.append(ServiceListTypeInfo(
                name=list_type,
                description=config.get("description", ""),
                has_detail_view=has_detail,
                supports_pagination=config.get("supports_pagination", False),
                default_page_size=config.get("default_page_size", 25),
                example_ids=config.get("example_ids", []),
                required_scopes=config.get("required_scopes", [])
            ))
        
        return list_types
        
    def get_list_config(self, service: str, list_type: str) -> Optional[Dict[str, Any]]:
        """Get enhanced configuration for a specific list type."""
        service = service.lower()
        list_type = list_type.lower()
        return self.SERVICE_MAPPINGS.get(service, {}).get(list_type)
        
    def _filter_params_for_tool(self, tool: Any, base_params: Dict[str, Any],
                               page_size: Optional[int], page_token: Optional[str],
                               config: Dict[str, Any]) -> Dict[str, Any]:
        """Filter parameters based on what the tool actually supports."""
        # Start with base parameters (user_google_email)
        filtered_params = dict(base_params)
        
        # Get tool function to inspect its signature
        tool_func = None
        if hasattr(tool, 'fn'):
            tool_func = tool.fn
        elif callable(tool):
            tool_func = tool
            
        if not tool_func:
            return filtered_params
            
        try:
            import inspect
            sig = inspect.signature(tool_func)
            param_names = set(sig.parameters.keys())
            
            # Only add pagination params if the tool accepts them
            if config.get("supports_pagination", False):
                if "page_size" in param_names and page_size is not None:
                    filtered_params["page_size"] = page_size
                if "page_token" in param_names and page_token is not None:
                    filtered_params["page_token"] = page_token
                    
        except Exception as e:
            logger.debug(f"Could not inspect tool signature: {e}, using base params only")
            
        return filtered_params

    async def get_list_items(self, service: str, list_type: str, user_email: str,
                            page_size: Optional[int] = None,
                            page_token: Optional[str] = None) -> Any:
        """Get all items/IDs for a list type using direct tool calls."""
        # Ensure tools are discovered
        await self._discover_tools()
        
        config = self.get_list_config(service, list_type)
        if not config:
            return []
            
        tool_name = config["tool"]
        
        if tool_name not in self.discovered_tools:
            logger.warning(f"Tool {tool_name} not found in discovered tools")
            return []
            
        # Apply default page size if not provided
        if page_size is None:
            page_size = config.get("default_page_size", 25)
            
        # Build base parameters
        base_params = {"user_google_email": user_email}
        
        if config.get("id_field"):
            # For tools that need an ID parameter, we'll handle this separately
            return await self._get_available_ids(service, list_type, user_email)
        
        # Get the actual tool to check its signature
        tool = self.discovered_tools.get(tool_name)
        if not tool:
            logger.error(f"Tool {tool_name} not found in discovered tools")
            return []
        
        # Filter parameters based on tool's actual signature
        filtered_params = self._filter_params_for_tool(tool, base_params, page_size, page_token, config)
        
        try:
            logger.debug(f"Calling {tool_name} with filtered params: {filtered_params}")
            
            # Call the tool directly (don't use forward() here as we're not in a transform context)
            if hasattr(tool, 'fn'):
                # This is a FunctionTool, call its wrapped function
                result = await tool.fn(**filtered_params)
            elif callable(tool):
                # The tool itself is callable
                result = await tool(**filtered_params)
            else:
                logger.error(f"Tool {tool_name} is not callable")
                return []
            
            logger.debug(f"Got result from {tool_name}: {type(result)}")
            
            # Parse the result to extract list data
            return self._parse_list_result(result, service, list_type)
            
        except Exception as e:
            logger.error(f"Error calling {tool_name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
            
    async def get_list_item_details(
        self,
        service: str,
        list_type: str,
        item_id: str,
        user_email: str,
        include_metadata: bool = True,
        include_raw: bool = False
    ) -> Any:
        """Get detailed data for a specific item using FastMCP forward() pattern."""
        # Ensure tools are discovered
        await self._discover_tools()
        
        config = self.get_list_config(service, list_type)
        if not config:
            return None
        
        # Special handling for Gmail labels which support detail extraction from list
        if service == "gmail" and list_type == "labels" and config.get("supports_detail_from_list"):
            # Get all labels and extract the specific one
            tool_name = config["tool"]
            if tool_name not in self.discovered_tools:
                return None
            
            try:
                # Call list_gmail_labels to get all labels
                params = {"user_google_email": user_email}
                
                # Use forward() pattern to call the tool
                logger.debug(f"Using forward() to call {tool_name} to extract label {item_id}")
                
                try:
                    result = await forward(tool_name, **params)
                except TypeError as te:
                    # If forward() doesn't work, try calling the tool directly
                    logger.warning(f"forward() failed: {te}, trying direct call")
                    tool = self.discovered_tools.get(tool_name)
                    if tool and hasattr(tool, 'fn'):
                        result = await tool.fn(**params)
                    elif tool and callable(tool):
                        result = await tool(**params)
                    else:
                        logger.error(f"Tool {tool_name} not found or not callable")
                        return None
                
                # Parse the result to find the specific label
                parsed_labels = self._parse_list_result(result, service, list_type)
                
                # Find the specific label by ID
                target_label = None
                for label in parsed_labels:
                    if label.get("id") == item_id or label.get("name") == item_id:
                        target_label = label
                        break
                
                if not target_label:
                    logger.info(f"Label with ID '{item_id}' not found")
                    return None
                
                # Enhance with metadata if requested
                if include_metadata:
                    service_info = ServiceMetadata.get_service_info(service)
                    target_label['_metadata'] = {
                        'service_info': service_info,
                        'list_type': list_type,
                        'item_id': item_id,
                        'retrieved_at': datetime.now().isoformat()
                    }
                
                return target_label
                
            except Exception as e:
                logger.error(f"Error getting Gmail label details for '{item_id}': {e}")
                return None
            
        # If there's an id_field, call the list tool with that ID
        elif config.get("id_field"):
            tool_name = config["tool"]
            if tool_name not in self.discovered_tools:
                return None
            
            # Build parameters with the ID field
            params = {
                "user_google_email": user_email,
                config["id_field"]: item_id
            }
            
            # Add optional parameters if supported
            if include_metadata:
                params["include_metadata"] = True
            if include_raw:
                params["include_raw"] = True
            
            try:
                # Use forward() pattern to call the tool
                logger.debug(f"Using forward() to call {tool_name} with ID field")
                
                try:
                    result = await forward(tool_name, **params)
                except TypeError as te:
                    # If forward() doesn't work, try calling the tool directly
                    logger.warning(f"forward() failed: {te}, trying direct call")
                    tool = self.discovered_tools.get(tool_name)
                    if tool and hasattr(tool, 'fn'):
                        result = await tool.fn(**params)
                    elif tool and callable(tool):
                        result = await tool(**params)
                    else:
                        logger.error(f"Tool {tool_name} not found or not callable")
                        return None
                
                # Enhance result with metadata if requested
                if include_metadata and isinstance(result, dict):
                    service_info = ServiceMetadata.get_service_info(service)
                    result['_metadata'] = {
                        'service_info': service_info,
                        'list_type': list_type,
                        'item_id': item_id,
                        'retrieved_at': datetime.now().isoformat()
                    }
                    
                return result
            except Exception as e:
                logger.error(f"Error calling {tool_name} with ID {item_id}: {e}")
                return None
                
        # If there's a detail tool, use that
        elif config.get("detail_tool"):
            detail_tool_name = config["detail_tool"]
            if detail_tool_name not in self.discovered_tools:
                return None
            
            try:
                # Determine the ID parameter name
                id_param_name = f"{list_type[:-1]}_id" if list_type.endswith('s') else f"{list_type}_id"
                
                params = {
                    "user_google_email": user_email,
                    id_param_name: item_id
                }
                
                # Add optional parameters if supported
                if include_metadata:
                    params["include_metadata"] = True
                if include_raw:
                    params["include_raw"] = True
                
                # Use forward() pattern to call the detail tool
                logger.debug(f"Using forward() to call detail tool {detail_tool_name}")
                
                try:
                    result = await forward(detail_tool_name, **params)
                except TypeError as te:
                    # If forward() doesn't work, try calling the tool directly
                    logger.warning(f"forward() failed: {te}, trying direct call")
                    tool = self.discovered_tools.get(detail_tool_name)
                    if tool and hasattr(tool, 'fn'):
                        result = await tool.fn(**params)
                    elif tool and callable(tool):
                        result = await tool(**params)
                    else:
                        logger.error(f"Tool {detail_tool_name} not found or not callable")
                        return None
                
                # Enhance result with metadata if requested
                if include_metadata and isinstance(result, dict):
                    service_info = ServiceMetadata.get_service_info(service)
                    result['_metadata'] = {
                        'service_info': service_info,
                        'list_type': list_type,
                        'item_id': item_id,
                        'retrieved_at': datetime.now().isoformat()
                    }
                    
                return result
            except Exception as e:
                logger.error(f"Error calling {detail_tool_name} for ID {item_id}: {e}")
                return None
                
        return None
        
    def _parse_list_result(self, result: Any, service: str, list_type: str) -> List[Dict[str, Any]]:
        """Parse the result from a list tool - simplified without type introspection.
        
        This method now uses a simpler approach without complex field discovery.
        """
        # First, try to parse JSON if result is a string
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                logger.warning(f"Could not parse string result as JSON for {service}/{list_type}")
                return []
        
        # If it's already a list, return it directly
        if isinstance(result, list):
            return self._enhance_items_with_metadata(result, service, list_type)
        
        # Handle TypedDict responses - look for common list field names
        if isinstance(result, dict):
            # Common field names that contain list data
            list_field_names = [
                'filters', 'labels', 'items', 'data', 'results', 'entries',
                'albums', 'photos', 'messages', 'spaces', 'calendars', 'events',
                'documents', 'spreadsheets', 'forms', 'responses', 'files', 'folders'
            ]
            
            # Check each potential list field
            for field_name in list_field_names:
                if field_name in result:
                    field_value = result[field_name]
                    if isinstance(field_value, list):
                        logger.info(f"Found list data in field '{field_name}' for {service}/{list_type}")
                        return self._enhance_items_with_metadata(field_value, service, list_type)
            
            # If no list field found, check if the dict itself is the single item
            if 'id' in result or 'name' in result:
                logger.debug(f"Result appears to be a single item for {service}/{list_type}")
                return self._enhance_items_with_metadata([result], service, list_type)
            
            logger.warning(f"Could not find list data in dict result for {service}/{list_type}")
            return []
        
        # If we can't parse the result, return empty list
        logger.warning(f"Unexpected result type {type(result)} for {service}/{list_type}")
        return []
    
    def _enhance_items_with_metadata(self, items: List[Any], service: str, list_type: str) -> List[Dict[str, Any]]:
        """Enhance list items with service metadata.
        
        Adds service information and ensures consistent structure for all items.
        """
        service_info = ServiceMetadata.get_service_info(service)
        enhanced_items = []
        
        for item in items:
            if isinstance(item, dict):
                # Copy the item and add service metadata
                enhanced_item = dict(item)
                # Only add service metadata if not already present
                if 'service' not in enhanced_item:
                    enhanced_item['service'] = service
                if 'service_icon' not in enhanced_item:
                    enhanced_item['service_icon'] = service_info['icon']
                if 'list_type' not in enhanced_item:
                    enhanced_item['list_type'] = list_type
                enhanced_items.append(enhanced_item)
            elif isinstance(item, str):
                # Handle simple string items
                enhanced_items.append({
                    'value': item,
                    'service': service,
                    'service_icon': service_info['icon'],
                    'list_type': list_type
                })
            else:
                # Handle other types by converting to string
                enhanced_items.append({
                    'value': str(item),
                    'service': service,
                    'service_icon': service_info['icon'],
                    'list_type': list_type
                })
        
        return enhanced_items
        
    async def _get_available_ids(self, service: str, list_type: str, user_email: str) -> List[Dict[str, Any]]:
        """Get available IDs with enhanced metadata and examples."""
        items = []
        config = self.get_list_config(service, list_type)
        service_info = ServiceMetadata.get_service_info(service)
        
        if config:
            # Add example IDs from configuration with metadata
            for example_id in config.get("example_ids", []):
                items.append({
                    "id": example_id,
                    "description": f"Example {list_type[:-1]} ID",
                    "is_example": True,
                    "service": service,
                    "service_icon": service_info['icon'],
                    "service_name": service_info['display_name']
                })
        
        # Add service-specific defaults with enhanced metadata
        if service == "drive" and list_type == "items":
            items.append({
                "id": "root",
                "description": "Root folder - Top level of My Drive",
                "is_default": True,
                "service": service,
                "service_icon": service_info['icon'],
                "service_name": service_info['display_name'],
                "usage_hint": "Use this to list files in the root of your Drive"
            })
            
        elif service == "calendar" and list_type == "events":
            items.append({
                "id": "primary",
                "description": "Primary calendar - Your main Google Calendar",
                "is_default": True,
                "service": service,
                "service_icon": service_info['icon'],
                "service_name": service_info['display_name'],
                "usage_hint": "Use this to access events in your primary calendar"
            })
            
        elif service == "gmail":
            if list_type == "filters":
                items.append({
                    "note": "Use list_gmail_filters directly to get all filters",
                    "service": service,
                    "service_icon": service_info['icon'],
                    "service_name": service_info['display_name'],
                    "no_id_required": True
                })
            elif list_type == "labels":
                items.append({
                    "note": "Use list_gmail_labels directly to get all labels",
                    "service": service,
                    "service_icon": service_info['icon'],
                    "service_name": service_info['display_name'],
                    "no_id_required": True
                })
        
        # If no specific items added, provide generic guidance
        if not items:
            items.append({
                "note": f"No default IDs available for {service}/{list_type}",
                "service": service,
                "service_icon": service_info['icon'],
                "service_name": service_info['display_name'],
                "suggestion": f"Use appropriate {service} tools to discover available IDs"
            })
            
        return items


# ============================================================================
# MAIN SETUP FUNCTION WITH ENHANCEMENTS
# ============================================================================

def setup_service_list_resources(mcp: FastMCP) -> None:
    """
    Setup enhanced dynamic service list resources with comprehensive features.
    
    Args:
        mcp: FastMCP instance to register resources with
    """
    logger.info("Setting up enhanced dynamic service list resources with tag-based discovery...")
    
    # Initialize enhanced discovery system
    discovery = ServiceListDiscovery(mcp)
    
    # Generate dynamic description with accepted service values
    def generate_resource_description() -> str:
        """Generate a description that includes all valid service values."""
        services = get_supported_services()
        service_lines = []
        
        for service in services:
            info = ServiceMetadata.get_service_info(service)
            service_lines.append(f"  • {service} ({info['icon']}): {info['description']}")
        
        return f"""Get available list types for a Google service with rich metadata.

Accepted service values:
{chr(10).join(service_lines)}

Returns comprehensive metadata including pagination support, default values, and example IDs."""
    
    # Resource 1: Enhanced list types discovery with accepted values in description
    @mcp.resource(
        uri="service://{service}/lists",
        name="Service List Types (Enhanced)",
        description=generate_resource_description(),
        mime_type="application/json",
        tags={"service", "lists", "discovery", "dynamic", "enhanced"},
        annotations={
            "readOnlyHint": True,
            "idempotentHint": True
        },
        meta={
            "version": "2.0",
            "category": "discovery",
            "response_model": "ServiceListTypesResponse",
            "enhanced": True,
            "includes_metadata": True,
            "accepted_values": get_supported_services()
        }
    )
    async def get_service_list_types(
        ctx: Context,
        service: str
    ) -> Union[ServiceListTypesResponse, ServiceErrorResponse]:
        """Get available list types for a service with enhanced metadata and documentation."""
        try:
            service_request = ServiceRequest(service=service)
            service_lower = service_request.service
        except ValueError as e:
            # Enhanced error response with suggestions
            suggestions = [s for s in get_supported_services() 
                         if s.startswith(service[0].lower()) if service]
            return ServiceErrorResponse(
                error=str(e),
                error_code="INVALID_SERVICE",
                service=service.lower() if isinstance(service, str) else None,
                list_type=None,
                available_services=list(discovery.SERVICE_MAPPINGS.keys()),
                available_list_types=None,
                suggestions=suggestions,
                documentation_url=f"https://docs.fastmcp2.com/services/{service.lower()}"
            )
        
        list_types = discovery.get_service_lists(service_lower)
        
        if not list_types:
            return ServiceErrorResponse(
                error=f"Service '{service}' not found or has no list types",
                error_code="NO_LIST_TYPES",
                service=service_lower,
                list_type=None,
                available_services=list(discovery.SERVICE_MAPPINGS.keys()),
                available_list_types=None,
                suggestions=None,
                documentation_url=f"https://docs.fastmcp2.com/services/"
            )
            
        # Build enhanced response with metadata
        service_info = ServiceMetadata.get_service_info(service_lower)
        
        return ServiceListTypesResponse(
            service=service_lower,
            service_metadata=service_info,
            list_types=list_types,
            documentation_url=f"https://docs.fastmcp2.com/services/{service_lower}",
            examples=[f"service://{service_lower}/{lt['name']}" for lt in list_types[:3]]
        )
    
    # Resource 2: List all items/IDs for a specific list type with accepted values
    @mcp.resource(
        uri="service://{service}/{list_type}",
        name="Service List Items (Enhanced)",
        description=f"""Get all items/IDs for a specific list type with pagination support.

Accepted service values:
{chr(10).join([f"  • {s} ({ServiceMetadata.get_service_info(s)['icon']})" for s in get_supported_services()])}

Common list types by service:
  • gmail: filters, labels
  • drive: items (folders/files)
  • calendar: calendars, events
  • photos: albums
  • forms: form_responses
  • sheets: spreadsheets
  • chat: spaces
  • docs: documents

Returns items with pagination support and metadata.""",
        mime_type="application/json",
        tags={"service", "lists", "items", "dynamic", "enhanced"},
        annotations={
            "readOnlyHint": True,
            "idempotentHint": False  # May change as new items are added
        },
        meta={
            "version": "2.0",
            "category": "data",
            "response_model": "ServiceListItemsResponse",
            "requires_auth": True,
            "accepted_services": get_supported_services()
        }
    )
    async def get_service_list_items(
        ctx: Context,
        service: str,
        list_type: str
    ) -> Union[ServiceListItemsResponse, ServiceErrorResponse]:
        """Get all items for a specific list type."""
        # Validate and normalize inputs using Pydantic model
        try:
            list_request = ServiceListRequest(service=service, list_type=list_type)
            service_lower = list_request.service
            list_type_lower = list_request.list_type
        except ValueError as e:
            return ServiceErrorResponse(
                error=str(e),
                error_code="INVALID_SERVICE",
                service=service.lower() if isinstance(service, str) else None,
                list_type=list_type.lower() if isinstance(list_type, str) else None,
                available_services=list(discovery.SERVICE_MAPPINGS.keys()),
                available_list_types=None,
                suggestions=[s for s in get_supported_services() if s.startswith(service[0].lower())] if service else [],
                documentation_url=f"https://docs.fastmcp2.com/services/"
            )
        
        # Validate service parameter
        if service_lower not in get_supported_services():
            return ServiceErrorResponse(
                error=f"Service '{service}' not found",
                error_code="SERVICE_NOT_FOUND",
                service=service_lower,
                list_type=None,
                available_services=list(discovery.SERVICE_MAPPINGS.keys()),
                available_list_types=None,
                suggestions=None,
                documentation_url=f"https://docs.fastmcp2.com/services/"
            )
            
        # Check if list type is valid
        config = discovery.get_list_config(service_lower, list_type_lower)
        if not config:
            return ServiceErrorResponse(
                error=f"List type '{list_type}' not found for service '{service}'",
                error_code="LIST_TYPE_NOT_FOUND",
                service=service_lower,
                list_type=list_type_lower,
                available_services=None,
                available_list_types=discovery.get_service_lists(service_lower),
                suggestions=None,
                documentation_url=f"https://docs.fastmcp2.com/services/{service_lower}"
            )
            
        # Get user email using the unified authentication helper
        user_email = _get_authenticated_user_email(ctx)
        
        if not user_email:
            return _create_auth_error_response(service_lower, list_type_lower)
            
        items = await discovery.get_list_items(service_lower, list_type_lower, user_email)
        
        # Build structured response
        if isinstance(items, dict):
            response = ServiceListItemsResponse(
                service=service_lower,
                list_type=list_type_lower,
                description=config.get("description", ""),
                count=None,
                items=None,
                data=items,
                next_page_token=None,
                has_more=False,
                metadata=ServiceMetadata.get_service_info(service_lower)
            )
            if "items" in items:
                response["items"] = items["items"]
                response["count"] = len(items["items"]) if items["items"] else 0
            return response
        elif isinstance(items, list):
            return ServiceListItemsResponse(
                service=service_lower,
                list_type=list_type_lower,
                description=config.get("description", ""),
                count=len(items),
                items=items,
                data=None,
                next_page_token=None,
                has_more=False,
                metadata=ServiceMetadata.get_service_info(service_lower)
            )
        else:
            return ServiceListItemsResponse(
                service=service_lower,
                list_type=list_type_lower,
                description=config.get("description", ""),
                count=None,
                items=None,
                data=items,
                next_page_token=None,
                has_more=False,
                metadata=ServiceMetadata.get_service_info(service_lower)
            )
        
    # Resource 3: Get detailed data for a specific item with accepted values
    @mcp.resource(
        uri="service://{service}/{list_type}/{item_id}",
        name="Service List Item Details (Enhanced)",
        description=f"""Get detailed data for a specific item.

Accepted service values:
{chr(10).join([f"  • {s} ({ServiceMetadata.get_service_info(s)['icon']})" for s in get_supported_services()])}

Returns detailed item data with optional metadata and raw response.""",
        mime_type="application/json",
        tags={"service", "lists", "detail", "dynamic", "enhanced"},
        annotations={
            "readOnlyHint": True,
            "idempotentHint": False  # Item details may change
        },
        meta={
            "version": "2.0",
            "category": "detail",
            "response_model": "ServiceListItemDetailsResponse",
            "requires_auth": True,
            "accepted_services": get_supported_services()
        }
    )
    async def get_service_list_item_details(
        ctx: Context,
        service: str,
        list_type: str,
        item_id: str
    ) -> Union[ServiceListItemDetailsResponse, ServiceErrorResponse]:
        """Get detailed data for a specific item."""
        # Validate and normalize inputs using Pydantic model
        try:
            item_request = ServiceItemRequest(service=service, list_type=list_type, item_id=item_id)
            service_lower = item_request.service
            list_type_lower = item_request.list_type
            normalized_item_id = item_request.item_id
        except ValueError as e:
            return ServiceErrorResponse(
                error=str(e),
                error_code="INVALID_REQUEST",
                service=service.lower() if isinstance(service, str) else None,
                list_type=list_type.lower() if isinstance(list_type, str) else None,
                available_services=list(discovery.SERVICE_MAPPINGS.keys()),
                available_list_types=None,
                suggestions=None,
                documentation_url=f"https://docs.fastmcp2.com/services/"
            )
        
        # Validate service
        if service_lower not in get_supported_services():
            return ServiceErrorResponse(
                error=f"Service '{service}' not found",
                error_code="SERVICE_NOT_FOUND",
                service=service_lower,
                list_type=None,
                available_services=list(discovery.SERVICE_MAPPINGS.keys()),
                available_list_types=None,
                suggestions=None,
                documentation_url=f"https://docs.fastmcp2.com/services/"
            )
            
        # Get user email using the unified authentication helper
        user_email = _get_authenticated_user_email(ctx)
        
        if not user_email:
            return _create_auth_error_response(service_lower, list_type_lower)
            
        # Validate list type configuration
        config = discovery.get_list_config(service_lower, list_type_lower)
        if not config:
            return ServiceErrorResponse(
                error=f"List type '{list_type}' not found for service '{service}'",
                error_code="LIST_TYPE_NOT_FOUND",
                service=service_lower,
                list_type=list_type_lower,
                available_services=None,
                available_list_types=discovery.get_service_lists(service_lower),
                suggestions=None,
                documentation_url=f"https://docs.fastmcp2.com/services/{service_lower}"
            )
            
        details = await discovery.get_list_item_details(service_lower, list_type_lower, normalized_item_id, user_email)
        
        if details is None:
            return ServiceErrorResponse(
                error=f"Could not retrieve details for item '{normalized_item_id}'",
                error_code="ITEM_NOT_FOUND",
                service=service_lower,
                list_type=list_type_lower,
                available_services=None,
                available_list_types=None,
                suggestions=None,
                documentation_url=None
            )
            
        # Return structured response
        return ServiceListItemDetailsResponse(
            service=service_lower,
            list_type=list_type_lower,
            item_id=normalized_item_id,
            data=details,
            metadata=ServiceMetadata.get_service_info(service_lower),
            raw_response=None
        )
    
    logger.info(f"✅ Registered enhanced services with dynamic list resources using tag-based discovery")
    
    # Generate and log comprehensive documentation
    for service in discovery.SERVICE_MAPPINGS.keys():
        doc = ServiceMetadata.generate_service_documentation(service)
        logger.debug(f"Generated documentation for {service}:\n{doc}")
    
    logger.info(f"  Enhanced services with metadata: {len(discovery.SERVICE_MAPPINGS)}")
    for service, list_types in discovery.SERVICE_MAPPINGS.items():
        info = ServiceMetadata.get_service_info(service)
        logger.info(f"  {info['icon']} {service}: {', '.join(list_types.keys())}")