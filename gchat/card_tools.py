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
from fastmcp import Context, FastMCP
from fastmcp.dependencies import Progress
from pydantic import BaseModel, Field
from typing_extensions import Annotated, Any, Dict, List, Optional

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
    import urllib.parse

    thread_id = _extract_thread_id(thread_key)
    if not thread_id:
        return webhook_url

    # URL-encode thread_id to prevent injection via crafted thread keys
    safe_thread_id = urllib.parse.quote(thread_id, safe="")
    separator = "&" if "?" in webhook_url else "?"
    return f"{webhook_url}{separator}threadKey={safe_thread_id}&messageReplyOption=REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"


# ---------------------------------------------------------------------------
# Webhook SSRF protection
# ---------------------------------------------------------------------------

# Private / reserved IP ranges that must never be targeted by webhooks
import ipaddress
import os
import urllib.parse

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

# Configurable allowlist; defaults to Google Chat webhook host
_WEBHOOK_DOMAIN_ALLOWLIST: list[str] | None = None


def _get_webhook_domain_allowlist() -> list[str] | None:
    """Return domain allowlist from env, or None if unrestricted."""
    global _WEBHOOK_DOMAIN_ALLOWLIST
    if _WEBHOOK_DOMAIN_ALLOWLIST is not None:
        return _WEBHOOK_DOMAIN_ALLOWLIST if _WEBHOOK_DOMAIN_ALLOWLIST else None

    raw = os.getenv("WEBHOOK_DOMAIN_ALLOWLIST", "chat.googleapis.com")
    if raw.strip().lower() in ("", "*", "any"):
        _WEBHOOK_DOMAIN_ALLOWLIST = []  # empty → unrestricted
        return None
    _WEBHOOK_DOMAIN_ALLOWLIST = [d.strip().lower() for d in raw.split(",") if d.strip()]
    return _WEBHOOK_DOMAIN_ALLOWLIST


def _validate_webhook_url(url: str) -> None:
    """Validate a webhook URL against SSRF risks.

    Raises ``ValueError`` if the URL fails validation.
    """
    import socket

    parsed = urllib.parse.urlparse(url)

    # 1. Require HTTPS (allow HTTP only for local dev)
    allow_http = os.getenv("ALLOW_HTTP_WEBHOOKS", "false").lower() in ("true", "1")
    if parsed.scheme not in ("https",) and not (allow_http and parsed.scheme == "http"):
        raise ValueError(
            f"Webhook URL must use HTTPS (got {parsed.scheme}). "
            "Set ALLOW_HTTP_WEBHOOKS=true to allow HTTP in local dev."
        )

    # 2. Domain allowlist check
    allowlist = _get_webhook_domain_allowlist()
    hostname = (parsed.hostname or "").lower()
    if allowlist and hostname not in allowlist:
        raise ValueError(
            f"Webhook host '{hostname}' not in allowed domains: {allowlist}"
        )

    # 3. Block private / reserved IP ranges
    try:
        for addr_info in socket.getaddrinfo(hostname, None):
            ip = ipaddress.ip_address(addr_info[4][0])
            for net in _BLOCKED_NETWORKS:
                if ip in net:
                    raise ValueError(
                        f"Webhook URL resolves to private/reserved IP {ip} — blocked for SSRF protection."
                    )
    except socket.gaierror:
        # DNS resolution failed — allow through (Qdrant/Google might be on private DNS)
        pass


