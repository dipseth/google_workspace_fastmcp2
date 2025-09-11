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
from datetime import datetime, UTC
from typing_extensions import Optional, Literal, Any, List, Dict, Union,Annotated
from pydantic import Field
from dataclasses import dataclass

from fastmcp import FastMCP, Context
from googleapiclient.errors import HttpError

from .service import _get_gmail_service_with_fallback
from .utils import _create_mime_message, _prepare_reply_subject, _quote_original_message, _html_to_plain_text, _extract_headers, _extract_message_body, extract_email_addresses, _prepare_forward_subject, _extract_html_body, _format_forward_content
from .templates import EmailTemplateManager
from .gmail_types import (
    SendGmailMessageResponse, DraftGmailMessageResponse, ReplyGmailMessageResponse,
    DraftGmailReplyResponse, ForwardGmailMessageResponse, DraftGmailForwardResponse
)
from config.settings import settings
from tools.common_types import UserGoogleEmail


logger = logging.getLogger(__name__)

# Initialize template manager
template_manager = EmailTemplateManager()


@dataclass
class EmailAction:
    action: Literal["send", "save_draft", "cancel"]


async def _handle_elicitation_fallback(
    fallback_mode: str,
    to: Union[str, List[str]],
    subject: str,
    body: str,
    user_google_email: str,
    content_type: str,
    html_body: Optional[str],
    cc: Optional[Union[str, List[str]]],
    bcc: Optional[Union[str, List[str]]],
    recipients_not_allowed: List[str]
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
        logger.info("Fallback mode 'allow' - proceeding with send despite untrusted recipients")
        return None  # Return None to continue with normal send flow
        
    elif fallback_mode == "draft":
        # Save as draft instead of sending
        logger.info("Fallback mode 'draft' - saving as draft due to untrusted recipients")
        draft_result = await draft_gmail_message(
            subject=subject,
            body=body,
            user_google_email=user_google_email,
            to=to,
            content_type=content_type,
            html_body=html_body,
            cc=cc,
            bcc=bcc
        )
        return SendGmailMessageResponse(
            success=True,
            message=f"""📝 **EMAIL SAVED AS DRAFT** (not sent)

✅ **Action:** Saved to Gmail Drafts folder
📧 **Draft ID:** {draft_result['draft_id']}
📬 **Recipients:** {draft_result['recipient_count']} (not notified)

⚠️ **Why draft:** Recipients not on allow list: {', '.join(recipients_not_allowed)}
📱 **Cause:** Your MCP client doesn't support elicitation

🔧 **Next steps:**
   • Review draft in Gmail and send manually
   • OR add recipients to allow list for auto-sending""",
            messageId=None,
            threadId=None,
            draftId=draft_result['draft_id'],
            recipientCount=draft_result['recipient_count'],
            contentType=content_type,
            templateApplied=False,
            error=None,
            elicitationRequired=False,
            elicitationNotSupported=True,
            action="saved_draft"
        )
    else:  # fallback_mode == "block" (default)
        # Block the send and inform user
        logger.info("Fallback mode 'block' - blocking send due to untrusted recipients")
        return SendGmailMessageResponse(
            success=False,
            message=f"""🚫 **EMAIL BLOCKED** (not sent)

❌ **Action:** Send operation blocked for security
📧 **Subject:** {subject}
📬 **Recipients:** {to if isinstance(to, str) else ', '.join(to)} ({len(recipients_not_allowed)} not verified)

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
            recipientsNotAllowed=recipients_not_allowed
        )


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
            # Check if elicitation is enabled in settings
            if not settings.gmail_enable_elicitation:
                logger.info(f"Elicitation disabled in settings - applying fallback: {settings.gmail_elicitation_fallback}")
                return await _handle_elicitation_fallback(
                    settings.gmail_elicitation_fallback, to, subject, body, user_google_email,
                    content_type, html_body, cc, bcc, recipients_not_allowed
                )

            # Log elicitation trigger
            logger.info(f"Elicitation triggered for {len(recipients_not_allowed)} recipient(s) not on allow list")

            # Prepare elicitation message with better formatting
            to_display = to if isinstance(to, str) else ', '.join(to)
            cc_display = f"\n📋 **CC:** {cc if isinstance(cc, str) else ', '.join(cc)}" if cc else ""
            bcc_display = f"\n📋 **BCC:** {bcc if isinstance(bcc, str) else ', '.join(bcc)}" if bcc else ""

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
                response = await asyncio.wait_for(
                    ctx.elicit(
                        message=elicitation_message,
                        response_type=EmailAction
                    ),
                    timeout=300.0
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
                    recipientsNotAllowed=recipients_not_allowed
                )
            except Exception as elicit_error:
                # Handle clients that don't support elicitation
                error_msg = str(elicit_error).lower()
                if ("method not found" in error_msg or "not found" in error_msg or
                    "not supported" in error_msg or "unsupported" in error_msg):
                    
                    logger.warning(f"Client doesn't support elicitation - applying fallback: {settings.gmail_elicitation_fallback}")
                    fallback_result = await _handle_elicitation_fallback(
                        settings.gmail_elicitation_fallback, to, subject, body, user_google_email,
                        content_type, html_body, cc, bcc, recipients_not_allowed
                    )
                    if fallback_result is not None:
                        return fallback_result
                    # If fallback_result is None (allow mode), continue with normal sending
                else:
                    # Other elicitation errors
                    logger.error(f"Elicitation failed: {elicit_error}")
                    return SendGmailMessageResponse(
                        success=False,
                        message=f"❌ Email confirmation failed: {elicit_error}",
                        messageId=None,
                        threadId=None,
                        recipientCount=0,
                        contentType=content_type,
                        templateApplied=False,
                        error=f"Elicitation error: {elicit_error}",
                        elicitationRequired=True,
                        recipientsNotAllowed=recipients_not_allowed
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
                    recipientsNotAllowed=recipients_not_allowed
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
                        message=f"""📝 **EMAIL SAVED AS DRAFT** (not sent)

✅ **Action:** User chose to save as draft
📧 **Draft ID:** {draft_result['draft_id']}
📬 **Recipients:** {draft_result['recipient_count']} (not notified)

ℹ️ **User choice:** Save as draft via elicitation prompt
🔧 **Next step:** Review draft in Gmail and send manually""",
                        messageId=None,
                        threadId=None,
                        draftId=draft_result['draft_id'],  # Include draft ID
                        recipientCount=draft_result['recipient_count'],
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
        
        # TEMPORARILY DISABLED: Skip Gmail template processing to allow Template Parameter Middleware to work
        if False and primary_recipient:
            try:
                # Try to get template for this recipient
                template = await template_manager.get_template_for_recipient(primary_recipient)
                
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
            draft_id="",
            subject=subject,
            content_type=content_type,
            has_recipients=bool(to),
            recipient_count=0,
            userEmail=user_google_email or "",
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
            subject=subject,
            content_type=content_type,
            has_recipients=bool(to),
            recipient_count=0,
            userEmail=user_google_email or "",
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
            draft_id=draft_id,
            subject=subject,
            content_type=content_type,
            has_recipients=bool(to),
            recipient_count=total_recipients,
            userEmail=user_google_email or "",
            error=None
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
            error=str(e)
        )


async def reply_to_gmail_message(
    message_id: str,
    body: str,
    user_google_email: UserGoogleEmail = None,
    reply_mode: Literal["sender_only", "reply_all", "custom"] = "sender_only",
    to: Optional[Union[str, List[str]]] = None,
    cc: Optional[Union[str, List[str]]] = None,
    bcc: Optional[Union[str, List[str]]] = None,
    content_type: Literal["plain", "html", "mixed"] = "mixed",
    html_body: Optional[str] = None
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
    logger.info(f"[reply_to_gmail_message] Email: '{user_google_email}', Replying to Message ID: '{message_id}', reply_mode: {reply_mode}, content_type: {content_type}")

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
                raise ValueError("When using reply_mode='custom', you must provide 'to' recipients")
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
            thread_id=original_message.get("threadId")
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
            to_recipients=final_to if isinstance(final_to, list) else [final_to] if final_to else [],
            cc_recipients=final_cc if isinstance(final_cc, list) else [final_cc] if final_cc else [],
            bcc_recipients=final_bcc if isinstance(final_bcc, list) else [final_bcc] if final_bcc else [],
            userEmail=user_google_email or "",
            error=None
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
            error=str(e)
        )


async def draft_gmail_reply(
    message_id: str,
    body: str,
    user_google_email: UserGoogleEmail = None,
    reply_mode: Literal["sender_only", "reply_all", "custom"] = "sender_only",
    to: Optional[Union[str, List[str]]] = None,
    cc: Optional[Union[str, List[str]]] = None,
    bcc: Optional[Union[str, List[str]]] = None,
    content_type: Literal["plain", "html", "mixed"] = "mixed",
    html_body: Optional[str] = None
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
    logger.info(f"[draft_gmail_reply] Email: '{user_google_email}', Drafting reply to Message ID: '{message_id}', reply_mode: {reply_mode}, content_type: {content_type}")

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
                raise ValueError("When using reply_mode='custom', you must provide 'to' recipients")
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
            to_recipients=final_to if isinstance(final_to, list) else [final_to] if final_to else [],
            cc_recipients=final_cc if isinstance(final_cc, list) else [final_cc] if final_cc else [],
            bcc_recipients=final_bcc if isinstance(final_bcc, list) else [final_bcc] if final_bcc else [],
            userEmail=user_google_email or "",
            error=None
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
            error=str(e)
        )


async def forward_gmail_message(
    ctx: Context,
    message_id: str,
    to: Union[str, List[str]],
    user_google_email: UserGoogleEmail = None,
    body: Optional[str] = None,
    content_type: Literal["plain", "html", "mixed"] = "mixed",
    html_body: Optional[str] = None,
    cc: Optional[Union[str, List[str]]] = None,
    bcc: Optional[Union[str, List[str]]] = None
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
    # Format recipients for logging
    to_str = to if isinstance(to, str) else f"{len(to)} recipients"
    cc_str = f", CC: {cc if isinstance(cc, str) else f'{len(cc)} recipients'}" if cc else ""
    bcc_str = f", BCC: {bcc if isinstance(bcc, str) else f'{len(bcc)} recipients'}" if bcc else ""

    logger.info(f"[forward_gmail_message] Email: '{user_google_email}', Forwarding Message ID: '{message_id}', To: {to_str}{cc_str}{bcc_str}, content_type: {content_type}")

    # Check allow list and trigger elicitation if needed (same pattern as send_gmail_message)
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
            # Check if elicitation is enabled in settings
            if not settings.gmail_enable_elicitation:
                logger.info(f"Elicitation disabled in settings - applying fallback: {settings.gmail_elicitation_fallback}")
                fallback_result = await _handle_elicitation_fallback(
                    settings.gmail_elicitation_fallback, to, f"Fwd: Original Message",
                    body or "Forwarded message", user_google_email,
                    content_type, html_body, cc, bcc, recipients_not_allowed
                )
                if fallback_result is not None:
                    # Convert SendGmailMessageResponse to ForwardGmailMessageResponse
                    return ForwardGmailMessageResponse(
                        success=fallback_result['success'],
                        forward_message_id=fallback_result.get('messageId'),
                        original_message_id=message_id,
                        forwarded_to=to if isinstance(to, str) else ', '.join(to),
                        subject=f"Fwd: Original Message",
                        content_type=content_type,
                        to_recipients=to if isinstance(to, list) else [to] if to else [],
                        cc_recipients=cc if isinstance(cc, list) else [cc] if cc else [],
                        bcc_recipients=bcc if isinstance(bcc, list) else [bcc] if bcc else [],
                        html_preserved=False,
                        userEmail=user_google_email or "",
                        error=fallback_result.get('error'),
                        elicitationRequired=fallback_result.get('elicitationRequired', False),
                        elicitationNotSupported=fallback_result.get('elicitationNotSupported', False),
                        recipientsNotAllowed=fallback_result.get('recipientsNotAllowed', []),
                        action=fallback_result.get('action', 'blocked'),
                        draftId=fallback_result.get('draftId')
                    )

            # Log elicitation trigger
            logger.info(f"Elicitation triggered for {len(recipients_not_allowed)} recipient(s) not on allow list")

            # Prepare elicitation message
            to_display = to if isinstance(to, str) else ', '.join(to)
            cc_display = f"\n📋 **CC:** {cc if isinstance(cc, str) else ', '.join(cc)}" if cc else ""
            bcc_display = f"\n📋 **BCC:** {bcc if isinstance(bcc, str) else ', '.join(bcc)}" if bcc else ""

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
   • HTML Preservation: {'Yes' if content_type in ['html', 'mixed'] else 'No'}{body_preview}

🔒 **Security Notice:** This recipient is not on your allow list.

❓ **Choose your action:**
   • **Send** - Forward the email immediately
   • **Save as Draft** - Save to drafts folder without sending
   • **Cancel** - Discard the forward
   
⏰ Auto-cancels in 300 seconds if no response"""

            # Trigger elicitation with graceful fallback for unsupported clients
            try:
                response = await asyncio.wait_for(
                    ctx.elicit(
                        message=elicitation_message,
                        response_type=EmailAction
                    ),
                    timeout=300.0
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
                    recipientsNotAllowed=recipients_not_allowed
                )
            except Exception as elicit_error:
                # Handle clients that don't support elicitation
                error_msg = str(elicit_error).lower()
                if ("method not found" in error_msg or "not found" in error_msg or
                    "not supported" in error_msg or "unsupported" in error_msg):
                    
                    logger.warning(f"Client doesn't support elicitation - applying fallback: {settings.gmail_elicitation_fallback}")
                    fallback_result = await _handle_elicitation_fallback(
                        settings.gmail_elicitation_fallback, to, f"Fwd: Original Message",
                        body or "Forwarded message", user_google_email,
                        content_type, html_body, cc, bcc, recipients_not_allowed
                    )
                    if fallback_result is not None:
                        # Convert SendGmailMessageResponse to ForwardGmailMessageResponse
                        return ForwardGmailMessageResponse(
                            success=fallback_result['success'],
                            forward_message_id=fallback_result.get('messageId'),
                            original_message_id=message_id,
                            forwarded_to=to if isinstance(to, str) else ', '.join(to),
                            subject=f"Fwd: Original Message",
                            content_type=content_type,
                            to_recipients=to if isinstance(to, list) else [to] if to else [],
                            cc_recipients=cc if isinstance(cc, list) else [cc] if cc else [],
                            bcc_recipients=bcc if isinstance(bcc, list) else [bcc] if bcc else [],
                            html_preserved=False,
                            userEmail=user_google_email or "",
                            error=fallback_result.get('error'),
                            elicitationRequired=fallback_result.get('elicitationRequired', False),
                            elicitationNotSupported=fallback_result.get('elicitationNotSupported', False),
                            recipientsNotAllowed=fallback_result.get('recipientsNotAllowed', []),
                            action=fallback_result.get('action', 'blocked'),
                            draftId=fallback_result.get('draftId')
                        )
                    # If fallback_result is None (allow mode), continue with normal forwarding
                else:
                    # Other elicitation errors
                    logger.error(f"Elicitation failed: {elicit_error}")
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
                        error=f"Forward confirmation failed: {elicit_error}",
                        elicitationRequired=True,
                        recipientsNotAllowed=recipients_not_allowed
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
                    recipientsNotAllowed=recipients_not_allowed
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
                        recipientsNotAllowed=recipients_not_allowed
                    )
                elif user_choice == "save_draft":
                    logger.info("User chose to save forward as draft")
                    # Create draft instead of sending
                    draft_result = await draft_gmail_forward(
                        message_id=message_id,
                        to=to,
                        user_google_email=user_google_email,
                        body=body,
                        content_type=content_type,
                        html_body=html_body,
                        cc=cc,
                        bcc=bcc
                    )
                    # Return as forward response with draft info
                    return ForwardGmailMessageResponse(
                        success=True,
                        forward_message_id="",
                        original_message_id=message_id,
                        forwarded_to=to if isinstance(to, str) else ', '.join(to),
                        subject=draft_result.get('subject', ''),
                        content_type=content_type,
                        to_recipients=draft_result.get('to_recipients', []),
                        cc_recipients=draft_result.get('cc_recipients', []),
                        bcc_recipients=draft_result.get('bcc_recipients', []),
                        html_preserved=draft_result.get('html_preserved', False),
                        userEmail=user_google_email or "",
                        error=None,
                        elicitationRequired=True,
                        recipientsNotAllowed=recipients_not_allowed,
                        action="saved_draft",
                        draftId=draft_result.get('draft_id')
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
                        recipientsNotAllowed=recipients_not_allowed
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
                    recipientsNotAllowed=recipients_not_allowed
                )
        else:
            # All recipients are on allow list
            logger.info(f"All {len(all_recipients)} recipient(s) are on allow list - forwarding without elicitation")
    else:
        # No allow list configured
        logger.debug("No Gmail allow list configured - forwarding without elicitation")

    try:
        gmail_service = await _get_gmail_service_with_fallback(user_google_email)

        # Fetch the original message to get headers and body for forwarding
        original_message = await asyncio.to_thread(
            gmail_service.users().messages().get(userId="me", id=message_id, format="full").execute
        )
        payload = original_message.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
        original_subject = headers.get("Subject", "(no subject)")

        # Extract both plain text and HTML content from original message
        original_plain_body = _extract_message_body(payload)
        original_html_body = _extract_html_body(payload)
        
        # Determine if we have HTML content to preserve
        has_html = bool(original_html_body)
        html_preserved = has_html and content_type in ['html', 'mixed']

        # Prepare forward subject
        forward_subject = _prepare_forward_subject(original_subject)

        # Format the forwarded content based on content_type
        if content_type == "plain":
            # Plain text only - use plain text version of original
            forwarded_content = _format_forward_content(original_plain_body, headers, is_html=False)
            if body:
                full_body = f"{body}{forwarded_content}"
            else:
                full_body = forwarded_content
            final_html_body = None
            
        elif content_type == "html":
            # HTML only - use HTML version if available, fallback to plain text
            content_to_forward = original_html_body if has_html else original_plain_body
            forwarded_content = _format_forward_content(content_to_forward, headers, is_html=has_html)
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
            plain_forwarded = _format_forward_content(original_plain_body, headers, is_html=False)
            if body:
                full_plain_body = f"{body}{plain_forwarded}"
            else:
                full_plain_body = plain_forwarded
            
            # HTML version
            if has_html:
                html_forwarded = _format_forward_content(original_html_body, headers, is_html=True)
                if html_body:
                    final_html_body = f"{html_body}{html_forwarded}"
                else:
                    final_html_body = html_forwarded
            else:
                # No HTML content in original, convert plain text to HTML
                html_forwarded = _format_forward_content(original_plain_body, headers, is_html=True)
                if html_body:
                    final_html_body = f"{html_body}{html_forwarded}"
                else:
                    final_html_body = html_forwarded
            
            full_body = full_plain_body

        # Create properly formatted MIME message using helper function
        raw_message = _create_mime_message(
            to=to,
            cc=cc,
            bcc=bcc,
            subject=forward_subject,
            body=full_body,
            content_type=content_type,
            html_body=final_html_body,
            from_email=user_google_email
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
        
        forwarded_to_str = format_recipient_string(to)
        
        return ForwardGmailMessageResponse(
            success=True,
            forward_message_id=sent_message_id,
            original_message_id=message_id,
            forwarded_to=forwarded_to_str,
            subject=forward_subject,
            content_type=content_type,
            to_recipients=to if isinstance(to, list) else [to] if to else [],
            cc_recipients=cc if isinstance(cc, list) else [cc] if cc else [],
            bcc_recipients=bcc if isinstance(bcc, list) else [bcc] if bcc else [],
            html_preserved=html_preserved,
            userEmail=user_google_email or "",
            error=None,
            elicitationRequired=bool(recipients_not_allowed) if allow_list else False,
            recipientsNotAllowed=recipients_not_allowed if allow_list else []
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
            error=str(e)
        )


async def draft_gmail_forward(
    message_id: str,
    to: Union[str, List[str]],
    user_google_email: UserGoogleEmail = None,
    body: Optional[str] = None,
    content_type: Literal["plain", "html", "mixed"] = "mixed",
    html_body: Optional[str] = None,
    cc: Optional[Union[str, List[str]]] = None,
    bcc: Optional[Union[str, List[str]]] = None
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
    # Format recipients for logging
    to_str = to if isinstance(to, str) else f"{len(to)} recipients"
    cc_str = f", CC: {cc if isinstance(cc, str) else f'{len(cc)} recipients'}" if cc else ""
    bcc_str = f", BCC: {bcc if isinstance(bcc, str) else f'{len(bcc)} recipients'}" if bcc else ""

    logger.info(f"[draft_gmail_forward] Email: '{user_google_email}', Drafting forward of Message ID: '{message_id}', To: {to_str}{cc_str}{bcc_str}, content_type: {content_type}")

    try:
        gmail_service = await _get_gmail_service_with_fallback(user_google_email)

        # Fetch the original message to get headers and body for forwarding
        original_message = await asyncio.to_thread(
            gmail_service.users().messages().get(userId="me", id=message_id, format="full").execute
        )
        payload = original_message.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
        original_subject = headers.get("Subject", "(no subject)")

        # Extract both plain text and HTML content from original message
        original_plain_body = _extract_message_body(payload)
        original_html_body = _extract_html_body(payload)
        
        # Determine if we have HTML content to preserve
        has_html = bool(original_html_body)
        html_preserved = has_html and content_type in ['html', 'mixed']

        # Prepare forward subject
        forward_subject = _prepare_forward_subject(original_subject)

        # Format the forwarded content based on content_type
        if content_type == "plain":
            # Plain text only - use plain text version of original
            forwarded_content = _format_forward_content(original_plain_body, headers, is_html=False)
            if body:
                full_body = f"{body}{forwarded_content}"
            else:
                full_body = forwarded_content
            final_html_body = None
            
        elif content_type == "html":
            # HTML only - use HTML version if available, fallback to plain text
            content_to_forward = original_html_body if has_html else original_plain_body
            forwarded_content = _format_forward_content(content_to_forward, headers, is_html=has_html)
            if body:
                full_body = f"{body}{forwarded_content}"
            else:
                full_body = forwarded_content
            final_html_body = None
            
        elif content_type == "mixed":
            # Mixed content - prepare both plain and HTML versions
            # Plain text version
            plain_forwarded = _format_forward_content(original_plain_body, headers, is_html=False)
            if body:
                full_plain_body = f"{body}{plain_forwarded}"
            else:
                full_plain_body = plain_forwarded
            
            # HTML version
            if has_html:
                html_forwarded = _format_forward_content(original_html_body, headers, is_html=True)
                if html_body:
                    final_html_body = f"{html_body}{html_forwarded}"
                else:
                    final_html_body = html_forwarded
            else:
                # No HTML content in original, convert plain text to HTML
                html_forwarded = _format_forward_content(original_plain_body, headers, is_html=True)
                if html_body:
                    final_html_body = f"{html_body}{html_forwarded}"
                else:
                    final_html_body = html_forwarded
            
            full_body = full_plain_body

        # Create properly formatted MIME message using helper function
        raw_message = _create_mime_message(
            to=to,
            cc=cc,
            bcc=bcc,
            subject=forward_subject,
            body=full_body,
            content_type=content_type,
            html_body=final_html_body,
            from_email=user_google_email
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
        
        forwarded_to_str = format_recipient_string(to)
        
        return DraftGmailForwardResponse(
            success=True,
            draft_id=draft_id,
            original_message_id=message_id,
            forwarded_to=forwarded_to_str,
            subject=forward_subject,
            content_type=content_type,
            to_recipients=to if isinstance(to, list) else [to] if to else [],
            cc_recipients=cc if isinstance(cc, list) else [cc] if cc else [],
            bcc_recipients=bcc if isinstance(bcc, list) else [bcc] if bcc else [],
            html_preserved=html_preserved,
            userEmail=user_google_email or "",
            error=None
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
        reply_mode: Annotated[Literal["sender_only", "reply_all", "custom"], Field(description="Who receives the reply: 'sender_only' = only original sender (default), 'reply_all' = all original recipients, 'custom' = use provided to/cc/bcc parameters")] = "sender_only",
        to: Annotated[Optional[Union[str, List[str]]], Field(description="Recipient(s) when reply_mode='custom'. Single: 'user@example.com' or Multiple: ['user1@example.com', 'user2@example.com']")] = None,
        cc: Annotated[Optional[Union[str, List[str]]], Field(description="CC recipient(s) when reply_mode='custom'. Single: 'cc@example.com' or Multiple: ['cc1@example.com', 'cc2@example.com']")] = None,
        bcc: Annotated[Optional[Union[str, List[str]]], Field(description="BCC recipient(s) when reply_mode='custom'. Single: 'bcc@example.com' or Multiple: ['bcc1@example.com', 'bcc2@example.com']")] = None,
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
        return await reply_to_gmail_message(message_id, body, user_google_email, reply_mode, to, cc, bcc, content_type, html_body)

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
        reply_mode: Annotated[Literal["sender_only", "reply_all", "custom"], Field(description="Who receives the reply: 'sender_only' = only original sender (default), 'reply_all' = all original recipients, 'custom' = use provided to/cc/bcc parameters")] = "sender_only",
        to: Annotated[Optional[Union[str, List[str]]], Field(description="Recipient(s) when reply_mode='custom'. Single: 'user@example.com' or Multiple: ['user1@example.com', 'user2@example.com']")] = None,
        cc: Annotated[Optional[Union[str, List[str]]], Field(description="CC recipient(s) when reply_mode='custom'. Single: 'cc@example.com' or Multiple: ['cc1@example.com', 'cc2@example.com']")] = None,
        bcc: Annotated[Optional[Union[str, List[str]]], Field(description="BCC recipient(s) when reply_mode='custom'. Single: 'bcc@example.com' or Multiple: ['bcc1@example.com', 'bcc2@example.com']")] = None,
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
        return await draft_gmail_reply(message_id, body, user_google_email, reply_mode, to, cc, bcc, content_type, html_body)

    @mcp.tool(
        name="forward_gmail_message",
        description="Forward a Gmail message to specified recipients with HTML formatting preservation and elicitation support",
        tags={"gmail", "forward", "send", "email", "html", "elicitation", "compose"},
        annotations={
            "title": "Forward Gmail Message",
            "readOnlyHint": False,  # Sends emails, modifies state
            "destructiveHint": False,  # Creates new content, doesn't destroy
            "idempotentHint": False,  # Multiple forwards create multiple emails
            "openWorldHint": True
        }
    )
    async def forward_gmail_message_tool(
        ctx: Annotated[Context, Field(description="FastMCP context for elicitation support and user interaction")],
        message_id: Annotated[str, Field(description="The ID of the Gmail message to forward. This will include the original message content and headers")],
        to: Annotated[Union[str, List[str]], Field(description="Recipient email address(es). Single: 'user@example.com' or Multiple: ['user1@example.com', 'user2@example.com']")],
        user_google_email: UserGoogleEmail = None,
        body: Annotated[Optional[str], Field(description="Optional additional message body to add before the forwarded content. Usage depends on content_type: 'plain' = plain text only, 'html' = HTML content, 'mixed' = plain text (HTML in html_body)")] = None,
        content_type: Annotated[Literal["plain", "html", "mixed"], Field(description="Content type: 'plain' (converts original HTML to text), 'html' (preserves HTML formatting), 'mixed' (both plain and HTML versions - recommended)")] = "mixed",
        html_body: Annotated[Optional[str], Field(description="HTML content when content_type='mixed'. This will be added before the forwarded HTML content. Ignored for 'plain' and 'html' types")] = None,
        cc: Annotated[Optional[Union[str, List[str]]], Field(description="CC recipient(s). Single: 'cc@example.com' or Multiple: ['cc1@example.com', 'cc2@example.com']")] = None,
        bcc: Annotated[Optional[Union[str, List[str]]], Field(description="BCC recipient(s). Single: 'bcc@example.com' or Multiple: ['bcc1@example.com', 'bcc2@example.com']")] = None
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
        return await forward_gmail_message(ctx, message_id, to, user_google_email, body, content_type, html_body, cc, bcc)

    @mcp.tool(
        name="draft_gmail_forward",
        description="Create a draft forward of a Gmail message with HTML formatting preservation",
        tags={"gmail", "draft", "forward", "email", "html", "save", "compose"},
        annotations={
            "title": "Draft Gmail Forward",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def draft_gmail_forward_tool(
        message_id: Annotated[str, Field(description="The ID of the Gmail message to create a forward draft for. This will include the original message content and headers")],
        to: Annotated[Union[str, List[str]], Field(description="Recipient email address(es). Single: 'user@example.com' or Multiple: ['user1@example.com', 'user2@example.com']")],
        user_google_email: UserGoogleEmail = None,
        body: Annotated[Optional[str], Field(description="Optional additional message body to add before the forwarded content. Usage depends on content_type: 'plain' = plain text only, 'html' = HTML content, 'mixed' = plain text (HTML in html_body)")] = None,
        content_type: Annotated[Literal["plain", "html", "mixed"], Field(description="Content type: 'plain' (converts original HTML to text), 'html' (preserves HTML formatting), 'mixed' (both plain and HTML versions - recommended)")] = "mixed",
        html_body: Annotated[Optional[str], Field(description="HTML content when content_type='mixed'. This will be added before the forwarded HTML content. Ignored for 'plain' and 'html' types")] = None,
        cc: Annotated[Optional[Union[str, List[str]]], Field(description="CC recipient(s). Single: 'cc@example.com' or Multiple: ['cc1@example.com', 'cc2@example.com']")] = None,
        bcc: Annotated[Optional[Union[str, List[str]]], Field(description="BCC recipient(s). Single: 'bcc@example.com' or Multiple: ['bcc1@example.com', 'bcc2@example.com']")] = None
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
        return await draft_gmail_forward(message_id, to, user_google_email, body, content_type, html_body, cc, bcc)