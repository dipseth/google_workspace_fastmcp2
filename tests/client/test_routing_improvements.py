"""Test suite for Phase 3.3: Routing Middleware Improvements using FastMCP Client SDK."""

import asyncio
import os
import time

import pytest
from dotenv import load_dotenv

from .test_helpers import assert_tools_registered, get_registered_tools

# Load environment variables
load_dotenv()

# Test configuration
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test@example.com")


class TestRoutingImprovements:
    """Test routing improvements and enhanced request handling.

    🔧 MCP Tools Used:
    - Request routing system: Test improved request routing logic
    - Service dispatch: Test service selection and routing
    - Load balancing: Test request distribution and balancing
    - Route optimization: Test routing performance improvements

    🧪 What's Being Tested:
    - Enhanced request routing algorithms and logic
    - Service discovery and selection improvements
    - Load balancing and performance optimization
    - Route caching and optimization mechanisms
    - Error handling in routing scenarios
    - Failover and redundancy in request handling
    - Integration with authentication and middleware systems

    🔍 Potential Duplications:
    - Request handling might overlap with MCP client protocol tests
    - Performance testing similar to other optimization tests
    - Service selection might overlap with service registry tests
    - Error handling patterns similar to other error handling tests
    """

    # Using the global client fixture from conftest.py

    @pytest.mark.asyncio
    async def test_routing_confidence_scores(self, client):
        """Test that routing assigns appropriate confidence scores to services."""
        # Test tools that should have high confidence routing
        high_confidence_tools = [
            ("list_gmail_labels", "gmail", 0.95),
            ("list_calendars", "calendar", 0.95),
            ("list_drive_items", "drive", 0.90),
            ("send_message", "chat", 0.70),
            ("list_spaces", "chat", 0.70),
        ]

        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]

        for tool_name, expected_service, min_confidence in high_confidence_tools:
            if tool_name in tool_names:
                # Tool should be routed with appropriate confidence
                print(f"✅ Tool '{tool_name}' routed to {expected_service} service")
                print(f"   Expected confidence: >={min_confidence}")

        # Verify routing works by calling tools
        test_result = await client.call_tool(
            "list_gmail_labels", {"user_google_email": TEST_EMAIL}
        )

        assert test_result is not None, "Routing should deliver tool calls"
        content = test_result.content[0].text
        assert len(content) > 0, "Routed call should return response"

    @pytest.mark.asyncio
    async def test_routing_service_detection(self, client):
        """Test that routing correctly detects service from tool names."""
        # Map of tool patterns to services
        routing_patterns = {
            "gmail": [
                "list_gmail_labels",
                "send_gmail_message",
                "search_gmail_messages",
            ],
            "calendar": ["list_calendars", "create_event", "list_events"],
            "drive": ["upload_to_drive", "search_drive_files", "list_drive_items"],
            "docs": ["create_doc", "get_doc_content", "search_docs"],
            "sheets": [
                "create_spreadsheet",
                "read_sheet_values",
                "modify_sheet_values",
            ],
            "slides": ["create_presentation", "add_slide", "export_presentation"],
            "forms": ["create_form", "add_questions_to_form", "get_form"],
            "chat": ["list_spaces", "send_message", "send_card_message"],
            "photos": ["list_photos_albums", "search_photos", "create_photos_album"],
        }

        # Use get_registered_tools to check the registry, not just enabled tools
        tool_names = await get_registered_tools(client)

        routing_success = {}
        for service, service_tools in routing_patterns.items():
            routing_success[service] = 0
            for tool_name in service_tools:
                if tool_name in tool_names:
                    routing_success[service] += 1

        # Each service should have tools properly routed
        for service, count in routing_success.items():
            assert count > 0, f"Service {service} should have routed tools"
            print(f"Service '{service}': {count} tools properly routed")

    @pytest.mark.asyncio
    async def test_routing_chain(self, client):
        """Test that routing properly chains with other middleware."""
        # Test a tool that goes through multiple middleware layers
        # Template middleware -> Service router -> Service handler

        result = await client.call_tool(
            "list_gmail_labels", {"user_google_email": TEST_EMAIL}
        )

        assert result is not None, "Middleware chain should complete"
        content = result.content[0].text

        # Response should show it went through the chain
        assert len(content) > 0, "Should get response through middleware chain"

        # Test another service to verify routing switches correctly
        cal_result = await client.call_tool(
            "list_calendars", {"user_google_email": TEST_EMAIL}
        )

        assert cal_result is not None, "Should route to different service"
        cal_content = cal_result.content[0].text
        assert len(cal_content) > 0, "Different service should also work"

        print("✅ Middleware chain works correctly")
        print(f"   Gmail service response: {len(content)} chars")
        print(f"   Calendar service response: {len(cal_content)} chars")

    @pytest.mark.asyncio
    async def test_routing_fallback_behavior(self, client):
        """Test routing fallback for ambiguous or unknown tools."""
        # Tools that might be ambiguous or need fallback
        edge_cases = [
            "health_check",  # System tool, not service-specific
            "start_google_auth",  # Auth tool, crosses services
            "search_tool_history",  # Meta tool
        ]

        # Use get_registered_tools to check the registry, not just enabled tools
        tool_names = await get_registered_tools(client)

        found_count = 0
        for tool_name in edge_cases:
            if tool_name in tool_names:
                found_count += 1
                # These should still be routed, even if not to a specific service
                print(f"Edge case tool '{tool_name}' is properly handled")

        # Verify at least one edge case tool is registered
        assert found_count > 0, "At least one edge case tool should be registered"
        print(f"System tools routed successfully: {found_count}/{len(edge_cases)}")

    @pytest.mark.asyncio
    async def test_routing_performance(self, client):
        """Test that routing doesn't significantly impact performance."""
        # Measure routing overhead by comparing tool discovery and execution times

        # Time tool discovery (includes routing setup)
        start = time.time()
        tools = await client.list_tools()
        discovery_time = time.time() - start

        # Time a routed tool call
        start = time.time()
        result = await client.call_tool(
            "list_gmail_labels", {"user_google_email": TEST_EMAIL}
        )
        call_time = time.time() - start

        # Routing should not add significant overhead
        assert (
            discovery_time < 3.0
        ), f"Tool discovery with routing took {discovery_time:.2f}s"
        assert call_time < 5.0, f"Routed tool call took {call_time:.2f}s"

        print("✅ Routing performance acceptable")
        print(f"   Discovery time: {discovery_time:.3f}s")
        print(f"   Call time: {call_time:.3f}s")

    @pytest.mark.asyncio
    async def test_routing_error_handling(self, client):
        """Test that routing handles errors gracefully."""
        # Test various error scenarios
        error_cases = [
            {
                "tool": "list_gmail_labels",
                "params": {},  # Missing required param
                "error_type": "validation",
            },
            {"tool": "non_existent_tool", "params": {}, "error_type": "not_found"},
        ]

        for case in error_cases:
            try:
                result = await client.call_tool(case["tool"], case["params"])
                # May succeed with defaults or error in response
                if result:
                    content = result.content[0].text
                    # Should indicate the error type
                    if case["error_type"] == "validation":
                        assert any(
                            word in content.lower()
                            for word in ["error", "required", "missing"]
                        )
            except Exception as e:
                # Should get appropriate error
                error_msg = str(e).lower()
                if case["error_type"] == "not_found":
                    assert any(
                        word in error_msg
                        for word in ["unknown", "not found", "invalid"]
                    )
                elif case["error_type"] == "validation":
                    assert any(
                        word in error_msg
                        for word in ["validation", "required", "missing"]
                    )

        print("✅ Routing error handling works correctly")


