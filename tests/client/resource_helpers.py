"""
Resource helpers for client tests to fetch real IDs from service:// resources.

This module provides utilities to fetch real IDs from the service resource system
instead of using hardcoded fake IDs in tests. This makes tests more realistic
and helps validate the actual resource system.

MCP client types:
- client.read_resource() → ReadResourceResult
  - .contents: list[TextResourceContents | BlobResourceContents]
    - TextResourceContents: .text (str), .uri, .mimeType
"""

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ResourceIDFetcher:
    """Helper class to fetch real IDs from service resources."""

    def __init__(self, client):
        """Initialize with a FastMCP client."""
        self.client = client
        self._cache = {}

    async def get_first_id_from_service(
        self, service: str, list_type: str
    ) -> Optional[str]:
        """
        Get the first available ID from a service list.

        Args:
            service: Service name (gmail, drive, calendar, etc.)
            list_type: Type of list (filters, labels, events, items, etc.)

        Returns:
            First available ID or None if no items found
        """
        cache_key = f"{service}_{list_type}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            # Read the service list resource
            resource_uri = f"service://{service}/{list_type}"
            logger.info(f"📡 Fetching real IDs from {resource_uri}")

            # ReadResourceResult.contents[0] is TextResourceContents with .text
            result = await self.client.read_resource(resource_uri)
            data = json.loads(result.contents[0].text)

            # Extract first ID from various response formats
            first_id = self._extract_first_id(data, list_type)

            if first_id:
                self._cache[cache_key] = first_id
                logger.info(f"✅ Found real {list_type} ID: {first_id}")
                return first_id
            else:
                logger.warning(f"No IDs found in {resource_uri} response")
                return None

        except Exception as e:
            logger.warning(f"Failed to fetch real ID from {resource_uri}: {e}")
            return None

    def _extract_first_id(self, data: Dict[Any, Any], list_type: str) -> Optional[str]:
        """Extract the first ID from response data based on list type."""

        # Handle different response structures
        if isinstance(data, dict):
            # Look for common ID patterns in the response
            if "result" in data and isinstance(data["result"], dict):
                result = data["result"]

                # Gmail filters/labels
                if list_type in ["filters", "labels"] and "filters" in result:
                    filters = result["filters"]
                    if filters and len(filters) > 0:
                        return filters[0].get("id")
                elif list_type in ["filters", "labels"] and "labels" in result:
                    labels = result["labels"]
                    if labels and len(labels) > 0:
                        return labels[0].get("id")

                # Calendar events
                elif list_type == "events" and "items" in result:
                    items = result["items"]
                    if items and len(items) > 0:
                        return items[0].get("id")

                # Drive items
                elif list_type == "items" and "files" in result:
                    files = result["files"]
                    if files and len(files) > 0:
                        return files[0].get("id")

                # Photos albums
                elif list_type == "albums" and "albums" in result:
                    albums = result["albums"]
                    if albums and len(albums) > 0:
                        return albums[0].get("id")

                # Forms
                elif list_type in ["forms", "form_responses"] and "forms" in result:
                    forms = result["forms"]
                    if forms and len(forms) > 0:
                        return forms[0].get("formId") or forms[0].get("id")

                # Chat spaces
                elif list_type == "spaces" and "spaces" in result:
                    spaces = result["spaces"]
                    if spaces and len(spaces) > 0:
                        return spaces[0].get("name") or spaces[0].get("id")

                # Generic search for ID fields
                else:
                    # Look for any list with ID fields
                    for key, value in result.items():
                        if isinstance(value, list) and value:
                            first_item = value[0]
                            if isinstance(first_item, dict):
                                # Try common ID field names
                                for id_field in [
                                    "id",
                                    "messageId",
                                    "formId",
                                    "eventId",
                                    "fileId",
                                    "albumId",
                                ]:
                                    if id_field in first_item:
                                        return first_item[id_field]

            # Direct result format
            elif isinstance(data, list) and data:
                first_item = data[0]
                if isinstance(first_item, dict):
                    for id_field in [
                        "id",
                        "messageId",
                        "formId",
                        "eventId",
                        "fileId",
                        "albumId",
                    ]:
                        if id_field in first_item:
                            return first_item[id_field]

        return None

    async def get_gmail_message_id(self) -> Optional[str]:
        """Get a real Gmail message ID."""
        try:
            # Try to get from messages list
            resource_uri = "service://gmail/messages"
            result = await self.client.read_resource(resource_uri)
            data = json.loads(result.contents[0].text)

            # Look for message ID in response
            if isinstance(data, dict) and "result" in data:
                messages = data["result"].get("messages", [])
                if messages:
                    return messages[0].get("id")

            return None
        except Exception as e:
            logger.warning(f"Failed to get Gmail message ID: {e}")
            return None

    async def get_gmail_filter_id(self) -> Optional[str]:
        """Get a real Gmail filter ID."""
        return await self.get_first_id_from_service("gmail", "filters")

    async def get_drive_document_id(self) -> Optional[str]:
        """Get a real Drive document ID."""
        try:
            # Get items from Drive
            all_items = await self.get_first_id_from_service("drive", "items")
            if all_items:
                # Filter for document types if possible
                return all_items
            return None
        except Exception as e:
            logger.warning(f"Failed to get Drive document ID: {e}")
            return None

    async def get_drive_folder_id(self) -> Optional[str]:
        """Get a real Drive folder ID."""
        try:
            # Try to find a folder in Drive items
            resource_uri = "service://drive/items"
            result = await self.client.read_resource(resource_uri)
            data = json.loads(result.contents[0].text)

            # Look for folders in the response
            if isinstance(data, dict) and "result" in data:
                files = data["result"].get("files", [])
                for file in files:
                    if file.get("mimeType") == "application/vnd.google-apps.folder":
                        return file.get("id")
                # If no folders found, use first item
                if files:
                    return files[0].get("id")

            return None
        except Exception as e:
            logger.warning(f"Failed to get Drive folder ID: {e}")
            return None

    async def get_calendar_event_id(self) -> Optional[str]:
        """Get a real Calendar event ID."""
        return await self.get_first_id_from_service("calendar", "events")

    async def get_photos_album_id(self) -> Optional[str]:
        """Get a real Photos album ID."""
        return await self.get_first_id_from_service("photos", "albums")

    async def get_forms_form_id(self) -> Optional[str]:
        """Get a real Forms form ID."""
        return await self.get_first_id_from_service("forms", "form_responses")

    async def get_chat_space_id(self) -> Optional[str]:
        """Get a real Chat space ID."""
        return await self.get_first_id_from_service("chat", "spaces")


