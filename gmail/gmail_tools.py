"""
Gmail tools for FastMCP2 with middleware-based service injection and fallback support.

This module provides comprehensive Gmail integration tools for FastMCP2 servers,
using the new middleware-dependent pattern for Google service authentication with
fallback to direct service creation when middleware injection is unavailable.

Key Features:
- Message search and retrieval with Gmail query syntax
- Batch message processing for efficiency
- Email composition, sending, and draft creation
- Thread-based conversation handling
- Label management and message labeling
- Reply functionality with proper threading
- Comprehensive error handling with user-friendly messages
- Fallback to direct service creation when middleware unavailable

Architecture:
- Primary: Uses middleware-based service injection (no decorators)
- Fallback: Direct service creation when middleware unavailable
- Automatic Google service authentication and caching
- Consistent error handling and token refresh
- FastMCP2 framework integration

Dependencies:
- google-api-python-client: Gmail API integration
- fastmcp: FastMCP server framework
- auth.service_helpers: Service injection utilities
"""

import logging
import asyncio
import base64
from typing import Optional, List, Dict, Literal, Any
from pathlib import Path

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re

from fastmcp import FastMCP
from googleapiclient.errors import HttpError

from auth.service_helpers import request_service, get_injected_service, get_service
from auth.context import get_user_email_context

logger = logging.getLogger(__name__)


def _extract_message_body(payload):
    """
    Helper function to extract plain text body from a Gmail message payload.

    Args:
        payload (dict): The message payload from Gmail API

    Returns:
        str: The plain text body content, or empty string if not found
    """
    body_data = ""
    parts = [payload] if "parts" not in payload else payload.get("parts", [])

    part_queue = list(parts)  # Use a queue for BFS traversal of parts
    while part_queue:
        part = part_queue.pop(0)
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            data = base64.urlsafe_b64decode(part["body"]["data"])
            body_data = data.decode("utf-8", errors="ignore")
            break  # Found plain text body
        elif part.get("mimeType", "").startswith("multipart/") and "parts" in part:
            part_queue.extend(part.get("parts", []))  # Add sub-parts to the queue

    # If no plain text found, check the main payload body if it exists
    if (
        not body_data
        and payload.get("mimeType") == "text/plain"
        and payload.get("body", {}).get("data")
    ):
        data = base64.urlsafe_b64decode(payload["body"]["data"])
        body_data = data.decode("utf-8", errors="ignore")

    return body_data


def _extract_headers(payload: dict, header_names: List[str]) -> Dict[str, str]:
    """
    Extract specified headers from a Gmail message payload.

    Args:
        payload: The message payload from Gmail API
        header_names: List of header names to extract

    Returns:
        Dict mapping header names to their values
    """
    headers = {}
    for header in payload.get("headers", []):
        if header["name"] in header_names:
            headers[header["name"]] = header["value"]
    return headers


def _generate_gmail_web_url(item_id: str, account_index: int = 0) -> str:
    """
    Generate Gmail web interface URL for a message or thread ID.
    Uses #all to access messages from any Gmail folder/label (not just inbox).

    Args:
        item_id: Gmail message ID or thread ID
        account_index: Google account index (default 0 for primary account)

    Returns:
        Gmail web interface URL that opens the message/thread in Gmail web interface
    """
    return f"https://mail.google.com/mail/u/{account_index}/#all/{item_id}"


def _format_gmail_results_plain(messages: list, query: str) -> str:
    """Format Gmail search results in clean, LLM-friendly plain text."""
    if not messages:
        return f"No messages found for query: '{query}'"

    lines = [
        f"Found {len(messages)} messages matching '{query}':",
        "",
        "📧 MESSAGES:",
    ]

    for i, msg in enumerate(messages, 1):
        message_url = _generate_gmail_web_url(msg["id"])
        thread_url = _generate_gmail_web_url(msg["threadId"])

        lines.extend([
            f"  {i}. Message ID: {msg['id']}",
            f"     Web Link: {message_url}",
            f"     Thread ID: {msg['threadId']}",
            f"     Thread Link: {thread_url}",
            ""
        ])

    lines.extend([
        "💡 USAGE:",
        "  • Pass the Message IDs **as a list** to get_gmail_messages_content_batch()",
        "    e.g. get_gmail_messages_content_batch(message_ids=[...])",
        "  • Pass the Thread IDs to get_gmail_thread_content() (single) _or_",
        "    get_gmail_threads_content_batch() (coming soon)"
    ])

    return "\n".join(lines)


