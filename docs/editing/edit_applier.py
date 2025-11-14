"""
Edit application logic for Google Docs.

Coordinates the application of different editing modes (replace_all, insert_at_line,
regex_replace, append) to Google Docs using the Docs API batch update mechanism.
"""

import logging
import asyncio
from typing import Dict, List, Any, Tuple
from docs.docs_types import EditConfig, RegexReplace
from .line_parser import (
    parse_document_lines,
    find_line_position,
    get_document_end_index,
    extract_document_text,
)
from .regex_operations import apply_regex_replacements, validate_regex_operations

logger = logging.getLogger(__name__)


async def apply_edit_config(
    docs_service: Any,
    document_id: str,
    content: str,
    edit_config: EditConfig,
    doc_data: Dict,
) -> Tuple[List[Dict], str]:
    """
    Apply an EditConfig to a document and return the batch update requests.

    Args:
        docs_service: The authenticated Google Docs service
        document_id: The document ID to edit
        content: The content to insert/replace
        edit_config: The EditConfig specifying how to edit
        doc_data: The current document data from docs_service.documents().get()

    Returns:
        Tuple[List[Dict], str]: (batch_update_requests, success_message)

    Raises:
        ValueError: If edit configuration is invalid
    """
    requests: List[Dict] = []

    if edit_config.mode == "replace_all":
        logger.info("[apply_edit_config] Mode: replace_all")

        # Get document end index
        end_index = get_document_end_index(doc_data)

        # Delete all existing content (except required first character)
        if end_index > 1:
            requests.append(
                {
                    "deleteContentRange": {
                        "range": {"startIndex": 1, "endIndex": end_index - 1}
                    }
                }
            )

        # Insert new content at the beginning
        requests.append({"insertText": {"location": {"index": 1}, "text": content}})

        message = "Replaced all document content"

    elif edit_config.mode == "insert_at_line":
        logger.info(
            f"[apply_edit_config] Mode: insert_at_line (line {edit_config.line_number})"
        )

        if not edit_config.line_number:
            raise ValueError("line_number is required for insert_at_line mode")

        # Parse document lines
        lines = parse_document_lines(doc_data)

        # Find the insertion position
        insert_index = find_line_position(lines, edit_config.line_number)

        if insert_index is None:
            # If line not found, append to end
            insert_index = get_document_end_index(doc_data) - 1
            logger.warning(
                f"[apply_edit_config] Line {edit_config.line_number} not found, "
                f"appending to end at index {insert_index}"
            )

        # Insert content at the specified position
        requests.append(
            {
                "insertText": {
                    "location": {"index": insert_index},
                    "text": content + "\n",  # Add newline after inserted content
                }
            }
        )

        message = f"Inserted content at line {edit_config.line_number}"

    elif edit_config.mode == "append":
        logger.info("[apply_edit_config] Mode: append")

        # Get document end index
        end_index = get_document_end_index(doc_data)

        # Insert content at the end (before the final required character)
        requests.append(
            {
                "insertText": {
                    "location": {"index": end_index - 1},
                    "text": "\n" + content,  # Add newline before appended content
                }
            }
        )

        message = "Appended content to end of document"

    elif edit_config.mode == "regex_replace":
        logger.info("[apply_edit_config] Mode: regex_replace")

        if not edit_config.regex_operations:
            raise ValueError("regex_operations is required for regex_replace mode")

        # Validate regex operations first
        is_valid, error_msg = validate_regex_operations(edit_config.regex_operations)
        if not is_valid:
            raise ValueError(f"Invalid regex operations: {error_msg}")

        # Extract document text using comprehensive extraction utility
        current_text = extract_document_text(doc_data)
        
        logger.info(
            f"[apply_edit_config] Extracted {len(current_text)} characters from document"
        )
        logger.info(
            f"[apply_edit_config] First 200 chars: {repr(current_text[:200])}"
        )

        # Validate that we extracted some text
        if not current_text or len(current_text) <= 1:
            raise ValueError(
                "No text content found in document. The document may be empty or contain only non-text elements."
            )

        # Apply regex operations
        modified_text, replacement_count = apply_regex_replacements(
            current_text, edit_config.regex_operations
        )

        # Get document end index
        end_index = get_document_end_index(doc_data)

        # Delete all existing content
        if end_index > 1:
            requests.append(
                {
                    "deleteContentRange": {
                        "range": {"startIndex": 1, "endIndex": end_index - 1}
                    }
                }
            )

        # Insert modified content
        requests.append(
            {"insertText": {"location": {"index": 1}, "text": modified_text}}
        )

        message = f"Applied {len(edit_config.regex_operations)} regex operations ({replacement_count} replacements)"

    else:
        raise ValueError(f"Unknown edit mode: {edit_config.mode}")

    logger.info(f"[apply_edit_config] Generated {len(requests)} batch update requests")
    return requests, message
