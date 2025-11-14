"""
Document line parsing utilities for Google Docs.

Handles parsing of Google Docs structure to identify line positions
and character indices for targeted editing operations.
"""

import logging
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)


class DocumentLine:
    """Represents a single line in a Google Doc with its position metadata."""

    def __init__(
        self, line_number: int, start_index: int, end_index: int, content: str
    ):
        self.line_number = line_number
        self.start_index = start_index
        self.end_index = end_index
        self.content = content

    def __repr__(self):
        return f"DocumentLine(line={self.line_number}, start={self.start_index}, end={self.end_index}, content_len={len(self.content)})"


def parse_document_lines(doc_data: Dict) -> List[DocumentLine]:
    """
    Parse a Google Doc's structure to extract line-by-line positions.

    Google Docs API returns a hierarchical structure with paragraphs and text runs.
    This function flattens it into a line-based view with character indices.

    Args:
        doc_data: The document data from docs_service.documents().get()

    Returns:
        List[DocumentLine]: List of lines with their positions and content
    """
    lines: List[DocumentLine] = []
    body_content = doc_data.get("body", {}).get("content", [])

    current_line_number = 1

    for element in body_content:
        if "paragraph" in element:
            paragraph = element.get("paragraph", {})
            para_elements = paragraph.get("elements", [])

            # Collect all text from this paragraph
            paragraph_text = ""
            start_index = element.get("startIndex", 0)
            end_index = element.get("endIndex", 0)

            for pe in para_elements:
                text_run = pe.get("textRun", {})
                if text_run and "content" in text_run:
                    paragraph_text += text_run["content"]

            # Split paragraph into lines if it contains newlines
            if paragraph_text:
                # Each paragraph in Google Docs ends with \n, so we split carefully
                text_lines = paragraph_text.split("\n")

                # Calculate approximate character positions for each line
                current_pos = start_index
                for i, line_text in enumerate(text_lines):
                    if (
                        line_text or i < len(text_lines) - 1
                    ):  # Include empty lines except trailing
                        line_end = current_pos + len(line_text) + 1  # +1 for newline

                        lines.append(
                            DocumentLine(
                                line_number=current_line_number,
                                start_index=current_pos,
                                end_index=line_end,
                                content=line_text,
                            )
                        )
                        current_line_number += 1
                        current_pos = line_end

    logger.info(f"[parse_document_lines] Parsed {len(lines)} lines from document")
    return lines


def find_line_position(lines: List[DocumentLine], target_line: int) -> Optional[int]:
    """
    Find the character index for a specific line number.

    Args:
        lines: List of DocumentLine objects from parse_document_lines
        target_line: The line number to find (1-based)

    Returns:
        Optional[int]: The character index where the line starts, or None if not found
    """
    for line in lines:
        if line.line_number == target_line:
            return line.start_index

    logger.warning(f"[find_line_position] Line {target_line} not found in document")
    return None


def get_document_end_index(doc_data: Dict) -> int:
    """
    Get the end index of the document (for appending content).

    Args:
        doc_data: The document data from docs_service.documents().get()

    Returns:
        int: The character index at the end of the document
    """
    body_content = doc_data.get("body", {}).get("content", [])
    end_index = 1  # Minimum is 1 (Google Docs always has at least one character)

    for element in body_content:
        if "endIndex" in element:
            end_index = max(end_index, element["endIndex"])

    return end_index


def extract_document_text(doc_data: Dict) -> str:
    """
    Extract all text content from a Google Doc as a continuous string.
    
    This function comprehensively extracts text from all content types:
    - Paragraphs
    - Tables (including nested cells)
    - Lists
    - Any other structural elements
    
    Args:
        doc_data: The document data from docs_service.documents().get()
    
    Returns:
        str: The complete document text as a single string
    """
    
    def extract_from_element(element: Dict) -> str:
        """Recursively extract text from a document element."""
        text_content = ""
        
        # Handle paragraph elements
        if "paragraph" in element:
            paragraph = element.get("paragraph", {})
            para_elements = paragraph.get("elements", [])
            for pe in para_elements:
                text_run = pe.get("textRun", {})
                if text_run and "content" in text_run:
                    text_content += text_run["content"]
        
        # Handle table elements
        elif "table" in element:
            table = element.get("table", {})
            table_rows = table.get("tableRows", [])
            for row in table_rows:
                table_cells = row.get("tableCells", [])
                for cell in table_cells:
                    cell_content = cell.get("content", [])
                    for cell_element in cell_content:
                        # Recursively extract text from cell content
                        text_content += extract_from_element(cell_element)
        
        # Handle section breaks and other structural elements
        # (They typically don't contain text, but we check for completeness)
        elif "sectionBreak" in element:
            # Section breaks don't contain text
            pass
        
        # Handle table of contents
        elif "tableOfContents" in element:
            toc = element.get("tableOfContents", {})
            toc_content = toc.get("content", [])
            for toc_element in toc_content:
                text_content += extract_from_element(toc_element)
        
        return text_content
    
    # Extract text from body content
    body_content = doc_data.get("body", {}).get("content", [])
    full_text = ""
    
    for element in body_content:
        full_text += extract_from_element(element)
    
    logger.info(
        f"[extract_document_text] Extracted {len(full_text)} characters from document"
    )
    
    return full_text
