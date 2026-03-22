"""
Gmail email composition and sending tools for FastMCP2.

This module provides tools for:
- Sending emails with elicitation support for untrusted recipients
- Creating email drafts
- Replying to messages with proper threading
- Creating draft replies
"""

import asyncio
import html
from dataclasses import dataclass

from fastmcp import Context, FastMCP
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import Field
from typing_extensions import Annotated, List, Literal, Optional, Union

from auth.context import get_auth_middleware
from config.enhanced_logging import setup_logger
from config.settings import settings
from tools.common_types import UserGoogleEmail

from .gmail_types import (
    DraftGmailForwardResponse,
    DraftGmailMessageResponse,
    DraftGmailReplyResponse,
    ForwardGmailMessageResponse,
    GmailRecipients,
    GmailRecipientsOptional,
    ReplyGmailMessageResponse,
    SendGmailMessageResponse,
)
from .mjml_types import EmailSpec
from .service import _get_gmail_service_with_fallback
from .utils import (
    _create_mime_message,
    _extract_html_body,
    _extract_message_body,
    _format_forward_content,
    _prepare_forward_subject,
    _prepare_reply_subject,
    _quote_original_message,
    count_recipients,
    extract_email_addresses,
)

logger = setup_logger()


@dataclass
class EmailAction:
    action: Literal["send", "save_draft", "cancel"]


def _resolve_recipient_aliases(
    recipient: Union[str, List[str], None], user_google_email: str
) -> Union[str, List[str], None]:
    """
    Resolve 'me'/'myself' aliases in recipient fields to actual user email.

    Args:
        recipient: Recipient(s) that may contain 'me'/'myself' aliases
        user_google_email: Actual user email to substitute for aliases

    Returns:
        Resolved recipient(s) with aliases replaced by actual email
    """
    if not recipient:
        return recipient

    if isinstance(recipient, str):
        # Handle single string or comma-separated list
        if "," in recipient:
            emails = [email.strip() for email in recipient.split(",")]
            resolved = [
                user_google_email if email.lower() in ["me", "myself"] else email
                for email in emails
            ]
            return ", ".join(resolved)
        else:
            # Single recipient
            if recipient.strip().lower() in ["me", "myself"]:
                return user_google_email
            return recipient

    elif isinstance(recipient, list):
        # List of recipients
        return [
            user_google_email if email.strip().lower() in ["me", "myself"] else email
            for email in recipient
        ]

    return recipient


async def _resolve_group_recipients(
    recipients: Union[str, List[str], None], user_google_email: UserGoogleEmail
) -> Union[str, List[str], None]:
    """
    Resolve group: and groupId: recipient specs to actual email addresses.

    This enables sending to groups by specifying:
      - "group:Team Name" → resolves to all member emails
      - "groupId:contactGroups/123" → resolves to all member emails

    Args:
        recipients: May contain group specs mixed with regular emails
        user_google_email: For People API access

    Returns:
        Recipients with group specs expanded to actual emails
    """
    if not recipients or not user_google_email:
        return recipients

    # Import People tools for group resolution
    try:
        from people.people_tools import get_people_contact_group_members
    except Exception as exc:
        logger.warning(f"Failed to import People tools for group resolution: {exc}")
        return recipients

    # Convert to list for processing
    if isinstance(recipients, str):
        recipient_list = [r.strip() for r in recipients.split(",")]
    elif isinstance(recipients, list):
        recipient_list = recipients
    else:
        return recipients

    resolved_emails: List[str] = []

    for recipient in recipient_list:
        recipient = recipient.strip()
        if not recipient:
            continue

        lower = recipient.lower()

        # Check if this is a group spec
        if lower.startswith("group:"):
            # Extract group name
            group_name = recipient[len("group:") :].strip()
            logger.info(
                f"Resolving group spec 'group:{group_name}' to member emails..."
            )

            # Call People API to get group members
            result = await get_people_contact_group_members(
                group_name, user_google_email
            )

            if result.get("error"):
                logger.warning(
                    f"Failed to resolve group '{group_name}': {result['error']}"
                )
                # Keep the original spec if resolution fails
                resolved_emails.append(recipient)
            elif result.get("emails"):
                member_emails = result["emails"]
                logger.info(
                    f"Resolved 'group:{group_name}' to {len(member_emails)} member(s)"
                )
                resolved_emails.extend(member_emails)
            else:
                logger.warning(f"Group '{group_name}' has no members")

        elif lower.startswith("groupid:"):
            # Extract resource name
            resource_name = recipient[len("groupId:") :].strip()
            logger.warning(
                f"groupId: resolution not yet implemented for '{resource_name}'"
            )
            # Keep the original spec
            resolved_emails.append(recipient)
        else:
            # Regular email address - keep as is
            resolved_emails.append(recipient)

    # Return in same format as input
    if isinstance(recipients, str):
        return ", ".join(resolved_emails)
    else:
        return resolved_emails


async def _resolve_recipients_and_check_allow_list(
    to: Union[str, List[str]],
    cc: Optional[Union[str, List[str]]],
    bcc: Optional[Union[str, List[str]]],
    user_google_email: UserGoogleEmail,
    allow_list: List[str],
) -> List[str]:
    """
    Resolve 'me'/'myself' aliases and check recipients against allow list.

    The allow list now supports:
      - Explicit email addresses (existing behavior)
      - Group specs based on People API contact groups:
        * "group:Team A"           → contact group by display name
        * "groupId:contactGroups/ID" → contact group by resourceName

    Recipients are considered allowed if:
      - Their email is explicitly in the allow list, OR
      - They are a member of any allowed contact group (best-effort via People API), OR
      - They are a group spec that matches an allow list group spec (case-insensitive).

    Returns:
        List of recipients that are NOT on the allow list (after group checks).
    """
    from .allowlist import (
        split_allow_list_tokens,
    )  # Local import to avoid circular imports

    # Split allow list into explicit email entries and group specs
    email_entries, group_specs = split_allow_list_tokens(allow_list)

    # Normalize group specs for case-insensitive matching
    normalized_group_specs = [spec.lower() for spec in group_specs]

    # Collect all recipient emails for the message
    all_recipients: List[str] = []

    # Process 'to' recipients
    if isinstance(to, str):
        all_recipients.extend([email.strip() for email in to.split(",")])
    elif isinstance(to, list):
        all_recipients.extend(to)

    # Process 'cc' recipients
    if cc:
        if isinstance(cc, str):
            all_recipients.extend([email.strip() for email in cc.split(",")])
        elif isinstance(cc, list):
            all_recipients.extend(cc)

    # Process 'bcc' recipients
    if bcc:
        if isinstance(bcc, str):
            all_recipients.extend([email.strip() for email in bcc.split(",")])
        elif isinstance(bcc, list):
            all_recipients.extend(bcc)

    # Resolve 'me'/'myself' aliases to actual user email before elicitation check
    # ALSO check if any recipient is a group spec that's in the allow list
    resolved_recipients: List[str] = []
    group_specs_found_in_recipients: List[str] = []

    for email in all_recipients:
        email_lower = email.strip().lower()

        # Check if this is a 'me'/'myself' alias
        if email_lower in ["me", "myself"]:
            # Resolve to actual user email address
            if user_google_email:
                resolved_recipients.append(user_google_email.strip().lower())
            # If user_google_email not available yet, skip elicitation for 'me'/'myself'
            # The middleware will resolve it properly later
        # Check if this recipient is itself a group spec that's in the allow list
        elif email_lower.startswith("group:") or email_lower.startswith("groupid:"):
            if email_lower in normalized_group_specs:
                # This group spec is in the allow list - mark as allowed
                logger.info(
                    f"Recipient '{email}' is a group spec in allow list - treating as allowed"
                )
                group_specs_found_in_recipients.append(email_lower)
                # Don't add to resolved_recipients - it's already allowed
            else:
                # Group spec not in allow list - treat as regular recipient
                resolved_recipients.append(email_lower)
        else:
            resolved_recipients.append(email_lower)

    # Normalize resolved recipient emails (lowercase, strip whitespace)
    all_recipients = [email for email in resolved_recipients if email]

    # Normalize allow list explicit email entries
    normalized_allow_emails = [email.lower() for email in email_entries]

    # Initial pass: recipients not covered by explicit email entries
    recipients_not_allowed = [
        email for email in all_recipients if email not in normalized_allow_emails
    ]

    # If there are group specs configured, try to allow some recipients via People API group membership
    if group_specs and recipients_not_allowed and user_google_email:
        group_allowed = await _filter_recipients_allowed_by_groups(
            recipients_not_allowed, group_specs, user_google_email
        )
        # Keep only those still not allowed after group checks
        recipients_not_allowed = [
            email for email in recipients_not_allowed if email not in group_allowed
        ]

    return recipients_not_allowed


async def _get_people_service_for_allow_list(user_email: UserGoogleEmail):
    """
    Create a People API service instance for allow list group resolution.

    This uses the same AuthMiddleware-backed credential loading approach as the
    profile enrichment middleware, but is scoped specifically for allow list checks.

    Returns:
        People API service instance or None on failure.
    """
    try:
        if not user_email:
            logger.warning("No user email provided for People API (allow list groups)")
            return None

        auth_middleware = get_auth_middleware()
        if not auth_middleware:
            logger.warning(
                "No AuthMiddleware available for People API (allow list groups)"
            )
            return None

        credentials = auth_middleware.load_credentials(user_email)
        if not credentials:
            logger.warning(
                f"No credentials found for People API (allow list groups) for user {user_email}"
            )
            return None

        people_service = await asyncio.to_thread(
            build, "people", "v1", credentials=credentials
        )
        return people_service
    except Exception as e:
        logger.error(
            f"Failed to create People API service for allow list groups: {e}",
            exc_info=True,
        )
        return None


async def _resolve_allowed_group_ids(
    group_specs: List[str], people_service
) -> List[str]:
    """
    Resolve configured group specs into concrete contact group resourceNames.

    Supports:
      - "group:Team A" → resolved via contactGroups.list() name matching
      - "groupId:contactGroups/123" → used as-is

    Returns:
        List of contact group resourceNames to treat as trusted groups.
    """
    allowed_ids: List[str] = []
    try:
        # Fetch user's contact groups once for name → resourceName mapping
        def _list_groups():
            return people_service.contactGroups().list(pageSize=200).execute()

        result = await asyncio.to_thread(_list_groups)
        groups = result.get("contactGroups", []) or []
        name_to_id = {
            g.get("name", ""): g.get("resourceName")
            for g in groups
            if g.get("name") and g.get("resourceName")
        }

        for spec in group_specs:
            value = spec.strip()
            lower = value.lower()
            if lower.startswith("groupid:"):
                gid = value[len("groupId:") :].strip()
                if gid:
                    allowed_ids.append(gid)
            elif lower.startswith("group:"):
                group_name = value[len("group:") :].strip()
                gid = name_to_id.get(group_name)
                if gid:
                    allowed_ids.append(gid)
                else:
                    logger.warning(
                        f"[allow_list_groups] No contact group found with name '{group_name}'"
                    )
            else:
                logger.warning(
                    f"[allow_list_groups] Unknown group spec format: {value}"
                )

    except Exception as e:
        logger.error(
            f"Failed to resolve allow list group specs via People API: {e}",
            exc_info=True,
        )

    return allowed_ids


async def _get_contact_group_ids_for_email(email: str, people_service) -> List[str]:
    """
    Fetch contact group resourceNames for a given email using People API.

    This uses people.searchContacts with readMask including memberships.
    Returns:
        List of contact group resourceNames the person belongs to.
    """
    group_ids: List[str] = []
    try:

        def _search():
            # searchContacts returns results containing person objects
            return (
                people_service.people()
                .searchContacts(query=email, readMask="emailAddresses,memberships")
                .execute()
            )

        result = await asyncio.to_thread(_search)
        # Handle both "results" (searchContacts) and possible "connections"/"people" structures
        containers = (
            result.get("results")
            or result.get("connections")
            or result.get("people")
            or []
        )

        for item in containers:
            person = item.get("person", item)
            for membership in person.get("memberships", []):
                cgm = membership.get("contactGroupMembership")
                if cgm:
                    gid = cgm.get("contactGroupResourceName")
                    if gid:
                        group_ids.append(gid)

    except Exception as e:
        logger.error(
            f"Failed to fetch contact group memberships for {email}: {e}", exc_info=True
        )

    return group_ids


async def _filter_recipients_allowed_by_groups(
    recipients: List[str], group_specs: List[str], user_google_email: UserGoogleEmail
) -> List[str]:
    """
    Determine which recipients should be considered allowed based on group specs.

    Uses People API to:
      1) Resolve configured group specs → contact group resourceNames
      2) For each recipient, fetch memberships and see if they belong to any allowed group

    Returns:
        List of recipient emails that are allowed via contact group membership.
    """
    allowed_recipients: List[str] = []

    people_service = await _get_people_service_for_allow_list(user_google_email)
    if not people_service:
        return allowed_recipients

    allowed_group_ids = await _resolve_allowed_group_ids(group_specs, people_service)
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
            f"[allow_list_groups] Marked {len(allowed_recipients)} recipient(s) as allowed via contact group membership"
        )

    return allowed_recipients


def _maybe_append_feedback_blocks(
    email_spec: EmailSpec,
    email_id: Optional[str] = None,
) -> EmailSpec:
    """Append feedback blocks to an EmailSpec if email feedback is enabled.

    Checks ``ENABLE_EMAIL_FEEDBACK`` env var (default: ``false``).
    Uses ``settings.feedback_base_url`` for redirect URL generation —
    the same base URL that the card feedback system uses (``FEEDBACK_BASE_URL``
    env var, falling back to ``settings.base_url``).

    Args:
        email_spec: The email spec to augment.
        email_id: Unique identifier for the email (for URL signing).
            If None, a random ID is generated.

    Returns:
        The same EmailSpec with feedback blocks appended (if enabled),
        or unmodified if disabled.
    """
    import os

    if os.getenv("ENABLE_EMAIL_FEEDBACK", "false").lower() != "true":
        return email_spec

    # Reuse the same feedback_base_url as card feedback
    # (FEEDBACK_BASE_URL env var → settings.base_url fallback)
    base_url = settings.feedback_base_url
    if not base_url:
        logger.debug("No feedback_base_url configured; skipping feedback blocks")
        return email_spec

    if not email_id:
        import secrets

        email_id = secrets.token_urlsafe(16)

    try:
        from gmail.email_feedback.dynamic import get_email_feedback_builder

        builder = get_email_feedback_builder()
        feedback_blocks = builder.build_feedback_blocks(
            email_id=email_id,
            base_url=base_url,
            feedback_type="content",
            layout="with_divider",
        )
        email_spec.blocks.extend(feedback_blocks)
    except Exception as e:
        logger.warning(f"Could not add email feedback blocks: {e}")

    return email_spec


