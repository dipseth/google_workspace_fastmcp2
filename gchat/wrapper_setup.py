"""
Singleton ModuleWrapper for card_framework — setup, constants, and initialization.

This module owns:
    - All card-specific constants and metadata
    - Singleton state (_wrapper, _wrapper_lock, _symbols, _symbols_lock)
    - Wrapper creation and initialization
    - Skill template registration

Usage:
    from gchat.wrapper_setup import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()
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
    from gchat.wrapper_dag import _warm_start_with_dag_patterns

    logger.info("🔧 Creating singleton ModuleWrapper for card_framework...")

    wrapper = ModuleWrapper(
        module_or_name="card_framework",
        qdrant_url=settings.qdrant_url,
        qdrant_api_key=settings.qdrant_api_key,
        collection_name=settings.card_collection,
        auto_initialize=False,  # We call initialize() manually below
        index_nested=True,
        index_private=False,
        max_depth=5,  # Capture full component hierarchy
        skip_standard_library=True,
        priority_overrides=CARD_PRIORITY_OVERRIDES,
        nl_relationship_patterns=GCHAT_NL_RELATIONSHIP_PATTERNS,
    )

    # Initialize: populates self.components and symbols synchronously.
    # If the pipeline is needed, it runs in a background thread.
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
    # If pipeline is running in the background, defer these until it completes.
    # If pipeline already completed (fast path), they run immediately.

    def _post_pipeline_qdrant_writes():
        """Runs after pipeline creates the collection — indexes custom components + text indices."""
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

    if wrapper.pipeline_status == "running":
        # Pipeline is running in background — queue Qdrant writes for when it finishes.
        # Order matters: custom components first, then DAG warm-start (needs the collection ready).
        logger.info("📋 Pipeline running — queuing Qdrant writes for post-pipeline")
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
