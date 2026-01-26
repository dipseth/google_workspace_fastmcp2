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

═══════════════════════════════════════════════════════════════════════════════
                     📋 THE LIVING DOCUMENTATION 📋
═══════════════════════════════════════════════════════════════════════════════

    Static docs grow stale, forgotten files
    collecting dust across the miles.
    But instructions that can learn and grow
    reflect the truth of what they know.

    Query the vectors, count the calls,
    find patterns hidden in the halls.
    "Gmail was used a hundred times"—
    let that wisdom shape the rhymes.

    Not just a list of what we offer,
    but proof of what the users proffer.
    Active services earn their glow,
    error rates let caution show.

    Cache for five, then ask again:
    what tools are popular? which domain?
    The README writes itself each day
    from the footprints left along the way.

                                        — Field Notes, Jan 2026

═══════════════════════════════════════════════════════════════════════════════
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from auth.scope_registry import ScopeRegistry
from config.enhanced_logging import setup_logger
from config.settings import settings
from middleware.qdrant_core.client import get_or_create_client_manager

logger = setup_logger()


def _build_services_section(enabled_services: Optional[set] = None) -> str:
    """
    Build the Available Services section using ScopeRegistry metadata.

    Args:
        enabled_services: Optional set of enabled service names. If provided,
                         only shows those services. If None, shows all services.

    Returns:
        Formatted markdown string with service information
    """
    # Determine header based on whether we're filtering
    if enabled_services is not None:
        lines = ["## 🔓 Enabled Services"]
    else:
        lines = ["## Available Services"]

    # Get all services from the registry
    all_services = ScopeRegistry.get_all_services()

    for service_name in all_services:
        # Skip if we have an enabled filter and this service isn't in it
        if enabled_services is not None and service_name.lower() not in {
            s.lower() for s in enabled_services
        }:
            continue

        metadata = ScopeRegistry.get_service_metadata(service_name)
        if metadata:
            # Format: - **📁 Google Drive**: Cloud storage and file synchronization service
            lines.append(
                f"- **{metadata.icon} {metadata.name}**: {metadata.description}"
            )

    # If filtering resulted in empty list, show a message
    if enabled_services is not None and len(lines) == 1:
        lines.append(
            "- *No services currently enabled. Use `manage_tools` to enable services.*"
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


# Build base instructions using registry data (static, all services)
BASE_INSTRUCTIONS = _build_base_instructions()


def _build_session_aware_base_instructions(
    enabled_services: Optional[set] = None,
) -> str:
    """
    Build base instructions with session-aware service filtering.

    Args:
        enabled_services: Set of enabled service names for this session.
                         If None, shows all services.

    Returns:
        Complete base instructions string with filtered services
    """
    services_section = _build_services_section(enabled_services)

    return f"""Google Workspace MCP Server - Comprehensive access to Google services.

## Authentication
1. Call `start_google_auth` with your email to begin OAuth flow
2. Complete authentication in browser
3. Call `check_drive_auth` to verify credentials

{services_section}

## Tool Management
Use `manage_tools` to list, enable, or disable tools at runtime."""


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
            logger.debug("📊 Qdrant middleware not set")
            return False
        try:
            has_client_manager = hasattr(self.qdrant_middleware, "client_manager")
            if not has_client_manager:
                logger.debug("📊 Qdrant middleware has no client_manager")
                return False

            is_available = self.qdrant_middleware.client_manager.is_available
            if not is_available:
                logger.debug("📊 Qdrant client_manager.is_available = False")
            return is_available
        except Exception as e:
            logger.debug(f"📊 Qdrant availability check failed: {e}")
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

    async def get_collection_summary(self) -> List[Dict[str, Any]]:
        """
        Fetch summary info for all relevant Qdrant collections.

        Uses the singleton client_manager from qdrant_core which handles
        initialization automatically based on settings.

        Returns:
            List of dicts with collection name, point count, status, and purpose
        """
        collections_info = []

        # Define collections to report on with their purposes
        collections_to_check = [
            (settings.tool_collection, "Tool responses & analytics"),
            (settings.card_collection, "Card templates & feedback patterns"),
        ]

        try:
            # Get the singleton client manager (initializes from settings if needed)
            client_manager = get_or_create_client_manager()

            # Ensure client is initialized
            if not client_manager.is_initialized:
                await client_manager.initialize()

            if not client_manager.client:
                logger.debug("📊 Qdrant client not available after initialization")
                return []

            for collection_name, purpose in collections_to_check:
                try:
                    # Get collection info from Qdrant
                    collection_info = await asyncio.to_thread(
                        client_manager.client.get_collection, collection_name
                    )

                    collections_info.append(
                        {
                            "name": collection_name,
                            "points_count": getattr(collection_info, "points_count", 0)
                            or 0,
                            "vectors_count": getattr(
                                collection_info, "vectors_count", 0
                            )
                            or 0,
                            "status": str(
                                getattr(collection_info, "status", "unknown")
                            ),
                            "purpose": purpose,
                        }
                    )
                except Exception as e:
                    # Collection might not exist yet
                    logger.debug(f"📊 Collection {collection_name} not available: {e}")
                    collections_info.append(
                        {
                            "name": collection_name,
                            "points_count": 0,
                            "vectors_count": 0,
                            "status": "not_found",
                            "purpose": purpose,
                        }
                    )

            return collections_info

        except Exception as e:
            logger.warning(f"📊 Failed to get collection summary: {e}")
            return []

    def _format_collection_summary(self, collections: List[Dict[str, Any]]) -> str:
        """
        Format Qdrant collection summary for instructions.

        Args:
            collections: List of collection info dicts

        Returns:
            Formatted markdown string with collection summary
        """
        if not collections:
            return ""

        lines = ["## 🗄️ Qdrant Collections"]

        for col in collections:
            name = col["name"]
            points = col["points_count"]
            status = col["status"]
            purpose = col["purpose"]

            # Status indicator
            if status == "Green" or status == "green":
                status_icon = "🟢"
            elif status == "Yellow" or status == "yellow":
                status_icon = "🟡"
            elif status == "not_found":
                status_icon = "⚪"
            else:
                status_icon = "🔴"

            # Format point count with commas
            points_str = f"{points:,}" if points > 0 else "empty"

            lines.append(f"- {status_icon} **{name}**: {points_str} points — {purpose}")

        return "\n".join(lines)

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

    async def build_dynamic_instructions(
        self,
        force_refresh: bool = False,
        enabled_services: Optional[set] = None,
    ) -> str:
        """
        Build complete dynamic instructions incorporating Qdrant data.

        Args:
            force_refresh: If True, bypass cache and rebuild instructions
            enabled_services: Optional set of enabled service names for session-aware
                            instructions. If provided, the "Available Services" section
                            will only show these services.

        Returns:
            Complete instructions string with dynamic content
        """
        # Check cache validity (only use cache if no session-specific filtering)
        if not force_refresh and enabled_services is None and self._cached_instructions:
            if self._cache_timestamp:
                age = (
                    datetime.now(timezone.utc) - self._cache_timestamp
                ).total_seconds()
                if age < self._cache_ttl_seconds:
                    logger.debug(f"📋 Using cached instructions (age: {age:.1f}s)")
                    return self._cached_instructions

        logger.info("📋 Building dynamic instructions from Qdrant data...")

        # Start with base instructions (session-aware if enabled_services provided)
        if enabled_services is not None:
            base = _build_session_aware_base_instructions(enabled_services)
            logger.info(
                f"📋 Building session-aware instructions with {len(enabled_services)} enabled services"
            )
        else:
            base = BASE_INSTRUCTIONS
        sections = [base]

        # Try to get collection summary using singleton client (handles its own init)
        try:
            collections = await self.get_collection_summary()
            if collections:
                collection_summary = self._format_collection_summary(collections)
                if collection_summary:
                    sections.append(collection_summary)
                    logger.info(
                        f"📋 Added collection summary for {len(collections)} collections"
                    )
            else:
                # No collections found - show offline status
                sections.append(self._format_qdrant_status())
        except Exception as e:
            logger.warning(f"📋 Failed to get collection summary: {e}")
            sections.append(self._format_qdrant_status())

        # Try to add additional dynamic content (analytics) if middleware available
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
                logger.warning(f"📋 Error building analytics sections: {e}")

        # Add timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        sections.append(f"\n---\n*Instructions updated: {timestamp}*")

        # Join all sections
        instructions = "\n".join(sections)

        # Only cache non-session-specific instructions
        if enabled_services is None:
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


async def refresh_instructions_for_session(
    mcp: Any,
    session_id: str,
    all_tools: List[str],
) -> bool:
    """
    Refresh MCP instructions with session-aware service filtering.

    Call this after tools are enabled/disabled to update the Available Services
    section to reflect only the services that have enabled tools.

    Args:
        mcp: FastMCP server instance
        session_id: Current session ID
        all_tools: List of all available tool names

    Returns:
        bool: True if refresh was successful
    """
    try:
        from auth.context import get_session_enabled_services

        # Get enabled services for this session
        enabled_services = await get_session_enabled_services(session_id, all_tools)

        if _builder:
            dynamic_instructions = await _builder.build_dynamic_instructions(
                force_refresh=True,
                enabled_services=enabled_services,
            )
            mcp.instructions = dynamic_instructions
            logger.info(
                f"🔄 MCP instructions refreshed for session with {len(enabled_services)} enabled services"
            )
            return True
        else:
            logger.warning("🔄 No instructions builder available for session refresh")
            return False

    except Exception as e:
        logger.error(f"❌ Failed to refresh session instructions: {e}")
        return False
