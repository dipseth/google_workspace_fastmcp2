"""
Type definitions for Gmail tool responses.

These TypedDict classes define the structure of data returned by Gmail tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

from typing_extensions import TypedDict, List, Optional, Dict, Any, NotRequired, Union


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


class AllowedGroupInfo(TypedDict):
    """Structure for a single allowed group entry based on People API contact groups."""
    raw: str  # Raw token from GMAIL_ALLOW_LIST (e.g., "group:Team A" or "groupId:contactGroups/123")
    type: NotRequired[str]  # "name" or "id"
    group_name: NotRequired[str]  # Human-friendly group name when available
    group_id: NotRequired[str]  # Contact group resourceName when available (e.g., "contactGroups/123")


class GmailAllowListResponse(TypedDict):
    """Response structure for view_gmail_allow_list tool."""
    allowed_emails: List[AllowedEmailInfo]
    # Optional list of group-based allow list entries (People API contact groups)
    allowed_groups: NotRequired[List[AllowedGroupInfo]]
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
    system_count: int  # Number of system labels
    user_count: int  # Number of user-created labels
    id_to_name: Dict[str, str]  # Convenience map from label ID to label name
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
    labels: NotRequired[List[str]]  # Gmail label IDs applied to this message
    label_names: NotRequired[List[str]]  # Human-readable label names corresponding to labels
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
    labels_added_names: NotRequired[List[str]]  # Human-readable names for added labels
    labels_removed_names: NotRequired[List[str]]  # Human-readable names for removed labels
    userEmail: str
    error: NotRequired[Optional[str]]


class SendGmailMessageResponse(TypedDict):
    """Response structure for send_gmail_message tool."""
    success: bool
    message_id: NotRequired[Optional[str]]  # Optional when saved as draft instead of sent
    to_recipients: NotRequired[List[str]]  # Optional when blocked or draft
    cc_recipients: NotRequired[List[str]]
    bcc_recipients: NotRequired[List[str]]
    subject: NotRequired[str]  # Optional when blocked
    content_type: NotRequired[str]  # Optional when blocked
    template_applied: NotRequired[bool]
    template_name: NotRequired[Optional[str]]
    elicitation_triggered: NotRequired[bool]
    userEmail: NotRequired[str]  # Optional when user context unavailable
    error: NotRequired[Optional[str]]
    # Draft-specific fields for when email is saved as draft
    draftId: NotRequired[Optional[str]]
    recipientCount: NotRequired[int]
    action: NotRequired[str]  # "sent", "saved_draft", "blocked", etc.
    elicitationRequired: NotRequired[bool]
    elicitationNotSupported: NotRequired[bool]
    recipientsNotAllowed: NotRequired[List[str]]
    # Jinja2 template processing fields (from template middleware)
    jinjaTemplateApplied: NotRequired[bool]
    jinjaTemplateError: NotRequired[Optional[str]]


class DraftGmailMessageResponse(TypedDict):
    """Response structure for draft_gmail_message tool."""
    success: bool
    draft_id: NotRequired[Optional[str]]  # Optional when there's an error
    subject: str
    content_type: str
    has_recipients: bool
    recipient_count: int
    userEmail: str
    error: NotRequired[Optional[str]]


class ReplyGmailMessageResponse(TypedDict):
    """Response structure for reply_to_gmail_message tool."""
    success: bool
    reply_message_id: NotRequired[Optional[str]]  # Optional when there's an error
    original_message_id: str
    thread_id: NotRequired[Optional[str]]  # Optional when there's an error
    replied_to: NotRequired[Optional[str]]  # Recipients who received the reply (comma-separated)
    subject: NotRequired[Optional[str]]  # Optional when there's an error
    content_type: str
    reply_mode: NotRequired[str]  # "sender_only", "reply_all", or "custom"
    to_recipients: NotRequired[List[str]]  # List of To recipients
    cc_recipients: NotRequired[List[str]]  # List of CC recipients
    bcc_recipients: NotRequired[List[str]]  # List of BCC recipients
    userEmail: str
    error: NotRequired[Optional[str]]


class DraftGmailReplyResponse(TypedDict):
    """Response structure for draft_gmail_reply tool."""
    success: bool
    draft_id: NotRequired[Optional[str]]  # Optional when there's an error
    original_message_id: str
    thread_id: NotRequired[Optional[str]]  # Optional when there's an error
    replied_to: NotRequired[Optional[str]]  # Recipients who would receive the reply (comma-separated)
    subject: NotRequired[Optional[str]]  # Optional when there's an error
    content_type: str
    reply_mode: NotRequired[str]  # "sender_only", "reply_all", or "custom"
    to_recipients: NotRequired[List[str]]  # List of To recipients
    cc_recipients: NotRequired[List[str]]  # List of CC recipients
    bcc_recipients: NotRequired[List[str]]  # List of BCC recipients
    userEmail: str
    error: NotRequired[Optional[str]]


class ForwardGmailMessageResponse(TypedDict):
    """Response structure for forward_gmail_message tool."""
    success: bool
    forward_message_id: NotRequired[Optional[str]]  # Optional when there's an error
    original_message_id: str
    forwarded_to: NotRequired[Optional[str]]  # Recipients who received the forward (comma-separated)
    subject: NotRequired[Optional[str]]  # Optional when there's an error
    content_type: str
    to_recipients: NotRequired[List[str]]  # List of To recipients
    cc_recipients: NotRequired[List[str]]  # List of CC recipients
    bcc_recipients: NotRequired[List[str]]  # List of BCC recipients
    html_preserved: NotRequired[bool]  # Whether original HTML formatting was preserved
    userEmail: str
    error: NotRequired[Optional[str]]
    # Elicitation support fields
    elicitationRequired: NotRequired[bool]
    elicitationNotSupported: NotRequired[bool]
    recipientsNotAllowed: NotRequired[List[str]]
    action: NotRequired[str]  # "forwarded", "saved_draft", "blocked", etc.
    draftId: NotRequired[Optional[str]]  # Draft ID when saved as draft instead


class DraftGmailForwardResponse(TypedDict):
    """Response structure for draft_gmail_forward tool."""
    success: bool
    draft_id: NotRequired[Optional[str]]  # Optional when there's an error
    original_message_id: str
    forwarded_to: NotRequired[Optional[str]]  # Recipients who would receive the forward (comma-separated)
    subject: NotRequired[Optional[str]]  # Optional when there's an error
    content_type: str
    to_recipients: NotRequired[List[str]]  # List of To recipients
    cc_recipients: NotRequired[List[str]]  # List of CC recipients
    bcc_recipients: NotRequired[List[str]]  # List of BCC recipients
    html_preserved: NotRequired[bool]  # Whether original HTML formatting was preserved
    userEmail: str
    error: NotRequired[Optional[str]]


# Gmail Recipient Types

# Standardized types for Gmail recipient fields
GmailRecipients = Union[str, List[str]]
"""
Standardized type for required Gmail recipient fields (to field).
Supports three formats:
- Single email string: "user@example.com"
- List of emails: ["user1@example.com", "user2@example.com"]
- Comma-separated string: "user1@example.com,user2@example.com"
"""

GmailRecipientsOptional = Optional[Union[str, List[str]]]
"""
Standardized type for optional Gmail recipient fields (cc, bcc fields).
Supports same formats as GmailRecipients but can also be None.
"""


# Unified Gmail Message Content Types


class GmailMessageData(TypedDict):
    """Structure for unified Gmail message data."""
    message_id: str
    thread_id: str
    subject: str
    sender: str
    recipients: List[str]
    cc: NotRequired[List[str]]
    bcc: NotRequired[List[str]]
    date: NotRequired[Optional[str]]
    body_text: NotRequired[Optional[str]]  # Only when format="full"
    body_html: NotRequired[Optional[str]]  # Only when format="full"
    headers: NotRequired[Dict[str, str]]
    attachments: NotRequired[List[str]]
    labels: NotRequired[List[str]]
    web_url: str


class GmailMessageContentResponse(TypedDict):
    """Response structure for unified get_gmail_message_content tool."""
    success: bool
    messages: List[GmailMessageData]
    total_count: int
    request_type: str  # "single", "batch", "thread"
    thread_id: NotRequired[Optional[str]]
    format: str
    user_email: str
    error: NotRequired[Optional[str]]