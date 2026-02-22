"""
Configuration Module for Qdrant Middleware

This module contains configuration classes and enums for the Qdrant
vector database middleware, including:
- Payload type enumeration
- Main configuration dataclass
- Configuration validation and defaults
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class PayloadType(Enum):
    """Types of payloads we store in Qdrant."""

    TOOL_RESPONSE = "tool_response"
    CLUSTER = "cluster"
    JOB = "job"
    QUERY = "query"
    GENERIC = "generic"


class CollectionSchema(Enum):
    """Schema variants for Qdrant collection vector configuration."""

    V1_SINGLE_VECTOR = "v1"  # Single 384-dim vector (legacy default)
    V7_NAMED_VECTORS = "v7"  # 3 named vectors: components, inputs, relationships (RIC)


class OptimizationProfile(Enum):
    """Optimization profiles for different deployment scenarios."""

    CLOUD_LOW_LATENCY = "cloud_low_latency"  # Cloud + small datasets + fastest search
    CLOUD_BALANCED = "cloud_balanced"  # Cloud + medium datasets + balanced performance
    CLOUD_LARGE_SCALE = "cloud_large_scale"  # Cloud + large datasets + efficiency focus
    LOCAL_DEVELOPMENT = "local_development"  # Local development + fast startup


@dataclass
class QdrantConfig:
    """Configuration for Qdrant middleware."""

    # Connection settings
    ports: List[int] = field(default_factory=lambda: [6333, 6335, 6334])
    host: str = "localhost"
    connection_timeout: int = 5000
    retry_attempts: int = 3

    # Collection settings
    collection_name: str = "mcp_tool_responses"
    vector_size: int = 384
    distance: str = "Cosine"

    # Storage settings
    compression_threshold: int = 5120  # 5KB
    compression_type: str = "gzip"

    # Search settings
    default_search_limit: int = 10
    score_threshold: float = 0.3  # Lower threshold for better semantic search results

    # Middleware settings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    summary_max_tokens: int = 500
    verbose_param: str = "verbose"
    enabled: bool = True

    # Data retention settings
    cache_retention_days: int = 14

    # Schema settings
    collection_schema: CollectionSchema = CollectionSchema.V1_SINGLE_VECTOR
    dual_write: bool = False  # Write to both v1 and v7 schemas during migration
    v7_collection_name: str = ""  # Explicit v7 collection name (auto-derived if empty)

    # Optimization settings
    optimization_profile: OptimizationProfile = OptimizationProfile.CLOUD_LOW_LATENCY

    def __post_init__(self):
        """Post-initialization validation and setup."""
        # Ensure ports list is properly initialized
        if self.ports is None:
            self.ports = [6333, 6335, 6334]

        # Validate configuration values
        self._validate_config()

    def _validate_config(self):
        """Validate configuration values."""
        # Validate ports
        if not self.ports:
            raise ValueError("At least one port must be specified")
        for port in self.ports:
            if not isinstance(port, int) or port < 1 or port > 65535:
                raise ValueError(f"Invalid port: {port}")

        # Validate connection settings
        if self.connection_timeout < 0:
            raise ValueError("Connection timeout must be non-negative")
        if self.retry_attempts < 0:
            raise ValueError("Retry attempts must be non-negative")

        # Validate collection settings
        if not self.collection_name:
            raise ValueError("Collection name cannot be empty")
        if self.vector_size < 1:
            raise ValueError("Vector size must be positive")
        if self.distance not in ["Cosine", "Euclidean", "Dot"]:
            raise ValueError(f"Invalid distance metric: {self.distance}")

        # Validate storage settings
        if self.compression_threshold < 0:
            raise ValueError("Compression threshold must be non-negative")
        if self.compression_type not in ["gzip", "none"]:
            raise ValueError(f"Invalid compression type: {self.compression_type}")

        # Validate search settings
        if self.default_search_limit < 1:
            raise ValueError("Default search limit must be positive")
        if not 0.0 <= self.score_threshold <= 1.0:
            raise ValueError("Score threshold must be between 0.0 and 1.0")

        # Validate middleware settings
        if not self.embedding_model:
            raise ValueError("Embedding model cannot be empty")
        if self.summary_max_tokens < 1:
            raise ValueError("Summary max tokens must be positive")

        # Validate data retention settings
        if self.cache_retention_days < 1:
            raise ValueError("Cache retention days must be positive")

        # Validate optimization profile
        if not isinstance(self.optimization_profile, OptimizationProfile):
            raise ValueError(
                f"Invalid optimization profile: {self.optimization_profile}"
            )

    def to_dict(self) -> dict:
        """Convert configuration to dictionary."""
        return {
            "host": self.host,
            "ports": self.ports,
            "connection_timeout": self.connection_timeout,
            "retry_attempts": self.retry_attempts,
            "collection_name": self.collection_name,
            "vector_size": self.vector_size,
            "distance": self.distance,
            "compression_threshold": self.compression_threshold,
            "compression_type": self.compression_type,
            "default_search_limit": self.default_search_limit,
            "score_threshold": self.score_threshold,
            "embedding_model": self.embedding_model,
            "summary_max_tokens": self.summary_max_tokens,
            "verbose_param": self.verbose_param,
            "enabled": self.enabled,
            "cache_retention_days": self.cache_retention_days,
            "collection_schema": self.collection_schema.value,
            "dual_write": self.dual_write,
            "v7_collection_name": self.v7_collection_name,
            "optimization_profile": self.optimization_profile.value,
        }

    @classmethod
    def from_dict(cls, config_dict: dict) -> "QdrantConfig":
        """Create configuration from dictionary."""
        config_dict = config_dict.copy()
        # Handle optimization_profile conversion from string to enum
        if "optimization_profile" in config_dict and isinstance(
            config_dict["optimization_profile"], str
        ):
            config_dict["optimization_profile"] = OptimizationProfile(
                config_dict["optimization_profile"]
            )
        # Handle collection_schema conversion from string to enum
        if "collection_schema" in config_dict and isinstance(
            config_dict["collection_schema"], str
        ):
            config_dict["collection_schema"] = CollectionSchema(
                config_dict["collection_schema"]
            )
        return cls(**config_dict)

    def clone(self) -> "QdrantConfig":
        """Create a copy of this configuration."""
        return QdrantConfig.from_dict(self.to_dict())

    def get_optimization_params(self) -> Dict[str, Any]:
        """
        Get optimization parameters based on the selected profile.

        Returns:
            Dict with optimization parameters for Qdrant collection creation
        """
        profiles = {
            OptimizationProfile.CLOUD_LOW_LATENCY: {
                "description": "Optimized for cloud deployment with small datasets and lowest latency",
                "vector_config": {
                    "on_disk": False  # Keep in memory for fastest access
                },
                "hnsw_config": {
                    "ef_construct": 200,  # Higher quality, slower build
                    "m": 32,  # Better search quality
                    "on_disk": False,  # Keep in memory
                },
                "optimizer_config": {
                    "indexing_threshold": 1000,  # Index immediately for small datasets
                    "memmap_threshold": 50000,  # Use memory for small datasets
                    "default_segment_number": 2,  # Fewer segments for small data
                    "deleted_threshold": 0.1,  # Clean up sooner
                    "vacuum_min_vector_number": 100,  # Lower threshold
                },
            },
            OptimizationProfile.CLOUD_BALANCED: {
                "description": "Balanced cloud deployment for medium datasets",
                "vector_config": {
                    "on_disk": False  # Still keep in memory for good performance
                },
                "hnsw_config": {
                    "ef_construct": 100,  # Default quality/speed balance
                    "m": 16,  # Default connectivity
                    "on_disk": False,  # Keep in memory
                },
                "optimizer_config": {
                    "indexing_threshold": 10000,  # Standard indexing threshold
                    "memmap_threshold": 20000,  # Standard memmap threshold (same as indexing)
                    "default_segment_number": 0,  # Auto-detect based on CPUs
                    "deleted_threshold": 0.2,  # Default cleanup threshold
                    "vacuum_min_vector_number": 1000,  # Default
                },
            },
            OptimizationProfile.CLOUD_LARGE_SCALE: {
                "description": "Optimized for large-scale cloud deployment",
                "vector_config": {
                    "on_disk": True  # Use disk storage for large datasets
                },
                "hnsw_config": {
                    "ef_construct": 100,  # Balance quality vs build time
                    "m": 16,  # Standard connectivity
                    "on_disk": True,  # Use disk for HNSW index
                },
                "optimizer_config": {
                    "indexing_threshold": 20000,  # Higher threshold for large data
                    "memmap_threshold": 10000,  # Lower memmap threshold (disk first)
                    "default_segment_number": 0,  # Auto-detect
                    "deleted_threshold": 0.3,  # Less aggressive cleanup
                    "vacuum_min_vector_number": 5000,  # Higher threshold
                },
            },
            OptimizationProfile.LOCAL_DEVELOPMENT: {
                "description": "Fast startup for local development",
                "vector_config": {"on_disk": False},  # Memory for fast access
                "hnsw_config": {
                    "ef_construct": 50,  # Lower quality, faster build
                    "m": 8,  # Lower connectivity, faster
                    "on_disk": False,  # Memory
                },
                "optimizer_config": {
                    "indexing_threshold": 100,  # Very low threshold for immediate indexing
                    "memmap_threshold": 100000,  # High threshold to stay in memory
                    "default_segment_number": 1,  # Single segment for simplicity
                    "deleted_threshold": 0.05,  # Aggressive cleanup
                    "vacuum_min_vector_number": 10,  # Very low threshold
                },
            },
        }

        return profiles[self.optimization_profile]


def get_default_config() -> QdrantConfig:
    """Get default Qdrant configuration."""
    return QdrantConfig()


def load_config_from_settings() -> QdrantConfig:
    """Load configuration from centralized settings (preferred method)."""
    try:
        from config.settings import settings

        config = QdrantConfig()

        # Use centralized settings for cache retention
        config.cache_retention_days = settings.mcp_tool_responses_collection_cache_days

        # Use centralized Qdrant settings
        if settings.qdrant_host:
            config.host = settings.qdrant_host

        if settings.qdrant_port:
            config.ports = [settings.qdrant_port] + [
                p for p in config.ports if p != settings.qdrant_port
            ]

        # Primary collection from centralized settings (TOOL_COLLECTION)
        # This allows a single env var to define the main tool-response collection
        if getattr(settings, "tool_collection", None):
            config.collection_name = settings.tool_collection

        # Additional overrides from environment variables if present
        import os

        if os.getenv("QDRANT_COLLECTION"):
            config.collection_name = os.getenv("QDRANT_COLLECTION")

        if os.getenv("QDRANT_EMBEDDING_MODEL"):
            config.embedding_model = os.getenv("QDRANT_EMBEDDING_MODEL")

        if os.getenv("QDRANT_ENABLED"):
            config.enabled = os.getenv("QDRANT_ENABLED").lower() in ["true", "1", "yes"]

        if os.getenv("QDRANT_OPTIMIZATION_PROFILE"):
            try:
                config.optimization_profile = OptimizationProfile(
                    os.getenv("QDRANT_OPTIMIZATION_PROFILE")
                )
            except ValueError:
                # Invalid profile name, keep default
                pass

        if os.getenv("QDRANT_COLLECTION_SCHEMA"):
            try:
                config.collection_schema = CollectionSchema(
                    os.getenv("QDRANT_COLLECTION_SCHEMA")
                )
            except ValueError:
                pass

        if os.getenv("QDRANT_DUAL_WRITE"):
            config.dual_write = os.getenv("QDRANT_DUAL_WRITE").lower() in [
                "true",
                "1",
                "yes",
            ]

        if os.getenv("QDRANT_V7_COLLECTION"):
            config.v7_collection_name = os.getenv("QDRANT_V7_COLLECTION")

        return config

    except ImportError:
        # Fallback to legacy environment-only loading
        return load_config_from_env()


def load_config_from_env() -> QdrantConfig:
    """Load configuration from environment variables (legacy method)."""
    import os

    config = QdrantConfig()

    # Override with environment variables if present
    if os.getenv("QDRANT_HOST"):
        config.host = os.getenv("QDRANT_HOST")

    if os.getenv("QDRANT_PORT"):
        port = int(os.getenv("QDRANT_PORT"))
        config.ports = [port] + [p for p in config.ports if p != port]

    if os.getenv("QDRANT_COLLECTION"):
        config.collection_name = os.getenv("QDRANT_COLLECTION")

    if os.getenv("QDRANT_EMBEDDING_MODEL"):
        config.embedding_model = os.getenv("QDRANT_EMBEDDING_MODEL")

    if os.getenv("QDRANT_ENABLED"):
        config.enabled = os.getenv("QDRANT_ENABLED").lower() in ["true", "1", "yes"]

    if os.getenv("MCP_TOOL_RESPONSES_COLLECTION_CACHE_DAYS"):
        config.cache_retention_days = int(
            os.getenv("MCP_TOOL_RESPONSES_COLLECTION_CACHE_DAYS")
        )

    if os.getenv("QDRANT_OPTIMIZATION_PROFILE"):
        try:
            config.optimization_profile = OptimizationProfile(
                os.getenv("QDRANT_OPTIMIZATION_PROFILE")
            )
        except ValueError:
            # Invalid profile name, keep default
            pass

    if os.getenv("QDRANT_COLLECTION_SCHEMA"):
        try:
            config.collection_schema = CollectionSchema(
                os.getenv("QDRANT_COLLECTION_SCHEMA")
            )
        except ValueError:
            pass

    if os.getenv("QDRANT_DUAL_WRITE"):
        config.dual_write = os.getenv("QDRANT_DUAL_WRITE").lower() in [
            "true",
            "1",
            "yes",
        ]

    return config
