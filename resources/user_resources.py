"""User and authentication resource templates for FastMCP2 Google Workspace Platform.

This module provides FastMCP resources and templates that expose authenticated user
information, eliminating the need for tools to manually require user_google_email parameters.
"""

from datetime import datetime

from fastmcp import Context, FastMCP
from pydantic import Field
from typing_extensions import (
    Annotated,
    Any,
    Dict,
    List,
    NotRequired,
    Optional,
    TypedDict,
)

from auth.context import (
    get_session_context,
    get_session_data,
    get_user_email_context,
    list_sessions,
)
from auth.google_auth import get_valid_credentials
from config.enhanced_logging import setup_logger

logger = setup_logger()


# ============================================================================
# TYPED DICT RESPONSE MODELS FOR USER RESOURCES
# ============================================================================


class AuthenticationStatus(TypedDict):
    """Authentication status information for Google OAuth credentials.

    Contains comprehensive status information about a user's Google authentication
    including credential validity, token expiration, and available scopes.
    """

    authenticated: bool  # Whether the user has valid stored credentials
    credentials_valid: (
        bool  # Whether the stored credentials are currently valid (not expired)
    )
    has_refresh_token: (
        bool  # Whether a refresh token is available for automatic token renewal
    )
    scopes: List[str]  # List of OAuth scopes granted to the application
    expires_at: Optional[
        str
    ]  # ISO 8601 timestamp when the access token expires (None if no expiry)


class UserEmailResponse(TypedDict):
    """Response model for current user email resource (user://current/email).

    Provides the authenticated user's email address along with session information
    and authentication status. Used for session-based authentication workflows.
    """

    email: NotRequired[Optional[str]]  # The authenticated user's email address
    session_id: NotRequired[Optional[str]]  # Current session identifier for tracking
    timestamp: str  # ISO 8601 timestamp when this response was generated
    authenticated: bool  # Whether a user is currently authenticated
    error: NotRequired[Optional[str]]  # Error message if authentication failed
    suggestion: NotRequired[
        Optional[str]
    ]  # Suggested action to resolve authentication issues


class UserProfileResponse(TypedDict):
    """Response model for user profile resources (user://current/profile, user://profile/{email}).

    Comprehensive user profile information including authentication status, credential
    validity, and session details. Supports both current user and email-specific lookups.
    """

    email: NotRequired[Optional[str]]  # The user's email address
    session_id: NotRequired[Optional[str]]  # Current session identifier
    auth_status: NotRequired[
        AuthenticationStatus
    ]  # Detailed authentication status information
    timestamp: str  # ISO 8601 timestamp when this response was generated
    authenticated: NotRequired[bool]  # Whether the user is currently authenticated
    is_current_user: NotRequired[
        bool
    ]  # Whether this profile matches the current session user
    error: NotRequired[Optional[str]]  # Error message if profile retrieval failed
    debug_info: NotRequired[
        Optional[Dict[str, Any]]
    ]  # Additional debugging information for troubleshooting


class SessionInfoResponse(TypedDict):
    """Response model for session information resources (auth://session/current).

    Detailed information about the current authentication session including session
    metadata, user information, and session lifecycle timestamps.
    """

    session_id: NotRequired[Optional[str]]  # Unique session identifier
    user_email: NotRequired[Optional[str]]  # Email address of the authenticated user
    session_active: bool  # Whether the session is currently active and valid
    timestamp: str  # ISO 8601 timestamp when this response was generated
    created_at: NotRequired[
        Optional[str]
    ]  # ISO 8601 timestamp when the session was created
    last_accessed: NotRequired[
        Optional[str]
    ]  # ISO 8601 timestamp when the session was last accessed
    error: NotRequired[
        Optional[str]
    ]  # Error message if session information retrieval failed


class SessionListResponse(TypedDict):
    """Response model for active sessions list resource (auth://sessions/list).

    Administrative view of all active authentication sessions with session details,
    user information, and metadata for multi-user session management.
    """

    active_sessions: List[
        Dict[str, Any]
    ]  # List of all active session objects with metadata
    count: int  # Total number of active sessions
    current_session: NotRequired[
        Optional[str]
    ]  # Session ID of the current session making this request
    timestamp: str  # ISO 8601 timestamp when this response was generated
    error: NotRequired[Optional[str]]  # Error message if session listing failed


class CredentialStatusResponse(TypedDict):
    """Response model for credential status resources (auth://credentials/{email}/status).

    Detailed credential status for a specific user including validity, expiration,
    refresh token availability, and granted scopes for authentication management.
    """

    email: str  # Email address of the user whose credentials are being checked
    authenticated: bool  # Whether valid credentials exist for this user
    credentials_valid: NotRequired[
        bool
    ]  # Whether the credentials are currently valid (not expired)
    expired: NotRequired[bool]  # Whether the access token has expired
    has_refresh_token: NotRequired[
        bool
    ]  # Whether a refresh token is available for renewal
    scopes: NotRequired[List[str]]  # List of OAuth scopes granted to the application
    client_id: NotRequired[
        Optional[str]
    ]  # Truncated OAuth client ID for identification (first 10 chars + "...")
    token_uri: NotRequired[Optional[str]]  # OAuth token endpoint URI
    expires_at: NotRequired[
        Optional[str]
    ]  # ISO 8601 timestamp when the access token expires
    timestamp: str  # ISO 8601 timestamp when this status check was performed
    status: NotRequired[
        str
    ]  # Status summary: "valid", "expired", "no_credentials", or "error"
    error: NotRequired[Optional[str]]  # Error message if credential status check failed
    time_until_expiry: NotRequired[
        Optional[str]
    ]  # Human-readable time remaining until token expires
    refresh_recommended: NotRequired[
        bool
    ]  # Whether token refresh is recommended (expires within 1 hour)


class ServiceScopesResponse(TypedDict):
    """Response model for Google service scopes resource (google://services/scopes/{service}).

    Provides OAuth scope information, API version, and configuration details for
    specific Google services including Drive, Gmail, Calendar, and other Workspace APIs.
    """

    service: str  # Name of the Google service (e.g., "gmail", "drive", "calendar")
    default_scopes: List[str]  # List of OAuth scopes required for this service
    version: str  # API version used for this service (e.g., "v1", "v3")
    description: str  # Human-readable description of the service
    timestamp: str  # ISO 8601 timestamp when this response was generated
    error: NotRequired[
        Optional[str]
    ]  # Error message if service information retrieval failed
    available_services: NotRequired[
        List[str]
    ]  # List of all available services if service lookup failed


class ToolInfo(TypedDict):
    """Information about a single FastMCP tool for directory listings.

    Basic metadata about tools including name, description, and parameters.
    Used in tools directory responses for tool discovery and categorization.
    """

    name: str  # Unique tool name identifier
    description: str  # Human-readable description of the tool's functionality
    parameters: List[str]  # List of parameter names this tool accepts
    example: NotRequired[str]  # Optional usage example showing how to call the tool


class ToolParameterInfo(TypedDict):
    """Common parameter information for FastMCP tools.

    Describes typical parameters used across Google Workspace tools for
    consistency in parameter naming and expected value formats.
    """

    query: NotRequired[str]  # Search query parameter description and format
    page_size: NotRequired[str]  # Pagination size parameter description and limits
    max_results: NotRequired[str]  # Maximum results parameter description and limits
    summary: NotRequired[str]  # Summary/title parameter description and format
    start_time: NotRequired[str]  # Start time parameter description and ISO 8601 format
    end_time: NotRequired[str]  # End time parameter description and ISO 8601 format
    description: NotRequired[str]  # Description parameter format and length limits
    attendees: NotRequired[str]  # Attendees parameter format (email list)
    calendar_id: NotRequired[str]  # Calendar ID parameter format and special values


class DetailedToolInfo(TypedDict):
    """Detailed tool information with comprehensive parameter descriptions.

    Comprehensive tool metadata for detailed tools that use automatic authentication
    via resource templating, eliminating the need for user_google_email parameters.
    """

    name: str  # Unique tool name identifier
    description: str  # Detailed description of the tool's functionality and use cases
    parameters: Dict[
        str, str
    ]  # Dictionary mapping parameter names to their descriptions
    example: str  # Complete usage example with realistic parameter values


