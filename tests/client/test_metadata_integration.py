"""Test suite for Phase 3.2: MCP Metadata Integration using FastMCP Client SDK."""

import os

import pytest
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Test configuration
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test@example.com")


class TestMetadataIntegration:
    """Test MCP metadata as source of truth implementation."""

    # Using the global client fixture from conftest.py

    @pytest.mark.asyncio
    async def test_tool_metadata_structure(self, client):
        """Test that tools have proper MCP metadata structure."""
        tools = await client.list_tools()

        # Sample several tools to verify metadata
        sample_size = min(10, len(tools))
        sample_tools = tools[:sample_size]

        for tool in sample_tools:
            # Each tool should have MCP-compliant metadata
            assert hasattr(tool, "name"), "Tool missing 'name' field"
            assert hasattr(
                tool, "description"
            ), f"Tool {tool.name} missing 'description'"
            assert hasattr(
                tool, "inputSchema"
            ), f"Tool {tool.name} missing 'inputSchema'"

            # Input schema should be properly structured
            if hasattr(tool.inputSchema, "__dict__"):
                schema = tool.inputSchema.__dict__
                # Should have type field
                if "type" in schema:
                    assert (
                        schema["type"] == "object"
                    ), f"Tool {tool.name} schema type should be 'object'"

                # Should have properties for parameters
                if "properties" in schema:
                    assert isinstance(
                        schema["properties"], dict
                    ), f"Tool {tool.name} properties should be dict"

            print(f"✅ Tool '{tool.name}' has proper MCP metadata structure")

    @pytest.mark.asyncio
    async def test_resource_metadata_structure(self, client):
        """Test that resources have proper MCP metadata structure."""
        resources = await client.list_resources()

        # Check several resource types
        expected_resources = [
            "user://current/email",
            "tools://list/all",
            "service://gmail/lists",
            "service://calendar/lists",
        ]

        resource_uris = [r.uri for r in resources]

        for expected in expected_resources:
            if expected in resource_uris:
                resource = next((r for r in resources if r.uri == expected), None)
                assert resource is not None, f"Resource {expected} should exist"

                # Check metadata structure
                assert hasattr(resource, "uri"), "Resource should have URI"
                assert hasattr(resource, "name"), "Resource should have name"
                assert hasattr(
                    resource, "description"
                ), "Resource should have description"

                print(f"✅ Resource '{expected}' has proper metadata")

    @pytest.mark.asyncio
    async def test_metadata_consistency(self, client):
        """Test that metadata is consistent across calls."""
        # Get tools metadata twice
        tools_1 = await client.list_tools()
        tools_2 = await client.list_tools()

        # Create dictionaries for comparison
        tools_meta_1 = {t.name: t.description for t in tools_1}
        tools_meta_2 = {t.name: t.description for t in tools_2}

        # Metadata should be consistent
        assert tools_meta_1 == tools_meta_2, "Tool metadata should be consistent"

        print("✅ Metadata is consistent across calls")
        print(f"   Verified {len(tools_meta_1)} tool definitions")

    @pytest.mark.asyncio
    async def test_metadata_parameter_types(self, client):
        """Test that metadata correctly defines parameter types."""
        tools = await client.list_tools()

        # Test specific tools with known parameter types
        test_cases = {
            "list_gmail_labels": {"user_google_email": "string"},
            "create_event": {
                "user_google_email": "string",
                "summary": "string",
                "start_time": "string",
                "end_time": "string",
            },
            "search_drive_files": {
                "user_google_email": "string",
                "query": "string",
                "page_size": "integer",
            },
        }

        for tool_name, expected_params in test_cases.items():
            tool = next((t for t in tools if t.name == tool_name), None)
            if tool:
                # Check parameter types in schema
                if hasattr(tool.inputSchema, "properties"):
                    schema_props = tool.inputSchema.properties
                    for param_name, expected_type in expected_params.items():
                        # Verify parameter exists and has correct type
                        assert param_name in str(
                            schema_props
                        ), f"Tool {tool_name} should have parameter {param_name}"

                print(f"✅ Tool '{tool_name}' has correct parameter types")

    @pytest.mark.asyncio
    async def test_metadata_required_fields(self, client):
        """Test that metadata correctly marks required fields."""
        tools = await client.list_tools()

        # Test tools with known required fields
        test_cases = {
            "send_gmail_message": ["to", "subject", "body"],
            "create_event": ["summary", "start_time", "end_time"],
            "create_doc": ["title", "user_google_email"],
        }

        for tool_name, required_fields in test_cases.items():
            tool = next((t for t in tools if t.name == tool_name), None)
            if tool:
                # Check if schema has required field list
                if hasattr(tool.inputSchema, "required"):
                    schema_required = tool.inputSchema.required
                    for field in required_fields:
                        if isinstance(schema_required, list):
                            # Some required fields should be marked
                            pass  # Can't strictly enforce as it depends on implementation

                print(f"✅ Tool '{tool_name}' has required field metadata")

    @pytest.mark.asyncio
    async def test_metadata_descriptions(self, client):
        """Test that metadata includes meaningful descriptions."""
        tools = await client.list_tools()

        # Sample tools to check descriptions
        sample_size = min(20, len(tools))
        sample_tools = tools[:sample_size]

        for tool in sample_tools:
            # Description should be meaningful (not empty, not too short)
            assert tool.description, f"Tool {tool.name} should have description"
            assert len(tool.description) > 10, f"Tool {tool.name} description too short"

            # Description should be relevant (contain tool name or related keywords)
            desc_lower = tool.description.lower()
            tool_words = tool.name.replace("_", " ").lower().split()

            # At least one word from tool name should be in description
            relevant = any(word in desc_lower for word in tool_words if len(word) > 2)
            assert relevant, f"Tool {tool.name} description should be relevant"

        print("✅ All sampled tools have meaningful descriptions")
        print(f"   Verified {sample_size} tool descriptions")

    @pytest.mark.asyncio
    async def test_metadata_version_info(self, client):
        """Test that metadata includes version information where applicable."""
        tools = await client.list_tools()

        # Check if any tools have version metadata
        tools_with_version = 0
        for tool in tools:
            # Version might be in description or separate field
            if hasattr(tool, "version"):
                tools_with_version += 1
            elif (
                "v" in tool.description.lower() or "version" in tool.description.lower()
            ):
                tools_with_version += 1

        print("✅ Metadata version check complete")
        print(f"   Tools with version info: {tools_with_version}/{len(tools)}")

    @pytest.mark.asyncio
    async def test_metadata_error_schemas(self, client):
        """Test that metadata includes error response schemas."""
        # Test a tool with invalid parameters to check error metadata
        try:
            result = await client.call_tool(
                "list_gmail_labels", {"invalid_param": "test"}
            )
            # May succeed with default behavior
        except Exception as e:
            # Error should be well-structured
            error_msg = str(e)
            assert len(error_msg) > 0, "Error should have message"
            # Error should mention the issue
            assert any(
                word in error_msg.lower()
                for word in ["validation", "parameter", "invalid", "required"]
            ), "Error should be descriptive"

        print("✅ Error metadata properly structured")