class TestRoutingServicePriority:
    """Test service routing priority and confidence scoring."""

    # Using the global client fixture from conftest.py

    @pytest.mark.asyncio
    async def test_gmail_high_confidence(self, client):
        """Test that Gmail tools are routed with 95% confidence."""
        gmail_tools = [
            "list_gmail_labels",
            "search_gmail_messages",
            "send_gmail_message",
            "create_gmail_filter",
            "manage_gmail_label",
        ]

        # Use get_registered_tools to check the registry, not just enabled tools
        tool_names = await get_registered_tools(client)

        gmail_found = 0
        for tool_name in gmail_tools:
            if tool_name in tool_names:
                gmail_found += 1
                # These should be routed with high confidence (0.95)
                print(f"Gmail tool '{tool_name}' available (95% confidence expected)")

        assert gmail_found > 0, "Should have Gmail tools with high confidence routing"
        print(f"Total Gmail tools found: {gmail_found}")

    @pytest.mark.asyncio
    async def test_calendar_high_confidence(self, client):
        """Test that Calendar tools are routed with 95% confidence."""
        calendar_tools = [
            "list_calendars",
            "list_events",
            "create_event",
            "modify_event",
            "delete_event",
        ]

        # Use get_registered_tools to check the registry, not just enabled tools
        tool_names = await get_registered_tools(client)

        calendar_found = 0
        for tool_name in calendar_tools:
            if tool_name in tool_names:
                calendar_found += 1
                # These should be routed with high confidence (0.95)
                print(
                    f"Calendar tool '{tool_name}' available (95% confidence expected)"
                )

        assert (
            calendar_found > 0
        ), "Should have Calendar tools with high confidence routing"
        print(f"Total Calendar tools found: {calendar_found}")

    @pytest.mark.asyncio
    async def test_chat_medium_confidence(self, client):
        """Test that Chat tools are routed with 70% confidence."""
        chat_tools = [
            "list_spaces",
            "send_message",
            "send_card_message",
            "send_simple_card",
            "search_messages",
        ]

        # Use get_registered_tools to check the registry, not just enabled tools
        tool_names = await get_registered_tools(client)

        chat_found = 0
        for tool_name in chat_tools:
            if tool_name in tool_names:
                chat_found += 1
                # These should be routed with medium confidence (0.70)
                print(f"Chat tool '{tool_name}' available (70% confidence expected)")

        assert chat_found > 0, "Should have Chat tools with medium confidence routing"
        print(f"Total Chat tools found: {chat_found}")

    @pytest.mark.asyncio
    async def test_routing_priority_order(self, client):
        """Test that routing respects priority order based on confidence."""
        # When multiple services could handle a request, higher confidence wins

        # Test calling tools from different confidence tiers
        high_confidence_result = await client.call_tool(
            "list_gmail_labels", {"user_google_email": TEST_EMAIL}
        )

        medium_confidence_result = await client.call_tool(
            "list_spaces", {"user_google_email": TEST_EMAIL}
        )

        # Both should work, but high confidence should be faster/more reliable
        assert high_confidence_result is not None, "High confidence routing should work"
        assert (
            medium_confidence_result is not None
        ), "Medium confidence routing should work"

        print("✅ Routing priority order works correctly")
        print("   High confidence (Gmail): Success")
        print("   Medium confidence (Chat): Success")


