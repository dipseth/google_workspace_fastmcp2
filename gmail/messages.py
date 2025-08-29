"""
Gmail message reading and search tools for FastMCP2.

This module provides tools for:
- Searching Gmail messages using Gmail query syntax
- Retrieving individual message content
- Batch message content retrieval
- Thread content retrieval
"""

import logging
import asyncio
from typing import List, Literal

from fastmcp import FastMCP, Context
from googleapiclient.errors import HttpError

from .service import _get_gmail_service_with_fallback
from .utils import _format_gmail_results_plain, _extract_message_body, _extract_headers, _generate_gmail_web_url

logger = logging.getLogger(__name__)


async def search_gmail_messages(
    user_google_email: str,
    query: str,
    page_size: int = 10
) -> str:
    """
    Searches messages in a user's Gmail account based on a query.
    Returns both Message IDs and Thread IDs for each found message, along with Gmail web interface links for manual verification.

    Args:
        user_google_email: The user's Google email address
        query: The search query. Supports standard Gmail search operators
        page_size: The maximum number of messages to return (default: 10)

    Returns:
        str: LLM-friendly structured results with Message IDs, Thread IDs, and clickable Gmail web interface URLs
    """
    logger.info(f"[search_gmail_messages] Email: '{user_google_email}', Query: '{query}'")

    try:
        # Get Gmail service with fallback support
        gmail_service = await _get_gmail_service_with_fallback(user_google_email)

        response = await asyncio.to_thread(
            gmail_service.users()
            .messages()
            .list(userId="me", q=query, maxResults=page_size)
            .execute
        )
        messages = response.get("messages", [])
        formatted_output = _format_gmail_results_plain(messages, query)

        logger.info(f"[search_gmail_messages] Found {len(messages)} messages")
        return formatted_output

    except HttpError as e:
        logger.error(f"Gmail API error in search_gmail_messages: {e}")
        return f"❌ Gmail API error: {e}"

    except Exception as e:
        logger.error(f"Unexpected error in search_gmail_messages: {e}")
        return f"❌ Unexpected error: {e}"


async def get_gmail_message_content(
    user_google_email: str,
    message_id: str
) -> str:
    """
    Retrieves the full content (subject, sender, plain text body) of a specific Gmail message.

    Args:
        user_google_email: The user's Google email address
        message_id: The unique ID of the Gmail message to retrieve

    Returns:
        str: The message details including subject, sender, and body content
    """
    logger.info(f"[get_gmail_message_content] Message ID: '{message_id}', Email: '{user_google_email}'")

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
                metadataHeaders=["Subject", "From"],
            )
            .execute
        )

        headers = {
            h["name"]: h["value"]
            for h in message_metadata.get("payload", {}).get("headers", [])
        }
        subject = headers.get("Subject", "(no subject)")
        sender = headers.get("From", "(unknown sender)")

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

        content_text = "\n".join(
            [
                f"Subject: {subject}",
                f"From:    {sender}",
                f"\n--- BODY ---\n{body_data or '[No text/plain body found]'}",
            ]
        )
        return content_text

    except HttpError as e:
        logger.error(f"Gmail API error in get_gmail_message_content: {e}")
        return f"❌ Gmail API error: {e}"

    except Exception as e:
        logger.error(f"Unexpected error in get_gmail_message_content: {e}")
        return f"❌ Unexpected error: {e}"


