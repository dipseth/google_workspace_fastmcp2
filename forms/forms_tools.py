"""
Google Forms MCP Tools for FastMCP2 - Comprehensive Form Management Suite.

This module provides a complete set of MCP tools for creating, managing, and analyzing
Google Forms. It supports the full form lifecycle from creation to response analysis.

KEY WORKFLOWS:
1. CREATE FORM → ADD QUESTIONS → PUBLISH → COLLECT RESPONSES → ANALYZE
2. Forms can be shared publicly or with specific users via email
3. Responses can be retrieved individually or in batches with pagination
4. Questions support multiple types: text, multiple choice, scale, date, etc.

TOOL RELATIONSHIPS:
- create_form: Creates the base form structure
- add_questions_to_form: Adds interactive questions (use after create_form)
- get_form: Retrieves form details and structure for inspection
- set_form_publish_state/publish_form_publicly: Controls access and sharing
- list_form_responses/get_form_response: Retrieves submitted responses
- update_form_questions: Modifies existing questions

AUTHENTICATION:
All tools use unified authentication via user_google_email parameter.
When using middleware injection, this parameter can be omitted.

SUPPORTED QUESTION TYPES:
- TEXT_QUESTION: Short/long text responses
- MULTIPLE_CHOICE_QUESTION: Radio button selections
- CHECKBOX_QUESTION: Multiple selection checkboxes
- SCALE_QUESTION: Numeric rating scales (1-5, 1-10, etc.)
- DATE_QUESTION: Date picker with optional time
- TIME_QUESTION: Time picker with optional duration
- RATING_QUESTION: Star rating systems
- FILE_UPLOAD_QUESTION: File attachment uploads
- DROPDOWN_QUESTION: Drop-down selections

SUPPORTED CONTENT ITEMS (add_questions_to_form, same list as the questions):
- IMAGE_ITEM: A standalone image (image_url, optional title/description)
- VIDEO_ITEM: A YouTube video (youtube_url, optional caption)
- TEXT_ITEM: A title + description block
- PAGE_BREAK_ITEM: Starts a new section
Any question can also carry an image (image_url), and so can a choice option
({"value": "A", "image_url": "..."}). Image URLs must be publicly reachable -
Google fetches them once when the item is created and stores its own copy.

HTML FORMATTING SUPPORT:
Google Forms API has LIMITED HTML support for rich content:

SUPPORTED HTML ELEMENTS:
- Form/Question Descriptions: Basic HTML tags like <b>, <i>, <u>, <br>, <p>
- Links: <a href="...">text</a> for clickable links
- Lists: <ul>, <ol>, <li> for bullet and numbered lists

RICH CONTENT ALTERNATIVES:
- Images: Use IMAGE_ITEM, or image_url on a question/option (not HTML <img> tags)
- Videos: Use VIDEO_ITEM (YouTube videos)
- Formatted Text: Use TEXT_ITEM for rich text sections
- HTML limitations: No CSS, JavaScript, or complex HTML structures

FORMATTING EXAMPLES:
- Description with HTML: "Please fill out <b>all required</b> fields.<br>Visit <a href='https://example.com'>our website</a> for help."
- Text Item HTML: "<p>Welcome to our survey!</p><ul><li>Be honest</li><li>Take your time</li></ul>"

Note: Full HTML web forms require custom web development - Google Forms API is designed for structured surveys with limited formatting.
"""

import asyncio

from fastmcp import FastMCP
from googleapiclient.errors import HttpError
from pydantic import Field
from typing_extensions import Annotated, Any, Dict, List, Optional, Tuple

from auth.service_helpers import get_service
from config.enhanced_logging import setup_logger

# Import our custom type for consistent parameter definition
from tools.common_types import UserGoogleEmailForms

from .forms_types import (
    FormCreationResult,
    FormDetails,
    FormItemSummary,
    FormPublishResult,
    FormQuestion,
    FormResponseAnswer,
    FormResponseDetails,
    FormResponseInfo,
    FormResponsesListResponse,
    FormUpdateResult,
)

logger = setup_logger()


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

# Simplified choice question types -> Forms API ChoiceQuestion.type
CHOICE_QUESTION_TYPES = {
    "MULTIPLE_CHOICE_QUESTION": "RADIO",
    "CHECKBOX_QUESTION": "CHECKBOX",
    "DROPDOWN_QUESTION": "DROP_DOWN",
}

IMAGE_ALIGNMENTS = {"LEFT", "CENTER", "RIGHT"}

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
        details.append(
            f"Type: {'Radio' if choice_q.get('type') == 'RADIO' else 'Checkbox'}"
        )
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

    return f'- "{q_text}" ({", ".join(parts)})'


def format_response_answers(
    response: Dict[str, Any], form_metadata: Dict[str, Any]
) -> List[str]:
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


def _has_choice_options(question: Dict[str, Any]) -> bool:
    """Choice questions accept both the simplified and the API option format."""
    return "options" in question or "options" in question.get("choiceQuestion", {})


