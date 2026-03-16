"""
Google Chat MCP Tools for FastMCP2.

This module provides MCP tools for interacting with Google Chat API.
Enhanced with Card Framework integration and adapter system support.
Migrated from decorator-based pattern to FastMCP2 architecture.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 CRITICAL: GOOGLE CHAT MARKDOWN FORMAT REQUIREMENTS 🚨
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Google Chat uses its own markdown syntax, NOT HTML or standard Markdown!

✅ CORRECT FORMATTING (Use these):
  *bold text*           → renders as bold
  _italic text_         → renders as italic
  ~strikethrough~       → renders as strikethrough
  `monospace code`      → renders as code
  ```code block```      → renders as code block
  <url|link text>       → custom link (e.g., <https://google.com|Click Here>)
  <users/12345>         → user mention
  * Bullet item         → bullet list
  - Bullet item         → bullet list (alternative)

❌ WRONG FORMATTING (Do NOT use):
  <b>bold</b>           → displays literal text: "<b>bold</b>"
  <i>italic</i>         → displays literal text: "<i>italic</i>"
  <strong>text</strong> → displays literal text: "<strong>text</strong>"
  <a href="url">text</a>→ displays literal text with broken link
  **bold**              → displays literal text: "**bold**"
  __italic__            → displays literal text: "__italic__"

⚠️  HTML TAGS DISPLAY AS LITERAL TEXT - THEY DO NOT RENDER!
⚠️  STANDARD MARKDOWN (**, __, etc.) DOES NOT WORK!

For more details: https://developers.google.com/chat/format-messages
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

═══════════════════════════════════════════════════════════════════════════════
                      💬 THE DIALECT OF SPACES 💬
═══════════════════════════════════════════════════════════════════════════════

    Every kingdom speaks its tongue—
    Chat refuses what HTML has sung.
    <b> tags render raw and bare,
    *asterisks* show bold with care.

    The LLM arrives with assumptions deep:
    "Markdown works everywhere," it thinks in sleep.
    But Chat has customs all its own,
    a dialect carved in Google's stone.

    <url|Click Here> is how links flow,
    not href attributes in a row.
    _Underscores_ lean the text italic,
    ~tildes~ strike through, analytic.

    This docstring screams in warning red
    so future callers aren't misled.
    Cards and messages, spaces wide—
    learn the format, or be denied.

    The adapter pattern helps translate,
    but knowing the rules seals your fate.
    Speak Chat's language, earn your place,
    or watch your formatting fall from grace.

                                        — Field Notes, Jan 2026

═══════════════════════════════════════════════════════════════════════════════
"""

import asyncio
import json

from fastmcp import FastMCP
from googleapiclient.errors import HttpError
from pydantic import Field
from typing_extensions import Annotated, Any, Dict, List, Literal, Optional

from auth.context import get_injected_service
from auth.service_helpers import get_service, request_service
from config.enhanced_logging import setup_logger
from config.settings import settings
from resources.user_resources import get_current_user_email_simple
from tools.common_types import UserGoogleEmail

from .chat_types import (
    ManageSpaceResponse,
    MemberInfo,
    MessageInfo,
    MessageListResponse,
    SearchMessageResult,
    SearchMessagesResponse,
    SendMessageResponse,
    SpaceInfo,
    SpaceListResponse,
)

logger = setup_logger()


def _process_thread_key_for_request(
    request_params: Dict[str, Any], thread_key: Optional[str] = None
) -> None:
    """
    Process thread key for Google Chat API request and update request parameters.

    CRITICAL FIX: This function now correctly handles thread replies by adding the thread
    information to the message BODY (not just as query parameters).

    According to Google Chat API documentation, to reply to an existing thread, you must:
    1. Include 'thread.name' in the request body with the full thread path
    2. Add 'messageReplyOption' as a query parameter

    Args:
        request_params: Dictionary of request parameters to modify in-place
        thread_key: Optional thread key (can be full resource name or just thread ID)
    """
    if thread_key:
        # Use the full thread path as provided
        # The thread_key should be in format: "spaces/{space}/threads/{threadId}"
        thread_path = thread_key

        # CRITICAL FIX: Add thread to the message body (this is what was missing!)
        if "body" in request_params:
            request_params["body"]["thread"] = {"name": thread_path}

        # Add query parameter for message reply option
        request_params["messageReplyOption"] = "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"

        logger.debug(f"Thread reply configured: thread_path={thread_path}")
        logger.debug(
            f"Request params updated with thread in body: {request_params.get('body', {}).get('thread')}"
        )


def _process_thread_key_for_webhook_url(
    webhook_url: str, thread_key: Optional[str] = None
) -> str:
    """
    Process thread key for Google Chat webhook URL and append thread parameters.

    This function handles the correct thread reply implementation for webhook URLs by:
    1. Extracting the thread ID from full resource name format
    2. Appending threadKey and messageReplyOption as query parameters

    Args:
        webhook_url: The original webhook URL
        thread_key: Optional thread key (can be full resource name or just thread ID)

    Returns:
        Modified webhook URL with thread parameters appended
    """
    if not thread_key:
        return webhook_url

    # Extract thread ID from the full thread resource name
    # Format: "spaces/{space}/threads/{threadId}" -> use just the threadId
    if "threads/" in thread_key:
        thread_id = thread_key.split("threads/")[-1]
    else:
        thread_id = thread_key

    # Determine URL separator (& if already has query params, ? if not)
    separator = "&" if "?" in webhook_url else "?"

    # Append thread parameters to webhook URL
    threaded_webhook_url = f"{webhook_url}{separator}threadKey={thread_id}&messageReplyOption=REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"

    logger.debug(f"Webhook thread key processed: {thread_key} -> {thread_id}")
    logger.debug(f"Webhook URL updated: {webhook_url} -> {threaded_webhook_url}")

    return threaded_webhook_url


