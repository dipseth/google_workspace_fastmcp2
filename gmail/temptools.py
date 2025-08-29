#     @mcp.tool(
#         name="search_gmail_messages",
#         description="Search messages in Gmail account using Gmail query syntax with message and thread IDs",
#         tags={"gmail", "search", "messages", "email"},
#         annotations={
#             "title": "Gmail Message Search",
#             "readOnlyHint": True,  # Only searches, doesn't modify
#             "destructiveHint": False,  # Safe read-only operation
#             "idempotentHint": True,  # Multiple calls return same result
#             "openWorldHint": True  # Interacts with external Gmail API
#         }
#     )
#     async def search_gmail_messages(
#         user_google_email: str, 
#         query: str, 
#         page_size: int = 10
#     ) -> str:
#         """
#         Searches messages in a user's Gmail account based on a query.
#         Returns both Message IDs and Thread IDs for each found message, along with Gmail web interface links for manual verification.

#         Args:
#             user_google_email: The user's Google email address
#             query: The search query. Supports standard Gmail search operators
#             page_size: The maximum number of messages to return (default: 10)

#         Returns:
#             str: LLM-friendly structured results with Message IDs, Thread IDs, and clickable Gmail web interface URLs
#         """
#         logger.info(f"[search_gmail_messages] Email: '{user_google_email}', Query: '{query}'")
        
#         try:
#             # Get Gmail service with fallback support
#             gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
#             response = await asyncio.to_thread(
#                 gmail_service.users()
#                 .messages()
#                 .list(userId="me", q=query, maxResults=page_size)
#                 .execute
#             )
#             messages = response.get("messages", [])
#             formatted_output = _format_gmail_results_plain(messages, query)

#             logger.info(f"[search_gmail_messages] Found {len(messages)} messages")
#             return formatted_output
                
#         except HttpError as e:
#             logger.error(f"Gmail API error in search_gmail_messages: {e}")
#             return f"❌ Gmail API error: {e}"
            
#         except Exception as e:
#             logger.error(f"Unexpected error in search_gmail_messages: {e}")
#             return f"❌ Unexpected error: {e}"

#     @mcp.tool(
#         name="get_gmail_message_content",
#         description="Retrieve the full content (subject, sender, body) of a specific Gmail message",
#         tags={"gmail", "message", "content", "email"},
#         annotations={
#             "title": "Gmail Message Content",
#             "readOnlyHint": True,
#             "destructiveHint": False,
#             "idempotentHint": True,
#             "openWorldHint": True
#         }
#     )
#     async def get_gmail_message_content(
#         user_google_email: str,
#         message_id: str
#     ) -> str:
#         """
#         Retrieves the full content (subject, sender, plain text body) of a specific Gmail message.

#         Args:
#             user_google_email: The user's Google email address
#             message_id: The unique ID of the Gmail message to retrieve

#         Returns:
#             str: The message details including subject, sender, and body content
#         """
#         logger.info(f"[get_gmail_message_content] Message ID: '{message_id}', Email: '{user_google_email}'")
        
#         try:
#             gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
#             # Fetch message metadata first to get headers
#             message_metadata = await asyncio.to_thread(
#                 gmail_service.users()
#                 .messages()
#                 .get(
#                     userId="me",
#                     id=message_id,
#                     format="metadata",
#                     metadataHeaders=["Subject", "From"],
#                 )
#                 .execute
#             )

#             headers = {
#                 h["name"]: h["value"]
#                 for h in message_metadata.get("payload", {}).get("headers", [])
#             }
#             subject = headers.get("Subject", "(no subject)")
#             sender = headers.get("From", "(unknown sender)")

#             # Now fetch the full message to get the body parts
#             message_full = await asyncio.to_thread(
#                 gmail_service.users()
#                 .messages()
#                 .get(
#                     userId="me",
#                     id=message_id,
#                     format="full",  # Request full payload for body
#                 )
#                 .execute
#             )

#             # Extract the plain text body using helper function
#             payload = message_full.get("payload", {})
#             body_data = _extract_message_body(payload)

#             content_text = "\n".join(
#                 [
#                     f"Subject: {subject}",
#                     f"From:    {sender}",
#                     f"\n--- BODY ---\n{body_data or '[No text/plain body found]'}",
#                 ]
#             )
#             return content_text
                
#         except HttpError as e:
#             logger.error(f"Gmail API error in get_gmail_message_content: {e}")
#             return f"❌ Gmail API error: {e}"
            
#         except Exception as e:
#             logger.error(f"Unexpected error in get_gmail_message_content: {e}")
#             return f"❌ Unexpected error: {e}"

#     @mcp.tool(
#         name="get_gmail_messages_content_batch",
#         description="Retrieve content of multiple Gmail messages in a single batch request (up to 100 messages)",
#         tags={"gmail", "batch", "messages", "content", "email"},
#         annotations={
#             "title": "Gmail Batch Message Content",
#             "readOnlyHint": True,
#             "destructiveHint": False,
#             "idempotentHint": True,
#             "openWorldHint": True
#         }
#     )
#     async def get_gmail_messages_content_batch(
#         user_google_email: str,
#         message_ids: List[str],
#         format: Literal["full", "metadata"] = "full"
#     ) -> str:
#         """
#         Retrieves the content of multiple Gmail messages in a single batch request.
#         Supports up to 100 messages per request using Google's batch API.

#         Args:
#             user_google_email: The user's Google email address
#             message_ids: List of Gmail message IDs to retrieve (max 100)
#             format: Message format. "full" includes body, "metadata" only headers

#         Returns:
#             str: A formatted list of message contents with separators
#         """
#         logger.info(f"[get_gmail_messages_content_batch] Message count: {len(message_ids)}, Email: '{user_google_email}'")
        
#         if not message_ids:
#             return "❌ No message IDs provided"
        
#         try:
#             gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
#             output_messages = []

#             # Process in chunks of 100 (Gmail batch limit)
#             for chunk_start in range(0, len(message_ids), 100):
#                 chunk_ids = message_ids[chunk_start:chunk_start + 100]
#                 results: Dict[str, Dict] = {}

#                 def _batch_callback(request_id, response, exception):
#                     """Callback for batch requests"""
#                     results[request_id] = {"data": response, "error": exception}

#                 # Try to use batch API
#                 try:
#                     batch = gmail_service.new_batch_http_request(callback=_batch_callback)

#                     for mid in chunk_ids:
#                         if format == "metadata":
#                             req = gmail_service.users().messages().get(
#                                 userId="me",
#                                 id=mid,
#                                 format="metadata",
#                                 metadataHeaders=["Subject", "From"]
#                             )
#                         else:
#                             req = gmail_service.users().messages().get(
#                                 userId="me",
#                                 id=mid,
#                                 format="full"
#                             )
#                         batch.add(req, request_id=mid)

#                     # Execute batch request
#                     await asyncio.to_thread(batch.execute)

#                 except Exception as batch_error:
#                     # Fallback to asyncio.gather if batch API fails
#                     logger.warning(f"[get_gmail_messages_content_batch] Batch API failed, falling back to asyncio.gather: {batch_error}")

#                     async def fetch_message(mid: str):
#                         try:
#                             if format == "metadata":
#                                 msg = await asyncio.to_thread(
#                                     gmail_service.users().messages().get(
#                                         userId="me",
#                                         id=mid,
#                                         format="metadata",
#                                         metadataHeaders=["Subject", "From"]
#                                     ).execute
#                                 )
#                             else:
#                                 msg = await asyncio.to_thread(
#                                     gmail_service.users().messages().get(
#                                         userId="me",
#                                         id=mid,
#                                         format="full"
#                                     ).execute
#                                 )
#                             return mid, msg, None
#                         except Exception as e:
#                             return mid, None, e

#                     # Fetch all messages in parallel
#                     fetch_results = await asyncio.gather(
#                         *[fetch_message(mid) for mid in chunk_ids],
#                         return_exceptions=False
#                     )

#                     # Convert to results format
#                     for mid, msg, error in fetch_results:
#                         results[mid] = {"data": msg, "error": error}

#                 # Process results for this chunk
#                 for mid in chunk_ids:
#                     entry = results.get(mid, {"data": None, "error": "No result"})

#                     if entry["error"]:
#                         output_messages.append(f"⚠️ Message {mid}: {entry['error']}\n")
#                     else:
#                         message = entry["data"]
#                         if not message:
#                             output_messages.append(f"⚠️ Message {mid}: No data returned\n")
#                             continue

#                         # Extract content based on format
#                         payload = message.get("payload", {})

#                         if format == "metadata":
#                             headers = _extract_headers(payload, ["Subject", "From"])
#                             subject = headers.get("Subject", "(no subject)")
#                             sender = headers.get("From", "(unknown sender)")

#                             output_messages.append(
#                                 f"Message ID: {mid}\n"
#                                 f"Subject: {subject}\n"
#                                 f"From: {sender}\n"
#                                 f"Web Link: {_generate_gmail_web_url(mid)}\n"
#                             )
#                         else:
#                             # Full format - extract body too
#                             headers = _extract_headers(payload, ["Subject", "From"])
#                             subject = headers.get("Subject", "(no subject)")
#                             sender = headers.get("From", "(unknown sender)")
#                             body = _extract_message_body(payload)

