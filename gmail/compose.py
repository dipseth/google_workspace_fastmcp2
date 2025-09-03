"""
Gmail email composition and sending tools for FastMCP2.

This module provides tools for:
- Sending emails with elicitation support for untrusted recipients
- Creating email drafts
- Replying to messages with proper threading
- Creating draft replies
"""

import logging
import json
import asyncio
import html
from datetime import datetime
from typing_extensions import Optional, Literal, Any, List, Dict, Union,Annotated
from pydantic import Field
from dataclasses import dataclass

from fastmcp import FastMCP, Context
from googleapiclient.errors import HttpError

from .service import _get_gmail_service_with_fallback
from .utils import _create_mime_message, _prepare_reply_subject, _quote_original_message, _html_to_plain_text, _extract_headers, _extract_message_body
from .templates import EmailTemplateManager
from .gmail_types import (
    SendGmailMessageResponse, DraftGmailMessageResponse, ReplyGmailMessageResponse, 
    DraftGmailReplyResponse
)
from config.settings import settings
from tools.common_types import UserGoogleEmail


logger = logging.getLogger(__name__)

# Initialize template manager
template_manager = EmailTemplateManager()


@dataclass
class EmailAction:
    action: Literal["send", "save_draft", "cancel"]


async def send_gmail_message(
    ctx: Context,
    to: Union[str, List[str]],
    subject: str,
    body: str,
    user_google_email: UserGoogleEmail = None,
    content_type: Literal["plain", "html", "mixed"] = "mixed",
    html_body: Optional[str] = None,
    cc: Optional[Union[str, List[str]]] = None,
    bcc: Optional[Union[str, List[str]]] = None
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

        # Multiple recipients with HTML
        send_gmail_message(ctx, ["user1@example.com", "user2@example.com"],
                          "Subject", "<p>HTML for everyone!</p>", content_type="html",
                          cc="manager@example.com")

        # Auto-injected user (middleware handles user_google_email)
        send_gmail_message(ctx, "user@example.com", "Subject", "Body content")
    """
    # Parameter validation and helpful error messages
    if content_type == "html" and html_body and not body.strip().startswith('<'):
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
            error="Parameter validation error: incorrect content_type usage"
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
            error="Parameter validation error: missing html_body for mixed content"
        )

    # Format recipients for logging
    to_str = to if isinstance(to, str) else f"{len(to)} recipients"
    cc_str = f", CC: {cc if isinstance(cc, str) else f'{len(cc)} recipients'}" if cc else ""
    bcc_str = f", BCC: {bcc if isinstance(bcc, str) else f'{len(bcc)} recipients'}" if bcc else ""

    logger.info(f"[send_gmail_message] Sending to: {to_str}{cc_str}{bcc_str}, from: {user_google_email}, content_type: {content_type}")

    # Check allow list and trigger elicitation if needed
    allow_list = settings.get_gmail_allow_list()

    if allow_list:
        # Collect all recipient emails for the message
        all_recipients = []

        # Process 'to' recipients
        if isinstance(to, str):
            all_recipients.extend([email.strip() for email in to.split(',')])
        elif isinstance(to, list):
            all_recipients.extend(to)

        # Process 'cc' recipients
        if cc:
            if isinstance(cc, str):
                all_recipients.extend([email.strip() for email in cc.split(',')])
            elif isinstance(cc, list):
                all_recipients.extend(cc)

        # Process 'bcc' recipients
        if bcc:
            if isinstance(bcc, str):
                all_recipients.extend([email.strip() for email in bcc.split(',')])
            elif isinstance(bcc, list):
                all_recipients.extend(bcc)

        # Normalize all recipient emails (lowercase, strip whitespace)
        all_recipients = [email.strip().lower() for email in all_recipients if email]

        # Normalize allow list emails
        normalized_allow_list = [email.lower() for email in allow_list]

        # Check if any recipient is NOT on the allow list
        recipients_not_allowed = [
            email for email in all_recipients
            if email not in normalized_allow_list
        ]

        if recipients_not_allowed:
            # Log elicitation trigger
            logger.info(f"Elicitation triggered for {len(recipients_not_allowed)} recipient(s) not on allow list")

            # Prepare elicitation message with better formatting
            to_display = to if isinstance(to, str) else ', '.join(to)
            cc_display = f"\n📋 **CC:** {cc if isinstance(cc, str) else ', '.join(cc)}" if cc else ""
            bcc_display = f"\n📋 **BCC:** {bcc if isinstance(bcc, str) else ', '.join(bcc)}" if bcc else ""

            # Truncate body for preview if too long
            body_preview = body[:300] + "... [truncated]" if len(body) > 300 else body

            elicitation_message = f"""📧 **Email Confirmation Required**

⏰ **Auto-timeout:** 60 seconds

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

            # Trigger elicitation with 60-second timeout
            try:
                response = await asyncio.wait_for(
                    ctx.elicit(
                        message=elicitation_message,
                        response_type=EmailAction
                    ),
                    timeout=300.0
                )
            except asyncio.TimeoutError:
                logger.info("Elicitation timed out after 60 seconds")
                return SendGmailMessageResponse(
                    success=False,
                    message="Email operation timed out - no response received within 60 seconds",
                    messageId=None,
                    threadId=None,
                    recipientCount=0,
                    contentType=content_type,
                    templateApplied=False,
                    error="Elicitation timeout",
                    elicitationRequired=True,
                    recipientsNotAllowed=recipients_not_allowed
                )

            # Handle standard elicitation response structure
            if response.action == "decline" or response.action == "cancel":
                logger.info(f"User {response.action}d email operation")
                return SendGmailMessageResponse(
                    success=False,
                    message=f"Email operation {response.action}d by user",
                    messageId=None,
                    threadId=None,
                    recipientCount=0,
                    contentType=content_type,
                    templateApplied=False,
                    error=f"User {response.action}d",
                    elicitationRequired=True,
                    recipientsNotAllowed=recipients_not_allowed
                )
            elif response.action == "accept":
                # Get the user's choice from the data field
                user_choice = response.data.action
                
                if user_choice == "cancel":
                    logger.info("User chose to cancel email operation")
                    return SendGmailMessageResponse(
                        success=False,
                        message="Email operation cancelled by user",
                        messageId=None,
                        threadId=None,
                        recipientCount=0,
                        contentType=content_type,
                        templateApplied=False,
                        error="User cancelled",
                        elicitationRequired=True,
                        recipientsNotAllowed=recipients_not_allowed
                    )
                elif user_choice == "save_draft":
                    logger.info("User chose to save email as draft")
                    # Create draft instead of sending
                    draft_result = await draft_gmail_message(
                        user_google_email=user_google_email,
                        subject=subject,
                        body=body,
                        to=to,
                        content_type=content_type,
                        html_body=html_body,
                        cc=cc,
                        bcc=bcc
                    )
                    # Return as send response with draft info
                    return SendGmailMessageResponse(
                        success=True,
                        message=f"Email saved as draft instead of sending. Draft ID: {draft_result.draftId}",
                        messageId=None,
                        threadId=None,
                        draftId=draft_result.draftId,  # Include draft ID
                        recipientCount=draft_result.recipientCount,
                        contentType=content_type,
                        templateApplied=False,
                        error=None,
                        elicitationRequired=True,
                        recipientsNotAllowed=recipients_not_allowed,
                        action="saved_draft"
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
                        recipientsNotAllowed=recipients_not_allowed
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
                    recipientsNotAllowed=recipients_not_allowed
                )
        else:
            # All recipients are on allow list
            logger.info(f"All {len(all_recipients)} recipient(s) are on allow list - sending without elicitation")
    else:
        # No allow list configured
        logger.debug("No Gmail allow list configured - sending without elicitation")

    try:
        gmail_service = await _get_gmail_service_with_fallback(user_google_email)

        # Check for email templates for recipients
        template_applied = False
        template = None
        final_body = body
        final_html_body = html_body
        final_content_type = content_type
        
        # Get primary recipient for template lookup
        primary_recipient = None
        if isinstance(to, str):
            # Handle comma-separated string
            recipients = [email.strip() for email in to.split(',') if email.strip()]
            if recipients:
                primary_recipient = recipients[0]
        elif isinstance(to, list) and to:
            primary_recipient = to[0]
        
        if primary_recipient:
            try:
                # Try to get template for this recipient
                template = await template_manager.get_template_for_user(primary_recipient)
                
                if template:
                    logger.info(f"Applying template '{template.name}' for recipient {primary_recipient}")
                    
                    # Prepare placeholders for replacement
                    placeholders = {
                        "recipient_email": primary_recipient,
                        "recipient_name": primary_recipient.split('@')[0],  # Simple name extraction
                        "sender_email": user_google_email,
                        "sender_name": user_google_email.split('@')[0],
                        "subject": subject,
                        "date": datetime.now().strftime("%B %d, %Y"),  # Formatted date
                    }
                    
                    # Handle content based on original content type
                    if content_type == "plain":
                        # Plain text email - wrap in template
                        placeholders["email_body"] = body
                        placeholders["content"] = body
                        templated_html = await template_manager.apply_template(
                            template.id,
                            placeholders
                        )
                        # Convert to mixed mode with template
                        final_content_type = "mixed"
                        final_body = body  # Keep plain text version
                        final_html_body = templated_html
                        template_applied = True
                        
                    elif content_type == "html":
                        # HTML email - insert HTML into template
                        placeholders["email_body"] = body  # HTML content
                        placeholders["content"] = _html_to_plain_text(body)  # Plain text version
                        templated_html = await template_manager.apply_template(
                            template.id,
                            placeholders
                        )
                        # Convert to mixed mode
                        final_content_type = "mixed"
                        final_body = _html_to_plain_text(body)  # Plain text version
                        final_html_body = templated_html
                        template_applied = True
                        
                    elif content_type == "mixed":
                        # Mixed content - use HTML body for template
                        placeholders["email_body"] = html_body if html_body else body
                        placeholders["content"] = body
                        templated_html = await template_manager.apply_template(
                            template.id,
                            placeholders
                        )
                        final_content_type = "mixed"
                        final_body = body
                        final_html_body = templated_html
                        template_applied = True
                        
                    if template_applied:
                        logger.info(f"Successfully applied template '{template.name}' to email")
                        
            except Exception as e:
                # Log but don't fail if template application fails
                logger.warning(f"Failed to apply email template: {e}")
                # Continue with original content

        # Create properly formatted MIME message using helper function
        raw_message = _create_mime_message(
            to=to,
            subject=subject,
            body=final_body,
            content_type=final_content_type,
            html_body=final_html_body,
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
            recipientsNotAllowed=recipients_not_allowed if allow_list else []
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
            error=str(e)
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
            error=str(e)
        )


async def draft_gmail_message(
    subject: str,
    body: str,
    user_google_email: UserGoogleEmail = None,
    to: Optional[Union[str, List[str]]] = None,
    content_type: Literal["plain", "html", "mixed"] = "mixed",
    html_body: Optional[str] = None,
    cc: Optional[Union[str, List[str]]] = None,
    bcc: Optional[Union[str, List[str]]] = None
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
    # Parameter validation and helpful error messages (same as send_gmail_message)
    if content_type == "html" and html_body and not body.strip().startswith('<'):
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
            message=error_msg,
            draftId=None,
            messageId=None,
            threadId=None,
            recipientCount=0,
            contentType=content_type,
            subject=subject,
            error="Parameter validation error: incorrect content_type usage"
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
            message=error_msg,
            draftId=None,
            messageId=None,
            threadId=None,
            recipientCount=0,
            contentType=content_type,
            subject=subject,
            error="Parameter validation error: missing html_body for mixed content"
        )

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

        # Get message ID from the draft
        message_id = created_draft.get("message", {}).get("id")
        thread_id = created_draft.get("message", {}).get("threadId")

        return DraftGmailMessageResponse(
            success=True,
            message=f"✅ Draft created! Draft ID: {draft_id}",
            draftId=draft_id,
            messageId=message_id,
            threadId=thread_id,
            recipientCount=total_recipients,
            contentType=content_type,
            subject=subject,
            error=None
        )

    except Exception as e:
        logger.error(f"Unexpected error in draft_gmail_message: {e}")
        return DraftGmailMessageResponse(
            success=False,
            message=f"❌ Unexpected error: {e}",
            draftId=None,
            messageId=None,
            threadId=None,
            recipientCount=0,
            contentType=content_type,
            subject=subject,
            error=str(e)
        )


async def reply_to_gmail_message(
    message_id: str,
    body: str,
    user_google_email: UserGoogleEmail = None,
    content_type: Literal["plain", "html", "mixed"] = "mixed",
    html_body: Optional[str] = None
) -> ReplyGmailMessageResponse:
    """
    Sends a reply to a specific Gmail message with support for HTML formatting.

    Args:
        message_id: The ID of the message to reply to
        body: Reply body content. Usage depends on content_type:
            - content_type="plain": Contains plain text only
            - content_type="html": Contains HTML content (plain text auto-generated for Gmail)
            - content_type="mixed": Contains plain text (HTML goes in html_body parameter)
        user_google_email: The user's Google email address for Gmail access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware).
        content_type: Content type - controls how body and html_body are used:
            - "plain": Plain text reply (backward compatible)
            - "html": HTML reply - put HTML content in 'body' parameter
            - "mixed": Dual content - plain text in 'body', HTML in 'html_body' (default)
        html_body: HTML content when content_type="mixed". Ignored for other content types.

    Returns:
        str: Confirmation message with the sent reply's message ID

    Examples:
        # Plain text reply
        reply_to_gmail_message("msg_123", "Thanks for your message!")

        # HTML reply (HTML content goes in 'body' parameter)
        reply_to_gmail_message("msg_123", "<p>Thanks for your <b>message</b>!</p>", content_type="html")

        # Mixed content reply
        reply_to_gmail_message("msg_123", "Thanks for your message!",
                              content_type="mixed", html_body="<p>Thanks for your <b>message</b>!</p>")

        # Auto-injected user (middleware handles user_google_email)
        reply_to_gmail_message("msg_123", "Thanks for your message!")
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
        thread_id = sent_message.get("threadId")
        
        return ReplyGmailMessageResponse(
            success=True,
            message=f"✅ Reply sent! Message ID: {sent_message_id}",
            messageId=sent_message_id,
            threadId=thread_id,
            originalMessageId=message_id,
            recipientEmail=original_from,
            contentType=content_type,
            subject=reply_subject,
            error=None
        )

    except Exception as e:
        logger.error(f"Unexpected error in reply_to_gmail_message: {e}")
        return ReplyGmailMessageResponse(
            success=False,
            message=f"❌ Unexpected error: {e}",
            messageId=None,
            threadId=None,
            originalMessageId=message_id,
            recipientEmail=None,
            contentType=content_type,
            subject=None,
            error=str(e)
        )


async def draft_gmail_reply(
    message_id: str,
    body: str,
    user_google_email: UserGoogleEmail = None,
    content_type: Literal["plain", "html", "mixed"] = "mixed",
    html_body: Optional[str] = None
) -> DraftGmailReplyResponse:
    """
    Creates a draft reply to a specific Gmail message with support for HTML formatting.

    Args:
        message_id: The ID of the message to draft a reply for
        body: Reply body content. Usage depends on content_type:
            - content_type="plain": Contains plain text only
            - content_type="html": Contains HTML content (plain text auto-generated for Gmail)
            - content_type="mixed": Contains plain text (HTML goes in html_body parameter)
        user_google_email: The user's Google email address for Gmail access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware).
        content_type: Content type - controls how body and html_body are used:
            - "plain": Plain text draft reply (backward compatible)
            - "html": HTML draft reply - put HTML content in 'body' parameter
            - "mixed": Dual content - plain text in 'body', HTML in 'html_body' (default)
        html_body: HTML content when content_type="mixed". Ignored for other content types.

    Returns:
        str: Confirmation message with the created draft's ID

    Examples:
        # Plain text draft reply
        draft_gmail_reply("msg_123", "Thanks for your message!")

        # HTML draft reply (HTML content goes in 'body' parameter)
        draft_gmail_reply("msg_123", "<p>Thanks for your <b>message</b>!</p>", content_type="html")

        # Mixed content draft reply
        draft_gmail_reply("msg_123", "Thanks for your message!",
                         content_type="mixed", html_body="<p>Thanks for your <b>message</b>!</p>")

        # Auto-injected user (middleware handles user_google_email)
        draft_gmail_reply("msg_123", "Thanks for your message!")
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
        message_id_from_draft = created_draft.get("message", {}).get("id")
        thread_id = created_draft.get("message", {}).get("threadId")
        
        return DraftGmailReplyResponse(
            success=True,
            message=f"✅ Draft reply created! Draft ID: {draft_id}",
            draftId=draft_id,
            messageId=message_id_from_draft,
            threadId=thread_id,
            originalMessageId=message_id,
            recipientEmail=original_from,
            contentType=content_type,
            subject=reply_subject,
            error=None
        )

    except Exception as e:
        logger.error(f"Unexpected error in draft_gmail_reply: {e}")
        return DraftGmailReplyResponse(
            success=False,
            message=f"❌ Unexpected error: {e}",
            draftId=None,
            messageId=None,
            threadId=None,
            originalMessageId=message_id,
            recipientEmail=None,
            contentType=content_type,
            subject=None,
            error=str(e)
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
            "openWorldHint": True
        }
    )
    async def send_gmail_message_tool(
        ctx: Annotated[Context, Field(description="FastMCP context for elicitation support and user interaction")],
        to: Annotated[Union[str, List[str]], Field(description="Recipient email address(es). Single: 'user@example.com' or Multiple: ['user1@example.com', 'user2@example.com']")],
        subject: Annotated[str, Field(description="Email subject line")],
        body: Annotated[str, Field(description="Email body content. Usage depends on content_type: 'plain' = plain text only, 'html' = HTML content (plain auto-generated), 'mixed' = plain text (HTML in html_body)")],
        user_google_email: UserGoogleEmail = None,
        content_type: Annotated[Literal["plain", "html", "mixed"], Field(description="Content type: 'plain' (text only), 'html' (HTML in body param), 'mixed' (text in body, HTML in html_body)")] = "mixed",
        html_body: Annotated[Optional[str], Field(description="HTML content when content_type='mixed'. Ignored for 'plain' and 'html' types")] = None,
        cc: Annotated[Optional[Union[str, List[str]]], Field(description="CC recipient(s). Single: 'cc@example.com' or Multiple: ['cc1@example.com', 'cc2@example.com']")] = None,
        bcc: Annotated[Optional[Union[str, List[str]]], Field(description="BCC recipient(s). Single: 'bcc@example.com' or Multiple: ['bcc1@example.com', 'bcc2@example.com']")] = None
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
        
        Args:
            ctx: FastMCP context for user interactions and elicitation
            to: Recipient email address(es)
            subject: Email subject line
            body: Email body content (usage varies by content_type)
            user_google_email: User's email address (auto-injected if None)
            content_type: How to handle body/html_body content
            html_body: HTML content for mixed-type emails
            cc: CC recipients (optional)
            bcc: BCC recipients (optional)
            
        Returns:
        SendGmailMessageResponse: Structured response with send status and details
        """
        return await send_gmail_message(ctx, to, subject, body, user_google_email, content_type, html_body, cc, bcc)

    @mcp.tool(
        name="draft_gmail_message",
        description="Create a draft email in the user's Gmail account with HTML support and multiple recipients",
        tags={"gmail", "draft", "email", "compose", "html", "save"},
        annotations={
            "title": "Draft Gmail Message",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def draft_gmail_message_tool(
        subject: Annotated[str, Field(description="Email subject line for the draft")],
        body: Annotated[str, Field(description="Email body content. Usage depends on content_type: 'plain' = plain text only, 'html' = HTML content (plain auto-generated), 'mixed' = plain text (HTML in html_body)")],
        user_google_email: UserGoogleEmail = None,
        to: Annotated[Optional[Union[str, List[str]]], Field(description="Optional recipient email address(es). Single: 'user@example.com' or Multiple: ['user1@example.com', 'user2@example.com']. Can be None for recipient-less drafts")] = None,
        content_type: Annotated[Literal["plain", "html", "mixed"], Field(description="Content type: 'plain' (text only), 'html' (HTML in body param), 'mixed' (text in body, HTML in html_body)")] = "mixed",
        html_body: Annotated[Optional[str], Field(description="HTML content when content_type='mixed'. Ignored for 'plain' and 'html' types")] = None,
        cc: Annotated[Optional[Union[str, List[str]]], Field(description="CC recipient(s). Single: 'cc@example.com' or Multiple: ['cc1@example.com', 'cc2@example.com']")] = None,
        bcc: Annotated[Optional[Union[str, List[str]]], Field(description="BCC recipient(s). Single: 'bcc@example.com' or Multiple: ['bcc1@example.com', 'bcc2@example.com']")] = None
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
        
        Args:
            subject: Email subject line
            body: Email body content (usage varies by content_type)
            user_google_email: User's email address (auto-injected if None)
            to: Optional recipient email address(es)
            content_type: How to handle body/html_body content
            html_body: HTML content for mixed-type emails
            cc: CC recipients (optional)
            bcc: BCC recipients (optional)
            
        Returns:
        DraftGmailMessageResponse: Structured response with draft creation details
        """
        return await draft_gmail_message(subject, body, user_google_email, to, content_type, html_body, cc, bcc)

    @mcp.tool(
        name="reply_to_gmail_message",
        description="Send a reply to a specific Gmail message with proper threading and HTML support",
        tags={"gmail", "reply", "send", "thread", "email", "html", "conversation"},
        annotations={
            "title": "Reply to Gmail Message",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def reply_to_gmail_message_tool(
        message_id: Annotated[str, Field(description="The ID of the original Gmail message to reply to. This maintains proper email threading")],
        body: Annotated[str, Field(description="Reply body content. Usage depends on content_type: 'plain' = plain text only, 'html' = HTML content (plain auto-generated), 'mixed' = plain text (HTML in html_body). Original message will be automatically quoted")],
        user_google_email: UserGoogleEmail = None,
        content_type: Annotated[Literal["plain", "html", "mixed"], Field(description="Content type: 'plain' (text only with quoted original), 'html' (HTML in body param with quoted original), 'mixed' (text in body, HTML in html_body, both with quoted original)")] = "mixed",
        html_body: Annotated[Optional[str], Field(description="HTML content when content_type='mixed'. The original message will be automatically quoted in HTML format. Ignored for 'plain' and 'html' types")] = None
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
        - Auto-extraction of reply-to address and subject
        - Auto-injection of user context via middleware
        
        Args:
            message_id: ID of the original message to reply to
            body: Reply body content (original message auto-quoted)
            user_google_email: User's email address (auto-injected if None)
            content_type: How to handle body/html_body content
            html_body: HTML content for mixed-type replies
            
        Returns:
        ReplyGmailMessageResponse: Structured response with reply status and threading info
        """
        return await reply_to_gmail_message(message_id, body, user_google_email, content_type, html_body)

    @mcp.tool(
        name="draft_gmail_reply",
        description="Create a draft reply to a specific Gmail message with proper threading and HTML support",
        tags={"gmail", "draft", "reply", "thread", "email", "html", "conversation", "save"},
        annotations={
            "title": "Draft Gmail Reply",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def draft_gmail_reply_tool(
        message_id: Annotated[str, Field(description="The ID of the original Gmail message to draft a reply for. This maintains proper email threading in the draft")],
        body: Annotated[str, Field(description="Draft reply body content. Usage depends on content_type: 'plain' = plain text only, 'html' = HTML content (plain auto-generated), 'mixed' = plain text (HTML in html_body). Original message will be automatically quoted")],
        user_google_email: UserGoogleEmail = None,
        content_type: Annotated[Literal["plain", "html", "mixed"], Field(description="Content type: 'plain' (text only with quoted original), 'html' (HTML in body param with quoted original), 'mixed' (text in body, HTML in html_body, both with quoted original)")] = "mixed",
        html_body: Annotated[Optional[str], Field(description="HTML content when content_type='mixed'. The original message will be automatically quoted in HTML format. Ignored for 'plain' and 'html' types")] = None
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
        - Auto-extraction of reply-to address and subject
        - Auto-injection of user context via middleware
        
        Args:
            message_id: ID of the original message to draft reply for
            body: Draft reply body content (original message auto-quoted)
            user_google_email: User's email address (auto-injected if None)
            content_type: How to handle body/html_body content
            html_body: HTML content for mixed-type draft replies
            
        Returns:
        DraftGmailReplyResponse: Structured response with draft creation and threading info
        """
        return await draft_gmail_reply(message_id, body, user_google_email, content_type, html_body)