"""
Gmail message reading and search tools for FastMCP2.

This module provides tools for:
- Searching Gmail messages using Gmail query syntax
- Retrieving individual message content
- Batch message content retrieval
- Thread content retrieval
- Downloading message attachments
"""

import asyncio
import base64
import os

from fastmcp import FastMCP
from googleapiclient.errors import HttpError
from pydantic import Field
from typing_extensions import Annotated, List, Literal, Optional

from config.enhanced_logging import setup_logger

# Import our custom type for consistent parameter definition
from tools.common_types import UserGoogleEmail

from .gmail_types import (
    BatchMessageResult,
    DownloadGmailAttachmentResponse,
    GetGmailMessageContentResponse,
    GetGmailMessagesBatchResponse,
    GetGmailThreadContentResponse,
    GmailMessageContent,
    GmailMessageInfo,
    SearchGmailMessagesResponse,
    ThreadMessageInfo,
)
from .service import _get_gmail_service_with_fallback
from .utils import (
    _extract_attachment_metadata,
    _extract_headers,
    _extract_message_body,
    _generate_gmail_web_url,
)

logger = setup_logger()


async def search_gmail_messages(
    query: Annotated[
        str,
        Field(
            description="Gmail search query using standard Gmail search operators (e.g., 'from:sender@example.com', 'subject:important')"
        ),
    ],
    user_google_email: UserGoogleEmail = None,
    page_size: Annotated[
        int, Field(description="Maximum number of messages to return", ge=1, le=100)
    ] = 10,
) -> SearchGmailMessagesResponse:
    """
    Searches messages in a user's Gmail account based on a query.
    Returns both Message IDs and Thread IDs for each found message, along with Gmail web interface links for manual verification.

    Args:
        user_google_email: The user's Google email address. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware).
        query: The search query. Supports standard Gmail search operators
        page_size: The maximum number of messages to return (default: 10)

    Returns:
        SearchGmailMessagesResponse: Structured response with message information and metadata
    """
    logger.info(
        f"[search_gmail_messages] Email: '{user_google_email}', Query: '{query}'"
    )

    try:
        # Get Gmail service with fallback support
        gmail_service = await _get_gmail_service_with_fallback(user_google_email)

        response = await asyncio.to_thread(
            gmail_service.users()
            .messages()
            .list(userId="me", q=query, maxResults=page_size)
            .execute
        )
        messages_raw = response.get("messages", [])

        # Fetch labels once so we can resolve label IDs to human-readable names
        labels_response = await asyncio.to_thread(
            gmail_service.users().labels().list(userId="me").execute
        )
        labels_data = labels_response.get("labels", [])
        label_id_to_name = {
            lbl.get("id"): lbl.get("name", lbl.get("id"))
            for lbl in labels_data
            if isinstance(lbl, dict)
        }

        # Convert to structured format
        messages: List[GmailMessageInfo] = []
        for msg_raw in messages_raw:
            msg_id = msg_raw["id"]
            thread_id = msg_raw["threadId"]

            # Try to get basic message info (snippet, subject, sender)
            try:
                msg_metadata = await asyncio.to_thread(
                    gmail_service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=msg_id,
                        format="metadata",
                        metadataHeaders=["Subject", "From", "Date"],
                    )
                    .execute
                )

                headers = _extract_headers(
                    msg_metadata.get("payload", {}), ["Subject", "From", "Date"]
                )
                snippet = msg_metadata.get("snippet", "")
                label_ids = (
                    msg_metadata.get("labelIds", [])
                    or msg_raw.get("labelIds", [])
                    or []
                )
                label_names = [label_id_to_name.get(lid, lid) for lid in label_ids]

                message_info: GmailMessageInfo = {
                    "id": msg_id,
                    "thread_id": thread_id,
                    "snippet": snippet,
                    "subject": headers.get("Subject"),
                    "sender": headers.get("From"),
                    "date": headers.get("Date"),
                    "labels": label_ids,
                    "label_names": label_names,
                    "web_url": _generate_gmail_web_url(msg_id),
                }
            except Exception as e:
                logger.warning(f"Could not get metadata for message {msg_id}: {e}")
                # Fallback with minimal info
                fallback_label_ids = msg_raw.get("labelIds", []) or []
                fallback_label_names = [
                    label_id_to_name.get(lid, lid) for lid in fallback_label_ids
                ]

                message_info: GmailMessageInfo = {
                    "id": msg_id,
                    "thread_id": thread_id,
                    "labels": fallback_label_ids,
                    "label_names": fallback_label_names,
                    "web_url": _generate_gmail_web_url(msg_id),
                }

            messages.append(message_info)

        logger.info(f"[search_gmail_messages] Found {len(messages)} messages")

        return SearchGmailMessagesResponse(
            success=True,
            messages=messages,
            total_found=len(messages),
            query=query,
            userEmail=user_google_email,
            page_size=page_size,
        )

    except HttpError as e:
        logger.error(f"Gmail API error in search_gmail_messages: {e}")
        return SearchGmailMessagesResponse(
            success=False,
            messages=[],
            total_found=0,
            query=query,
            userEmail=user_google_email,
            page_size=page_size,
            error=f"Gmail API error: {e}",
        )

    except Exception as e:
        logger.error(f"Unexpected error in search_gmail_messages: {e}")
        return SearchGmailMessagesResponse(
            success=False,
            messages=[],
            total_found=0,
            query=query,
            userEmail=user_google_email,
            page_size=page_size,
            error=f"Unexpected error: {e}",
        )