#                             output_messages.append(
#                                 f"Message ID: {mid}\n"
#                                 f"Subject: {subject}\n"
#                                 f"From: {sender}\n"
#                                 f"Web Link: {_generate_gmail_web_url(mid)}\n"
#                                 f"\n{body or '[No text/plain body found]'}\n"
#                             )

#             # Combine all messages with separators
#             final_output = f"Retrieved {len(message_ids)} messages:\n\n"
#             final_output += "\n---\n\n".join(output_messages)

#             return final_output
                
#         except Exception as e:
#             logger.error(f"Unexpected error in get_gmail_messages_content_batch: {e}")
#             return f"❌ Unexpected error: {e}"

#     @mcp.tool(
#         name="send_gmail_message",
#         description="Send an email using the user's Gmail account",
#         tags={"gmail", "send", "email", "compose"},
#         annotations={
#             "title": "Send Gmail Message",
#             "readOnlyHint": False,  # Sends emails, modifies state
#             "destructiveHint": False,  # Creates new content, doesn't destroy
#             "idempotentHint": False,  # Multiple sends create multiple emails
#             "openWorldHint": True
#         }
#     )
#     async def send_gmail_message(
#         ctx: Context,
#         user_google_email: str,
#         to: Union[str, List[str]],
#         subject: str,
#         body: str,
#         content_type: Literal["plain", "html", "mixed"] = "mixed",
#         html_body: Optional[str] = None,
#         cc: Optional[Union[str, List[str]]] = None,
#         bcc: Optional[Union[str, List[str]]] = None
#     ) -> str:
#         """
#         Sends an email using the user's Gmail account with support for HTML formatting and multiple recipients.

#         Features elicitation for recipients not on the allow list - if any recipient
#         is not on the configured allow list, the tool will ask for confirmation
#         before sending the email.

#         Args:
#             ctx: FastMCP context for elicitation support
#             user_google_email: The user's Google email address
#             to: Recipient email address(es) - can be a single string or list of strings
#             subject: Email subject
#             body: Email body content. Usage depends on content_type:
#                 - content_type="plain": Contains plain text only
#                 - content_type="html": Contains HTML content (plain text auto-generated for Gmail)
#                 - content_type="mixed": Contains plain text (HTML goes in html_body parameter)
#             content_type: Content type - controls how body and html_body are used:
#                 - "plain": Plain text email (backward compatible)
#                 - "html": HTML email - put HTML content in 'body' parameter
#                 - "mixed": Dual content - plain text in 'body', HTML in 'html_body' (default)
#             html_body: HTML content when content_type="mixed". Ignored for other content types.
#             cc: Optional CC recipient(s) - can be a single string or list of strings
#             bcc: Optional BCC recipient(s) - can be a single string or list of strings

#         Returns:
#             str: Confirmation message with the sent email's message ID

#         Examples:
#             # Plain text (backward compatible)
#             send_gmail_message(ctx, user_email, "user@example.com", "Subject", "Plain text body")

#             # HTML email (HTML content goes in 'body' parameter)
#             send_gmail_message(ctx, user_email, "user@example.com", "Subject", "<h1>HTML content</h1>", content_type="html")

#             # Mixed content (separate plain and HTML versions)
#             send_gmail_message(ctx, user_email, "user@example.com", "Subject", "Plain version",
#                               content_type="mixed", html_body="<h1>HTML version</h1>")

#             # Multiple recipients with HTML
#             send_gmail_message(ctx, user_email, ["user1@example.com", "user2@example.com"],
#                               "Subject", "<p>HTML for everyone!</p>", content_type="html",
#                               cc="manager@example.com")
#         """
#         # Parameter validation and helpful error messages
#         if content_type == "html" and html_body and not body.strip().startswith('<'):
#             return f"❌ **Parameter Usage Error for content_type='html'**\n\n" \
#                    f"When using content_type='html':\n" \
#                    f"• Put your HTML content in the 'body' parameter\n" \
#                    f"• The 'html_body' parameter is ignored\n\n" \
#                    f"**For your case, try one of these:**\n" \
#                    f"1. Use content_type='mixed' (uses both body and html_body)\n" \
#                    f"2. Put HTML in 'body' parameter and remove 'html_body'\n\n" \
#                    f"**Example:** body='<h1>Your HTML here</h1>', content_type='html'"
        
#         if content_type == "mixed" and not html_body:
#             return f"❌ **Missing HTML Content for content_type='mixed'**\n\n" \
#                    f"When using content_type='mixed', you must provide:\n" \
#                    f"• Plain text in 'body' parameter\n" \
#                    f"• HTML content in 'html_body' parameter"
        
#         # Format recipients for logging
#         to_str = to if isinstance(to, str) else f"{len(to)} recipients"
#         cc_str = f", CC: {cc if isinstance(cc, str) else f'{len(cc)} recipients'}" if cc else ""
#         bcc_str = f", BCC: {bcc if isinstance(bcc, str) else f'{len(bcc)} recipients'}" if bcc else ""

#         logger.info(f"[send_gmail_message] Sending to: {to_str}{cc_str}{bcc_str}, from: {user_google_email}, content_type: {content_type}")

#         # Check allow list and trigger elicitation if needed
#         allow_list = settings.get_gmail_allow_list()

#         if allow_list:
#             # Collect all recipient emails for the message
#             all_recipients = []

#             # Process 'to' recipients
#             if isinstance(to, str):
#                 all_recipients.extend([email.strip() for email in to.split(',')])
#             elif isinstance(to, list):
#                 all_recipients.extend(to)

#             # Process 'cc' recipients
#             if cc:
#                 if isinstance(cc, str):
#                     all_recipients.extend([email.strip() for email in cc.split(',')])
#                 elif isinstance(cc, list):
#                     all_recipients.extend(cc)

#             # Process 'bcc' recipients
#             if bcc:
#                 if isinstance(bcc, str):
#                     all_recipients.extend([email.strip() for email in bcc.split(',')])
#                 elif isinstance(bcc, list):
#                     all_recipients.extend(bcc)

#             # Normalize all recipient emails (lowercase, strip whitespace)
#             all_recipients = [email.strip().lower() for email in all_recipients if email]

#             # Normalize allow list emails
#             normalized_allow_list = [email.lower() for email in allow_list]

#             # Check if any recipient is NOT on the allow list
#             recipients_not_allowed = [
#                 email for email in all_recipients
#                 if email not in normalized_allow_list
#             ]

#             if recipients_not_allowed:
#                 # Log elicitation trigger
#                 logger.info(f"Elicitation triggered for {len(recipients_not_allowed)} recipient(s) not on allow list")

#                 # Prepare elicitation message
#                 to_display = to if isinstance(to, str) else ', '.join(to)
#                 cc_display = f"\nCC: {cc if isinstance(cc, str) else ', '.join(cc)}" if cc else ""
#                 bcc_display = f"\nBCC: {bcc if isinstance(bcc, str) else ', '.join(bcc)}" if bcc else ""

#                 # Truncate body for preview if too long
#                 body_preview = body[:500] + "... [truncated]" if len(body) > 500 else body

#                 elicitation_message = f"""📧 Email Ready to Send

# To: {to_display}{cc_display}{bcc_display}
# Subject: {subject}
# Content Type: {content_type}
# Body Preview: {body_preview}

# Would you like to send this email?"""

#                 # Trigger elicitation
#                 response = await ctx.elicit(
#                     prompt=elicitation_message,
#                     response_type=None  # Just need approve/decline
#                 )

#                 if response.action == "decline":
#                     logger.info("User declined to send email")
#                     return json.dumps({
#                         "success": False,
#                         "message": "Email not sent - user declined",
#                         "recipients_not_on_allow_list": recipients_not_allowed
#                     })
#                 elif response.action == "cancel":
#                     logger.info("User cancelled email operation")
#                     return json.dumps({
#                         "success": False,
#                         "message": "Email operation cancelled",
#                         "recipients_not_on_allow_list": recipients_not_allowed
#                     })
#                 # If accept, continue with sending
#                 logger.info("User approved sending email")
#             else:
#                 # All recipients are on allow list
#                 logger.info(f"All {len(all_recipients)} recipient(s) are on allow list - sending without elicitation")
#         else:
#             # No allow list configured
#             logger.debug("No Gmail allow list configured - sending without elicitation")

#         try:
#             gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
#             # Create properly formatted MIME message using helper function
#             raw_message = _create_mime_message(
#                 to=to,
#                 subject=subject,
#                 body=body,
#                 content_type=content_type,
#                 html_body=html_body,
#                 from_email=user_google_email,
#                 cc=cc,
#                 bcc=bcc
#             )
            
#             send_body = {"raw": raw_message}

#             # Send the message
#             sent_message = await asyncio.to_thread(
#                 gmail_service.users().messages().send(userId="me", body=send_body).execute
#             )
#             message_id = sent_message.get("id")
            
#             # Count total recipients for confirmation
#             total_recipients = (len(to) if isinstance(to, list) else 1) + \
#                              (len(cc) if isinstance(cc, list) else (1 if cc else 0)) + \
#                              (len(bcc) if isinstance(bcc, list) else (1 if bcc else 0))
            