def _render_email_spec(
    email_spec: Union[dict, EmailSpec],
    email_id: Optional[str] = None,
) -> tuple:
    """Render an EmailSpec to (subject, html_body).

    Optionally appends feedback blocks if ``ENABLE_EMAIL_FEEDBACK=true``.

    Args:
        email_spec: EmailSpec object or dict with EmailSpec fields
        email_id: Optional email ID for feedback URL signing.

    Returns:
        (subject, html_body) tuple

    Raises:
        ValueError: If rendering fails
    """
    if isinstance(email_spec, dict):
        email_spec = EmailSpec(**email_spec)

    # Optionally append feedback blocks before rendering
    email_spec = _maybe_append_feedback_blocks(email_spec, email_id)

    result = email_spec.render()
    if not result.success:
        diag_msgs = "; ".join(d.message for d in result.diagnostics)
        raise ValueError(f"EmailSpec rendering failed: {diag_msgs}")

    return email_spec.subject, result.html


# =============================================================================
# DSL → EmailSpec builder
# =============================================================================

# Class name → block_type literal mapping (used by _build_email_spec_from_dsl)
_CLASS_TO_BLOCK_TYPE = {
    "HeroBlock": "hero",
    "TextBlock": "text",
    "ButtonBlock": "button",
    "ImageBlock": "image",
    "ColumnsBlock": "columns",
    "SpacerBlock": "spacer",
    "DividerBlock": "divider",
    "FooterBlock": "footer",
    "HeaderBlock": "header",
    "SocialBlock": "social",
    "TableBlock": "table",
    "AccordionBlock": "accordion",
    "CarouselBlock": "carousel",
}


def _build_email_spec_from_dsl(
    parse_result,
    email_params: Optional[dict],
    description: str,
) -> EmailSpec:
    """Convert parsed DSL + params into an EmailSpec.

    Walks parse_result.root_nodes and maps each component to a block instance
    using email_params for content. Supports symbol-keyed _shared/_items merging.

    Args:
        parse_result: DSLParseResult from parse_email_dsl()
        email_params: Block content keyed by symbol, class name, or block_type
        description: Natural language description (used as fallback subject)

    Returns:
        EmailSpec ready for rendering
    """
    from gmail.mjml_types import _BLOCK_TYPE_MAP
    from gmail.mjml_types import Column as EmailColumn

    email_params = email_params or {}

    # Build reverse lookup: symbol → class name (for symbol-keyed params)
    from gmail.email_wrapper_api import get_email_symbols

    symbols = get_email_symbols()
    reverse_symbols = {v: k for k, v in symbols.items()}

    # Normalize email_params keys → class name
    normalized_params: dict = {}
    for key, value in email_params.items():
        if key in reverse_symbols:
            # Symbol key → class name
            normalized_params[reverse_symbols[key]] = value
        elif key in _CLASS_TO_BLOCK_TYPE:
            # Already a class name
            normalized_params[key] = value
        elif key in _BLOCK_TYPE_MAP:
            # block_type literal → class name
            cls = _BLOCK_TYPE_MAP[key]
            normalized_params[cls.__name__] = value
        else:
            # Pass through (e.g. "subject", "preheader")
            normalized_params[key] = value

    # Track consumption index per class for _items lists
    item_indices: dict = {}

    def _get_item_for_class(class_name: str) -> Optional[dict]:
        """Get next item from _items list for the given class, with _shared merging."""
        params_entry = normalized_params.get(class_name)
        if params_entry is None:
            return None

        if isinstance(params_entry, dict):
            shared = params_entry.get("_shared", {})
            items = params_entry.get("_items")
            if items and isinstance(items, list):
                idx = item_indices.get(class_name, 0)
                if idx < len(items):
                    item_indices[class_name] = idx + 1
                    merged = {**shared, **items[idx]}
                    return merged
                return {**shared} if shared else None
            else:
                # Single dict without _items — use directly (consumed once)
                if class_name not in item_indices:
                    item_indices[class_name] = 1
                    return params_entry
                return None
        return None

    def _build_block(node, depth: int = 0):
        """Recursively build a block from a DSLNode."""
        class_name = node.component_name
        block_type_str = _CLASS_TO_BLOCK_TYPE.get(class_name)

        if class_name == "EmailSpec":
            # Top-level: recurse into children
            blocks = []
            for child in node.children:
                for _ in range(child.multiplier):
                    block = _build_block(child, depth + 1)
                    if block is not None:
                        blocks.append(block)
            return blocks

        if class_name == "ColumnsBlock":
            # Children should be Column nodes
            columns = []
            for child in node.children:
                for _ in range(child.multiplier):
                    col = _build_block(child, depth + 1)
                    if col is not None:
                        columns.append(col)
            return _BLOCK_TYPE_MAP["columns"](columns=columns)

        if class_name == "Column":
            # Column children are content blocks
            col_blocks = []
            for child in node.children:
                for _ in range(child.multiplier):
                    block = _build_block(child, depth + 1)
                    if block is not None:
                        col_blocks.append(block)
            item_data = _get_item_for_class("Column") or {}
            # When DSL has no child nodes (e.g. ©x2), pull blocks from params
            if not col_blocks and "blocks" in item_data:
                col_blocks = item_data.pop("blocks")
            return EmailColumn(
                blocks=col_blocks,
                width=item_data.get("width"),
                padding=item_data.get("padding", "0"),
            )

        # Leaf block — get params from email_params
        if block_type_str is None:
            logger.warning(f"Unknown block class: {class_name}")
            return None

        block_cls = _BLOCK_TYPE_MAP.get(block_type_str)
        if block_cls is None:
            return None

        item_data = _get_item_for_class(class_name)
        if item_data:
            # Ensure block_type is set
            item_data.setdefault("block_type", block_type_str)
            try:
                return block_cls(**item_data)
            except Exception as e:
                logger.warning(f"Failed to build {class_name} from params: {e}")

        # Fallback: create with minimal defaults for blocks that need them
        if class_name in ("SpacerBlock", "DividerBlock"):
            return block_cls()
        if class_name == "TextBlock":
            return block_cls(text="")
        if class_name == "HeroBlock":
            return block_cls(title="")
        if class_name == "ButtonBlock":
            return block_cls(text="", url="#")

        return None

    # Walk root nodes to build blocks
    all_blocks = []
    for root in parse_result.root_nodes:
        for _ in range(root.multiplier):
            result = _build_block(root)
            if isinstance(result, list):
                all_blocks.extend(result)
            elif result is not None:
                all_blocks.append(result)

    # Determine subject
    subject = normalized_params.get("subject", "")
    if not subject:
        # Strip DSL from description to get NL part
        from gmail.email_wrapper_api import extract_email_dsl_from_description

        dsl_part = extract_email_dsl_from_description(description)
        if dsl_part:
            subject = description.replace(dsl_part, "").strip()
        else:
            subject = description.strip()
    if not subject:
        subject = "Email"

    # Guard: if subject is unreasonably long, the caller likely put block
    # content into email_description instead of email_params.  Truncate to
    # the first sentence / 120 chars to keep a usable subject line.
    if len(subject) > 120:
        # Try to find a natural break point (period, dash separator, colon)
        for sep in [". ", " - ", ": ", "; "]:
            idx = subject.find(sep)
            if 0 < idx <= 120:
                subject = subject[:idx].strip()
                break
        else:
            subject = subject[:120].rstrip()
        logger.warning(
            "[compose_dynamic_email] Subject was truncated — block content "
            "should go in email_params, not email_description"
        )

    # Strip leading punctuation/whitespace that can result from DSL removal
    subject = subject.lstrip("-–—:;, ").strip()
    if not subject:
        subject = "Email"

    preheader = normalized_params.get("preheader")

    return EmailSpec(
        subject=subject,
        preheader=preheader,
        blocks=all_blocks,
    )


async def _handle_elicitation_fallback(
    fallback_mode: str,
    to: Union[str, List[str]],
    subject: str,
    body: str,
    user_google_email: UserGoogleEmail,
    content_type: str,
    html_body: Optional[str],
    cc: Optional[Union[str, List[str]]],
    bcc: Optional[Union[str, List[str]]],
    recipients_not_allowed: List[str],
) -> Optional[SendGmailMessageResponse]:
    """
    Handle elicitation fallback when client doesn't support elicitation.

    Args:
        fallback_mode: "block", "allow", or "draft"
        Other args: Same as send_gmail_message
        recipients_not_allowed: List of recipients not on allow list

    Returns:
        Optional[SendGmailMessageResponse]: Result based on fallback mode, or None to continue sending
    """
    if fallback_mode == "allow":
        # Proceed with sending (allow untrusted recipients)
        logger.info(
            "Fallback mode 'allow' - proceeding with send despite untrusted recipients"
        )
        return None  # Return None to continue with normal send flow

    elif fallback_mode == "draft":
        # Save as draft instead of sending
        logger.info(
            "Fallback mode 'draft' - saving as draft due to untrusted recipients"
        )
        draft_result = await draft_gmail_message(
            subject=subject,
            body=body,
            user_google_email=user_google_email,
            to=to,
            content_type=content_type,
            html_body=html_body,
            cc=cc,
            bcc=bcc,
        )
        return SendGmailMessageResponse(
            success=True,
            message=f"""📝 **EMAIL SAVED AS DRAFT** (not sent)

✅ **Action:** Saved to Gmail Drafts folder
📧 **Draft ID:** {draft_result["draft_id"]}
📬 **Recipients:** {draft_result["recipient_count"]} (not notified)

⚠️ **Why draft:** Recipients not on allow list: {", ".join(recipients_not_allowed)}
📱 **Cause:** Your MCP client doesn't support elicitation

🔧 **Next steps:**
   • Review draft in Gmail and send manually
   • OR add recipients to allow list for auto-sending""",
            messageId=None,
            threadId=None,
            draftId=draft_result["draft_id"],
            recipientCount=draft_result["recipient_count"],
            contentType=content_type,
            templateApplied=False,
            error=None,
            elicitationRequired=False,
            elicitationNotSupported=True,
            action="saved_draft",
        )
    else:  # fallback_mode == "block" (default)
        # Block the send and inform user
        logger.info("Fallback mode 'block' - blocking send due to untrusted recipients")
        return SendGmailMessageResponse(
            success=False,
            message=f"""🚫 **EMAIL BLOCKED** (not sent)

❌ **Action:** Send operation blocked for security
📧 **Subject:** {subject}
📬 **Recipients:** {to if isinstance(to, str) else ", ".join(to)} ({len(recipients_not_allowed)} not verified)

🚨 **Issue:** Recipients not on your allow list
📱 **Cause:** MCP client doesn't support interactive confirmation

🔧 **Solutions:**
   1. Add recipients to allow list: `add_to_gmail_allow_list`
   2. Save as draft instead: `draft_gmail_message`
   3. Set GMAIL_ELICITATION_FALLBACK=allow to send anyway
   4. Set GMAIL_ELICITATION_FALLBACK=draft to auto-save drafts

⚠️ **NO EMAIL SENT** - Review and take manual action""",
            messageId=None,
            threadId=None,
            recipientCount=0,
            contentType=content_type,
            templateApplied=False,
            error="Recipients not on allow list and elicitation not supported",
            elicitationRequired=True,
            elicitationNotSupported=True,
            recipientsNotAllowed=recipients_not_allowed,
        )


