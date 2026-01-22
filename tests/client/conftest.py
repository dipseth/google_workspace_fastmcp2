"""Pytest configuration and fixtures for standardized client testing.

🔧 MCP Tools Used:
- N/A (Pytest configuration - enables testing of all MCP tools)
- Provides client fixture used by all MCP tool tests

🧪 What's Being Tested:
- Pytest fixture configuration for client testing
- Global test markers and categories
- Client instance management and reuse
- Test session configuration and cleanup
- Integration with base_test_config for connection management

🔍 Potential Duplications:
- No duplications - this is the central pytest configuration
- Eliminates fixture duplication across individual test files
- Provides shared client instance to avoid connection overhead

Note: This is the pytest framework configuration file.
"""

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

import pytest
import pytest_asyncio

# Ensure pytest process uses the same trusted cert bundle as the running HTTPS server.
# This mirrors the VS Code MCP client config that connects to https://localhost:8002/mcp.
os.environ.setdefault(
    "SSL_CERT_FILE",
    os.path.abspath("localhost+2.pem"),
)
os.environ.setdefault(
    "REQUESTS_CA_BUNDLE",
    os.path.abspath("localhost+2.pem"),
)

from .base_test_config import TEST_EMAIL, create_test_client, print_test_configuration
from .resource_helpers import (
    get_real_calendar_event_id,
    get_real_chat_space_id,
    get_real_drive_document_id,
    get_real_drive_folder_id,
    get_real_forms_form_id,
    get_real_gmail_filter_id,
    get_real_gmail_message_id,
    get_real_photos_album_id,
)

# NOTE:
# Pytest 8+ no longer supports defining `pytest_plugins` in non-top-level conftest.
# Keep this file fixture-only.


# =============================================================================
# Resource Cleanup Infrastructure
# =============================================================================


@dataclass
class ResourceCleanupTracker:
    """Tracks resources created during tests for cleanup at session end.

    This tracker helps prevent orphaned resources in Google Workspace by
    collecting resource IDs created during test runs and cleaning them up
    automatically when the test session completes.

    Supported resource types:
    - calendar_events: Cleaned via delete_event tool
    - gmail_filters: Cleaned via delete_gmail_filter tool
    - drive_files: Cleaned via manage_drive_files (delete) tool

    Resources without delete APIs (photos, chat, docs, forms, slides) must be
    cleaned manually or via the standalone cleanup script.

    Usage in tests:
        def test_something(cleanup_tracker, client):
            result = await client.call_tool("create_event", {...})
            event_id = result["event_id"]
            cleanup_tracker.track_calendar_event(event_id)
    """

    calendar_events: list[str] = field(default_factory=list)
    gmail_filters: list[str] = field(default_factory=list)
    gmail_labels: list[str] = field(default_factory=list)
    drive_files: list[str] = field(default_factory=list)
    spreadsheets: list[str] = field(default_factory=list)
    # Resources without delete APIs - tracked for manual cleanup reference
    photos_albums: list[str] = field(default_factory=list)
    docs: list[str] = field(default_factory=list)
    forms: list[str] = field(default_factory=list)
    presentations: list[str] = field(default_factory=list)
    _cleanup_errors: list[dict[str, Any]] = field(default_factory=list)

    def track_calendar_event(self, event_id: str) -> None:
        """Track a calendar event for cleanup."""
        if event_id and event_id not in self.calendar_events:
            self.calendar_events.append(event_id)

    def track_gmail_filter(self, filter_id: str) -> None:
        """Track a Gmail filter for cleanup."""
        if filter_id and filter_id not in self.gmail_filters:
            self.gmail_filters.append(filter_id)

    def track_drive_file(self, file_id: str) -> None:
        """Track a Drive file for cleanup."""
        if file_id and file_id not in self.drive_files:
            self.drive_files.append(file_id)

    def track_photos_album(self, album_id: str) -> None:
        """Track a Photos album (manual cleanup required)."""
        if album_id and album_id not in self.photos_albums:
            self.photos_albums.append(album_id)

    def track_doc(self, doc_id: str) -> None:
        """Track a Google Doc (manual cleanup required)."""
        if doc_id and doc_id not in self.docs:
            self.docs.append(doc_id)

    def track_form(self, form_id: str) -> None:
        """Track a Google Form (manual cleanup required)."""
        if form_id and form_id not in self.forms:
            self.forms.append(form_id)

    def track_presentation(self, presentation_id: str) -> None:
        """Track a Google Slides presentation (manual cleanup required)."""
        if presentation_id and presentation_id not in self.presentations:
            self.presentations.append(presentation_id)

    def track_gmail_label(self, label_id: str) -> None:
        """Track a Gmail label for cleanup."""
        if label_id and label_id not in self.gmail_labels:
            self.gmail_labels.append(label_id)

    def track_spreadsheet(self, spreadsheet_id: str) -> None:
        """Track a Google Spreadsheet for cleanup (deleted via Drive API)."""
        if spreadsheet_id and spreadsheet_id not in self.spreadsheets:
            self.spreadsheets.append(spreadsheet_id)

    def get_summary(self) -> dict[str, int]:
        """Get a summary of tracked resources."""
        return {
            "calendar_events": len(self.calendar_events),
            "gmail_filters": len(self.gmail_filters),
            "gmail_labels": len(self.gmail_labels),
            "drive_files": len(self.drive_files),
            "spreadsheets": len(self.spreadsheets),
            "photos_albums": len(self.photos_albums),
            "docs": len(self.docs),
            "forms": len(self.forms),
            "presentations": len(self.presentations),
            "cleanup_errors": len(self._cleanup_errors),
        }

    def get_manual_cleanup_needed(self) -> dict[str, list[str]]:
        """Get resources that require manual cleanup (no delete API available)."""
        return {
            "photos_albums": self.photos_albums.copy(),
            "docs": self.docs.copy(),
            "forms": self.forms.copy(),
            "presentations": self.presentations.copy(),
        }


