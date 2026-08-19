# Qdrant Search Params Reference

How to use `filter_dsl`, `query_dsl`, and `prefetch_dsl` with the `qdrant_search` tool.

## Parameter Overview

| Param | Purpose | DSL Type |
|-------|---------|----------|
| `query` | Natural language search text (semantic) | Plain text |
| `filter_dsl` | Precise metadata filtering | Filter DSL |
| `query_dsl` | Advanced query modes (recommend, fusion, order-by) | Query DSL |
| `prefetch_dsl` | Multi-stage prefetch pipelines | Prefetch DSL |
| `dry_run` | Parse+build without executing (for validation) | Boolean |

## filter_dsl

Root symbol: `ƒ` with `must`, `should`, `must_not` arrays.

### Structure
```
ƒ{
  must=[
    ʄ{key="field_name", match=☆{value="exact_value"}}
  ]
}
```

### ʄ Match Types

| Type | Symbol | Fields | Usage |
|------|--------|--------|-------|
| Exact match | `☆` | `value` | Single value equality |
| Any of | `ɱ` | `any` (list) | Match any in list |
| Full-text | `ṁ` | `text` | Full-text search |
| Range | `ř` | `gt`, `gte`, `lt`, `lte` | Numeric/date range |

### Common filter patterns

**Filter by tool_name:**
```
ƒ{must=[ʄ{key="tool_name", match=☆{value="search_gmail_messages"}}]}
```

**Filter by service + date range:**
```
ƒ{must=[
  ʄ{key="service", match=☆{value="gmail"}},
  ʄ{key="timestamp", range=ř{gte="2026-03-01"}}
]}
```

**Match any of multiple tools:**
```
ƒ{must=[ʄ{key="tool_name", match=ɱ{any=["send_dynamic_card", "compose_dynamic_email"]}}]}
```

## query_dsl

For advanced query modes beyond simple semantic search.

| Symbol | Purpose | Key Fields |
|--------|---------|------------|
| `R_4` | Find similar to examples | `positive`, `negative` (point ID lists) |
| `φ` | Fuse multiple queries | `queries` (list) |
| `ɵ` | Sort by field | `order_by` (ø), `filter` |

## prefetch_dsl

Multi-stage retrieval using `¶` chains.

## Tips

1. **Use `dry_run: true`** to validate DSL without executing
2. **`query` is still used** as semantic text even when `filter_dsl` is set
3. **Combine modes**: `filter_dsl` + `query` = filtered semantic search
4. **Point IDs**: Use `positive_point_ids`/`negative_point_ids` for recommend mode without DSL
