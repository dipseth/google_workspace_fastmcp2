"""
Type definitions for Google Chat tool responses.

These TypedDict classes define the structure of data returned by Chat tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

from typing import TypedDict, List, Optional


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


class MessageListResponse(TypedDict):
    """Response structure for list_messages tool."""
    messages: List[MessageInfo]
    count: int
    spaceId: str
    spaceName: str
    orderBy: str
    userEmail: str