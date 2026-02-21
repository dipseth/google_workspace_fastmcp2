"""
Singleton ModuleWrapper for card_framework.

This provides a single shared ModuleWrapper instance for all gchat modules
that need to access card_framework components. Avoids redundant wrapper
creation and ensures consistent configuration.

Features:
    - Singleton pattern for shared access
    - Text indices for keyword/phrase search
    - Symbol generation for compact DSL notation
    - Styling registry for color/formatting rules

Usage:
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    # Vector search
    results = wrapper.search("button with icon")

    # Text search (keyword)
    results = wrapper.search_by_text("Button", field="name")

    # Relationship search
    results = wrapper.search_by_relationship_text("clickable image")

    # Hybrid search (text + vector)
    results = wrapper.hybrid_search("decorated text with button")

    # Get symbols for DSL
    symbols = get_gchat_symbols()
"""

import logging
import threading
from typing import Any, Dict, List, Optional

from config.enhanced_logging import setup_logger

logger = setup_logger(__name__)

# Thread-safe singleton
_wrapper: Optional["ModuleWrapper"] = None
_wrapper_lock = threading.Lock()

# Cached symbols
_symbols: Optional[Dict[str, str]] = None
_symbols_lock = threading.Lock()

# =============================================================================
# GCHAT-SPECIFIC CONFIGURATION
# =============================================================================

# Google Chat Card API Limits
GCHAT_CARD_MAX_BYTES = 20_000  # Maximum card payload size
GCHAT_TEXT_MAX_CHARS = 18_000  # Maximum text message length
GCHAT_SAFE_LIMIT_RATIO = 0.75  # Recommended operating ratio (75% of max)
GCHAT_SAFE_CARD_BYTES = int(GCHAT_CARD_MAX_BYTES * GCHAT_SAFE_LIMIT_RATIO)  # ~15KB

# Domain-specific stopwords for gchat card search
GCHAT_STOPWORDS = [
    "widget",  # Too generic
    "component",  # Too generic
    "google",  # Domain noise
    "chat",  # Domain noise
    "card",  # Everything is a card
    "framework",  # Module name noise
]

# =============================================================================
# COMPONENT METADATA (Single Source of Truth for Card Framework)
# =============================================================================
# These constants define card-specific component behavior. They are registered
# with ModuleWrapper via register_component_metadata_batch() at initialization.
# SmartCardBuilder and DSLParser query the wrapper instead of hardcoding these.

# What context resource each component consumes
# Format: component → (context_key, index_key)
CARD_CONTEXT_RESOURCES = {
    "Button": ("buttons", "_button_index"),
    "Chip": ("chips", "_chip_index"),
    "DecoratedText": ("content_texts", "_text_index"),
    "TextParagraph": ("content_texts", "_text_index"),
}

# Container components: JSON field name for children
# Format: container → (children_field, expected_child_type or None)
CARD_CONTAINERS = {
    "ButtonList": ("buttons", "Button"),
    "ChipList": ("chips", "Chip"),
    "Grid": ("items", "GridItem"),
    "Columns": ("columnItems", "Column"),
    "Column": ("widgets", None),  # Heterogeneous
    "Section": ("widgets", None),  # Heterogeneous
    "Carousel": ("carouselCards", "CarouselCard"),
    "CarouselCard": ("widgets", None),
    "NestedWidget": ("widgets", None),
    "SelectionInput": ("items", "SelectionItem"),
}

# Components that require a wrapper parent
# Format: child → required_wrapper_parent
CARD_WRAPPER_REQUIREMENTS = {
    "Button": "ButtonList",
    "Chip": "ChipList",
    "GridItem": "Grid",
    "Column": "Columns",
    "SelectionItem": "SelectionInput",
}

# Valid widget types that can go directly in a Section
CARD_WIDGET_TYPES = {
    "DecoratedText",
    "TextParagraph",
    "Image",
    "ButtonList",
    "ChipList",
    "Grid",
    "SelectionInput",
    "DateTimePicker",
    "Divider",
    "TextInput",
    "Columns",
    "SwitchControl",
    "CollapseControl",
}

# Form components that need a 'name' field
CARD_FORM_COMPONENTS = {
    "TextInput",
    "SelectionInput",
    "DateTimePicker",
    "SwitchControl",
}

# Empty components (just structure, no content params)
CARD_EMPTY_COMPONENTS = {
    "Divider",
    "CollapseControl",
}

# Heterogeneous containers - can hold any widget_type
CARD_HETEROGENEOUS_CONTAINERS = {
    "Section",
    "Column",
}

# Priority overrides for symbol generation — containers get boosted priority
# so they receive more visually distinct symbols from SymbolGenerator.
CARD_PRIORITY_OVERRIDES = {
    "Section": 100,
    "Card": 100,
    "ButtonList": 100,
    "Grid": 100,
    "Columns": 100,
    "ChipList": 100,
}

# Natural language relationship patterns for Google Chat card components.
# Moved from relationships_mixin.py to keep module_wrapper domain-agnostic.
GCHAT_NL_RELATIONSHIP_PATTERNS = {
    # Widget containers
    ("Section", "Widget"): "section containing widgets",
    ("Section", "DecoratedText"): "section with decorated text items",
    ("Section", "TextParagraph"): "section with text paragraphs",
    ("Section", "ButtonList"): "section with button list",
    ("Section", "Grid"): "section with grid layout",
    ("Section", "Image"): "section with image",
    ("Section", "Columns"): "section with column layout",
    ("Section", "Divider"): "section with divider",
    ("Section", "TextInput"): "section with text input field",
    ("Section", "DateTimePicker"): "section with date/time picker",
    ("Section", "SelectionInput"): "section with selection input",
    ("Section", "ChipList"): "section with chip list",
    # Click actions
    ("Image", "OnClick"): "clickable image, image with click action",
    ("Button", "OnClick"): "button click action, button that opens link",
    ("Chip", "OnClick"): "clickable chip",
    ("DecoratedText", "OnClick"): "clickable decorated text",
    ("GridItem", "OnClick"): "clickable grid item",
    # Button containers
    ("ButtonList", "Button"): "list of buttons",
    ("ChipList", "Chip"): "list of chips",
    # Layout
    ("Columns", "Column"): "multi-column layout",
    ("Column", "Widget"): "column containing widgets",
    ("Grid", "GridItem"): "grid with items",
    # Icons and styling
    ("Button", "Icon"): "button with icon",
    ("Chip", "Icon"): "chip with icon",
    ("DecoratedText", "Icon"): "decorated text with icon",
    ("DecoratedText", "Button"): "decorated text with button",
    ("DecoratedText", "SwitchControl"): "decorated text with switch/toggle",
    # Card structure
    ("Card", "Section"): "card with sections",
    ("Card", "CardHeader"): "card with header",
    ("Card", "CardFixedFooter"): "card with footer",
}


def _register_card_component_metadata(wrapper) -> None:
    """
    Register card-specific component metadata with the ModuleWrapper.

    This populates the wrapper's metadata registries so SmartCardBuilder
    and DSLParser can query instead of using hardcoded dicts.
    """
    wrapper.register_component_metadata_batch(
        context_resources=CARD_CONTEXT_RESOURCES,
        containers=CARD_CONTAINERS,
        wrapper_requirements=CARD_WRAPPER_REQUIREMENTS,
        widget_types=CARD_WIDGET_TYPES,
        heterogeneous_containers=CARD_HETEROGENEOUS_CONTAINERS,
        form_components=CARD_FORM_COMPONENTS,
        empty_components=CARD_EMPTY_COMPONENTS,
    )
    logger.info(
        f"📋 Registered card component metadata: "
        f"{len(CARD_CONTEXT_RESOURCES)} resources, "
        f"{len(CARD_CONTAINERS)} containers, "
        f"{len(CARD_WRAPPER_REQUIREMENTS)} wrappers, "
        f"{len(CARD_WIDGET_TYPES)} widgets"
    )