# Global tracker instance - shared across test session
_cleanup_tracker: ResourceCleanupTracker | None = None


def get_cleanup_tracker() -> ResourceCleanupTracker:
    """Get or create the global cleanup tracker."""
    global _cleanup_tracker
    if _cleanup_tracker is None:
        _cleanup_tracker = ResourceCleanupTracker()
    return _cleanup_tracker


async def _cleanup_resources(client) -> dict[str, Any]:
    """Clean up all tracked resources using MCP tools.

    Returns a summary of cleanup operations performed.
    """
    tracker = get_cleanup_tracker()
    results = {
        "calendar_events_deleted": 0,
        "gmail_filters_deleted": 0,
        "gmail_labels_deleted": 0,
        "drive_files_deleted": 0,
        "spreadsheets_deleted": 0,
        "errors": [],
    }

    # Clean up calendar events
    if tracker.calendar_events:
        print(f"\n🧹 Cleaning up {len(tracker.calendar_events)} calendar event(s)...")
        for event_id in tracker.calendar_events:
            try:
                await client.call_tool(
                    "delete_event",
                    {"user_google_email": TEST_EMAIL, "event_id": event_id},
                )
                results["calendar_events_deleted"] += 1
            except Exception as e:
                error = {"type": "calendar_event", "id": event_id, "error": str(e)}
                results["errors"].append(error)
                tracker._cleanup_errors.append(error)

    # Clean up Gmail filters
    if tracker.gmail_filters:
        print(f"🧹 Cleaning up {len(tracker.gmail_filters)} Gmail filter(s)...")
        for filter_id in tracker.gmail_filters:
            try:
                await client.call_tool(
                    "delete_gmail_filter",
                    {"user_google_email": TEST_EMAIL, "filter_id": filter_id},
                )
                results["gmail_filters_deleted"] += 1
            except Exception as e:
                error = {"type": "gmail_filter", "id": filter_id, "error": str(e)}
                results["errors"].append(error)
                tracker._cleanup_errors.append(error)

    # Clean up Gmail labels
    if tracker.gmail_labels:
        print(f"🧹 Cleaning up {len(tracker.gmail_labels)} Gmail label(s)...")
        for label_id in tracker.gmail_labels:
            try:
                await client.call_tool(
                    "manage_gmail_label",
                    {
                        "user_google_email": TEST_EMAIL,
                        "action": "delete",
                        "label_id": label_id,
                    },
                )
                results["gmail_labels_deleted"] += 1
            except Exception as e:
                error = {"type": "gmail_label", "id": label_id, "error": str(e)}
                results["errors"].append(error)
                tracker._cleanup_errors.append(error)

    # Clean up Drive files
    if tracker.drive_files:
        print(f"🧹 Cleaning up {len(tracker.drive_files)} Drive file(s)...")
        try:
            # Use batch delete for efficiency
            await client.call_tool(
                "manage_drive_files",
                {
                    "user_google_email": TEST_EMAIL,
                    "operation": "delete",
                    "file_ids": tracker.drive_files,
                    "permanent": False,  # Move to trash instead of permanent delete
                },
            )
            results["drive_files_deleted"] = len(tracker.drive_files)
        except Exception as e:
            error = {
                "type": "drive_files",
                "ids": tracker.drive_files,
                "error": str(e),
            }
            results["errors"].append(error)
            tracker._cleanup_errors.append(error)

    # Clean up Spreadsheets (via Drive API - they're Drive files)
    if tracker.spreadsheets:
        print(f"🧹 Cleaning up {len(tracker.spreadsheets)} spreadsheet(s)...")
        try:
            await client.call_tool(
                "manage_drive_files",
                {
                    "user_google_email": TEST_EMAIL,
                    "operation": "delete",
                    "file_ids": tracker.spreadsheets,
                    "permanent": False,  # Move to trash instead of permanent delete
                },
            )
            results["spreadsheets_deleted"] = len(tracker.spreadsheets)
        except Exception as e:
            error = {
                "type": "spreadsheets",
                "ids": tracker.spreadsheets,
                "error": str(e),
            }
            results["errors"].append(error)
            tracker._cleanup_errors.append(error)

    # Report on resources that need manual cleanup
    manual_cleanup = tracker.get_manual_cleanup_needed()
    manual_count = sum(len(ids) for ids in manual_cleanup.values())
    if manual_count > 0:
        print(f"\n⚠️  {manual_count} resource(s) require manual cleanup:")
        for resource_type, ids in manual_cleanup.items():
            if ids:
                print(f"   - {resource_type}: {len(ids)} item(s)")

    return results


