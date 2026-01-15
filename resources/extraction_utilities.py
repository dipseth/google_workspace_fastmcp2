"""
Enhanced tool extraction utilities for FastMCP2.

This module provides utilities for dynamically discovering and accessing tools
from the MCP registry instead of relying on hardcoded imports.
"""

from typing import Callable, Dict, List, Optional

from fastmcp import FastMCP

from config.enhanced_logging import setup_logger

logger = setup_logger()


def get_tools_for_service(
    mcp_server: FastMCP, service_name: str
) -> Dict[str, Callable]:
    """
    Get all tools for a specific service using registry access.

    Args:
        mcp_server: FastMCP server instance
        service_name: Name of the service (e.g., 'gmail', 'calendar')

    Returns:
        Dict mapping tool names to callable functions
    """
    if not hasattr(mcp_server, "_tool_manager") or not hasattr(
        mcp_server._tool_manager, "_tools"
    ):
        logger.error("❌ Cannot access FastMCP tool manager")
        return {}

    registered_tools = mcp_server._tool_manager._tools
    service_tools = {}

    for tool_name, tool_instance in registered_tools.items():
        # Use naming convention and tags to identify service
        if (
            service_name in tool_name.lower()
            or (hasattr(tool_instance, "tags") and service_name in tool_instance.tags)
            or tool_name.startswith(f"list_{service_name}")
            or tool_name.startswith(f"{service_name}_")
        ):

            service_tools[tool_name] = (
                tool_instance.fn if hasattr(tool_instance, "fn") else tool_instance
            )
            logger.debug(f"Found {service_name} tool: {tool_name}")

    return service_tools


def get_tool_by_name(mcp_server: FastMCP, tool_name: str) -> Optional[Callable]:
    """
    Get a specific tool by name from the registry.

    Args:
        mcp_server: FastMCP server instance
        tool_name: Exact name of the tool

    Returns:
        Tool callable or None if not found
    """
    if not hasattr(mcp_server, "_tool_manager") or not hasattr(
        mcp_server._tool_manager, "_tools"
    ):
        logger.error("❌ Cannot access FastMCP tool manager")
        return None

    registered_tools = mcp_server._tool_manager._tools

    if tool_name in registered_tools:
        tool_instance = registered_tools[tool_name]
        return tool_instance.fn if hasattr(tool_instance, "fn") else tool_instance

    logger.warning(f"Tool '{tool_name}' not found in registry")
    return None


def categorize_tools_by_service(mcp_server: FastMCP) -> Dict[str, List[str]]:
    """
    Categorize all registered tools by service.

    Args:
        mcp_server: FastMCP server instance

    Returns:
        Dict mapping service names to lists of tool names
    """
    if not hasattr(mcp_server, "_tool_manager") or not hasattr(
        mcp_server._tool_manager, "_tools"
    ):
        logger.error("❌ Cannot access FastMCP tool manager")
        return {}

    registered_tools = mcp_server._tool_manager._tools
    service_categories = {
        "gmail": [],
        "drive": [],
        "calendar": [],
        "forms": [],
        "sheets": [],
        "docs": [],
        "chat": [],
        "photos": [],
        "slides": [],
    }

    for tool_name, tool_instance in registered_tools.items():
        # Categorize by naming patterns
        for service in service_categories.keys():
            if (
                service in tool_name.lower()
                or tool_name.startswith(f"list_{service}")
                or tool_name.startswith(f"{service}_")
                or (
                    hasattr(tool_instance, "tags")
                    and service in getattr(tool_instance, "tags", [])
                )
            ):
                service_categories[service].append(tool_name)
                break

    return service_categories


def get_list_tools_mapping() -> Dict[str, Dict[str, str]]:
    """
    Get the expected mapping of services to list tools.
    This provides fallback information when registry access fails.

    Returns:
        Dict mapping services to their list tool configurations
    """
    return {
        "gmail": {"filters": "list_gmail_filters", "labels": "list_gmail_labels"},
        "drive": {"items": "list_drive_items"},
        "calendar": {"calendars": "list_calendars", "events": "list_events"},
        "forms": {"form_responses": "list_form_responses"},
        "sheets": {"spreadsheets": "list_spreadsheets"},
        "docs": {"documents": "list_docs_in_folder"},
        "chat": {"spaces": "list_spaces"},
        "photos": {"albums": "list_photos_albums"},
    }


def get_service_tool_for_list_type(service: str, list_type: str) -> Optional[str]:
    """
    Get the tool name for a specific service list type.

    Args:
        service: Service name (e.g., 'gmail')
        list_type: List type (e.g., 'labels')

    Returns:
        Tool name or None if not found
    """
    mapping = get_list_tools_mapping()
    return mapping.get(service, {}).get(list_type)


def verify_tool_availability(mcp_server: FastMCP, tool_name: str) -> bool:
    """
    Verify that a tool is available in the registry.

    Args:
        mcp_server: FastMCP server instance
        tool_name: Name of the tool to check

    Returns:
        True if tool is available, False otherwise
    """
    tool = get_tool_by_name(mcp_server, tool_name)
    return tool is not None
