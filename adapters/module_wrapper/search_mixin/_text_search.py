"""Text index search methods: search_by_text, search_by_relationship_text, search_within_module."""

from typing import Any, Dict, List

from adapters.module_wrapper.types import (
    Payload,
    QueryText,
)
from config.enhanced_logging import setup_logger

logger = setup_logger()


def search_by_text(
    self,
    field: str,
    query: QueryText,
    limit: int = 10,
    is_phrase: bool = False,
) -> List[Payload]:
    """
    Search collection using Qdrant text index.

    Args:
        field: Field to search on (e.g., "name", "docstring")
        query: Search query
        limit: Max results
        is_phrase: If True, treat query as exact phrase

    Returns:
        List of matching points with payloads
    """
    if not self.client:
        logger.warning("Cannot search: Qdrant client not available")
        return []

    try:
        from qdrant_client import models

        # Wrap in quotes for phrase search
        search_text = f'"{query}"' if is_phrase else query

        results, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key=field,
                        match=models.MatchText(text=search_text),
                    )
                ]
            ),
            limit=limit,
            with_payload=True,
        )

        # Convert to standard result format
        return [
            {
                "id": point.id,
                "name": point.payload.get("name"),
                "type": point.payload.get("type"),
                "full_path": point.payload.get("full_path"),
                "symbol": point.payload.get("symbol"),
                "docstring": point.payload.get("docstring", "")[:200],
                "score": 1.0,  # Text matches don't have scores
            }
            for point in results
        ]

    except Exception as e:
        logger.error(f"Text search failed: {e}")
        return []


def search_by_relationship_text(
    self,
    query: QueryText,
    limit: int = 10,
) -> List[Payload]:
    """
    Search components by their relationship descriptions.

    Uses the stemmed text index for fuzzy NL matching.

    Args:
        query: NL query like "button with icon"
        limit: Max results

    Returns:
        List of matching component points
    """
    return self.search_by_text(
        field="relationships.nl_descriptions",
        query=query,
        limit=limit,
    )


def search_within_module(
    self,
    module_name: str,
    text_query: str,
    field: str = "name",
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Search within a specific module.

    Args:
        module_name: Module to filter by (e.g., "card_framework", "gmail")
        text_query: Text to search for
        field: Field to search in
        limit: Max results

    Returns:
        List of matching points
    """
    if not self.client:
        logger.warning("Cannot search: Qdrant client not available")
        return []

    try:
        from qdrant_client import models

        results, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="module",
                        match=models.MatchValue(value=module_name),
                    ),
                    models.FieldCondition(
                        key=field,
                        match=models.MatchText(text=text_query),
                    ),
                ]
            ),
            limit=limit,
            with_payload=True,
        )

        return [
            {
                "id": point.id,
                "name": point.payload.get("name"),
                "type": point.payload.get("type"),
                "full_path": point.payload.get("full_path"),
                "symbol": point.payload.get("symbol"),
                "docstring": point.payload.get("docstring", "")[:200],
                "score": 1.0,
            }
            for point in results
        ]

    except Exception as e:
        logger.error(f"Module-scoped search failed: {e}")
        return []
