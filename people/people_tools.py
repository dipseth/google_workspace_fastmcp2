"""
People API tools for FastMCP2.

Currently includes:
- list_people_contact_labels: list Google People contact groups / labels.

═══════════════════════════════════════════════════════════════════════════════
                      👥 THE CONNECTIVE TISSUE 👥
═══════════════════════════════════════════════════════════════════════════════

    Between the system and the soul
    lies metadata's quiet role.
    A contact group, a label's name—
    "Family," "Work," they're not the same.

    The People API knows the links,
    who connects to whom, and thinks
    in resourceNames, membership lists,
    the social graph that still persists.

    _parse_label_emails takes the string,
    commas and lists, disentangling.
    "alice@mail.com, bob@mail.com"
    becomes a list that feels like home.

    _ensure_contact_group creates
    what doesn't exist, anticipates
    the need for labels yet unborn,
    new groups assembled, freshly worn.

    This module's small but holds the key:
    identity and company.
    For what's an inbox without names?
    Just addresses playing games.

    The People tools remind us all:
    behind each ID stands a call,
    a human waiting to be known,
    not just an email, carved in stone.

                                        — Field Notes, Jan 2026

═══════════════════════════════════════════════════════════════════════════════
"""

import asyncio

from fastmcp import FastMCP
from googleapiclient.discovery import build
from typing_extensions import Any, Dict, List, Optional, Union

from auth.context import get_auth_middleware
from config.enhanced_logging import setup_logger
from tools.common_types import UserGoogleEmail

from .people_types import (
    ContactLabelInfo,
    GetPeopleContactGroupMembersResponse,
    ListPeopleContactLabelsResponse,
    ManagePeopleContactLabelsResponse,
)

logger = setup_logger()


async def _get_people_service(user_email: UserGoogleEmail):
    """
    Build a Google People API service instance.

    Returns:
        A People API service client or None if credentials are unavailable.
    """
    if not user_email:
        logger.warning("No user email provided for People API (contact labels listing)")
        return None

    try:
        auth_middleware = get_auth_middleware()
    except Exception as exc:
        logger.warning(
            f"AuthMiddleware lookup failed for People API (contact labels listing): {exc}"
        )
        return None

    if not auth_middleware:
        logger.warning(
            "No AuthMiddleware available for People API (contact labels listing)"
        )
        return None

    try:
        credentials = auth_middleware.load_credentials(user_email)
    except Exception as exc:
        logger.warning(
            f"Error loading credentials for People API (contact labels listing) for user {user_email}: {exc}"
        )
        return None

    if not credentials:
        logger.warning(
            f"No credentials found for People API (contact labels listing) for user {user_email}"
        )
        return None

    try:
        return await asyncio.to_thread(build, "people", "v1", credentials=credentials)
    except Exception as exc:
        logger.error(f"Failed to build People API service for user {user_email}: {exc}")
        return None


def _parse_label_emails(email_input: Union[str, List[str], None]) -> List[str]:
    """
    Lightweight email token parser for People label operations.

    Supports:
      - Single string: "a@example.com,b@example.com"
      - List of strings: ["a@example.com", "b@example.com"]
    """
    tokens: List[str] = []
    if email_input is None:
        return tokens

    if isinstance(email_input, str):
        tokens = [part.strip() for part in email_input.split(",")]
    elif isinstance(email_input, list):
        for item in email_input:
            if isinstance(item, str):
                tokens.extend(part.strip() for part in item.split(","))

    return [t for t in tokens if t]


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
            return (
                people_service.contactGroups()
                .create(body={"contactGroup": {"name": label_name}})
                .execute()
            )

        created = await asyncio.to_thread(_create_group)
        resource_name = created.get("resourceName")
        if not resource_name:
            logger.error(
                f"People API returned contactGroup without resourceName for label '{label_name}'"
            )
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
            return (
                people_service.people()
                .searchContacts(query=normalized_email, readMask="emailAddresses")
                .execute()
            )

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
            return (
                people_service.people()
                .createContact(body={"emailAddresses": [{"value": normalized_email}]})
                .execute()
            )

        person = await asyncio.to_thread(_create)
        resource_name = person.get("resourceName")
        if not resource_name:
            logger.error(
                f"People API returned contact without resourceName for email '{normalized_email}'"
            )
        return resource_name
    except Exception as exc:
        logger.error(f"Error creating contact for email '{email}': {exc}")
        return None


