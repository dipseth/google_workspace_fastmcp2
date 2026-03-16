"""
Type definitions for Google Chat tool responses.

These TypedDict classes define the structure of data returned by Chat tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

from pydantic import BaseModel
from pydantic import Field as PydanticField
from typing_extensions import List, NotRequired, Optional, TypedDict


class SpaceInfo(TypedDict):
    """Structure for a single Chat space entry."""

    id: str
    displayName: str
    spaceType: str  # 'SPACE', 'DIRECT_MESSAGE', etc.
    singleUserBotDm: Optional[bool]
    threaded: Optional[bool]
    spaceHistoryState: Optional[str]


class MessageInfo(TypedDict):
    """Structure for a single Chat message."""

    id: str
    text: str
    senderName: str
    senderEmail: Optional[str]
    createTime: str
    threadId: Optional[str]
    spaceName: Optional[str]
    attachments: Optional[List[dict]]


class SpaceListResponse(TypedDict):
    """Response structure for list_spaces tool."""

    spaces: List[SpaceInfo]
    count: int
    spaceType: str  # Filter type used: 'all', 'room', 'dm'
    userEmail: str
    error: NotRequired[Optional[str]]  # Optional error message for error responses


class MessageListResponse(TypedDict):
    """Response structure for list_messages tool."""

    messages: List[MessageInfo]
    count: int
    spaceId: str
    spaceName: str
    orderBy: str
    userEmail: str
    error: NotRequired[Optional[str]]  # Optional error message for error responses


class CardTypeInfo(TypedDict):
    """Structure for a single card type entry."""

    type: str
    description: str
    supported_features: List[str]


class CardTypesResponse(TypedDict):
    """Response structure for list_available_card_types tool."""

    card_types: List[CardTypeInfo]
    count: int
    framework_status: str
    error: NotRequired[Optional[str]]  # Optional error message for error responses


class CardComponentInfo(TypedDict):
    """Structure for a single card component entry."""

    name: str
    path: str
    type: str
    score: Optional[float]
    docstring: str


class CardComponentsResponse(TypedDict):
    """Response structure for list_available_card_components tool."""

    components: List[CardComponentInfo]
    count: int
    query: str
    error: NotRequired[Optional[str]]  # Optional error message for error responses


class CardTemplateInfo(TypedDict):
    """Structure for a single card template entry."""

    template_id: str
    name: str
    description: str
    created_at: Optional[str]
    template: Optional[dict]  # The actual template data


class CardTemplatesResponse(TypedDict):
    """Response structure for list_card_templates tool."""

    templates: List[CardTemplateInfo]
    count: int
    query: str
    # error: NotRequired[Optional[str]]
    error: NotRequired[Optional[str]]


class JWTSpaceInfo(TypedDict):
    """Structure for a single JWT-authenticated Chat space entry."""

    name: str
    displayName: str
    type: str
    spaceType: str  # 'SPACE', 'DIRECT_MESSAGE', etc.
    threaded: bool
    spaceDetails: dict
    memberCount: Optional[int]


class JWTSpacesResponse(TypedDict):
    """Response structure for list_spaces_jwt tool."""

    spaces: List[JWTSpaceInfo]
    count: int
    userEmail: str
    authMethod: str  # 'JWT Bearer Token', 'resource_context', etc.
    filterApplied: str  # 'all', 'room', 'dm'
    error: NotRequired[Optional[str]]  # Optional error message for error responses


class SendMessageResponse(TypedDict):
    """Response structure for send_message tool."""

    success: bool
    messageId: Optional[str]
    spaceId: str
    messageText: str
    threadKey: Optional[str]
    createTime: Optional[str]
    userEmail: str
    message: str
    error: NotRequired[Optional[str]]


class SearchMessageResult(TypedDict):
    """Structure for individual search message result."""

    messageId: str
    text: str
    senderName: str
    createTime: str
    spaceName: str
    spaceId: str


class SearchMessagesResponse(TypedDict):
    """Response structure for search_messages tool."""

    success: bool
    query: str
    results: List[SearchMessageResult]
    totalResults: int
    searchScope: str  # 'specific_space' or 'all_spaces'
    spaceId: Optional[str]  # If searching within specific space
    userEmail: str
    message: str
    error: NotRequired[Optional[str]]


class MemberInfo(TypedDict):
    """Structure for a single Chat space member."""

    name: str  # Full resource name (spaces/xxx/members/yyy)
    email: Optional[str]
    displayName: str
    role: str  # ROLE_MEMBER or ROLE_MANAGER
    type: str  # HUMAN or BOT
    createTime: Optional[str]


class ManageSpaceResponse(TypedDict):
    """Response structure for manage_space tool."""

    success: bool
    action: str
    spaceId: Optional[str]
    data: Optional[dict]
    message: str
    error: NotRequired[Optional[str]]


class SendCardMessageResponse(TypedDict):
    """Response structure for send_card_message tool."""

    success: bool
    messageId: Optional[str]
    spaceId: str
    cardType: str
    title: str
    deliveryMethod: str  # 'api' or 'webhook'
    threadKey: Optional[str]
    createTime: Optional[str]
    webhookUrl: Optional[str]
    userEmail: str
    message: str
    error: NotRequired[Optional[str]]


class SendSimpleCardResponse(TypedDict):
    """Response structure for send_simple_card tool."""

    success: bool
    messageId: Optional[str]
    spaceId: str
    title: str
    deliveryMethod: str  # 'api' or 'webhook'
    webhookUrl: Optional[str]
    userEmail: str
    message: str
    error: NotRequired[Optional[str]]


class SendInteractiveCardResponse(TypedDict):
    """Response structure for send_interactive_card tool."""

    success: bool
    messageId: Optional[str]
    spaceId: str
    title: str
    buttonCount: int
    deliveryMethod: str  # 'api' or 'webhook'
    webhookUrl: Optional[str]
    userEmail: str
    message: str
    error: NotRequired[Optional[str]]


class SendFormCardResponse(TypedDict):
    """Response structure for send_form_card tool."""

    success: bool
    messageId: Optional[str]
    spaceId: str
    title: str
    fieldCount: int
    deliveryMethod: str  # 'api' or 'webhook'
    webhookUrl: Optional[str]
    userEmail: str
    message: str
    error: NotRequired[Optional[str]]


class SendRichCardResponse(TypedDict):
    """Response structure for send_rich_card tool."""

    success: bool
    messageId: Optional[str]
    spaceId: str
    title: str
    sectionCount: int
    deliveryMethod: str  # 'api' or 'webhook'
    webhookUrl: Optional[str]
    userEmail: str
    message: str
    error: NotRequired[Optional[str]]


class DigestMessageInfo(TypedDict):
    """Simplified message info for chat digest responses."""

    id: str
    text: str
    sender_name: str
    sender_email: Optional[str]
    create_time: str
    thread_id: Optional[str]


class DigestSpaceEntry(TypedDict):
    """Per-space entry in a chat digest response."""

    space_id: str
    display_name: str
    space_type: str
    message_count: int
    messages: List[DigestMessageInfo]


class ChatDigestResponse(TypedDict):
    """Response structure for chat digest resources."""

    user_email: str
    hours_back: int
    total_messages: int
    total_spaces_with_activity: int
    spaces_checked: int
    spaces: List[DigestSpaceEntry]
    timestamp: str
    error: NotRequired[Optional[str]]


# ---------------------------------------------------------------------------
# Pydantic models for Chat Digest resources (FastMCP 3.0+ pattern)
# ---------------------------------------------------------------------------


class DigestMessage(BaseModel):
    """A single message in a chat digest."""

    id: str = PydanticField(description="Full message resource name")
    text: str = PydanticField(description="Message text content")
    sender_name: str = PydanticField(description="Display name of the sender")
    sender_email: Optional[str] = PydanticField(
        default=None, description="Email of the sender if available"
    )
    create_time: str = PydanticField(description="ISO 8601 creation timestamp")
    thread_id: Optional[str] = PydanticField(
        default=None, description="Thread resource name for threaded conversations"
    )


class DigestSpace(BaseModel):
    """Per-space entry in a chat digest."""

    space_id: str = PydanticField(description="Full space resource name")
    display_name: str = PydanticField(description="Human-readable space name")
    space_type: str = PydanticField(
        description="Space type: SPACE, GROUP_CHAT, DIRECT_MESSAGE"
    )
    message_count: int = PydanticField(description="Number of messages in this space")
    messages: List[DigestMessage] = PydanticField(
        description="Recent messages ordered by createTime desc"
    )


class ChatDigest(BaseModel):
    """Aggregated digest of recent Google Chat messages across spaces."""

    user_email: str = PydanticField(description="Authenticated user email")
    hours_back: int = PydanticField(description="Hours of history included")
    limit: int = PydanticField(description="Max messages per space")
    total_messages: int = PydanticField(description="Total messages across all spaces")
    total_spaces_with_activity: int = PydanticField(
        description="Number of spaces with at least one message"
    )
    spaces_checked: int = PydanticField(
        description="Total spaces scanned (including empty ones)"
    )
    spaces: List[DigestSpace] = PydanticField(
        description="Spaces with recent activity, sorted by most recent message"
    )
    timestamp: str = PydanticField(description="ISO 8601 timestamp of the digest")
    error: Optional[str] = PydanticField(
        default=None, description="Error message if the digest could not be built"
    )
