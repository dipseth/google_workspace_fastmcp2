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
import json

# Import MCP-related components
from fastmcp import FastMCP
from fastmcp.dependencies import Progress
from pydantic import Field
from typing_extensions import Annotated, Any, Dict, Optional

# Template middleware integration handled at server level - no imports needed here
from auth.context import get_injected_service

# Import auth helpers
from auth.service_helpers import get_service, request_service

# Import TypedDict response types for structured responses
from config.enhanced_logging import setup_logger

# Import settings for default webhook configuration
from config.settings import settings

# NLP parser commented out - SmartCardBuilder handles all parsing and rendering
# SmartCardBuilder: NL description → Qdrant search → ModuleWrapper → Render
# from .nlp_card_parser import parse_enhanced_natural_language_description
# Import SmartCardBuilder for component-based card creation
from .card_builder import (
    COMPONENT_PARAMS,
    get_smart_card_builder,
    suggest_dsl_for_params,
)

# Import structured response types
from .card_types import (
    ComponentSearchInfo,
    DSLValidationInfo,
    ExpectedParamsInfo,
    InputMappingInfo,
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


def _generate_alternative_dsl(
    rendered_dsl: Optional[str],
    component_paths: Optional[list] = None,
    max_alternatives: int = 3,
) -> Optional[list]:
    """
    Generate alternative valid DSL patterns based on rendered card structure.

    Uses the wrapper's variation capabilities to suggest similar but different
    card structures that would also be valid.

    Args:
        rendered_dsl: The DSL notation of the rendered card
        component_paths: List of component paths used in the card
        max_alternatives: Maximum number of alternatives to generate

    Returns:
        List of alternative DSL strings, or None if generation fails
    """
    if not rendered_dsl:
        return None

    try:
        from gchat.card_framework_wrapper import get_card_framework_wrapper

        wrapper = get_card_framework_wrapper()
        symbols = wrapper.symbol_mapping

        # Extract components from rendered DSL (first section before +)
        base_dsl = rendered_dsl.split(" + ")[0].strip()

        # Common alternative patterns based on what's in the DSL
        alternatives = []

        # Get symbols for common components
        section_sym = symbols.get("Section", "§")
        text_sym = symbols.get("DecoratedText", "δ")
        para_sym = symbols.get("TextParagraph", "ʈ")
        btn_list_sym = symbols.get("ButtonList", "Ƀ")
        btn_sym = symbols.get("Button", "ᵬ")
        chip_list_sym = symbols.get("ChipList", "ȼ")
        chip_sym = symbols.get("Chip", "ℂ")
        img_sym = symbols.get("Image", "Ɨ")
        grid_sym = symbols.get("Grid", "ℊ")
        grid_item_sym = symbols.get("GridItem", "ǵ")
        divider_sym = symbols.get("Divider", "Đ")

        # Generate variations based on common patterns
        if text_sym in base_dsl:
            # Text card variations
            alternatives.append(f"{section_sym}[{text_sym}, {divider_sym}]")
            alternatives.append(f"{section_sym}[{para_sym}]")
            alternatives.append(f"{section_sym}[{text_sym}, {btn_list_sym}[{btn_sym}]]")

        if btn_list_sym in base_dsl or btn_sym in base_dsl:
            # Button variations
            alternatives.append(
                f"{section_sym}[{text_sym}, {btn_list_sym}[{btn_sym}×3]]"
            )
            alternatives.append(f"{section_sym}[{chip_list_sym}[{chip_sym}×2]]")

        if chip_list_sym in base_dsl or chip_sym in base_dsl:
            # Chip variations
            alternatives.append(
                f"{section_sym}[{text_sym}, {chip_list_sym}[{chip_sym}×3]]"
            )
            alternatives.append(f"{section_sym}[{btn_list_sym}[{btn_sym}×2]]")

        if img_sym in base_dsl:
            # Image variations
            alternatives.append(f"{section_sym}[{img_sym}, {text_sym}]")
            alternatives.append(f"{section_sym}[{grid_sym}[{grid_item_sym}×4]]")

        # Add a grid alternative if not already present
        if grid_sym not in base_dsl:
            alternatives.append(f"{section_sym}[{grid_sym}[{grid_item_sym}×4]]")

        # Filter out duplicates and the original, limit results
        seen = {base_dsl}
        unique = []
        for alt in alternatives:
            if alt not in seen:
                seen.add(alt)
                unique.append(alt)
                if len(unique) >= max_alternatives:
                    break

        return unique if unique else None

    except Exception as e:
        logger.debug(f"Failed to generate alternative DSL: {e}")
        return None


# Global variables for module wrappers and caches
_card_framework_wrapper = None
_qdrant_client = None
_card_templates_collection = "card_templates"


async def _get_chat_service_with_fallback(user_google_email: str):
    """
    Get Google Chat service with fallback to direct creation if middleware injection fails.

    Args:
        user_google_email: User's Google email address

    Returns:
        Authenticated Google Chat service instance or None if unavailable
    """
    # First, try middleware injection
    service_key = await request_service("chat")

    try:
        # Try to get the injected service from middleware
        chat_service = await get_injected_service(service_key)
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
                logger.warning(
                    "⚠️ Qdrant client not available - template storage disabled"
                )
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
    """Reset the card framework wrapper singleton to force reinitialization."""
    global _card_framework_wrapper
    from gchat.card_framework_wrapper import reset_wrapper

    _card_framework_wrapper = None
    reset_wrapper()
    logger.info("🔄 Card framework wrapper singleton reset")


def _initialize_card_framework_wrapper(force_reset: bool = False):
    """
    Initialize the ModuleWrapper for the card_framework module.

    Uses the singleton from gchat.card_framework_wrapper for consistent
    configuration across all gchat modules.
    """
    global _card_framework_wrapper

    if not CARD_FRAMEWORK_AVAILABLE:
        logger.warning("❌ Card Framework not available - cannot initialize wrapper")
        return None

    if force_reset:
        logger.info("🔄 Force reset requested - clearing singleton")
        _reset_card_framework_wrapper()

    if _card_framework_wrapper is None:
        try:
            from gchat.card_framework_wrapper import get_card_framework_wrapper

            _card_framework_wrapper = get_card_framework_wrapper(
                force_reinitialize=force_reset
            )

            # Validate component count
            component_count = (
                len(_card_framework_wrapper.components)
                if _card_framework_wrapper.components
                else 0
            )

            if component_count == 0:
                logger.error("❌ CRITICAL: ModuleWrapper has ZERO components indexed!")
            else:
                logger.info(f"✅ Singleton wrapper ready: {component_count} components")

            # Initialize Qdrant client for template storage
            qdrant_client = _get_qdrant_client()
            if qdrant_client:
                logger.debug("✅ Qdrant client initialized for template storage")

        except ImportError as import_error:
            logger.error(f"❌ Could not import card_framework module: {import_error}")
            return None
        except Exception as e:
            logger.error(
                f"❌ Failed to get ModuleWrapper singleton: {e}", exc_info=True
            )
            return None
    else:
        logger.debug(
            f"♻️ Using existing singleton with {len(_card_framework_wrapper.components) if _card_framework_wrapper.components else 0} components"
        )

    return _card_framework_wrapper


def _initialize_colbert_wrapper():
    """
    Initialize SmartCardBuilder for card building.

    This is called on server startup when COLBERT_EMBEDDING_DEV=true.
    SmartCardBuilderV2 queries Qdrant directly (no local ColBERT embedder).
    """
    try:
        builder = get_smart_card_builder()
        # Force initialization (lazy init is no-op, but keeps compatibility)
        builder.initialize()
        logger.info("✅ SmartCardBuilder initialized")
    except Exception as e:
        logger.warning(f"⚠️ SmartCardBuilder initialization failed: {e}")
        # Non-fatal - will initialize on-demand when needed


def _get_dsl_field_description() -> str:
    """
    Get auto-generated DSL field description from the symbol table.

    This pulls the description dynamically from the card_framework_wrapper
    so it stays in sync with the actual symbol mappings.
    """
    try:
        from gchat.card_framework_wrapper import get_dsl_field_description

        return get_dsl_field_description()
    except Exception:
        # Fallback if wrapper not available - no hardcoded symbols
        return (
            "DSL structure using symbols generated by ModuleWrapper. "
            "Symbols are auto-generated from component names. "
            "Use 'symbol[children]' syntax for nesting, 'symbol×N' for repetition."
        )


def setup_card_tools(mcp: FastMCP) -> None:
    """
    Setup the card tools for MCP.

    Args:
        mcp: The FastMCP server instance
    """
    logger.info("Setting up card tools")

    # Initialize card framework wrapper
    _initialize_card_framework_wrapper()

    # Generate DSL documentation dynamically after wrapper is initialized
    # This ensures symbol mappings are included in tool documentation
    from gchat.card_framework_wrapper import (
        get_dsl_documentation,
        get_gchat_symbols,
        get_tool_examples,
    )

    dsl_field_desc = _get_dsl_field_description()
    dsl_full_doc = get_dsl_documentation(include_examples=True, include_hierarchy=True)
    tool_examples = get_tool_examples(max_examples=5)
    symbols = get_gchat_symbols()

    # Build dynamic tool description with actual symbols from DAG
    section_sym = symbols.get("Section", "§")
    dtext_sym = symbols.get("DecoratedText", "δ")
    btnlist_sym = symbols.get("ButtonList", "Ƀ")
    btn_sym = symbols.get("Button", "ᵬ")
    grid_sym = symbols.get("Grid", "ℊ")
    gitem_sym = symbols.get("GridItem", "ǵ")

    tool_description = (
        "Send cards to Google Chat using DSL notation for precise structure control. "
        "REQUIRED: Use DSL symbols in card_description to define card structure. "
        f"Common patterns: {section_sym}[{dtext_sym}] = text card, "
        f"{section_sym}[{dtext_sym}, {btnlist_sym}[{btn_sym}×2]] = text + 2 buttons, "
        f"{section_sym}[{grid_sym}[{gitem_sym}×4]] = grid with 4 items. "
        f"{dsl_field_desc}"
    )

    # Build dynamic field help - DSL is primary, NL is fallback
    card_description_help = (
        "IMPORTANT: Start with DSL symbols to define card structure. "
        "Without DSL, cards render as simple text only. "
        f"DSL Examples: {section_sym}[{dtext_sym}] = Section with DecoratedText, "
        f"{section_sym}[{dtext_sym}, {btnlist_sym}[{btn_sym}×2]] = text + 2 buttons, "
        f"{section_sym}[{dtext_sym}×3] = 3 text items, "
        f"{section_sym}[{grid_sym}[{gitem_sym}×4]] = grid with 4 items. "
        "Provide content in card_params: title, subtitle, text, buttons=[{text, url}]. "
        "Jinja styling in text: {{ 'Online' | success_text }}, {{ text | color('#hex') }}. "
        f"{dsl_field_desc}"
    )

    @mcp.tool(
        name="send_dynamic_card",
        description=tool_description,
        tags={"chat", "card", "dynamic", "google"},
        task=True,  # Enable background task execution for long-running card operations
        annotations={
            "title": "Send Dynamic Card with NLP",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
            "dsl_documentation": dsl_full_doc,  # Full DSL docs in annotations
            "examples": tool_examples,  # Dynamically generated from DAG symbols
        },
    )
    async def send_dynamic_card(
        user_google_email: Annotated[
            str,
            Field(description="Google email for authentication"),
        ],
        card_description: Annotated[
            str,
            Field(description=card_description_help),
        ],
        space_id: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Chat space ID (e.g., 'spaces/AAAA1234'). Optional when using webhook (most common). Required only for API delivery.",
            ),
        ] = None,
        card_params: Annotated[
            Optional[Dict[str, Any]],
            Field(
                default=None,
                description="Explicit overrides: title, subtitle, text, buttons, images. "
                "The 'text' field supports Jinja filters ({{ 'text' | success_text }}) "
                'and raw HTML (<font color="#hex">text</font>). '
                "Message-level fields: 'message_text' (plain text above card), "
                "'fallback_text' (notification text), "
                "'accessory_widgets' (buttons outside card: [{buttonList: {buttons: [{text, url}]}}]).",
            ),
        ] = None,
        thread_key: Annotated[
            Optional[str],
            Field(default=None, description="Thread key for replies"),
        ] = None,
        webhook_url: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Webhook URL. Defaults to MCP_CHAT_WEBHOOK env var if not provided.",
            ),
        ] = None,
        progress: Progress = Progress(),  # FastMCP background task progress reporting
    ) -> SendDynamicCardResponse:
        """
        Send a card to Google Chat using DSL notation for structure control.

        IMPORTANT: Use DSL symbols in card_description to define card structure.
        Without DSL, cards render as simple text only.

        DSL Syntax:
        - §[widgets] = Section containing widgets
        - δ = DecoratedText (text display)
        - Ƀ[ᵬ×N] = ButtonList with N buttons
        - ℊ[ǵ×N] = Grid with N items
        - ×N = repeat N times

        Common Patterns:
        - §[δ] = Simple text card
        - §[δ, Ƀ[ᵬ×2]] = Text + 2 buttons
        - §[δ×3] = 3 text items
        - §[ℊ[ǵ×4]] = Grid with 4 items
        - §[δ, Ƀ[ᵬ×2], δ] = Text, buttons, more text

        Content (in card_params):
        - title: Card header title
        - subtitle: Card header subtitle
        - text: Main text content
        - buttons: [{text, url}, ...] for ButtonList

        Jinja Styling (in card_params.text):
        - {{ 'text' | success_text }} = green
        - {{ 'text' | error_text }} = red
        - {{ 'text' | warning_text }} = yellow
        - {{ 'text' | color('#hex') }} = custom color

        Examples:
            card_description="§[δ]", card_params={"title": "Alert", "text": "Done"}
            card_description="§[δ, Ƀ[ᵬ×2]]", card_params={"title": "Actions", "buttons": [...]}
        """
        try:
            logger.info(f"🔍 Finding card component for: {card_description}")

            # Report progress for background task tracking
            await progress.set_message("Initializing card builder...")

            # Use default webhook from settings if not provided
            if not webhook_url and settings.mcp_chat_webhook:
                webhook_url = settings.mcp_chat_webhook
                logger.info("📡 Using default webhook from MCP_CHAT_WEBHOOK setting")

            # Validate: space_id is required for API mode (when no webhook)
            if not webhook_url and not space_id:
                return SendDynamicCardResponse(
                    success=False,
                    deliveryMethod="api",
                    cardType="unknown",
                    cardDescription=card_description,
                    userEmail=user_google_email,
                    validationPassed=False,
                    message="space_id is required when no webhook_url is provided (API mode)",
                    error="Missing required parameter: space_id",
                )

            # Default parameters if not provided
            if card_params is None:
                card_params = {}

            # =================================================================
            # EXTRACT MESSAGE-LEVEL PARAMS FROM card_params (early extraction)
            # These need to be extracted before webhook URL is built
            # =================================================================
            if not thread_key:
                thread_key = card_params.get("thread_key") or card_params.get("thread")
                if thread_key:
                    logger.info(
                        f"🧵 Extracted thread_key from card_params: {thread_key}"
                    )

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
            # DSL VALIDATION AND SUGGESTIONS
            # Extract and validate DSL from description, provide expected params
            # and suggest DSL when params provided but no DSL in description
            # =================================================================
            from gchat.card_framework_wrapper import (
                extract_dsl_from_description,
                get_dsl_parser,
                get_gchat_symbols,
            )

            dsl_validation_result: Optional[DSLValidationInfo] = None
            expected_params_info: Optional[ExpectedParamsInfo] = None
            suggested_dsl: Optional[str] = None
            input_mapping_info: Optional[InputMappingInfo] = None

            # Extract DSL from description if present
            dsl_string = (
                extract_dsl_from_description(card_description)
                if card_description
                else None
            )

            if dsl_string:
                await progress.set_message("Validating DSL structure...")
                try:
                    parser = get_dsl_parser()
                    parsed = parser.parse(dsl_string)

                    # Build expanded notation from root nodes
                    expanded = None
                    if parsed.root_nodes:
                        expanded = ", ".join(
                            node.to_expanded_notation() for node in parsed.root_nodes
                        )

                    dsl_validation_result = DSLValidationInfo(
                        is_valid=parsed.is_valid,
                        dsl_input=dsl_string,
                        expanded_notation=expanded,
                        component_counts=parsed.component_counts,
                        issues=parsed.issues,
                        suggestions=parsed.suggestions,
                    )

                    # Get expected params for detected components
                    if parsed.component_counts:
                        expected_params_info = ExpectedParamsInfo(
                            by_component={
                                comp: COMPONENT_PARAMS.get(comp, {})
                                for comp in parsed.component_counts.keys()
                                if comp in COMPONENT_PARAMS
                            },
                            common_params={
                                "title": "Card header title",
                                "subtitle": "Card header subtitle",
                                "buttons": "List of [{text, url}] for Button components",
                            },
                        )

                    logger.info(
                        f"🔍 DSL validation: valid={parsed.is_valid}, components={parsed.component_counts}"
                    )
                except Exception as dsl_err:
                    logger.warning(f"⚠️ DSL validation failed: {dsl_err}")

            elif card_params:
                # Suggest DSL when no DSL provided but params exist
                try:
                    symbols = get_gchat_symbols()
                    suggested_dsl = suggest_dsl_for_params(card_params, symbols)
                    if suggested_dsl:
                        logger.info(f"💡 Suggested DSL for params: {suggested_dsl}")
                except Exception as suggest_err:
                    logger.warning(f"⚠️ DSL suggestion failed: {suggest_err}")

            # =================================================================
            # SMART CARD BUILDER - PRIMARY PATH (Natural Language)
            # SmartCardBuilder is the primary card building path for NL because it:
            # 1. Searches Qdrant vector DB for relevant components (ColBERT)
            # 2. Loads components via ModuleWrapper.get_component_by_path()
            # 3. Has smart content inference (prices, IDs, dates, URLs)
            # 4. Has layout inference (columns, image positioning)
            # 5. Renders via component .render() methods
            # =================================================================
            # Track DSL detection for response
            dsl_detected: Optional[str] = None
            jinja_template_applied: bool = False

            if not google_format_card:
                logger.info("🔨 Using SmartCardBuilder as primary card building path")
                await progress.set_message(
                    "Querying Qdrant and building card structure..."
                )
                try:
                    # Use SmartCardBuilder.build() directly with unpacked params
                    import time

                    builder = get_smart_card_builder()

                    # Extract params
                    title = card_params.get("title") if card_params else None
                    subtitle = card_params.get("subtitle") if card_params else None
                    image_url = card_params.get("image_url") if card_params else None
                    text = card_params.get("text") if card_params else None
                    buttons = card_params.get("buttons") if card_params else None
                    chips = card_params.get("chips") if card_params else None
                    grid = card_params.get("grid") if card_params else None
                    images = card_params.get("images") if card_params else None
                    image_titles = (
                        card_params.get("image_titles") if card_params else None
                    )
                    items = card_params.get("items") if card_params else None
                    cards = (
                        (card_params.get("cards") or card_params.get("carousel_cards"))
                        if card_params
                        else None
                    )

                    # Convert grid images to items for DSL building
                    grid_items = None
                    if images:
                        logger.info(f"🔲 Grid images: {len(images)}")
                        grid_items = [
                            {
                                "title": (
                                    image_titles[i]
                                    if image_titles and i < len(image_titles)
                                    else f"Item {i + 1}"
                                ),
                                "image_url": img_url,
                            }
                            for i, img_url in enumerate(images)
                        ]
                    elif grid and grid.get("items"):
                        logger.info(f"🔲 Grid items: {len(grid.get('items', []))}")
                        grid_items = grid["items"]

                    if cards:
                        logger.info(f"🎠 Carousel: {len(cards)} card(s)")

                    # Build card via unified DSL/DAG pipeline
                    card_dict = builder.build(
                        description=card_description,
                        title=title,
                        subtitle=subtitle,
                        buttons=buttons,
                        chips=chips,
                        image_url=image_url,
                        text=text,
                        items=grid_items or items,
                        cards=cards,
                    )

                    # Wrap in cardsV2 format for Google Chat API
                    if card_dict:
                        card_id = f"smart_card_{int(time.time())}_{hash(str(card_params)) % 10000}"
                        google_format_card = {
                            "cardId": card_id,
                            "card": card_dict,
                        }
                    if google_format_card:
                        best_match = {
                            "type": "smart_builder",
                            "name": "SmartCardBuilder",
                            "score": 1.0,
                        }
                        logger.info("✅ SmartCardBuilder created card successfully")
                        await progress.set_message(
                            "Card structure built, preparing message..."
                        )

                        # Extract DSL structure and Jinja template status from card
                        inner_card = google_format_card.get("card", {})
                        if isinstance(inner_card, dict):
                            dsl_detected = inner_card.get("_dsl_structure")
                            jinja_template_applied = inner_card.get(
                                "_jinja_applied", False
                            )
                            if dsl_detected:
                                logger.info(
                                    f"🔣 DSL structure detected: {dsl_detected}"
                                )
                            if jinja_template_applied:
                                logger.info("🎨 Jinja template was applied")
                except Exception as smart_err:
                    logger.warning(
                        f"⚠️ SmartCardBuilder failed: {smart_err}",
                        exc_info=True,
                    )
                    google_format_card = None

            # SmartCardBuilder always returns a valid card (has internal fallbacks)
            # If we still have None, something is seriously wrong

            if not google_format_card:
                return SendDynamicCardResponse(
                    success=False,
                    spaceId=space_id,
                    deliveryMethod="webhook" if webhook_url else "api",
                    cardType=best_match.get("type", "unknown"),
                    cardDescription=card_description,
                    userEmail=user_google_email,
                    validationPassed=False,
                    dslDetected=dsl_detected,
                    jinjaTemplateApplied=jinja_template_applied,
                    message="Failed to create card structure",
                    error="Card structure generation returned None",
                )

            # Create message payload
            message_obj = Message()

            # =================================================================
            # MESSAGE-LEVEL PARAMS FROM card_params
            # These can be passed in card_params as an alternative to tool params
            # =================================================================

            # Extract thread_key from card_params if not provided as tool param
            if not thread_key:
                thread_key = card_params.get("thread_key") or card_params.get("thread")
                if thread_key:
                    logger.debug(
                        f"🧵 Extracted thread_key from card_params: {thread_key}"
                    )

            # Set fallback_text if provided in card_params
            # This shows in notifications and is used for accessibility
            fallback_text = card_params.get("fallback_text") or card_params.get(
                "notification_text"
            )
            if fallback_text:
                message_obj.fallback_text = fallback_text
                logger.debug(
                    f"📱 Set fallback_text for notifications: {fallback_text[:50]}..."
                )

            # Set plain text content (appears above/below card)
            text_content = card_params.get("text_content") or card_params.get(
                "message_text"
            )
            if text_content:
                message_obj.text = text_content
                logger.debug(f"📝 Set message text: {text_content[:50]}...")

            # Set quoted message metadata for reply quotes
            quoted_message = card_params.get(
                "quoted_message_metadata"
            ) or card_params.get("quote")
            if quoted_message:
                if isinstance(quoted_message, dict):
                    # Expect {"name": "spaces/X/messages/Y", "lastUpdateTime": "..."}
                    from card_framework.v2.message import QuotedMessageMetadata

                    message_obj.quoted_message_metadata = QuotedMessageMetadata(
                        name=quoted_message.get("name"),
                        last_update_time=quoted_message.get("last_update_time")
                        or quoted_message.get("lastUpdateTime"),
                    )
                    logger.debug(f"💬 Set quoted message: {quoted_message.get('name')}")

            # Set annotations (rich text annotations like user mentions)
            annotations = card_params.get("annotations")
            if annotations and isinstance(annotations, list):
                message_obj.annotations = annotations
                logger.debug(f"🏷️ Set {len(annotations)} annotations")

            # Add card to message - handle both single card object and wrapped format
            if isinstance(google_format_card, dict) and "cardsV2" in google_format_card:
                # Old format with wrapper - extract cards
                for card in google_format_card["cardsV2"]:
                    message_obj.cards_v2.append(card)
            else:
                # New format - single card object
                message_obj.cards_v2.append(google_format_card)

            # Add accessory_widgets if provided (buttons at bottom of message, outside card)
            # These are useful for feedback buttons or quick actions
            accessory_widgets = card_params.get("accessory_widgets")
            if accessory_widgets:
                # Use wrapper to get classes (avoid direct imports)
                # Use full paths for v2 classes to avoid v1 conflicts
                from gchat.card_framework_wrapper import get_card_framework_wrapper

                wrapper = get_card_framework_wrapper()
                AccessoryWidget = wrapper.get_cached_class("AccessoryWidget")
                ButtonList = wrapper.get_cached_class("ButtonList")
                Button = wrapper.get_cached_class("Button")
                # OnClick and OpenLink need full paths to get v2 versions
                OnClick = wrapper.get_component_by_path(
                    "card_framework.v2.widgets.on_click.OnClick"
                )
                OpenLink = wrapper.get_component_by_path(
                    "card_framework.v2.widgets.open_link.OpenLink"
                )

                if AccessoryWidget and ButtonList and Button:
                    for aw in accessory_widgets:
                        if isinstance(aw, dict):
                            # Build AccessoryWidget from dict
                            # AccessoryWidget only supports button_list per API docs
                            if "buttonList" in aw or "button_list" in aw:
                                button_list = aw.get("buttonList") or aw.get(
                                    "button_list"
                                )
                                buttons = []
                                for btn_data in button_list.get("buttons", []):
                                    btn = Button(text=btn_data.get("text", ""))
                                    if btn_data.get("onClick") or btn_data.get("url"):
                                        url = btn_data.get("url") or btn_data.get(
                                            "onClick", {}
                                        ).get("openLink", {}).get("url")
                                        if url and OnClick and OpenLink:
                                            btn.on_click = OnClick(
                                                open_link=OpenLink(url=url)
                                            )
                                    buttons.append(btn)
                                if buttons:
                                    bl = ButtonList(buttons=buttons)
                                    aw_obj = AccessoryWidget(button_list=bl)
                                    message_obj.accessory_widgets.append(aw_obj)
                                    logger.debug(
                                        f"🔘 Added accessory widget with {len(buttons)} buttons"
                                    )

            # Render message
            message_body = message_obj.render()

            # Convert snake_case to camelCase using SmartCardBuilder's method
            builder = get_smart_card_builder()
            message_body = builder._convert_to_camel_case(message_body)

            # Special case: fallbackText -> text (Google Chat webhook uses 'text' not 'fallbackText')
            if "fallbackText" in message_body:
                message_body["text"] = message_body.pop("fallbackText")

            # CRITICAL DEBUGGING: Pre-validate card content before sending
            await progress.set_message("Validating card content...")
            final_card = (
                google_format_card.get("card", {})
                if isinstance(google_format_card, dict)
                else {}
            )
            # Use SmartCardBuilder for validation (reuse builder from camelCase conversion)
            is_valid_content, content_issues = builder.validate_content(final_card)

            # Generate DSL notation from rendered card (for LLM learning)
            rendered_dsl = builder.generate_dsl_notation(google_format_card)
            if rendered_dsl:
                logger.info(f"🔣 Rendered DSL notation: {rendered_dsl}")

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
                    dslDetected=dsl_detected,
                    jinjaTemplateApplied=jinja_template_applied,
                    message="Prevented sending blank card - no renderable content",
                    error=f"Validation issues: {'; '.join(content_issues)}",
                )

            logger.info("✅ Pre-send validation passed - card has renderable content")

            # Choose delivery method based on webhook_url
            if webhook_url:
                await progress.set_message("Sending card via webhook...")
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

                # Strip internal fields (like _card_id) that shouldn't be sent to the API
                # NOTE: Do NOT convert field names - Google Chat webhook API expects camelCase
                # for widget fields (onClick, imageUri, etc.). SmartCardBuilder already
                # produces correctly formatted cards.
                webhook_message_body = builder._clean_card_metadata(message_body)

                # NOTE: Threading for webhooks is handled via URL params (threadKey, messageReplyOption)
                # added in _process_thread_key_for_webhook_url(). Do NOT add thread.name to body
                # as it expects a full resource name which we don't have for new threads.

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
                            dslDetected=dsl_detected,
                            jinjaTemplateApplied=jinja_template_applied,
                            dslValidation=dsl_validation_result,
                            inputMapping=input_mapping_info,
                            expectedParams=expected_params_info,
                            suggestedDsl=suggested_dsl,
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
                            dslDetected=dsl_detected,
                            renderedDslNotation=rendered_dsl,
                            jinjaTemplateApplied=jinja_template_applied,
                            dslValidation=dsl_validation_result,
                            inputMapping=input_mapping_info,
                            expectedParams=expected_params_info,
                            suggestedDsl=suggested_dsl,
                            alternativeDsl=_generate_alternative_dsl(rendered_dsl),
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
                        dslDetected=dsl_detected,
                        jinjaTemplateApplied=jinja_template_applied,
                        dslValidation=dsl_validation_result,
                        inputMapping=input_mapping_info,
                        expectedParams=expected_params_info,
                        suggestedDsl=suggested_dsl,
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
                        dslDetected=dsl_detected,
                        jinjaTemplateApplied=jinja_template_applied,
                        dslValidation=dsl_validation_result,
                        inputMapping=input_mapping_info,
                        expectedParams=expected_params_info,
                        suggestedDsl=suggested_dsl,
                        message=f"Webhook delivery failed with status {response.status_code}",
                        error=response.text,
                    )
            else:
                # Send via API
                await progress.set_message("Sending card via Google Chat API...")
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
                        dslDetected=dsl_detected,
                        jinjaTemplateApplied=jinja_template_applied,
                        message=f"Failed to create Google Chat service for {user_google_email}",
                        error="Chat service authentication failed",
                    )

                # Add thread key if provided
                # Strip internal fields (like _card_id) before sending to API
                api_message_body = builder._clean_card_metadata(message_body)
                request_params = {"parent": space_id, "body": api_message_body}
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
                    dslDetected=dsl_detected,
                    renderedDslNotation=rendered_dsl,
                    jinjaTemplateApplied=jinja_template_applied,
                    dslValidation=dsl_validation_result,
                    inputMapping=input_mapping_info,
                    expectedParams=expected_params_info,
                    suggestedDsl=suggested_dsl,
                    alternativeDsl=_generate_alternative_dsl(rendered_dsl),
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
