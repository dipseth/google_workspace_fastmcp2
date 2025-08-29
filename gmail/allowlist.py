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
from typing import Optional, Union, List

from fastmcp import FastMCP

from config.settings import settings
from .utils import _parse_email_addresses

logger = logging.getLogger(__name__)


async def add_to_gmail_allow_list(
    user_google_email: str,
    email: Union[str, List[str]]
) -> str:
    """
    Adds one or more email addresses to the Gmail allow list.
    Recipients on this list will skip elicitation confirmation when sending emails.

    Args:
        user_google_email: The authenticated user's Google email address (for authorization)
        email: Email address(es) to add to the allow list. Supports:
            - Single email: "user@example.com"
            - List of emails: ["user1@example.com", "user2@example.com"]
            - Comma-separated string: "user1@example.com,user2@example.com"

    Returns:
        str: Confirmation message of the operation
    """
    logger.info(f"[add_to_gmail_allow_list] User: '{user_google_email}' adding email(s): '{email}'")

    # Parse input emails using utility function and normalize to lowercase
    emails_to_add = [e.strip().lower() for e in _parse_email_addresses(email)]
    if not emails_to_add:
        return "❌ No valid email addresses provided"

    # Validate email formats
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    invalid_emails = []
    valid_emails = []
    
    for email_addr in emails_to_add:
        if re.match(email_pattern, email_addr):
            valid_emails.append(email_addr)
        else:
            invalid_emails.append(email_addr)

    if not valid_emails:
        return f"❌ No valid email addresses found. Invalid: {', '.join(invalid_emails)}"

    try:
        # Get current allow list
        current_list = settings.get_gmail_allow_list()

        # Track which emails are already in the list and which are new
        already_in_list = []
        emails_added = []

        for email_to_add in valid_emails:
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

    except Exception as e:
        logger.error(f"Unexpected error in add_to_gmail_allow_list: {e}")
        return f"❌ Unexpected error: {e}"


async def remove_from_gmail_allow_list(
    user_google_email: str,
    email: Union[str, List[str]]
) -> str:
    """
    Removes one or more email addresses from the Gmail allow list.
    After removal, these recipients will require elicitation confirmation when sending emails.

    Args:
        user_google_email: The authenticated user's Google email address (for authorization)
        email: Email address(es) to remove from the allow list. Supports:
            - Single email: "user@example.com"
            - List of emails: ["user1@example.com", "user2@example.com"]
            - Comma-separated string: "user1@example.com,user2@example.com"

    Returns:
        str: Confirmation message of the operation
    """
    logger.info(f"[remove_from_gmail_allow_list] User: '{user_google_email}' removing email(s): '{email}'")

    # Parse input emails using utility function and normalize to lowercase
    emails_to_remove = [e.strip().lower() for e in _parse_email_addresses(email)]
    if not emails_to_remove:
        return "❌ No valid email addresses provided"

    try:
        # Get current allow list
        current_list = settings.get_gmail_allow_list()

        # Track which emails are not in the list and which are removed
        not_in_list = []
        emails_removed = []

        for email_to_remove in emails_to_remove:
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
        logger.error(f"Unexpected error in remove_from_gmail_allow_list: {e}")
        return f"❌ Unexpected error: {e}"


async def view_gmail_allow_list(
    user_google_email: str
) -> str:
    """
    Views the current Gmail allow list configuration.
    Shows which email addresses will skip elicitation confirmation.

    Args:
        user_google_email: The authenticated user's Google email address (for authorization)

    Returns:
        str: Formatted list of allowed email addresses
    """
    logger.info(f"[view_gmail_allow_list] User: '{user_google_email}' viewing allow list")

    try:
        # Get current allow list
        allow_list = settings.get_gmail_allow_list()

        if not allow_list:
            return """📋 Gmail Allow List Status

**Currently Empty**
• No emails are configured to skip elicitation confirmation
• All recipients will require confirmation before sending

**To add emails to the allow list:**
Use `add_to_gmail_allow_list` tool with the email address

**Configuration:**
Set the GMAIL_ALLOW_LIST environment variable with comma-separated emails"""

        # Create masked versions for privacy
        masked_list = []
        for email in allow_list:
            if '@' in email:
                local, domain = email.split('@', 1)
                if len(local) > 3:
                    masked = f"{local[:2]}***@{domain}"
                else:
                    masked = f"***@{domain}"
            else:
                masked = email[:3] + "***" if len(email) > 3 else "***"
            masked_list.append(masked)

        # Build response
        lines = [
            "📋 Gmail Allow List Status",
            "",
            f"**{len(allow_list)} Email(s) Configured**",
            "These recipients will skip elicitation confirmation when sending emails:",
            ""
        ]

        for i, (masked, full) in enumerate(zip(masked_list, allow_list), 1):
            lines.append(f"{i}. {masked}")

        lines.extend([
            "",
            "**Management:**",
            "• Use `add_to_gmail_allow_list` to add new emails",
            "• Use `remove_from_gmail_allow_list` to remove emails",
            "",
            "**Configuration Source:**",
            "GMAIL_ALLOW_LIST environment variable",
            "",
            "**Note:** Full email addresses are hidden for privacy."
        ])

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Unexpected error in view_gmail_allow_list: {e}")
        return f"❌ Unexpected error: {e}"


def setup_allowlist_tools(mcp: FastMCP) -> None:
    """Register Gmail allow list tools with the FastMCP server."""

    @mcp.tool(
        name="add_to_gmail_allow_list",
        description="Add one or more email addresses to the Gmail allow list (recipients on this list skip elicitation confirmation). Supports single emails, lists, or comma-separated strings.",
        tags={"gmail", "allow-list", "security", "management", "trusted", "bulk"},
        annotations={
            "title": "Add to Gmail Allow List",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,  # Adding same email multiple times has same effect
            "openWorldHint": False  # Local configuration only
        }
    )
    async def add_to_gmail_allow_list_tool(
        user_google_email: str,
        email: Union[str, List[str]]
    ) -> str:
        return await add_to_gmail_allow_list(user_google_email, email)

    @mcp.tool(
        name="remove_from_gmail_allow_list",
        description="Remove one or more email addresses from the Gmail allow list. Supports single emails, lists, or comma-separated strings.",
        tags={"gmail", "allow-list", "security", "management", "untrust", "bulk"},
        annotations={
            "title": "Remove from Gmail Allow List",
            "readOnlyHint": False,
            "destructiveHint": False,  # Not truly destructive, just removes trust
            "idempotentHint": True,  # Removing non-existent email has same effect
            "openWorldHint": False  # Local configuration only
        }
    )
    async def remove_from_gmail_allow_list_tool(
        user_google_email: str,
        email: Union[str, List[str]]
    ) -> str:
        return await remove_from_gmail_allow_list(user_google_email, email)

    @mcp.tool(
        name="view_gmail_allow_list",
        description="View the current Gmail allow list configuration",
        tags={"gmail", "allow-list", "security", "view", "list"},
        annotations={
            "title": "View Gmail Allow List",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def view_gmail_allow_list_tool(
        user_google_email: str
    ) -> str:
        return await view_gmail_allow_list(user_google_email)