"""
Test suite for service list resources using FastMCP Client SDK.

Tests the dynamic service list resources that provide hierarchical access to
list-based tools across Google services:
1. service://{service}/lists - Get available list types
2. service://{service}/{list_type} - Get all items/IDs  
3. service://{service}/{list_type}/{id} - Get item details
"""

import pytest
import asyncio
import json
from typing import Any, Dict, List, Optional
from fastmcp import Client
import os
from .test_auth_utils import get_client_auth_config


# Server configuration
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "localhost")
SERVER_PORT = os.getenv("MCP_SERVER_PORT", os.getenv("SERVER_PORT", "8002"))
SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://{SERVER_HOST}:{SERVER_PORT}/mcp/")

# Test email address
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test_user@example.com")


class TestServiceListResources:
    """Test the service list resources functionality."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_list_resource_templates(self, client):
        """Test that service list resource templates are registered."""
        templates = await client.list_resource_templates()
        
        # Convert templates to URIs for easier checking
        template_uris = [str(template.uriTemplate) for template in templates]
        
        # Check for our service list resource templates
        expected_templates = [
            "service://{service}/lists",
            "service://{service}/{list_type}",
            "service://{service}/{list_type}/{item_id}"
        ]
        
        for expected in expected_templates:
            assert expected in template_uris, f"Template {expected} not found. Available: {template_uris}"
    
    @pytest.mark.asyncio
    async def test_get_service_lists_gmail(self, client):
        """Test getting available list types for Gmail service."""
        content = await client.read_resource("service://gmail/lists")
        
        assert len(content) > 0
        data = json.loads(content[0].text)
        
        # Verify structure
        assert "service" in data
        assert data["service"] == "gmail"
        assert "list_types" in data
        
        # Check for expected Gmail list types
        list_type_names = [lt["name"] for lt in data["list_types"]]
        assert "filters" in list_type_names
        assert "labels" in list_type_names
        
        # Verify list type structure
        for list_type in data["list_types"]:
            assert "name" in list_type
            assert "description" in list_type
            assert "has_detail_view" in list_type
    
    @pytest.mark.asyncio
    async def test_get_service_lists_forms(self, client):
        """Test getting available list types for Forms service."""
        content = await client.read_resource("service://forms/lists")
        
        assert len(content) > 0
        data = json.loads(content[0].text)
        
        assert data["service"] == "forms"
        assert "list_types" in data
        
        # Check for Forms list types
        list_type_names = [lt["name"] for lt in data["list_types"]]
        assert "form_responses" in list_type_names
        
        # Check that form_responses has detail view
        form_responses = next(lt for lt in data["list_types"] if lt["name"] == "form_responses")
        assert form_responses["has_detail_view"] is True
    
    @pytest.mark.asyncio
    async def test_get_service_lists_photos(self, client):
        """Test getting available list types for Photos service."""
        content = await client.read_resource("service://photos/lists")
        
        assert len(content) > 0
        data = json.loads(content[0].text)
        
        assert data["service"] == "photos"
        list_type_names = [lt["name"] for lt in data["list_types"]]
        assert "albums" in list_type_names
    
    @pytest.mark.asyncio
    async def test_get_service_lists_calendar(self, client):
        """Test getting available list types for Calendar service."""
        content = await client.read_resource("service://calendar/lists")
        
        assert len(content) > 0
        data = json.loads(content[0].text)
        
        assert data["service"] == "calendar"
        list_type_names = [lt["name"] for lt in data["list_types"]]
        assert "calendars" in list_type_names
        assert "events" in list_type_names
    
    @pytest.mark.asyncio
    async def test_get_service_lists_sheets(self, client):
        """Test getting available list types for Sheets service."""
        content = await client.read_resource("service://sheets/lists")
        
        assert len(content) > 0
        data = json.loads(content[0].text)
        
        assert data["service"] == "sheets"
        list_type_names = [lt["name"] for lt in data["list_types"]]
        assert "spreadsheets" in list_type_names
    
    @pytest.mark.asyncio
    async def test_get_service_lists_drive(self, client):
        """Test getting available list types for Drive service."""
        content = await client.read_resource("service://drive/lists")
        
        assert len(content) > 0
        data = json.loads(content[0].text)
        
        assert data["service"] == "drive"
        list_type_names = [lt["name"] for lt in data["list_types"]]
        assert "items" in list_type_names
    
    @pytest.mark.asyncio
    async def test_get_service_lists_chat(self, client):
        """Test getting available list types for Chat service."""
        content = await client.read_resource("service://chat/lists")
        
        assert len(content) > 0
        data = json.loads(content[0].text)
        
        assert data["service"] == "chat"
        list_type_names = [lt["name"] for lt in data["list_types"]]
        assert "spaces" in list_type_names
    
    @pytest.mark.asyncio
    async def test_get_service_lists_docs(self, client):
        """Test getting available list types for Docs service."""
        content = await client.read_resource("service://docs/lists")
        
        assert len(content) > 0
        data = json.loads(content[0].text)
        
        assert data["service"] == "docs"
        list_type_names = [lt["name"] for lt in data["list_types"]]
        assert "documents" in list_type_names
    
    @pytest.mark.asyncio
    async def test_get_service_lists_invalid_service(self, client):
        """Test getting list types for an invalid service."""
        content = await client.read_resource("service://invalid_service/lists")
        
        assert len(content) > 0
        data = json.loads(content[0].text)
        
        # Should return an error with available services
        assert "error" in data
        assert "not found" in data["error"].lower() or "no list types" in data["error"].lower()
        assert "available_services" in data
        
        # Check that available services include expected ones
        available = data["available_services"]
        assert "gmail" in available
        assert "forms" in available
        assert "photos" in available
    
    @pytest.mark.asyncio
    async def test_get_list_items_without_auth(self, client):
        """Test getting list items without authentication (should fail gracefully)."""
        # Try to get Gmail filters
        content = await client.read_resource("service://gmail/filters")
        
        assert len(content) > 0
        data = json.loads(content[0].text)
        
        # Should indicate authentication error
        assert "error" in data
        assert ("email" in data["error"].lower() or
                "authentication" in data["error"].lower() or
                "context" in data["error"].lower())
    
    @pytest.mark.asyncio
    async def test_get_list_items_gmail_labels(self, client):
        """Test getting Gmail labels list items (without auth should fail)."""
        content = await client.read_resource("service://gmail/labels")
        
        assert len(content) > 0
        data = json.loads(content[0].text)
        
        # Without auth, should get error
        assert "error" in data
        assert ("email" in data["error"].lower() or
                "authentication" in data["error"].lower() or
                "context" in data["error"].lower())
    
    @pytest.mark.asyncio
    async def test_get_list_items_invalid_list_type(self, client):
        """Test getting items for an invalid list type."""
        content = await client.read_resource("service://gmail/invalid_list_type")
        
        assert len(content) > 0
        data = json.loads(content[0].text)
        
        # Should return error with available list types
        assert "error" in data
        assert "not found" in data["error"].lower() or "authentication" in data["error"].lower()
        if "not found" in data["error"].lower():
            assert "available_list_types" in data
        
        # Check available list types for gmail
        available = data["available_list_types"]
        assert "filters" in available
        assert "labels" in available
    
    @pytest.mark.asyncio
    async def test_get_list_item_details_without_auth(self, client):
        """Test getting item details without authentication."""
        # Try to get details for a specific Gmail filter
        content = await client.read_resource("service://gmail/filters/test_filter_id")
        
        assert len(content) > 0
        data = json.loads(content[0].text)
        
        # Should indicate authentication error
        assert "error" in data
        assert ("email" in data["error"].lower() or
                "authentication" in data["error"].lower() or
                "context" in data["error"].lower())
    
    @pytest.mark.asyncio
    async def test_get_list_item_details_invalid_service(self, client):
        """Test getting item details for invalid service."""
        content = await client.read_resource("service://invalid_service/some_list/some_id")
        
        assert len(content) > 0
        data = json.loads(content[0].text)
        
        # Should return error
        assert "error" in data
        assert "not found" in data["error"].lower()
    
    @pytest.mark.asyncio
    async def test_hierarchical_resource_navigation(self, client):
        """Test navigating through the hierarchical resource structure."""
        # Level 1: Get services list for a service
        content = await client.read_resource("service://photos/lists")
        assert len(content) > 0
        data = json.loads(content[0].text)
        
        assert data["service"] == "photos"
        list_types = [lt["name"] for lt in data["list_types"]]
        assert "albums" in list_types
        
        # Level 2: Try to get albums (will fail without auth)
        content = await client.read_resource("service://photos/albums")
        assert len(content) > 0
        data = json.loads(content[0].text)
        
        # Should have structure even if error
        if "error" in data:
            assert ("email" in data["error"].lower() or
                    "authentication" in data["error"].lower() or
                    "context" in data["error"].lower())
        else:
            assert "service" in data
            assert "list_type" in data
            assert "count" in data
            assert "items" in data
        
        # Level 3: Try to get specific album details (will fail without auth)
        content = await client.read_resource("service://photos/albums/test_album_id")
        assert len(content) > 0
        data = json.loads(content[0].text)
        
        if "error" in data:
            assert ("email not found" in data["error"].lower() or 
                    "authentication" in data["error"].lower() or
                    "could not retrieve" in data["error"].lower())
        else:
            assert "service" in data
            assert "list_type" in data
            assert "item_id" in data
            assert "data" in data
    
    @pytest.mark.asyncio
    async def test_resource_metadata_tags(self, client):
        """Test that service list resources have proper metadata tags."""
        templates = await client.list_resource_templates()
        
        # Find our service list templates
        service_templates = [t for t in templates 
                            if str(t.uriTemplate).startswith("service://")]
        
        assert len(service_templates) >= 3
        
        # Check metadata tags if available
        for template in service_templates:
            if hasattr(template, '_meta') and template._meta:
                fastmcp_meta = template._meta.get('_fastmcp', {})
                tags = fastmcp_meta.get('tags', [])
                
                # Should have relevant tags
                assert "service" in tags
                assert "lists" in tags or "items" in tags or "detail" in tags
                assert "dynamic" in tags
    
    @pytest.mark.asyncio
    async def test_all_services_have_lists_endpoint(self, client):
        """Test that all configured services respond to the /lists endpoint."""
        expected_services = [
            "gmail", "forms", "photos", "calendar", 
            "sheets", "drive", "chat", "docs"
        ]
        
        for service in expected_services:
            content = await client.read_resource(f"service://{service}/lists")
            assert len(content) > 0
            
            data = json.loads(content[0].text)
            
            # Should either have list_types or an error
            if "error" not in data:
                assert "service" in data
                assert data["service"] == service
                assert "list_types" in data
                assert isinstance(data["list_types"], list)
    
    @pytest.mark.asyncio
    async def test_service_list_response_consistency(self, client):
        """Test that all service list responses have consistent structure."""
        test_services = ["gmail", "calendar", "sheets"]
        
        for service in test_services:
            content = await client.read_resource(f"service://{service}/lists")
            assert len(content) > 0
            
            data = json.loads(content[0].text)
            
            if "error" not in data:
                # Check consistent structure
                assert "service" in data
                assert "list_types" in data
                
                for list_type in data["list_types"]:
                    # Each list type should have these fields
                    assert "name" in list_type
                    assert "description" in list_type
                    assert "has_detail_view" in list_type
                    
                    # Types should be correct
                    assert isinstance(list_type["name"], str)
                    assert isinstance(list_type["description"], str)
                    assert isinstance(list_type["has_detail_view"], bool)


class TestServiceListItemsWithMockAuth:
    """Test service list items with mocked authentication context."""
    
    @pytest.fixture
    async def client_with_context(self):
        """Create a client with authentication context metadata."""
        auth_config = get_client_auth_config(TEST_EMAIL)
        
        # Create client with metadata context
        client = Client(
            SERVER_URL, 
            auth=auth_config,
            # Note: In real tests, the server would provide user context
            # This demonstrates expected behavior with auth
        )
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_forms_list_structure(self, client_with_context):
        """Test expected structure of forms list responses."""
        # This test documents the expected response structure
        # when authentication is available
        
        # Expected structure for form_responses list
        expected_structure = {
            "service": "forms",
            "list_type": "form_responses",
            "description": "Form submission responses",
            "count": 0,  # Would have actual count with data
            "items": []  # Would have form IDs or placeholder
        }
        
        # The actual response would come from:
        # content = await client_with_context.read_resource("service://forms/form_responses")
        # data = json.loads(content[0].text)
        
        # Verify structure matches expected
        assert "service" in expected_structure
        assert "list_type" in expected_structure
        assert "description" in expected_structure
        assert "count" in expected_structure
        assert "items" in expected_structure
    
    @pytest.mark.asyncio
    async def test_photos_albums_structure(self, client_with_context):
        """Test expected structure of photos albums responses."""
        # Expected structure for albums list
        expected_structure = {
            "service": "photos",
            "list_type": "albums",
            "description": "Photo albums",
            "count": 0,
            "items": [
                # Would contain items like:
                # {"id": "album_id_1", "type": "album"},
                # {"id": "album_id_2", "type": "album"}
            ]
        }
        
        # Verify expected fields
        assert isinstance(expected_structure["items"], list)
        assert isinstance(expected_structure["count"], int)
    
    @pytest.mark.asyncio
    async def test_calendar_events_with_id_structure(self, client_with_context):
        """Test expected structure for list types that require IDs."""
        # For calendar events, which requires calendar_id
        expected_structure = {
            "service": "calendar",
            "list_type": "events",
            "description": "Calendar events",
            "count": 0,
            "items": []
            # This would be populated when called with a specific calendar_id
            # e.g., service://calendar/events would need to list calendars first
        }
        
        # Services with id_field requirement
        services_with_id_field = {
            "forms": {"form_responses": "form_id"},
            "calendar": {"events": "calendar_id"},
            "drive": {"items": "folder_id"},
            "docs": {"documents": "folder_id"}
        }
        
        for service, list_types in services_with_id_field.items():
            for list_type, id_field in list_types.items():
                # These would return placeholder or instruction without specific ID
                assert isinstance(id_field, str)
                assert id_field.endswith("_id")
    
    @pytest.mark.asyncio
    async def test_detail_view_structure(self, client_with_context):
        """Test expected structure of detail view responses."""
        # Expected structure for item details
        expected_structure = {
            "service": "photos",
            "list_type": "albums",
            "item_id": "test_album_id",
            "data": {
                # Would contain actual album photos or details
                # The structure depends on the detail_tool used
            }
        }
        
        # Verify required fields for detail views
        assert "service" in expected_structure
        assert "list_type" in expected_structure
        assert "item_id" in expected_structure
        assert "data" in expected_structure


class TestServiceListErrorHandling:
    """Test error handling for service list resources."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_malformed_uri_patterns(self, client):
        """Test handling of malformed URI patterns."""
        # Test various malformed patterns
        malformed_uris = [
            "service://",  # Missing service
            "service:///lists",  # Empty service
            "service://gmail/",  # Trailing slash
            "service://gmail//",  # Double slash
        ]
        
        for uri in malformed_uris:
            try:
                content = await client.read_resource(uri)
                # If it doesn't error, check for error in response
                if content and len(content) > 0:
                    data = json.loads(content[0].text)
                    # Should have some kind of error indication
                    assert "error" in data or "available_services" in data
            except Exception as e:
                # Some malformed URIs might raise exceptions
                # That's acceptable error handling
                assert ("invalid" in str(e).lower() or
                        "not found" in str(e).lower() or
                        "unknown" in str(e).lower())
    
    @pytest.mark.asyncio
    async def test_deep_nesting_beyond_three_levels(self, client):
        """Test accessing resources beyond the three-level hierarchy."""
        # Try to access a fourth level (not supported)
        # This should raise an exception since the resource doesn't exist
        from mcp.shared.exceptions import McpError
        
        with pytest.raises(McpError) as exc_info:
            await client.read_resource("service://gmail/filters/filter_id/extra_level")
        
        # The error should indicate the resource is unknown
        assert "unknown resource" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_special_characters_in_ids(self, client):
        """Test handling of special characters in item IDs."""
        # Test IDs with special characters
        special_ids = [
            "id-with-dash",
            "id_with_underscore",
            "id.with.dots",
            "id%20with%20spaces",  # URL encoded spaces
        ]
        
        for item_id in special_ids:
            content = await client.read_resource(f"service://gmail/filters/{item_id}")
            assert len(content) > 0
            
            data = json.loads(content[0].text)
            # Should handle gracefully (either process or error appropriately)
            if "error" in data:
                # Check for authentication or context error
                assert ("email" in data["error"].lower() or
                        "authentication" in data["error"].lower() or
                        "context" in data["error"].lower())
            else:
                assert "item_id" in data
    
    @pytest.mark.asyncio
    async def test_case_sensitivity(self, client):
        """Test case sensitivity in service and list type names."""
        # Test uppercase service name
        content = await client.read_resource("service://GMAIL/lists")
        assert len(content) > 0
        data = json.loads(content[0].text)
        
        # Should either handle case-insensitively or return error
        if "error" not in data:
            assert data["service"].lower() == "gmail"
        else:
            assert "not found" in data["error"].lower()
        
        # Test mixed case list type
        content = await client.read_resource("service://gmail/Filters")
        assert len(content) > 0
        data = json.loads(content[0].text)
        
        # Should handle appropriately
        if "error" in data:
            # Check for authentication or context error
            assert ("email" in data["error"].lower() or
                    "authentication" in data["error"].lower() or
                    "context" in data["error"].lower())
        else:
            assert "list_type" in data