async def get_gmail_message_content(
    message_id: Annotated[
        str, Field(description="The unique Gmail message ID to retrieve content from")
    ],
    user_google_email: Annotated[
        Optional[str],
        Field(
            description="The user's Google email address for Gmail access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware)."
        ),
    ] = None,
) -> GetGmailMessageContentResponse:
    """
    Retrieves the full content (subject, sender, plain text body) of a specific Gmail message.

    Args:
        user_google_email: The user's Google email address. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware).
        message_id: The unique ID of the Gmail message to retrieve

    Returns:
        GetGmailMessageContentResponse: Structured response with message content
    """
    logger.info(
        f"[get_gmail_message_content] Message ID: '{message_id}', Email: '{user_google_email}'"
    )

    try:
        gmail_service = await _get_gmail_service_with_fallback(user_google_email)

        # Fetch message metadata first to get headers
        message_metadata = await asyncio.to_thread(
            gmail_service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            )
            .execute
        )

        headers = {
            h["name"]: h["value"]
            for h in message_metadata.get("payload", {}).get("headers", [])
        }
        subject = headers.get("Subject", "(no subject)")
        sender = headers.get("From", "(unknown sender)")
        date = headers.get("Date")

        # Now fetch the full message to get the body parts
        message_full = await asyncio.to_thread(
            gmail_service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="full",  # Request full payload for body
            )
            .execute
        )

        # Extract the plain text body using helper function
        payload = message_full.get("payload", {})
        body_data = _extract_message_body(payload)

        # Extract attachment metadata from the full payload
        attachment_metadata = _extract_attachment_metadata(payload)

        message_content: GmailMessageContent = {
            "id": message_id,
            "subject": subject,
            "sender": sender,
            "date": date,
            "body": body_data or "[No text/plain body found]",
            "web_url": _generate_gmail_web_url(message_id),
        }
        if attachment_metadata:
            message_content["attachments"] = attachment_metadata

        return GetGmailMessageContentResponse(
            success=True, message_content=message_content, userEmail=user_google_email
        )

    except HttpError as e:
        logger.error(f"Gmail API error in get_gmail_message_content: {e}")
        return GetGmailMessageContentResponse(
            success=False, userEmail=user_google_email, error=f"Gmail API error: {e}"
        )

    except Exception as e:
        logger.error(f"Unexpected error in get_gmail_message_content: {e}")
        return GetGmailMessageContentResponse(
            success=False, userEmail=user_google_email, error=f"Unexpected error: {e}"
        )


