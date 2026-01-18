#!/usr/bin/env python3
"""Clean up orphaned test resources from Google Workspace.

This script finds and deletes resources created by tests that match known
test patterns. It's designed to be run manually or on a schedule to clean
up resources that weren't cleaned up during test runs.

Usage:
    # Preview what would be deleted (dry run - default)
    python scripts/cleanup_test_resources.py

    # Actually delete resources
    python scripts/cleanup_test_resources.py --execute

    # Clean specific resource types
    python scripts/cleanup_test_resources.py --execute --calendar --gmail-filters

    # Use custom email
    python scripts/cleanup_test_resources.py --email user@example.com

Environment Variables:
    TEST_EMAIL_ADDRESS: Google account email to use for cleanup
    MCP_SERVER_URL: MCP server URL (default: http://localhost:8002/mcp)
"""

import argparse
import asyncio
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


# Test resource patterns - resources matching these are candidates for cleanup
TEST_PATTERNS = {
    "calendar_events": [
        r"^Test Event",
        r"^All Day Test Event",
        r"^Meeting with Team",
        r"^Event with Attachments",
        r"Bulk Test Event",
        r"^Legacy Mode Test Event",
        r"^MCP Test",
        r"^🎈",  # Emoji prefixes used in bulk tests
        r"^🎉",
        r"^🎯",
    ],
    "gmail_filters": [
        r"@starbucks-test-",
        r"@starbucks-retro-",
        r"@starbucks-complex-",
        r"@example-perf-",
        r"@starbucks-scenario-",
        r"-test-\d{10,}",  # timestamp patterns
    ],
    "gmail_labels": [
        r"^Test Label",
        r"^MCP Test",
    ],
    "drive_files": [
        r"^Test Document",
        r"^Test Form",
        r"^Test Presentation",
        r"^Shared Test Presentation",
        r"^Test Album",
    ],
}


@dataclass
class CleanupResult:
    """Results from cleanup operation."""

    resource_type: str
    found: int = 0
    deleted: int = 0
    errors: list[str] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)


async def create_cleanup_client(email: str):
    """Create an MCP client for cleanup operations."""
    from tests.client.base_test_config import create_test_client

    return await create_test_client(email)


def matches_test_pattern(text: str | None, patterns: list[str]) -> bool:
    """Check if text matches any of the test patterns."""
    if not text:
        return False
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def parse_mcp_response(response) -> dict | list | str:
    """Parse MCP tool response into usable data.

    Handles JSON responses from MCP tools. Falls back to ast.literal_eval
    for Python repr format, then returns raw string if parsing fails.
    """
    import json

    if not response or not response.content:
        return {}

    content = response.content[0]
    text = content.text if hasattr(content, "text") else str(content)

    # Try to parse as JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # If not JSON, it might be a Python repr - try ast.literal_eval
        import ast

        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return text


async def find_test_calendar_events(client, email: str) -> CleanupResult:
    """Find calendar events matching test patterns."""
    result = CleanupResult(resource_type="calendar_events")

    try:
        # Search for events in the past 90 days and next 90 days
        time_min = (datetime.utcnow() - timedelta(days=90)).isoformat() + "Z"
        time_max = (datetime.utcnow() + timedelta(days=90)).isoformat() + "Z"

        response = await client.call_tool(
            "list_events",
            {
                "user_google_email": email,
                "time_min": time_min,
                "time_max": time_max,
                "max_results": 500,
            },
        )

        data = parse_mcp_response(response)
        if isinstance(data, dict):
            # EventListResponse has "events" field
            events = data.get("events", data.get("items", []))
            if isinstance(events, list):
                for event in events:
                    if not isinstance(event, dict):
                        continue
                    summary = event.get("summary", "")
                    if matches_test_pattern(summary, TEST_PATTERNS["calendar_events"]):
                        # Handle both nested and flat start time formats
                        start = event.get("start")
                        if isinstance(start, dict):
                            start_time = start.get("dateTime", start.get("date"))
                        else:
                            start_time = start  # Already a string
                        result.items.append(
                            {
                                "id": event.get("id"),
                                "summary": summary,
                                "start": start_time,
                            }
                        )

        result.found = len(result.items)

    except Exception as e:
        result.errors.append(f"Error listing calendar events: {e}")

    return result


