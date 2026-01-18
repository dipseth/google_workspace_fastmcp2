"""
Enhanced Unified Card Tool with ModuleWrapper and Qdrant Integration

This module provides a unified MCP tool for Google Chat cards that leverages
the ModuleWrapper adapter to handle inputs for any type of card dynamically.
It implements the hybrid approach for complex cards, improves widget formatting,
and integrates with Qdrant for storing and retrieving card templates.

This enhanced version replaces the separate card tools in chat_tools.py,
chat_cards_optimized.py, and enhanced_card_adapter.py with a single,
more powerful approach that can handle any card type.

## Key Technical Insights from Testing:

### Google Chat Cards v2 API Requirements:
1. **Structure**: Cards must have nested structure: {header: {...}, sections: [{widgets: [...]}]}
2. **Images**: Cannot be placed in header.imageUrl - must be widgets in sections
3. **Flat Parameters**: Direct flat params like {"title": "Hello"} cause 400 errors
4. **Error Fields**: Any "error" field in card structure causes API rejection

### Card Creation Approaches:
- **Simple Cards**: Use direct parameter transformation for basic title/text cards
- **Complex Cards**: Use component-based creation via ModuleWrapper search
- **Fallback**: Always provide valid card structure even on transformation errors

### Testing Patterns:
- Simple cards (title/text): Always use "variable" type transformation
- Complex descriptions: Trigger component search, return "class" type
- Image handling: Requires widget placement, not header placement
- Error handling: Must return valid card structure, never error objects
"""

import asyncio
import inspect
import json
import os
import time

# Import MCP-related components
from fastmcp import FastMCP
from typing_extensions import Any, Dict, List, Optional, Tuple, Union

# Template middleware integration handled at server level - no imports needed here
# Import ModuleWrapper
from adapters.module_wrapper import ModuleWrapper
from auth.context import get_injected_service

# Import auth helpers
from auth.service_helpers import get_service, request_service

# Import TypedDict response types for structured responses
from config.enhanced_logging import setup_logger

# Import enhanced NLP parser
from .nlp_card_parser import parse_enhanced_natural_language_description

# Import structured response types
from .unified_card_types import (
    ComponentSearchInfo,
    NLPExtractionInfo,
    SendDynamicCardResponse,
)

logger = setup_logger()
logger.info("Card Framework v2 is available for rich card creation")


def _extract_thread_id(thread_key: Optional[str]) -> Optional[str]:
    """Extract thread ID from thread key (handles full resource name or raw ID)."""
    if not thread_key:
        return None
    # Format: "spaces/{space}/threads/{threadId}" -> use just the threadId
    return thread_key.split("threads/")[-1] if "threads/" in thread_key else thread_key


def _process_thread_key_for_request(
    request_params: Dict[str, Any], thread_key: Optional[str] = None
) -> None:
    """Process thread key for Google Chat API request (modifies request_params in-place)."""
    thread_id = _extract_thread_id(thread_key)
    if thread_id:
        request_params["threadKey"] = thread_id
        request_params["messageReplyOption"] = "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"
        logger.debug(f"Thread key processed: {thread_key} -> {thread_id}")


def _process_thread_key_for_webhook_url(
    webhook_url: str, thread_key: Optional[str] = None
) -> str:
    """Process thread key for webhook URL (returns modified URL with thread params)."""
    thread_id = _extract_thread_id(thread_key)
    if not thread_id:
        return webhook_url

    separator = "&" if "?" in webhook_url else "?"
    return f"{webhook_url}{separator}threadKey={thread_id}&messageReplyOption=REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"


# Try to import Card Framework with graceful fallback
try:
    from card_framework.v2 import Card, CardHeader, Message, Section, Widget
    from card_framework.v2.card import CardWithId
    from card_framework.v2.widgets import (
        Button,
        ButtonList,
        Column,
        Columns,
        DecoratedText,
        Divider,
        Icon,
        Image,
        OnClick,
        OpenLink,
        SelectionInput,
        TextInput,
        TextParagraph,
    )

    CARD_FRAMEWORK_AVAILABLE = True

except ImportError:
    CARD_FRAMEWORK_AVAILABLE = False
    logger.warning("Card Framework v2 not available. Falling back to REST API format.")

    # Define placeholder classes for type hints when Card Framework is not available
    class Card:
        pass

    class Section:
        pass

    class Widget:
        pass


# Global variables for module wrappers and caches
_card_framework_wrapper = None
_card_framework_wrapper_colbert = None  # ColBERT-enabled wrapper for raw query mode
_card_types_cache = {}
_qdrant_client = None
_card_templates_collection = "card_templates"

# Field conversion cache for performance optimization
_camel_to_snake_cache = {}


async def _get_chat_service_with_fallback(user_google_email: str):
    """
    Get Google Chat service with fallback to direct creation if middleware injection fails.

    Args:
        user_google_email: User's Google email address

    Returns:
        Authenticated Google Chat service instance or None if unavailable
    """
    # First, try middleware injection
    service_key = request_service("chat")

    try:
        # Try to get the injected service from middleware
        chat_service = get_injected_service(service_key)
        logger.info(
            f"Successfully retrieved injected Chat service for {user_google_email}"
        )
        return chat_service

    except RuntimeError as e:
        if (
            "not yet fulfilled" in str(e).lower()
            or "service injection" in str(e).lower()
        ):
            # Middleware injection failed, fall back to direct service creation
            logger.warning(
                f"Middleware injection unavailable, falling back to direct service creation for {user_google_email}"
            )

            try:
                # Use the same helper function pattern as Gmail
                chat_service = await get_service("chat", user_google_email)
                logger.info(
                    f"Successfully created Chat service directly for {user_google_email}"
                )
                return chat_service

            except Exception as direct_error:
                logger.error(
                    f"Direct Chat service creation failed for {user_google_email}: {direct_error}"
                )
                return None
        else:
            # Different type of RuntimeError, log and return None
            logger.error(f"Chat service injection error for {user_google_email}: {e}")
            return None

    except Exception as e:
        logger.error(
            f"Unexpected error getting Chat service for {user_google_email}: {e}"
        )
        return None


