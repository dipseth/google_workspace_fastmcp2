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
- update_form_questions: Modifies, reorders and deletes existing items
- update_form_settings: Title, description, quiz mode, email collection

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

- GRID_QUESTION: Rows x columns grid (rows, columns, multiple=True for checkboxes)
Choice options can branch the form (go_to_action / go_to_section_id) and
multiple choice / checkbox questions can carry an "Other" option ({"is_other": True}).

FORMATTING AND THEMING LIMITS (Forms API v1):
The API has no theme, colour, font, header-image or rich-text fields. Titles and
descriptions are plain text - HTML and Markdown are shown literally. What the API
does control: images and videos (width, alignment), sections, item order, quiz
and email-collection settings. For a styled form, theme a form once in the
editor and pass it as create_form's template_form_id: the Drive copy keeps the
theme colour, header image and fonts.
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

# Choice option branching (radio and dropdown questions only)
GO_TO_ACTIONS = {"NEXT_SECTION", "RESTART_FORM", "SUBMIT_FORM"}
BRANCHING_CHOICE_KINDS = {"RADIO", "DROP_DOWN"}

RATING_ICON_TYPES = {"STAR", "HEART", "THUMB_UP"}

EMAIL_COLLECTION_TYPES = {"DO_NOT_COLLECT", "VERIFIED", "RESPONDER_INPUT"}

# Valid update fields for validation
VALID_UPDATE_FIELDS = {
    "title",
    "description",
    "required",
    "options",
    "shuffle",
    "image_url",
    "image_alt_text",
    "image_width",
    "image_alignment",
    "move_to_index",
    "delete",
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
    "fileUploadQuestion": "FILE_UPLOAD",
}

CHOICE_KIND_LABELS = {"RADIO": "Radio", "CHECKBOX": "Checkbox", "DROP_DOWN": "Dropdown"}

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

    # The API's Question has no "type" field; the kind is whichever
    # *Question key is present.
    q_type = extract_question_type(question)
    q_text = question.get("title", "No title")
    q_id = question.get("itemId", "No ID")
    required = q_question.get("required", False)

    # Extract additional details based on question type
    details = []

    if q_type == "MULTIPLE_CHOICE":
        choice_q = q_question.get("choiceQuestion", {})
        options = choice_q.get("options", [])
        kind = choice_q.get("type", "")
        details.append(f"Kind: {CHOICE_KIND_LABELS.get(kind, kind or 'Unknown')}")
        details.append(
            "Options: " + ", ".join(str(o.get("value", "")) for o in options)
            if options
            else "Options: none"
        )
        with_image = sum(1 for o in options if "image" in o)
        if with_image:
            details.append(f"Option images: {with_image}")
        if choice_q.get("shuffle"):
            details.append("Shuffled: Yes")
    elif q_type == "SCALE":
        scale_q = q_question.get("scaleQuestion", {})
        details.append(f"Scale: {scale_q.get('low', 1)} to {scale_q.get('high', 5)}")
    elif q_type == "TEXT":
        text_q = q_question.get("textQuestion", {})
        details.append(f"Paragraph: {'Yes' if text_q.get('paragraph') else 'No'}")

    if "image" in question_item:
        details.append("Image: Yes")

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
    elif q_type == "GRID_QUESTION":
        return (
            "title" in question
            and bool(question.get("rows"))
            and bool(question.get("columns"))
        )

    return False


def build_media_properties(source: Dict[str, Any], prefix: str) -> Dict[str, Any]:
    """Build Forms API MediaProperties from `<prefix>_width` / `<prefix>_alignment`."""
    properties: Dict[str, Any] = {}
    if f"{prefix}_width" in source:
        properties["width"] = source[f"{prefix}_width"]
    if f"{prefix}_alignment" in source:
        alignment = str(source[f"{prefix}_alignment"]).upper()
        if alignment not in IMAGE_ALIGNMENTS:
            raise ValueError(
                f"{prefix}_alignment must be one of {sorted(IMAGE_ALIGNMENTS)}: {alignment!r}"
            )
        properties["alignment"] = alignment
    return properties


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

    properties = build_media_properties(source, "image")
    if properties:
        image["properties"] = properties

    return image


