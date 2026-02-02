# Search Strategies

> **Status:** Coming soon

This document will cover the various search methods available in ModuleWrapper.

## Planned Topics

### Search Method Overview

| Method | Vector(s) | Use Case |
|--------|-----------|----------|
| `search()` | MiniLM | Basic semantic search |
| `colbert_search()` | ColBERT | Token-level matching |
| `search_v7()` | Single named | Targeted vector search |
| `search_v7_hybrid()` | All 3 + RRF | Best overall results |
| `search_by_dsl()` | ColBERT | DSL-aware queries |
| `query_by_symbol()` | None (filter) | Exact symbol lookup |

### Simple Searches (Single Vector)

- `search(query, limit, score_threshold)` - MiniLM semantic search
- `search_async()` - Async version of basic search
- `colbert_search()` - ColBERT multi-vector with MaxSim
- `query_by_symbol()` - Exact match on symbol field

### Text Index Searches

- `search_by_text(field, query)` - Qdrant text index search
- `search_by_relationship_text()` - Search relationship descriptions
- `search_within_module()` - Module-scoped text search

### DSL-Aware Searches

```python
# Extract DSL and search
results = wrapper.search_by_dsl("§[δ, Ƀ[ᵬ×2]] Build a status card")

# Hybrid DSL search (classes + patterns)
results = wrapper.search_by_dsl_hybrid("§[δ] notification card")
# Returns: {"classes": [...], "patterns": [...], "query_info": {...}}
```

- DSL extraction from natural language
- DSL + description embedding
- Class vs pattern filtering

### V7 Multi-Vector Searches

```python
# Search specific vector
results = wrapper.search_v7(
    query="button with icon",
    vector_name="components",  # or "inputs", "relationships"
    limit=10,
)

# Hybrid search with RRF fusion
classes, patterns, relationships = wrapper.search_v7_hybrid(
    description="status card with action button",
    component_paths=["Section", "DecoratedText"],
    content_feedback="positive",  # Filter by feedback
)
```

### Vector Selection Guide

| Query Type | Best Vector | Why |
|------------|-------------|-----|
| "Find Button class" | `components` | Component identity |
| "card with status text" | `inputs` | Content/parameter matching |
| "Section containing Button" | `relationships` | Structural patterns |
| Complex queries | `search_v7_hybrid` | RRF combines all |

### RRF Fusion

Reciprocal Rank Fusion combines results from multiple vectors:

```
RRF_score = Σ (1 / (k + rank))
```

- Default k=60 (higher = more weight to lower ranks)
- Deduplicates across result sets
- Preserves best results from each strategy

### Feedback Filtering

```python
# Filter by content feedback
classes, patterns, _ = wrapper.search_v7_hybrid(
    description="notification card",
    content_feedback="positive",  # Only positive content matches
)

# Filter by form/structure feedback
_, _, relationships = wrapper.search_v7_hybrid(
    description="grid layout",
    form_feedback="positive",  # Only positive structure matches
)
```

### Direct Component Lookup

Before vector search, methods check for exact matches:

1. Exact name match in `components` dict
2. Case-insensitive name match
3. Check `widgets` submodule
4. Fall back to vector search

### Result Processing

```python
# Standard result format
{
    "id": "point_id",
    "score": 0.85,
    "name": "Button",
    "type": "class",
    "full_path": "card_framework.v2.widgets.button.Button",
    "symbol": "ᵬ",
    "docstring": "...",
    "component": <class Button>,  # Resolved class object
}
```

### Performance Tips

- Use `token_ratio` < 1.0 for faster ColBERT searches
- Use `query_by_symbol()` for known symbols (fastest)
- Use `search_v7()` with specific vector for targeted queries
- Use `search_v7_hybrid()` when unsure which vector is best

## Related Files

- `search_mixin.py` - SearchMixin implementation
- `embedding_mixin.py` - Embedding generation
- `symbols_mixin.py` - DSL extraction methods