async def get_gmail_messages_content_batch(
    user_google_email: str,
    message_ids: List[str],
    format: Literal["full", "metadata"] = "full"
) -> str:
    """
    Retrieves the content of multiple Gmail messages in a single batch request.
    Supports up to 100 messages per request using Google's batch API.

    Args:
        user_google_email: The user's Google email address
        message_ids: List of Gmail message IDs to retrieve (max 100)
        format: Message format. "full" includes body, "metadata" only headers

    Returns:
        str: A formatted list of message contents with separators
    """
    logger.info(f"[get_gmail_messages_content_batch] Message count: {len(message_ids)}, Email: '{user_google_email}'")

    if not message_ids:
        return "❌ No message IDs provided"

    try:
        gmail_service = await _get_gmail_service_with_fallback(user_google_email)

        output_messages = []

        # Process in chunks of 100 (Gmail batch limit)
        for chunk_start in range(0, len(message_ids), 100):
            chunk_ids = message_ids[chunk_start:chunk_start + 100]
            results: dict = {}

            def _batch_callback(request_id, response, exception):
                """Callback for batch requests"""
                results[request_id] = {"data": response, "error": exception}

            # Try to use batch API
            try:
                batch = gmail_service.new_batch_http_request(callback=_batch_callback)

                for mid in chunk_ids:
                    if format == "metadata":
                        req = gmail_service.users().messages().get(
                            userId="me",
                            id=mid,
                            format="metadata",
                            metadataHeaders=["Subject", "From"]
                        )
                    else:
                        req = gmail_service.users().messages().get(
                            userId="me",
                            id=mid,
                            format="full"
                        )
                    batch.add(req, request_id=mid)

                # Execute batch request
                await asyncio.to_thread(batch.execute)

            except Exception as batch_error:
                # Fallback to asyncio.gather if batch API fails
                logger.warning(f"[get_gmail_messages_content_batch] Batch API failed, falling back to asyncio.gather: {batch_error}")

                async def fetch_message(mid: str):
                    try:
                        if format == "metadata":
                            msg = await asyncio.to_thread(
                                gmail_service.users().messages().get(
                                    userId="me",
                                    id=mid,
                                    format="metadata",
                                    metadataHeaders=["Subject", "From"]
                                ).execute
                            )
                        else:
                            msg = await asyncio.to_thread(
                                gmail_service.users().messages().get(
                                    userId="me",
                                    id=mid,
                                    format="full"
                                ).execute
                            )
                        return mid, msg, None
                    except Exception as e:
                        return mid, None, e

                # Fetch all messages in parallel
                fetch_results = await asyncio.gather(
                    *[fetch_message(mid) for mid in chunk_ids],
                    return_exceptions=False
                )

                # Convert to results format
                for mid, msg, error in fetch_results:
                    results[mid] = {"data": msg, "error": error}

            # Process results for this chunk
            for mid in chunk_ids:
                entry = results.get(mid, {"data": None, "error": "No result"})

                if entry["error"]:
                    output_messages.append(f"⚠️ Message {mid}: {entry['error']}\n")
                else:
                    message = entry["data"]
                    if not message:
                        output_messages.append(f"⚠️ Message {mid}: No data returned\n")
                        continue

                    # Extract content based on format
                    payload = message.get("payload", {})

                    if format == "metadata":
                        headers = _extract_headers(payload, ["Subject", "From"])
                        subject = headers.get("Subject", "(no subject)")
                        sender = headers.get("From", "(unknown sender)")

                        output_messages.append(
                            f"Message ID: {mid}\n"
                            f"Subject: {subject}\n"
                            f"From: {sender}\n"
                            f"Web Link: {_generate_gmail_web_url(mid)}\n"
                        )
                    else:
                        # Full format - extract body too
                        headers = _extract_headers(payload, ["Subject", "From"])
                        subject = headers.get("Subject", "(no subject)")
                        sender = headers.get("From", "(unknown sender)")
                        body = _extract_message_body(payload)

                        output_messages.append(
                            f"Message ID: {mid}\n"
                            f"Subject: {subject}\n"
                            f"From: {sender}\n"
                            f"Web Link: {_generate_gmail_web_url(mid)}\n"
                            f"\n{body or '[No text/plain body found]'}\n"
                        )

        # Combine all messages with separators
        final_output = f"Retrieved {len(message_ids)} messages:\n\n"
        final_output += "\n---\n\n".join(output_messages)

        return final_output

    except Exception as e:
        logger.error(f"Unexpected error in get_gmail_messages_content_batch: {e}")
        return f"❌ Unexpected error: {e}"


