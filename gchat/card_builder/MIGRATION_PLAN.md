# SmartCardBuilder Migration Plan

## Current State (Updated 2026-03-23)

**builder_v2.py**: 1,897 lines (reduced from 3,750 original — **49% reduction**)
**card_builder/ package**: 17 modules + feedback subpackage (6 files)

## Already Migrated ✅

| Original Location | New Location | Status |
|-------------------|--------------|--------|
| `fire_and_forget()` | `card_builder/utils.py` | ✅ Done |
| `get_context_resource()` | `card_builder/metadata.py` | ✅ Done |
| `get_children_field()` | `card_builder/metadata.py` | ✅ Done |
| `get_container_child_type()` | `card_builder/metadata.py` | ✅ Done |
| `is_form_component()` | `card_builder/metadata.py` | ✅ Done |
| `is_empty_component()` | `card_builder/metadata.py` | ✅ Done |
| `extract_style_metadata()` | `card_builder/jinja_styling.py` | ✅ Done |
| `DynamicFeedbackBuilder` | `card_builder/feedback/dynamic.py` | ✅ Done |
| `InputMappingReport` | `card_builder/prepared_pattern.py` | ✅ Done |
| `PreparedPattern` | `card_builder/prepared_pattern.py` | ✅ Done |
| `COMPONENT_PARAMS` | `card_builder/constants.py` | ✅ Done |
| `COMPONENT_PATHS` | `card_builder/constants.py` | ✅ Done |
| `FEEDBACK_DETECTION_PATTERNS` | `card_builder/constants.py` | ✅ Done |
| Feedback prompts/icons | `card_builder/feedback/` | ✅ Done |
| `prepare_children_for_container()` | `card_builder/rendering.py` | ✅ Done |
| `_get_json_key()` | `card_builder/rendering.py` | ✅ Done (Phase 1) |
| `_json_key_to_component_name()` | `card_builder/rendering.py` | ✅ Done (Phase 1) |
| `_convert_to_camel_case()` | `card_builder/rendering.py` | ✅ Done (Phase 1) |
| `_extract_component_paths()` | `card_builder/dsl.py` | ✅ Done (Phase 2) |
| `generate_dsl_notation()` | `card_builder/dsl.py` | ✅ Done (Phase 2) |
| `suggest_dsl_for_params()` | `card_builder/dsl.py` | ✅ Done (Phase 2) |
| `_apply_styles()` | `card_builder/jinja_styling.py` | ✅ Done (Styling) |
| `_style_keyword()` | `card_builder/jinja_styling.py` | ✅ Done (Styling) |
| `_style_feedback_keyword()` | `card_builder/jinja_styling.py` | ✅ Done (Styling) |
| All feedback widget methods | `card_builder/feedback/widgets.py` | ✅ Done (Phase 7) |
| Cache functions (3) | `card_builder/search.py` | ✅ Done (Phase 3) |
| Search functions (3) | `card_builder/search.py` | ✅ Done (Phase 3) |
| Storage functions (2) | `card_builder/search.py` | ✅ Done (Phase 3) |
| `_find_required_wrapper_via_dag()` | `adapters/module_wrapper/graph_mixin.py` → `find_required_wrapper()` | ✅ Done (Phase 4) |
| `_build_child_widget()` | `card_builder/rendering.py` → `build_child_widget()` | ✅ Done (Phase 4) |
| `_build_component()` | `card_builder/component_builder.py` → `ComponentBuilder.build_component()` | ✅ Done (Phase 4) |
| `_build_widget_generic()` | `card_builder/component_builder.py` → `ComponentBuilder.build_widget_generic()` | ✅ Done (Phase 4) |
| `_build_container_generic()` | `card_builder/component_builder.py` → `ComponentBuilder.build_container_generic()` | ✅ Done (Phase 4) |
| `_build_columns_generic()` | `card_builder/component_builder.py` → `ComponentBuilder.build_columns_generic()` | ✅ Done (Phase 4) |
| `_map_children_to_params()` | `card_builder/component_builder.py` → `ComponentBuilder._map_children_to_params()` | ✅ Done (Phase 4) |
| `_resolve_child_params()` | `card_builder/component_builder.py` → `ComponentBuilder._resolve_child_params()` | ✅ Done (Phase 4) |
| `_consume_from_context()` | Removed (dead — ComponentBuilder calls `context.consume_from_context()` directly) | ✅ Removed |
| `_convert_to_camel_case()` | Removed (dead — ComponentBuilder calls `rendering.convert_to_camel_case()` directly) | ✅ Removed |
| `_get_default_params()` | Removed (dead — ComponentBuilder calls `constants.get_default_params()` directly) | ✅ Removed |

## Cleanup Summary (2026-03-23)

