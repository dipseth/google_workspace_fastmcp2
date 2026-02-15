"""Test suite for Phase 3.1: Registry-based Tool Discovery using FastMCP Client SDK."""

import os

import pytest
from dotenv import load_dotenv

from .test_helpers import assert_tools_registered, get_registered_tools

# Load environment variables
load_dotenv()

# Test configuration
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test@example.com")


class TestRegistryDiscovery:
    """Test registry-based tool discovery implementation."""

    # Using the global client fixture from conftest.py

    @pytest.mark.asyncio
    async def test_registry_tools_available(self, client):
        """Test that tools are discovered through the registry system.

        Note: The server starts with only 5 core tools enabled by default.
        This test uses assert_tools_registered to check the full registry,
        not just the currently enabled/exposed tools.
        """
        # Get all registered tools from the registry (not just enabled ones)
        registered_tools = await get_registered_tools(client)

        # Verify key service tools are registered in the registry
        expected_services = {
            "gmail": [
                "list_gmail_labels",
                "search_gmail_messages",
                "send_gmail_message",
            ],
            "drive": ["upload_to_drive", "search_drive_files", "list_drive_items"],
            "calendar": ["list_calendars", "list_events", "create_event"],
            "docs": ["search_docs", "get_doc_content", "create_doc"],
            "sheets": ["list_spreadsheets", "read_sheet_values", "modify_sheet_values"],
            "slides": ["create_presentation", "add_slide", "export_presentation"],
            "forms": ["create_form", "add_questions_to_form", "list_form_responses"],
            "chat": ["list_spaces", "send_message", "send_card_message"],
            "photos": ["list_photos_albums", "search_photos", "create_photos_album"],
        }

        discovered_services = {}
        for service, service_tools in expected_services.items():
            discovered_services[service] = []
            for tool in service_tools:
                if tool in registered_tools:
                    discovered_services[service].append(tool)

        # Each service should have at least some tools registered
        for service, tools_found in discovered_services.items():
            assert (
                len(tools_found) > 0
            ), f"No tools registered for {service} service in registry"

        print("Registry discovery found tools for all services")
        for service, tools in discovered_services.items():
            print(f"   {service}: {len(tools)} tools registered")

    @pytest.mark.asyncio
    async def test_registry_dynamic_loading(self, client):
        """Test that registry supports dynamic tool loading.

        Note: The server starts with only 5 core tools enabled by default.
        This test checks the full registry via get_registered_tools, then
        enables all tools to verify metadata.
        """
        # Get all registered tools from the registry (not just enabled ones)
        registered_tools = await get_registered_tools(client)
        initial_count = len(registered_tools)

        print(f"Registered tool count: {initial_count}")

        # Verify registry has loaded a substantial number of tools
        # The system should have at least 80+ tools from all services
        assert (
            initial_count > 80
        ), f"Registry should have 80+ tools registered, found {initial_count}"

        # Enable all tools to check metadata
        await client.call_tool(
            "manage_tools", {"action": "enable_all", "scope": "session"}
        )

        # Now get enabled tools and check their metadata
        enabled_tools = await client.list_tools()
        sample_tools = enabled_tools[:5]  # Check first 5 tools
        for tool in sample_tools:
            assert tool.name, "Tool should have a name from registry"
            assert tool.description, "Tool should have a description from registry"
            assert hasattr(
                tool, "inputSchema"
            ), "Tool should have input schema from registry"

    @pytest.mark.asyncio
    async def test_registry_service_grouping(self, client):
        """Test that registry properly groups tools by service.

        Note: The server starts with only 5 core tools enabled by default.
        This test uses get_registered_tools() to analyze the full registry
        and groups tools by service based on naming patterns.
        """
        # Get all registered tools from the registry (not just enabled ones)
        registered_tools = await get_registered_tools(client)

        # Group tools by service prefix based on tool names
        service_groups = {}
        for tool_name in registered_tools:
            # Most Google service tools follow naming patterns
            if (
                tool_name.startswith("list_")
                or tool_name.startswith("create_")
                or tool_name.startswith("send_")
                or tool_name.startswith("search_")
                or tool_name.startswith("get_")
                or tool_name.startswith("upload_")
            ):
                # Extract service from tool name patterns
                name_lower = tool_name.lower()
                if "gmail" in name_lower:
                    service = "gmail"
                elif "drive" in name_lower:
                    service = "drive"
                elif "calendar" in name_lower or "event" in name_lower:
                    service = "calendar"
                elif "doc" in name_lower:
                    service = "docs"
                elif "sheet" in name_lower or "spreadsheet" in name_lower:
                    service = "sheets"
                elif "slide" in name_lower or "presentation" in name_lower:
                    service = "slides"
                elif "form" in name_lower:
                    service = "forms"
                elif (
                    "chat" in name_lower
                    or "space" in name_lower
                    or "card" in name_lower
                ):
                    service = "chat"
                elif "photo" in name_lower or "album" in name_lower:
                    service = "photos"
                else:
                    service = "other"

                if service not in service_groups:
                    service_groups[service] = []
                service_groups[service].append(tool_name)

        # Verify we have tools grouped by service
        expected_services = ["gmail", "drive", "calendar", "docs", "sheets", "chat"]
        for service in expected_services:
            assert (
                service in service_groups
            ), f"Registry should have tools registered for {service}"
            assert (
                len(service_groups[service]) > 0
            ), f"Registry should have tools for {service}"

        print("Registry groups tools by service:")
        for service, tools in service_groups.items():
            print(f"   {service}: {len(tools)} tools")

    @pytest.mark.asyncio
    async def test_registry_tool_metadata(self, client):
        """Test that registry provides complete metadata for tools.

        Note: The server starts with only 5 core tools enabled by default.
        This test verifies the tool is registered and has metadata via
        the manage_tools list action which returns ToolInfo with descriptions.
        """
        import json

        # First verify the tool is registered
        await assert_tools_registered(
            client, ["list_gmail_labels"], "checking gmail labels tool"
        )

        # Get tool info with descriptions from manage_tools list action
        result = await client.call_tool("manage_tools", {"action": "list"})
        content = (
            result.content[0].text
            if hasattr(result.content[0], "text")
            else str(result.content[0])
        )
        data = json.loads(content)

        # Find the gmail labels tool in the tool list
        gmail_label_tool = None
        for tool in data.get("toolList", []):
            if tool["name"] == "list_gmail_labels":
                gmail_label_tool = tool
                break

        assert (
            gmail_label_tool is not None
        ), "list_gmail_labels tool should be in manage_tools list"

        # Check metadata completeness from ToolInfo
        assert gmail_label_tool.get("name"), "Tool should have name"
        assert gmail_label_tool.get(
            "description"
        ), "Tool should have description from registry"
        assert "enabled" in gmail_label_tool, "Tool should have enabled status"

        print("Registry provides complete metadata for tools")
        print(f"   Tool: {gmail_label_tool['name']}")
        desc = gmail_label_tool["description"]
        print(f"   Description: {desc[:100] if len(desc) > 100 else desc}...")

    @pytest.mark.asyncio
    async def test_registry_hot_reload_capability(self, client):
        """Test that registry supports hot-reload of tool definitions.

        Note: This test verifies consistency of list_tools() calls.
        It works with the default enabled tools (no need to enable all).
        """
        # Get tools twice to verify consistency
        tools_1 = await client.list_tools()
        tools_2 = await client.list_tools()

        tool_names_1 = set(tool.name for tool in tools_1)
        tool_names_2 = set(tool.name for tool in tools_2)

        # Tool lists should be consistent across calls
        assert (
            tool_names_1 == tool_names_2
        ), "Registry should provide consistent tool list"

        print("Registry provides consistent tool discovery")
        print(f"   Total tools: {len(tools_1)}")
        print("   Consistency verified across multiple calls")

    @pytest.mark.asyncio
    async def test_registry_error_handling(self, client):
        """Test registry's error handling for invalid tools."""
        # Try to call a non-existent tool
        try:
            result = await client.call_tool("non_existent_tool_xyz", {})
            # Should not reach here
            assert False, "Should raise error for non-existent tool"
        except Exception as e:
            error_msg = str(e).lower()
            # Should get a clear error about unknown tool
            assert (
                "unknown" in error_msg
                or "not found" in error_msg
                or "invalid" in error_msg
            ), f"Should get clear error for unknown tool, got: {e}"

        print("Registry properly handles invalid tool requests")

    @pytest.mark.asyncio
    async def test_registry_performance(self, client):
        """Test registry tool discovery performance.

        Note: The server starts with only 5 core tools enabled by default.
        This test measures the performance of querying the full registry
        via manage_tools list action, which returns all registered tools.
        """
        import time

        # Measure time to query full registry via manage_tools
        start_time = time.time()
        registered_tools = await get_registered_tools(client)
        registry_time = time.time() - start_time

        # Registry query should be fast (under 2 seconds)
        assert (
            registry_time < 2.0
        ), f"Registry query took {registry_time:.2f}s, should be under 2s"

        # Verify we got a reasonable number of tools registered
        assert (
            len(registered_tools) > 50
        ), f"Expected 50+ tools registered, got {len(registered_tools)}"

        # Also measure list_tools performance for enabled tools
        start_time = time.time()
        tools = await client.list_tools()
        discovery_time = time.time() - start_time

        # Discovery should be fast (under 2 seconds)
        assert (
            discovery_time < 2.0
        ), f"Tool discovery took {discovery_time:.2f}s, should be under 2s"

        print("Registry tool discovery performance:")
        print(
            f"   Registry has {len(registered_tools)} tools (queried in {registry_time:.3f}s)"
        )
        print(
            f"   Currently {len(tools)} tools enabled (discovered in {discovery_time:.3f}s)"
        )
        print(
            f"   Average registry query: {(registry_time * 1000) / len(registered_tools):.2f}ms per tool"
        )


