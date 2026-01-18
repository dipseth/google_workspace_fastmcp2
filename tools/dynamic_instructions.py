"""
Dynamic MCP Server Instructions Module.

This module provides functionality to populate MCP server instructions dynamically
using data from Qdrant vector database collections. Instructions are enhanced with:
- Tool usage analytics and popularity metrics
- Recent activity patterns and service health indicators
- Dynamic tips based on historical usage data
- Service metadata from ScopeRegistry (icons, descriptions, features)

The instructions are updated on server startup/connection after Qdrant middleware
initializes, providing users with contextual, data-driven guidance.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from auth.scope_registry import ScopeRegistry
from config.enhanced_logging import setup_logger
from config.settings import settings

logger = setup_logger()


def _build_services_section() -> str:
    """
    Build the Available Services section using ScopeRegistry metadata.

    Returns:
        Formatted markdown string with service information
    """
    lines = ["## Available Services"]

    # Get all services from the registry
    for service_name in ScopeRegistry.get_all_services():
        metadata = ScopeRegistry.get_service_metadata(service_name)
        if metadata:
            # Format: - **📁 Google Drive**: Cloud storage and file synchronization service
            lines.append(
                f"- **{metadata.icon} {metadata.name}**: {metadata.description}"
            )

    return "\n".join(lines)


def _build_base_instructions() -> str:
    """
    Build complete base instructions using ScopeRegistry for service information.

    Returns:
        Complete base instructions string
    """
    services_section = _build_services_section()

    return f"""Google Workspace MCP Server - Comprehensive access to Google services.

## Authentication
1. Call `start_google_auth` with your email to begin OAuth flow
2. Complete authentication in browser
3. Call `check_drive_auth` to verify credentials

{services_section}