def _prepare_reply_subject(subject: str) -> str:
    """
    Prepare the subject line for a reply email.
    Adds 'Re: ' prefix if not already present (case-insensitive).

    Args:
        subject (str): Original email subject.

    Returns:
        str: Prepared reply subject.
    """
    if subject is None:
        return "Re: (no subject)"
    if re.match(r"(?i)^re:\s", subject):
        return subject
    return f"Re: {subject}"


def _quote_original_message(original_body: str) -> str:
    """
    Quote the original message body for inclusion in a reply.
    Prefixes each line with '> '.

    Args:
        original_body (str): The original message body.

    Returns:
        str: Quoted message body.
    """
    if not original_body:
        return ""
    quoted_lines = [f"> {line}" for line in original_body.splitlines()]
    return "\n".join(quoted_lines)


async def _get_gmail_service_with_fallback(user_google_email: str) -> Any:
    """
    Get Gmail service with fallback to direct creation if middleware injection fails.
    
    Args:
        user_google_email: User's Google email address
        
    Returns:
        Authenticated Gmail service instance
        
    Raises:
        RuntimeError: If both middleware injection and direct creation fail
    """
    # First, try middleware injection
    service_key = request_service("gmail")
    
    try:
        # Try to get the injected service from middleware
        gmail_service = get_injected_service(service_key)
        logger.info(f"Successfully retrieved injected Gmail service for {user_google_email}")
        return gmail_service
        
    except RuntimeError as e:
        if "not yet fulfilled" in str(e).lower() or "service injection" in str(e).lower():
            # Middleware injection failed, fall back to direct service creation
            logger.warning(f"Middleware injection unavailable, falling back to direct service creation for {user_google_email}")
            
            try:
                # Use the helper function that handles smart defaults
                gmail_service = await get_service("gmail", user_google_email)
                logger.info(f"Successfully created Gmail service directly for {user_google_email}")
                return gmail_service
                
            except Exception as direct_error:
                error_str = str(direct_error)
                logger.error(f"Direct service creation also failed: {direct_error}")
                
                # Check for specific credential errors
                if "credentials do not contain the necessary fields" in error_str.lower():
                    raise RuntimeError(
                        f"❌ **Invalid or Corrupted Credentials**\n\n"
                        f"Your stored credentials for {user_google_email} are missing required OAuth fields.\n"
                        f"This typically happens when:\n"
                        f"- The OAuth flow was interrupted or didn't complete properly\n"
                        f"- The credentials file became corrupted\n"
                        f"- The authentication token expired and cannot be refreshed\n\n"
                        f"**To fix this, please:**\n"
                        f"1. Run `start_google_auth` with your email: {user_google_email}\n"
                        f"2. Complete the full authentication flow in your browser\n"
                        f"3. Grant all requested Gmail permissions\n"
                        f"4. Wait for the success confirmation\n"
                        f"5. Try your Gmail command again\n\n"
                        f"This will create fresh, valid credentials with all necessary fields."
                    )
                elif "no valid credentials found" in error_str.lower():
                    raise RuntimeError(
                        f"❌ **No Credentials Found**\n\n"
                        f"No authentication credentials found for {user_google_email}.\n\n"
                        f"**To authenticate:**\n"
                        f"1. Run `start_google_auth` with your email: {user_google_email}\n"
                        f"2. Follow the authentication flow in your browser\n"
                        f"3. Grant Gmail permissions when prompted\n"
                        f"4. Return here after seeing the success page"
                    )
                else:
                    raise RuntimeError(
                        f"Failed to get Gmail service through both middleware and direct creation.\n"
                        f"Middleware error: {e}\n"
                        f"Direct creation error: {direct_error}\n\n"
                        f"Please ensure you are authenticated by running `start_google_auth` with your email ({user_google_email}) "
                        f"and service_name='Gmail'."
                    )
        else:
            # Re-raise unexpected RuntimeErrors
            raise


