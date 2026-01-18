"""
Prompt Tool Optimization Helper

This module provides helper functions for generating tool optimization sections
in prompts. It leverages the ScopeRegistry service metadata and provides
dynamic tool filtering recommendations based on Google service names.

Usage:
    from prompts.tool_optimization_helper import ToolOptimizationHelper

    # Generate optimization section for Gmail prompts
    section = ToolOptimizationHelper.generate_optimization_section(
        include_services=["gmail"],
        prompt_name="quick_email_demo"
    )

    # Generate for multiple services
    section = ToolOptimizationHelper.generate_optimization_section(
        include_services=["chat", "drive", "calendar"],
        prompt_name="workspace_integration"
    )
"""

from typing import Dict, List, Optional, Set

from auth.scope_registry import ScopeRegistry


class ToolOptimizationHelper:
    """Helper class for generating tool optimization sections in prompts."""

    # Mapping of service names to their associated tool names
    # This is the single source of truth for service-to-tool mappings
    SERVICE_TOOLS: Dict[str, List[str]] = {
        "gmail": [
            "send_gmail_message",
            "search_gmail_messages",
            "get_gmail_message_content",
            "get_gmail_messages_content_batch",
            "get_gmail_thread_content",
            "draft_gmail_message",
            "reply_to_gmail_message",
            "draft_gmail_reply",
            "forward_gmail_message",
            "draft_gmail_forward",
            "list_gmail_labels",
            "manage_gmail_label",
            "modify_gmail_message_labels",
            "list_gmail_filters",
            "create_gmail_filter",
            "get_gmail_filter",
            "delete_gmail_filter",
            "manage_gmail_allow_list",
        ],
        "drive": [
            "upload_to_drive",
            "search_drive_files",
            "get_drive_file_content",
            "list_drive_items",
            "create_drive_file",
            "share_drive_files",
            "make_drive_files_public",
            "manage_drive_files",
        ],
        "calendar": [
            "list_calendars",
            "create_calendar",
            "list_events",
            "create_event",
            "modify_event",
            "delete_event",
            "bulk_calendar_operations",
            "move_events_between_calendars",
            "get_event",
        ],
        "docs": [
            "search_docs",
            "get_doc_content",
            "list_docs_in_folder",
            "create_doc",
        ],
        "sheets": [
            "list_spreadsheets",
            "get_spreadsheet_info",
            "read_sheet_values",
            "modify_sheet_values",
            "create_spreadsheet",
            "create_sheet",
            "format_sheet_range",
        ],
        "chat": [
            "list_spaces",
            "list_messages",
            "send_message",
            "search_messages",
            "send_card_message",
            "send_simple_card",
            "send_interactive_card",
            "send_form_card",
            "send_rich_card",
            "send_dynamic_card",
        ],
        "forms": [
            "create_form",
            "add_questions_to_form",
            "get_form",
            "set_form_publish_state",
            "publish_form_publicly",
            "get_form_response",
            "list_form_responses",
            "update_form_questions",
        ],
        "slides": [
            "create_presentation",
            "get_presentation_info",
            "add_slide",
            "update_slide_content",
            "export_and_download_presentation",
        ],
        "photos": [
            "list_photos_albums",
            "search_photos",
            "list_album_photos",
            "get_photo_details",
            "create_photos_album",
            "get_photos_library_info",
            "photos_smart_search",
            "photos_batch_details",
            "photos_performance_stats",
            "photos_optimized_album_sync",
            "upload_photos",
            "upload_folder_photos",
        ],
        "people": [
            "list_people_contact_labels",
            "get_people_contact_group_members",
            "manage_people_contact_labels",
        ],
    }

    # Protected tools that should always remain available
    PROTECTED_TOOLS: Set[str] = {
        "manage_tools",
        "manage_tools_by_analytics",
        "health_check",
        "start_google_auth",
        "check_drive_auth",
    }

    # Tool categories for better organization in documentation
    TOOL_CATEGORIES: Dict[str, Dict[str, List[str]]] = {
        "gmail": {
            "Send/Draft": ["send_gmail_message", "draft_gmail_message", "reply_to_gmail_message", "forward_gmail_message"],
            "Search/Read": ["search_gmail_messages", "get_gmail_message_content", "get_gmail_thread_content"],
            "Labels": ["list_gmail_labels", "manage_gmail_label", "modify_gmail_message_labels"],
            "Filters": ["list_gmail_filters", "create_gmail_filter", "delete_gmail_filter"],
        },
        "drive": {
            "Upload/Create": ["upload_to_drive", "create_drive_file"],
            "Search/List": ["search_drive_files", "list_drive_items", "get_drive_file_content"],
            "Manage": ["share_drive_files", "make_drive_files_public", "manage_drive_files"],
        },
        "calendar": {
            "List/Get": ["list_calendars", "list_events", "get_event"],
            "Create/Modify": ["create_calendar", "create_event", "modify_event"],
            "Delete/Bulk": ["delete_event", "bulk_calendar_operations", "move_events_between_calendars"],
        },
        "chat": {
            "Spaces": ["list_spaces", "list_messages", "search_messages"],
            "Basic": ["send_message", "send_card_message"],
            "Cards": ["send_simple_card", "send_interactive_card", "send_form_card", "send_rich_card", "send_dynamic_card"],
        },
        "sheets": {
            "Read": ["list_spreadsheets", "get_spreadsheet_info", "read_sheet_values"],
            "Write": ["modify_sheet_values", "create_spreadsheet", "create_sheet"],
            "Format": ["format_sheet_range"],
        },
        "forms": {
            "Create": ["create_form", "add_questions_to_form", "update_form_questions"],
            "Manage": ["get_form", "set_form_publish_state", "publish_form_publicly"],
            "Responses": ["get_form_response", "list_form_responses"],
        },
        "slides": {
            "Create": ["create_presentation", "add_slide"],
            "Manage": ["get_presentation_info", "update_slide_content", "export_and_download_presentation"],
        },
        "photos": {
            "Albums": ["list_photos_albums", "list_album_photos", "create_photos_album"],
            "Search": ["search_photos", "photos_smart_search"],
            "Details": ["get_photo_details", "photos_batch_details", "get_photos_library_info"],
            "Upload": ["upload_photos", "upload_folder_photos"],
            "Advanced": ["photos_performance_stats", "photos_optimized_album_sync"],
        },
        "people": {
            "Labels": ["list_people_contact_labels", "get_people_contact_group_members", "manage_people_contact_labels"],
        },
        "docs": {
            "Read": ["search_docs", "get_doc_content", "list_docs_in_folder"],
            "Create": ["create_doc"],
        },
    }

    @classmethod
    def get_tools_for_services(
        cls,
        include_services: List[str],
        exclude_services: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Get all tools for the specified services.

        Args:
            include_services: List of service names to include (e.g., ["gmail", "drive"])
            exclude_services: Optional list of service names to exclude

        Returns:
            List of tool names for the specified services
        """
        tools: Set[str] = set()
        exclude_services = exclude_services or []

        for service in include_services:
            if service in cls.SERVICE_TOOLS and service not in exclude_services:
                tools.update(cls.SERVICE_TOOLS[service])

        return sorted(list(tools))

    @classmethod
    def get_all_service_names(cls) -> List[str]:
        """Get all available service names."""
        return sorted(list(cls.SERVICE_TOOLS.keys()))

    @classmethod
    def get_service_metadata(cls, service: str) -> Optional[dict]:
        """
        Get service metadata from ScopeRegistry.

        Args:
            service: Service name

        Returns:
            Service metadata dict or None
        """
        metadata = ScopeRegistry.get_service_metadata(service)
        if metadata:
            return {
                "name": metadata.name,
                "description": metadata.description,
                "icon": metadata.icon,
                "features": metadata.features,
            }
        return None

    @classmethod
    def generate_tool_list_string(
        cls,
        services: List[str],
        format_type: str = "python_list",
    ) -> str:
        """
        Generate a formatted string of tools for the specified services.

        Args:
            services: List of service names
            format_type: "python_list", "comma_separated", or "bullet_points"

        Returns:
            Formatted string of tool names
        """
        tools = cls.get_tools_for_services(services)

        if format_type == "python_list":
            # Format as Python list for code blocks
            tool_strings = [f'"{tool}"' for tool in tools]
            # Break into lines of ~4 tools each for readability
            lines = []
            for i in range(0, len(tool_strings), 4):
                chunk = tool_strings[i:i + 4]
                lines.append(", ".join(chunk))
            return ",\n        ".join(lines)

        elif format_type == "comma_separated":
            return ", ".join(tools)

        elif format_type == "bullet_points":
            return "\n".join([f"- `{tool}`" for tool in tools])

        return str(tools)

    @classmethod
    def generate_categorized_tool_list(cls, services: List[str]) -> str:
        """
        Generate a categorized tool list for documentation.

        Args:
            services: List of service names

        Returns:
            Markdown-formatted categorized tool list
        """
        lines = []
        for service in services:
            if service in cls.TOOL_CATEGORIES:
                metadata = cls.get_service_metadata(service)
                service_name = metadata["name"] if metadata else service.title()
                icon = metadata["icon"] if metadata else "🔧"

                lines.append(f"**{icon} {service_name} Tools:**")
                for category, tools in cls.TOOL_CATEGORIES[service].items():
                    tool_list = ", ".join([f"`{t}`" for t in tools])
                    lines.append(f"- **{category}**: {tool_list}")
                lines.append("")

        return "\n".join(lines)

    @classmethod
    def generate_optimization_section(
        cls,
        include_services: List[str],
        prompt_name: Optional[str] = None,
        include_service_list: bool = True,
        include_code_block: bool = True,
        include_tool_categories: bool = True,
    ) -> str:
        """
        Generate a complete tool optimization section for a prompt.

        Args:
            include_services: List of service names to include
            prompt_name: Optional name of the prompt (for context)
            include_service_list: Whether to include list of all service names
            include_code_block: Whether to include the manage_tools code block
            include_tool_categories: Whether to include categorized tool list

        Returns:
            Complete markdown section for tool optimization
        """
        tools = cls.get_tools_for_services(include_services)
        tool_list_str = cls.generate_tool_list_string(include_services)

        # Build the section
        lines = [
            "## 🔧 **IMPORTANT: Tool Optimization**",
            "",
            "**Before using this prompt, optimize your session by disabling unrelated tools:**",
            "",
        ]

        if include_code_block:
            services_comment = ", ".join([s.title() for s in include_services])
            lines.extend([
                "```python",
                f"# Disable all tools except {services_comment}-related ones for better performance",
                "await manage_tools(",
                '    action="disable_all_except",',
                "    tool_names=[",
                f"        {tool_list_str}",
                "    ],",
                '    scope="session"',
                ")",
                "```",
                "",
            ])

        if include_tool_categories:
            lines.append("**Relevant Tools for this prompt:**")
            lines.append(cls.generate_categorized_tool_list(include_services))

        if include_service_list:
            all_services = cls.get_all_service_names()
            service_list = ", ".join([f"`{s}`" for s in all_services])
            lines.extend([
                "**All available service names for manage_tools:**",
                service_list,
                "",
            ])

        lines.append("---")
        lines.append("")

        return "\n".join(lines)

    @classmethod
    def generate_multi_service_section(
        cls,
        service_examples: Optional[Dict[str, List[str]]] = None,
    ) -> str:
        """
        Generate a tool optimization section that shows examples for multiple services.
        Useful for prompts that demonstrate capabilities across services.

        Args:
            service_examples: Optional dict of service_name -> tool subset
                             If None, uses default representative tools per service

        Returns:
            Complete markdown section with multiple service examples
        """
        if service_examples is None:
            # Default representative tools per service
            service_examples = {
                "gmail": ["send_gmail_message", "search_gmail_messages", "draft_gmail_message"],
                "drive": ["upload_to_drive", "search_drive_files", "list_drive_items"],
                "calendar": ["create_event", "list_events", "modify_event"],
                "chat": ["send_message", "send_dynamic_card", "list_spaces"],
                "forms": ["create_form", "add_questions_to_form", "get_form"],
                "slides": ["create_presentation", "add_slide", "get_presentation_info"],
                "sheets": ["list_spreadsheets", "read_sheet_values", "modify_sheet_values"],
                "photos": ["list_photos_albums", "search_photos", "upload_photos"],
                "people": ["list_people_contact_labels", "get_people_contact_group_members"],
                "docs": ["search_docs", "get_doc_content", "create_doc"],
            }

        lines = [
            "## 🔧 **IMPORTANT: Tool Optimization**",
            "",
            "**Before using this prompt, optimize your session by disabling unrelated tools.**",
            "",
            "Choose the appropriate service based on what you're demonstrating:",
            "",
            "```python",
            "# Select the service you want to work with:",
            "",
        ]

        for service, tools in service_examples.items():
            metadata = cls.get_service_metadata(service)
            service_display = metadata["name"] if metadata else service.title()
            tool_str = ", ".join([f'"{t}"' for t in tools])
            lines.append(f"# For {service_display}:")
            lines.append(f'await manage_tools(action="disable_all_except", tool_names=[{tool_str}], scope="session")')
            lines.append("")

        lines.extend([
            "```",
            "",
            "**All Google Service Names:**",
        ])

        for service in sorted(service_examples.keys()):
            metadata = cls.get_service_metadata(service)
            if metadata:
                lines.append(f"- `{service}` - {metadata['description'][:50]}...")
            else:
                lines.append(f"- `{service}`")

        lines.extend([
            "",
            "---",
            "",
        ])

        return "\n".join(lines)


# Convenience functions for direct use in prompts
def get_gmail_optimization_section() -> str:
    """Get tool optimization section for Gmail prompts."""
    return ToolOptimizationHelper.generate_optimization_section(
        include_services=["gmail"],
        include_service_list=False,
    )


def get_chat_optimization_section() -> str:
    """Get tool optimization section for Chat prompts."""
    return ToolOptimizationHelper.generate_optimization_section(
        include_services=["chat"],
        include_service_list=False,
    )


def get_sheets_optimization_section() -> str:
    """Get tool optimization section for Sheets prompts."""
    return ToolOptimizationHelper.generate_optimization_section(
        include_services=["sheets"],
        include_service_list=False,
    )


def get_drive_optimization_section() -> str:
    """Get tool optimization section for Drive prompts."""
    return ToolOptimizationHelper.generate_optimization_section(
        include_services=["drive"],
        include_service_list=False,
    )


def get_calendar_optimization_section() -> str:
    """Get tool optimization section for Calendar prompts."""
    return ToolOptimizationHelper.generate_optimization_section(
        include_services=["calendar"],
        include_service_list=False,
    )


def get_photos_optimization_section() -> str:
    """Get tool optimization section for Photos prompts."""
    return ToolOptimizationHelper.generate_optimization_section(
        include_services=["photos"],
        include_service_list=False,
    )


def get_people_optimization_section() -> str:
    """Get tool optimization section for People prompts."""
    return ToolOptimizationHelper.generate_optimization_section(
        include_services=["people"],
        include_service_list=False,
    )


def get_multi_service_optimization_section() -> str:
    """Get tool optimization section for multi-service prompts."""
    return ToolOptimizationHelper.generate_multi_service_section()


# Export all public functions and classes
__all__ = [
    "ToolOptimizationHelper",
    "get_gmail_optimization_section",
    "get_chat_optimization_section",
    "get_sheets_optimization_section",
    "get_drive_optimization_section",
    "get_calendar_optimization_section",
    "get_photos_optimization_section",
    "get_people_optimization_section",
    "get_multi_service_optimization_section",
]