def _get_qdrant_client():
    """Get or initialize the Qdrant client."""
    global _qdrant_client

    if _qdrant_client is None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            # Import settings to get proper Qdrant configuration
            from config.settings import settings

            logger.info("🔗 Initializing Qdrant client...")
            logger.info(
                f"📊 SETTINGS DEBUG - Using Qdrant config: URL={settings.qdrant_url}, Host={settings.qdrant_host}, Port={settings.qdrant_port}, API Key={'***' if settings.qdrant_api_key else 'None'}"
            )

            # Use settings-based configuration instead of hardcoded localhost
            if settings.qdrant_url:
                # Use URL-based initialization for cloud instances
                if settings.qdrant_api_key:
                    _qdrant_client = QdrantClient(
                        url=settings.qdrant_url, api_key=settings.qdrant_api_key
                    )
                    logger.info(
                        f"🌐 Connected to Qdrant cloud: {settings.qdrant_url} (API Key: ***)"
                    )
                else:
                    _qdrant_client = QdrantClient(url=settings.qdrant_url)
                    logger.info(
                        f"🌐 Connected to Qdrant: {settings.qdrant_url} (No API Key)"
                    )
            else:
                # Fallback to host/port configuration
                if settings.qdrant_api_key:
                    _qdrant_client = QdrantClient(
                        host=settings.qdrant_host or "localhost",
                        port=settings.qdrant_port or 6333,
                        api_key=settings.qdrant_api_key,
                    )
                else:
                    _qdrant_client = QdrantClient(
                        host=settings.qdrant_host or "localhost",
                        port=settings.qdrant_port or 6333,
                    )
                logger.info(
                    f"🌐 Connected to Qdrant: {settings.qdrant_host}:{settings.qdrant_port} (API Key: {'***' if settings.qdrant_api_key else 'None'})"
                )

            # Ensure card templates collection exists
            collections = _qdrant_client.get_collections()
            collection_names = [c.name for c in collections.collections]

            if _card_templates_collection not in collection_names:
                # Create collection for card templates
                _qdrant_client.create_collection(
                    collection_name=_card_templates_collection,
                    vectors_config=VectorParams(
                        size=384,  # Default size for all-MiniLM-L6-v2
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(
                    f"✅ Created Qdrant collection: {_card_templates_collection}"
                )
            else:
                logger.info(
                    f"✅ Using existing collection: {_card_templates_collection}"
                )

            logger.info("✅ Qdrant client initialized")

        except ImportError:
            logger.warning("⚠️ Qdrant client not available - template storage disabled")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to initialize Qdrant client: {e}", exc_info=True)
            return None

    return _qdrant_client


def _reset_card_framework_wrapper():
    """Reset the card framework wrapper to force reinitialization."""
    global _card_framework_wrapper, _card_types_cache
    _card_framework_wrapper = None
    _card_types_cache = {}
    logger.info("🔄 Card framework wrapper reset")


def _initialize_card_framework_wrapper(force_reset: bool = False):
    """Initialize the ModuleWrapper for the card_framework module with comprehensive debugging."""
    global _card_framework_wrapper

    if not CARD_FRAMEWORK_AVAILABLE:
        logger.warning("❌ Card Framework not available - cannot initialize wrapper")
        return None

    if force_reset:
        logger.info("🔄 Force reset requested - clearing existing wrapper")
        _reset_card_framework_wrapper()

    if _card_framework_wrapper is None:
        try:
            import card_framework

            logger.info(
                "🔍 COMPREHENSIVE DEBUG: Initializing ModuleWrapper for card_framework..."
            )
            logger.info(f"📦 Card Framework module location: {card_framework.__file__}")

            # Import settings to pass Qdrant configuration
            from config.settings import settings

            logger.info("🌐 QDRANT CONFIG DEBUG:")
            logger.info(f"  - URL: {settings.qdrant_url}")
            logger.info(f"  - Host: {settings.qdrant_host}")
            logger.info(f"  - Port: {settings.qdrant_port}")
            logger.info(f"  - API Key: {'***' if settings.qdrant_api_key else 'None'}")

            # Create wrapper with optimized settings - use FastEmbed-compatible collection
            logger.info("🔧 Creating ModuleWrapper with comprehensive settings...")
            _card_framework_wrapper = ModuleWrapper(
                module_or_name="card_framework.v2",
                qdrant_url=settings.qdrant_url,  # Pass cloud URL from settings
                qdrant_api_key=settings.qdrant_api_key,  # Pass API key from settings
                collection_name="card_framework_components_fastembed",
                index_nested=True,  # Index methods within classes
                index_private=False,  # Skip private components
                max_depth=2,  # Limit recursion depth for better performance
                skip_standard_library=True,  # Skip standard library modules
                include_modules=[
                    "card_framework",
                    "gchat",
                ],  # Only include relevant modules
                exclude_modules=[
                    "numpy",
                    "pandas",
                    "matplotlib",
                    "scipy",
                ],  # Exclude irrelevant modules
                force_reindex=False,  # Don't force reindex if collection has data
                clear_collection=False,  # Set to True to clear duplicates on restart
            )

            logger.info("✅ ModuleWrapper created successfully!")
            logger.info(
                f"🌐 Connected to Qdrant: {settings.qdrant_url or f'{settings.qdrant_host}:{settings.qdrant_port}'}"
            )

            # CRITICAL: Validate component indexing immediately after creation
            component_count = (
                len(_card_framework_wrapper.components)
                if _card_framework_wrapper.components
                else 0
            )
            logger.info("📊 COMPONENT CACHE VALIDATION:")
            logger.info(f"  - Total components indexed: {component_count}")

            if component_count == 0:
                logger.error("❌ CRITICAL: ModuleWrapper has ZERO components indexed!")
                logger.error("❌ This will cause all component searches to fail.")
                logger.error(
                    "❌ Possible causes: Qdrant connection issues, indexing failures, empty module"
                )

                # Try to get more diagnostic info
                try:
                    if hasattr(_card_framework_wrapper, "collection_name"):
                        logger.error(
                            f"❌ Collection name: {_card_framework_wrapper.collection_name}"
                        )
                    if hasattr(_card_framework_wrapper, "qdrant_client"):
                        logger.error(
                            f"❌ Qdrant client available: {_card_framework_wrapper.qdrant_client is not None}"
                        )
                except Exception as diag_error:
                    logger.error(f"❌ Diagnostic error: {diag_error}")
            else:
                logger.info(
                    f"✅ Component indexing successful - {component_count} components available"
                )

                # Log sample of indexed components for verification
                sample_components = list(_card_framework_wrapper.components.keys())[:10]
                logger.info(f"📋 Sample indexed components: {sample_components}")

                # Count components by type for additional validation
                try:
                    class_count = sum(
                        1
                        for comp_data in _card_framework_wrapper.components.values()
                        if hasattr(comp_data, "obj") and inspect.isclass(comp_data.obj)
                    )
                    function_count = sum(
                        1
                        for comp_data in _card_framework_wrapper.components.values()
                        if hasattr(comp_data, "obj")
                        and inspect.isfunction(comp_data.obj)
                    )
                    logger.info(
                        f"📊 Component breakdown: {class_count} classes, {function_count} functions"
                    )
                except Exception as count_error:
                    logger.warning(f"⚠️ Error counting component types: {count_error}")

            # Initialize Qdrant client for template storage
            qdrant_client = _get_qdrant_client()
            if qdrant_client:
                logger.info("✅ Qdrant client initialized for template storage")
            else:
                logger.warning(
                    "⚠️ Qdrant client initialization failed - template features disabled"
                )

            logger.info("✅ ModuleWrapper initialization complete")

        except ImportError as import_error:
            logger.error(f"❌ Could not import card_framework module: {import_error}")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to initialize ModuleWrapper: {e}", exc_info=True)
            return None
    else:
        logger.info(
            f"♻️ Using existing ModuleWrapper with {len(_card_framework_wrapper.components) if _card_framework_wrapper.components else 0} components"
        )

    return _card_framework_wrapper


def _initialize_colbert_wrapper(force_reset: bool = False):
    """Initialize the ColBERT-enabled ModuleWrapper for raw query mode."""
    global _card_framework_wrapper_colbert

    if not CARD_FRAMEWORK_AVAILABLE:
        logger.warning(
            "❌ Card Framework not available - cannot initialize ColBERT wrapper"
        )
        return None

    if force_reset:
        logger.info("🔄 Force reset ColBERT wrapper")
        _card_framework_wrapper_colbert = None

    if _card_framework_wrapper_colbert is None:
        try:
            import card_framework

            from config.settings import settings

            logger.info("🤖 Initializing ColBERT-enabled ModuleWrapper...")

            _card_framework_wrapper_colbert = ModuleWrapper(
                module_or_name="card_framework.v2",
                qdrant_url=settings.qdrant_url,
                qdrant_api_key=settings.qdrant_api_key,
                collection_name="card_framework_components_fastembed",
                enable_colbert=True,  # Enable ColBERT multi-vector embeddings
                colbert_model="colbert-ir/colbertv2.0",
                colbert_collection_name="card_framework_components_colbert",
                index_nested=True,
                index_private=False,
                max_depth=2,
                skip_standard_library=True,
                include_modules=["card_framework", "gchat"],
                exclude_modules=["numpy", "pandas", "matplotlib", "scipy"],
                force_reindex=False,
                clear_collection=False,
            )

            logger.info("✅ ColBERT ModuleWrapper created successfully!")
            logger.info(
                f"📊 ColBERT components indexed: {len(_card_framework_wrapper_colbert.components)}"
            )

        except Exception as e:
            logger.error(f"❌ Failed to initialize ColBERT wrapper: {e}", exc_info=True)
            return None

    return _card_framework_wrapper_colbert


async def _find_card_component_colbert(
    query: str, limit: int = 5, score_threshold: float = 0.1
) -> List[Dict[str, Any]]:
    """
    Find card components using ColBERT multi-vector semantic search.

    This uses the raw query directly without NLP preprocessing,
    relying on ColBERT's superior semantic matching capabilities.

    Args:
        query: Raw natural language query
        limit: Maximum number of results
        score_threshold: Minimum similarity score threshold

    Returns:
        List of matching components
    """
    global _card_framework_wrapper_colbert

    # Initialize ColBERT wrapper if needed
    if not _card_framework_wrapper_colbert:
        _initialize_colbert_wrapper(force_reset=True)

    if not _card_framework_wrapper_colbert:
        logger.error("❌ ColBERT ModuleWrapper not available")
        return []

    try:
        logger.info(f"🔍 ColBERT raw query search: '{query}'")

        # Use ColBERT search directly with raw query
        results = _card_framework_wrapper_colbert.colbert_search(
            query=query,
            limit=limit,
            score_threshold=score_threshold,
        )

        if results:
            logger.info(f"✅ ColBERT search returned {len(results)} results")
            for i, r in enumerate(results[:3]):
                logger.info(
                    f"  {i+1}. {r.get('name')} (score: {r.get('score', 0):.4f})"
                )

        return results

    except Exception as e:
        logger.error(f"❌ ColBERT search failed: {e}", exc_info=True)
        return []


async def _find_card_component(
    query: str, limit: int = 5, score_threshold: float = 0.1
):
    """
    Find card components using ModuleWrapper semantic search.

    REFACTORED: Now properly leverages ModuleWrapper.search() instead of duplicating functionality.

    Args:
        query: Natural language query describing the card
        limit: Maximum number of results
        score_threshold: Minimum similarity score threshold

    Returns:
        List of matching components
    """
    # Initialize wrapper if needed
    if not _card_framework_wrapper:
        _initialize_card_framework_wrapper(force_reset=True)

    if not _card_framework_wrapper:
        logger.error("❌ ModuleWrapper not available")
        return []

    # ENHANCED VALIDATION: Check if we have components, if not, force reinitialize
    if len(_card_framework_wrapper.components) == 0:
        logger.error(
            "❌ CRITICAL: Existing wrapper has ZERO components! This will cause all searches to fail."
        )
        logger.info("🔄 Forcing reinitialization to attempt component recovery...")
        _initialize_card_framework_wrapper(force_reset=True)

        # Validate reinitialization worked
        if not _card_framework_wrapper or len(_card_framework_wrapper.components) == 0:
            logger.error("❌ REINITIALIZATION FAILED: Still no components available!")
            logger.error(
                "❌ ModuleWrapper is non-functional - all component searches will return empty results"
            )
            return []
        else:
            logger.info(
                f"✅ Reinitialization successful: {len(_card_framework_wrapper.components)} components available"
            )

    # On-demand caching: check if query matches a common card type
    #
    # IMPORTANT:
    # Historically we tried to speed things up by caching "card_type" searches like "text card".
    # In practice this caused bad behavior for `send_dynamic_card`:
    # - it returns *metadata-only* search results (no `component` field)
    # - callers then treat that as a successful search but fail to build widgets and fall back
    #   to empty "simple card" output.
    #
    # Fix: disable this cache shortcut by default so we always return the full search result
    # objects (including `component`) from the normal ModuleWrapper path below.
    enable_card_type_cache = os.getenv("ENABLE_CARD_TYPE_CACHE", "0") == "1"

    common_card_types = [
        "simple",
        "interactive",
        "form",
        "rich",
        "text",
        "button",
        "image",
        "decorated",
        "header",
        "section",
        "widget",
        "divider",
        "selection",
        "chip",
        "grid",
        "column",
    ]

    if enable_card_type_cache:
        # Check if query matches a card type we might want to cache
        query_lower = query.lower()
        for card_type in common_card_types:
            if card_type in query_lower:
                # Check if already cached
                if card_type in _card_types_cache:
                    logger.info(f"Using cached results for card type: {card_type}")
                    return _card_types_cache[card_type]

                # Not cached yet - search and cache now
                logger.info(f"On-demand caching for card type: {card_type}")
                results = _card_framework_wrapper.search(f"{card_type} card", limit=5)
                if results:
                    # Store only relevant information from the search results
                    formatted_results = []
                    for result in results:
                        formatted_results.append(
                            {
                                "name": result.get("name"),
                                "path": result.get("path"),
                                "type": result.get("type"),
                                "score": result.get("score"),
                                "docstring": result.get("docstring", "")[:200],
                            }
                        )
                    _card_types_cache[card_type] = formatted_results
                    logger.info(
                        f"✅ Cached {len(formatted_results)} results for card type: {card_type}"
                    )
                    return formatted_results

    try:
        # LEVERAGE MODULEWRAPPER: Use existing search functionality
        try:
            results = await _card_framework_wrapper.search_async(
                query, limit=limit, score_threshold=score_threshold
            )
            logger.info(
                f"✅ ModuleWrapper async search for '{query}' returned {len(results)} results"
            )
        except (AttributeError, NotImplementedError):
            # Fall back to sync search if async not available
            results = _card_framework_wrapper.search(
                query, limit=limit, score_threshold=score_threshold
            )
            logger.info(
                f"✅ ModuleWrapper sync search for '{query}' returned {len(results)} results"
            )

        # SIMPLIFIED: Resolve component paths with better error handling
        def _map_search_path_to_actual_path(search_path: str) -> str:
            """Map search index path to actual component path with enhanced error handling."""
            if not search_path:
                logger.warning("⚠️ Empty search path provided")
                return search_path

            logger.info(f"🔧 Mapping search path: {search_path}")

            # Strategy 1: Direct match (path exists as-is)
            if search_path in _card_framework_wrapper.components:
                logger.info(f"✅ Direct path match: {search_path}")
                return search_path

            # Strategy 2: Common Card Framework v2 patterns
            #
            # NOTE: Many widgets live under card_framework.v2.widgets (e.g. TextInput),
            # not directly under card_framework.v2. Prefer widgets.* before v2.*.
            component_name = search_path.split(".")[-1]
            common_patterns = [
                f"card_framework.v2.widgets.{component_name}",
                f"card_framework.v2.{component_name}",
                f"card_framework.widgets.{component_name}",
                f"card_framework.{component_name}",
            ]

            for pattern in common_patterns:
                if pattern in _card_framework_wrapper.components:
                    logger.info(f"✅ Pattern match: {search_path} -> {pattern}")
                    return pattern

            # Strategy 3: Fuzzy match on component name
            # Prefer v2.widgets.* matches first (prevents bad paths like card_framework.v2.TextInput)
            available_paths = list(_card_framework_wrapper.components.keys())

            preferred_suffixes = [
                f"card_framework.v2.widgets.{component_name}",
                f"card_framework.v2.{component_name}",
                f"card_framework.widgets.{component_name}",
                f"card_framework.{component_name}",
            ]
            for preferred in preferred_suffixes:
                if preferred in _card_framework_wrapper.components:
                    logger.info(
                        f"✅ Preferred exact match: {search_path} -> {preferred}"
                    )
                    return preferred

            for path in available_paths:
                if path.endswith(f".{component_name}"):
                    # Skip the known-bad import path where a widget is treated as a submodule
                    if path.startswith("card_framework.v2.") and (
                        ".widgets." not in path and component_name.endswith("Input")
                    ):
                        continue
                    logger.info(f"✅ Fuzzy match: {search_path} -> {path}")
                    return path

            # Strategy 4: Log available options for debugging
            logger.warning(f"⚠️ No path mapping found for: {search_path}")
            logger.info(f"🔍 Available component paths: {len(available_paths)} total")
            if len(available_paths) <= 20:  # Only log if reasonable number
                logger.info(f"🔍 Sample paths: {available_paths[:10]}")

            # Fallback - return original path
            return search_path

        # ENHANCED: Resolve component objects with comprehensive error handling and fallback extraction
        filtered_results = []
        for i, result in enumerate(results):
            # Prefer canonical module_path + name when available (more reliable than legacy full_path)
            module_path = result.get("module_path")
            name = result.get("name")
            canonical = f"{module_path}.{name}" if module_path and name else None

            search_path = canonical or result.get("path", "")
            component = result.get("component")

            logger.info(
                f"🔍 Processing search result {i+1}/{len(results)}: {search_path}"
            )

            # ENHANCED COMPONENT RESOLUTION: Handle all component types including modules
            if not component and search_path:
                # Map search path to actual component path
                actual_path = _map_search_path_to_actual_path(search_path)

                if actual_path != search_path:
                    logger.info(f"🔧 Mapped search path: {search_path} → {actual_path}")
                    result["path"] = actual_path  # Update result with correct path
                else:
                    # Ensure the result dict stays aligned with the canonical path we attempted.
                    result["path"] = actual_path

                # TRUST THE WRAPPER: Use ModuleWrapper's get_component_by_path method
                try:
                    component = _card_framework_wrapper.get_component_by_path(
                        actual_path
                    )
                    if component:
                        result["component"] = component
                        logger.info(
                            f"✅ ModuleWrapper resolved component: {actual_path} -> {type(component).__name__}"
                        )

                        # ENHANCED: If component is a module, extract usable classes/functions
                        if inspect.ismodule(component):
                            logger.info(
                                "🔍 Component is module, extracting usable members..."
                            )
                            module_members = inspect.getmembers(component)

                            for name, member in module_members:
                                if (
                                    not name.startswith("_")
                                    and (inspect.isclass(member) or callable(member))
                                    and any(
                                        keyword in name.lower()
                                        for keyword in [
                                            "card",
                                            "widget",
                                            "button",
                                            "text",
                                            "decorated",
                                        ]
                                    )
                                ):

                                    # Use the first suitable member found
                                    result["component"] = member
                                    result["extracted_from_module"] = component.__name__
                                    result["extracted_member"] = name
                                    logger.info(
                                        f"✅ Extracted {type(member).__name__} '{name}' from module {component.__name__}"
                                    )
                                    component = member
                                    break
                    else:
                        logger.warning(
                            f"⚠️ ModuleWrapper could not resolve component: {actual_path}"
                        )

                        # ENHANCED FALLBACK: Try direct access with module extraction
                        if actual_path in _card_framework_wrapper.components:
                            component_data = _card_framework_wrapper.components[
                                actual_path
                            ]
                            if hasattr(component_data, "obj") and component_data.obj:
                                obj = component_data.obj

                                # Check if it's already a class/callable we can use directly
                                if inspect.isclass(obj) or callable(obj):
                                    component = obj
                                    result["component"] = component
                                    logger.info(
                                        f"✅ Direct fallback resolution: {type(obj).__name__}"
                                    )

                                # If it's a module, extract components from it
                                elif inspect.ismodule(obj):
                                    logger.info(
                                        f"🔍 Fallback: Extracting from module {obj.__name__}"
                                    )
                                    module_members = inspect.getmembers(obj)

                                    for name, member in module_members:
                                        if not name.startswith("_") and (
                                            inspect.isclass(member) or callable(member)
                                        ):
                                            component = member
                                            result["component"] = component
                                            result["fallback_extracted"] = (
                                                f"{obj.__name__}.{name}"
                                            )
                                            logger.info(
                                                f"✅ Fallback extracted: {type(member).__name__} '{name}'"
                                            )
                                            break
                                else:
                                    logger.warning(
                                        f"⚠️ Component data object is not usable: {type(obj)}"
                                    )
                            else:
                                logger.warning(
                                    f"⚠️ Component data has no usable obj: {component_data}"
                                )
                        else:
                            logger.warning(
                                f"⚠️ Component path not in wrapper.components: {actual_path}"
                            )

                except Exception as resolution_error:
                    logger.error(
                        f"❌ Error resolving component via wrapper: {resolution_error}"
                    )
                    # Don't let resolution errors break the search
                    component = None

            # ENHANCED FILTERING: Better component validation
            if component:
                component_path = result.get("path", "")

                # Check for usable component types
                if inspect.isclass(component) or callable(component):
                    # Skip bound methods
                    if inspect.ismethod(component) or (
                        hasattr(component, "__self__")
                        and component.__self__ is not None
                    ):
                        logger.debug(f"❌ Skipping bound method: {component_path}")
                        continue

                    # Skip likely utility methods based on naming patterns
                    if any(
                        pattern in component_path.lower()
                        for pattern in [
                            ".add_",
                            ".set_",
                            ".get_",
                            ".remove_",
                            ".update_",
                            ".create_",
                        ]
                    ):
                        logger.debug(f"❌ Skipping utility method: {component_path}")
                        continue

                    # This is a valid component
                    filtered_results.append(result)
                    logger.info(
                        f"✅ Added valid component: {component_path} ({type(component).__name__})"
                    )

                elif inspect.ismodule(component):
                    # Module was not successfully processed - keep for fallback but note the issue
                    filtered_results.append(result)
                    logger.warning(
                        f"⚠️ Module component not processed, keeping for fallback: {component_path}"
                    )

                else:
                    # Unknown component type - keep for fallback
                    filtered_results.append(result)
                    logger.warning(
                        f"⚠️ Unknown component type, keeping for fallback: {component_path} ({type(component)})"
                    )
            else:
                # No component resolved - DO NOT add to results
                # Unresolved components can't be instantiated, so keeping them
                # causes valid components with lower scores to be skipped
                logger.warning(f"⚠️ No component resolved, skipping: {search_path}")

        # Log top results for debugging
        if filtered_results:
            logger.info(
                f"Top result: {filtered_results[0]['name']} (score: {filtered_results[0]['score']:.4f})"
            )

        return filtered_results

    except Exception as e:
        logger.error(f"❌ ModuleWrapper search failed: {e}", exc_info=True)
        return []


def _create_card_from_component(
    component: Any, params: Dict[str, Any]
) -> Optional[Union[Card, Dict[str, Any]]]:
    """
    Create a card using a component found by the ModuleWrapper.

    ENHANCED: Now includes post-construction configuration for DecoratedText widgets.

    Args:
        component: The component to use (class or function)
        params: Parameters to pass to the component

    Returns:
        Card object or dictionary
    """
    if not component or not _card_framework_wrapper:
        return None

    # TRUST MODULEWRAPPER: Use create_card_component functionality
    logger.info(
        f"🔧 Using trusted ModuleWrapper.create_card_component for: {type(component).__name__}"
    )

    result = _card_framework_wrapper.create_card_component(component, params)

    # POST-CONSTRUCTION ENHANCEMENT: Handle DecoratedText widgets specifically
    if (
        result
        and hasattr(result, "__class__")
        and "DecoratedText" in result.__class__.__name__
    ):
        logger.info("🎯 Post-construction configuration for DecoratedText widget")

        # Apply DecoratedText-specific configurations after creation
        try:
            # Handle topLabel/top_label
            top_label = params.get("topLabel") or params.get("top_label")
            if top_label and hasattr(result, "top_label"):
                result.top_label = top_label
                logger.info(f"✅ Set DecoratedText top_label: {top_label}")

            # Handle bottomLabel/bottom_label
            bottom_label = params.get("bottomLabel") or params.get("bottom_label")
            if bottom_label and hasattr(result, "bottom_label"):
                result.bottom_label = bottom_label
                logger.info(f"✅ Set DecoratedText bottom_label: {bottom_label}")

            # Handle wrap_text
            if "wrap_text" in params and hasattr(result, "wrap_text"):
                result.wrap_text = params["wrap_text"]
                logger.info(f"✅ Set DecoratedText wrap_text: {params['wrap_text']}")

            # Handle horizontal_alignment
            if "horizontal_alignment" in params and hasattr(
                result, "horizontal_alignment"
            ):
                result.horizontal_alignment = params["horizontal_alignment"]
                logger.info(
                    f"✅ Set DecoratedText horizontal_alignment: {params['horizontal_alignment']}"
                )

            # Handle switch_control
            if "switch_control" in params and hasattr(result, "switch_control"):
                result.switch_control = params["switch_control"]
                logger.info("✅ Set DecoratedText switch_control")

            # Handle button configuration
            if "button" in params and hasattr(result, "button"):
                button_data = params["button"]
                if isinstance(button_data, dict):
                    # Try to create button using Card Framework
                    try:
                        from card_framework.v2.widgets import Button, OnClick, OpenLink

                        # Create button with proper configuration
                        button_text = button_data.get("text", "Button")
                        button = Button(text=button_text)

                        # Handle onClick action
                        action_url = (
                            button_data.get("onClick", {})
                            .get("openLink", {})
                            .get("url")
                            or button_data.get("onclick_action")
                            or button_data.get("url")
                            or button_data.get("action")
                        )
                        if action_url:
                            button.on_click = OnClick(
                                open_link=OpenLink(url=action_url)
                            )
                            logger.info(
                                f"✅ Set DecoratedText button onClick: {action_url}"
                            )

                        # Handle button type/style
                        btn_type = button_data.get("type")
                        if btn_type and hasattr(button, "type"):
                            button.type = btn_type
                            logger.info(f"✅ Set DecoratedText button type: {btn_type}")

                        result.button = button
                        logger.info(f"✅ Set DecoratedText button: {button_text}")

                    except ImportError:
                        # Fallback to direct assignment
                        result.button = button_data
                        logger.info(
                            f"✅ Set DecoratedText button (fallback): {button_data}"
                        )

            # Handle icon configuration
            if "icon" in params and hasattr(result, "icon"):
                icon_data = params["icon"]
                if isinstance(icon_data, dict):
                    try:
                        from card_framework.v2.widgets import Icon

                        # Create icon with proper configuration
                        if "icon_url" in icon_data:
                            icon = Icon(icon_url=icon_data["icon_url"])
                        elif "known_icon" in icon_data:
                            icon = Icon(known_icon=icon_data["known_icon"])
                        else:
                            icon = icon_data

                        result.icon = icon
                        logger.info("✅ Set DecoratedText icon")

                    except ImportError:
                        # Fallback to direct assignment
                        result.icon = icon_data
                        logger.info("✅ Set DecoratedText icon (fallback)")

        except Exception as config_error:
            logger.warning(
                f"⚠️ DecoratedText post-construction configuration failed: {config_error}"
            )
            # Don't fail the entire creation process due to configuration issues

    if result:
        logger.info(f"✅ ModuleWrapper created component: {type(result).__name__}")

    return result


# REMOVED: _recursively_process_components function - redundant with ModuleWrapper functionality


def _create_card_with_hybrid_approach(
    card_component: Any, params: Dict[str, Any], sections: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a card using the hybrid approach with RECURSIVE component processing.

    This approach recursively processes all parameters to find and convert nested
    components (like buttons, images, etc.) using to_dict() methods before
    creating the main card component.

    Args:
        card_component: Any component found by semantic search
        params: Parameters for the card (header, etc.)
        sections: Optional sections to add directly

    Returns:
        Card in Google Chat API format
    """
    try:
        logger.info(
            f"🔧 Hybrid approach with recursive processing: {list(params.keys())}"
        )

        # DIRECT BUTTON PROCESSING: Handle button conversion directly in hybrid approach
        processed_params = dict(params)  # Copy params

        # Process buttons if they exist
        if "buttons" in params and isinstance(params["buttons"], list):
            processed_buttons = []
            for btn_data in params["buttons"]:
                if isinstance(btn_data, dict):
                    # Convert to proper Google Chat format
                    converted_btn = {"text": btn_data.get("text", "Button")}

                    # Handle onclick action
                    onclick_action = (
                        btn_data.get("onclick_action")
                        or btn_data.get("action")
                        or btn_data.get("url")
                    )
                    if onclick_action:
                        converted_btn["onClick"] = {"openLink": {"url": onclick_action}}

                    # CRITICAL FIX: Use correct 'type' field for button styling (not 'style')
                    btn_type = btn_data.get("type")
                    if btn_type in ["FILLED", "FILLED_TONAL", "OUTLINED", "BORDERLESS"]:
                        converted_btn["type"] = btn_type
                        logger.info(f"🎨 Added button type: {btn_type}")

                    processed_buttons.append(converted_btn)
                    logger.info(f"🔄 Converted button: {converted_btn}")

            processed_params["buttons"] = processed_buttons
            logger.info(
                f"✅ Button processing complete: {len(processed_buttons)} buttons"
            )

        # TRUST _create_card_from_component - it handles any component type intelligently
        created_component = _create_card_from_component(
            card_component, processed_params
        )

        if created_component is None:
            logger.info(
                "⚠️ Component creation returned None, building card from processed params"
            )
            # Build card structure from processed params directly
            card_dict = _build_card_structure_from_params(processed_params, sections)
        else:
            logger.info(f"✅ Component created: {type(created_component)}")

            # Try to use the component's to_dict() if available
            # Check if component is a full card (has sections) or a widget
            component_dict = None
            if hasattr(created_component, "to_dict"):
                component_dict = created_component.to_dict()
                logger.info("✅ Used component.to_dict() after recursive processing")
            elif isinstance(created_component, dict):
                component_dict = created_component

            # If it's a full card, use directly; otherwise build from widget
            if component_dict and "sections" in component_dict:
                card_dict = component_dict
                logger.info("🎯 Component is a full Card, using directly")
            else:
                logger.info(
                    "🧩 Component is a widget, incorporating into card structure"
                )
                card_dict = _build_card_from_widget(
                    created_component, processed_params, sections
                )

        # Generate a unique card ID
        card_id = (
            f"hybrid_card_{int(time.time())}_{hash(str(processed_params)) % 10000}"
        )

        # Create the final card dictionary
        result = {"cardId": card_id, "card": card_dict}

        logger.info(
            f"✅ Hybrid approach created card with structure: {list(card_dict.keys())}"
        )
        return result

    except Exception as e:
        logger.error(
            f"❌ Failed to create card with hybrid approach: {e}", exc_info=True
        )

        # Create a fallback card using processed_params if available
        fallback_params = locals().get("processed_params", params)
        return {
            "cardId": f"fallback_{int(time.time())}",
            "card": {
                "header": {
                    "title": fallback_params.get("title", "Fallback Card"),
                    "subtitle": fallback_params.get(
                        "subtitle", "Error occurred during card creation"
                    ),
                },
                "sections": [
                    {"widgets": [{"textParagraph": {"text": f"Error: {str(e)}"}}]}
                ],
            },
        }


def _build_simple_card_structure(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a simple card structure when no ModuleWrapper components are found.

    SIMPLIFIED: This replaces complex transformation logic with a simple, reliable approach.

    Args:
        params: Card parameters (title, text, buttons, etc.)

    Returns:
        Google Chat API format card with cardId
    """
    card_dict = _build_card_structure_from_params(params)

    return {
        "cardId": f"simple_card_{int(time.time())}_{hash(str(params)) % 10000}",
        "card": card_dict,
    }


def _validate_card_content(card_dict: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate that a card has actual renderable content for Google Chat.

    Args:
        card_dict: The card dictionary to validate

    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    issues = []

    # Check if card has any content at all
    if not card_dict:
        issues.append("Card dictionary is empty")
        return False, issues

    # Check header content
    header_has_content = False
    if "header" in card_dict and isinstance(card_dict["header"], dict):
        header = card_dict["header"]
        if header.get("title") and header["title"].strip():
            header_has_content = True
        elif header.get("subtitle") and header["subtitle"].strip():
            header_has_content = True

    # Check sections content
    sections_have_content = False
    if "sections" in card_dict and isinstance(card_dict["sections"], list):
        for section_idx, section in enumerate(card_dict["sections"]):
            if not isinstance(section, dict):
                issues.append(f"Section {section_idx} is not a dictionary")
                continue

            if "widgets" not in section:
                issues.append(f"Section {section_idx} has no widgets")
                continue

            widgets = section["widgets"]
            if not isinstance(widgets, list):
                issues.append(f"Section {section_idx} widgets is not a list")
                continue

            if len(widgets) == 0:
                issues.append(f"Section {section_idx} has empty widgets list")
                continue

            # Check each widget for actual content
            section_has_content = False
            for widget_idx, widget in enumerate(widgets):
                if not isinstance(widget, dict):
                    issues.append(
                        f"Section {section_idx}, widget {widget_idx} is not a dictionary"
                    )
                    continue

                # Check for text content
                if "textParagraph" in widget:
                    text_content = widget["textParagraph"].get("text", "").strip()
                    if text_content:
                        section_has_content = True

                # Check for image content
                elif "image" in widget:
                    image_url = widget["image"].get("imageUrl", "").strip()
                    if image_url:
                        section_has_content = True

                # Check for button content
                elif "buttonList" in widget:
                    buttons = widget["buttonList"].get("buttons", [])
                    if isinstance(buttons, list) and len(buttons) > 0:
                        for button in buttons:
                            if (
                                isinstance(button, dict)
                                and button.get("text", "").strip()
                            ):
                                section_has_content = True
                                break

                # Check other widget types
                elif any(
                    key in widget
                    for key in [
                        "decoratedText",
                        "selectionInput",
                        "textInput",
                        "divider",
                    ]
                ):
                    section_has_content = True

            if section_has_content:
                sections_have_content = True
    else:
        issues.append("Card has no sections or sections is not a list")

    # Card must have either header content OR section content
    has_content = header_has_content or sections_have_content

    if not has_content:
        issues.append(
            "Card has no renderable content (empty header and empty/missing sections)"
        )

    return has_content, issues


def _build_card_structure_from_params(
    params: Dict[str, Any], sections: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Build card structure directly from parameters when no component is available."""
    card_dict = {}

    # CRITICAL FIX: Handle both flat and nested header structures
    header = {}

    # Check if params has a nested "header" object
    if "header" in params and isinstance(params["header"], dict):
        header_data = params["header"]
        if "title" in header_data:
            header["title"] = header_data["title"]
        if "subtitle" in header_data:
            header["subtitle"] = header_data["subtitle"]
    else:
        # Handle flat structure (title/subtitle directly in params)
        if "title" in params:
            header["title"] = params["title"]
        if "subtitle" in params:
            header["subtitle"] = params["subtitle"]

    # Only add header if we have title or subtitle
    if header:
        card_dict["header"] = header
        logger.info(f"✅ Built header: {header}")

    # Handle sections
    # CRITICAL FIX: Also check params.get("sections") when explicit sections arg is None
    # This ensures NLP-extracted sections don't get dropped in fallback paths
    if sections:
        card_dict["sections"] = sections
    elif isinstance(params.get("sections"), list) and params.get("sections"):
        card_dict["sections"] = params["sections"]
        logger.info(
            f"✅ Using sections from params: {len(params['sections'])} section(s)"
        )
    else:
        widgets = []

        # Add text widget if provided
        if "text" in params:
            widgets.append({"textParagraph": {"text": params["text"]}})
            logger.info(f"✅ Added text widget: {params['text'][:50]}...")

        # Add image widget if provided
        if "image_url" in params:
            image_widget = {"image": {"imageUrl": params["image_url"]}}
            # Add alt text if provided
            if "image_alt_text" in params:
                image_widget["image"]["altText"] = params["image_alt_text"]
            widgets.append(image_widget)
            logger.info(f"✅ Added image widget: {params['image_url']}")

        # Add buttons widget if provided
        if "buttons" in params and isinstance(params["buttons"], list):
            button_widgets = []
            for button_data in params["buttons"]:
                if isinstance(button_data, dict):
                    # CRITICAL FIX: Check if button is already processed (has onClick)
                    if "onClick" in button_data:
                        # Button already processed by hybrid approach - use as-is
                        button_widget = button_data.copy()
                        logger.info(f"✅ Using pre-processed button: {button_widget}")
                    else:
                        # Button not processed yet - process it now
                        button_widget = {"text": button_data.get("text", "Button")}

                        # Handle various onclick formats
                        onclick_url = (
                            button_data.get("onclick_action")
                            or button_data.get("action")
                            or button_data.get("url")
                        )
                        if onclick_url:
                            button_widget["onClick"] = {
                                "openLink": {"url": onclick_url}
                            }

                        # CRITICAL FIX: Use correct 'type' field for button styling (not 'style')
                        btn_type = button_data.get("type")
                        if btn_type in [
                            "FILLED",
                            "FILLED_TONAL",
                            "OUTLINED",
                            "BORDERLESS",
                        ]:
                            button_widget["type"] = btn_type
                            logger.info(f"🎨 Added button type: {btn_type}")

                        logger.info(f"✅ Processed new button: {button_widget}")

                    button_widgets.append(button_widget)

            if button_widgets:
                widgets.append({"buttonList": {"buttons": button_widgets}})

        # CRITICAL FIX: Don't create empty sections - ensure we have some content
        if not widgets and not header:
            # Fallback: add a basic text widget to prevent completely empty card
            widgets.append(
                {"textParagraph": {"text": "Empty card - no content provided"}}
            )
            logger.warning("⚠️ Created fallback text widget for empty card")

        # Always create sections even if no widgets (required for valid card)
        card_dict["sections"] = [{"widgets": widgets}]
        logger.info(f"✅ Built {len(widgets)} widgets in sections")

    # VALIDATE CARD CONTENT before returning
    is_valid, issues = _validate_card_content(card_dict)
    if not is_valid:
        logger.error(f"❌ CARD CONTENT VALIDATION FAILED: {issues}")
        logger.error(f"❌ Invalid card structure: {json.dumps(card_dict, indent=2)}")

        # Add error information to card for debugging
        card_dict.setdefault("_debug_info", {})["validation_issues"] = issues
    else:
        logger.info("✅ Card content validation passed")

    logger.info(f"✅ Final card structure keys: {list(card_dict.keys())}")
    return card_dict


def _universal_component_unpacker(
    component_data: Any, context: str = "component"
) -> List[Dict[str, Any]]:
    """
    Universal component unpacker that recursively extracts all widget data
    from any component's to_dict() output and converts to Google Chat format.

    ENHANCED: Now properly handles advanced widgets like DecoratedText, preserving their structure.
    """
    widgets = []
    logger.info(f"🔓 Universal unpacking: {context} data: {component_data}")

    if not component_data:
        return widgets

    if isinstance(component_data, dict):
        # CRITICAL FIX: Check for already-valid Google Chat widget types FIRST
        # This prevents destructive conversion of advanced widgets to simple text
        valid_widget_types = {
            "textParagraph",
            "image",
            "decoratedText",
            "buttonList",
            "selectionInput",
            "textInput",
            "dateTimePicker",
            "divider",
            "grid",
            "columns",
            "chipList",
        }

        # If the component data already contains a valid widget type, preserve it
        widget_type_found = None
        for widget_type in valid_widget_types:
            if widget_type in component_data:
                widget_type_found = widget_type
                break

        if widget_type_found:
            # This is already a properly formatted Google Chat widget - use it directly
            widgets.append(component_data)
            logger.info(f"✅ Preserved valid {widget_type_found} widget from {context}")
            return widgets

        # ENHANCED: Check for DecoratedText patterns specifically
        # DecoratedText components often have topLabel, bottomLabel, text, button, etc.
        if any(
            key in component_data
            for key in ["topLabel", "top_label", "bottomLabel", "bottom_label"]
        ):
            decorated_text_widget = {"decoratedText": {}}

            # Map common fields to decoratedText format
            if "text" in component_data:
                decorated_text_widget["decoratedText"]["text"] = component_data["text"]

            # Handle labels
            top_label = component_data.get("topLabel", component_data.get("top_label"))
            if top_label:
                decorated_text_widget["decoratedText"]["topLabel"] = top_label

            bottom_label = component_data.get(
                "bottomLabel", component_data.get("bottom_label")
            )
            if bottom_label:
                decorated_text_widget["decoratedText"]["bottomLabel"] = bottom_label

            # Handle button
            button_data = component_data.get("button")
            if button_data and isinstance(button_data, dict):
                button_widget = {"text": button_data.get("text", "Button")}
                action_url = (
                    button_data.get("onClick", {}).get("openLink", {}).get("url")
                    or button_data.get("onclick_action")
                    or button_data.get("url")
                    or button_data.get("action")
                )
                if action_url:
                    button_widget["onClick"] = {"openLink": {"url": action_url}}
                decorated_text_widget["decoratedText"]["button"] = button_widget

            widgets.append(decorated_text_widget)
            logger.info(f"✅ Created decoratedText widget from {context}")
            return widgets

        # Look for button patterns (existing logic)
        if "buttons" in component_data or "button" in component_data:
            buttons_data = component_data.get("buttons", [component_data.get("button")])
            if buttons_data and buttons_data != [None]:
                button_widgets = []
                for btn in (
                    buttons_data if isinstance(buttons_data, list) else [buttons_data]
                ):
                    if isinstance(btn, dict):
                        button_widget = {
                            "text": btn.get("text", btn.get("label", "Button"))
                        }
                        # Look for various action patterns
                        action_url = (
                            btn.get("onClick", {}).get("openLink", {}).get("url")
                            or btn.get("onclick_action")
                            or btn.get("url")
                            or btn.get("action")
                        )
                        if action_url:
                            button_widget["onClick"] = {"openLink": {"url": action_url}}
                        button_widgets.append(button_widget)

                if button_widgets:
                    widgets.append({"buttonList": {"buttons": button_widgets}})
                    logger.info(
                        f"✅ Unpacked {len(button_widgets)} buttons from {context}"
                    )

        # Look for text patterns (ONLY if not already processed as advanced widget)
        elif "text" in component_data and not any(
            key in component_data
            for key in ["topLabel", "top_label", "bottomLabel", "bottom_label"]
        ):
            widgets.append({"textParagraph": {"text": component_data["text"]}})
            logger.info(f"✅ Unpacked simple text from {context}")

        # Look for image patterns
        elif "imageUrl" in component_data or "image_url" in component_data:
            image_url = component_data.get("imageUrl", component_data.get("image_url"))
            image_widget = {"image": {"imageUrl": image_url}}
            alt_text = component_data.get("altText", component_data.get("alt_text"))
            if alt_text:
                image_widget["image"]["altText"] = alt_text
            widgets.append(image_widget)
            logger.info(f"✅ Unpacked image from {context}")

        # Recursively process nested structures (but skip already-processed keys)
        processed_keys = {
            "text",
            "buttons",
            "button",
            "imageUrl",
            "image_url",
            "altText",
            "alt_text",
            "topLabel",
            "top_label",
            "bottomLabel",
            "bottom_label",
        }
        for key, value in component_data.items():
            if key not in processed_keys and not any(
                wtype in key for wtype in valid_widget_types
            ):
                nested_widgets = _universal_component_unpacker(
                    value, f"{context}.{key}"
                )
                widgets.extend(nested_widgets)

    elif isinstance(component_data, list):
        # Process list items
        for i, item in enumerate(component_data):
            nested_widgets = _universal_component_unpacker(item, f"{context}[{i}]")
            widgets.extend(nested_widgets)

    return widgets


def _build_header_from_params(params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Build card header from params.

    Handles both flat structure (title/subtitle in params) and nested structure
    (header object in params).

    Args:
        params: Card parameters

    Returns:
        Header dict or None if no title/subtitle provided
    """
    header = {}

    # Check for nested header object first
    if "header" in params and isinstance(params["header"], dict):
        header_data = params["header"]
        if "title" in header_data:
            header["title"] = header_data["title"]
        if "subtitle" in header_data:
            header["subtitle"] = header_data["subtitle"]
    else:
        # Flat structure
        if "title" in params:
            header["title"] = params["title"]
        if "subtitle" in params:
            header["subtitle"] = params["subtitle"]

    return header if header else None


def _add_widgets_from_params(
    widgets: List[Dict[str, Any]],
    params: Dict[str, Any],
    skip_types: Optional[set] = None,
) -> Dict[str, bool]:
    """
    Add widgets from params to the widgets list.

    This unified helper handles text, image_url, and buttons consistently
    across all card building paths. It processes params and appends the
    appropriate widgets to the provided list.

    Args:
        widgets: List to append widgets to (modified in place)
        params: Card parameters containing text, image_url, buttons, etc.
        skip_types: Optional set of widget types to skip ('text', 'image', 'buttons')

    Returns:
        Dict indicating which widget types were added:
        {'text': bool, 'image': bool, 'buttons': bool}
    """
    skip_types = skip_types or set()
    added = {"text": False, "image": False, "buttons": False}

    # Add text widget if provided
    if "text" not in skip_types and "text" in params:
        widgets.append({"textParagraph": {"text": params["text"]}})
        added["text"] = True
        logger.info(f"✅ Added text widget: {params['text'][:50]}...")

    # Add image widget if provided
    if "image" not in skip_types and "image_url" in params:
        image_widget = {"image": {"imageUrl": params["image_url"]}}
        if "image_alt_text" in params:
            image_widget["image"]["altText"] = params["image_alt_text"]
        widgets.append(image_widget)
        added["image"] = True
        logger.info(f"✅ Added image widget: {params['image_url']}")

    # Add buttons widget if provided
    if (
        "buttons" not in skip_types
        and "buttons" in params
        and isinstance(params["buttons"], list)
    ):
        button_widgets = []
        for button_data in params["buttons"]:
            if isinstance(button_data, dict):
                # Check if button is already processed (has onClick)
                if "onClick" in button_data:
                    # Button already processed - use as-is
                    button_widgets.append(button_data)
                elif button_data.get("text"):
                    # Process the button
                    button_widget = {"text": button_data.get("text", "Button")}

                    # Handle various onclick formats
                    onclick_url = (
                        button_data.get("onclick_action")
                        or button_data.get("action")
                        or button_data.get("url")
                    )
                    if onclick_url:
                        button_widget["onClick"] = {"openLink": {"url": onclick_url}}

                    # Handle button type/style
                    btn_type = button_data.get("type")
                    if btn_type in ["FILLED", "FILLED_TONAL", "OUTLINED", "BORDERLESS"]:
                        button_widget["type"] = btn_type

                    button_widgets.append(button_widget)

        if button_widgets:
            widgets.append({"buttonList": {"buttons": button_widgets}})
            added["buttons"] = True
            logger.info(f"✅ Added buttonList with {len(button_widgets)} buttons")

    return added


def _build_card_from_widget(
    component: Any, params: Dict[str, Any], sections: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Build card structure from any widget component type.

    Handles three component types:
    - Objects with to_dict() method (widget components)
    - Plain dictionaries (widget dicts)
    - Raw objects without to_dict() (fallback)
    """
    card_dict = {}

    # Build header from params
    header = _build_header_from_params(params)
    if header:
        card_dict["header"] = header

    # If sections provided, use them directly
    if sections:
        card_dict["sections"] = sections
        return card_dict

    # Build widgets based on component type
    widgets = []
    added = _add_widgets_from_params(widgets, params)

    if hasattr(component, "to_dict"):
        # Widget component with to_dict() - use universal unpacker
        component_dict = component.to_dict()
        component_name = type(component).__name__

        logger.info(
            f"🔓 Using trusted universal unpacker for component: {component_name}"
        )
        unpacked_widgets = _universal_component_unpacker(component_dict, component_name)

        # Filter out duplicates from params
        for widget in unpacked_widgets:
            if not isinstance(widget, dict):
                widgets.append(widget)
                continue
            if added["text"] and "textParagraph" in widget:
                logger.info("🔧 Skipping duplicate text widget (using params text)")
                continue
            if added["image"] and "image" in widget:
                logger.info("🔧 Skipping duplicate image widget (using params image)")
                continue
            if added["buttons"] and "buttonList" in widget:
                logger.info(
                    "🔧 Skipping duplicate button widget (using params buttons)"
                )
                continue
            widgets.append(widget)

        logger.info(f"✅ Universal unpacker extracted widgets from {component_name}")

    elif isinstance(component, dict):
        # Plain dictionary - validate and add as widget
        valid_widget_types = {
            "textParagraph",
            "image",
            "decoratedText",
            "buttonList",
            "selectionInput",
            "textInput",
            "dateTimePicker",
            "divider",
            "grid",
            "columns",
        }

        if "text" in component and len(component) <= 2:
            widgets.append({"textParagraph": component})
        elif any(key in valid_widget_types for key in component.keys()):
            widgets.append(component)
        else:
            logger.warning(
                f"⚠️ Unknown component dict structure: {list(component.keys())}, creating fallback"
            )
            widgets.append(
                {
                    "textParagraph": {
                        "text": f"Component data: {str(component)[:100]}..."
                    }
                }
            )

    else:
        # Raw component without to_dict() - extract from __dict__
        if not added["text"] and hasattr(component, "__dict__"):
            component_data = component.__dict__
            if component_data and "text" in component_data:
                widgets.append({"textParagraph": {"text": str(component_data["text"])}})

    card_dict["sections"] = [{"widgets": widgets}]
    return card_dict


def _convert_field_names_to_snake_case(obj: Any) -> Any:
    """Convert camelCase field names to snake_case recursively for webhook API."""
    if isinstance(obj, dict):
        converted = {}
        for key, value in obj.items():
            # Convert camelCase to snake_case
            snake_key = _camel_to_snake(key)
            if snake_key != key:
                logger.info(f"WEBHOOK CONVERSION: {key} -> {snake_key}")
            converted[snake_key] = _convert_field_names_to_snake_case(value)
        return converted
    elif isinstance(obj, list):
        return [_convert_field_names_to_snake_case(item) for item in obj]
    else:
        return obj


def _camel_to_snake(camel_str: str) -> str:
    """Convert camelCase string to snake_case with caching for performance."""
    global _camel_to_snake_cache

    if camel_str in _camel_to_snake_cache:
        return _camel_to_snake_cache[camel_str]

    import re

    # Insert underscores before capital letters
    snake_str = re.sub("([a-z0-9])([A-Z])", r"\1_\2", camel_str)
    result = snake_str.lower()

    _camel_to_snake_cache[camel_str] = result
    return result


def setup_unified_card_tool(mcp: FastMCP) -> None:
    """
    Setup the unified card tool for MCP.

    Args:
        mcp: The FastMCP server instance
    """
    logger.info("Setting up unified card tool")

    # Initialize card framework wrapper
    _initialize_card_framework_wrapper()

    @mcp.tool(
        name="send_dynamic_card",
        description="Send any type of card to Google Chat using natural language description with advanced NLP parameter extraction",
        tags={"chat", "card", "dynamic", "google", "unified", "nlp"},
        annotations={
            "title": "Send Dynamic Card with NLP",
            "description": "Unified tool for sending Google Chat Cards v2 with natural language processing for complex card creation. Automatically extracts card structure from descriptions including sections, decoratedText widgets, icons, and buttons.",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
            "examples": [
                {
                    "description": "Simple text card",
                    "card_description": "simple notification",
                    "card_params": {"title": "Alert", "text": "System update complete"},
                },
                {
                    "description": "Natural language card with sections",
                    "card_description": "Create a monitoring dashboard with title 'Server Status' and three sections: 1. 'Health Check' section with decoratedText 'All Systems Go' with topLabel 'Status' and green check icon 2. 'Performance' section with decoratedText 'Response Time: 120ms' with topLabel 'API Latency' 3. 'Actions' section with a button 'View Logs' linking to https://logs.example.com",
                    "card_params": {},
                },
                {
                    "description": "Dashboard with decoratedText widgets",
                    "card_description": "Create a project dashboard with sections showing metrics: first section 'Build Status' with decoratedText 'Passing' with topLabel 'Latest Build' and green check icon, second section 'Coverage' with decoratedText '92%' with topLabel 'Code Coverage' and chart icon",
                    "card_params": {"title": "Project Dashboard"},
                },
                {
                    "description": "Card with collapsible sections",
                    "card_description": "Create a report card with collapsible sections: 'Summary' section (collapsible) with text about Q4 results, 'Details' section with a grid of metrics, and 'Actions' section with buttons 'Download PDF' and 'Share Report'",
                    "card_params": {},
                },
            ],
            "natural_language_features": [
                "Automatic extraction of card title, subtitle, and text from descriptions",
                "Support for numbered/bulleted sections (e.g., '1. Section Name' or '- Section Name')",
                "DecoratedText widget creation with topLabel, bottomLabel, and icons",
                "Icon mapping from natural language (e.g., 'green check' → CHECK_CIRCLE icon)",
                "Button extraction with text and onClick actions from URLs",
                "Grid layouts and column arrangements from descriptions",
                "Collapsible section headers",
                "HTML content formatting",
                "Switch controls and interactive elements",
            ],
            "limitations": [
                "Images cannot be placed in card headers - they become widgets in sections",
                "Maximum 100 widgets per section, 6 buttons per buttonList",
                "Field length limits: title/subtitle (200 chars), text (4000 chars)",
                "Icon mapping supports 20+ common icons with color modifiers",
            ],
        },
    )
    async def send_dynamic_card(
        user_google_email: str,
        space_id: str,
        card_description: str,
        card_params: Optional[Dict[str, Any]] = None,
        thread_key: Optional[str] = None,
        webhook_url: Optional[str] = None,
        use_colbert: bool = False,
    ) -> SendDynamicCardResponse:
        """
        Send any type of card to Google Chat using natural language description with enhanced NLP.

        This unified tool combines ModuleWrapper semantic search with advanced NLP parameter extraction
        to create complex Google Chat cards from natural language descriptions.

        See SendDynamicCardResponse, CardParams, and ICON_MAPPINGS in unified_card_types.py for
        detailed field descriptions, supported widget types, and icon mapping reference.

        Args:
            user_google_email: The user's Google email address for authentication
            space_id: The Google Chat space ID to send the card to
            card_description: Natural language description of the card structure and content
            card_params: Optional dict of explicit parameters that override NLP-extracted values
            thread_key: Optional thread key for threaded message replies
            webhook_url: Optional webhook URL for direct delivery (bypasses API auth)
            use_colbert: If True, use ColBERT multi-vector embeddings for semantic search.
                        This skips NLP parsing and uses the raw description directly as the
                        query to the RAG database. ColBERT provides more accurate semantic
                        matching at the token level. Default is False.

        Returns:
            SendDynamicCardResponse with delivery status, component info, and NLP extraction details
        """
        try:
            logger.info(f"🔍 Finding card component for: {card_description}")
            logger.info(f"🤖 ColBERT mode: {use_colbert}")

            # Default parameters if not provided
            if card_params is None:
                card_params = {}

            # ENHANCED NLP INTEGRATION: Parse natural language description to extract parameters
            # NOTE: NLP parsing runs for BOTH ColBERT and standard modes.
            # ColBERT determines how we SEARCH for the right component template,
            # but NLP extracts the PARAMETERS (title, buttons, text) to populate it.
            # They are complementary, not alternatives!
            try:
                logger.info(
                    f"🧠 Parsing natural language description: '{card_description}'"
                )
                nlp_extracted_params = parse_enhanced_natural_language_description(
                    card_description
                )

                if nlp_extracted_params:
                    logger.info(
                        f"✅ NLP extracted parameters: {list(nlp_extracted_params.keys())}"
                    )

                    # Merge NLP extracted parameters with user-provided card_params
                    # User-provided card_params take priority over NLP-extracted ones
                    merged_params: Dict[str, Any] = {}
                    merged_params.update(
                        nlp_extracted_params
                    )  # Add NLP extracted params first
                    merged_params.update(card_params)  # User params override NLP params

                    # CRITICAL: Ensure NLP-extracted `sections` survive and are used.
                    # Many descriptions imply sections/widgets, but older flows only used top-level `buttons`.
                    if isinstance(merged_params.get("sections"), list):
                        logger.info(
                            f"✅ NLP produced sections: {len(merged_params['sections'])} section(s)"
                        )

                    card_params = merged_params
                else:
                    logger.info(
                        "📝 No parameters extracted from natural language description"
                    )

            except Exception as nlp_error:
                logger.warning(
                    f"⚠️ NLP parsing failed, continuing with original card_params: {nlp_error}"
                )

            # Initialize default best_match to prevent UnboundLocalError
            best_match = {"type": "fallback", "name": "simple_fallback", "score": 0.0}
            google_format_card = None

            # Find card components using ModuleWrapper (ColBERT or standard)
            if use_colbert:
                logger.info("🔍 Using ColBERT multi-vector search...")
                results = await _find_card_component_colbert(card_description)
            else:
                results = await _find_card_component(card_description)

            if results:
                # Get the best match component
                best_match = results[0]
                component = best_match.get("component")

                # ENHANCED COMPONENT VALIDATION: Handle module objects and extract usable classes/functions
                usable_component = None
                component_type = "unknown"

                if component:
                    if inspect.ismodule(component):
                        logger.info(
                            "🔍 Component is a module, extracting usable classes/functions..."
                        )

                        # Extract usable classes and functions from the module
                        module_members = inspect.getmembers(component)
                        potential_components = []

                        for name, member in module_members:
                            # Skip private members and built-in types
                            if name.startswith("_"):
                                continue

                            # Look for classes that might be card components
                            if inspect.isclass(member):
                                # Check if it's likely a card component (has relevant methods or attributes)
                                if (
                                    hasattr(member, "to_dict")
                                    or hasattr(member, "__init__")
                                    or any(
                                        keyword in name.lower()
                                        for keyword in [
                                            "card",
                                            "widget",
                                            "button",
                                            "text",
                                            "image",
                                            "decorated",
                                        ]
                                    )
                                ):
                                    potential_components.append((name, member, "class"))
                                    logger.info(
                                        f"🔍 Found potential class component: {name}"
                                    )

                            # Look for functions that might create cards
                            elif inspect.isfunction(member) or callable(member):
                                if any(
                                    keyword in name.lower()
                                    for keyword in [
                                        "create",
                                        "make",
                                        "build",
                                        "card",
                                        "widget",
                                    ]
                                ):
                                    potential_components.append(
                                        (name, member, "function")
                                    )
                                    logger.info(
                                        f"🔍 Found potential function component: {name}"
                                    )

                        if potential_components:
                            # Use the first potential component (could be enhanced with better selection logic)
                            component_name, usable_component, component_type = (
                                potential_components[0]
                            )
                            logger.info(
                                f"✅ Extracted {component_type} component '{component_name}' from module"
                            )
                            best_match["extracted_component"] = component_name
                            best_match["type"] = (
                                "class" if component_type == "class" else "function"
                            )
                        else:
                            logger.warning(
                                "⚠️ Module contains no usable card components"
                            )
                            usable_component = None

                    elif inspect.isclass(component) or callable(component):
                        # Component is already a usable class or function
                        usable_component = component
                        component_type = (
                            "class" if inspect.isclass(component) else "function"
                        )
                        logger.info(f"✅ Component is directly usable {component_type}")
                        best_match["type"] = component_type

                    else:
                        logger.warning(
                            f"⚠️ Component is neither module, class, nor callable: {type(component)}"
                        )
                        usable_component = None

                # Use component if we found a usable one
                if usable_component:
                    logger.info(
                        f"✅ Using {component_type} component: {best_match.get('path')} (score: {best_match.get('score'):.4f})"
                    )

                    # TRUST MODULEWRAPPER: Use hybrid approach for component-based card creation
                    logger.info("🔧 Using trusted ModuleWrapper with hybrid approach")

                    # If NLP provided explicit sections/widgets, pass them through so they aren't dropped.
                    sections_from_params = (
                        card_params.get("sections")
                        if isinstance(card_params.get("sections"), list)
                        else None
                    )

                    google_format_card = _create_card_with_hybrid_approach(
                        card_component=usable_component,
                        params=card_params,
                        sections=sections_from_params,
                    )
                    logger.info(
                        "✅ Successfully created card using ModuleWrapper hybrid approach"
                    )
                else:
                    logger.warning(
                        "⚠️ No usable component found, using simple card structure"
                    )

                    # If NLP extracted sections, prefer them over the legacy "buttons-only" fallback.
                    if isinstance(card_params.get("sections"), list):
                        google_format_card = {
                            "cardId": f"simple_card_{int(time.time())}_{hash(str(card_params)) % 10000}",
                            "card": _build_card_structure_from_params(
                                {
                                    k: v
                                    for k, v in card_params.items()
                                    if k != "sections"
                                },
                                sections=card_params.get("sections"),
                            ),
                        }
                    else:
                        google_format_card = _build_simple_card_structure(card_params)

                    best_match = {
                        "type": "simple_fallback",
                        "name": "simple_card",
                        "score": 0.0,
                    }
            else:
                logger.warning(
                    f"⚠️ No search results found for: {card_description}, using simple card structure"
                )
                google_format_card = _build_simple_card_structure(card_params)
                best_match = {
                    "type": "simple_fallback",
                    "name": "simple_card",
                    "score": 0.0,
                }

            if not google_format_card:
                return SendDynamicCardResponse(
                    success=False,
                    spaceId=space_id,
                    deliveryMethod="webhook" if webhook_url else "api",
                    cardType=best_match.get("type", "unknown"),
                    cardDescription=card_description,
                    userEmail=user_google_email,
                    validationPassed=False,
                    message="Failed to create card structure",
                    error="Card structure generation returned None",
                )

            # Create message payload
            message_obj = Message()

            # IMPORTANT: Don't set top-level message text when sending a card.
            # If we include both message-level text and a card widget (e.g. textParagraph),
            # Google Chat renders BOTH, which looks like duplicated content.
            # Keep text content inside card widgets only.

            # Add card to message - handle both single card object and wrapped format
            if isinstance(google_format_card, dict) and "cardsV2" in google_format_card:
                # Old format with wrapper - extract cards
                for card in google_format_card["cardsV2"]:
                    message_obj.cards_v2.append(card)
            else:
                # New format - single card object
                message_obj.cards_v2.append(google_format_card)

            # Render message
            message_body = message_obj.render()

            # Fix Card Framework v2 field name issue: ensure proper cards_v2 format for webhook
            # The Google Chat webhook API expects snake_case (cards_v2), NOT camelCase (cardsV2)
            if "cards_v_2" in message_body:
                message_body["cards_v2"] = message_body.pop("cards_v_2")
            # Convert camelCase back to snake_case for webhook delivery (webhook API expects snake_case)
            if "cardsV2" in message_body:
                message_body["cards_v2"] = message_body.pop("cardsV2")

            # CRITICAL DEBUGGING: Pre-validate card content before sending
            final_card = (
                google_format_card.get("card", {})
                if isinstance(google_format_card, dict)
                else {}
            )
            is_valid_content, content_issues = _validate_card_content(final_card)

            if not is_valid_content:
                logger.error(
                    "🚨 BLANK MESSAGE PREVENTION: Card has no renderable content!"
                )
                logger.error(f"🚨 Content validation issues: {content_issues}")
                logger.error(
                    f"🚨 Card params received: {json.dumps(card_params, indent=2)}"
                )
                logger.error(
                    f"🚨 Card structure created: {json.dumps(google_format_card, indent=2)}"
                )

                # Return an error instead of sending a blank card
                return SendDynamicCardResponse(
                    success=False,
                    spaceId=space_id,
                    deliveryMethod="webhook" if webhook_url else "api",
                    cardType=best_match.get("type", "unknown"),
                    componentInfo=ComponentSearchInfo(
                        componentFound=bool(best_match.get("name")),
                        componentName=best_match.get("name"),
                        componentPath=best_match.get("path"),
                        componentType=best_match.get("type"),
                        searchScore=best_match.get("score"),
                    ),
                    cardDescription=card_description,
                    threadKey=thread_key,
                    webhookUrl=webhook_url,
                    userEmail=user_google_email,
                    validationPassed=False,
                    validationIssues=content_issues,
                    message="Prevented sending blank card - no renderable content",
                    error=f"Validation issues: {'; '.join(content_issues)}",
                )

            logger.info("✅ Pre-send validation passed - card has renderable content")

            # Choose delivery method based on webhook_url
            if webhook_url:
                # CRITICAL FIX: Process thread key for webhook URL to enable proper threading
                if thread_key:
                    logger.info(
                        f"🧵 THREADING FIX: Processing thread key for webhook: {thread_key}"
                    )
                    webhook_url = _process_thread_key_for_webhook_url(
                        webhook_url, thread_key
                    )
                    logger.info(
                        "🧵 THREADING FIX: Updated webhook URL with thread parameters"
                    )

                # CRITICAL FIX: Recursively convert ALL field names to snake_case for webhook API
                # The Google Chat webhook API requires snake_case field names throughout the entire payload
                logger.info(
                    "🔧 Converting ALL camelCase fields to snake_case for webhook API compatibility"
                )
                webhook_message_body = _convert_field_names_to_snake_case(message_body)

                # CRITICAL FIX: Add thread to message body for webhook threading
                if thread_key:
                    webhook_message_body["thread"] = {"name": thread_key}
                    logger.debug(f"Added thread to webhook message body: {thread_key}")

                # ENHANCED DEBUGGING: Log everything before sending
                logger.info(
                    f"🔄 ENHANCED DEBUG - Sending via webhook URL: {webhook_url}"
                )
                logger.info("🧪 CARD DEBUG INFO:")
                logger.info(f"  - Description: '{card_description}'")
                logger.info(f"  - Params keys: {list(card_params.keys())}")
                logger.info(f"  - Component found: {bool(results)}")
                logger.info(
                    f"  - Best match: {best_match.get('name', 'N/A')} (score: {best_match.get('score', 0):.3f})"
                )
                logger.info(f"  - Card type: {best_match.get('type', 'unknown')}")

                # Log original card structure
                logger.info("📊 ORIGINAL CARD STRUCTURE:")
                logger.info(
                    f"   Keys: {list(google_format_card.keys()) if isinstance(google_format_card, dict) else 'Not a dict'}"
                )
                if (
                    isinstance(google_format_card, dict)
                    and "card" in google_format_card
                ):
                    card_content = google_format_card["card"]
                    logger.info(
                        f"   Card keys: {list(card_content.keys()) if isinstance(card_content, dict) else 'Not a dict'}"
                    )
                    if isinstance(card_content, dict):
                        if "header" in card_content:
                            header = card_content["header"]
                            logger.info(
                                f"   Header: title='{header.get('title', 'N/A')}', subtitle='{header.get('subtitle', 'N/A')}'"
                            )
                        if "sections" in card_content and isinstance(
                            card_content["sections"], list
                        ):
                            logger.info(
                                f"   Sections: {len(card_content['sections'])} section(s)"
                            )
                            for i, section in enumerate(card_content["sections"]):
                                if isinstance(section, dict) and "widgets" in section:
                                    widgets = section["widgets"]
                                    logger.info(
                                        f"     Section {i}: {len(widgets) if isinstance(widgets, list) else 0} widget(s)"
                                    )
                                    if isinstance(widgets, list):
                                        for j, widget in enumerate(widgets):
                                            if isinstance(widget, dict):
                                                widget_type = (
                                                    next(iter(widget.keys()))
                                                    if widget
                                                    else "empty"
                                                )
                                                logger.info(
                                                    f"       Widget {j}: type={widget_type}"
                                                )

                # Log final webhook payload
                logger.info("🔧 FINAL WEBHOOK PAYLOAD:")
                logger.info(
                    f"📋 Message JSON: {json.dumps(webhook_message_body, indent=2)}"
                )

                import requests

                # Log the request details
                logger.info("🌐 Making POST request to webhook:")
                logger.info(f"  URL: {webhook_url}")
                logger.info("  Headers: {'Content-Type': 'application/json'}")
                logger.info(
                    f"  Payload size: {len(json.dumps(webhook_message_body))} characters"
                )

                response = requests.post(
                    webhook_url,
                    json=webhook_message_body,
                    headers={"Content-Type": "application/json"},
                )

                # Enhanced response logging
                logger.info(f"🔍 WEBHOOK RESPONSE - Status: {response.status_code}")
                logger.info(f"🔍 WEBHOOK RESPONSE - Headers: {dict(response.headers)}")
                logger.info(f"🔍 WEBHOOK RESPONSE - Body: {response.text}")

                # Build component info for response
                component_info = ComponentSearchInfo(
                    componentFound=bool(best_match.get("name")),
                    componentName=best_match.get("name"),
                    componentPath=best_match.get("path"),
                    componentType=best_match.get("type"),
                    searchScore=best_match.get("score"),
                    extractedFromModule=best_match.get("extracted_from_module"),
                )

                # ANALYZE RESPONSE for content issues
                if response.status_code == 200:
                    # Check if response indicates content issues
                    response_text = response.text.lower()
                    if any(
                        keyword in response_text
                        for keyword in ["empty", "blank", "no content", "invalid"]
                    ):
                        logger.warning(
                            f"⚠️ SUCCESS but possible content issue - Response: {response.text}"
                        )
                        return SendDynamicCardResponse(
                            success=True,
                            spaceId=space_id,
                            deliveryMethod="webhook",
                            cardType=best_match.get("type", "unknown"),
                            componentInfo=component_info,
                            cardDescription=card_description,
                            threadKey=thread_key,
                            webhookUrl=webhook_url,
                            userEmail=user_google_email,
                            httpStatus=200,
                            validationPassed=True,
                            message=f"Card sent (Status 200) but may appear blank. Response: {response.text}",
                        )
                    else:
                        logger.info(
                            f"✅ Card sent successfully via webhook. Status: {response.status_code}"
                        )
                        return SendDynamicCardResponse(
                            success=True,
                            spaceId=space_id,
                            deliveryMethod="webhook",
                            cardType=best_match.get("type", "unknown"),
                            componentInfo=component_info,
                            cardDescription=card_description,
                            threadKey=thread_key,
                            webhookUrl=webhook_url,
                            userEmail=user_google_email,
                            httpStatus=200,
                            validationPassed=True,
                            message="Card message sent successfully via webhook",
                        )
                elif response.status_code == 429:
                    # Handle rate limiting with helpful message
                    logger.warning(
                        "⚠️ Rate limited by Google Chat API. This indicates successful card formatting but too many requests."
                    )
                    return SendDynamicCardResponse(
                        success=False,
                        spaceId=space_id,
                        deliveryMethod="webhook",
                        cardType=best_match.get("type", "unknown"),
                        componentInfo=component_info,
                        cardDescription=card_description,
                        threadKey=thread_key,
                        webhookUrl=webhook_url,
                        userEmail=user_google_email,
                        httpStatus=429,
                        validationPassed=True,
                        message="Rate limited (429) - Card format is correct but hitting quota limits",
                        error="Too many requests - reduce request frequency",
                    )
                else:
                    error_details = {
                        "status": response.status_code,
                        "headers": dict(response.headers),
                        "body": response.text,
                        "message_sent": message_body,
                        "card_validation_issues": (
                            content_issues if not is_valid_content else []
                        ),
                    }
                    logger.error(
                        f"❌ Failed to send card via webhook: {json.dumps(error_details, indent=2)}"
                    )
                    return SendDynamicCardResponse(
                        success=False,
                        spaceId=space_id,
                        deliveryMethod="webhook",
                        cardType=best_match.get("type", "unknown"),
                        componentInfo=component_info,
                        cardDescription=card_description,
                        threadKey=thread_key,
                        webhookUrl=webhook_url,
                        userEmail=user_google_email,
                        httpStatus=response.status_code,
                        validationPassed=True,
                        message=f"Webhook delivery failed with status {response.status_code}",
                        error=response.text,
                    )
            else:
                # Send via API
                chat_service = await _get_chat_service_with_fallback(user_google_email)

                if not chat_service:
                    return SendDynamicCardResponse(
                        success=False,
                        spaceId=space_id,
                        deliveryMethod="api",
                        cardType=best_match.get("type", "unknown"),
                        cardDescription=card_description,
                        userEmail=user_google_email,
                        validationPassed=True,
                        message=f"Failed to create Google Chat service for {user_google_email}",
                        error="Chat service authentication failed",
                    )

                # Add thread key if provided
                request_params = {"parent": space_id, "body": message_body}
                _process_thread_key_for_request(request_params, thread_key)

                message = await asyncio.to_thread(
                    chat_service.spaces().messages().create(**request_params).execute
                )

                message_name = message.get("name", "")
                create_time = message.get("createTime", "")

                # Build component info for response
                component_info = ComponentSearchInfo(
                    componentFound=bool(best_match.get("name")),
                    componentName=best_match.get("name"),
                    componentPath=best_match.get("path"),
                    componentType=best_match.get("type"),
                    searchScore=best_match.get("score"),
                    extractedFromModule=best_match.get("extracted_from_module"),
                )

                return SendDynamicCardResponse(
                    success=True,
                    messageId=message_name,
                    spaceId=space_id,
                    deliveryMethod="api",
                    cardType=best_match.get("type", "unknown"),
                    componentInfo=component_info,
                    cardDescription=card_description,
                    threadKey=thread_key,
                    createTime=create_time,
                    userEmail=user_google_email,
                    validationPassed=True,
                    message=f"Card message sent successfully to space '{space_id}'",
                )

        except Exception as e:
            logger.error(f"❌ Error sending dynamic card: {e}", exc_info=True)
            return SendDynamicCardResponse(
                success=False,
                spaceId=space_id,
                deliveryMethod="webhook" if webhook_url else "api",
                cardType="unknown",
                cardDescription=card_description,
                threadKey=thread_key,
                webhookUrl=webhook_url,
                userEmail=user_google_email,
                validationPassed=False,
                message="Error sending dynamic card",
                error=str(e),
            )
