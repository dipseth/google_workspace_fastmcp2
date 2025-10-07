#!/usr/bin/env python3
"""
Qdrant Resource Response Types

This module defines Pydantic models for Qdrant resource responses to ensure
proper FastMCP integration and consistent API responses.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field


class QdrantCollectionInfo(BaseModel):
    """Information about a single Qdrant collection."""
    name: str = Field(description="Collection name")
    points_count: int = Field(description="Number of points in the collection")
    vectors_count: int = Field(default=0, description="Number of vectors")
    indexed_vectors_count: int = Field(default=0, description="Number of indexed vectors")
    segments_count: int = Field(default=0, description="Number of segments")
    status: str = Field(default="unknown", description="Collection status")
    error: Optional[str] = Field(default=None, description="Error message if collection info failed")


class QdrantCollectionsListResponse(BaseModel):
    """Response for qdrant://collections/list resource."""
    qdrant_enabled: bool = Field(description="Whether Qdrant is available and connected")
    qdrant_url: Optional[str] = Field(description="The discovered or configured Qdrant URL")
    total_collections: int = Field(description="Number of collections found")
    collections: List[QdrantCollectionInfo] = Field(description="List of collections with their info")
    config: Dict[str, Any] = Field(default_factory=dict, description="Current Qdrant configuration")
    timestamp: str = Field(description="When this data was retrieved")


class QdrantCollectionDetailsResponse(BaseModel):
    """Response for qdrant://collection/{name}/info resource."""
    qdrant_enabled: bool = Field(description="Whether Qdrant is available")
    qdrant_url: Optional[str] = Field(description="Qdrant connection URL")
    requested_collection: str = Field(description="Name of the requested collection")
    collection_exists: bool = Field(description="Whether the collection exists")
    total_collections: int = Field(description="Total number of collections")
    all_collections: List[str] = Field(description="Names of all available collections")
    collection_info: Optional[Dict[str, Any]] = Field(description="Detailed collection information if it exists")
    config: Dict[str, Any] = Field(description="Qdrant configuration")
    timestamp: str = Field(description="When this data was retrieved")


class QdrantStoredResponse(BaseModel):
    """A single stored response from Qdrant."""
    id: str = Field(description="Point ID in Qdrant")
    tool_name: str = Field(description="Name of the tool that generated this response")
    timestamp: str = Field(description="When the response was stored")
    user_id: str = Field(description="User ID associated with the response")
    user_email: str = Field(description="User email associated with the response")
    session_id: str = Field(description="Session ID when the response was generated")
    payload_type: str = Field(description="Type of the stored payload")
    compressed: bool = Field(description="Whether the response data is compressed")
    response_data: Union[Dict[str, Any], str] = Field(description="The actual response data")


class QdrantRecentResponsesResponse(BaseModel):
    """Response for qdrant://collection/{name}/responses/recent resource."""
    qdrant_enabled: bool = Field(description="Whether Qdrant is available")
    collection_name: str = Field(description="Name of the collection")
    total_points: int = Field(description="Total number of points in the collection")
    responses_shown: int = Field(description="Number of responses included in this response")
    responses: List[QdrantStoredResponse] = Field(description="List of recent responses")
    timestamp: str = Field(description="When this data was retrieved")


class QdrantSearchResult(BaseModel):
    """A single search result from Qdrant."""
    id: str = Field(description="Point ID")
    score: float = Field(description="Relevance score")
    tool_name: Optional[str] = Field(description="Tool name if available")
    timestamp: Optional[str] = Field(description="When the response was stored")
    user_email: Optional[str] = Field(description="User email if available")
    # Additional fields from search results
    payload: Dict[str, Any] = Field(default_factory=dict, description="Raw payload data")


class QdrantSearchResponse(BaseModel):
    """Response for qdrant://search/* resources."""
    qdrant_enabled: bool = Field(description="Whether Qdrant is available")
    query: str = Field(description="The search query used")
    collection: Optional[str] = Field(default=None, description="Collection name if collection-specific search")
    total_results: int = Field(description="Number of results found")
    results: List[QdrantSearchResult] = Field(description="Search results")
    timestamp: str = Field(description="When the search was performed")


class QdrantErrorResponse(BaseModel):
    """Error response for Qdrant resources."""
    error: str = Field(description="Error message")
    uri: str = Field(description="The original URI that caused the error")
    timestamp: str = Field(description="When the error occurred")
    qdrant_enabled: bool = Field(default=False, description="Whether Qdrant is available")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional error details")


