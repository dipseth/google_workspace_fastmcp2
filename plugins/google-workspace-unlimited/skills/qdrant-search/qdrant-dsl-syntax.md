# Qdrant DSL Syntax

The `qdrant_search` tool supports a parameterized DSL for precise filter and query construction.

## Grammar

```
symbol{param1=value1, param2=value2}
```

Values can be:
- Strings: `"hello"`
- Numbers: `42`, `3.14`
- Booleans: `true`, `false`
- Null: `null`
- Nested symbols: `symbol{...}`
- Lists: `[item1, item2, ...]`

## Filter Symbols (used in `filter_dsl` param)

| Symbol | Type |
|--------|------|
| `ƒ` | Filter |
| `ʄ` | FieldCondition |
| `☆` | MatchValue |
| `ɱ` | MatchAny |
| `ṁ` | MatchText |
| `ř` | Range |
| `ℏ` | HasIdCondition |
| `I_0` | IsNullCondition |
| `I_2` | IsEmptyCondition |

## Query Symbols (used in `query_dsl`/`prefetch_dsl` params)

| Symbol | Type |
|--------|------|
| `R_4` | RecommendQuery |
| `D_2` | DiscoverQuery |
| `φ` | FusionQuery |
| `¶` | Prefetch |
| `ø` | OrderBy |
| `ɵ` | OrderByQuery |
| `C_0` | ContextQuery |
| `♦` | SearchParams |

## Examples

- `ƒ{must=[ʄ{key="tool_name", match=☆{value="search"}}]}` — Filter by tool_name
- `ƒ{must=[ʄ{key="tool_name", match=ɱ{any=["send_dynamic_card", "search"]}}]}` — Match any of multiple values
- `ƒ{must=[ʄ{key="score", range=ř{gte=0.5}}]}` — Range filter
