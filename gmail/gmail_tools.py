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
from typing import Optional, List, Dict, Literal, Any, Union
from pathlib import Path

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import make_msgid
import re
import html

from fastmcp import FastMCP
from googleapiclient.errors import HttpError

from auth.service_helpers import request_service, get_injected_service, get_service
from auth.context import get_user_email_context

logger = logging.getLogger(__name__)


# Gmail API supported colors (from official documentation)
GMAIL_LABEL_COLORS = {
    "text_colors": [
        "#000000", "#434343", "#666666", "#999999", "#cccccc", "#efefef", "#f3f3f3", "#ffffff",
        "#fb4c2f", "#ffad47", "#fad165", "#16a766", "#43d692", "#4a86e8", "#a479e2", "#f691b3",
        "#f6c5be", "#ffe6c7", "#fef1d1", "#b9e4d0", "#c6f3de", "#c9daf8", "#e4d7f5", "#fcdee8",
        "#efa093", "#ffd6a2", "#fce8b3", "#89d3b2", "#a0eac9", "#a4c2f4", "#d0bcf1", "#fbc8d9",
        "#e66550", "#ffbc6b", "#fcda83", "#44b984", "#68dfa9", "#6d9eeb", "#b694e8", "#f7a7c0",
        "#cc3a21", "#eaa041", "#f2c960", "#149e60", "#3dc789", "#3c78d8", "#8e63ce", "#e07798",
        "#ac2b16", "#cf8933", "#d5ae49", "#0b804b", "#2a9c68", "#285bac", "#653e9b", "#b65775",
        "#822111", "#a46a21", "#aa8831", "#076239", "#1a764d", "#1c4587", "#41236d", "#83334c",
        "#464646", "#e7e7e7", "#0d3472", "#b6cff5", "#0d3b44", "#98d7e4", "#3d188e", "#e3d7ff",
        "#711a36", "#fbd3e0", "#8a1c0a", "#f2b2a8", "#7a2e0b", "#ffc8af", "#7a4706", "#ffdeb5",
        "#594c05", "#fbe983", "#684e07", "#fdedc1", "#0b4f30", "#b3efd3", "#04502e", "#a2dcc1",
        "#c2c2c2", "#4986e7", "#2da2bb", "#b99aff", "#994a64", "#f691b2", "#ff7537", "#ffad46",
        "#662e37", "#ebdbde", "#cca6ac", "#094228", "#42d692", "#16a765"
    ],
    "background_colors": [
        "#000000", "#434343", "#666666", "#999999", "#cccccc", "#efefef", "#f3f3f3", "#ffffff",
        "#fb4c2f", "#ffad47", "#fad165", "#16a766", "#43d692", "#4a86e8", "#a479e2", "#f691b3",
        "#f6c5be", "#ffe6c7", "#fef1d1", "#b9e4d0", "#c6f3de", "#c9daf8", "#e4d7f5", "#fcdee8",
        "#efa093", "#ffd6a2", "#fce8b3", "#89d3b2", "#a0eac9", "#a4c2f4", "#d0bcf1", "#fbc8d9",
        "#e66550", "#ffbc6b", "#fcda83", "#44b984", "#68dfa9", "#6d9eeb", "#b694e8", "#f7a7c0",
        "#cc3a21", "#eaa041", "#f2c960", "#149e60", "#3dc789", "#3c78d8", "#8e63ce", "#e07798",
        "#ac2b16", "#cf8933", "#d5ae49", "#0b804b", "#2a9c68", "#285bac", "#653e9b", "#b65775",
        "#822111", "#a46a21", "#aa8831", "#076239", "#1a764d", "#1c4587", "#41236d", "#83334c",
        "#464646", "#e7e7e7", "#0d3472", "#b6cff5", "#0d3b44", "#98d7e4", "#3d188e", "#e3d7ff",
        "#711a36", "#fbd3e0", "#8a1c0a", "#f2b2a8", "#7a2e0b", "#ffc8af", "#7a4706", "#ffdeb5",
        "#594c05", "#fbe983", "#684e07", "#fdedc1", "#0b4f30", "#b3efd3", "#04502e", "#a2dcc1",
        "#c2c2c2", "#4986e7", "#2da2bb", "#b99aff", "#994a64", "#f691b2", "#ff7537", "#ffad46",
        "#662e37", "#ebdbde", "#cca6ac", "#094228", "#42d692", "#16a765"
    ]
}


def _validate_gmail_color(color_value: str, color_type: str) -> bool:
    """
    Validate Gmail label color against supported values.
    
    Args:
        color_value: Hex color code (e.g., "#fb4c2f")
        color_type: Either "text" or "background"
        
    Returns:
        bool: True if color is valid, False otherwise
    """
    if not color_value or not isinstance(color_value, str):
        return False
        
    color_key = f"{color_type}_colors"
    if color_key not in GMAIL_LABEL_COLORS:
        return False
        
    return color_value.lower() in [c.lower() for c in GMAIL_LABEL_COLORS[color_key]]


def _format_label_color_info(color_obj: Optional[Dict]) -> str:
    """
    Format label color information for display.
    
    Args:
        color_obj: Color object from Gmail API response
        
    Returns:
        str: Formatted color information
    """
    if not color_obj:
        return "No color set"
    
    text_color = color_obj.get("textColor", "N/A")
    bg_color = color_obj.get("backgroundColor", "N/A")
    
    return f"🎨 Text: {text_color} | Background: {bg_color}"


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


