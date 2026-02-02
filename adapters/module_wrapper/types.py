"""
Module Wrapper Type Definitions

This module provides consolidated type definitions, protocols, and type aliases
used throughout the module_wrapper package. Centralizing these types ensures:

1. Consistency across all mixins and utilities
2. Reusable protocols for common behaviors
3. Type aliases for cleaner function signatures
4. Shared dataclasses for cross-module communication

Usage:
    from adapters.module_wrapper.types import (
        # Type Aliases
        Payload,
        SymbolMapping,
        ComponentPath,
        RelationshipDict,
        # Protocols
        Serializable,
        Timestamped,
        Validatable,
        # Common Dataclasses
        SearchResult,
        EmbeddingConfig,
        QdrantConfig,
    )

Note: Domain-specific types remain in their respective files:
    - skill_types.py: SkillDocument, SkillManifest, etc.
    - dsl_parser.py: DSLToken, DSLNode, DSLParseResult, etc.
    - instance_pattern_mixin.py: InstancePattern, PatternVariation, etc.
    - structure_validator.py: ValidationResult, ComponentSlot
    - component_cache.py: CacheEntry
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    runtime_checkable,
)

if TYPE_CHECKING:
    from qdrant_client import QdrantClient


# =============================================================================
# TYPE ALIASES
# =============================================================================
# These aliases improve code readability and make type signatures cleaner.

# Basic payload types
Payload = Dict[str, Any]
"""A generic payload dictionary for Qdrant points or API responses."""

JsonDict = Dict[str, Any]
"""A JSON-compatible dictionary."""

# Symbol and DSL types
Symbol = str
"""A single Unicode symbol representing a component (e.g., '§', 'δ', 'ᵬ')."""

SymbolMapping = Dict[str, str]
"""Mapping from component name to symbol: {"Section": "§", "Button": "ᵬ"}."""

ReverseSymbolMapping = Dict[str, str]
"""Mapping from symbol to component name: {"§": "Section", "ᵬ": "Button"}."""

DSLNotation = str
"""DSL structure notation string (e.g., '§[δ×3, Ƀ[ᵬ×2]]')."""

# Component and path types
ComponentPath = str
"""Full import path to a component (e.g., 'card_framework.v2.Section')."""

ComponentName = str
"""Simple component name without module path (e.g., 'Section')."""

ComponentPaths = List[str]
"""List of component paths or names."""

# Relationship types
RelationshipDict = Dict[str, List[str]]
"""Parent → children relationships: {"Section": ["Widget", "Divider"]}."""

RelationshipList = List[Dict[str, Any]]
"""List of detailed relationship dictionaries with metadata."""

# Embedding types
EmbeddingVector = List[float]
"""A single dense embedding vector (e.g., 384-dim MiniLM)."""

MultiVector = List[List[float]]
"""Multi-vector embedding (e.g., ColBERT token embeddings)."""

EmbeddingDimension = int
"""Dimension of an embedding vector (e.g., 384, 128, 768)."""

# Filter and query types
QdrantFilter = Dict[str, Any]
"""Qdrant filter specification dictionary."""

QueryText = str
"""Text to be embedded for search queries."""

# Cache types
CacheKey = str
"""Unique identifier for cached items."""

# Validation types
IssueList = List[str]
"""List of validation issues or errors."""

SuggestionList = List[str]
"""List of suggestions for fixing issues."""

# Callback types
WrapperGetter = Callable[[], Any]
"""Callable that returns a ModuleWrapper instance."""

EvictionCallback = Callable[[str, Any], None]
"""Callback invoked when items are evicted from cache."""


# =============================================================================
# PROTOCOLS
# =============================================================================
# Protocols define interfaces that types can implement for duck typing.


@runtime_checkable
class Serializable(Protocol):
    """Protocol for objects that can be serialized to dictionaries.

    All dataclasses in the module_wrapper package should implement this
    to ensure consistent serialization for storage and API responses.

    Example:
        @dataclass
        class MyType:
            name: str
            value: int

            def to_dict(self) -> Dict[str, Any]:
                return {"name": self.name, "value": self.value}
    """

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        ...


@runtime_checkable
class Timestamped(Protocol):
    """Protocol for objects with creation/access timestamps.

    Used for cache entries, patterns, and other time-tracked objects.
    """

    created_at: float
    """Unix timestamp of creation."""

    @property
    def age_seconds(self) -> float:
        """Get age in seconds since creation."""
        ...


@runtime_checkable
class Validatable(Protocol):
    """Protocol for objects that can be validated.

    Used for DSL structures, patterns, and configurations.
    """

    is_valid: bool
    """Whether the object passed validation."""

    issues: List[str]
    """List of validation issues found."""


@runtime_checkable
class HasSymbol(Protocol):
    """Protocol for objects associated with a DSL symbol.

    Used for components, DSL nodes, and content lines.
    """

    symbol: str
    """The Unicode symbol for this object."""

    component_name: str
    """The resolved component name."""


@runtime_checkable
class Embeddable(Protocol):
    """Protocol for objects that can be embedded into vectors.

    Used for components, patterns, and documents that need
    vector representation for semantic search.
    """

    def to_embedding_text(self) -> str:
        """Generate text representation for embedding."""
        ...


# =============================================================================
# COMMON DATACLASSES
# =============================================================================
# Shared dataclasses used across multiple modules.


@dataclass
class QdrantConfig:
    """Configuration for Qdrant connection.

    Centralizes Qdrant settings used by QdrantMixin and core.py.
    """

    host: str = "localhost"
    port: int = 6333
    url: Optional[str] = None
    api_key: Optional[str] = None
    use_https: bool = False
    prefer_grpc: bool = True
    timeout: float = 30.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "host": self.host,
            "port": self.port,
            "url": self.url,
            "api_key": "***" if self.api_key else None,  # Mask for safety
            "use_https": self.use_https,
            "prefer_grpc": self.prefer_grpc,
            "timeout": self.timeout,
        }

    @classmethod
    def from_env(cls) -> "QdrantConfig":
        """Create from environment variables."""
        import os

        url = os.getenv("QDRANT_URL")
        if url:
            from adapters.module_wrapper.core import parse_qdrant_url

            parsed = parse_qdrant_url(url)
            return cls(
                host=parsed["host"],
                port=parsed["port"],
                url=url,
                api_key=os.getenv("QDRANT_API_KEY") or os.getenv("QDRANT_KEY"),
                use_https=parsed["use_https"],
            )

        return cls(
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", "6333")),
            api_key=os.getenv("QDRANT_API_KEY") or os.getenv("QDRANT_KEY"),
            use_https=os.getenv("QDRANT_USE_HTTPS", "false").lower() == "true",
        )


@dataclass
class EmbeddingConfig:
    """Configuration for embedding models.

    Centralizes embedding model settings used by EmbeddingMixin.
    """

    # MiniLM / dense embedding
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    dimension: int = 384

    # ColBERT / multi-vector
    colbert_enabled: bool = False
    colbert_model_name: str = "colbert-ir/colbertv2.0"
    colbert_dimension: int = 128

    # Relationships embedding (separate from main)
    relationships_dimension: int = 384

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "model_name": self.model_name,
            "dimension": self.dimension,
            "colbert_enabled": self.colbert_enabled,
            "colbert_model_name": self.colbert_model_name,
            "colbert_dimension": self.colbert_dimension,
            "relationships_dimension": self.relationships_dimension,
        }


@dataclass
class SearchResult:
    """A single search result from Qdrant.

    Provides a consistent structure for search results across
    all search methods (standard, ColBERT, hybrid, text).
    """

    # Identification
    id: str
    name: str
    component_type: str

    # Scoring
    score: float
    rank: Optional[int] = None

    # Metadata
    module_path: Optional[str] = None
    full_path: Optional[str] = None
    docstring: Optional[str] = None
    symbol: Optional[str] = None
    dsl_notation: Optional[str] = None

    # Relationships
    children: List[str] = field(default_factory=list)
    parents: List[str] = field(default_factory=list)

    # Raw payload for additional fields
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "component_type": self.component_type,
            "score": self.score,
            "rank": self.rank,
            "module_path": self.module_path,
            "full_path": self.full_path,
            "docstring": self.docstring,
            "symbol": self.symbol,
            "dsl_notation": self.dsl_notation,
            "children": self.children,
            "parents": self.parents,
        }

    @classmethod
    def from_qdrant_point(
        cls, point: Any, rank: Optional[int] = None
    ) -> "SearchResult":
        """Create from a Qdrant ScoredPoint."""
        payload = point.payload or {}

        return cls(
            id=str(point.id),
            name=payload.get("name", ""),
            component_type=payload.get("type", "unknown"),
            score=point.score,
            rank=rank,
            module_path=payload.get("module_path"),
            full_path=payload.get("full_path"),
            docstring=payload.get("docstring"),
            symbol=payload.get("symbol"),
            dsl_notation=payload.get("dsl_notation"),
            children=payload.get("children", []),
            parents=payload.get("relationships", {}).get("parent_classes", []),
            payload=payload,
        )


@dataclass
class ComponentInfo:
    """Lightweight component information for listings and summaries.

    Unlike ModuleComponent (which holds the actual object), this is
    a pure data container suitable for serialization and transfer.
    """

    name: str
    component_type: str  # "class", "function", "variable"
    module_path: str
    full_path: str
    symbol: Optional[str] = None
    docstring: Optional[str] = None
    has_children: bool = False
    child_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "type": self.component_type,
            "module_path": self.module_path,
            "full_path": self.full_path,
            "symbol": self.symbol,
            "docstring": self.docstring,
            "has_children": self.has_children,
            "child_count": self.child_count,
        }


@dataclass
class RelationshipInfo:
    """Relationship between two components.

    Used for graph construction and relationship indexing.
    """

    parent_class: str
    child_class: str
    field_name: str
    is_optional: bool = True
    is_list: bool = False
    cardinality: str = "0..1"  # "0..1", "1", "0..*", "1..*"

    # Natural language description for embedding
    nl_description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "parent_class": self.parent_class,
            "child_class": self.child_class,
            "field_name": self.field_name,
            "is_optional": self.is_optional,
            "is_list": self.is_list,
            "cardinality": self.cardinality,
            "nl_description": self.nl_description,
        }

    def to_compact_text(self) -> str:
        """Generate compact text for embedding."""
        opt = "?" if self.is_optional else ""
        mult = "[]" if self.is_list else ""
        return f"{self.parent_class}.{self.field_name}:{self.child_class}{mult}{opt}"


@dataclass
class IndexingStats:
    """Statistics from component indexing operation.

    Returned by IndexingMixin methods to track indexing progress.
    """

    components_found: int = 0
    components_indexed: int = 0
    components_skipped: int = 0
    relationships_extracted: int = 0
    embeddings_generated: int = 0
    points_upserted: int = 0
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "components_found": self.components_found,
            "components_indexed": self.components_indexed,
            "components_skipped": self.components_skipped,
            "relationships_extracted": self.relationships_extracted,
            "embeddings_generated": self.embeddings_generated,
            "points_upserted": self.points_upserted,
            "errors": self.errors,
            "duration_seconds": self.duration_seconds,
            "success": len(self.errors) == 0,
        }


@dataclass
class TimestampedMixin:
    """Mixin providing timestamp fields and methods.

    Inherit from this to add consistent timestamp handling.
    """

    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0

    @property
    def age_seconds(self) -> float:
        """Get age in seconds since creation."""
        return time.time() - self.created_at

    @property
    def idle_seconds(self) -> float:
        """Get seconds since last access."""
        return time.time() - self.last_accessed

    @property
    def created_datetime(self) -> datetime:
        """Get creation time as datetime."""
        return datetime.fromtimestamp(self.created_at)

    @property
    def last_accessed_datetime(self) -> datetime:
        """Get last access time as datetime."""
        return datetime.fromtimestamp(self.last_accessed)

    def touch(self) -> None:
        """Update last_accessed timestamp and increment access count."""
        self.last_accessed = time.time()
        self.access_count += 1


# =============================================================================
# CONSTANTS
# =============================================================================
# Shared constants used across multiple modules.

# Vector dimensions for v7 schema (used by pipeline_mixin.py and search_mixin.py)
COLBERT_DIM: int = 128
"""ColBERT multi-vector embedding dimension."""

MINILM_DIM: int = 384
"""MiniLM dense embedding dimension."""

RELATIONSHIPS_DIM: int = 384
"""Dimension for relationship embeddings."""

# Default relationship extraction depth (used by core.py and relationships_mixin.py)
DEFAULT_RELATIONSHIP_DEPTH: int = 5
"""Default depth for relationship extraction."""

# Primitive types to skip during relationship extraction
PRIMITIVE_TYPES: Set[type] = {str, int, float, bool, bytes, type(None)}
"""Types considered primitive (not indexed as relationships)."""

# Built-in module prefixes to skip
BUILTIN_PREFIXES: Set[str] = {"builtins", "typing", "collections", "abc"}
"""Module prefixes to skip during indexing."""


# =============================================================================
# TYPE VARIABLES
# =============================================================================
# Generic type variables for type-safe functions.

T = TypeVar("T")
"""Generic type variable."""

S = TypeVar("S", bound=Serializable)
"""Type variable bound to Serializable protocol."""

V = TypeVar("V", bound=Validatable)
"""Type variable bound to Validatable protocol."""


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Type Aliases
    "Payload",
    "JsonDict",
    "Symbol",
    "SymbolMapping",
    "ReverseSymbolMapping",
    "DSLNotation",
    "ComponentPath",
    "ComponentName",
    "ComponentPaths",
    "RelationshipDict",
    "RelationshipList",
    "EmbeddingVector",
    "MultiVector",
    "EmbeddingDimension",
    "QdrantFilter",
    "QueryText",
    "CacheKey",
    "IssueList",
    "SuggestionList",
    "WrapperGetter",
    "EvictionCallback",
    # Protocols
    "Serializable",
    "Timestamped",
    "Validatable",
    "HasSymbol",
    "Embeddable",
    # Dataclasses
    "QdrantConfig",
    "EmbeddingConfig",
    "SearchResult",
    "ComponentInfo",
    "RelationshipInfo",
    "IndexingStats",
    "TimestampedMixin",
    # Constants
    "COLBERT_DIM",
    "MINILM_DIM",
    "RELATIONSHIPS_DIM",
    "DEFAULT_RELATIONSHIP_DEPTH",
    "PRIMITIVE_TYPES",
    "BUILTIN_PREFIXES",
    # Type Variables
    "T",
    "S",
    "V",
]