class QdrantStatusResponse(BaseModel):
    """Response for qdrant://status resource."""
    qdrant_enabled: bool = Field(description="Whether Qdrant is enabled and available")
    qdrant_url: Optional[str] = Field(description="Discovered Qdrant URL")
    client_available: bool = Field(description="Whether the Qdrant client is available")
    embedder_available: bool = Field(description="Whether the embedding model is loaded")
    initialized: bool = Field(description="Whether the middleware is fully initialized")
    collections_count: int = Field(default=0, description="Number of collections")
    config: Dict[str, Any] = Field(description="Current configuration")
    supported_uris: List[str] = Field(description="List of supported URI patterns")
    handler_info: Dict[str, Any] = Field(description="Resource handler information")
    timestamp: str = Field(description="When the status was checked")


# Additional models needed by tools.py

class QdrantSearchResultItem(BaseModel):
    """A single search result item for the search tool."""
    id: str = Field(description="Point ID")
    title: str = Field(description="Formatted title with service icon and tool name")
    url: str = Field(description="qdrant:// URL for this result")
    score: float = Field(description="Relevance score")
    tool_name: str = Field(description="Name of the tool")
    service: str = Field(description="Service name (gmail, drive, etc.)")
    timestamp: str = Field(description="When the response was stored")
    user_email: str = Field(description="User email associated with the response")


class QdrantDocumentMetadata(BaseModel):
    """Metadata for a Qdrant document in the fetch tool."""
    tool_name: str = Field(description="Name of the tool")
    service: str = Field(description="Service name")
    service_display_name: str = Field(description="Human-readable service name")
    user_email: str = Field(description="User email")
    timestamp: str = Field(description="When the response was stored")
    response_type: str = Field(description="Type of the response object")
    arguments_count: int = Field(description="Number of arguments passed to the tool")
    payload_type: str = Field(description="Type of the payload")
    collection_name: str = Field(description="Qdrant collection name")
    point_id: str = Field(description="Qdrant point ID")


class QdrantFetchResponse(BaseModel):
    """Response for the fetch tool."""
    id: str = Field(description="Point ID")
    title: str = Field(description="Document title")
    text: str = Field(description="Full document text content")
    url: str = Field(description="qdrant:// URL for this document")
    metadata: QdrantDocumentMetadata = Field(description="Document metadata")
    found: bool = Field(description="Whether the document was found")
    collection_name: str = Field(description="Qdrant collection name")
    error: Optional[str] = Field(default=None, description="Error message if fetch failed")


class QdrantToolSearchResponse(BaseModel):
    """Response for the enhanced search tool (different from resource search)."""
    results: List[QdrantSearchResultItem] = Field(description="Search results")
    query: str = Field(description="The search query used")
    query_type: str = Field(description="Type of query (semantic, service_history, etc.)")
    total_results: int = Field(description="Number of results found")
    processing_time_ms: float = Field(description="Time taken to process the search")
    collection_name: str = Field(description="Qdrant collection name")
    error: Optional[str] = Field(default=None, description="Error message if search failed")


class QdrantPointDetailsResponse(BaseModel):
    """Response for qdrant://collection/{collection}/{point_id} resource."""
    qdrant_enabled: bool = Field(description="Whether Qdrant is available")
    collection_name: str = Field(description="Name of the collection")
    point_id: str = Field(description="ID of the retrieved point")
    point_exists: bool = Field(description="Whether the point was found")
    payload: Optional[Dict[str, Any]] = Field(default=None, description="Point payload/metadata")
    vector_available: bool = Field(default=False, description="Whether vector data is included")
    vector_size: Optional[int] = Field(default=None, description="Size of the vector if available")
    # Extracted common fields for easy access
    tool_name: Optional[str] = Field(default=None, description="Tool name from payload")
    user_email: Optional[str] = Field(default=None, description="User email from payload")
    timestamp: Optional[str] = Field(default=None, description="Timestamp from payload")
    session_id: Optional[str] = Field(default=None, description="Session ID from payload")
    payload_type: Optional[str] = Field(default=None, description="Payload type from payload")
    compressed: bool = Field(default=False, description="Whether data is compressed")
    # Decompressed data if available
    response_data: Optional[Union[Dict[str, Any], str]] = Field(default=None, description="Decompressed response data")
    retrieved_at: str = Field(description="When this point was retrieved")