# NOTE: Symbols are auto-generated by SymbolGenerator based on LETTER_SYMBOLS pools.
# ModuleWrapper.generate_component_symbols() is the SSoT for card_framework components.
# See adapters/symbol_generator.py:LETTER_SYMBOLS for the character pools.
#
# CUSTOM CHAT API RELATIONSHIPS: Google Chat API components not in the card_framework
# Python package. These are registered via wrapper.register_custom_components() which
# generates symbols using SymbolGenerator (consistent with the rest of the system).
CUSTOM_CHAT_API_RELATIONSHIPS = {
    # ==========================================================================
    # MESSAGE-LEVEL COMPONENTS (above Card level)
    # These wrap the entire card payload and support webhook features like
    # accessoryWidgets, thread, and fallbackText.
    # ==========================================================================
    # Message is the top-level container for Google Chat messages
    # Supports: text (fallback), cardsV2, accessoryWidgets, thread
    "Message": ["CardWithId", "AccessoryWidget", "Thread"],
    # AccessoryWidget: Buttons at bottom of message (outside card)
    # Only ButtonList is supported in accessoryWidgets per API docs
    "AccessoryWidget": ["ButtonList"],
    # Thread: For reply threading via threadKey
    "Thread": [],  # Leaf component - just has name/threadKey field
    # ==========================================================================
    # CAROUSEL WIDGET HIERARCHY (Google Chat API only)
    # Note: NestedWidget is limited - only supports textParagraph, buttonList, image
    # NOT decoratedText, selectionInput, dateTimePicker, grid, etc.
    # ==========================================================================
    "Carousel": ["CarouselCard"],
    "CarouselCard": ["NestedWidget"],
    "NestedWidget": ["TextParagraph", "ButtonList", "Image"],  # Limited per API docs
    # Card-level components
    "CardFixedFooter": ["Button"],  # primaryButton, secondaryButton
    "CollapseControl": ["Button"],  # expandButton, collapseButton
    # Selection input types
    "SelectionInput": ["SelectionItem", "SelectionType", "PlatformDataSource"],
    # Icon types - MaterialIcon contains the 2,209 valid icon names from Material Design
    # Usage: {"materialIcon": {"name": "arrow_forward"}}
    # Valid names are in gchat.material_icons.MATERIAL_ICONS
    "Icon": ["MaterialIcon", "KnownIcon"],
    "MaterialIcon": [],  # Leaf component - valid names from MATERIAL_ICONS
}

# Metadata for custom Google Chat API components
# This provides docstrings and json_field mappings for the custom components
CUSTOM_CHAT_API_METADATA = {
    # Message-level components
    "Message": {
        "docstring": "Top-level Google Chat message container. Supports text (fallback for "
        "notifications), cardsV2 (card content), accessoryWidgets (buttons at "
        "bottom of message), and thread (for reply threading).",
        "json_field": None,  # Message is the root, no wrapper field
    },
    "AccessoryWidget": {
        "docstring": "Widget displayed at the bottom of a message, outside the card. "
        "Currently only supports ButtonList. Useful for feedback buttons "
        "or quick actions that apply to the whole message.",
        "json_field": "accessoryWidgets",
    },
    "Thread": {
        "docstring": "Thread object for reply threading. Use threadKey to create or "
        "reply to a specific thread. Format: {'name': 'spaces/X/threads/Y'} "
        "or {'threadKey': 'my-custom-key'}.",
        "json_field": "thread",
    },
    # Carousel components
    "Carousel": {
        "docstring": "Horizontal scrollable carousel of cards in Google Chat. "
        "Contains CarouselCard items that users can swipe through.",
        "json_field": "carousel",
    },
    "CarouselCard": {
        "docstring": "Individual card within a Carousel. Contains widgets for content "
        "and optional footerWidgets for actions.",
        "json_field": "carouselCard",
    },
    "NestedWidget": {
        "docstring": "Container for widgets inside CarouselCard. Limited to "
        "TextParagraph, ButtonList, and Image only (per Google Chat API).",
        "json_field": "nestedWidget",
    },
    "CardFixedFooter": {
        "docstring": "Fixed footer at the bottom of a card with primary and secondary buttons.",
        "json_field": "cardFixedFooter",
    },
    "CollapseControl": {
        "docstring": "Controls for collapsible sections with expand/collapse buttons.",
        "json_field": "collapseControl",
    },
    "MaterialIcon": {
        "docstring": "Material Design icon from the 2,209 available icons. "
        "Use with name parameter: {'materialIcon': {'name': 'thumb_up'}}",
        "json_field": "materialIcon",
    },
    "KnownIcon": {
        "docstring": "Legacy known icon type with limited options (STAR, BOOKMARK, etc.).",
        "json_field": "knownIcon",
    },
}


# =============================================================================
# SINGLETON ACCESS
# =============================================================================


def get_card_framework_wrapper(
    force_reinitialize: bool = False,
    ensure_text_indices: bool = True,
) -> "ModuleWrapper":
    """
    Get the singleton ModuleWrapper for card_framework.

    This wrapper is shared across:
        - SmartCardBuilder
        - TemplateComponent
        - card_tools
        - CardBuilderV2
        - Any other gchat modules needing card_framework access

    Args:
        force_reinitialize: If True, recreate the wrapper even if one exists.
                           Use sparingly (e.g., after collection schema changes).
        ensure_text_indices: If True, ensure text indices exist on first init.

    Returns:
        Shared ModuleWrapper instance configured for card_framework
    """
    global _wrapper

    with _wrapper_lock:
        if _wrapper is None or force_reinitialize:
            _wrapper = _create_wrapper(ensure_text_indices=ensure_text_indices)

    return _wrapper