async def send_gmail_message(
    ctx: Context,
    subject: str,
    body: str,
    to: GmailRecipients = "myself",
    user_google_email: UserGoogleEmail = None,
    content_type: Literal["plain", "html", "mixed"] = "mixed",
    html_body: Optional[str] = None,
    cc: GmailRecipientsOptional = None,
    bcc: GmailRecipientsOptional = None,
    email_spec: Optional[Union[dict, EmailSpec]] = None,
) -> SendGmailMessageResponse:
    """
    Sends an email using the user's Gmail account with support for HTML formatting and multiple recipients.

    Features elicitation for recipients not on the allow list - if any recipient
    is not on the configured allow list, the tool will ask for confirmation
    before sending the email.

    Args:
        ctx: FastMCP context for elicitation support
        to: Recipient email address(es) - can be a single string or list of strings
        subject: Email subject
        body: Email body content. Usage depends on content_type:
            - content_type="plain": Contains plain text only
            - content_type="html": Contains HTML content (plain text auto-generated for Gmail)
            - content_type="mixed": Contains plain text (HTML goes in html_body parameter)
        user_google_email: The user's Google email address for Gmail access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware).
        content_type: Content type - controls how body and html_body are used:
            - "plain": Plain text email (backward compatible)
            - "html": HTML email - put HTML content in 'body' parameter
            - "mixed": Dual content - plain text in 'body', HTML in 'html_body' (default)
        html_body: HTML content when content_type="mixed". Ignored for other content types.
        cc: Optional CC recipient(s) - can be a single string or list of strings
        bcc: Optional BCC recipient(s) - can be a single string or list of strings
        email_spec: Optional EmailSpec (dict or object) for MJML-based responsive emails.
            When provided, renders to HTML and overrides content_type/body/html_body/subject.
            The EmailSpec subject is used unless subject is explicitly provided.

    Returns:
        str: Confirmation message with the sent email's message ID

    Examples:
        # Plain text (backward compatible)
        send_gmail_message(ctx, "user@example.com", "Subject", "Plain text body")

        # HTML email (HTML content goes in 'body' parameter)
        send_gmail_message(ctx, "user@example.com", "Subject", "<h1>HTML content</h1>", content_type="html")

        # Mixed content (separate plain and HTML versions)
        send_gmail_message(ctx, "user@example.com", "Subject", "Plain version",
                          content_type="mixed", html_body="<h1>HTML version</h1>")

        # EmailSpec (MJML-based responsive email)
        send_gmail_message(ctx, "user@example.com", "", "", email_spec={
            "subject": "Welcome!", "blocks": [{"type": "TextBlock", "text": "Hello!"}]
        })
    """
    # EmailSpec rendering — overrides content_type/body/html_body
    if email_spec is not None:
        try:
            spec_subject, rendered_html = _render_email_spec(email_spec)
            # Use spec subject unless caller explicitly provided one
            if not subject:
                subject = spec_subject
            # Switch to HTML mode with rendered content
            body = rendered_html
            content_type = "html"
            html_body = None
            logger.info(
                f"[send_gmail_message] EmailSpec rendered: subject='{subject}', "
                f"html_size={len(rendered_html)} bytes"
            )
        except (ValueError, Exception) as e:
            logger.error(f"[send_gmail_message] EmailSpec render failed: {e}")
            return SendGmailMessageResponse(
                success=False,
                message=f"EmailSpec rendering failed: {e}",
                messageId=None,
                threadId=None,
                recipientCount=0,
                contentType="html",
                templateApplied=False,
                error=f"EmailSpec render error: {e}",
            )

    # Parameter validation and helpful error messages
    if content_type == "html" and html_body and not body.strip().startswith("<"):
        error_msg = (
            "❌ **Parameter Usage Error for content_type='html'**\n\n"
            "When using content_type='html':\n"
            "• Put your HTML content in the 'body' parameter\n"
            "• The 'html_body' parameter is ignored\n\n"
            "**For your case, try one of these:**\n"
            "1. Use content_type='mixed' (uses both body and html_body)\n"
            "2. Put HTML in 'body' parameter and remove 'html_body'\n\n"
            "**Example:** body='<h1>Your HTML here</h1>', content_type='html'"
        )
        return SendGmailMessageResponse(
            success=False,
            message=error_msg,
            messageId=None,
            threadId=None,
            recipientCount=0,
            contentType=content_type,
            templateApplied=False,
            error="Parameter validation error: incorrect content_type usage",
        )

    if content_type == "mixed" and not html_body:
        error_msg = (
            "❌ **Missing HTML Content for content_type='mixed'**\n\n"
            "When using content_type='mixed', you must provide:\n"
            "• Plain text in 'body' parameter\n"
            "• HTML content in 'html_body' parameter"
        )
        return SendGmailMessageResponse(
            success=False,
            message=error_msg,
            messageId=None,
            threadId=None,
            recipientCount=0,
            contentType=content_type,
            templateApplied=False,
            error="Parameter validation error: missing html_body for mixed content",
        )

    # Format recipients for logging using shared utility function
    to_count = count_recipients(to)
    cc_count = count_recipients(cc) if cc else 0
    bcc_count = count_recipients(bcc) if bcc else 0

    to_str = to if isinstance(to, str) else f"{to_count} recipients"
    cc_str = (
        f", CC: {cc if isinstance(cc, str) else f'{cc_count} recipients'}" if cc else ""
    )
    bcc_str = (
        f", BCC: {bcc if isinstance(bcc, str) else f'{bcc_count} recipients'}"
        if bcc
        else ""
    )

    logger.info(
        f"[send_gmail_message] Sending to: {to_str}{cc_str}{bcc_str}, from: {user_google_email}, content_type: {content_type}"
    )

    # STEP 1: Resolve any group: or groupId: recipient specs to actual email addresses
    # This must happen BEFORE allow list checking so we check the actual recipients
    resolved_to = await _resolve_group_recipients(to, user_google_email)
    resolved_cc = await _resolve_group_recipients(cc, user_google_email)
    resolved_bcc = await _resolve_group_recipients(bcc, user_google_email)

    logger.debug(
        f"[send_gmail_message] After group resolution - to: {resolved_to}, cc: {resolved_cc}, bcc: {resolved_bcc}"
    )

    # STEP 2: Check allow list and trigger elicitation if needed
    allow_list = settings.get_gmail_allow_list()
    recipients_not_allowed: List[str] = []

    if allow_list:
        # Use consolidated helper to resolve aliases and perform email + group checks
        # Now using resolved recipients (groups expanded to emails)
        recipients_not_allowed = await _resolve_recipients_and_check_allow_list(
            resolved_to, resolved_cc, resolved_bcc, user_google_email, allow_list
        )

        if recipients_not_allowed:
            # Check if elicitation is enabled in settings
            if not settings.gmail_enable_elicitation:
                logger.info(
                    f"Elicitation disabled in settings - applying fallback: {settings.gmail_elicitation_fallback}"
                )
                fallback_result = await _handle_elicitation_fallback(
                    settings.gmail_elicitation_fallback,
                    resolved_to,
                    subject,
                    body,
                    user_google_email,
                    content_type,
                    html_body,
                    resolved_cc,
                    resolved_bcc,
                    recipients_not_allowed,
                )
                if fallback_result is not None:
                    return fallback_result

            # Log elicitation trigger
            logger.info(
                f"Elicitation triggered for {len(recipients_not_allowed)} recipient(s) not on allow list"
            )

            # Prepare elicitation message with better formatting
            to_display = (
                resolved_to if isinstance(resolved_to, str) else ", ".join(resolved_to)
            )
            cc_display = (
                f"\n📋 **CC:** {resolved_cc if isinstance(resolved_cc, str) else ', '.join(resolved_cc)}"
                if resolved_cc
                else ""
            )
            bcc_display = (
                f"\n📋 **BCC:** {resolved_bcc if isinstance(resolved_bcc, str) else ', '.join(resolved_bcc)}"
                if resolved_bcc
                else ""
            )

            # Truncate body for preview if too long
            body_preview = body[:300] + "... [truncated]" if len(body) > 300 else body

            elicitation_message = f"""📧 **Email Confirmation Required**

⏰ **Auto-timeout:** 300 seconds

📬 **Recipients:**
   • To: {to_display}{cc_display}{bcc_display}

📝 **Email Details:**
   • Subject: {subject}
   • Content Type: {content_type}

📄 **Body Preview:**
```
{body_preview}
```

🔒 **Security Notice:** This recipient is not on your allow list.

❓ **Choose your action:**
   • **Send** - Send the email immediately
   • **Save as Draft** - Save to drafts folder without sending
   • **Cancel** - Discard the email
   
⏰ Auto-cancels in 300 seconds if no response"""

            # Trigger elicitation with graceful fallback for unsupported clients
            try:
                # response = await ctx.elicit(
                #         message=elicitation_message,
                #         response_type=EmailAction
                #     )
                response = await asyncio.wait_for(
                    ctx.elicit(message=elicitation_message, response_type=EmailAction),
                    timeout=300.0,
                )
            except asyncio.TimeoutError:
                logger.info("Elicitation timed out after 300 seconds")
                return SendGmailMessageResponse(
                    success=False,
                    message="Email operation timed out - no response received within 300 seconds",
                    messageId=None,
                    threadId=None,
                    recipientCount=0,
                    contentType=content_type,
                    templateApplied=False,
                    error="Elicitation timeout",
                    elicitationRequired=True,
                    recipientsNotAllowed=recipients_not_allowed,
                )
            except Exception as elicit_error:
                # Enhanced client support detection - broader patterns to catch more unsupported clients
                error_msg = str(elicit_error).lower()
                error_type = type(elicit_error).__name__

                # Check for indicators that elicitation is not supported by the client
                # Using broader patterns to catch various client implementations
                is_unsupported_client = (
                    # Method/feature not found errors
                    "method not found" in error_msg
                    or "unknown method" in error_msg
                    or "unsupported method" in error_msg
                    or "not found" in error_msg  # Broader pattern
                    or "not supported" in error_msg  # Broader pattern
                    or "unsupported" in error_msg  # Broader pattern
                    or
                    # FastMCP/MCP-specific indicators
                    "elicit not supported" in error_msg
                    or "elicitation not supported" in error_msg
                    or "elicitation not available" in error_msg
                    or
                    # Exception types that commonly indicate missing functionality
                    error_type in ["AttributeError", "NotImplementedError", "TypeError"]
                    or
                    # Common client error patterns
                    "elicit" in error_msg
                    and ("error" in error_msg or "fail" in error_msg)
                )

                if is_unsupported_client:
                    logger.warning(
                        f"Client doesn't support elicitation (error: {error_type}: {error_msg}) - applying fallback: {settings.gmail_elicitation_fallback}"
                    )
                    fallback_result = await _handle_elicitation_fallback(
                        settings.gmail_elicitation_fallback,
                        resolved_to,
                        subject,
                        body,
                        user_google_email,
                        content_type,
                        html_body,
                        resolved_cc,
                        resolved_bcc,
                        recipients_not_allowed,
                    )
                    if fallback_result is not None:
                        return fallback_result
                    # If fallback_result is None (allow mode), continue with normal sending
                else:
                    # Very specific errors that indicate client should support elicitation
                    logger.error(
                        f"Elicitation failed for supporting client: {error_type}: {elicit_error}"
                    )
                    return SendGmailMessageResponse(
                        success=False,
                        message=f"❌ Email confirmation failed: {elicit_error}\n\n🔧 **Client appears to support elicitation but encountered an error**",
                        messageId=None,
                        threadId=None,
                        recipientCount=0,
                        contentType=content_type,
                        templateApplied=False,
                        error=f"Elicitation error: {elicit_error}",
                        elicitationRequired=True,
                        recipientsNotAllowed=recipients_not_allowed,
                    )

            # Handle standard elicitation response structure
            if response.action == "decline" or response.action == "cancel":
                logger.info(f"User {response.action}d email operation")
                return SendGmailMessageResponse(
                    success=False,
                    message=f"""🚫 **EMAIL CANCELLED** (not sent)

❌ **Action:** User {response.action}d the send operation
📧 **Subject:** {subject}
📬 **Recipients:** No one notified

ℹ️ **User choice:** {response.action.title()} via elicitation prompt""",
                    messageId=None,
                    threadId=None,
                    recipientCount=0,
                    contentType=content_type,
                    templateApplied=False,
                    error=f"User {response.action}d",
                    elicitationRequired=True,
                    recipientsNotAllowed=recipients_not_allowed,
                )
            elif response.action == "accept":
                # Get the user's choice from the data field
                user_choice = response.data.action

                if user_choice == "cancel":
                    logger.info("User chose to cancel email operation")
                    return SendGmailMessageResponse(
                        success=False,
                        message=f"""🚫 **EMAIL CANCELLED** (not sent)

❌ **Action:** User chose to cancel
📧 **Subject:** {subject}
📬 **Recipients:** No one notified

ℹ️ **User choice:** Cancel via elicitation prompt""",
                        messageId=None,
                        threadId=None,
                        recipientCount=0,
                        contentType=content_type,
                        templateApplied=False,
                        error="User cancelled",
                        elicitationRequired=True,
                        recipientsNotAllowed=recipients_not_allowed,
                    )
                elif user_choice == "save_draft":
                    logger.info("User chose to save email as draft")
                    # Create draft instead of sending (use resolved recipients)
                    draft_result = await draft_gmail_message(
                        user_google_email=user_google_email,
                        subject=subject,
                        body=body,
                        to=resolved_to,
                        content_type=content_type,
                        html_body=html_body,
                        cc=resolved_cc,
                        bcc=resolved_bcc,
                    )
                    # Return as send response with draft info
                    return SendGmailMessageResponse(
                        success=True,
                        message=f"""📝 **EMAIL SAVED AS DRAFT** (not sent)

✅ **Action:** User chose to save as draft
📧 **Draft ID:** {draft_result["draft_id"]}
📬 **Recipients:** {draft_result["recipient_count"]} (not notified)

ℹ️ **User choice:** Save as draft via elicitation prompt
🔧 **Next step:** Review draft in Gmail and send manually""",
                        messageId=None,
                        threadId=None,
                        draftId=draft_result["draft_id"],  # Include draft ID
                        recipientCount=draft_result["recipient_count"],
                        contentType=content_type,
                        templateApplied=False,
                        error=None,
                        elicitationRequired=True,
                        recipientsNotAllowed=recipients_not_allowed,
                        action="saved_draft",
                    )
                elif user_choice == "send":
                    # Continue with sending
                    logger.info("User chose to send email")
                else:
                    # Unexpected choice
                    logger.error(f"Unexpected user choice: {user_choice}")
                    return SendGmailMessageResponse(
                        success=False,
                        message=f"Unexpected choice: {user_choice}",
                        messageId=None,
                        threadId=None,
                        recipientCount=0,
                        contentType=content_type,
                        templateApplied=False,
                        error=f"Unexpected choice: {user_choice}",
                        elicitationRequired=True,
                        recipientsNotAllowed=recipients_not_allowed,
                    )
            else:
                # Unexpected elicitation action
                logger.error(f"Unexpected elicitation action: {response.action}")
                return SendGmailMessageResponse(
                    success=False,
                    message=f"Unexpected elicitation response: {response.action}",
                    messageId=None,
                    threadId=None,
                    recipientCount=0,
                    contentType=content_type,
                    templateApplied=False,
                    error=f"Unexpected elicitation response: {response.action}",
                    elicitationRequired=True,
                    recipientsNotAllowed=recipients_not_allowed,
                )
        else:
            # All recipients are on allow list
            total_recipients = count_recipients(resolved_to, resolved_cc, resolved_bcc)
            logger.info(
                f"All {total_recipients} recipient(s) are on allow list - sending without elicitation"
            )
    else:
        # No allow list configured - still need to resolve groups
        logger.debug("No Gmail allow list configured - sending without elicitation")
        resolved_to = await _resolve_group_recipients(to, user_google_email)
        resolved_cc = await _resolve_group_recipients(cc, user_google_email)
        resolved_bcc = await _resolve_group_recipients(bcc, user_google_email)

    try:
        gmail_service = await _get_gmail_service_with_fallback(user_google_email)

        # STEP 3: Resolve 'me'/'myself' aliases in the already-group-resolved recipients
        # The Gmail API expects valid email addresses, not keywords
        final_to = _resolve_recipient_aliases(resolved_to, user_google_email)
        final_cc = _resolve_recipient_aliases(resolved_cc, user_google_email)
        final_bcc = _resolve_recipient_aliases(resolved_bcc, user_google_email)

        logger.debug(
            f"Final recipients after alias resolution - to: {final_to}, cc: {final_cc}, bcc: {final_bcc}"
        )

        # Check for email templates for recipients
        template_applied = False
        template = None
        final_body = body
        final_html_body = html_body
        final_content_type = content_type

        # Get primary recipient for template lookup
        primary_recipient = None
        if isinstance(final_to, str):
            # Handle comma-separated string
            recipients = [
                email.strip() for email in final_to.split(",") if email.strip()
            ]
            if recipients:
                primary_recipient = recipients[0]
        elif isinstance(final_to, list) and final_to:
            primary_recipient = final_to[0]

        # Create properly formatted MIME message using helper function
        raw_message = _create_mime_message(
            to=final_to,
            subject=subject,
            body=final_body,
            content_type=final_content_type,
            html_body=final_html_body,
            from_email=user_google_email,
            cc=final_cc,
            bcc=final_bcc,
        )

        send_body = {"raw": raw_message}

        # Send the message
        sent_message = await asyncio.to_thread(
            gmail_service.users().messages().send(userId="me", body=send_body).execute
        )
        message_id = sent_message.get("id")

        # Count total recipients for confirmation using shared utility function
        total_recipients = count_recipients(final_to, final_cc, final_bcc)

        # Get thread ID from the sent message
        thread_id = sent_message.get("threadId")

        return SendGmailMessageResponse(
            success=True,
            message=f"✅ Email sent to {total_recipients} recipient(s)! Message ID: {message_id}",
            messageId=message_id,
            threadId=thread_id,
            recipientCount=total_recipients,
            contentType=final_content_type,
            templateApplied=template_applied,
            templateName=template.name if template_applied and template else None,
            error=None,
            elicitationRequired=bool(recipients_not_allowed) if allow_list else False,
            recipientsNotAllowed=recipients_not_allowed if allow_list else [],
        )

    except HttpError as e:
        logger.error(f"Gmail API error in send_gmail_message: {e}")
        return SendGmailMessageResponse(
            success=False,
            message=f"❌ Gmail API error: {e}",
            messageId=None,
            threadId=None,
            recipientCount=0,
            contentType=content_type,
            templateApplied=False,
            error=str(e),
        )

    except Exception as e:
        logger.error(f"Unexpected error in send_gmail_message: {e}")
        return SendGmailMessageResponse(
            success=False,
            message=f"❌ Unexpected error: {e}",
            messageId=None,
            threadId=None,
            recipientCount=0,
            contentType=content_type,
            templateApplied=False,
            error=str(e),
        )


