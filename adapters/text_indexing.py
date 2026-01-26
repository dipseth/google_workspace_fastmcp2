"""
Qdrant Text Indexing Helpers

Provides optimized full-text index configurations for semantic search
on component metadata. These complement vector embeddings for:
- Fast keyword lookups
- Fuzzy matching via stemming
- Phrase matching for multi-word names
- Language-aware stopword filtering

Usage:
    from adapters.text_indexing import create_component_text_indices

    client = get_qdrant_client()
    create_component_text_indices(client, "mcp_gchat_cards_v7")
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def create_component_text_indices(
    client,
    collection_name: str,
    enable_stemming: bool = True,
    enable_stopwords: bool = True,
    enable_phrase_matching: bool = True,
    enable_ascii_folding: bool = True,
    custom_stopwords: Optional[List[str]] = None,
) -> int:
    """
    Create optimized text indices for component search.

    Creates indices on:
    - name: Component names with phrase matching
    - docstring: Documentation with stemming/stopwords
    - relationships.nl_descriptions: NL relationship descriptions

    Args:
        client: Qdrant client instance
        collection_name: Collection to add indices to
        enable_stemming: Enable Snowball English stemmer
        enable_stopwords: Enable English stopwords removal
        enable_phrase_matching: Enable phrase search on names
        enable_ascii_folding: Enable Unicode→ASCII normalization
        custom_stopwords: Additional stopwords to filter

    Returns:
        Number of indices created
    """
    from qdrant_client import models

    indices_created = 0

    # Default domain-specific stopwords
    domain_stopwords = custom_stopwords or [
        "widget",  # Too generic
        "component",  # Too generic
        "google",  # Domain noise
        "chat",  # Domain noise
    ]

    try:
        # 1. Component name index - phrase matching for multi-word names
        logger.info(f"📝 Creating text index on 'name' field...")
        client.create_payload_index(
            collection_name=collection_name,
            field_name="name",
            field_schema=models.TextIndexParams(
                type=models.TextIndexType.TEXT,
                tokenizer=models.TokenizerType.WORD,
                lowercase=True,
                phrase_matching=enable_phrase_matching,
            ),
        )
        indices_created += 1
        logger.info("✅ Created 'name' text index")

    except Exception as e:
        if "already exists" in str(e).lower():
            logger.debug("'name' index already exists")
        else:
            logger.warning(f"Failed to create 'name' index: {e}")

    try:
        # 2. Docstring index - full NLP treatment
        logger.info(f"📝 Creating text index on 'docstring' field...")

        docstring_params = {
            "type": models.TextIndexType.TEXT,
            "tokenizer": models.TokenizerType.WORD,
            "lowercase": True,
        }

        if enable_ascii_folding:
            docstring_params["ascii_folding"] = True

        if enable_stemming:
            docstring_params["stemmer"] = models.SnowballParams(
                type=models.Snowball.SNOWBALL,
                language=models.SnowballLanguage.ENGLISH,
            )

        if enable_stopwords:
            docstring_params["stopwords"] = models.StopwordsSet(
                languages=[models.Language.ENGLISH],
                custom=domain_stopwords,
            )

        client.create_payload_index(
            collection_name=collection_name,
            field_name="docstring",
            field_schema=models.TextIndexParams(**docstring_params),
        )
        indices_created += 1
        logger.info("✅ Created 'docstring' text index")

    except Exception as e:
        if "already exists" in str(e).lower():
            logger.debug("'docstring' index already exists")
        else:
            logger.warning(f"Failed to create 'docstring' index: {e}")

    try:
        # 3. Relationship NL descriptions - stemming for NL matching
        logger.info(f"📝 Creating text index on 'relationships.nl_descriptions'...")

        nl_params = {
            "type": models.TextIndexType.TEXT,
            "tokenizer": models.TokenizerType.WORD,
            "lowercase": True,
        }

        if enable_stemming:
            nl_params["stemmer"] = models.SnowballParams(
                type=models.Snowball.SNOWBALL,
                language=models.SnowballLanguage.ENGLISH,
            )

        client.create_payload_index(
            collection_name=collection_name,
            field_name="relationships.nl_descriptions",
            field_schema=models.TextIndexParams(**nl_params),
        )
        indices_created += 1
        logger.info("✅ Created 'relationships.nl_descriptions' text index")

    except Exception as e:
        if "already exists" in str(e).lower():
            logger.debug("'relationships.nl_descriptions' index already exists")
        else:
            logger.warning(
                f"Failed to create 'relationships.nl_descriptions' index: {e}"
            )

    try:
        # 4. Full path index - for exact path lookups
        logger.info(f"📝 Creating text index on 'full_path' field...")
        client.create_payload_index(
            collection_name=collection_name,
            field_name="full_path",
            field_schema=models.TextIndexParams(
                type=models.TextIndexType.TEXT,
                tokenizer=models.TokenizerType.WORD,
                lowercase=True,
            ),
        )
        indices_created += 1
        logger.info("✅ Created 'full_path' text index")

    except Exception as e:
        if "already exists" in str(e).lower():
            logger.debug("'full_path' index already exists")
        else:
            logger.warning(f"Failed to create 'full_path' index: {e}")

    logger.info(f"📊 Created {indices_created} text indices on {collection_name}")
    return indices_created


def search_by_text(
    client,
    collection_name: str,
    field: str,
    query: str,
    limit: int = 10,
    is_phrase: bool = False,
) -> list:
    """
    Search collection using text index.

    Args:
        client: Qdrant client
        collection_name: Collection to search
        field: Field to search on
        query: Search query
        limit: Max results
        is_phrase: If True, treat query as exact phrase

    Returns:
        List of matching points
    """
    from qdrant_client import models

    # Wrap in quotes for phrase search
    search_text = f'"{query}"' if is_phrase else query

    results, _ = client.scroll(
        collection_name=collection_name,
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

    return results


def search_components_by_relationship(
    client,
    collection_name: str,
    relationship_query: str,
    limit: int = 10,
) -> list:
    """
    Search components by their relationship descriptions.

    Uses the stemmed text index for fuzzy NL matching.

    Args:
        client: Qdrant client
        collection_name: Collection to search
        relationship_query: NL query like "button with icon"
        limit: Max results

    Returns:
        List of matching component points
    """
    return search_by_text(
        client,
        collection_name,
        "relationships.nl_descriptions",
        relationship_query,
        limit=limit,
    )


# =============================================================================
# MULTI-MODULE SUPPORT
# =============================================================================


def create_module_field_index(
    client,
    collection_name: str,
) -> bool:
    """
    Create a keyword index on the 'module' field for multi-module filtering.

    This enables fast filtering by module prefix when the same collection
    contains components from multiple modules.

    Args:
        client: Qdrant client
        collection_name: Collection to index

    Returns:
        True if created, False if already exists or failed
    """
    from qdrant_client import models

    try:
        client.create_payload_index(
            collection_name=collection_name,
            field_name="module",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        logger.info(f"✅ Created 'module' keyword index on {collection_name}")
        return True

    except Exception as e:
        if "already exists" in str(e).lower():
            logger.debug("'module' index already exists")
            return False
        logger.warning(f"Failed to create 'module' index: {e}")
        return False


def search_within_module(
    client,
    collection_name: str,
    module_name: str,
    text_query: str,
    field: str = "name",
    limit: int = 10,
) -> list:
    """
    Search within a specific module.

    Args:
        client: Qdrant client
        collection_name: Collection to search
        module_name: Module to filter by (e.g., "card_framework", "gmail")
        text_query: Text to search for
        field: Field to search in
        limit: Max results

    Returns:
        List of matching points
    """
    from qdrant_client import models

    results, _ = client.scroll(
        collection_name=collection_name,
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

    return results
