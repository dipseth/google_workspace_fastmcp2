"""
Type definitions for Google Docs tool responses.

These TypedDict classes define the structure of data returned by Docs tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""


from typing_extensions import TypedDict, List, Optional,NotRequired


class DocInfo(TypedDict):
    """Structure for a single document entry."""
    id: str
    name: str
    modifiedTime: Optional[str]
    webViewLink: Optional[str]


class DocsListResponse(TypedDict):
    """Response structure for list_docs_in_folder tool."""
    docs: List[DocInfo]
    count: int
    folderId: str
    folderName: Optional[str]
    userEmail: str
    error: NotRequired[Optional[str]] 