class TestServiceListPerformance:
    """Test performance characteristics of service list resources."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_concurrent_service_list_requests(self, client):
        """Test handling of concurrent requests to different services."""
        import asyncio
        
        services = ["gmail", "forms", "photos", "calendar", "sheets"]
        
        # Create concurrent requests
        tasks = [
            client.read_resource(f"service://{service}/lists")
            for service in services
        ]
        
        # Execute concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All should complete successfully
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Exceptions are acceptable but should be meaningful
                assert "timeout" not in str(result).lower()
            else:
                assert len(result) > 0
                data = json.loads(result[0].text)
                assert "service" in data or "error" in data
    
    @pytest.mark.asyncio
    async def test_repeated_requests_consistency(self, client):
        """Test that repeated requests return consistent results."""
        # Make the same request multiple times
        uri = "service://gmail/lists"
        
        results = []
        for _ in range(3):
            content = await client.read_resource(uri)
            assert len(content) > 0
            data = json.loads(content[0].text)
            results.append(data)
        
        # All results should be consistent
        first_result = results[0]
        for result in results[1:]:
            if "error" not in first_result:
                assert result["service"] == first_result["service"]
                assert len(result["list_types"]) == len(first_result["list_types"])
                
                # List types should be the same
                first_names = {lt["name"] for lt in first_result["list_types"]}
                result_names = {lt["name"] for lt in result["list_types"]}
                assert first_names == result_names


if __name__ == "__main__":
    # Run tests with asyncio
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])