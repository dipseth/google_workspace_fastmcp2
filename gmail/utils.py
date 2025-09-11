"""
Utility functions and helpers for Gmail tools.

This module contains shared utility functions used across Gmail tools including:
- Color validation and formatting for Gmail labels
- Message body extraction and processing
- Header extraction
- URL generation
- Result formatting
- Text processing and conversion
- MIME message creation
"""

import logging
import base64
from typing_extensions import Optional, List, Dict, Literal, Any, Union
from pathlib import Path

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import make_msgid
import re
import html

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


def _prepare_forward_subject(subject: str) -> str:
    """
    Prepare the subject line for a forward email.
    Adds 'Fwd: ' prefix if not already present (case-insensitive).

    Args:
        subject (str): Original email subject.

    Returns:
        str: Prepared forward subject.
    """
    if subject is None:
        return "Fwd: (no subject)"
    if re.match(r"(?i)^fwd:\s", subject):
        return subject
    return f"Fwd: {subject}"


def _extract_html_body(payload):
    """
    Helper function to extract HTML body from a Gmail message payload.
    Prioritizes HTML content over plain text to preserve formatting.

    Args:
        payload (dict): The message payload from Gmail API

    Returns:
        str: The HTML body content, or empty string if not found
    """
    html_body = ""
    parts = [payload] if "parts" not in payload else payload.get("parts", [])

    part_queue = list(parts)  # Use a queue for BFS traversal of parts
    while part_queue:
        part = part_queue.pop(0)
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            data = base64.urlsafe_b64decode(part["body"]["data"])
            html_body = data.decode("utf-8", errors="ignore")
            break  # Found HTML body
        elif part.get("mimeType", "").startswith("multipart/") and "parts" in part:
            part_queue.extend(part.get("parts", []))  # Add sub-parts to the queue

    # If no HTML found, check the main payload body if it exists
    if (
        not html_body
        and payload.get("mimeType") == "text/html"
        and payload.get("body", {}).get("data")
    ):
        data = base64.urlsafe_b64decode(payload["body"]["data"])
        html_body = data.decode("utf-8", errors="ignore")

    return html_body


def _format_forward_content(original_body: str, original_headers: dict, is_html: bool = False) -> str:
    """
    Format original message content for forwarding with proper headers.
    
    Args:
        original_body (str): The original message body (plain text or HTML)
        original_headers (dict): Dictionary of original message headers
        is_html (bool): Whether the content is HTML or plain text
        
    Returns:
        str: Formatted forward content with headers
    """
    if not original_body:
        return ""
    
    # Extract key headers
    from_header = original_headers.get("From", "(unknown sender)")
    to_header = original_headers.get("To", "")
    cc_header = original_headers.get("Cc", "")
    date_header = original_headers.get("Date", "")
    subject_header = original_headers.get("Subject", "(no subject)")
    
    if is_html:
        # HTML format with proper styling
        separator = "---------- Forwarded message ---------"
        header_lines = []
        
        header_lines.append(f"<strong>From:</strong> {html.escape(from_header)}<br>")
        if date_header:
            header_lines.append(f"<strong>Date:</strong> {html.escape(date_header)}<br>")
        header_lines.append(f"<strong>Subject:</strong> {html.escape(subject_header)}<br>")
        if to_header:
            header_lines.append(f"<strong>To:</strong> {html.escape(to_header)}<br>")
        if cc_header:
            header_lines.append(f"<strong>Cc:</strong> {html.escape(cc_header)}<br>")
        
        formatted_content = (
            f"<br><br>{html.escape(separator)}<br>"
            + "".join(header_lines)
            + f"<br>{original_body}"
        )
    else:
        # Plain text format
        separator = "---------- Forwarded message ---------"
        header_lines = []
        
        header_lines.append(f"From: {from_header}")
        if date_header:
            header_lines.append(f"Date: {date_header}")
        header_lines.append(f"Subject: {subject_header}")
        if to_header:
            header_lines.append(f"To: {to_header}")
        if cc_header:
            header_lines.append(f"Cc: {cc_header}")
        
        formatted_content = (
            f"\n\n{separator}\n"
            + "\n".join(header_lines)
            + f"\n\n{original_body}"
        )
    
    return formatted_content


def _parse_email_addresses(email_input: Union[str, List[str]]) -> List[str]:
    """
    Parse email addresses from various input formats.
    
    Supports:
    - Single email string: "user@example.com"
    - List of emails: ["user1@example.com", "user2@example.com"]
    - Comma-separated string: "user1@example.com,user2@example.com"
    
    Args:
        email_input: Email address(es) in various formats
        
    Returns:
        List of email addresses, normalized and stripped
    """
    if isinstance(email_input, list):
        return [email.strip() for email in email_input if email.strip()]
    elif isinstance(email_input, str):
        # Handle comma-separated string
        return [email.strip() for email in email_input.split(',') if email.strip()]
    else:
        return []


def extract_email_addresses(header_value: str) -> List[str]:
    """
    Extract email addresses from an email header value.
    
    Handles formats like:
    - "John Doe <john@example.com>"
    - "john@example.com"
    - "John Doe <john@example.com>, Jane Smith <jane@example.com>"
    - "john@example.com, jane@example.com"
    
    Args:
        header_value: The raw header value string from Gmail API
        
    Returns:
        List of extracted email addresses (lowercase, unique)
    """
    if not header_value:
        return []
    
    # Regular expression to match email addresses
    # This pattern matches email addresses either standalone or within angle brackets
    # Using a more precise pattern that handles both cases correctly
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    
    # Find all email addresses in the header
    matches = re.findall(email_pattern, header_value)
    
    # Remove duplicates and return lowercase
    unique_emails = list(set(email.strip().lower() for email in matches))
    
    return unique_emails


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