def _create_wrapper(ensure_text_indices: bool = True) -> "ModuleWrapper":
    """Create and configure the ModuleWrapper instance."""
    from adapters.module_wrapper import ModuleWrapper
    from config.settings import settings

    logger.info("🔧 Creating singleton ModuleWrapper for card_framework...")

    wrapper = ModuleWrapper(
        module_or_name="card_framework",
        qdrant_url=settings.qdrant_url,
        qdrant_api_key=settings.qdrant_api_key,
        collection_name=settings.card_collection,  # mcp_gchat_cards_v7
        auto_initialize=False,  # We call initialize() manually below
        index_nested=True,
        index_private=False,
        max_depth=5,  # Capture full component hierarchy
        skip_standard_library=True,
        priority_overrides=CARD_PRIORITY_OVERRIDES,
        nl_relationship_patterns=GCHAT_NL_RELATIONSHIP_PATTERNS,
        use_v7_schema=True,
    )

    # Initialize: populates self.components and symbols synchronously.
    # If v7 pipeline is needed, it runs in a background thread.
    wrapper.initialize()

    component_count = len(wrapper.components) if wrapper.components else 0
    logger.info(f"✅ Singleton ModuleWrapper ready: {component_count} components")

    # === IN-MEMORY OPERATIONS (always sync — no Qdrant writes) ===

    # Custom component metadata for Qdrant indexing (used by deferred callback below)
    custom_components_metadata = {
        # Message-level components (webhook-supported)
        "Message": {
            "children": ["CardWithId", "AccessoryWidget", "Thread"],
            "docstring": "Top-level Google Chat message container. Supports text (fallback for "
            "notifications), cardsV2 (card content), accessoryWidgets (buttons at "
            "bottom of message), and thread (for reply threading). Symbol: μ",
            "json_field": None,  # Message is the root
            "full_path": "card_framework.v2.message.Message",
        },
        "AccessoryWidget": {
            "children": ["ButtonList"],
            "docstring": "Widget displayed at the bottom of a message, outside the card. "
            "Currently only supports ButtonList. Useful for feedback buttons. Symbol: 𝒜",
            "json_field": "accessoryWidgets",
            "full_path": "card_framework.v2.message.AccessoryWidget",
        },
        "Thread": {
            "children": [],
            "docstring": "Thread object for reply threading. Use threadKey to create or "
            "reply to a specific thread. Symbol: Ʈ",
            "json_field": "thread",
            "full_path": "card_framework.v2.message.Thread",
        },
        # Carousel components
        "Carousel": {
            "children": ["CarouselCard"],
            "docstring": "Horizontal scrollable carousel of cards in Google Chat. Contains CarouselCard items.",
            "json_field": "carousel",
        },
        "CarouselCard": {
            "children": ["NestedWidget"],
            "docstring": "Individual card within a Carousel. Contains NestedWidget for content.",
            "json_field": "carouselCard",
        },
        "NestedWidget": {
            "children": ["TextParagraph", "ButtonList", "Image"],
            "docstring": "Container for widgets inside CarouselCard. Limited to "
            "TextParagraph, ButtonList, and Image only (per Google Chat API).",
            "json_field": "nestedWidget",
        },
    }

    # Register custom components IN MEMORY (symbol generation, ModuleComponent creation)
    try:
        custom_symbols = wrapper.register_custom_components(
            CUSTOM_CHAT_API_RELATIONSHIPS,
            generate_symbols=True,
            custom_metadata=CUSTOM_CHAT_API_METADATA,
        )
        if custom_symbols:
            logger.info(
                f"🔧 Registered {len(custom_symbols)} custom Chat API components: "
                f"{list(custom_symbols.keys())}"
            )
    except Exception as e:
        logger.warning(f"⚠️ Failed to register custom components: {e}")

    # Register card-specific component metadata (context resources, containers, etc.)
    # This is the SSoT for SmartCardBuilder and DSLParser queries
    try:
        _register_card_component_metadata(wrapper)
    except Exception as e:
        logger.warning(f"⚠️ Failed to register component metadata: {e}")

    # Register gchat-specific skill templates for FastMCP SkillsDirectoryProvider
    try:
        _register_gchat_skill_templates(wrapper)
    except Exception as e:
        logger.warning(f"⚠️ Failed to register skill templates: {e}")

    # === QDRANT WRITE OPERATIONS ===
    # If v7 pipeline is running in the background, defer these until it completes.
    # If pipeline already completed (fast path), they run immediately.

    def _post_pipeline_qdrant_writes():
        """Runs after v7 pipeline creates the collection — indexes custom components + text indices."""
        try:
            indexed_count = wrapper.index_custom_components(custom_components_metadata)
            if indexed_count > 0:
                logger.info(f"💾 Indexed {indexed_count} custom components to Qdrant")
        except Exception as e:
            logger.warning(f"⚠️ Failed to index custom components: {e}")

        if ensure_text_indices and wrapper.client:
            try:
                from adapters.module_wrapper.text_indexing import (
                    create_component_text_indices,
                )

                indices_created = create_component_text_indices(
                    client=wrapper.client,
                    collection_name=wrapper.collection_name,
                    enable_stemming=True,
                    enable_stopwords=True,
                    enable_phrase_matching=True,
                    enable_ascii_folding=True,
                    custom_stopwords=GCHAT_STOPWORDS,
                )
                if indices_created > 0:
                    logger.info(f"✅ Created {indices_created} new text indices")
            except Exception as e:
                logger.warning(f"⚠️ Failed to create text indices: {e}")

    def _post_pipeline_dag_warmstart():
        """Generate DAG-based instance patterns to warm-start the collection."""
        try:
            _warm_start_with_dag_patterns(wrapper)
        except Exception as e:
            logger.warning(f"⚠️ DAG warm-start failed: {e}")

    if wrapper.v7_pipeline_status == "running":
        # Pipeline is running in background — queue Qdrant writes for when it finishes.
        # Order matters: custom components first, then DAG warm-start (needs the collection ready).
        logger.info("📋 V7 pipeline running — queuing Qdrant writes for post-pipeline")
        wrapper.queue_post_pipeline_callback(_post_pipeline_qdrant_writes)
        wrapper.queue_post_pipeline_callback(_post_pipeline_dag_warmstart)
    else:
        # Pipeline already completed (fast path) — run custom component writes immediately.
        _post_pipeline_qdrant_writes()

        # Check if instance patterns exist — if not, warm-start even on fast path.
        # This handles the case where the pipeline ran but warm-start was missed.
        if wrapper.client:
            try:
                from qdrant_client import models as qmodels

                result = wrapper.client.count(
                    collection_name=wrapper.collection_name,
                    count_filter=qmodels.Filter(
                        must=[
                            qmodels.FieldCondition(
                                key="type",
                                match=qmodels.MatchValue(value="instance_pattern"),
                            )
                        ]
                    ),
                    exact=False,
                )
                if result.count == 0:
                    logger.info(
                        "🌱 No instance patterns found — running DAG warm-start"
                    )
                    _post_pipeline_dag_warmstart()
                else:
                    logger.debug(
                        f"Instance patterns already exist ({result.count}) — skipping warm-start"
                    )
            except Exception as e:
                logger.debug(f"Could not check instance patterns: {e}")

    return wrapper


def reset_wrapper():
    """
    Reset the singleton wrapper and cached symbols.

    Use this when you need to force reinitialization, such as:
        - After updating the Qdrant collection schema
        - During testing
        - After configuration changes
    """
    global _wrapper, _symbols

    with _wrapper_lock:
        if _wrapper is not None:
            logger.info("🔄 Resetting singleton ModuleWrapper")
            _wrapper = None

    with _symbols_lock:
        _symbols = None


# =============================================================================
# DAG WARM-START
# =============================================================================

# Diverse structure recipes for DAG warm-start.
# Each recipe generates a different card structure pattern.
_DAG_WARMSTART_RECIPES = [
    # Basic widget patterns
    {"root": "Section", "required": ["DecoratedText"], "desc": "Simple text card"},
    {
        "root": "Section",
        "required": ["DecoratedText", "ButtonList"],
        "desc": "Text with action buttons",
    },
    {"root": "Section", "required": ["Grid"], "desc": "Grid layout card"},
    {"root": "Section", "required": ["Image"], "desc": "Card with image"},
    {
        "root": "Section",
        "required": ["TextParagraph", "ButtonList"],
        "desc": "Paragraph with buttons",
    },
    {
        "root": "Section",
        "required": ["DecoratedText", "ChipList"],
        "desc": "Text with chip filters",
    },
    {"root": "Section", "required": ["Columns"], "desc": "Multi-column layout"},
    {
        "root": "Section",
        "required": ["SelectionInput"],
        "desc": "Form with selection input",
    },
    {"root": "Section", "required": ["TextInput"], "desc": "Form with text input"},
    {
        "root": "Section",
        "required": ["DecoratedText", "Image", "ButtonList"],
        "desc": "Rich content card",
    },
    # Carousel patterns
    {"root": "Carousel", "required": [], "desc": "Carousel of cards"},
]


