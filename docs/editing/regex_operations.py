"""
Regex operations for Google Docs content manipulation.

Provides utilities for applying regex search and replace operations
to document text content before updating via the Docs API.
"""

import logging
import re
from typing import List, Tuple

from docs.docs_types import RegexReplace

logger = logging.getLogger(__name__)


def apply_regex_replacements(
    content: str, operations: List[RegexReplace]
) -> Tuple[str, int]:
    """
    Apply a series of regex search and replace operations to document content.

    Args:
        content: The original document text content
        operations: List of RegexReplace operations to apply sequentially

    Returns:
        Tuple[str, int]: (modified_content, number_of_replacements_made)
    """
    modified_content = content
    total_replacements = 0

    for i, operation in enumerate(operations):
        try:
            # Parse regex flags if provided
            flags = 0
            if operation.flags:
                if "i" in operation.flags.lower():
                    flags |= re.IGNORECASE
                if "m" in operation.flags.lower():
                    flags |= re.MULTILINE
                if "s" in operation.flags.lower():
                    flags |= re.DOTALL
                if "x" in operation.flags.lower():
                    flags |= re.VERBOSE

            # Compile pattern
            try:
                pattern = re.compile(operation.pattern, flags)
            except re.error as regex_err:
                logger.error(
                    f"[apply_regex_replacements] Invalid regex pattern '{operation.pattern}': {regex_err}"
                )
                raise ValueError(
                    f"Invalid regex pattern in operation {i + 1}: {regex_err}"
                )

            # Count matches before replacement
            matches = pattern.findall(modified_content)
            match_count = len(matches)

            # Apply replacement
            modified_content = pattern.sub(operation.replacement, modified_content)

            total_replacements += match_count
            logger.info(
                f"[apply_regex_replacements] Operation {i + 1}: "
                f"Pattern '{operation.pattern}' -> '{operation.replacement}' "
                f"(Made {match_count} replacements)"
            )

        except Exception as e:
            logger.error(f"[apply_regex_replacements] Error in operation {i + 1}: {e}")
            raise

    logger.info(
        f"[apply_regex_replacements] Completed {len(operations)} operations "
        f"with {total_replacements} total replacements"
    )

    return modified_content, total_replacements


def validate_regex_operations(operations: List[RegexReplace]) -> Tuple[bool, str]:
    """
    Validate regex operations before applying them.

    Args:
        operations: List of RegexReplace operations to validate

    Returns:
        Tuple[bool, str]: (is_valid, error_message)
    """
    if not operations:
        return False, "No regex operations provided"

    for i, operation in enumerate(operations):
        # Validate pattern
        try:
            # Parse flags
            flags = 0
            if operation.flags:
                if "i" in operation.flags.lower():
                    flags |= re.IGNORECASE
                if "m" in operation.flags.lower():
                    flags |= re.MULTILINE
                if "s" in operation.flags.lower():
                    flags |= re.DOTALL
                if "x" in operation.flags.lower():
                    flags |= re.VERBOSE

            re.compile(operation.pattern, flags)
        except re.error as e:
            return (
                False,
                f"Invalid regex pattern in operation {i + 1} ('{operation.pattern}'): {str(e)}",
            )

        # Validate replacement string (check for valid backreferences)
        try:
            # Test the replacement string with a dummy match
            test_pattern = re.compile(operation.pattern, flags)
            # Create a simple test to see if replacement references are valid
            test_match = re.match(r"(.*)", "test")
            if test_match:
                test_match.expand(operation.replacement)
        except re.error as e:
            return (
                False,
                f"Invalid replacement string in operation {i + 1} ('{operation.replacement}'): {str(e)}",
            )
        except Exception:
            # If we can't test it, let it through - it might be valid
            pass

    return True, ""
