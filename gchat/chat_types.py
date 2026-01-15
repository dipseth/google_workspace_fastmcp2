"""
Type definitions for Google Chat tool responses.

These TypedDict classes define the structure of data returned by Chat tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

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
