"""
Type definitions for Google Docs tool responses.

These TypedDict classes define the structure of data returned by Docs tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

from typing_extensions import TypedDict, List, Optional, NotRequired, Literal
from pydantic import BaseModel, Field


class RegexReplace(BaseModel):
    """Configuration for regex search and replace operation."""

    pattern: str = Field(..., description="Regex pattern to search for")
    replacement: str = Field(..., description="Text to replace matches with")
    flags: Optional[str] = Field(
        default=None,
        description="Regex flags (e.g., 'i' for case-insensitive, 'm' for multiline)",
    )


class EditConfig(BaseModel):
    """
    Configuration for granular document editing operations.

    Supports four editing modes:
    - replace_all: Replace entire document content (default behavior)
    - insert_at_line: Insert content at a specific line number
    - regex_replace: Perform regex search and replace operations
    - append: Append content to the end of the document
    """

    mode: Literal["replace_all", "insert_at_line", "regex_replace", "append"] = Field(
        default="replace_all", description="Editing mode to use"
    )

    # For insert_at_line mode
    line_number: Optional[int] = Field(
        default=None,
        description="Line number to insert content at (1-based, required for insert_at_line mode)",
    )

    # For regex_replace mode
    regex_operations: Optional[List[RegexReplace]] = Field(
        default=None,
        description="List of regex search/replace operations (required for regex_replace mode)",
    )

    preserve_formatting: bool = Field(
        default=True,
        description="Whether to preserve existing document formatting when editing",
    )

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True


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


class CreateDocResponse(TypedDict):
    """Response structure for create_doc tool with enhanced metadata."""

    docId: str
    docName: str
    webViewLink: str
    mimeType: str  # Always 'application/vnd.google-apps.document' for Google Docs
    sourceContentType: (
        str  # Detected type: 'plain', 'markdown', 'html', 'rtf', 'docx', etc.
    )
    uploadMimeType: (
        str  # Actual MIME type used for upload (e.g., 'text/html', 'text/plain')
    )
    userEmail: str
    success: bool
    message: str
    contentLength: NotRequired[int]  # Length of original content
    hasFormatting: NotRequired[bool]  # Whether rich formatting was applied
    error: NotRequired[Optional[str]]