async def get_gmail_messages_content_batch(
    message_ids: Annotated[
        List[str],
        Field(
            description="List of Gmail message IDs to retrieve content from (maximum 100 messages per request)"
        ),
    ],
    user_google_email: Annotated[
        Optional[str],
        Field(
            description="The user's Google email address for Gmail access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware)."
        ),
    ] = None,
    format: Annotated[
        Literal["full", "metadata"],
        Field(
            description="Message format - 'full' includes message body, 'metadata' only includes headers"
        ),
    ] = "full",
) -> GetGmailMessagesBatchResponse:
    """
    Retrieves the content of multiple Gmail messages in a single batch request.
    Supports up to 100 messages per request using Google's batch API.

    Args:
        user_google_email: The user's Google email address. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware).
        message_ids: List of Gmail message IDs to retrieve (max 100)
        format: Message format. "full" includes body, "metadata" only headers

    Returns:
        GetGmailMessagesBatchResponse: Structured response with batch results
    """
    logger.info(
        f"[get_gmail_messages_content_batch] Message count: {len(message_ids)}, Email: '{user_google_email}'"
    )

    if not message_ids:
        return GetGmailMessagesBatchResponse(
            success=False,
            messages=[],
            total_requested=0,
            successful_count=0,
            failed_count=0,
            format=format,
            userEmail=user_google_email,
            error="No message IDs provided",
        )

    try:
        gmail_service = await _get_gmail_service_with_fallback(user_google_email)

        batch_messages: List[BatchMessageResult] = []
        successful_count = 0
        failed_count = 0

        # Process in chunks of 100 (Gmail batch limit)
        for chunk_start in range(0, len(message_ids), 100):
            chunk_ids = message_ids[chunk_start : chunk_start + 100]
            results: dict = {}

            def _batch_callback(request_id, response, exception):
                """Callback for batch requests"""
                results[request_id] = {"data": response, "error": exception}

            # Try to use batch API
            try:
                batch = gmail_service.new_batch_http_request(callback=_batch_callback)

                for mid in chunk_ids:
                    if format == "metadata":
                        req = (
                            gmail_service.users()
                            .messages()
                            .get(
                                userId="me",
                                id=mid,
                                format="metadata",
                                metadataHeaders=["Subject", "From", "Date"],
                            )
                        )
                    else:
                        req = (
                            gmail_service.users()
                            .messages()
                            .get(userId="me", id=mid, format="full")
                        )
                    batch.add(req, request_id=mid)

                # Execute batch request
                await asyncio.to_thread(batch.execute)

            except Exception as batch_error:
                # Fallback to asyncio.gather if batch API fails
                logger.warning(
                    f"[get_gmail_messages_content_batch] Batch API failed, falling back to asyncio.gather: {batch_error}"
                )

                async def fetch_message(mid: str):
                    try:
                        if format == "metadata":
                            msg = await asyncio.to_thread(
                                gmail_service.users()
                                .messages()
                                .get(
                                    userId="me",
                                    id=mid,
                                    format="metadata",
                                    metadataHeaders=["Subject", "From", "Date"],
                                )
                                .execute
                            )
                        else:
                            msg = await asyncio.to_thread(
                                gmail_service.users()
                                .messages()
                                .get(userId="me", id=mid, format="full")
                                .execute
                            )
                        return mid, msg, None
                    except Exception as e:
                        return mid, None, e

                # Fetch all messages in parallel
                fetch_results = await asyncio.gather(
                    *[fetch_message(mid) for mid in chunk_ids], return_exceptions=False
                )

                # Convert to results format
                for mid, msg, error in fetch_results:
                    results[mid] = {"data": msg, "error": error}

            # Process results for this chunk
            for mid in chunk_ids:
                entry = results.get(mid, {"data": None, "error": "No result"})

                if entry["error"]:
                    batch_messages.append(
                        BatchMessageResult(
                            id=mid,
                            success=False,
                            web_url=_generate_gmail_web_url(mid),
                            error=str(entry["error"]),
                        )
                    )
                    failed_count += 1
                else:
                    message = entry["data"]
                    if not message:
                        batch_messages.append(
                            BatchMessageResult(
                                id=mid,
                                success=False,
                                web_url=_generate_gmail_web_url(mid),
                                error="No data returned",
                            )
                        )
                        failed_count += 1
                        continue

                    # Extract content based on format
                    payload = message.get("payload", {})
                    headers = _extract_headers(payload, ["Subject", "From", "Date"])
                    subject = headers.get("Subject", "(no subject)")
                    sender = headers.get("From", "(unknown sender)")
                    date = headers.get("Date")

                    if format == "metadata":
                        batch_messages.append(
                            BatchMessageResult(
                                id=mid,
                                success=True,
                                subject=subject,
                                sender=sender,
                                date=date,
                                web_url=_generate_gmail_web_url(mid),
                            )
                        )
                    else:
                        # Full format - extract body too
                        body = _extract_message_body(payload)
                        batch_messages.append(
                            BatchMessageResult(
                                id=mid,
                                success=True,
                                subject=subject,
                                sender=sender,
                                date=date,
                                body=body or "[No text/plain body found]",
                                web_url=_generate_gmail_web_url(mid),
                            )
                        )

                    successful_count += 1

        return GetGmailMessagesBatchResponse(
            success=True,
            messages=batch_messages,
            total_requested=len(message_ids),
            successful_count=successful_count,
            failed_count=failed_count,
            format=format,
            userEmail=user_google_email,
        )

    except Exception as e:
        logger.error(f"Unexpected error in get_gmail_messages_content_batch: {e}")
        return GetGmailMessagesBatchResponse(
            success=False,
            messages=[],
            total_requested=len(message_ids),
            successful_count=0,
            failed_count=len(message_ids),
            format=format,
            userEmail=user_google_email,
            error=f"Unexpected error: {e}",
        )


