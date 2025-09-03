"""
Type definitions for Google Drive search functionality.

This module defines structured response types for Drive search operations
to provide consistent, typed responses across the FastMCP2 platform.
"""

from typing import List, Optional, Dict, Any
from typing_extensions import TypedDict


class DriveFileInfo(TypedDict):
    """Information about a single Drive file or folder."""
    id: str
    name: str
    mimeType: str
    size: Optional[str]
    webViewLink: Optional[str]
    iconLink: Optional[str]
    createdTime: Optional[str]
    modifiedTime: Optional[str]
    parents: Optional[List[str]]
    owners: Optional[List[Dict[str, str]]]
    shared: Optional[bool]
    starred: Optional[bool]
    trashed: Optional[bool]
    isFolder: bool


class DriveSearchResponse(TypedDict):
    """Structured response for Drive search operations."""
    query: str
    queryType: str  # "structured" or "free-text"
    processedQuery: str  # The actual query sent to API
    results: List[DriveFileInfo]
    resultCount: int
    totalResults: Optional[int]  # May be unknown if pagination
    nextPageToken: Optional[str]
    userEmail: str
    driveId: Optional[str]
    corpora: Optional[str]
    searchScope: str  # "user", "domain", "drive", "allDrives"
    error: Optional[str]


class DriveSearchError(TypedDict):
    """Error response for Drive search operations."""
    query: str
    error: str
    errorType: str  # "AUTH_ERROR", "API_ERROR", "INVALID_QUERY", etc.
    userEmail: str
    suggestions: Optional[List[str]]