#             return f"✅ Email sent to {total_recipients} recipient(s)! Message ID: {message_id} (Content type: {content_type})"
                
#         except HttpError as e:
#             logger.error(f"Gmail API error in send_gmail_message: {e}")
#             return f"❌ Gmail API error: {e}"
            
#         except Exception as e:
#             logger.error(f"Unexpected error in send_gmail_message: {e}")
#             return f"❌ Unexpected error: {e}"

#     @mcp.tool(
#         name="draft_gmail_message",
#         description="Create a draft email in the user's Gmail account",
#         tags={"gmail", "draft", "email", "compose"},
#         annotations={
#             "title": "Draft Gmail Message",
#             "readOnlyHint": False,
#             "destructiveHint": False,
#             "idempotentHint": False,
#             "openWorldHint": True
#         }
#     )
#     async def draft_gmail_message(
#         user_google_email: str,
#         subject: str,
#         body: str,
#         to: Optional[Union[str, List[str]]] = None,
#         content_type: Literal["plain", "html", "mixed"] = "mixed",
#         html_body: Optional[str] = None,
#         cc: Optional[Union[str, List[str]]] = None,
#         bcc: Optional[Union[str, List[str]]] = None
#     ) -> str:
#         """
#         Creates a draft email in the user's Gmail account with support for HTML formatting and multiple recipients.

#         Args:
#             user_google_email: The user's Google email address
#             subject: Email subject
#             body: Email body content. Usage depends on content_type:
#                 - content_type="plain": Contains plain text only
#                 - content_type="html": Contains HTML content (plain text auto-generated for Gmail)
#                 - content_type="mixed": Contains plain text (HTML goes in html_body parameter)
#             to: Optional recipient email address(es) - can be a single string, list of strings, or None for drafts
#             content_type: Content type - controls how body and html_body are used:
#                 - "plain": Plain text draft (backward compatible)
#                 - "html": HTML draft - put HTML content in 'body' parameter
#                 - "mixed": Dual content - plain text in 'body', HTML in 'html_body' (default)
#             html_body: HTML content when content_type="mixed". Ignored for other content types.
#             cc: Optional CC recipient(s) - can be a single string or list of strings
#             bcc: Optional BCC recipient(s) - can be a single string or list of strings

#         Returns:
#             str: Confirmation message with the created draft's ID
            
#         Examples:
#             # Plain text draft
#             draft_gmail_message(user_email, "Subject", "Plain text body")
            
#             # HTML draft (HTML content goes in 'body' parameter)
#             draft_gmail_message(user_email, "Subject", "<h1>HTML content</h1>", content_type="html")
            
#             # Mixed content draft
#             draft_gmail_message(user_email, "Subject", "Plain version",
#                               content_type="mixed", html_body="<h1>HTML version</h1>")
#         """
#         # Format recipients for logging
#         to_str = "no recipients" if not to else (to if isinstance(to, str) else f"{len(to)} recipients")
#         cc_str = f", CC: {cc if isinstance(cc, str) else f'{len(cc)} recipients'}" if cc else ""
#         bcc_str = f", BCC: {bcc if isinstance(bcc, str) else f'{len(bcc)} recipients'}" if bcc else ""
        
#         logger.info(f"[draft_gmail_message] Email: '{user_google_email}', Subject: '{subject}', To: {to_str}{cc_str}{bcc_str}, content_type: {content_type}")
        
#         try:
#             gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
#             # Create properly formatted MIME message using helper function
#             raw_message = _create_mime_message(
#                 to=to or "",  # Use empty string if no recipient for draft
#                 subject=subject,
#                 body=body,
#                 content_type=content_type,
#                 html_body=html_body,
#                 from_email=user_google_email,
#                 cc=cc,
#                 bcc=bcc
#             )

#             # Create a draft instead of sending
#             draft_body = {"message": {"raw": raw_message}}

#             # Create the draft
#             created_draft = await asyncio.to_thread(
#                 gmail_service.users().drafts().create(userId="me", body=draft_body).execute
#             )
#             draft_id = created_draft.get("id")
            
#             # Count total recipients for confirmation (if any)
#             total_recipients = 0
#             if to:
#                 total_recipients += len(to) if isinstance(to, list) else 1
#             if cc:
#                 total_recipients += len(cc) if isinstance(cc, list) else 1
#             if bcc:
#                 total_recipients += len(bcc) if isinstance(bcc, list) else 1
            
#             recipient_info = f" ({total_recipients} recipient(s))" if total_recipients > 0 else " (no recipients)"
#             return f"✅ Draft created{recipient_info}! Draft ID: {draft_id} (Content type: {content_type})"
            
#         except Exception as e:
#             logger.error(f"Unexpected error in draft_gmail_message: {e}")
#             return f"❌ Unexpected error: {e}"

#     @mcp.tool(
#         name="get_gmail_thread_content",
#         description="Retrieve the complete content of a Gmail conversation thread with all messages",
#         tags={"gmail", "thread", "conversation", "messages"},
#         annotations={
#             "title": "Gmail Thread Content",
#             "readOnlyHint": True,
#             "destructiveHint": False,
#             "idempotentHint": True,
#             "openWorldHint": True
#         }
#     )
#     async def get_gmail_thread_content(
#         user_google_email: str,
#         thread_id: str
#     ) -> str:
#         """
#         Retrieves the complete content of a Gmail conversation thread, including all messages.

#         Args:
#             user_google_email: The user's Google email address
#             thread_id: The unique ID of the Gmail thread to retrieve

#         Returns:
#             str: The complete thread content with all messages formatted for reading
#         """
#         logger.info(f"[get_gmail_thread_content] Thread ID: '{thread_id}', Email: '{user_google_email}'")
        
#         try:
#             gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
#             # Fetch the complete thread with all messages
#             thread_response = await asyncio.to_thread(
#                 gmail_service.users()
#                 .threads()
#                 .get(userId="me", id=thread_id, format="full")
#                 .execute
#             )

#             messages = thread_response.get("messages", [])
#             if not messages:
#                 return f"No messages found in thread '{thread_id}'."

#             # Extract thread subject from the first message
#             first_message = messages[0]
#             first_headers = {
#                 h["name"]: h["value"]
#                 for h in first_message.get("payload", {}).get("headers", [])
#             }
#             thread_subject = first_headers.get("Subject", "(no subject)")

#             # Build the thread content
#             content_lines = [
#                 f"Thread ID: {thread_id}",
#                 f"Subject: {thread_subject}",
#                 f"Messages: {len(messages)}",
#                 "",
#             ]

#             # Process each message in the thread
#             for i, message in enumerate(messages, 1):
#                 # Extract headers
#                 headers = {
#                     h["name"]: h["value"]
#                     for h in message.get("payload", {}).get("headers", [])
#                 }

#                 sender = headers.get("From", "(unknown sender)")
#                 date = headers.get("Date", "(unknown date)")
#                 subject = headers.get("Subject", "(no subject)")

#                 # Extract message body
#                 payload = message.get("payload", {})
#                 body_data = _extract_message_body(payload)

#                 # Add message to content
#                 content_lines.extend(
#                     [
#                         f"=== Message {i} ===",
#                         f"From: {sender}",
#                         f"Date: {date}",
#                     ]
#                 )

#                 # Only show subject if it's different from thread subject
#                 if subject != thread_subject:
#                     content_lines.append(f"Subject: {subject}")

#                 content_lines.extend(
#                     [
#                         "",
#                         body_data or "[No text/plain body found]",
#                         "",
#                     ]
#                 )

#             content_text = "\n".join(content_lines)
#             return content_text
                
#         except Exception as e:
#             logger.error(f"Unexpected error in get_gmail_thread_content: {e}")
#             return f"❌ Unexpected error: {e}"

#     # Label tools - these are now defined in gmail/labels.py and imported
#     # The setup_label_tools function from labels.py will register these tools
#     from .labels import setup_label_tools
#     setup_label_tools(mcp)

#     @mcp.tool(
#         name="manage_gmail_label",
#         description="Manage Gmail labels: create, update, or delete labels",
#         tags={"gmail", "labels", "manage", "create", "update", "delete"},
#         annotations={
#             "title": "Manage Gmail Label",
#             "readOnlyHint": False,
#             "destructiveHint": True,  # Can delete labels
#             "idempotentHint": False,
#             "openWorldHint": True
#         }
#     )
#     async def manage_gmail_label(
#         user_google_email: str,
#         action: Literal["create", "update", "delete"],
#         name: Optional[str] = None,
#         label_id: Optional[str] = None,
#         label_list_visibility: Literal["labelShow", "labelHide"] = "labelShow",
#         message_list_visibility: Literal["show", "hide"] = "show",
#         text_color: Optional[str] = None,
#         background_color: Optional[str] = None
#     ) -> str:
#         """
#         Manages Gmail labels: create, update, or delete labels.