async def get_gmail_thread_content(
    thread_id: Annotated[
        str,
        Field(
            description="The unique Gmail thread ID to retrieve the complete conversation"
        ),
    ],
    user_google_email: Annotated[
        Optional[str],
        Field(
            description="The user's Google email address for Gmail access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware)."
        ),
    ] = None,
) -> GetGmailThreadContentResponse:
    """
    Retrieves the complete content of a Gmail conversation thread, including all messages.

    Args:
        user_google_email: The user's Google email address. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware).
        thread_id: The unique ID of the Gmail thread to retrieve

    Returns:
        GetGmailThreadContentResponse: Structured response with thread content and all messages
    """
    logger.info(
        f"[get_gmail_thread_content] Thread ID: '{thread_id}', Email: '{user_google_email}'"
    )

    try:
        gmail_service = await _get_gmail_service_with_fallback(user_google_email)

        # Fetch the complete thread with all messages
        thread_response = await asyncio.to_thread(
            gmail_service.users()
            .threads()
            .get(userId="me", id=thread_id, format="full")
            .execute
        )

        messages = thread_response.get("messages", [])
        if not messages:
            return GetGmailThreadContentResponse(
                success=False,
                thread_id=thread_id,
                thread_subject="(unknown subject)",
                message_count=0,
                messages=[],
                userEmail=user_google_email,
                error=f"No messages found in thread '{thread_id}'",
            )

        # Extract thread subject from the first message
        first_message = messages[0]
        first_headers = {
            h["name"]: h["value"]
            for h in first_message.get("payload", {}).get("headers", [])
        }
        thread_subject = first_headers.get("Subject", "(no subject)")

        # Process each message in the thread
        thread_messages: List[ThreadMessageInfo] = []
        for i, message in enumerate(messages, 1):
            # Extract headers
            headers = {
                h["name"]: h["value"]
                for h in message.get("payload", {}).get("headers", [])
            }

            sender = headers.get("From", "(unknown sender)")
            date = headers.get("Date", "(unknown date)")
            subject = headers.get("Subject", thread_subject)

            # Extract message body
            payload = message.get("payload", {})
            body_data = _extract_message_body(payload)

            thread_message: ThreadMessageInfo = {
                "message_number": i,
                "id": message.get("id", ""),
                "subject": subject,
                "sender": sender,
                "date": date,
                "body": body_data or "[No text/plain body found]",
            }
            thread_messages.append(thread_message)

        return GetGmailThreadContentResponse(
            success=True,
            thread_id=thread_id,
            thread_subject=thread_subject,
            message_count=len(messages),
            messages=thread_messages,
            userEmail=user_google_email,
        )

    except Exception as e:
        logger.error(f"Unexpected error in get_gmail_thread_content: {e}")
        return GetGmailThreadContentResponse(
            success=False,
            thread_id=thread_id,
            thread_subject="(unknown subject)",
            message_count=0,
            messages=[],
            userEmail=user_google_email,
            error=f"Unexpected error: {e}",
        )


# 10 MB limit for attachment downloads to keep MCP responses manageable
MAX_ATTACHMENT_DOWNLOAD_BYTES = 10 * 1024 * 1024


DEFAULT_ATTACHMENT_DIR = os.path.join(os.path.expanduser("~"), "Downloads")


