"""
Enums and constants for Google Drive operations.

This module provides clean, type-safe enumerations for Drive file types
and query operations.
"""

from enum import Enum
from typing import Optional


class MimeTypeFilter(str, Enum):
    """
    Enumeration of common file type filters for Google Drive searches.

    Each value maps to either a single MIME type or a logical group
    of related MIME types for convenient filtering.
    """

    # Google Workspace
    GOOGLE_DOCS = "google_docs"
    GOOGLE_SHEETS = "google_sheets"
    GOOGLE_SLIDES = "google_slides"
    GOOGLE_FORMS = "google_forms"
    GOOGLE_DRAWINGS = "google_drawings"
    GOOGLE_FOLDER = "google_folder"

    # Microsoft Office
    WORD = "word"
    EXCEL = "excel"
    POWERPOINT = "powerpoint"

    # Common Documents
    PDF = "pdf"
    TEXT = "text"
    CSV = "csv"
    JSON = "json"
    XML = "xml"
    HTML = "html"

    # Images
    JPEG = "jpeg"
    PNG = "png"
    GIF = "gif"
    SVG = "svg"

    # Videos
    MP4 = "mp4"
    AVI = "avi"
    MOV = "mov"

    # Archives
    ZIP = "zip"
    TAR = "tar"
    RAR = "rar"

    # Special Groups
    ALL_SPREADSHEETS = "all_spreadsheets"  # Google Sheets + Excel
    ALL_DOCUMENTS = "all_documents"  # Google Docs + Word + PDF
    ALL_PRESENTATIONS = "all_presentations"  # Google Slides + PowerPoint
    EXCLUDE_FOLDERS = "exclude_folders"  # Everything except folders

    def to_mime_type(self) -> Optional[str]:
        """
        Convert the enum value to actual Google Drive MIME type string(s).

        Returns:
            The MIME type string for single types, None for compound types
            (compound types need special query construction)
        """
        mime_map = {
            # Google Workspace
            self.GOOGLE_DOCS: "application/vnd.google-apps.document",
            self.GOOGLE_SHEETS: "application/vnd.google-apps.spreadsheet",
            self.GOOGLE_SLIDES: "application/vnd.google-apps.presentation",
            self.GOOGLE_FORMS: "application/vnd.google-apps.form",
            self.GOOGLE_DRAWINGS: "application/vnd.google-apps.drawing",
            self.GOOGLE_FOLDER: "application/vnd.google-apps.folder",
            # Microsoft Office
            self.WORD: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            self.EXCEL: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            self.POWERPOINT: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            # Common Documents
            self.PDF: "application/pdf",
            self.TEXT: "text/plain",
            self.CSV: "text/csv",
            self.JSON: "application/json",
            self.XML: "application/xml",
            self.HTML: "text/html",
            # Images
            self.JPEG: "image/jpeg",
            self.PNG: "image/png",
            self.GIF: "image/gif",
            self.SVG: "image/svg+xml",
            # Videos
            self.MP4: "video/mp4",
            self.AVI: "video/x-msvideo",
            self.MOV: "video/quicktime",
            # Archives
            self.ZIP: "application/zip",
            self.TAR: "application/x-tar",
            self.RAR: "application/x-rar-compressed",
        }
        return mime_map.get(self)

    def to_query_filter(self) -> str:
        """
        Convert the enum value to a Google Drive query filter string.

        Returns:
            A query string fragment that can be combined with other filters
        """
        # Handle special compound types
        if self == self.ALL_SPREADSHEETS:
            return "(mimeType = 'application/vnd.google-apps.spreadsheet' or mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')"
        elif self == self.ALL_DOCUMENTS:
            return "(mimeType = 'application/vnd.google-apps.document' or mimeType = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' or mimeType = 'application/pdf')"
        elif self == self.ALL_PRESENTATIONS:
            return "(mimeType = 'application/vnd.google-apps.presentation' or mimeType = 'application/vnd.openxmlformats-officedocument.presentationml.presentation')"
        elif self == self.EXCLUDE_FOLDERS:
            return "mimeType != 'application/vnd.google-apps.folder'"

        # Handle single MIME types
        mime_type = self.to_mime_type()
        if mime_type:
            return f"mimeType = '{mime_type}'"

        return ""


class QueryField(str, Enum):
    """
    Common Google Drive query fields for structured searches.
    """

    MIME_TYPE = "mimeType"
    NAME = "name"
    FULL_TEXT = "fullText"
    MODIFIED_TIME = "modifiedTime"
    CREATED_TIME = "createdTime"
    OWNERS = "owners"
    TRASHED = "trashed"
    STARRED = "starred"
    PARENTS = "parents"
    SHARED_WITH_ME = "sharedWithMe"


class QueryOperator(str, Enum):
    """
    Google Drive query operators.
    """

    EQUALS = "="
    NOT_EQUALS = "!="
    CONTAINS = "contains"
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_EQUAL = ">="
    LESS_EQUAL = "<="
    IN = "in"
    AND = "and"
    OR = "or"
    NOT = "not"