#         Args:
#             user_google_email: The user's Google email address
#             action: Action to perform on the label
#             name: Label name. Required for create, optional for update
#             label_id: Label ID. Required for update and delete operations
#             label_list_visibility: Whether the label is shown in the label list
#             message_list_visibility: Whether the label is shown in the message list
#             text_color: Hex color code for label text (e.g., "#ffffff"). Must be a valid Gmail color.
#             background_color: Hex color code for label background (e.g., "#fb4c2f"). Must be a valid Gmail color.

#         Returns:
#             str: Confirmation message of the label operation
#         """
#         logger.info(f"[manage_gmail_label] Email: '{user_google_email}', Action: '{action}'")
        
#         if action == "create" and not name:
#             return "❌ Label name is required for create action."

#         if action in ["update", "delete"] and not label_id:
#             return "❌ Label ID is required for update and delete actions."
        
#         # Validate colors if provided
#         if text_color and not _validate_gmail_color(text_color, "text"):
#             return f"❌ Invalid text color: {text_color}. Must be a valid Gmail label color."
        
#         if background_color and not _validate_gmail_color(background_color, "background"):
#             return f"❌ Invalid background color: {background_color}. Must be a valid Gmail label color."
        
#         try:
#             gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
#             if action == "create":
#                 label_object = {
#                     "name": name,
#                     "labelListVisibility": label_list_visibility,
#                     "messageListVisibility": message_list_visibility,
#                 }
                
#                 # Add color information if provided
#                 if text_color or background_color:
#                     color_obj = {}
#                     if text_color:
#                         color_obj["textColor"] = text_color
#                     if background_color:
#                         color_obj["backgroundColor"] = background_color
#                     label_object["color"] = color_obj
                
#                 created_label = await asyncio.to_thread(
#                     gmail_service.users().labels().create(userId="me", body=label_object).execute
#                 )
                
#                 # Format response with color information
#                 response_lines = [
#                     "✅ Label created successfully!",
#                     f"Name: {created_label['name']}",
#                     f"ID: {created_label['id']}"
#                 ]
                
#                 if created_label.get("color"):
#                     color_info = _format_label_color_info(created_label["color"])
#                     response_lines.append(f"Colors: {color_info}")
                
#                 return "\n".join(response_lines)

#             elif action == "update":
#                 current_label = await asyncio.to_thread(
#                     gmail_service.users().labels().get(userId="me", id=label_id).execute
#                 )

#                 label_object = {
#                     "id": label_id,
#                     "name": name if name is not None else current_label["name"],
#                     "labelListVisibility": label_list_visibility,
#                     "messageListVisibility": message_list_visibility,
#                 }
                
#                 # Handle color updates
#                 if text_color or background_color:
#                     # Get existing colors or create new color object
#                     existing_color = current_label.get("color", {})
#                     color_obj = {}
                    
#                     # Use provided colors or keep existing ones
#                     if text_color:
#                         color_obj["textColor"] = text_color
#                     elif existing_color.get("textColor"):
#                         color_obj["textColor"] = existing_color["textColor"]
                        
#                     if background_color:
#                         color_obj["backgroundColor"] = background_color
#                     elif existing_color.get("backgroundColor"):
#                         color_obj["backgroundColor"] = existing_color["backgroundColor"]
                    
#                     label_object["color"] = color_obj

#                 updated_label = await asyncio.to_thread(
#                     gmail_service.users().labels().update(userId="me", id=label_id, body=label_object).execute
#                 )
                
#                 # Format response with color information
#                 response_lines = [
#                     "✅ Label updated successfully!",
#                     f"Name: {updated_label['name']}",
#                     f"ID: {updated_label['id']}"
#                 ]
                
#                 if updated_label.get("color"):
#                     color_info = _format_label_color_info(updated_label["color"])
#                     response_lines.append(f"Colors: {color_info}")
                
#                 return "\n".join(response_lines)

#             elif action == "delete":
#                 label = await asyncio.to_thread(
#                     gmail_service.users().labels().get(userId="me", id=label_id).execute
#                 )
#                 label_name = label["name"]

#                 await asyncio.to_thread(
#                     gmail_service.users().labels().delete(userId="me", id=label_id).execute
#                 )
#                 return f"✅ Label '{label_name}' (ID: {label_id}) deleted successfully!"
                
#         except Exception as e:
#             logger.error(f"Unexpected error in manage_gmail_label: {e}")
#             return f"❌ Unexpected error: {e}"

#     @mcp.tool(
#         name="modify_gmail_message_labels",
#         description="Add or remove labels from a Gmail message",
#         tags={"gmail", "labels", "modify", "organize", "messages"},
#         annotations={
#             "title": "Modify Gmail Message Labels",
#             "readOnlyHint": False,
#             "destructiveHint": False,
#             "idempotentHint": False,
#             "openWorldHint": True
#         }
#     )
#     async def modify_gmail_message_labels(
#         user_google_email: str,
#         message_id: str,
#         add_label_ids: Optional[Any] = None,
#         remove_label_ids: Optional[Any] = None
#     ) -> str:
#         """
#         Adds or removes labels from a Gmail message.

#         Args:
#             user_google_email: The user's Google email address
#             message_id: The ID of the message to modify
#             add_label_ids: List of label IDs to add to the message (can be list or JSON string)
#             remove_label_ids: List of label IDs to remove from the message (can be list or JSON string)

#         Returns:
#             str: Confirmation message of the label changes applied to the message
#         """
#         import json
        
#         logger.info(f"[modify_gmail_message_labels] Email: '{user_google_email}', Message ID: '{message_id}'")
#         logger.info(f"[modify_gmail_message_labels] Raw add_label_ids: {add_label_ids} (type: {type(add_label_ids)})")
#         logger.info(f"[modify_gmail_message_labels] Raw remove_label_ids: {remove_label_ids} (type: {type(remove_label_ids)})")
        
#         # Helper function to parse label IDs (handles both list and JSON string formats)
#         def parse_label_ids(label_ids: Any) -> Optional[List[str]]:
#             if not label_ids:
#                 return None
            
#             # If it's already a list, return it
#             if isinstance(label_ids, list):
#                 return label_ids
            
#             # If it's a string, try to parse as JSON
#             if isinstance(label_ids, str):
#                 try:
#                     parsed = json.loads(label_ids)
#                     if isinstance(parsed, list):
#                         return parsed
#                     else:
#                         # Single string wrapped in quotes - convert to list
#                         return [parsed] if isinstance(parsed, str) else None
#                 except json.JSONDecodeError:
#                     # Not valid JSON, treat as single label ID
#                     return [label_ids]
            
#             return None
        
#         # Parse the label ID parameters
#         parsed_add_label_ids = parse_label_ids(add_label_ids)
#         parsed_remove_label_ids = parse_label_ids(remove_label_ids)
        
#         logger.info(f"[modify_gmail_message_labels] Parsed add_label_ids: {parsed_add_label_ids}")
#         logger.info(f"[modify_gmail_message_labels] Parsed remove_label_ids: {parsed_remove_label_ids}")
        
#         if not parsed_add_label_ids and not parsed_remove_label_ids:
#             return "❌ At least one of add_label_ids or remove_label_ids must be provided."
        
#         try:
#             gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
#             body = {}
#             if parsed_add_label_ids:
#                 body["addLabelIds"] = parsed_add_label_ids
#             if parsed_remove_label_ids:
#                 body["removeLabelIds"] = parsed_remove_label_ids

#             await asyncio.to_thread(
#                 gmail_service.users().messages().modify(userId="me", id=message_id, body=body).execute
#             )

#             actions = []
#             if parsed_add_label_ids:
#                 actions.append(f"Added labels: {', '.join(parsed_add_label_ids)}")
#             if parsed_remove_label_ids:
#                 actions.append(f"Removed labels: {', '.join(parsed_remove_label_ids)}")

#             return f"✅ Message labels updated successfully!\nMessage ID: {message_id}\n{'; '.join(actions)}"
                
#         except Exception as e:
#             logger.error(f"Unexpected error in modify_gmail_message_labels: {e}")
#             return f"❌ Unexpected error: {e}"

#     @mcp.tool(
#         name="reply_to_gmail_message",
#         description="Send a reply to a specific Gmail message with proper threading",
#         tags={"gmail", "reply", "send", "thread", "email"},
#         annotations={
#             "title": "Reply to Gmail Message",
#             "readOnlyHint": False,
#             "destructiveHint": False,
#             "idempotentHint": False,
#             "openWorldHint": True
#         }
#     )
#     async def reply_to_gmail_message(
#         user_google_email: str,
#         message_id: str,
#         body: str,
#         content_type: Literal["plain", "html", "mixed"] = "mixed",
#         html_body: Optional[str] = None
#     ) -> str:
#         """
#         Sends a reply to a specific Gmail message with support for HTML formatting.

#         Args:
#             user_google_email: The user's Google email address
#             message_id: The ID of the message to reply to
#             body: Reply body content. Usage depends on content_type:
#                 - content_type="plain": Contains plain text only
#                 - content_type="html": Contains HTML content (plain text auto-generated for Gmail)
#                 - content_type="mixed": Contains plain text (HTML goes in html_body parameter)
#             content_type: Content type - controls how body and html_body are used:
#                 - "plain": Plain text reply (backward compatible)
#                 - "html": HTML reply - put HTML content in 'body' parameter
#                 - "mixed": Dual content - plain text in 'body', HTML in 'html_body' (default)
#             html_body: HTML content when content_type="mixed". Ignored for other content types.

