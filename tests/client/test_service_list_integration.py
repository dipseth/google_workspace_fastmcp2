"""
Integration tests for service list resources with actual tool execution.

This file tests the complete flow from resource discovery to tool execution,
verifying that the service list resources correctly map to underlying tools.
"""

import pytest
import asyncio
import json
from typing import Any, Dict, List
from .base_test_config import TEST_EMAIL


@pytest.mark.integration
class TestServiceListToToolMapping:
    """Test that service list resources correctly map to underlying tools."""
    
    @pytest.mark.asyncio
    async def test_gmail_filters_tool_mapping(self, client):
        """Test that Gmail filters resource maps to list_gmail_filters tool."""
        # First, check the tool exists
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        if "list_gmail_filters" in tool_names:
            # Get the service lists
            content = await client.read_resource("service://gmail/lists")
            data = json.loads(content[0].text)
            
            list_types = [lt["name"] for lt in data["list_types"]]
            assert "filters" in list_types
            
            # Try to call the underlying tool directly
            result = await client.call_tool("list_gmail_filters", {
                "user_google_email": TEST_EMAIL
            })
            
            # Compare with resource approach (would need auth context)
            # The resource would internally call the same tool
            assert len(result) > 0
    
    @pytest.mark.asyncio
    async def test_gmail_labels_tool_mapping(self, client):
        """Test that Gmail labels resource maps to list_gmail_labels tool."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        if "list_gmail_labels" in tool_names:
            # Verify service lists include labels
            content = await client.read_resource("service://gmail/lists")
            data = json.loads(content[0].text)
            
            list_types = [lt["name"] for lt in data["list_types"]]
            assert "labels" in list_types
            
            # The labels list type should not have a detail tool
            labels_config = next(lt for lt in data["list_types"] if lt["name"] == "labels")
            assert labels_config["has_detail_view"] is False  # No detail tool for labels
    
    @pytest.mark.asyncio
    async def test_photos_albums_tool_mapping(self, client):
        """Test that Photos albums resource maps to correct tools."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Check both list and detail tools exist
        if "list_photos_albums" in tool_names:
            # Verify service configuration
            content = await client.read_resource("service://photos/lists")
            data = json.loads(content[0].text)
            
            albums_config = next(
                (lt for lt in data["list_types"] if lt["name"] == "albums"),
                None
            )
            assert albums_config is not None
            assert albums_config["has_detail_view"] is True
            
            # The detail tool should be list_album_photos (renamed from get_album_photos)
            if "list_album_photos" in tool_names:
                # Test calling the detail tool directly
                result = await client.call_tool("list_album_photos", {
                    "user_google_email": TEST_EMAIL,
                    "album_id": "test_album_id"
                })
                
                # Should get a response (even if auth error)
                assert len(result) > 0
    
    @pytest.mark.asyncio
    async def test_calendar_tools_mapping(self, client):
        """Test Calendar service tool mappings."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        if "list_calendars" in tool_names and "list_events" in tool_names:
            # Check service configuration
            content = await client.read_resource("service://calendar/lists")
            data = json.loads(content[0].text)
            
            list_type_names = [lt["name"] for lt in data["list_types"]]
            assert "calendars" in list_type_names
            assert "events" in list_type_names
            
            # Events should have id_field (calendar_id)
            events_config = next(lt for lt in data["list_types"] if lt["name"] == "events")
            assert events_config["has_detail_view"] is True  # Has calendar_id parameter
    
    @pytest.mark.asyncio
    async def test_forms_responses_tool_mapping(self, client):
        """Test Forms responses resource with id_field mapping."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        if "list_form_responses" in tool_names:
            # Check service configuration
            content = await client.read_resource("service://forms/lists")
            data = json.loads(content[0].text)
            
            form_responses = next(
                (lt for lt in data["list_types"] if lt["name"] == "form_responses"),
                None
            )
            assert form_responses is not None
            assert form_responses["has_detail_view"] is True  # Has form_id parameter
            
            # Test the tool directly with a form_id
            result = await client.call_tool("list_form_responses", {
                "user_google_email": TEST_EMAIL,
                "form_id": "test_form_id"
            })
            
            # Should get a response
            assert len(result) > 0
    
    @pytest.mark.asyncio
    async def test_sheets_spreadsheets_tool_mapping(self, client):
        """Test Sheets spreadsheets resource mapping."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        if "list_spreadsheets" in tool_names:
            # Check service configuration
            content = await client.read_resource("service://sheets/lists")
            data = json.loads(content[0].text)
            
            spreadsheets = next(
                (lt for lt in data["list_types"] if lt["name"] == "spreadsheets"),
                None
            )
            assert spreadsheets is not None
            
            # Should have detail tool (get_spreadsheet_info)
            if "get_spreadsheet_info" in tool_names:
                assert spreadsheets["has_detail_view"] is True
    
    @pytest.mark.asyncio
    async def test_drive_items_tool_mapping(self, client):
        """Test Drive items resource with folder_id parameter."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        if "list_drive_items" in tool_names:
            # Check service configuration
            content = await client.read_resource("service://drive/lists")
            data = json.loads(content[0].text)
            
            items_config = next(
                (lt for lt in data["list_types"] if lt["name"] == "items"),
                None
            )
            assert items_config is not None
            assert items_config["has_detail_view"] is True  # Has folder_id parameter
            
            # Test with root folder
            result = await client.call_tool("list_drive_items", {
                "user_google_email": TEST_EMAIL,
                "folder_id": "root"
            })
            
            # Should get a response
            assert len(result) > 0
    
    @pytest.mark.asyncio
    async def test_chat_spaces_tool_mapping(self, client):
        """Test Chat spaces resource mapping."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        if "list_spaces" in tool_names:
            # Check service configuration
            content = await client.read_resource("service://chat/lists")
            data = json.loads(content[0].text)
            
            spaces_config = next(
                (lt for lt in data["list_types"] if lt["name"] == "spaces"),
                None
            )
            assert spaces_config is not None
            
            # Should have detail tool (list_messages, renamed from get_messages)
            if "list_messages" in tool_names:
                assert spaces_config["has_detail_view"] is True
    
    @pytest.mark.asyncio
    async def test_docs_documents_tool_mapping(self, client):
        """Test Docs documents resource with folder_id parameter."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        if "list_docs_in_folder" in tool_names:
            # Check service configuration
            content = await client.read_resource("service://docs/lists")
            data = json.loads(content[0].text)
            
            documents = next(
                (lt for lt in data["list_types"] if lt["name"] == "documents"),
                None
            )
            assert documents is not None
            assert documents["has_detail_view"] is True  # Has folder_id parameter
            
            # Should also have get_doc_content as detail tool
            if "get_doc_content" in tool_names:
                # Test calling with a document ID
                result = await client.call_tool("get_doc_content", {
                    "user_google_email": TEST_EMAIL,
                    "document_id": "test_doc_id"
                })
                
                assert len(result) > 0


