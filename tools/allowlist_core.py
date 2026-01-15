"""Shared workspace trust list (allow list) helpers for Gmail & Chat.

This module is NOT an MCP tool itself. It provides reusable helpers for:
- Parsing GMAIL_ALLOW_LIST tokens into typed entries
- Resolving People contact group specs via the People API
- Determining which recipients are NOT trusted based on:
  - Explicit email entries
  - People contact group membership
  - (Planned) Chat space specs
"""

import asyncio
import re
from dataclasses import dataclass

from googleapiclient.discovery import build
from typing_extensions import List, Literal

from auth.context import get_auth_middleware
from config.enhanced_logging import setup_logger
from tools.common_types import UserGoogleEmail

logger = setup_logger()


@dataclass
class AllowListEntry:
    """Typed representation of a single trust-list token."""

    kind: Literal[
        "email", "people_group_name", "people_group_id", "chat_space", "unknown"
    ]
    raw: str
    value: str  # normalized core value (email, group name/id, or space id)


_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def parse_allow_list_tokens(tokens: List[str]) -> List[AllowListEntry]:
    """
    Parse raw allow list tokens into typed entries.

    Recognized formats:
      - user@example.com                   → kind="email"
      - group:Team Name                    → kind="people_group_name"
      - groupId:contactGroups/123          → kind="people_group_id"
      - space:spaces/AAAA...               → kind="chat_space" (for Chat spaces)
      - anything else                      → kind="unknown"
    """
    entries: List[AllowListEntry] = []

    for raw in tokens:
        if not raw:
            continue
        value = raw.strip()
        if not value:
            continue

        lower = value.lower()

        if lower.startswith("groupid:"):
            inner = value[len("groupid:") :].strip()
            entries.append(
                AllowListEntry(
                    kind="people_group_id",
                    raw=value,
                    value=inner,
                )
            )
        elif lower.startswith("group:"):
            inner = value[len("group:") :].strip()
            entries.append(
                AllowListEntry(
                    kind="people_group_name",
                    raw=value,
                    value=inner,
                )
            )
        elif lower.startswith("space:"):
            inner = value[len("space:") :].strip()
            entries.append(
                AllowListEntry(
                    kind="chat_space",
                    raw=value,
                    value=inner or value,
                )
            )
        else:
            # Try to treat as an email; otherwise mark as unknown
            if _EMAIL_REGEX.match(value):
                entries.append(
                    AllowListEntry(
                        kind="email",
                        raw=value,
                        value=value.lower(),
                    )
                )
            else:
                entries.append(
                    AllowListEntry(
                        kind="unknown",
                        raw=value,
                        value=value,
                    )
                )

    return entries


async def _get_people_service_for_trust(user_email: UserGoogleEmail):
    """
    Create a People API service instance for trust-list group resolution.

    This mirrors the AuthMiddleware-backed credential loading pattern used
    elsewhere in the project.
    """
    try:
        if not user_email:
            logger.warning("No user email provided for People API (trust list groups)")
            return None

        auth_middleware = get_auth_middleware()
        if not auth_middleware:
            logger.warning(
                "No AuthMiddleware available for People API (trust list groups)"
            )
            return None

        credentials = auth_middleware.load_credentials(user_email)
        if not credentials:
            logger.warning(
                f"No credentials found for People API (trust list groups) for user {user_email}"
            )
            return None

        people_service = await asyncio.to_thread(
            build, "people", "v1", credentials=credentials
        )
        return people_service
    except Exception as exc:
        logger.error(
            f"Failed to create People API service for trust list groups: {exc}",
            exc_info=True,
        )
        return None