| Action | Details | Lines Saved |
|--------|---------|-------------|
| Deleted dead code | `_get_style_for_text()`, `_apply_styles_recursively()`, `build_component_tree()` | ~80 |
| Inlined delegators | 4 `_build_*_via_wrapper()` → direct rendering.py calls | ~30 |
| Wired symbol_params | `resolve_symbol_params()` called in `build_from_params()` | +8 |
| Extracted feedback (Phase 7) | 30+ methods → `feedback/widgets.py` (805 lines) | ~575 |
| Extracted search/cache/storage (Phase 3) | 8 methods → `search.py` (expanded to ~480 lines) | ~373 |
| Pushed `find_required_wrapper` upstream (Phase 4) | 76 lines → `graph_mixin.py` method | ~70 |
| Extracted `build_child_widget` (Phase 4) | Registry dispatcher → `rendering.py` | ~45 |
| Extracted component builders (Phase 4) | 6 methods → `ComponentBuilder` class in `component_builder.py` (~530 lines) | ~820 |
| Removed dead methods | `_consume_from_context`, `_convert_to_camel_case`, `_get_default_params`, `_map_children_to_params`, `_resolve_child_params` | ~150 |
| Removed unused imports | `warn_strict`, `ThreadPoolExecutor`, `extract_style_metadata`, 5 metadata functions | ~10 |

**Total reduction: 3,750 → 1,897 lines (49.4%)**

## Phase Status

### Phase 1: Core Utilities ✅ COMPLETE
### Phase 2: DSL Parsing ✅ COMPLETE
### Phase 3: Qdrant/Search ✅ COMPLETE
### Phase 4: Component Building ✅ COMPLETE

Extracted via three strategies:
1. **Pushed upstream** — `find_required_wrapper()` moved to `graph_mixin.py` (pure wrapper query orchestrator)
2. **Module function** — `build_child_widget()` moved to `rendering.py` (registry dispatcher)
3. **ComponentBuilder class** — `component_builder.py` encapsulates the mutually-recursive build pipeline:
   - `build_component()` — universal component builder (DAG auto-wrap, wrapper instantiation)
   - `build_widget_generic()` — mapping-driven widget builder
   - `build_container_generic()` — container builder (ButtonList, Grid, Carousel)
   - `build_columns_generic()` — specialized Columns layout
   - `_map_children_to_params()` / `_resolve_child_params()` — DSL nested child mapping

Builder retains thin delegators + a cached `_get_component_builder()` factory.

### Phase 5: Widget Helpers ✅ COMPLETE (inlined)
### Phase 6: Style Application ✅ COMPLETE (delegators kept)
### Phase 7: Feedback Building ✅ COMPLETE
### Phase 8: Main Builder Refactoring ✅ TARGET MET

builder_v2.py is now **1,897 lines** — below the 2,000 line target. It contains only:
- Entry points: `build()`, `build_from_params()`
- DSL orchestration: `_build_from_dsl()`, `_build_from_pattern()`, `_build_widgets()`
- Infrastructure: `__init__`, `_get_wrapper()`, `_get_qdrant_client()`, `_get_jinja_env()`
- Thin delegators to extracted modules
- Top-level functions: `get_smart_card_builder()`, `reset_builder()`, `build_card()`

### Phase 9: Top-Level Functions — No changes needed

## Files

```
gchat/card_builder/
├── __init__.py            (updated — exports ComponentBuilder, build_child_widget)
├── builder_v2.py          (1,897 lines — orchestration + thin delegators)
├── component_builder.py   (NEW — ComponentBuilder class, ~530 lines)
├── constants.py           (exists)
├── context.py             (exists)
├── dsl.py                 (exists)
├── field_extractors.py    (exists)
├── jinja_styling.py       (exists)
├── metadata.py            (exists)
├── prepared_pattern.py    (exists)
├── rendering.py           (expanded — added build_child_widget)
├── search.py              (expanded — cache, search, storage functions)
├── symbol_params.py       (exists)
├── utils.py               (exists)
├── validation.py          (exists)
└── feedback/
    ├── __init__.py        (exists)
    ├── components.py      (exists)
    ├── dynamic.py         (exists)
    ├── icons.py           (exists)
    ├── prompts.py         (exists)
    ├── registries.py      (exists)
    └── widgets.py         (805 lines)
```

## Upstream Changes

| File | Change | Why |
|------|--------|-----|
| `adapters/module_wrapper/graph_mixin.py` | Added `find_required_wrapper(component, target_parent)` | Pure wrapper query orchestrator — belongs in graph layer, not card builder |

## Success Criteria ✅ ALL MET

- ✅ builder_v2.py < 2,000 lines (1,897)
- ✅ All functionality preserved (thin delegators maintain API compatibility)
- ✅ No breaking changes to existing imports
- ✅ `card_builder/` package is the canonical source
