"""DSL-aware search methods: extract_dsl_from_text, search_by_dsl, search_by_dsl_hybrid."""

import re
from typing import Any, Dict, List, Optional

from config.enhanced_logging import setup_logger

logger = setup_logger()


def extract_dsl_from_text(self, text: str) -> Dict[str, Any]:
    """
    Extract DSL notation from arbitrary text.

    Finds DSL patterns like "section[delta, B[p*2]]" within natural language text
    and separates the DSL from the description.

    Args:
        text: Any text that may contain DSL notation

    Returns:
        Dict with:
            - dsl: Extracted DSL string (or None if not found)
            - description: Remaining text after DSL extraction
            - has_dsl: Whether DSL was found
            - components: Parsed component info (if DSL found)

    Examples:
        >>> extract_dsl_from_text("section[delta, B[p*2]] Build a status card")
        {"dsl": "section[delta, B[p*2]]", "description": "Build a status card", ...}

        >>> extract_dsl_from_text("Build a card with buttons")
        {"dsl": None, "description": "Build a card with buttons", "has_dsl": False}
    """
    # Get all known symbols for pattern matching
    all_symbols = set()
    if hasattr(self, "symbol_mapping"):
        all_symbols.update(self.symbol_mapping.values())
    if hasattr(self, "reverse_symbol_mapping"):
        all_symbols.update(self.reverse_symbol_mapping.keys())

    text = text.strip()
    if not text:
        return {
            "dsl": None,
            "description": text,
            "has_dsl": False,
            "inline_symbols": [],
            "components": [],
            "component_paths": [],
            "is_valid": False,
        }

    # Check if text starts with a known symbol
    first_char = text[0] if text else ""
    if first_char not in all_symbols:
        # No DSL at start - check for inline symbols
        inline_symbols = []
        for symbol in all_symbols:
            if symbol in text:
                comp_name = (
                    self.reverse_symbol_mapping.get(symbol)
                    if hasattr(self, "reverse_symbol_mapping")
                    else None
                )
                if comp_name:
                    inline_symbols.append({"symbol": symbol, "name": comp_name})

        return {
            "dsl": None,
            "description": text,
            "has_dsl": False,
            "inline_symbols": inline_symbols,
            "components": [],
            "component_paths": [],
            "is_valid": False,
        }

    # Extract DSL using bracket counting (handles nested brackets correctly)
    def extract_balanced_dsl(s: str) -> tuple:
        """Extract DSL with balanced brackets from start of string."""
        if not s:
            return "", s

        # Start with first symbol
        ii = 1
        if ii >= len(s) or s[ii] != "[":
            # Symbol without brackets - just the symbol
            return s[0], s[1:].strip()

        # Count brackets to find end of DSL
        bracket_count = 0
        for ii, char in enumerate(s):
            if char == "[":
                bracket_count += 1
            elif char == "]":
                bracket_count -= 1
                if bracket_count == 0:
                    # Found the end of DSL
                    dsl_part = s[: ii + 1]
                    remaining = s[ii + 1 :].strip()
                    return dsl_part, remaining

        # Unbalanced brackets - take up to first space or end
        space_idx = s.find(" ")
        if space_idx > 0:
            return s[:space_idx], s[space_idx:].strip()
        return s, ""

    dsl_part, remaining = extract_balanced_dsl(text)

    if dsl_part:
        # Clean up remaining text - remove leading separators (| and ::)
        remaining = re.sub(r"^[\s\|:]+", "", remaining).strip()

        # Parse the DSL to get component info if parse_dsl_to_components exists
        parsed = {}
        if hasattr(self, "parse_dsl_to_components"):
            parsed = self.parse_dsl_to_components(dsl_part)

        return {
            "dsl": dsl_part,
            "description": remaining if remaining else text,
            "has_dsl": True,
            "full_match": dsl_part,
            "components": parsed.get("components", []),
            "component_paths": parsed.get("component_paths", []),
            "is_valid": parsed.get("is_valid", False),
        }

    # Fallback - no DSL found
    return {
        "dsl": None,
        "description": text,
        "has_dsl": False,
        "inline_symbols": [],
        "components": [],
        "component_paths": [],
        "is_valid": False,
    }


