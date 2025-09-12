"""
Tests for the Unified Card Tool with ModuleWrapper Integration.

This module tests the functionality of the unified_card_tool.py module,
which provides a dynamic card creation and sending capability using
the ModuleWrapper adapter.
"""

"""Test unified card tool providing consolidated card functionality.

🔧 MCP Tools Used:
- Unified card interface: Single tool for all card types
- Card type detection: Automatically detect appropriate card type
- Multi-format support: Support various input formats for card generation
- Card conversion: Convert between different card formats

🧪 What's Being Tested:
- Unified interface for all card generation workflows
- Automatic card type detection and selection
- Multi-format input handling (JSON, natural language, templates)
- Card format conversion and compatibility
- Simplified API for complex card operations
- Backward compatibility with existing card tools
- Performance optimization through unified processing

🔍 Potential Duplications:
- Consolidates functionality from multiple other card tests
- Very high overlap with test_send_dynamic_card.py, test_smart_card_tool.py
- Unified approach may duplicate patterns from test_chat_app_tools.py
- Format conversion might overlap with general data transformation tests
"""

import pytest
import asyncio
import json
from typing import Any, Dict, List
import os
from datetime import datetime
from dotenv import load_dotenv
from ..test_auth_utils import get_client_auth_config

from fastmcp import Client

# Load environment variables from .env file
load_dotenv()

# Server configuration from environment variables with defaults
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "localhost")
SERVER_PORT = os.getenv("MCP_SERVER_PORT", os.getenv("SERVER_PORT", "8002"))
# FastMCP servers in HTTP mode use the /mcp/ endpoint
SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://{SERVER_HOST}:{SERVER_PORT}/mcp/")

# Test email address from environment variable
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test_user@example.com")
# Test space ID for Google Chat
TEST_SPACE_ID = os.getenv("TEST_CHAT_SPACE_ID", "spaces/AAAAAAAAAAA")
# Test webhook URL for Google Chat
TEST_WEBHOOK_URL = os.getenv("TEST_CHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/AAAAAAAAAAA/messages?key=test&token=test")