def _warm_start_with_dag_patterns(wrapper, count_per_recipe: int = 2) -> int:
    """
    Generate DAG-based instance patterns and store them in the v7 collection.

    Uses DAGStructureGenerator to create random but valid card structures,
    then stores them via FeedbackLoop.store_instance_pattern() as positive
    instance_patterns for warm-starting the search/feedback system.

    Args:
        wrapper: The initialized ModuleWrapper for card_framework
        count_per_recipe: Number of random structures per recipe

    Returns:
        Number of patterns stored
    """
    from gchat.feedback_loop import get_feedback_loop
    from gchat.testing.dag_structure_generator import DAGStructureGenerator

    logger.info(
        f"🌱 DAG warm-start: generating {len(_DAG_WARMSTART_RECIPES)} recipes "
        f"× {count_per_recipe} variations..."
    )

    try:
        gen = DAGStructureGenerator()
    except Exception as e:
        logger.warning(f"⚠️ Could not create DAGStructureGenerator: {e}")
        return 0

    feedback_loop = get_feedback_loop()
    stored = 0

    for recipe in _DAG_WARMSTART_RECIPES:
        root = recipe["root"]
        required = recipe.get("required", [])
        desc = recipe["desc"]

        for i in range(count_per_recipe):
            try:
                structure = gen.generate_random_structure(
                    root=root,
                    required_components=required if required else None,
                )

                if not structure.is_valid:
                    logger.debug(
                        f"   Skipping invalid structure: {structure.validation_issues}"
                    )
                    continue

                # Build component paths from the generated structure
                component_paths = [
                    f"card_framework.v2.{comp}" if "." not in comp else comp
                    for comp in structure.components
                ]

                # Build a natural description
                card_description = (
                    f"{desc} with {', '.join(structure.components[:4])}"
                    f"{' and more' if len(structure.components) > 4 else ''}"
                )

                point_id = feedback_loop.store_instance_pattern(
                    card_description=card_description,
                    component_paths=component_paths,
                    instance_params={
                        "dsl": structure.dsl,
                        "components": structure.components,
                        "depth": structure.depth,
                    },
                    content_feedback="positive",
                    form_feedback="positive",
                    user_email="dag-warmstart@system.local",
                    card_id=f"dag-warmstart-{root.lower()}-{i}",
                    structure_description=f"DSL: {structure.dsl}",
                    pattern_type="content",
                )

                if point_id:
                    stored += 1

            except Exception as e:
                logger.debug(f"   Error generating {desc} variant {i}: {e}")
                continue

    logger.info(f"🌱 DAG warm-start complete: {stored} patterns stored")
    return stored


# =============================================================================
# SYMBOL GENERATION
# =============================================================================


def get_gchat_symbols(force_regenerate: bool = False) -> Dict[str, str]:
    """
    Get the symbol table for gchat card components.

    Returns cached symbols, generating them on first call.
    Symbols are auto-generated by SymbolGenerator based on LETTER_SYMBOLS pools.

    Args:
        force_regenerate: If True, regenerate symbols even if cached

    Returns:
        Dict mapping component names to symbols (e.g., {"Button": "ᵬ"})
    """
    global _symbols

    with _symbols_lock:
        if _symbols is None or force_regenerate:
            _symbols = _generate_gchat_symbols()

    return _symbols


def _generate_gchat_symbols() -> Dict[str, str]:
    """Load symbols from the ModuleWrapper (Single Source of Truth).

    The ModuleWrapper loads symbols from Qdrant and also includes custom
    Google Chat API components (Carousel, NestedWidget, CardFixedFooter, etc.)
    that were registered via register_custom_components().

    This function simply returns the wrapper's symbol_mapping, which is
    the authoritative source for all component symbols.
    """
    wrapper = get_card_framework_wrapper(ensure_text_indices=False)

    # The wrapper's symbol_mapping includes both:
    # 1. Symbols loaded from Qdrant (card_framework components)
    # 2. Custom Chat API symbols (registered via register_custom_components)
    symbols = wrapper.symbol_mapping or {}

    if symbols:
        logger.info(f"🔣 Loaded {len(symbols)} symbols from ModuleWrapper")
        return symbols

    # Fallback: Load from Qdrant directly if symbol_mapping is empty
    if wrapper.client:
        try:
            from qdrant_client import models

            # Scroll through ALL class components to get their stored symbols
            offset = None
            while True:
                results, offset = wrapper.client.scroll(
                    collection_name=wrapper.collection_name,
                    scroll_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="type",
                                match=models.MatchValue(value="class"),
                            )
                        ]
                    ),
                    limit=500,
                    offset=offset,
                    with_payload=["name", "symbol"],
                )

                for p in results:
                    name = p.payload.get("name")
                    symbol = p.payload.get("symbol")
                    if name and symbol:
                        symbols[name] = symbol

                if offset is None:
                    break

            if symbols:
                logger.info(f"🔣 Loaded {len(symbols)} symbols from Qdrant (fallback)")
                return symbols

        except Exception as e:
            logger.warning(f"Failed to load symbols from Qdrant: {e}")

    # Ultimate fallback: Generate symbols if Qdrant unavailable
    logger.warning("⚠️ Falling back to symbol generation (Qdrant unavailable)")
    from adapters.module_wrapper.symbol_generator import SymbolGenerator

    component_names = []
    if wrapper.components:
        component_names = [
            comp.name
            for comp in wrapper.components.values()
            if comp.component_type == "class"
        ]

    generator = SymbolGenerator(module_prefix=None)
    symbols = generator.generate_symbols(component_names)

    logger.info(f"✅ Generated {len(symbols)} symbols (fallback)")
    return symbols


def get_gchat_symbol_table_text() -> str:
    """
    Get a formatted symbol table for LLM instructions.

    Returns:
        Markdown-formatted symbol table
    """
    symbols = get_gchat_symbols()

    # Group by first letter
    from collections import defaultdict

    by_letter = defaultdict(list)
    for comp, sym in symbols.items():
        by_letter[comp[0].upper()].append((sym, comp))

    lines = ["## Google Chat Card Symbols\n"]
    for letter in sorted(by_letter.keys()):
        items = by_letter[letter]
        mappings = [f"{sym}={comp}" for sym, comp in sorted(items, key=lambda x: x[1])]
        lines.append(f"**{letter}:** {', '.join(mappings)}")

    return "\n".join(lines)


def configure_structure_dsl_symbols():
    """
    Configure the structure_dsl module with gchat symbols.

    This updates the global symbol tables in structure_dsl.py to use
    the gchat-specific symbols, enabling both natural language and
    symbol-based card descriptions.
    """
    import gchat.structure_dsl as structure_dsl_module
    from gchat.structure_dsl import (
        ALL_SYMBOLS,
        COMPONENT_TO_SYMBOL,
        SYMBOL_TO_COMPONENT,
    )

    symbols = get_gchat_symbols()

    # Update structure_dsl globals
    SYMBOL_TO_COMPONENT.clear()
    COMPONENT_TO_SYMBOL.clear()

    for comp, sym in symbols.items():
        SYMBOL_TO_COMPONENT[sym] = comp
        COMPONENT_TO_SYMBOL[comp] = sym

    ALL_SYMBOLS.clear()
    ALL_SYMBOLS.update(SYMBOL_TO_COMPONENT.keys())

    # Build ASCII confusable aliases (e.g. 'g' → 'ℊ')
    from gchat.structure_dsl import _build_ascii_confusables

    _build_ascii_confusables()

    # Mark as initialized
    structure_dsl_module._initialized = True

    logger.info(f"🔣 Configured structure_dsl with {len(symbols)} symbols")


# =============================================================================
# CONVENIENCE SEARCH FUNCTIONS
# =============================================================================


def search_components(
    query: str,
    limit: int = 10,
    search_mode: str = "hybrid",
) -> List[Dict]:
    """
    Search for card components using natural language or symbols.

    Args:
        query: Search query (natural language, keywords, or symbols)
        limit: Maximum results
        search_mode: "vector", "text", "relationship", or "hybrid"

    Returns:
        List of matching components
    """
    wrapper = get_card_framework_wrapper()

    if search_mode == "vector":
        return wrapper.search(query, limit=limit)
    elif search_mode == "text":
        return wrapper.search_by_text(query, limit=limit)
    elif search_mode == "relationship":
        return wrapper.search_by_relationship_text(query, limit=limit)
    else:  # hybrid
        return wrapper.hybrid_search(query, limit=limit)