def build_choice_options(
    options: List[Any], choice_kind: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Build Forms API choice options.

    Each option is either a plain string or a dict with `value` and optional
    image_* keys (see build_image) to show a picture beside the option. A dict
    may also branch the form - `go_to_action` (NEXT_SECTION / RESTART_FORM /
    SUBMIT_FORM) or `go_to_section_id` (the itemId of a PAGE_BREAK_ITEM) - or be
    the free-text "Other" option ({"is_other": True}, no value).

    Args:
        options: Simplified options
        choice_kind: The question's API kind (RADIO / CHECKBOX / DROP_DOWN), used
            to reject fields the kind does not support; None skips that check
    """
    built = []
    for opt in options:
        if isinstance(opt, dict):
            if opt.get("is_other"):
                if choice_kind == "DROP_DOWN":
                    raise ValueError("Dropdown questions cannot have an 'Other' option")
                option: Dict[str, Any] = {"isOther": True}
            elif "value" not in opt:
                raise ValueError(f"Choice option is missing 'value': {opt}")
            else:
                option = {"value": opt["value"]}
            if "image_url" in opt:
                option["image"] = build_image(opt)
            if "go_to_action" in opt and "go_to_section_id" in opt:
                raise ValueError(
                    f"Use go_to_action or go_to_section_id, not both: {opt}"
                )
            if "go_to_action" in opt or "go_to_section_id" in opt:
                if (
                    choice_kind is not None
                    and choice_kind not in BRANCHING_CHOICE_KINDS
                ):
                    raise ValueError(
                        "Branching only applies to multiple choice and dropdown questions"
                    )
            if "go_to_action" in opt:
                action = str(opt["go_to_action"]).upper()
                if action not in GO_TO_ACTIONS:
                    raise ValueError(
                        f"go_to_action must be one of {sorted(GO_TO_ACTIONS)}: {action!r}"
                    )
                option["goToAction"] = action
            if "go_to_section_id" in opt:
                option["goToSectionId"] = opt["go_to_section_id"]
            built.append(option)
        else:
            built.append({"value": opt})
    return built


def build_grid_item(question: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a questionGroupItem grid: one row question per entry in `rows`, all
    sharing the `columns` choices. `multiple` makes it a checkbox grid.
    """
    rows = question["rows"]
    columns = question["columns"]
    if not all(isinstance(value, str) and value for value in [*rows, *columns]):
        raise ValueError("GRID_QUESTION rows and columns must be non-empty strings")

    required = question.get("required", False)
    grid: Dict[str, Any] = {
        "columns": {
            "type": "CHECKBOX" if question.get("multiple") else "RADIO",
            "options": [{"value": column} for column in columns],
        }
    }
    if question.get("shuffle_rows"):
        grid["shuffleQuestions"] = True

    return {
        "questions": [
            {"required": required, "rowQuestion": {"title": row}} for row in rows
        ],
        "grid": grid,
    }


def build_question_item(question: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a Forms API item from a simplified item dict.

    Handles questions and the non-question items (IMAGE_ITEM, VIDEO_ITEM,
    TEXT_ITEM, PAGE_BREAK_ITEM) and GRID_QUESTION.

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
        properties = build_media_properties(question, "video")
        if properties:
            item["videoItem"]["video"]["properties"] = properties
        if "caption" in question:
            item["videoItem"]["caption"] = question["caption"]
        return item
    elif q_type == "TEXT_ITEM":
        item["textItem"] = {}
        return item
    elif q_type == "PAGE_BREAK_ITEM":
        item["pageBreakItem"] = {}
        return item
    elif q_type == "GRID_QUESTION":
        item["questionGroupItem"] = build_grid_item(question)
        if "image_url" in question:
            item["questionGroupItem"]["image"] = build_image(question)
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
            "options": build_choice_options(options, CHOICE_QUESTION_TYPES[q_type]),
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
        icon_type = str(question.get("icon_type", "STAR")).upper()
        if icon_type not in RATING_ICON_TYPES:
            raise ValueError(
                f"icon_type must be one of {sorted(RATING_ICON_TYPES)}: {icon_type!r}"
            )
        q_obj["ratingQuestion"] = {
            "ratingScaleLevel": question["rating_scale_level"],
            "iconType": icon_type,
        }

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


def build_batch_update_request(
    updates: List[Dict[str, Any]], items: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Build a batch update request from a list of updates.

    The Forms API addresses items by index, so each update's item_id is resolved
    against the form's current items. All fields for one item go into a single
    updateItem. Moves run after the updates, in the order given, each against the
    order the previous moves left behind. Deletes run last, highest index first,
    so earlier indexes stay valid within the batch.

    Args:
        updates: List of update dictionaries (item_id plus fields to change)
        items: The form's current items, in order (from forms.get)

    Returns:
        Batch update request body

    Raises:
        ValueError: If an item_id is unknown or a field does not fit the item type
    """
    index_by_id = {item.get("itemId"): idx for idx, item in enumerate(items)}
    update_requests: List[Dict[str, Any]] = []
    moves: List[Tuple[str, int]] = []
    delete_ids: List[str] = []

    for update in updates:
        item_id = update.get("item_id")
        if not item_id:
            continue
        if item_id not in index_by_id:
            raise ValueError(f"item_id not found in form: {item_id!r}")
        index = index_by_id[item_id]
        existing = items[index]

        if update.get("delete"):
            delete_ids.append(item_id)
            continue

        if "move_to_index" in update:
            new_index = update["move_to_index"]
            if (
                not isinstance(new_index, int)
                or isinstance(new_index, bool)
                or not 0 <= new_index < len(items)
            ):
                raise ValueError(
                    f"move_to_index must be between 0 and {len(items) - 1}: {new_index!r}"
                )
            moves.append((item_id, new_index))

        item: Dict[str, Any] = {"itemId": item_id}
        mask: List[str] = []

        if "title" in update:
            item["title"] = update["title"]
            mask.append("title")

        if "description" in update:
            item["description"] = update["description"]
            mask.append("description")

        question_fields = {"required", "options", "shuffle"} & set(update)
        if question_fields and "questionItem" not in existing:
            raise ValueError(
                f"{sorted(question_fields)} only apply to questions: {item_id!r}"
            )

        if "required" in update:
            question = item.setdefault("questionItem", {}).setdefault("question", {})
            question["required"] = update["required"]
            mask.append("questionItem.question.required")

        if "options" in update or "shuffle" in update:
            existing_choice = (
                existing["questionItem"].get("question", {}).get("choiceQuestion")
            )
            if not existing_choice:
                raise ValueError(
                    f"options/shuffle only apply to choice questions: {item_id!r}"
                )
            question = item.setdefault("questionItem", {}).setdefault("question", {})
            choice = question.setdefault(
                "choiceQuestion", {"type": existing_choice.get("type", "RADIO")}
            )
            if "options" in update:
                choice["options"] = build_choice_options(
                    update["options"], choice["type"]
                )
                mask.append("questionItem.question.choiceQuestion.options")
            if "shuffle" in update:
                choice["shuffle"] = update["shuffle"]
                mask.append("questionItem.question.choiceQuestion.shuffle")

        if "image_url" in update:
            if "questionItem" in existing:
                item.setdefault("questionItem", {})["image"] = build_image(update)
                mask.append("questionItem.image")
            elif "imageItem" in existing:
                item["imageItem"] = {"image": build_image(update)}
                mask.append("imageItem.image")
            else:
                raise ValueError(
                    f"image_url only applies to questions and image items: {item_id!r}"
                )

        if mask:
            update_requests.append(
                {
                    "updateItem": {
                        "item": item,
                        "location": {"index": index},
                        "updateMask": ",".join(mask),
                    }
                }
            )

    order = [item.get("itemId") for item in items]
    move_requests: List[Dict[str, Any]] = []
    for item_id, new_index in moves:
        current_index = order.index(item_id)
        if current_index == new_index:
            continue
        order.insert(new_index, order.pop(current_index))
        move_requests.append(
            {
                "moveItem": {
                    "originalLocation": {"index": current_index},
                    "newLocation": {"index": new_index},
                }
            }
        )

    delete_requests = [
        {"deleteItem": {"location": {"index": index}}}
        for index in sorted({order.index(i) for i in delete_ids}, reverse=True)
    ]

    return {"requests": update_requests + move_requests + delete_requests}


def build_settings_requests(
    title: Optional[str] = None,
    description: Optional[str] = None,
    is_quiz: Optional[bool] = None,
    email_collection_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Build updateFormInfo / updateSettings requests for the fields that are set.

    Returns:
        batchUpdate requests (empty when nothing was given)
    """
    requests: List[Dict[str, Any]] = []

    info: Dict[str, Any] = {}
    if title is not None:
        info["title"] = title
    if description is not None:
        info["description"] = description
    if info:
        requests.append(
            {"updateFormInfo": {"info": info, "updateMask": ",".join(info)}}
        )

    settings: Dict[str, Any] = {}
    mask: List[str] = []
    if is_quiz is not None:
        settings["quizSettings"] = {"isQuiz": is_quiz}
        mask.append("quizSettings.isQuiz")
    if email_collection_type is not None:
        collection = str(email_collection_type).upper()
        if collection not in EMAIL_COLLECTION_TYPES:
            raise ValueError(
                f"email_collection_type must be one of {sorted(EMAIL_COLLECTION_TYPES)}: {collection!r}"
            )
        settings["emailCollectionType"] = collection
        mask.append("emailCollectionType")
    if settings:
        requests.append(
            {"updateSettings": {"settings": settings, "updateMask": ",".join(mask)}}
        )

    return requests


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
        description="Create a new Google Form with customizable title, description, and document title. Returns form ID and URLs for editing and responses. The Forms API cannot set theme colour, fonts or a header image: to get a styled form, pass template_form_id (a form already themed in the editor) and the copy keeps its look.",
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
        template_form_id: Annotated[
            Optional[str],
            Field(
                description="ID of an existing form to copy instead of starting blank. The copy keeps the template's theme colour, header image, fonts AND its items - the only way to get a themed form, since the Forms API has no theme fields. Use update_form_questions to delete template items you don't want."
            ),
        ] = None,
        user_google_email: UserGoogleEmailForms = None,
    ) -> FormCreationResult:
        """
        Create a new Google Form with customizable title, description, and document title.

        Args:
            title: Form title displayed at the top
            description: Optional description explaining the form's purpose
            document_title: Title shown in browser tab (defaults to main title)
            template_form_id: Existing form to copy (keeps its theme and items)
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

            if template_form_id:
                # A Drive copy is the only way to carry a theme over; the copy's
                # file name is its documentTitle, the form title is set below.
                drive_service = await _get_drive_service_with_fallback(
                    user_google_email
                )
                copied = await asyncio.to_thread(
                    drive_service.files()
                    .copy(
                        fileId=template_form_id,
                        body={"name": document_title or title},
                        fields="id",
                        supportsAllDrives=True,
                    )
                    .execute
                )
                created_form = {"formId": copied["id"]}
                update_requests = build_settings_requests(
                    title=title, description=description
                )
            else:
                # Create the form via the API
                created_form = await asyncio.to_thread(
                    forms_service.forms().create(body=form_data).execute
                )
                # description can only be set after creation
                update_requests = build_settings_requests(description=description)

            form_id = created_form.get("formId")
            if update_requests:
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
        description="Add questions and content items to an existing Google Form. Supports all question types (text, multiple choice, checkbox, dropdown, scale, date, time, rating, grid, file upload) plus images, YouTube videos, text blocks and section breaks. Questions and choice options can carry an image, and multiple choice / dropdown options can branch to a section. Text is plain: the Forms API renders no HTML, Markdown, colours or fonts. Items are appended to the end of the form unless insert_index is given.",
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
                description="List of item dictionaries using SIMPLIFIED format, added in order. Questions: {'type': 'TEXT_QUESTION', 'title': 'Name', 'required': True} or {'type': 'MULTIPLE_CHOICE_QUESTION', 'title': 'Pick one', 'options': ['A', 'B', 'C'], 'required': True}. Any item takes an optional 'description'. Any question takes an optional 'image_url' (shown with the question), and a choice option may be {'value': 'A', 'image_url': 'https://...'} instead of a string. Content items: {'type': 'IMAGE_ITEM', 'image_url': 'https://...', 'title': 'Poster A'}, {'type': 'VIDEO_ITEM', 'youtube_url': 'https://www.youtube.com/watch?v=...'}, {'type': 'TEXT_ITEM', 'title': 'Heading', 'description': 'Body text'}, {'type': 'PAGE_BREAK_ITEM', 'title': 'Section 2'}. Grid: {'type': 'GRID_QUESTION', 'title': 'Rate each', 'rows': ['Speed', 'Price'], 'columns': ['Bad', 'OK', 'Good'], 'multiple': False, 'shuffle_rows': False, 'required': True}. Rating: {'type': 'RATING_QUESTION', 'title': 'Stars', 'rating_scale_level': 5, 'icon_type': 'STAR'} (STAR/HEART/THUMB_UP). Branching (MULTIPLE_CHOICE_QUESTION and DROPDOWN_QUESTION only): an option may be {'value': 'No', 'go_to_action': 'SUBMIT_FORM'} (NEXT_SECTION/RESTART_FORM/SUBMIT_FORM) or {'value': 'Yes', 'go_to_section_id': '<itemId of a PAGE_BREAK_ITEM from get_form>'} - add the sections first, then set the options with update_form_questions. {'is_other': True} adds a free-text 'Other' option (not for dropdowns). Videos take optional 'video_width' and 'video_alignment'. Images take optional 'image_alt_text', 'image_width' (pixels, max 740) and 'image_alignment' (LEFT/CENTER/RIGHT). image_url must be publicly reachable: Google fetches it once when the item is created and keeps its own copy."
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
                        type=extract_question_type(item),
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
        description="Open or close a Google Form to responses (forms.setPublishSettings). The form stays published either way; closing it shows responders a 'no longer accepting responses' page. Forms created before Google's publish-settings rollout reject this call and must be toggled in the editor.",
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
                description="True = accept responses (default), False = close the form to new responses."
            ),
        ] = True,
    ) -> FormPublishResult:
        """
        Open or close a Google Form to responses via forms.setPublishSettings.

        Args:
            form_id: Form ID to configure
            user_google_email: Google account for authentication
            accepting_responses: Whether form should accept responses (True by default)

        Returns:
            FormPublishResult: Resulting publish state and URLs
        """

        try:
            forms_service = await _get_forms_service_with_fallback(user_google_email)

            publish_body = {
                "publishSettings": {
                    "publishState": {
                        "isPublished": True,
                        "isAcceptingResponses": accepting_responses,
                    }
                },
                "updateMask": "publishState",
            }
            await asyncio.to_thread(
                forms_service.forms()
                .setPublishSettings(formId=form_id, body=publish_body)
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
            success_msg = f"✅ Form is now {state}"

            return FormPublishResult(
                success=True,
                message=success_msg,
                formId=form_id,
                title=title,
                editUrl=edit_url,
                responseUrl=response_url,
                publishState=state,
                sharingResults=[f"Publish state: {state}"],
                publicAccess=accepting_responses,
                sharedWith=[],
            )

        except HttpError as e:
            error_msg = (
                f"❌ Failed to set publish state: {e}. Forms created before Google's "
                "publish-settings rollout reject this call - toggle 'Accepting "
                "responses' in the editor's Responses tab instead."
            )
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
        description="Let anyone with the link respond to a Google Form without signing in (responder-only access to the published form; the editor stays private), publish it, and optionally share edit access with specific users.",
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
                    # Responder access is a reader permission on the *published*
                    # view; any other anyone-permission would expose the editor.
                    permission = {
                        "type": "anyone",
                        "role": "reader",
                        "view": "published",
                    }

                    await asyncio.to_thread(
                        drive_service.permissions()
                        .create(fileId=form_id, body=permission, fields="id")
                        .execute
                    )

                    # Copies and newer forms start unpublished
                    await asyncio.to_thread(
                        forms_service.forms()
                        .setPublishSettings(
                            formId=form_id,
                            body={
                                "publishSettings": {
                                    "publishState": {
                                        "isPublished": True,
                                        "isAcceptingResponses": True,
                                    }
                                },
                                "updateMask": "publishState",
                            },
                        )
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
        name="update_form_settings",
        description="Change a Google Form's title, description, quiz mode and email collection. Only the fields you pass are changed. The Forms API has no theme, colour, font or header-image settings - those are editor-only (see create_form's template_form_id).",
        tags={"forms", "settings", "update", "google"},
        annotations={
            "title": "Update Form Settings",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def update_form_settings(
        form_id: Annotated[
            str,
            Field(description="The unique ID of the form to configure."),
        ],
        title: Annotated[
            Optional[str], Field(description="New form title (plain text).")
        ] = None,
        description: Annotated[
            Optional[str],
            Field(description="New form description (plain text; '' clears it)."),
        ] = None,
        is_quiz: Annotated[
            Optional[bool],
            Field(
                description="True makes the form a quiz (enables points/correct_answers on questions). Turning it off drops existing grading."
            ),
        ] = None,
        email_collection_type: Annotated[
            Optional[str],
            Field(
                description="DO_NOT_COLLECT, VERIFIED (responder's signed-in Google account) or RESPONDER_INPUT (responder types an address)."
            ),
        ] = None,
        user_google_email: UserGoogleEmailForms = None,
    ) -> FormUpdateResult:
        """
        Change a form's title, description, quiz mode and email collection.

        Args:
            form_id: Form ID to configure
            title: New form title
            description: New form description
            is_quiz: Whether the form is a quiz
            email_collection_type: DO_NOT_COLLECT / VERIFIED / RESPONDER_INPUT
            user_google_email: Google account for authentication

        Returns:
            FormUpdateResult: Success status and form URLs
        """
        edit_url = f"https://docs.google.com/forms/d/{form_id}/edit"

        try:
            requests = build_settings_requests(
                title=title,
                description=description,
                is_quiz=is_quiz,
                email_collection_type=email_collection_type,
            )
            if not requests:
                error_msg = "❌ No settings given to change"
                return FormUpdateResult(
                    success=False,
                    message=error_msg,
                    formId=form_id,
                    title=None,
                    editUrl=edit_url,
                    error=error_msg,
                )

            forms_service = await _get_forms_service_with_fallback(user_google_email)
            result = await asyncio.to_thread(
                forms_service.forms()
                .batchUpdate(
                    formId=form_id,
                    body={"requests": requests, "includeFormInResponse": True},
                )
                .execute
            )

            changed = [
                name
                for name, value in {
                    "title": title,
                    "description": description,
                    "is_quiz": is_quiz,
                    "email_collection_type": email_collection_type,
                }.items()
                if value is not None
            ]
            return FormUpdateResult(
                success=True,
                message=f"✅ Updated form settings: {', '.join(changed)}",
                formId=form_id,
                title=result.get("form", {}).get("info", {}).get("title"),
                editUrl=edit_url,
            )

        except HttpError as e:
            error_msg = f"❌ Failed to update form settings: {e}"
            logger.error(f"[update_form_settings] HTTP error: {e}")
            return FormUpdateResult(
                success=False,
                message=error_msg,
                formId=form_id,
                title=None,
                editUrl=edit_url,
                error=str(e),
            )
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[update_form_settings] {error_msg}")
            return FormUpdateResult(
                success=False,
                message=error_msg,
                formId=form_id,
                title=None,
                editUrl=edit_url,
                error=str(e),
            )

    @mcp.tool(
        name="update_form_questions",
        description="Modify or delete existing items in a Google Form: titles, descriptions, required status, choice options (with optional per-option images), question/image-item images, option branching, item reordering, and item deletion. Uses one batch operation for all updates.",
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
                description="List of update dictionaries. Each must include item_id (from get_form) and one or more of: 'title', 'description', 'required' (questions), 'options' (choice questions; REPLACES the option list - each option is a string or {'value': 'A', 'image_url': 'https://...'}), 'shuffle' (choice questions), 'image_url' (sets the image on a question or replaces an image item's image; takes optional 'image_alt_text', 'image_width', 'image_alignment'), 'move_to_index' (new 0-based position among all items; moves apply in the order given), or 'delete': True to remove the item. Options on multiple choice / dropdown questions may branch: {'value': 'Yes', 'go_to_section_id': '<PAGE_BREAK_ITEM itemId>'} or {'value': 'No', 'go_to_action': 'SUBMIT_FORM'}. Image URLs must be publicly reachable. Examples: [{'item_id': '12345', 'title': 'Updated Question', 'required': True}], [{'item_id': '12345', 'options': [{'value': 'A', 'image_url': 'https://example.com/a.png'}, 'None of them']}], [{'item_id': '67890', 'delete': True}]"
            ),
        ],
        user_google_email: UserGoogleEmailForms = None,
    ) -> FormUpdateResult:
        """
        Modify existing questions in a Google Form using efficient batch operations.

        Use get_form first to get item_ids. Supported updates: title, description,
        required, options (with per-option images and branching), shuffle,
        image_url, move_to_index, delete.

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

            # Build batch update request (the Forms API addresses items by index)
            current = await asyncio.to_thread(
                forms_service.forms().get(formId=form_id).execute
            )
            batch_update_body = build_batch_update_request(
                valid_updates, current.get("items", [])
            )

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

        except ValueError as e:
            error_msg = f"❌ Invalid update: {e}"
            logger.warning(f"[update_form_questions] {error_msg}")
            return FormUpdateResult(
                success=False,
                message=error_msg,
                formId=form_id,
                title=None,
                editUrl=f"https://docs.google.com/forms/d/{form_id}/edit",
                error=str(e),
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
    tool_count = 9  # Total number of Forms tools
    logger.info(
        f"Successfully registered {tool_count} Google Forms tools with enhanced documentation"
    )

    # Parameter defaults validation summary:
    # - create_form: description=None, document_title=None (optional fields)
    # - set_form_publish_state: accepting_responses=True (forms should accept by default)
    # - publish_form_publicly: anyone_can_respond=True (public by default), share_with_emails=None (optional)
    # - list_form_responses: page_size=10 (reasonable for most use cases), page_token=None (start from beginning)
    # All parameter defaults are validated and reasonable for typical use cases.
