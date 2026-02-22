"""
Pydantic response models for Qdrant DSL search tools.

Consolidated from middleware/qdrant_search_v2/types.py into qdrant_core.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SearchV2ResultItem(BaseModel):
    """A single search result from Qdrant."""

    id: str
    score: Optional[float] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    tool_name: Optional[str] = None
    user_email: Optional[str] = None
    timestamp: Optional[str] = None


class SearchV2Response(BaseModel):
    """Response from a Qdrant DSL query."""

    results: List[SearchV2ResultItem] = Field(default_factory=list)
    dsl_input: str = ""
    query_type: str = ""  # "query_points", "scroll", "dry_run"
    collection_name: str = ""
    total_results: int = 0
    processing_time_ms: float = 0.0
    built_filter_repr: Optional[str] = None
    error: Optional[str] = None


class SearchV2SymbolsResponse(BaseModel):
    """Response from the symbols discovery tool."""

    symbols: Dict[str, str] = Field(default_factory=dict)  # symbol → class name
    relationships: Dict[str, List[str]] = Field(
        default_factory=dict
    )  # parent → children
    dsl_grammar: str = ""
    examples: List[Dict[str, str]] = Field(default_factory=list)
