"""
Gmail service management and authentication for FastMCP2.

This module handles Gmail API service creation with fallback support:
- Middleware-based service injection (primary)
- Direct service creation (fallback)
- Authentication error handling
- Service caching and session management
"""

from fastmcp import FastMCP
from typing_extensions import Any

from auth.service_helpers import get_injected_service, get_service, request_service
from config.enhanced_logging import setup_logger

logger = setup_logger()


async def _get_gmail_service_with_fallback(user_google_email: str) -> Any:
    """
    Get Gmail service with fallback to direct creation if middleware injection fails.

    Args:
        user_google_email: User's Google email address

    Returns:
        Authenticated Gmail service instance

    Raises:
        RuntimeError: If both middleware injection and direct creation fail
    """
    # First, try middleware injection
    service_key = await request_service("gmail")

    try:
        # Try to get the injected service from middleware
        gmail_service = await get_injected_service(service_key)
        logger.info(
            f"Successfully retrieved injected Gmail service for {user_google_email}"
        )
        return gmail_service

    except RuntimeError as e:
        if (
            "not yet fulfilled" in str(e).lower()
            or "service injection" in str(e).lower()
        ):
            # Middleware injection failed, fall back to direct service creation
            logger.warning(
                f"Middleware injection unavailable, falling back to direct service creation for {user_google_email}"
            )

            try:
                # Use the helper function that handles smart defaults
                gmail_service = await get_service("gmail", user_google_email)
                logger.info(
                    f"Successfully created Gmail service directly for {user_google_email}"
                )
                return gmail_service

            except Exception as direct_error:
                error_str = str(direct_error)
                logger.error(f"Direct service creation also failed: {direct_error}")

                # Check for specific credential errors
                if (
                    "credentials do not contain the necessary fields"
                    in error_str.lower()
                ):
                    raise RuntimeError(
                        f"❌ **Invalid or Corrupted Credentials**\n\n"
                        f"Your stored credentials for {user_google_email} are missing required OAuth fields.\n"
                        f"This typically happens when:\n"
                        f"- The OAuth flow was interrupted or didn't complete properly\n"
                        f"- The credentials file became corrupted\n"
                        f"- The authentication token expired and cannot be refreshed\n\n"
                        f"**To fix this, please:**\n"
                        f"1. Run `start_google_auth` with your email: {user_google_email}\n"
                        f"2. Complete the full authentication flow in your browser\n"
                        f"3. Grant all requested Gmail permissions\n"
                        f"4. Wait for the success confirmation\n"
                        f"5. Try your Gmail command again\n\n"
                        f"This will create fresh, valid credentials with all necessary fields."
                    )
                elif "no valid credentials found" in error_str.lower():
                    raise RuntimeError(
                        f"❌ **No Credentials Found**\n\n"
                        f"No authentication credentials found for {user_google_email}.\n\n"
                        f"**To authenticate:**\n"
                        f"1. Run `start_google_auth` with your email: {user_google_email}\n"
                        f"2. Follow the authentication flow in your browser\n"
                        f"3. Grant Gmail permissions when prompted\n"
                        f"4. Return here after seeing the success page"
                    )
                else:
                    raise RuntimeError(
                        f"Failed to get Gmail service through both middleware and direct creation.\n"
                        f"Middleware error: {e}\n"
                        f"Direct creation error: {direct_error}\n\n"
                        f"Please ensure you are authenticated by running `start_google_auth` with your email ({user_google_email}) "
                        f"and service_name='Gmail'."
                    )
        else:
            # Re-raise unexpected RuntimeErrors
            raise


def setup_gmail_tools(mcp: FastMCP) -> None:
    """
    Register Gmail tools with the FastMCP server using middleware-based service injection with fallback.

    This function registers all Gmail tools that use the new middleware-dependent pattern
    for Google service authentication with fallback to direct service creation when
    middleware injection is unavailable.

    Args:
        mcp: FastMCP server instance to register tools with

    Returns:
        None: Tools are registered as side effects
    """
    logger.info("Setting up Gmail tools with middleware-based service injection...")

    # Import all Gmail tool modules and call their setup functions
    try:
        from . import allowlist, compose, filters, labels, messages, ui_tools

        # Call each module's setup function to register their tools
        messages.setup_message_tools(mcp)
        compose.setup_compose_tools(mcp)
        labels.setup_label_tools(mcp)
        filters.setup_filter_tools(mcp)
        allowlist.setup_allowlist_tools(mcp)
        ui_tools.setup_gmail_ui_tools(mcp)

        # Log successful setup
        logger.info("✅ Gmail tools setup completed successfully")
        logger.info("Available Gmail tools:")
        logger.info(
            "  📧 Message tools: search_gmail_messages, get_gmail_message_content, get_gmail_messages_content_batch, get_gmail_thread_content"
        )
        logger.info(
            "  ✍️  Compose tools: send_gmail_message, draft_gmail_message, reply_to_gmail_message, draft_gmail_reply"
        )
        logger.info(
            "  🏷️  Label tools: list_gmail_labels, manage_gmail_label, modify_gmail_message_labels"
        )
        logger.info(
            "  🔍 Filter tools: list_gmail_filters, create_gmail_filter, get_gmail_filter, delete_gmail_filter"
        )
        logger.info(
            "  ✅ Allow list tools: add_to_gmail_allow_list, remove_from_gmail_allow_list, view_gmail_allow_list"
        )
        logger.info(
            "  🖼️  UI tools: search_gmail_ui (MCP Apps pattern)"
        )

    except ImportError as e:
        logger.error(f"❌ Failed to import Gmail tool modules: {e}")
        logger.error("Gmail tools setup aborted")
        raise
