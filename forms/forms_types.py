"""
Type definitions for Google Forms tool responses.

These TypedDict classes define the structure of data returned by Forms tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

from typing_extensions import List, NotRequired, Optional, TypedDict


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
    error: NotRequired[Optional[str]]  # Optional error message for error responses


class FormCreationResult(TypedDict):
    """Response structure for create_form tool."""

    success: bool
    message: str
    formId: Optional[str]
    title: str
    editUrl: Optional[str]
    responseUrl: Optional[str]
    error: NotRequired[Optional[str]]


class FormUpdateResult(TypedDict):
    """Response structure for form update operations."""

    success: bool
    message: str
    formId: str
    title: Optional[str]
    editUrl: str
    questionsUpdated: NotRequired[int]
    error: NotRequired[Optional[str]]


class FormQuestion(TypedDict):
    """Structure for a form question."""

    itemId: str
    title: str
    type: str
    required: bool
    details: str  # Formatted question details


class FormDetails(TypedDict):
    """Response structure for get_form tool."""

    success: bool
    formId: str
    title: str
    description: Optional[str]
    documentTitle: str
    editUrl: str
    responseUrl: Optional[str]
    questions: List[FormQuestion]
    questionCount: int
    error: NotRequired[Optional[str]]


class FormPublishResult(TypedDict):
    """Response structure for form publishing operations."""

    success: bool
    message: str
    formId: str
    title: str
    editUrl: str
    responseUrl: Optional[str]
    publishState: str  # "accepting responses" or "not accepting responses"
    publicAccess: NotRequired[bool]  # Whether form is publicly accessible
    sharedWith: NotRequired[List[str]]  # List of emails shared with
    sharingResults: NotRequired[List[str]]  # Detailed sharing operation results
    error: NotRequired[Optional[str]]


class FormResponseDetails(TypedDict):
    """Response structure for get_form_response tool."""

    success: bool
    responseId: str
    formId: str
    submittedTime: str
    respondentEmail: Optional[str]
    answers: List[FormResponseAnswer]
    answerCount: int
    error: NotRequired[Optional[str]]