@pytest.mark.integration
class TestServiceListResourceConsistency:
    """Test consistency between resources and tools."""
    
    @pytest.mark.asyncio
    async def test_all_list_tools_have_resources(self, client):
        """Verify that all list-based tools are exposed through resources."""
        tools = await client.list_tools()
        
        # Find all list-based tools
        list_tools = [
            tool for tool in tools
            if tool.name.startswith("list_") or 
               tool.name in ["get_form", "get_form_response"]  # Some legacy names
        ]
        
        # Map of expected tool to service mappings
        tool_to_service = {
            "list_gmail_filters": ("gmail", "filters"),
            "list_gmail_labels": ("gmail", "labels"),
            "list_form_responses": ("forms", "form_responses"),
            "list_photos_albums": ("photos", "albums"),
            "list_album_photos": ("photos", "albums"),  # Detail tool
            "list_calendars": ("calendar", "calendars"),
            "list_events": ("calendar", "events"),
            "list_spreadsheets": ("sheets", "spreadsheets"),
            "list_drive_items": ("drive", "items"),
            "list_spaces": ("chat", "spaces"),
            "list_messages": ("chat", "spaces"),  # Detail tool
            "list_docs_in_folder": ("docs", "documents"),
        }
        
        # Check that each list tool has a corresponding resource mapping
        for tool in list_tools:
            if tool.name in tool_to_service:
                service, list_type = tool_to_service[tool.name]
                
                # Check that the service lists endpoint exists
                content = await client.read_resource(f"service://{service}/lists")
                assert len(content) > 0
                data = json.loads(content[0].text)
                
                # Check that the list type is in the service
                list_type_names = [lt["name"] for lt in data.get("list_types", [])]
                if tool.name not in ["list_album_photos", "list_messages"]:  # Detail tools
                    assert list_type in list_type_names, f"{list_type} not found for {service}"
    
    @pytest.mark.asyncio
    async def test_structured_response_format(self, client):
        """Test that list tools return structured responses when available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Test tools that should return structured data
        structured_tools = [
            "list_calendars",
            "list_events", 
            "list_spaces",
            "list_messages",
            "list_photos_albums",
            "list_album_photos",
            "list_spreadsheets"
        ]
        
        for tool_name in structured_tools:
            if tool_name in tool_names:
                # Get the tool's output schema if available
                tool = next((t for t in tools if t.name == tool_name), None)
                if tool and hasattr(tool, 'inputSchema'):
                    # Tool has a schema, which means it's been properly configured
                    assert tool.inputSchema is not None
    
    @pytest.mark.asyncio
    async def test_service_discovery_completeness(self, client):
        """Test that all expected services are discoverable."""
        expected_services = [
            "gmail", "forms", "photos", "calendar",
            "sheets", "drive", "chat", "docs"
        ]
        
        # Check each service
        for service in expected_services:
            content = await client.read_resource(f"service://{service}/lists")
            assert len(content) > 0
            
            data = json.loads(content[0].text)
            
            # Should not have an error for valid services
            assert "error" not in data or "not found" not in data.get("error", "").lower()
            assert data["service"] == service
            assert "list_types" in data
            assert len(data["list_types"]) > 0


@pytest.mark.integration
class TestServiceListResourceBehavior:
    """Test the behavior and data flow of service list resources."""
    
    @pytest.mark.asyncio
    async def test_hierarchical_navigation(self, client):
        """Test navigating through the three-level hierarchy."""
        # Level 1: Get service lists
        services = ["gmail", "photos", "calendar"]
        
        for service in services:
            # Get list types for service
            content = await client.read_resource(f"service://{service}/lists")
            assert len(content) > 0
            data = json.loads(content[0].text)
            
            assert "list_types" in data
            
            # Level 2: For each list type, try to get items
            for list_type_info in data["list_types"]:
                list_type = list_type_info["name"]
                
                # Try to get items (will fail without auth but structure should be correct)
                content = await client.read_resource(f"service://{service}/{list_type}")
                assert len(content) > 0
                items_data = json.loads(content[0].text)
                
                # Should have standard fields even if error
                if "error" not in items_data:
                    assert "service" in items_data
                    assert items_data["service"] == service
                    assert "list_type" in items_data or "error" in items_data
    
    @pytest.mark.asyncio
    async def test_error_handling_consistency(self, client):
        """Test that errors are handled consistently across all resource levels."""
        # Test invalid service
        content = await client.read_resource("service://invalid_service/lists")
        data = json.loads(content[0].text)
        assert "error" in data
        assert "available_services" in data
        
        # Test invalid list type
        content = await client.read_resource("service://gmail/invalid_list")
        data = json.loads(content[0].text)
        assert "error" in data
        assert "available_list_types" in data
        
        # Test missing auth context
        content = await client.read_resource("service://gmail/filters")
        data = json.loads(content[0].text)
        assert "error" in data
        # Should indicate auth issue
        assert "email" in data["error"].lower() or "auth" in data["error"].lower()
    
    @pytest.mark.asyncio
    async def test_resource_metadata_presence(self, client):
        """Test that resources include proper metadata."""
        templates = await client.list_resource_templates()
        
        # Find service list templates
        service_templates = [
            t for t in templates 
            if str(t.uriTemplate).startswith("service://")
        ]
        
        # Should have our three template patterns
        assert len(service_templates) >= 3
        
        template_patterns = [str(t.uriTemplate) for t in service_templates]
        assert "service://{service}/lists" in template_patterns
        assert "service://{service}/{list_type}" in template_patterns
        assert "service://{service}/{list_type}/{item_id}" in template_patterns
        
        # Check metadata
        for template in service_templates:
            assert template.name is not None
            assert template.description is not None
            
            # Check for tags if available
            if hasattr(template, '_meta') and template._meta:
                fastmcp_meta = template._meta.get('_fastmcp', {})
                if 'tags' in fastmcp_meta:
                    tags = fastmcp_meta['tags']
                    assert "service" in tags
                    assert "dynamic" in tags


if __name__ == "__main__":
    # Run tests with asyncio
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])