def find_component_by_symbol(symbol: str) -> Optional[Dict]:
    """
    Find a component by its symbol.

    Args:
        symbol: Component symbol (e.g., "ᵬ" for Button)

    Returns:
        Component info dict or None
    """
    symbols = get_gchat_symbols()

    # Reverse lookup
    reverse = {v: k for k, v in symbols.items()}

    component_name = reverse.get(symbol)
    if not component_name:
        return None

    # Search for the component
    wrapper = get_card_framework_wrapper()
    results = wrapper.search_by_text(
        component_name, field="name", limit=1, is_phrase=True
    )

    return results[0] if results else None


def search_patterns_for_card(
    description: str,
    limit: int = 5,
    require_positive_feedback: bool = True,
) -> Dict[str, Any]:
    """
    Search for card patterns matching a description.

    This is a high-level convenience method for card tools that:
    1. Extracts DSL symbols from the description (if present)
    2. Uses DSL-aware search for precise pattern matching
    3. Falls back to hybrid V7 search if no DSL
    4. Returns structured results ready for card building

    Args:
        description: Card description (may include DSL notation like "§[δ, Ƀ[ᵬ×2]]")
        limit: Maximum patterns to return
        require_positive_feedback: Only return patterns with positive feedback

    Returns:
        Dict with:
            - has_dsl: Whether DSL was detected
            - dsl: Extracted DSL string (or None)
            - patterns: List of matching patterns with component_paths, instance_params
            - classes: List of matching class definitions
            - query_description: Cleaned description without DSL
    """
    wrapper = get_card_framework_wrapper()

    # Extract DSL from description
    extracted = wrapper.extract_dsl_from_text(description)

    result = {
        "has_dsl": extracted.get("has_dsl", False),
        "dsl": extracted.get("dsl"),
        "query_description": extracted.get("description", description),
        "patterns": [],
        "classes": [],
    }

    if extracted.get("has_dsl"):
        # Use DSL-aware search for precise matching
        logger.info(f"🔤 DSL search: {extracted['dsl']}")

        # Search for patterns
        pattern_results = wrapper.search_by_dsl(
            text=description,
            limit=limit,
            score_threshold=0.3,
            vector_name="inputs",
            type_filter="instance_pattern",
        )

        # Search for classes
        class_results = wrapper.search_by_dsl(
            text=description,
            limit=limit,
            score_threshold=0.3,
            vector_name="components",
            type_filter="class",
        )

        result["patterns"] = pattern_results
        result["classes"] = class_results
    else:
        # Use hybrid V7 search
        feedback_filter = "positive" if require_positive_feedback else None

        class_results, content_patterns, form_patterns = wrapper.search_v7_hybrid(
            description=description,
            component_paths=None,
            limit=limit,
            token_ratio=1.0,
            content_feedback=feedback_filter,
            form_feedback=feedback_filter,
            include_classes=True,
        )

        result["classes"] = class_results
        result["patterns"] = content_patterns

    logger.info(
        f"Pattern search: {len(result['classes'])} classes, "
        f"{len(result['patterns'])} patterns (DSL={result['has_dsl']})"
    )

    return result


# =============================================================================
# AUTO-GENERATED DSL DOCUMENTATION
# =============================================================================


def get_dsl_documentation(
    include_examples: bool = True, include_hierarchy: bool = True
) -> str:
    """
    Auto-generate COMPACT DSL documentation for MCP tool descriptions.

    Only includes the ~20 most crucial components to keep tool
    descriptions concise. For complete documentation, use skill:// resources.

    Args:
        include_examples: Whether to include usage examples
        include_hierarchy: Whether to include component hierarchy

    Returns:
        Markdown-formatted documentation string (compact)
    """
    symbols = get_gchat_symbols()

    # Crucial components for building cards - organized by role
    CORE_COMPONENTS = {
        "card_structure": ["Card", "CardHeader", "Section"],
        "carousel": ["Carousel", "CarouselCard", "NestedWidget"],
        "containers": ["ButtonList", "ChipList", "Grid", "Columns"],
        "widgets": ["DecoratedText", "TextParagraph", "Image", "Divider"],
        "items": ["Button", "Chip", "GridItem", "Column"],
        "message": ["AccessoryWidget"],  # For message-level buttons
    }

    lines = ["## Card DSL Quick Reference\n"]

    # Core symbols organized by category
    lines.append("### Core Symbols")
    lines.append(
        "**Card:** "
        + ", ".join(
            f"{symbols.get(c, '?')}={c}"
            for c in CORE_COMPONENTS["card_structure"]
            if c in symbols
        )
    )
    lines.append(
        "**Carousel:** "
        + ", ".join(
            f"{symbols.get(c, '?')}={c}"
            for c in CORE_COMPONENTS["carousel"]
            if c in symbols
        )
    )
    lines.append(
        "**Containers:** "
        + ", ".join(
            f"{symbols.get(c, '?')}={c}"
            for c in CORE_COMPONENTS["containers"]
            if c in symbols
        )
    )
    lines.append(
        "**Widgets:** "
        + ", ".join(
            f"{symbols.get(c, '?')}={c}"
            for c in CORE_COMPONENTS["widgets"]
            if c in symbols
        )
    )
    lines.append(
        "**Items:** "
        + ", ".join(
            f"{symbols.get(c, '?')}={c}"
            for c in CORE_COMPONENTS["items"]
            if c in symbols
        )
    )

    # Key containment rules (most common patterns)
    if include_hierarchy:
        lines.append("\n### Containment Rules")
        # Get symbols
        section_sym = symbols.get("Section", "§")
        buttonlist_sym = symbols.get("ButtonList", "Ƀ")
        button_sym = symbols.get("Button", "ᵬ")
        chiplist_sym = symbols.get("ChipList", "ȼ")
        chip_sym = symbols.get("Chip", "ℂ")
        grid_sym = symbols.get("Grid", "ℊ")
        gitem_sym = symbols.get("GridItem", "ǵ")
        columns_sym = symbols.get("Columns", "¢")
        column_sym = symbols.get("Column", "ç")
        dtext_sym = symbols.get("DecoratedText", "δ")
        tpara_sym = symbols.get("TextParagraph", "ʈ")
        image_sym = symbols.get("Image", "ǐ")
        carousel_sym = symbols.get("Carousel", "◦")
        ccard_sym = symbols.get("CarouselCard", "▲")
        nested_sym = symbols.get("NestedWidget", "ŋ")

        lines.append(
            f"- {section_sym} Section → {dtext_sym} {tpara_sym} {image_sym} {buttonlist_sym} {chiplist_sym} {grid_sym} {columns_sym}"
        )
        lines.append(
            f"- {carousel_sym} Carousel → {ccard_sym} CarouselCard → {nested_sym} NestedWidget → {tpara_sym} {buttonlist_sym} {image_sym}"
        )
        lines.append(
            f"- {buttonlist_sym} ButtonList → {button_sym}, {chiplist_sym} ChipList → {chip_sym}"
        )
        lines.append(
            f"- {grid_sym} Grid → {gitem_sym}, {columns_sym} Columns → {column_sym}"
        )

    if include_examples:
        section_sym = symbols.get("Section", "§")
        button_sym = symbols.get("Button", "ᵬ")
        buttonlist_sym = symbols.get("ButtonList", "Ƀ")
        dtext_sym = symbols.get("DecoratedText", "δ")
        grid_sym = symbols.get("Grid", "ℊ")
        gitem_sym = symbols.get("GridItem", "ǵ")
        carousel_sym = symbols.get("Carousel", "◦")
        ccard_sym = symbols.get("CarouselCard", "▲")
        nested_sym = symbols.get("NestedWidget", "ŋ")
        tpara_sym = symbols.get("TextParagraph", "ʈ")

        lines.append("\n### Examples")
        lines.append(f"- `{section_sym}[{dtext_sym}]` → Section with text")
        lines.append(
            f"- `{section_sym}[{dtext_sym}, {buttonlist_sym}[{button_sym}×2]]` → Text + 2 buttons"
        )
        lines.append(
            f"- `{section_sym}[{grid_sym}[{gitem_sym}×4]]` → Grid with 4 items"
        )
        lines.append(f"- `{carousel_sym}[{ccard_sym}×3]` → Carousel with 3 cards")
        lines.append("- Syntax: `×N` = multiplier, `[]` = children, `,` = siblings")

    # Reference to complete docs
    lines.append("\n### More Info")
    lines.append(
        "Read `skill://gchat-cards/` resources for complete docs (100+ components)."
    )

    return "\n".join(lines)


