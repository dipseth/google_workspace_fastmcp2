# SmartCardBuilder Migration Plan

## Current State

**smart_card_builder.py**: 5,564 lines (reduced from 5,838, -274 lines)
**card_builder/ package**: ~2,500+ lines (growing as we migrate)

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

## To Migrate

### Phase 1: Core Utilities (Small, Independent) ✅ COMPLETE

| Function/Method | Target File | Lines | Status |
|-----------------|-------------|-------|--------|
| `_convert_to_camel_case()` | `rendering.py` | ~20 | ✅ Done |
| `_get_json_key()` | `rendering.py` | ~10 | ✅ Done |
| `_json_key_to_component_name()` | `rendering.py` | ~10 | ✅ Done |
| `_format_text_for_chat()` | `jinja_styling.py` | ~30 | Deferred |
| `_process_text_with_jinja()` | `jinja_styling.py` | ~40 | Deferred |
| `_get_jinja_env()` | `jinja_styling.py` | ~50 | Deferred |

### Phase 2: DSL Parsing (New File: dsl.py) ✅ COMPLETE

| Function/Method | Target File | Lines | Status |
|-----------------|-------------|-------|--------|
| `_get_dsl_parser()` | Stays in builder | ~10 | Thin wrapper |
| `_parse_content_dsl()` | Stays in builder | ~100 | Uses wrapper |
| `_extract_structure_dsl()` | Stays in builder | ~20 | Uses wrapper |
| `_extract_component_paths()` | `dsl.py` | ~30 | ✅ Done |
| `generate_dsl_notation()` | `dsl.py` | ~50 | ✅ Done |
| `suggest_dsl_for_params()` | `dsl.py` | ~40 | ✅ Done |

### Phase 3: Qdrant/Search (New File: search.py)

| Function/Method | Target File | Lines | Priority |
|-----------------|-------------|-------|----------|
| `_get_qdrant_client()` | `search.py` | ~20 | MEDIUM |
| `_query_qdrant_patterns()` | `search.py` | ~100 | MEDIUM |
| `_query_wrapper_patterns()` | `search.py` | ~80 | MEDIUM |
| `_generate_pattern_from_wrapper()` | `search.py` | ~60 | MEDIUM |
| `_get_cached_pattern()` | `search.py` | ~30 | MEDIUM |
| `_cache_pattern()` | `search.py` | ~20 | MEDIUM |
| `_get_cache_key()` | `search.py` | ~15 | MEDIUM |
| `_store_card_pattern()` | `search.py` | ~80 | MEDIUM |

### Phase 4: Component Building (New File: builder.py)

| Function/Method | Target File | Lines | Priority |
|-----------------|-------------|-------|----------|
| `_build_component()` | `builder.py` | ~200 | HIGH |
| `_build_widget_generic()` | `builder.py` | ~100 | HIGH |
| `_build_widget_fallback()` | `builder.py` | ~80 | HIGH |
| `_build_container_generic()` | `builder.py` | ~150 | HIGH |
| `_build_columns_generic()` | `builder.py` | ~80 | MEDIUM |
| `_build_child_widget()` | `builder.py` | ~60 | MEDIUM |
| `_find_required_wrapper_via_dag()` | `builder.py` | ~80 | MEDIUM |
| `build_component_tree()` | `builder.py` | ~50 | HIGH |

### Phase 5: Widget Helpers (Add to rendering.py)

| Function/Method | Target File | Lines | Priority |
|-----------------|-------------|-------|----------|
| `_build_button_via_wrapper()` | `rendering.py` | ~40 | MEDIUM |
| `_build_icon_via_wrapper()` | `rendering.py` | ~30 | MEDIUM |
| `_build_onclick_via_wrapper()` | `rendering.py` | ~30 | MEDIUM |
| `_build_switch_via_wrapper()` | `rendering.py` | ~30 | MEDIUM |
| `_build_material_icon()` | `rendering.py` | ~20 | MEDIUM |
| `_build_start_icon()` | `rendering.py` | ~20 | MEDIUM |

### Phase 6: Style Application (Add to jinja_styling.py)

