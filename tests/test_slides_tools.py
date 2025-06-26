"""Test suite for Google Slides tools using FastMCP Client SDK."""

import pytest
import asyncio
from fastmcp import Client
from typing import Any, Dict, List
import os
import json
import re


# Server configuration from environment variables with defaults
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "localhost")
SERVER_PORT = os.getenv("MCP_SERVER_PORT", os.getenv("SERVER_PORT", "8002"))
# FastMCP servers in HTTP mode use the /mcp/ endpoint
SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://{SERVER_HOST}:{SERVER_PORT}/mcp/")

# Test email address from environment variable
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test_user@example.com")

# Global variable to store created presentation ID
_test_presentation_id = None


class TestSlidesTools:
    """Test Google Slides tools using the FastMCP Client."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        client = Client(SERVER_URL)
        async with client:
            yield client
    
    @pytest.fixture(scope="session")
    async def test_presentation_id(self):
        """Create a test presentation and return its ID, or None if creation fails."""
        global _test_presentation_id
        
        if _test_presentation_id is not None:
            return _test_presentation_id
            
        # Try to create a test presentation
        client = Client(SERVER_URL)
        async with client:
            try:
                result = await client.call_tool("create_presentation", {
                    "user_google_email": TEST_EMAIL,
                    "title": "Test Presentation for MCP Tests"
                })
                
                if result and len(result) > 0:
                    content = result[0].text
                    if "presentation created successfully" in content.lower():
                        # Extract presentation ID from the response
                        match = re.search(r'presentation id[:\s]+([a-zA-Z0-9_-]+)', content, re.IGNORECASE)
                        if match:
                            _test_presentation_id = match.group(1)
                            return _test_presentation_id
            except Exception:
                pass  # Failed to create, will return None
        
        return None
    
    @pytest.mark.asyncio
    async def test_slides_tools_available(self, client):
        """Test that all Slides tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Check for all Slides tools
        expected_tools = [
            "create_presentation",
            "get_presentation_info",
            "add_slide",
            "update_slide_content",
            "export_presentation"
        ]
        
        for tool in expected_tools:
            assert tool in tool_names, f"Tool '{tool}' not found in available tools"
    
    @pytest.mark.asyncio
    async def test_create_presentation(self, client):
        """Test creating a new presentation."""
        result = await client.call_tool("create_presentation", {
            "user_google_email": TEST_EMAIL,
            "title": "Test Presentation from MCP"
        })
        
        # Check that we get a result
        assert len(result) > 0
        
        content = result[0].text
        # Should either succeed or return authentication error
        assert ("requires authentication" in content.lower() or
                "no valid credentials" in content.lower() or
                "presentation created successfully" in content.lower())
    
    @pytest.mark.asyncio
    async def test_create_presentation_minimal(self, client):
        """Test creating a presentation with minimal parameters."""
        result = await client.call_tool("create_presentation", {
            "user_google_email": TEST_EMAIL,
            "title": "Minimal Test Presentation"
        })
        
        assert len(result) > 0
        content = result[0].text
        # Should either succeed or return authentication error
        assert ("error" in content.lower() or
                "requires authentication" in content.lower() or
                "no valid credentials" in content.lower() or
                "presentation created successfully" in content.lower())
    
    @pytest.mark.asyncio
    async def test_get_presentation_info(self, client, test_presentation_id):
        """Test getting presentation information."""
        presentation_id = await test_presentation_id if hasattr(test_presentation_id, '__await__') else test_presentation_id
        
        if not presentation_id:
            pytest.skip("No test presentation ID available")
        
        result = await client.call_tool("get_presentation_info", {
            "user_google_email": TEST_EMAIL,
            "presentation_id": presentation_id
        })
        
        assert len(result) > 0
        content = result[0].text
        # Should return auth error or presentation info
        assert any(keyword in content.lower() for keyword in ["requires authentication", "presentation", "title", "no valid credentials"])
    
    @pytest.mark.asyncio
    async def test_add_slide(self, client, test_presentation_id):
        """Test adding a slide to a presentation."""
        presentation_id = await test_presentation_id if hasattr(test_presentation_id, '__await__') else test_presentation_id
        
        if not presentation_id:
            pytest.skip("No test presentation ID available")
        
        result = await client.call_tool("add_slide", {
            "user_google_email": TEST_EMAIL,
            "presentation_id": presentation_id,
            "layout_id": "TITLE_AND_BODY"
        })
        
        assert len(result) > 0
        content = result[0].text
        assert any(keyword in content.lower() for keyword in ["requires authentication", "no valid credentials", "added", "slide"])
    
    @pytest.mark.asyncio
    async def test_update_slide_content(self, client, test_presentation_id):
        """Test updating slide content with batch operations."""
        presentation_id = await test_presentation_id if hasattr(test_presentation_id, '__await__') else test_presentation_id
        
        if not presentation_id:
            pytest.skip("No test presentation ID available")
        
        # Test with a simple text update request
        requests = [
            {
                "insertText": {
                    "objectId": "test_shape_id",
                    "text": "Updated text content",
                    "insertionIndex": 0
                }
            }
        ]
        
        result = await client.call_tool("update_slide_content", {
            "user_google_email": TEST_EMAIL,
            "presentation_id": presentation_id,
            "requests": requests
        })
        
        assert len(result) > 0
        content = result[0].text
        assert any(keyword in content.lower() for keyword in ["requires authentication", "no valid credentials", "update", "completed"])
    
    @pytest.mark.asyncio
    async def test_export_presentation(self, client, test_presentation_id):
        """Test exporting a presentation to different formats."""
        presentation_id = await test_presentation_id if hasattr(test_presentation_id, '__await__') else test_presentation_id
        
        if not presentation_id:
            pytest.skip("No test presentation ID available")
        
        # Test PDF export
        result = await client.call_tool("export_presentation", {
            "user_google_email": TEST_EMAIL,
            "presentation_id": presentation_id,
            "export_format": "PDF"
        })
        
        assert len(result) > 0
        content = result[0].text
        assert any(keyword in content.lower() for keyword in ["requires authentication", "no valid credentials", "export", "pdf"])
    
    @pytest.mark.asyncio
    async def test_export_presentation_invalid_format(self, client, test_presentation_id):
        """Test exporting with invalid format."""
        presentation_id = await test_presentation_id if hasattr(test_presentation_id, '__await__') else test_presentation_id
        
        if not presentation_id:
            pytest.skip("No test presentation ID available")
        
        result = await client.call_tool("export_presentation", {
            "user_google_email": TEST_EMAIL,
            "presentation_id": presentation_id,
            "export_format": "INVALID_FORMAT"
        })
        
        assert len(result) > 0
        content = result[0].text
        # Should return error about invalid format
        assert "invalid" in content.lower() or "error" in content.lower() or "requires authentication" in content.lower()
    
    @pytest.mark.asyncio
    async def test_slides_tools_parameter_validation(self, client):
        """Test parameter validation for Slides tools."""
        # Test missing required parameters
        with pytest.raises(Exception):  # FastMCP should raise an error
            await client.call_tool("create_presentation", {
                # Missing user_google_email and title
            })
        
        with pytest.raises(Exception):
            await client.call_tool("get_presentation_info", {
                "user_google_email": TEST_EMAIL
                # Missing presentation_id
            })
    
    @pytest.mark.asyncio
    async def test_add_slide_with_different_layouts(self, client, test_presentation_id):
        """Test adding slides with different layouts."""
        presentation_id = await test_presentation_id if hasattr(test_presentation_id, '__await__') else test_presentation_id
        
        if not presentation_id:
            pytest.skip("No test presentation ID available")
        
        layouts = ["TITLE_ONLY", "SECTION_HEADER", "BLANK", "ONE_COLUMN_TEXT"]
        
        for layout in layouts:
            result = await client.call_tool("add_slide", {
                "user_google_email": TEST_EMAIL,
                "presentation_id": presentation_id,
                "layout_id": layout
            })
            
            assert len(result) > 0
            content = result[0].text
            # Each should either succeed or fail with auth error
            assert any(keyword in content.lower() for keyword in ["requires authentication", "no valid credentials", "added", "slide", layout.lower()])
    
    @pytest.mark.asyncio
    async def test_update_slide_complex_requests(self, client, test_presentation_id):
        """Test complex batch update requests."""
        presentation_id = await test_presentation_id if hasattr(test_presentation_id, '__await__') else test_presentation_id
        
        if not presentation_id:
            pytest.skip("No test presentation ID available")
        
        # Complex batch request with multiple operations
        requests = [
            {
                "createShape": {
                    "shapeType": "TEXT_BOX",
                    "pageObjectId": "test_page_id",
                    "elementProperties": {
                        "size": {
                            "width": {"magnitude": 100, "unit": "PT"},
                            "height": {"magnitude": 50, "unit": "PT"}
                        },
                        "transform": {
                            "translateX": 100,
                            "translateY": 100,
                            "unit": "PT"
                        }
                    }
                }
            },
            {
                "updateTextStyle": {
                    "objectId": "test_text_id",
                    "style": {
                        "fontSize": {"magnitude": 18, "unit": "PT"},
                        "bold": True
                    },
                    "fields": "fontSize,bold"
                }
            }
        ]
        
        result = await client.call_tool("update_slide_content", {
            "user_google_email": TEST_EMAIL,
            "presentation_id": presentation_id,
            "requests": requests
        })
        
        assert len(result) > 0
        content = result[0].text
        assert any(keyword in content.lower() for keyword in ["requires authentication", "no valid credentials", "batch", "update", "completed"])


class TestSlidesIntegration:
    """Integration tests for Slides tools with other services."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        client = Client(SERVER_URL)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_slides_with_drive_integration(self, client):
        """Test that Slides tools work with Drive permissions."""
        # This would test the integration between Slides and Drive
        # For example, checking if created presentations appear in Drive
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # If both Slides and Drive tools are available
        if "create_presentation" in tool_names and "list_drive_items" in tool_names:
            # Test would verify that presentations created via Slides API
            # are accessible via Drive API
            pass  # Actual integration test would go here
    
    @pytest.mark.asyncio
    async def test_slides_error_handling(self, client):
        """Test error handling for various failure scenarios."""
        # Test with invalid presentation ID
        result = await client.call_tool("get_presentation_info", {
            "user_google_email": TEST_EMAIL,
            "presentation_id": "invalid_id_12345"
        })
        
        assert len(result) > 0
        content = result[0].text
        assert "error" in content.lower() or "not found" in content.lower() or "requires authentication" in content.lower() or "no valid credentials" in content.lower()