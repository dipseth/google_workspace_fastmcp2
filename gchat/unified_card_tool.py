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
import time

# Import MCP-related components
from fastmcp import FastMCP
from typing_extensions import Annotated, Any, Dict, List, Optional, Tuple

from pydantic import Field

# Template middleware integration handled at server level - no imports needed here
# Import ModuleWrapper
from adapters.module_wrapper import ModuleWrapper
from auth.context import get_injected_service

# Import auth helpers
from auth.service_helpers import get_service, request_service

# Import TypedDict response types for structured responses
from config.enhanced_logging import setup_logger

# NLP parser commented out - SmartCardBuilder handles all parsing and rendering
# SmartCardBuilder: NL description → Qdrant search → ModuleWrapper → Render
# from .nlp_card_parser import parse_enhanced_natural_language_description

# Import SmartCardBuilder for component-based card creation
from .smart_card_builder import get_smart_card_builder

# Import structured response types
from .unified_card_types import (
    ComponentSearchInfo,
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
    from card_framework.v2 import Message

    CARD_FRAMEWORK_AVAILABLE = True

except ImportError:
    CARD_FRAMEWORK_AVAILABLE = False
    logger.warning("Card Framework v2 not available. Falling back to REST API format.")

    Message = None  # Placeholder for when Card Framework is not available


# Global variables for module wrappers and caches
_card_framework_wrapper = None
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
    """
    Get the Qdrant client from centralized singleton.

    Uses config.qdrant_client.get_qdrant_client() for the actual client,
    then ensures the card_templates collection exists.
    """
    global _qdrant_client

    if _qdrant_client is None:
        try:
            # Use centralized Qdrant client singleton
            from config.qdrant_client import get_qdrant_client as get_central_client

            _qdrant_client = get_central_client()

            if _qdrant_client is None:
                logger.warning("⚠️ Qdrant client not available - template storage disabled")
                return None

            # Ensure card templates collection exists
            from qdrant_client.models import Distance, VectorParams

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

        except ImportError:
            logger.warning("⚠️ Qdrant client not available - template storage disabled")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to get Qdrant client: {e}", exc_info=True)
            return None

    return _qdrant_client


def _reset_card_framework_wrapper():
    """Reset the card framework wrapper to force reinitialization."""
    global _card_framework_wrapper
    _card_framework_wrapper = None
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


def _build_card_with_smart_builder(
    card_description: str, card_params: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build a card using SmartCardBuilder.

    SmartCardBuilder handles the full flow:
    1. Parses natural language description into sections/items
    2. Uses Qdrant vector search to find components
    3. Loads components via ModuleWrapper
    4. Infers layout from description (columns, image positioning)
    5. Renders using component .render() methods

    Args:
        card_description: Natural language description (parsed by SmartCardBuilder)
        card_params: Parameters with title, subtitle, image_url, text, buttons overrides

    Returns:
        Card structure in cardsV2 format ready for Google Chat API
    """
    import time

    builder = get_smart_card_builder()

    # Extract all params - pass everything to SmartCardBuilder
    title = card_params.get("title")
    subtitle = card_params.get("subtitle")
    image_url = card_params.get("image_url")
    text = card_params.get("text")
    buttons = card_params.get("buttons")

    logger.info(f"🔨 SmartCardBuilder parsing description: {card_description[:80]}...")

    # Build card using SmartCardBuilder - pass text so it can be used in layout inference
    card_dict = builder.build_card_from_description(
        description=card_description,
        title=title,
        subtitle=subtitle,
        image_url=image_url,
        text=text,  # Pass text for layout inference (columns, etc.)
        buttons=buttons,  # Pass buttons too
    )

    if not card_dict:
        logger.warning("⚠️ SmartCardBuilder returned empty card")
        return {}

    # Wrap in cardsV2 format
    card_id = f"smart_card_{int(time.time())}_{hash(str(card_params)) % 10000}"

    return {
        "cardId": card_id,
        "card": card_dict,
    }


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
        # ENHANCEMENT: Add image_url as widget in first section if provided
        if "image_url" in params and sections:
            image_widget = {"image": {"imageUrl": params["image_url"]}}
            if "image_alt_text" in params:
                image_widget["image"]["altText"] = params["image_alt_text"]
            # Insert image at the beginning of first section's widgets
            if sections[0].get("widgets"):
                sections[0]["widgets"].insert(0, image_widget)
            else:
                sections[0]["widgets"] = [image_widget]
            logger.info(f"✅ Added image widget to first section: {params['image_url']}")
    elif isinstance(params.get("sections"), list) and params.get("sections"):
        card_dict["sections"] = params["sections"]
        logger.info(
            f"✅ Using sections from params: {len(params['sections'])} section(s)"
        )
        # ENHANCEMENT: Add image_url as widget in first section if provided
        if "image_url" in params and card_dict["sections"]:
            image_widget = {"image": {"imageUrl": params["image_url"]}}
            if "image_alt_text" in params:
                image_widget["image"]["altText"] = params["image_alt_text"]
            # Insert image at the beginning of first section's widgets
            if card_dict["sections"][0].get("widgets"):
                card_dict["sections"][0]["widgets"].insert(0, image_widget)
            else:
                card_dict["sections"][0]["widgets"] = [image_widget]
            logger.info(f"✅ Added image widget to first section: {params['image_url']}")
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
        description="Send any type of card to Google Chat using natural language description with NLP extraction",
        tags={"chat", "card", "dynamic", "google", "unified", "nlp"},
        annotations={
            "title": "Send Dynamic Card with NLP",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
            "examples": [
                {
                    "description": "Simple card",
                    "card_description": "simple notification",
                    "card_params": {"title": "Alert", "text": "System update complete"},
                },
                {
                    "description": "Multi-section card (recommended pattern)",
                    "card_description": "First section titled 'Deployments' showing Frontend at https://app.example.com. Second section titled 'Status' showing All systems operational.",
                    "card_params": {"title": "Dashboard"},
                },
            ],
        },
    )
    async def send_dynamic_card(
        user_google_email: Annotated[
            str,
            Field(description="The user's Google email address for authentication and API access"),
        ],
        space_id: Annotated[
            str,
            Field(description="The Google Chat space ID (e.g., 'spaces/AAAA1234') to send the card to"),
        ],
        card_description: Annotated[
            str,
            Field(
                description="Natural language description of the card. Use pattern: 'First section titled \"NAME\" showing CONTENT. Second section titled \"NAME\" showing CONTENT.' URLs become clickable buttons automatically."
            ),
        ],
        card_params: Annotated[
            Optional[Dict[str, Any]],
            Field(
                default=None,
                description="Optional dict of explicit parameters (title, subtitle, text, buttons) that override NLP-extracted values",
            ),
        ] = None,
        thread_key: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Optional thread key for replying to existing message threads",
            ),
        ] = None,
        webhook_url: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Optional webhook URL for direct delivery (bypasses API auth, useful for incoming webhooks)",
            ),
        ] = None,
        use_colbert: Annotated[
            bool,
            Field(
                default=True,
                description="Use ColBERT multi-vector embeddings for semantic search. Provides more accurate matching.",
            ),
        ] = True,
    ) -> SendDynamicCardResponse:
        """
        Send any type of card to Google Chat using natural language description.

        RECOMMENDED PATTERN for multi-section cards:
            First section titled "NAME" showing CONTENT.
            Second section titled "NAME" showing CONTENT.

        AUTOMATIC FEATURES:
        - URLs become clickable "Open" buttons
        - "warning/stale" keywords get warning icons
        - "@username" and "commit HASH" get appropriate icons
        - "X and Y" splits into separate widgets

        Returns:
            SendDynamicCardResponse with delivery status and component info
        """
        try:
            logger.info(f"🔍 Finding card component for: {card_description}")
            logger.info(f"🤖 ColBERT mode: {use_colbert}")

            # Default parameters if not provided
            if card_params is None:
                card_params = {}

            # =================================================================
            # NLP PARSING COMMENTED OUT - SmartCardBuilder has its own inference
            # SmartCardBuilder.infer_content_type() detects prices, IDs, URLs, etc.
            # SmartCardBuilder.infer_layout() detects columns, image positioning
            # If we need NLP parsing for multi-section cards, uncomment below.
            # =================================================================
            # try:
            #     logger.info(
            #         f"🧠 Parsing natural language description: '{card_description}'"
            #     )
            #     nlp_extracted_params = parse_enhanced_natural_language_description(
            #         card_description
            #     )
            #
            #     if nlp_extracted_params:
            #         logger.info(
            #             f"✅ NLP extracted parameters: {list(nlp_extracted_params.keys())}"
            #         )
            #
            #         merged_params: Dict[str, Any] = {}
            #         merged_params.update(nlp_extracted_params)
            #         merged_params.update(card_params)
            #
            #         if isinstance(merged_params.get("sections"), list):
            #             logger.info(
            #                 f"✅ NLP produced sections: {len(merged_params['sections'])} section(s)"
            #             )
            #
            #         card_params = merged_params
            #     else:
            #         logger.info("📝 No parameters extracted from NLP")
            #
            # except Exception as nlp_error:
            #     logger.warning(f"⚠️ NLP parsing failed: {nlp_error}")
            # =================================================================

            # Initialize default best_match to prevent UnboundLocalError
            best_match = {"type": "fallback", "name": "simple_fallback", "score": 0.0}
            google_format_card = None

            # =================================================================
            # SMART CARD BUILDER - PRIMARY PATH
            # SmartCardBuilder is now the primary card building path because it:
            # 1. Searches Qdrant vector DB for relevant components (ColBERT)
            # 2. Loads components via ModuleWrapper.get_component_by_path()
            # 3. Has smart content inference (prices, IDs, dates, URLs)
            # 4. Has layout inference (columns, image positioning)
            # 5. Renders via component .render() methods
            # =================================================================
            logger.info("🔨 Using SmartCardBuilder as primary card building path")
            try:
                google_format_card = _build_card_with_smart_builder(
                    card_description, card_params
                )
                if google_format_card:
                    best_match = {
                        "type": "smart_builder",
                        "name": "SmartCardBuilder",
                        "score": 1.0,
                    }
                    logger.info("✅ SmartCardBuilder created card successfully")
            except Exception as smart_err:
                logger.warning(
                    f"⚠️ SmartCardBuilder failed, falling back to simple card: {smart_err}",
                    exc_info=True
                )
                google_format_card = None

            # =================================================================
            # SIMPLE FALLBACK - Only used if SmartCardBuilder failed
            # The legacy ColBERT/standard component search code has been removed
            # because SmartCardBuilder now handles:
            # - Qdrant vector search for components
            # - ModuleWrapper.get_component_by_path() for loading
            # - Smart content inference (prices, IDs, URLs, dates)
            # - Layout inference (columns, image positioning)
            # =================================================================
            if not google_format_card:
                logger.warning("⚠️ SmartCardBuilder didn't create a card, using simple fallback")
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
                logger.info(f"  - Card source: {best_match.get('type', 'unknown')}")
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