async def download_gmail_attachment(
    message_id: Annotated[
        str,
        Field(description="The Gmail message ID that contains the attachment"),
    ],
    filename: Annotated[
        str,
        Field(
            description="The attachment filename from get_gmail_message_content response"
        ),
    ],
    save_dir: Annotated[
        str,
        Field(
            description="Directory to save the attachment to. Defaults to ~/Downloads. Ignored when return_content is true."
        ),
    ] = "",
    return_content: Annotated[
        bool,
        Field(
            description="If true, return base64-encoded file content instead of saving to disk. Use for remote clients that cannot access the server filesystem."
        ),
    ] = False,
    user_google_email: Annotated[
        Optional[str],
        Field(
            description="The user's Google email address for Gmail access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware)."
        ),
    ] = None,
) -> DownloadGmailAttachmentResponse:
    """
    Download a specific attachment from a Gmail message.

    By default, saves the file to disk (save_dir, defaults to ~/Downloads).
    Set return_content=True to return base64-encoded data instead (for remote clients).

    Use get_gmail_message_content first to discover available attachments.

    Args:
        message_id: The Gmail message ID that contains the attachment
        filename: The attachment filename from get_gmail_message_content response
        save_dir: Directory to save the file to. Defaults to ~/Downloads.
        return_content: If True, return base64 data instead of saving to disk.
        user_google_email: The user's Google email address. If None, uses the
            current authenticated user from FastMCP context (auto-injected by middleware).

    Returns:
        DownloadGmailAttachmentResponse: Response with file_path (disk) or data (base64)
    """
    if not save_dir:
        save_dir = DEFAULT_ATTACHMENT_DIR

    logger.info(
        f"[download_gmail_attachment] Message: '{message_id}', "
        f"Filename: '{filename}', Save dir: '{save_dir}', "
        f"Return content: {return_content}, Email: '{user_google_email}'"
    )

    try:
        gmail_service = await _get_gmail_service_with_fallback(user_google_email)

        # Fetch the full message to find the attachment by filename
        # Gmail attachment IDs are ephemeral and change between API calls,
        # so we match by filename and get a fresh attachmentId each time.
        message_full = await asyncio.to_thread(
            gmail_service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute
        )

        payload = message_full.get("payload", {})
        attachment_metadata = _extract_attachment_metadata(payload)
        matching = [a for a in attachment_metadata if a["filename"] == filename]

        if not matching:
            available = [a["filename"] for a in attachment_metadata]
            return DownloadGmailAttachmentResponse(
                success=False,
                message_id=message_id,
                filename=filename,
                userEmail=user_google_email,
                error=(
                    f"Attachment '{filename}' not found in message '{message_id}'. "
                    f"Available attachments: {available}"
                ),
            )

        att_info = matching[0]
        attachment_id = att_info["attachmentId"]

        # Check size limit
        if att_info["size"] > MAX_ATTACHMENT_DOWNLOAD_BYTES:
            size_mb = att_info["size"] / (1024 * 1024)
            limit_mb = MAX_ATTACHMENT_DOWNLOAD_BYTES / (1024 * 1024)
            return DownloadGmailAttachmentResponse(
                success=False,
                message_id=message_id,
                attachment_id=attachment_id,
                filename=filename,
                mimeType=att_info["mimeType"],
                size=att_info["size"],
                userEmail=user_google_email,
                error=(
                    f"Attachment too large ({size_mb:.1f} MB). "
                    f"Limit is {limit_mb:.0f} MB. "
                    f"Access via Gmail web: {_generate_gmail_web_url(message_id)}"
                ),
            )

        # Download the attachment using the fresh attachmentId
        attachment_response = await asyncio.to_thread(
            gmail_service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute
        )

        raw_bytes = base64.urlsafe_b64decode(attachment_response["data"])

        response = DownloadGmailAttachmentResponse(
            success=True,
            message_id=message_id,
            attachment_id=attachment_id,
            filename=filename,
            mimeType=att_info["mimeType"],
            size=len(raw_bytes),
            userEmail=user_google_email,
        )

        if return_content:
            # Return base64 data for remote clients
            response["data"] = base64.b64encode(raw_bytes).decode("ascii")
            logger.info(
                f"[download_gmail_attachment] Returning {len(raw_bytes)} bytes as base64"
            )
        else:
            # Save to disk for local clients
            os.makedirs(save_dir, exist_ok=True)
            file_path = os.path.join(save_dir, filename)

            # Avoid overwriting existing files by appending a counter
            base, ext = os.path.splitext(file_path)
            counter = 1
            while os.path.exists(file_path):
                file_path = f"{base} ({counter}){ext}"
                counter += 1

            with open(file_path, "wb") as f:
                f.write(raw_bytes)

            response["file_path"] = file_path
            logger.info(
                f"[download_gmail_attachment] Saved {len(raw_bytes)} bytes to {file_path}"
            )

        return response

    except HttpError as e:
        logger.error(f"Gmail API error in download_gmail_attachment: {e}")
        return DownloadGmailAttachmentResponse(
            success=False,
            message_id=message_id,
            filename=filename,
            userEmail=user_google_email,
            error=f"Gmail API error: {e}",
        )

    except Exception as e:
        logger.error(f"Unexpected error in download_gmail_attachment: {e}")
        return DownloadGmailAttachmentResponse(
            success=False,
            message_id=message_id,
            attachment_id=attachment_id,
            userEmail=user_google_email,
            error=f"Unexpected error: {e}",
        )


