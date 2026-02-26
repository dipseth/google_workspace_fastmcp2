"""
Singleton ModuleWrapper for card_framework — backward-compatible facade.

This module re-exports all public names from the split modules so that
existing ``from gchat.card_framework_wrapper import X`` statements
continue to work without modification.

Internal implementation lives in:
    - gchat.wrapper_setup  (constants, singleton, skill templates)
    - gchat.wrapper_api    (symbols, search, DSL docs, DSL parsing)
    - gchat.wrapper_dag    (DAG warm-start recipes and generation)
"""

# --- Setup: constants, singleton, skill templates ---
# --- API: symbols, search, DSL docs, DSL parsing ---
from gchat.wrapper_api import (
    compact_dsl,
    configure_structure_dsl_symbols,
    content_to_jinja,
    content_to_params,
    dsl_to_qdrant_queries,
    expand_dsl,
    extract_dsl_from_description,
    find_component_by_symbol,
    get_available_style_modifiers,
    get_component_relationships_for_dsl,
    get_dsl_documentation,
    get_dsl_field_description,
    get_dsl_parser,
    get_full_hierarchy_documentation,
    get_gchat_symbol_table_text,
    get_gchat_symbols,
    get_hierarchy_tree_text,
    get_tool_examples,
    parse_content_dsl,
    parse_dsl,
    search_components,
    search_patterns_for_card,
    validate_dsl,
)
from gchat.wrapper_setup import (
    CARD_CONTAINERS,
    CARD_CONTEXT_RESOURCES,
    CARD_EMPTY_COMPONENTS,
    CARD_FORM_COMPONENTS,
    CARD_HETEROGENEOUS_CONTAINERS,
    CARD_PRIORITY_OVERRIDES,
    CARD_WIDGET_TYPES,
    CARD_WRAPPER_REQUIREMENTS,
    CUSTOM_CHAT_API_METADATA,
    CUSTOM_CHAT_API_RELATIONSHIPS,
    GCHAT_CARD_MAX_BYTES,
    GCHAT_NL_RELATIONSHIP_PATTERNS,
    GCHAT_SAFE_CARD_BYTES,
    GCHAT_SAFE_LIMIT_RATIO,
    GCHAT_STOPWORDS,
    GCHAT_TEXT_MAX_CHARS,
    get_card_framework_wrapper,
    reset_wrapper,
)

__all__ = [
    # Setup / constants
    "CARD_CONTEXT_RESOURCES",
    "CARD_CONTAINERS",
    "CARD_EMPTY_COMPONENTS",
    "CARD_FORM_COMPONENTS",
    "CARD_HETEROGENEOUS_CONTAINERS",
    "CARD_PRIORITY_OVERRIDES",
    "CARD_WIDGET_TYPES",
    "CARD_WRAPPER_REQUIREMENTS",
    "CUSTOM_CHAT_API_METADATA",
    "CUSTOM_CHAT_API_RELATIONSHIPS",
    "GCHAT_CARD_MAX_BYTES",
    "GCHAT_NL_RELATIONSHIP_PATTERNS",
    "GCHAT_SAFE_CARD_BYTES",
    "GCHAT_SAFE_LIMIT_RATIO",
    "GCHAT_STOPWORDS",
    "GCHAT_TEXT_MAX_CHARS",
    "get_card_framework_wrapper",
    "reset_wrapper",
    # API / symbols / search / DSL
    "compact_dsl",
    "configure_structure_dsl_symbols",
    "content_to_jinja",
    "content_to_params",
    "dsl_to_qdrant_queries",
    "expand_dsl",
    "extract_dsl_from_description",
    "find_component_by_symbol",
    "get_available_style_modifiers",
    "get_component_relationships_for_dsl",
    "get_dsl_documentation",
    "get_dsl_field_description",
    "get_dsl_parser",
    "get_full_hierarchy_documentation",
    "get_gchat_symbol_table_text",
    "get_gchat_symbols",
    "get_hierarchy_tree_text",
    "get_tool_examples",
    "parse_content_dsl",
    "parse_dsl",
    "search_components",
    "search_patterns_for_card",
    "validate_dsl",
]
