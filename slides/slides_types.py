"""
Type definitions for Google Slides tool responses.

These TypedDict classes define the structure of data returned by Slides tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

from typing_extensions import Dict, List, NotRequired, Optional, TypedDict


class SlideInfo(TypedDict):
    """Structure for a single slide within a presentation."""

    objectId: str
    index: int
    elementCount: int
    elementTypes: Dict[str, int]  # e.g., {"shapes": 2, "tables": 1}


class PageSize(TypedDict):
    """Structure for page size information."""

    width: float
    height: float
    unit: str


class CreatePresentationResponse(TypedDict):
    """Response structure for create_presentation tool."""

    presentationId: str
    presentationUrl: str
    title: str
    slideCount: int
    success: bool
    message: str
    userEmail: NotRequired[str]
    error: NotRequired[Optional[str]]


class PresentationInfoResponse(TypedDict):
    """Response structure for get_presentation_info tool."""

    presentationId: str
    title: str
    presentationUrl: str
    slideCount: int
    pageSize: PageSize
    slides: List[SlideInfo]
    userEmail: NotRequired[str]
    error: NotRequired[Optional[str]]


class AddSlideResponse(TypedDict):
    """Response structure for add_slide tool."""

    presentationId: str
    slideId: str
    insertionIndex: NotRequired[Optional[int]]
    layoutId: NotRequired[Optional[str]]
    presentationUrl: str
    success: bool
    message: str
    userEmail: NotRequired[str]
    error: NotRequired[Optional[str]]


class BatchUpdateReply(TypedDict):
    """Structure for a single batch update reply."""

    requestIndex: int
    operationType: str
    objectId: NotRequired[Optional[str]]
    details: str


class UpdateSlideContentResponse(TypedDict):
    """Response structure for update_slide_content tool."""

    presentationId: str
    presentationUrl: str
    requestCount: int
    replyCount: int
    replies: List[BatchUpdateReply]
    success: bool
    message: str
    userEmail: NotRequired[str]
    error: NotRequired[Optional[str]]


class ExportPresentationResponse(TypedDict):
    """Response structure for export_presentation tool."""

    presentationId: str
    exportFormat: str
    exportUrl: str
    editUrl: str
    success: bool
    message: str
    userEmail: NotRequired[str]
    warning: NotRequired[Optional[str]]
    error: NotRequired[Optional[str]]


class FileDownloadInfo(TypedDict):
    """Structure for downloaded file information."""

    localPath: str
    absolutePath: str
    fileSize: int
    fileSizeMB: float
    downloadDuration: float
    timestamp: str


class GetPresentationFileResponse(TypedDict):
    """Response structure for get_presentation_file tool."""

    presentationId: str
    presentationTitle: str
    exportFormat: str
    fileInfo: FileDownloadInfo
    editUrl: str
    success: bool
    message: str
    userEmail: NotRequired[str]
    warning: NotRequired[Optional[str]]
    error: NotRequired[Optional[str]]


class ExportAndDownloadPresentationResponse(TypedDict):
    """Response structure for combined export_and_download_presentation tool."""

    presentationId: str
    presentationTitle: str
    exportFormat: str
    exportUrl: str
    editUrl: str
    downloaded: bool
    fileInfo: NotRequired[Optional[FileDownloadInfo]]  # Only present if downloaded=True
    success: bool
    message: str
    userEmail: NotRequired[str]
    warning: NotRequired[Optional[str]]
    error: NotRequired[Optional[str]]
