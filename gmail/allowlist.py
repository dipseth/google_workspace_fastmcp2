"""
Workspace trust list (Gmail allow list) management tools for FastMCP2.

This module provides tools for managing the **workspace trust list** that
is currently consumed by Gmail tools and will be shared with Google Chat:

- Adding entries to the trust list (trusted recipients/targets skip elicitation)
- Removing entries from the trust list
- Viewing the current trust list configuration

The trust list is stored in the GMAIL_ALLOW_LIST environment variable and
is interpreted as:

- Explicit email addresses used by Gmail and Chat DM flows
- People contact group specs (e.g. "group:Team", "groupId:contactGroups/123")
  which are expanded via the People API for dynamic trust
- (Planned) Chat space specs (e.g. "space:spaces/AAAA...") for trusted spaces

Even though the environment variable is named GMAIL_ALLOW_LIST for
backward compatibility, it should be thought of as a shared workspace
trust list used by Gmail send/forward tools today and, over time,
by Chat tools as well.
"""

import logging
import re
import asyncio
from typing_extensions import Optional, Union, List

from fastmcp import FastMCP

# Import our custom type for consistent parameter definition
from tools.common_types import UserGoogleEmail
from .gmail_types import GmailAllowListResponse, AllowedEmailInfo, GmailRecipientsOptional, AllowedGroupInfo

from config.settings import settings
from .utils import _parse_email_addresses
from auth.context import get_auth_middleware
from googleapiclient.discovery import build

from config.enhanced_logging import setup_logger
logger = setup_logger()


def split_allow_list_tokens(allow_list: List[str]) -> (List[str], List[str]):
    """
    Split raw GMAIL_ALLOW_LIST entries into explicit email entries and group specs.

    Group specs are strings that start with:
      - "group:"   → group by display name (People contact group name)
      - "groupId:" → group by contact group resourceName (e.g., "contactGroups/123")

    Returns:
        Tuple[List[str], List[str]]: (email_entries, group_specs)
    """
    email_entries: List[str] = []
    group_specs: List[str] = []

    for raw in allow_list:
        if not raw:
            continue
        value = raw.strip()
        if not value:
            continue

        lower = value.lower()
        if lower.startswith("group:") or lower.startswith("groupid:"):
            group_specs.append(value)
        else:
            email_entries.append(value)

    return email_entries, group_specs


async def _get_people_service_for_labels(user_email: UserGoogleEmail):
    """
    Build a Google People API service instance for contact label operations.

    Returns:
        A People API service client or None if credentials are unavailable.
    """
    if not user_email:
        logger.warning("No user email provided for People API (contact labels)")
        return None

    try:
        auth_middleware = get_auth_middleware()
    except Exception as exc:
        logger.warning(f"AuthMiddleware lookup failed for People API (contact labels): {exc}")
        return None

    if not auth_middleware:
        logger.warning("No AuthMiddleware available for People API (contact labels)")
        return None

    try:
        credentials = auth_middleware.load_credentials(user_email)
    except Exception as exc:
        logger.warning(f"Error loading credentials for People API (contact labels) for user {user_email}: {exc}")
        return None

    if not credentials:
        logger.warning(f"No credentials found for People API (contact labels) for user {user_email}")
        return None

    try:
        return await asyncio.to_thread(build, "people", "v1", credentials=credentials)
    except Exception as exc:
        logger.error(f"Failed to build People API service for user {user_email}: {exc}")
        return None


async def _ensure_contact_group(people_service, label_name: str) -> Optional[str]:
    """
    Ensure a contact group with the given label name exists and return its resourceName.
    """
    if not people_service or not label_name:
        return None

    label_name = label_name.strip()
    if not label_name:
        return None

    try:
        def _list_groups():
            return people_service.contactGroups().list(pageSize=200).execute()

        result = await asyncio.to_thread(_list_groups)
        groups = result.get("contactGroups", []) or []
        for group in groups:
            group_name = group.get("name")
            resource_name = group.get("resourceName")
            if group_name == label_name and resource_name:
                return resource_name

        # Create group if not found
        def _create_group():
            return people_service.contactGroups().create(
                body={"contactGroup": {"name": label_name}}
            ).execute()

        created = await asyncio.to_thread(_create_group)
        resource_name = created.get("resourceName")
        if not resource_name:
            logger.error(f"People API returned contactGroup without resourceName for label '{label_name}'")
        return resource_name
    except Exception as exc:
        logger.error(f"Error ensuring contact group '{label_name}': {exc}")
        return None


