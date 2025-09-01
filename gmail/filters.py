"""
Gmail filter management tools for FastMCP2.

This module provides tools for:
- Listing Gmail filters/rules
- Creating new filters with criteria and actions
- Getting filter details by ID
- Deleting filters
- Retroactive application of filters to existing emails
"""

import logging
import asyncio
import time
from typing_extensions import Optional, Literal, Any, List, Dict, Tuple

from fastmcp import FastMCP, Context
from googleapiclient.errors import HttpError

from .service import _get_gmail_service_with_fallback
from .gmail_types import GmailFiltersResponse, FilterInfo, FilterCriteria, FilterAction

logger = logging.getLogger(__name__)

async def apply_filter_to_existing_messages(
    gmail_service: Any,
    search_query: str,
    add_label_ids: Optional[List[str]] = None,
    remove_label_ids: Optional[List[str]] = None,
    batch_size: int = 100,
    max_messages: Optional[int] = None,
    rate_limit_delay: float = 0.1,
    ctx: Optional[Context] = None
) -> str:
    """
    Enhanced retroactive filter application with pagination, batch processing, and comprehensive error handling.
    
    Args:
        gmail_service: Authenticated Gmail service instance
        search_query: Gmail search query to find matching messages
        add_label_ids: List of label IDs to add to matching messages
        remove_label_ids: List of label IDs to remove from matching messages
        batch_size: Number of messages to process in each batch (default: 100)
        max_messages: Maximum number of messages to process (None for unlimited)
        rate_limit_delay: Delay in seconds between API calls (default: 0.1)
    
    Returns:
        Dict containing:
        - total_found: Total messages found matching criteria
        - processed_count: Number of messages successfully processed
        - error_count: Number of messages that failed processing
        - errors: List of error details
        - truncated: Whether processing was limited by max_messages
    """
    logger.info(f"[apply_filter_to_existing_messages] Starting retroactive application with query: {search_query}")
    
    results = {
        "total_found": 0,
        "processed_count": 0,
        "error_count": 0,
        "errors": [],
        "truncated": False
    }
    
    if not add_label_ids and not remove_label_ids:
        logger.warning("[apply_filter_to_existing_messages] No label actions specified")
        return results
    
    try:
        # Get all messages matching the criteria with pagination
        all_message_ids = []
        next_page_token = None
        page_count = 0
        
        while True:
            page_count += 1
            logger.info(f"[apply_filter_to_existing_messages] Fetching page {page_count}")
            
            # Report progress for page fetching
            if ctx:
                await ctx.info(f"Fetching email page {page_count}...")
            
            # Build list request with pagination
            search_params = {
                "userId": "me",
                "q": search_query,
                "maxResults": min(500, batch_size)  # Gmail API limit is 500 per request
            }
            
            if next_page_token:
                search_params["pageToken"] = next_page_token
            
            search_response = await asyncio.to_thread(
                gmail_service.users().messages().list(**search_params).execute
            )
            
            page_messages = search_response.get("messages", [])
            
            if not page_messages:
                break
                
            all_message_ids.extend([msg["id"] for msg in page_messages])
            logger.info(f"[apply_filter_to_existing_messages] Page {page_count}: Found {len(page_messages)} messages")
            
            # Report progress on total messages found so far
            if ctx:
                await ctx.report_progress(
                    progress=len(all_message_ids),
                    total=len(all_message_ids) + (500 if next_page_token else 0)  # Estimate
                )
            
            # Check if we've reached the maximum message limit
            if max_messages and len(all_message_ids) >= max_messages:
                all_message_ids = all_message_ids[:max_messages]
                results["truncated"] = True
                logger.info(f"[apply_filter_to_existing_messages] Reached max_messages limit: {max_messages}")
                break
            
            # Check for next page
            next_page_token = search_response.get("nextPageToken")
            if not next_page_token:
                break
            
            # Rate limiting between pages
            if rate_limit_delay > 0:
                await asyncio.sleep(rate_limit_delay)
        
        results["total_found"] = len(all_message_ids)
        logger.info(f"[apply_filter_to_existing_messages] Total messages found: {results['total_found']}")
        
        if not all_message_ids:
            return results
        
        # Process messages in batches
        for batch_start in range(0, len(all_message_ids), batch_size):
            batch_end = min(batch_start + batch_size, len(all_message_ids))
            batch_message_ids = all_message_ids[batch_start:batch_end]
            
            batch_num = batch_start//batch_size + 1
            logger.info(f"[apply_filter_to_existing_messages] Processing batch {batch_num}: {len(batch_message_ids)} messages")
            
            # Report batch processing progress
            if ctx:
                await ctx.report_progress(
                    progress=batch_start,
                    total=len(all_message_ids)
                )
                await ctx.info(f"Processing batch {batch_num} of {(len(all_message_ids) + batch_size - 1) // batch_size}: {len(batch_message_ids)} messages")
            
            # Try batch modify first (more efficient)
            try:
                if len(batch_message_ids) > 1:
                    # Use batchModify API for efficiency
                    modify_body = {
                        "ids": batch_message_ids
                    }
                    if add_label_ids:
                        modify_body["addLabelIds"] = add_label_ids
                    if remove_label_ids:
                        modify_body["removeLabelIds"] = remove_label_ids
                    
                    await asyncio.to_thread(
                        gmail_service.users().messages().batchModify(
                            userId="me", body=modify_body
                        ).execute
                    )
                    
                    results["processed_count"] += len(batch_message_ids)
                    logger.info(f"[apply_filter_to_existing_messages] Batch processed successfully: {len(batch_message_ids)} messages")
                    
                    # Report successful batch completion
                    if ctx:
                        await ctx.info(f"✅ Batch {batch_num} completed: {len(batch_message_ids)} messages processed")
                
                else:
                    # Single message - use regular modify
                    message_id = batch_message_ids[0]
                    modify_body = {}
                    if add_label_ids:
                        modify_body["addLabelIds"] = add_label_ids
                    if remove_label_ids:
                        modify_body["removeLabelIds"] = remove_label_ids
                    
                    await asyncio.to_thread(
                        gmail_service.users().messages().modify(
                            userId="me", id=message_id, body=modify_body
                        ).execute
                    )
                    
                    results["processed_count"] += 1
                    logger.info(f"[apply_filter_to_existing_messages] Single message processed: {message_id}")
                
            except Exception as batch_error:
                logger.warning(f"[apply_filter_to_existing_messages] Batch processing failed, falling back to individual calls: {batch_error}")
                
                # Fallback: Process messages individually
                for idx, message_id in enumerate(batch_message_ids):
                    try:
                        modify_body = {}
                        if add_label_ids:
                            modify_body["addLabelIds"] = add_label_ids
                        if remove_label_ids:
                            modify_body["removeLabelIds"] = remove_label_ids
                        
                        await asyncio.to_thread(
                            gmail_service.users().messages().modify(
                                userId="me", id=message_id, body=modify_body
                            ).execute
                        )
                        
                        results["processed_count"] += 1
                        
                        # Report individual message progress in fallback mode
                        if ctx and idx % 10 == 0:  # Report every 10 messages to avoid spam
                            await ctx.report_progress(
                                progress=batch_start + idx,
                                total=len(all_message_ids)
                            )
                        
                        # Rate limiting for individual calls
                        if rate_limit_delay > 0:
                            await asyncio.sleep(rate_limit_delay)
                            
                    except Exception as msg_error:
                        error_detail = f"Message {message_id}: {str(msg_error)}"
                        results["errors"].append(error_detail)
                        results["error_count"] += 1
                        logger.warning(f"[apply_filter_to_existing_messages] Failed to process message {message_id}: {msg_error}")
            
            # Rate limiting between batches
            if rate_limit_delay > 0 and batch_end < len(all_message_ids):
                await asyncio.sleep(rate_limit_delay)
    
    except Exception as e:
        error_detail = f"General error during retroactive application: {str(e)}"
        results["errors"].append(error_detail)
        results["error_count"] += 1
        logger.error(f"[apply_filter_to_existing_messages] Unexpected error: {e}")
    
    # Report final completion
    if ctx:
        await ctx.report_progress(
            progress=results['processed_count'],
            total=results['total_found']
        )
        await ctx.info(f"✅ Retroactive filter application completed: {results['processed_count']}/{results['total_found']} messages processed, {results['error_count']} errors")
    
    logger.info(f"[apply_filter_to_existing_messages] Completed - Found: {results['total_found']}, Processed: {results['processed_count']}, Errors: {results['error_count']}")
    return results



