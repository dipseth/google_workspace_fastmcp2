"""
Search and pattern extraction utilities for card components.

This module provides standalone functions for:
- Extracting component information from Qdrant search results and pattern data
- Pattern cache management (LRU with TTL)
- Querying patterns via wrapper (DSL-aware) and feedback loop (discovery API)
- Generating fallback patterns from card params
- Storing card and feedback UI patterns in Qdrant

Extracted from SmartCardBuilderV2 (Phase 3 of migration plan).
"""

import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from config.enhanced_logging import setup_logger
from adapters.module_wrapper.types import ComponentPaths, JsonDict, Payload

logger = setup_logger()


# =============================================================================
# PATTERN EXTRACTION (existing functions)
# =============================================================================


def extract_paths_from_pattern(pattern: Payload) -> ComponentPaths:
    """
    Extract component paths from a Qdrant pattern result.

    Checks multiple fields in order of preference:
    1. component_paths - direct field
    2. parent_paths - alternate field name used in storage
    3. relationship_text - parse from DSL notation

    Args:
        pattern: Pattern dict from Qdrant query result

    Returns:
        List of component names (e.g., ["Section", "DecoratedText", "ButtonList"])

    Example:
        >>> pattern = {"component_paths": ["Section", "DecoratedText"]}
        >>> extract_paths_from_pattern(pattern)
        ["Section", "DecoratedText"]
    """
    # Try component_paths first
    paths = pattern.get("component_paths", [])
    if paths:
        return paths

    # Try parent_paths (alternate storage field)
    paths = pattern.get("parent_paths", [])
    if paths:
        # Extract just the class name from full paths like "card_framework.v2.widgets.DecoratedText"
        return [p.split(".")[-1] if "." in p else p for p in paths]

    # Parse from relationship_text as fallback
    # Format: "<DSL> | Component Names :: description"
    rel_text = pattern.get("relationship_text", "")
    if rel_text and "|" in rel_text:
        try:
            # Split on | and take the component names part
            parts = rel_text.split("|")
            if len(parts) >= 2:
                # Take the part after the first |
                # Handle both "| names" and "| names :: desc" formats
                names_part = parts[1].split("::")[0].strip()
                # Extract component names (words that look like class names)
                # Filter out counts like "×3" and DSL symbols
                names = re.findall(r"\b([A-Z][a-zA-Z]+)\b", names_part)
                if names:
                    logger.debug(f"Extracted paths from relationship_text: {names}")
                    return names
        except Exception as e:
            logger.debug(f"Failed to parse relationship_text: {e}")

    return []


def extract_style_metadata_from_pattern(pattern: Payload) -> JsonDict:
    """
    Extract style metadata from a pattern's instance_params.

    Args:
        pattern: Pattern dict from Qdrant query result

    Returns:
        Style metadata dict with keys:
        - semantic_styles: ["success", "error", "warning", "info"]
        - jinja_filters: ["success_text", "bold", etc.]
        - formatting: ["bold", "italic", etc.]
        - colors: ["#hexcolor", ...]
    """
    instance_params = pattern.get("instance_params", {})
    return instance_params.get("style_metadata", {})


def has_style_metadata(pattern: Payload) -> bool:
    """Check if a pattern has meaningful style metadata."""
    style_meta = extract_style_metadata_from_pattern(pattern)
    return bool(style_meta.get("semantic_styles") or style_meta.get("jinja_filters"))


def find_pattern_with_styles(patterns: List[Payload]) -> Payload:
    """Find the first pattern with style metadata from a list.

    Args:
        patterns: List of pattern dicts from search results

    Returns:
        First pattern with style metadata, or empty dict if none found
    """
    for pattern in patterns:
        if has_style_metadata(pattern):
            return pattern
    return {}


# =============================================================================
# PATTERN CACHE (extracted from SmartCardBuilderV2)
# =============================================================================


def get_cache_key(
    description: str, card_params: Optional[Dict[str, Any]] = None
) -> str:
    """Generate an MD5 cache key from description and params."""
    params_str = str(sorted(card_params.items())) if card_params else ""
    key_str = f"{description}:{params_str}"
    return hashlib.md5(key_str.encode()).hexdigest()


