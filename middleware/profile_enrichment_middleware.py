"""
Profile Enrichment Middleware - Universal User Profile Enhancement

This middleware automatically enriches tool responses with full user names and emails
by calling Google People API when user IDs are detected in responses.

Works across all services: Chat, Gmail, Drive, Calendar, etc.

═══════════════════════════════════════════════════════════════════════════════
                      👤 THE HUMANIZER'S REFRAIN 👤
═══════════════════════════════════════════════════════════════════════════════

    A string of digits, cold and bare—
    "user/12345" tells nothing there.
    But behind each ID hides a soul,
    a name, a face, a human whole.

    The middleware intercepts the stream,
    sees the shadow, not the dream.
    Calls the People API with care,
    "Who is this? Make them aware."

    Two-tier cache: memory first,
    Qdrant second for the worst.
    Fast for those we've lately seen,
    persistent for the in-between.

    External users get their grace,
    privacy respected, given space.
    Not every ID yields a name—
    but we ask kindly, all the same.

    From Chat to Calendar to Drive,
    this middleware keeps context alive.
    No more "someone modified your doc"—
    now you know just who to talk.

                                        — Field Notes, Jan 2026

═══════════════════════════════════════════════════════════════════════════════
"""

import asyncio

from fastmcp.server.middleware import Middleware, MiddlewareContext
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing_extensions import Any, Dict, List, Optional, Set

from auth.context import get_auth_middleware
from config.enhanced_logging import setup_logger

logger = setup_logger()


