"""
Singleton ModuleWrapper for qdrant_client.models.

Follows the same pattern as gchat/card_framework_wrapper.py but wraps
qdrant_client.models — the public API surface for Qdrant search primitives.

The ModuleWrapper automatically:
- Indexes all classes in qdrant_client.models as ModuleComponents
- Generates Unicode symbols via SymbolGenerator
- Extracts relationships from Pydantic model fields (via Phase 1f support)
- Builds DSL metadata from relationships

Usage:
    from middleware.qdrant_core.qdrant_models_wrapper import get_qdrant_models_wrapper

    wrapper = get_qdrant_models_wrapper()
    symbols = wrapper.symbol_mapping
    parser = wrapper.get_dsl_parser()
"""

from config.enhanced_logging import setup_logger
import threading
from typing import Dict, Optional

logger = setup_logger()

# Thread-safe singleton
_wrapper: Optional["ModuleWrapper"] = None
_wrapper_lock = threading.Lock()

def get_qdrant_models_wrapper(
    force_reinitialize: bool = False,
) -> "ModuleWrapper":
    """
    Get the singleton ModuleWrapper for qdrant_client.models.

    Args:
        force_reinitialize: If True, recreate the wrapper even if one exists.

    Returns:
        Shared ModuleWrapper instance configured for qdrant_client.models
    """
    global _wrapper

    with _wrapper_lock:
        if _wrapper is None or force_reinitialize:
            _wrapper = _create_wrapper()

    return _wrapper

def _create_wrapper() -> "ModuleWrapper":
    """Create and configure the ModuleWrapper for qdrant_client.models."""
    from adapters.module_wrapper import ModuleWrapper
    from config.settings import settings

    logger.info("Creating ModuleWrapper for qdrant_client.models...")

    wrapper = ModuleWrapper(
        module_or_name="qdrant_client.models",
        qdrant_url=settings.qdrant_url,
        qdrant_api_key=settings.qdrant_api_key,
        collection_name="mcp_qdrant_client_models",
        auto_initialize=True,
        index_nested=True,
        index_private=False,
        max_depth=2,
        skip_standard_library=True,
        include_modules=["qdrant_client"],
    )

    component_count = len(wrapper.components) if wrapper.components else 0
    class_count = sum(
        1 for c in wrapper.components.values() if c.component_type == "class"
    )

    # Register Qdrant-specific skill templates
    _register_qdrant_skill_templates(wrapper)

    logger.info(
        f"ModuleWrapper ready for qdrant_client.models: "
        f"{component_count} components, {class_count} classes"
    )

    return wrapper

def _register_qdrant_skill_templates(wrapper) -> None:
    """Register Qdrant-specific skill templates with the ModuleWrapper."""
    wrapper.register_skill_template("qdrant-dsl-syntax", _generate_qdrant_dsl_template)
    wrapper.register_skill_template("qdrant-dsl-params", _generate_qdrant_dsl_params_template)
    logger.info("Registered Qdrant skill templates with ModuleWrapper")


def _generate_qdrant_dsl_template(wrapper) -> str:
    """Generate the Qdrant DSL syntax skill document dynamically from wrapper symbols."""
    symbols = getattr(wrapper, "symbol_mapping", {})

    s = lambda name, fallback="?": symbols.get(name, fallback)  # noqa: E731

    # Categorize symbols
    filter_names = [
        "Filter", "FieldCondition", "MatchValue", "MatchAny", "MatchText",
        "Range", "HasIdCondition", "IsNullCondition", "IsEmptyCondition",
    ]
    query_names = [
        "RecommendQuery", "DiscoverQuery", "FusionQuery",
        "Prefetch", "OrderBy", "OrderByQuery", "ContextQuery", "SearchParams",
    ]

    filter_rows = "\n".join(
        f"| `{s(n)}` | {n} |" for n in filter_names if s(n, None) is not None
    )
    query_rows = "\n".join(
        f"| `{s(n)}` | {n} |" for n in query_names if s(n, None) is not None
    )

    lines = [
        "# Qdrant DSL Syntax",
        "",
        "The `qdrant_search` tool supports a parameterized DSL for precise filter and query construction.",
        "",
        "## Grammar",
        "",
        "```",
        "symbol{param1=value1, param2=value2}",
        "```",
        "",
        "Values can be:",
        '- Strings: `"hello"`',
        "- Numbers: `42`, `3.14`",
        "- Booleans: `true`, `false`",
        "- Null: `null`",
        "- Nested symbols: `symbol{...}`",
        "- Lists: `[item1, item2, ...]`",
        "",
        "## Filter Symbols (used in `filter_dsl` param)",
        "",
        "| Symbol | Type |",
        "|--------|------|",
        filter_rows,
        "",
        "## Query Symbols (used in `query_dsl`/`prefetch_dsl` params)",
        "",
        "| Symbol | Type |",
        "|--------|------|",
        query_rows,
        "",
        "## Examples",
        "",
        f"- `{s('Filter')}{{must=[{s('FieldCondition')}{{key=\"tool_name\", match={s('MatchValue')}{{value=\"search\"}}}}]}}` — Filter by tool_name",
        f"- `{s('Filter')}{{must=[{s('FieldCondition')}{{key=\"tool_name\", match={s('MatchAny')}{{any=[\"send_dynamic_card\", \"search\"]}}}}]}}` — Match any of multiple values",
        f"- `{s('Filter')}{{must=[{s('FieldCondition')}{{key=\"score\", range={s('Range')}{{gte=0.5}}}}]}}` — Range filter",
        "",
    ]

    return "\n".join(lines)