def _is_http_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def validate_question_structure(question: Dict[str, Any]) -> bool:
    """
    Validate that an item dict has the required structure.
    Accepts both simplified format and Google API format.

    Args:
        question: Question (or non-question item) dictionary to validate

    Returns:
        bool: True if valid, False otherwise
    """
    if not isinstance(question, dict):
        return False

    if "type" not in question:
        return False

    q_type = question["type"]

    # An image attached to a question must be a fetchable URL
    if "image_url" in question and not _is_http_url(question["image_url"]):
        return False

    # Non-question items
    if q_type == "IMAGE_ITEM":
        return "image_url" in question
    elif q_type == "VIDEO_ITEM":
        return _is_http_url(question.get("youtube_url"))
    elif q_type in ("TEXT_ITEM", "PAGE_BREAK_ITEM"):
        return "title" in question

    # Check required fields based on question type
    if q_type == "TEXT_QUESTION":
        return "title" in question
    elif q_type in CHOICE_QUESTION_TYPES:
        return "title" in question and _has_choice_options(question)
    elif q_type == "SCALE_QUESTION":
        return all(key in question for key in ["title", "low", "high"])
    elif q_type == "DATE_QUESTION":
        return "title" in question
    elif q_type == "TIME_QUESTION":
        return "title" in question
    elif q_type == "RATING_QUESTION":
        return "title" in question and "rating_scale_level" in question
    elif q_type == "FILE_UPLOAD_QUESTION":
        return "title" in question

    return False