def _chunked(items: List[str], chunk_size: int):
    """Yield successive chunks from a list."""
    for i in range(0, len(items), chunk_size):
        yield items[i : i + chunk_size]


async def manage_people_contact_labels(
    action: str,
    email: Union[str, List[str], None] = None,
    label: Optional[str] = None,
    user_google_email: UserGoogleEmail = None,
) -> ManagePeopleContactLabelsResponse:
    """
    Manage Google People contact labels (contact groups) for one or more emails.

    Supports:
      - 'label_add' to add or create contacts and attach them to a label
      - 'label_remove' to detach matching contacts from a label
    """
    normalized_action = action.lower().strip() if action else ""
    if normalized_action not in ("label_add", "label_remove"):
        return ManagePeopleContactLabelsResponse(
            success=False,
            action=action or "",
            label_name=label or "",
            error=f"Unsupported label action: {action}",
            message=f"Unsupported label action: {action}",
        )

    if not user_google_email:
        return ManagePeopleContactLabelsResponse(
            success=False,
            action=normalized_action,
            label_name=label or "",
            error="user_google_email is required for contact label operations",
            message="user_google_email is required for contact label operations",
        )

    if not label or not label.strip():
        return ManagePeopleContactLabelsResponse(
            success=False,
            action=normalized_action,
            label_name="",
            error="'label' parameter is required for contact label actions",
            message="'label' parameter is required for contact label actions",
        )

    if email is None:
        return ManagePeopleContactLabelsResponse(
            success=False,
            action=normalized_action,
            label_name=label,
            error=f"Email parameter is required for '{normalized_action}' action",
            message=f"Email parameter is required for '{normalized_action}' action",
        )

    raw_tokens = [e.strip() for e in _parse_label_emails(email)]
    emails = sorted({token for token in raw_tokens if token})
    if not emails:
        return ManagePeopleContactLabelsResponse(
            success=False,
            action=normalized_action,
            label_name=label,
            error="No valid email addresses provided for label operation",
            message="No valid email addresses provided for label operation",
        )

    people_service = await _get_people_service(user_google_email)
    if not people_service:
        return ManagePeopleContactLabelsResponse(
            success=False,
            action=normalized_action,
            label_name=label,
            error="People API service is not available. Please ensure People scopes are granted.",
            message="People API service is not available. Please ensure People scopes are granted.",
        )

    label_name = label.strip()
    group_resource = await _ensure_contact_group(people_service, label_name)
    if not group_resource:
        return ManagePeopleContactLabelsResponse(
            success=False,
            action=normalized_action,
            label_name=label_name,
            error=f"Failed to resolve or create contact label '{label_name}' via People API",
            message=f"Failed to resolve or create contact label '{label_name}' via People API",
        )

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
                    return (
                        people_service.contactGroups()
                        .members()
                        .modify(
                            resourceName=group_resource,
                            body={"resourceNamesToAdd": chunk},
                        )
                        .execute()
                    )

                await asyncio.to_thread(_modify)
                modified_count += len(chunk)
            except Exception as exc:
                batch_errors += 1
                logger.error(f"Error adding contacts to label '{label_name}': {exc}")

        # Build message
        lines: List[str] = []
        lines.append(
            f"Processed {len(emails)} email(s) for People contact label '{label_name}'"
        )
        lines.append(f"Added {modified_count} contact(s) to label.")
        if created_contacts:
            lines.append(f"Created {len(created_contacts)} new contact(s).")
        if existing_contacts:
            lines.append(
                f"Found existing contacts for {len(existing_contacts)} email(s)."
            )
        if failed_emails:
            unique_failed = sorted(set(failed_emails))
            lines.append(
                f"Failed to process {len(unique_failed)} email(s): {', '.join(unique_failed)}"
            )
        if batch_errors:
            lines.append(
                f"{batch_errors} batch People API operation(s) encountered errors."
            )

        return ManagePeopleContactLabelsResponse(
            success=len(failed_emails) == 0 and batch_errors == 0,
            action=normalized_action,
            label_name=label_name,
            label_resourceName=group_resource,
            emails_processed=len(emails),
            contacts_modified=modified_count,
            contacts_created=len(created_contacts),
            contacts_existing=len(existing_contacts),
            failed_emails=sorted(set(failed_emails)),
            batch_errors=batch_errors,
            message=" ".join(lines),
        )

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
                return (
                    people_service.contactGroups()
                    .members()
                    .modify(
                        resourceName=group_resource,
                        body={"resourceNamesToRemove": chunk},
                    )
                    .execute()
                )

            await asyncio.to_thread(_modify_remove)
            removed_count += len(chunk)
        except Exception as exc:
            batch_errors += 1
            logger.error(f"Error removing contacts from label '{label_name}': {exc}")

    # Build message
    lines = []
    lines.append(
        f"Processed {len(emails)} email(s) for People contact label '{label_name}'"
    )
    lines.append(f"Removed {removed_count} contact(s) from label.")
    if no_match_emails:
        lines.append(f"No matching contacts found for {len(no_match_emails)} email(s).")
    if failed_emails:
        unique_failed = sorted(set(failed_emails))
        lines.append(
            f"Failed to process {len(unique_failed)} email(s): {', '.join(unique_failed)}"
        )
    if batch_errors:
        lines.append(
            f"{batch_errors} batch People API operation(s) encountered errors."
        )

    return ManagePeopleContactLabelsResponse(
        success=len(failed_emails) == 0 and batch_errors == 0,
        action=normalized_action,
        label_name=label_name,
        label_resourceName=group_resource,
        emails_processed=len(emails),
        contacts_modified=removed_count,
        contacts_not_found=len(no_match_emails),
        failed_emails=sorted(set(failed_emails)),
        batch_errors=batch_errors,
        message=" ".join(lines),
    )


