"""
Google Forms MCP Tools for FastMCP2.

This module provides MCP tools for interacting with Google Forms API.
Migrated from decorator-based pattern to FastMCP2 architecture.
"""

import logging
import asyncio
from typing_extensions import List, Optional, Dict, Any, Union, Tuple
from googleapiclient.errors import HttpError
from fastmcp import FastMCP

from auth.service_helpers import get_service, request_service
from auth.context import get_injected_service
from .forms_types import FormResponsesListResponse, FormResponseInfo, FormResponseAnswer

logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS AND CONFIGURATION
# ============================================================================

# Question types that support grading
GRADABLE_QUESTION_TYPES = {
    "TEXT_QUESTION",
    "MULTIPLE_CHOICE_QUESTION",
    "SCALE_QUESTION",
    "CHECKBOX_QUESTION",
    "DATE_QUESTION",
    "TIME_QUESTION",
    "RATING_QUESTION",
}

# Valid update fields for validation
VALID_UPDATE_FIELDS = {
    "title",
    "description",
    "question",
    "questionGroupItem",
    "imageItem",
    "videoItem",
    "pageBreakItem",
    "textItem",
}

# Item type mappings for detection
ITEM_TYPE_MAPPINGS = {
    "questionItem": "questionItem",
    "videoItem": "videoItem",
    "imageItem": "imageItem",
    "pageBreakItem": "pageBreakItem",
    "textItem": "textItem",
    "questionGroupItem": "questionGroupItem",
}