def _generate_qdrant_dsl_params_template(wrapper) -> str:
    """Generate the Qdrant DSL params reference dynamically from wrapper symbols."""
    symbols = getattr(wrapper, "symbol_mapping", {})

    s = lambda name, fallback="?": symbols.get(name, fallback)  # noqa: E731

    lines = [
        "# Qdrant Search Params Reference",
        "",
        "How to use `filter_dsl`, `query_dsl`, and `prefetch_dsl` with the `qdrant_search` tool.",
        "",
        "## Parameter Overview",
        "",
        "| Param | Purpose | DSL Type |",
        "|-------|---------|----------|",
        "| `query` | Natural language search text (semantic) | Plain text |",
        "| `filter_dsl` | Precise metadata filtering | Filter DSL |",
        "| `query_dsl` | Advanced query modes (recommend, fusion, order-by) | Query DSL |",
        "| `prefetch_dsl` | Multi-stage prefetch pipelines | Prefetch DSL |",
        "| `dry_run` | Parse+build without executing (for validation) | Boolean |",
        "",
        "## filter_dsl",
        "",
        f"Root symbol: `{s('Filter')}` with `must`, `should`, `must_not` arrays.",
        "",
        "### Structure",
        "```",
        f"{s('Filter')}{{",
        f"  must=[",
        f"    {s('FieldCondition')}{{key=\"field_name\", match={s('MatchValue')}{{value=\"exact_value\"}}}}",
        f"  ]",
        f"}}",
        "```",
        "",
        f"### {s('FieldCondition')} Match Types",
        "",
        f"| Type | Symbol | Fields | Usage |",
        f"|------|--------|--------|-------|",
        f"| Exact match | `{s('MatchValue')}` | `value` | Single value equality |",
        f"| Any of | `{s('MatchAny')}` | `any` (list) | Match any in list |",
        f"| Full-text | `{s('MatchText')}` | `text` | Full-text search |",
        f"| Range | `{s('Range')}` | `gt`, `gte`, `lt`, `lte` | Numeric/date range |",
        "",
        "### Common filter patterns",
        "",
        f"**Filter by tool_name:**",
        f"```",
        f'{s("Filter")}{{must=[{s("FieldCondition")}{{key="tool_name", match={s("MatchValue")}{{value="search_gmail_messages"}}}}]}}',
        f"```",
        "",
        f"**Filter by service + date range:**",
        f"```",
        f'{s("Filter")}{{must=[',
        f'  {s("FieldCondition")}{{key="service", match={s("MatchValue")}{{value="gmail"}}}},',
        f'  {s("FieldCondition")}{{key="timestamp", range={s("Range")}{{gte="2026-03-01"}}}}',
        f"]}}",
        "```",
        "",
        f"**Match any of multiple tools:**",
        f"```",
        f'{s("Filter")}{{must=[{s("FieldCondition")}{{key="tool_name", match={s("MatchAny")}{{any=["send_dynamic_card", "compose_dynamic_email"]}}}}]}}',
        "```",
        "",
        "## query_dsl",
        "",
        "For advanced query modes beyond simple semantic search.",
        "",
        f"| Symbol | Purpose | Key Fields |",
        f"|--------|---------|------------|",
        f"| `{s('RecommendQuery', 'RecommendQuery')}` | Find similar to examples | `positive`, `negative` (point ID lists) |",
        f"| `{s('FusionQuery', 'FusionQuery')}` | Fuse multiple queries | `queries` (list) |",
        f"| `{s('OrderByQuery', 'OrderByQuery')}` | Sort by field | `order_by` ({s('OrderBy', 'OrderBy')}), `filter` |",
        "",
        "## prefetch_dsl",
        "",
        f"Multi-stage retrieval using `{s('Prefetch', 'Prefetch')}` chains.",
        "",
        "## Tips",
        "",
        "1. **Use `dry_run: true`** to validate DSL without executing",
        "2. **`query` is still used** as semantic text even when `filter_dsl` is set",
        "3. **Combine modes**: `filter_dsl` + `query` = filtered semantic search",
        "4. **Point IDs**: Use `positive_point_ids`/`negative_point_ids` for recommend mode without DSL",
        "",
    ]

    return "\n".join(lines)


def reset_wrapper():
    """Reset the singleton wrapper."""
    global _wrapper
    with _wrapper_lock:
        if _wrapper is not None:
            logger.info("Resetting qdrant_client.models ModuleWrapper")
            _wrapper = None
