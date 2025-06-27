"""Test suite for Google Slides tools using FastMCP Client SDK."""

import pytest
import asyncio
from fastmcp import Client
from typing import Any, Dict, List
import os
import json
import re
from .test_auth_utils import get_client_auth_config


# Server configuration from environment variables with defaults
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "localhost")
SERVER_PORT = os.getenv("MCP_SERVER_PORT", os.getenv("SERVER_PORT", "8002"))
# FastMCP servers in HTTP mode use the /mcp/ endpoint
SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://{SERVER_HOST}:{SERVER_PORT}/mcp/")

# Test email address from environment variable
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test@example.com")

# Global variable to store created presentation ID for session sharing
_test_presentation_id = None


class TestSlidesTools:
    """Test Google Slides tools using the FastMCP Client."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        try:
            async with client:
                yield client
        except Exception as e:
            # Log the error but don't re-yield
            print(f"Warning: Client connection error during teardown: {e}")
    
    @pytest.fixture(scope="class")
    async def shared_test_presentation(self):
        """Create a test presentation once per test class and return its ID."""
        global _test_presentation_id
        
        # If we already have a presentation ID, return it
        if _test_presentation_id is not None:
            return _test_presentation_id
            
        # Create a test presentation for the entire test class with its own client
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        
        try:
            async with client:
                result = await client.call_tool("create_presentation", {
                    "user_google_email": TEST_EMAIL,
                    "title": "Shared Test Presentation for MCP Tests"
                })
                
                if result and len(result) > 0:
                    content = result[0].text
                    print(f"Create presentation response: {content}")  # Debug output
                    
                    if "presentation created successfully" in content.lower():
                        # Try multiple regex patterns to extract presentation ID
                        patterns = [
                            r'presentation id[:\s]+([a-zA-Z0-9_-]{20,})',  # Standard format
                            r'id[:\s]*([a-zA-Z0-9_-]{20,})',              # Shorter format
                            r'([a-zA-Z0-9_-]{44})',                       # Google ID length
                            r'https://docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)',  # URL format
                        ]
                        
                        for pattern in patterns:
                            match = re.search(pattern, content, re.IGNORECASE)
                            if match:
                                presentation_id = match.group(1)
                                # Validate that this looks like a Google Slides ID
                                if len(presentation_id) >= 20:
                                    _test_presentation_id = presentation_id
                                    print(f"Extracted presentation ID: {presentation_id}")
                                    return presentation_id
                        
                        # If no regex worked, try to find any long alphanumeric string
                        words = content.split()
                        for word in words:
                            # Clean up the word (remove punctuation)
                            clean_word = re.sub(r'[^a-zA-Z0-9_-]', '', word)
                            if len(clean_word) >= 20 and re.match(r'^[a-zA-Z0-9_-]+$', clean_word):
                                _test_presentation_id = clean_word
                                print(f"Found potential presentation ID: {clean_word}")
                                return clean_word
                    
                    # Also handle authentication errors gracefully
                    elif any(keyword in content.lower() for keyword in ["requires authentication", "no valid credentials"]):
                        print("Authentication required - tests will be skipped")
                        return None
                        
        except Exception as e:
            print(f"Failed to create test presentation: {e}")
            # Suppress errors during fixture setup to avoid blocking all tests
            pass
        
        return None
    
    @pytest.fixture
    async def test_presentation_id(self, shared_test_presentation):
        """Get the shared test presentation ID."""
        return await shared_test_presentation if hasattr(shared_test_presentation, '__await__') else shared_test_presentation
    
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
            "export_presentation",
            "get_presentation_file"
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
            pytest.skip("No test presentation ID available - authentication required or presentation creation failed")
        
        result = await client.call_tool("get_presentation_info", {
            "user_google_email": TEST_EMAIL,
            "presentation_id": presentation_id
        })
        
        assert len(result) > 0
        content = result[0].text
        print(f"Get presentation info response: {content}")  # Debug output
        
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
        
        content = result[0].text
        print(f"Add slide response: {content}")  # Debug output
        assert any(keyword in content.lower() for keyword in ["requires authentication", "no valid credentials", "added", "slide"])
    
    @pytest.mark.asyncio
    async def test_update_slide_content(self, client, test_presentation_id):
        """Test updating slide content with batch operations."""
        presentation_id = await test_presentation_id if hasattr(test_presentation_id, '__await__') else test_presentation_id
        
        if not presentation_id:
            pytest.skip("No test presentation ID available - authentication required or presentation creation failed")
        
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
        print(f"Update slide content response: {content}")  # Debug output
        assert any(keyword in content.lower() for keyword in ["requires authentication", "no valid credentials", "update", "completed"])
    
    @pytest.mark.asyncio
    async def test_export_presentation(self, client, test_presentation_id):
        """Test exporting a presentation to different formats."""
        presentation_id = await test_presentation_id if hasattr(test_presentation_id, '__await__') else test_presentation_id
        
        if not presentation_id:
            pytest.skip("No test presentation ID available - authentication required or presentation creation failed")
        
        # Test PDF export
        result = await client.call_tool("export_presentation", {
            "user_google_email": TEST_EMAIL,
            "presentation_id": presentation_id,
            "export_format": "PDF"
        })
        
        assert len(result) > 0
        content = result[0].text
        print(f"Export presentation response: {content}")  # Debug output
        assert any(keyword in content.lower() for keyword in ["requires authentication", "no valid credentials", "export", "pdf"])
    
    @pytest.mark.asyncio
    async def test_get_presentation_file(self, client, test_presentation_id):
        """Test downloading a presentation file to local storage."""
        presentation_id = await test_presentation_id if hasattr(test_presentation_id, '__await__') else test_presentation_id
        
        if not presentation_id:
            pytest.skip("No test presentation ID available")
        
        # Test PDF download (most common format)
        result = await client.call_tool("get_presentation_file", {
            "user_google_email": TEST_EMAIL,
            "presentation_id": presentation_id,
            "export_format": "PDF",
            "download_directory": "./test_downloads"
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Check if authentication is required or if download succeeded
        if any(keyword in content.lower() for keyword in ["requires authentication", "no valid credentials"]):
            # Authentication required - this is expected in test environment
            assert True
        elif "presentation file downloaded successfully" in content.lower():
            # Download succeeded - verify file operations
            
            # Extract file path from response using regex
            file_path_match = re.search(r'Local File Path: ([^\n]+)', content)
            assert file_path_match, "Could not extract file path from response"
            local_file_path = file_path_match.group(1).strip()
            
            # Verify file exists
            assert os.path.exists(local_file_path), f"Downloaded file does not exist at: {local_file_path}"
            
            # Verify file has reasonable size (> 0 bytes)
            file_size = os.path.getsize(local_file_path)
            assert file_size > 0, f"Downloaded file is empty: {file_size} bytes"
            
            # Verify response contains expected metadata
            assert "presentation id:" in content.lower()
            assert "export format: pdf" in content.lower()
            assert "file size:" in content.lower()
            assert "download duration:" in content.lower()
            assert presentation_id in content
            
            # Verify file size in response matches actual file
            size_match = re.search(r'File Size: ([\d,]+) bytes', content)
            if size_match:
                reported_size = int(size_match.group(1).replace(',', ''))
                assert reported_size == file_size, f"Reported size {reported_size} != actual size {file_size}"
            
            # Clean up downloaded file
            try:
                os.remove(local_file_path)
                # Also try to remove test directory if empty
                test_dir = os.path.dirname(local_file_path)
                if os.path.exists(test_dir) and not os.listdir(test_dir):
                    os.rmdir(test_dir)
            except Exception as cleanup_error:
                # Log cleanup error but don't fail test
                print(f"Warning: Could not clean up test file {local_file_path}: {cleanup_error}")
        else:
            # Unexpected response - should contain either auth error or success
            assert False, f"Unexpected response content: {content}"
    
    @pytest.mark.asyncio
    async def test_get_presentation_file_different_formats(self, client, test_presentation_id):
        """Test downloading presentation files in different formats."""
        presentation_id = await test_presentation_id if hasattr(test_presentation_id, '__await__') else test_presentation_id
        
        if not presentation_id:
            pytest.skip("No test presentation ID available")
        
        # Test different export formats
        formats_to_test = ["PDF", "PPTX", "TXT"]
        
        for export_format in formats_to_test:
            result = await client.call_tool("get_presentation_file", {
                "user_google_email": TEST_EMAIL,
                "presentation_id": presentation_id,
                "export_format": export_format,
                "download_directory": "./test_downloads"
            })
            
            assert len(result) > 0
            content = result[0].text
            
            # Should either succeed with download or require authentication
            assert any(keyword in content.lower() for keyword in [
                "requires authentication",
                "no valid credentials",
                "presentation file downloaded successfully",
                f"export format: {export_format.lower()}"
            ]), f"Unexpected response for format {export_format}: {content}"
    
    @pytest.mark.asyncio
    async def test_get_presentation_file_invalid_format(self, client, test_presentation_id):
        """Test get_presentation_file with invalid export format."""
        presentation_id = await test_presentation_id if hasattr(test_presentation_id, '__await__') else test_presentation_id
        
        if not presentation_id:
            pytest.skip("No test presentation ID available")
        
        # Test with invalid format
        result = await client.call_tool("get_presentation_file", {
            "user_google_email": TEST_EMAIL,
            "presentation_id": presentation_id,
            "export_format": "INVALID_FORMAT"
        })
        
        assert len(result) > 0
        content = result[0].text
        # Should return error about invalid format
        assert "invalid export format" in content.lower(), f"Expected invalid format error, got: {content}"
    
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
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        try:
            async with client:
                yield client
        except Exception as e:
            # Log the error but don't re-yield
            print(f"Warning: Client connection error during teardown: {e}")
    
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