def get_cached_pattern(
    cache_key: str,
    pattern_cache: Dict[str, Dict[str, Any]],
    pattern_cache_timestamps: Dict[str, float],
    pattern_cache_ttl: float = 300,
) -> Optional[Dict[str, Any]]:
    """Get a cached pattern if valid (not expired).

    Args:
        cache_key: MD5 hash key
        pattern_cache: The cache dict (key -> pattern)
        pattern_cache_timestamps: The timestamps dict (key -> epoch)
        pattern_cache_ttl: Time-to-live in seconds (default 300s / 5 min)

    Returns:
        Cached pattern dict, or None if not found / expired
    """
    if cache_key in pattern_cache:
        timestamp = pattern_cache_timestamps.get(cache_key, 0)
        if time.time() - timestamp < pattern_cache_ttl:
            logger.debug(f"⚡ Cache hit for pattern query: {cache_key[:8]}...")
            return pattern_cache[cache_key]
        else:
            # Expired, remove from cache
            del pattern_cache[cache_key]
            del pattern_cache_timestamps[cache_key]
    return None


def cache_pattern(
    cache_key: str,
    pattern: Optional[Dict[str, Any]],
    pattern_cache: Dict[str, Dict[str, Any]],
    pattern_cache_timestamps: Dict[str, float],
    pattern_cache_max_size: int = 100,
) -> None:
    """Cache a pattern result with LRU eviction.

    Args:
        cache_key: MD5 hash key
        pattern: Pattern to cache (or empty dict for "no result")
        pattern_cache: The cache dict (mutated in place)
        pattern_cache_timestamps: The timestamps dict (mutated in place)
        pattern_cache_max_size: Max entries before LRU eviction
    """
    # Evict oldest entries if cache is full
    if len(pattern_cache) >= pattern_cache_max_size:
        oldest_key = min(
            pattern_cache_timestamps, key=pattern_cache_timestamps.get
        )
        del pattern_cache[oldest_key]
        del pattern_cache_timestamps[oldest_key]

    pattern_cache[cache_key] = pattern
    pattern_cache_timestamps[cache_key] = time.time()


# =============================================================================
# PATTERN SEARCH (extracted from SmartCardBuilderV2)
# =============================================================================