def _build_chat_from_sa_info(sa_info: dict, user_google_email: str = None):
    """Build a Chat service from a parsed service account JSON dict.

    Tries DWD delegation first, falls back to app-level auth.
    """
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    from auth.scope_registry import ScopeRegistry

    scopes = ScopeRegistry.resolve_scope_group("chat_app")
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=scopes
    )

    if user_google_email:
        try:
            delegated = creds.with_subject(user_google_email)
            svc = build("chat", "v1", credentials=delegated)
            logger.info(
                f"Built Chat service with delegated auth for {user_google_email}"
            )
            return svc
        except Exception as e:
            logger.debug(
                f"Delegated auth failed for {user_google_email}, using app-level: {e}"
            )

    svc = build("chat", "v1", credentials=creds)
    logger.info("Built Chat service from SA info (app-level)")
    return svc


def _get_chat_service_account(user_google_email: str = None):
    """Build a Chat service using per-user encrypted SA or global SA file.

    Priority:
      1. Per-user encrypted Chat SA (from OAuth consent screen upload)
      2. Global CHAT_SERVICE_ACCOUNT_FILE env var

    Uses ``chat_app`` scope group from ``ScopeRegistry``.  When
    ``user_google_email`` is provided, tries domain-wide delegation.

    Returns:
        Authenticated Google Chat service instance or None if unavailable/unconfigured.
    """
    # 1. Try per-user encrypted SA
    if user_google_email:
        try:
            from auth.context import (
                get_auth_middleware,
                get_session_data,
                list_sessions,
            )
            from auth.types import SessionKey

            # Check session cache first
            for sid in reversed(list_sessions()):
                cached = get_session_data(sid, SessionKey.CHAT_SERVICE_ACCOUNT_JSON)
                if cached and isinstance(cached, dict):
                    logger.info("Using cached per-user Chat SA from session")
                    return _build_chat_from_sa_info(cached, user_google_email)

            # Try loading from encrypted file
            auth_middleware = get_auth_middleware()
            if auth_middleware:
                per_user_key = None
                google_sub = None
                for sid in reversed(list_sessions()):
                    per_user_key = per_user_key or get_session_data(
                        sid, SessionKey.PER_USER_ENCRYPTION_KEY
                    )
                    google_sub = google_sub or get_session_data(
                        sid, SessionKey.GOOGLE_SUB
                    )
                    if per_user_key:
                        break

                sa_info = auth_middleware.load_chat_service_account(
                    user_google_email,
                    per_user_key=per_user_key,
                    google_sub=google_sub,
                )
                if sa_info:
                    # Cache in session for subsequent calls
                    for sid in reversed(list_sessions()):
                        from auth.context import store_session_data

                        store_session_data(
                            sid, SessionKey.CHAT_SERVICE_ACCOUNT_JSON, sa_info
                        )
                        break
                    logger.info("Using per-user encrypted Chat SA")
                    return _build_chat_from_sa_info(sa_info, user_google_email)
        except Exception as e:
            logger.debug(f"Per-user Chat SA lookup failed: {e}")

    # 2. Fall back to global SA file
    sa_file = settings.chat_service_account_file
    if not sa_file:
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        from auth.scope_registry import ScopeRegistry

        scopes = ScopeRegistry.resolve_scope_group("chat_app")
        creds = service_account.Credentials.from_service_account_file(
            sa_file, scopes=scopes
        )

        if user_google_email:
            try:
                delegated_creds = creds.with_subject(user_google_email)
                service = build("chat", "v1", credentials=delegated_creds)
                logger.info(
                    f"Built Chat service with delegated auth for {user_google_email}"
                )
                return service
            except Exception as e:
                logger.debug(
                    f"Delegated auth failed for {user_google_email}, using app-level: {e}"
                )

        service = build("chat", "v1", credentials=creds)
        logger.info(f"Built Chat service from global SA (app-level): {sa_file}")
        return service
    except Exception as e:
        logger.warning(f"Failed to build Chat service from global SA: {e}")
        return None


async def _get_chat_service_with_fallback(user_google_email: UserGoogleEmail):
    """
    Get Google Chat service with fallback chain:
      1. Service account file (CHAT_SERVICE_ACCOUNT_FILE) — preferred for Workspace Chat API
      2. Middleware injection (OAuth)
      3. Direct service creation (OAuth)

    Args:
        user_google_email: User's Google email address

    Returns:
        Authenticated Google Chat service instance or None if unavailable
    """
    # Prefer service account when configured (Chat API requires Workspace / Chat app)
    # Pass user email for delegated auth (enables reading messages etc.)
    sa_service = _get_chat_service_account(user_google_email)
    if sa_service:
        logger.info("Using Chat service account (CHAT_SERVICE_ACCOUNT_FILE)")
        return sa_service

    # Otherwise, try middleware injection
    service_key = await request_service("chat")

    try:
        # Try to get the injected service from middleware
        chat_service = await get_injected_service(service_key)
        logger.info(
            f"Successfully retrieved injected Chat service for {user_google_email}"
        )
        return chat_service

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
                # Use the same helper function pattern as Gmail
                chat_service = await get_service("chat", user_google_email)
                logger.info(
                    f"Successfully created Chat service directly for {user_google_email}"
                )
                return chat_service

            except Exception as direct_error:
                logger.error(
                    f"Direct Chat service creation failed for {user_google_email}: {direct_error}"
                )
        else:
            # Different type of RuntimeError, log and return None
            logger.error(f"Chat service injection error for {user_google_email}: {e}")

    except Exception as e:
        logger.error(
            f"Unexpected error getting Chat service for {user_google_email}: {e}"
        )

    return None


