"""
Qdrant Search and Analytics Module

This module contains search and analytics functionality extracted from the main
Qdrant middleware, including:
- Semantic search operations using embeddings
- Advanced query parsing and filtering
- Analytics and reporting on stored data
- Response retrieval and data access
- Unified search with intelligent query routing

This focused module handles all aspects of searching and analyzing data stored
in Qdrant while maintaining async patterns, error handling, and integration
with client management and query parsing modules.
"""

import asyncio
import base64
import gzip
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config.enhanced_logging import setup_logger

from .client import QdrantClientManager
from .config import CollectionSchema
from .lazy_imports import get_qdrant_imports
from .query_parser import (
    format_search_results,
    parse_search_query,
    parse_unified_query,
)

logger = setup_logger()


class QdrantSearchManager:
    """
    Manages search and analytics operations for the Qdrant vector database.

    This class encapsulates all search functionality including:
    - Semantic search with query parsing support
    - Advanced filtering and ID lookup capabilities
    - Analytics and reporting on stored tool responses
    - Response retrieval and data access operations
    - Unified search with intelligent query routing
    - Integration with client management and query parsing
    """

    def __init__(self, client_manager: QdrantClientManager):
        """
        Initialize the Qdrant search manager.

        Args:
            client_manager: QdrantClientManager instance for client operations
        """
        self.client_manager = client_manager
        self.config = client_manager.config

        logger.debug("🔍 QdrantSearchManager initialized")

    def _is_gzipped_data(self, data: bytes) -> bool:
        """
        Check if data is actually gzip compressed by examining magic bytes.

        Args:
            data: Raw bytes to check

        Returns:
            bool: True if data appears to be gzipped
        """
        return len(data) >= 2 and data[:2] == b"\x1f\x8b"

    def _safe_decompress_data(self, compressed_data: bytes) -> Optional[str]:
        """
        Safely decompress data with proper gzip detection and fallback handling.

        Args:
            compressed_data: Potentially compressed bytes data

        Returns:
            Decompressed string data or None if decompression fails
        """
        try:
            # First check if this is actually gzipped data
            if not self._is_gzipped_data(compressed_data):
                logger.debug(
                    "🔍 Data not gzipped (missing magic bytes), treating as plain data"
                )
                # Try to decode as UTF-8 string directly
                try:
                    return compressed_data.decode("utf-8")
                except UnicodeDecodeError:
                    logger.debug("🔍 Data not UTF-8, attempting base64 decode")
                    try:
                        return base64.b64decode(compressed_data).decode("utf-8")
                    except:
                        return None

            # Data appears to be gzipped, attempt decompression
            logger.debug("🔍 Detected gzipped data, decompressing")
            return gzip.decompress(compressed_data).decode("utf-8")

        except gzip.BadGzipFile:
            logger.debug("🔍 Invalid gzip format, treating as plain data")
            try:
                return compressed_data.decode("utf-8")
            except UnicodeDecodeError:
                return None
        except Exception as e:
            logger.debug(f"🔍 Decompression failed: {e}, treating as plain data")
            try:
                return compressed_data.decode("utf-8")
            except UnicodeDecodeError:
                return None

    @property
    def is_initialized(self) -> bool:
        """Check if search manager is fully initialized."""
        return self.client_manager.is_initialized

    def _select_search_vector(self, query_type: str) -> Optional[str]:
        """Select the named vector to search based on query type (v7 schema only).

        Args:
            query_type: One of 'overview', 'service_history', 'general', 'recommend'

        Returns:
            Named vector name for v7 schema, or None for v1 (single vector).
        """
        if self.config.collection_schema != CollectionSchema.V7_NAMED_VECTORS:
            return None

        routing = {
            "overview": "components",
            "service_history": "relationships",
            "general": "inputs",
            "recommend": "relationships",
        }
        return routing.get(query_type, "inputs")

    async def _execute_semantic_search(
        self, query_embedding, qdrant_filter=None, limit=None, score_threshold=None,
        using=None, collection=None,
    ):
        """
        Execute semantic search using query_points (new Qdrant API).

        Args:
            query_embedding: The embedding vector for the query
            qdrant_filter: Optional Qdrant filter
            limit: Maximum number of results
            score_threshold: Minimum similarity score
            using: Optional named vector to search (for v7 schema). None uses default vector.
            collection: Optional collection name override. Uses default if not provided.

        Returns:
            List of ScoredPoint objects from Qdrant
        """
        # Ensure client is initialized
        if not self.client_manager.is_initialized:
            await self.client_manager.initialize()

        if not self.client_manager.is_available:
            raise RuntimeError("Qdrant client not available")

        target_collection = collection or self.config.collection_name
        kwargs = {
            "collection_name": target_collection,
            "query": query_embedding.tolist(),
            "query_filter": qdrant_filter,
            "limit": limit or self.config.default_search_limit,
            "score_threshold": score_threshold or self.config.score_threshold,
            "with_payload": True,
        }
        if using:
            kwargs["using"] = using

        search_response = await asyncio.to_thread(
            self.client_manager.client.query_points,
            **kwargs,
        )
        return search_response.points  # Extract points from response

    async def search(
        self,
        query: str,
        limit: int = None,
        score_threshold: float = None,
        positive_point_ids: Optional[List[str]] = None,
        negative_point_ids: Optional[List[str]] = None,
        query_type: Optional[str] = None,
        collection: Optional[str] = None,
    ) -> List[Dict]:
        """
        Advanced search with query parsing support.

        Supports:
        - Direct ID lookup: "id:12345"
        - Filtered search: "user_email:test@gmail.com semantic query"
        - Multiple filters: "tool_name:search user_email:test@gmail.com documents"
        - Pure semantic search: "natural language query"

        Args:
            query: Search query (supports filters and semantic search)
            limit: Maximum number of results
            score_threshold: Minimum similarity score
            query_type: Optional hint for named vector routing in v7 schema
                        ('overview', 'service_history', 'general', 'recommend')
            collection: Optional collection name override. Uses default if not provided.

        Returns:
            List of matching responses with scores and metadata
        """
        # Ensure client is initialized
        if not self.client_manager.is_initialized:
            await self.client_manager.initialize()

        if not self.client_manager.client or not self.client_manager.embedder:
            raise RuntimeError("Qdrant client or embedding model not available")

        target_collection = collection or self.config.collection_name

        try:
            # Resolve named vector for v7 schema
            using = self._select_search_vector(
                query_type or ("recommend" if positive_point_ids else "general")
            )

            # Short-circuit: recommendation-style search using positive/negative examples
            if positive_point_ids or negative_point_ids:
                logger.debug(
                    f"🧲 Recommendation search with examples: "
                    f"positive={positive_point_ids}, negative={negative_point_ids}"
                )

                search_results = await self._execute_recommend_search(
                    positive_ids=positive_point_ids or [],
                    negative_ids=negative_point_ids or [],
                    limit=limit,
                    score_threshold=score_threshold,
                    using=using,
                    collection=target_collection,
                )
            else:
                # Parse the query to extract filters and semantic components
                parsed_query = parse_search_query(query)
                logger.debug(f"🔍 Parsed query: {parsed_query}")

                search_results = []

                # When not using example-based recommendation, fall back to query parsing path
                if not (positive_point_ids or negative_point_ids):
                    # Handle direct ID lookup
                    if parsed_query["query_type"] == "id_lookup":
                        target_id = parsed_query["id"]
                        logger.debug(f"🎯 Looking up point by ID: {target_id}")

                        try:
                            # Handle both string and UUID formats - always use string for Qdrant
                            try:
                                # Try to parse as UUID first to validate, but keep as string
                                uuid.UUID(target_id)
                                search_id = target_id  # Keep as string
                            except ValueError:
                                # If not a valid UUID, use as string anyway
                                search_id = target_id

                            points = await asyncio.to_thread(
                                self.client_manager.client.retrieve,
                                collection_name=target_collection,
                                ids=[search_id],
                                with_payload=True,
                            )

                            if points:
                                point = points[0]
                                search_results = [
                                    {
                                        "id": str(point.id),
                                        "score": 1.0,  # Perfect match for direct lookup
                                        "payload": point.payload,
                                    }
                                ]
                            logger.debug(
                                f"📍 ID lookup found {len(search_results)} results"
                            )

                        except Exception as e:
                            logger.error(f"❌ ID lookup failed: {e}")
                            raise

                    # Handle filtered search (with or without semantic component)
                    else:
                        qdrant_filter = None

                        # Build Qdrant filter from parsed filters
                        if parsed_query["filters"]:
                            try:
                                # Import Qdrant models for filtering
                                _, qdrant_models = get_qdrant_imports()
                                Filter = qdrant_models["models"].Filter
                                FieldCondition = qdrant_models["models"].FieldCondition
                                MatchValue = qdrant_models["models"].MatchValue

                                conditions = []
                                for filter_key, filter_value in parsed_query[
                                    "filters"
                                ].items():
                                    logger.debug(
                                        f"🏷️  Adding filter: {filter_key}={filter_value}"
                                    )
                                    conditions.append(
                                        FieldCondition(
                                            key=filter_key,
                                            match=MatchValue(value=filter_value),
                                        )
                                    )

                                if conditions:
                                    qdrant_filter = Filter(must=conditions)
                                    logger.debug(
                                        f"🔧 Built filter with {len(conditions)} conditions"
                                    )

                            except Exception as e:
                                logger.warning(
                                    f"⚠️ Failed to build filter, falling back to simple search: {e}"
                                )
                                qdrant_filter = None

                        # Perform semantic search if there's a semantic query
                        if parsed_query["semantic_query"]:
                            logger.debug(
                                f"🧠 Performing semantic search: '{parsed_query['semantic_query']}'"
                            )

                            # Generate embedding for the semantic query using FastEmbed
                            embedding_list = await asyncio.to_thread(
                                lambda q: list(self.client_manager.embedder.embed([q])),
                                parsed_query["semantic_query"],
                            )
                            query_embedding = (
                                embedding_list[0] if embedding_list else None
                            )

                            if query_embedding is None:
                                logger.error(
                                    f"Failed to generate embedding for semantic query: {parsed_query['semantic_query']}"
                                )
                                return []

                            # Use helper method for consistent query_points usage with fallback for missing indexes
                            try:
                                search_results = await self._execute_semantic_search(
                                    query_embedding=query_embedding,
                                    qdrant_filter=qdrant_filter,
                                    limit=limit,
                                    score_threshold=score_threshold,
                                    using=using,
                                    collection=target_collection,
                                )

                                logger.debug(
                                    f"🎯 Semantic search found {len(search_results)} results"
                                )

                            except Exception as e:
                                error_msg = str(e)
                                # Check for missing index error specifically for label field
                                if (
                                    "Index required but not found" in error_msg
                                    and '"label"' in error_msg
                                ):
                                    logger.warning(
                                        f"⚠️ Missing label index detected, falling back to unfiltered search. "
                                        f"Original error: {error_msg}"
                                    )

                                    # Retry with full query embedding and no filters
                                    try:
                                        # Embed the full original query to preserve filter terms in semantic search
                                        fallback_embedding_list = (
                                            await asyncio.to_thread(
                                                lambda q: list(
                                                    self.client_manager.embedder.embed(
                                                        [q]
                                                    )
                                                ),
                                                query,
                                            )
                                        )
                                        fallback_embedding = (
                                            fallback_embedding_list[0]
                                            if fallback_embedding_list
                                            else None
                                        )

                                        if fallback_embedding is None:
                                            logger.error(
                                                "Failed to generate fallback embedding, returning empty results"
                                            )
                                            return []

                                        # Retry without filters
                                        search_results = (
                                            await self._execute_semantic_search(
                                                query_embedding=fallback_embedding,
                                                qdrant_filter=None,
                                                limit=limit,
                                                score_threshold=score_threshold,
                                                using=using,
                                                collection=target_collection,
                                            )
                                        )

                                        logger.warning(
                                            f"✅ Fallback search completed with {len(search_results)} results "
                                            f"(filters dropped due to missing label index)"
                                        )

                                    except Exception as fallback_error:
                                        logger.error(
                                            f"❌ Fallback search also failed: {fallback_error}"
                                        )
                                        return []
                                else:
                                    # Re-raise other exceptions
                                    raise

                        # If no semantic query, just filter and return results
                        elif parsed_query["filters"]:
                            logger.debug("📋 Performing filter-only search")

                            # Scroll with filter to get filtered results
                            scroll_result = await asyncio.to_thread(
                                self.client_manager.client.scroll,
                                collection_name=target_collection,
                                scroll_filter=qdrant_filter,
                                limit=limit or self.config.default_search_limit,
                                with_payload=True,
                            )

                            # Convert scroll results to search result format
                            search_results = [
                                {
                                    "id": str(point.id),
                                    "score": 1.0,  # Equal relevance for filter-only results
                                    "payload": point.payload,
                                }
                                for point in scroll_result[0]
                            ]  # scroll returns (points, next_page_offset)

                            logger.debug(
                                f"📋 Filter search found {len(search_results)} results"
                            )

                        # Default behavior for plain semantic search
                        else:
                            logger.debug(f"🧠 Pure semantic search: '{query}'")

                            # Generate embedding for the entire query using FastEmbed
                            embedding_list = await asyncio.to_thread(
                                lambda q: list(self.client_manager.embedder.embed([q])),
                                query,
                            )
                            query_embedding = (
                                embedding_list[0] if embedding_list else None
                            )

                            if query_embedding is None:
                                logger.error(
                                    f"Failed to generate embedding for query: {query}"
                                )
                                return []

                            # Use helper method for consistent query_points usage
                            search_results = await self._execute_semantic_search(
                                query_embedding=query_embedding,
                                limit=limit,
                                score_threshold=score_threshold,
                                using=using,
                                collection=target_collection,
                            )

                            logger.debug(
                                f"🧠 Pure semantic search found {len(search_results)} results"
                            )

            # Process and format results
            results = []
            for result in search_results:
                # Handle different result formats
                if hasattr(result, "payload"):
                    # Standard Qdrant search result
                    payload = result.payload or {}
                    result_id = str(result.id)
                    score = result.score
                else:
                    # Custom format from our query parsing
                    payload = result.get("payload", {})
                    result_id = str(result.get("id", "unknown"))
                    score = result.get("score", 0.0)

                # Get response data from payload - handle different storage formats
                response_data = None

                # Check for compressed data first
                if payload.get("compressed", False) and payload.get("compressed_data"):
                    compressed_data = payload["compressed_data"]
                    # Ensure compressed_data is bytes (handle string encoding if necessary)
                    if isinstance(compressed_data, str):
                        # Check for base64: prefix from sanitize_for_json
                        if compressed_data.startswith("base64:"):
                            compressed_data = base64.b64decode(compressed_data[7:])
                        else:
                            # If it's a string, it might be base64 encoded or need to be encoded as bytes
                            try:
                                # Try base64 decode first (common for binary data stored as string)
                                compressed_data = base64.b64decode(compressed_data)
                            except Exception:
                                # Fallback to encoding as UTF-8 bytes
                                compressed_data = compressed_data.encode("utf-8")

                    # Use safe decompression with intelligent detection
                    decompressed_data = self._safe_decompress_data(compressed_data)
                    if decompressed_data:
                        try:
                            response_data = json.loads(decompressed_data)
                        except json.JSONDecodeError:
                            response_data = {
                                "error": "Failed to parse decompressed JSON data"
                            }
                    else:
                        # Decompression failed, try fallback data sources
                        if payload.get("data"):
                            try:
                                response_data = json.loads(payload["data"])
                            except json.JSONDecodeError:
                                response_data = {
                                    "error": "Failed to parse fallback data"
                                }
                        elif payload.get("response_data"):
                            response_data = payload["response_data"]
                        else:
                            response_data = {
                                "error": "Decompression failed and no fallback data available"
                            }

                # Check for JSON string data
                elif payload.get("data"):
                    try:
                        response_data = json.loads(payload["data"])
                    except json.JSONDecodeError:
                        response_data = {"error": "Failed to parse JSON data"}

                # Check for already structured response_data (new format)
                elif payload.get("response_data"):
                    response_data = payload["response_data"]

                # Fallback to empty response
                else:
                    response_data = {
                        "error": "No response data found",
                        "available_keys": list(payload.keys()),
                    }

                results.append(
                    {
                        "id": result_id,
                        "score": score,
                        "tool_name": payload.get("tool_name"),
                        "timestamp": payload.get("timestamp"),
                        "user_id": payload.get("user_id"),
                        "user_email": payload.get("user_email"),
                        "session_id": payload.get("session_id"),
                        "response_data": response_data,
                        "payload_type": payload.get("payload_type", "unknown"),
                        "payload": payload,
                    }
                )

            logger.info(
                f"✅ Search completed: {len(results)} results for query '{query}'"
            )
            return results

        except Exception as e:
            logger.error(f"❌ Search failed: {e}")
            raise

    async def search_responses(
        self, query: str, filters: Dict = None, limit: int = 10
    ) -> List[Dict]:
        """
        Search stored responses with optional filters.

        Args:
            query: Natural language search query
            filters: Dictionary of filter criteria
            limit: Maximum number of results

        Returns:
            List of matching responses
        """
        try:
            # Use the existing search method and apply filters
            results = await self.search(query, limit=limit)

            if filters:
                filtered_results = []
                for result in results:
                    match = True
                    if (
                        "tool_name" in filters
                        and result.get("tool_name") != filters["tool_name"]
                    ):
                        match = False
                    if (
                        "user_email" in filters
                        and result.get("user_email") != filters["user_email"]
                    ):
                        match = False
                    if match:
                        filtered_results.append(result)
                return filtered_results

            return results
        except Exception as e:
            logger.error(f"❌ Search responses failed: {e}")
            # Return empty list instead of raising to prevent tool failures
            return []

    async def get_analytics(
        self, start_date=None, end_date=None, group_by="tool_name"
    ) -> Dict:
        """
        Get comprehensive analytics on stored tool responses including point IDs and detailed metrics.

        Args:
            start_date: Start date filter (datetime object)
            end_date: End date filter (datetime object)
            group_by: Field to group results by (tool_name, user_email, etc.)

        Returns:
            Enhanced analytics data dictionary with point_ids and detailed metrics
        """
        # Ensure client is initialized
        if not self.client_manager.is_initialized:
            await self.client_manager.initialize()

        if not self.client_manager.client:
            return {"error": "Qdrant client not available"}

        try:
            # Get all points from the collection
            _, qdrant_models = get_qdrant_imports()

            # Scroll through all points in the collection (get more if needed)
            all_points = []
            next_page_offset = None

            # Paginate through all points
            while True:
                points_result = await asyncio.to_thread(
                    self.client_manager.client.scroll,
                    collection_name=self.config.collection_name,
                    limit=1000,
                    offset=next_page_offset,
                    with_payload=True,
                )

                points_batch = points_result[0]
                next_page_offset = points_result[1]

                all_points.extend(points_batch)

                # Break if no more points or if we got less than requested (last page)
                if (
                    not points_batch
                    or len(points_batch) < 1000
                    or next_page_offset is None
                ):
                    break

            # Enhanced analytics structure
            analytics = {
                "total_responses": len(all_points),
                "group_by": group_by,
                "groups": {},
                "collection_name": self.config.collection_name,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "date_range": {
                    "start_date": start_date.isoformat() if start_date else None,
                    "end_date": end_date.isoformat() if end_date else None,
                    "filtered": bool(start_date or end_date),
                },
            }

            # Process each point with enhanced data collection
            for point in all_points:
                payload = point.payload or {}
                point_id = str(point.id)

                # Apply date filtering if specified
                if start_date or end_date:
                    timestamp_str = payload.get("timestamp")
                    if timestamp_str:
                        try:
                            # Parse timestamp (handle different formats)
                            if "T" in timestamp_str:
                                timestamp = datetime.fromisoformat(
                                    timestamp_str.replace("Z", "+00:00")
                                )
                            else:
                                timestamp = datetime.fromisoformat(timestamp_str)

                            # Apply date filters
                            if start_date and timestamp < start_date:
                                continue
                            if end_date and timestamp > end_date:
                                continue
                        except (ValueError, TypeError):
                            # Skip points with invalid timestamps if filtering by date
                            if start_date or end_date:
                                continue

                group_key = payload.get(group_by, "unknown")

                # Initialize group if it doesn't exist
                if group_key not in analytics["groups"]:
                    analytics["groups"][group_key] = {
                        "count": 0,
                        "point_ids": [],
                        "timestamps": [],
                        "users": set(),
                        "payload_types": set(),
                        "session_ids": set(),
                        "response_sizes": [],
                        "has_errors": 0,
                        "compressed_responses": 0,
                        "latest_timestamp": None,
                        "earliest_timestamp": None,
                    }

                group_data = analytics["groups"][group_key]

                # Increment count and add point ID
                group_data["count"] += 1
                group_data["point_ids"].append(point_id)

                # Collect timestamp data
                if "timestamp" in payload:
                    timestamp_str = payload["timestamp"]
                    group_data["timestamps"].append(timestamp_str)

                    # Track earliest/latest timestamps
                    if (
                        group_data["latest_timestamp"] is None
                        or timestamp_str > group_data["latest_timestamp"]
                    ):
                        group_data["latest_timestamp"] = timestamp_str
                    if (
                        group_data["earliest_timestamp"] is None
                        or timestamp_str < group_data["earliest_timestamp"]
                    ):
                        group_data["earliest_timestamp"] = timestamp_str

                # Collect user information
                if "user_email" in payload:
                    group_data["users"].add(payload["user_email"])
                if "user_id" in payload:
                    group_data["users"].add(payload["user_id"])

                # Collect payload type information
                if "payload_type" in payload:
                    group_data["payload_types"].add(payload["payload_type"])

                # Collect session information
                if "session_id" in payload:
                    group_data["session_ids"].add(payload["session_id"])

                # Analyze response data for size and errors
                if "data" in payload:
                    try:
                        data_str = payload["data"]
                        group_data["response_sizes"].append(len(data_str))

                        # Check for errors in the response
                        if isinstance(data_str, str):
                            try:
                                parsed_data = json.loads(data_str)
                                if isinstance(parsed_data, dict) and (
                                    "error" in parsed_data or "status" in parsed_data
                                ):
                                    if (
                                        parsed_data.get("error")
                                        or parsed_data.get("status", "").lower()
                                        == "error"
                                    ):
                                        group_data["has_errors"] += 1
                            except json.JSONDecodeError:
                                pass
                    except (TypeError, AttributeError):
                        pass

                # Track compressed responses
                if payload.get("compressed", False):
                    group_data["compressed_responses"] += 1

            # Convert sets to lists and add computed metrics for each group
            for group_key, group_data in analytics["groups"].items():
                # Convert sets to sorted lists
                group_data["users"] = sorted(list(group_data["users"]))
                group_data["payload_types"] = sorted(list(group_data["payload_types"]))
                group_data["session_ids"] = sorted(list(group_data["session_ids"]))

                # Add computed metrics
                group_data["unique_users"] = len(group_data["users"])
                group_data["unique_payload_types"] = len(group_data["payload_types"])
                group_data["unique_sessions"] = len(group_data["session_ids"])
                group_data["error_rate"] = (
                    group_data["has_errors"] / group_data["count"]
                    if group_data["count"] > 0
                    else 0
                )
                group_data["compression_rate"] = (
                    group_data["compressed_responses"] / group_data["count"]
                    if group_data["count"] > 0
                    else 0
                )

                # Response size statistics
                if group_data["response_sizes"]:
                    group_data["avg_response_size"] = sum(
                        group_data["response_sizes"]
                    ) / len(group_data["response_sizes"])
                    group_data["min_response_size"] = min(group_data["response_sizes"])
                    group_data["max_response_size"] = max(group_data["response_sizes"])
                else:
                    group_data["avg_response_size"] = 0
                    group_data["min_response_size"] = 0
                    group_data["max_response_size"] = 0

                # Activity timeline (recent activity in last 24 hours, 7 days, 30 days)
                if group_data["timestamps"]:
                    now = datetime.now(timezone.utc)
                    recent_activity = {"last_24h": 0, "last_7d": 0, "last_30d": 0}

                    for ts in group_data["timestamps"]:
                        try:
                            if "T" in ts:
                                timestamp = datetime.fromisoformat(
                                    ts.replace("Z", "+00:00")
                                )
                            else:
                                timestamp = datetime.fromisoformat(ts)

                            age_days = (now - timestamp).days
                            if age_days <= 1:
                                recent_activity["last_24h"] += 1
                            if age_days <= 7:
                                recent_activity["last_7d"] += 1
                            if age_days <= 30:
                                recent_activity["last_30d"] += 1
                        except (ValueError, TypeError):
                            continue

                    group_data["recent_activity"] = recent_activity
                else:
                    group_data["recent_activity"] = {
                        "last_24h": 0,
                        "last_7d": 0,
                        "last_30d": 0,
                    }

            # Add summary statistics
            analytics["summary"] = {
                "total_groups": len(analytics["groups"]),
                "total_unique_users": len(
                    set().union(*[g["users"] for g in analytics["groups"].values()])
                ),
                "total_unique_payload_types": len(
                    set().union(
                        *[g["payload_types"] for g in analytics["groups"].values()]
                    )
                ),
                "total_unique_sessions": len(
                    set().union(
                        *[g["session_ids"] for g in analytics["groups"].values()]
                    )
                ),
                "overall_error_rate": (
                    sum(g["has_errors"] for g in analytics["groups"].values())
                    / analytics["total_responses"]
                    if analytics["total_responses"] > 0
                    else 0
                ),
                "overall_compression_rate": (
                    sum(g["compressed_responses"] for g in analytics["groups"].values())
                    / analytics["total_responses"]
                    if analytics["total_responses"] > 0
                    else 0
                ),
            }

            return analytics

        except Exception as e:
            logger.error(f"❌ Failed to get analytics: {e}")
            return {"error": str(e)}

    async def _execute_recommend_search(
        self,
        positive_ids: List[str],
        negative_ids: List[str],
        limit: Optional[int] = None,
        score_threshold: Optional[float] = None,
        using: Optional[str] = None,
        collection: Optional[str] = None,
    ):
        """
        Execute recommendation-style search using positive/negative example point IDs.

        This uses Qdrant's RecommendQuery API as described in docs/qdrant_explore_data.md.
        Only stored vectors are used (no new embeddings are computed).
        """
        # Ensure client is initialized
        if not self.client_manager.is_initialized:
            await self.client_manager.initialize()

        if not self.client_manager.is_available:
            raise RuntimeError("Qdrant client not available")

        # Import Qdrant models
        _, qdrant_models = get_qdrant_imports()
        models = qdrant_models["models"]

        # Build recommend input from example IDs
        recommend_input = models.RecommendInput(
            positive=positive_ids,
            negative=negative_ids or None,
            # Default strategy aligns with docs: average_vector
            strategy=models.RecommendStrategy.AVERAGE_VECTOR,
        )

        recommend_query = models.RecommendQuery(recommend=recommend_input)

        target_collection = collection or self.config.collection_name
        kwargs = {
            "collection_name": target_collection,
            "query": recommend_query,
            "limit": limit or self.config.default_search_limit,
            "score_threshold": score_threshold or self.config.score_threshold,
            "with_payload": True,
        }
        if using:
            kwargs["using"] = using

        search_response = await asyncio.to_thread(
            self.client_manager.client.query_points,
            **kwargs,
        )

        return search_response.points

    async def get_response_by_id(self, response_id: str) -> Optional[Dict]:
        """
        Get a specific response by its ID.

        Args:
            response_id: UUID of the stored response

        Returns:
            Response data or None if not found
        """
        # Ensure client is initialized
        if not self.client_manager.is_initialized:
            await self.client_manager.initialize()

        if not self.client_manager.client:
            return None

        try:
            # Handle both string and UUID formats - always use string for Qdrant
            try:
                # Try to parse as UUID first to validate, but keep as string
                uuid.UUID(response_id)
                search_id = response_id  # Keep as string
            except ValueError:
                # If not a valid UUID, use as string anyway
                search_id = response_id

            # Retrieve the specific point by ID
            point = await asyncio.to_thread(
                self.client_manager.client.retrieve,
                collection_name=self.config.collection_name,
                ids=[search_id],
            )

            if not point:
                return None

            payload = point[0].payload

            # Get response data from payload - handle different storage formats
            response_data = None

            # Check for compressed data first
            if payload.get("compressed", False):
                compressed_data = payload.get("compressed_data")
                if compressed_data:
                    # Ensure compressed_data is bytes (handle string encoding if necessary)
                    if isinstance(compressed_data, str):
                        # Check for base64: prefix from sanitize_for_json
                        if compressed_data.startswith("base64:"):
                            compressed_data = base64.b64decode(compressed_data[7:])
                        else:
                            # If it's a string, it might be base64 encoded or need to be encoded as bytes
                            try:
                                # Try base64 decode first (common for binary data stored as string)
                                compressed_data = base64.b64decode(compressed_data)
                            except Exception:
                                # Fallback to encoding as UTF-8 bytes
                                compressed_data = compressed_data.encode("utf-8")

                    # Use safe decompression with intelligent detection
                    decompressed_data = self._safe_decompress_data(compressed_data)
                    if decompressed_data:
                        try:
                            response_data = json.loads(decompressed_data)
                        except json.JSONDecodeError:
                            response_data = {
                                "error": "Failed to parse decompressed JSON data",
                                "raw_data": decompressed_data,
                            }
                    else:
                        response_data = {"error": "Failed to decompress data"}

            # Check for JSON string data
            elif payload.get("data"):
                try:
                    response_data = json.loads(payload["data"])
                except json.JSONDecodeError:
                    response_data = {
                        "error": "Failed to parse JSON data",
                        "raw_data": payload["data"],
                    }

            # Check for already structured response_data (new format)
            elif payload.get("response_data"):
                response_data = payload["response_data"]

            # Fallback to empty response
            else:
                response_data = {
                    "error": "No response data found in payload",
                    "payload_keys": list(payload.keys()),
                }

            return response_data

        except Exception as e:
            logger.error(f"❌ Failed to get response by ID: {e}")
            return {"error": str(e)}

    async def get_responses_by_ids(self, response_ids: List[str]) -> Dict[str, Dict]:
        """
        Batch retrieve multiple responses by their IDs.

        Args:
            response_ids: List of Qdrant point IDs

        Returns:
            Dict mapping point_id -&gt; response data (same shape as get_response_by_id)
        """
        results: Dict[str, Dict] = {}
        if not response_ids:
            return results

        for rid in response_ids:
            try:
                data = await self.get_response_by_id(rid)
                if data is not None:
                    results[rid] = data
            except Exception as e:
                logger.error(f"❌ Failed to get response for ID {rid}: {e}")
        return results

    async def unified_search_core(self, query: str, limit: int = 10) -> Dict:
        """
        Core unified search function with intelligent query routing.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            Dictionary in OpenAI MCP format with 'results' array
        """
        # Parse query using enhanced parser
        parsed_query = parse_unified_query(query)
        logger.info(
            f"🔍 Unified search: capability={parsed_query['capability']}, confidence={parsed_query['confidence']}"
        )

        # Route to appropriate search strategy based on capability
        if parsed_query["capability"] == "overview":
            # Get analytics/overview data
            try:
                analytics = await self.get_analytics()
                if analytics and "groups" in analytics:
                    # Convert analytics to search result format
                    results = []
                    for group_name, group_data in analytics["groups"].items():
                        results.append(
                            {
                                "id": f"analytics_{group_name}",
                                "tool_name": f"analytics_{group_name}",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "user_email": "system",
                                "score": 1.0,
                                "response_data": {
                                    "summary": f"{group_name}: {group_data.get('count', 0)} responses",
                                    "analytics": group_data,
                                },
                            }
                        )
                    return await format_search_results(
                        self, results[:limit], parsed_query
                    )
                else:
                    return {"results": []}
            except Exception as e:
                logger.error(f"❌ Overview search failed: {e}")
                return {"results": []}

        elif parsed_query["capability"] == "service_history":
            # Build filtered query for service history
            search_query = ""
            if parsed_query.get("service_name"):
                search_query += f"tool_name:{parsed_query['service_name']}"
            if parsed_query.get("time_range"):
                search_query += f" {parsed_query['time_range']}"
            if parsed_query.get("semantic_query"):
                search_query += f" {parsed_query['semantic_query']}"

            search_query = search_query.strip() or query

            try:
                results = await self.search(search_query, limit=limit)
                return await format_search_results(self, results, parsed_query)
            except Exception as e:
                logger.error(f"❌ Service history search failed: {e}")
                return {"results": []}

        else:
            # General search - use existing search functionality
            try:
                results = await self.search(query, limit=limit)
                return await format_search_results(self, results, parsed_query)
            except Exception as e:
                logger.error(f"❌ General search failed: {e}")
                return {"results": []}

    async def get_search_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the search collection and performance.

        Returns:
            Dict with collection statistics and search metrics
        """
        # Ensure client is initialized
        if not self.client_manager.is_initialized:
            await self.client_manager.initialize()

        if not self.client_manager.client:
            return {"error": "Qdrant client not available"}

        try:
            # Get collection info
            collection_info = await asyncio.to_thread(
                self.client_manager.client.get_collection, self.config.collection_name
            )

            # Get analytics for additional metrics
            analytics = await self.get_analytics()

            stats = {
                "collection_name": self.config.collection_name,
                "total_points": collection_info.points_count or 0,
                "vectors_count": collection_info.indexed_vectors_count or 0,
                "indexed_vectors_count": collection_info.indexed_vectors_count or 0,
                "segments_count": collection_info.segments_count,
                "status": str(collection_info.status),
                "config": {
                    "vector_size": self.config.vector_size,
                    "distance": self.config.distance,
                    "embedding_model": self.config.embedding_model,
                    "default_search_limit": self.config.default_search_limit,
                    "score_threshold": self.config.score_threshold,
                },
                "analytics_summary": {
                    "total_responses": analytics.get("total_responses", 0),
                    "unique_tools": len(analytics.get("groups", {})),
                    "group_counts": {
                        k: v.get("count", 0)
                        for k, v in analytics.get("groups", {}).items()
                    },
                },
                "client_info": self.client_manager.get_connection_info(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            return stats

        except Exception as e:
            logger.error(f"❌ Failed to get search statistics: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def get_search_info(self) -> Dict[str, Any]:
        """
        Get information about the search manager and its status.

        Returns:
            Dict with search manager information and status
        """
        return {
            "client_manager_status": self.client_manager.get_connection_info(),
            "config": self.config.to_dict(),
            "available": self.client_manager.is_available,
            "initialized": self.client_manager.is_initialized,
            "search_capabilities": [
                "semantic_search",
                "filtered_search",
                "id_lookup",
                "analytics",
                "unified_search",
                "response_retrieval",
            ],
            "query_parsers": ["parse_search_query", "parse_unified_query"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# Legacy function for backward compatibility with the main middleware
async def _unified_search_core(middleware, query: str, limit: int = 10) -> Dict:
    """
    Legacy wrapper function for unified search to maintain compatibility.

    Args:
        middleware: QdrantUnifiedMiddleware instance (for compatibility)
        query: Search query string
        limit: Maximum number of results

    Returns:
        Dictionary in OpenAI MCP format with 'results' array
    """
    # Check if middleware has a search_manager attribute
    if hasattr(middleware, "search_manager"):
        return await middleware.search_manager.unified_search_core(query, limit)

    # Fallback: create a temporary search manager
    logger.warning(
        "Using fallback search manager creation - consider updating middleware integration"
    )
    search_manager = QdrantSearchManager(
        middleware.client_manager
        if hasattr(middleware, "client_manager")
        else middleware
    )
    return await search_manager.unified_search_core(query, limit)