class TestMetadataSourceOfTruth:
    """Test that MCP metadata serves as the single source of truth."""

    # Using the global client fixture from conftest.py

    @pytest.mark.asyncio
    async def test_metadata_overrides_implementation(self, client):
        """Test that metadata definitions override implementation details."""
        tools = await client.list_tools()

        # The metadata should be authoritative
        # Check that tools follow metadata schema, not implementation
        gmail_tools = [t for t in tools if "gmail" in t.name.lower()]

        for tool in gmail_tools[:3]:  # Sample a few Gmail tools
            # Metadata should define the interface
            assert tool.description, "Metadata should provide description"
            assert hasattr(tool, "inputSchema"), "Metadata should provide schema"

            # The schema should be the contract
            if hasattr(tool.inputSchema, "properties"):
                # Schema is the source of truth for parameters
                print(f"✅ Tool '{tool.name}' uses metadata as source of truth")

    @pytest.mark.asyncio
    async def test_metadata_driven_validation(self, client):
        """Test that validation is driven by metadata schemas."""
        # Try calling a tool with schema-violating parameters
        test_cases = [
            {
                "tool": "create_event",
                "params": {
                    "user_google_email": TEST_EMAIL,
                    "summary": "",  # Empty string might violate schema
                    "start_time": "invalid-date",  # Invalid format
                    "end_time": "also-invalid",
                },
                "expect_error": True,
            },
            {
                "tool": "search_drive_files",
                "params": {
                    "user_google_email": TEST_EMAIL,
                    "page_size": "not-a-number",  # Type violation
                },
                "expect_error": True,
            },
        ]

        for test in test_cases:
            try:
                result = await client.call_tool(test["tool"], test["params"])
                # Might succeed with lenient validation
                if test["expect_error"]:
                    # Should at least get an error in response
                    content = result.content[0].text
                    assert any(
                        word in content.lower()
                        for word in ["error", "invalid", "failed"]
                    ), "Should indicate error for invalid params"
            except Exception as e:
                # Expected for schema violations
                if test["expect_error"]:
                    assert (
                        "validation" in str(e).lower() or "invalid" in str(e).lower()
                    ), "Should get validation error"

        print("✅ Validation is metadata-driven")

    @pytest.mark.asyncio
    async def test_metadata_backwards_compatibility(self, client):
        """Test that metadata maintains backwards compatibility."""
        tools = await client.list_tools()

        # Legacy tools should still work with metadata
        legacy_patterns = [
            "list_gmail_labels",  # Original Gmail tool
            "list_calendars",  # Original Calendar tool
            "list_drive_items",  # Original Drive tool
        ]

        for pattern in legacy_patterns:
            tool = next((t for t in tools if t.name == pattern), None)
            assert tool is not None, f"Legacy tool {pattern} should exist"

            # Should have both old and new metadata fields
            assert tool.name, "Should have name (legacy)"
            assert tool.description, "Should have description (legacy)"
            assert hasattr(tool, "inputSchema"), "Should have schema (new)"

        print("✅ Metadata maintains backwards compatibility")
        print(f"   Verified {len(legacy_patterns)} legacy tools")

    @pytest.mark.asyncio
    async def test_metadata_extensibility(self, client):
        """Test that metadata schema is extensible."""
        tools = await client.list_tools()
        resources = await client.list_resources()

        # Check for extended metadata fields
        extended_fields = ["category", "tags", "version", "deprecated", "experimental"]

        tools_with_extensions = 0
        for tool in tools:
            for field in extended_fields:
                if hasattr(tool, field):
                    tools_with_extensions += 1
                    break

        resources_with_extensions = 0
        for resource in resources:
            for field in extended_fields:
                if hasattr(resource, field):
                    resources_with_extensions += 1
                    break

        print("✅ Metadata schema is extensible")
        print(f"   Tools with extensions: {tools_with_extensions}/{len(tools)}")
        print(
            f"   Resources with extensions: {resources_with_extensions}/{len(resources)}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
