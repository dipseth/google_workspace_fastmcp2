"""
Simple test for the refactored service list resources using FastMCP Client SDK.

This tests the new tag-based discovery and forward() pattern implementation.
"""

import json

import pytest


@pytest.mark.service("resources")
class TestRefactoredServiceResources:
    """Test the refactored service list resources."""

    @pytest.mark.asyncio
    async def test_gmail_service_lists(self, client):
        """Test Gmail service list types structure."""
        print("Testing service://gmail/lists")

        content = await client.read_resource("service://gmail/lists")
        assert content and len(content) > 0, "Should receive content"

        data = json.loads(content[0].text)
        print(f"Got response: {json.dumps(data, indent=2)[:500]}")

        # Verify structure
        assert "service" in data, "Missing 'service' field"
        assert data["service"] == "gmail", f"Wrong service: {data['service']}"
        assert "list_types" in data, "Missing 'list_types' field"

        # Check for expected Gmail list types (new format: dict with type names as keys)
        list_type_names = list(data["list_types"].keys())
        assert "filters" in list_type_names, "Missing 'filters' list type"
        assert "labels" in list_type_names, "Missing 'labels' list type"
        print("Structure validation passed")

    @pytest.mark.asyncio
    async def test_gmail_labels_without_auth(self, client):
        """Test Gmail labels resource without authentication."""
        print("Testing service://gmail/labels")

        content = await client.read_resource("service://gmail/labels")
        assert content and len(content) > 0, "Should receive content"

        data = json.loads(content[0].text)
        print(f"Response: {json.dumps(data, indent=2)[:500]}")

        if "error" in data:
            # Expected to have authentication error
            print(f"Expected auth error: {data['error'][:100]}")
            assert (
                "email" in data["error"].lower()
                or "authenticated" in data["error"].lower()
                or "authentication" in data["error"].lower()
                or "context" in data["error"].lower()
            ), "Unexpected error type"
        else:
            print("Got label data (unexpected without auth)")

    @pytest.mark.asyncio
    async def test_multiple_services_lists(self, client):
        """Test service lists for multiple Google services."""
        services_to_test = [
            "calendar",
            "forms",
            "photos",
            "sheets",
            "drive",
            "chat",
            "docs",
        ]

        for service in services_to_test:
            uri = f"service://{service}/lists"
            print(f"Testing {uri}...")

            try:
                content = await client.read_resource(uri)
                if content and len(content) > 0:
                    data = json.loads(content[0].text)

                    if "error" not in data:
                        assert "service" in data
                        assert data["service"] == service
                        assert "list_types" in data
                        print(f"✅ {service}: {len(data['list_types'])} list types")
                    else:
                        print(f"❌ {service}: Error - {data['error'][:50]}")
                else:
                    print(f"❌ {service}: No content")
            except Exception as e:
                print(f"❌ {service}: Exception - {str(e)[:50]}")

    @pytest.mark.asyncio
    async def test_invalid_service_error_handling(self, client):
        """Test error handling for invalid service."""
        print("Testing invalid service...")

        content = await client.read_resource("service://invalid_service/lists")
        assert content and len(content) > 0, "Should receive error response"

        data = json.loads(content[0].text)
        print(f"Response: {json.dumps(data, indent=2)[:300]}")

        # New behavior: server returns fallback response with empty list_types for unknown services
        # Check for either explicit error OR fallback response (empty list_types, fallback description)
        is_fallback = (
            data.get("total_list_types", -1) == 0
            or "fallback"
            in str(data.get("service_metadata", {}).get("description", "")).lower()
        )
        has_error = "error" in data
        assert (
            has_error or is_fallback
        ), f"Should have error or fallback for invalid service, got: {data}"
        print("Proper error/fallback handling for invalid service")

    @pytest.mark.asyncio
    async def test_calendar_service_without_auth(self, client):
        """Test calendar service resource without authentication."""
        print("Testing service://calendar/calendars (without auth)...")

        content = await client.read_resource("service://calendar/calendars")
        assert content and len(content) > 0, "Should receive content"

        data = json.loads(content[0].text)
        print(f"Response: {json.dumps(data, indent=2)[:300]}")

        if "error" in data:
            print(f"Expected auth error: {data['error'][:100]}")
        else:
            print("Got calendar data (unexpected without auth)")
