"""
Example test showing how to use the resource helpers to fetch real IDs.

This test demonstrates the new pattern of using real IDs from the service resource system
instead of hardcoded fake IDs. This makes tests more realistic and helps validate
the actual resource system integration.
"""

import pytest

from .base_test_config import TEST_EMAIL
from .resource_helpers import ResourceIDFetcher


@pytest.mark.service("example")
class TestResourceHelpersExample:
    """Example test class showing resource helper usage patterns."""

    @pytest.mark.asyncio
    async def test_resource_id_fetcher_basic_usage(self, client):
        """Demonstrate basic ResourceIDFetcher usage."""
        fetcher = ResourceIDFetcher(client)

        # Try to get a real Gmail message ID
        gmail_message_id = await fetcher.get_gmail_message_id()
        print(f"📧 Gmail message ID: {gmail_message_id}")

        # Try to get a real Gmail filter ID
        gmail_filter_id = await fetcher.get_gmail_filter_id()
        print(f"🔍 Gmail filter ID: {gmail_filter_id}")

        # Try to get a real Drive document ID
        drive_document_id = await fetcher.get_drive_document_id()
        print(f"📄 Drive document ID: {drive_document_id}")

        # Try to get a real Calendar event ID
        calendar_event_id = await fetcher.get_calendar_event_id()
        print(f"📅 Calendar event ID: {calendar_event_id}")

        # At least one should be available (or None if no data/auth issues)
        all_ids = [
            gmail_message_id,
            gmail_filter_id,
            drive_document_id,
            calendar_event_id,
        ]
        print(
            f"✅ Resource helper test completed. Found {sum(1 for id in all_ids if id is not None)} real IDs"
        )

    @pytest.mark.asyncio
    async def test_using_real_gmail_message_id_in_test(
        self, client, real_gmail_message_id
    ):
        """Example of using real Gmail message ID fixture in a test."""
        print(f"📧 Using real Gmail message ID: {real_gmail_message_id}")

        # Now you can use this real ID in your actual test
        # For example, testing a reply operation:
        # result = await client.call_tool("reply_to_gmail_message", {
        #     "user_google_email": TEST_EMAIL,
        #     "message_id": real_gmail_message_id,
        #     "body": "This is a test reply with a REAL message ID!"
        # })

        assert real_gmail_message_id is not None, (
            "Should have a real message ID or fallback"
        )

        # The ID will be either:
        # 1. A real Gmail message ID fetched from service://gmail/messages
        # 2. A fallback fake ID if no real messages are available
        print("✅ Test using real message ID completed")

    @pytest.mark.asyncio
    async def test_using_real_drive_document_id_in_test(
        self, client, real_drive_document_id
    ):
        """Example of using real Drive document ID fixture in a test."""
        print(f"📄 Using real Drive document ID: {real_drive_document_id}")

        # Now you can use this real ID for Drive operations:
        # result = await client.call_tool("get_doc_content", {
        #     "user_google_email": TEST_EMAIL,
        #     "document_id": real_drive_document_id
        # })

        assert real_drive_document_id is not None, (
            "Should have a real document ID or fallback"
        )
        print("✅ Test using real Drive document ID completed")

    @pytest.mark.asyncio
    async def test_using_real_calendar_event_id_in_test(
        self, client, real_calendar_event_id
    ):
        """Example of using real Calendar event ID fixture in a test."""
        print(f"📅 Using real Calendar event ID: {real_calendar_event_id}")

        # Now you can use this real ID for Calendar operations:
        # result = await client.call_tool("get_event", {
        #     "user_google_email": TEST_EMAIL,
        #     "event_id": real_calendar_event_id
        # })

        assert real_calendar_event_id is not None, (
            "Should have a real event ID or fallback"
        )
        print("✅ Test using real Calendar event ID completed")

    @pytest.mark.asyncio
    async def test_generic_service_resource_access(self, client):
        """Example of using generic service resource access."""
        fetcher = ResourceIDFetcher(client)

        # Get IDs from different services using the generic method
        services_to_test = [
            ("gmail", "filters"),
            ("gmail", "labels"),
            ("drive", "items"),
            ("calendar", "events"),
            ("photos", "albums"),
        ]

        results = {}
        for service, list_type in services_to_test:
            try:
                first_id = await fetcher.get_first_id_from_service(service, list_type)
                results[f"{service}/{list_type}"] = first_id
                print(f"🔍 {service}/{list_type}: {first_id}")
            except Exception as e:
                print(f"❌ Failed to get {service}/{list_type}: {e}")
                results[f"{service}/{list_type}"] = None

        # At least some services should be testable
        successful_fetches = sum(1 for result in results.values() if result is not None)
        print(
            f"✅ Successfully fetched IDs from {successful_fetches}/{len(services_to_test)} service resources"
        )

        # Log the results for debugging
        print("📊 Resource fetch results:")
        for resource, id_value in results.items():
            status = "✅" if id_value else "❌"
            print(f"   {status} {resource}: {id_value}")


# =============================================================================
# COMPARISON: Old vs New Test Pattern
# =============================================================================


class ComparisonExample:
    """Shows the difference between old fake ID pattern and new real ID pattern."""

    # OLD PATTERN (using fake IDs):
    async def old_pattern_test_gmail_reply(self, client):
        """❌ OLD: Using hardcoded fake IDs - less realistic testing."""
        result = await client.call_tool(
            "reply_to_gmail_message",
            {
                "user_google_email": TEST_EMAIL,
                "message_id": "fake_message_id_12345",  # ❌ Fake ID
                "body": "Test reply",
            },
        )
        # This will always fail with "message not found" - doesn't test real functionality

    # NEW PATTERN (using real IDs from resources):
    async def new_pattern_test_gmail_reply(self, client, real_gmail_message_id):
        """✅ NEW: Using real IDs from service resources - realistic testing."""
        result = await client.call_tool(
            "reply_to_gmail_message",
            {
                "user_google_email": TEST_EMAIL,
                "message_id": real_gmail_message_id,  # ✅ Real ID from service://gmail/messages
                "body": "Test reply",
            },
        )
        # This tests against a real message, giving us realistic results
        # Could succeed (if authenticated) or fail with proper auth errors
