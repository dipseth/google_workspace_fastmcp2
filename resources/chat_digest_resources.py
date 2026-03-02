"""
Chat Digest Resources for FastMCP2 Google Workspace Platform.

Provides resources that aggregate recent messages across all Google Chat
spaces into one structured digest, making it trivial for an agent to "check chats."

Uses the Chat API directly via _get_chat_service_with_fallback() rather than going
through the tool registry.

Resource URIs (RFC 6570):
    chat://digest{?hours,limit}          — all spaces, optional hours/limit
    chat://digest/space/{space_id}{?hours,limit}  — single space
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastmcp import Context, FastMCP
from pydantic import Field
from typing_extensions import Annotated, Any, Dict, List, Optional

from auth.context import get_user_email_context
from config.enhanced_logging import setup_logger
from gchat.chat_tools import _get_chat_service_with_fallback
from gchat.chat_types import ChatDigest, DigestMessage, DigestSpace

logger = setup_logger()

MAX_SPACES = 15
DEFAULT_HOURS = 24
DEFAULT_LIMIT = 10


def _fetch_all_sync(
    chat_service,
    spaces_to_scan: List[Dict[str, Any]],
    time_filter: str,
    limit: int,
) -> List[DigestSpace]:
    """Synchronous function that fetches messages from all spaces sequentially.

    Runs entirely in a single thread to avoid httplib2/SSL thread-safety issues.
    The google-api-python-client uses httplib2 which is NOT thread-safe — running
    multiple asyncio.to_thread() calls can corrupt SSL state even when awaited
    sequentially (thread pool reuse). This function ensures all API calls happen
    on exactly one thread.
    """
    active_spaces: List[DigestSpace] = []

    for space in spaces_to_scan:
        space_id = space.get("name", "")
        display_name = space.get("displayName", "Unnamed Space")
        space_type = space.get("spaceType", "UNKNOWN")

        try:
            response = (
                chat_service.spaces()
                .messages()
                .list(
                    parent=space_id,
                    pageSize=limit,
                    filter=time_filter,
                    orderBy="createTime desc",
                )
                .execute()
            )

            raw_messages = response.get("messages", [])
            if not raw_messages:
                continue

            messages: List[DigestMessage] = []
            for msg in raw_messages:
                sender = msg.get("sender", {})
                sender_name = sender.get("displayName") or sender.get("name", "Unknown")
                sender_email = sender.get("email")

                messages.append(
                    DigestMessage(
                        id=msg.get("name", ""),
                        text=msg.get("text", ""),
                        sender_name=sender_name,
                        sender_email=sender_email,
                        create_time=msg.get("createTime", ""),
                        thread_id=(
                            msg.get("thread", {}).get("name")
                            if "thread" in msg
                            else None
                        ),
                    )
                )

            active_spaces.append(
                DigestSpace(
                    space_id=space_id,
                    display_name=display_name,
                    space_type=space_type,
                    message_count=len(messages),
                    messages=messages,
                )
            )

        except Exception as e:
            logger.debug(f"Skipping space {space_id} ({display_name}): {e}")

    return active_spaces


async def _build_digest(
    user_email: str,
    hours_back: int = DEFAULT_HOURS,
    limit: int = DEFAULT_LIMIT,
    space_id_filter: Optional[str] = None,
) -> ChatDigest:
    """Core digest builder used by all resource handlers."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

    chat_service = await _get_chat_service_with_fallback(user_email)
    if chat_service is None:
        return ChatDigest(
            user_email=user_email,
            hours_back=hours_back,
            limit=limit,
            total_messages=0,
            total_spaces_with_activity=0,
            spaces_checked=0,
            spaces=[],
            timestamp=datetime.now(timezone.utc).isoformat(),
            error="Failed to authenticate with Google Chat. Use start_google_auth to authenticate first.",
        )

    # Build time filter for server-side filtering
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    time_filter = f'createTime > "{cutoff_str}"'

    # Resolve which spaces to scan — run in single thread to avoid SSL issues
    def _resolve_and_fetch() -> tuple:
        """Resolve spaces and fetch all messages in one thread."""
        if space_id_filter:
            spaces = [{"name": space_id_filter}]
            try:
                space_info = chat_service.spaces().get(name=space_id_filter).execute()
                spaces = [space_info]
            except Exception as e:
                logger.warning(f"Could not fetch space info for {space_id_filter}: {e}")
        else:
            response = chat_service.spaces().list(pageSize=MAX_SPACES).execute()
            spaces = response.get("spaces", [])[:MAX_SPACES]

        active = _fetch_all_sync(chat_service, spaces, time_filter, limit)
        return spaces, active

    try:
        spaces_to_scan, active_spaces = await asyncio.to_thread(_resolve_and_fetch)
    except Exception as e:
        return ChatDigest(
            user_email=user_email,
            hours_back=hours_back,
            limit=limit,
            total_messages=0,
            total_spaces_with_activity=0,
            spaces_checked=0,
            spaces=[],
            timestamp=datetime.now(timezone.utc).isoformat(),
            error=f"Failed to fetch Chat digest: {e}",
        )

    total_messages = sum(s.message_count for s in active_spaces)

    return ChatDigest(
        user_email=user_email,
        hours_back=hours_back,
        limit=limit,
        total_messages=total_messages,
        total_spaces_with_activity=len(active_spaces),
        spaces_checked=len(spaces_to_scan),
        spaces=active_spaces,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def setup_chat_digest_resources(mcp: FastMCP) -> None:
    """Register chat digest resources on the FastMCP server."""

    logger.debug("Setting up chat digest resources")

    @mcp.resource(
        uri="chat://digest{?hours,limit}",
        name="Chat Digest",
        description=(
            "Get a digest of recent messages across all Google Chat spaces. "
            "Returns messages grouped by space with sender info and timestamps.\n\n"
            "Query parameters:\n"
            "  - hours: Hours of history to include (1-168, default 24)\n"
            "  - limit: Max messages per space (1-50, default 10)\n\n"
            "Examples:\n"
            "  - chat://digest → Last 24 hours, 10 messages/space\n"
            "  - chat://digest?hours=4 → Last 4 hours\n"
            "  - chat://digest?hours=48&limit=20 → Last 2 days, 20 messages/space"
        ),
        mime_type="application/json",
        tags={"chat", "digest", "messages", "recent", "google"},
        annotations={"readOnlyHint": True, "idempotentHint": False},
        meta={
            "version": "1.0",
            "category": "digest",
            "max_spaces_scanned": MAX_SPACES,
        },
    )
    async def get_chat_digest(
        ctx: Context,
        hours: Annotated[
            int,
            Field(
                description="Hours of history to include (1-168)",
                ge=1,
                le=168,
                examples=[4, 24, 48],
            ),
        ] = DEFAULT_HOURS,
        limit: Annotated[
            int,
            Field(
                description="Max messages per space (1-50)",
                ge=1,
                le=50,
                examples=[5, 10, 25],
            ),
        ] = DEFAULT_LIMIT,
    ) -> str:
        """Recent chat messages across all spaces."""
        user_email = await get_user_email_context()
        if not user_email:
            return json.dumps(
                {
                    "error": "No authenticated user found",
                    "suggestion": "Use start_google_auth tool to authenticate first",
                },
            )

        result = await _build_digest(user_email, hours_back=hours, limit=limit)
        return result.model_dump_json()

    @mcp.resource(
        uri="chat://digest/space/{space_id}{?hours,limit}",
        name="Chat Digest (Single Space)",
        description=(
            "Get a digest of recent messages from a specific Google Chat space.\n\n"
            "Query parameters:\n"
            "  - hours: Hours of history to include (1-168, default 24)\n"
            "  - limit: Max messages to return (1-50, default 10)\n\n"
            "Examples:\n"
            "  - chat://digest/space/spaces/AAAA1234 → Last 24 hours\n"
            "  - chat://digest/space/spaces/AAAA1234?hours=4&limit=5"
        ),
        mime_type="application/json",
        tags={"chat", "digest", "messages", "recent", "google", "space"},
        annotations={"readOnlyHint": True, "idempotentHint": False},
        meta={
            "version": "1.0",
            "category": "digest",
        },
    )
    async def get_chat_digest_space(
        ctx: Context,
        space_id: Annotated[
            str,
            Field(
                description="Full space resource name",
                examples=["spaces/AAAA1234", "spaces/AAAAWvjq2HE"],
            ),
        ],
        hours: Annotated[
            int,
            Field(
                description="Hours of history to include (1-168)",
                ge=1,
                le=168,
                examples=[4, 24, 48],
            ),
        ] = DEFAULT_HOURS,
        limit: Annotated[
            int,
            Field(
                description="Max messages to return (1-50)",
                ge=1,
                le=50,
                examples=[5, 10, 25],
            ),
        ] = DEFAULT_LIMIT,
    ) -> str:
        """Recent chat messages from a specific space."""
        user_email = await get_user_email_context()
        if not user_email:
            return json.dumps(
                {
                    "error": "No authenticated user found",
                    "suggestion": "Use start_google_auth tool to authenticate first",
                },
            )

        result = await _build_digest(
            user_email, hours_back=hours, limit=limit, space_id_filter=space_id
        )
        return result.model_dump_json()

    logger.debug(
        "Chat digest resources registered: "
        "chat://digest{?hours,limit}, "
        "chat://digest/space/{space_id}{?hours,limit}"
    )