async def _send_text_message_helper(
    space_id: str,
    message_text: str,
    thread_key: Optional[str] = None,
    user_google_email: UserGoogleEmail = None,
) -> str:
    """
    Helper function to send a text message to Google Chat.
    Can be called by other functions within the module.
    """
    try:
        chat_service = await _get_chat_service_with_fallback(user_google_email)

        if chat_service is None:
            error_msg = f"❌ Failed to create Google Chat service for {user_google_email}. Please check your credentials and permissions."
            logger.error(f"[_send_text_message_helper] {error_msg}")
            return error_msg

        message_body = {"text": message_text}

        # Add thread key if provided (for threaded replies)
        request_params = {"parent": space_id, "body": message_body}
        _process_thread_key_for_request(request_params, thread_key)

        message = await asyncio.to_thread(
            chat_service.spaces().messages().create(**request_params).execute
        )

        message_name = message.get("name", "")
        create_time = message.get("createTime", "")

        msg = f"Message sent to space '{space_id}' by {user_google_email}. Message ID: {message_name}, Time: {create_time}"
        logger.info(
            f"Successfully sent message to space '{space_id}' by {user_google_email}"
        )
        return msg

    except HttpError as e:
        error_msg = f"❌ Failed to send message: {e}"
        logger.error(f"[_send_text_message_helper] HTTP error: {e}")
        return error_msg
    except Exception as e:
        error_msg = f"❌ Unexpected error: {str(e)}"
        logger.error(f"[_send_text_message_helper] {error_msg}")
        return error_msg


