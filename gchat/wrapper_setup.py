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

import threading
from typing import Any, Dict, List, Optional

from config.enhanced_logging import setup_logger

logger = setup_logger()

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
GCHAT_CARD_MAX_BYTES = 32_000  # Empirically determined webhook payload limit (~32KB)
GCHAT_TEXT_MAX_CHARS = 18_000  # Maximum text message length
GCHAT_SAFE_LIMIT_RATIO = 0.75  # Recommended operating ratio (75% of max)
GCHAT_SAFE_CARD_BYTES = int(GCHAT_CARD_MAX_BYTES * GCHAT_SAFE_LIMIT_RATIO)  # ~24KB

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
    "GridItem": ("grid_items", "_grid_item_index"),
    "CarouselCard": ("carousel_cards", "_carousel_card_index"),
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

def _register_card_input_resolution(wrapper) -> None:
    """Register card-specific input resolution with InputResolverMixin.

    Populates field extractors, overflow handlers, and param key overrides
    so the mixin can drive symbol param resolution and context consumption.
    """
    from gchat.card_builder.field_extractors import (
        CARD_FIELD_EXTRACTORS,
        CARD_OVERFLOW_HANDLERS,
        CARD_PARAM_KEY_OVERRIDES,
        CARD_SCALAR_PARAMS,
    )

    wrapper.register_input_resolution_batch(
        extractors=CARD_FIELD_EXTRACTORS,
        overflow_handlers=CARD_OVERFLOW_HANDLERS,
        param_key_overrides=CARD_PARAM_KEY_OVERRIDES,
        scalar_params=CARD_SCALAR_PARAMS,
    )
    logger.info(
        f"📋 Registered card input resolution: "
        f"{len(CARD_FIELD_EXTRACTORS)} extractors, "
        f"{len(CARD_OVERFLOW_HANDLERS)} overflow handlers"
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
    """Create and configure the ModuleWrapper instance using DomainConfig."""
    from adapters.module_wrapper import DomainConfig, ModuleWrapper
    from config.settings import settings
    from gchat.wrapper_dag import _warm_start_with_dag_patterns

    logger.info("🔧 Creating singleton ModuleWrapper for card_framework.v2...")

    # Custom component metadata for Qdrant indexing (used by post-pipeline hook)
    custom_components_metadata = {
        "Message": {
            "children": ["CardWithId", "AccessoryWidget", "Thread"],
            "docstring": "Top-level Google Chat message container. Supports text (fallback for "
            "notifications), cardsV2 (card content), accessoryWidgets (buttons at "
            "bottom of message), and thread (for reply threading). Symbol: μ",
            "json_field": None,
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

    # -------------------------------------------------------------------------
    # Post-init hooks: in-memory operations (sync, no Qdrant writes)
    # -------------------------------------------------------------------------
    def _hook_register_custom_components(wrapper):
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

    # -------------------------------------------------------------------------
    # Post-pipeline hooks: Qdrant write operations (deferred if pipeline running)
    # -------------------------------------------------------------------------
    def _hook_post_pipeline_qdrant_writes(wrapper):
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

    def _hook_post_pipeline_dag_warmstart(wrapper):
        try:
            _warm_start_with_dag_patterns(wrapper)
        except Exception as e:
            logger.warning(f"⚠️ DAG warm-start failed: {e}")

    # -------------------------------------------------------------------------
    # DomainConfig: declarative domain configuration
    # -------------------------------------------------------------------------
    # NOTE: DAG warm-start is NOT in post_pipeline_hooks because it needs
    # conditional logic (skip if instance patterns already exist on fast path).
    # It's handled explicitly below.
    domain_config = DomainConfig(
        module_name="card_framework.v2",
        pip_package="python-card-framework",
        auto_install=False,  # Already in requirements.txt
        priority_overrides=CARD_PRIORITY_OVERRIDES,
        nl_relationship_patterns=GCHAT_NL_RELATIONSHIP_PATTERNS,
        post_init_hooks=[
            _hook_register_custom_components,
            _register_card_component_metadata,
            _register_card_input_resolution,
            _register_gchat_skill_templates,
        ],
        post_pipeline_hooks=[
            _hook_post_pipeline_qdrant_writes,
        ],
        domain_label="Google Chat Cards",
    )

    wrapper = ModuleWrapper(
        module_or_name=domain_config.module_name,
        qdrant_url=settings.qdrant_url,
        qdrant_api_key=settings.qdrant_api_key,
        collection_name=settings.card_collection,
        auto_initialize=False,
        index_nested=True,
        index_private=False,
        max_depth=5,
        skip_standard_library=True,
        domain_config=domain_config,
    )

    # Initialize: populates self.components and symbols synchronously.
    # If the pipeline is needed, it runs in a background thread.
    wrapper.initialize()

    component_count = len(wrapper.components) if wrapper.components else 0
    logger.info(f"✅ Singleton ModuleWrapper ready: {component_count} components")

    # Run post-init hooks (in-memory operations)
    wrapper.run_domain_hooks("post_init")

    # Schedule post-pipeline hooks (Qdrant write operations)
    if wrapper.pipeline_status == "running":
        # Pipeline running in background — queue writes + DAG warm-start for when it finishes.
        # Order matters: custom components first, then DAG warm-start (needs the collection ready).
        logger.info("📋 Pipeline running — queuing Qdrant writes for post-pipeline")
        for hook in domain_config.post_pipeline_hooks:
            wrapper.queue_post_pipeline_callback(lambda h=hook: h(wrapper))
        wrapper.queue_post_pipeline_callback(
            lambda: _hook_post_pipeline_dag_warmstart(wrapper)
        )
    else:
        # Pipeline already completed (fast path) — run Qdrant writes immediately
        wrapper.run_domain_hooks("post_pipeline")

        # DAG warm-start: only if no instance patterns exist yet
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
                    _hook_post_pipeline_dag_warmstart(wrapper)
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

def _generate_gchat_card_params_template(wrapper) -> str:
    """
    Generate the card_params skill document dynamically from wrapper symbols.

    All symbols are pulled from wrapper.symbol_mapping — no hardcoded Unicode.

    Args:
        wrapper: ModuleWrapper instance

    Returns:
        Markdown content for card_params guide
    """
    symbols = getattr(wrapper, "symbol_mapping", {})

    # Get symbols dynamically
    s = lambda name, fallback="?": symbols.get(name, fallback)  # noqa: E731

    # Symbol-to-flat-key mapping table (from symbol_params.py resolution rules)
    # These are the components that have context_resources and resolve to flat keys
    param_rows = [
        (s("DecoratedText"), "DecoratedText", "items", "List of decorated text widgets"),
        (s("TextParagraph"), "TextParagraph", "items", "List of text paragraph widgets"),
        (s("Button"), "Button", "buttons", "List of button widgets"),
        (s("GridItem"), "GridItem", "grid_items", "List of grid cells"),
        (s("CarouselCard"), "CarouselCard", "cards", "List of carousel card widgets"),
        (s("Chip"), "Chip", "chips", "List of chip widgets"),
    ]

    # Container symbols (no param key — use children's symbols)
    container_syms = ", ".join(
        f"`{s(c)}`" for c in ["Section", "ButtonList", "Grid", "Carousel", "Columns", "ChipList"]
        if s(c, None) is not None
    )

    # Build the mapping table
    table_rows = "\n".join(
        f"| `{sym}` | {comp} | `{key}` | {purpose} |"
        for sym, comp, key, purpose in param_rows
    )

    # Build dynamic examples using actual symbols
    dtext = s("DecoratedText")
    btn = s("Button")
    gitem = s("GridItem")
    ccard = s("CarouselCard")
    section = s("Section")
    divider = s("Divider")
    btnlist = s("ButtonList")

    lines = [
        "# Card Params Reference",
        "",
        "How to structure `card_params` when using DSL notation with `send_dynamic_card`.",
        "",
        "## Symbol-Keyed Params",
        "",
        "Use DSL symbols as keys in `card_params` for direct correspondence with the DSL structure.",
        "",
        "### Symbol to Flat Key Mapping",
        "",
        "| Symbol | Component | Flat Key | Purpose |",
        "|--------|-----------|----------|---------|",
        table_rows,
        "",
        f"Container symbols ({container_syms}) have no param key — use their children's symbols.",
        "",
        "## Three Formats",
        "",
        "### Format A: Direct List",
        "```json",
        f'{{"{dtext}": [{{"text": "Item 1", "top_label": "Status"}}, {{"text": "Item 2"}}]}}',
        "```",
        "",
        "### Format B: _shared/_items (DRY — recommended)",
        "```json",
        "{",
        f'  "{dtext}": {{',
        '    "_shared": {"top_label": "Status", "icon": "check_circle"},',
        '    "_items": [',
        '      {"text": "Drive: Online"},',
        '      {"text": "Gmail: Online"}',
        "    ]",
        "  }",
        "}",
        "```",
        "Each `_items` entry is merged with `_shared` (item fields override shared).",
        "",
        "### Format C: Single Dict (auto-wrapped in list)",
        "```json",
        f'{{"{btn}": {{"text": "Click Me", "url": "https://example.com"}}}}',
        "```",
        "",
        "## Component Field Reference",
        "",
        f"### DecoratedText (`{dtext}`)",
        "- `text` (**required**) — Main content (supports HTML: `<b>`, `<font color=\"...\">`)",
        "- `top_label` — Small label above text",
        "- `bottom_label` — Small label below text",
        "- `icon` — Google Material icon name (e.g., `star`, `check_circle`, `error`)",
        "",
        f"### Button (`{btn}`)",
        "- `text` (**required**) — Button label",
        "- `url` — Click target URL",
        "- `icon` — Optional icon name",
        "",
        f"### GridItem (`{gitem}`)",
        "- `title` (**required**) — Item title",
        "- `subtitle` — Optional subtitle",
        "- `image_url` — Optional image URL",
        "",
        f"### CarouselCard (`{ccard}`)",
        "- `title` (**required**) — Card title",
        "- `subtitle` — Optional subtitle",
        "- `text` — Optional card body",
        "- `image_url` — Optional image",
        "- `buttons` — Optional list of `{text, url}` dicts",
        "",
        f"### TextParagraph (`{s('TextParagraph')}`)",
        "- `text` (**required**) — Paragraph text (supports HTML)",
        "",
        "## Important Rules",
        "",
        f"1. **Item count must match DSL multiplier**: `{dtext}×3` requires exactly 3 items in `_items`",
        f"2. **Symbol keys override flat keys**: If both `{dtext}` and `items` exist, `{dtext}` wins",
        "3. **Backward compatible**: Flat keys (`items`, `buttons`, `grid_items`) still work",
        "4. **`title` and `subtitle`** are card-level params, not symbol-keyed",
        "",
        "## Full Example",
        "",
        f"DSL: `{section}[{dtext}×2, {divider}, {btnlist}[{btn}×2]]`",
        "",
        "```json",
        "{",
        '  "title": "System Status",',
        '  "subtitle": "All services",',
        f'  "{dtext}": {{',
        '    "_shared": {"icon": "monitoring", "top_label": "Service"},',
        '    "_items": [',
        '      {"text": "API: <font color=\\"#34a853\\"><b>Online</b></font>"},',
        '      {"text": "DB: <font color=\\"#fbbc04\\"><b>Warning</b></font>"}',
        "    ]",
        "  },",
        f'  "{btn}": [',
        '    {"text": "View Details", "url": "https://example.com/details"},',
        '    {"text": "Export CSV", "url": "https://example.com/export"}',
        "  ]",
        "}",
        "```",
        "",
    ]

    return "\n".join(lines)

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

    # Register card_params guide (symbol keys, _shared/_items, field reference)
    wrapper.register_skill_template("card-params", _generate_gchat_card_params_template)

    # Register Jinja filter guide
    wrapper.register_skill_template("jinja-filters", _generate_gchat_jinja_template)

    # Register examples for each skill type
    for skill_type, examples in GCHAT_SKILL_EXAMPLES.items():
        wrapper.register_skill_examples(skill_type, examples)

    logger.info("Registered gchat skill templates with ModuleWrapper")
