"""
Type definitions for Google Forms tool responses.

These TypedDict classes define the structure of data returned by Forms tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

from typing_extensions import TypedDict, List, Optional, Dict, Any


class FormResponseAnswer(TypedDict):
    """Structure for a single answer in a form response."""
    questionId: str
    questionTitle: str
    answer: str  # Formatted answer text


class FormResponseInfo(TypedDict):
    """Structure for a single form response entry."""
    responseId: str
    submittedTime: str
    respondentEmail: Optional[str]  # May be Anonymous
    answers: List[FormResponseAnswer]


class FormResponsesListResponse(TypedDict):
    """Response structure for list_form_responses tool."""
    responses: List[FormResponseInfo]
    count: int
    formId: str
    formTitle: str
    userEmail: str
    pageToken: Optional[str]  # For pagination
    nextPageToken: Optional[str]  # Next page token if more results available
    error: Optional[str]  # Optional error message for error responses