async def list_gmail_filters(user_google_email: str) -> GmailFiltersResponse:
    """
    Lists all Gmail filters/rules in the user's account.

    Args:
        user_google_email: The user's Google email address

    Returns:
        GmailFiltersResponse: Structured response with filter list and metadata
    """
    logger.info(f"[list_gmail_filters] Email: '{user_google_email}'")

    try:
        gmail_service = await _get_gmail_service_with_fallback(user_google_email)

        response = await asyncio.to_thread(
            gmail_service.users().settings().filters().list(userId="me").execute
        )
        filter_items = response.get("filter", [])

        # Convert to structured format
        filters: List[FilterInfo] = []
        for filter_obj in filter_items:
            # Extract criteria
            criteria_obj = filter_obj.get("criteria", {})
            criteria: FilterCriteria = {
                "from_address": criteria_obj.get("from"),
                "to_address": criteria_obj.get("to"),
                "subject": criteria_obj.get("subject"),
                "query": criteria_obj.get("query"),
                "hasAttachment": criteria_obj.get("hasAttachment"),
                "excludeChats": criteria_obj.get("excludeChats"),
                "size": criteria_obj.get("size"),
                "sizeComparison": criteria_obj.get("sizeComparison")
            }
            
            # Extract actions
            action_obj = filter_obj.get("action", {})
            action: FilterAction = {
                "addLabelIds": action_obj.get("addLabelIds"),
                "removeLabelIds": action_obj.get("removeLabelIds"),
                "forward": action_obj.get("forward"),
                "markAsSpam": action_obj.get("markAsSpam"),
                "markAsImportant": action_obj.get("markAsImportant"),
                "neverMarkAsSpam": action_obj.get("neverMarkAsSpam"),
                "neverMarkAsImportant": action_obj.get("neverMarkAsImportant")
            }
            
            filter_info: FilterInfo = {
                "id": filter_obj.get("id", ""),
                "criteria": criteria,
                "action": action
            }
            filters.append(filter_info)
        
        logger.info(f"Successfully retrieved {len(filters)} filters for {user_google_email}")
        
        return GmailFiltersResponse(
            filters=filters,
            count=len(filters),
            userEmail=user_google_email,
            error=None
        )

    except HttpError as e:
        logger.error(f"Gmail API error in list_gmail_filters: {e}")
        error_msg = None
        if e.resp.status in [401, 403]:
            error_msg = "Authentication error: Please check your Gmail permissions and re-authenticate if necessary."
        elif e.resp.status == 400:
            error_msg = f"Bad request: Unable to list Gmail filters. {e}"
        else:
            error_msg = f"Gmail API error: {e}"
        
        # Return structured error response
        return GmailFiltersResponse(
            filters=[],
            count=0,
            userEmail=user_google_email,
            error=error_msg
        )

    except Exception as e:
        logger.error(f"Unexpected error in list_gmail_filters: {e}")
        # Return structured error response
        return GmailFiltersResponse(
            filters=[],
            count=0,
            userEmail=user_google_email,
            error=f"Unexpected error: {e}"
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
    never_mark_as_important: Optional[bool] = None,
    ctx: Optional[Context] = None
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

                # Use enhanced retroactive application function with progress reporting
                retro_result = await apply_filter_to_existing_messages(
                    gmail_service=gmail_service,
                    search_query=search_query,
                    add_label_ids=parsed_add_label_ids,
                    remove_label_ids=parsed_remove_label_ids,
                    batch_size=100,  # Default batch size
                    max_messages=10000,  # Safety limit, much higher than original 500
                    rate_limit_delay=0.05,  # Small delay for API rate limiting
                    ctx=ctx  # Pass context for progress reporting
                )

                # Add the retroactive results to the response
                if isinstance(retro_result, dict):
                    total_found = retro_result.get('total_found', 0)
                    processed_count = retro_result.get('processed_count', 0)
                    error_count = retro_result.get('error_count', 0)
                    truncated = retro_result.get('truncated', False)
                    
                    response_lines.append(f"\n📊 RETROACTIVE APPLICATION RESULTS:")
                    response_lines.append(f"  Messages found: {total_found}")
                    response_lines.append(f"  Messages processed: {processed_count}")
                    response_lines.append(f"  Errors: {error_count}")
                    if truncated:
                        response_lines.append(f"  ⚠️ Processing limited to 10000 messages")
                else:
                    # Fallback for string results
                    response_lines.append(f"\n{retro_result}")

            except Exception as retro_error:
                logger.error(f"[create_gmail_filter] Error during retroactive application: {retro_error}")
                response_lines.append(f"\n⚠️ Filter created but retroactive application failed: {retro_error}")

        return "\n".join(response_lines)

    except HttpError as e:
        logger.error(f"Gmail API error in create_gmail_filter: {e}")
        if e.resp.status in [401, 403]:
            return f"❌ Authentication error: Please check your Gmail permissions and re-authenticate if necessary."
        elif e.resp.status == 400:
            error_details = str(e)
            if "already exists" in error_details.lower():
                return f"❌ Filter already exists: A filter with similar criteria already exists in your Gmail account."
            elif "label" in error_details.lower() and ("not found" in error_details.lower() or "invalid" in error_details.lower()):
                return f"❌ Invalid label: One or more specified label IDs do not exist in your Gmail account. Please check your label IDs and try again."
            else:
                return f"❌ Bad request: Unable to create Gmail filter. {e}"
        elif e.resp.status == 409:
            return f"❌ Conflict: Unable to create filter due to a conflict with existing filters or settings."
        else:
            return f"❌ Gmail API error: {e}"

    except Exception as e:
        logger.error(f"Unexpected error in create_gmail_filter: {e}")
        return f"❌ Unexpected error: {e}"


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

    except HttpError as e:
        logger.error(f"Gmail API error in get_gmail_filter: {e}")
        if e.resp.status in [401, 403]:
            return f"❌ Authentication error: Please check your Gmail permissions and re-authenticate if necessary."
        elif e.resp.status == 400:
            return f"❌ Bad request: Unable to retrieve Gmail filter details. {e}"
        elif e.resp.status == 404:
            return f"❌ Filter not found: The specified filter ID '{filter_id}' does not exist in your Gmail account."
        else:
            return f"❌ Gmail API error: {e}"

    except Exception as e:
        logger.error(f"Unexpected error in get_gmail_filter: {e}")
        return f"❌ Unexpected error: {e}"


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

    except HttpError as e:
        logger.error(f"Gmail API error in delete_gmail_filter: {e}")
        if e.resp.status in [401, 403]:
            return f"❌ Authentication error: Please check your Gmail permissions and re-authenticate if necessary."
        elif e.resp.status == 400:
            return f"❌ Bad request: Unable to delete Gmail filter. {e}"
        elif e.resp.status == 404:
            return f"❌ Filter not found: The specified filter ID '{filter_id}' does not exist in your Gmail account."
        else:
            return f"❌ Gmail API error: {e}"

    except Exception as e:
        logger.error(f"Unexpected error in delete_gmail_filter: {e}")
        return f"❌ Unexpected error: {e}"


def setup_filter_tools(mcp: FastMCP) -> None:
    """Register Gmail filter tools with the FastMCP server."""

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
    async def list_gmail_filters_tool(user_google_email: str) -> GmailFiltersResponse:
        return await list_gmail_filters(user_google_email)

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
    async def create_gmail_filter_tool(
        ctx: Context,
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
        return await create_gmail_filter(
            user_google_email, from_address, to_address, subject_contains, query,
            has_attachment, exclude_chats, size, size_comparison, add_label_ids,
            remove_label_ids, forward_to, mark_as_spam, mark_as_important,
            never_mark_as_spam, never_mark_as_important, ctx
        )

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
    async def get_gmail_filter_tool(
        user_google_email: str,
        filter_id: str
    ) -> str:
        return await get_gmail_filter(user_google_email, filter_id)

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
    async def delete_gmail_filter_tool(
        user_google_email: str,
        filter_id: str
    ) -> str:
        return await delete_gmail_filter(user_google_email, filter_id)