async def _search_contacts_for_email(people_service, email: str) -> List[str]:
    """
    Search contacts by email address and return matching resourceNames.
    """
    resource_names: List[str] = []
    if not people_service or not email:
        return resource_names

    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        return resource_names

    try:
        def _search():
            return people_service.people().searchContacts(
                query=normalized_email,
                readMask="emailAddresses"
            ).execute()

        result = await asyncio.to_thread(_search)
        containers = (
            result.get("results")
            or result.get("connections")
            or result.get("people")
            or []
        )

        for item in containers:
            person = item.get("person", item)
            if not isinstance(person, dict):
                continue
            resource_name = person.get("resourceName")
            if not resource_name:
                continue
            for addr in person.get("emailAddresses", []):
                value = (addr.get("value") or "").strip().lower()
                if value == normalized_email:
                    resource_names.append(resource_name)
                    break
    except Exception as exc:
        logger.error(f"Error searching contacts for email '{email}': {exc}")

    return resource_names


async def _create_contact_for_email(people_service, email: str) -> Optional[str]:
    """
    Create a new contact with the given email address and return its resourceName.
    """
    if not people_service or not email:
        return None

    normalized_email = email.strip()
    if not normalized_email:
        return None

    try:
        def _create():
            return people_service.people().createContact(
                body={"emailAddresses": [{"value": normalized_email}]}
            ).execute()

        person = await asyncio.to_thread(_create)
        resource_name = person.get("resourceName")
        if not resource_name:
            logger.error(f"People API returned contact without resourceName for email '{normalized_email}'")
        return resource_name
    except Exception as exc:
        logger.error(f"Error creating contact for email '{email}': {exc}")
        return None


def _chunked(items: List[str], chunk_size: int):
    """Yield successive chunks from a list."""
    for i in range(0, len(items), chunk_size):
        yield items[i:i + chunk_size]


