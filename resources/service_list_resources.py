"""
Dynamic Service List Resources for FastMCP2.

This module provides dynamic resources that expose list-based tools from various Google services
through a standardized hierarchical resource pattern:

1. service://{service}/lists - Returns available list types for the service
2. service://{service}/{list_type} - Returns all IDs/items for that list type  
3. service://{service}/{list_type}/{id} - Returns detailed data for a specific ID

Examples:
- service://forms/lists → ["form_responses"]
- service://forms/form_responses → [list of form IDs]
- service://forms/form_responses/abc123 → [actual form responses for form abc123]

Key Features:
- Automatic discovery of list-based tools across all services
- Hierarchical resource organization
- Dynamic parameter extraction and validation
- Metadata extraction for tool documentation
- Support for pagination and filtering parameters
- Proper use of FastMCP's tool transformation with forward()
"""

import logging
import json
import asyncio
import inspect
from typing import Dict, List, Any, Optional, Set, Tuple, Callable, TypedDict
from datetime import datetime

from fastmcp import FastMCP, Context
from fastmcp.tools import Tool

logger = logging.getLogger(__name__)

# Import from our centralized sources of truth
try:
    from auth.service_helpers import SERVICE_DEFAULTS
    from auth.scope_registry import ScopeRegistry
    logger.info("Successfully imported service configuration from auth module")
except ImportError as e:
    logger.warning(f"Could not import from auth module: {e}, using fallback")
    SERVICE_DEFAULTS = None
    ScopeRegistry = None


def _get_valid_services() -> List[str]:
    """
    Dynamically get the list of valid services from SERVICE_DEFAULTS.
    Falls back to a basic list if SERVICE_DEFAULTS is not available.
    """
    if SERVICE_DEFAULTS:
        return list(SERVICE_DEFAULTS.keys())
    else:
        # Fallback if imports fail
        return ["gmail", "forms", "photos", "calendar", "sheets", "drive", "chat", "docs"]

# Dynamically generate valid services list
VALID_SERVICES = _get_valid_services()