async def draft_gmail_message(
    subject: str,
    body: str,
    user_google_email: UserGoogleEmail = None,
    to: GmailRecipientsOptional = None,
    content_type: Literal["plain", "html", "mixed"] = "mixed",
    html_body: Optional[str] = None,
    cc: GmailRecipientsOptional = None,
    bcc: GmailRecipientsOptional = None,
    email_spec: Optional[Union[dict, EmailSpec]] = None,
) -> DraftGmailMessageResponse:
    """
    Creates a draft email in the user's Gmail account with support for HTML formatting and multiple recipients.

    Args:
        subject: Email subject
        body: Email body content. Usage depends on content_type:
            - content_type="plain": Contains plain text only
            - content_type="html": Contains HTML content (plain text auto-generated for Gmail)
            - content_type="mixed": Contains plain text (HTML goes in html_body parameter)
        user_google_email: The user's Google email address for Gmail access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware).
        to: Optional recipient email address(es) - can be a single string, list of strings, or None for drafts
        content_type: Content type - controls how body and html_body are used:
            - "plain": Plain text draft (backward compatible)
            - "html": HTML draft - put HTML content in 'body' parameter
            - "mixed": Dual content - plain text in 'body', HTML in 'html_body' (default)
        html_body: HTML content when content_type="mixed". Ignored for other content types.
        cc: Optional CC recipient(s) - can be a single string or list of strings
        bcc: Optional BCC recipient(s) - can be a single string or list of strings
        email_spec: Optional EmailSpec (dict or object) for MJML-based responsive emails.

    Returns:
        str: Confirmation message with the created draft's ID

    Examples:
        # Plain text draft
        draft_gmail_message("Subject", "Plain text body")

        # HTML draft (HTML content goes in 'body' parameter)
        draft_gmail_message("Subject", "<h1>HTML content</h1>", content_type="html")

        # Mixed content draft
        draft_gmail_message("Subject", "Plain version",
                          content_type="mixed", html_body="<h1>HTML version</h1>")

        # Auto-injected user (middleware handles user_google_email)
        draft_gmail_message("Subject", "Body content")
    """
    # EmailSpec rendering — overrides content_type/body/html_body
    if email_spec is not None:
        try:
            spec_subject, rendered_html = _render_email_spec(email_spec)
            if not subject:
                subject = spec_subject
            body = rendered_html
            content_type = "html"
            html_body = None
            logger.info(
                f"[draft_gmail_message] EmailSpec rendered: subject='{subject}', "
                f"html_size={len(rendered_html)} bytes"
            )
        except (ValueError, Exception) as e:
            logger.error(f"[draft_gmail_message] EmailSpec render failed: {e}")
            return DraftGmailMessageResponse(
                success=False,
                subject=subject,
                content_type="html",
                has_recipients=bool(to),
                recipient_count=0,
                userEmail=user_google_email or "",
                error=f"EmailSpec render error: {e}",
            )

    # Parameter validation and helpful error messages (same as send_gmail_message)
    if content_type == "html" and html_body and not body.strip().startswith("<"):
        error_msg = (
            "❌ **Parameter Usage Error for content_type='html'**\n\n"
            "When using content_type='html':\n"
            "• Put your HTML content in the 'body' parameter\n"
            "• The 'html_body' parameter is ignored\n\n"
            "**For your case, try one of these:**\n"
            "1. Use content_type='mixed' (uses both body and html_body)\n"
            "2. Put HTML in 'body' parameter and remove 'html_body'\n\n"
            "**Example:** body='<h1>Your HTML here</h1>', content_type='html'"
        )
        return DraftGmailMessageResponse(
            success=False,
            draft_id="",
            subject=subject,
            content_type=content_type,
            has_recipients=bool(to),
            recipient_count=0,
            userEmail=user_google_email or "",
            error="Parameter validation error: incorrect content_type usage",
        )

    if content_type == "mixed" and not html_body:
        error_msg = (
            "❌ **Missing HTML Content for content_type='mixed'**\n\n"
            "When using content_type='mixed', you must provide:\n"
            "• Plain text in 'body' parameter\n"
            "• HTML content in 'html_body' parameter"
        )
        return DraftGmailMessageResponse(
            success=False,
            subject=subject,
            content_type=content_type,
            has_recipients=bool(to),
            recipient_count=0,
            userEmail=user_google_email or "",
            error="Parameter validation error: missing html_body for mixed content",
        )

    # Format recipients for logging using shared utility function
    to_count = count_recipients(to) if to else 0
    cc_count = count_recipients(cc) if cc else 0
    bcc_count = count_recipients(bcc) if bcc else 0

    to_str = (
        "no recipients"
        if not to
        else (to if isinstance(to, str) else f"{to_count} recipients")
    )
    cc_str = (
        f", CC: {cc if isinstance(cc, str) else f'{cc_count} recipients'}" if cc else ""
    )
    bcc_str = (
        f", BCC: {bcc if isinstance(bcc, str) else f'{bcc_count} recipients'}"
        if bcc
        else ""
    )

    logger.info(
        f"[draft_gmail_message] Email: '{user_google_email}', Subject: '{subject}', To: {to_str}{cc_str}{bcc_str}, content_type: {content_type}"
    )

    try:
        gmail_service = await _get_gmail_service_with_fallback(user_google_email)

        # CRITICAL FIX: Resolve 'me'/'myself' aliases BEFORE creating MIME message
        resolved_to = _resolve_recipient_aliases(to, user_google_email) if to else ""
        resolved_cc = _resolve_recipient_aliases(cc, user_google_email)
        resolved_bcc = _resolve_recipient_aliases(bcc, user_google_email)

        logger.debug(
            f"[draft] Resolved recipients - to: {resolved_to}, cc: {resolved_cc}, bcc: {resolved_bcc}"
        )

        # Create properly formatted MIME message using helper function
        raw_message = _create_mime_message(
            to=resolved_to,
            subject=subject,
            body=body,
            content_type=content_type,
            html_body=html_body,
            from_email=user_google_email,
            cc=resolved_cc,
            bcc=resolved_bcc,
        )

        # Create a draft instead of sending
        draft_body = {"message": {"raw": raw_message}}

        # Create the draft
        created_draft = await asyncio.to_thread(
            gmail_service.users().drafts().create(userId="me", body=draft_body).execute
        )
        draft_id = created_draft.get("id")

        # Count total recipients for confirmation using shared utility function
        total_recipients = count_recipients(resolved_to, resolved_cc, resolved_bcc)

        # Get message ID from the draft
        message_id = created_draft.get("message", {}).get("id")
        thread_id = created_draft.get("message", {}).get("threadId")

        return DraftGmailMessageResponse(
            success=True,
            draft_id=draft_id,
            subject=subject,
            content_type=content_type,
            has_recipients=bool(to),
            recipient_count=total_recipients,
            userEmail=user_google_email or "",
            error=None,
        )

    except Exception as e:
        logger.error(f"Unexpected error in draft_gmail_message: {e}")
        return DraftGmailMessageResponse(
            success=False,
            draft_id="",
            subject=subject,
            content_type=content_type,
            has_recipients=bool(to),
            recipient_count=0,
            userEmail=user_google_email or "",
            error=str(e),
        )


async def reply_to_gmail_message(
    message_id: str,
    body: str,
    user_google_email: UserGoogleEmail = None,
    reply_mode: Literal["sender_only", "reply_all", "custom"] = "sender_only",
    to: GmailRecipientsOptional = None,
    cc: GmailRecipientsOptional = None,
    bcc: GmailRecipientsOptional = None,
    content_type: Literal["plain", "html", "mixed"] = "mixed",
    html_body: Optional[str] = None,
) -> ReplyGmailMessageResponse:
    """
    Sends a reply to a specific Gmail message with support for HTML formatting and flexible recipient options.

    Args:
        message_id: The ID of the message to reply to
        body: Reply body content. Usage depends on content_type:
            - content_type="plain": Contains plain text only
            - content_type="html": Contains HTML content (plain text auto-generated for Gmail)
            - content_type="mixed": Contains plain text (HTML goes in html_body parameter)
        user_google_email: The user's Google email address for Gmail access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware).
        reply_mode: Controls who receives the reply:
            - "sender_only": Reply only to the original sender (default, backward compatible)
            - "reply_all": Reply to all original recipients (sender + all To/CC recipients)
            - "custom": Use the provided to/cc/bcc parameters (must provide at least 'to')
        to: Optional recipient(s) when reply_mode="custom" - can be a single string or list of strings
        cc: Optional CC recipient(s) when reply_mode="custom" - can be a single string or list of strings
        bcc: Optional BCC recipient(s) when reply_mode="custom" - can be a single string or list of strings
        content_type: Content type - controls how body and html_body are used:
            - "plain": Plain text reply (backward compatible)
            - "html": HTML reply - put HTML content in 'body' parameter
            - "mixed": Dual content - plain text in 'body', HTML in 'html_body' (default)
        html_body: HTML content when content_type="mixed". Ignored for other content types.

    Returns:
        ReplyGmailMessageResponse: Structured response with reply details

    Examples:
        # Traditional reply to sender only (backward compatible)
        reply_to_gmail_message("msg_123", "Thanks for your message!")

        # Reply to all recipients
        reply_to_gmail_message("msg_123", "Thanks everyone!", reply_mode="reply_all")

        # Custom recipients
        reply_to_gmail_message("msg_123", "Forwarding to team",
                              reply_mode="custom", to=["team@example.com"], cc=["manager@example.com"])

        # HTML reply with reply all
        reply_to_gmail_message("msg_123", "<p>Thanks <b>everyone</b>!</p>",
                              content_type="html", reply_mode="reply_all")
    """
    logger.info(
        f"[reply_to_gmail_message] Email: '{user_google_email}', Replying to Message ID: '{message_id}', reply_mode: {reply_mode}, content_type: {content_type}"
    )

    try:
        gmail_service = await _get_gmail_service_with_fallback(user_google_email)

        # Fetch the original message to get headers and body for quoting
        original_message = await asyncio.to_thread(
            gmail_service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute
        )
        payload = original_message.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
        original_subject = headers.get("Subject", "(no subject)")
        original_from = headers.get("From", "(unknown sender)")
        original_to = headers.get("To", "")
        original_cc = headers.get("Cc", "")
        original_body = _extract_message_body(payload)

        # Determine recipients based on reply_mode
        if reply_mode == "sender_only":
            # Current behavior - reply only to sender
            final_to = original_from
            final_cc = None
            final_bcc = None

        elif reply_mode == "reply_all":
            # Extract all original recipients
            from_emails = extract_email_addresses(original_from)
            to_emails = extract_email_addresses(original_to)
            cc_emails = extract_email_addresses(original_cc)

            # Remove current user's email from the lists (case-insensitive)
            if user_google_email:
                user_email_lower = user_google_email.lower()
                to_emails = [e for e in to_emails if e.lower() != user_email_lower]
                cc_emails = [e for e in cc_emails if e.lower() != user_email_lower]
                # Also remove from from_emails in case user is replying to their own message
                from_emails = [e for e in from_emails if e.lower() != user_email_lower]

            # Combine recipients appropriately
            # Original sender goes to 'To' field along with original To recipients
            # Original CC recipients stay in 'CC' field
            all_to_recipients = []
            if from_emails:
                all_to_recipients.extend(from_emails)
            if to_emails:
                all_to_recipients.extend(to_emails)

            # Remove duplicates while preserving order
            seen = set()
            final_to = []
            for email in all_to_recipients:
                if email.lower() not in seen:
                    seen.add(email.lower())
                    final_to.append(email)

            # If no recipients left (e.g., replying to own message), use original from
            if not final_to:
                final_to = original_from

            final_cc = cc_emails if cc_emails else None
            final_bcc = None

        elif reply_mode == "custom":
            # Use provided recipients
            if not to:
                raise ValueError(
                    "When using reply_mode='custom', you must provide 'to' recipients"
                )
            final_to = to
            final_cc = cc
            final_bcc = bcc

        else:
            raise ValueError(f"Invalid reply_mode: {reply_mode}")

        reply_subject = _prepare_reply_subject(original_subject)
        quoted_body = _quote_original_message(original_body)

        # Compose the reply message body based on content type
        if content_type == "html":
            # For HTML content, create HTML version with quoting
            full_body = f"{body}<br><br>On {html.escape(original_from)} wrote:<br><blockquote style='margin-left: 20px; padding-left: 10px; border-left: 2px solid #ccc;'>{html.escape(original_body).replace(chr(10), '<br>')}</blockquote>"
        elif content_type == "mixed":
            # Use provided HTML and plain text bodies
            if not html_body:
                raise ValueError("html_body is required when content_type is 'mixed'")
            plain_full_body = f"{body}\n\nOn {original_from} wrote:\n{quoted_body}"
            html_full_body = f"{html_body}<br><br>On {html.escape(original_from)} wrote:<br><blockquote style='margin-left: 20px; padding-left: 10px; border-left: 2px solid #ccc;'>{html.escape(original_body).replace(chr(10), '<br>')}</blockquote>"
            full_body = plain_full_body  # For the main body parameter
        else:  # plain
            full_body = f"{body}\n\nOn {original_from} wrote:\n{quoted_body}"

        # Create properly formatted MIME message using helper function
        raw_message = _create_mime_message(
            to=final_to,
            cc=final_cc,
            bcc=final_bcc,
            subject=reply_subject,
            body=full_body,
            content_type=content_type,
            html_body=html_full_body if content_type == "mixed" else None,
            from_email=user_google_email,
            reply_to_message_id=headers.get("Message-ID", ""),
            thread_id=original_message.get("threadId"),
        )

        send_body = {"raw": raw_message, "threadId": original_message.get("threadId")}

        # Send the reply message
        sent_message = await asyncio.to_thread(
            gmail_service.users().messages().send(userId="me", body=send_body).execute
        )
        sent_message_id = sent_message.get("id")
        thread_id = sent_message.get("threadId")

        # Format recipients for response
        def format_recipient_string(recipients):
            if not recipients:
                return ""
            if isinstance(recipients, str):
                return recipients
            elif isinstance(recipients, list):
                return ", ".join(recipients)
            return ""

        replied_to_str = format_recipient_string(final_to)

        return ReplyGmailMessageResponse(
            success=True,
            reply_message_id=sent_message_id,
            original_message_id=message_id,
            thread_id=thread_id or "",
            replied_to=replied_to_str,
            subject=reply_subject,
            content_type=content_type,
            reply_mode=reply_mode,
            to_recipients=(
                final_to
                if isinstance(final_to, list)
                else [final_to]
                if final_to
                else []
            ),
            cc_recipients=(
                final_cc
                if isinstance(final_cc, list)
                else [final_cc]
                if final_cc
                else []
            ),
            bcc_recipients=(
                final_bcc
                if isinstance(final_bcc, list)
                else [final_bcc]
                if final_bcc
                else []
            ),
            userEmail=user_google_email or "",
            error=None,
        )

    except Exception as e:
        logger.error(f"Unexpected error in reply_to_gmail_message: {e}")
        return ReplyGmailMessageResponse(
            success=False,
            reply_message_id="",
            original_message_id=message_id,
            thread_id="",
            replied_to="",
            subject="",
            content_type=content_type,
            reply_mode=reply_mode,
            to_recipients=[],
            cc_recipients=[],
            bcc_recipients=[],
            userEmail=user_google_email or "",
            error=str(e),
        )