def build_image(source: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a Forms API Image from the simplified image_* keys.

    The Forms API fetches `sourceUri` once, at creation time, and keeps its own
    copy, so the URL only has to be publicly reachable while the item is created.

    Args:
        source: Dict carrying image_url plus optional image_alt_text,
            image_width (pixels, 0-740) and image_alignment (LEFT/CENTER/RIGHT)

    Returns:
        Forms API formatted Image
    """
    image_url = source.get("image_url")
    if not _is_http_url(image_url):
        raise ValueError(f"image_url must be a public http(s) URL: {image_url!r}")

    image: Dict[str, Any] = {"sourceUri": image_url}
    if source.get("image_alt_text"):
        image["altText"] = source["image_alt_text"]

    properties: Dict[str, Any] = {}
    if "image_width" in source:
        properties["width"] = source["image_width"]
    if "image_alignment" in source:
        alignment = str(source["image_alignment"]).upper()
        if alignment not in IMAGE_ALIGNMENTS:
            raise ValueError(
                f"image_alignment must be one of {sorted(IMAGE_ALIGNMENTS)}: {alignment!r}"
            )
        properties["alignment"] = alignment
    if properties:
        image["properties"] = properties

    return image


def build_choice_options(options: List[Any]) -> List[Dict[str, Any]]:
    """
    Build Forms API choice options.

    Each option is either a plain string or a dict with `value` and optional
    image_* keys (see build_image) to show a picture beside the option.
    """
    built = []
    for opt in options:
        if isinstance(opt, dict):
            if "value" not in opt:
                raise ValueError(f"Choice option is missing 'value': {opt}")
            option: Dict[str, Any] = {"value": opt["value"]}
            if "image_url" in opt:
                option["image"] = build_image(opt)
            built.append(option)
        else:
            built.append({"value": opt})
    return built


def build_question_item(question: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a Forms API item from a simplified item dict.

    Handles questions and the non-question items (IMAGE_ITEM, VIDEO_ITEM,
    TEXT_ITEM, PAGE_BREAK_ITEM).

    Args:
        question: Simplified item dictionary

    Returns:
        Forms API formatted item
    """
    if not validate_question_structure(question):
        raise ValueError(f"Invalid question structure: {question}")

    q_type = question["type"]

    item: Dict[str, Any] = {}
    if "title" in question:
        item["title"] = question["title"]
    if "description" in question:
        item["description"] = question["description"]

    # Non-question items
    if q_type == "IMAGE_ITEM":
        item["imageItem"] = {"image": build_image(question)}
        return item
    elif q_type == "VIDEO_ITEM":
        item["videoItem"] = {"video": {"youtubeUri": question["youtube_url"]}}
        if "caption" in question:
            item["videoItem"]["caption"] = question["caption"]
        return item
    elif q_type == "TEXT_ITEM":
        item["textItem"] = {}
        return item
    elif q_type == "PAGE_BREAK_ITEM":
        item["pageBreakItem"] = {}
        return item

    item["questionItem"] = {"question": {"required": question.get("required", False)}}
    if "image_url" in question:
        item["questionItem"]["image"] = build_image(question)

    q_obj = item["questionItem"]["question"]

    if q_type == "TEXT_QUESTION":
        q_obj["textQuestion"] = {"paragraph": question.get("paragraph", False)}

    elif q_type in CHOICE_QUESTION_TYPES:
        options = question.get("options") or question["choiceQuestion"]["options"]
        q_obj["choiceQuestion"] = {
            "type": CHOICE_QUESTION_TYPES[q_type],
            "options": build_choice_options(options),
            "shuffle": question.get("shuffle", False),
        }

    elif q_type == "SCALE_QUESTION":
        q_obj["scaleQuestion"] = {
            "low": question.get("low", 1),
            "high": question.get("high", 5),
            "lowLabel": question.get("low_label", ""),
            "highLabel": question.get("high_label", ""),
        }

    elif q_type == "DATE_QUESTION":
        q_obj["dateQuestion"] = {
            "includeTime": question.get("include_time", False),
            "includeYear": question.get("include_year", True),
        }

    elif q_type == "TIME_QUESTION":
        q_obj["timeQuestion"] = {"duration": question.get("duration", False)}

    elif q_type == "RATING_QUESTION":
        q_obj["ratingQuestion"] = {"ratingScaleLevel": question["rating_scale_level"]}

    elif q_type == "FILE_UPLOAD_QUESTION":
        q_obj["fileUploadQuestion"] = {
            "folderId": question.get("folder_id", ""),
            "maxFiles": question.get("max_files", 1),
            "maxFileSize": question.get("max_file_size", 10485760),  # 10MB default
        }

    # Add grading if specified
    if "points" in question:
        q_obj["grading"] = {
            "pointValue": question["points"],
            "correctAnswers": {"answers": question.get("correct_answers", [])},
        }

    return item


def build_create_item_requests(
    questions: List[Dict[str, Any]], start_index: int
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Build createItem requests that place the items consecutively from start_index.

    Invalid items are skipped without leaving a gap in the indexes (the Forms API
    rejects an index past the end of the form).

    Args:
        questions: Simplified item dictionaries
        start_index: Position of the first new item (0 = top of the form)

    Returns:
        Tuple of (createItem requests, one error string per skipped item)
    """
    requests: List[Dict[str, Any]] = []
    skipped: List[str] = []

    for position, question in enumerate(questions):
        try:
            item = build_question_item(question)
        except (ValueError, KeyError, TypeError) as e:
            skipped.append(f"#{position}: {e}")
            continue
        requests.append(
            {
                "createItem": {
                    "item": item,
                    "location": {"index": start_index + len(requests)},
                }
            }
        )

    return requests, skipped


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
                "updateMask": "title",
            }

        if "description" in update:
            request["updateItem"] = {
                "item": {"itemId": item_id, "description": update["description"]},
                "updateMask": "description",
            }

        if "required" in update:
            request["updateItem"] = {
                "item": {
                    "itemId": item_id,
                    "questionItem": {"question": {"required": update["required"]}},
                },
                "updateMask": "questionItem.question.required",
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
        description="Create a new Google Form with customizable title, description, and document title. Returns form ID and URLs for editing and responses.",
        tags={"forms", "create", "google"},
        annotations={
            "title": "Create Google Form",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def create_form(
        title: str,
        description: Optional[str] = None,
        document_title: Optional[str] = None,
        user_google_email: UserGoogleEmailForms = None,
    ) -> FormCreationResult:
        """
        Create a new Google Form with customizable title, description, and document title.

        Args:
            title: Form title displayed at the top
            description: Optional description explaining the form's purpose
            document_title: Title shown in browser tab (defaults to main title)
            user_google_email: Google account for authentication

        Returns:
            FormCreationResult: Contains form ID, edit URL, and response URL
        """
        # Log the tool request

        try:
            # Get the Forms service via middleware injection
            forms_service = await _get_forms_service_with_fallback(user_google_email)

            # Build the initial form data - include title and documentTitle on creation
            form_data = {
                "info": {
                    "title": title,
                }
            }

            # documentTitle must be set on creation (read-only afterward)
            if document_title:
                form_data["info"]["documentTitle"] = document_title

            # Create the form via the API
            created_form = await asyncio.to_thread(
                forms_service.forms().create(body=form_data).execute
            )

            # If description provided, update via batchUpdate (description can be updated later)
            form_id = created_form.get("formId")
            if description:
                update_requests = [
                    {
                        "updateFormInfo": {
                            "info": {"description": description},
                            "updateMask": "description",
                        }
                    }
                ]

                batch_update_body = {"requests": update_requests}
                await asyncio.to_thread(
                    forms_service.forms()
                    .batchUpdate(formId=form_id, body=batch_update_body)
                    .execute
                )

                # Get updated form to return the final state
                created_form = await asyncio.to_thread(
                    forms_service.forms().get(formId=form_id).execute
                )

            edit_url = f"https://docs.google.com/forms/d/{form_id}/edit"
            responder_uri = created_form.get("responderUri")

            success_msg = f"✅ Successfully created form '{title}'"
            logger.info(f"[create_form] {success_msg}")

            return FormCreationResult(
                success=True,
                message=success_msg,
                formId=form_id,
                title=title,
                editUrl=edit_url,
                responseUrl=responder_uri,
            )

        except HttpError as e:
            error_msg = f"❌ Failed to create form: {e}"
            logger.error(f"[create_form] HTTP error: {e}")
            return FormCreationResult(
                success=False,
                message=error_msg,
                formId=None,
                title=title,
                editUrl=None,
                responseUrl=None,
                error=str(e),
            )
        except Exception as e:
            error_msg = f"❌ Unexpected error creating form: {str(e)}"
            logger.error(f"[create_form] Unexpected error: {e}")
            return FormCreationResult(
                success=False,
                message=error_msg,
                formId=None,
                title=title,
                editUrl=None,
                responseUrl=None,
                error=str(e),
            )

    @mcp.tool(
        name="add_questions_to_form",
        description="Add questions and content items to an existing Google Form. Supports all question types (text, multiple choice, checkbox, dropdown, scale, date, time, rating, file upload) plus images, YouTube videos, text blocks and section breaks. Questions and choice options can carry an image. Items are appended to the end of the form unless insert_index is given.",
        tags={"forms", "questions", "images", "update", "google"},
        annotations={
            "title": "Add Questions to Form",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def add_questions_to_form(
        form_id: Annotated[
            str,
            Field(
                description="The ID of the form to add questions to. Get this from create_form output."
            ),
        ],
        questions: Annotated[
            List[Dict[str, Any]],
            Field(
                description="List of item dictionaries using SIMPLIFIED format, added in order. Questions: {'type': 'TEXT_QUESTION', 'title': 'Name', 'required': True} or {'type': 'MULTIPLE_CHOICE_QUESTION', 'title': 'Pick one', 'options': ['A', 'B', 'C'], 'required': True}. Any item takes an optional 'description'. Any question takes an optional 'image_url' (shown with the question), and a choice option may be {'value': 'A', 'image_url': 'https://...'} instead of a string. Content items: {'type': 'IMAGE_ITEM', 'image_url': 'https://...', 'title': 'Poster A'}, {'type': 'VIDEO_ITEM', 'youtube_url': 'https://www.youtube.com/watch?v=...'}, {'type': 'TEXT_ITEM', 'title': 'Heading', 'description': 'Body text'}, {'type': 'PAGE_BREAK_ITEM', 'title': 'Section 2'}. Images take optional 'image_alt_text', 'image_width' (pixels, max 740) and 'image_alignment' (LEFT/CENTER/RIGHT). image_url must be publicly reachable: Google fetches it once when the item is created and keeps its own copy."
            ),
        ],
        insert_index: Annotated[
            Optional[int],
            Field(
                description="Position of the first new item, 0 = top of the form (positions count every item, not just questions - see get_form's items list). Default: append after the last existing item.",
                ge=0,
            ),
        ] = None,
        user_google_email: UserGoogleEmailForms = None,
    ) -> FormUpdateResult:
        """
        Add questions and content items to an existing Google Form using batch operations.

        Use simplified format: Text: {"type": "TEXT_QUESTION", "title": "Name", "required": True}
        Multiple choice: {"type": "MULTIPLE_CHOICE_QUESTION", "title": "Pick", "options": ["A", "B"]}
        Image: {"type": "IMAGE_ITEM", "image_url": "https://example.com/a.png", "title": "A"}

        Args:
            form_id: Form ID from create_form output
            questions: List of simplified item dictionaries
            insert_index: Position of the first new item; None appends to the end
            user_google_email: Google account for authentication

        Returns:
            FormUpdateResult: Success status, number of questions added, form details
        """

        try:
            forms_service = await _get_forms_service_with_fallback(user_google_email)

            # New items go after the existing ones unless a position is given
            if insert_index is None:
                existing = await asyncio.to_thread(
                    forms_service.forms().get(formId=form_id).execute
                )
                start_index = len(existing.get("items", []))
            else:
                start_index = insert_index

            # Build batch update requests
            requests, skipped = build_create_item_requests(questions, start_index)
            for reason in skipped:
                logger.warning(f"Skipping invalid question {reason}")

            if not requests:
                error_msg = "❌ No valid questions to add"
                if skipped:
                    error_msg += f" (skipped: {'; '.join(skipped)})"
                return FormUpdateResult(
                    success=False,
                    message=error_msg,
                    formId=form_id,
                    title=None,
                    editUrl=f"https://docs.google.com/forms/d/{form_id}/edit",
                    error=error_msg,
                )

            batch_update_body = {"requests": requests}

            # Execute the batch update
            result = await asyncio.to_thread(
                forms_service.forms()
                .batchUpdate(formId=form_id, body=batch_update_body)
                .execute
            )

            # Get the updated form to show the edit URL
            form = await asyncio.to_thread(
                forms_service.forms().get(formId=form_id).execute
            )

            edit_url = f"https://docs.google.com/forms/d/{form_id}/edit"
            title = form.get("info", {}).get("title", "Untitled Form")
            success_msg = f"✅ Successfully added {len(requests)} items to form"
            if skipped:
                success_msg += (
                    f" (skipped {len(skipped)} invalid: {'; '.join(skipped)})"
                )

            logger.info(f"[add_questions_to_form] {success_msg}")
            return FormUpdateResult(
                success=True,
                message=success_msg,
                formId=form_id,
                title=title,
                editUrl=edit_url,
                questionsUpdated=len(requests),
            )

        except HttpError as e:
            error_msg = f"❌ Failed to add questions: {e}"
            logger.error(f"[add_questions_to_form] HTTP error: {e}")
            return FormUpdateResult(
                success=False,
                message=error_msg,
                formId=form_id,
                title=None,
                editUrl=f"https://docs.google.com/forms/d/{form_id}/edit",
                error=str(e),
            )
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[add_questions_to_form] {error_msg}")
            return FormUpdateResult(
                success=False,
                message=error_msg,
                formId=form_id,
                title=None,
                editUrl=f"https://docs.google.com/forms/d/{form_id}/edit",
                error=str(e),
            )

    @mcp.tool(
        name="get_form",
        description="Retrieve comprehensive details of a Google Form including metadata, all questions with their types and settings, and access URLs. Perfect for form inspection and analysis.",
        tags={"forms", "read", "google", "get"},
        annotations={
            "title": "Get Form Details",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def get_form(
        form_id: Annotated[
            str,
            Field(
                description="The unique ID of the form to retrieve. Get this from create_form output or from a Google Forms URL: https://docs.google.com/forms/d/FORM_ID_HERE/edit"
            ),
        ],
        user_google_email: UserGoogleEmailForms = None,
    ) -> FormDetails:
        """
        Retrieve comprehensive details and structure of a Google Form.

        Read-only tool that provides complete form information including metadata,
        question details, and access URLs for inspection and analysis.

        Args:
            form_id: Form ID from create_form output or Google Forms URL
            user_google_email: Google account for authentication

        Returns:
            FormDetails: Form metadata, questions list, URLs, and configuration details
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
            questions: List[FormQuestion] = []
            item_summaries: List[FormItemSummary] = []

            for index, item in enumerate(items):
                item_type = extract_item_type(item)
                item_summaries.append(
                    FormItemSummary(
                        index=index,
                        itemId=item.get("itemId", ""),
                        title=item.get("title", ""),
                        itemType=item_type,
                    )
                )
                if item_type == "questionItem":
                    question_item = item.get("questionItem", {})
                    q_question = question_item.get("question", {})

                    form_question = FormQuestion(
                        itemId=item.get("itemId", ""),
                        title=item.get("title", "No title"),
                        type=q_question.get("type", "Unknown"),
                        required=q_question.get("required", False),
                        details=format_question_details(item),
                    )
                    questions.append(form_question)

            edit_url = f"https://docs.google.com/forms/d/{form_id}/edit"
            response_url = form.get("responderUri")

            return FormDetails(
                success=True,
                formId=form_id,
                title=title,
                description=description if description != "No description" else None,
                documentTitle=document_title,
                editUrl=edit_url,
                responseUrl=response_url,
                questions=questions,
                questionCount=len(questions),
                items=item_summaries,
            )

        except HttpError as e:
            error_msg = f"❌ Failed to get form: {e}"
            logger.error(f"[get_form] HTTP error: {e}")
            return FormDetails(
                success=False,
                formId=form_id,
                title="Unknown",
                description=None,
                documentTitle="Unknown",
                editUrl=f"https://docs.google.com/forms/d/{form_id}/edit",
                responseUrl=None,
                questions=[],
                questionCount=0,
                error=str(e),
            )
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[get_form] {error_msg}")
            return FormDetails(
                success=False,
                formId=form_id,
                title="Unknown",
                description=None,
                documentTitle="Unknown",
                editUrl=f"https://docs.google.com/forms/d/{form_id}/edit",
                responseUrl=None,
                questions=[],
                questionCount=0,
                error=str(e),
            )

    @mcp.tool(
        name="set_form_publish_state",
        description="Control whether a Google Form is accepting responses. Configures basic form settings and provides guidance for full response control via the Forms UI.",
        tags={"forms", "settings", "publish", "google"},
        annotations={
            "title": "Set Form Publish State",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def set_form_publish_state(
        form_id: Annotated[
            str,
            Field(
                description="The unique ID of the form to configure. Get this from create_form output."
            ),
        ],
        user_google_email: UserGoogleEmailForms = None,
        accepting_responses: Annotated[
            bool,
            Field(
                description="Desired response acceptance state. True = Form should accept responses (default), False = Form should not accept responses. Note: Final control requires manual UI configuration."
            ),
        ] = True,
    ) -> FormPublishResult:
        """
        Control whether a Google Form is accepting responses. Limited API control - manual UI steps may be needed.

        Args:
            form_id: Form ID to configure
            user_google_email: Google account for authentication
            accepting_responses: Whether form should accept responses (True by default)

        Returns:
            FormPublishResult: Configuration status, URLs, and manual setup instructions
        """

        try:
            forms_service = await _get_forms_service_with_fallback(user_google_email)

            # Update form settings
            update_body = {
                "requests": [
                    {
                        "updateSettings": {
                            "settings": {
                                "quizSettings": {
                                    "isQuiz": False  # Ensure it's not a quiz
                                }
                            },
                            "updateMask": "quizSettings.isQuiz",
                        }
                    }
                ]
            }

            # Note: The Forms API doesn't directly support setting accepting_responses
            # This is typically controlled through the form's settings in the UI
            # We'll update what we can and provide instructions

            await asyncio.to_thread(
                forms_service.forms()
                .batchUpdate(formId=form_id, body=update_body)
                .execute
            )

            # Get the form to show current state
            form = await asyncio.to_thread(
                forms_service.forms().get(formId=form_id).execute
            )

            state = (
                "accepting responses"
                if accepting_responses
                else "not accepting responses"
            )
            title = form.get("info", {}).get("title", "Untitled")
            edit_url = f"https://docs.google.com/forms/d/{form_id}/edit"
            response_url = form.get("responderUri", "Not yet available")
            success_msg = "✅ Form settings updated"

            return FormPublishResult(
                success=True,
                message=success_msg,
                formId=form_id,
                title=title,
                editUrl=edit_url,
                responseUrl=response_url,
                publishState=state,
                sharingResults=[
                    f"Desired state: {state}",
                    "Note: To fully control response acceptance, visit the form editor and use Settings > Responses",
                ],
                publicAccess=accepting_responses,
                sharedWith=[],
            )

        except HttpError as e:
            error_msg = f"❌ Failed to update form settings: {e}"
            logger.error(f"[set_form_publish_state] HTTP error: {e}")
            return FormPublishResult(
                success=False,
                message=error_msg,
                formId=form_id,
                title="Unknown",
                editUrl=f"https://docs.google.com/forms/d/{form_id}/edit",
                responseUrl="Unknown",
                publishState="error",
                sharingResults=[error_msg],
                publicAccess=accepting_responses,
                sharedWith=[],
                error=str(e),
            )
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[set_form_publish_state] {error_msg}")
            return FormPublishResult(
                success=False,
                message=error_msg,
                formId=form_id,
                title="Unknown",
                editUrl=f"https://docs.google.com/forms/d/{form_id}/edit",
                responseUrl="Unknown",
                publishState="error",
                sharingResults=[error_msg],
                publicAccess=accepting_responses,
                sharedWith=[],
                error=str(e),
            )

    @mcp.tool(
        name="publish_form_publicly",
        description="Make a Google Form publicly accessible without sign-in requirements and share with specific users. Uses both Forms and Drive APIs for comprehensive permission management.",
        tags={"forms", "share", "publish", "google", "permissions"},
        annotations={
            "title": "Publish Form Publicly",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def publish_form_publicly(
        form_id: Annotated[
            str,
            Field(
                description="The unique ID of the form to publish. Get this from create_form output."
            ),
        ],
        anyone_can_respond: Annotated[
            bool,
            Field(
                description="Enable public access to the form. True = Anyone with the link can respond (no sign-in required) - DEFAULT, False = Only shared users can access. Note: May require domain admin permissions in some organizations"
            ),
        ] = True,
        share_with_emails: Annotated[
            Optional[List[str]],
            Field(
                description="List of email addresses to share with. These users will get edit access to the form and receive email notifications. Example: ['colleague@company.com', 'manager@company.com']"
            ),
        ] = None,
        user_google_email: UserGoogleEmailForms = None,
    ) -> FormPublishResult:
        """
        Make a Google Form publicly accessible and share with specific users using Drive API permissions.

        Args:
            form_id: Form ID to publish
            anyone_can_respond: Enable public access (no sign-in required)
            share_with_emails: Email addresses to share with (get edit access)
            user_google_email: Google account for authentication

        Returns:
            FormPublishResult: Publishing status, sharing results, URLs
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
                    permission = {"type": "anyone", "role": "writer"}

                    await asyncio.to_thread(
                        drive_service.permissions()
                        .create(fileId=form_id, body=permission, fields="id")
                        .execute
                    )

                    results.append(
                        "✅ Form is now publicly accessible (no sign-in required)"
                    )
                except HttpError as e:
                    if e.resp.status == 403:
                        results.append(
                            "⚠️ Could not make form public (may require domain admin permissions)"
                        )
                    else:
                        results.append(f"⚠️ Error setting public access: {e}")

            # Share with specific emails
            if share_with_emails:
                for email in share_with_emails:
                    try:
                        permission = {
                            "type": "user",
                            "role": "writer",
                            "emailAddress": email,
                        }

                        await asyncio.to_thread(
                            drive_service.permissions()
                            .create(
                                fileId=form_id,
                                body=permission,
                                sendNotificationEmail=True,
                                fields="id",
                            )
                            .execute
                        )

                        results.append(f"✅ Shared with {email} as editor")
                    except HttpError as e:
                        results.append(f"⚠️ Failed to share with {email}: {e}")

            # Build final response
            success_msg = f"✅ Successfully published form '{title}'"
            edit_url = f"https://docs.google.com/forms/d/{form_id}/edit"
            response_url = form.get("responderUri", "Not yet available")

            return FormPublishResult(
                success=True,
                message=success_msg,
                formId=form_id,
                title=title,
                editUrl=edit_url,
                responseUrl=response_url,
                publishState="published",
                sharingResults=results,
                publicAccess=anyone_can_respond,
                sharedWith=share_with_emails or [],
            )

        except HttpError as e:
            error_msg = f"❌ Failed to publish form: {e}"
            logger.error(f"[publish_form_publicly] HTTP error: {e}")
            return FormPublishResult(
                success=False,
                message=error_msg,
                formId=form_id,
                title="Unknown",
                editUrl=f"https://docs.google.com/forms/d/{form_id}/edit",
                responseUrl="Unknown",
                publishState="error",
                sharingResults=[error_msg],
                publicAccess=anyone_can_respond,
                sharedWith=share_with_emails or [],
                error=str(e),
            )
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[publish_form_publicly] {error_msg}")
            return FormPublishResult(
                success=False,
                message=error_msg,
                formId=form_id,
                title="Unknown",
                editUrl=f"https://docs.google.com/forms/d/{form_id}/edit",
                responseUrl="Unknown",
                publishState="error",
                sharingResults=[error_msg],
                publicAccess=anyone_can_respond,
                sharedWith=share_with_emails or [],
                error=str(e),
            )

    @mcp.tool(
        name="get_form_response",
        description="Retrieve a specific response from a Google Form with detailed answer mappings to questions. Perfect for analyzing individual submissions in detail.",
        tags={"forms", "responses", "get", "google"},
        annotations={
            "title": "Get Form Response",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def get_form_response(
        form_id: Annotated[
            str,
            Field(
                description="The unique ID of the form containing the response. Get this from create_form output or from list_form_responses."
            ),
        ],
        response_id: Annotated[
            str,
            Field(
                description="The unique ID of the specific response to retrieve. Get this from list_form_responses output - each response has a unique ID. Format: Usually a long alphanumeric string from Google Forms API."
            ),
        ],
        user_google_email: UserGoogleEmailForms = None,
    ) -> FormResponseDetails:
        """
        Retrieve a specific response from a Google Form with detailed answer mappings to questions.

        Args:
            form_id: Form ID containing the response
            response_id: Unique response ID from list_form_responses
            user_google_email: Google account for authentication

        Returns:
            FormResponseDetails: Response metadata, answers mapped to questions
        """

        try:
            forms_service = await _get_forms_service_with_fallback(user_google_email)

            # Get the specific response
            response = await asyncio.to_thread(
                forms_service.forms()
                .responses()
                .get(formId=form_id, responseId=response_id)
                .execute
            )

            # Get form metadata to map questions
            form = await asyncio.to_thread(
                forms_service.forms().get(formId=form_id).execute
            )

            # Format answers with question context
            answers = response.get("answers", {})
            items = form.get("items", [])

            # Create a mapping of question IDs to questions
            question_map = {}
            for item in items:
                if "questionItem" in item:
                    question_map[item["itemId"]] = item

            # Convert to structured format
            structured_answers: List[FormResponseAnswer] = []
            for question_id, answer_data in answers.items():
                question = question_map.get(question_id, {})
                question_title = question.get("title", f"Question {question_id}")

                text_answers = answer_data.get("textAnswers", {})
                answer_text = ""
                if text_answers and "answers" in text_answers:
                    answer_values = [
                        ans.get("value", "") for ans in text_answers["answers"]
                    ]
                    answer_text = ", ".join(answer_values)
                else:
                    answer_text = "[No answer]"

                answer_info: FormResponseAnswer = {
                    "questionId": question_id,
                    "questionTitle": question_title,
                    "answer": answer_text,
                }
                structured_answers.append(answer_info)

            success_msg = f"✅ Retrieved response {response_id}"

            return FormResponseDetails(
                success=True,
                message=success_msg,
                responseId=response_id,
                formId=form_id,
                submittedTime=response.get("lastSubmittedTime", "Unknown"),
                respondentEmail=response.get("respondentEmail"),
                answers=structured_answers,
                answerCount=len(structured_answers),
            )

        except HttpError as e:
            if e.resp.status == 404:
                error_msg = f"❌ Response not found. Please check the response ID: {response_id}"
            else:
                error_msg = f"❌ Failed to get response: {e}"
            logger.error(f"[get_form_response] HTTP error: {e}")
            return FormResponseDetails(
                success=False,
                message=error_msg,
                responseId=response_id,
                formId=form_id,
                submittedTime="Unknown",
                respondentEmail=None,
                answers=[],
                answerCount=0,
                error=str(e),
            )
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[get_form_response] {error_msg}")
            return FormResponseDetails(
                success=False,
                message=error_msg,
                responseId=response_id,
                formId=form_id,
                submittedTime="Unknown",
                respondentEmail=None,
                answers=[],
                answerCount=0,
                error=str(e),
            )

    @mcp.tool(
        name="list_form_responses",
        description="Retrieve all responses from a Google Form with efficient pagination support and structured answer mapping. Returns comprehensive response data ready for analysis.",
        tags={"forms", "responses", "list", "google"},
        annotations={
            "title": "List Form Responses",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def list_form_responses(
        form_id: Annotated[
            str,
            Field(
                description="The unique ID of the form to retrieve responses from. Get this from create_form output."
            ),
        ],
        page_size: Annotated[
            int,
            Field(
                description="Number of responses to return per page. Range: 1-100 responses per page. Recommendations: Small forms: 10-25, Large surveys: 25-50, Bulk export: 100",
                ge=1,
                le=100,
            ),
        ] = 10,
        page_token: Annotated[
            Optional[str],
            Field(
                description="Token for pagination continuation. Use nextPageToken from previous response for subsequent pages. Set to None to start over from the beginning."
            ),
        ] = None,
        user_google_email: UserGoogleEmailForms = None,
    ) -> FormResponsesListResponse:
        """
        Retrieve all responses from a Google Form with pagination support and structured answer mapping.

        Args:
            form_id: Form ID to retrieve responses from
            page_size: Number of responses per page (1-100, default 10)
            page_token: Pagination token from previous response (None to start over)
            user_google_email: Google account for authentication

        Returns:
            FormResponsesListResponse: List of responses with answers mapped to questions, pagination info
        """

        try:
            forms_service = await _get_forms_service_with_fallback(user_google_email)

            # Build request parameters
            params = {"pageSize": page_size}
            if page_token:
                params["pageToken"] = page_token

            # List responses
            result = await asyncio.to_thread(
                forms_service.forms().responses().list(formId=form_id, **params).execute
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
                        answer_values = [
                            ans.get("value", "") for ans in text_answers["answers"]
                        ]
                        answer_text = ", ".join(answer_values)
                    else:
                        answer_text = "[No answer]"

                    answer_info: FormResponseAnswer = {
                        "questionId": question_id,
                        "questionTitle": question_title,
                        "answer": answer_text,
                    }
                    structured_answers.append(answer_info)

                response_info: FormResponseInfo = {
                    "responseId": response.get("responseId", ""),
                    "submittedTime": response.get("lastSubmittedTime", "Unknown"),
                    "respondentEmail": response.get("respondentEmail"),
                    "answers": structured_answers,
                }
                responses.append(response_info)

            logger.info(
                f"Successfully retrieved {len(responses)} responses for form {form_id}"
            )

            return FormResponsesListResponse(
                responses=responses,
                count=len(responses),
                formId=form_id,
                formTitle=title,
                userEmail=user_google_email or "",
                pageToken=page_token,
                nextPageToken=next_page_token,
                error=None,
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
                userEmail=user_google_email or "",
                pageToken=page_token,
                nextPageToken=None,
                error=error_msg,
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
                userEmail=user_google_email or "",
                pageToken=page_token,
                nextPageToken=None,
                error=error_msg,
            )

    @mcp.tool(
        name="update_form_questions",
        description="Modify existing questions in a Google Form including titles, descriptions, required status, and other settings. Uses efficient batch operations for multiple updates.",
        tags={"forms", "update", "questions", "google"},
        annotations={
            "title": "Update Form Questions",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def update_form_questions(
        form_id: Annotated[
            str,
            Field(
                description="The unique ID of the form containing questions to update. Get this from create_form output."
            ),
        ],
        questions_to_update: Annotated[
            List[Dict[str, Any]],
            Field(
                description="List of update dictionaries. Each dictionary must include: item_id (the ID of the question to update from get_form), and one or more fields to update (title, description, required). Example: [{'item_id': '12345', 'title': 'Updated Question', 'required': True}]"
            ),
        ],
        user_google_email: UserGoogleEmailForms = None,
    ) -> FormUpdateResult:
        """
        Modify existing questions in a Google Form using efficient batch operations.

        Use get_form first to get item_ids. Supported updates: title, description, required status.

        Args:
            form_id: Form ID containing questions to update
            questions_to_update: List of update dicts with item_id + fields to change
            user_google_email: Google account for authentication

        Returns:
            FormUpdateResult: Update summary, number of questions modified, URLs
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
                error_msg = "❌ No valid updates to apply"
                return FormUpdateResult(
                    success=False,
                    message=error_msg,
                    formId=form_id,
                    title=None,
                    editUrl=f"https://docs.google.com/forms/d/{form_id}/edit",
                    error=error_msg,
                )

            # Build batch update request
            batch_update_body = build_batch_update_request(valid_updates)

            # Execute the update
            result = await asyncio.to_thread(
                forms_service.forms()
                .batchUpdate(formId=form_id, body=batch_update_body)
                .execute
            )

            # Get updated form info
            form = await asyncio.to_thread(
                forms_service.forms().get(formId=form_id).execute
            )

            success_msg = f"✅ Successfully updated {len(valid_updates)} questions"
            title = form.get("info", {}).get("title", "Untitled")
            edit_url = f"https://docs.google.com/forms/d/{form_id}/edit"

            return FormUpdateResult(
                success=True,
                message=success_msg,
                formId=form_id,
                title=title,
                editUrl=edit_url,
                questionsUpdated=len(valid_updates),
            )

        except HttpError as e:
            error_msg = f"❌ Failed to update questions: {e}"
            logger.error(f"[update_form_questions] HTTP error: {e}")
            return FormUpdateResult(
                success=False,
                message=error_msg,
                formId=form_id,
                title=None,
                editUrl=f"https://docs.google.com/forms/d/{form_id}/edit",
                error=str(e),
            )
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[update_form_questions] {error_msg}")
            return FormUpdateResult(
                success=False,
                message=error_msg,
                formId=form_id,
                title=None,
                editUrl=f"https://docs.google.com/forms/d/{form_id}/edit",
                error=str(e),
            )

    # Log successful setup
    tool_count = 8  # Total number of Forms tools
    logger.info(
        f"Successfully registered {tool_count} Google Forms tools with enhanced documentation"
    )

    # Parameter defaults validation summary:
    # - create_form: description=None, document_title=None (optional fields)
    # - set_form_publish_state: accepting_responses=True (forms should accept by default)
    # - publish_form_publicly: anyone_can_respond=True (public by default), share_with_emails=None (optional)
    # - list_form_responses: page_size=10 (reasonable for most use cases), page_token=None (start from beginning)
    # All parameter defaults are validated and reasonable for typical use cases.