async def get_people_contact_group_members(
    label: str,
    user_google_email: UserGoogleEmail = None,
) -> GetPeopleContactGroupMembersResponse:
    """
    Get all member emails from a People API contact group/label.

    This enables label-to-emails resolution, similar to Gmail's autocomplete.

    Args:
        label: Contact group/label name (e.g., "Work Team", "AI Tribe")
        user_google_email: User's Google email address

    Returns:
        GetPeopleContactGroupMembersResponse containing emails, member_count, label_name, resourceName
    """
    if not user_google_email:
        return GetPeopleContactGroupMembersResponse(
            success=False,
            label_name=label or "",
            error="user_google_email is required",
        )

    if not label or not label.strip():
        return GetPeopleContactGroupMembersResponse(
            success=False,
            error="'label' parameter is required",
        )

    people_service = await _get_people_service(user_google_email)
    if not people_service:
        return GetPeopleContactGroupMembersResponse(
            success=False,
            label_name=label,
            error="People API service is not available. Please ensure People scopes are granted.",
        )

    label_name = label.strip()

    # Find the group resource name
    group_resource = await _ensure_contact_group(people_service, label_name)
    if not group_resource:
        return GetPeopleContactGroupMembersResponse(
            success=False,
            label_name=label_name,
            error=f"Contact group '{label_name}' not found",
        )

    try:
        # Get group with members (up to 1000)
        def _get_group():
            return (
                people_service.contactGroups()
                .get(
                    resourceName=group_resource,
                    maxMembers=1000,
                )
                .execute()
            )

        group_data = await asyncio.to_thread(_get_group)
        member_resource_names = group_data.get("memberResourceNames", [])

        if not member_resource_names:
            return GetPeopleContactGroupMembersResponse(
                success=True,
                emails=[],
                member_count=0,
                label_name=label_name,
                resourceName=group_resource,
            )

        # Batch get contact details for all members
        emails: List[str] = []

        # People API allows batch get up to 200 contacts at a time
        for chunk in _chunked(member_resource_names, 200):
            try:

                def _batch_get():
                    return (
                        people_service.people()
                        .getBatchGet(resourceNames=chunk, personFields="emailAddresses")
                        .execute()
                    )

                batch_result = await asyncio.to_thread(_batch_get)

                for response in batch_result.get("responses", []):
                    person = response.get("person", {})
                    email_addrs = person.get("emailAddresses", [])
                    for email_obj in email_addrs:
                        email_val = email_obj.get("value", "").strip()
                        if email_val and email_val not in emails:
                            emails.append(email_val)

            except Exception as exc:
                logger.error(
                    f"Error fetching batch of contact emails for group '{label_name}': {exc}"
                )

        return GetPeopleContactGroupMembersResponse(
            success=True,
            emails=sorted(emails),
            member_count=len(emails),
            label_name=label_name,
            resourceName=group_resource,
        )

    except Exception as exc:
        logger.error(f"Error getting members for contact group '{label_name}': {exc}")
        return GetPeopleContactGroupMembersResponse(
            success=False,
            label_name=label_name,
            resourceName=group_resource,
            error=f"Error getting members: {exc}",
        )