def query_wrapper_patterns(
    description: str,
    card_params: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Query patterns using wrapper's SearchMixin methods (preferred).

    Uses DSL-aware search when DSL symbols are detected in the description,
    otherwise falls back to hybrid V7 search with positive feedback filters.

    Searches are parallelized when DSL is detected for improved latency.

    Args:
        description: Card description (may include DSL symbols)
        card_params: Additional params to include in search context

    Returns:
        Dict with component_paths, instance_params from best match, or None
    """
    try:
        from gchat.card_framework_wrapper import get_card_framework_wrapper

        wrapper = get_card_framework_wrapper()

        # Check for DSL in description (fast, synchronous - determines search strategy)
        extracted = wrapper.extract_dsl_from_text(description)
        has_dsl = extracted.get("has_dsl")

        if has_dsl:
            logger.info(f"🔤 DSL detected: {extracted['dsl']}")

        # Run searches in parallel when DSL is detected (both searches are independent)
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Always submit hybrid search for style_metadata extraction
            hybrid_future = executor.submit(
                wrapper.search_hybrid_dispatch,
                description=description,
                component_paths=None,
                limit=5,
                token_ratio=1.0,
                content_feedback="positive",
                form_feedback="positive",
                include_classes=False,  # Only want patterns
            )

            # Conditionally submit DSL search in parallel
            dsl_future = None
            if has_dsl:
                dsl_future = executor.submit(
                    wrapper.search_by_dsl,
                    text=description,
                    limit=5,
                    score_threshold=0.3,
                    vector_name="inputs",  # Search for patterns
                    type_filter="instance_pattern",
                )

            # Gather results (blocks until complete)
            class_results, content_patterns, form_patterns = hybrid_future.result()
            dsl_results = dsl_future.result() if dsl_future else None

        # Find patterns with actual style_metadata content (for auto-styling)
        styled_pattern = None
        for pattern in content_patterns:
            instance_params = pattern.get("instance_params", {})
            style_meta = instance_params.get("style_metadata", {})
            # Check for actual style content, not just empty dict
            if style_meta.get("semantic_styles") or style_meta.get("jinja_filters"):
                styled_pattern = pattern
                logger.info(f"🎨 Found pattern with style_metadata: {style_meta}")
                break

        # Process DSL results if available
        if dsl_results:
            best = dsl_results[0]
            component_paths = extract_paths_from_pattern(best)
            instance_params = best.get("instance_params", {})

            # Check if DSL result has actual style content (not just empty dict)
            dsl_style = instance_params.get("style_metadata", {})
            dsl_has_styles = dsl_style.get("semantic_styles") or dsl_style.get(
                "jinja_filters"
            )

            # Merge style_metadata from styled_pattern if DSL result lacks actual styles
            if styled_pattern and not dsl_has_styles:
                styled_instance_params = styled_pattern.get("instance_params", {})
                styled_style = styled_instance_params.get("style_metadata", {})
                if styled_style.get("semantic_styles") or styled_style.get(
                    "jinja_filters"
                ):
                    instance_params = {
                        **instance_params,
                        "style_metadata": styled_style,
                    }
                    logger.info(
                        f"🎨 Merged style_metadata from similar pattern: {styled_style}"
                    )

            return {
                "component_paths": component_paths,
                "instance_params": instance_params,
                "structure_description": best.get("structure_description", ""),
                "score": best.get("score", 0),
                "source": "wrapper_dsl",
            }

        # No DSL results - use hybrid search results
        if content_patterns:
            # Prefer patterns with style_metadata
            best = styled_pattern if styled_pattern else content_patterns[0]
            component_paths = extract_paths_from_pattern(best)
            return {
                "component_paths": component_paths,
                "instance_params": best.get("instance_params", {}),
                "structure_description": best.get("structure_description", ""),
                "score": best.get("score", 0),
                "source": "wrapper_hybrid",
            }

        return None

    except Exception as e:
        logger.debug(f"Wrapper pattern search failed: {e}")
        return None


def query_qdrant_patterns(
    description: str,
    card_params: Optional[Dict[str, Any]] = None,
    pattern_cache: Optional[Dict[str, Dict[str, Any]]] = None,
    pattern_cache_timestamps: Optional[Dict[str, float]] = None,
    pattern_cache_ttl: float = 300,
    pattern_cache_max_size: int = 100,
) -> Optional[Dict[str, Any]]:
    """
    Query Qdrant for matching instance patterns with caching.

    First tries wrapper's SearchMixin methods (search_by_dsl, search_hybrid),
    then falls back to feedback_loop.query_with_discovery() using Qdrant's Discovery API.
    Results are cached for 5 minutes to improve performance.

    Args:
        description: Card description (may include DSL symbols)
        card_params: Additional params to include in search context
        pattern_cache: Cache dict (key -> pattern). If None, caching is skipped.
        pattern_cache_timestamps: Timestamps dict (key -> epoch)
        pattern_cache_ttl: Time-to-live in seconds
        pattern_cache_max_size: Max cache entries

    Returns:
        Dict with component_paths, instance_params from best match, or None
    """
    use_cache = pattern_cache is not None and pattern_cache_timestamps is not None

    # Check cache first
    if use_cache:
        ck = get_cache_key(description, card_params)
        cached_result = get_cached_pattern(
            ck, pattern_cache, pattern_cache_timestamps, pattern_cache_ttl
        )
        if cached_result is not None:
            return cached_result if cached_result else None

    # Try wrapper-based search first (DSL-aware, cleaner)
    wrapper_result = query_wrapper_patterns(description, card_params)
    if wrapper_result:
        logger.info(
            f"✅ Wrapper pattern match (source: {wrapper_result.get('source', 'unknown')})"
        )
        if use_cache:
            cache_pattern(
                ck, wrapper_result, pattern_cache, pattern_cache_timestamps,
                pattern_cache_max_size,
            )
        return wrapper_result

    # Fall back to feedback_loop (has negative demotion support)
    try:
        from gchat.feedback_loop import get_feedback_loop

        feedback_loop = get_feedback_loop()

        # Query using description - symbols in description will match
        # symbol-enriched embeddings in Qdrant
        class_results, content_patterns, form_patterns = (
            feedback_loop.query_with_discovery(
                component_query=description,
                description=description,
                limit=5,
            )
        )

        # Use best matching content pattern (has positive content_feedback)
        if content_patterns:
            best_pattern = content_patterns[0]
            logger.info(
                f"🎯 Found Qdrant pattern: {best_pattern.get('structure_description', '')[:50]}..."
            )
            component_paths = extract_paths_from_pattern(best_pattern)
            result = {
                "component_paths": component_paths,
                "instance_params": best_pattern.get("instance_params", {}),
                "structure_description": best_pattern.get(
                    "structure_description", ""
                ),
                "score": best_pattern.get("score", 0),
            }
            if use_cache:
                cache_pattern(
                    ck, result, pattern_cache, pattern_cache_timestamps,
                    pattern_cache_max_size,
                )
            return result

        # If no content patterns, try class results
        if class_results:
            component_paths = [r.get("name", "") for r in class_results[:5]]
            logger.info(f"🔍 Found class components: {component_paths}")
            result = {
                "component_paths": component_paths,
                "instance_params": {},
                "structure_description": f"From classes: {', '.join(component_paths)}",
                "score": class_results[0].get("score", 0) if class_results else 0,
            }
            if use_cache:
                cache_pattern(
                    ck, result, pattern_cache, pattern_cache_timestamps,
                    pattern_cache_max_size,
                )
            return result

        # Cache the "no result" case too (as empty dict)
        if use_cache:
            cache_pattern(
                ck, {}, pattern_cache, pattern_cache_timestamps,
                pattern_cache_max_size,
            )
        return None
    except Exception as e:
        logger.warning(f"Qdrant pattern query failed: {e}")
        return None


def generate_pattern_from_wrapper(
    description: str,
    card_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate a valid instance pattern from card params.

    Determines component_paths based on what params are provided
    (text -> DecoratedText, buttons -> ButtonList, image -> Image, etc.).

    Args:
        description: Original card description
        card_params: Parameters to determine component structure

    Returns:
        Dict with component_paths and instance_params
    """
    # Determine what components to use based on params
    component_paths = ["Section"]  # Always start with Section

    if card_params:
        # Add text component if we have text content
        if card_params.get("text") or card_params.get("description"):
            component_paths.append("DecoratedText")

        # Add button list if we have buttons
        if card_params.get("buttons"):
            component_paths.append("ButtonList")
            # Add individual buttons
            for _ in card_params["buttons"]:
                component_paths.append("Button")

        # Add image if we have image URL
        if card_params.get("image_url"):
            component_paths.append("Image")

    # Default: Section with TextParagraph if nothing specified
    if len(component_paths) == 1:
        component_paths.append("TextParagraph")

    logger.info(f"🔧 Generated pattern: {component_paths}")

    return {
        "component_paths": component_paths,
        "instance_params": card_params or {},
        "structure_description": f"Generated from: {description[:100]}",
    }


# =============================================================================
# PATTERN STORAGE (extracted from SmartCardBuilderV2)
# =============================================================================


def store_card_pattern(
    card_id: str,
    description: str,
    title: Optional[str],
    structure_dsl: Optional[str],
    card: Dict[str, Any],
    description_rendered: Optional[str] = None,
    jinja_applied: bool = False,
    enable_feedback: bool = True,
    supply_map: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Store the main card content pattern in Qdrant.

    This stores ONLY the main card content (pattern_type="content"),
    NOT the feedback UI section which is stored separately.

    Args:
        card_id: Unique ID for this card
        description: Original card description (RAW, before Jinja processing)
        title: Card title
        structure_dsl: DSL structure if parsed
        card: The built card dict (without feedback section)
        description_rendered: Jinja-processed description (if different from raw)
        jinja_applied: Whether Jinja template processing was applied
        enable_feedback: Whether feedback storage is enabled
        supply_map: Post-rendering content values (buttons, items, chips, etc.)
    """
    if not enable_feedback:
        return

    try:
        from gchat.feedback_loop import get_feedback_loop

        from gchat.card_builder.dsl import extract_component_paths
        from gchat.card_builder.jinja_styling import extract_style_metadata

        feedback_loop = get_feedback_loop()

        # Extract component paths from card structure
        component_paths = extract_component_paths(card)

        # Build instance params from card content
        instance_params = {
            "title": title,
            "description": description[:500] if description else "",
            "dsl": structure_dsl,
            "component_count": len(component_paths),
            "description_rendered": (
                description_rendered[:500] if description_rendered else None
            ),
            "jinja_applied": jinja_applied,
        }

        # Extract style metadata from rendered description (or raw if no rendering)
        style_metadata = extract_style_metadata(description_rendered or description)

        # Also scan instance_params for any text fields with Jinja
        for key, value in instance_params.items():
            if isinstance(value, str) and "{{" in value:
                additional_styles = extract_style_metadata(value)
                for style_field in [
                    "jinja_filters",
                    "colors",
                    "semantic_styles",
                    "formatting",
                ]:
                    style_metadata[style_field].extend(
                        additional_styles.get(style_field, [])
                    )

        # Deduplicate after merging
        for key in style_metadata:
            style_metadata[key] = list(set(style_metadata[key]))

        # Store style metadata with instance params
        instance_params["style_metadata"] = style_metadata

        # Build content text from supply_map (actual user content values)
        content_text = ""
        if supply_map:
            from adapters.module_wrapper.pipeline_mixin import (
                extract_content_text_from_params,
            )

            # supply_map keys align with extract_content_text_from_params fields
            content_params = {
                "title": title,
                "buttons": supply_map.get("buttons", []),
                "items": supply_map.get("grid_items", []),
                "content_texts": supply_map.get("content_texts", []),
                "chips": supply_map.get("chips", []),
            }
            content_text = extract_content_text_from_params(
                content_params, description or ""
            )

        # Store the CONTENT pattern (main card, not feedback UI)
        point_id = feedback_loop.store_instance_pattern(
            card_description=description,
            component_paths=component_paths,
            instance_params=instance_params,
            card_id=card_id,
            structure_description=structure_dsl or "",
            pattern_type="content",
            content_text=content_text or None,
        )

        if point_id:
            logger.debug(
                f"📦 Stored content pattern: {card_id[:8]}... -> {point_id[:8]}..."
            )
            if jinja_applied:
                logger.debug(
                    f"   🎨 Jinja rendered: '{description[:30]}...' -> '{description_rendered[:30] if description_rendered else ''}...'"
                )
            if style_metadata.get("semantic_styles") or style_metadata.get(
                "formatting"
            ):
                logger.debug(f"   🎨 Style metadata: {style_metadata}")

    except Exception as e:
        logger.warning(f"⚠️ Failed to store card pattern: {e}")


def store_feedback_ui_pattern(
    card_id: str,
    feedback_section: Dict[str, Any],
    enable_feedback: bool = True,
) -> None:
    """
    Store the feedback UI section pattern in Qdrant.

    This stores the randomly generated feedback UI (pattern_type="feedback_ui"),
    allowing learning of which feedback layouts work best.

    Args:
        card_id: Unique ID for this card (links content + feedback_ui patterns)
        feedback_section: The feedback section dict with _feedback_assembly metadata
        enable_feedback: Whether feedback storage is enabled
    """
    if not enable_feedback:
        return

    try:
        from gchat.feedback_loop import get_feedback_loop

        feedback_loop = get_feedback_loop()

        # Get assembly metadata
        assembly = feedback_section.get("_feedback_assembly", {})
        if not assembly:
            return  # No metadata to store

        # Build description from assembly
        description = (
            f"Feedback UI: {assembly.get('content_text', '?')} + "
            f"{assembly.get('form_text', '?')} in {assembly.get('layout', '?')} layout"
        )

        # Extract component paths from feedback widgets
        from gchat.card_builder.rendering import (
            _JSON_KEY_TO_COMPONENT,
            json_key_to_component_name,
        )

        component_paths = []
        for widget in feedback_section.get("widgets", []):
            for key in widget.keys():
                if key in _JSON_KEY_TO_COMPONENT:
                    component_paths.append(json_key_to_component_name(key))

        # Store the FEEDBACK_UI pattern
        point_id = feedback_loop.store_instance_pattern(
            card_description=description,
            component_paths=component_paths,
            instance_params=assembly,
            card_id=f"{card_id}_feedback",
            structure_description=description,
            pattern_type="feedback_ui",
        )

        if point_id:
            logger.debug(
                f"📦 Stored feedback_ui pattern: {card_id[:8]}... -> {point_id[:8]}..."
            )

    except Exception as e:
        logger.warning(f"⚠️ Failed to store feedback_ui pattern: {e}")


__all__ = [
    # Pattern extraction (existing)
    "extract_paths_from_pattern",
    "extract_style_metadata_from_pattern",
    "has_style_metadata",
    "find_pattern_with_styles",
    # Cache management
    "get_cache_key",
    "get_cached_pattern",
    "cache_pattern",
    # Pattern search
    "query_wrapper_patterns",
    "query_qdrant_patterns",
    "generate_pattern_from_wrapper",
    # Pattern storage
    "store_card_pattern",
    "store_feedback_ui_pattern",
]
