"""
Gmail integration tools for FastMCP2.

This package provides comprehensive Gmail integration tools including:
- Message search and retrieval
- Email composition and sending with elicitation support
- Label management
- Filter management
- Allow list management for security

The package is organized into logical modules:
- utils: Utility functions and helpers
- service: Gmail service management and authentication
- messages: Message reading and search tools
- compose: Email composition and sending tools
- labels: Gmail label management tools
- filters: Gmail filter management tools
- allowlist: Allow list management for elicitation security
"""

from .allowlist import *
from .compose import *
from .filters import *
from .labels import *
from .messages import *
from .service import *
from .utils import *

__version__ = "1.0.0"
__all__ = [
    # Utils
    "GMAIL_LABEL_COLORS",
    "_validate_gmail_color",
    "_format_label_color_info",
    "_extract_message_body",
    "_extract_headers",
    "_generate_gmail_web_url",
    "_format_gmail_results_plain",
    "_prepare_reply_subject",
    "_quote_original_message",
    "_html_to_plain_text",
    "_create_mime_message",
    # Service
    "_get_gmail_service_with_fallback",
    "setup_gmail_tools",
    # Messages
    "search_gmail_messages",
    "get_gmail_message_content",
    "get_gmail_messages_content_batch",
    "get_gmail_thread_content",
    # Compose
    "send_gmail_message",
    "draft_gmail_message",
    "reply_to_gmail_message",
    "draft_gmail_reply",
    # Labels
    "list_gmail_labels",
    "manage_gmail_label",
    "modify_gmail_message_labels",
    # Filters
    "list_gmail_filters",
    "create_gmail_filter",
    "get_gmail_filter",
    "delete_gmail_filter",
    # Allow List
    "add_to_gmail_allow_list",
    "remove_from_gmail_allow_list",
    "view_gmail_allow_list",
]