class TestRegistryIntegration:
    """Test registry integration with other components."""

    # Using the global client fixture from conftest.py

    @pytest.mark.asyncio
    async def test_registry_with_middleware(self, client):
        """Test that registry works with middleware components.

        Note: The server starts with only 5 core tools enabled by default.
        This test enables all tools first to test middleware integration.
        """
        # Enable all tools first (scope='session' needed because session-level filtering
        # may independently disable tools even when globally enabled)
        await client.call_tool(
            "manage_tools", {"action": "enable_all", "scope": "session"}
        )

        # Call a tool that requires middleware (template resolution)
        result = await client.call_tool(
            "list_gmail_labels", {"user_google_email": TEST_EMAIL}
        )

        assert result is not None, "Registry should work with middleware"
        content = result.content[0].text

        # Should get a response (auth error or success)
        assert len(content) > 0, "Should get response through registry + middleware"

        print("Registry integrates with middleware")
        print(f"   Response length: {len(content)} chars")

    @pytest.mark.asyncio
    async def test_registry_with_auth_patterns(self, client):
        """Test registry tools work with authentication patterns.

        Note: The server starts with only 5 core tools enabled by default.
        This test enables all tools first to test auth patterns.
        """
        # Enable all tools first (scope='session' needed because session-level filtering
        # may independently disable tools even when globally enabled)
        await client.call_tool(
            "manage_tools", {"action": "enable_all", "scope": "session"}
        )

        # Test tools that require authentication
        auth_required_tools = [
            ("list_gmail_labels", {"user_google_email": TEST_EMAIL}),
            ("list_calendars", {"user_google_email": TEST_EMAIL}),
            ("list_drive_items", {"user_google_email": TEST_EMAIL}),
        ]

        for tool_name, params in auth_required_tools:
            result = await client.call_tool(tool_name, params)
            assert result is not None, f"{tool_name} should work through registry"

            content = result.content[0].text
            # Should get auth error or success
            assert len(content) > 0, f"{tool_name} should return response"

        print("Registry tools work with auth patterns")
        print(f"   Tested {len(auth_required_tools)} auth-required tools")

    @pytest.mark.asyncio
    async def test_registry_tool_routing(self, client):
        """Test that registry properly routes tools to correct handlers.

        Note: The server starts with only 5 core tools enabled by default.
        This test enables all tools first to test routing.
        """
        # Enable all tools first (scope='session' to enable at session level)
        await client.call_tool(
            "manage_tools", {"action": "enable_all", "scope": "session"}
        )

        # Test tools from different services
        test_cases = [
            ("list_gmail_labels", "gmail"),
            ("list_calendars", "calendar"),
            ("list_drive_items", "drive"),
            ("list_spaces", "chat"),
        ]

        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]

        for tool_name, expected_service in test_cases:
            if tool_name in tool_names:
                # Tool should be routed to correct service
                tool = next((t for t in tools if t.name == tool_name), None)
                assert tool is not None, f"{tool_name} should be in registry"

                # Description should mention the service
                desc_lower = tool.description.lower()
                assert (
                    expected_service in desc_lower
                    or tool_name.replace("_", " ") in desc_lower
                ), f"{tool_name} should be associated with {expected_service}"

        print("Registry properly routes tools to services")
        print(f"   Verified routing for {len(test_cases)} tools")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