async def find_test_gmail_filters(client, email: str) -> CleanupResult:
    """Find Gmail filters matching test patterns."""
    result = CleanupResult(resource_type="gmail_filters")

    try:
        response = await client.call_tool(
            "list_gmail_filters",
            {"user_google_email": email},
        )

        data = parse_mcp_response(response)
        if isinstance(data, dict):
            filters = data.get("filters", data.get("items", []))
            if isinstance(filters, list):
                for f in filters:
                    criteria = f.get("criteria", {})
                    from_addr = criteria.get("from", "")
                    if matches_test_pattern(from_addr, TEST_PATTERNS["gmail_filters"]):
                        result.items.append(
                            {
                                "id": f.get("id"),
                                "criteria": criteria,
                            }
                        )

        result.found = len(result.items)

    except Exception as e:
        result.errors.append(f"Error listing Gmail filters: {e}")

    return result


async def find_test_gmail_labels(client, email: str) -> CleanupResult:
    """Find Gmail labels matching test patterns."""
    result = CleanupResult(resource_type="gmail_labels")

    try:
        response = await client.call_tool(
            "list_gmail_labels",
            {"user_google_email": email},
        )

        data = parse_mcp_response(response)
        if isinstance(data, dict):
            labels = data.get("labels", data.get("items", []))
            if isinstance(labels, list):
                for label in labels:
                    name = label.get("name", "")
                    # Only match user-created labels (not system labels)
                    label_type = label.get("type", "user")
                    if label_type == "user" and matches_test_pattern(
                        name, TEST_PATTERNS["gmail_labels"]
                    ):
                        result.items.append(
                            {
                                "id": label.get("id"),
                                "name": name,
                            }
                        )

        result.found = len(result.items)

    except Exception as e:
        result.errors.append(f"Error listing Gmail labels: {e}")

    return result


async def find_test_drive_files(client, email: str) -> CleanupResult:
    """Find Drive files matching test patterns."""
    result = CleanupResult(resource_type="drive_files")

    try:
        # Search for files with test-related names using search_drive_files
        response = await client.call_tool(
            "search_drive_files",
            {
                "user_google_email": email,
                "query": "name contains 'Test' or name contains 'MCP'",
                "page_size": 100,
            },
        )

        data = parse_mcp_response(response)
        if isinstance(data, dict):
            # DriveSearchResponse has "results" field
            files = data.get("results", data.get("files", data.get("items", [])))
            if isinstance(files, list):
                for f in files:
                    name = f.get("name", "")
                    if matches_test_pattern(name, TEST_PATTERNS["drive_files"]):
                        result.items.append(
                            {
                                "id": f.get("id"),
                                "name": name,
                                "mimeType": f.get("mimeType"),
                            }
                        )

        result.found = len(result.items)

    except Exception as e:
        result.errors.append(f"Error listing Drive files: {e}")

    return result


async def delete_calendar_events(
    client, email: str, event_ids: list[str]
) -> tuple[int, list[str]]:
    """Delete calendar events by ID."""
    deleted = 0
    errors = []

    for event_id in event_ids:
        try:
            await client.call_tool(
                "delete_event",
                {"user_google_email": email, "event_id": event_id},
            )
            deleted += 1
        except Exception as e:
            errors.append(f"Failed to delete event {event_id}: {e}")

    return deleted, errors


async def delete_gmail_filters(
    client, email: str, filter_ids: list[str]
) -> tuple[int, list[str]]:
    """Delete Gmail filters by ID."""
    deleted = 0
    errors = []

    for filter_id in filter_ids:
        try:
            await client.call_tool(
                "delete_gmail_filter",
                {"user_google_email": email, "filter_id": filter_id},
            )
            deleted += 1
        except Exception as e:
            errors.append(f"Failed to delete filter {filter_id}: {e}")

    return deleted, errors