class ServiceListDiscovery:
    """
    Discovers and manages list-based tools across all services.
    Maps tools to hierarchical resource patterns.
    """
    
    # Tool configuration mapping - defines which tools are list-based for each service
    # This is NOT another source of truth for services, just metadata about list tools
    TOOL_CONFIGURATIONS = {
        "gmail": {
            "filters": {
                "tool": "list_gmail_filters",
                "id_field": None,  # Returns all filters, no separate ID listing
                "detail_tool": "get_gmail_filter",
                "description": "Gmail filter rules"
            },
            "labels": {
                "tool": "list_gmail_labels", 
                "id_field": None,
                "detail_tool": None,  # No detail tool for labels
                "description": "Gmail labels"
            }
        },
        "forms": {
            "form_responses": {
                "tool": "list_form_responses",
                "id_field": "form_id",  # Parameter that specifies which form
                "list_forms_tool": "get_form",  # Tool to list available forms
                "description": "Form submission responses"
            }
        },
        "photos": {
            "albums": {
                "tool": "list_photos_albums",
                "id_field": None,  # Lists all albums directly
                "detail_tool": "list_album_photos",
                "description": "Photo albums"
            }
        },
        "calendar": {
            "calendars": {
                "tool": "list_calendars",
                "id_field": None,
                "detail_tool": None,
                "description": "Available calendars"
            },
            "events": {
                "tool": "list_events",
                "id_field": "calendar_id",
                "description": "Calendar events"
            }
        },
        "sheets": {
            "spreadsheets": {
                "tool": "list_spreadsheets",
                "id_field": None,
                "detail_tool": "get_spreadsheet_info",
                "description": "Google Sheets spreadsheets"
            }
        },
        "drive": {
            "items": {
                "tool": "list_drive_items",
                "id_field": "folder_id",
                "description": "Drive files and folders"
            }
        },
        "chat": {
            "spaces": {
                "tool": "list_spaces",
                "id_field": None,
                "detail_tool": "list_messages",
                "description": "Chat spaces and rooms"
            }
        },
        "docs": {
            "documents": {
                "tool": "list_docs_in_folder",
                "id_field": "folder_id",
                "detail_tool": "get_doc_content",
                "description": "Google Docs documents"
            }
        }
    }
    
    def __init__(self, mcp: FastMCP):
        """
        Initialize the service discovery system.
        
        Args:
            mcp: FastMCP instance to inspect for tools
        """
        self.mcp = mcp
        self.discovered_tools: Dict[str, Tool] = {}
        self._generate_service_mappings()
        self._discover_tools()
        
    def _generate_service_mappings(self) -> None:
        """
        Generate SERVICE_MAPPINGS dynamically from SERVICE_DEFAULTS.
        Only includes services that have list-based tools configured.
        """
        # Start with tool configurations
        self.SERVICE_MAPPINGS = {}
        
        # Only include services that are in SERVICE_DEFAULTS and have tool configurations
        if SERVICE_DEFAULTS:
            for service in SERVICE_DEFAULTS.keys():
                service_lower = service.lower()
                # Check if we have tool configurations for this service
                tool_config = getattr(self.__class__, 'TOOL_CONFIGURATIONS', {})
                if service_lower in tool_config:
                    self.SERVICE_MAPPINGS[service_lower] = tool_config[service_lower]
                    logger.debug(f"Added {service_lower} to SERVICE_MAPPINGS from SERVICE_DEFAULTS")
        else:
            # Fallback: use all tool configurations if SERVICE_DEFAULTS is not available
            tool_config = getattr(self.__class__, 'TOOL_CONFIGURATIONS', {})
            self.SERVICE_MAPPINGS = tool_config.copy()
            logger.warning("SERVICE_DEFAULTS not available, using all TOOL_CONFIGURATIONS")
        
        logger.info(f"Generated SERVICE_MAPPINGS for {len(self.SERVICE_MAPPINGS)} services")
        
    def _discover_tools(self) -> None:
        """Discover and cache all available list tools."""
        logger.info("Discovering list-based tools across all services...")
        
        # Get tools from the MCP instance
        # FastMCP stores tools differently - we need to get them properly
        try:
            # Try to get tools from the MCP instance
            if hasattr(self.mcp, 'tools'):
                # FastMCP 2.x stores tools in a tools property
                for tool in self.mcp.tools:
                    if hasattr(tool, 'name'):
                        self.discovered_tools[tool.name] = tool
                        logger.debug(f"Discovered tool via tools property: {tool.name}")
            elif hasattr(self.mcp, '_tools'):
                # Fallback to _tools if available
                for tool_name, tool_info in self.mcp._tools.items():
                    self.discovered_tools[tool_name] = tool_info
                    logger.debug(f"Discovered tool via _tools: {tool_name}")
            else:
                logger.warning("Could not access tools from MCP instance")
                
        except Exception as e:
            logger.error(f"Error discovering tools: {e}")
            
    def get_service_lists(self, service: str) -> List[str]:
        """
        Get available list types for a service.
        
        Args:
            service: Service name (e.g., "forms", "gmail")
            
        Returns:
            List of available list types
        """
        # Normalize service name to lowercase
        service = service.lower()
        if service not in self.SERVICE_MAPPINGS:
            return []
        return list(self.SERVICE_MAPPINGS[service].keys())
        
    def get_list_config(self, service: str, list_type: str) -> Optional[Dict[str, Any]]:
        """
        Get configuration for a specific list type.
        
        Args:
            service: Service name
            list_type: List type name
            
        Returns:
            Configuration dictionary or None if not found
        """
        # Normalize service name to lowercase
        service = service.lower()
        # Normalize list_type to lowercase for case-insensitive lookup
        list_type = list_type.lower()
        return self.SERVICE_MAPPINGS.get(service, {}).get(list_type)
        
    async def get_list_items(self, service: str, list_type: str, user_email: str) -> Any:
        """
        Get all items/IDs for a list type.
        
        Args:
            service: Service name
            list_type: List type name
            user_email: User's Google email
            
        Returns:
            List of items or IDs, or the structured response from the tool
        """
        config = self.get_list_config(service, list_type)
        if not config:
            return []
            
        tool_name = config["tool"]
        
        # Check if tool exists in discovered tools
        if tool_name not in self.discovered_tools:
            logger.warning(f"Tool {tool_name} not found in discovered tools")
            return []
            
        # For tools that list IDs directly (no id_field), call the tool
        if not config.get("id_field"):
            try:
                # Get the tool and call it properly
                tool = self.discovered_tools[tool_name]
                
                # Call the tool with basic parameters
                # Since we're in a resource context, we need to call the tool's function
                if hasattr(tool, 'function'):
                    result = await tool.function(user_google_email=user_email)
                elif callable(tool):
                    result = await tool(user_google_email=user_email)
                else:
                    # Try to extract the callable from the tool object
                    if isinstance(tool, dict) and 'function' in tool:
                        result = await tool['function'](user_google_email=user_email)
                    else:
                        logger.error(f"Could not determine how to call tool {tool_name}")
                        return []
                
                # Return the structured result directly if it's already a dict/list
                if isinstance(result, (dict, list)):
                    return result
                    
                # Otherwise parse it as before
                return self._parse_list_result(result, service, list_type)
                
            except Exception as e:
                logger.error(f"Error calling {tool_name}: {e}")
                return []
        else:
            # For tools that need an ID parameter, we need to list available IDs first
            return await self._get_available_ids(service, list_type, user_email)
            
    async def get_list_item_details(
        self,
        service: str,
        list_type: str,
        item_id: str,
        user_email: str
    ) -> Any:
        """
        Get detailed data for a specific item.
        
        Args:
            service: Service name
            list_type: List type name
            item_id: Item ID
            user_email: User's Google email
            
        Returns:
            Detailed item data
        """
        config = self.get_list_config(service, list_type)
        if not config:
            return None
            
        # If there's an id_field, call the list tool with that ID
        if config.get("id_field"):
            tool_name = config["tool"]
            if tool_name not in self.discovered_tools:
                return None
                
            tool = self.discovered_tools[tool_name]
            
            # Build parameters with the ID field
            params = {
                "user_google_email": user_email,
                config["id_field"]: item_id
            }
            
            try:
                # Call the tool properly
                if hasattr(tool, 'function'):
                    result = await tool.function(**params)
                elif callable(tool):
                    result = await tool(**params)
                elif isinstance(tool, dict) and 'function' in tool:
                    result = await tool['function'](**params)
                else:
                    logger.error(f"Could not determine how to call tool {tool_name}")
                    return None
                    
                return result
            except Exception as e:
                logger.error(f"Error calling {tool_name} with ID {item_id}: {e}")
                return None
                
        # If there's a detail tool, use that
        elif config.get("detail_tool"):
            detail_tool_name = config["detail_tool"]
            if detail_tool_name not in self.discovered_tools:
                return None
                
            tool = self.discovered_tools[detail_tool_name]
            
            try:
                # Determine the ID parameter name
                # For albums -> album_id, for filters -> filter_id, etc.
                id_param_name = f"{list_type[:-1]}_id" if list_type.endswith('s') else f"{list_type}_id"
                
                params = {
                    "user_google_email": user_email,
                    id_param_name: item_id
                }
                
                # Call the tool properly
                if hasattr(tool, 'function'):
                    result = await tool.function(**params)
                elif callable(tool):
                    result = await tool(**params)
                elif isinstance(tool, dict) and 'function' in tool:
                    result = await tool['function'](**params)
                else:
                    logger.error(f"Could not determine how to call tool {detail_tool_name}")
                    return None
                    
                return result
            except Exception as e:
                logger.error(f"Error calling {detail_tool_name} for ID {item_id}: {e}")
                return None
                
        return None
        
    def _parse_list_result(self, result: Any, service: str, list_type: str) -> List[Dict[str, Any]]:
        """
        Parse the result from a list tool to extract items.
        
        Args:
            result: Raw result from tool (could be string, dict, or structured data)
            service: Service name
            list_type: List type name
            
        Returns:
            List of parsed items with IDs or the result itself if already structured
        """
        # If result is already a structured response (dict or list), return it
        if isinstance(result, dict):
            # Check if it has a standard structure with items
            if 'items' in result:
                return result['items']
            elif 'data' in result:
                return result['data']
            # Return as single item list
            return [result]
            
        if isinstance(result, list):
            return result
            
        # Otherwise, parse string results
        items = []
        result_str = str(result)
        
        # Service-specific parsing logic for string results
        if service == "forms" and list_type == "form_responses":
            # Parse form IDs from the response
            import re
            form_ids = re.findall(r'Form ID:\s*([^\s\n]+)', result_str)
            for form_id in form_ids:
                items.append({"id": form_id, "type": "form"})
                
        elif service == "photos" and list_type == "albums":
            # Check if it's a structured response first
            if isinstance(result, dict) and 'albums' in result:
                return result['albums']
            # Parse album IDs from string response
            import re
            album_matches = re.findall(r'ID:\s*([^\s\)]+)', result_str)
            for album_id in album_matches:
                items.append({"id": album_id, "type": "album"})
                
        elif service == "sheets" and list_type == "spreadsheets":
            # Check for structured response
            if isinstance(result, dict) and 'spreadsheets' in result:
                return result['spreadsheets']
            # Parse spreadsheet IDs from string
            import re
            sheet_matches = re.findall(r'\(ID:\s*([^\)]+)\)', result_str)
            for sheet_id in sheet_matches:
                items.append({"id": sheet_id, "type": "spreadsheet"})
                
        elif service == "calendar":
            if list_type == "calendars" and isinstance(result, dict) and 'calendars' in result:
                return result['calendars']
            elif list_type == "events" and isinstance(result, dict) and 'events' in result:
                return result['events']
                
        elif service == "chat" and list_type == "spaces":
            if isinstance(result, dict) and 'spaces' in result:
                return result['spaces']
                
        # Add more service-specific parsing as needed
        
        return items
        
    async def _get_available_ids(self, service: str, list_type: str, user_email: str) -> List[Dict[str, Any]]:
        """
        Get available IDs for services that require an ID parameter.
        
        Args:
            service: Service name
            list_type: List type name
            user_email: User's Google email
            
        Returns:
            List of available IDs
        """
        # This would need to call appropriate tools to list available items
        items = []
        
        if service == "forms" and list_type == "form_responses":
            # We would need a tool to list all forms
            # For now, return a placeholder
            items.append({
                "id": "placeholder", 
                "description": "Use a specific form ID to get responses"
            })
            
        elif service == "drive" and list_type == "items":
            # List root folder as default
            items.append({
                "id": "root",
                "description": "Root folder"
            })
            
        elif service == "calendar" and list_type == "events":
            # Would need to list calendars first
            items.append({
                "id": "primary",
                "description": "Primary calendar"
            })
            
        elif service == "docs" and list_type == "documents":
            # List root folder as default
            items.append({
                "id": "root",
                "description": "Root folder"
            })
            
        return items