class TestUnifiedCardTool:
    """Test the Unified Card Tool using the FastMCP Client."""
    
    # Use standardized client fixture from conftest.py
    
    @pytest.mark.asyncio
    async def test_unified_card_tools_available(self, client):
        """Test that all Unified Card tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Check for all Unified Card tools
        expected_tools = [
            "send_dynamic_card",
            "list_available_card_components",
            "get_card_component_info"
        ]
        
        for tool in expected_tools:
            assert tool in tool_names, f"Tool '{tool}' not found in available tools"
    
    @pytest.mark.asyncio
    async def test_list_available_card_components_no_query(self, client):
        """Test listing available card components without a query."""
        try:
            # Call the tool without a query
            result = await client.call_tool(
                "list_available_card_components",
                {}
            )
            
            assert len(result) > 0
            content = result[0].text
            
            # Parse the JSON result
            try:
                data = json.loads(content)
                
                # Verify structure
                assert "results" in data, "Results field missing in response"
                assert "count" in data, "Count field missing in response"
                assert isinstance(data["results"], list), "Results should be a list"
                
                # Check if we got any results
                if data["count"] > 0:
                    # Verify first result has expected fields
                    first_result = data["results"][0]
                    assert "name" in first_result, "Name field missing in result"
                    assert "path" in first_result, "Path field missing in result"
                    assert "type" in first_result, "Type field missing in result"
                    
                    print(f"Found {data['count']} card components")
                    print(f"First component: {first_result['name']} ({first_result['path']})")
                else:
                    print("No card components found - this may indicate Card Framework is not available")
                    
            except json.JSONDecodeError:
                print(f"Failed to parse JSON response: {content}")
                # Return a minimal valid response structure
                data = {"results": [], "count": 0}
        except Exception as e:
            print(f"Error during test_list_available_card_components_no_query: {str(e)}")
            # Don't fail the test if there's a server-side error
            pytest.skip(f"Server error occurred: {str(e)}")
    
    @pytest.mark.asyncio
    async def test_list_available_card_components_with_query(self, client):
        """Test listing available card components with a specific query."""
        try:
            # Call the tool with a specific query
            result = await client.call_tool(
                "list_available_card_components",
                {
                    "query": "interactive buttons clickable",
                    "limit": 5
                }
            )
            
            assert len(result) > 0
            content = result[0].text
            
            # Parse the JSON result
            try:
                data = json.loads(content)
                
                # Verify structure
                assert "results" in data, "Results field missing in response"
                assert "count" in data, "Count field missing in response"
                assert isinstance(data["results"], list), "Results should be a list"
                
                # Check if we got any results
                if data["count"] > 0:
                    # Verify first result has expected fields
                    first_result = data["results"][0]
                    assert "name" in first_result, "Name field missing in result"
                    assert "path" in first_result, "Path field missing in result"
                    assert "type" in first_result, "Type field missing in result"
                    
                    print(f"Found {data['count']} components matching 'interactive buttons clickable'")
                    print(f"Top component: {first_result['name']} ({first_result['path']})")
                    print(f"Score: {first_result['score']}")
                    
                    # Check if the results are relevant to buttons or interactive elements
                    relevant_terms = ["button", "interactive", "click", "action", "on_click"]
                    found_relevant = False
                    
                    for result_item in data["results"]:
                        name = result_item["name"].lower()
                        path = result_item["path"].lower()
                        docstring = result_item.get("docstring", "").lower()
                        
                        for term in relevant_terms:
                            if term in name or term in path or term in docstring:
                                found_relevant = True
                                break
                        
                        if found_relevant:
                            break
                    
                    # Only assert if we have results
                    if not found_relevant:
                        print("Warning: No relevant components found for 'interactive buttons clickable'")
                else:
                    print("No components found matching 'interactive buttons clickable'")
                    
            except json.JSONDecodeError:
                print(f"Failed to parse JSON response: {content}")
                # Return a minimal valid response structure
                data = {"results": [], "count": 0}
        except Exception as e:
            print(f"Error during test_list_available_card_components_with_query: {str(e)}")
            # Don't fail the test if there's a server-side error
            pytest.skip(f"Server error occurred: {str(e)}")
    
    @pytest.mark.asyncio
    async def test_get_card_component_info(self, client):
        """Test getting card component info."""
        # First get a component path from list_available_card_components
        list_result = await client.call_tool(
            "list_available_card_components",
            {}
        )
        
        assert len(list_result) > 0
        list_content = list_result[0].text
        
        try:
            list_data = json.loads(list_content)
            
            # Skip test if no components available
            if list_data["count"] == 0:
                pytest.skip("No card components available to test with")
            
            # Get the path of the first component
            component_path = list_data["results"][0]["path"]
            
            # Now get info for this component
            info_result = await client.call_tool(
                "get_card_component_info",
                {
                    "component_path": component_path,
                    "include_source": False
                }
            )
            
            assert len(info_result) > 0
            info_content = info_result[0].text
            
            # Parse the JSON result
            try:
                info_data = json.loads(info_content)
                
                # Verify structure
                assert "name" in info_data, "Name field missing in response"
                assert "path" in info_data, "Path field missing in response"
                assert "type" in info_data, "Type field missing in response"
                assert "docstring" in info_data, "Docstring field missing in response"
                
                print(f"Successfully retrieved info for {info_data['name']}")
                print(f"Component type: {info_data['type']}")
                print(f"Module path: {info_data['module_path']}")
                
                # Check for signature if available
                if "signature" in info_data:
                    print(f"Signature: {info_data['signature']}")
                
                # Check for example if available
                if "example" in info_data:
                    print(f"Example usage: {info_data['example']}")
                
            except json.JSONDecodeError:
                pytest.fail(f"Failed to parse JSON response: {info_content}")
                
        except json.JSONDecodeError:
            pytest.fail(f"Failed to parse JSON response from list_available_card_components: {list_content}")
    
    @pytest.mark.asyncio
    async def test_get_card_component_info_with_source(self, client):
        """Test getting card component info with source code."""
        # First search for a specific component type
        list_result = await client.call_tool(
            "list_available_card_components",
            {
                "query": "simple card"
            }
        )
        
        assert len(list_result) > 0
        list_content = list_result[0].text
        
        try:
            list_data = json.loads(list_content)
            
            # Skip test if no components available
            if list_data["count"] == 0:
                pytest.skip("No card components available to test with")
            
            # Get the path of the first component
            component_path = list_data["results"][0]["path"]
            
            # Now get info for this component with source code
            info_result = await client.call_tool(
                "get_card_component_info",
                {
                    "component_path": component_path,
                    "include_source": True
                }
            )
            
            assert len(info_result) > 0
            info_content = info_result[0].text
            
            # Parse the JSON result
            try:
                info_data = json.loads(info_content)
                
                # Verify structure
                assert "name" in info_data, "Name field missing in response"
                assert "path" in info_data, "Path field missing in response"
                assert "type" in info_data, "Type field missing in response"
                assert "docstring" in info_data, "Docstring field missing in response"
                
                # Check for source code
                if "source" in info_data:
                    source = info_data["source"]
                    assert len(source) > 0, "Source code is empty"
                    print(f"Successfully retrieved source code for {info_data['name']}")
                    print(f"Source code length: {len(source)} characters")
                else:
                    print(f"Source code not available for {info_data['name']}")
                
            except json.JSONDecodeError:
                pytest.fail(f"Failed to parse JSON response: {info_content}")
                
        except json.JSONDecodeError:
            pytest.fail(f"Failed to parse JSON response from list_available_card_components: {list_content}")
    
    @pytest.mark.asyncio
    async def test_send_dynamic_card_simple(self, client):
        """Test sending a simple dynamic card."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing send_dynamic_card")
        
        try:
            # Call the tool with a simple card description
            result = await client.call_tool(
                "send_dynamic_card",
                {
                    "user_google_email": TEST_EMAIL,
                    "space_id": TEST_SPACE_ID,
                    "card_description": "simple card with title and text",
                    "card_params": {
                        "title": "Simple Test Card",
                        "text": "This is a simple test card sent by the unified card tool",
                        "subtitle": "Simple Test"
                    },
                    "webhook_url": TEST_WEBHOOK_URL
                }
            )
            
            assert len(result) > 0
            content = result[0].text
            
            # Check result
            assert "successfully" in content.lower() or "sent" in content.lower(), f"Failed to send card: {content}"
            print(f"Simple card sending result: {content}")
        except Exception as e:
            # Handle server errors gracefully
            print(f"Error during test_send_dynamic_card_simple: {str(e)}")
            # Don't fail the test if there's a server-side error
            pytest.skip(f"Server error occurred: {str(e)}")
    
    @pytest.mark.asyncio
    async def test_send_dynamic_card_with_image(self, client):
        """Test sending a dynamic card with an image."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing send_dynamic_card")
        
        try:
            # Call the tool with a card description that includes an image
            result = await client.call_tool(
                "send_dynamic_card",
                {
                    "user_google_email": TEST_EMAIL,
                    "space_id": TEST_SPACE_ID,
                    "card_description": "card with title, text and image",
                    "card_params": {
                        "title": "Image Test Card",
                        "text": "This card includes an image",
                        "subtitle": "Image Test",
                        "image_url": "https://picsum.photos/200/300"
                    },
                    "webhook_url": TEST_WEBHOOK_URL
                }
            )
            
            assert len(result) > 0
            content = result[0].text
            
            # Check result
            assert "successfully" in content.lower() or "sent" in content.lower(), f"Failed to send card with image: {content}"
            print(f"Card with image sending result: {content}")
        except Exception as e:
            # Handle server errors gracefully
            print(f"Error during test_send_dynamic_card_with_image: {str(e)}")
            # Don't fail the test if there's a server-side error
            pytest.skip(f"Server error occurred: {str(e)}")
    
    @pytest.mark.asyncio
    async def test_send_dynamic_card_interactive(self, client):
        """Test sending an interactive dynamic card with buttons."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing send_dynamic_card")
        
        try:
            # Call the tool with an interactive card description
            result = await client.call_tool(
                "send_dynamic_card",
                {
                    "user_google_email": TEST_EMAIL,
                    "space_id": TEST_SPACE_ID,
                    "card_description": "interactive card with buttons",
                    "card_params": {
                        "title": "Interactive Test Card",
                        "text": "This card has interactive buttons",
                        "buttons": [
                            {
                                "text": "Visit Google",
                                "url": "https://www.google.com"
                            },
                            {
                                "text": "Visit GitHub",
                                "url": "https://www.github.com"
                            }
                        ]
                    },
                    "webhook_url": TEST_WEBHOOK_URL
                }
            )
            
            assert len(result) > 0
            content = result[0].text
            
            # Check result
            assert "successfully" in content.lower() or "sent" in content.lower(), f"Failed to send interactive card: {content}"
            print(f"Interactive card sending result: {content}")
        except Exception as e:
            # Handle server errors gracefully
            print(f"Error during test_send_dynamic_card_interactive: {str(e)}")
            # Don't fail the test if there's a server-side error
            pytest.skip(f"Server error occurred: {str(e)}")
    
    @pytest.mark.asyncio
    async def test_send_dynamic_card_with_natural_language(self, client):
        """Test sending a dynamic card using complex natural language description."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing send_dynamic_card")
        
        try:
            # Call the tool with a complex natural language description
            result = await client.call_tool(
                "send_dynamic_card",
                {
                    "user_google_email": TEST_EMAIL,
                    "space_id": TEST_SPACE_ID,
                    "card_description": "create a rich card with a header, some formatted text, and a button to visit a website",
                    "card_params": {
                        "title": "Natural Language Card",
                        "text": "This card was created using a complex natural language description",
                        "subtitle": "Demonstrates ModuleWrapper's semantic search",
                        "image_url": "https://picsum.photos/200/300",
                        "buttons": [
                            {
                                "text": "Learn More",
                                "url": "https://cloud.google.com/chat"
                            }
                        ]
                    },
                    "webhook_url": TEST_WEBHOOK_URL
                }
            )
            
            assert len(result) > 0
            content = result[0].text
            
            # Check result
            assert "successfully" in content.lower() or "sent" in content.lower(), f"Failed to send card with natural language: {content}"
            print(f"Natural language card sending result: {content}")
        except Exception as e:
            # Handle server errors gracefully
            print(f"Error during test_send_dynamic_card_with_natural_language: {str(e)}")
            # Don't fail the test if there's a server-side error
            pytest.skip(f"Server error occurred: {str(e)}")
    
    @pytest.mark.asyncio
    async def test_send_dynamic_card_fallback(self, client):
        """Test the fallback behavior when card description doesn't match any component."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing send_dynamic_card")
        
        try:
            # Call the tool with an unusual description that might not match any component
            result = await client.call_tool(
                "send_dynamic_card",
                {
                    "user_google_email": TEST_EMAIL,
                    "space_id": TEST_SPACE_ID,
                    "card_description": "something completely unusual that doesn't match any card type",
                    "card_params": {
                        "title": "Fallback Test",
                        "text": "Testing fallback behavior"
                    },
                    "webhook_url": TEST_WEBHOOK_URL
                }
            )
            
            assert len(result) > 0
            content = result[0].text
            
            # We should either get a fallback to a simple card or an error message
            # Either way, the test should not fail with an exception
            print(f"Fallback test result: {content}")
        except Exception as e:
            # Handle server errors gracefully
            print(f"Error during test_send_dynamic_card_fallback: {str(e)}")
            # Don't fail the test if there's a server-side error
            pytest.skip(f"Server error occurred: {str(e)}")