class DetailedToolsResponse(TypedDict):
    """Response model for detailed tools collection resource (tools://detailed/list).

    Curated list of detailed tools that use automatic resource templating for seamless
    authentication through OAuth session context without requiring email parameters.
    """

    detailed_tools: List[
        DetailedToolInfo
    ]  # List of detailed tools with comprehensive information
    count: int  # Total number of detailed tools available
    benefit: str  # Explanation of the benefits of using detailed tools
    timestamp: str  # ISO 8601 timestamp when this response was generated


class ToolCategoryInfo(TypedDict):
    """Information about a category of FastMCP tools.

    Groups related tools by service or functionality (e.g., Gmail tools, Drive tools)
    with metadata about authentication requirements and tool counts.
    """

    description: str  # Description of this tool category's purpose and scope
    tool_count: int  # Number of tools in this category
    requires_email: NotRequired[
        bool
    ]  # Whether tools in this category require user_google_email parameter
    tools: NotRequired[List[ToolInfo]]  # Optional list of tools in this category


class ToolsDirectoryResponse(TypedDict):
    """Response model for complete tools directory resource (tools://list/all).

    Comprehensive catalog of all available FastMCP tools organized by category with
    detailed capability descriptions, authentication requirements, and migration status.
    """

    total_tools: int  # Total number of tools available across all categories
    total_categories: int  # Number of tool categories with at least one tool
    detailed_tools_count: int  # Number of detailed tools (no email parameter required)
    tools_by_category: Dict[
        str, Any
    ]  # Dictionary mapping category names to ToolCategoryInfo objects
    timestamp: str  # ISO 8601 timestamp when this directory was generated
    resource_templating_available: (
        bool  # Whether resource templating is implemented and available
    )
    migration_status: str  # Status message about migration to detailed tools
    error: NotRequired[
        Optional[str]
    ]  # Error message if tool directory generation failed


class WorkflowExample(TypedDict):
    """Example workflow information for tool usage guides.

    Sample workflows showing how to combine different Google Workspace tools
    for common use cases and productivity scenarios.
    """

    drive: str  # Example Drive operation or workflow step
    gmail: str  # Example Gmail operation or workflow step
    calendar: str  # Example Calendar operation or workflow step
    status: str  # Status or result of this workflow example


class ToolUsageGuideResponse(TypedDict):
    """Response model for tools usage guide resource (tools://usage/guide).

    Complete usage guide with examples, workflows, and best practices for both
    detailed and legacy tools including authentication flows and migration guidance.
    """

    quick_start: Dict[str, str]  # Quick start guide with basic usage examples
    detailed_tools_workflow: Dict[str, Any]  # Workflow examples for detailed tools
    legacy_tools_workflow: Dict[
        str, Any
    ]  # Workflow examples for legacy tools requiring email
    migration_guide: Dict[str, str]  # Guide for migrating from legacy to detailed tools
    error_handling: Dict[str, str]  # Common error scenarios and resolution steps
    timestamp: str  # ISO 8601 timestamp when this guide was generated


class WorkspaceContentItem(TypedDict):
    """Individual Google Workspace content item for search results.

    Represents a single file or document from Google Drive with metadata
    relevant for email composition and content referencing workflows.
    """

    id: str  # Unique Google Drive file ID
    name: str  # File or document name/title
    type: str  # Content type (document, spreadsheet, presentation, etc.)
    modified_time: str  # ISO 8601 timestamp when the item was last modified
    web_view_link: str  # URL for viewing the item in a web browser
    mime_type: NotRequired[
        str
    ]  # MIME type of the file (e.g., 'application/vnd.google-apps.document')


class WorkspaceContentResponse(TypedDict):
    """Response model for workspace content resources (workspace://content/search/{query}).

    Search results from Google Workspace content with categorization and metadata
    for dynamic email composition and content linking workflows.
    """

    user_email: str  # Email address of the authenticated user who performed the search
    content_items: List[
        WorkspaceContentItem
    ]  # List of matching workspace content items
    count: int  # Total number of items found in the search
    timestamp: str  # ISO 8601 timestamp when this search was performed
    source: str  # Source of the content (e.g., "google_drive")
    error: NotRequired[Optional[str]]  # Error message if content search failed


class ContentSuggestion(TypedDict):
    """Content suggestion item for Gmail composition assistance.

    Individual suggestion for email content including documents to reference,
    templates to use, or actions to take for detailed email composition.
    """

    type: str  # Type of suggestion (e.g., "document_reference", "template", "action")
    title: str  # Human-readable title for this suggestion
    description: str  # Detailed description of what this suggestion provides
    action: str  # Recommended action or next step for using this suggestion
    priority: int  # Priority ranking (lower numbers = higher priority)


class GmailContentSuggestionsResponse(TypedDict):
    """Response model for Gmail content suggestions resource (gmail://content/suggestions).

    Dynamic content suggestions for Gmail composition based on user's recent activity,
    workspace content, and email patterns to enhance productivity and relevance.
    """

    user_email: str  # Email address of the authenticated user
    suggestions: List[
        ContentSuggestion
    ]  # List of content suggestions for email composition
    count: int  # Total number of suggestions generated
    categories: List[
        str
    ]  # Categories of suggestions included (e.g., ["documents", "templates"])
    timestamp: str  # ISO 8601 timestamp when these suggestions were generated
    error: NotRequired[Optional[str]]  # Error message if suggestion generation failed


class GmailAllowListResponse(TypedDict):
    """Response model for Gmail allow list resource (gmail://allow-list).

    Configuration of the Gmail allow list for send_gmail_message tool showing which
    recipients will skip elicitation confirmation for trusted communication.
    """

    user_email: str  # Email address of the authenticated user
    allow_list: List[str]  # List of email addresses that skip elicitation confirmation
    count: int  # Number of email addresses in the allow list
    description: str  # Description of how the allow list works
    last_updated: str  # ISO 8601 timestamp when the allow list was last updated
    timestamp: str  # ISO 8601 timestamp when this response was generated
    error: NotRequired[Optional[str]]  # Error message if allow list retrieval failed