def get_dsl_field_description() -> str:
    """
    Get a compact field description for the structure_dsl parameter.

    Returns a single-line description suitable for Field(description=...).
    """
    symbols = get_gchat_symbols()

    # Core symbols - most commonly used components
    key_mappings = []
    key_components = [
        "Section",
        "DecoratedText",
        "ButtonList",
        "Button",
        "Grid",
        "GridItem",
        "Carousel",
        "CarouselCard",
        "NestedWidget",
    ]

    for comp in key_components:
        if comp in symbols:
            key_mappings.append(f"{symbols[comp]}={comp}")

    return (
        f"DSL structure using symbols. "
        f"Examples: '§[δ, Ƀ[ᵬ×2]]' = Section + text + 2 buttons, "
        f"'◦[▲×3]' = Carousel with 3 cards. "
        f"Symbols: {', '.join(key_mappings)}. "
        f"Read skill://gchat-cards/ for full reference."
    )


def get_tool_examples(max_examples: int = 5) -> List[Dict[str, Any]]:
    """
    Generate dynamic tool examples using symbols from the DAG.

    Creates examples that demonstrate common card patterns with proper
    DSL notation and matching card_params.

    Args:
        max_examples: Maximum number of examples to generate

    Returns:
        List of example dicts with description, card_description, card_params
    """
    symbols = get_gchat_symbols()

    # Get symbols for common components (with fallbacks)
    section = symbols.get("Section", "§")
    dtext = symbols.get("DecoratedText", "δ")
    btnlist = symbols.get("ButtonList", "Ƀ")
    btn = symbols.get("Button", "ᵬ")
    grid = symbols.get("Grid", "ℊ")
    gitem = symbols.get("GridItem", "ǵ")
    chiplist = symbols.get("ChipList", "ȼ")
    chip = symbols.get("Chip", "ℂ")
    carousel = symbols.get("Carousel", "◦")
    ccard = symbols.get("CarouselCard", "▲")
    image = symbols.get("Image", "Ɨ")
    divider = symbols.get("Divider", "Đ")

    # Define examples using dynamic symbols
    all_examples = [
        {
            "description": "Simple text card",
            "card_description": f"{section}[{dtext}]",
            "card_params": {"title": "Alert", "text": "System update complete"},
        },
        {
            "description": "Text + 2 action buttons",
            "card_description": f"{section}[{dtext}, {btnlist}[{btn}×2]]",
            "card_params": {
                "title": "Actions Required",
                "text": "Choose an action",
                "buttons": [
                    {"text": "Approve", "url": "https://example.com/yes"},
                    {"text": "Reject", "url": "https://example.com/no"},
                ],
            },
        },
        {
            "description": "Grid with 4 items",
            "card_description": f"{section}[{grid}[{gitem}×4]]",
            "card_params": {
                "title": "Gallery",
                "images": [
                    "https://picsum.photos/200/200?1",
                    "https://picsum.photos/200/200?2",
                    "https://picsum.photos/200/200?3",
                    "https://picsum.photos/200/200?4",
                ],
            },
        },
        {
            "description": "Jinja styled status text",
            "card_description": f"{section}[{dtext}]",
            "card_params": {
                "title": "System Status",
                "text": "Server: {{ 'Online' | success_text }} | DB: {{ 'Warning' | warning_text }}",
            },
        },
        {
            "description": "Chip list for quick selection",
            "card_description": f"{section}[{dtext}, {chiplist}[{chip}×3]]",
            "card_params": {
                "title": "Select Tags",
                "text": "Choose categories",
                "chips": [
                    {"text": "Bug", "url": "#bug"},
                    {"text": "Feature", "url": "#feature"},
                    {"text": "Docs", "url": "#docs"},
                ],
            },
        },
        {
            "description": "Carousel with 3 cards",
            "card_description": f"{carousel}[{ccard}×3]",
            "card_params": {
                "title": "Recent Items",
                "cards": [
                    {"title": "Card 1", "text": "First item"},
                    {"title": "Card 2", "text": "Second item"},
                    {"title": "Card 3", "text": "Third item"},
                ],
            },
        },
        {
            "description": "Image with text and divider",
            "card_description": f"{section}[{image}, {divider}, {dtext}]",
            "card_params": {
                "title": "Featured",
                "image_url": "https://picsum.photos/400/200",
                "text": "Featured content description",
            },
        },
    ]

    return all_examples[:max_examples]


def get_hierarchy_tree_text(
    root_components: Optional[List[str]] = None,
    max_depth: int = 3,
    include_symbols: bool = True,
) -> str:
    """
    Generate a deterministic text-based tree representation of component hierarchy.

    Delegates to ModuleWrapper.get_hierarchy_tree_text() for the actual implementation.

    Args:
        root_components: Optional list of root component names to start from.
                        If None, uses common card containers (Card, Section, etc.)
        max_depth: Maximum depth to traverse (default 3)
        include_symbols: Whether to include symbols in the output

    Returns:
        ASCII tree representation of the hierarchy
    """
    wrapper = get_card_framework_wrapper()

    # Default root components for gchat cards
    if root_components is None:
        root_components = ["Card", "Section", "DecoratedText", "Grid", "ButtonList"]

    return wrapper.get_hierarchy_tree_text(
        root_components=root_components,
        max_depth=max_depth,
        include_symbols=include_symbols,
    )


def get_full_hierarchy_documentation(include_tree: bool = True) -> str:
    """
    Generate complete hierarchy documentation with symbols and tree visualization.

    Delegates to ModuleWrapper.get_full_module_documentation().

    Args:
        include_tree: Whether to include the ASCII tree visualization

    Returns:
        Complete markdown documentation string
    """
    wrapper = get_card_framework_wrapper()

    return wrapper.get_full_module_documentation(
        include_tree=include_tree,
        include_symbols=True,
        include_examples=True,
    )


def get_component_relationships_for_dsl() -> Dict[str, List[str]]:
    """
    Get component relationships formatted for DSL validation.

    Returns a dict mapping parent components to their valid children,
    using component names (not symbols).

    Dynamically loads relationships from Qdrant and expands base class
    references (e.g., Widget) to actual widget subclasses via Python introspection.
    """
    wrapper = get_card_framework_wrapper()
    relationships = {}

    # Step 1: Get Widget subclasses via Python introspection (most accurate)
    widget_subclasses = _get_widget_subclasses()
    logger.info(
        f"📦 Found {len(widget_subclasses)} Widget subclasses via introspection"
    )

    if not wrapper.client:
        logger.warning("No Qdrant client - using introspection-based relationships")
        return _build_relationships_from_introspection(widget_subclasses)

    try:
        from qdrant_client import models

        # Step 2: Get all classes with their relationships from Qdrant
        results, _ = wrapper.client.scroll(
            collection_name=wrapper.collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="type",
                        match=models.MatchValue(value="class"),
                    )
                ]
            ),
            limit=300,
            with_payload=["name", "relationships"],
        )

        # Step 3: Build relationships, expanding Widget -> all widget subclasses
        for point in results:
            payload = point.payload
            name = payload.get("name")
            rels = payload.get("relationships", {})
            children = rels.get("child_classes", [])

            if name and children:
                # Expand "Widget" to all actual widget subclasses
                expanded_children = []
                for child in children:
                    if child == "Widget":
                        # Replace Widget with all subclasses from introspection
                        expanded_children.extend(widget_subclasses)
                    else:
                        expanded_children.append(child)

                relationships[name] = expanded_children

        logger.info(
            f"📋 Loaded {len(relationships)} component relationships for DSL (Qdrant + introspection)"
        )

        # Log Section's children for debugging
        section_children = relationships.get("Section", [])
        logger.info(
            f"📋 Section can contain: {len(section_children)} widget types: {section_children}"
        )

        return relationships

    except Exception as e:
        logger.warning(f"Failed to load relationships from Qdrant: {e}")
        return _build_relationships_from_introspection(widget_subclasses)