async def list_people_contact_labels(
    user_google_email: UserGoogleEmail = None,
) -> ListPeopleContactLabelsResponse:
    """
    List Google People contact groups / labels for the authenticated user.

    Returns a structured payload including:
      - labels: list of groups with resourceName, name, memberCount, groupType
      - total_count: number of groups
      - user_email: user whose labels were listed
    """
    people_service = await _get_people_service(user_google_email)
    if not people_service:
        return ListPeopleContactLabelsResponse(
            success=False,
            user_email=user_google_email or "",
            error="People API service is not available. Please ensure People scopes are granted.",
        )

    try:

        def _list_groups():
            return (
                people_service.contactGroups()
                .list(
                    pageSize=200,
                    # groupFields can include "metadata,groupType,memberCount,name"
                    groupFields="metadata,groupType,memberCount,name",
                )
                .execute()
            )

        result = await asyncio.to_thread(_list_groups)
    except Exception as exc:
        logger.error(
            f"Error listing People contact groups for {user_google_email}: {exc}"
        )
        return ListPeopleContactLabelsResponse(
            success=False,
            user_email=user_google_email or "",
            error=f"Error listing People contact groups: {exc}",
        )

    raw_groups: List[Dict[str, Any]] = result.get("contactGroups", []) or []
    labels: List[ContactLabelInfo] = []

    for group in raw_groups:
        resource_name = group.get("resourceName")
        name = group.get("name")
        member_count = group.get("memberCount", 0)
        group_type = group.get("groupType")

        if not resource_name:
            continue

        labels.append(
            ContactLabelInfo(
                resourceName=resource_name,
                name=name,
                memberCount=member_count,
                formattedMemberCount=f"{member_count:,}",
                groupType=group_type,
            )
        )

    return ListPeopleContactLabelsResponse(
        success=True,
        labels=labels,
        total_count=len(labels),
        user_email=user_google_email or "",
    )


def setup_people_tools(mcp: FastMCP) -> None:
    """Register People API tools with the FastMCP server."""

    @mcp.tool(
        name="list_people_contact_labels",
        description=(
            "List Google People contact groups / labels for the authenticated user, "
            "returning resourceName, name, member counts, and groupType."
        ),
        tags={"people", "contacts", "labels", "list", "service"},
    )
    async def list_people_contact_labels_tool(
        user_google_email: UserGoogleEmail = None,
    ) -> ListPeopleContactLabelsResponse:
        return await list_people_contact_labels(user_google_email)

    @mcp.tool(
        name="get_people_contact_group_members",
        description=(
            "Resolve a contact group/label name to its member email addresses. "
            "Similar to Gmail's autocomplete - type a label name and get all emails in that group. "
            "Useful for batch operations: resolve label → get emails → perform actions on those emails."
        ),
        tags={"people", "contacts", "labels", "resolve", "emails", "autocomplete"},
    )
    async def get_people_contact_group_members_tool(
        label: str,
        user_google_email: UserGoogleEmail = None,
    ) -> GetPeopleContactGroupMembersResponse:
        return await get_people_contact_group_members(label, user_google_email)

    @mcp.tool(
        name="manage_people_contact_labels",
        description=(
            "Manage Google People contact labels (contact groups) for one or more emails. "
            "Supports 'label_add' to ensure contacts exist and attach them to a label, "
            "and 'label_remove' to detach matching contacts from a label."
        ),
        tags={"people", "contacts", "labels", "manage", "workspace", "allow-list"},
    )
    async def manage_people_contact_labels_tool(
        action: str,
        email: Union[str, List[str], None] = None,
        label: Optional[str] = None,
        user_google_email: UserGoogleEmail = None,
    ) -> ManagePeopleContactLabelsResponse:
        return await manage_people_contact_labels(
            action=action,
            email=email,
            label=label,
            user_google_email=user_google_email,
        )