#         Returns:
#             str: Confirmation message with the sent reply's message ID
            
#         Examples:
#             # Plain text reply
#             reply_to_gmail_message(user_email, "msg_123", "Thanks for your message!")
            
#             # HTML reply (HTML content goes in 'body' parameter)
#             reply_to_gmail_message(user_email, "msg_123", "<p>Thanks for your <b>message</b>!</p>", content_type="html")
            
#             # Mixed content reply
#             reply_to_gmail_message(user_email, "msg_123", "Thanks for your message!",
#                                  content_type="mixed", html_body="<p>Thanks for your <b>message</b>!</p>")
#         """
#         logger.info(f"[reply_to_gmail_message] Email: '{user_google_email}', Replying to Message ID: '{message_id}', content_type: {content_type}")
        
#         try:
#             gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
#             # Fetch the original message to get headers and body for quoting
#             original_message = await asyncio.to_thread(
#                 gmail_service.users().messages().get(userId="me", id=message_id, format="full").execute
#             )
#             payload = original_message.get("payload", {})
#             headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
#             original_subject = headers.get("Subject", "(no subject)")
#             original_from = headers.get("From", "(unknown sender)")
#             original_body = _extract_message_body(payload)

#             reply_subject = _prepare_reply_subject(original_subject)
#             quoted_body = _quote_original_message(original_body)

#             # Compose the reply message body based on content type
#             if content_type == "html":
#                 # For HTML content, create HTML version with quoting
#                 full_body = f"{body}<br><br>On {html.escape(original_from)} wrote:<br><blockquote style='margin-left: 20px; padding-left: 10px; border-left: 2px solid #ccc;'>{html.escape(original_body).replace(chr(10), '<br>')}</blockquote>"
#             elif content_type == "mixed":
#                 # Use provided HTML and plain text bodies
#                 if not html_body:
#                     raise ValueError("html_body is required when content_type is 'mixed'")
#                 plain_full_body = f"{body}\n\nOn {original_from} wrote:\n{quoted_body}"
#                 html_full_body = f"{html_body}<br><br>On {html.escape(original_from)} wrote:<br><blockquote style='margin-left: 20px; padding-left: 10px; border-left: 2px solid #ccc;'>{html.escape(original_body).replace(chr(10), '<br>')}</blockquote>"
#                 full_body = plain_full_body  # For the main body parameter
#             else:  # plain
#                 full_body = f"{body}\n\nOn {original_from} wrote:\n{quoted_body}"

#             # Create properly formatted MIME message using helper function
#             raw_message = _create_mime_message(
#                 to=original_from,
#                 subject=reply_subject,
#                 body=full_body,
#                 content_type=content_type,
#                 html_body=html_full_body if content_type == "mixed" else None,
#                 from_email=user_google_email,
#                 reply_to_message_id=headers.get("Message-ID", ""),
#                 thread_id=original_message.get("threadId")
#             )

#             send_body = {"raw": raw_message, "threadId": original_message.get("threadId")}

#             # Send the reply message
#             sent_message = await asyncio.to_thread(
#                 gmail_service.users().messages().send(userId="me", body=send_body).execute
#             )
#             sent_message_id = sent_message.get("id")
#             return f"✅ Reply sent! Message ID: {sent_message_id} (Content type: {content_type})"
                
#         except Exception as e:
#             logger.error(f"Unexpected error in reply_to_gmail_message: {e}")
#             return f"❌ Unexpected error: {e}"

#     @mcp.tool(
#         name="draft_gmail_reply",
#         description="Create a draft reply to a specific Gmail message with proper threading",
#         tags={"gmail", "draft", "reply", "thread", "email"},
#         annotations={
#             "title": "Draft Gmail Reply",
#             "readOnlyHint": False,
#             "destructiveHint": False,
#             "idempotentHint": False,
#             "openWorldHint": True
#         }
#     )
#     async def draft_gmail_reply(
#         user_google_email: str,
#         message_id: str,
#         body: str,
#         content_type: Literal["plain", "html", "mixed"] = "mixed",
#         html_body: Optional[str] = None
#     ) -> str:
#         """
#         Creates a draft reply to a specific Gmail message with support for HTML formatting.

#         Args:
#             user_google_email: The user's Google email address
#             message_id: The ID of the message to draft a reply for
#             body: Reply body content. Usage depends on content_type:
#                 - content_type="plain": Contains plain text only
#                 - content_type="html": Contains HTML content (plain text auto-generated for Gmail)
#                 - content_type="mixed": Contains plain text (HTML goes in html_body parameter)
#             content_type: Content type - controls how body and html_body are used:
#                 - "plain": Plain text draft reply (backward compatible)
#                 - "html": HTML draft reply - put HTML content in 'body' parameter
#                 - "mixed": Dual content - plain text in 'body', HTML in 'html_body' (default)
#             html_body: HTML content when content_type="mixed". Ignored for other content types.

#         Returns:
#             str: Confirmation message with the created draft's ID
            
#         Examples:
#             # Plain text draft reply
#             draft_gmail_reply(user_email, "msg_123", "Thanks for your message!")
            
#             # HTML draft reply (HTML content goes in 'body' parameter)
#             draft_gmail_reply(user_email, "msg_123", "<p>Thanks for your <b>message</b>!</p>", content_type="html")
            
#             # Mixed content draft reply
#             draft_gmail_reply(user_email, "msg_123", "Thanks for your message!",
#                             content_type="mixed", html_body="<p>Thanks for your <b>message</b>!</p>")
#         """
#         logger.info(f"[draft_gmail_reply] Email: '{user_google_email}', Drafting reply to Message ID: '{message_id}', content_type: {content_type}")
        
#         try:
#             gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
#             # Fetch the original message to get headers and body for quoting
#             original_message = await asyncio.to_thread(
#                 gmail_service.users().messages().get(userId="me", id=message_id, format="full").execute
#             )
#             payload = original_message.get("payload", {})
#             headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
#             original_subject = headers.get("Subject", "(no subject)")
#             original_from = headers.get("From", "(unknown sender)")
#             original_body = _extract_message_body(payload)

#             reply_subject = _prepare_reply_subject(original_subject)
#             quoted_body = _quote_original_message(original_body)

#             # Compose the reply message body based on content type
#             if content_type == "html":
#                 # For HTML content, create HTML version with quoting
#                 full_body = f"{body}<br><br>On {html.escape(original_from)} wrote:<br><blockquote style='margin-left: 20px; padding-left: 10px; border-left: 2px solid #ccc;'>{html.escape(original_body).replace(chr(10), '<br>')}</blockquote>"
#             elif content_type == "mixed":
#                 # Use provided HTML and plain text bodies
#                 if not html_body:
#                     raise ValueError("html_body is required when content_type is 'mixed'")
#                 plain_full_body = f"{body}\n\nOn {original_from} wrote:\n{quoted_body}"
#                 html_full_body = f"{html_body}<br><br>On {html.escape(original_from)} wrote:<br><blockquote style='margin-left: 20px; padding-left: 10px; border-left: 2px solid #ccc;'>{html.escape(original_body).replace(chr(10), '<br>')}</blockquote>"
#                 full_body = plain_full_body  # For the main body parameter
#             else:  # plain
#                 full_body = f"{body}\n\nOn {original_from} wrote:\n{quoted_body}"

#             # Create properly formatted MIME message using helper function
#             raw_message = _create_mime_message(
#                 to=original_from,
#                 subject=reply_subject,
#                 body=full_body,
#                 content_type=content_type,
#                 html_body=html_full_body if content_type == "mixed" else None,
#                 from_email=user_google_email,
#                 reply_to_message_id=headers.get("Message-ID", ""),
#                 thread_id=original_message.get("threadId")
#             )

#             draft_body = {"message": {"raw": raw_message, "threadId": original_message.get("threadId")}}

#             # Create the draft reply
#             created_draft = await asyncio.to_thread(
#                 gmail_service.users().drafts().create(userId="me", body=draft_body).execute
#             )
#             draft_id = created_draft.get("id")
#             return f"✅ Draft reply created! Draft ID: {draft_id} (Content type: {content_type})"
                
#         except Exception as e:
#             logger.error(f"Unexpected error in draft_gmail_reply: {e}")
#             return f"❌ Unexpected error: {e}"

#     @mcp.tool(
#         name="list_gmail_filters",
#         description="List all Gmail filters/rules in the user's account",
#         tags={"gmail", "filters", "rules", "list", "automation"},
#         annotations={
#             "title": "List Gmail Filters",
#             "readOnlyHint": True,
#             "destructiveHint": False,
#             "idempotentHint": True,
#             "openWorldHint": True
#         }
#     )
#     async def list_gmail_filters(
#         user_google_email: str
#     ) -> str:
#         """
#         Lists all Gmail filters/rules in the user's account.

#         Args:
#             user_google_email: The user's Google email address