def _get_widget_subclasses() -> List[str]:
    """Get all Widget subclasses via Python introspection."""
    try:
        from card_framework.v2.widget import Widget

        def get_all_subclasses(cls):
            all_subs = []
            for sub in cls.__subclasses__():
                all_subs.append(sub)
                all_subs.extend(get_all_subclasses(sub))
            return all_subs

        subclasses = get_all_subclasses(Widget)
        return sorted([c.__name__ for c in subclasses])
    except ImportError:
        logger.warning("Could not import Widget class for introspection")
        return [
            "Action",
            "Button",
            "ButtonList",
            "Chip",
            "ChipList",
            "Columns",
            "DateTimePicker",
            "DecoratedText",
            "Divider",
            "Grid",
            "Image",
            "SelectionInput",
            "SwitchControl",
            "TextInput",
            "TextParagraph",
            "UpdatedWidget",
        ]


def _build_relationships_from_introspection(
    widget_subclasses: List[str],
) -> Dict[str, List[str]]:
    """Build relationships using Python introspection when Qdrant is unavailable.

    This includes manually-added Google Chat API components that may not exist
    in the card_framework Python package but are supported by the Chat API.
    Custom components are defined in CUSTOM_CHAT_API_RELATIONSHIPS.
    """
    # Base relationships from card_framework introspection
    base_relationships = {
        "Card": ["CardHeader", "Section", "CardFixedFooter", "Carousel"],
        "Section": ["CollapseControl"] + widget_subclasses,
        "Columns": ["Column"],
        "Column": widget_subclasses,  # Column can contain any widget
        "ButtonList": ["Button"],
        "ChipList": ["Chip"],
        "Grid": ["GridItem"],
        "DecoratedText": ["Icon", "Button", "OnClick", "SwitchControl"],
        "Button": ["Icon", "OnClick", "Color"],
        "Chip": ["Icon", "OnClick"],
        "OnClick": ["OpenLink", "Action", "OverflowMenu"],
        "OverflowMenu": ["OverflowMenuItem"],
        "GridItem": ["ImageComponent"],
        "TextInput": ["Suggestions", "Validation"],
    }

    # Merge with custom Chat API relationships (avoids duplication)
    base_relationships.update(CUSTOM_CHAT_API_RELATIONSHIPS)

    return base_relationships


# =============================================================================
# DSL PARSING HELPERS (using refactored module_wrapper.dsl_parser)
# =============================================================================


def get_dsl_parser():
    """
    Get a configured DSL parser for gchat card components.

    Uses the new refactored DSLParser from adapters.module_wrapper.dsl_parser
    which provides:
    - Robust tokenization and parsing
    - Qdrant query generation
    - DSL extraction from descriptions
    - Validation against component hierarchy

    Returns:
        DSLParser instance configured with gchat symbols and relationships
    """
    from adapters.module_wrapper.dsl_parser import DSLParser

    symbols = get_gchat_symbols()
    relationships = get_component_relationships_for_dsl()

    return DSLParser(
        symbol_mapping=symbols,
        reverse_mapping={v: k for k, v in symbols.items()},
        relationships=relationships,
    )


def parse_dsl(dsl_string: str):
    """
    Parse a DSL string using the refactored DSL parser.

    Args:
        dsl_string: DSL notation like "§[đ×3, Ƀ[ᵬ×2]]"

    Returns:
        DSLParseResult with:
        - is_valid: Whether structure is valid
        - component_counts: Dict of component name → count
        - component_paths: Flat list of component names
        - root_nodes: Parsed tree structure
        - issues: List of validation issues

    Example:
        result = parse_dsl("§[đ×3, Ƀ[ᵬ×2]]")
        if result.is_valid:
            print(result.component_counts)
            # {'Section': 1, 'DecoratedText': 3, 'ButtonList': 1, 'Button': 2}
    """
    parser = get_dsl_parser()
    return parser.parse(dsl_string)


def extract_dsl_from_description(description: str) -> Optional[str]:
    """
    Extract DSL notation from a description string.

    Uses the refactored DSL parser for robust extraction.

    Args:
        description: Text that may contain DSL notation
                    e.g., "§[đ×3, Ƀ[ᵬ×2]] Server Status Dashboard"

    Returns:
        DSL string if found, None otherwise
        e.g., "§[δ×3, Ƀ[ᵬ×2]]"

    Example:
        dsl = extract_dsl_from_description("§[đ×3] Server Status")
        # Returns: "§[đ×3]"
    """
    if not description:
        return None

    parser = get_dsl_parser()
    return parser.extract_dsl_from_text(description)


def dsl_to_qdrant_queries(
    dsl_string: str, collection_name: Optional[str] = None
) -> List[Dict]:
    """
    Generate Qdrant queries from a DSL string.

    Uses the refactored DSL parser to generate optimized queries
    for the relationships, components, and inputs vectors.

    Args:
        dsl_string: DSL notation
        collection_name: Qdrant collection name (uses settings.card_collection if None)

    Returns:
        List of query dicts with:
        - vector_name: Which vector to search ('relationships', 'components', 'inputs')
        - query_text: The query text
        - filters: Any filters to apply

    Example:
        queries = dsl_to_qdrant_queries("§[đ×3, Ƀ[ᵬ×2]]")
        for q in queries:
            print(f"{q['vector_name']}: {q['query_text']}")
    """
    from config.settings import settings

    parser = get_dsl_parser()
    result = parser.parse(dsl_string)

    if not result.is_valid:
        logger.warning(f"Invalid DSL structure: {result.issues}")
        return []

    collection = collection_name or settings.card_collection
    queries = parser.to_qdrant_queries(result, collection)

    return [q.to_dict() for q in queries]


def validate_dsl(dsl_string: str) -> tuple:
    """
    Validate a DSL structure against the component hierarchy.

    Args:
        dsl_string: DSL notation to validate

    Returns:
        Tuple of (is_valid, issues_list)

    Example:
        is_valid, issues = validate_dsl("§[đ, ᵬ]")
        if not is_valid:
            print(f"Issues: {issues}")
    """
    parser = get_dsl_parser()
    result = parser.parse(dsl_string)
    return result.is_valid, result.issues


def expand_dsl(dsl_string: str) -> str:
    """
    Expand DSL symbols to full component names.

    Args:
        dsl_string: Compact DSL like "§[đ, ᵬ×2]"

    Returns:
        Expanded notation like "Section[DecoratedText, Button×2]"
    """
    parser = get_dsl_parser()
    return parser.expand_dsl(dsl_string)


def compact_dsl(component_notation: str) -> str:
    """
    Compact component names to DSL symbols.

    Args:
        component_notation: Full names like "Section[DecoratedText, Button×2]"

    Returns:
        Compact DSL like "§[đ, ᵬ×2]"
    """
    parser = get_dsl_parser()
    return parser.compact_to_dsl(component_notation)