async def _manage_contact_labels(
    action: str,
    email: GmailRecipientsOptional,
    label: Optional[str],
    user_google_email: UserGoogleEmail
) -> str:
    """
    Handle People contact label operations for manage_gmail_allow_list.

    Supports:
      - 'label_add' to add or create contacts and attach them to a label
      - 'label_remove' to detach matching contacts from a label
    """
    normalized_action = action.lower().strip() if action else ""
    if normalized_action not in ("label_add", "label_remove"):
        return f"❌ Unsupported label action: {action}"

    if not user_google_email:
        return "❌ user_google_email is required for contact label operations"

    if not label or not label.strip():
        return "❌ 'label' parameter is required for contact label actions"

    if email is None:
        return f"❌ Email parameter is required for '{normalized_action}' action"

    raw_tokens = [e.strip() for e in _parse_email_addresses(email)]
    emails = sorted({token for token in raw_tokens if token})
    if not emails:
        return "❌ No valid email addresses provided for label operation"

    people_service = await _get_people_service_for_labels(user_google_email)
    if not people_service:
        return "❌ People API service is not available. Please ensure People scopes are granted."

    label_name = label.strip()
    group_resource = await _ensure_contact_group(people_service, label_name)
    if not group_resource:
        return f"❌ Failed to resolve or create contact label '{label_name}' via People API"

    if normalized_action == "label_add":
        created_contacts: List[str] = []
        existing_contacts: List[str] = []
        failed_emails: List[str] = []
        seen_resource_names = set()

        for addr in emails:
            try:
                matches = await _search_contacts_for_email(people_service, addr)
                if matches:
                    existing_contacts.append(addr)
                    for rn in matches:
                        if rn and rn not in seen_resource_names:
                            seen_resource_names.add(rn)
                else:
                    rn = await _create_contact_for_email(people_service, addr)
                    if rn:
                        created_contacts.append(addr)
                        if rn not in seen_resource_names:
                            seen_resource_names.add(rn)
                    else:
                        failed_emails.append(addr)
            except Exception as exc:
                logger.error(f"Error processing email '{addr}' for label_add: {exc}")
                failed_emails.append(addr)

        resource_names_to_add = list(seen_resource_names)

        modified_count = 0
        batch_errors = 0
        for chunk in _chunked(resource_names_to_add, 200):
            try:
                def _modify():
                    return people_service.contactGroups().members().modify(
                        resourceName=group_resource,
                        body={"resourceNamesToAdd": chunk}
                    ).execute()

                await asyncio.to_thread(_modify)
                modified_count += len(chunk)
            except Exception as exc:
                batch_errors += 1
                logger.error(f"Error adding contacts to label '{label_name}': {exc}")

        lines: List[str] = []
        lines.append(f"✅ Processed {len(emails)} email(s) for People contact label '{label_name}' ({group_resource})")
        lines.append(f"• Added {modified_count} contact(s) to label.")
        if created_contacts:
            lines.append(f"• Created {len(created_contacts)} new contact(s).")
        if existing_contacts:
            lines.append(f"• Found existing contacts for {len(existing_contacts)} email(s).")
        if failed_emails:
            unique_failed = sorted(set(failed_emails))
            lines.append(f"❌ Failed to process {len(unique_failed)} email(s): {', '.join(unique_failed)}")
        if batch_errors:
            lines.append(f"❌ {batch_errors} batch People API operation(s) encountered errors. See logs for details.")

        lines.append("")
        lines.append("Label details:")
        lines.append(f"• Label name: {label_name}")
        lines.append(f"• Label resourceName: {group_resource}")

        return "\n".join(lines)

    # label_remove
    resource_names_to_remove_set = set()
    no_match_emails: List[str] = []
    failed_emails: List[str] = []

    for addr in emails:
        try:
            matches = await _search_contacts_for_email(people_service, addr)
            if matches:
                for rn in matches:
                    if rn:
                        resource_names_to_remove_set.add(rn)
            else:
                no_match_emails.append(addr)
        except Exception as exc:
            logger.error(f"Error processing email '{addr}' for label_remove: {exc}")
            failed_emails.append(addr)

    resource_names_to_remove = list(resource_names_to_remove_set)

    removed_count = 0
    batch_errors = 0
    for chunk in _chunked(resource_names_to_remove, 200):
        try:
            def _modify_remove():
                return people_service.contactGroups().members().modify(
                    resourceName=group_resource,
                    body={"resourceNamesToRemove": chunk}
                ).execute()

            await asyncio.to_thread(_modify_remove)
            removed_count += len(chunk)
        except Exception as exc:
            batch_errors += 1
            logger.error(f"Error removing contacts from label '{label_name}': {exc}")

    lines = []
    lines.append(f"✅ Processed {len(emails)} email(s) for People contact label '{label_name}' ({group_resource})")
    lines.append(f"• Removed {removed_count} contact(s) from label.")
    if no_match_emails:
        lines.append(f"ℹ️ No matching contacts found for {len(no_match_emails)} email(s): {', '.join(no_match_emails)}")
    if failed_emails:
        unique_failed = sorted(set(failed_emails))
        lines.append(f"❌ Failed to process {len(unique_failed)} email(s): {', '.join(unique_failed)}")
    if batch_errors:
        lines.append(f"❌ {batch_errors} batch People API operation(s) encountered errors. See logs for details.")

    lines.append("")
    lines.append("Label details:")
    lines.append(f"• Label name: {label_name}")
    lines.append(f"• Label resourceName: {group_resource}")

    return "\n".join(lines)