#         Returns:
#             str: A formatted list of all filters with their criteria and actions
#         """
#         logger.info(f"[list_gmail_filters] Email: '{user_google_email}'")
        
#         try:
#             gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
#             response = await asyncio.to_thread(
#                 gmail_service.users().settings().filters().list(userId="me").execute
#             )
#             filters = response.get("filter", [])

#             if not filters:
#                 return "No Gmail filters found."

#             lines = [f"Found {len(filters)} Gmail filters:", ""]

#             for i, filter_obj in enumerate(filters, 1):
#                 filter_id = filter_obj.get("id", "unknown")
#                 criteria = filter_obj.get("criteria", {})
#                 action = filter_obj.get("action", {})

#                 lines.append(f"📋 FILTER {i} (ID: {filter_id})")
                
#                 # Display criteria
#                 criteria_parts = []
#                 if criteria.get("from"):
#                     criteria_parts.append(f"From: {criteria['from']}")
#                 if criteria.get("to"):
#                     criteria_parts.append(f"To: {criteria['to']}")
#                 if criteria.get("subject"):
#                     criteria_parts.append(f"Subject: {criteria['subject']}")
#                 if criteria.get("query"):
#                     criteria_parts.append(f"Query: {criteria['query']}")
#                 if criteria.get("hasAttachment"):
#                     criteria_parts.append("Has attachment: Yes")
#                 if criteria.get("excludeChats"):
#                     criteria_parts.append("Exclude chats: Yes")
#                 if criteria.get("size"):
#                     criteria_parts.append(f"Size: {criteria['size']}")
#                 if criteria.get("sizeComparison"):
#                     criteria_parts.append(f"Size comparison: {criteria['sizeComparison']}")

#                 lines.append(f"  Criteria: {' | '.join(criteria_parts) if criteria_parts else 'None'}")

#                 # Display actions
#                 action_parts = []
#                 if action.get("addLabelIds"):
#                     action_parts.append(f"Add labels: {', '.join(action['addLabelIds'])}")
#                 if action.get("removeLabelIds"):
#                     action_parts.append(f"Remove labels: {', '.join(action['removeLabelIds'])}")
#                 if action.get("forward"):
#                     action_parts.append(f"Forward to: {action['forward']}")
#                 if action.get("markAsSpam"):
#                     action_parts.append("Mark as spam")
#                 if action.get("markAsImportant"):
#                     action_parts.append("Mark as important")
#                 if action.get("neverMarkAsSpam"):
#                     action_parts.append("Never mark as spam")
#                 if action.get("neverMarkAsImportant"):
#                     action_parts.append("Never mark as important")

#                 lines.append(f"  Actions: {' | '.join(action_parts) if action_parts else 'None'}")
#                 lines.append("")

#             return "\n".join(lines)
                
#         except Exception as e:
#             logger.error(f"Unexpected error in list_gmail_filters: {e}")
#             return f"❌ Unexpected error: {e}"

#     @mcp.tool(
#         name="create_gmail_filter",
#         description="Create a new Gmail filter/rule with criteria and actions, with optional retroactive application to existing emails",
#         tags={"gmail", "filters", "rules", "create", "automation"},
#         annotations={
#             "title": "Create Gmail Filter",
#             "readOnlyHint": False,
#             "destructiveHint": False,
#             "idempotentHint": False,
#             "openWorldHint": True
#         }
#     )
#     async def create_gmail_filter(
#         user_google_email: str,
#         # Criteria parameters
#         from_address: Optional[str] = None,
#         to_address: Optional[str] = None,
#         subject_contains: Optional[str] = None,
#         query: Optional[str] = None,
#         has_attachment: Optional[bool] = None,
#         exclude_chats: Optional[bool] = None,
#         size: Optional[int] = None,
#         size_comparison: Optional[Literal["larger", "smaller"]] = None,
#         # Action parameters
#         add_label_ids: Optional[Any] = None,
#         remove_label_ids: Optional[Any] = None,
#         forward_to: Optional[str] = None,
#         mark_as_spam: Optional[bool] = None,
#         mark_as_important: Optional[bool] = None,
#         never_mark_as_spam: Optional[bool] = None,
#         never_mark_as_important: Optional[bool] = None
#     ) -> str:
#         """
#         Creates a new Gmail filter/rule with specified criteria and actions.

#         Args:
#             user_google_email: The user's Google email address
#             from_address: Filter messages from this email address
#             to_address: Filter messages to this email address
#             subject_contains: Filter messages with this text in subject
#             query: Gmail search query for advanced filtering
#             has_attachment: Filter messages that have/don't have attachments
#             exclude_chats: Whether to exclude chat messages
#             size: Size threshold in bytes
#             size_comparison: Whether size should be "larger" or "smaller" than threshold
#             add_label_ids: List of label IDs to add to matching messages (can be list or JSON string)
#             remove_label_ids: List of label IDs to remove from matching messages (can be list or JSON string)
#             forward_to: Email address to forward matching messages to
#             mark_as_spam: Whether to mark matching messages as spam
#             mark_as_important: Whether to mark matching messages as important
#             never_mark_as_spam: Whether to never mark matching messages as spam
#             never_mark_as_important: Whether to never mark matching messages as important

#         Returns:
#             str: Confirmation message with the created filter's ID
#         """
#         import json
        
#         logger.info(f"[create_gmail_filter] Email: '{user_google_email}'")
#         logger.info(f"[create_gmail_filter] Raw add_label_ids: {add_label_ids} (type: {type(add_label_ids)})")
#         logger.info(f"[create_gmail_filter] Raw remove_label_ids: {remove_label_ids} (type: {type(remove_label_ids)})")
        
#         # Helper function to parse label IDs (reuse from modify_gmail_message_labels)
#         def parse_label_ids(label_ids: Any) -> Optional[List[str]]:
#             if not label_ids:
#                 return None
            
#             # If it's already a list, return it
#             if isinstance(label_ids, list):
#                 return label_ids
            
#             # If it's a string, try to parse as JSON
#             if isinstance(label_ids, str):
#                 try:
#                     parsed = json.loads(label_ids)
#                     if isinstance(parsed, list):
#                         return parsed
#                     else:
#                         # Single string wrapped in quotes - convert to list
#                         return [parsed] if isinstance(parsed, str) else None
#                 except json.JSONDecodeError:
#                     # Not valid JSON, treat as single label ID
#                     return [label_ids]
            
#             return None

#         # Build criteria object
#         criteria = {}
#         if from_address:
#             criteria["from"] = from_address
#         if to_address:
#             criteria["to"] = to_address
#         if subject_contains:
#             criteria["subject"] = subject_contains
#         if query:
#             criteria["query"] = query
#         if has_attachment is not None:
#             criteria["hasAttachment"] = has_attachment
#         if exclude_chats is not None:
#             criteria["excludeChats"] = exclude_chats
#         if size is not None:
#             criteria["size"] = size
#         if size_comparison:
#             criteria["sizeComparison"] = size_comparison

#         # Build action object
#         action = {}
#         parsed_add_label_ids = parse_label_ids(add_label_ids)
#         parsed_remove_label_ids = parse_label_ids(remove_label_ids)
        
#         logger.info(f"[create_gmail_filter] Parsed add_label_ids: {parsed_add_label_ids}")
#         logger.info(f"[create_gmail_filter] Parsed remove_label_ids: {parsed_remove_label_ids}")
        
#         if parsed_add_label_ids:
#             action["addLabelIds"] = parsed_add_label_ids
#         if parsed_remove_label_ids:
#             action["removeLabelIds"] = parsed_remove_label_ids
#         if forward_to:
#             action["forward"] = forward_to
#         if mark_as_spam is not None:
#             action["markAsSpam"] = mark_as_spam
#         if mark_as_important is not None:
#             action["markAsImportant"] = mark_as_important
#         if never_mark_as_spam is not None:
#             action["neverMarkAsSpam"] = never_mark_as_spam
#         if never_mark_as_important is not None:
#             action["neverMarkAsImportant"] = never_mark_as_important

#         # Validate that we have at least one criteria and one action
#         if not criteria:
#             return "❌ At least one filter criteria must be specified."
#         if not action:
#             return "❌ At least one filter action must be specified."
        
#         try:
#             gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
#             filter_body = {
#                 "criteria": criteria,
#                 "action": action
#             }

#             created_filter = await asyncio.to_thread(
#                 gmail_service.users().settings().filters().create(userId="me", body=filter_body).execute
#             )
            
#             filter_id = created_filter.get("id")
            
#             # Format response with details
#             criteria_summary = []
#             if from_address:
#                 criteria_summary.append(f"From: {from_address}")
#             if to_address:
#                 criteria_summary.append(f"To: {to_address}")
#             if subject_contains:
#                 criteria_summary.append(f"Subject contains: {subject_contains}")
#             if query:
#                 criteria_summary.append(f"Query: {query}")
                
#             action_summary = []
#             if parsed_add_label_ids:
#                 action_summary.append(f"Add labels: {', '.join(parsed_add_label_ids)}")
#             if parsed_remove_label_ids:
#                 action_summary.append(f"Remove labels: {', '.join(parsed_remove_label_ids)}")
#             if forward_to:
#                 action_summary.append(f"Forward to: {forward_to}")
#             if mark_as_spam:
#                 action_summary.append("Mark as spam")
#             if mark_as_important:
#                 action_summary.append("Mark as important")

