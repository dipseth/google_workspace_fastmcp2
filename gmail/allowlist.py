"""
Gmail allow list management tools for FastMCP2.

This module provides tools for managing the Gmail allow list:
- Adding emails to the allow list (recipients skip elicitation)
- Removing emails from the allow list
- Viewing the current allow list configuration

The allow list is stored in the GMAIL_ALLOW_LIST environment variable
and provides a security feature for Gmail sending operations.
"""

import logging
import re
from typing_extensions import Optional, Union, List

from fastmcp import FastMCP

# Import our custom type for consistent parameter definition
from tools.common_types import UserGoogleEmail

from config.settings import settings
from .utils import _parse_email_addresses
from .gmail_types import GmailAllowListResponse, AllowedEmailInfo

from config.enhanced_logging import setup_logger
logger = setup_logger()


async def manage_gmail_allow_list(
    action: str,
    email: Optional[Union[str, List[str]]] = None,
    user_google_email: UserGoogleEmail = None
) -> Union[str, GmailAllowListResponse]:
    """
    Manage the Gmail allow list: add, remove, or view email addresses.
    Recipients on this list will skip elicitation confirmation when sending emails.

    Args:
        action: Action to perform - 'add', 'remove', or 'view'
        email: Email address(es) for add/remove operations. Supports:
            - Single email: "user@example.com"
            - List of emails: ["user1@example.com", "user2@example.com"]
            - Comma-separated string: "user1@example.com,user2@example.com"
            (Required for add/remove, ignored for view)
        user_google_email: The authenticated user's Google email address (for authorization)

    Returns:
        Union[str, GmailAllowListResponse]: Confirmation message for add/remove, structured response for view
    """
    action = action.lower().strip()
    logger.info(f"[manage_gmail_allow_list] User: '{user_google_email}' action: '{action}' email(s): '{email}'")

    if action not in ['add', 'remove', 'view']:
        return "❌ Invalid action. Must be 'add', 'remove', or 'view'"

    # Handle view action
    if action == 'view':
        try:
            # Get current allow list
            allow_list = settings.get_gmail_allow_list()

            # Convert to structured format
            allowed_emails: List[AllowedEmailInfo] = []
            
            for email_addr in allow_list:
                # Create masked version for privacy
                if '@' in email_addr:
                    local, domain = email_addr.split('@', 1)
                    if len(local) > 3:
                        masked = f"{local[:2]}***@{domain}"
                    else:
                        masked = f"***@{domain}"
                else:
                    masked = email_addr[:3] + "***" if len(email_addr) > 3 else "***"
                
                email_info: AllowedEmailInfo = {
                    "email": email_addr,
                    "masked_email": masked
                }
                allowed_emails.append(email_info)

            logger.info(f"Successfully retrieved {len(allowed_emails)} allowed emails for {user_google_email}")

            return GmailAllowListResponse(
                allowed_emails=allowed_emails,
                count=len(allowed_emails),
                userEmail=user_google_email,
                is_configured=len(allowed_emails) > 0,
                source="GMAIL_ALLOW_LIST environment variable",
                error=None
            )

        except Exception as e:
            logger.error(f"Unexpected error in manage_gmail_allow_list (view): {e}")
            # Return structured error response
            return GmailAllowListResponse(
                allowed_emails=[],
                count=0,
                userEmail=user_google_email,
                is_configured=False,
                source="GMAIL_ALLOW_LIST environment variable",
                error=f"Unexpected error: {e}"
            )

    # For add/remove actions, email parameter is required
    if email is None:
        return f"❌ Email parameter is required for '{action}' action"

    # Parse input emails using utility function and normalize to lowercase
    emails_to_process = [e.strip().lower() for e in _parse_email_addresses(email)]
    if not emails_to_process:
        return "❌ No valid email addresses provided"

    # Validate email formats for add/remove operations
    if action in ['add', 'remove']:
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        invalid_emails = []
        valid_emails = []
        
        for email_addr in emails_to_process:
            if re.match(email_pattern, email_addr):
                valid_emails.append(email_addr)
            else:
                invalid_emails.append(email_addr)

        if not valid_emails and action == 'add':
            return f"❌ No valid email addresses found. Invalid: {', '.join(invalid_emails)}"

        emails_to_process = valid_emails

    try:
        # Get current allow list
        current_list = settings.get_gmail_allow_list()

        if action == 'add':
            # Track which emails are already in the list and which are new
            already_in_list = []
            emails_added = []

            for email_to_add in emails_to_process:
                if email_to_add in current_list:
                    already_in_list.append(email_to_add)
                else:
                    emails_added.append(email_to_add)

            # Add the new emails
            updated_list = current_list + emails_added

            if emails_added:
                # Update the environment variable (in memory)
                new_value = ",".join(updated_list)
                settings.gmail_allow_list = new_value
                import os
                os.environ["GMAIL_ALLOW_LIST"] = new_value

            # Build response
            response_lines = []

            if emails_added:
                # Mask emails for privacy
                masked_added = [f"{e[:3]}...@{e.split('@')[1]}" if '@' in e else e for e in emails_added]
                response_lines.append(f"✅ Successfully added {len(emails_added)} email(s) to Gmail allow list!")
                response_lines.append(f"Added: {', '.join(masked_added)}")

            if already_in_list:
                masked_already = [f"{e[:3]}...@{e.split('@')[1]}" if '@' in e else e for e in already_in_list]
                response_lines.append(f"ℹ️ {len(already_in_list)} email(s) were already in the allow list: {', '.join(masked_already)}")

            if invalid_emails:
                response_lines.append(f"❌ {len(invalid_emails)} invalid email(s) skipped: {', '.join(invalid_emails)}")

            response_lines.extend([
                "",
                "**Current Status:**",
                f"• Allow list now contains {len(updated_list)} email(s)",
                "• Added emails will skip elicitation confirmation when sending emails"
            ])

            if emails_added:
                response_lines.extend([
                    "",
                    "**⚠️ IMPORTANT - Make this change permanent:**",
                    "To persist this change across server restarts, update your .env file:",
                    "```",
                    f"GMAIL_ALLOW_LIST={','.join(updated_list)}",
                    "```",
                    "",
                    "**Note:** The change is active for the current session but will be lost on restart unless updated in .env file."
                ])

            return "\n".join(response_lines)

        elif action == 'remove':
            # Track which emails are not in the list and which are removed
            not_in_list = []
            emails_removed = []

            for email_to_remove in emails_to_process:
                if email_to_remove not in current_list:
                    not_in_list.append(email_to_remove)
                else:
                    emails_removed.append(email_to_remove)

            # Remove the emails
            updated_list = [e for e in current_list if e not in emails_removed]

            if emails_removed:
                # Update the environment variable (in memory)
                new_value = ",".join(updated_list) if updated_list else ""
                settings.gmail_allow_list = new_value
                import os
                os.environ["GMAIL_ALLOW_LIST"] = new_value

            # Build response
            response_lines = []

            if emails_removed:
                # Mask emails for privacy
                masked_removed = [f"{e[:3]}...@{e.split('@')[1]}" if '@' in e else e for e in emails_removed]
                response_lines.append(f"✅ Successfully removed {len(emails_removed)} email(s) from Gmail allow list!")
                response_lines.append(f"Removed: {', '.join(masked_removed)}")

            if not_in_list:
                masked_not_in_list = [f"{e[:3]}...@{e.split('@')[1]}" if '@' in e else e for e in not_in_list]
                response_lines.append(f"ℹ️ {len(not_in_list)} email(s) were not in the allow list: {', '.join(masked_not_in_list)}")

            response_lines.extend([
                "",
                "**Current Status:**",
                f"• Allow list now contains {len(updated_list)} email(s)",
                "• Removed emails will now require elicitation confirmation when sending emails"
            ])

            if emails_removed:
                if updated_list:
                    env_instruction = f"GMAIL_ALLOW_LIST={','.join(updated_list)}"
                else:
                    env_instruction = "# GMAIL_ALLOW_LIST= (comment out or remove the line)"

                response_lines.extend([
                    "",
                    "**⚠️ IMPORTANT - Make this change permanent:**",
                    "To persist this change across server restarts, update your .env file:",
                    "```",
                    env_instruction,
                    "```",
                    "",
                    "**Note:** The change is active for the current session but will be lost on restart unless updated in .env file."
                ])

            return "\n".join(response_lines)

    except Exception as e:
        logger.error(f"Unexpected error in manage_gmail_allow_list ({action}): {e}")
        return f"❌ Unexpected error: {e}"


def setup_allowlist_tools(mcp: FastMCP) -> None:
    """Register Gmail allow list tool with the FastMCP server."""

    @mcp.tool(
        name="manage_gmail_allow_list",
        description="Manage Gmail allow list: add, remove, or view email addresses. Recipients on this list skip elicitation confirmation. Supports single emails, lists, or comma-separated strings.",
        tags={"gmail", "allow-list", "security", "management", "trusted", "bulk", "unified"},
        annotations={
            "title": "Manage Gmail Allow List",
            "readOnlyHint": False,  # Can modify list with add/remove actions
            "destructiveHint": False,  # Not truly destructive, manages trust settings
            "idempotentHint": True,  # Same operations have same effect
            "openWorldHint": False  # Local configuration only
        }
    )
    async def manage_gmail_allow_list_tool(
        action: str,
        email: Optional[Union[str, List[str]]] = None,
        user_google_email: UserGoogleEmail = None
    ) -> Union[str, GmailAllowListResponse]:
        return await manage_gmail_allow_list(action, email, user_google_email)