async def draft_gmail_reply(
    message_id: str,
    body: str,
    user_google_email: UserGoogleEmail = None,
    reply_mode: Literal["sender_only", "reply_all", "custom"] = "sender_only",
    to: GmailRecipientsOptional = None,
    cc: GmailRecipientsOptional = None,
    bcc: GmailRecipientsOptional = None,
    content_type: Literal["plain", "html", "mixed"] = "mixed",
    html_body: Optional[str] = None,
) -> DraftGmailReplyResponse:
    """
    Creates a draft reply to a specific Gmail message with support for HTML formatting and flexible recipient options.

    Args:
        message_id: The ID of the message to draft a reply for
        body: Reply body content. Usage depends on content_type:
            - content_type="plain": Contains plain text only
            - content_type="html": Contains HTML content (plain text auto-generated for Gmail)
            - content_type="mixed": Contains plain text (HTML goes in html_body parameter)
        user_google_email: The user's Google email address for Gmail access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware).
        reply_mode: Controls who receives the reply:
            - "sender_only": Reply only to the original sender (default, backward compatible)
            - "reply_all": Reply to all original recipients (sender + all To/CC recipients)
            - "custom": Use the provided to/cc/bcc parameters (must provide at least 'to')
        to: Optional recipient(s) when reply_mode="custom" - can be a single string or list of strings
        cc: Optional CC recipient(s) when reply_mode="custom" - can be a single string or list of strings
        bcc: Optional BCC recipient(s) when reply_mode="custom" - can be a single string or list of strings
        content_type: Content type - controls how body and html_body are used:
            - "plain": Plain text draft reply (backward compatible)
            - "html": HTML draft reply - put HTML content in 'body' parameter
            - "mixed": Dual content - plain text in 'body', HTML in 'html_body' (default)
        html_body: HTML content when content_type="mixed". Ignored for other content types.

    Returns:
        DraftGmailReplyResponse: Structured response with draft creation details

    Examples:
        # Traditional draft reply to sender only (backward compatible)
        draft_gmail_reply("msg_123", "Thanks for your message!")

        # Draft reply to all recipients
        draft_gmail_reply("msg_123", "Thanks everyone!", reply_mode="reply_all")

        # Custom recipients draft
        draft_gmail_reply("msg_123", "Forwarding to team",
                         reply_mode="custom", to=["team@example.com"], cc=["manager@example.com"])

        # HTML draft reply with reply all
        draft_gmail_reply("msg_123", "<p>Thanks <b>everyone</b>!</p>",
                         content_type="html", reply_mode="reply_all")
    """
    logger.info(
        f"[draft_gmail_reply] Email: '{user_google_email}', Drafting reply to Message ID: '{message_id}', reply_mode: {reply_mode}, content_type: {content_type}"
    )

    try:
        gmail_service = await _get_gmail_service_with_fallback(user_google_email)

        # Fetch the original message to get headers and body for quoting
        original_message = await asyncio.to_thread(
            gmail_service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute
        )
        payload = original_message.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
        original_subject = headers.get("Subject", "(no subject)")
        original_from = headers.get("From", "(unknown sender)")
        original_to = headers.get("To", "")
        original_cc = headers.get("Cc", "")
        original_body = _extract_message_body(payload)

        # Determine recipients based on reply_mode
        if reply_mode == "sender_only":
            # Current behavior - reply only to sender
            final_to = original_from
            final_cc = None
            final_bcc = None

        elif reply_mode == "reply_all":
            # Extract all original recipients
            from_emails = extract_email_addresses(original_from)
            to_emails = extract_email_addresses(original_to)
            cc_emails = extract_email_addresses(original_cc)

            # Remove current user's email from the lists (case-insensitive)
            if user_google_email:
                user_email_lower = user_google_email.lower()
                to_emails = [e for e in to_emails if e.lower() != user_email_lower]
                cc_emails = [e for e in cc_emails if e.lower() != user_email_lower]
                # Also remove from from_emails in case user is replying to their own message
                from_emails = [e for e in from_emails if e.lower() != user_email_lower]

            # Combine recipients appropriately
            # Original sender goes to 'To' field along with original To recipients
            # Original CC recipients stay in 'CC' field
            all_to_recipients = []
            if from_emails:
                all_to_recipients.extend(from_emails)
            if to_emails:
                all_to_recipients.extend(to_emails)

            # Remove duplicates while preserving order
            seen = set()
            final_to = []
            for email in all_to_recipients:
                if email.lower() not in seen:
                    seen.add(email.lower())
                    final_to.append(email)

            # If no recipients left (e.g., replying to own message), use original from
            if not final_to:
                final_to = original_from

            final_cc = cc_emails if cc_emails else None
            final_bcc = None

        elif reply_mode == "custom":
            # Use provided recipients
            if not to:
                raise ValueError(
                    "When using reply_mode='custom', you must provide 'to' recipients"
                )
            final_to = to
            final_cc = cc
            final_bcc = bcc

        else:
            raise ValueError(f"Invalid reply_mode: {reply_mode}")

        reply_subject = _prepare_reply_subject(original_subject)
        quoted_body = _quote_original_message(original_body)

        # Compose the reply message body based on content type
        if content_type == "html":
            # For HTML content, create HTML version with quoting
            full_body = f"{body}<br><br>On {html.escape(original_from)} wrote:<br><blockquote style='margin-left: 20px; padding-left: 10px; border-left: 2px solid #ccc;'>{html.escape(original_body).replace(chr(10), '<br>')}</blockquote>"
        elif content_type == "mixed":
            # Use provided HTML and plain text bodies
            if not html_body:
                raise ValueError("html_body is required when content_type is 'mixed'")
            plain_full_body = f"{body}\n\nOn {original_from} wrote:\n{quoted_body}"
            html_full_body = f"{html_body}<br><br>On {html.escape(original_from)} wrote:<br><blockquote style='margin-left: 20px; padding-left: 10px; border-left: 2px solid #ccc;'>{html.escape(original_body).replace(chr(10), '<br>')}</blockquote>"
            full_body = plain_full_body  # For the main body parameter
        else:  # plain
            full_body = f"{body}\n\nOn {original_from} wrote:\n{quoted_body}"

        # Create properly formatted MIME message using helper function
        raw_message = _create_mime_message(
            to=final_to,
            cc=final_cc,
            bcc=final_bcc,
            subject=reply_subject,
            body=full_body,
            content_type=content_type,
            html_body=html_full_body if content_type == "mixed" else None,
            from_email=user_google_email,
            reply_to_message_id=headers.get("Message-ID", ""),
            thread_id=original_message.get("threadId"),
        )

        draft_body = {
            "message": {
                "raw": raw_message,
                "threadId": original_message.get("threadId"),
            }
        }

        # Create the draft reply
        created_draft = await asyncio.to_thread(
            gmail_service.users().drafts().create(userId="me", body=draft_body).execute
        )
        draft_id = created_draft.get("id")
        message_id_from_draft = created_draft.get("message", {}).get("id")
        thread_id = created_draft.get("message", {}).get("threadId")

        # Format recipients for response
        def format_recipient_string(recipients):
            if not recipients:
                return ""
            if isinstance(recipients, str):
                return recipients
            elif isinstance(recipients, list):
                return ", ".join(recipients)
            return ""

        replied_to_str = format_recipient_string(final_to)

        return DraftGmailReplyResponse(
            success=True,
            draft_id=draft_id,
            original_message_id=message_id,
            thread_id=thread_id or "",
            replied_to=replied_to_str,
            subject=reply_subject,
            content_type=content_type,
            reply_mode=reply_mode,
            to_recipients=(
                final_to
                if isinstance(final_to, list)
                else [final_to]
                if final_to
                else []
            ),
            cc_recipients=(
                final_cc
                if isinstance(final_cc, list)
                else [final_cc]
                if final_cc
                else []
            ),
            bcc_recipients=(
                final_bcc
                if isinstance(final_bcc, list)
                else [final_bcc]
                if final_bcc
                else []
            ),
            userEmail=user_google_email or "",
            error=None,
        )

    except Exception as e:
        logger.error(f"Unexpected error in draft_gmail_reply: {e}")
        return DraftGmailReplyResponse(
            success=False,
            draft_id="",
            original_message_id=message_id,
            thread_id="",
            replied_to="",
            subject="",
            content_type=content_type,
            reply_mode=reply_mode,
            to_recipients=[],
            cc_recipients=[],
            bcc_recipients=[],
            userEmail=user_google_email or "",
            error=str(e),
        )