#             response_lines = [
#                 "✅ Gmail filter created successfully!",
#                 f"Filter ID: {filter_id}",
#                 f"Criteria: {' | '.join(criteria_summary)}",
#                 f"Actions: {' | '.join(action_summary)}"
#             ]

#             # Apply filter to existing emails retroactively (always enabled for label actions)
#             if parsed_add_label_ids or parsed_remove_label_ids:
#                 logger.info(f"[create_gmail_filter] Applying filter retroactively to existing emails")
                
#                 try:
#                     # Build Gmail search query from filter criteria
#                     search_terms = []
#                     if from_address:
#                         search_terms.append(f"from:{from_address}")
#                     if to_address:
#                         search_terms.append(f"to:{to_address}")
#                     if subject_contains:
#                         search_terms.append(f"subject:({subject_contains})")
#                     if query:
#                         search_terms.append(query)
#                     if has_attachment is True:
#                         search_terms.append("has:attachment")
#                     elif has_attachment is False:
#                         search_terms.append("-has:attachment")
#                     if size is not None and size_comparison:
#                         if size_comparison == "larger":
#                             search_terms.append(f"larger:{size}")
#                         else:  # smaller
#                             search_terms.append(f"smaller:{size}")
                    
#                     if not search_terms:
#                         response_lines.append("\n⚠️ Cannot apply to existing emails: no searchable criteria specified")
#                         return "\n".join(response_lines)
                    
#                     search_query = " ".join(search_terms)
#                     logger.info(f"[create_gmail_filter] Searching for existing emails with query: {search_query}")
                    
#                     # Search for existing messages that match the filter criteria
#                     search_response = await asyncio.to_thread(
#                         gmail_service.users()
#                         .messages()
#                         .list(userId="me", q=search_query, maxResults=500)  # Limit to 500 for safety
#                         .execute
#                     )
#                     existing_messages = search_response.get("messages", [])
                    
#                     if existing_messages:
#                         logger.info(f"[create_gmail_filter] Found {len(existing_messages)} existing messages to process")
                        
#                         # Apply label actions to existing messages
#                         processed_count = 0
#                         error_count = 0
                        
#                         for message in existing_messages:
#                             try:
#                                 message_id = message["id"]
                                
#                                 # Only apply label actions (not forwarding, spam, etc. for safety)
#                                 if parsed_add_label_ids or parsed_remove_label_ids:
#                                     modify_body = {}
#                                     if parsed_add_label_ids:
#                                         modify_body["addLabelIds"] = parsed_add_label_ids
#                                     if parsed_remove_label_ids:
#                                         modify_body["removeLabelIds"] = parsed_remove_label_ids
                                    
#                                     await asyncio.to_thread(
#                                         gmail_service.users().messages().modify(
#                                             userId="me", id=message_id, body=modify_body
#                                         ).execute
#                                     )
#                                     processed_count += 1
                                    
#                             except Exception as msg_error:
#                                 logger.warning(f"[create_gmail_filter] Failed to process message {message.get('id', 'unknown')}: {msg_error}")
#                                 error_count += 1
                        
#                         if processed_count > 0:
#                             response_lines.append(f"\n🔄 Retroactive application: {processed_count} existing messages updated")
#                         if error_count > 0:
#                             response_lines.append(f"⚠️ {error_count} messages had errors during retroactive application")
#                     else:
#                         response_lines.append("\n🔍 No existing messages found matching the filter criteria")
                        
#                 except Exception as retro_error:
#                     logger.error(f"[create_gmail_filter] Error during retroactive application: {retro_error}")
#                     response_lines.append(f"\n⚠️ Filter created but retroactive application failed: {retro_error}")

#             return "\n".join(response_lines)
                
#         except Exception as e:
#             logger.error(f"Unexpected error in create_gmail_filter: {e}")
#             return f"❌ Unexpected error: {e}"

#     @mcp.tool(
#         name="get_gmail_filter",
#         description="Get details of a specific Gmail filter by ID",
#         tags={"gmail", "filters", "rules", "get", "details"},
#         annotations={
#             "title": "Get Gmail Filter",
#             "readOnlyHint": True,
#             "destructiveHint": False,
#             "idempotentHint": True,
#             "openWorldHint": True
#         }
#     )
#     async def get_gmail_filter(
#         user_google_email: str,
#         filter_id: str
#     ) -> str:
#         """
#         Gets details of a specific Gmail filter by ID.

#         Args:
#             user_google_email: The user's Google email address
#             filter_id: The ID of the filter to retrieve

#         Returns:
#             str: Detailed information about the filter including criteria and actions
#         """
#         logger.info(f"[get_gmail_filter] Email: '{user_google_email}', Filter ID: '{filter_id}'")
        
#         try:
#             gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
#             filter_obj = await asyncio.to_thread(
#                 gmail_service.users().settings().filters().get(userId="me", id=filter_id).execute
#             )

#             criteria = filter_obj.get("criteria", {})
#             action = filter_obj.get("action", {})

#             lines = [
#                 f"Gmail Filter Details (ID: {filter_id})",
#                 "",
#                 "📋 CRITERIA:"
#             ]

#             # Display criteria
#             if criteria.get("from"):
#                 lines.append(f"  From: {criteria['from']}")
#             if criteria.get("to"):
#                 lines.append(f"  To: {criteria['to']}")
#             if criteria.get("subject"):
#                 lines.append(f"  Subject contains: {criteria['subject']}")
#             if criteria.get("query"):
#                 lines.append(f"  Query: {criteria['query']}")
#             if criteria.get("hasAttachment"):
#                 lines.append(f"  Has attachment: {criteria['hasAttachment']}")
#             if criteria.get("excludeChats"):
#                 lines.append(f"  Exclude chats: {criteria['excludeChats']}")
#             if criteria.get("size"):
#                 lines.append(f"  Size: {criteria['size']} bytes")
#             if criteria.get("sizeComparison"):
#                 lines.append(f"  Size comparison: {criteria['sizeComparison']}")

#             if not any(criteria.values()):
#                 lines.append("  None specified")

#             lines.extend([
#                 "",
#                 "⚡ ACTIONS:"
#             ])

#             # Display actions
#             if action.get("addLabelIds"):
#                 lines.append(f"  Add labels: {', '.join(action['addLabelIds'])}")
#             if action.get("removeLabelIds"):
#                 lines.append(f"  Remove labels: {', '.join(action['removeLabelIds'])}")
#             if action.get("forward"):
#                 lines.append(f"  Forward to: {action['forward']}")
#             if action.get("markAsSpam"):
#                 lines.append(f"  Mark as spam: {action['markAsSpam']}")
#             if action.get("markAsImportant"):
#                 lines.append(f"  Mark as important: {action['markAsImportant']}")
#             if action.get("neverMarkAsSpam"):
#                 lines.append(f"  Never mark as spam: {action['neverMarkAsSpam']}")
#             if action.get("neverMarkAsImportant"):
#                 lines.append(f"  Never mark as important: {action['neverMarkAsImportant']}")

#             if not any(action.values()):
#                 lines.append("  None specified")

#             return "\n".join(lines)
                
#         except Exception as e:
#             logger.error(f"Unexpected error in get_gmail_filter: {e}")
#             return f"❌ Unexpected error: {e}"

#     @mcp.tool(
#         name="delete_gmail_filter",
#         description="Delete a Gmail filter by ID",
#         tags={"gmail", "filters", "rules", "delete", "remove"},
#         annotations={
#             "title": "Delete Gmail Filter",
#             "readOnlyHint": False,
#             "destructiveHint": True,  # Deletes filters
#             "idempotentHint": False,
#             "openWorldHint": True
#         }
#     )
#     async def delete_gmail_filter(
#         user_google_email: str,
#         filter_id: str
#     ) -> str:
#         """
#         Deletes a Gmail filter by ID.

#         Args:
#             user_google_email: The user's Google email address
#             filter_id: The ID of the filter to delete

#         Returns:
#             str: Confirmation message of the filter deletion
#         """
#         logger.info(f"[delete_gmail_filter] Email: '{user_google_email}', Filter ID: '{filter_id}'")
        
#         try:
#             gmail_service = await _get_gmail_service_with_fallback(user_google_email)
            
#             # Get filter details before deletion for confirmation
#             try:
#                 filter_obj = await asyncio.to_thread(
#                     gmail_service.users().settings().filters().get(userId="me", id=filter_id).execute
#                 )
#                 criteria = filter_obj.get("criteria", {})
#                 criteria_summary = []
#                 if criteria.get("from"):
#                     criteria_summary.append(f"From: {criteria['from']}")
#                 if criteria.get("to"):
#                     criteria_summary.append(f"To: {criteria['to']}")
#                 if criteria.get("subject"):
#                     criteria_summary.append(f"Subject: {criteria['subject']}")
#                 if criteria.get("query"):
#                     criteria_summary.append(f"Query: {criteria['query']}")
                    
#                 criteria_text = " | ".join(criteria_summary) if criteria_summary else "No criteria found"
                