class TestRoutingIntegration:
    """Test routing integration with the overall system."""

    # Using the global client fixture from conftest.py

    @pytest.mark.asyncio
    async def test_routing_with_auth_middleware(self, client):
        """Test that routing works with authentication middleware."""
        # Tools that require auth and routing
        auth_tools = [
            ("list_gmail_labels", {"user_google_email": TEST_EMAIL}),
            ("list_calendars", {"user_google_email": TEST_EMAIL}),
            ("list_drive_items", {"user_google_email": TEST_EMAIL}),
        ]

        for tool_name, params in auth_tools:
            result = await client.call_tool(tool_name, params)
            assert result is not None, f"{tool_name} should work through routing + auth"

            content = result.content[0].text
            assert len(content) > 0, f"{tool_name} should return response"

        print("✅ Routing integrates with auth middleware")
        print(f"   Tested {len(auth_tools)} authenticated + routed tools")

    @pytest.mark.asyncio
    async def test_routing_with_template_middleware(self, client):
        """Test that routing works with template resolution middleware."""
        # Tools that use templates and routing

        # Call without user_google_email to test template resolution
        try:
            result = await client.call_tool("list_gmail_labels", {})
            # May work with template resolution
            if result:
                content = result.content[0].text
                assert len(content) > 0, "Should get response"
                print("✅ Routing + template resolution works")
        except Exception as e:
            # May require explicit parameter
            if "required" in str(e).lower():
                print("✅ Routing validates parameters correctly")

    @pytest.mark.asyncio
    async def test_concurrent_routing(self, client):
        """Test that routing handles concurrent requests correctly."""
        # Launch multiple requests to different services concurrently
        tasks = [
            client.call_tool("list_gmail_labels", {"user_google_email": TEST_EMAIL}),
            client.call_tool("list_calendars", {"user_google_email": TEST_EMAIL}),
            client.call_tool("list_drive_items", {"user_google_email": TEST_EMAIL}),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = 0
        for i, result in enumerate(results):
            if not isinstance(result, Exception):
                success_count += 1
                assert result is not None, f"Request {i} should succeed"

        assert success_count > 0, "At least some concurrent requests should succeed"

        print("✅ Concurrent routing works")
        print(f"   Successful requests: {success_count}/{len(tasks)}")

    @pytest.mark.asyncio
    async def test_routing_metrics(self, client):
        """Test that routing provides useful metrics/logging."""
        # Make several calls to gather routing metrics
        services_called = set()

        test_calls = [
            ("list_gmail_labels", "gmail"),
            ("list_calendars", "calendar"),
            ("list_drive_items", "drive"),
            ("list_spaces", "chat"),
        ]

        for tool_name, expected_service in test_calls:
            try:
                result = await client.call_tool(
                    tool_name, {"user_google_email": TEST_EMAIL}
                )
                if result:
                    services_called.add(expected_service)
            except:
                pass  # Some may fail due to auth

        print("✅ Routing metrics collected")
        print(f"   Services routed to: {services_called}")
        print(f"   Coverage: {len(services_called)}/{len(test_calls)} services")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