def pytest_configure(config):
    """Configure pytest with custom markers and settings."""
    config.addinivalue_line(
        "markers", "auth_required: mark test as requiring authentication"
    )
    config.addinivalue_line(
        "markers", "service(name): mark test as belonging to a specific Google service"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test requiring server"
    )


@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop for async fixtures.

    This is required for session-scoped async fixtures to work properly
    with pytest-asyncio. Without this, session-scoped async fixtures
    will hang because they try to use a function-scoped event loop.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def print_global_test_config():
    """Print test configuration once per session."""
    print_test_configuration()


@pytest.fixture(scope="session")
def cleanup_tracker() -> ResourceCleanupTracker:
    """Session-scoped fixture providing the resource cleanup tracker.

    Usage:
        async def test_create_event(client, cleanup_tracker):
            result = await client.call_tool("create_event", {...})
            event_id = result.content[0].text  # Extract event ID
            cleanup_tracker.track_calendar_event(event_id)
    """
    return get_cleanup_tracker()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def session_cleanup():
    """Automatically clean up tracked resources at end of test session.

    This fixture runs after all tests complete and cleans up any resources
    that were tracked via the cleanup_tracker fixture.

    Set SKIP_TEST_CLEANUP=1 to disable automatic cleanup (useful for debugging).
    """
    # Setup: nothing to do
    yield

    # Teardown: clean up all tracked resources
    if os.getenv("SKIP_TEST_CLEANUP", "").lower() in ("1", "true", "yes"):
        print("\n⏭️  Skipping test cleanup (SKIP_TEST_CLEANUP=1)")
        tracker = get_cleanup_tracker()
        summary = tracker.get_summary()
        total = sum(summary.values()) - summary.get("cleanup_errors", 0)
        if total > 0:
            print(f"   {total} resource(s) left for manual cleanup")
        return

    tracker = get_cleanup_tracker()
    summary = tracker.get_summary()
    total = sum(summary.values()) - summary.get("cleanup_errors", 0)

    if total == 0:
        return  # Nothing to clean up

    print(f"\n{'='*60}")
    print("🧹 TEST SESSION CLEANUP")
    print(f"{'='*60}")
    print(f"   Tracked resources: {summary}")

    try:
        # Create a fresh client for cleanup
        client = await create_test_client(TEST_EMAIL)
        async with client:
            results = await _cleanup_resources(client)
            print(f"\n✅ Cleanup complete:")
            print(f"   - Calendar events deleted: {results['calendar_events_deleted']}")
            print(f"   - Gmail filters deleted: {results['gmail_filters_deleted']}")
            print(f"   - Gmail labels deleted: {results['gmail_labels_deleted']}")
            print(f"   - Drive files deleted: {results['drive_files_deleted']}")
            print(f"   - Spreadsheets deleted: {results['spreadsheets_deleted']}")
            if results["errors"]:
                print(f"   - Errors: {len(results['errors'])}")
                for err in results["errors"][:5]:  # Show first 5 errors
                    print(
                        f"     ⚠️  {err['type']}: {err.get('id', err.get('ids', 'N/A'))}"
                    )
    except Exception as e:
        print(f"\n❌ Cleanup failed: {e}")
        print("   Run scripts/cleanup_test_resources.py for manual cleanup")

    print(f"{'='*60}\n")


