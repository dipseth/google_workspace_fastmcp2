"""
Type definitions for Gmail tool responses.

These TypedDict classes define the structure of data returned by Gmail tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

from typing_extensions import TypedDict, List, Optional, Dict, Any, NotRequired


class FilterCriteria(TypedDict):
    """Structure for Gmail filter criteria."""
    from_address: Optional[str]
    to_address: Optional[str]
    subject: Optional[str]
    query: Optional[str]
    hasAttachment: Optional[bool]
    excludeChats: Optional[bool]
    size: Optional[int]
    sizeComparison: Optional[str]


class FilterAction(TypedDict):
    """Structure for Gmail filter actions."""
    addLabelIds: Optional[List[str]]
    removeLabelIds: Optional[List[str]]
    forward: Optional[str]
    markAsSpam: Optional[bool]
    markAsImportant: Optional[bool]
    neverMarkAsSpam: Optional[bool]
    neverMarkAsImportant: Optional[bool]


class FilterInfo(TypedDict):
    """Structure for a single Gmail filter entry."""
    id: str
    criteria: FilterCriteria
    action: FilterAction


class GmailFiltersResponse(TypedDict):
    """Response structure for list_gmail_filters tool."""
    filters: List[FilterInfo]
    count: int
    userEmail: str
    error: NotRequired[Optional[str]]  # Optional error message for error responses


class AllowedEmailInfo(TypedDict):
    """Structure for a single allowed email entry."""
    email: str
    masked_email: str  # Privacy-masked version of the email


class GmailAllowListResponse(TypedDict):
    """Response structure for view_gmail_allow_list tool."""
    allowed_emails: List[AllowedEmailInfo]
    count: int
    userEmail: str
    is_configured: bool
    source: str  # "GMAIL_ALLOW_LIST environment variable"
    error: NotRequired[Optional[str]]  # Optional error message for error responses


class EmailTemplateInfo(TypedDict):
    """Structure for a single email template entry."""
    id: str
    name: str
    description: str
    placeholders: List[str]
    tags: List[str]
    created_at: str
    assigned_users: List[str]


class EmailTemplatesResponse(TypedDict):
    """Response structure for list_email_templates tool."""
    templates: List[EmailTemplateInfo]
    count: int
    userEmail: str
    search_query: Optional[str]
    error: NotRequired[Optional[str]]  # Optional error message for error responses


class GmailLabelInfo(TypedDict):
    """Structure for a single Gmail label entry."""
    id: str
    name: str
    type: str  # "system" or "user"
    messageListVisibility: Optional[str]
    labelListVisibility: Optional[str]
    color: Optional[Dict[str, str]]  # Contains textColor and backgroundColor
    messagesTotal: Optional[int]
    messagesUnread: Optional[int]
    threadsTotal: Optional[int]
    threadsUnread: Optional[int]


class GmailLabelsResponse(TypedDict):
    """Response structure for list_gmail_labels tool."""
    labels: List[GmailLabelInfo]
    total_count: int
    system_labels: List[GmailLabelInfo]
    user_labels: List[GmailLabelInfo]
    error: NotRequired[Optional[str]]  # Optional error message for error responses