async def delete_gmail_labels(
    client, email: str, label_ids: list[str]
) -> tuple[int, list[str]]:
    """Delete Gmail labels by ID."""
    deleted = 0
    errors = []

    for label_id in label_ids:
        try:
            await client.call_tool(
                "manage_gmail_label",
                {"user_google_email": email, "action": "delete", "label_id": label_id},
            )
            deleted += 1
        except Exception as e:
            errors.append(f"Failed to delete label {label_id}: {e}")

    return deleted, errors


async def delete_drive_files(
    client, email: str, file_ids: list[str]
) -> tuple[int, list[str]]:
    """Delete Drive files by ID (moves to trash)."""
    errors = []

    try:
        await client.call_tool(
            "manage_drive_files",
            {
                "user_google_email": email,
                "operation": "delete",
                "file_ids": file_ids,
                "permanent": False,
            },
        )
        return len(file_ids), errors
    except Exception as e:
        errors.append(f"Failed to delete files: {e}")
        return 0, errors


async def run_cleanup(
    email: str,
    execute: bool = False,
    calendar: bool = True,
    gmail_filters: bool = True,
    gmail_labels: bool = True,
    drive: bool = True,
) -> dict:
    """Run the cleanup process."""
    results = {}
    print(f"\n{'='*60}")
    print("🧹 TEST RESOURCE CLEANUP")
    print(f"{'='*60}")
    print(f"   Email: {email}")
    print(
        f"   Mode: {'EXECUTE (will delete)' if execute else 'DRY RUN (preview only)'}"
    )
    print(
        f"   Resources: calendar={calendar}, gmail_filters={gmail_filters}, gmail_labels={gmail_labels}, drive={drive}"
    )
    print()

    try:
        client = await create_cleanup_client(email)
        async with client:
            # Find test resources
            if calendar:
                print("📅 Searching for test calendar events...")
                cal_result = await find_test_calendar_events(client, email)
                results["calendar"] = cal_result
                print(f"   Found: {cal_result.found} event(s)")
                if cal_result.items:
                    for item in cal_result.items[:5]:
                        print(
                            f"     - {item.get('summary', 'N/A')} ({item.get('id', 'N/A')[:20]}...)"
                        )
                    if len(cal_result.items) > 5:
                        print(f"     ... and {len(cal_result.items) - 5} more")
                if cal_result.errors:
                    print(f"   Errors: {cal_result.errors}")

            if gmail_filters:
                print("\n📧 Searching for test Gmail filters...")
                filter_result = await find_test_gmail_filters(client, email)
                results["gmail_filters"] = filter_result
                print(f"   Found: {filter_result.found} filter(s)")
                if filter_result.items:
                    for item in filter_result.items[:5]:
                        criteria = item.get("criteria", {})
                        print(
                            f"     - from:{criteria.get('from', 'N/A')} ({item.get('id', 'N/A')[:20]}...)"
                        )
                    if len(filter_result.items) > 5:
                        print(f"     ... and {len(filter_result.items) - 5} more")
                if filter_result.errors:
                    print(f"   Errors: {filter_result.errors}")

            if gmail_labels:
                print("\n🏷️  Searching for test Gmail labels...")
                label_result = await find_test_gmail_labels(client, email)
                results["gmail_labels"] = label_result
                print(f"   Found: {label_result.found} label(s)")
                if label_result.items:
                    for item in label_result.items[:5]:
                        print(
                            f"     - {item.get('name', 'N/A')} ({item.get('id', 'N/A')[:20]}...)"
                        )
                    if len(label_result.items) > 5:
                        print(f"     ... and {len(label_result.items) - 5} more")
                if label_result.errors:
                    print(f"   Errors: {label_result.errors}")

            if drive:
                print("\n📁 Searching for test Drive files...")
                drive_result = await find_test_drive_files(client, email)
                results["drive"] = drive_result
                print(f"   Found: {drive_result.found} file(s)")
                if drive_result.items:
                    for item in drive_result.items[:5]:
                        print(
                            f"     - {item.get('name', 'N/A')} ({item.get('id', 'N/A')[:20]}...)"
                        )
                    if len(drive_result.items) > 5:
                        print(f"     ... and {len(drive_result.items) - 5} more")
                if drive_result.errors:
                    print(f"   Errors: {drive_result.errors}")

            # Execute deletion if requested
            if execute:
                print(f"\n{'='*60}")
                print("🗑️  DELETING RESOURCES")
                print(f"{'='*60}")

                if calendar and results.get("calendar") and results["calendar"].items:
                    event_ids = [item["id"] for item in results["calendar"].items]
                    deleted, errors = await delete_calendar_events(
                        client, email, event_ids
                    )
                    results["calendar"].deleted = deleted
                    results["calendar"].errors.extend(errors)
                    print(f"   Calendar events deleted: {deleted}/{len(event_ids)}")

                if (
                    gmail_filters
                    and results.get("gmail_filters")
                    and results["gmail_filters"].items
                ):
                    filter_ids = [item["id"] for item in results["gmail_filters"].items]
                    deleted, errors = await delete_gmail_filters(
                        client, email, filter_ids
                    )
                    results["gmail_filters"].deleted = deleted
                    results["gmail_filters"].errors.extend(errors)
                    print(f"   Gmail filters deleted: {deleted}/{len(filter_ids)}")

                if (
                    gmail_labels
                    and results.get("gmail_labels")
                    and results["gmail_labels"].items
                ):
                    label_ids = [item["id"] for item in results["gmail_labels"].items]
                    deleted, errors = await delete_gmail_labels(
                        client, email, label_ids
                    )
                    results["gmail_labels"].deleted = deleted
                    results["gmail_labels"].errors.extend(errors)
                    print(f"   Gmail labels deleted: {deleted}/{len(label_ids)}")

                if drive and results.get("drive") and results["drive"].items:
                    file_ids = [item["id"] for item in results["drive"].items]
                    deleted, errors = await delete_drive_files(client, email, file_ids)
                    results["drive"].deleted = deleted
                    results["drive"].errors.extend(errors)
                    print(f"   Drive files deleted: {deleted}/{len(file_ids)}")
            else:
                print(f"\n{'='*60}")
                print("ℹ️  DRY RUN COMPLETE - No resources were deleted")
                print("   Run with --execute to actually delete resources")
                print(f"{'='*60}")

    except Exception as e:
        print(f"\n❌ Cleanup failed: {e}")
        raise

    # Summary
    print(f"\n{'='*60}")
    print("📊 SUMMARY")
    print(f"{'='*60}")
    total_found = sum(r.found for r in results.values() if hasattr(r, "found"))
    total_deleted = sum(r.deleted for r in results.values() if hasattr(r, "deleted"))
    total_errors = sum(len(r.errors) for r in results.values() if hasattr(r, "errors"))
    print(f"   Total found: {total_found}")
    print(f"   Total deleted: {total_deleted}")
    print(f"   Total errors: {total_errors}")
    print(f"{'='*60}\n")

    return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Clean up orphaned test resources from Google Workspace",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete resources (default is dry run)",
    )
    parser.add_argument(
        "--email",
        default=os.getenv("TEST_EMAIL_ADDRESS", "test_example@gmail.com"),
        help="Google account email to use",
    )
    parser.add_argument(
        "--calendar",
        action="store_true",
        default=None,
        help="Clean up calendar events",
    )
    parser.add_argument(
        "--gmail-filters",
        action="store_true",
        default=None,
        help="Clean up Gmail filters",
    )
    parser.add_argument(
        "--gmail-labels",
        action="store_true",
        default=None,
        help="Clean up Gmail labels",
    )
    parser.add_argument(
        "--drive",
        action="store_true",
        default=None,
        help="Clean up Drive files",
    )

    args = parser.parse_args()

    # If no specific resources requested, clean all
    if (
        args.calendar is None
        and args.gmail_filters is None
        and args.gmail_labels is None
        and args.drive is None
    ):
        args.calendar = True
        args.gmail_filters = True
        args.gmail_labels = True
        args.drive = True
    else:
        args.calendar = args.calendar or False
        args.gmail_filters = args.gmail_filters or False
        args.gmail_labels = args.gmail_labels or False
        args.drive = args.drive or False

    asyncio.run(
        run_cleanup(
            email=args.email,
            execute=args.execute,
            calendar=args.calendar,
            gmail_filters=args.gmail_filters,
            gmail_labels=args.gmail_labels,
            drive=args.drive,
        )
    )


if __name__ == "__main__":
    main()