def search_by_dsl(
    self,
    text: str,
    limit: int = 10,
    score_threshold: float = 0.3,
    vector_name: str = "components",
    token_ratio: float = 1.0,
    type_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search Qdrant using DSL symbols extracted from text.

    Extracts DSL notation from the input text, embeds it using ColBERT,
    and searches against the specified vector (components/inputs).

    This method is optimized for queries that contain DSL symbols at the
    start, which provide strong semantic signal for matching.

    Args:
        text: Text containing DSL notation (e.g., "section[delta, B[p*2]] status card")
        limit: Maximum results to return
        score_threshold: Minimum similarity score
        vector_name: Which vector to search ("components" or "inputs")
        token_ratio: Fraction of ColBERT tokens to use (0.0-1.0).
                     Lower values = faster but potentially less accurate.
        type_filter: Optional filter for point type ("class", "instance_pattern")

    Returns:
        List of matching results with scores and payloads

    Example:
        >>> results = wrapper.search_by_dsl("section[delta, B[p*2]] Build a card")
        >>> results[0]["name"]  # "DecoratedText" or similar
    """
    if not self.client:
        logger.warning("Cannot search: Qdrant client not available")
        return []

    # Extract DSL from text
    extracted = self.extract_dsl_from_text(text)

    # Build the search query - prioritize DSL if found
    if extracted["has_dsl"]:
        # Use DSL + description for search (DSL symbols at start)
        search_query = f"{extracted['dsl']} {extracted['description']}"
        logger.info(
            f"DSL search: '{extracted['dsl']}' + '{extracted['description'][:30]}...'"
        )
    else:
        # No DSL found - use full text
        search_query = text
        logger.info(f"Text search (no DSL): '{text[:50]}...'")

    # Generate ColBERT embedding
    vectors = self._embed_with_colbert(search_query, token_ratio)
    if not vectors:
        logger.warning("ColBERT embedding failed for DSL search")
        return []

    try:
        from qdrant_client import models

        # Build filter
        filter_conditions = []
        if type_filter:
            filter_conditions.append(
                models.FieldCondition(
                    key="type",
                    match=models.MatchValue(value=type_filter),
                )
            )

        query_filter = (
            models.Filter(must=filter_conditions) if filter_conditions else None
        )

        # Search against the specified vector
        results = self.client.query_points(
            collection_name=self.collection_name,
            query=vectors,
            using=vector_name,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )

        # Process results
        processed = []
        for point in results.points:
            payload = point.payload or {}
            processed.append(
                {
                    "id": point.id,
                    "score": point.score,
                    "name": payload.get("name"),
                    "type": payload.get("type"),
                    "full_path": payload.get("full_path"),
                    "symbol": payload.get("symbol"),
                    "docstring": payload.get("docstring", "")[:200],
                    "parent_paths": payload.get("parent_paths", []),
                    "card_description": payload.get("card_description", ""),
                    "relationship_text": payload.get("relationship_text", ""),
                }
            )

        logger.info(
            f"DSL search found {len(processed)} results "
            f"(vector={vector_name}, tokens={len(vectors)})"
        )
        return processed

    except Exception as e:
        logger.error(f"DSL search failed: {e}")
        return []


def search_by_dsl_hybrid(
    self,
    text: str,
    limit: int = 10,
    score_threshold: float = 0.3,
    token_ratio: float = 1.0,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Hybrid search using both components and inputs vectors.

    Searches against both ColBERT vectors and returns categorized results.
    Useful for finding both class definitions and usage patterns.

    Args:
        text: Text containing DSL notation
        limit: Maximum results per category
        score_threshold: Minimum similarity score
        token_ratio: Fraction of ColBERT tokens to use

    Returns:
        Dict with "classes" and "patterns" result lists
    """
    # Search for class definitions
    class_results = self.search_by_dsl(
        text=text,
        limit=limit,
        score_threshold=score_threshold,
        vector_name="components",
        token_ratio=token_ratio,
        type_filter="class",
    )

    # Search for usage patterns
    pattern_results = self.search_by_dsl(
        text=text,
        limit=limit,
        score_threshold=score_threshold,
        vector_name="inputs",
        token_ratio=token_ratio,
        type_filter="instance_pattern",
    )

    return {
        "classes": class_results,
        "patterns": pattern_results,
        "query_info": self.extract_dsl_from_text(text),
    }