async def manage_gmail_allow_list(
    action: str,
    email: GmailRecipientsOptional = None,
    label: Optional[str] = None,
    user_google_email: UserGoogleEmail = None
) -> Union[str, GmailAllowListResponse]:
    """
    Manage the Gmail allow list and People contact labels.

    This unified tool supports:
      - Gmail allow list operations: add, remove, view
      - People contact label operations: label_add, label_remove

    Args:
        action: Action to perform. Supported values:
            - 'add', 'remove', 'view' for Gmail allow list
            - 'label_add', 'label_remove' for People contact labels
        email: Email address(es) for add/remove operations. Supports:
            - Single email: "user@example.com"
            - List of emails: ["user1@example.com", "user2@example.com"]
            - Comma-separated string: "user1@example.com,user2@example.com"
            (Required for add/remove and label_add/label_remove, ignored for view)
        label: Contact label name for People API operations when using
            'label_add' or 'label_remove' actions.
        user_google_email: The authenticated user's Google email address (for authorization)

    Returns:
        Union[str, GmailAllowListResponse]: Confirmation message for add/remove and label operations,
        structured response for view.
    """
    action = action.lower().strip()
    logger.info(
        f"[manage_gmail_allow_list] User: '{user_google_email}' "
        f"action: '{action}' email(s): '{email}' label: '{label}'"
    )

    valid_actions = {'add', 'remove', 'view', 'label_add', 'label_remove'}
    if action not in valid_actions:
        return "❌ Invalid action. Must be one of: 'add', 'remove', 'view', 'label_add', or 'label_remove'"

    # Delegate People contact label operations to People tools
    if action in ('label_add', 'label_remove'):
        try:
            from people.people_tools import manage_people_contact_labels  # Local import to avoid circulars
        except Exception as exc:
            logger.error(f"Failed to import manage_people_contact_labels from People tools: {exc}")
            return "❌ People contact label management is not available in this deployment"

        return await manage_people_contact_labels(action, email, label, user_google_email)

    # Handle view action
    if action == 'view':
        try:
            # Get current allow list (raw tokens: emails + optional group specs)
            raw_allow_list = settings.get_gmail_allow_list()

            # Split into explicit email entries and group specs
            email_entries, group_specs = split_allow_list_tokens(raw_allow_list)

            # Convert email entries to structured format
            allowed_emails: List[AllowedEmailInfo] = []
            for email_addr in email_entries:
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

            # Convert group specs to structured format (no People API calls here)
            allowed_groups: List[AllowedGroupInfo] = []
            for spec in group_specs:
                value = spec.strip()
                lower = value.lower()
                group_entry: AllowedGroupInfo = {
                    "raw": value
                }
                if lower.startswith("groupid:"):
                    group_entry["type"] = "id"
                    group_entry["group_id"] = value[len("groupId:"):].strip()
                elif lower.startswith("group:"):
                    group_entry["type"] = "name"
                    group_entry["group_name"] = value[len("group:"):].strip()
                else:
                    # Fallback - unknown format but still expose raw token
                    group_entry["type"] = "unknown"
                allowed_groups.append(group_entry)

            total_entries = len(allowed_emails) + len(allowed_groups)
            logger.info(f"Successfully retrieved {total_entries} allowed entries "
                        f"({len(allowed_emails)} emails, {len(allowed_groups)} groups) for {user_google_email}")

            response: GmailAllowListResponse = {
                "allowed_emails": allowed_emails,
                "count": total_entries,
                "userEmail": user_google_email,
                "is_configured": total_entries > 0,
                "source": "GMAIL_ALLOW_LIST environment variable",
                "error": None
            }
            # Only include allowed_groups key when we actually have group specs
            if allowed_groups:
                response["allowed_groups"] = allowed_groups

            return response

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

    # Parse input tokens (emails and/or group specs)
    raw_tokens = [e.strip() for e in _parse_email_addresses(email)]
    if not raw_tokens:
        return "❌ No valid email or group entries provided"

    # Split into email-like tokens and group specs (group: / groupId:)
    email_like_tokens, group_specs_to_process = split_allow_list_tokens(raw_tokens)

    # Prepare collections for email validation
    invalid_emails: List[str] = []
    valid_emails: List[str] = []

    # Validate email formats for add/remove operations (group specs bypass this)
    if action in ['add', 'remove'] and email_like_tokens:
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

        for email_addr in email_like_tokens:
            if re.match(email_pattern, email_addr.lower()):
                valid_emails.append(email_addr)
            else:
                invalid_emails.append(email_addr)

        # For add operation, ensure we have at least one valid email or group spec
        if not valid_emails and not group_specs_to_process and action == 'add':
            return f"❌ No valid email or group entries found. Invalid: {', '.join(invalid_emails)}"

    # Combine validated emails and group specs into a single list for downstream processing
    emails_to_process = valid_emails + group_specs_to_process

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
                f"• Allow list now contains {len(updated_list)} entries (emails and/or groups)",
                "• Added entries will skip elicitation confirmation when sending emails"
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
                f"• Allow list now contains {len(updated_list)} entries (emails and/or groups)",
                "• Removed entries will now require elicitation confirmation when sending emails"
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
        description=(
            "Manage the workspace trust list stored in GMAIL_ALLOW_LIST and related People "
            "contact labels. Supports 'add', 'remove', 'view' for the Gmail/Chat trust list "
            "and 'label_add', 'label_remove' for People contact labels. Trust entries can "
            "be single emails, lists, or comma-separated strings; group specs "
            "('group:<name>', 'groupId:<resource>') are resolved via the People API. "
            "Trusted recipients/targets skip elicitation confirmation for Gmail sending "
            "operations today and (in future) selected Chat operations."
        ),
        tags={"gmail", "allow-list", "security", "management", "trusted", "bulk", "unified", "workspace"},
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
        email: GmailRecipientsOptional = None,
        label: Optional[str] = None,
        user_google_email: UserGoogleEmail = None
    ) -> Union[str, GmailAllowListResponse]:
        return await manage_gmail_allow_list(action, email, label, user_google_email)