async def _resolve_allowed_group_ids(
    group_entries: List[AllowListEntry],
    people_service,
) -> List[str]:
    """
    Resolve configured People group entries into contact group resourceNames.

    Supports:
      - kind="people_group_name"  → resolved via contactGroups.list() name matching
      - kind="people_group_id"    → used as-is
    """
    allowed_ids: List[str] = []
    if not people_service or not group_entries:
        return allowed_ids

    try:

        def _list_groups():
            return people_service.contactGroups().list(pageSize=200).execute()

        result = await asyncio.to_thread(_list_groups)
        groups = result.get("contactGroups", []) or []
        name_to_id = {
            g.get("name", ""): g.get("resourceName")
            for g in groups
            if g.get("name") and g.get("resourceName")
        }

        for entry in group_entries:
            if entry.kind == "people_group_id":
                gid = entry.value.strip()
                if gid:
                    allowed_ids.append(gid)
            elif entry.kind == "people_group_name":
                gid = name_to_id.get(entry.value)
                if gid:
                    allowed_ids.append(gid)
                else:
                    logger.warning(
                        f"[trust_list] No contact group found with name '{entry.value}'"
                    )
    except Exception as exc:
        logger.error(
            f"Failed to resolve trust list group specs via People API: {exc}",
            exc_info=True,
        )

    return allowed_ids


async def _get_contact_group_ids_for_email(email: str, people_service) -> List[str]:
    """
    Fetch contact group resourceNames for a given email using People API.

    Uses people.searchContacts with readMask including memberships.
    """
    group_ids: List[str] = []
    if not people_service or not email:
        return group_ids

    try:

        def _search():
            return (
                people_service.people()
                .searchContacts(
                    query=email,
                    readMask="emailAddresses,memberships",
                )
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
            for membership in person.get("memberships", []):
                cgm = membership.get("contactGroupMembership")
                if cgm:
                    gid = cgm.get("contactGroupResourceName")
                    if gid:
                        group_ids.append(gid)
    except Exception as exc:
        logger.error(
            f"Failed to fetch contact group memberships for {email}: {exc}",
            exc_info=True,
        )

    return group_ids


async def filter_recipients_allowed_by_groups(
    recipients: List[str],
    entries: List[AllowListEntry],
    user_google_email: UserGoogleEmail,
) -> List[str]:
    """
    Determine which recipients should be considered allowed based on People groups.

    Steps:
      1) Resolve configured group specs → contact group resourceNames
      2) For each recipient, fetch memberships and see if they belong to any allowed group
    """
    allowed_recipients: List[str] = []

    # Extract only group-related entries
    group_entries = [
        e for e in entries if e.kind in ("people_group_name", "people_group_id")
    ]
    if not group_entries or not recipients:
        return allowed_recipients

    people_service = await _get_people_service_for_trust(user_google_email)
    if not people_service:
        return allowed_recipients

    allowed_group_ids = await _resolve_allowed_group_ids(group_entries, people_service)
    if not allowed_group_ids:
        return allowed_recipients

    allowed_group_ids_set = set(allowed_group_ids)

    # De-duplicate recipients for efficiency
    unique_recipients = sorted(set(recipients))
    for email in unique_recipients:
        group_ids = await _get_contact_group_ids_for_email(email, people_service)
        if not group_ids:
            continue

        if allowed_group_ids_set.intersection(group_ids):
            allowed_recipients.append(email)

    if allowed_recipients:
        logger.info(
            f"[trust_list] Marked {len(allowed_recipients)} recipient(s) as allowed via contact group membership"
        )

    return allowed_recipients


async def resolve_untrusted_recipients(
    recipients: List[str],
    allow_tokens: List[str],
    user_google_email: UserGoogleEmail,
) -> List[str]:
    """
    Given a list of recipient email addresses and raw allow-list tokens, return
    the subset of recipients that are NOT trusted.

    Recipients are considered trusted if:
      - Their normalized email is explicitly in the allow list, OR
      - They are a member of any allowed People contact group.
    """
    if not recipients:
        return []

    entries = parse_allow_list_tokens(allow_tokens or [])

    # Normalize recipients to lowercase, trimmed
    normalized_recipients = [
        (email or "").strip().lower() for email in recipients if (email or "").strip()
    ]

    # Explicit email entries
    explicit_emails = {e.value for e in entries if e.kind == "email" and e.value}

    # Initial pass: recipients not covered by explicit email entries
    not_allowed = [
        email for email in normalized_recipients if email not in explicit_emails
    ]

    if not not_allowed:
        return []

    # Apply People group-based trust if group specs are configured
    allowed_via_groups = await filter_recipients_allowed_by_groups(
        not_allowed,
        entries,
        user_google_email,
    )

    if not allowed_via_groups:
        return not_allowed

    allowed_set = set(allowed_via_groups)
    remaining = [email for email in not_allowed if email not in allowed_set]
    return remaining