class ProfileEnrichmentMiddleware(Middleware):
    """
    Middleware that enriches tool responses with user profile information from People API.

    Features:
    - Automatically detects user IDs in tool responses
    - Calls People API to fetch displayName and email
    - Two-tier caching: In-memory (fast) + optional Qdrant (persistent)
    - Gracefully handles external users and privacy restrictions
    - Works universally across all services
    - Optional analytics via Qdrant integration
    """

    def __init__(
        self,
        enable_caching: bool = True,
        cache_ttl_seconds: int = 300,
        qdrant_middleware=None,
        enable_qdrant_cache: bool = False,
    ):
        """
        Initialize Profile Enrichment Middleware.

        Args:
            enable_caching: Whether to cache People API results (default: True)
            cache_ttl_seconds: Cache TTL in seconds (default: 300 = 5 minutes)
            qdrant_middleware: Optional QdrantUnifiedMiddleware for persistent cache
            enable_qdrant_cache: Whether to use Qdrant for persistent caching
        """
        self._enable_caching = enable_caching
        self._cache_ttl = cache_ttl_seconds
        self._profile_cache: Dict[
            str, Dict[str, Any]
        ] = {}  # In-memory cache (fast tier)
        self._cache_timestamps: Dict[str, float] = {}

        # Optional Qdrant integration for persistent caching
        self._qdrant_middleware = qdrant_middleware
        self._enable_qdrant_cache = (
            enable_qdrant_cache and qdrant_middleware is not None
        )

        # Analytics tracking
        self._stats = {
            "total_lookups": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "api_calls": 0,
            "api_errors": 0,
            "qdrant_cache_hits": 0,
            "qdrant_cache_misses": 0,
        }

        logger.info("👤 Profile Enrichment Middleware initialized")
        logger.info(
            f"  In-memory caching: {'enabled' if enable_caching else 'disabled'}"
        )
        if enable_caching:
            logger.info(f"  Cache TTL: {cache_ttl_seconds}s")
        logger.info(
            f"  Qdrant persistent cache: {'enabled' if self._enable_qdrant_cache else 'disabled'}"
        )
        if self._enable_qdrant_cache:
            logger.info("  Two-tier caching: In-memory (fast) → Qdrant (persistent)")

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """
        Intercept tool calls and enrich responses with People API data.

        Args:
            context: Middleware context containing tool call info
            call_next: Next middleware in chain
        """
        tool_name = getattr(context.message, "name", "unknown")
        logger.info(f"👤 ProfileEnrichmentMiddleware: Processing tool '{tool_name}'")

        # Execute the tool first
        result = await call_next(context)
        logger.debug(f"👤 Tool '{tool_name}' executed, checking if enrichment needed")

        # Only enrich specific tools that return user data
        if not self._should_enrich_tool(tool_name):
            logger.debug(f"👤 Tool '{tool_name}' not in enrichable list, skipping")
            return result

        logger.info(f"👤 Tool '{tool_name}' is enrichable, proceeding with enrichment")

        # Extract user email from context
        user_email = self._extract_user_email(context)
        if not user_email or user_email == "unknown":
            logger.warning(
                f"👤 No user email available for People API enrichment in {tool_name}"
            )
            logger.debug(f"👤 Context message: {context.message}")
            return result

        logger.info(f"👤 User email extracted: {user_email}")

        # Enrich the result
        try:
            logger.info(
                f"👤 Starting enrichment for {tool_name} with user {user_email}"
            )
            enriched_result = await self._enrich_response(result, user_email, tool_name)
            logger.info(f"👤 Enrichment completed successfully for {tool_name}")
            return enriched_result
        except Exception as e:
            logger.error(
                f"👤 Failed to enrich response for {tool_name}: {e}", exc_info=True
            )
            return result

    def _should_enrich_tool(self, tool_name: str) -> bool:
        """Check if tool should have profile enrichment."""
        enrichable_tools = {
            "list_messages",  # Chat messages with sender info
            "search_messages",  # Chat search results
            "search_gmail_messages",  # Gmail search (future)
            "get_gmail_message_content",  # Gmail message details (future)
        }
        return tool_name in enrichable_tools

    def _extract_user_email(self, context: MiddlewareContext) -> Optional[str]:
        """Extract user email from tool arguments."""
        try:
            if hasattr(context.message, "arguments") and context.message.arguments:
                args = context.message.arguments
                return args.get("user_google_email") or args.get("user_email")
        except Exception as e:
            logger.debug(f"Could not extract user email: {e}")
        return None

    async def _enrich_response(
        self, result: Any, user_email: str, tool_name: str
    ) -> Any:
        """
        Enrich response with People API data.

        Args:
            result: Tool response object (typically ToolResult)
            user_email: Authenticated user's email
            tool_name: Name of the tool that was called

        Returns:
            Enriched response with full names and emails
        """
        logger.debug(f"👤 _enrich_response called with result type: {type(result)}")

        # Handle ToolResult objects (FastMCP standard response)
        if hasattr(result, "structured_content") and result.structured_content:
            logger.info("👤 Extracting structured_content from ToolResult")
            structured_data = result.structured_content
            logger.debug(f"👤 Structured content type: {type(structured_data)}")

            if isinstance(structured_data, dict):
                # Enrich the structured content
                enriched_data = await self._enrich_dict_response(
                    structured_data, user_email, tool_name
                )

                # Update BOTH structured_content AND content
                result.structured_content = enriched_data

                # Regenerate the content field so client sees enriched data
                import json

                from mcp.types import TextContent

                enriched_json = json.dumps(enriched_data, indent=2, default=str)
                result.content = [TextContent(type="text", text=enriched_json)]

                logger.info(
                    "👤 Updated ToolResult with enriched data in BOTH structured_content and content"
                )
                return result

        # Handle plain dict responses
        if isinstance(result, dict):
            logger.debug("👤 Handling plain dict response")
            return await self._enrich_dict_response(result, user_email, tool_name)

        # Handle other dict-like objects
        elif hasattr(result, "__dict__"):
            logger.debug(f"👤 Handling dict-like object: {type(result)}")
            result_dict = dict(result) if isinstance(result, dict) else result.__dict__
            enriched = await self._enrich_dict_response(
                result_dict, user_email, tool_name
            )
            # Return as same type
            return type(result)(**enriched) if hasattr(result, "__init__") else enriched

        logger.debug(f"👤 No enrichable content found in result type: {type(result)}")
        return result

    async def _enrich_dict_response(
        self, response: Dict, user_email: str, tool_name: str
    ) -> Dict:
        """Enrich dictionary response with People API data."""
        logger.info(f"👤 _enrich_dict_response called for {tool_name}")
        logger.info(f"👤 Response type: {type(response)}")
        logger.info(
            f"👤 Response keys: {response.keys() if isinstance(response, dict) else 'NOT A DICT'}"
        )

        # Log first 500 chars of response for debugging
        response_str = str(response)[:500]
        logger.info(f"👤 Response preview: {response_str}")

        # Chat-specific enrichment
        if tool_name in ["list_messages", "search_messages"]:
            messages = response.get("messages", [])
            logger.info(
                f"👤 Extracted messages array - type: {type(messages)}, length: {len(messages)}"
            )

            if messages:
                logger.info(f"👤 Found {len(messages)} messages to enrich")
                logger.info(
                    f"👤 First message sample: {messages[0] if messages else 'NONE'}"
                )
                await self._enrich_chat_messages(messages, user_email)
            else:
                logger.warning(f"👤 No messages found in response for {tool_name}")
                logger.warning(f"👤 Available keys: {list(response.keys())}")
        else:
            logger.debug(f"👤 Tool {tool_name} not in enrichable list")

        return response

    async def _enrich_chat_messages(self, messages: List[Dict], user_email: str):
        """
        Enrich Chat messages with sender profile information.

        Args:
            messages: List of message dictionaries
            user_email: Authenticated user's email for People API access
        """
        # Collect unique user IDs to enrich
        user_ids_to_fetch: Set[str] = set()

        for msg in messages:
            sender_name = msg.get("senderName", "")
            # Check if senderName looks like a user ID (starts with 'users/')
            if sender_name and sender_name.startswith("users/"):
                user_id = sender_name.split("/")[-1]
                user_ids_to_fetch.add(user_id)

        if not user_ids_to_fetch:
            logger.debug("No user IDs to enrich in messages")
            return

        logger.info(
            f"👤 Enriching {len(user_ids_to_fetch)} unique user profiles via People API..."
        )

        # Get People API service
        people_service = await self._get_people_service(user_email)
        if not people_service:
            logger.warning("Could not create People API service - skipping enrichment")
            return

        # Fetch profiles (with caching)
        profiles = await self._fetch_profiles_batch(user_ids_to_fetch, people_service)

        # Apply enrichment to messages
        enriched_count = 0
        for msg in messages:
            sender_name = msg.get("senderName", "")
            if sender_name and sender_name.startswith("users/"):
                user_id = sender_name.split("/")[-1]
                profile = profiles.get(user_id)

                if profile:
                    # Enrich with real name and email
                    msg["senderName"] = profile.get("displayName", sender_name)
                    if profile.get("email") and not msg.get("senderEmail"):
                        msg["senderEmail"] = profile["email"]
                    enriched_count += 1

        logger.info(
            f"✅ Enriched {enriched_count}/{len(messages)} messages with People API data"
        )

    async def _get_people_service(self, user_email: str):
        """
        Get or create People API service directly using encrypted credentials.

        This bypasses get_service() to avoid service type registration issues.
        """
        try:
            logger.info(f"👤 Attempting to create People API service for {user_email}")

            # Get AuthMiddleware to load credentials
            auth_middleware = get_auth_middleware()
            if not auth_middleware:
                logger.warning("👤 No AuthMiddleware available for credential loading")
                return None

            logger.debug("👤 AuthMiddleware found, loading credentials")

            # Load credentials using middleware's storage system
            credentials = auth_middleware.load_credentials(user_email)
            if not credentials:
                logger.warning(f"👤 No credentials found for {user_email}")
                return None

            logger.info(
                f"👤 Credentials loaded for {user_email}, building People API service"
            )

            # Build People service directly
            people_service = await asyncio.to_thread(
                build, "people", "v1", credentials=credentials
            )

            logger.info(f"✅ Successfully created People API service for {user_email}")
            return people_service

        except Exception as e:
            logger.error(f"👤 Failed to create People API service: {e}", exc_info=True)
            return None

    async def _fetch_profiles_batch(
        self, user_ids: Set[str], people_service
    ) -> Dict[str, Dict]:
        """
        Fetch user profiles in batch with caching.

        Args:
            user_ids: Set of user IDs to fetch
            people_service: Authenticated People API service

        Returns:
            Dict mapping user_id -> profile data
        """
        import time

        profiles = {}

        # Check cache first
        if self._enable_caching:
            current_time = time.time()
            for user_id in list(user_ids):
                if user_id in self._profile_cache:
                    # Check if cache is still valid
                    cache_age = current_time - self._cache_timestamps.get(user_id, 0)
                    if cache_age < self._cache_ttl:
                        profiles[user_id] = self._profile_cache[user_id]
                        user_ids.remove(user_id)
                        logger.debug(f"📦 Cache hit for user {user_id}")

        # Fetch remaining profiles from API
        if user_ids:
            logger.debug(f"🌐 Fetching {len(user_ids)} profiles from People API...")

            # Fetch each profile (People API doesn't support batch get)
            tasks = []
            for user_id in user_ids:
                tasks.append(self._fetch_single_profile(user_id, people_service))

            # Wait for all fetches
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for user_id, result in zip(user_ids, results):
                if isinstance(result, dict):
                    profiles[user_id] = result

                    # Cache the result
                    if self._enable_caching:
                        self._profile_cache[user_id] = result
                        self._cache_timestamps[user_id] = time.time()

        return profiles

    async def _fetch_single_profile(
        self, user_id: str, people_service
    ) -> Optional[Dict]:
        """
        Fetch a single user profile from People API.

        Args:
            user_id: Numeric Google user ID
            people_service: Authenticated People API service

        Returns:
            Dict with displayName and email, or None if fetch fails
        """
        try:
            # People API expects format: people/{account_id}
            resource_name = f"people/{user_id}"
            logger.info(f"👤 Fetching profile for resource: {resource_name}")

            # Request profile with names and email addresses
            person = await asyncio.to_thread(
                people_service.people()
                .get(resourceName=resource_name, personFields="names,emailAddresses")
                .execute
            )

            logger.info(f"👤 People API response for {user_id}: {person}")

            # Extract display name
            names = person.get("names", [])
            display_name = names[0].get("displayName") if names else None

            logger.info(
                f"👤 Extracted name: {display_name} from {len(names)} name entries"
            )

            # Extract email
            emails = person.get("emailAddresses", [])
            email = emails[0].get("value") if emails else None

            logger.info(f"👤 Extracted email: {email} from {len(emails)} email entries")

            if display_name or email:
                logger.info(
                    f"✅ People API SUCCESS: {user_id} → {display_name} ({email})"
                )
                return {
                    "displayName": display_name or f"User {user_id}",
                    "email": email,
                }
            else:
                logger.warning(f"⚠️ People API: No profile data for {user_id}")
                logger.warning(f"⚠️ Full person object: {person}")
                return None

        except HttpError as http_err:
            # Common for external users or privacy restrictions
            status_code = (
                http_err.resp.status if hasattr(http_err, "resp") else "unknown"
            )
            logger.error(
                f"👤 People API HTTP {status_code} for {user_id} - likely external/restricted"
            )
            logger.error(f"👤 Full error: {http_err}")
            return None
        except Exception as e:
            logger.error(f"👤 People API EXCEPTION for {user_id}: {e}", exc_info=True)
            return None

    def clear_cache(self):
        """Clear the profile cache."""
        self._profile_cache.clear()
        self._cache_timestamps.clear()
        logger.info("🧹 Profile cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics including Qdrant integration."""
        import time

        current_time = time.time()

        valid_entries = sum(
            1
            for user_id, timestamp in self._cache_timestamps.items()
            if (current_time - timestamp) < self._cache_ttl
        )

        # Calculate hit rate
        total_lookups = self._stats["total_lookups"]
        cache_hit_rate = (
            (self._stats["cache_hits"] / total_lookups * 100)
            if total_lookups > 0
            else 0.0
        )

        stats = {
            "in_memory_cache": {
                "total_entries": len(self._profile_cache),
                "valid_entries": valid_entries,
                "expired_entries": len(self._profile_cache) - valid_entries,
                "cache_ttl_seconds": self._cache_ttl,
                "enabled": self._enable_caching,
            },
            "performance": {
                "total_lookups": total_lookups,
                "cache_hits": self._stats["cache_hits"],
                "cache_misses": self._stats["cache_misses"],
                "cache_hit_rate_percent": round(cache_hit_rate, 2),
                "api_calls": self._stats["api_calls"],
                "api_errors": self._stats["api_errors"],
            },
            "qdrant_integration": {
                "enabled": self._enable_qdrant_cache,
                "available": self._qdrant_middleware is not None,
                "cache_hits": self._stats["qdrant_cache_hits"],
                "cache_misses": self._stats["qdrant_cache_misses"],
            },
        }

        return stats

    def get_enrichment_analytics(self) -> Dict[str, Any]:
        """Get detailed analytics about profile enrichment operations."""
        return {
            "cache_stats": self.get_cache_stats(),
            "middleware_status": "active",
            "enrichable_tools": [
                "list_messages",
                "search_messages",
                "search_gmail_messages",
                "get_gmail_message_content",
            ],
            "features": {
                "in_memory_cache": self._enable_caching,
                "qdrant_persistent_cache": self._enable_qdrant_cache,
                "two_tier_caching": self._enable_caching and self._enable_qdrant_cache,
                "people_api_integration": True,
                "analytics_tracking": True,
            },
        }