@pytest_asyncio.fixture(scope="function")
async def client():
    """Create a function-scoped client connected to the running server.

    NOTE: Changed from session-scoped to function-scoped to fix hanging issue
    with pytest-asyncio event loop scope. Each test gets a fresh client.

    IMPORTANT:
    - Always use the shared connection logic in [`tests/client/base_test_config.create_test_client()`](tests/client/base_test_config.py:90)
      so tests don't depend on a valid local TLS/CA chain.
    - If the server is not running, skip the suite (this is an integration-style test harness).
    """
    from .base_test_config import TEST_EMAIL, create_test_client

    try:
        client_obj = await create_test_client(TEST_EMAIL)
    except Exception as e:
        pytest.skip(f"MCP server not reachable for integration tests: {e}")

    async with client_obj:
        yield client_obj


@pytest.fixture
async def custom_client():
    """Factory fixture for creating clients with custom email addresses."""

    async def _create_client(test_email: str):
        client = await create_test_client(test_email)
        async with client:
            yield client

    return _create_client


# =============================================================================
# Real ID Fixtures from Resource System
# =============================================================================


@pytest_asyncio.fixture
async def real_gmail_message_id(client):
    """Get a real Gmail message ID from resources."""
    real_id = await get_real_gmail_message_id(client)
    return real_id or "fake_message_id_fallback"


@pytest_asyncio.fixture
async def real_gmail_filter_id(client):
    """Get a real Gmail filter ID from resources."""
    real_id = await get_real_gmail_filter_id(client)
    return real_id or "fake_filter_id_fallback"


@pytest_asyncio.fixture
async def real_drive_document_id(client):
    """Get a real Drive document ID from resources."""
    real_id = await get_real_drive_document_id(client)
    return real_id or "fake_document_id_fallback"


@pytest_asyncio.fixture
async def real_drive_folder_id(client):
    """Get a real Drive folder ID from resources."""
    real_id = await get_real_drive_folder_id(client)
    return real_id or "fake_folder_id_fallback"


@pytest_asyncio.fixture
async def real_calendar_event_id(client):
    """Get a real Calendar event ID from resources."""
    real_id = await get_real_calendar_event_id(client)
    return real_id or "fake_event_id_fallback"


@pytest_asyncio.fixture
async def real_photos_album_id(client):
    """Get a real Photos album ID from resources."""
    real_id = await get_real_photos_album_id(client)
    return real_id or "fake_album_id_fallback"


@pytest_asyncio.fixture
async def real_forms_form_id(client):
    """Get a real Forms form ID from resources."""
    real_id = await get_real_forms_form_id(client)
    return real_id or "fake_form_id_fallback"


@pytest_asyncio.fixture
async def real_chat_space_id(client):
    """Get a real Chat space ID from resources."""
    real_id = await get_real_chat_space_id(client)
    return real_id or "fake_space_id_fallback"


# NOTE: Pytest 8+ disallows pytest_plugins in non-top-level conftest.
# pytest-asyncio is already installed and auto-loaded via entry points.


def pytest_collection_modifyitems(config, items):
    """Automatically mark async tests with asyncio marker."""
    for item in items:
        if asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)