async def forward_gmail_message(
    ctx: Context,
    message_id: str,
    to: GmailRecipients = "myself",
    user_google_email: UserGoogleEmail = None,
    body: Optional[str] = None,
    content_type: Literal["plain", "html", "mixed"] = "mixed",
    html_body: Optional[str] = None,
    cc: GmailRecipientsOptional = None,
    bcc: GmailRecipientsOptional = None,
) -> ForwardGmailMessageResponse:
    """
    Forward a Gmail message to specified recipients with HTML formatting preservation and elicitation support.

    This function forwards an existing Gmail message while preserving the original HTML formatting
    as much as possible. It includes the original message headers (From, Date, Subject, To, Cc)
    and supports elicitation for recipients not on the allow list.

    Args:
        ctx: FastMCP context for elicitation support
        message_id: The ID of the message to forward
        to: Recipient email address(es) - can be a single string or list of strings
        user_google_email: The user's Google email address for Gmail access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware).
        body: Optional additional message body to add before the forwarded content. Usage depends on content_type:
            - content_type="plain": Contains plain text only
            - content_type="html": Contains HTML content
            - content_type="mixed": Contains plain text (HTML goes in html_body parameter)
        content_type: Content type - controls how body and html_body are used:
            - "plain": Plain text forward (original HTML converted to plain text)
            - "html": HTML forward - preserves original HTML formatting
            - "mixed": Dual content - plain text in 'body', HTML in 'html_body' (default, recommended)
        html_body: HTML content when content_type="mixed". Ignored for other content types.
        cc: Optional CC recipient(s) - can be a single string or list of strings
        bcc: Optional BCC recipient(s) - can be a single string or list of strings

    Returns:
        ForwardGmailMessageResponse: Structured response with forward details

    Examples:
        # Simple forward (preserves HTML)
        forward_gmail_message(ctx, "msg_123", "user@example.com")

        # Forward with additional message
        forward_gmail_message(ctx, "msg_123", "user@example.com",
                            body="Please review this email.",
                            content_type="mixed",
                            html_body="<p>Please review this email.</p>")

        # Forward to multiple recipients
        forward_gmail_message(ctx, "msg_123", ["user1@example.com", "user2@example.com"],
                            cc="manager@example.com")
    """
    # Format recipients for logging using shared utility function
    to_count = count_recipients(to)
    cc_count = count_recipients(cc) if cc else 0
    bcc_count = count_recipients(bcc) if bcc else 0

    to_str = to if isinstance(to, str) else f"{to_count} recipients"
    cc_str = (
        f", CC: {cc if isinstance(cc, str) else f'{cc_count} recipients'}" if cc else ""
    )
    bcc_str = (
        f", BCC: {bcc if isinstance(bcc, str) else f'{bcc_count} recipients'}"
        if bcc
        else ""
    )

    logger.info(
        f"[forward_gmail_message] Email: '{user_google_email}', Forwarding Message ID: '{message_id}', To: {to_str}{cc_str}{bcc_str}, content_type: {content_type}"
    )

    # STEP 1: Resolve any group: or groupId: recipient specs to actual email addresses
    resolved_to = await _resolve_group_recipients(to, user_google_email)
    resolved_cc = await _resolve_group_recipients(cc, user_google_email)
    resolved_bcc = await _resolve_group_recipients(bcc, user_google_email)

    logger.debug(
        f"[forward_gmail_message] After group resolution - to: {resolved_to}, cc: {resolved_cc}, bcc: {resolved_bcc}"
    )

    # STEP 2: Check allow list and trigger elicitation if needed (same pattern as send_gmail_message)
    allow_list = settings.get_gmail_allow_list()

    if allow_list:
        # Use consolidated function to resolve recipients and check allow list
        recipients_not_allowed = await _resolve_recipients_and_check_allow_list(
            resolved_to, resolved_cc, resolved_bcc, user_google_email, allow_list
        )

        if recipients_not_allowed:
            # Check if elicitation is enabled in settings
            if not settings.gmail_enable_elicitation:
                logger.info(
                    f"Elicitation disabled in settings - applying fallback: {settings.gmail_elicitation_fallback}"
                )
                fallback_result = await _handle_elicitation_fallback(
                    settings.gmail_elicitation_fallback,
                    resolved_to,
                    "Fwd: Original Message",
                    body or "Forwarded message",
                    user_google_email,
                    content_type,
                    html_body,
                    resolved_cc,
                    resolved_bcc,
                    recipients_not_allowed,
                )
                if fallback_result is not None:
                    # Convert SendGmailMessageResponse to ForwardGmailMessageResponse
                    return ForwardGmailMessageResponse(
                        success=fallback_result["success"],
                        forward_message_id=fallback_result.get("messageId"),
                        original_message_id=message_id,
                        forwarded_to=(
                            resolved_to
                            if isinstance(resolved_to, str)
                            else ", ".join(resolved_to)
                        ),
                        subject="Fwd: Original Message",
                        content_type=content_type,
                        to_recipients=(
                            resolved_to
                            if isinstance(resolved_to, list)
                            else [resolved_to]
                            if resolved_to
                            else []
                        ),
                        cc_recipients=(
                            resolved_cc
                            if isinstance(resolved_cc, list)
                            else [resolved_cc]
                            if resolved_cc
                            else []
                        ),
                        bcc_recipients=(
                            resolved_bcc
                            if isinstance(resolved_bcc, list)
                            else [resolved_bcc]
                            if resolved_bcc
                            else []
                        ),
                        html_preserved=False,
                        userEmail=user_google_email or "",
                        error=fallback_result.get("error"),
                        elicitationRequired=fallback_result.get(
                            "elicitationRequired", False
                        ),
                        elicitationNotSupported=fallback_result.get(
                            "elicitationNotSupported", False
                        ),
                        recipientsNotAllowed=fallback_result.get(
                            "recipientsNotAllowed", []
                        ),
                        action=fallback_result.get("action", "blocked"),
                        draftId=fallback_result.get("draftId"),
                    )

            # Log elicitation trigger
            logger.info(
                f"Elicitation triggered for {len(recipients_not_allowed)} recipient(s) not on allow list"
            )

            # Prepare elicitation message
            to_display = (
                resolved_to if isinstance(resolved_to, str) else ", ".join(resolved_to)
            )
            cc_display = (
                f"\n📋 **CC:** {resolved_cc if isinstance(resolved_cc, str) else ', '.join(resolved_cc)}"
                if resolved_cc
                else ""
            )
            bcc_display = (
                f"\n📋 **BCC:** {resolved_bcc if isinstance(resolved_bcc, str) else ', '.join(resolved_bcc)}"
                if resolved_bcc
                else ""
            )

            # Preview of additional message if provided
            body_preview = ""
            if body:
                body_preview = f"\n📝 **Additional Message:**\n```\n{body[:200]}{'... [truncated]' if len(body) > 200 else ''}\n```\n"

            elicitation_message = f"""📧 **Forward Email Confirmation Required**

⏰ **Auto-timeout:** 300 seconds

📬 **Recipients:**
   • To: {to_display}{cc_display}{bcc_display}

📄 **Forward Details:**
   • Original Message ID: {message_id}
   • Content Type: {content_type}
   • HTML Preservation: {"Yes" if content_type in ["html", "mixed"] else "No"}{body_preview}

🔒 **Security Notice:** This recipient is not on your allow list.

❓ **Choose your action:**
   • **Send** - Forward the email immediately
   • **Save as Draft** - Save to drafts folder without sending
   • **Cancel** - Discard the forward
   
⏰ Auto-cancels in 300 seconds if no response"""

            # Trigger elicitation with graceful fallback for unsupported clients
            try:
                response = await asyncio.wait_for(
                    ctx.elicit(message=elicitation_message, response_type=EmailAction),
                    timeout=300.0,
                )
            except asyncio.TimeoutError:
                logger.info("Elicitation timed out after 300 seconds")
                return ForwardGmailMessageResponse(
                    success=False,
                    forward_message_id="",
                    original_message_id=message_id,
                    forwarded_to="",
                    subject="",
                    content_type=content_type,
                    to_recipients=[],
                    cc_recipients=[],
                    bcc_recipients=[],
                    html_preserved=False,
                    userEmail=user_google_email or "",
                    error="Forward operation timed out - no response received within 300 seconds",
                    elicitationRequired=True,
                    recipientsNotAllowed=recipients_not_allowed,
                )
            except Exception as elicit_error:
                # Enhanced client support detection - broader patterns to catch more unsupported clients
                error_msg = str(elicit_error).lower()
                error_type = type(elicit_error).__name__

                # Check for indicators that elicitation is not supported by the client
                # Using broader patterns to catch various client implementations
                is_unsupported_client = (
                    # Method/feature not found errors
                    "method not found" in error_msg
                    or "unknown method" in error_msg
                    or "unsupported method" in error_msg
                    or "not found" in error_msg  # Broader pattern
                    or "not supported" in error_msg  # Broader pattern
                    or "unsupported" in error_msg  # Broader pattern
                    or
                    # FastMCP/MCP-specific indicators
                    "elicit not supported" in error_msg
                    or "elicitation not supported" in error_msg
                    or "elicitation not available" in error_msg
                    or
                    # Exception types that commonly indicate missing functionality
                    error_type in ["AttributeError", "NotImplementedError", "TypeError"]
                    or
                    # Common client error patterns
                    "elicit" in error_msg
                    and ("error" in error_msg or "fail" in error_msg)
                )

                if is_unsupported_client:
                    logger.warning(
                        f"Client doesn't support elicitation (error: {error_type}: {error_msg}) - applying fallback: {settings.gmail_elicitation_fallback}"
                    )
                    fallback_result = await _handle_elicitation_fallback(
                        settings.gmail_elicitation_fallback,
                        resolved_to,
                        "Fwd: Original Message",
                        body or "Forwarded message",
                        user_google_email,
                        content_type,
                        html_body,
                        resolved_cc,
                        resolved_bcc,
                        recipients_not_allowed,
                    )
                    if fallback_result is not None:
                        # Convert SendGmailMessageResponse to ForwardGmailMessageResponse
                        return ForwardGmailMessageResponse(
                            success=fallback_result["success"],
                            forward_message_id=fallback_result.get("messageId"),
                            original_message_id=message_id,
                            forwarded_to=(
                                resolved_to
                                if isinstance(resolved_to, str)
                                else ", ".join(resolved_to)
                            ),
                            subject="Fwd: Original Message",
                            content_type=content_type,
                            to_recipients=(
                                resolved_to
                                if isinstance(resolved_to, list)
                                else [resolved_to]
                                if resolved_to
                                else []
                            ),
                            cc_recipients=(
                                resolved_cc
                                if isinstance(resolved_cc, list)
                                else [resolved_cc]
                                if resolved_cc
                                else []
                            ),
                            bcc_recipients=(
                                resolved_bcc
                                if isinstance(resolved_bcc, list)
                                else [resolved_bcc]
                                if resolved_bcc
                                else []
                            ),
                            html_preserved=False,
                            userEmail=user_google_email or "",
                            error=fallback_result.get("error"),
                            elicitationRequired=fallback_result.get(
                                "elicitationRequired", False
                            ),
                            elicitationNotSupported=fallback_result.get(
                                "elicitationNotSupported", False
                            ),
                            recipientsNotAllowed=fallback_result.get(
                                "recipientsNotAllowed", []
                            ),
                            action=fallback_result.get("action", "blocked"),
                            draftId=fallback_result.get("draftId"),
                        )
                    # If fallback_result is None (allow mode), continue with normal forwarding
                else:
                    # Very specific errors that indicate client should support elicitation
                    logger.error(
                        f"Forward elicitation failed for supporting client: {error_type}: {elicit_error}"
                    )
                    return ForwardGmailMessageResponse(
                        success=False,
                        forward_message_id="",
                        original_message_id=message_id,
                        forwarded_to="",
                        subject="",
                        content_type=content_type,
                        to_recipients=[],
                        cc_recipients=[],
                        bcc_recipients=[],
                        html_preserved=False,
                        userEmail=user_google_email or "",
                        error=f"Forward confirmation failed: {elicit_error}\n\n🔧 **Client appears to support elicitation but encountered an error**",
                        elicitationRequired=True,
                        recipientsNotAllowed=recipients_not_allowed,
                    )

            # Handle elicitation responses
            if response.action == "decline" or response.action == "cancel":
                logger.info(f"User {response.action}d forward operation")
                return ForwardGmailMessageResponse(
                    success=False,
                    forward_message_id="",
                    original_message_id=message_id,
                    forwarded_to="",
                    subject="",
                    content_type=content_type,
                    to_recipients=[],
                    cc_recipients=[],
                    bcc_recipients=[],
                    html_preserved=False,
                    userEmail=user_google_email or "",
                    error=f"User {response.action}d",
                    elicitationRequired=True,
                    recipientsNotAllowed=recipients_not_allowed,
                )
            elif response.action == "accept":
                # Get the user's choice from the data field
                user_choice = response.data.action

                if user_choice == "cancel":
                    logger.info("User chose to cancel forward operation")
                    return ForwardGmailMessageResponse(
                        success=False,
                        forward_message_id="",
                        original_message_id=message_id,
                        forwarded_to="",
                        subject="",
                        content_type=content_type,
                        to_recipients=[],
                        cc_recipients=[],
                        bcc_recipients=[],
                        html_preserved=False,
                        userEmail=user_google_email or "",
                        error="User cancelled",
                        elicitationRequired=True,
                        recipientsNotAllowed=recipients_not_allowed,
                    )
                elif user_choice == "save_draft":
                    logger.info("User chose to save forward as draft")
                    # Create draft instead of sending (use resolved recipients)
                    draft_result = await draft_gmail_forward(
                        message_id=message_id,
                        to=resolved_to,
                        user_google_email=user_google_email,
                        body=body,
                        content_type=content_type,
                        html_body=html_body,
                        cc=resolved_cc,
                        bcc=resolved_bcc,
                    )
                    # Return as forward response with draft info
                    return ForwardGmailMessageResponse(
                        success=True,
                        forward_message_id="",
                        original_message_id=message_id,
                        forwarded_to=(
                            resolved_to
                            if isinstance(resolved_to, str)
                            else ", ".join(resolved_to)
                        ),
                        subject=draft_result.get("subject", ""),
                        content_type=content_type,
                        to_recipients=draft_result.get("to_recipients", []),
                        cc_recipients=draft_result.get("cc_recipients", []),
                        bcc_recipients=draft_result.get("bcc_recipients", []),
                        html_preserved=draft_result.get("html_preserved", False),
                        userEmail=user_google_email or "",
                        error=None,
                        elicitationRequired=True,
                        recipientsNotAllowed=recipients_not_allowed,
                        action="saved_draft",
                        draftId=draft_result.get("draft_id"),
                    )
                elif user_choice == "send":
                    # Continue with forwarding
                    logger.info("User chose to forward email")
                else:
                    # Unexpected choice
                    logger.error(f"Unexpected user choice: {user_choice}")
                    return ForwardGmailMessageResponse(
                        success=False,
                        forward_message_id="",
                        original_message_id=message_id,
                        forwarded_to="",
                        subject="",
                        content_type=content_type,
                        to_recipients=[],
                        cc_recipients=[],
                        bcc_recipients=[],
                        html_preserved=False,
                        userEmail=user_google_email or "",
                        error=f"Unexpected choice: {user_choice}",
                        elicitationRequired=True,
                        recipientsNotAllowed=recipients_not_allowed,
                    )
            else:
                # Unexpected elicitation action
                logger.error(f"Unexpected elicitation action: {response.action}")
                return ForwardGmailMessageResponse(
                    success=False,
                    forward_message_id="",
                    original_message_id=message_id,
                    forwarded_to="",
                    subject="",
                    content_type=content_type,
                    to_recipients=[],
                    cc_recipients=[],
                    bcc_recipients=[],
                    html_preserved=False,
                    userEmail=user_google_email or "",
                    error=f"Unexpected elicitation response: {response.action}",
                    elicitationRequired=True,
                    recipientsNotAllowed=recipients_not_allowed,
                )
        else:
            # All recipients are on allow list - get count safely
            total_recipients = count_recipients(resolved_to, resolved_cc, resolved_bcc)
            logger.info(
                f"All {total_recipients} recipient(s) are on allow list - forwarding without elicitation"
            )
    else:
        # No allow list configured - still need to resolve groups
        logger.debug("No Gmail allow list configured - forwarding without elicitation")
        resolved_to = await _resolve_group_recipients(to, user_google_email)
        resolved_cc = await _resolve_group_recipients(cc, user_google_email)
        resolved_bcc = await _resolve_group_recipients(bcc, user_google_email)

    try:
        gmail_service = await _get_gmail_service_with_fallback(user_google_email)

        # STEP 3: Resolve 'me'/'myself' aliases in the already-group-resolved recipients
        final_to = _resolve_recipient_aliases(resolved_to, user_google_email)
        final_cc = _resolve_recipient_aliases(resolved_cc, user_google_email)
        final_bcc = _resolve_recipient_aliases(resolved_bcc, user_google_email)

        logger.debug(
            f"[forward] Final recipients after alias resolution - to: {final_to}, cc: {final_cc}, bcc: {final_bcc}"
        )

        # Fetch the original message to get headers and body for forwarding
        original_message = await asyncio.to_thread(
            gmail_service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute
        )
        payload = original_message.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
        original_subject = headers.get("Subject", "(no subject)")

        # Extract both plain text and HTML content from original message
        original_plain_body = _extract_message_body(payload)
        original_html_body = _extract_html_body(payload)

        # Determine if we have HTML content to preserve
        has_html = bool(original_html_body)
        html_preserved = has_html and content_type in ["html", "mixed"]

        # Prepare forward subject
        forward_subject = _prepare_forward_subject(original_subject)

        # Format the forwarded content based on content_type
        if content_type == "plain":
            # Plain text only - use plain text version of original
            forwarded_content = _format_forward_content(
                original_plain_body, headers, is_html=False
            )
            if body:
                full_body = f"{body}{forwarded_content}"
            else:
                full_body = forwarded_content
            final_html_body = None

        elif content_type == "html":
            # HTML only - use HTML version if available, fallback to plain text
            content_to_forward = original_html_body if has_html else original_plain_body
            forwarded_content = _format_forward_content(
                content_to_forward, headers, is_html=has_html
            )
            if body:
                if has_html:
                    full_body = f"{body}{forwarded_content}"
                else:
                    full_body = f"{body}{forwarded_content}"
            else:
                full_body = forwarded_content
            final_html_body = None

        elif content_type == "mixed":
            # Mixed content - prepare both plain and HTML versions
            # Plain text version
            plain_forwarded = _format_forward_content(
                original_plain_body, headers, is_html=False
            )
            if body:
                full_plain_body = f"{body}{plain_forwarded}"
            else:
                full_plain_body = plain_forwarded

            # HTML version
            if has_html:
                html_forwarded = _format_forward_content(
                    original_html_body, headers, is_html=True
                )
                if html_body:
                    final_html_body = f"{html_body}{html_forwarded}"
                else:
                    final_html_body = html_forwarded
            else:
                # No HTML content in original, convert plain text to HTML
                html_forwarded = _format_forward_content(
                    original_plain_body, headers, is_html=True
                )
                if html_body:
                    final_html_body = f"{html_body}{html_forwarded}"
                else:
                    final_html_body = html_forwarded

            full_body = full_plain_body

        # Create properly formatted MIME message using helper function
        raw_message = _create_mime_message(
            to=final_to,
            cc=final_cc,
            bcc=final_bcc,
            subject=forward_subject,
            body=full_body,
            content_type=content_type,
            html_body=final_html_body,
            from_email=user_google_email,
        )

        send_body = {"raw": raw_message}

        # Send the forward message
        sent_message = await asyncio.to_thread(
            gmail_service.users().messages().send(userId="me", body=send_body).execute
        )
        sent_message_id = sent_message.get("id")

        # Format recipients for response
        def format_recipient_string(recipients):
            if not recipients:
                return ""
            if isinstance(recipients, str):
                return recipients
            elif isinstance(recipients, list):
                return ", ".join(recipients)
            return ""

        forwarded_to_str = format_recipient_string(final_to)

        return ForwardGmailMessageResponse(
            success=True,
            forward_message_id=sent_message_id,
            original_message_id=message_id,
            forwarded_to=forwarded_to_str,
            subject=forward_subject,
            content_type=content_type,
            to_recipients=(
                final_to
                if isinstance(final_to, list)
                else [final_to]
                if final_to
                else []
            ),
            cc_recipients=(
                final_cc
                if isinstance(final_cc, list)
                else [final_cc]
                if final_cc
                else []
            ),
            bcc_recipients=(
                final_bcc
                if isinstance(final_bcc, list)
                else [final_bcc]
                if final_bcc
                else []
            ),
            html_preserved=html_preserved,
            userEmail=user_google_email or "",
            error=None,
            elicitationRequired=bool(recipients_not_allowed) if allow_list else False,
            recipientsNotAllowed=recipients_not_allowed if allow_list else [],
        )

    except Exception as e:
        logger.error(f"Unexpected error in forward_gmail_message: {e}")
        return ForwardGmailMessageResponse(
            success=False,
            forward_message_id="",
            original_message_id=message_id,
            forwarded_to="",
            subject="",
            content_type=content_type,
            to_recipients=[],
            cc_recipients=[],
            bcc_recipients=[],
            html_preserved=False,
            userEmail=user_google_email or "",
            error=str(e),
        )


