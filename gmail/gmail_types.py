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


class RetroactiveResults(TypedDict):
    """Structure for retroactive filter application results."""
    total_found: int
    processed_count: int
    error_count: int
    errors: List[str]
    truncated: bool


class CreateGmailFilterResponse(TypedDict):
    """Response structure for create_gmail_filter tool."""
    success: bool
    filter_id: NotRequired[Optional[str]]
    criteria_summary: NotRequired[Optional[str]]
    actions_summary: NotRequired[Optional[str]]
    retroactive_results: NotRequired[Optional[RetroactiveResults]]
    error: NotRequired[Optional[str]]


class GetGmailFilterResponse(TypedDict):
    """Response structure for get_gmail_filter tool."""
    success: bool
    filter_info: NotRequired[Optional[FilterInfo]]
    filter_id: str
    userEmail: str
    error: NotRequired[Optional[str]]


class DeleteGmailFilterResponse(TypedDict):
    """Response structure for delete_gmail_filter tool."""
    success: bool
    filter_id: str
    criteria_summary: NotRequired[Optional[str]]
    userEmail: str
    error: NotRequired[Optional[str]]


class GmailMessageInfo(TypedDict):
    """Structure for a single Gmail message entry."""
    id: str
    thread_id: str
    snippet: NotRequired[Optional[str]]
    subject: NotRequired[Optional[str]]
    sender: NotRequired[Optional[str]]
    date: NotRequired[Optional[str]]
    web_url: str


class SearchGmailMessagesResponse(TypedDict):
    """Response structure for search_gmail_messages tool."""
    success: bool
    messages: List[GmailMessageInfo]
    total_found: int
    query: str
    userEmail: str
    page_size: int
    error: NotRequired[Optional[str]]


class GmailMessageContent(TypedDict):
    """Structure for Gmail message content."""
    id: str
    subject: str
    sender: str
    date: NotRequired[Optional[str]]
    body: str
    web_url: str


class GetGmailMessageContentResponse(TypedDict):
    """Response structure for get_gmail_message_content tool."""
    success: bool
    message_content: NotRequired[Optional[GmailMessageContent]]
    userEmail: str
    error: NotRequired[Optional[str]]


class BatchMessageResult(TypedDict):
    """Structure for individual message in batch result."""
    id: str
    success: bool
    subject: NotRequired[Optional[str]]
    sender: NotRequired[Optional[str]]
    date: NotRequired[Optional[str]]
    body: NotRequired[Optional[str]]
    web_url: str
    error: NotRequired[Optional[str]]


class GetGmailMessagesBatchResponse(TypedDict):
    """Response structure for get_gmail_messages_content_batch tool."""
    success: bool
    messages: List[BatchMessageResult]
    total_requested: int
    successful_count: int
    failed_count: int
    format: str
    userEmail: str
    error: NotRequired[Optional[str]]


class ThreadMessageInfo(TypedDict):
    """Structure for a message within a thread."""
    message_number: int
    id: str
    subject: str
    sender: str
    date: str
    body: str


class GetGmailThreadContentResponse(TypedDict):
    """Response structure for get_gmail_thread_content tool."""
    success: bool
    thread_id: str
    thread_subject: str
    message_count: int
    messages: List[ThreadMessageInfo]
    userEmail: str
    error: NotRequired[Optional[str]]


class ManageGmailLabelResponse(TypedDict):
    """Response structure for manage_gmail_label tool."""
    success: bool
    action: str
    labels_processed: int
    results: List[str]
    color_adjustments: NotRequired[Optional[List[str]]]
    userEmail: str
    error: NotRequired[Optional[str]]


class ModifyGmailMessageLabelsResponse(TypedDict):
    """Response structure for modify_gmail_message_labels tool."""
    success: bool
    message_id: str
    labels_added: List[str]
    labels_removed: List[str]
    userEmail: str
    error: NotRequired[Optional[str]]


class SendGmailMessageResponse(TypedDict):
    """Response structure for send_gmail_message tool."""
    success: bool
    message_id: str
    to_recipients: List[str]
    cc_recipients: NotRequired[List[str]]
    bcc_recipients: NotRequired[List[str]]
    subject: str
    content_type: str
    template_applied: NotRequired[bool]
    template_name: NotRequired[Optional[str]]
    elicitation_triggered: NotRequired[bool]
    userEmail: str
    error: NotRequired[Optional[str]]


class DraftGmailMessageResponse(TypedDict):
    """Response structure for draft_gmail_message tool."""
    success: bool
    draft_id: str
    subject: str
    content_type: str
    has_recipients: bool
    recipient_count: int
    userEmail: str
    error: NotRequired[Optional[str]]


class ReplyGmailMessageResponse(TypedDict):
    """Response structure for reply_to_gmail_message tool."""
    success: bool
    reply_message_id: str
    original_message_id: str
    thread_id: str
    replied_to: str
    subject: str
    content_type: str
    userEmail: str
    error: NotRequired[Optional[str]]


class DraftGmailReplyResponse(TypedDict):
    """Response structure for draft_gmail_reply tool."""
    success: bool
    draft_id: str
    original_message_id: str
    thread_id: str
    replied_to: str
    subject: str
    content_type: str
    userEmail: str
    error: NotRequired[Optional[str]]