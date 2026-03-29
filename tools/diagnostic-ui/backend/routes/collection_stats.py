"""Collection statistics routes using Qdrant facet API.

Provides real-time collection composition data (point type distribution,
feedback breakdown, etc.) without scrolling through all points.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_wrapper(domain: str = "card"):
    """Get the appropriate module wrapper for the domain."""
    if domain == "email":
        from gmail.email_wrapper_setup import get_email_wrapper
        return get_email_wrapper()
    else:
        from gchat.card_framework_wrapper import get_card_framework_wrapper
        return get_card_framework_wrapper()


@router.get("/collection/stats")
async def collection_stats(domain: str = Query("card", description="Domain: card or email")):
    """Get collection composition using Qdrant facet API.

    Returns distribution of point types, feedback values, and other
    payload field cardinalities — without scrolling the full collection.
    """
    try:
        wrapper = _get_wrapper(domain)
        client = wrapper.client
        collection_name = wrapper.collection_name

        # Get basic collection info
        info = client.get_collection(collection_name)
        total_points = info.points_count

        facets = {}

        # Facet by type (class, instance_pattern, function, variable, etc.)
        for field in ["type", "content_feedback", "form_feedback"]:
            try:
                result = client.facet(
                    collection_name=collection_name,
                    key=field,
                )
                facets[field] = [
                    {"value": hit.value, "count": hit.count}
                    for hit in result.hits
                ]
            except Exception as e:
                logger.debug("Facet on '%s' failed: %s", field, e)
                facets[field] = None

        return {
            "collection": collection_name,
            "domain": domain,
            "total_points": total_points,
            "facets": facets,
        }

    except Exception as e:
        logger.error("Collection stats failed: %s", e)
        return {"error": str(e), "facets": {}}


@router.get("/collection/type-distribution")
async def type_distribution(domain: str = Query("card", description="Domain: card or email")):
    """Focused endpoint: just the type distribution for charts."""
    try:
        wrapper = _get_wrapper(domain)
        client = wrapper.client

        result = client.facet(
            collection_name=wrapper.collection_name,
            key="type",
        )

        distribution = {hit.value: hit.count for hit in result.hits}
        total = sum(distribution.values())

        return {
            "distribution": distribution,
            "total": total,
            "domain": domain,
        }

    except Exception as e:
        logger.error("Type distribution failed: %s", e)
        return {"error": str(e), "distribution": {}}