#             except Exception:
#                 criteria_text = "Could not retrieve criteria"

#             # Delete the filter
#             await asyncio.to_thread(
#                 gmail_service.users().settings().filters().delete(userId="me", id=filter_id).execute
#             )

#             return f"✅ Gmail filter deleted successfully!\nFilter ID: {filter_id}\nCriteria was: {criteria_text}"
                
#         except Exception as e:
#             logger.error(f"Unexpected error in delete_gmail_filter: {e}")
    
#     @mcp.tool(
#         name="add_to_gmail_allow_list",
#         description="Add an email address to the Gmail allow list (recipients on this list skip elicitation confirmation)",
#         tags={"gmail", "allow-list", "security", "management", "trusted"},
#         annotations={
#             "title": "Add to Gmail Allow List",
#             "readOnlyHint": False,
#             "destructiveHint": False,
#             "idempotentHint": True,  # Adding same email multiple times has same effect
#             "openWorldHint": False  # Local configuration only
#         }
#     )
#     async def add_to_gmail_allow_list(
#         user_google_email: str,
#         email: str
#     ) -> str:
#         """
#         Adds an email address to the Gmail allow list.
#         Recipients on this list will skip elicitation confirmation when sending emails.
        
#         Args:
#             user_google_email: The authenticated user's Google email address (for authorization)
#             email: The email address to add to the allow list
            
#         Returns:
#             str: Confirmation message of the operation
#         """
#         import re
#         from config.settings import settings
        
#         logger.info(f"[add_to_gmail_allow_list] User: '{user_google_email}' adding email: '{email}'")
        
#         # Validate email format
#         email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
#         if not re.match(email_pattern, email):
#             return f"❌ Invalid email format: {email}"
        
#         # Normalize email to lowercase
#         email_to_add = email.strip().lower()
        
#         try:
#             # Get current allow list
#             current_list = settings.get_gmail_allow_list()
            
#             # Check if email is already in the list
#             if email_to_add in current_list:
#                 masked_email = f"{email_to_add[:3]}...@{email_to_add.split('@')[1]}" if '@' in email_to_add else email_to_add
#                 return f"ℹ️ Email {masked_email} is already in the allow list"
            
#             # Add the new email
#             updated_list = current_list + [email_to_add]
            
#             # Update the environment variable (in memory)
#             new_value = ",".join(updated_list)
#             settings.gmail_allow_list = new_value
#             import os
#             os.environ["GMAIL_ALLOW_LIST"] = new_value
            
#             # Mask the email for privacy in response
#             masked_email = f"{email_to_add[:3]}...@{email_to_add.split('@')[1]}" if '@' in email_to_add else email_to_add
            
#             # Create response with instructions for persistence
#             return f"""✅ Successfully added {masked_email} to Gmail allow list!

# **Current Status:**
# • Allow list now contains {len(updated_list)} email(s)
# • This email will skip elicitation confirmation when sending emails

# **⚠️ IMPORTANT - Make this change permanent:**
# To persist this change across server restarts, add the following to your .env file:
# ```
# GMAIL_ALLOW_LIST={new_value}
# ```

# **Note:** The change is active for the current session but will be lost on restart unless added to .env file."""
            
#         except Exception as e:
#             logger.error(f"Unexpected error in add_to_gmail_allow_list: {e}")
#             return f"❌ Unexpected error: {e}"
    
#     @mcp.tool(
#         name="remove_from_gmail_allow_list",
#         description="Remove an email address from the Gmail allow list",
#         tags={"gmail", "allow-list", "security", "management", "untrust"},
#         annotations={
#             "title": "Remove from Gmail Allow List",
#             "readOnlyHint": False,
#             "destructiveHint": False,  # Not truly destructive, just removes trust
#             "idempotentHint": True,  # Removing non-existent email has same effect
#             "openWorldHint": False  # Local configuration only
#         }
#     )
#     async def remove_from_gmail_allow_list(
#         user_google_email: str,
#         email: str
#     ) -> str:
#         """
#         Removes an email address from the Gmail allow list.
#         After removal, this recipient will require elicitation confirmation when sending emails.
        
#         Args:
#             user_google_email: The authenticated user's Google email address (for authorization)
#             email: The email address to remove from the allow list
            
#         Returns:
#             str: Confirmation message of the operation
#         """
#         from config.settings import settings
        
#         logger.info(f"[remove_from_gmail_allow_list] User: '{user_google_email}' removing email: '{email}'")
        
#         # Normalize email to lowercase
#         email_to_remove = email.strip().lower()
        
#         try:
#             # Get current allow list
#             current_list = settings.get_gmail_allow_list()
            
#             # Check if email is in the list
#             if email_to_remove not in current_list:
#                 masked_email = f"{email_to_remove[:3]}...@{email_to_remove.split('@')[1]}" if '@' in email_to_remove else email_to_remove
#                 return f"ℹ️ Email {masked_email} is not in the allow list"
            
#             # Remove the email
#             updated_list = [e for e in current_list if e != email_to_remove]
            
#             # Update the environment variable (in memory)
#             new_value = ",".join(updated_list) if updated_list else ""
#             settings.gmail_allow_list = new_value
#             import os
#             os.environ["GMAIL_ALLOW_LIST"] = new_value
            
#             # Mask the email for privacy in response
#             masked_email = f"{email_to_remove[:3]}...@{email_to_remove.split('@')[1]}" if '@' in email_to_remove else email_to_remove
            
#             # Create response with instructions for persistence
#             if updated_list:
#                 env_instruction = f"GMAIL_ALLOW_LIST={new_value}"
#             else:
#                 env_instruction = "# GMAIL_ALLOW_LIST= (comment out or remove the line)"
            
#             return f"""✅ Successfully removed {masked_email} from Gmail allow list!

# **Current Status:**
# • Allow list now contains {len(updated_list)} email(s)
# • This email will now require elicitation confirmation when sending emails

# **⚠️ IMPORTANT - Make this change permanent:**
# To persist this change across server restarts, update your .env file:
# ```
# {env_instruction}
# ```

# **Note:** The change is active for the current session but will be lost on restart unless updated in .env file."""
            
#         except Exception as e:
#             logger.error(f"Unexpected error in remove_from_gmail_allow_list: {e}")
#             return f"❌ Unexpected error: {e}"
    
#     @mcp.tool(
#         name="view_gmail_allow_list",
#         description="View the current Gmail allow list configuration",
#         tags={"gmail", "allow-list", "security", "view", "list"},
#         annotations={
#             "title": "View Gmail Allow List",
#             "readOnlyHint": True,
#             "destructiveHint": False,
#             "idempotentHint": True,
#             "openWorldHint": False
#         }
#     )
#     async def view_gmail_allow_list(
#         user_google_email: str
#     ) -> str:
#         """
#         Views the current Gmail allow list configuration.
#         Shows which email addresses will skip elicitation confirmation.
        
#         Args:
#             user_google_email: The authenticated user's Google email address (for authorization)
            
#         Returns:
#             str: Formatted list of allowed email addresses
#         """
#         from config.settings import settings
        
#         logger.info(f"[view_gmail_allow_list] User: '{user_google_email}' viewing allow list")
        
#         try:
#             # Get current allow list
#             allow_list = settings.get_gmail_allow_list()
            
#             if not allow_list:
#                 return """📋 Gmail Allow List Status

# **Currently Empty**
# • No emails are configured to skip elicitation confirmation
# • All recipients will require confirmation before sending

# **To add emails to the allow list:**
# Use `add_to_gmail_allow_list` tool with the email address

# **Configuration:**
# Set the GMAIL_ALLOW_LIST environment variable with comma-separated emails"""
            
#             # Create masked versions for privacy
#             masked_list = []
#             for email in allow_list:
#                 if '@' in email:
#                     local, domain = email.split('@', 1)
#                     if len(local) > 3:
#                         masked = f"{local[:2]}***@{domain}"
#                     else:
#                         masked = f"***@{domain}"
#                 else:
#                     masked = email[:3] + "***" if len(email) > 3 else "***"
#                 masked_list.append(masked)
            
#             # Build response
#             lines = [
#                 "📋 Gmail Allow List Status",
#                 "",
#                 f"**{len(allow_list)} Email(s) Configured**",
#                 "These recipients will skip elicitation confirmation when sending emails:",
#                 ""
#             ]
            
#             for i, (masked, full) in enumerate(zip(masked_list, allow_list), 1):
#                 lines.append(f"{i}. {masked}")
            
#             lines.extend([
#                 "",
#                 "**Management:**",
#                 "• Use `add_to_gmail_allow_list` to add new emails",
#                 "• Use `remove_from_gmail_allow_list` to remove emails",
#                 "",
#                 "**Configuration Source:**",
#                 "GMAIL_ALLOW_LIST environment variable",
#                 "",
#                 "**Note:** Full email addresses are hidden for privacy."
#             ])
            
#             return "\n".join(lines)
            
#         except Exception as e:
#             logger.error(f"Unexpected error in view_gmail_allow_list: {e}")
#             return f"❌ Unexpected error: {e}"
#             return f"❌ Unexpected error: {e}"