async def draft_gmail_forward(
    message_id: str,
    to: GmailRecipients = "myself",
    user_google_email: UserGoogleEmail = None,
    body: Optional[str] = None,
    content_type: Literal["plain", "html", "mixed"] = "mixed",
    html_body: Optional[str] = None,
    cc: GmailRecipientsOptional = None,
    bcc: GmailRecipientsOptional = None,
) -> DraftGmailForwardResponse:
    """
    Create a draft forward of a Gmail message with HTML formatting preservation.

    This function creates a draft forward of an existing Gmail message while preserving
    the original HTML formatting as much as possible. It includes the original message
    headers (From, Date, Subject, To, Cc).

    Args:
        message_id: The ID of the message to forward
        to: Recipient email address(es) - can be a single string or list of strings
        user_google_email: The user's Google email address for Gmail access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware).
        body: Optional additional message body to add before the forwarded content. Usage depends on content_type:
            - content_type="plain": Contains plain text only
            - content_type="html": Contains HTML content
            - content_type="mixed": Contains plain text (HTML goes in html_body parameter)
        content_type: Content type - controls how body and html_body are used:
            - "plain": Plain text forward (original HTML converted to plain text)
            - "html": HTML forward - preserves original HTML formatting
            - "mixed": Dual content - plain text in 'body', HTML in 'html_body' (default, recommended)
        html_body: HTML content when content_type="mixed". Ignored for other content types.
        cc: Optional CC recipient(s) - can be a single string or list of strings
        bcc: Optional BCC recipient(s) - can be a single string or list of strings

    Returns:
        DraftGmailForwardResponse: Structured response with draft creation details

    Examples:
        # Simple draft forward
        draft_gmail_forward("msg_123", "user@example.com")

        # Draft forward with additional message
        draft_gmail_forward("msg_123", "user@example.com",
                          body="Please review this email.",
                          content_type="mixed",
                          html_body="<p>Please review this email.</p>")
    """
    # Format recipients for logging using shared utility function
    to_count = count_recipients(to)
    cc_count = count_recipients(cc) if cc else 0
    bcc_count = count_recipients(bcc) if bcc else 0

    to_str = to if isinstance(to, str) else f"{to_count} recipients"
    cc_str = (
        f", CC: {cc if isinstance(cc, str) else f'{cc_count} recipients'}" if cc else ""
    )
    bcc_str = (
        f", BCC: {bcc if isinstance(bcc, str) else f'{bcc_count} recipients'}"
        if bcc
        else ""
    )

    logger.info(
        f"[draft_gmail_forward] Email: '{user_google_email}', Drafting forward of Message ID: '{message_id}', To: {to_str}{cc_str}{bcc_str}, content_type: {content_type}"
    )

    try:
        gmail_service = await _get_gmail_service_with_fallback(user_google_email)

        # CRITICAL FIX: Resolve 'me'/'myself' aliases BEFORE processing
        resolved_to = _resolve_recipient_aliases(to, user_google_email)
        resolved_cc = _resolve_recipient_aliases(cc, user_google_email)
        resolved_bcc = _resolve_recipient_aliases(bcc, user_google_email)

        logger.debug(
            f"[draft_forward] Resolved recipients - to: {resolved_to}, cc: {resolved_cc}, bcc: {resolved_bcc}"
        )

        # Fetch the original message to get headers and body for forwarding
        original_message = await asyncio.to_thread(
            gmail_service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute
        )
        payload = original_message.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
        original_subject = headers.get("Subject", "(no subject)")

        # Extract both plain text and HTML content from original message
        original_plain_body = _extract_message_body(payload)
        original_html_body = _extract_html_body(payload)

        # Determine if we have HTML content to preserve
        has_html = bool(original_html_body)
        html_preserved = has_html and content_type in ["html", "mixed"]

        # Prepare forward subject
        forward_subject = _prepare_forward_subject(original_subject)

        # Format the forwarded content based on content_type
        if content_type == "plain":
            # Plain text only - use plain text version of original
            forwarded_content = _format_forward_content(
                original_plain_body, headers, is_html=False
            )
            if body:
                full_body = f"{body}{forwarded_content}"
            else:
                full_body = forwarded_content
            final_html_body = None

        elif content_type == "html":
            # HTML only - use HTML version if available, fallback to plain text
            content_to_forward = original_html_body if has_html else original_plain_body
            forwarded_content = _format_forward_content(
                content_to_forward, headers, is_html=has_html
            )
            if body:
                full_body = f"{body}{forwarded_content}"
            else:
                full_body = forwarded_content
            final_html_body = None

        elif content_type == "mixed":
            # Mixed content - prepare both plain and HTML versions
            # Plain text version
            plain_forwarded = _format_forward_content(
                original_plain_body, headers, is_html=False
            )
            if body:
                full_plain_body = f"{body}{plain_forwarded}"
            else:
                full_plain_body = plain_forwarded

            # HTML version
            if has_html:
                html_forwarded = _format_forward_content(
                    original_html_body, headers, is_html=True
                )
                if html_body:
                    final_html_body = f"{html_body}{html_forwarded}"
                else:
                    final_html_body = html_forwarded
            else:
                # No HTML content in original, convert plain text to HTML
                html_forwarded = _format_forward_content(
                    original_plain_body, headers, is_html=True
                )
                if html_body:
                    final_html_body = f"{html_body}{html_forwarded}"
                else:
                    final_html_body = html_forwarded

            full_body = full_plain_body

        # Create properly formatted MIME message using helper function
        raw_message = _create_mime_message(
            to=resolved_to,
            cc=resolved_cc,
            bcc=resolved_bcc,
            subject=forward_subject,
            body=full_body,
            content_type=content_type,
            html_body=final_html_body,
            from_email=user_google_email,
        )

        draft_body = {"message": {"raw": raw_message}}

        # Create the draft forward
        created_draft = await asyncio.to_thread(
            gmail_service.users().drafts().create(userId="me", body=draft_body).execute
        )
        draft_id = created_draft.get("id")

        # Format recipients for response
        def format_recipient_string(recipients):
            if not recipients:
                return ""
            if isinstance(recipients, str):
                return recipients
            elif isinstance(recipients, list):
                return ", ".join(recipients)
            return ""

        forwarded_to_str = format_recipient_string(resolved_to)

        return DraftGmailForwardResponse(
            success=True,
            draft_id=draft_id,
            original_message_id=message_id,
            forwarded_to=forwarded_to_str,
            subject=forward_subject,
            content_type=content_type,
            to_recipients=(
                resolved_to
                if isinstance(resolved_to, list)
                else [resolved_to]
                if resolved_to
                else []
            ),
            cc_recipients=(
                resolved_cc
                if isinstance(resolved_cc, list)
                else [resolved_cc]
                if resolved_cc
                else []
            ),
            bcc_recipients=(
                resolved_bcc
                if isinstance(resolved_bcc, list)
                else [resolved_bcc]
                if resolved_bcc
                else []
            ),
            html_preserved=html_preserved,
            userEmail=user_google_email or "",
            error=None,
        )

    except Exception as e:
        logger.error(f"Unexpected error in draft_gmail_forward: {e}")
        return DraftGmailForwardResponse(
            success=False,
            draft_id="",
            original_message_id=message_id,
            forwarded_to="",
            subject="",
            content_type=content_type,
            to_recipients=[],
            cc_recipients=[],
            bcc_recipients=[],
            html_preserved=False,
            userEmail=user_google_email or "",
            error=str(e),
        )