async def create_resource_id_fetcher(client) -> ResourceIDFetcher:
    """Create a ResourceIDFetcher instance."""
    return ResourceIDFetcher(client)


# Convenience functions for pytest fixtures
def pytest_real_id_fixture(service: str, list_type: str):
    """
    Create a pytest fixture that fetches real IDs from resources.

    Usage:
        @pytest.fixture
        async def real_message_id(client):
            return await pytest_real_id_fixture("gmail", "messages")(client)
    """

    async def _get_real_id(client):
        fetcher = ResourceIDFetcher(client)
        return await fetcher.get_first_id_from_service(service, list_type)

    return _get_real_id


# Pre-defined fixtures for common ID types
async def get_real_gmail_message_id(client) -> Optional[str]:
    """Fixture to get real Gmail message ID."""
    fetcher = ResourceIDFetcher(client)
    return await fetcher.get_gmail_message_id()


async def get_real_gmail_filter_id(client) -> Optional[str]:
    """Fixture to get real Gmail filter ID."""
    fetcher = ResourceIDFetcher(client)
    return await fetcher.get_gmail_filter_id()


async def get_real_drive_document_id(client) -> Optional[str]:
    """Fixture to get real Drive document ID."""
    fetcher = ResourceIDFetcher(client)
    return await fetcher.get_drive_document_id()


async def get_real_drive_folder_id(client) -> Optional[str]:
    """Fixture to get real Drive folder ID."""
    fetcher = ResourceIDFetcher(client)
    return await fetcher.get_drive_folder_id()


async def get_real_calendar_event_id(client) -> Optional[str]:
    """Fixture to get real Calendar event ID."""
    fetcher = ResourceIDFetcher(client)
    return await fetcher.get_calendar_event_id()


async def get_real_photos_album_id(client) -> Optional[str]:
    """Fixture to get real Photos album ID."""
    fetcher = ResourceIDFetcher(client)
    return await fetcher.get_photos_album_id()


async def get_real_forms_form_id(client) -> Optional[str]:
    """Fixture to get real Forms form ID."""
    fetcher = ResourceIDFetcher(client)
    return await fetcher.get_forms_form_id()


async def get_real_chat_space_id(client) -> Optional[str]:
    """Fixture to get real Chat space ID."""
    fetcher = ResourceIDFetcher(client)
    return await fetcher.get_chat_space_id()