def setup_chat_tools(mcp: FastMCP) -> None:
    """
    Setup and register all Google Chat tools with the MCP server.

    Args:
        mcp: The FastMCP server instance to register tools with
    """
    logger.info("Setting up Google Chat tools")

    @mcp.tool(
        name="list_spaces",
        description="Lists Google Chat spaces (rooms and direct messages) accessible to the user",
        tags={"chat", "spaces", "list", "google"},
        annotations={
            "title": "List Chat Spaces",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def list_spaces(
        page_size: int = 100,
        space_type: str = "all",  # "all", "room", "dm"
        user_google_email: UserGoogleEmail = None,
    ) -> SpaceListResponse:
        """
        Lists Google Chat spaces (rooms and direct messages) accessible to the user.

        🎯 ENHANCED: Gets user email automatically from resources if not provided!
        user_google_email parameter is now optional.

        Args:
            user_google_email (str): The user's Google email address (optional - will auto-detect if not provided).
            page_size (int): Number of spaces to return (default: 100).
            space_type (str): Filter by space type: "all", "room", or "dm" (default: "all").

        Returns:
            SpaceListResponse: Structured list of Chat spaces with metadata.
        """
        try:
            # 🎯 Multi-method email detection
            user_email = None
            auth_method = "unknown"

            # Method 1: Use provided email if given
            if user_google_email and user_google_email.strip():
                user_email = user_google_email.strip()
                auth_method = "provided_parameter"
                logger.info(f"🎯 [list_spaces] Using provided email: {user_email}")

            # Method 2: Try resource context (primary method)
            if not user_email:
                try:
                    user_email = get_current_user_email_simple()
                    auth_method = "resource_context"
                    logger.info(
                        f"🎯 [list_spaces] Got email from resource context: {user_email}"
                    )
                except ValueError:
                    logger.info("🎯 [list_spaces] No resource context available")

            # Final check
            if not user_email:
                return SpaceListResponse(
                    spaces=[],
                    count=0,
                    spaceType=space_type,
                    userEmail="unknown",
                    error="Authentication error: Could not determine user email. Please provide user_google_email parameter or ensure proper authentication is set up.",
                )

            logger.info(
                f"🎯 [list_spaces] Using email: {user_email} (method: {auth_method}), Type={space_type}"
            )

            chat_service = await _get_chat_service_with_fallback(user_email)

            if chat_service is None:
                error_msg = f"Failed to create Google Chat service for {user_email}. Please check your credentials and permissions."
                logger.error(f"[list_spaces] {error_msg}")
                return SpaceListResponse(
                    spaces=[],
                    count=0,
                    spaceType=space_type,
                    userEmail=user_email,
                    error=error_msg,
                )

            # Build filter based on space_type
            filter_param = None
            if space_type == "room":
                filter_param = "spaceType = SPACE"
            elif space_type == "dm":
                filter_param = "spaceType = DIRECT_MESSAGE"

            request_params = {"pageSize": page_size}
            if filter_param:
                request_params["filter"] = filter_param

            response = await asyncio.to_thread(
                chat_service.spaces().list(**request_params).execute
            )

            items = response.get("spaces", [])

            # Convert to structured format
            spaces: List[SpaceInfo] = []
            for space in items:
                space_info: SpaceInfo = {
                    "id": space.get("name", ""),
                    "displayName": space.get("displayName", "Unnamed Space"),
                    "spaceType": space.get("spaceType", "UNKNOWN"),
                    "singleUserBotDm": space.get("singleUserBotDm"),
                    "threaded": space.get("threaded"),
                    "spaceHistoryState": space.get("spaceHistoryState"),
                }
                spaces.append(space_info)

            logger.info(
                f"Found {len(spaces)} Chat spaces (type: {space_type}) for {user_email}"
            )

            return SpaceListResponse(
                spaces=spaces,
                count=len(spaces),
                spaceType=space_type,
                userEmail=user_email,
                error=None,
            )

        except HttpError as e:
            error_msg = f"Failed to list spaces: {e}"
            logger.error(f"[list_spaces] HTTP error: {e}")
            return SpaceListResponse(
                spaces=[],
                count=0,
                spaceType=space_type,
                userEmail=user_google_email or "unknown",
                error=error_msg,
            )
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"[list_spaces] {error_msg}")
            return SpaceListResponse(
                spaces=[],
                count=0,
                spaceType=space_type,
                userEmail=user_google_email or "unknown",
                error=error_msg,
            )

    @mcp.tool(
        name="list_messages",
        description="Lists messages from a Google Chat space",
        tags={"chat", "messages", "list", "google"},
        annotations={
            "title": "List Chat Messages",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def list_messages(
        space_id: str,
        page_size: int = 50,
        order_by: str = "createTime desc",
        user_google_email: UserGoogleEmail = None,
    ) -> MessageListResponse:
        """
        Lists messages from a Google Chat space.

        Args:
            user_google_email (str): The user's Google email address. Required.
            space_id (str): The ID of the Chat space. Required.
            page_size (int): Number of messages to return (default: 50).
            order_by (str): Sort order for messages (default: "createTime desc").

        Returns:
            MessageListResponse: Structured list of messages with metadata.
        """
        logger.info(
            f"[list_messages] Space ID: '{space_id}' for user '{user_google_email}'"
        )

        try:
            chat_service = await _get_chat_service_with_fallback(user_google_email)

            # Get space info first
            space_info = await asyncio.to_thread(
                chat_service.spaces().get(name=space_id).execute
            )
            space_name = space_info.get("displayName", "Unknown Space")

            # Get messages
            response = await asyncio.to_thread(
                chat_service.spaces()
                .messages()
                .list(parent=space_id, pageSize=page_size, orderBy=order_by)
                .execute
            )

            items = response.get("messages", [])

            # Convert to structured format with enriched sender information
            messages: List[MessageInfo] = []

            # Collect unique sender IDs for batch lookup
            sender_ids = set()
            for msg in items:
                sender = msg.get("sender", {})
                sender_id = sender.get("name")
                if sender_id and sender_id.startswith("users/"):
                    sender_ids.add(sender_id)

            # Fetch sender details in batch if we have any IDs
            sender_details_cache = {}
            if sender_ids:
                logger.info(
                    f"🔍 Fetching member details for {len(sender_ids)} unique senders..."
                )
                for sender_id in sender_ids:
                    try:
                        # Extract just the numeric ID from "users/12345" format
                        member_id = (
                            sender_id.split("/")[-1] if "/" in sender_id else sender_id
                        )
                        # Correct format: spaces/{space}/members/{numericId}
                        member_resource_name = f"{space_id}/members/{member_id}"
                        logger.debug(
                            f"📝 Fetching member: {member_resource_name} (from sender_id: {sender_id})"
                        )

                        member_info = await asyncio.to_thread(
                            chat_service.spaces()
                            .members()
                            .get(name=member_resource_name)
                            .execute
                        )

                        # DEBUG: Log the full API response to see what data is available
                        logger.info(f"📊 API Response for {member_resource_name}:")
                        logger.info(f"   Response keys: {list(member_info.keys())}")
                        logger.info(
                            f"   Full response: {json.dumps(member_info, indent=2, default=str)}"
                        )

                        # Extract user information from member response
                        member_data = member_info.get("member", {})
                        logger.info(
                            f"   member_data keys: {list(member_data.keys()) if member_data else 'None'}"
                        )

                        display_name = (
                            member_data.get("displayName")
                            or member_info.get("displayName")
                            or member_data.get("name", "Unknown User")
                        )
                        email = member_data.get("email") or member_info.get("email")

                        sender_details_cache[sender_id] = {
                            "displayName": display_name,
                            "email": email,
                        }
                        logger.info(
                            f"✅ Extracted - {sender_id}: {display_name} ({email or 'no email'})"
                        )

                    except HttpError as http_err:
                        logger.warning(
                            f"❌ HTTP error fetching member {sender_id}: {http_err}"
                        )
                        sender_details_cache[sender_id] = {
                            "displayName": sender_id,
                            "email": None,
                        }
                    except Exception as e:
                        logger.warning(
                            f"❌ Could not fetch member details for {sender_id}: {e}"
                        )
                        sender_details_cache[sender_id] = {
                            "displayName": sender_id,
                            "email": None,
                        }

            # Process messages with enriched sender data
            for msg in items:
                sender = msg.get("sender", {})
                sender_id = sender.get("name", "")

                # Use cached sender details if available
                if sender_id in sender_details_cache:
                    sender_name = sender_details_cache[sender_id]["displayName"]
                    sender_email = sender_details_cache[sender_id]["email"]
                else:
                    # Fallback to original extraction
                    sender_name = (
                        sender.get("displayName") or sender_id or "Unknown Sender"
                    )
                    sender_email = (
                        sender.get("email")
                        or sender.get("emailAddress")
                        or sender.get("user", {}).get("email")
                    )

                message_info: MessageInfo = {
                    "id": msg.get("name", ""),
                    "text": msg.get("text", "No text content"),
                    "senderName": sender_name,
                    "senderEmail": sender_email,
                    "createTime": msg.get("createTime", "Unknown Time"),
                    "threadId": (
                        msg.get("thread", {}).get("name") if "thread" in msg else None
                    ),
                    "spaceName": space_name,
                    "attachments": (
                        msg.get("attachment") if "attachment" in msg else None
                    ),
                }
                messages.append(message_info)

            logger.info(
                f"Retrieved {len(messages)} messages from space '{space_name}' for {user_google_email}"
            )

            return MessageListResponse(
                messages=messages,
                count=len(messages),
                spaceId=space_id,
                spaceName=space_name,
                orderBy=order_by,
                userEmail=user_google_email,
                error=None,
            )

        except HttpError as e:
            error_msg = f"Failed to list messages: {e}"
            logger.error(f"[list_messages] HTTP error: {e}")
            return MessageListResponse(
                messages=[],
                count=0,
                spaceId=space_id,
                spaceName="Unknown Space",
                orderBy=order_by,
                userEmail=user_google_email,
                error=error_msg,
            )
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"[list_messages] {error_msg}")
            return MessageListResponse(
                messages=[],
                count=0,
                spaceId=space_id,
                spaceName="Unknown Space",
                orderBy=order_by,
                userEmail=user_google_email,
                error=error_msg,
            )

    @mcp.tool(
        name="send_message",
        description="Sends a message to a Google Chat space with full markdown formatting support",
        tags={"chat", "message", "send", "google", "markdown", "formatting"},
        annotations={
            "title": "Send Chat Message",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def send_message(
        space_id: str,
        message_text: str,
        thread_key: Optional[str] = None,
        user_google_email: UserGoogleEmail = None,
    ) -> SendMessageResponse:
        """
        Sends a message to a Google Chat space with full markdown formatting support.

        🚨 MARKDOWN FORMAT: Google Chat uses SPECIFIC markdown syntax!

        ✅ SUPPORTED FORMATS:
          - *Bold*: `*text*` → displays as bold
          - _Italic_: `_text_` → displays as italic
          - ~Strikethrough~: `~text~` → displays as strikethrough
          - `Monospace`: backticks → displays as code
          - Bulleted lists: `* item` or `- item`
          - Custom links: `<https://example.com|Display Text>`
          - User mentions: `<users/{user_id}>`
          - Code blocks: triple backticks (```)

        ❌ DO NOT USE:
          - HTML tags: <b>, <i>, <a>, etc. (display as literal text!)
          - Standard markdown: **, __, etc. (do not render!)

        Args:
            space_id (str): Chat space ID (format: "spaces/{id}"). Required.
            message_text (str): Message content with Google Chat markdown. Max ~4096 chars. Required.
            thread_key (Optional[str]): Thread key for replies. Creates new thread if None.
            user_google_email (str): Google email for authentication. Required.

        Returns:
            SendMessageResponse: Structured response with message details and success status.
        """
        logger.info(f"[send_message] Email: '{user_google_email}', Space: '{space_id}'")

        try:
            chat_service = await _get_chat_service_with_fallback(user_google_email)

            if chat_service is None:
                return SendMessageResponse(
                    success=False,
                    messageId=None,
                    spaceId=space_id,
                    messageText=message_text,
                    threadKey=thread_key,
                    createTime=None,
                    userEmail=user_google_email,
                    message="Failed to create Google Chat service. Please check your credentials and permissions.",
                    error="Service unavailable",
                )

            message_body = {"text": message_text}

            request_params = {"parent": space_id, "body": message_body}

            # Process thread key for proper reply handling
            _process_thread_key_for_request(request_params, thread_key)

            message = await asyncio.to_thread(
                chat_service.spaces().messages().create(**request_params).execute
            )

            message_name = message.get("name", "")
            create_time = message.get("createTime", "")

            return SendMessageResponse(
                success=True,
                messageId=message_name,
                spaceId=space_id,
                messageText=message_text,
                threadKey=thread_key,
                createTime=create_time,
                userEmail=user_google_email,
                message=f"Message sent to space '{space_id}' by {user_google_email}. Message ID: {message_name}",
                error=None,
            )

        except HttpError as e:
            logger.error(f"[send_message] HTTP error: {e}")
            return SendMessageResponse(
                success=False,
                messageId=None,
                spaceId=space_id,
                messageText=message_text,
                threadKey=thread_key,
                createTime=None,
                userEmail=user_google_email,
                message=f"Failed to send message: {e}",
                error=str(e),
            )
        except Exception as e:
            logger.error(f"[send_message] {str(e)}")
            return SendMessageResponse(
                success=False,
                messageId=None,
                spaceId=space_id,
                messageText=message_text,
                threadKey=thread_key,
                createTime=None,
                userEmail=user_google_email,
                message=f"Unexpected error: {str(e)}",
                error=str(e),
            )

    @mcp.tool(
        name="search_messages",
        description="Searches for messages in Google Chat spaces by text content",
        tags={"chat", "search", "messages", "google"},
        annotations={
            "title": "Search Chat Messages",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def search_messages(
        query: str,
        space_id: Optional[str] = None,
        user_google_email: UserGoogleEmail = None,
        page_size: int = 25,
    ) -> SearchMessagesResponse:
        """
        Searches for messages in Google Chat spaces by text content.

        Args:
            user_google_email (str): The user's Google email address. Required.
            query (str): The search query. Required.
            space_id (Optional[str]): Search within a specific space ID (default: search all).
            page_size (int): Number of results per space (default: 25).

        Returns:
            SearchMessagesResponse: Structured response with search results.
        """
        logger.info(f"[search_messages] Email={user_google_email}, Query='{query}'")

        try:
            chat_service = await _get_chat_service_with_fallback(user_google_email)

            if chat_service is None:
                return SearchMessagesResponse(
                    success=False,
                    query=query,
                    results=[],
                    totalResults=0,
                    searchScope="unknown",
                    spaceId=space_id,
                    userEmail=user_google_email,
                    message="Failed to create Google Chat service. Please check your credentials and permissions.",
                    error="Service unavailable",
                )

            search_results: List[SearchMessageResult] = []

            # If specific space provided, search within that space
            if space_id:
                response = await asyncio.to_thread(
                    chat_service.spaces()
                    .messages()
                    .list(parent=space_id, pageSize=page_size, filter=f'text:"{query}"')
                    .execute
                )
                messages = response.get("messages", [])
                search_scope = "specific_space"

                for msg in messages:
                    result = SearchMessageResult(
                        messageId=msg.get("name", ""),
                        text=msg.get("text", "No text content"),
                        senderName=msg.get("sender", {}).get(
                            "displayName", "Unknown Sender"
                        ),
                        createTime=msg.get("createTime", "Unknown Time"),
                        spaceName="Current Space",  # We don't have space name in this context
                        spaceId=space_id,
                    )
                    search_results.append(result)
            else:
                # Search across all accessible spaces
                spaces_response = await asyncio.to_thread(
                    chat_service.spaces().list(pageSize=100).execute
                )
                spaces = spaces_response.get("spaces", [])
                search_scope = "all_spaces"

                for space in spaces[:10]:  # Limit to first 10 spaces to avoid timeout
                    try:
                        space_messages = await asyncio.to_thread(
                            chat_service.spaces()
                            .messages()
                            .list(
                                parent=space.get("name"),
                                pageSize=5,
                                filter=f'text:"{query}"',
                            )
                            .execute
                        )
                        space_msgs = space_messages.get("messages", [])
                        space_name = space.get("displayName", "Unknown Space")

                        for msg in space_msgs:
                            result = SearchMessageResult(
                                messageId=msg.get("name", ""),
                                text=msg.get("text", "No text content"),
                                senderName=msg.get("sender", {}).get(
                                    "displayName", "Unknown Sender"
                                ),
                                createTime=msg.get("createTime", "Unknown Time"),
                                spaceName=space_name,
                                spaceId=space.get("name", ""),
                            )
                            search_results.append(result)
                    except HttpError:
                        continue  # Skip spaces we can't access

            return SearchMessagesResponse(
                success=True,
                query=query,
                results=search_results,
                totalResults=len(search_results),
                searchScope=search_scope,
                spaceId=space_id,
                userEmail=user_google_email,
                message=f"Found {len(search_results)} messages matching '{query}' in {search_scope.replace('_', ' ')}",
                error=None,
            )

        except HttpError as e:
            logger.error(f"[search_messages] HTTP error: {e}")
            return SearchMessagesResponse(
                success=False,
                query=query,
                results=[],
                totalResults=0,
                searchScope="unknown",
                spaceId=space_id,
                userEmail=user_google_email,
                message=f"Failed to search messages: {e}",
                error=str(e),
            )
        except Exception as e:
            logger.error(f"[search_messages] {str(e)}")
            return SearchMessagesResponse(
                success=False,
                query=query,
                results=[],
                totalResults=0,
                searchScope="unknown",
                spaceId=space_id,
                userEmail=user_google_email,
                message=f"Unexpected error: {str(e)}",
                error=str(e),
            )

    @mcp.tool(
        name="manage_space",
        description="Unified tool for Google Chat space administration: manage members, create/update/delete spaces",
        tags={"chat", "spaces", "members", "management"},
        annotations={
            "title": "Manage Chat Space",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def manage_space(
        action: Annotated[
            Literal[
                "list_members",
                "add_member",
                "remove_member",
                "create_space",
                "update_space",
                "delete_space",
                "get_message",
                "update_message",
                "delete_message",
                "add_reaction",
                "list_reactions",
                "delete_reaction",
            ],
            Field(
                description=(
                    "Action to perform. Space/member actions: 'list_members', 'add_member', "
                    "'remove_member', 'create_space', 'update_space', 'delete_space'. "
                    "Message actions: 'get_message', 'update_message', 'delete_message'. "
                    "Reaction actions (require delegated user auth): 'add_reaction', "
                    "'list_reactions', 'delete_reaction'."
                )
            ),
        ],
        space_id: Annotated[
            Optional[str],
            Field(
                description="Space resource name (e.g., 'spaces/AAQAKl_yP9Y'). Required for list_members, add_member, update_space, delete_space."
            ),
        ] = None,
        member_email: Annotated[
            Optional[str],
            Field(
                description="Email address of the member to add. Required for add_member."
            ),
        ] = None,
        member_role: Annotated[
            Optional[Literal["ROLE_MEMBER", "ROLE_MANAGER"]],
            Field(description="Role for the member. Default: ROLE_MEMBER."),
        ] = None,
        member_name: Annotated[
            Optional[str],
            Field(
                description="Full member resource name (e.g., 'spaces/xxx/members/yyy'). Required for remove_member."
            ),
        ] = None,
        display_name: Annotated[
            Optional[str],
            Field(description="Display name for create_space or update_space."),
        ] = None,
        space_type: Annotated[
            Optional[Literal["SPACE", "GROUP_CHAT"]],
            Field(description="Type of space to create. Default: SPACE."),
        ] = None,
        description: Annotated[
            Optional[str],
            Field(description="Description for create_space or update_space."),
        ] = None,
        message_name: Annotated[
            Optional[str],
            Field(
                description="Full message resource name (e.g., 'spaces/xxx/messages/yyy'). Required for get/update/delete_message and reaction actions."
            ),
        ] = None,
        message_text: Annotated[
            Optional[str],
            Field(
                description="New message text for update_message. Supports @mentions via <users/email> format."
            ),
        ] = None,
        emoji: Annotated[
            Optional[str],
            Field(
                description="Unicode emoji for add_reaction (e.g., '\U0001f680', '\U0001f44d')."
            ),
        ] = None,
        reaction_name: Annotated[
            Optional[str],
            Field(
                description="Full reaction resource name (e.g., 'spaces/xxx/messages/yyy/reactions/zzz'). Required for delete_reaction."
            ),
        ] = None,
        user_google_email: UserGoogleEmail = None,
    ) -> ManageSpaceResponse:
        """
        Unified tool for Google Chat space administration, message operations, and reactions.

        Supports the following actions:
        - list_members: List all members of a space
        - add_member: Add a member to a space
        - remove_member: Remove a member from a space
        - create_space: Create a new space
        - update_space: Update an existing space
        - delete_space: Delete a space
        - get_message: Retrieve a single message by resource name
        - update_message: Edit message text (app can only edit its own messages)
        - delete_message: Delete a message (app can only delete its own messages)
        - add_reaction: Add an emoji reaction to a message (requires delegated user auth)
        - list_reactions: List reactions on a message (requires delegated user auth)
        - delete_reaction: Remove a reaction (requires delegated user auth)

        Args:
            action: The action to perform.
            space_id: Space resource name. Required for space/member actions.
            member_email: Email of member to add. Required for add_member.
            member_role: Role for the member (ROLE_MEMBER or ROLE_MANAGER).
            member_name: Full member resource name. Required for remove_member.
            display_name: Display name for create_space or update_space.
            space_type: Type of space to create (SPACE or GROUP_CHAT).
            description: Description for create_space or update_space.
            message_name: Full message resource name. Required for message/reaction actions.
            message_text: New message text for update_message.
            emoji: Unicode emoji for add_reaction.
            reaction_name: Full reaction resource name. Required for delete_reaction.
            user_google_email: User's Google email for authentication.

        Returns:
            ManageSpaceResponse with operation result.
        """
        logger.info(
            f"[manage_space] action={action}, space_id={space_id}, user={user_google_email}"
        )

        try:
            if action == "list_members":
                if not space_id:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="space_id is required for list_members",
                        error="Missing parameter: space_id",
                    )

                chat_service = await _get_chat_service_with_fallback(user_google_email)
                if chat_service is None:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=space_id,
                        data=None,
                        message="Failed to create Chat service",
                        error="Service unavailable",
                    )

                response = await asyncio.to_thread(
                    chat_service.spaces()
                    .members()
                    .list(parent=space_id, pageSize=100)
                    .execute
                )
                memberships = response.get("memberships", [])
                members = []
                for m in memberships:
                    member_data = m.get("member", {})
                    members.append(
                        MemberInfo(
                            name=m.get("name", ""),
                            email=member_data.get("email"),
                            displayName=member_data.get("displayName", "Unknown"),
                            role=m.get("role", "ROLE_MEMBER"),
                            type=member_data.get("type", "HUMAN"),
                            createTime=m.get("createTime"),
                        )
                    )
                return ManageSpaceResponse(
                    success=True,
                    action=action,
                    spaceId=space_id,
                    data={
                        "members": [dict(mem) for mem in members],
                        "count": len(members),
                    },
                    message=f"Found {len(members)} members in {space_id}",
                )

            elif action == "add_member":
                if not space_id:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="space_id is required for add_member",
                        error="Missing parameter: space_id",
                    )
                if not member_email:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=space_id,
                        data=None,
                        message="member_email is required for add_member",
                        error="Missing parameter: member_email",
                    )

                chat_service = await _get_chat_service_with_fallback(user_google_email)
                if chat_service is None:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=space_id,
                        data=None,
                        message="Failed to create Chat service",
                        error="Service unavailable",
                    )

                membership_body = {
                    "member": {
                        "name": f"users/{member_email}",
                        "type": "HUMAN",
                    },
                    "role": member_role or "ROLE_MEMBER",
                }
                result = await asyncio.to_thread(
                    chat_service.spaces()
                    .members()
                    .create(parent=space_id, body=membership_body)
                    .execute
                )
                return ManageSpaceResponse(
                    success=True,
                    action=action,
                    spaceId=space_id,
                    data={"membership": result},
                    message=f"Added {member_email} to {space_id} as {member_role or 'ROLE_MEMBER'}",
                )

            elif action == "remove_member":
                if not member_name:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="member_name is required for remove_member",
                        error="Missing parameter: member_name",
                    )

                chat_service = await _get_chat_service_with_fallback(user_google_email)
                if chat_service is None:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="Failed to create Chat service",
                        error="Service unavailable",
                    )

                await asyncio.to_thread(
                    chat_service.spaces().members().delete(name=member_name).execute
                )
                return ManageSpaceResponse(
                    success=True,
                    action=action,
                    spaceId=None,
                    data={"removedMember": member_name},
                    message=f"Removed member {member_name}",
                )

            elif action == "create_space":
                if not display_name:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="display_name is required for create_space",
                        error="Missing parameter: display_name",
                    )

                chat_service = await _get_chat_service_with_fallback(user_google_email)
                if chat_service is None:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="Failed to create Chat service",
                        error="Service unavailable",
                    )

                space_body = {
                    "displayName": display_name,
                    "spaceType": space_type or "SPACE",
                }
                if description:
                    space_body["spaceDetails"] = {"description": description}

                # Service account auth requires customer ID in the body.
                # Resolve it from an existing named space.
                try:
                    existing = await asyncio.to_thread(
                        chat_service.spaces().list(pageSize=10).execute
                    )
                    for sp in existing.get("spaces", []):
                        customer = sp.get("customer")
                        if customer:
                            space_body["customer"] = customer
                            logger.info(
                                f"Resolved customer for create_space: {customer}"
                            )
                            break
                    else:
                        # DM spaces lack customer — fetch a named space's detail
                        for sp in existing.get("spaces", []):
                            if sp.get("spaceType") == "SPACE":
                                detail = await asyncio.to_thread(
                                    chat_service.spaces().get(name=sp["name"]).execute
                                )
                                customer = detail.get("customer")
                                if customer:
                                    space_body["customer"] = customer
                                    logger.info(
                                        f"Resolved customer from space detail: {customer}"
                                    )
                                    break
                except Exception as e:
                    logger.warning(f"Could not resolve customer ID: {e}")

                result = await asyncio.to_thread(
                    chat_service.spaces().create(body=space_body).execute
                )
                new_space_id = result.get("name", "")

                # Auto-add the requesting user as ROLE_MANAGER so they can access
                added_user = None
                if user_google_email and new_space_id:
                    try:
                        membership_body = {
                            "member": {
                                "name": f"users/{user_google_email}",
                                "type": "HUMAN",
                            },
                            "role": "ROLE_MANAGER",
                        }
                        await asyncio.to_thread(
                            chat_service.spaces()
                            .members()
                            .create(parent=new_space_id, body=membership_body)
                            .execute
                        )
                        added_user = user_google_email
                        logger.info(
                            f"Auto-added {user_google_email} as ROLE_MANAGER to {new_space_id}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Could not auto-add {user_google_email} to new space: {e}"
                        )

                return ManageSpaceResponse(
                    success=True,
                    action=action,
                    spaceId=new_space_id,
                    data={"space": result, "addedUser": added_user},
                    message=f"Created space '{display_name}' ({new_space_id})",
                )

            elif action == "update_space":
                if not space_id:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="space_id is required for update_space",
                        error="Missing parameter: space_id",
                    )
                if not display_name and not description:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=space_id,
                        data=None,
                        message="At least one of display_name or description is required for update_space",
                        error="Missing parameter",
                    )

                chat_service = await _get_chat_service_with_fallback(user_google_email)
                if chat_service is None:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=space_id,
                        data=None,
                        message="Failed to create Chat service",
                        error="Service unavailable",
                    )

                update_body = {}
                update_mask_fields = []
                if display_name:
                    update_body["displayName"] = display_name
                    update_mask_fields.append("displayName")
                if description:
                    update_body.setdefault("spaceDetails", {})["description"] = (
                        description
                    )
                    update_mask_fields.append("spaceDetails")

                result = await asyncio.to_thread(
                    chat_service.spaces()
                    .patch(
                        name=space_id,
                        updateMask=",".join(update_mask_fields),
                        body=update_body,
                    )
                    .execute
                )
                return ManageSpaceResponse(
                    success=True,
                    action=action,
                    spaceId=space_id,
                    data={"space": result},
                    message=f"Updated space {space_id}",
                )

            elif action == "delete_space":
                if not space_id:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="space_id is required for delete_space",
                        error="Missing parameter: space_id",
                    )

                chat_service = await _get_chat_service_with_fallback(user_google_email)
                if chat_service is None:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=space_id,
                        data=None,
                        message="Failed to create Chat service",
                        error="Service unavailable",
                    )

                await asyncio.to_thread(
                    chat_service.spaces().delete(name=space_id).execute
                )
                return ManageSpaceResponse(
                    success=True,
                    action=action,
                    spaceId=space_id,
                    data=None,
                    message=f"Deleted space {space_id}",
                )

            # ── Message operations ──────────────────────────────────────

            elif action == "get_message":
                if not message_name:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="message_name is required for get_message",
                        error="Missing parameter: message_name",
                    )

                chat_service = await _get_chat_service_with_fallback(user_google_email)
                if chat_service is None:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="Failed to create Chat service",
                        error="Service unavailable",
                    )

                result = await asyncio.to_thread(
                    chat_service.spaces().messages().get(name=message_name).execute
                )
                return ManageSpaceResponse(
                    success=True,
                    action=action,
                    spaceId=result.get("space", {}).get("name"),
                    data={"message": result},
                    message=f"Retrieved message {message_name}",
                )

            elif action == "update_message":
                if not message_name:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="message_name is required for update_message",
                        error="Missing parameter: message_name",
                    )
                if not message_text:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="message_text is required for update_message",
                        error="Missing parameter: message_text",
                    )

                chat_service = await _get_chat_service_with_fallback(user_google_email)
                if chat_service is None:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="Failed to create Chat service",
                        error="Service unavailable",
                    )

                result = await asyncio.to_thread(
                    chat_service.spaces()
                    .messages()
                    .patch(
                        name=message_name,
                        updateMask="text",
                        body={"text": message_text},
                    )
                    .execute
                )
                return ManageSpaceResponse(
                    success=True,
                    action=action,
                    spaceId=result.get("space", {}).get("name"),
                    data={"message": result},
                    message=f"Updated message {message_name}",
                )

            elif action == "delete_message":
                if not message_name:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="message_name is required for delete_message",
                        error="Missing parameter: message_name",
                    )

                chat_service = await _get_chat_service_with_fallback(user_google_email)
                if chat_service is None:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="Failed to create Chat service",
                        error="Service unavailable",
                    )

                await asyncio.to_thread(
                    chat_service.spaces().messages().delete(name=message_name).execute
                )
                return ManageSpaceResponse(
                    success=True,
                    action=action,
                    spaceId=None,
                    data={"deletedMessage": message_name},
                    message=f"Deleted message {message_name}",
                )

            # ── Reaction operations (require delegated user auth) ───────

            elif action == "add_reaction":
                if not message_name:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="message_name is required for add_reaction",
                        error="Missing parameter: message_name",
                    )
                if not emoji:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="emoji is required for add_reaction",
                        error="Missing parameter: emoji",
                    )
                if not user_google_email:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="Reactions require delegated user auth. Provide user_google_email.",
                        error="Reactions require user-level auth (delegated). user_google_email is required.",
                    )

                chat_service = await _get_chat_service_with_fallback(user_google_email)
                if chat_service is None:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="Failed to create Chat service with delegated auth for reactions",
                        error="Service unavailable",
                    )

                result = await asyncio.to_thread(
                    chat_service.spaces()
                    .messages()
                    .reactions()
                    .create(
                        parent=message_name,
                        body={"emoji": {"unicode": emoji}},
                    )
                    .execute
                )
                return ManageSpaceResponse(
                    success=True,
                    action=action,
                    spaceId=None,
                    data={"reaction": result},
                    message=f"Added reaction {emoji} to {message_name}",
                )

            elif action == "list_reactions":
                if not message_name:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="message_name is required for list_reactions",
                        error="Missing parameter: message_name",
                    )
                if not user_google_email:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="Reactions require delegated user auth. Provide user_google_email.",
                        error="Reactions require user-level auth (delegated). user_google_email is required.",
                    )

                chat_service = await _get_chat_service_with_fallback(user_google_email)
                if chat_service is None:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="Failed to create Chat service with delegated auth for reactions",
                        error="Service unavailable",
                    )

                response = await asyncio.to_thread(
                    chat_service.spaces()
                    .messages()
                    .reactions()
                    .list(parent=message_name, pageSize=100)
                    .execute
                )
                reactions = response.get("reactions", [])
                return ManageSpaceResponse(
                    success=True,
                    action=action,
                    spaceId=None,
                    data={"reactions": reactions, "count": len(reactions)},
                    message=f"Found {len(reactions)} reactions on {message_name}",
                )

            elif action == "delete_reaction":
                if not reaction_name:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="reaction_name is required for delete_reaction",
                        error="Missing parameter: reaction_name",
                    )
                if not user_google_email:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="Reactions require delegated user auth. Provide user_google_email.",
                        error="Reactions require user-level auth (delegated). user_google_email is required.",
                    )

                chat_service = await _get_chat_service_with_fallback(user_google_email)
                if chat_service is None:
                    return ManageSpaceResponse(
                        success=False,
                        action=action,
                        spaceId=None,
                        data=None,
                        message="Failed to create Chat service with delegated auth for reactions",
                        error="Service unavailable",
                    )

                await asyncio.to_thread(
                    chat_service.spaces()
                    .messages()
                    .reactions()
                    .delete(name=reaction_name)
                    .execute
                )
                return ManageSpaceResponse(
                    success=True,
                    action=action,
                    spaceId=None,
                    data={"deletedReaction": reaction_name},
                    message=f"Deleted reaction {reaction_name}",
                )

            else:
                return ManageSpaceResponse(
                    success=False,
                    action=action,
                    spaceId=None,
                    data=None,
                    message=f"Unknown action: {action}",
                    error=f"Unsupported action: {action}",
                )

        except HttpError as e:
            logger.error(f"[manage_space] HTTP error: {e}")
            return ManageSpaceResponse(
                success=False,
                action=action,
                spaceId=space_id,
                data=None,
                message=f"Google API error: {e}",
                error=str(e),
            )
        except Exception as e:
            logger.error(f"[manage_space] Unexpected error: {e}")
            return ManageSpaceResponse(
                success=False,
                action=action,
                spaceId=space_id,
                data=None,
                message=f"Unexpected error: {str(e)}",
                error=str(e),
            )

    logger.info(
        "Basic chat tools registered (list_spaces, list_messages, send_message, search_messages, manage_space)"
    )