def setup_compose_tools(mcp: FastMCP) -> None:
    """Register Gmail composition tools with the FastMCP server."""

    @mcp.tool(
        name="send_gmail_message",
        description="Send an email using the user's Gmail account with elicitation support for untrusted recipients",
        tags={"gmail", "send", "email", "compose", "html", "templates", "elicitation"},
        annotations={
            "title": "Send Gmail Message",
            "readOnlyHint": False,  # Sends emails, modifies state
            "destructiveHint": False,  # Creates new content, doesn't destroy
            "idempotentHint": False,  # Multiple sends create multiple emails
            "openWorldHint": True,
        },
    )
    async def send_gmail_message_tool(
        ctx: Context,
        subject: Annotated[str, Field(description="Email subject line")],
        body: Annotated[
            str,
            Field(
                description="Email body content. Usage depends on content_type: 'plain' = plain text only, 'html' = HTML content (plain auto-generated), 'mixed' = plain text (HTML in html_body)"
            ),
        ],
        user_google_email: UserGoogleEmail = None,
        to: GmailRecipients = "myself",
        content_type: Annotated[
            Literal["plain", "html", "mixed"],
            Field(
                description="Content type: 'plain' (text only), 'html' (HTML in body param), 'mixed' (text in body, HTML in html_body)"
            ),
        ] = "mixed",
        html_body: Annotated[
            Optional[str],
            Field(
                description="HTML content when content_type='mixed'. Ignored for 'plain' and 'html' types"
            ),
        ] = None,
        cc: GmailRecipientsOptional = None,
        bcc: GmailRecipientsOptional = None,
        email_spec: Annotated[
            Optional[dict],
            Field(
                description="MJML-based responsive email spec. When provided, renders blocks to HTML "
                "and overrides body/content_type/html_body. Subject comes from spec unless explicitly set. "
                'Example: {"subject": "Welcome!", "blocks": [{"title": "Hello", ...}]}'
            ),
        ] = None,
    ) -> SendGmailMessageResponse:
        """
        Send Gmail message with structured output and elicitation support.

        Returns both:
        - Traditional content: Human-readable confirmation message (automatic via FastMCP)
        - Structured content: Machine-readable JSON with detailed send results

        Features:
        - HTML and plain text support with automatic conversion
        - Multiple recipients (to, cc, bcc)
        - Email template auto-application based on recipients
        - Elicitation for recipients not on allow list
        - Auto-injection of user context via middleware
        - MJML-based responsive email rendering via email_spec

        Args:
            ctx: FastMCP context for user interactions and elicitation
            subject: Email subject line
            body: Email body content (usage varies by content_type)
            user_google_email: User's email address (auto-injected if None)
            to: Recipient email address(es) - defaults to 'myself' (authenticated user)
            content_type: How to handle body/html_body content
            html_body: HTML content for mixed-type emails
            cc: CC recipients (optional)
            bcc: BCC recipients (optional)
            email_spec: Optional MJML EmailSpec for responsive HTML emails

        Returns:
        SendGmailMessageResponse: Structured response with send status and details
        """
        return await send_gmail_message(
            ctx,
            subject,
            body,
            to,
            user_google_email,
            content_type,
            html_body,
            cc,
            bcc,
            email_spec=email_spec,
        )

    @mcp.tool(
        name="draft_gmail_message",
        description="Create a draft email in the user's Gmail account with HTML support and multiple recipients",
        tags={"gmail", "draft", "email", "compose", "html", "save"},
        annotations={
            "title": "Draft Gmail Message",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def draft_gmail_message_tool(
        subject: Annotated[str, Field(description="Email subject line for the draft")],
        body: Annotated[
            str,
            Field(
                description="Email body content. Usage depends on content_type: 'plain' = plain text only, 'html' = HTML content (plain auto-generated), 'mixed' = plain text (HTML in html_body)"
            ),
        ],
        user_google_email: UserGoogleEmail = None,
        to: GmailRecipientsOptional = None,
        content_type: Annotated[
            Literal["plain", "html", "mixed"],
            Field(
                description="Content type: 'plain' (text only), 'html' (HTML in body param), 'mixed' (text in body, HTML in html_body)"
            ),
        ] = "mixed",
        html_body: Annotated[
            Optional[str],
            Field(
                description="HTML content when content_type='mixed'. Ignored for 'plain' and 'html' types"
            ),
        ] = None,
        cc: GmailRecipientsOptional = None,
        bcc: GmailRecipientsOptional = None,
        email_spec: Annotated[
            Optional[dict],
            Field(
                description="MJML-based responsive email spec. When provided, renders blocks to HTML "
                "and overrides body/content_type/html_body. Subject comes from spec unless explicitly set."
            ),
        ] = None,
    ) -> DraftGmailMessageResponse:
        """
        Create Gmail draft with structured output.

        Returns both:
        - Traditional content: Human-readable confirmation message (automatic via FastMCP)
        - Structured content: Machine-readable JSON with draft creation details

        Features:
        - HTML and plain text support with automatic conversion
        - Multiple recipients (to, cc, bcc) or recipient-less drafts
        - Auto-injection of user context via middleware
        - Flexible content type handling
        - MJML-based responsive email rendering via email_spec

        Args:
            subject: Email subject line
            body: Email body content (usage varies by content_type)
            user_google_email: User's email address (auto-injected if None)
            to: Optional recipient email address(es)
            content_type: How to handle body/html_body content
            html_body: HTML content for mixed-type emails
            cc: CC recipients (optional)
            bcc: BCC recipients (optional)
            email_spec: Optional MJML EmailSpec for responsive HTML emails

        Returns:
        DraftGmailMessageResponse: Structured response with draft creation details
        """
        return await draft_gmail_message(
            subject,
            body,
            user_google_email,
            to,
            content_type,
            html_body,
            cc,
            bcc,
            email_spec=email_spec,
        )

    @mcp.tool(
        name="reply_to_gmail_message",
        description="Send a reply to a specific Gmail message with proper threading and HTML support",
        tags={"gmail", "reply", "send", "thread", "email", "html", "conversation"},
        annotations={
            "title": "Reply to Gmail Message",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def reply_to_gmail_message_tool(
        message_id: Annotated[
            str,
            Field(
                description="The ID of the original Gmail message to reply to. This maintains proper email threading"
            ),
        ],
        body: Annotated[
            str,
            Field(
                description="Reply body content. Usage depends on content_type: 'plain' = plain text only, 'html' = HTML content (plain auto-generated), 'mixed' = plain text (HTML in html_body). Original message will be automatically quoted"
            ),
        ],
        user_google_email: UserGoogleEmail = None,
        reply_mode: Annotated[
            Literal["sender_only", "reply_all", "custom"],
            Field(
                description="Who receives the reply: 'sender_only' = only original sender (default), 'reply_all' = all original recipients, 'custom' = use provided to/cc/bcc parameters"
            ),
        ] = "sender_only",
        to: GmailRecipientsOptional = None,
        cc: GmailRecipientsOptional = None,
        bcc: GmailRecipientsOptional = None,
        content_type: Annotated[
            Literal["plain", "html", "mixed"],
            Field(
                description="Content type: 'plain' (text only with quoted original), 'html' (HTML in body param with quoted original), 'mixed' (text in body, HTML in html_body, both with quoted original)"
            ),
        ] = "mixed",
        html_body: Annotated[
            Optional[str],
            Field(
                description="HTML content when content_type='mixed'. The original message will be automatically quoted in HTML format. Ignored for 'plain' and 'html' types"
            ),
        ] = None,
    ) -> ReplyGmailMessageResponse:
        """
        Reply to Gmail message with structured output and proper threading.

        Returns both:
        - Traditional content: Human-readable confirmation message (automatic via FastMCP)
        - Structured content: Machine-readable JSON with reply details and threading info

        Features:
        - Automatic email threading (maintains conversation)
        - Original message quoting in reply
        - HTML and plain text support
        - Flexible recipient options: sender only, reply all, or custom
        - Auto-extraction of reply-to address and subject
        - Auto-injection of user context via middleware

        Args:
            message_id: ID of the original message to reply to
            body: Reply body content (original message auto-quoted)
            user_google_email: User's email address (auto-injected if None)
            reply_mode: Controls who receives the reply
            to: Custom recipients (when reply_mode='custom')
            cc: Custom CC recipients (when reply_mode='custom')
            bcc: Custom BCC recipients (when reply_mode='custom')
            content_type: How to handle body/html_body content
            html_body: HTML content for mixed-type replies

        Returns:
        ReplyGmailMessageResponse: Structured response with reply status and threading info
        """
        return await reply_to_gmail_message(
            message_id,
            body,
            user_google_email,
            reply_mode,
            to,
            cc,
            bcc,
            content_type,
            html_body,
        )

    @mcp.tool(
        name="draft_gmail_reply",
        description="Create a draft reply to a specific Gmail message with proper threading and HTML support",
        tags={
            "gmail",
            "draft",
            "reply",
            "thread",
            "email",
            "html",
            "conversation",
            "save",
        },
        annotations={
            "title": "Draft Gmail Reply",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def draft_gmail_reply_tool(
        message_id: Annotated[
            str,
            Field(
                description="The ID of the original Gmail message to draft a reply for. This maintains proper email threading in the draft"
            ),
        ],
        body: Annotated[
            str,
            Field(
                description="Draft reply body content. Usage depends on content_type: 'plain' = plain text only, 'html' = HTML content (plain auto-generated), 'mixed' = plain text (HTML in html_body). Original message will be automatically quoted"
            ),
        ],
        user_google_email: UserGoogleEmail = None,
        reply_mode: Annotated[
            Literal["sender_only", "reply_all", "custom"],
            Field(
                description="Who receives the reply: 'sender_only' = only original sender (default), 'reply_all' = all original recipients, 'custom' = use provided to/cc/bcc parameters"
            ),
        ] = "sender_only",
        to: GmailRecipientsOptional = None,
        cc: GmailRecipientsOptional = None,
        bcc: GmailRecipientsOptional = None,
        content_type: Annotated[
            Literal["plain", "html", "mixed"],
            Field(
                description="Content type: 'plain' (text only with quoted original), 'html' (HTML in body param with quoted original), 'mixed' (text in body, HTML in html_body, both with quoted original)"
            ),
        ] = "mixed",
        html_body: Annotated[
            Optional[str],
            Field(
                description="HTML content when content_type='mixed'. The original message will be automatically quoted in HTML format. Ignored for 'plain' and 'html' types"
            ),
        ] = None,
    ) -> DraftGmailReplyResponse:
        """
        Create Gmail draft reply with structured output and proper threading.

        Returns both:
        - Traditional content: Human-readable confirmation message (automatic via FastMCP)
        - Structured content: Machine-readable JSON with draft creation and threading info

        Features:
        - Automatic email threading (maintains conversation in draft)
        - Original message quoting in draft
        - HTML and plain text support
        - Flexible recipient options: sender only, reply all, or custom
        - Auto-extraction of reply-to address and subject
        - Auto-injection of user context via middleware

        Args:
            message_id: ID of the original message to draft reply for
            body: Draft reply body content (original message auto-quoted)
            user_google_email: User's email address (auto-injected if None)
            reply_mode: Controls who receives the reply
            to: Custom recipients (when reply_mode='custom')
            cc: Custom CC recipients (when reply_mode='custom')
            bcc: Custom BCC recipients (when reply_mode='custom')
            content_type: How to handle body/html_body content
            html_body: HTML content for mixed-type draft replies

        Returns:
        DraftGmailReplyResponse: Structured response with draft creation and threading info
        """
        return await draft_gmail_reply(
            message_id,
            body,
            user_google_email,
            reply_mode,
            to,
            cc,
            bcc,
            content_type,
            html_body,
        )

    @mcp.tool(
        name="forward_gmail_message",
        description="Forward a Gmail message to specified recipients with HTML formatting preservation and elicitation support",
        tags={"gmail", "forward", "send", "email", "html", "elicitation", "compose"},
        annotations={
            "title": "Forward Gmail Message",
            "readOnlyHint": False,  # Sends emails, modifies state
            "destructiveHint": False,  # Creates new content, doesn't destroy
            "idempotentHint": False,  # Multiple forwards create multiple emails
            "openWorldHint": True,
        },
    )
    async def forward_gmail_message_tool(
        ctx: Context,
        message_id: Annotated[
            str,
            Field(
                description="The ID of the Gmail message to forward. This will include the original message content and headers"
            ),
        ],
        to: GmailRecipients = "myself",
        user_google_email: UserGoogleEmail = None,
        body: Annotated[
            Optional[str],
            Field(
                description="Optional additional message body to add before the forwarded content. Usage depends on content_type: 'plain' = plain text only, 'html' = HTML content, 'mixed' = plain text (HTML in html_body)"
            ),
        ] = None,
        content_type: Annotated[
            Literal["plain", "html", "mixed"],
            Field(
                description="Content type: 'plain' (converts original HTML to text), 'html' (preserves HTML formatting), 'mixed' (both plain and HTML versions - recommended)"
            ),
        ] = "mixed",
        html_body: Annotated[
            Optional[str],
            Field(
                description="HTML content when content_type='mixed'. This will be added before the forwarded HTML content. Ignored for 'plain' and 'html' types"
            ),
        ] = None,
        cc: GmailRecipientsOptional = None,
        bcc: GmailRecipientsOptional = None,
    ) -> ForwardGmailMessageResponse:
        """
        Forward Gmail message with structured output, HTML preservation, and elicitation support.

        Returns both:
        - Traditional content: Human-readable confirmation message (automatic via FastMCP)
        - Structured content: Machine-readable JSON with forward details and HTML preservation status

        Features:
        - HTML formatting preservation (maintains original email styling)
        - Elicitation for recipients not on allow list
        - Multiple recipients (to, cc, bcc)
        - Original message headers included (From, Date, Subject, To, Cc)
        - Auto-injection of user context via middleware
        - Proper Gmail forward formatting with "---------- Forwarded message ---------" separator

        HTML Preservation Strategy:
        - Uses 'mixed' content type by default for maximum compatibility
        - Preserves original HTML structure and inline styles
        - Includes both plain text and HTML versions for email client compatibility
        - Maintains formatting even when forwarded through Gmail

        Args:
            ctx: FastMCP context for user interactions and elicitation
            message_id: ID of the Gmail message to forward
            to: Recipient email address(es)
            user_google_email: User's email address (auto-injected if None)
            body: Optional additional message before forwarded content
            content_type: How to handle original message formatting
            html_body: HTML content for mixed-type forwards
            cc: CC recipients (optional)
            bcc: BCC recipients (optional)

        Returns:
        ForwardGmailMessageResponse: Structured response with forward status and HTML preservation info
        """
        return await forward_gmail_message(
            ctx,
            message_id,
            to,
            user_google_email,
            body,
            content_type,
            html_body,
            cc,
            bcc,
        )

    @mcp.tool(
        name="draft_gmail_forward",
        description="Create a draft forward of a Gmail message with HTML formatting preservation",
        tags={"gmail", "draft", "forward", "email", "html", "save", "compose"},
        annotations={
            "title": "Draft Gmail Forward",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def draft_gmail_forward_tool(
        message_id: Annotated[
            str,
            Field(
                description="The ID of the Gmail message to create a forward draft for. This will include the original message content and headers"
            ),
        ],
        to: GmailRecipients = "myself",
        user_google_email: UserGoogleEmail = None,
        body: Annotated[
            Optional[str],
            Field(
                description="Optional additional message body to add before the forwarded content. Usage depends on content_type: 'plain' = plain text only, 'html' = HTML content, 'mixed' = plain text (HTML in html_body)"
            ),
        ] = None,
        content_type: Annotated[
            Literal["plain", "html", "mixed"],
            Field(
                description="Content type: 'plain' (converts original HTML to text), 'html' (preserves HTML formatting), 'mixed' (both plain and HTML versions - recommended)"
            ),
        ] = "mixed",
        html_body: Annotated[
            Optional[str],
            Field(
                description="HTML content when content_type='mixed'. This will be added before the forwarded HTML content. Ignored for 'plain' and 'html' types"
            ),
        ] = None,
        cc: GmailRecipientsOptional = None,
        bcc: GmailRecipientsOptional = None,
    ) -> DraftGmailForwardResponse:
        """
        Create Gmail forward draft with structured output and HTML preservation.

        Returns both:
        - Traditional content: Human-readable confirmation message (automatic via FastMCP)
        - Structured content: Machine-readable JSON with draft creation and HTML preservation info

        Features:
        - HTML formatting preservation (maintains original email styling)
        - Multiple recipients (to, cc, bcc)
        - Original message headers included (From, Date, Subject, To, Cc)
        - Auto-injection of user context via middleware
        - Proper Gmail forward formatting with "---------- Forwarded message ---------" separator
        - Draft saved to Gmail drafts folder for later review/sending

        HTML Preservation Strategy:
        - Uses 'mixed' content type by default for maximum compatibility
        - Preserves original HTML structure and inline styles
        - Includes both plain text and HTML versions for email client compatibility
        - Maintains formatting even when forwarded through Gmail

        Args:
            message_id: ID of the Gmail message to draft forward for
            to: Recipient email address(es)
            user_google_email: User's email address (auto-injected if None)
            body: Optional additional message before forwarded content
            content_type: How to handle original message formatting
            html_body: HTML content for mixed-type draft forwards
            cc: CC recipients (optional)
            bcc: BCC recipients (optional)

        Returns:
        DraftGmailForwardResponse: Structured response with draft creation and HTML preservation info
        """
        return await draft_gmail_forward(
            message_id, to, user_google_email, body, content_type, html_body, cc, bcc
        )

    # =========================================================================
    # compose_dynamic_email — DSL-driven email composition
    # =========================================================================

    from gmail.email_wrapper_api import (
        get_email_dsl_documentation,
        get_email_dsl_field_description,
        get_email_symbols,
        get_email_tool_examples,
    )

    email_symbols = get_email_symbols()
    spec_sym = email_symbols["EmailSpec"]
    hero_sym = email_symbols["HeroBlock"]
    text_sym = email_symbols["TextBlock"]
    btn_sym = email_symbols["ButtonBlock"]
    email_dsl_field_desc = get_email_dsl_field_description()

    # Generate skill_resources annotation from wrapper (if available)
    email_skill_resources = []
    try:
        from gmail.email_wrapper_setup import get_email_wrapper

        _email_wrapper = get_email_wrapper()
        if hasattr(_email_wrapper, "get_skill_resources_annotation"):
            email_skill_resources = _email_wrapper.get_skill_resources_annotation(
                skill_name="mjml-email",
                resource_hints={
                    "email-params.md": {
                        "purpose": "How to structure email_params with symbol keys, _shared/_items format, and per-block field reference",
                        "when_to_read": "BEFORE first call — required for correct email rendering",
                    },
                    "email-dsl-syntax.md": {
                        "purpose": "Email DSL notation syntax, symbol table, containment rules",
                        "when_to_read": "When constructing email_description DSL strings",
                    },
                    "jinja-filters.md": {
                        "purpose": "Jinja2 template filters for text styling in email content",
                        "when_to_read": "When styling text content in emails",
                    },
                },
            )
    except Exception:
        pass  # Non-fatal — skill_resources is optional

    compose_tool_description = (
        "Compose responsive HTML emails using DSL notation for block structure. "
        f"Common patterns: {spec_sym}[{hero_sym}, {text_sym}] = hero + text, "
        f"{spec_sym}[{hero_sym}, {text_sym}x2, {btn_sym}] = hero + 2 text blocks + button. "
        f"{email_dsl_field_desc}"
    )

    email_description_help = (
        "ONLY the DSL structure + email subject line. "
        f"Format: '{spec_sym}[{hero_sym}, {text_sym}] My Subject Here'. "
        "Do NOT put block content here — use email_params for that. "
        f"Examples: '{spec_sym}[{hero_sym}, {text_sym}] Welcome aboard', "
        f"'{spec_sym}[{hero_sym}, {text_sym}x2, {btn_sym}] Monthly Newsletter'. "
        "Text after the DSL becomes the email subject (keep it short). "
        f"{email_dsl_field_desc}"
    )

    @mcp.tool(
        name="compose_dynamic_email",
        description=compose_tool_description,
        tags={"gmail", "email", "compose", "mjml", "dynamic", "dsl"},
        annotations={
            "title": "Compose Dynamic Email",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
            "dsl_documentation": get_email_dsl_documentation(include_examples=True),
            "examples": get_email_tool_examples(max_examples=5),
            "skill_resources": email_skill_resources,  # Dynamic from wrapper.get_skill_resources_annotation()
        },
    )
    async def compose_dynamic_email(
        ctx: Context,
        email_description: Annotated[
            str,
            Field(description=email_description_help),
        ],
        email_params: Annotated[
            Optional[Union[dict, str]],
            Field(
                default=None,
                description="REQUIRED for content — all block text/titles/URLs go here, "
                "keyed by symbol or class name. "
                f'Example: {{"{hero_sym}": {{"title": "Welcome!", "subtitle": "Hi there"}}, '
                f'"{text_sym}": {{"_items": [{{"text": "Your message here"}}]}}, '
                f'"{btn_sym}": {{"_items": [{{"text": "Click", "url": "https://..."}}]}}}}. '
                "Also accepts 'subject' and 'preheader' keys.",
            ),
        ] = None,
        to: GmailRecipients = "myself",
        user_google_email: UserGoogleEmail = None,
        action: Annotated[
            Literal["send", "draft"],
            Field(
                description="'draft' (default, safe) or 'send' to deliver immediately"
            ),
        ] = "draft",
        cc: GmailRecipientsOptional = None,
        bcc: GmailRecipientsOptional = None,
    ):
        """Compose responsive HTML email via DSL notation, then send or draft."""
        import json as _json

        from gmail.email_wrapper_api import (
            extract_email_dsl_from_description,
            parse_email_dsl,
        )

        # MCP clients / Jinja macros may send email_params as a JSON string; coerce to dict.
        if isinstance(email_params, str):
            try:
                email_params = _json.loads(email_params)
            except (ValueError, TypeError):
                email_params = None

        # 1. Extract DSL from description
        dsl_string = extract_email_dsl_from_description(email_description)
        if not dsl_string:
            return SendGmailMessageResponse(
                success=False,
                message=(
                    "No DSL notation found in email_description. "
                    f"Use symbols like {spec_sym}[{hero_sym}, {text_sym}] to define structure."
                ),
                messageId=None,
                threadId=None,
                recipientCount=0,
                contentType="html",
                templateApplied=False,
                error="No DSL found in email_description",
            )

        # 2. Parse DSL
        dsl_result = parse_email_dsl(dsl_string)
        if not dsl_result.is_valid:
            return SendGmailMessageResponse(
                success=False,
                message=f"Invalid DSL: {'; '.join(dsl_result.issues)}",
                messageId=None,
                threadId=None,
                recipientCount=0,
                contentType="html",
                templateApplied=False,
                error=f"DSL parse error: {dsl_result.issues}",
            )

        logger.info(
            f"[compose_dynamic_email] DSL parsed: {dsl_result.component_counts}"
        )

        # 3. Build EmailSpec from DSL + params
        try:
            email_spec = _build_email_spec_from_dsl(
                dsl_result, email_params, email_description
            )
        except Exception as e:
            logger.error(f"[compose_dynamic_email] Build failed: {e}", exc_info=True)
            return SendGmailMessageResponse(
                success=False,
                message=f"Failed to build email from DSL: {e}",
                messageId=None,
                threadId=None,
                recipientCount=0,
                contentType="html",
                templateApplied=False,
                error=str(e),
            )

        # 4. Deliver via existing send/draft paths
        if action == "send":
            return await send_gmail_message(
                ctx,
                subject=email_spec.subject,
                body="",
                to=to,
                user_google_email=user_google_email,
                cc=cc,
                bcc=bcc,
                email_spec=email_spec,
            )
        else:
            return await draft_gmail_message(
                subject=email_spec.subject,
                body="",
                user_google_email=user_google_email,
                to=to,
                cc=cc,
                bcc=bcc,
                email_spec=email_spec,
            )
