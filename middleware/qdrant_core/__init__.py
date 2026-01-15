"""
Qdrant Core Module

This package contains the core functionality extracted from the main
Qdrant middleware, organized into focused, reusable modules:

- query_parser: Query parsing and formatting functionality
- lazy_imports: Lazy loading utilities for heavy dependencies
- config: Configuration classes and validation

This modular structure allows for better code organization, testing,
and maintenance while keeping the main middleware focused on FastMCP
integration hooks.
"""

# Import core functionality from submodules
from .client import (
    QdrantClientManager,
)
from .config import (
    PayloadType,
    QdrantConfig,
    get_default_config,
    load_config_from_env,
    load_config_from_settings,
)
from .lazy_imports import (
    _get_fastembed,
    # Legacy aliases
    _get_numpy,
    _get_qdrant_imports,
    get_fastembed,
    get_import_status,
    get_numpy,
    get_qdrant_imports,
    reset_imports,
)
from .query_parser import (
    _extract_service_from_tool,
    _format_search_results,
    # Legacy aliases
    _parse_search_query,
    _parse_unified_query,
    extract_service_from_tool,
    format_search_results,
    parse_search_query,
    parse_unified_query,
)
from .resource_handler import (
    QdrantResourceHandler,
)
from .resources import (
    setup_qdrant_resources,
)
from .search import (
    QdrantSearchManager,
)
from .storage import (
    QdrantStorageManager,
)
from .tools import (
    setup_enhanced_qdrant_tools,
)

# Version information
__version__ = "1.0.0"

# Public API exports
__all__ = [
    # Query parsing functions
    "parse_search_query",
    "parse_unified_query",
    "format_search_results",
    "extract_service_from_tool",
    # Lazy import functions
    "get_numpy",
    "get_qdrant_imports",
    "get_fastembed",
    "reset_imports",
    "get_import_status",
    # Configuration classes
    "PayloadType",
    "QdrantConfig",
    "get_default_config",
    "load_config_from_env",
    # Client management
    "QdrantClientManager",
    # Storage management
    "QdrantStorageManager",
    # Search management
    "QdrantSearchManager",
    # Resource handling
    "QdrantResourceHandler",
    # Tool and resource setup functions
    "setup_enhanced_qdrant_tools",
    "setup_qdrant_resources",
    # Legacy aliases (for backward compatibility)
    "_parse_search_query",
    "_parse_unified_query",
    "_format_search_results",
    "_extract_service_from_tool",
    "_get_numpy",
    "_get_qdrant_imports",
    "_get_fastembed",
]


def get_module_info():
    """
    Get information about the qdrant_core module.

    Returns:
        dict: Module information including version and available components
    """
    return {
        "version": __version__,
        "modules": {
            "query_parser": "Query parsing and formatting functionality",
            "lazy_imports": "Lazy loading utilities for dependencies",
            "config": "Configuration classes and validation",
            "client": "Client connection and management functionality",
            "storage": "Storage operations and data persistence functionality",
            "search": "Search and analytics operations functionality",
        },
        "import_status": get_import_status(),
    }