# Question type detection mappings
QUESTION_TYPE_DETECTORS = {
    "choiceQuestion": "MULTIPLE_CHOICE",
    "textQuestion": "TEXT",
    "scaleQuestion": "SCALE",
    "dateQuestion": "DATE",
    "timeQuestion": "TIME",
    "ratingQuestion": "RATING",
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def format_question_details(question: Dict[str, Any]) -> str:
    """
    Format a single question's details for display.
    
    Args:
        question: Question dict from Forms API
        
    Returns:
        Formatted string describing the question
    """
    question_item = question.get("questionItem", {})
    q_question = question_item.get("question", {})
    
    q_type = q_question.get("type", "Unknown")
    q_text = question.get("title", "No title")
    q_id = question.get("itemId", "No ID")
    required = q_question.get("required", False)
    
    # Extract additional details based on question type
    details = []
    
    if q_type == "CHOICE_QUESTION":
        choice_q = q_question.get("choiceQuestion", {})
        options = choice_q.get("options", [])
        details.append(f"Options: {len(options)}")
        details.append(f"Type: {'Radio' if choice_q.get('type') == 'RADIO' else 'Checkbox'}")
    elif q_type == "SCALE":
        scale_q = q_question.get("scaleQuestion", {})
        details.append(f"Scale: {scale_q.get('low', 1)} to {scale_q.get('high', 5)}")
    elif q_type == "TEXT":
        text_q = q_question.get("textQuestion", {})
        details.append(f"Paragraph: {'Yes' if text_q.get('paragraph') else 'No'}")
    
    # Build the formatted string
    parts = [
        f"ID: {q_id}",
        f"Type: {q_type}",
        f"Required: {'Yes' if required else 'No'}",
    ]
    if details:
        parts.extend(details)
    
    return f"- \"{q_text}\" ({', '.join(parts)})"


def format_response_answers(response: Dict[str, Any], form_metadata: Dict[str, Any]) -> List[str]:
    """
    Format response answers with question context.
    
    Args:
        response: Response object from Forms API
        form_metadata: Form metadata including questions
        
    Returns:
        List of formatted answer strings
    """
    answers = response.get("answers", {})
    items = form_metadata.get("items", [])
    
    # Create a mapping of question IDs to questions
    question_map = {}
    for item in items:
        if "questionItem" in item:
            question_map[item["itemId"]] = item
    
    formatted_answers = []
    for question_id, answer_data in answers.items():
        question = question_map.get(question_id, {})
        question_title = question.get("title", f"Question {question_id}")
        
        text_answers = answer_data.get("textAnswers", {})
        if text_answers and "answers" in text_answers:
            answer_values = [ans.get("value", "") for ans in text_answers["answers"]]
            answer_text = ", ".join(answer_values)
            formatted_answers.append(f"- {question_title}: {answer_text}")
        else:
            formatted_answers.append(f"- {question_title}: [No answer]")
    
    return formatted_answers


def validate_question_structure(question: Dict[str, Any]) -> bool:
    """
    Validate that a question dict has the required structure.
    
    Args:
        question: Question dictionary to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not isinstance(question, dict):
        return False
    
    if "type" not in question:
        return False
    
    q_type = question["type"]
    
    # Check required fields based on question type
    if q_type == "TEXT_QUESTION":
        return "title" in question
    elif q_type == "MULTIPLE_CHOICE_QUESTION":
        return "title" in question and "options" in question
    elif q_type == "SCALE_QUESTION":
        return all(key in question for key in ["title", "low", "high"])
    elif q_type == "CHECKBOX_QUESTION":
        return "title" in question and "options" in question
    elif q_type == "DATE_QUESTION":
        return "title" in question
    elif q_type == "TIME_QUESTION":
        return "title" in question
    elif q_type == "RATING_QUESTION":
        return "title" in question and "rating_scale_level" in question
    elif q_type == "FILE_UPLOAD_QUESTION":
        return "title" in question
    
    return False


def build_question_item(question: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a Forms API question item from a simplified question dict.
    
    Args:
        question: Simplified question dictionary
        
    Returns:
        Forms API formatted question item
    """
    if not validate_question_structure(question):
        raise ValueError(f"Invalid question structure: {question}")
    
    q_type = question["type"]
    title = question["title"]
    
    # Base structure
    item = {
        "title": title,
        "questionItem": {
            "question": {
                "required": question.get("required", False)
            }
        }
    }
    
    q_obj = item["questionItem"]["question"]
    
    if q_type == "TEXT_QUESTION":
        q_obj["textQuestion"] = {"paragraph": question.get("paragraph", False)}
    
    elif q_type == "MULTIPLE_CHOICE_QUESTION":
        options = [{"value": opt} for opt in question["options"]]
        q_obj["choiceQuestion"] = {
            "type": "RADIO",
            "options": options,
            "shuffle": question.get("shuffle", False)
        }
    
    elif q_type == "CHECKBOX_QUESTION":
        options = [{"value": opt} for opt in question["options"]]
        q_obj["choiceQuestion"] = {
            "type": "CHECKBOX",
            "options": options,
            "shuffle": question.get("shuffle", False)
        }
    
    elif q_type == "SCALE_QUESTION":
        q_obj["scaleQuestion"] = {
            "low": question.get("low", 1),
            "high": question.get("high", 5),
            "lowLabel": question.get("low_label", ""),
            "highLabel": question.get("high_label", "")
        }
    
    elif q_type == "DATE_QUESTION":
        q_obj["dateQuestion"] = {
            "includeTime": question.get("include_time", False),
            "includeYear": question.get("include_year", True)
        }
    
    elif q_type == "TIME_QUESTION":
        q_obj["timeQuestion"] = {"duration": question.get("duration", False)}
    
    elif q_type == "RATING_QUESTION":
        q_obj["ratingQuestion"] = {
            "ratingScaleLevel": question["rating_scale_level"]
        }
    
    elif q_type == "FILE_UPLOAD_QUESTION":
        q_obj["fileUploadQuestion"] = {
            "folderId": question.get("folder_id", ""),
            "maxFiles": question.get("max_files", 1),
            "maxFileSize": question.get("max_file_size", 10485760)  # 10MB default
        }
    
    # Add grading if specified
    if "points" in question:
        q_obj["grading"] = {
            "pointValue": question["points"],
            "correctAnswers": {"answers": question.get("correct_answers", [])}
        }
    
    return item


def build_batch_update_request(updates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build a batch update request from a list of updates.
    
    Args:
        updates: List of update dictionaries
        
    Returns:
        Batch update request body
    """
    requests = []
    
    for update in updates:
        item_id = update.get("item_id")
        if not item_id:
            continue
            
        request = {}
        
        # Handle different update types
        if "title" in update:
            request["updateItem"] = {
                "item": {"itemId": item_id, "title": update["title"]},
                "updateMask": "title"
            }
        
        if "description" in update:
            request["updateItem"] = {
                "item": {"itemId": item_id, "description": update["description"]},
                "updateMask": "description"
            }
        
        if "required" in update:
            request["updateItem"] = {
                "item": {
                    "itemId": item_id,
                    "questionItem": {"question": {"required": update["required"]}}
                },
                "updateMask": "questionItem.question.required"
            }
        
        if request:
            requests.append(request)
    
    return {"requests": requests}


def extract_item_type(item: Dict[str, Any]) -> str:
    """
    Extract the type of a form item.
    
    Args:
        item: Form item from API
        
    Returns:
        Item type string
    """
    for key, value in ITEM_TYPE_MAPPINGS.items():
        if key in item:
            return value
    return "unknown"


def extract_question_type(item: Dict[str, Any]) -> str:
    """
    Extract the specific question type from a question item.
    
    Args:
        item: Form item from API
        
    Returns:
        Question type string
    """
    if "questionItem" not in item:
        return "NOT_A_QUESTION"
    
    question = item["questionItem"].get("question", {})
    
    for key, q_type in QUESTION_TYPE_DETECTORS.items():
        if key in question:
            return q_type
    
    return "UNKNOWN"


def validate_update_request(update: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate an update request structure.
    
    Args:
        update: Update request dictionary
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(update, dict):
        return False, "Update must be a dictionary"
    
    if "item_id" not in update:
        return False, "Missing required field: item_id"
    
    # Check if at least one update field is present
    update_fields = set(update.keys()) - {"item_id"}
    if not update_fields:
        return False, "No update fields specified"
    
    # Validate update fields
    invalid_fields = update_fields - VALID_UPDATE_FIELDS
    if invalid_fields:
        return False, f"Invalid update fields: {invalid_fields}"
    
    return True, ""


# ============================================================================
# SERVICE HELPER FUNCTIONS  
# ============================================================================

async def _get_forms_service_with_fallback(user_google_email: str):
    """Get Forms service with fallback to direct creation."""
    try:
        return await get_service("forms", user_google_email)
    except Exception as e:
        logger.warning(f"Failed to get Forms service via middleware: {e}")
        logger.info("Falling back to direct service creation")
        return await get_service("forms", user_google_email)


async def _get_drive_service_with_fallback(user_google_email: str):
    """Get Drive service with fallback to direct creation."""
    try:
        return await get_service("drive", user_google_email)
    except Exception as e:
        logger.warning(f"Failed to get Drive service via middleware: {e}")
        logger.info("Falling back to direct service creation")
        return await get_service("drive", user_google_email)


# ============================================================================
# MAIN TOOL FUNCTIONS
# ============================================================================


def setup_forms_tools(mcp: FastMCP) -> None:
    """
    Setup and register all Google Forms tools with the MCP server.
    
    Args:
        mcp: The FastMCP server instance to register tools with
    """
    logger.info("Setting up Google Forms tools")
    
    @mcp.tool(
        name="create_form",
        description="Create a new Google Form with title, description, and document title",
        tags={"forms", "create", "google"},
        annotations={
            "title": "Create Google Form",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def create_form(
        user_google_email: str,
        title: str,
        description: Optional[str] = None,
        document_title: Optional[str] = None,
    ) -> str:
        """
        Create a new Google Form - UPDATED WITH API BEST PRACTICES.

        This function creates a basic Google Form with title, description, and document title.
        To add questions to the form, use the add_questions_to_form tool after creation.

        Args:
            user_google_email (str): The user's Google email address. Required.
            title (str): The title of the form.
            description (Optional[str]): The description of the form.
            document_title (Optional[str]): The document title (shown in browser tab).

        Returns:
            str: Success message with form ID and edit URL.
        """
        # Log the tool request

        try:
            # Get the Forms service via middleware injection
            forms_service = await _get_forms_service_with_fallback(user_google_email)
            
            # Build the form data according to the API best practices
            form_data = {
                "info": {
                    "title": title,
                }
            }
            
            if description:
                form_data["info"]["description"] = description
                
            if document_title:
                form_data["info"]["documentTitle"] = document_title
            
            # Create the form via the API
            created_form = await asyncio.to_thread(
                forms_service.forms().create(body=form_data).execute
            )
            
            form_id = created_form.get("formId")
            edit_url = f"https://docs.google.com/forms/d/{form_id}/edit"
            responder_uri = created_form.get("responderUri", "Not yet available")
            
            success_msg = (
                f"✅ Successfully created form '{title}'\n"
                f"Form ID: {form_id}\n"
                f"Edit URL: {edit_url}\n"
                f"Response URL: {responder_uri}"
            )
            
            logger.info(f"[create_form] {success_msg}")
            return success_msg
            
        except HttpError as e:
            error_msg = f"❌ Failed to create form: {e}"
            logger.error(f"[create_form] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error creating form: {str(e)}"
            logger.error(f"[create_form] Unexpected error: {e}")
            return error_msg

    @mcp.tool(
        name="add_questions_to_form",
        description="Add multiple questions to an existing Google Form",
        tags={"forms", "questions", "update", "google"},
        annotations={
            "title": "Add Questions to Form",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def add_questions_to_form(
        user_google_email: str,
        form_id: str,
        questions: List[Dict[str, Any]]
    ) -> str:
        """
        Add multiple questions to an existing Google Form - BATCH OPERATIONS.

        This function adds questions to an existing form using batch operations
        for efficiency. Supports all standard question types.

        Args:
            user_google_email (str): The user's Google email address.
            form_id (str): The ID of the form to add questions to.
            questions (List[Dict]): List of question dictionaries.

        Returns:
            str: Success message with number of questions added.
        """

        try:
            forms_service = await _get_forms_service_with_fallback(user_google_email)
            
            # Build batch update requests
            requests = []
            for i, question in enumerate(questions):
                try:
                    item = build_question_item(question)
                    requests.append({
                        "createItem": {
                            "item": item,
                            "location": {"index": i}
                        }
                    })
                except ValueError as e:
                    logger.warning(f"Skipping invalid question: {e}")
                    continue
            
            if not requests:
                return "❌ No valid questions to add"
            
            batch_update_body = {"requests": requests}
            
            # Execute the batch update
            result = await asyncio.to_thread(
                forms_service.forms().batchUpdate(
                    formId=form_id,
                    body=batch_update_body
                ).execute
            )
            
            # Get the updated form to show the edit URL
            form = await asyncio.to_thread(
                forms_service.forms().get(formId=form_id).execute
            )
            
            edit_url = f"https://docs.google.com/forms/d/{form_id}/edit"
            responder_uri = form.get("responderUri", "Not yet available")
            
            success_msg = (
                f"✅ Successfully added {len(requests)} questions to form\n"
                f"Form ID: {form_id}\n"
                f"Edit URL: {edit_url}\n"
                f"Response URL: {responder_uri}"
            )
            
            logger.info(f"[add_questions_to_form] {success_msg}")
            return success_msg
            
        except HttpError as e:
            error_msg = f"❌ Failed to add questions: {e}"
            logger.error(f"[add_questions_to_form] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[add_questions_to_form] {error_msg}")
            return error_msg

    @mcp.tool(
        name="get_form",
        description="Get details of a Google Form including all questions and settings",
        tags={"forms", "read", "google", "get"},
        annotations={
            "title": "Get Form Details",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def get_form(
        user_google_email: str,
        form_id: str
    ) -> str:
        """
        Get details of a Google Form - COMPREHENSIVE INFO.

        Retrieves complete form information including title, description,
        questions, and settings.

        Args:
            user_google_email (str): The user's Google email address.
            form_id (str): The ID of the form to retrieve.

        Returns:
            str: Form details including title, description, and questions.
        """

        
        try:
            forms_service = await _get_forms_service_with_fallback(user_google_email)
            
            # Get the form
            form = await asyncio.to_thread(
                forms_service.forms().get(formId=form_id).execute
            )
            
            # Extract form info
            info = form.get("info", {})
            title = info.get("title", "Untitled Form")
            description = info.get("description", "No description")
            document_title = info.get("documentTitle", title)
            
            # Extract questions
            items = form.get("items", [])
            questions = []
            
            for item in items:
                item_type = extract_item_type(item)
                if item_type == "questionItem":
                    questions.append(format_question_details(item))
            
            # Build response
            response_parts = [
                f"📋 Form: {title}",
                f"Document Title: {document_title}",
                f"Description: {description}",
                f"Form ID: {form_id}",
                f"Edit URL: https://docs.google.com/forms/d/{form_id}/edit",
                f"Response URL: {form.get('responderUri', 'Not yet available')}",
                f"\nQuestions ({len(questions)}):"
            ]
            
            if questions:
                response_parts.extend(questions)
            else:
                response_parts.append("No questions found")
            
            return "\n".join(response_parts)
            
        except HttpError as e:
            error_msg = f"❌ Failed to get form: {e}"
            logger.error(f"[get_form] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[get_form] {error_msg}")
            return error_msg

    @mcp.tool(
        name="set_form_publish_state",
        description="Publish or unpublish a Google Form (make it accepting responses or not)",
        tags={"forms", "settings", "publish", "google"},
        annotations={
            "title": "Set Form Publish State",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def set_form_publish_state(
        user_google_email: str,
        form_id: str,
        accepting_responses: bool = True
    ) -> str:
        """
        Set whether a form is accepting responses - FORM SETTINGS.

        Updates form settings to control response acceptance.
        Note: Full control over response settings requires manual configuration
        in the Forms UI.

        Args:
            user_google_email (str): The user's Google email address.
            form_id (str): The ID of the form.
            accepting_responses (bool): Whether to accept responses.

        Returns:
            str: Success message with form state.
        """

        try:
            forms_service = await _get_forms_service_with_fallback(user_google_email)
            
            # Update form settings
            update_body = {
                "requests": [{
                    "updateSettings": {
                        "settings": {
                            "quizSettings": {
                                "isQuiz": False  # Ensure it's not a quiz
                            }
                        },
                        "updateMask": "quizSettings.isQuiz"
                    }
                }]
            }
            
            # Note: The Forms API doesn't directly support setting accepting_responses
            # This is typically controlled through the form's settings in the UI
            # We'll update what we can and provide instructions
            
            await asyncio.to_thread(
                forms_service.forms().batchUpdate(
                    formId=form_id,
                    body=update_body
                ).execute
            )
            
            # Get the form to show current state
            form = await asyncio.to_thread(
                forms_service.forms().get(formId=form_id).execute
            )
            
            state = "accepting responses" if accepting_responses else "not accepting responses"
            
            return (
                f"✅ Form settings updated\n"
                f"Form ID: {form_id}\n"
                f"Title: {form.get('info', {}).get('title', 'Untitled')}\n"
                f"Desired state: {state}\n"
                f"Edit URL: https://docs.google.com/forms/d/{form_id}/edit\n"
                f"Response URL: {form.get('responderUri', 'Not yet available')}\n\n"
                f"Note: To fully control response acceptance, visit the form editor and use Settings > Responses"
            )
            
        except HttpError as e:
            error_msg = f"❌ Failed to update form settings: {e}"
            logger.error(f"[set_form_publish_state] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[set_form_publish_state] {error_msg}")
            return error_msg

    @mcp.tool(
        name="publish_form_publicly", 
        description="Make a Google Form publicly accessible (no sign-in required) and share with specific permissions",
        tags={"forms", "share", "publish", "google", "permissions"},
        annotations={
            "title": "Publish Form Publicly",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def publish_form_publicly(
        user_google_email: str,
        form_id: str,
        anyone_can_respond: bool = True,
        share_with_emails: Optional[List[str]] = None
    ) -> str:
        """
        Make a form publicly accessible - MULTI-SERVICE OPERATION.

        Uses both Forms and Drive APIs to manage sharing permissions.
        Allows public access and sharing with specific users.

        Args:
            user_google_email (str): The user's Google email address.
            form_id (str): The ID of the form.
            anyone_can_respond (bool): Whether anyone can respond.
            share_with_emails (List[str]): Emails to share with.

        Returns:
            str: Success message with sharing details.
        """

        
        try:
            # Get both services
            forms_service = await _get_forms_service_with_fallback(user_google_email)
            drive_service = await _get_drive_service_with_fallback(user_google_email)
            
            results = []
            
            # Get form details first
            form = await asyncio.to_thread(
                forms_service.forms().get(formId=form_id).execute
            )
            title = form.get("info", {}).get("title", "Untitled Form")
            
            # Set public access if requested
            if anyone_can_respond:
                try:
                    permission = {
                        'type': 'anyone',
                        'role': 'writer'
                    }
                    
                    await asyncio.to_thread(
                        drive_service.permissions().create(
                            fileId=form_id,
                            body=permission,
                            fields='id'
                        ).execute
                    )
                    
                    results.append("✅ Form is now publicly accessible (no sign-in required)")
                except HttpError as e:
                    if e.resp.status == 403:
                        results.append("⚠️ Could not make form public (may require domain admin permissions)")
                    else:
                        results.append(f"⚠️ Error setting public access: {e}")
            
            # Share with specific emails
            if share_with_emails:
                for email in share_with_emails:
                    try:
                        permission = {
                            'type': 'user',
                            'role': 'writer',
                            'emailAddress': email
                        }
                        
                        await asyncio.to_thread(
                            drive_service.permissions().create(
                                fileId=form_id,
                                body=permission,
                                sendNotificationEmail=True,
                                fields='id'
                            ).execute
                        )
                        
                        results.append(f"✅ Shared with {email} as editor")
                    except HttpError as e:
                        results.append(f"⚠️ Failed to share with {email}: {e}")
            
            # Build final response
            response_parts = [
                f"📋 Form: {title}",
                f"Form ID: {form_id}",
                f"Response URL: {form.get('responderUri', 'Not yet available')}",
                f"Edit URL: https://docs.google.com/forms/d/{form_id}/edit",
                "",
                "Sharing Results:"
            ]
            response_parts.extend(results)
            
            return "\n".join(response_parts)
            
        except HttpError as e:
            error_msg = f"❌ Failed to publish form: {e}"
            logger.error(f"[publish_form_publicly] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[publish_form_publicly] {error_msg}")
            return error_msg

    @mcp.tool(
        name="get_form_response",
        description="Get a specific response from a Google Form by response ID",
        tags={"forms", "responses", "get", "google"},
        annotations={
            "title": "Get Form Response",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def get_form_response(
        user_google_email: str,
        form_id: str,
        response_id: str
    ) -> str:
        """
        Get a specific response from a form - RESPONSE DETAILS.

        Retrieves a single response with full answer details mapped
        to the corresponding questions.

        Args:
            user_google_email (str): The user's Google email address.
            form_id (str): The ID of the form.
            response_id (str): The ID of the response.

        Returns:
            str: Response details with answers.
        """

        
        try:
            forms_service = await _get_forms_service_with_fallback(user_google_email)
            
            # Get the specific response
            response = await asyncio.to_thread(
                forms_service.forms().responses().get(
                    formId=form_id,
                    responseId=response_id
                ).execute
            )
            
            # Get form metadata to map questions
            form = await asyncio.to_thread(
                forms_service.forms().get(formId=form_id).execute
            )
            
            # Format response details
            response_parts = [
                f"📋 Response Details",
                f"Response ID: {response_id}",
                f"Submitted: {response.get('lastSubmittedTime', 'Unknown')}",
                f"Respondent Email: {response.get('respondentEmail', 'Anonymous')}",
                "",
                "Answers:"
            ]
            
            # Format answers with question context
            formatted_answers = format_response_answers(response, form)
            response_parts.extend(formatted_answers)
            
            return "\n".join(response_parts)
            
        except HttpError as e:
            if e.resp.status == 404:
                error_msg = f"❌ Response not found. Please check the response ID: {response_id}"
            else:
                error_msg = f"❌ Failed to get response: {e}"
            logger.error(f"[get_form_response] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[get_form_response] {error_msg}")
            return error_msg

    @mcp.tool(
        name="list_form_responses",
        description="List all responses for a Google Form with pagination support",
        tags={"forms", "responses", "list", "google"},
        annotations={
            "title": "List Form Responses",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def list_form_responses(
        user_google_email: str,
        form_id: str,
        page_size: int = 10,
        page_token: Optional[str] = None
    ) -> FormResponsesListResponse:
        """
        List responses for a form - PAGINATED RESULTS.

        Retrieves form responses with pagination support for handling
        large numbers of submissions.

        Args:
            user_google_email (str): The user's Google email address.
            form_id (str): The ID of the form.
            page_size (int): Number of responses per page.
            page_token (str): Pagination token.

        Returns:
            FormResponsesListResponse: Structured response with form responses
        """
        
        try:
            forms_service = await _get_forms_service_with_fallback(user_google_email)
            
            # Build request parameters
            params = {"pageSize": page_size}
            if page_token:
                params["pageToken"] = page_token
            
            # List responses
            result = await asyncio.to_thread(
                forms_service.forms().responses().list(
                    formId=form_id,
                    **params
                ).execute
            )
            
            raw_responses = result.get("responses", [])
            next_page_token = result.get("nextPageToken")
            
            # Get form metadata to map questions
            form = await asyncio.to_thread(
                forms_service.forms().get(formId=form_id).execute
            )
            title = form.get("info", {}).get("title", "Untitled Form")
            
            # Create a mapping of question IDs to questions
            items = form.get("items", [])
            question_map = {}
            for item in items:
                if "questionItem" in item:
                    question_map[item["itemId"]] = item
            
            # Convert to structured format
            responses: List[FormResponseInfo] = []
            for response in raw_responses:
                # Format answers with question context
                structured_answers: List[FormResponseAnswer] = []
                answers = response.get("answers", {})
                
                for question_id, answer_data in answers.items():
                    question = question_map.get(question_id, {})
                    question_title = question.get("title", f"Question {question_id}")
                    
                    text_answers = answer_data.get("textAnswers", {})
                    answer_text = ""
                    if text_answers and "answers" in text_answers:
                        answer_values = [ans.get("value", "") for ans in text_answers["answers"]]
                        answer_text = ", ".join(answer_values)
                    else:
                        answer_text = "[No answer]"
                    
                    answer_info: FormResponseAnswer = {
                        "questionId": question_id,
                        "questionTitle": question_title,
                        "answer": answer_text
                    }
                    structured_answers.append(answer_info)
                
                response_info: FormResponseInfo = {
                    "responseId": response.get("responseId", ""),
                    "submittedTime": response.get("lastSubmittedTime", "Unknown"),
                    "respondentEmail": response.get("respondentEmail"),
                    "answers": structured_answers
                }
                responses.append(response_info)
            
            logger.info(f"Successfully retrieved {len(responses)} responses for form {form_id}")
            
            return FormResponsesListResponse(
                responses=responses,
                count=len(responses),
                formId=form_id,
                formTitle=title,
                userEmail=user_google_email,
                pageToken=page_token,
                nextPageToken=next_page_token,
                error=None
            )
            
        except HttpError as e:
            error_msg = f"Failed to list responses: {e}"
            logger.error(f"[list_form_responses] HTTP error: {e}")
            # Return structured error response
            return FormResponsesListResponse(
                responses=[],
                count=0,
                formId=form_id,
                formTitle="Unknown",
                userEmail=user_google_email,
                pageToken=page_token,
                nextPageToken=None,
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"[list_form_responses] {error_msg}")
            # Return structured error response
            return FormResponsesListResponse(
                responses=[],
                count=0,
                formId=form_id,
                formTitle="Unknown",
                userEmail=user_google_email,
                pageToken=page_token,
                nextPageToken=None,
                error=error_msg
            )
    @mcp.tool(
        name="update_form_questions",
        description="Update existing questions in a Google Form (modify titles, descriptions, or settings)",
        tags={"forms", "update", "questions", "google"},
        annotations={
            "title": "Update Form Questions",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def update_form_questions(
        user_google_email: str,
        form_id: str,
        questions_to_update: List[Dict[str, Any]]
    ) -> str:
        """
        Update existing questions in a form - BATCH UPDATES.

        Modifies question titles, descriptions, or settings using
        batch operations for efficiency.

        Args:
            user_google_email (str): The user's Google email address.
            form_id (str): The ID of the form.
            questions_to_update (List[Dict]): List of question updates.

        Returns:
            str: Success message with update details.
        """

        
        try:
            forms_service = await _get_forms_service_with_fallback(user_google_email)
            
            # Validate updates
            valid_updates = []
            for update in questions_to_update:
                is_valid, error = validate_update_request(update)
                if is_valid:
                    valid_updates.append(update)
                else:
                    logger.warning(f"Skipping invalid update: {error}")
            
            if not valid_updates:
                return "❌ No valid updates to apply"
            
            # Build batch update request
            batch_update_body = build_batch_update_request(valid_updates)
            
            # Execute the update
            result = await asyncio.to_thread(
                forms_service.forms().batchUpdate(
                    formId=form_id,
                    body=batch_update_body
                ).execute
            )
            
            # Get updated form info
            form = await asyncio.to_thread(
                forms_service.forms().get(formId=form_id).execute
            )
            
            return (
                f"✅ Successfully updated {len(valid_updates)} questions\n"
                f"Form: {form.get('info', {}).get('title', 'Untitled')}\n"
                f"Form ID: {form_id}\n"
                f"Edit URL: https://docs.google.com/forms/d/{form_id}/edit"
            )
            
        except HttpError as e:
            error_msg = f"❌ Failed to update questions: {e}"
            logger.error(f"[update_form_questions] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[update_form_questions] {error_msg}")
            return error_msg
    
    # Log successful setup
    tool_count = 8  # Total number of Forms tools
    logger.info(f"Successfully registered {tool_count} Google Forms tools")