def _redact_webhook_url(url: str) -> str:
    """Return a redacted URL suitable for INFO-level logging (strip query params)."""
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, "", "", "")
    )


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
    """Get Google Chat service — delegates to chat_tools which includes service account fallback."""
    from gchat.chat_tools import (
        _get_chat_service_with_fallback as _chat_tools_fallback,
    )

    return await _chat_tools_fallback(user_google_email)


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

    # Generate skill_resources annotation from wrapper (if available)
    from adapters.module_wrapper.wrapper_factory import get_skill_resources_safe

    skill_resources = get_skill_resources_safe(
        _card_framework_wrapper,
        skill_name="gchat-cards",
        resource_hints={
            "card-params.md": {
                "purpose": "How to structure card_params with symbol keys, _shared/_items format, and per-component field reference",
                "when_to_read": "BEFORE first call — required for correct card rendering",
            },
            "dsl-syntax.md": {
                "purpose": "DSL notation syntax, symbol table, containment rules",
                "when_to_read": "When constructing card_description DSL strings",
            },
            "jinja-filters.md": {
                "purpose": "Jinja2 template filters for text styling (colors, bold, etc.)",
                "when_to_read": "When styling text content in cards",
            },
        },
    )

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

    # =========================================================================
    # DRAFT VARIATIONS — Pydantic models and generation function
    # =========================================================================

    class CardVariation(BaseModel):
        """A single card design variation."""

        card_description: str = Field(description="DSL notation for the card structure")
        card_params: dict = Field(description="Widget content params for the variation")
        label: str = Field(
            description="Variation label: Conservative, Enhanced, or Styled"
        )

    class DraftVariationsResult(BaseModel):
        """Structured output from the draft variations agent."""

        variations: List[CardVariation] = Field(
            description="Exactly 3 card variations", min_length=3, max_length=3
        )
        reasoning: str = Field(description="Brief explanation of design choices")

    async def _generate_draft_variations(
        ctx: Context,
        card_description: str,
        card_params: dict,
        webhook_url: Optional[str],
        space_id: Optional[str],
        user_google_email: str,
        thread_key: Optional[str] = None,
    ) -> SendDynamicCardResponse:
        """Generate 3 draft card variations via tool-equipped sampling agent.

        Sends each variation to the Chat space in a shared thread for comparison.
        """
        import secrets

        from gchat.card_builder.utils import coerce_json_param
        from gchat.card_delivery import deliver_card_message
        from middleware.sampling_prompts.card_dsl import (
            DRAFT_AGENT_TOOLS,
            get_draft_variations_prompt,
        )

        card_params = coerce_json_param(card_params, "card_params")

        # Build the agent prompt with original inputs
        tool_args = {
            "card_description": card_description,
            "card_params": card_params,
        }
        system_prompt = get_draft_variations_prompt(tool_args)

        # Sample with tools — the agent can validate DSL, search patterns, check relationships
        user_message = (
            f"Generate 3 draft variations for this card.\n"
            f"card_description: {card_description}\n"
            f"card_params: {json.dumps(card_params, default=str)}"
        )

        result = await ctx.sample(
            messages=user_message,
            system_prompt=system_prompt,
            tools=DRAFT_AGENT_TOOLS,
            result_type=DraftVariationsResult,
            max_tokens=2000,
            temperature=0.4,
        )

        # Extract parsed result
        draft_result = result.result if hasattr(result, "result") else result
        if not isinstance(draft_result, DraftVariationsResult):
            return SendDynamicCardResponse(
                success=False,
                deliveryMethod="webhook" if webhook_url else "api",
                cardType="draft_variations",
                cardDescription=card_description,
                userEmail=user_google_email,
                validationPassed=False,
                message="Draft variations agent did not return structured output",
                error="Sampling result_type mismatch",
            )

        # Send each variation to the Chat space in a shared thread
        draft_thread = thread_key or f"draft_{secrets.token_hex(4)}"
        variations_sent = []

        # Resolve webhook/service for delivery
        if not webhook_url and not space_id and settings.mcp_chat_webhook:
            webhook_url = settings.mcp_chat_webhook

        chat_service = None
        if not webhook_url and space_id:
            chat_service = await _get_chat_service_with_fallback(user_google_email)

        for idx, variation in enumerate(draft_result.variations, 1):
            # Start from original user params as base, overlay agent's variation
            var_params = dict(card_params)
            agent_params = coerce_json_param(variation.card_params, "card_params")
            var_params.update(agent_params)

            # Resolve symbol-keyed params (e.g. δ → items, ᵬ → buttons)
            if (
                _card_framework_wrapper
                and _card_framework_wrapper.reverse_symbol_mapping
            ):
                var_params = _card_framework_wrapper.resolve_symbol_params(var_params)

            # Set draft header
            var_params["title"] = f"Draft {idx}/3 — {variation.label}"
            var_params.setdefault("subtitle", card_description[:80])

            # Build card via SmartCardBuilder (same path as normal send)
            builder = get_smart_card_builder()
            google_format_card = builder.build_from_params(
                description=variation.card_description,
                card_params=var_params,
            )

            if not google_format_card:
                logger.warning(f"Draft {idx} ({variation.label}) failed to build")
                continue

            message_body = {"cardsV2": [google_format_card]}

            # Deliver
            delivery = await deliver_card_message(
                message_body=message_body,
                webhook_url=webhook_url,
                chat_service=chat_service,
                space_id=space_id,
                thread_key=draft_thread,
                builder=builder,
            )

            if delivery.success:
                variations_sent.append(variation.label)

            # Rate limit safety between sends
            if idx < 3:
                await asyncio.sleep(0.5)

        return SendDynamicCardResponse(
            success=len(variations_sent) > 0,
            deliveryMethod="webhook" if webhook_url else "api",
            cardType="draft_variations",
            cardDescription=card_description,
            threadKey=draft_thread,
            webhookUrl=webhook_url,
            userEmail=user_google_email,
            validationPassed=True,
            message=f"Sent {len(variations_sent)}/3 draft variations: {', '.join(variations_sent)}",
            alternativeDsl=[v.card_description for v in draft_result.variations],
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
            "skill_resources": skill_resources,  # Dynamic from wrapper.get_skill_resources_annotation()
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
            Optional[Any],
            Field(
                default=None,
                description="Explicit overrides: title, subtitle, text, buttons, images. "
                f"Supports DSL symbol keys (e.g. {dtext_sym} for items, {btn_sym} for buttons) with optional "
                f'_shared/_items merging: {{"{dtext_sym}": {{"_shared": {{...}}, "_items": [...]}}}}. '
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
        draft_variations: Annotated[
            bool,
            Field(
                default=False,
                description="When true, generate 3 draft card variations (Conservative, Enhanced, Creative) "
                "and send them to the Chat space in a shared thread for comparison instead of sending "
                "the original card. Uses a tool-equipped sampling agent for informed design.",
            ),
        ] = False,
        ctx: Context = None,  # FastMCP injects this; gives access to ctx.sample()
        progress: Progress = Progress(),  # FastMCP background task progress reporting
    ) -> SendDynamicCardResponse:
        """Send a card to Google Chat using DSL notation for structure control."""
        try:
            logger.info(f"🔍 Finding card component for: {card_description}")

            # Report progress for background task tracking
            await progress.set_message("Initializing card builder...")

            # --- Draft variations mode: generate 3 alternatives via sampling agent ---
            if draft_variations and ctx:
                await progress.set_message(
                    "Generating draft variations via sampling agent..."
                )
                return await _generate_draft_variations(
                    ctx=ctx,
                    card_description=card_description,
                    card_params=card_params,
                    webhook_url=webhook_url,
                    space_id=space_id,
                    user_google_email=user_google_email,
                    thread_key=thread_key,
                )

            # Use default webhook from settings if neither webhook nor space_id provided.
            # When space_id is explicitly given, prefer API delivery over default webhook.
            if not webhook_url and not space_id and settings.mcp_chat_webhook:
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

            # MCP clients may send card_params as a JSON string; coerce to dict.
            from gchat.card_builder.utils import coerce_json_param

            card_params = coerce_json_param(card_params, "card_params")

            # =================================================================
            # AUTO-EXTRACT URLs FROM DESCRIPTION
            # When the description contains URLs but no buttons in card_params,
            # extract them as buttons so the DSL suggestion can include ButtonList.
            # =================================================================
            if card_description and not card_params.get("buttons"):
                from gchat.card_builder.utils import extract_urls_from_text

                extracted_buttons, clean_text = extract_urls_from_text(card_description)
                if extracted_buttons:
                    card_params.setdefault("buttons", extracted_buttons)
                    if not card_params.get("text") and clean_text:
                        card_params["text"] = clean_text
                    logger.info(
                        f"🔗 Auto-extracted {len(extracted_buttons)} URL(s) as buttons from description"
                    )

            # =================================================================
            # RESOLVE SYMBOL-KEYED card_params (e.g. δ → items, ᵬ → buttons)
            # =================================================================
            if (
                _card_framework_wrapper
                and _card_framework_wrapper.reverse_symbol_mapping
            ):
                card_params = _card_framework_wrapper.resolve_symbol_params(card_params)

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

            # =============================================================
            # QDRANT INSTANCE PATTERN REUSE
            # When no DSL and no suggested_dsl yet, search Qdrant for similar
            # previously-built cards and reuse their DSL structure.
            # Searches the 'inputs' vector for instance_patterns, then
            # extracts DSL from the relationship_text field.
            # =============================================================
            if not dsl_string and not suggested_dsl:
                try:
                    if _card_framework_wrapper:
                        pattern_results = _card_framework_wrapper.search_by_dsl(
                            text=card_description,
                            limit=5,
                            score_threshold=0.1,
                            vector_name="inputs",
                            type_filter="instance_pattern",
                        )
                        for pattern in pattern_results:
                            rel_text = pattern.get("relationship_text", "")
                            if rel_text:
                                pattern_dsl = extract_dsl_from_description(rel_text)
                                if pattern_dsl:
                                    suggested_dsl = pattern_dsl
                                    logger.info(
                                        f"🔍 Reusing DSL from similar instance pattern: "
                                        f"{suggested_dsl} (score={pattern.get('score', 0):.1f})"
                                    )
                                    break
                except Exception as reuse_err:
                    logger.debug(f"Instance pattern reuse search failed: {reuse_err}")

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
                    builder = get_smart_card_builder()

                    google_format_card = builder.build_from_params(
                        description=card_description,
                        card_params=card_params,
                        suggested_dsl=suggested_dsl,
                    )

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

                        # Extract mapping report from card (attached by builder as dict)
                        inner_card = google_format_card.get("card", {})
                        if isinstance(inner_card, dict):
                            report_dict = inner_card.pop("_mapping_report", None)
                            if isinstance(report_dict, dict):
                                input_mapping_info = InputMappingInfo(
                                    mappings=report_dict.get("mappings", []),
                                    unconsumed=report_dict.get("unconsumed", {}),
                                    dsl_demands=report_dict.get("dsl_demands"),
                                    auto_corrections=report_dict.get("auto_corrections"),
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
            # (thread_key already extracted above at early extraction)
            # =================================================================

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

            # Convert snake_case to camelCase for Google Chat API
            from gchat.card_builder.rendering import convert_to_camel_case

            message_body = convert_to_camel_case(message_body)

            # Special case: fallbackText -> text (Google Chat webhook uses 'text' not 'fallbackText')
            if "fallbackText" in message_body:
                message_body["text"] = message_body.pop("fallbackText")

            # Validate content + structure, auto-repair if needed
            await progress.set_message("Validating card content...")
            is_valid, rendered_dsl, content_issues = builder.validate_and_repair_card(
                google_format_card
            )
            if rendered_dsl:
                logger.info(f"🔣 Rendered DSL notation: {rendered_dsl}")

            if not is_valid:
                logger.error(
                    "🚨 BLANK MESSAGE PREVENTION: Card has no renderable content!"
                )
                logger.error(f"🚨 Content validation issues: {content_issues}")

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

            # Apply structural repairs to message_body if card was fixed
            if content_issues:
                fixed_card = google_format_card.get("card", {})
                cards_v2 = message_body.get("cardsV2", [])
                for card_wrapper in cards_v2:
                    if isinstance(card_wrapper, dict) and "card" in card_wrapper:
                        card_wrapper["card"] = fixed_card
                        break

            # --- Deliver via card_delivery module (handles split + retry) ---
            from gchat.card_delivery import deliver_card_message

            delivery_method = "webhook" if webhook_url else "api"
            await progress.set_message(f"Sending card via {delivery_method}...")

            # For API path, obtain the chat service first
            chat_service = None
            if not webhook_url:
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

            # Pass message_body BEFORE _clean_card_metadata so split can detect feedback sections
            delivery = await deliver_card_message(
                message_body=message_body,
                webhook_url=webhook_url,
                chat_service=chat_service,
                space_id=space_id,
                thread_key=thread_key,
                builder=builder,
            )

            # Build response — common fields shared by success and failure
            component_info = ComponentSearchInfo(
                componentFound=bool(best_match.get("name")),
                componentName=best_match.get("name"),
                componentPath=best_match.get("path"),
                componentType=best_match.get("type"),
                searchScore=best_match.get("score"),
                extractedFromModule=best_match.get("extracted_from_module"),
            )
            parts_sent = delivery.parts_sent if delivery.parts_sent > 1 else None
            split_thread = delivery.thread_key if delivery.parts_sent > 1 else None

            base_response = dict(
                spaceId=space_id,
                deliveryMethod=delivery_method,
                cardType=best_match.get("type", "unknown"),
                componentInfo=component_info,
                cardDescription=card_description,
                threadKey=delivery.thread_key or thread_key,
                webhookUrl=webhook_url,
                userEmail=user_google_email,
                httpStatus=delivery.status_code,
                validationPassed=True,
                dslDetected=dsl_detected,
                jinjaTemplateApplied=jinja_template_applied,
                dslValidation=dsl_validation_result,
                inputMapping=input_mapping_info,
                expectedParams=expected_params_info,
                suggestedDsl=suggested_dsl,
                partsSent=parts_sent,
                splitThreadKey=split_thread,
            )

            # Log card render feedback for A/B scoring correlation
            try:
                from config.settings import Settings as _CfgS
                if _CfgS().search_shadow_scoring:
                    import hashlib as _hl
                    _qh = _hl.md5(card_description.encode()).hexdigest()[:12]
                    logger.info(
                        "Card render feedback | query=%s | success=%s | search_score=%s | component=%s | dsl=%s",
                        _qh,
                        delivery.success,
                        best_match.get("score"),
                        best_match.get("name"),
                        rendered_dsl,
                    )
            except Exception:
                pass

            if delivery.success:
                msg = (
                    f"Card message sent successfully via {delivery_method}"
                    if webhook_url
                    else f"Card message sent successfully to space '{space_id}'"
                )
                return SendDynamicCardResponse(
                    success=True,
                    validationIssues=content_issues if content_issues else None,
                    renderedDslNotation=rendered_dsl,
                    alternativeDsl=_generate_alternative_dsl(rendered_dsl),
                    message=msg,
                    **base_response,
                )
            else:
                return SendDynamicCardResponse(
                    success=False,
                    message=delivery.error or f"Delivery failed via {delivery_method}",
                    error=delivery.error,
                    **base_response,
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

    # Dynamic docstring — symbols generated from SymbolGenerator, never hardcoded
    send_dynamic_card.__doc__ = (
        "Send a card to Google Chat using DSL notation for structure control.\n\n"
        "IMPORTANT: Use DSL symbols in card_description to define card structure.\n"
        "Without DSL, cards render as simple text only.\n\n"
        f"DSL Syntax:\n"
        f"- {section_sym}[widgets] = Section containing widgets\n"
        f"- {dtext_sym} = DecoratedText (text display)\n"
        f"- {btnlist_sym}[{btn_sym}×N] = ButtonList with N buttons\n"
        f"- {grid_sym}[{gitem_sym}×N] = Grid with N items\n"
        "- ×N = repeat N times\n\n"
        f"Common Patterns:\n"
        f"- {section_sym}[{dtext_sym}] = Simple text card\n"
        f"- {section_sym}[{dtext_sym}, {btnlist_sym}[{btn_sym}×2]] = Text + 2 buttons\n"
        f"- {section_sym}[{dtext_sym}×3] = 3 text items\n"
        f"- {section_sym}[{grid_sym}[{gitem_sym}×4]] = Grid with 4 items\n\n"
        "Content (in card_params):\n"
        "- title: Card header title\n"
        "- subtitle: Card header subtitle\n"
        "- text: Main text content\n"
        "- buttons: [{text, url}, ...] for ButtonList\n\n"
        "Jinja Styling (in card_params.text):\n"
        "- {{ 'text' | success_text }} = green\n"
        "- {{ 'text' | error_text }} = red\n"
        "- {{ 'text' | warning_text }} = yellow\n"
        "- {{ 'text' | color('#hex') }} = custom color\n\n"
        "Examples:\n"
        f'    card_description="{section_sym}[{dtext_sym}]", '
        'card_params={"title": "Alert", "text": "Done"}\n'
        f'    card_description="{section_sym}[{dtext_sym}, {btnlist_sym}[{btn_sym}×2]]", '
        'card_params={"title": "Actions", "buttons": [...]}'
    )