| Function/Method | Target File | Lines | Priority |
|-----------------|-------------|-------|----------|
| `_has_explicit_styles()` | `jinja_styling.py` | ~20 | MEDIUM |
| `_apply_pattern_styles()` | `jinja_styling.py` | ~60 | MEDIUM |
| `_apply_style_to_text()` | `jinja_styling.py` | ~40 | MEDIUM |
| `_apply_styles()` | `jinja_styling.py` | ~30 | MEDIUM |
| `_apply_styles_recursively()` | `jinja_styling.py` | ~40 | MEDIUM |
| `_get_style_for_text()` | `jinja_styling.py` | ~30 | MEDIUM |
| `_style_keyword()` | `jinja_styling.py` | ~20 | LOW |
| `_style_feedback_keyword()` | `jinja_styling.py` | ~20 | LOW |

### Phase 7: Feedback Building (Add to feedback/)

| Function/Method | Target File | Lines | Priority |
|-----------------|-------------|-------|----------|
| `_build_feedback_widget()` | `feedback/widgets.py` | ~100 | MEDIUM |
| `_build_feedback_layout()` | `feedback/widgets.py` | ~80 | MEDIUM |
| `_build_clickable_feedback()` | `feedback/widgets.py` | ~60 | MEDIUM |
| `_build_text_feedback()` | `feedback/widgets.py` | ~40 | MEDIUM |
| `_build_styled_feedback_prompt()` | `feedback/widgets.py` | ~50 | MEDIUM |
| `_create_feedback_section()` | `feedback/widgets.py` | ~60 | MEDIUM |
| `build_feedback_for_container()` | `feedback/widgets.py` | ~80 | MEDIUM |
| All `_click_*` methods | `feedback/click_handlers.py` | ~200 | LOW |
| All `_text_*` methods | `feedback/text_handlers.py` | ~150 | LOW |
| All `_dual_*` methods | `feedback/dual_handlers.py` | ~100 | LOW |
| All `_layout_*` methods | `feedback/layout_handlers.py` | ~100 | LOW |

### Phase 8: Main Builder Class (builder_v2.py)

After phases 1-7, `SmartCardBuilderV2` should only contain:
- `__init__()` - initialization
- `build()` - main entry point
- `build_card_from_description()` - DSL-based building
- `build_card_v2()` - alternative entry point
- Orchestration methods that call the extracted modules

### Phase 9: Top-Level Functions

| Function | Target File | Status |
|----------|-------------|--------|
| `get_smart_card_builder()` | `__init__.py` | Keep as factory |
| `reset_builder()` | `__init__.py` | Keep |
| `build_card()` | `__init__.py` | Keep as convenience |
| `suggest_dsl_for_params()` | `dsl.py` | Move |

## Execution Order

1. **Phase 1** - Core utilities (rendering.py, jinja_styling.py updates)
2. **Phase 2** - DSL parsing (new dsl.py)
3. **Phase 4** - Component building (new builder.py) - depends on Phase 1
4. **Phase 3** - Search/Qdrant (new search.py)
5. **Phase 5** - Widget helpers (rendering.py updates)
6. **Phase 6** - Style application (jinja_styling.py updates)
7. **Phase 7** - Feedback building (feedback/ updates)
8. **Phase 8** - Refactor SmartCardBuilderV2 to use extracted modules
9. **Phase 9** - Clean up top-level functions

## Testing Strategy

After each phase:
1. Run `gchat/testing/test_build_component.py`
2. Run `gchat/testing/test_auto_wrap.py`
3. Run `gchat/testing/test_return_instance.py`
4. Run `gchat/testing/test_style_auto_application.py`
5. Test via MCP: `send_dynamic_card` with various DSL patterns

## Files to Create

```
gchat/card_builder/
├── __init__.py          (exists - update exports)
├── constants.py         (exists)
├── metadata.py          (exists)
├── utils.py             (exists)
├── rendering.py         (exists - expand)
├── jinja_styling.py     (exists - expand)
├── prepared_pattern.py  (exists - updated)
├── dsl.py               (NEW)
├── search.py            (NEW)
├── builder.py           (NEW)
└── feedback/
    ├── __init__.py      (exists)
    ├── dynamic.py       (exists)
    ├── prompts.py       (exists)
    ├── icons.py         (exists)
    ├── components.py    (exists)
    ├── registries.py    (exists)
    ├── widgets.py       (NEW)
    ├── click_handlers.py (NEW - optional)
    ├── text_handlers.py  (NEW - optional)
    └── layout_handlers.py (NEW - optional)
```

## Success Criteria

- `smart_card_builder.py` reduced to < 1000 lines (orchestration only)
- All functionality preserved and tested
- No breaking changes to existing imports
- `card_builder/` package is the canonical source
