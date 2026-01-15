"""
Gmail tools for FastMCP2 with middleware-based service injection and fallback support.

This module provides comprehensive Gmail integration tools for FastMCP2 servers,
using the new middleware-dependent pattern for Google service authentication with
fallback to direct service creation when middleware injection is unavailable.

Key Features:
- Message search and retrieval with Gmail query syntax
- Batch message processing for efficiency
- Email composition, sending, and draft creation
- Thread-based conversation handling
- Label management and message labeling
- Reply functionality with proper threading
- Gmail filter/rule management with retroactive application
- Allow list management for trusted recipients
- Comprehensive error handling with user-friendly messages
- Fallback to direct service creation when middleware unavailable

Architecture:
- Primary: Uses middleware-based service injection (no decorators)
- Fallback: Direct service creation when middleware unavailable
- Automatic Google service authentication and caching
- Consistent error handling and token refresh
- FastMCP2 framework integration
- Modular design with specialized tool modules

Dependencies:
- google-api-python-client: Gmail API integration
- fastmcp: FastMCP server framework
- auth.service_helpers: Service injection utilities

Tool Modules:
- gmail.messages: Message search, retrieval, and batch operations
- gmail.compose: Email composition, sending, and drafting
- gmail.labels: Label management and message labeling
- gmail.filters: Gmail filter/rule management
- gmail.allowlist: Allow list management for trusted recipients
- gmail.service: Gmail service authentication and setup coordination
"""

from fastmcp import FastMCP

from config.enhanced_logging import setup_logger

logger = setup_logger()


def setup_gmail_tools(mcp: FastMCP) -> None:
    """
    Register Gmail tools with the FastMCP server using middleware-based service injection with fallback.

    This function delegates to the modular Gmail tools setup that imports all specialized
    tool modules. Each module auto-registers its tools when imported.

    Args:
        mcp: FastMCP server instance to register tools with

    Returns:
        None: Tools are registered as side effects through module imports
    """
    # Delegate to the modular setup function
    from .service import setup_gmail_tools as _setup_modular_gmail_tools

    logger.info("Setting up Gmail tools (delegating to modular structure)...")
    _setup_modular_gmail_tools(mcp)
    logger.info("✅ Gmail tools setup completed via modular delegation")
