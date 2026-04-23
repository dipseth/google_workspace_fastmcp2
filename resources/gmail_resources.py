"""Gmail-specific resources for FastMCP2 Google Workspace Platform.

This module provides Gmail-related configuration resources, including the
send allow-list used by send_gmail_message elicitation flows.
"""

from datetime import datetime

from fastmcp import Context, FastMCP
from fastmcp.resources import ResourceContent
from typing_extensions import List, NotRequired, Optional, TypedDict

from auth.context import get_user_email_context
from config.enhanced_logging import setup_logger

logger = setup_logger()


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


def setup_gmail_resources(mcp: FastMCP) -> None:
    """Setup Gmail-specific configuration resources."""

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
    async def get_gmail_allow_list_resource(ctx: Context) -> list[ResourceContent]:
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

        user_email = await get_user_email_context()
        if not user_email:
            response = GmailAllowListResponse(
                error="No authenticated user found in current session",
                user_email="",
                allow_list=[],
                count=0,
                description="Authentication required",
                last_updated="unknown",
                timestamp=datetime.now().isoformat(),
            )
            return [ResourceContent(response, mime_type="application/json")]

        try:
            # Get the allow list from settings
            allow_list = settings.get_gmail_allow_list()

            # Check if the environment variable is configured
            raw_value = settings.gmail_allow_list
            is_configured = bool(raw_value and raw_value.strip())

            response = GmailAllowListResponse(
                user_email=user_email,
                allow_list=allow_list,
                count=len(allow_list),
                description="Recipients in this list will skip elicitation confirmation when sending emails",
                last_updated=datetime.now().isoformat(),
                timestamp=datetime.now().isoformat(),
            )
            return [ResourceContent(response, mime_type="application/json")]

        except Exception as e:
            logger.error(f"Error retrieving Gmail allow list: {e}")
            response = GmailAllowListResponse(
                error=f"Failed to retrieve Gmail allow list: {str(e)}",
                user_email=user_email,
                allow_list=[],
                count=0,
                description="Error occurred",
                last_updated="unknown",
                timestamp=datetime.now().isoformat(),
            )
            return [ResourceContent(response, mime_type="application/json")]

    logger.info("✅ Gmail resources registered")
