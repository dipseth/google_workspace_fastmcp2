"""Workspace content resources for FastMCP2 Google Workspace Platform.

This module provides resources that search across Google Workspace content
(Drive, Docs, Sheets) for dynamic email composition and content discovery.
"""

from datetime import datetime

from fastmcp import Context, FastMCP
from pydantic import Field
from typing_extensions import Annotated

from auth.context import get_user_email_context
from config.enhanced_logging import setup_logger

logger = setup_logger()


def setup_workspace_resources(mcp: FastMCP) -> None:
    """Setup workspace content search resources."""

    @mcp.resource(
        uri="workspace://content/search/{query}",
        name="Search Google Workspace Content",
        description="Search across Google Workspace content (Drive, Docs, Sheets) for specific topics or keywords to dynamically populate email content with relevant links and references",
        mime_type="application/json",
        tags={
            "workspace",
            "search",
            "drive",
            "docs",
            "sheets",
            "content",
            "gmail",
            "dynamic",
        },
    )
    async def search_workspace_content(
        query: Annotated[
            str,
            Field(
                description="Search query to find relevant workspace content by filename or document content. Supports both keyword searches and phrase matching for comprehensive content discovery.",
                examples=[
                    "quarterly budget",
                    "project alpha",
                    "meeting notes",
                    "2024 planning",
                ],
                min_length=1,
                max_length=200,
                title="Search Query",
            ),
        ],
        ctx: Context,
    ) -> str:
        """Search Google Workspace content for email composition and content discovery.

        Performs comprehensive content-based search across Google Drive files including
        both filename matching and full-text content search within documents. Results
        are automatically categorized by file type and formatted for email composition
        workflows with suggested references, links, and attachments.

        This resource is essential for dynamic email composition, allowing users to
        discover relevant documents, spreadsheets, and presentations to reference or
        attach in their communications.

        Args:
            query: Search terms to find relevant workspace content. The query is used
                for both filename matching and full-text content search within documents.
                Supports single keywords, multiple terms, or phrase searches. Common
                examples include project names, topic keywords, or document titles.
            ctx: FastMCP Context object providing access to server state and logging

        Returns:
            str: JSON string with comprehensive search results including:
            - Categorized results by file type (documents, spreadsheets, presentations, PDFs, images)
            - Email composition suggestions with ready-to-use references and links
            - Relevance scoring based on filename matches
            - Total result count and search metadata
            - Error details if search fails or user is not authenticated

        Authentication:
            Requires active user authentication. Returns error if no authenticated
            user is found in the current session context.

        Example Usage:
            await search_workspace_content("quarterly budget report", ctx)
            await search_workspace_content("project alpha", ctx)

        Example Response:
            {
                "search_query": "quarterly budget",
                "user_email": "user@company.com",
                "total_results": 8,
                "results_by_type": {
                    "documents": [
                        {
                            "id": "1ABC123",
                            "name": "Q4 Budget Report",
                            "web_view_link": "https://docs.google.com/document/d/1ABC123",
                            "modified_time": "2024-01-10T15:30:00Z",
                            "relevance_score": "high"
                        }
                    ],
                    "spreadsheets": [...],
                    "presentations": [...],
                    "pdfs": [...],
                    "images": [],
                    "other": []
                },
                "suggested_email_content": {
                    "references": ["📄 Q4 Budget Report", "📊 Budget Analysis"],
                    "links": ["https://docs.google.com/document/d/1ABC123"],
                    "attachment_suggestions": [...]
                },
                "timestamp": "2024-01-15T10:30:00Z"
            }

        Example Response (Not Authenticated):
            {
                "error": "No authenticated user found in current session",
                "query": "quarterly budget"
            }
        """
        import json

        user_email = await get_user_email_context()
        if not user_email:
            return json.dumps(
                {
                    "error": "No authenticated user found in current session",
                    "query": query,
                }
            )

        try:
            # Import and call tools directly (not using forward())
            from drive.drive_tools import search_drive_files

            # Search Drive files using direct tool call
            search_results = await search_drive_files(
                user_google_email=user_email,
                query=f"name contains '{query}' or fullText contains '{query}'",
                page_size=15,
            )

            # Process and categorize results
            categorized_results = {
                "documents": [],
                "spreadsheets": [],
                "presentations": [],
                "pdfs": [],
                "images": [],
                "other": [],
            }

            for file_info in search_results.get("results", []):
                mime_type = file_info.get("mimeType", "")
                file_entry = {
                    "id": file_info.get("id"),
                    "name": file_info.get("name"),
                    "web_view_link": file_info.get("webViewLink"),
                    "modified_time": file_info.get("modifiedTime"),
                    "relevance_score": (
                        "high"
                        if query.lower() in file_info.get("name", "").lower()
                        else "medium"
                    ),
                }

                if "document" in mime_type:
                    categorized_results["documents"].append(file_entry)
                elif "spreadsheet" in mime_type:
                    categorized_results["spreadsheets"].append(file_entry)
                elif "presentation" in mime_type:
                    categorized_results["presentations"].append(file_entry)
                elif "pdf" in mime_type:
                    categorized_results["pdfs"].append(file_entry)
                elif "image" in mime_type:
                    categorized_results["images"].append(file_entry)
                else:
                    categorized_results["other"].append(file_entry)

            return json.dumps(
                {
                    "search_query": query,
                    "user_email": user_email,
                    "total_results": len(search_results.get("results", [])),
                    "results_by_type": categorized_results,
                    "suggested_email_content": {
                        "references": [
                            f"📄 {file['name']}"
                            for file in search_results.get("results", [])[:5]
                        ],
                        "links": [
                            file.get("webViewLink")
                            for file in search_results.get("results", [])[:3]
                        ],
                        "attachment_suggestions": [
                            file
                            for file in search_results.get("results", [])
                            if file.get("mimeType", "").startswith("application/")
                        ][:3],
                    },
                    "timestamp": datetime.now().isoformat(),
                },
                default=str,
            )

        except Exception as e:
            logger.error(f"Error searching workspace content: {e}")
            return json.dumps(
                {
                    "error": f"Failed to search workspace content: {str(e)}",
                    "search_query": query,
                    "timestamp": datetime.now().isoformat(),
                }
            )

    logger.info("✅ Workspace content resources registered")