def _html_to_plain_text(html_content: str) -> str:
    """
    Convert HTML content to plain text for Gmail API compliance.
    
    Gmail API requires both HTML and plain text versions in multipart/alternative
    structure for proper HTML rendering.
    
    Args:
        html_content: HTML content string
        
    Returns:
        Plain text version of the HTML content
    """
    if not html_content:
        return ""
    
    # Unescape HTML entities first
    text = html.unescape(html_content)
    
    # Remove HTML tags with regex (simple approach)
    # This handles basic HTML to text conversion
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)  # <br> to newline
    text = re.sub(r'<p[^>]*>', '\n', text, flags=re.IGNORECASE)   # <p> to newline
    text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)      # </p> to newline
    text = re.sub(r'<div[^>]*>', '\n', text, flags=re.IGNORECASE)  # <div> to newline
    text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)    # </div> to newline
    text = re.sub(r'<h[1-6][^>]*>', '\n', text, flags=re.IGNORECASE)  # Headers to newline
    text = re.sub(r'</h[1-6]>', '\n', text, flags=re.IGNORECASE)     # Header close to newline
    text = re.sub(r'<li[^>]*>', '\n• ', text, flags=re.IGNORECASE)   # List items
    text = re.sub(r'</li>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)  # Remove all remaining HTML tags
    
    # Clean up multiple newlines and whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)  # Multiple newlines to double newline
    text = re.sub(r'^\s+|\s+$', '', text, flags=re.MULTILINE)  # Trim lines
    text = text.strip()
    
    return text


def _create_mime_message(
    to: Union[str, List[str]],
    subject: str,
    body: str,
    content_type: Literal["plain", "html", "mixed"] = "plain",
    html_body: Optional[str] = None,
    from_email: Optional[str] = None,
    cc: Optional[Union[str, List[str]]] = None,
    bcc: Optional[Union[str, List[str]]] = None,
    reply_to_message_id: Optional[str] = None,
    thread_id: Optional[str] = None
) -> str:
    """
    Create a properly formatted MIME message for Gmail API with support for multiple recipients.
    
    This function creates RFC 2822 compliant MIME messages with proper structure
    for Gmail API. For HTML emails, it creates multipart/alternative with both
    plain text and HTML versions as required by Gmail for proper rendering.
    Supports multiple recipients, CC, and BCC.
    
    Args:
        to: Recipient email address(es) - string or list of strings
        subject: Email subject line
        body: Email body content (plain text or HTML based on content_type)
        content_type: Type of content ("plain", "html", or "mixed")
        html_body: Optional HTML body for mixed content type
        from_email: Optional sender email address
        cc: Optional CC recipient(s) - string or list of strings
        bcc: Optional BCC recipient(s) - string or list of strings
        reply_to_message_id: Optional Message-ID for replies (for In-Reply-To header)
        thread_id: Optional thread ID for Gmail threading
        
    Returns:
        Base64url encoded message string ready for Gmail API
    """
    # Helper function to format recipient list
    def format_recipients(recipients: Optional[Union[str, List[str]]]) -> Optional[str]:
        if not recipients:
            return None
        if isinstance(recipients, str):
            return recipients
        return ", ".join(recipients)
    if content_type == "plain":
        # Simple plain text message
        message = MIMEText(body, "plain")
        message["To"] = format_recipients(to)
        message["Subject"] = subject
        if from_email:
            message["From"] = from_email
        if cc:
            message["Cc"] = format_recipients(cc)
        if bcc:
            message["Bcc"] = format_recipients(bcc)
        if reply_to_message_id:
            message["In-Reply-To"] = reply_to_message_id
            message["References"] = reply_to_message_id
        message["Message-ID"] = make_msgid()
        
    elif content_type == "html":
        # HTML message with plain text alternative
        # Create multipart/alternative message
        message = MIMEMultipart("alternative")
        message["To"] = format_recipients(to)
        message["Subject"] = subject
        if from_email:
            message["From"] = from_email
        if cc:
            message["Cc"] = format_recipients(cc)
        if bcc:
            message["Bcc"] = format_recipients(bcc)
        if reply_to_message_id:
            message["In-Reply-To"] = reply_to_message_id
            message["References"] = reply_to_message_id
        message["Message-ID"] = make_msgid()
        
        # Create plain text version from HTML
        plain_text = _html_to_plain_text(body)
        
        # Attach plain text part first
        text_part = MIMEText(plain_text, "plain")
        message.attach(text_part)
        
        # Attach HTML part second (Gmail shows the last part by default)
        html_part = MIMEText(body, "html")
        message.attach(html_part)
        
    elif content_type == "mixed":
        # Mixed content with separate plain text and HTML bodies
        if not html_body:
            raise ValueError("html_body is required when content_type is 'mixed'")
            
        message = MIMEMultipart("alternative")
        message["To"] = format_recipients(to)
        message["Subject"] = subject
        if from_email:
            message["From"] = from_email
        if cc:
            message["Cc"] = format_recipients(cc)
        if bcc:
            message["Bcc"] = format_recipients(bcc)
        if reply_to_message_id:
            message["In-Reply-To"] = reply_to_message_id
            message["References"] = reply_to_message_id
        message["Message-ID"] = make_msgid()
        
        # Attach plain text part first
        text_part = MIMEText(body, "plain")
        message.attach(text_part)
        
        # Attach HTML part second
        html_part = MIMEText(html_body, "html")
        message.attach(html_part)
        
    else:
        raise ValueError(f"Unsupported content_type: {content_type}")
    
    # Convert to base64url encoded string for Gmail API
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return raw_message


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
        to: Union[str, List[str]],
        subject: str,
        body: str,
        content_type: Literal["plain", "html", "mixed"] = "mixed",
        html_body: Optional[str] = None,
        cc: Optional[Union[str, List[str]]] = None,
        bcc: Optional[Union[str, List[str]]] = None
    ) -> str:
        """
        Sends an email using the user's Gmail account with support for HTML formatting and multiple recipients.

        Args:
            user_google_email: The user's Google email address
            to: Recipient email address(es) - can be a single string or list of strings
            subject: Email subject
            body: Email body content. Usage depends on content_type:
                - content_type="plain": Contains plain text only
                - content_type="html": Contains HTML content (plain text auto-generated for Gmail)
                - content_type="mixed": Contains plain text (HTML goes in html_body parameter)
            content_type: Content type - controls how body and html_body are used:
                - "plain": Plain text email (backward compatible)
                - "html": HTML email - put HTML content in 'body' parameter
                - "mixed": Dual content - plain text in 'body', HTML in 'html_body' (default)
            html_body: HTML content when content_type="mixed". Ignored for other content types.
            cc: Optional CC recipient(s) - can be a single string or list of strings
            bcc: Optional BCC recipient(s) - can be a single string or list of strings

        Returns:
            str: Confirmation message with the sent email's message ID
            
        Examples:
            # Plain text (backward compatible)
            send_gmail_message(user_email, "user@example.com", "Subject", "Plain text body")
            
            # HTML email (HTML content goes in 'body' parameter)
            send_gmail_message(user_email, "user@example.com", "Subject", "<h1>HTML content</h1>", content_type="html")
            
            # Mixed content (separate plain and HTML versions)
            send_gmail_message(user_email, "user@example.com", "Subject", "Plain version",
                             content_type="mixed", html_body="<h1>HTML version</h1>")
                             
            # Multiple recipients with HTML
            send_gmail_message(user_email, ["user1@example.com", "user2@example.com"],
                             "Subject", "<p>HTML for everyone!</p>", content_type="html",
                             cc="manager@example.com")
        """
        # Parameter validation and helpful error messages
        if content_type == "html" and html_body and not body.strip().startswith('<'):
            return f"❌ **Parameter Usage Error for content_type='html'**\n\n" \
                   f"When using content_type='html':\n" \
                   f"• Put your HTML content in the 'body' parameter\n" \
                   f"• The 'html_body' parameter is ignored\n\n" \
                   f"**For your case, try one of these:**\n" \
                   f"1. Use content_type='mixed' (uses both body and html_body)\n" \
                   f"2. Put HTML in 'body' parameter and remove 'html_body'\n\n" \
                   f"**Example:** body='<h1>Your HTML here</h1>', content_type='html'"
        
        if content_type == "mixed" and not html_body:
            return f"❌ **Missing HTML Content for content_type='mixed'**\n\n" \
                   f"When using content_type='mixed', you must provide:\n" \
                   f"• Plain text in 'body' parameter\n" \
                   f"• HTML content in 'html_body' parameter"
        
        # Format recipients for logging
        to_str = to if isinstance(to, str) else f"{len(to)} recipients"
        cc_str = f", CC: {cc if isinstance(cc, str) else f'{len(cc)} recipients'}" if cc else ""
        bcc_str = f", BCC: {bcc if isinstance(bcc, str) else f'{len(bcc)} recipients'}" if bcc else ""
        
        logger.info(f"[send_gmail_message] Sending to: {to_str}{cc_str}{bcc_str}, from: {user_google_email}, content_type: {content_type}")
        
        try:
            gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
            # Create properly formatted MIME message using helper function
            raw_message = _create_mime_message(
                to=to,
                subject=subject,
                body=body,
                content_type=content_type,
                html_body=html_body,
                from_email=user_google_email,
                cc=cc,
                bcc=bcc
            )
            
            send_body = {"raw": raw_message}

            # Send the message
            sent_message = await asyncio.to_thread(
                gmail_service.users().messages().send(userId="me", body=send_body).execute
            )
            message_id = sent_message.get("id")
            
            # Count total recipients for confirmation
            total_recipients = (len(to) if isinstance(to, list) else 1) + \
                             (len(cc) if isinstance(cc, list) else (1 if cc else 0)) + \
                             (len(bcc) if isinstance(bcc, list) else (1 if bcc else 0))
            
            return f"✅ Email sent to {total_recipients} recipient(s)! Message ID: {message_id} (Content type: {content_type})"
                
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
        to: Optional[Union[str, List[str]]] = None,
        content_type: Literal["plain", "html", "mixed"] = "mixed",
        html_body: Optional[str] = None,
        cc: Optional[Union[str, List[str]]] = None,
        bcc: Optional[Union[str, List[str]]] = None
    ) -> str:
        """
        Creates a draft email in the user's Gmail account with support for HTML formatting and multiple recipients.

        Args:
            user_google_email: The user's Google email address
            subject: Email subject
            body: Email body content. Usage depends on content_type:
                - content_type="plain": Contains plain text only
                - content_type="html": Contains HTML content (plain text auto-generated for Gmail)
                - content_type="mixed": Contains plain text (HTML goes in html_body parameter)
            to: Optional recipient email address(es) - can be a single string, list of strings, or None for drafts
            content_type: Content type - controls how body and html_body are used:
                - "plain": Plain text draft (backward compatible)
                - "html": HTML draft - put HTML content in 'body' parameter
                - "mixed": Dual content - plain text in 'body', HTML in 'html_body' (default)
            html_body: HTML content when content_type="mixed". Ignored for other content types.
            cc: Optional CC recipient(s) - can be a single string or list of strings
            bcc: Optional BCC recipient(s) - can be a single string or list of strings

        Returns:
            str: Confirmation message with the created draft's ID
            
        Examples:
            # Plain text draft
            draft_gmail_message(user_email, "Subject", "Plain text body")
            
            # HTML draft (HTML content goes in 'body' parameter)
            draft_gmail_message(user_email, "Subject", "<h1>HTML content</h1>", content_type="html")
            
            # Mixed content draft
            draft_gmail_message(user_email, "Subject", "Plain version",
                              content_type="mixed", html_body="<h1>HTML version</h1>")
        """
        # Format recipients for logging
        to_str = "no recipients" if not to else (to if isinstance(to, str) else f"{len(to)} recipients")
        cc_str = f", CC: {cc if isinstance(cc, str) else f'{len(cc)} recipients'}" if cc else ""
        bcc_str = f", BCC: {bcc if isinstance(bcc, str) else f'{len(bcc)} recipients'}" if bcc else ""
        
        logger.info(f"[draft_gmail_message] Email: '{user_google_email}', Subject: '{subject}', To: {to_str}{cc_str}{bcc_str}, content_type: {content_type}")
        
        try:
            gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
            # Create properly formatted MIME message using helper function
            raw_message = _create_mime_message(
                to=to or "",  # Use empty string if no recipient for draft
                subject=subject,
                body=body,
                content_type=content_type,
                html_body=html_body,
                from_email=user_google_email,
                cc=cc,
                bcc=bcc
            )

            # Create a draft instead of sending
            draft_body = {"message": {"raw": raw_message}}

            # Create the draft
            created_draft = await asyncio.to_thread(
                gmail_service.users().drafts().create(userId="me", body=draft_body).execute
            )
            draft_id = created_draft.get("id")
            
            # Count total recipients for confirmation (if any)
            total_recipients = 0
            if to:
                total_recipients += len(to) if isinstance(to, list) else 1
            if cc:
                total_recipients += len(cc) if isinstance(cc, list) else 1
            if bcc:
                total_recipients += len(bcc) if isinstance(bcc, list) else 1
            
            recipient_info = f" ({total_recipients} recipient(s))" if total_recipients > 0 else " (no recipients)"
            return f"✅ Draft created{recipient_info}! Draft ID: {draft_id} (Content type: {content_type})"
            
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
        message_list_visibility: Literal["show", "hide"] = "show",
        text_color: Optional[str] = None,
        background_color: Optional[str] = None
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
            text_color: Hex color code for label text (e.g., "#ffffff"). Must be a valid Gmail color.
            background_color: Hex color code for label background (e.g., "#fb4c2f"). Must be a valid Gmail color.

        Returns:
            str: Confirmation message of the label operation
        """
        logger.info(f"[manage_gmail_label] Email: '{user_google_email}', Action: '{action}'")
        
        if action == "create" and not name:
            return "❌ Label name is required for create action."

        if action in ["update", "delete"] and not label_id:
            return "❌ Label ID is required for update and delete actions."
        
        # Validate colors if provided
        if text_color and not _validate_gmail_color(text_color, "text"):
            return f"❌ Invalid text color: {text_color}. Must be a valid Gmail label color."
        
        if background_color and not _validate_gmail_color(background_color, "background"):
            return f"❌ Invalid background color: {background_color}. Must be a valid Gmail label color."
        
        try:
            gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
            if action == "create":
                label_object = {
                    "name": name,
                    "labelListVisibility": label_list_visibility,
                    "messageListVisibility": message_list_visibility,
                }
                
                # Add color information if provided
                if text_color or background_color:
                    color_obj = {}
                    if text_color:
                        color_obj["textColor"] = text_color
                    if background_color:
                        color_obj["backgroundColor"] = background_color
                    label_object["color"] = color_obj
                
                created_label = await asyncio.to_thread(
                    gmail_service.users().labels().create(userId="me", body=label_object).execute
                )
                
                # Format response with color information
                response_lines = [
                    "✅ Label created successfully!",
                    f"Name: {created_label['name']}",
                    f"ID: {created_label['id']}"
                ]
                
                if created_label.get("color"):
                    color_info = _format_label_color_info(created_label["color"])
                    response_lines.append(f"Colors: {color_info}")
                
                return "\n".join(response_lines)

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
                
                # Handle color updates
                if text_color or background_color:
                    # Get existing colors or create new color object
                    existing_color = current_label.get("color", {})
                    color_obj = {}
                    
                    # Use provided colors or keep existing ones
                    if text_color:
                        color_obj["textColor"] = text_color
                    elif existing_color.get("textColor"):
                        color_obj["textColor"] = existing_color["textColor"]
                        
                    if background_color:
                        color_obj["backgroundColor"] = background_color
                    elif existing_color.get("backgroundColor"):
                        color_obj["backgroundColor"] = existing_color["backgroundColor"]
                    
                    label_object["color"] = color_obj

                updated_label = await asyncio.to_thread(
                    gmail_service.users().labels().update(userId="me", id=label_id, body=label_object).execute
                )
                
                # Format response with color information
                response_lines = [
                    "✅ Label updated successfully!",
                    f"Name: {updated_label['name']}",
                    f"ID: {updated_label['id']}"
                ]
                
                if updated_label.get("color"):
                    color_info = _format_label_color_info(updated_label["color"])
                    response_lines.append(f"Colors: {color_info}")
                
                return "\n".join(response_lines)

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
        add_label_ids: Optional[Any] = None,
        remove_label_ids: Optional[Any] = None
    ) -> str:
        """
        Adds or removes labels from a Gmail message.

        Args:
            user_google_email: The user's Google email address
            message_id: The ID of the message to modify
            add_label_ids: List of label IDs to add to the message (can be list or JSON string)
            remove_label_ids: List of label IDs to remove from the message (can be list or JSON string)

        Returns:
            str: Confirmation message of the label changes applied to the message
        """
        import json
        
        logger.info(f"[modify_gmail_message_labels] Email: '{user_google_email}', Message ID: '{message_id}'")
        logger.info(f"[modify_gmail_message_labels] Raw add_label_ids: {add_label_ids} (type: {type(add_label_ids)})")
        logger.info(f"[modify_gmail_message_labels] Raw remove_label_ids: {remove_label_ids} (type: {type(remove_label_ids)})")
        
        # Helper function to parse label IDs (handles both list and JSON string formats)
        def parse_label_ids(label_ids: Any) -> Optional[List[str]]:
            if not label_ids:
                return None
            
            # If it's already a list, return it
            if isinstance(label_ids, list):
                return label_ids
            
            # If it's a string, try to parse as JSON
            if isinstance(label_ids, str):
                try:
                    parsed = json.loads(label_ids)
                    if isinstance(parsed, list):
                        return parsed
                    else:
                        # Single string wrapped in quotes - convert to list
                        return [parsed] if isinstance(parsed, str) else None
                except json.JSONDecodeError:
                    # Not valid JSON, treat as single label ID
                    return [label_ids]
            
            return None
        
        # Parse the label ID parameters
        parsed_add_label_ids = parse_label_ids(add_label_ids)
        parsed_remove_label_ids = parse_label_ids(remove_label_ids)
        
        logger.info(f"[modify_gmail_message_labels] Parsed add_label_ids: {parsed_add_label_ids}")
        logger.info(f"[modify_gmail_message_labels] Parsed remove_label_ids: {parsed_remove_label_ids}")
        
        if not parsed_add_label_ids and not parsed_remove_label_ids:
            return "❌ At least one of add_label_ids or remove_label_ids must be provided."
        
        try:
            gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
            body = {}
            if parsed_add_label_ids:
                body["addLabelIds"] = parsed_add_label_ids
            if parsed_remove_label_ids:
                body["removeLabelIds"] = parsed_remove_label_ids

            await asyncio.to_thread(
                gmail_service.users().messages().modify(userId="me", id=message_id, body=body).execute
            )

            actions = []
            if parsed_add_label_ids:
                actions.append(f"Added labels: {', '.join(parsed_add_label_ids)}")
            if parsed_remove_label_ids:
                actions.append(f"Removed labels: {', '.join(parsed_remove_label_ids)}")

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
        body: str,
        content_type: Literal["plain", "html", "mixed"] = "mixed",
        html_body: Optional[str] = None
    ) -> str:
        """
        Sends a reply to a specific Gmail message with support for HTML formatting.

        Args:
            user_google_email: The user's Google email address
            message_id: The ID of the message to reply to
            body: Reply body content. Usage depends on content_type:
                - content_type="plain": Contains plain text only
                - content_type="html": Contains HTML content (plain text auto-generated for Gmail)
                - content_type="mixed": Contains plain text (HTML goes in html_body parameter)
            content_type: Content type - controls how body and html_body are used:
                - "plain": Plain text reply (backward compatible)
                - "html": HTML reply - put HTML content in 'body' parameter
                - "mixed": Dual content - plain text in 'body', HTML in 'html_body' (default)
            html_body: HTML content when content_type="mixed". Ignored for other content types.

        Returns:
            str: Confirmation message with the sent reply's message ID
            
        Examples:
            # Plain text reply
            reply_to_gmail_message(user_email, "msg_123", "Thanks for your message!")
            
            # HTML reply (HTML content goes in 'body' parameter)
            reply_to_gmail_message(user_email, "msg_123", "<p>Thanks for your <b>message</b>!</p>", content_type="html")
            
            # Mixed content reply
            reply_to_gmail_message(user_email, "msg_123", "Thanks for your message!",
                                 content_type="mixed", html_body="<p>Thanks for your <b>message</b>!</p>")
        """
        logger.info(f"[reply_to_gmail_message] Email: '{user_google_email}', Replying to Message ID: '{message_id}', content_type: {content_type}")
        
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
                to=original_from,
                subject=reply_subject,
                body=full_body,
                content_type=content_type,
                html_body=html_full_body if content_type == "mixed" else None,
                from_email=user_google_email,
                reply_to_message_id=headers.get("Message-ID", ""),
                thread_id=original_message.get("threadId")
            )

            send_body = {"raw": raw_message, "threadId": original_message.get("threadId")}

            # Send the reply message
            sent_message = await asyncio.to_thread(
                gmail_service.users().messages().send(userId="me", body=send_body).execute
            )
            sent_message_id = sent_message.get("id")
            return f"✅ Reply sent! Message ID: {sent_message_id} (Content type: {content_type})"
                
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
        body: str,
        content_type: Literal["plain", "html", "mixed"] = "mixed",
        html_body: Optional[str] = None
    ) -> str:
        """
        Creates a draft reply to a specific Gmail message with support for HTML formatting.

        Args:
            user_google_email: The user's Google email address
            message_id: The ID of the message to draft a reply for
            body: Reply body content. Usage depends on content_type:
                - content_type="plain": Contains plain text only
                - content_type="html": Contains HTML content (plain text auto-generated for Gmail)
                - content_type="mixed": Contains plain text (HTML goes in html_body parameter)
            content_type: Content type - controls how body and html_body are used:
                - "plain": Plain text draft reply (backward compatible)
                - "html": HTML draft reply - put HTML content in 'body' parameter
                - "mixed": Dual content - plain text in 'body', HTML in 'html_body' (default)
            html_body: HTML content when content_type="mixed". Ignored for other content types.

        Returns:
            str: Confirmation message with the created draft's ID
            
        Examples:
            # Plain text draft reply
            draft_gmail_reply(user_email, "msg_123", "Thanks for your message!")
            
            # HTML draft reply (HTML content goes in 'body' parameter)
            draft_gmail_reply(user_email, "msg_123", "<p>Thanks for your <b>message</b>!</p>", content_type="html")
            
            # Mixed content draft reply
            draft_gmail_reply(user_email, "msg_123", "Thanks for your message!",
                            content_type="mixed", html_body="<p>Thanks for your <b>message</b>!</p>")
        """
        logger.info(f"[draft_gmail_reply] Email: '{user_google_email}', Drafting reply to Message ID: '{message_id}', content_type: {content_type}")
        
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
                to=original_from,
                subject=reply_subject,
                body=full_body,
                content_type=content_type,
                html_body=html_full_body if content_type == "mixed" else None,
                from_email=user_google_email,
                reply_to_message_id=headers.get("Message-ID", ""),
                thread_id=original_message.get("threadId")
            )

            draft_body = {"message": {"raw": raw_message, "threadId": original_message.get("threadId")}}

            # Create the draft reply
            created_draft = await asyncio.to_thread(
                gmail_service.users().drafts().create(userId="me", body=draft_body).execute
            )
            draft_id = created_draft.get("id")
            return f"✅ Draft reply created! Draft ID: {draft_id} (Content type: {content_type})"
                
        except Exception as e:
            logger.error(f"Unexpected error in draft_gmail_reply: {e}")
            return f"❌ Unexpected error: {e}"

    @mcp.tool(
        name="list_gmail_filters",
        description="List all Gmail filters/rules in the user's account",
        tags={"gmail", "filters", "rules", "list", "automation"},
        annotations={
            "title": "List Gmail Filters",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def list_gmail_filters(
        user_google_email: str
    ) -> str:
        """
        Lists all Gmail filters/rules in the user's account.

        Args:
            user_google_email: The user's Google email address

        Returns:
            str: A formatted list of all filters with their criteria and actions
        """
        logger.info(f"[list_gmail_filters] Email: '{user_google_email}'")
        
        try:
            gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
            response = await asyncio.to_thread(
                gmail_service.users().settings().filters().list(userId="me").execute
            )
            filters = response.get("filter", [])

            if not filters:
                return "No Gmail filters found."

            lines = [f"Found {len(filters)} Gmail filters:", ""]

            for i, filter_obj in enumerate(filters, 1):
                filter_id = filter_obj.get("id", "unknown")
                criteria = filter_obj.get("criteria", {})
                action = filter_obj.get("action", {})

                lines.append(f"📋 FILTER {i} (ID: {filter_id})")
                
                # Display criteria
                criteria_parts = []
                if criteria.get("from"):
                    criteria_parts.append(f"From: {criteria['from']}")
                if criteria.get("to"):
                    criteria_parts.append(f"To: {criteria['to']}")
                if criteria.get("subject"):
                    criteria_parts.append(f"Subject: {criteria['subject']}")
                if criteria.get("query"):
                    criteria_parts.append(f"Query: {criteria['query']}")
                if criteria.get("hasAttachment"):
                    criteria_parts.append("Has attachment: Yes")
                if criteria.get("excludeChats"):
                    criteria_parts.append("Exclude chats: Yes")
                if criteria.get("size"):
                    criteria_parts.append(f"Size: {criteria['size']}")
                if criteria.get("sizeComparison"):
                    criteria_parts.append(f"Size comparison: {criteria['sizeComparison']}")

                lines.append(f"  Criteria: {' | '.join(criteria_parts) if criteria_parts else 'None'}")

                # Display actions
                action_parts = []
                if action.get("addLabelIds"):
                    action_parts.append(f"Add labels: {', '.join(action['addLabelIds'])}")
                if action.get("removeLabelIds"):
                    action_parts.append(f"Remove labels: {', '.join(action['removeLabelIds'])}")
                if action.get("forward"):
                    action_parts.append(f"Forward to: {action['forward']}")
                if action.get("markAsSpam"):
                    action_parts.append("Mark as spam")
                if action.get("markAsImportant"):
                    action_parts.append("Mark as important")
                if action.get("neverMarkAsSpam"):
                    action_parts.append("Never mark as spam")
                if action.get("neverMarkAsImportant"):
                    action_parts.append("Never mark as important")

                lines.append(f"  Actions: {' | '.join(action_parts) if action_parts else 'None'}")
                lines.append("")

            return "\n".join(lines)
                
        except Exception as e:
            logger.error(f"Unexpected error in list_gmail_filters: {e}")
            return f"❌ Unexpected error: {e}"

    @mcp.tool(
        name="create_gmail_filter",
        description="Create a new Gmail filter/rule with criteria and actions, with optional retroactive application to existing emails",
        tags={"gmail", "filters", "rules", "create", "automation"},
        annotations={
            "title": "Create Gmail Filter",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def create_gmail_filter(
        user_google_email: str,
        # Criteria parameters
        from_address: Optional[str] = None,
        to_address: Optional[str] = None,
        subject_contains: Optional[str] = None,
        query: Optional[str] = None,
        has_attachment: Optional[bool] = None,
        exclude_chats: Optional[bool] = None,
        size: Optional[int] = None,
        size_comparison: Optional[Literal["larger", "smaller"]] = None,
        # Action parameters
        add_label_ids: Optional[Any] = None,
        remove_label_ids: Optional[Any] = None,
        forward_to: Optional[str] = None,
        mark_as_spam: Optional[bool] = None,
        mark_as_important: Optional[bool] = None,
        never_mark_as_spam: Optional[bool] = None,
        never_mark_as_important: Optional[bool] = None
    ) -> str:
        """
        Creates a new Gmail filter/rule with specified criteria and actions.

        Args:
            user_google_email: The user's Google email address
            from_address: Filter messages from this email address
            to_address: Filter messages to this email address
            subject_contains: Filter messages with this text in subject
            query: Gmail search query for advanced filtering
            has_attachment: Filter messages that have/don't have attachments
            exclude_chats: Whether to exclude chat messages
            size: Size threshold in bytes
            size_comparison: Whether size should be "larger" or "smaller" than threshold
            add_label_ids: List of label IDs to add to matching messages (can be list or JSON string)
            remove_label_ids: List of label IDs to remove from matching messages (can be list or JSON string)
            forward_to: Email address to forward matching messages to
            mark_as_spam: Whether to mark matching messages as spam
            mark_as_important: Whether to mark matching messages as important
            never_mark_as_spam: Whether to never mark matching messages as spam
            never_mark_as_important: Whether to never mark matching messages as important

        Returns:
            str: Confirmation message with the created filter's ID
        """
        import json
        
        logger.info(f"[create_gmail_filter] Email: '{user_google_email}'")
        logger.info(f"[create_gmail_filter] Raw add_label_ids: {add_label_ids} (type: {type(add_label_ids)})")
        logger.info(f"[create_gmail_filter] Raw remove_label_ids: {remove_label_ids} (type: {type(remove_label_ids)})")
        
        # Helper function to parse label IDs (reuse from modify_gmail_message_labels)
        def parse_label_ids(label_ids: Any) -> Optional[List[str]]:
            if not label_ids:
                return None
            
            # If it's already a list, return it
            if isinstance(label_ids, list):
                return label_ids
            
            # If it's a string, try to parse as JSON
            if isinstance(label_ids, str):
                try:
                    parsed = json.loads(label_ids)
                    if isinstance(parsed, list):
                        return parsed
                    else:
                        # Single string wrapped in quotes - convert to list
                        return [parsed] if isinstance(parsed, str) else None
                except json.JSONDecodeError:
                    # Not valid JSON, treat as single label ID
                    return [label_ids]
            
            return None

        # Build criteria object
        criteria = {}
        if from_address:
            criteria["from"] = from_address
        if to_address:
            criteria["to"] = to_address
        if subject_contains:
            criteria["subject"] = subject_contains
        if query:
            criteria["query"] = query
        if has_attachment is not None:
            criteria["hasAttachment"] = has_attachment
        if exclude_chats is not None:
            criteria["excludeChats"] = exclude_chats
        if size is not None:
            criteria["size"] = size
        if size_comparison:
            criteria["sizeComparison"] = size_comparison

        # Build action object
        action = {}
        parsed_add_label_ids = parse_label_ids(add_label_ids)
        parsed_remove_label_ids = parse_label_ids(remove_label_ids)
        
        logger.info(f"[create_gmail_filter] Parsed add_label_ids: {parsed_add_label_ids}")
        logger.info(f"[create_gmail_filter] Parsed remove_label_ids: {parsed_remove_label_ids}")
        
        if parsed_add_label_ids:
            action["addLabelIds"] = parsed_add_label_ids
        if parsed_remove_label_ids:
            action["removeLabelIds"] = parsed_remove_label_ids
        if forward_to:
            action["forward"] = forward_to
        if mark_as_spam is not None:
            action["markAsSpam"] = mark_as_spam
        if mark_as_important is not None:
            action["markAsImportant"] = mark_as_important
        if never_mark_as_spam is not None:
            action["neverMarkAsSpam"] = never_mark_as_spam
        if never_mark_as_important is not None:
            action["neverMarkAsImportant"] = never_mark_as_important

        # Validate that we have at least one criteria and one action
        if not criteria:
            return "❌ At least one filter criteria must be specified."
        if not action:
            return "❌ At least one filter action must be specified."
        
        try:
            gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
            filter_body = {
                "criteria": criteria,
                "action": action
            }

            created_filter = await asyncio.to_thread(
                gmail_service.users().settings().filters().create(userId="me", body=filter_body).execute
            )
            
            filter_id = created_filter.get("id")
            
            # Format response with details
            criteria_summary = []
            if from_address:
                criteria_summary.append(f"From: {from_address}")
            if to_address:
                criteria_summary.append(f"To: {to_address}")
            if subject_contains:
                criteria_summary.append(f"Subject contains: {subject_contains}")
            if query:
                criteria_summary.append(f"Query: {query}")
                
            action_summary = []
            if parsed_add_label_ids:
                action_summary.append(f"Add labels: {', '.join(parsed_add_label_ids)}")
            if parsed_remove_label_ids:
                action_summary.append(f"Remove labels: {', '.join(parsed_remove_label_ids)}")
            if forward_to:
                action_summary.append(f"Forward to: {forward_to}")
            if mark_as_spam:
                action_summary.append("Mark as spam")
            if mark_as_important:
                action_summary.append("Mark as important")

            response_lines = [
                "✅ Gmail filter created successfully!",
                f"Filter ID: {filter_id}",
                f"Criteria: {' | '.join(criteria_summary)}",
                f"Actions: {' | '.join(action_summary)}"
            ]

            # Apply filter to existing emails retroactively (always enabled for label actions)
            if parsed_add_label_ids or parsed_remove_label_ids:
                logger.info(f"[create_gmail_filter] Applying filter retroactively to existing emails")
                
                try:
                    # Build Gmail search query from filter criteria
                    search_terms = []
                    if from_address:
                        search_terms.append(f"from:{from_address}")
                    if to_address:
                        search_terms.append(f"to:{to_address}")
                    if subject_contains:
                        search_terms.append(f"subject:({subject_contains})")
                    if query:
                        search_terms.append(query)
                    if has_attachment is True:
                        search_terms.append("has:attachment")
                    elif has_attachment is False:
                        search_terms.append("-has:attachment")
                    if size is not None and size_comparison:
                        if size_comparison == "larger":
                            search_terms.append(f"larger:{size}")
                        else:  # smaller
                            search_terms.append(f"smaller:{size}")
                    
                    if not search_terms:
                        response_lines.append("\n⚠️ Cannot apply to existing emails: no searchable criteria specified")
                        return "\n".join(response_lines)
                    
                    search_query = " ".join(search_terms)
                    logger.info(f"[create_gmail_filter] Searching for existing emails with query: {search_query}")
                    
                    # Search for existing messages that match the filter criteria
                    search_response = await asyncio.to_thread(
                        gmail_service.users()
                        .messages()
                        .list(userId="me", q=search_query, maxResults=500)  # Limit to 500 for safety
                        .execute
                    )
                    existing_messages = search_response.get("messages", [])
                    
                    if existing_messages:
                        logger.info(f"[create_gmail_filter] Found {len(existing_messages)} existing messages to process")
                        
                        # Apply label actions to existing messages
                        processed_count = 0
                        error_count = 0
                        
                        for message in existing_messages:
                            try:
                                message_id = message["id"]
                                
                                # Only apply label actions (not forwarding, spam, etc. for safety)
                                if parsed_add_label_ids or parsed_remove_label_ids:
                                    modify_body = {}
                                    if parsed_add_label_ids:
                                        modify_body["addLabelIds"] = parsed_add_label_ids
                                    if parsed_remove_label_ids:
                                        modify_body["removeLabelIds"] = parsed_remove_label_ids
                                    
                                    await asyncio.to_thread(
                                        gmail_service.users().messages().modify(
                                            userId="me", id=message_id, body=modify_body
                                        ).execute
                                    )
                                    processed_count += 1
                                    
                            except Exception as msg_error:
                                logger.warning(f"[create_gmail_filter] Failed to process message {message.get('id', 'unknown')}: {msg_error}")
                                error_count += 1
                        
                        if processed_count > 0:
                            response_lines.append(f"\n🔄 Retroactive application: {processed_count} existing messages updated")
                        if error_count > 0:
                            response_lines.append(f"⚠️ {error_count} messages had errors during retroactive application")
                    else:
                        response_lines.append("\n🔍 No existing messages found matching the filter criteria")
                        
                except Exception as retro_error:
                    logger.error(f"[create_gmail_filter] Error during retroactive application: {retro_error}")
                    response_lines.append(f"\n⚠️ Filter created but retroactive application failed: {retro_error}")

            return "\n".join(response_lines)
                
        except Exception as e:
            logger.error(f"Unexpected error in create_gmail_filter: {e}")
            return f"❌ Unexpected error: {e}"

    @mcp.tool(
        name="get_gmail_filter",
        description="Get details of a specific Gmail filter by ID",
        tags={"gmail", "filters", "rules", "get", "details"},
        annotations={
            "title": "Get Gmail Filter",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def get_gmail_filter(
        user_google_email: str,
        filter_id: str
    ) -> str:
        """
        Gets details of a specific Gmail filter by ID.

        Args:
            user_google_email: The user's Google email address
            filter_id: The ID of the filter to retrieve

        Returns:
            str: Detailed information about the filter including criteria and actions
        """
        logger.info(f"[get_gmail_filter] Email: '{user_google_email}', Filter ID: '{filter_id}'")
        
        try:
            gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
            filter_obj = await asyncio.to_thread(
                gmail_service.users().settings().filters().get(userId="me", id=filter_id).execute
            )

            criteria = filter_obj.get("criteria", {})
            action = filter_obj.get("action", {})

            lines = [
                f"Gmail Filter Details (ID: {filter_id})",
                "",
                "📋 CRITERIA:"
            ]

            # Display criteria
            if criteria.get("from"):
                lines.append(f"  From: {criteria['from']}")
            if criteria.get("to"):
                lines.append(f"  To: {criteria['to']}")
            if criteria.get("subject"):
                lines.append(f"  Subject contains: {criteria['subject']}")
            if criteria.get("query"):
                lines.append(f"  Query: {criteria['query']}")
            if criteria.get("hasAttachment"):
                lines.append(f"  Has attachment: {criteria['hasAttachment']}")
            if criteria.get("excludeChats"):
                lines.append(f"  Exclude chats: {criteria['excludeChats']}")
            if criteria.get("size"):
                lines.append(f"  Size: {criteria['size']} bytes")
            if criteria.get("sizeComparison"):
                lines.append(f"  Size comparison: {criteria['sizeComparison']}")

            if not any(criteria.values()):
                lines.append("  None specified")

            lines.extend([
                "",
                "⚡ ACTIONS:"
            ])

            # Display actions
            if action.get("addLabelIds"):
                lines.append(f"  Add labels: {', '.join(action['addLabelIds'])}")
            if action.get("removeLabelIds"):
                lines.append(f"  Remove labels: {', '.join(action['removeLabelIds'])}")
            if action.get("forward"):
                lines.append(f"  Forward to: {action['forward']}")
            if action.get("markAsSpam"):
                lines.append(f"  Mark as spam: {action['markAsSpam']}")
            if action.get("markAsImportant"):
                lines.append(f"  Mark as important: {action['markAsImportant']}")
            if action.get("neverMarkAsSpam"):
                lines.append(f"  Never mark as spam: {action['neverMarkAsSpam']}")
            if action.get("neverMarkAsImportant"):
                lines.append(f"  Never mark as important: {action['neverMarkAsImportant']}")

            if not any(action.values()):
                lines.append("  None specified")

            return "\n".join(lines)
                
        except Exception as e:
            logger.error(f"Unexpected error in get_gmail_filter: {e}")
            return f"❌ Unexpected error: {e}"

    @mcp.tool(
        name="delete_gmail_filter",
        description="Delete a Gmail filter by ID",
        tags={"gmail", "filters", "rules", "delete", "remove"},
        annotations={
            "title": "Delete Gmail Filter",
            "readOnlyHint": False,
            "destructiveHint": True,  # Deletes filters
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def delete_gmail_filter(
        user_google_email: str,
        filter_id: str
    ) -> str:
        """
        Deletes a Gmail filter by ID.

        Args:
            user_google_email: The user's Google email address
            filter_id: The ID of the filter to delete

        Returns:
            str: Confirmation message of the filter deletion
        """
        logger.info(f"[delete_gmail_filter] Email: '{user_google_email}', Filter ID: '{filter_id}'")
        
        try:
            gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
            # Get filter details before deletion for confirmation
            try:
                filter_obj = await asyncio.to_thread(
                    gmail_service.users().settings().filters().get(userId="me", id=filter_id).execute
                )
                criteria = filter_obj.get("criteria", {})
                criteria_summary = []
                if criteria.get("from"):
                    criteria_summary.append(f"From: {criteria['from']}")
                if criteria.get("to"):
                    criteria_summary.append(f"To: {criteria['to']}")
                if criteria.get("subject"):
                    criteria_summary.append(f"Subject: {criteria['subject']}")
                if criteria.get("query"):
                    criteria_summary.append(f"Query: {criteria['query']}")
                    
                criteria_text = " | ".join(criteria_summary) if criteria_summary else "No criteria found"
                
            except Exception:
                criteria_text = "Could not retrieve criteria"

            # Delete the filter
            await asyncio.to_thread(
                gmail_service.users().settings().filters().delete(userId="me", id=filter_id).execute
            )

            return f"✅ Gmail filter deleted successfully!\nFilter ID: {filter_id}\nCriteria was: {criteria_text}"
                
        except Exception as e:
            logger.error(f"Unexpected error in delete_gmail_filter: {e}")
            return f"❌ Unexpected error: {e}"