async def get_gmail_thread_content(
    user_google_email: str,
    thread_id: str
) -> str:
    """
    Retrieves the complete content of a Gmail conversation thread, including all messages.

    Args:
        user_google_email: The user's Google email address
        thread_id: The unique ID of the Gmail thread to retrieve

    Returns:
        str: The complete thread content with all messages formatted for reading
    """
    logger.info(f"[get_gmail_thread_content] Thread ID: '{thread_id}', Email: '{user_google_email}'")

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
            return f"No messages found in thread '{thread_id}'."

        # Extract thread subject from the first message
        first_message = messages[0]
        first_headers = {
            h["name"]: h["value"]
            for h in first_message.get("payload", {}).get("headers", [])
        }
        thread_subject = first_headers.get("Subject", "(no subject)")

        # Build the thread content
        content_lines = [
            f"Thread ID: {thread_id}",
            f"Subject: {thread_subject}",
            f"Messages: {len(messages)}",
            "",
        ]

        # Process each message in the thread
        for i, message in enumerate(messages, 1):
            # Extract headers
            headers = {
                h["name"]: h["value"]
                for h in message.get("payload", {}).get("headers", [])
            }

            sender = headers.get("From", "(unknown sender)")
            date = headers.get("Date", "(unknown date)")
            subject = headers.get("Subject", "(no subject)")

            # Extract message body
            payload = message.get("payload", {})
            body_data = _extract_message_body(payload)

            # Add message to content
            content_lines.extend(
                [
                    f"=== Message {i} ===",
                    f"From: {sender}",
                    f"Date: {date}",
                ]
            )

            # Only show subject if it's different from thread subject
            if subject != thread_subject:
                content_lines.append(f"Subject: {subject}")

            content_lines.extend(
                [
                    "",
                    body_data or "[No text/plain body found]",
                    "",
                ]
            )

        content_text = "\n".join(content_lines)
        return content_text

    except Exception as e:
        logger.error(f"Unexpected error in get_gmail_thread_content: {e}")
        return f"❌ Unexpected error: {e}"


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
            "openWorldHint": True  # Interacts with external Gmail API
        }
    )
    async def search_gmail_messages_tool(
        user_google_email: str,
        query: str,
        page_size: int = 10
    ) -> str:
        return await search_gmail_messages(user_google_email, query, page_size)

    @mcp.tool(
        name="get_gmail_message_content",
        description="Retrieve the full content (subject, sender, body) of a specific Gmail message",
        tags={"gmail", "message", "content", "email"},
        annotations={
            "title": "Gmail Message Content",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def get_gmail_message_content_tool(
        user_google_email: str,
        message_id: str
    ) -> str:
        return await get_gmail_message_content(user_google_email, message_id)

    @mcp.tool(
        name="get_gmail_messages_content_batch",
        description="Retrieve content of multiple Gmail messages in a single batch request (up to 100 messages)",
        tags={"gmail", "batch", "messages", "content", "email"},
        annotations={
            "title": "Gmail Batch Message Content",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def get_gmail_messages_content_batch_tool(
        user_google_email: str,
        message_ids: List[str],
        format: Literal["full", "metadata"] = "full"
    ) -> str:
        return await get_gmail_messages_content_batch(user_google_email, message_ids, format)

    @mcp.tool(
        name="get_gmail_thread_content",
        description="Retrieve the complete content of a Gmail conversation thread with all messages",
        tags={"gmail", "thread", "conversation", "messages"},
        annotations={
            "title": "Gmail Thread Content",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def get_gmail_thread_content_tool(
        user_google_email: str,
        thread_id: str
    ) -> str:
        return await get_gmail_thread_content(user_google_email, thread_id)