## Tool Management
Use `manage_tools` to list, enable, or disable tools at runtime."""


# Build base instructions using registry data
BASE_INSTRUCTIONS = _build_base_instructions()


class DynamicInstructionsBuilder:
    """
    Builds dynamic MCP server instructions using Qdrant analytics data.

    This class queries Qdrant collections to gather usage statistics and
    generates enhanced instructions that include:
    - Most frequently used tools
    - Recent activity summaries
    - Service health indicators
    - Contextual tips based on usage patterns
    """

    def __init__(self, qdrant_middleware: Optional[Any] = None):
        """
        Initialize the dynamic instructions builder.

        Args:
            qdrant_middleware: Optional QdrantUnifiedMiddleware instance for data access
        """
        self.qdrant_middleware = qdrant_middleware
        self._cached_instructions: Optional[str] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_seconds = 300  # 5 minute cache

    @property
    def is_qdrant_available(self) -> bool:
        """Check if Qdrant middleware is available and initialized."""
        if not self.qdrant_middleware:
            return False
        try:
            return (
                hasattr(self.qdrant_middleware, "client_manager")
                and self.qdrant_middleware.client_manager.is_available
            )
        except Exception:
            return False

    async def get_tool_analytics(self) -> Optional[Dict]:
        """
        Fetch tool usage analytics from Qdrant.

        Returns:
            Dict with analytics data or None if unavailable
        """
        if not self.is_qdrant_available:
            logger.debug("📊 Qdrant not available for analytics")
            return None

        try:
            # Access the search manager from the middleware
            search_manager = self.qdrant_middleware.search_manager
            if not search_manager:
                logger.debug("📊 Search manager not available")
                return None

            # Get analytics grouped by tool_name
            analytics = await search_manager.get_analytics(group_by="tool_name")

            if analytics and not analytics.get("error"):
                logger.info(
                    f"📊 Retrieved analytics: {analytics.get('total_responses', 0)} total responses"
                )
                return analytics
            else:
                logger.debug(f"📊 Analytics returned error or empty: {analytics}")
                return None

        except Exception as e:
            logger.warning(f"📊 Failed to get tool analytics: {e}")
            return None

    async def get_service_analytics(self) -> Optional[Dict]:
        """
        Fetch service-level analytics from Qdrant.

        Returns:
            Dict with service analytics or None if unavailable
        """
        if not self.is_qdrant_available:
            return None

        try:
            search_manager = self.qdrant_middleware.search_manager
            if not search_manager:
                return None

            # Get analytics grouped by service field
            analytics = await search_manager.get_analytics(group_by="service")

            if analytics and not analytics.get("error"):
                return analytics
            return None

        except Exception as e:
            logger.warning(f"📊 Failed to get service analytics: {e}")
            return None

    def _format_popular_tools(self, analytics: Dict, top_n: int = 5) -> str:
        """
        Format the most popular tools section.

        Args:
            analytics: Tool analytics data
            top_n: Number of top tools to include

        Returns:
            Formatted string for popular tools section
        """
        if not analytics or not analytics.get("groups"):
            return ""

        groups = analytics["groups"]

        # Sort by count descending
        sorted_tools = sorted(
            [(name, data) for name, data in groups.items() if name != "unknown"],
            key=lambda x: x[1].get("count", 0),
            reverse=True,
        )[:top_n]

        if not sorted_tools:
            return ""

        lines = ["## 📊 Popular Tools (Based on Usage)"]
        for i, (tool_name, data) in enumerate(sorted_tools, 1):
            count = data.get("count", 0)
            recent_24h = data.get("recent_activity", {}).get("last_24h", 0)

            # Format tool name nicely
            display_name = tool_name.replace("_", " ").title()

            activity_indicator = ""
            if recent_24h > 0:
                activity_indicator = f" 🔥 ({recent_24h} recent)"

            lines.append(f"{i}. **{display_name}** - {count} uses{activity_indicator}")

        return "\n".join(lines)

    def _format_service_health(self, service_analytics: Dict) -> str:
        """
        Format service health/activity indicators using ScopeRegistry metadata.

        Args:
            service_analytics: Service-level analytics data

        Returns:
            Formatted string for service health section
        """
        if not service_analytics or not service_analytics.get("groups"):
            return ""

        groups = service_analytics["groups"]

        active_services = []
        for service_name, data in groups.items():
            if service_name == "unknown":
                continue

            recent_7d = data.get("recent_activity", {}).get("last_7d", 0)
            if recent_7d > 0:
                # Get icon from ScopeRegistry metadata
                metadata = ScopeRegistry.get_service_metadata(service_name.lower())
                if metadata:
                    active_services.append(f"{metadata.icon} {metadata.name}")
                else:
                    # Fallback for services not in registry
                    active_services.append(f"✅ {service_name.title()}")

        if not active_services:
            return ""

        return f"\n## 🟢 Active Services (Last 7 Days)\n{', '.join(active_services)}"

    def _format_usage_tips(self, analytics: Dict) -> str:
        """
        Generate contextual tips based on usage patterns.

        Args:
            analytics: Analytics data

        Returns:
            Formatted string with usage tips
        """
        if not analytics:
            return ""

        tips = []

        # Tip based on total responses
        total = analytics.get("total_responses", 0)
        if total > 0:
            tips.append(f"💡 This server has processed **{total:,}** tool invocations")

        # Tip about error rate
        summary = analytics.get("summary", {})
        error_rate = summary.get("overall_error_rate", 0)
        if error_rate > 0.1:
            tips.append("⚠️ Some tools have elevated error rates - check authentication")
        elif error_rate < 0.01 and total > 100:
            tips.append("✨ Server health excellent - low error rate")

        # Tip about unique users
        unique_users = summary.get("total_unique_users", 0)
        if unique_users > 1:
            tips.append(f"👥 {unique_users} users have used this server")

        if not tips:
            return ""

        return "\n## 💡 Server Insights\n" + "\n".join(tips)

    def _format_qdrant_status(self) -> str:
        """
        Format Qdrant connection status for instructions.

        Returns:
            Formatted string indicating Qdrant status
        """
        if self.is_qdrant_available:
            collection = (
                settings.tool_collection
                if hasattr(settings, "tool_collection")
                else "mcp_tool_responses"
            )
            return f"\n## 🗄️ Vector Database\nQdrant connected: `{collection}` collection available for semantic search and analytics."
        else:
            return "\n## 🗄️ Vector Database\nQdrant: Offline (analytics unavailable)"

    async def build_dynamic_instructions(self, force_refresh: bool = False) -> str:
        """
        Build complete dynamic instructions incorporating Qdrant data.

        Args:
            force_refresh: If True, bypass cache and rebuild instructions

        Returns:
            Complete instructions string with dynamic content
        """
        # Check cache validity
        if not force_refresh and self._cached_instructions:
            if self._cache_timestamp:
                age = (
                    datetime.now(timezone.utc) - self._cache_timestamp
                ).total_seconds()
                if age < self._cache_ttl_seconds:
                    logger.debug(f"📋 Using cached instructions (age: {age:.1f}s)")
                    return self._cached_instructions

        logger.info("📋 Building dynamic instructions from Qdrant data...")

        # Start with base instructions
        sections = [BASE_INSTRUCTIONS]

        # Add Qdrant status
        sections.append(self._format_qdrant_status())

        # Try to add dynamic content from Qdrant
        if self.is_qdrant_available:
            try:
                # Get tool analytics
                tool_analytics = await self.get_tool_analytics()

                if tool_analytics:
                    # Add popular tools section
                    popular_tools = self._format_popular_tools(tool_analytics)
                    if popular_tools:
                        sections.append(popular_tools)

                    # Add usage tips
                    usage_tips = self._format_usage_tips(tool_analytics)
                    if usage_tips:
                        sections.append(usage_tips)

                # Get service analytics
                service_analytics = await self.get_service_analytics()
                if service_analytics:
                    service_health = self._format_service_health(service_analytics)
                    if service_health:
                        sections.append(service_health)

            except Exception as e:
                logger.warning(f"📋 Error building dynamic sections: {e}")
                # Continue with base instructions

        # Add timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        sections.append(f"\n---\n*Instructions updated: {timestamp}*")

        # Join all sections
        instructions = "\n".join(sections)

        # Cache the result
        self._cached_instructions = instructions
        self._cache_timestamp = datetime.now(timezone.utc)

        logger.info(f"📋 Dynamic instructions built ({len(instructions)} chars)")
        return instructions

    def invalidate_cache(self) -> None:
        """Invalidate the cached instructions, forcing rebuild on next access."""
        self._cached_instructions = None
        self._cache_timestamp = None
        logger.debug("📋 Instructions cache invalidated")


# Module-level builder instance (lazy initialization)
_builder: Optional[DynamicInstructionsBuilder] = None


def get_instructions_builder(
    qdrant_middleware: Optional[Any] = None,
) -> DynamicInstructionsBuilder:
    """
    Get or create the global DynamicInstructionsBuilder instance.

    Args:
        qdrant_middleware: Optional QdrantUnifiedMiddleware to use

    Returns:
        DynamicInstructionsBuilder instance
    """
    global _builder

    if _builder is None or (
        qdrant_middleware and _builder.qdrant_middleware != qdrant_middleware
    ):
        _builder = DynamicInstructionsBuilder(qdrant_middleware)
        logger.debug("📋 Created new DynamicInstructionsBuilder instance")

    return _builder


async def update_mcp_instructions(
    mcp: Any, qdrant_middleware: Optional[Any] = None
) -> bool:
    """
    Update the MCP server's instructions with dynamic content from Qdrant.

    This function should be called after Qdrant middleware is initialized in server.py.
    It builds dynamic instructions and updates the mcp.instructions property.

    Args:
        mcp: FastMCP server instance
        qdrant_middleware: Optional QdrantUnifiedMiddleware instance

    Returns:
        bool: True if instructions were updated successfully
    """
    try:
        builder = get_instructions_builder(qdrant_middleware)

        # Build dynamic instructions
        dynamic_instructions = await builder.build_dynamic_instructions()

        # Update MCP instructions property
        mcp.instructions = dynamic_instructions

        logger.info("✅ MCP instructions updated with dynamic content from Qdrant")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to update MCP instructions: {e}")
        return False


async def refresh_instructions(mcp: Any) -> bool:
    """
    Force refresh the MCP instructions (invalidate cache and rebuild).

    Args:
        mcp: FastMCP server instance

    Returns:
        bool: True if refresh was successful
    """
    try:
        if _builder:
            _builder.invalidate_cache()
            dynamic_instructions = await _builder.build_dynamic_instructions(
                force_refresh=True
            )
            mcp.instructions = dynamic_instructions
            logger.info("🔄 MCP instructions refreshed")
            return True
        else:
            logger.warning("🔄 No instructions builder available for refresh")
            return False

    except Exception as e:
        logger.error(f"❌ Failed to refresh MCP instructions: {e}")
        return False