def setup_message_tools(mcp: FastMCP) -> None:
    """Register Gmail message tools with the FastMCP server."""

    @mcp.tool(
        name="search_gmail_messages",
        description="Search messages in Gmail account using Gmail query syntax with message and thread IDs",
        tags={"gmail", "search", "messages", "email"},
        annotations={
            "title": "Gmail Message Search",
            "readOnlyHint": True,  # Only searches, doesn't modify
            "destructiveHint": False,  # Safe read-only operation
            "idempotentHint": True,  # Multiple calls return same result
            "openWorldHint": True,  # Interacts with external Gmail API
        },
    )
    async def search_gmail_messages_tool(
        query: Annotated[
            str,
            Field(
                description="Gmail search query using standard Gmail search operators (e.g., 'from:sender@example.com', 'subject:important')"
            ),
        ],
        user_google_email: UserGoogleEmail = None,
        page_size: Annotated[
            int, Field(description="Maximum number of messages to return", ge=1, le=100)
        ] = 10,
    ) -> SearchGmailMessagesResponse:
        return await search_gmail_messages(query, user_google_email, page_size)

    @mcp.tool(
        name="get_gmail_message_content",
        description="Retrieve the full content (subject, sender, body) of a specific Gmail message",
        tags={"gmail", "message", "content", "email"},
        annotations={
            "title": "Gmail Message Content",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def get_gmail_message_content_tool(
        message_id: Annotated[
            str,
            Field(description="The unique Gmail message ID to retrieve content from"),
        ],
        user_google_email: UserGoogleEmail = None,
    ) -> GetGmailMessageContentResponse:
        return await get_gmail_message_content(message_id, user_google_email)

    @mcp.tool(
        name="get_gmail_messages_content_batch",
        description="Retrieve content of multiple Gmail messages in a single batch request (up to 100 messages)",
        tags={"gmail", "batch", "messages", "content", "email"},
        annotations={
            "title": "Gmail Batch Message Content",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def get_gmail_messages_content_batch_tool(
        message_ids: Annotated[
            List[str],
            Field(
                description="List of Gmail message IDs to retrieve content from (maximum 100 messages per request)"
            ),
        ],
        user_google_email: UserGoogleEmail = None,
        format: Annotated[
            Literal["full", "metadata"],
            Field(
                description="Message format - 'full' includes message body, 'metadata' only includes headers"
            ),
        ] = "full",
    ) -> GetGmailMessagesBatchResponse:
        return await get_gmail_messages_content_batch(
            message_ids, user_google_email, format
        )

    @mcp.tool(
        name="get_gmail_thread_content",
        description="Retrieve the complete content of a Gmail conversation thread with all messages",
        tags={"gmail", "thread", "conversation", "messages"},
        annotations={
            "title": "Gmail Thread Content",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def get_gmail_thread_content_tool(
        thread_id: Annotated[
            str,
            Field(
                description="The unique Gmail thread ID to retrieve the complete conversation"
            ),
        ],
        user_google_email: UserGoogleEmail = None,
    ) -> GetGmailThreadContentResponse:
        return await get_gmail_thread_content(thread_id, user_google_email)

    @mcp.tool(
        name="download_gmail_attachment",
        description="Download a specific attachment from a Gmail message. Saves to disk by default (~/Downloads), or set return_content=true for base64 data. First use get_gmail_message_content to list attachments.",
        tags={"gmail", "attachment", "download", "email"},
        annotations={
            "title": "Gmail Attachment Download",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def download_gmail_attachment_tool(
        message_id: Annotated[
            str,
            Field(description="The Gmail message ID that contains the attachment"),
        ],
        filename: Annotated[
            str,
            Field(
                description="The attachment filename from get_gmail_message_content response"
            ),
        ],
        save_dir: Annotated[
            str,
            Field(
                description="Directory to save the attachment to. Defaults to ~/Downloads. Ignored when return_content is true."
            ),
        ] = "",
        return_content: Annotated[
            bool,
            Field(
                description="If true, return base64-encoded file content instead of saving to disk. Use for remote clients."
            ),
        ] = False,
        user_google_email: UserGoogleEmail = None,
    ) -> DownloadGmailAttachmentResponse:
        return await download_gmail_attachment(
            message_id, filename, save_dir, return_content, user_google_email
        )