# =============================================================================
# CONTENT DSL HELPERS
# =============================================================================


def parse_content_dsl(content_text: str):
    """
    Parse Content DSL text into structured blocks.

    Content DSL allows expressing component content with styling modifiers:

        δ 'Status: Online' success bold
        ᵬ Click Here https://example.com
          Continue on next line

    Features:
        - Symbol prefix indicates component type (δ, ᵬ, §, etc.)
        - Quoted or unquoted text content
        - Style modifiers (yellow, bold, success, error, italic, etc.)
        - URL detection for button/link actions
        - Continuation lines (indented) for multi-line content

    Args:
        content_text: Multi-line Content DSL text

    Returns:
        ContentDSLResult with:
        - is_valid: Whether parsing succeeded
        - blocks: List of ContentBlock objects
        - issues: Any parsing issues

    Example:
        result = parse_content_dsl('''
            § Dashboard bold
            δ 'Server Status' success
            ᵬ Refresh https://api.example.com/refresh
        ''')

        for block in result.blocks:
            print(f"{block.primary.component_name}: {block.to_jinja()}")
    """
    parser = get_dsl_parser()
    return parser.parse_content_dsl(content_text)


def content_to_jinja(content_text: str) -> List[str]:
    """
    Convert Content DSL directly to Jinja expressions.

    A convenience function that parses Content DSL and returns
    the Jinja template expressions for each block.

    Args:
        content_text: Content DSL text

    Returns:
        List of Jinja expressions like ["{{ 'text' | success_text | bold }}"]

    Example:
        expressions = content_to_jinja("δ 'Hello' success bold")
        # Returns: ["{{ 'Hello' | success_text | bold }}"]
    """
    parser = get_dsl_parser()
    result = parser.parse_content_dsl(content_text)
    return result.to_jinja_list()


def content_to_params(content_text: str) -> List[Dict]:
    """
    Convert Content DSL to component parameter dictionaries.

    Useful for directly building card components without going
    through the Jinja template system.

    Args:
        content_text: Content DSL text

    Returns:
        List of dicts with component parameters:
        - component: Component name (e.g., "DecoratedText")
        - text: The text content
        - jinja_text: Jinja-formatted text with filters
        - url: URL if detected (for buttons)
        - styles: List of style modifier names

    Example:
        params = content_to_params('''
            δ 'Server Online' success
            ᵬ Refresh https://api.example.com
        ''')
        # Returns:
        # [
        #   {"component": "DecoratedText", "text": "Server Online", "styles": ["success"], ...},
        #   {"component": "Button", "text": "Refresh", "url": "https://api.example.com", ...}
        # ]
    """
    parser = get_dsl_parser()
    result = parser.parse_content_dsl(content_text)
    return parser.content_to_component_params(result)


def get_available_style_modifiers() -> Dict[str, str]:
    """
    Get available style modifiers for Content DSL.

    Returns:
        Dict mapping modifier name to Jinja filter name

    Example:
        modifiers = get_available_style_modifiers()
        # {'bold': 'bold', 'success': 'success_text', 'yellow': 'color', ...}
    """
    from adapters.module_wrapper.dsl_parser import STYLE_MODIFIERS

    return {name: filter_info[0] for name, filter_info in STYLE_MODIFIERS.items()}


# =============================================================================
# GCHAT-SPECIFIC SKILL TEMPLATES
# =============================================================================

# DSL Guide template content
GCHAT_DSL_GUIDE = """# Structure DSL

Google Chat cards use a compact DSL notation for defining structure.

## Basic Syntax

```
§[δ×3, Ƀ[ᵬ×2]]
```

Means: Section with 3 DecoratedText items and a ButtonList with 2 Buttons.

## Notation Rules

- **Symbols**: Each component has a unique Unicode symbol (see `symbols.md`)
- **Brackets**: `[]` denote children of a container
- **Multiplier**: `×N` creates N copies of a component
- **Comma**: Separates sibling components

## Symbol Table

{symbol_table}

## Examples

{examples}
"""

# Jinja filter guide template content
GCHAT_JINJA_GUIDE = """# Jinja Template Filters

Google Chat cards support Jinja2 template expressions for dynamic content.

## Color Filters

Use these filters to style text with semantic colors:

| Filter | Color | Usage |
|--------|-------|-------|
| `success_text` | Green | `{{{{ 'Online' | success_text }}}}` |
| `error_text` | Red | `{{{{ 'Error' | error_text }}}}` |
| `warning_text` | Yellow | `{{{{ 'Warning' | warning_text }}}}` |
| `info_text` | Blue | `{{{{ 'Info' | info_text }}}}` |

## Custom Colors

Use the `color` filter with a hex value:

```jinja
{{{{ 'Custom text' | color('#FF5733') }}}}
```

## Text Styling

| Filter | Effect |
|--------|--------|
| `bold` | **Bold text** |
| `italic` | *Italic text* |
| `strike` | ~~Strikethrough~~ |

## Combining Filters

Filters can be chained:

```jinja
{{{{ 'Critical Error' | error_text | bold }}}}
```

## Examples

{examples}
"""

# Skill examples for different skill types
GCHAT_SKILL_EXAMPLES = {
    "dsl-syntax": [
        "§[δ] - Simple section with one DecoratedText",
        "§[δ×3, Ƀ[ᵬ×2]] - Section with 3 texts and 2 buttons",
        "§[ℊ[ǵ×4]] - Section with a 4-item Grid",
        "§[δ, Ɨ, Ƀ[ᵬ]] - Section with text, image, and button",
    ],
    "jinja-filters": [
        "{{ 'Online' | success_text }} - Green text",
        "{{ 'Error' | error_text }} - Red text",
        "{{ 'Warning' | warning_text }} - Yellow text",
        "{{ text | color('#FF5733') }} - Custom orange text",
        "{{ 'Important' | bold }} - Bold text",
    ],
}


def _generate_gchat_dsl_template(wrapper) -> str:
    """
    Generate the DSL syntax skill document.

    Args:
        wrapper: ModuleWrapper instance

    Returns:
        Markdown content for DSL syntax guide
    """
    # Get symbol table from wrapper
    symbol_table = (
        wrapper.get_symbol_table_text()
        if hasattr(wrapper, "get_symbol_table_text")
        else "No symbols available."
    )

    # Format examples
    examples = GCHAT_SKILL_EXAMPLES.get("dsl-syntax", [])
    examples_text = "\n".join(f"- `{e}`" for e in examples)

    return GCHAT_DSL_GUIDE.format(
        symbol_table=symbol_table,
        examples=examples_text,
    )


def _generate_gchat_jinja_template(wrapper) -> str:
    """
    Generate the Jinja filters skill document.

    Args:
        wrapper: ModuleWrapper instance

    Returns:
        Markdown content for Jinja filters guide
    """
    # Format examples
    examples = GCHAT_SKILL_EXAMPLES.get("jinja-filters", [])
    examples_text = "\n".join(f"- `{e}`" for e in examples)

    return GCHAT_JINJA_GUIDE.format(
        examples=examples_text,
    )


def _register_gchat_skill_templates(wrapper) -> None:
    """
    Register gchat-specific skill templates with the ModuleWrapper.

    Called during wrapper initialization, similar to _register_card_component_metadata().

    Args:
        wrapper: ModuleWrapper instance with SkillsMixin
    """
    # Register DSL syntax template
    wrapper.register_skill_template("dsl-syntax", _generate_gchat_dsl_template)

    # Register Jinja filter guide
    wrapper.register_skill_template("jinja-filters", _generate_gchat_jinja_template)

    # Register examples for each skill type
    for skill_type, examples in GCHAT_SKILL_EXAMPLES.items():
        wrapper.register_skill_examples(skill_type, examples)

    logger.info("Registered gchat skill templates with ModuleWrapper")