def setup_service_list_resources(mcp: FastMCP) -> None:
    """
    Setup dynamic service list resources.
    
    Args:
        mcp: FastMCP instance to register resources with
    """
    logger.info("Setting up dynamic service list resources...")
    
    # Initialize discovery system
    discovery = ServiceListDiscovery(mcp)
    
    # Resource 1: List available list types for a service
    @mcp.resource(
        uri="service://{service}/lists",
        name="Service List Types",
        description="Get available list types for a Google service",
        mime_type="application/json",
        tags={"service", "lists", "discovery", "dynamic"},
        annotations={
            "readOnlyHint": True,
            "idempotentHint": True
        }
    )
    async def get_service_list_types(ctx: Context, service: str) -> dict:
        """Get available list types for a service."""
        # Normalize service name to lowercase for case-insensitive handling
        service_lower = service.lower()
        
        # Validate service parameter
        if service_lower not in VALID_SERVICES:
            return {
                "error": f"Service '{service}' not found or has no list types",
                "available_services": list(discovery.SERVICE_MAPPINGS.keys())
            }
            
        list_types = discovery.get_service_lists(service_lower)
        
        if not list_types:
            return {
                "error": f"Service '{service}' not found or has no list types",
                "available_services": list(discovery.SERVICE_MAPPINGS.keys())
            }
            
        # Return list types with descriptions
        result = {
            "service": service_lower,
            "list_types": []
        }
        
        for list_type in list_types:
            config = discovery.get_list_config(service_lower, list_type)
            result["list_types"].append({
                "name": list_type,
                "description": config.get("description", ""),
                "has_detail_view": bool(config.get("detail_tool") or config.get("id_field"))
            })
            
        return result
        
    # Resource 2: List all items/IDs for a specific list type
    @mcp.resource(
        uri="service://{service}/{list_type}",
        name="Service List Items",
        description="Get all items/IDs for a specific list type",
        mime_type="application/json",
        tags={"service", "lists", "items", "dynamic"},
        annotations={
            "readOnlyHint": True,
            "idempotentHint": False  # May change as new items are added
        }
    )
    async def get_service_list_items(ctx: Context, service: str, list_type: str) -> dict:
        """Get all items for a specific list type."""
        # Normalize service name to lowercase for case-insensitive handling
        service_lower = service.lower()
        
        # Validate service parameter
        if service_lower not in VALID_SERVICES:
            return {
                "error": f"Service '{service}' not found",
                "available_services": list(discovery.SERVICE_MAPPINGS.keys())
            }
            
        # Check if list type is valid BEFORE checking authentication
        # Normalize list_type for case-insensitive comparison
        list_type_lower = list_type.lower()
        config = discovery.get_list_config(service_lower, list_type_lower)
        if not config:
            return {
                "error": f"List type '{list_type}' not found for service '{service}'",
                "available_list_types": discovery.get_service_lists(service_lower)
            }
            
        # Now check for user email from context
        # FastMCP Context might not have metadata attribute, handle gracefully
        user_email = None
        if hasattr(ctx, 'metadata') and ctx.metadata:
            user_email = ctx.metadata.get("user_email")
        elif hasattr(ctx, 'user_email'):
            user_email = ctx.user_email
        elif hasattr(ctx, 'session') and hasattr(ctx.session, 'user_email'):
            user_email = ctx.session.user_email
            
        if not user_email:
            return {"error": "User email not found in context - authentication required"}
            
        items = await discovery.get_list_items(service_lower, list_type_lower, user_email)
        
        # Handle different response types
        if isinstance(items, dict):
            # Already structured response
            return {
                "service": service_lower,
                "list_type": list_type_lower,
                "description": config.get("description", ""),
                **items  # Include the structured data
            }
        elif isinstance(items, list):
            # List of items
            return {
                "service": service_lower,
                "list_type": list_type_lower,
                "description": config.get("description", ""),
                "count": len(items),
                "items": items
            }
        else:
            # Fallback for unexpected types
            return {
                "service": service_lower,
                "list_type": list_type_lower,
                "description": config.get("description", ""),
                "data": items
            }
        
    # Resource 3: Get detailed data for a specific item
    @mcp.resource(
        uri="service://{service}/{list_type}/{item_id}",
        name="Service List Item Details",
        description="Get detailed data for a specific item",
        mime_type="application/json",
        tags={"service", "lists", "detail", "dynamic"},
        annotations={
            "readOnlyHint": True,
            "idempotentHint": False  # Item details may change
        }
    )
    async def get_service_list_item_details(
        ctx: Context,
        service: str,
        list_type: str,
        item_id: str
    ) -> dict:
        """Get detailed data for a specific item."""
        # Normalize service name to lowercase for case-insensitive handling
        service_lower = service.lower()
        
        # Validate service parameter
        if service_lower not in VALID_SERVICES:
            return {
                "error": f"Service '{service}' not found",
                "available_services": list(discovery.SERVICE_MAPPINGS.keys())
            }
            
        # Get user email from context
        # FastMCP Context might not have metadata attribute, handle gracefully
        user_email = None
        if hasattr(ctx, 'metadata') and ctx.metadata:
            user_email = ctx.metadata.get("user_email")
        elif hasattr(ctx, 'user_email'):
            user_email = ctx.user_email
        elif hasattr(ctx, 'session') and hasattr(ctx.session, 'user_email'):
            user_email = ctx.session.user_email
            
        if not user_email:
            return {"error": "User email not found in context - authentication required"}
            
        # Normalize list_type for case-insensitive comparison
        list_type_lower = list_type.lower()
        config = discovery.get_list_config(service_lower, list_type_lower)
        if not config:
            return {
                "error": f"List type '{list_type}' not found for service '{service}'",
                "available_list_types": discovery.get_service_lists(service_lower)
            }
            
        details = await discovery.get_list_item_details(service_lower, list_type_lower, item_id, user_email)
        
        if details is None:
            return {
                "error": f"Could not retrieve details for item '{item_id}'",
                "service": service,
                "list_type": list_type
            }
            
        # Return structured response
        if isinstance(details, dict):
            return {
                "service": service_lower,
                "list_type": list_type_lower,
                "item_id": item_id,
                **details  # Include the structured details
            }
        else:
            return {
                "service": service_lower,
                "list_type": list_type_lower,
                "item_id": item_id,
                "data": details
            }
        
    logger.info(f"✅ Registered services with dynamic list resources")
    
    # Log discovered services and their list types
    if hasattr(discovery, 'SERVICE_MAPPINGS'):
        logger.info(f"  Active services with list resources: {len(discovery.SERVICE_MAPPINGS)}")
        for service, list_types in discovery.SERVICE_MAPPINGS.items():
            logger.info(f"  - {service}: {', '.join(list_types.keys())}")
    else:
        logger.warning("SERVICE_MAPPINGS not initialized properly")