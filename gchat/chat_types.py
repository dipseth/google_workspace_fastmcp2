"""
Type definitions for Google Chat tool responses.

These TypedDict classes define the structure of data returned by Chat tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

from typing_extensions import TypedDict, List, Optional,NotRequired


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
    error: Optional[str]  # Optional error message for error responses


class MessageListResponse(TypedDict):
    """Response structure for list_messages tool."""
    messages: List[MessageInfo]
    count: int
    spaceId: str
    spaceName: str
    orderBy: str
    userEmail: str
    error: Optional[str]  # Optional error message for error responses


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
    error: Optional[str]  # Optional error message for error responses


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
    error: Optional[str]  # Optional error message for error responses


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
    error: Optional[str]  # Optional error message for error responses