def setup_user_resources(mcp: FastMCP) -> None:
    """Setup all user and authentication resources."""

    @mcp.resource(
        uri="user://current/email",
        name="Current User Email",
        description="Get the currently authenticated user's email address for session-based authentication",
        mime_type="application/json",
        tags={"authentication", "user", "email", "session", "template"},
        enabled=True,
        meta={
            "template_accessible": True,
            "property_paths": ["email", "session_id", "timestamp"],
            "response_model": "UserEmailResponse",
            "detailed": True,
        },
    )
    async def get_current_user_email(ctx: Context) -> UserEmailResponse:
        """Get the currently authenticated user's email address for session-based authentication.

        This resource provides the foundational authentication information needed by other
        resources and tools. It returns the email address of the user who has completed
        OAuth authentication via the start_google_auth tool.

        Args:
            ctx: FastMCP Context object providing access to server state and logging

        Returns:
            UserEmailResponse: Contains the authenticated user's email, session ID, and
            authentication status. If no user is authenticated, returns error information
            with suggestions for resolving authentication issues.

        Example Response (Success):
            {
                "email": "user@example.com",
                "session_id": "session_12345",
                "timestamp": "2024-01-15T10:30:00Z",
                "authenticated": true
            }

        Example Response (No Authentication):
            {
                "error": "No authenticated user found in current session",
                "suggestion": "Use start_google_auth tool to authenticate first",
                "authenticated": false,
                "timestamp": "2024-01-15T10:30:00Z"
            }
        """
        user_email = get_user_email_context()
        if not user_email:
            return UserEmailResponse(
                error="No authenticated user found in current session",
                suggestion="Use start_google_auth tool to authenticate first",
                authenticated=False,
                timestamp=datetime.now().isoformat(),
            )

        return UserEmailResponse(
            email=user_email,
            session_id=get_session_context(),
            timestamp=datetime.now().isoformat(),
            authenticated=True,
        )

    @mcp.resource(
        uri="user://current/profile",
        name="Current User Profile",
        description="Comprehensive profile information including authentication status, credential validity, and available Google services for the current session user",
        mime_type="application/json",
        tags={"authentication", "user", "profile", "credentials", "session", "google"},
        meta={
            "response_model": "UserProfileResponse",
            "detailed": True,
            "includes_debug": True,
        },
    )
    async def get_current_user_profile(ctx: Context) -> UserProfileResponse:
        """Get comprehensive profile information for the current session user.

        Provides detailed authentication status, credential validity, and available Google
        services for the currently authenticated user. Includes debugging information to
        help troubleshoot OAuth and session management issues.

        Args:
            ctx: FastMCP Context object providing access to server state and logging

        Returns:
            UserProfileResponse: Comprehensive profile information including:
            - User email and session ID
            - Detailed authentication status with token validity
            - OAuth scopes and credential expiration information
            - Debug information for troubleshooting authentication issues

        Example Response (Authenticated):
            {
                "email": "user@example.com",
                "session_id": "session_12345",
                "auth_status": {
                    "authenticated": true,
                    "credentials_valid": true,
                    "has_refresh_token": true,
                    "scopes": ["https://www.googleapis.com/auth/gmail.modify"],
                    "expires_at": "2024-01-15T12:30:00Z"
                },
                "timestamp": "2024-01-15T10:30:00Z"
            }

        Example Response (Not Authenticated):
            {
                "error": "No authenticated user found in current session",
                "authenticated": false,
                "timestamp": "2024-01-15T10:30:00Z",
                "debug_info": {
                    "user_email_context": null,
                    "session_context": null,
                    "issue": "OAuth proxy authentication may not be setting session context"
                }
            }
        """
        user_email = get_user_email_context()
        session_id = get_session_context()

        # DIAGNOSTIC: Log context state for debugging OAuth vs start_google_auth disconnect
        logger.info("🔍 DEBUG: get_current_user_profile called")
        logger.info(f"   user_email_context: {user_email}")
        logger.info(f"   session_context: {session_id}")

        if not user_email:
            return UserProfileResponse(
                error="No authenticated user found in current session",
                authenticated=False,
                timestamp=datetime.now().isoformat(),
                debug_info={
                    "user_email_context": user_email,
                    "session_context": session_id,
                    "issue": "OAuth proxy authentication may not be setting session context",
                },
            )

        # Check credential validity
        credentials = get_valid_credentials(user_email)
        auth_status = AuthenticationStatus(
            authenticated=credentials is not None,
            credentials_valid=credentials is not None and not credentials.expired,
            has_refresh_token=credentials is not None
            and credentials.refresh_token is not None,
            scopes=credentials.scopes if credentials else [],
            expires_at=(
                credentials.expiry.isoformat()
                if credentials and credentials.expiry
                else None
            ),
        )

        return UserProfileResponse(
            email=user_email,
            session_id=get_session_context(),
            auth_status=auth_status,
            timestamp=datetime.now().isoformat(),
        )

    @mcp.resource(
        uri="user://profile/{email}",
        name="User Profile by Email",
        description="Get detailed profile information for a specific user email including authentication status, credential validity, and comparison with current session user",
        mime_type="application/json",
        tags={"user", "profile", "authentication", "credentials", "email", "lookup"},
        meta={
            "response_model": "UserProfileResponse",
            "detailed": True,
            "supports_lookup": True,
        },
    )
    async def get_user_profile_by_email(
        email: Annotated[
            str,
            Field(
                description="Email address of the user to get profile information for. Must be a valid email format with @ symbol and domain.",
                pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
                examples=["user@example.com", "admin@company.org"],
                min_length=5,
                max_length=254,
            ),
        ],
        ctx: Context,
    ) -> UserProfileResponse:
        """Get detailed profile information for a specific user by email address.

        Retrieves comprehensive authentication and credential status for any user email,
        including comparison with the current session user. Useful for administrative
        tasks and multi-user authentication management.

        Args:
            email: Valid email address of the user to look up. Must match standard
                email format (e.g., "user@domain.com"). The email is validated against
                stored credentials and authentication status is checked.
            ctx: FastMCP Context object providing access to server state and logging

        Returns:
            UserProfileResponse: Detailed profile information including:
            - Authentication status and credential validity for the specified user
            - Comparison with current session user (is_current_user flag)
            - OAuth scopes and token expiration information
            - Profile lookup timestamp

        Raises:
            ValidationError: If email format is invalid or doesn't match regex pattern

        Example Usage:
            await get_user_profile_by_email("admin@company.com", ctx)

        Example Response:
            {
                "email": "admin@company.com",
                "auth_status": {
                    "authenticated": true,
                    "credentials_valid": false,
                    "has_refresh_token": true,
                    "scopes": ["https://www.googleapis.com/auth/gmail.modify"],
                    "expires_at": "2024-01-15T09:30:00Z"
                },
                "is_current_user": false,
                "timestamp": "2024-01-15T10:30:00Z"
            }
        """
        # Check credential validity for the specified user
        credentials = get_valid_credentials(email)
        auth_status = AuthenticationStatus(
            authenticated=credentials is not None,
            credentials_valid=credentials is not None and not credentials.expired,
            has_refresh_token=credentials is not None
            and credentials.refresh_token is not None,
            scopes=credentials.scopes if credentials else [],
            expires_at=(
                credentials.expiry.isoformat()
                if credentials and credentials.expiry
                else None
            ),
        )

        return UserProfileResponse(
            email=email,
            auth_status=auth_status,
            is_current_user=email == get_user_email_context(),
            timestamp=datetime.now().isoformat(),
        )

    @mcp.resource(
        uri="auth://session/current",
        name="Current Authentication Session",
        description="Detailed information about the current authentication session including token status, expiration times, and granted scopes",
        mime_type="application/json",
        tags={"authentication", "session", "oauth", "token", "security"},
        meta={
            "response_model": "SessionInfoResponse",
            "detailed": True,
            "includes_metadata": True,
        },
    )
    async def get_current_session_info(ctx: Context) -> SessionInfoResponse:
        """Get detailed information about the current authentication session.

        Provides comprehensive session metadata including session lifecycle information,
        user association, and activity timestamps. Essential for session management,
        debugging authentication issues, and monitoring user activity.

        Args:
            ctx: FastMCP Context object providing access to server state and logging

        Returns:
            SessionInfoResponse: Complete session information including:
            - Session ID and associated user email
            - Session activity status and lifecycle timestamps
            - Creation time and last accessed timestamps when available
            - Error details if no active session is found

        Authentication:
            Requires an active session context. Returns error information if no
            session is found or if session context is not properly initialized.

        Example Response (Active Session):
            {
                "session_id": "session_abc123",
                "user_email": "user@company.com",
                "session_active": true,
                "created_at": "2024-01-15T09:00:00Z",
                "last_accessed": "2024-01-15T10:25:00Z",
                "timestamp": "2024-01-15T10:30:00Z"
            }

        Example Response (No Session):
            {
                "error": "No active session found",
                "session_active": false,
                "timestamp": "2024-01-15T10:30:00Z"
            }

        Usage:
            This resource is useful for session debugging, user activity monitoring,
            and understanding the current authentication state for troubleshooting
            OAuth and session management issues.
        """
        session_id = get_session_context()
        user_email = get_user_email_context()

        if not session_id:
            return SessionInfoResponse(
                error="No active session found",
                session_active=False,
                timestamp=datetime.now().isoformat(),
            )

        # Get session metadata if available
        session_data = SessionInfoResponse(
            session_id=session_id,
            user_email=user_email,
            session_active=True,
            timestamp=datetime.now().isoformat(),
        )

        # Add any additional session data stored
        try:
            created_at = get_session_data(session_id, "created_at")
            last_accessed = get_session_data(session_id, "last_accessed")

            if created_at:
                session_data["created_at"] = created_at.isoformat()
            if last_accessed:
                session_data["last_accessed"] = last_accessed.isoformat()
        except Exception as e:
            logger.debug(f"Could not retrieve session metadata: {e}")

        return session_data

    @mcp.resource(
        uri="auth://sessions/list",
        name="Active Authentication Sessions",
        description="Administrative view of all active authentication sessions with session details, user information, and expiration status for multi-user session management",
        mime_type="application/json",
        tags={
            "authentication",
            "sessions",
            "admin",
            "multi-user",
            "management",
            "security",
        },
        meta={
            "response_model": "SessionListResponse",
            "detailed": True,
            "administrative": True,
        },
    )
    async def list_active_sessions(ctx: Context) -> SessionListResponse:
        """Get administrative view of all active authentication sessions.

        Provides comprehensive session management information for multi-user environments,
        including session details, user associations, and activity status. Essential for
        administrative monitoring, session debugging, and multi-user OAuth management.

        Args:
            ctx: FastMCP Context object providing access to server state and logging

        Returns:
            SessionListResponse: Complete session listing including:
            - List of all active sessions with metadata and user information
            - Total count of active sessions
            - Current session identifier for context
            - Error details if session listing fails

        Administrative Use:
            This resource provides administrative capabilities for monitoring and managing
            multiple user sessions. Useful for understanding authentication state across
            all users and debugging session-related issues.

        Example Response (Multiple Sessions):
            {
                "active_sessions": [
                    {
                        "session_id": "session_abc123",
                        "user_email": "user1@company.com",
                        "created_at": "2024-01-15T09:00:00Z",
                        "last_accessed": "2024-01-15T10:25:00Z"
                    },
                    {
                        "session_id": "session_def456",
                        "user_email": "user2@company.com",
                        "created_at": "2024-01-15T09:15:00Z",
                        "last_accessed": "2024-01-15T10:20:00Z"
                    }
                ],
                "count": 2,
                "current_session": "session_abc123",
                "timestamp": "2024-01-15T10:30:00Z"
            }

        Example Response (Error):
            {
                "error": "Failed to list sessions: Permission denied",
                "active_sessions": [],
                "count": 0,
                "timestamp": "2024-01-15T10:30:00Z"
            }
        """
        try:
            active_sessions = list_sessions()

            return SessionListResponse(
                active_sessions=active_sessions,
                count=len(active_sessions),
                current_session=get_session_context(),
                timestamp=datetime.now().isoformat(),
            )
        except Exception as e:
            logger.error(f"Error listing sessions: {e}")
            return SessionListResponse(
                error=f"Failed to list sessions: {str(e)}",
                active_sessions=[],
                count=0,
                timestamp=datetime.now().isoformat(),
            )

    @mcp.resource(
        uri="auth://credentials/{email}/status",
        name="User Credential Status",
        description="Detailed credential status for a specific user including validity, expiration, refresh token availability, and granted scopes for authentication management",
        mime_type="application/json",
        tags={
            "authentication",
            "credentials",
            "status",
            "oauth",
            "tokens",
            "security",
            "user",
        },
        meta={
            "response_model": "CredentialStatusResponse",
            "detailed": True,
            "supports_lookup": True,
        },
    )
    async def get_credential_status(
        email: Annotated[
            str,
            Field(
                description="Email address to check credential status for. Must be a valid email format for OAuth credential lookup.",
                pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
                examples=["user@gmail.com", "admin@company.com", "test@domain.org"],
                min_length=5,
                max_length=254,
                title="User Email Address",
            ),
        ],
        ctx: Context,
    ) -> CredentialStatusResponse:
        """Get detailed credential status for a specific user's OAuth tokens.

        Performs comprehensive credential validation including token expiry checking,
        refresh token availability, OAuth scope verification, and provides recommendations
        for token refresh when expiration is imminent.

        Args:
            email: Valid email address for credential status lookup. The email must match
                an existing OAuth credential store entry. Invalid emails or emails without
                stored credentials will return appropriate error responses.
            ctx: FastMCP Context object providing access to server state and logging

        Returns:
            CredentialStatusResponse: Comprehensive credential status including:
            - Authentication validity and token expiration status
            - Available OAuth scopes and refresh token presence
            - Time until expiry and refresh recommendations
            - Truncated client ID for identification purposes
            - Error details if credential checking fails

        Example Usage:
            await get_credential_status("user@company.com", ctx)

        Example Response (Valid Credentials):
            {
                "email": "user@company.com",
                "authenticated": true,
                "credentials_valid": true,
                "expired": false,
                "has_refresh_token": true,
                "scopes": ["https://www.googleapis.com/auth/gmail.modify"],
                "client_id": "1234567890...",
                "expires_at": "2024-01-15T12:30:00Z",
                "status": "valid",
                "time_until_expiry": "1:45:30",
                "refresh_recommended": false,
                "timestamp": "2024-01-15T10:45:00Z"
            }

        Example Response (No Credentials):
            {
                "email": "unknown@example.com",
                "status": "no_credentials",
                "authenticated": false,
                "timestamp": "2024-01-15T10:45:00Z",
                "error": "No stored credentials found for this user"
            }
        """
        try:
            credentials = get_valid_credentials(email)

            if not credentials:
                return CredentialStatusResponse(
                    email=email,
                    status="no_credentials",
                    authenticated=False,
                    timestamp=datetime.now().isoformat(),
                    error="No stored credentials found for this user",
                )

            status_info = CredentialStatusResponse(
                email=email,
                authenticated=True,
                credentials_valid=not credentials.expired,
                expired=credentials.expired,
                has_refresh_token=credentials.refresh_token is not None,
                scopes=credentials.scopes or [],
                client_id=(
                    credentials.client_id[:10] + "..."
                    if credentials.client_id
                    else None
                ),
                token_uri=credentials.token_uri,
                expires_at=(
                    credentials.expiry.isoformat() if credentials.expiry else None
                ),
                timestamp=datetime.now().isoformat(),
            )

            if credentials.expired:
                status_info["status"] = "expired"
                status_info["time_until_expiry"] = "Already expired"
                status_info["refresh_recommended"] = True
            else:
                status_info["status"] = "valid"
                if credentials.expiry:
                    time_remaining = credentials.expiry - datetime.now()
                    status_info["time_until_expiry"] = str(time_remaining)
                    status_info["refresh_recommended"] = (
                        time_remaining.total_seconds() < 3600
                    )  # < 1 hour

            return status_info

        except Exception as e:
            logger.error(f"Error checking credentials for {email}: {e}")
            return CredentialStatusResponse(
                email=email,
                status="error",
                authenticated=False,
                error=str(e),
                timestamp=datetime.now().isoformat(),
            )

    @mcp.resource(
        uri="template://user_email",
        name="User Email Template",
        description="Simple template resource that returns just the user email string - the most basic resource for tools that need only the email address",
        mime_type="text/plain",
        tags={"template", "user", "email", "simple", "authentication", "string"},
    )
    async def get_template_user_email(ctx: Context) -> str:
        """Get the authenticated user's email as a simple string for template usage.

        This is the most basic resource for tools that need only the email address without
        additional metadata. Returns a plain string rather than a JSON object, making it
        ideal for template substitution and simple email parameter injection.

        Args:
            ctx: FastMCP Context object providing access to server state and logging

        Returns:
            str: The authenticated user's email address as a plain string, or an error
            message string if no user is authenticated. This resource always returns
            a string (never raises exceptions) to maintain template compatibility.

        Authentication:
            Requires active user authentication via start_google_auth tool. Returns
            helpful error message if no authenticated user is found.

        Example Response (Authenticated):
            "user@company.com"

        Example Response (Not Authenticated):
            "❌ Authentication error: No authenticated user found in current session. Use start_google_auth tool first."

        Usage:
            This resource is primarily used by other resources and tools that need to
            inject the current user's email into API calls or template strings without
            dealing with complex JSON response parsing.
        """
        user_email = get_user_email_context()
        if not user_email:
            # Return a helpful error message as string instead of raising exception
            # This follows FastMCP2 resource patterns - resources should return data gracefully
            return "❌ Authentication error: No authenticated user found in current session. Use start_google_auth tool first."

        return user_email

    @mcp.resource(
        uri="google://services/scopes/{service}",
        name="Google Service Scopes",
        description="Get the required OAuth scopes, API version, and configuration details for a specific Google service including Drive, Gmail, Calendar, and other Workspace APIs",
        mime_type="application/json",
        tags={
            "google",
            "services",
            "scopes",
            "oauth",
            "api",
            "configuration",
            "workspace",
        },
        meta={
            "response_model": "ServiceScopesResponse",
            "detailed": True,
            "supports_lookup": True,
        },
    )
    async def get_service_scopes(
        service: Annotated[
            str,
            Field(
                description="Google service name to get OAuth scope and API configuration information for. Supported services include gmail, drive, calendar, docs, sheets, slides, forms, chat, photos.",
                examples=[
                    "gmail",
                    "drive",
                    "calendar",
                    "docs",
                    "sheets",
                    "slides",
                    "forms",
                    "chat",
                    "photos",
                ],
                min_length=3,
                max_length=20,
                pattern=r"^[a-z][a-z0-9_]*$",
                title="Google Service Name",
            ),
        ],
        ctx: Context,
    ) -> ServiceScopesResponse:
        """Get OAuth scopes, API version, and configuration details for a Google service.

        Retrieves comprehensive configuration information for Google Workspace and related
        services, including required OAuth scopes, API versions, and service descriptions.
        Essential for understanding authentication requirements and API capabilities.

        Args:
            service: Name of the Google service to lookup. Must be lowercase and match
                one of the supported services: gmail, drive, calendar, docs, sheets,
                slides, forms, chat, photos. Invalid service names return available
                services list with error details.
            ctx: FastMCP Context object providing access to server state and logging

        Returns:
            ServiceScopesResponse: Complete service configuration including:
            - Required OAuth scopes for API access
            - API version and endpoint information
            - Service description and capabilities
            - Error details and available services if lookup fails

        Example Usage:
            await get_service_scopes("gmail", ctx)
            await get_service_scopes("drive", ctx)

        Example Response (Gmail Service):
            {
                "service": "gmail",
                "default_scopes": [
                    "https://www.googleapis.com/auth/gmail.modify",
                    "https://www.googleapis.com/auth/gmail.send"
                ],
                "version": "v1",
                "description": "Gmail API for email management",
                "timestamp": "2024-01-15T10:30:00Z"
            }

        Example Response (Unknown Service):
            {
                "service": "unknown_service",
                "error": "Unknown Google service: unknown_service",
                "available_services": ["gmail", "drive", "calendar", "docs"],
                "default_scopes": [],
                "version": "unknown",
                "description": "Service not found",
                "timestamp": "2024-01-15T10:30:00Z"
            }
        """
        # Import here to avoid circular imports
        from auth.service_helpers import SERVICE_DEFAULTS

        service_info = SERVICE_DEFAULTS.get(service.lower())
        if not service_info:
            return ServiceScopesResponse(
                service=service,
                error=f"Unknown Google service: {service}",
                available_services=list(SERVICE_DEFAULTS.keys()),
                default_scopes=[],
                version="unknown",
                description="Service not found",
                timestamp=datetime.now().isoformat(),
            )

        return ServiceScopesResponse(
            service=service,
            default_scopes=service_info.get("default_scopes", []),
            version=service_info.get("version", "v1"),
            description=service_info.get(
                "description", f"Google {service.title()} API"
            ),
            timestamp=datetime.now().isoformat(),
        )

    @mcp.resource(
        uri="tools://list/all",
        name="Complete Tools Directory",
        description="Comprehensive catalog of all available tools organized by category including Drive, Gmail, Calendar, Chat, Forms, Docs, Sheets, and authentication tools with detailed capability descriptions",
        mime_type="application/json",
        tags={
            "tools",
            "directory",
            "catalog",
            "discovery",
            "google",
            "workspace",
            "detailed",
            "legacy",
        },
        meta={
            "response_model": "ToolsDirectoryResponse",
            "detailed": True,
            "comprehensive": True,
            "dynamic": True,
        },
    )
    async def get_all_tools_list(ctx: Context) -> ToolsDirectoryResponse:
        """Get comprehensive catalog of all available FastMCP tools organized by category.

        Dynamically discovers and categorizes all registered FastMCP tools including Drive,
        Gmail, Calendar, Chat, Forms, Docs, Sheets, authentication tools, and utility tools.
        Provides detailed capability descriptions, authentication requirements, and migration
        status for both detailed and legacy tools.

        This resource performs real-time tool discovery by introspecting the FastMCP server
        instance, analyzing tool schemas, and categorizing tools by service type and
        authentication requirements.

        Args:
            ctx: FastMCP Context object providing access to server state, tool registry,
                and logging capabilities for dynamic tool discovery

        Returns:
            ToolsDirectoryResponse: Complete tools catalog including:
            - Total tool count across all categories and services
            - Tools organized by category (Gmail, Drive, Calendar, etc.)
            - Detailed vs legacy tool counts and migration status
            - Tool metadata including parameters and descriptions
            - Resource templating availability status
            - Error details if tool discovery fails

        Tool Categories:
            - Detailed Tools: Use automatic authentication (no email params)
            - Service Tools: Gmail, Drive, Calendar, Docs, Sheets, Slides, Forms, Chat, Photos
            - System Tools: Authentication, Qdrant search, module wrappers
            - Utility Tools: Other helper and system tools

        Example Response:
            {
                "total_tools": 65,
                "total_categories": 12,
                "detailed_tools_count": 8,
                "tools_by_category": {
                    "gmail_tools": {
                        "description": "Gmail email management tools",
                        "tool_count": 11,
                        "requires_email": true,
                        "tools": [...]
                    },
                    "detailed_tools": {
                        "description": "New tools that use resource templating",
                        "tool_count": 8,
                        "requires_email": false,
                        "tools": [...]
                    }
                },
                "resource_templating_available": true,
                "migration_status": "✅ Resource templating implemented - detailed tools available!",
                "timestamp": "2024-01-15T10:30:00Z"
            }
        """
        try:
            # Access the FastMCP server instance through context
            fastmcp_server = ctx.fastmcp

            # Log FastMCP server structure for debugging
            await ctx.debug(f"FastMCP server type: {type(fastmcp_server)}")
            await ctx.debug(f"FastMCP server attributes: {dir(fastmcp_server)}")

            # Try to access tools via the documented fastmcp.tools attribute
            tools_list = None
            registered_tools = {}

            if hasattr(fastmcp_server, "tools"):
                tools_list = fastmcp_server.tools
                await ctx.info(f"✅ Found fastmcp.tools attribute: {type(tools_list)}")
                await ctx.debug(
                    f"Tools list length: {len(tools_list) if hasattr(tools_list, '__len__') else 'unknown'}"
                )

                # Convert tools list to dictionary if it's a list
                if isinstance(tools_list, list):
                    for tool in tools_list:
                        if hasattr(tool, "name"):
                            registered_tools[tool.name] = tool
                        else:
                            await ctx.warning(
                                f"Tool in list has no name attribute: {tool}"
                            )
                elif hasattr(tools_list, "items"):
                    # It's already a dict-like object
                    registered_tools = dict(tools_list.items())
                else:
                    await ctx.warning(
                        f"Tools attribute is not list or dict: {type(tools_list)}"
                    )

            # Fallback to tool manager if tools attribute doesn't work
            if not registered_tools and hasattr(fastmcp_server, "_tool_manager"):
                await ctx.info("Falling back to _tool_manager")
                if hasattr(fastmcp_server._tool_manager, "_tools"):
                    registered_tools = fastmcp_server._tool_manager._tools
                    await ctx.info(
                        f"✅ Found {len(registered_tools)} tools via _tool_manager"
                    )
                elif hasattr(fastmcp_server._tool_manager, "tools"):
                    registered_tools = fastmcp_server._tool_manager.tools
                    await ctx.info(
                        f"✅ Found {len(registered_tools)} tools via _tool_manager.tools"
                    )

            if not registered_tools:
                await ctx.warning(
                    "Could not access tools from FastMCP server - trying alternative methods"
                )
                # Try other common attributes
                for attr_name in ["_tools", "tool_registry", "registry"]:
                    if hasattr(fastmcp_server, attr_name):
                        attr_value = getattr(fastmcp_server, attr_name)
                        await ctx.debug(
                            f"Found attribute {attr_name}: {type(attr_value)}"
                        )
                        if hasattr(attr_value, "items"):
                            registered_tools = dict(attr_value.items())
                            break
                        elif hasattr(attr_value, "__len__") and len(attr_value) > 0:
                            # Convert list to dict
                            for item in attr_value:
                                if hasattr(item, "name"):
                                    registered_tools[item.name] = item
                            break

            await ctx.info(f"🔍 Final tool count: {len(registered_tools)}")

            # Categorize tools dynamically based on their names and tags
            categories = {
                "detailed_tools": {
                    "description": "New tools that use resource templating (no email params needed)",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": False,
                },
                "drive_tools": {
                    "description": "Google Drive file management tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True,
                },
                "gmail_tools": {
                    "description": "Gmail email management tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True,
                },
                "docs_tools": {
                    "description": "Google Docs document management tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True,
                },
                "forms_tools": {
                    "description": "Google Forms creation and management tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True,
                },
                "calendar_tools": {
                    "description": "Google Calendar event management tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True,
                },
                "slides_tools": {
                    "description": "Google Slides presentation tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True,
                },
                "sheets_tools": {
                    "description": "Google Sheets spreadsheet tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True,
                },
                "chat_tools": {
                    "description": "Google Chat messaging tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True,
                },
                "photos_tools": {
                    "description": "Google Photos tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True,
                },
                "auth_tools": {
                    "description": "Authentication and system tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": "mixed",
                },
                "qdrant_tools": {
                    "description": "Qdrant search and analytics tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": False,
                },
                "module_tools": {
                    "description": "Module wrapper and introspection tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": False,
                },
                "other_tools": {
                    "description": "Other utility and system tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": "mixed",
                },
            }

            # Categorize each tool
            for tool_name, tool_instance in registered_tools.items():
                await ctx.debug(f"Processing tool: {tool_name}")

                # Get tool metadata - be more defensive about accessing attributes
                tool_info = {
                    "name": tool_name,
                    "description": "No description available",
                    "tags": [],
                    "parameters": [],
                    "detailed": False,
                }

                # Safely get description
                if hasattr(tool_instance, "description") and tool_instance.description:
                    tool_info["description"] = tool_instance.description
                elif hasattr(tool_instance, "doc") and tool_instance.doc:
                    tool_info["description"] = tool_instance.doc

                # Safely get tags
                if hasattr(tool_instance, "tags") and tool_instance.tags:
                    if isinstance(tool_instance.tags, (set, list, tuple)):
                        tool_info["tags"] = list(tool_instance.tags)
                    else:
                        tool_info["tags"] = [str(tool_instance.tags)]

                # Extract parameters from tool schema if available
                parameter_names = []
                if hasattr(tool_instance, "schema") and tool_instance.schema:
                    schema = tool_instance.schema
                    if isinstance(schema, dict) and "parameters" in schema:
                        params = schema["parameters"]
                        if isinstance(params, dict) and "properties" in params:
                            parameter_names = list(params["properties"].keys())
                            tool_info["parameters"] = parameter_names
                elif hasattr(tool_instance, "parameters"):
                    # Some tools might have a direct parameters attribute
                    if hasattr(tool_instance.parameters, "keys"):
                        parameter_names = list(tool_instance.parameters.keys())
                        tool_info["parameters"] = parameter_names

                # Check if it's an detailed tool (no user_google_email parameter)
                is_detailed = "user_google_email" not in parameter_names
                tool_info["detailed"] = is_detailed

                # Categorize based on name patterns and tags
                categorized = False

                # Detailed tools (no email parameter)
                if is_detailed and any(
                    keyword in tool_name for keyword in ["my_", "_my", "get_my_"]
                ):
                    categories["detailed_tools"]["tools"].append(tool_info)
                    categories["detailed_tools"]["tool_count"] += 1
                    categorized = True

                # Service-specific tools
                elif any(keyword in tool_name for keyword in ["drive", "file"]):
                    categories["drive_tools"]["tools"].append(tool_info)
                    categories["drive_tools"]["tool_count"] += 1
                    categorized = True
                elif any(
                    keyword in tool_name
                    for keyword in ["gmail", "email", "message", "draft"]
                ):
                    categories["gmail_tools"]["tools"].append(tool_info)
                    categories["gmail_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ["doc", "document"]):
                    categories["docs_tools"]["tools"].append(tool_info)
                    categories["docs_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ["form", "response"]):
                    categories["forms_tools"]["tools"].append(tool_info)
                    categories["forms_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ["calendar", "event"]):
                    categories["calendar_tools"]["tools"].append(tool_info)
                    categories["calendar_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ["slide", "presentation"]):
                    categories["slides_tools"]["tools"].append(tool_info)
                    categories["slides_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ["sheet", "spreadsheet"]):
                    categories["sheets_tools"]["tools"].append(tool_info)
                    categories["sheets_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ["chat", "space", "card"]):
                    categories["chat_tools"]["tools"].append(tool_info)
                    categories["chat_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ["photo", "album"]):
                    categories["photos_tools"]["tools"].append(tool_info)
                    categories["photos_tools"]["tool_count"] += 1
                    categorized = True
                elif any(
                    keyword in tool_name
                    for keyword in ["auth", "credential", "session", "oauth"]
                ):
                    categories["auth_tools"]["tools"].append(tool_info)
                    categories["auth_tools"]["tool_count"] += 1
                    categorized = True
                elif any(
                    keyword in tool_name
                    for keyword in ["qdrant", "search", "vector", "embed"]
                ):
                    categories["qdrant_tools"]["tools"].append(tool_info)
                    categories["qdrant_tools"]["tool_count"] += 1
                    categorized = True
                elif any(
                    keyword in tool_name for keyword in ["module", "wrap", "component"]
                ):
                    categories["module_tools"]["tools"].append(tool_info)
                    categories["module_tools"]["tool_count"] += 1
                    categorized = True

                # Uncategorized tools go to "other"
                if not categorized:
                    categories["other_tools"]["tools"].append(tool_info)
                    categories["other_tools"]["tool_count"] += 1

            # Calculate totals
            total_tools = len(registered_tools)
            detailed_tools_count = categories["detailed_tools"]["tool_count"]

            # Log discovery results
            await ctx.info(
                f"🔍 Dynamic tool discovery: Found {total_tools} tools, {detailed_tools_count} detailed"
            )

            return ToolsDirectoryResponse(
                total_tools=total_tools,
                total_categories=len(
                    [cat for cat in categories.values() if cat["tool_count"] > 0]
                ),
                detailed_tools_count=detailed_tools_count,
                tools_by_category=categories,
                timestamp=datetime.now().isoformat(),
                resource_templating_available=True,
                migration_status="✅ Resource templating implemented - detailed tools available!",
            )

        except Exception as e:
            await ctx.error(f"Error during dynamic tool discovery: {e}")
            # Fallback to minimal response
            return ToolsDirectoryResponse(
                total_tools=0,
                total_categories=0,
                detailed_tools_count=0,
                tools_by_category={},
                timestamp=datetime.now().isoformat(),
                resource_templating_available=False,
                migration_status="❌ Error during tool discovery",
                error=str(e),
            )

        except Exception as e:
            logger.error(f"Error generating tools list: {e}")
            return ToolsDirectoryResponse(
                total_tools=0,
                total_categories=0,
                detailed_tools_count=0,
                tools_by_category={},
                timestamp=datetime.now().isoformat(),
                resource_templating_available=False,
                migration_status="❌ Error generating tools list",
                error=f"Failed to generate tools list: {str(e)}",
            )

    @mcp.resource(
        uri="tools://detailed/list",
        name="Detailed Tools Collection",
        description="Curated list of detailed tools that use automatic resource templating - no user_google_email parameters required, seamless authentication through OAuth session context",
        mime_type="application/json",
        tags={
            "tools",
            "detailed",
            "templating",
            "oauth",
            "seamless",
            "modern",
            "no-email",
        },
        meta={
            "response_model": "DetailedToolsResponse",
            "detailed": True,
            "oauth_enabled": True,
        },
    )
    async def get_detailed_tools_only(ctx: Context) -> DetailedToolsResponse:
        """Get curated list of detailed tools that use automatic resource templating.

        Dynamically discovers and returns only detailed tools that utilize automatic
        authentication through OAuth session context, eliminating the need for
        user_google_email parameters. These tools provide seamless authentication
        and improved developer experience.

        Detailed tools are identified by the absence of user_google_email parameters
        in their schema, indicating they use the newer resource templating approach
        for authentication injection.

        Args:
            ctx: FastMCP Context object providing access to server state and tool
                registry for dynamic detailed tool discovery

        Returns:
            DetailedToolsResponse: Curated detailed tools collection including:
            - List of detailed tools with comprehensive parameter descriptions
            - Complete usage examples with realistic parameter values
            - Benefits explanation of detailed authentication approach
            - Total count of available detailed tools
            - Error details if detailed tool discovery fails

        Benefits of Detailed Tools:
            - No user_google_email parameter required
            - Automatic OAuth session context injection
            - Cleaner API with fewer required parameters
            - Seamless authentication through middleware
            - Modern resource templating architecture

        Example Response:
            {
                "detailed_tools": [
                    {
                        "name": "get_my_recent_files",
                        "description": "Get recent files for the authenticated user",
                        "parameters": {
                            "days": "Number of days back to search (default: 7)",
                            "file_type": "Type of files to return (optional)"
                        },
                        "example": "get_my_recent_files(days=14, file_type=\"document\")"
                    }
                ],
                "count": 8,
                "benefit": "No user_google_email parameter required - uses OAuth session automatically",
                "timestamp": "2024-01-15T10:30:00Z"
            }
        """
        try:
            # Access the FastMCP server instance through context
            fastmcp_server = ctx.fastmcp

            # Try to access tools via the documented fastmcp.tools attribute first
            tools_list = None
            registered_tools = {}

            if hasattr(fastmcp_server, "tools"):
                tools_list = fastmcp_server.tools
                await ctx.debug(f"Found fastmcp.tools: {type(tools_list)}")

                # Convert tools list to dictionary if it's a list
                if isinstance(tools_list, list):
                    for tool in tools_list:
                        if hasattr(tool, "name"):
                            registered_tools[tool.name] = tool
                elif hasattr(tools_list, "items"):
                    # It's already a dict-like object
                    registered_tools = dict(tools_list.items())

            # Fallback to tool manager if tools attribute doesn't work
            if not registered_tools and hasattr(fastmcp_server, "_tool_manager"):
                if hasattr(fastmcp_server._tool_manager, "_tools"):
                    registered_tools = fastmcp_server._tool_manager._tools
                elif hasattr(fastmcp_server._tool_manager, "tools"):
                    registered_tools = fastmcp_server._tool_manager.tools

            if not registered_tools:
                await ctx.warning("Could not access tools from FastMCP server")
                return DetailedToolsResponse(
                    detailed_tools=[],
                    count=0,
                    benefit="No user_google_email parameter required - uses OAuth session automatically",
                    timestamp=datetime.now().isoformat(),
                )

            # Find detailed tools (tools without user_google_email parameter)
            detailed_tools = []

            for tool_name, tool_instance in registered_tools.items():
                # Get tool parameters safely
                parameters = {}
                parameter_names = []

                # Try to get parameters from schema
                if hasattr(tool_instance, "schema") and tool_instance.schema:
                    schema = tool_instance.schema
                    if isinstance(schema, dict) and "parameters" in schema:
                        params = schema["parameters"]
                        if isinstance(params, dict) and "properties" in params:
                            parameter_names = list(params["properties"].keys())
                            # Build parameter descriptions
                            for param_name, param_info in params["properties"].items():
                                if isinstance(param_info, dict):
                                    parameters[param_name] = param_info.get(
                                        "description", f"{param_name} parameter"
                                    )
                                else:
                                    parameters[param_name] = f"{param_name} parameter"

                # Check if it's an detailed tool (no user_google_email parameter)
                is_detailed = "user_google_email" not in parameter_names

                # Include tools that are clearly "detailed" based on naming or characteristics
                if is_detailed and (
                    any(keyword in tool_name for keyword in ["my_", "_my", "get_my_"])
                    or ("template" in getattr(tool_instance, "tags", set()))
                    or ("detailed" in getattr(tool_instance, "tags", set()))
                ):
                    # Safely get description
                    description = "Detailed tool with automatic authentication"
                    if (
                        hasattr(tool_instance, "description")
                        and tool_instance.description
                    ):
                        description = tool_instance.description

                    # Create a more meaningful example
                    example = f"{tool_name}()"
                    if parameters:
                        # Create a basic example with parameter names
                        param_examples = []
                        for param_name in list(parameters.keys())[:3]:  # First 3 params
                            if "query" in param_name:
                                param_examples.append(f'{param_name}="search term"')
                            elif "summary" in param_name or "title" in param_name:
                                param_examples.append(f'{param_name}="Example Title"')
                            elif "time" in param_name:
                                param_examples.append(
                                    f'{param_name}="2025-02-01T10:00:00Z"'
                                )
                            else:
                                param_examples.append(f'{param_name}="value"')

                        if param_examples:
                            example = f"{tool_name}({', '.join(param_examples)})"

                    detailed_tool = DetailedToolInfo(
                        name=tool_name,
                        description=description,
                        parameters=parameters,
                        example=example,
                    )
                    detailed_tools.append(detailed_tool)

            # Log discovery results
            await ctx.info(
                f"🔍 Detailed tool discovery: Found {len(detailed_tools)} detailed tools out of {len(registered_tools)} total"
            )

            return DetailedToolsResponse(
                detailed_tools=detailed_tools,
                count=len(detailed_tools),
                benefit="No user_google_email parameter required - uses OAuth session automatically",
                timestamp=datetime.now().isoformat(),
            )

        except Exception as e:
            await ctx.error(f"Error during detailed tool discovery: {e}")
            # Fallback to empty response
            return DetailedToolsResponse(
                detailed_tools=[],
                count=0,
                benefit="No user_google_email parameter required - uses OAuth session automatically",
                timestamp=datetime.now().isoformat(),
            )

    @mcp.resource(
        uri="workspace://content/search/{query}",
        name="Search Google Workspace Content",
        description="Search across Google Workspace content (Drive, Docs, Sheets) for specific topics or keywords to dynamically populate email content with relevant links and references",
        mime_type="application/json",
        tags={
            "workspace",
            "search",
            "drive",
            "docs",
            "sheets",
            "content",
            "gmail",
            "dynamic",
        },
    )
    async def search_workspace_content(
        query: Annotated[
            str,
            Field(
                description="Search query to find relevant workspace content by filename or document content. Supports both keyword searches and phrase matching for comprehensive content discovery.",
                examples=[
                    "quarterly budget",
                    "project alpha",
                    "meeting notes",
                    "2024 planning",
                ],
                min_length=1,
                max_length=200,
                title="Search Query",
            ),
        ],
        ctx: Context,
    ) -> dict:
        """Search Google Workspace content for email composition and content discovery.

        Performs comprehensive content-based search across Google Drive files including
        both filename matching and full-text content search within documents. Results
        are automatically categorized by file type and formatted for email composition
        workflows with suggested references, links, and attachments.

        This resource is essential for dynamic email composition, allowing users to
        discover relevant documents, spreadsheets, and presentations to reference or
        attach in their communications.

        Args:
            query: Search terms to find relevant workspace content. The query is used
                for both filename matching and full-text content search within documents.
                Supports single keywords, multiple terms, or phrase searches. Common
                examples include project names, topic keywords, or document titles.
            ctx: FastMCP Context object providing access to server state and logging

        Returns:
            dict: Comprehensive search results including:
            - Categorized results by file type (documents, spreadsheets, presentations, PDFs, images)
            - Email composition suggestions with ready-to-use references and links
            - Relevance scoring based on filename matches
            - Total result count and search metadata
            - Error details if search fails or user is not authenticated

        Authentication:
            Requires active user authentication. Returns error if no authenticated
            user is found in the current session context.

        Example Usage:
            await search_workspace_content("quarterly budget report", ctx)
            await search_workspace_content("project alpha", ctx)

        Example Response:
            {
                "search_query": "quarterly budget",
                "user_email": "user@company.com",
                "total_results": 8,
                "results_by_type": {
                    "documents": [
                        {
                            "id": "1ABC123",
                            "name": "Q4 Budget Report",
                            "web_view_link": "https://docs.google.com/document/d/1ABC123",
                            "modified_time": "2024-01-10T15:30:00Z",
                            "relevance_score": "high"
                        }
                    ],
                    "spreadsheets": [...],
                    "presentations": [...],
                    "pdfs": [...],
                    "images": [],
                    "other": []
                },
                "suggested_email_content": {
                    "references": ["📄 Q4 Budget Report", "📊 Budget Analysis"],
                    "links": ["https://docs.google.com/document/d/1ABC123"],
                    "attachment_suggestions": [...]
                },
                "timestamp": "2024-01-15T10:30:00Z"
            }

        Example Response (Not Authenticated):
            {
                "error": "No authenticated user found in current session",
                "query": "quarterly budget"
            }
        """
        user_email = get_user_email_context()
        if not user_email:
            return {
                "error": "No authenticated user found in current session",
                "query": query,
            }

        try:
            # Import and call tools directly (not using forward())
            from drive.drive_tools import search_drive_files

            # Search Drive files using direct tool call
            search_results = await search_drive_files(
                user_google_email=user_email,
                query=f"name contains '{query}' or fullText contains '{query}'",
                page_size=15,
            )

            # Process and categorize results
            categorized_results = {
                "documents": [],
                "spreadsheets": [],
                "presentations": [],
                "pdfs": [],
                "images": [],
                "other": [],
            }

            for file_info in search_results.get("files", []):
                mime_type = file_info.get("mimeType", "")
                file_entry = {
                    "id": file_info.get("id"),
                    "name": file_info.get("name"),
                    "web_view_link": file_info.get("webViewLink"),
                    "modified_time": file_info.get("modifiedTime"),
                    "relevance_score": (
                        "high"
                        if query.lower() in file_info.get("name", "").lower()
                        else "medium"
                    ),
                }

                if "document" in mime_type:
                    categorized_results["documents"].append(file_entry)
                elif "spreadsheet" in mime_type:
                    categorized_results["spreadsheets"].append(file_entry)
                elif "presentation" in mime_type:
                    categorized_results["presentations"].append(file_entry)
                elif "pdf" in mime_type:
                    categorized_results["pdfs"].append(file_entry)
                elif "image" in mime_type:
                    categorized_results["images"].append(file_entry)
                else:
                    categorized_results["other"].append(file_entry)

            return {
                "search_query": query,
                "user_email": user_email,
                "total_results": len(search_results.get("files", [])),
                "results_by_type": categorized_results,
                "suggested_email_content": {
                    "references": [
                        f"📄 {file['name']}"
                        for file in search_results.get("files", [])[:5]
                    ],
                    "links": [
                        file.get("webViewLink")
                        for file in search_results.get("files", [])[:3]
                    ],
                    "attachment_suggestions": [
                        file
                        for file in search_results.get("files", [])
                        if file.get("mimeType", "").startswith("application/")
                    ][:3],
                },
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error searching workspace content: {e}")
            return {
                "error": f"Failed to search workspace content: {str(e)}",
                "search_query": query,
                "timestamp": datetime.now().isoformat(),
            }

    @mcp.resource(
        uri="gmail://allow-list",
        name="Gmail Allow List",
        description="Get the configured Gmail allow list for send_gmail_message tool - recipients on this list skip elicitation confirmation",
        mime_type="application/json",
        tags={
            "gmail",
            "allow-list",
            "security",
            "elicitation",
            "trusted",
            "recipients",
        },
        meta={
            "response_model": "GmailAllowListResponse",
            "detailed": True,
            "security_related": True,
        },
    )
    async def get_gmail_allow_list_resource(ctx: Context) -> GmailAllowListResponse:
        """Get the configured Gmail allow list for send_gmail_message tool.

        Retrieves the list of trusted email recipients that skip elicitation confirmation
        when using the send_gmail_message tool. This security feature allows pre-approved
        recipients to receive emails without additional confirmation prompts.

        The allow list is configured via the GMAIL_ALLOW_LIST environment variable and
        provides a security mechanism to prevent accidental email sending while allowing
        trusted communication channels.

        Args:
            ctx: FastMCP Context object providing access to server state and logging

        Returns:
            GmailAllowListResponse: Gmail allow list configuration including:
            - List of email addresses that skip elicitation confirmation
            - Count of addresses in the allow list
            - Description of how the allow list works
            - Configuration status and last updated timestamp
            - Error details if allow list retrieval fails

        Authentication:
            Requires active user authentication. Returns error if no authenticated
            user is found in the current session context.

        Security:
            This resource provides visibility into email security settings without
            allowing modification. The actual allow list configuration is managed
            through environment variables and system configuration.

        Example Response (Configured):
            {
                "user_email": "user@company.com",
                "allow_list": ["trusted@company.com", "admin@company.com"],
                "count": 2,
                "description": "Recipients in this list will skip elicitation confirmation when sending emails",
                "last_updated": "2024-01-15T10:30:00Z",
                "timestamp": "2024-01-15T10:30:00Z"
            }

        Example Response (Not Configured):
            {
                "user_email": "user@company.com",
                "allow_list": [],
                "count": 0,
                "description": "Recipients in this list will skip elicitation confirmation when sending emails",
                "last_updated": "2024-01-15T10:30:00Z",
                "timestamp": "2024-01-15T10:30:00Z"
            }
        """
        from config.settings import settings

        user_email = get_user_email_context()
        if not user_email:
            return GmailAllowListResponse(
                error="No authenticated user found in current session",
                user_email="",
                allow_list=[],
                count=0,
                description="Authentication required",
                last_updated="unknown",
                timestamp=datetime.now().isoformat(),
            )

        try:
            # Get the allow list from settings
            allow_list = settings.get_gmail_allow_list()

            # Check if the environment variable is configured
            raw_value = settings.gmail_allow_list
            is_configured = bool(raw_value and raw_value.strip())

            return GmailAllowListResponse(
                user_email=user_email,
                allow_list=allow_list,
                count=len(allow_list),
                description="Recipients in this list will skip elicitation confirmation when sending emails",
                last_updated=datetime.now().isoformat(),
                timestamp=datetime.now().isoformat(),
            )

        except Exception as e:
            logger.error(f"Error retrieving Gmail allow list: {e}")
            return GmailAllowListResponse(
                error=f"Failed to retrieve Gmail allow list: {str(e)}",
                user_email=user_email,
                allow_list=[],
                count=0,
                description="Error occurred",
                last_updated="unknown",
                timestamp=datetime.now().isoformat(),
            )

    logger.info("✅ User and authentication resources registered")


def get_current_user_email_simple() -> str:
    """Utility function to get current user email for tools.

    This is a synchronous helper that tools can use to get the current
    user's email without dealing with async resource access.

    Returns:
        The current user's email address

    Raises:
        ValueError: If no authenticated user is found
    """
    user_email = get_user_email_context()
    if not user_email:
        raise ValueError(
            "No authenticated user found in current session. "
            "Please ensure the user is authenticated with start_google_auth tool first."
        )
    return user_email