def setup_gmail_tools(mcp: FastMCP) -> None:
    """
    Register Gmail tools with the FastMCP server using middleware-based service injection with fallback.
    
    This function registers all Gmail tools that use the new middleware-dependent pattern
    for Google service authentication with fallback to direct service creation when
    middleware injection is unavailable.
    
    Args:
        mcp: FastMCP server instance to register tools with
        
    Returns:
        None: Tools are registered as side effects
    """
    
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
                results: Dict[str, Dict] = {}

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

    @mcp.tool(
        name="send_gmail_message",
        description="Send an email using the user's Gmail account",
        tags={"gmail", "send", "email", "compose"},
        annotations={
            "title": "Send Gmail Message",
            "readOnlyHint": False,  # Sends emails, modifies state
            "destructiveHint": False,  # Creates new content, doesn't destroy
            "idempotentHint": False,  # Multiple sends create multiple emails
            "openWorldHint": True
        }
    )
    async def send_gmail_message(
        user_google_email: str,
        to: str,
        subject: str,
        body: str
    ) -> str:
        """
        Sends an email using the user's Gmail account.

        Args:
            user_google_email: The user's Google email address
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text)

        Returns:
            str: Confirmation message with the sent email's message ID
        """
        logger.info(f"[send_gmail_message] Sending to: {to}, from: {user_google_email}")
        
        try:
            gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
            # Prepare the email
            message = MIMEText(body)
            message["to"] = to
            message["subject"] = subject
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            send_body = {"raw": raw_message}

            # Send the message
            sent_message = await asyncio.to_thread(
                gmail_service.users().messages().send(userId="me", body=send_body).execute
            )
            message_id = sent_message.get("id")
            return f"✅ Email sent! Message ID: {message_id}"
                
        except HttpError as e:
            logger.error(f"Gmail API error in send_gmail_message: {e}")
            return f"❌ Gmail API error: {e}"
            
        except Exception as e:
            logger.error(f"Unexpected error in send_gmail_message: {e}")
            return f"❌ Unexpected error: {e}"

    @mcp.tool(
        name="draft_gmail_message",
        description="Create a draft email in the user's Gmail account",
        tags={"gmail", "draft", "email", "compose"},
        annotations={
            "title": "Draft Gmail Message",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def draft_gmail_message(
        user_google_email: str,
        subject: str,
        body: str,
        to: Optional[str] = None
    ) -> str:
        """
        Creates a draft email in the user's Gmail account.

        Args:
            user_google_email: The user's Google email address
            subject: Email subject
            body: Email body (plain text)
            to: Optional recipient email address. Can be left empty for drafts

        Returns:
            str: Confirmation message with the created draft's ID
        """
        logger.info(f"[draft_gmail_message] Email: '{user_google_email}', Subject: '{subject}'")
        
        try:
            gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
            # Prepare the email
            message = MIMEText(body)
            message["subject"] = subject

            # Add recipient if provided
            if to:
                message["to"] = to

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            # Create a draft instead of sending
            draft_body = {"message": {"raw": raw_message}}

            # Create the draft
            created_draft = await asyncio.to_thread(
                gmail_service.users().drafts().create(userId="me", body=draft_body).execute
            )
            draft_id = created_draft.get("id")
            return f"✅ Draft created! Draft ID: {draft_id}"
            
        except Exception as e:
            logger.error(f"Unexpected error in draft_gmail_message: {e}")
            return f"❌ Unexpected error: {e}"

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

    @mcp.tool(
        name="list_gmail_labels",
        description="List all labels in the user's Gmail account (system and user-created)",
        tags={"gmail", "labels", "list", "organize"},
        annotations={
            "title": "List Gmail Labels",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def list_gmail_labels(
        user_google_email: str
    ) -> str:
        """
        Lists all labels in the user's Gmail account.

        Args:
            user_google_email: The user's Google email address

        Returns:
            str: A formatted list of all labels with their IDs, names, and types
        """
        logger.info(f"[list_gmail_labels] Email: '{user_google_email}'")
        
        try:
            gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
            response = await asyncio.to_thread(
                gmail_service.users().labels().list(userId="me").execute
            )
            labels = response.get("labels", [])

            if not labels:
                return "No labels found."

            lines = [f"Found {len(labels)} labels:", ""]

            system_labels = []
            user_labels = []

            for label in labels:
                if label.get("type") == "system":
                    system_labels.append(label)
                else:
                    user_labels.append(label)

            if system_labels:
                lines.append("📂 SYSTEM LABELS:")
                for label in system_labels:
                    lines.append(f"  • {label['name']} (ID: {label['id']})")
                lines.append("")

            if user_labels:
                lines.append("🏷️  USER LABELS:")
                for label in user_labels:
                    lines.append(f"  • {label['name']} (ID: {label['id']})")

            return "\n".join(lines)
                
        except Exception as e:
            logger.error(f"Unexpected error in list_gmail_labels: {e}")
            return f"❌ Unexpected error: {e}"

    @mcp.tool(
        name="manage_gmail_label",
        description="Manage Gmail labels: create, update, or delete labels",
        tags={"gmail", "labels", "manage", "create", "update", "delete"},
        annotations={
            "title": "Manage Gmail Label",
            "readOnlyHint": False,
            "destructiveHint": True,  # Can delete labels
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def manage_gmail_label(
        user_google_email: str,
        action: Literal["create", "update", "delete"],
        name: Optional[str] = None,
        label_id: Optional[str] = None,
        label_list_visibility: Literal["labelShow", "labelHide"] = "labelShow",
        message_list_visibility: Literal["show", "hide"] = "show"
    ) -> str:
        """
        Manages Gmail labels: create, update, or delete labels.

        Args:
            user_google_email: The user's Google email address
            action: Action to perform on the label
            name: Label name. Required for create, optional for update
            label_id: Label ID. Required for update and delete operations
            label_list_visibility: Whether the label is shown in the label list
            message_list_visibility: Whether the label is shown in the message list

        Returns:
            str: Confirmation message of the label operation
        """
        logger.info(f"[manage_gmail_label] Email: '{user_google_email}', Action: '{action}'")
        
        if action == "create" and not name:
            return "❌ Label name is required for create action."

        if action in ["update", "delete"] and not label_id:
            return "❌ Label ID is required for update and delete actions."
        
        try:
            gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
            if action == "create":
                label_object = {
                    "name": name,
                    "labelListVisibility": label_list_visibility,
                    "messageListVisibility": message_list_visibility,
                }
                created_label = await asyncio.to_thread(
                    gmail_service.users().labels().create(userId="me", body=label_object).execute
                )
                return f"✅ Label created successfully!\nName: {created_label['name']}\nID: {created_label['id']}"

            elif action == "update":
                current_label = await asyncio.to_thread(
                    gmail_service.users().labels().get(userId="me", id=label_id).execute
                )

                label_object = {
                    "id": label_id,
                    "name": name if name is not None else current_label["name"],
                    "labelListVisibility": label_list_visibility,
                    "messageListVisibility": message_list_visibility,
                }

                updated_label = await asyncio.to_thread(
                    gmail_service.users().labels().update(userId="me", id=label_id, body=label_object).execute
                )
                return f"✅ Label updated successfully!\nName: {updated_label['name']}\nID: {updated_label['id']}"

            elif action == "delete":
                label = await asyncio.to_thread(
                    gmail_service.users().labels().get(userId="me", id=label_id).execute
                )
                label_name = label["name"]

                await asyncio.to_thread(
                    gmail_service.users().labels().delete(userId="me", id=label_id).execute
                )
                return f"✅ Label '{label_name}' (ID: {label_id}) deleted successfully!"
                
        except Exception as e:
            logger.error(f"Unexpected error in manage_gmail_label: {e}")
            return f"❌ Unexpected error: {e}"

    @mcp.tool(
        name="modify_gmail_message_labels",
        description="Add or remove labels from a Gmail message",
        tags={"gmail", "labels", "modify", "organize", "messages"},
        annotations={
            "title": "Modify Gmail Message Labels",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def modify_gmail_message_labels(
        user_google_email: str,
        message_id: str,
        add_label_ids: Optional[List[str]] = None,
        remove_label_ids: Optional[List[str]] = None
    ) -> str:
        """
        Adds or removes labels from a Gmail message.

        Args:
            user_google_email: The user's Google email address
            message_id: The ID of the message to modify
            add_label_ids: List of label IDs to add to the message
            remove_label_ids: List of label IDs to remove from the message

        Returns:
            str: Confirmation message of the label changes applied to the message
        """
        logger.info(f"[modify_gmail_message_labels] Email: '{user_google_email}', Message ID: '{message_id}'")
        
        if not add_label_ids and not remove_label_ids:
            return "❌ At least one of add_label_ids or remove_label_ids must be provided."
        
        try:
            gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
            body = {}
            if add_label_ids:
                body["addLabelIds"] = add_label_ids
            if remove_label_ids:
                body["removeLabelIds"] = remove_label_ids

            await asyncio.to_thread(
                gmail_service.users().messages().modify(userId="me", id=message_id, body=body).execute
            )

            actions = []
            if add_label_ids:
                actions.append(f"Added labels: {', '.join(add_label_ids)}")
            if remove_label_ids:
                actions.append(f"Removed labels: {', '.join(remove_label_ids)}")

            return f"✅ Message labels updated successfully!\nMessage ID: {message_id}\n{'; '.join(actions)}"
                
        except Exception as e:
            logger.error(f"Unexpected error in modify_gmail_message_labels: {e}")
            return f"❌ Unexpected error: {e}"

    @mcp.tool(
        name="reply_to_gmail_message",
        description="Send a reply to a specific Gmail message with proper threading",
        tags={"gmail", "reply", "send", "thread", "email"},
        annotations={
            "title": "Reply to Gmail Message",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def reply_to_gmail_message(
        user_google_email: str,
        message_id: str,
        body: str
    ) -> str:
        """
        Sends a reply to a specific Gmail message.

        Args:
            user_google_email: The user's Google email address
            message_id: The ID of the message to reply to
            body: The reply body (plain text)

        Returns:
            str: Confirmation message with the sent reply's message ID
        """
        logger.info(f"[reply_to_gmail_message] Email: '{user_google_email}', Replying to Message ID: '{message_id}'")
        
        try:
            gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
            # Fetch the original message to get headers and body for quoting
            original_message = await asyncio.to_thread(
                gmail_service.users().messages().get(userId="me", id=message_id, format="full").execute
            )
            payload = original_message.get("payload", {})
            headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
            original_subject = headers.get("Subject", "(no subject)")
            original_from = headers.get("From", "(unknown sender)")
            original_body = _extract_message_body(payload)

            reply_subject = _prepare_reply_subject(original_subject)
            quoted_body = _quote_original_message(original_body)

            # Compose the reply message body
            full_body = f"{body}\n\nOn {original_from} wrote:\n{quoted_body}"

            # Create MIME message with In-Reply-To and References headers
            message = MIMEMultipart()
            message["to"] = original_from
            message["subject"] = reply_subject
            message["In-Reply-To"] = headers.get("Message-ID", "")
            message["References"] = headers.get("Message-ID", "")
            message.attach(MIMEText(full_body, "plain"))

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            send_body = {"raw": raw_message, "threadId": original_message.get("threadId")}

            # Send the reply message
            sent_message = await asyncio.to_thread(
                gmail_service.users().messages().send(userId="me", body=send_body).execute
            )
            sent_message_id = sent_message.get("id")
            return f"✅ Reply sent! Message ID: {sent_message_id}"
                
        except Exception as e:
            logger.error(f"Unexpected error in reply_to_gmail_message: {e}")
            return f"❌ Unexpected error: {e}"

    @mcp.tool(
        name="draft_gmail_reply",
        description="Create a draft reply to a specific Gmail message with proper threading",
        tags={"gmail", "draft", "reply", "thread", "email"},
        annotations={
            "title": "Draft Gmail Reply",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def draft_gmail_reply(
        user_google_email: str,
        message_id: str,
        body: str
    ) -> str:
        """
        Creates a draft reply to a specific Gmail message.

        Args:
            user_google_email: The user's Google email address
            message_id: The ID of the message to draft a reply for
            body: The reply body (plain text)

        Returns:
            str: Confirmation message with the created draft's ID
        """
        logger.info(f"[draft_gmail_reply] Email: '{user_google_email}', Drafting reply to Message ID: '{message_id}'")
        
        try:
            gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
            # Fetch the original message to get headers and body for quoting
            original_message = await asyncio.to_thread(
                gmail_service.users().messages().get(userId="me", id=message_id, format="full").execute
            )
            payload = original_message.get("payload", {})
            headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
            original_subject = headers.get("Subject", "(no subject)")
            original_from = headers.get("From", "(unknown sender)")
            original_body = _extract_message_body(payload)

            reply_subject = _prepare_reply_subject(original_subject)
            quoted_body = _quote_original_message(original_body)

            # Compose the reply message body
            full_body = f"{body}\n\nOn {original_from} wrote:\n{quoted_body}"

            # Create MIME message with In-Reply-To and References headers
            message = MIMEMultipart()
            message["to"] = original_from
            message["subject"] = reply_subject
            message["In-Reply-To"] = headers.get("Message-ID", "")
            message["References"] = headers.get("Message-ID", "")
            message.attach(MIMEText(full_body, "plain"))

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            draft_body = {"message": {"raw": raw_message, "threadId": original_message.get("threadId")}}

            # Create the draft reply
            created_draft = await asyncio.to_thread(
                gmail_service.users().drafts().create(userId="me", body=draft_body).execute
            )
            draft_id = created_draft.get("id")
            return f"✅ Draft reply created! Draft ID: {draft_id}"
                
        except Exception as e:
            logger.error(f"Unexpected error in draft_gmail_reply: {e}")
            return f"❌ Unexpected error: {e}"