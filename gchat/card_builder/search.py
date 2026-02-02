"""
Search and pattern extraction utilities for card components.

This module provides standalone functions for extracting component information
from Qdrant search results and pattern data.
"""

import logging
import re
from typing import Any, Dict, List

from adapters.module_wrapper.types import ComponentPaths, JsonDict, Payload

logger = logging.getLogger(__name__)


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


__all__ = [
    "extract_paths_from_pattern",
    "extract_style_metadata_from_pattern",
    "has_style_metadata",
    "find_pattern_with_styles",
]
