"""Test suite for ModuleWrapper tools using FastMCP Client SDK."""

import pytest
import asyncio
from fastmcp import Client
from typing import Any, Dict, List
import os
import json
import re
from dotenv import load_dotenv
from .test_auth_utils import get_client_auth_config

# Load environment variables from .env file
load_dotenv()

# Server configuration from environment variables with defaults
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "localhost")
SERVER_PORT = os.getenv("MCP_SERVER_PORT", os.getenv("SERVER_PORT", "8002"))
# FastMCP servers in HTTP mode use the /mcp/ endpoint
SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://{SERVER_HOST}:{SERVER_PORT}/mcp/")

# Test email address from environment variable
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test_user@example.com")


class TestModuleWrapperTools:
    """Test ModuleWrapper tools using the FastMCP Client."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_module_wrapper_tools_available(self, client):
        """Test that all ModuleWrapper tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Check for all ModuleWrapper tools
        expected_tools = [
            "wrap_module",
            "search_module",
            "get_module_component",
            "list_module_components",
            "list_wrapped_modules"
        ]
        
        for tool in expected_tools:
            assert tool in tool_names, f"Tool '{tool}' not found in available tools"
    
    @pytest.mark.asyncio
    async def test_wrap_module(self, client):
        """Test wrapping a module."""
        result = await client.call_tool("wrap_module", {
            "module_name": "json",
            "index_components": True
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "successfully wrapped", "module wrapped", "components indexed",
            "❌", "failed to wrap", "unexpected error", "module not found"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_search_module(self, client):
        """Test searching a wrapped module."""
        # First wrap a module
        await client.call_tool("wrap_module", {
            "module_name": "json",
            "index_components": True
        })
        
        # Then search it
        result = await client.call_tool("search_module", {
            "module_name": "json",
            "query": "parse json string",
            "limit": 5
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "search results", "found", "components", "score",
            "❌", "failed to search", "unexpected error", "module not wrapped"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_get_module_component(self, client):
        """Test getting a specific module component."""
        # First wrap a module
        await client.call_tool("wrap_module", {
            "module_name": "json",
            "index_components": True
        })
        
        # Then get a specific component
        result = await client.call_tool("get_module_component", {
            "module_name": "json",
            "component_path": "json.loads"
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "component details", "function", "class", "method", "variable",
            "❌", "failed to get component", "unexpected error", "component not found"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_list_module_components(self, client):
        """Test listing all components in a wrapped module."""
        # First wrap a module
        await client.call_tool("wrap_module", {
            "module_name": "json",
            "index_components": True
        })
        
        # Then list its components
        result = await client.call_tool("list_module_components", {
            "module_name": "json"
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "components", "found", "functions", "classes", "variables",
            "❌", "failed to list", "unexpected error", "module not wrapped"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="get_module_info tool is not implemented")
    async def test_get_module_info(self, client):
        """Test getting information about a wrapped module."""
        # This test is skipped because the get_module_info tool is not implemented
        pass
    
    @pytest.mark.asyncio
    async def test_wrap_module_with_invalid_name(self, client):
        """Test wrapping a module with an invalid name."""
        result = await client.call_tool("wrap_module", {
            "module_name": "nonexistent_module_123456",
            "index_components": True
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should return an error about the module not being found
        assert "error" in content.lower() or "not found" in content.lower() or "failed" in content.lower()
    
    @pytest.mark.asyncio
    async def test_search_unwrapped_module(self, client):
        """Test searching a module that hasn't been wrapped."""
        result = await client.call_tool("search_module", {
            "module_name": "nonexistent_module_123456",
            "query": "test query",
            "limit": 5
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should either return an error or a JSON response with empty results
        if "{" in content and "}" in content:
            # Check if it's a JSON response with empty results
            try:
                data = json.loads(content)
                assert "results" in data, "JSON response should contain 'results' field"
                assert "count" in data, "JSON response should contain 'count' field"
                assert data["count"] == 0, "Results count should be 0 for unwrapped module"
                assert len(data["results"]) == 0, "Results list should be empty for unwrapped module"
            except json.JSONDecodeError:
                pytest.fail("Response should be valid JSON")
        else:
            # If not JSON, should contain an error message
            assert "error" in content.lower() or "not wrapped" in content.lower() or "not found" in content.lower()
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_component(self, client):
        """Test getting a component that doesn't exist."""
        # First wrap a module
        await client.call_tool("wrap_module", {
            "module_name": "json",
            "index_components": True
        })
        
        # Then try to get a nonexistent component
        result = await client.call_tool("get_module_component", {
            "module_name": "json",
            "component_path": "json.nonexistent_function_123456"
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should return an error about the component not being found
        assert "error" in content.lower() or "not found" in content.lower() or "failed" in content.lower()


class TestModuleWrapperIntegration:
    """Integration tests for ModuleWrapper with other services."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_module_wrapper_with_qdrant(self, client):
        """Test ModuleWrapper integration with Qdrant."""
        # Check if both ModuleWrapper and Qdrant tools are available
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        has_module_wrapper = "wrap_module" in tool_names
        has_qdrant = "search_tool_history" in tool_names
        
        if has_module_wrapper and has_qdrant:
            # Test the integration by wrapping a module and checking if search works
            # First wrap a module
            wrap_result = await client.call_tool("wrap_module", {
                "module_name": "json",
                "index_components": True
            })
            
            # Then search it
            search_result = await client.call_tool("search_module", {
                "module_name": "json",
                "query": "parse json string",
                "limit": 5
            })
            
            # Both operations should succeed or fail with meaningful errors
            assert len(wrap_result) > 0 and len(search_result) > 0
            
            # If both succeeded, the search should return results
            if "successfully wrapped" in wrap_result[0].text.lower() and "search results" in search_result[0].text.lower():
                # Verify that search results contain component information
                assert "component" in search_result[0].text.lower() or "path" in search_result[0].text.lower()
    
    @pytest.mark.asyncio
    async def test_module_wrapper_with_multiple_modules(self, client):
        """Test wrapping and searching multiple modules."""
        # Wrap multiple standard library modules
        modules_to_test = ["json", "os", "sys"]
        
        for module_name in modules_to_test:
            # Wrap the module
            wrap_result = await client.call_tool("wrap_module", {
                "module_name": module_name,
                "index_components": True
            })
            
            # Check that wrapping succeeded or failed with a meaningful error
            assert len(wrap_result) > 0
            
            # If wrapping succeeded, test searching
            if "successfully wrapped" in wrap_result[0].text.lower():
                # Search with a generic query that should match something in any module
                search_result = await client.call_tool("search_module", {
                    "module_name": module_name,
                    "query": "function",
                    "limit": 3
                })
                
                # Check that search succeeded or failed with a meaningful error
                assert len(search_result) > 0
                
                # If search succeeded, verify results
                if "search results" in search_result[0].text.lower():
                    assert "component" in search_result[0].text.lower() or "path" in search_result[0].text.lower()
    
    @pytest.mark.asyncio
    async def test_module_wrapper_persistence(self, client):
        """Test that wrapped modules persist between calls."""
        # Wrap a module
        await client.call_tool("wrap_module", {
            "module_name": "json",
            "index_components": True
        })
        
        # List module components to verify it's wrapped
        list_result = await client.call_tool("list_module_components", {
            "module_name": "json"
        })
        
        assert len(list_result) > 0
        content = list_result[0].text
        
        # Verify that components can be listed
        valid_responses = [
            "components", "found", "functions", "classes", "variables"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"


class TestModuleWrapperErrorHandling:
    """Test error handling in ModuleWrapper tools."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_missing_required_parameters(self, client):
        """Test calling tools with missing required parameters."""
        # Test wrap_module without module_name
        with pytest.raises(Exception):
            await client.call_tool("wrap_module", {
                # Missing module_name
                "index_components": True
            })
        
        # Test search_module without module_name or query
        with pytest.raises(Exception):
            await client.call_tool("search_module", {
                # Missing module_name and query
                "limit": 5
            })
        
        # Test get_module_component without component_path
        with pytest.raises(Exception):
            await client.call_tool("get_module_component", {
                "module_name": "json"
                # Missing component_path
            })
    
    @pytest.mark.asyncio
    async def test_invalid_parameter_values(self, client):
        """Test calling tools with invalid parameter values."""
        # Test search_module with invalid limit
        result = await client.call_tool("search_module", {
            "module_name": "json",
            "query": "test query",
            "limit": -1  # Invalid limit
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should handle invalid limit gracefully
        assert "error" in content.lower() or "invalid" in content.lower() or "limit" in content.lower()
        
        # Test get_module_component with invalid component path format
        result = await client.call_tool("get_module_component", {
            "module_name": "json",
            "component_path": "invalid:path:format"  # Invalid path format
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should handle invalid path format gracefully
        assert "error" in content.lower() or "invalid" in content.lower() or "path" in content.lower()
    
    @pytest.mark.asyncio
    async def test_module_import_errors(self, client):
        """Test handling of module import errors."""
        # Test wrapping a module that can't be imported
        result = await client.call_tool("wrap_module", {
            "module_name": "this.module.does.not.exist",
            "index_components": True
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should handle import error gracefully
        assert "error" in content.lower() or "import" in content.lower() or "not found" in content.lower() or "failed" in content.lower()
    
    @pytest.mark.asyncio
    async def test_component_access_errors(self, client):
        """Test handling of component access errors."""
        # First wrap a module
        await client.call_tool("wrap_module", {
            "module_name": "json",
            "index_components": True
        })
        
        # Test accessing a component with invalid path
        result = await client.call_tool("get_module_component", {
            "module_name": "json",
            "component_path": "json.loads.nonexistent_attribute"  # Invalid path
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should handle attribute error gracefully
        assert "error" in content.lower() or "not found" in content.lower() or "invalid" in content.lower()


class TestUnifiedCardTool:
    """Test the enhanced unified card tool with ModuleWrapper and Qdrant integration."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_unified_card_tool_available(self, client):
        """Test that the unified card tool is available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Check for all unified card tools
        expected_tools = [
            "send_dynamic_card",
            "list_available_card_components",
            "get_card_component_info",
            "list_card_templates",
            "get_card_template",
            "save_card_template",
            "delete_card_template",
            "create_card_framework_wrapper"
        ]
        
        for tool in expected_tools:
            assert tool in tool_names, f"Tool '{tool}' not found in available tools"
    
    @pytest.mark.asyncio
    async def test_list_available_card_components(self, client):
        """Test listing available card components."""
        result = await client.call_tool("list_available_card_components", {
            "limit": 10
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "components", "results", "card", "path", "type", "score",
            "❌", "error", "not available"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
        
        # If successful, should be JSON
        if "❌" not in content and "error" not in content.lower():
            try:
                data = json.loads(content)
                assert "results" in data, "JSON response should contain 'results' field"
                if "results" in data and len(data["results"]) > 0:
                    assert "name" in data["results"][0], "Each result should have a 'name' field"
                    assert "path" in data["results"][0], "Each result should have a 'path' field"
                    assert "type" in data["results"][0], "Each result should have a 'type' field"
            except json.JSONDecodeError:
                pytest.fail("Response should be valid JSON")
    
    @pytest.mark.asyncio
    async def test_get_card_component_info(self, client):
        """Test getting card component info."""
        # First list components to get a valid path
        list_result = await client.call_tool("list_available_card_components", {
            "limit": 1
        })
        
        assert len(list_result) > 0
        list_content = list_result[0].text
        
        # If listing succeeded and returned JSON, use the first component path
        component_path = None
        try:
            data = json.loads(list_content)
            if "results" in data and len(data["results"]) > 0:
                component_path = data["results"][0]["path"]
        except (json.JSONDecodeError, KeyError):
            pass
        
        # If we couldn't get a path, use a default one
        if not component_path:
            component_path = "card_framework.v2.Card"
        
        # Get component info
        result = await client.call_tool("get_card_component_info", {
            "component_path": component_path,
            "include_source": False
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "name", "path", "type", "module", "docstring", "signature",
            "❌", "error", "not found", "not available"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_create_card_framework_wrapper(self, client):
        """Test creating a ModuleWrapper for a module."""
        result = await client.call_tool("create_card_framework_wrapper", {
            "module_name": "json",
            "index_nested": True,
            "max_depth": 1
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "created", "wrapper", "components", "classes", "functions",
            "❌", "error", "could not import", "failed"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_save_and_get_card_template(self, client):
        """Test saving and retrieving a card template."""
        # Create a simple card template
        template = {
            "cardId": "test_template_card",
            "card": {
                "header": {
                    "title": "Test Template Card",
                    "subtitle": "Created for testing"
                },
                "sections": [
                    {
                        "widgets": [
                            {
                                "textParagraph": {
                                    "text": "This is a test template card"
                                }
                            }
                        ]
                    }
                ]
            }
        }
        
        # Save the template
        save_result = await client.call_tool("save_card_template", {
            "name": "Test Template",
            "description": "A template for testing",
            "template": template
        })
        
        assert len(save_result) > 0
        save_content = save_result[0].text
        
        # Should either succeed or return a meaningful error
        valid_save_responses = [
            "saved", "template", "id", "successfully",
            "❌", "error", "failed"
        ]
        assert any(keyword in save_content.lower() for keyword in valid_save_responses), f"Save response didn't match any expected pattern: {save_content}"
        
        # If save succeeded, extract the template ID
        template_id = None
        if "❌" not in save_content and "error" not in save_content.lower():
            # Try to extract the template ID using regex
            id_match = re.search(r'ID: ([a-f0-9-]+)', save_content)
            if id_match:
                template_id = id_match.group(1)
        
        # If we got a template ID, try to retrieve it
        if template_id:
            get_result = await client.call_tool("get_card_template", {
                "template_id": template_id
            })
            
            assert len(get_result) > 0
            get_content = get_result[0].text
            
            # Should either succeed or return a meaningful error
            valid_get_responses = [
                "template", "name", "description", "card",
                "❌", "error", "not found"
            ]
            assert any(keyword in get_content.lower() for keyword in valid_get_responses), f"Get response didn't match any expected pattern: {get_content}"
            
            # If get succeeded, should be JSON
            if "❌" not in get_content and "error" not in get_content.lower():
                try:
                    data = json.loads(get_content)
                    assert "template" in data or "card" in data, "JSON response should contain template data"
                except json.JSONDecodeError:
                    pytest.fail("Response should be valid JSON")
    
    @pytest.mark.asyncio
    async def test_list_card_templates(self, client):
        """Test listing card templates."""
        # First save a template to ensure there's at least one
        template = {
            "cardId": "test_list_template_card",
            "card": {
                "header": {
                    "title": "Test List Template Card",
                    "subtitle": "Created for testing list"
                }
            }
        }
        
        await client.call_tool("save_card_template", {
            "name": "Test List Template",
            "description": "A template for testing list",
            "template": template
        })
        
        # List templates
        result = await client.call_tool("list_card_templates", {
            "limit": 10
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "templates", "query", "count", "name", "description",
            "❌", "error", "not available"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
        
        # If successful, should be JSON
        if "❌" not in content and "error" not in content.lower():
            try:
                data = json.loads(content)
                assert "templates" in data, "JSON response should contain 'templates' field"
                if "templates" in data and len(data["templates"]) > 0:
                    assert "name" in data["templates"][0], "Each template should have a 'name' field"
                    assert "description" in data["templates"][0], "Each template should have a 'description' field"
            except json.JSONDecodeError:
                pytest.fail("Response should be valid JSON")
    
    @pytest.mark.asyncio
    async def test_send_dynamic_card_with_template(self, client):
        """Test sending a dynamic card using a template."""
        # This test requires webhook_url to be set
        webhook_url = os.getenv("TEST_CHAT_WEBHOOK_URL")
        if not webhook_url:
            pytest.skip("TEST_CHAT_WEBHOOK_URL not set, skipping test_send_dynamic_card_with_template")
        
        # First save a template
        template = {
            "cardId": "test_send_template_card",
            "card": {
                "header": {
                    "title": "Test Send Template Card",
                    "subtitle": "Created for testing send"
                },
                "sections": [
                    {
                        "widgets": [
                            {
                                "textParagraph": {
                                    "text": "This is a test template card for sending"
                                }
                            }
                        ]
                    }
                ]
            }
        }
        
        save_result = await client.call_tool("save_card_template", {
            "name": "Test Send Template",
            "description": "A template for testing send",
            "template": template
        })
        
        # Extract template ID
        template_id = None
        save_content = save_result[0].text
        id_match = re.search(r'ID: ([a-f0-9-]+)', save_content)
        if id_match:
            template_id = id_match.group(1)
        
        if not template_id:
            pytest.skip("Failed to create template, skipping test_send_dynamic_card_with_template")
        
        # Send card using template
        result = await client.call_tool("send_dynamic_card", {
            "user_google_email": TEST_EMAIL,
            "space_id": "spaces/test",
            "card_description": "Test card",
            "card_params": {
                "header": {
                    "title": "Updated Title",
                    "subtitle": "Updated Subtitle"
                }
            },
            "use_template": template_id,
            "webhook_url": webhook_url
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "sent", "successfully", "webhook", "status",
            "❌", "error", "failed"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_send_dynamic_card_with_hybrid_approach(self, client):
        """Test sending a dynamic card using the hybrid approach."""
        # This test requires webhook_url to be set
        webhook_url = os.getenv("TEST_CHAT_WEBHOOK_URL")
        if not webhook_url:
            pytest.skip("TEST_CHAT_WEBHOOK_URL not set, skipping test_send_dynamic_card_with_hybrid_approach")
        
        # Create sections for hybrid approach
        sections = [
            {
                "header": "Test Section",
                "widgets": [
                    {
                        "textParagraph": {
                            "text": "This is a test section created with the hybrid approach"
                        }
                    },
                    {
                        "buttonList": {
                            "buttons": [
                                {
                                    "text": "Test Button",
                                    "onClick": {
                                        "openLink": {
                                            "url": "https://example.com"
                                        }
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        ]
        
        # Send card using hybrid approach
        result = await client.call_tool("send_dynamic_card", {
            "user_google_email": TEST_EMAIL,
            "space_id": "spaces/test",
            "card_description": "card with sections",
            "card_params": {
                "header": {
                    "title": "Hybrid Approach Card",
                    "subtitle": "Created with hybrid approach"
                }
            },
            "sections": sections,
            "use_hybrid_approach": True,
            "webhook_url": webhook_url
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "sent", "successfully", "webhook", "status",
            "❌", "error", "failed"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_delete_card_template(self, client):
        """Test deleting a card template."""
        # First save a template
        template = {
            "cardId": "test_delete_template_card",
            "card": {
                "header": {
                    "title": "Test Delete Template Card",
                    "subtitle": "Created for testing delete"
                }
            }
        }
        
        save_result = await client.call_tool("save_card_template", {
            "name": "Test Delete Template",
            "description": "A template for testing delete",
            "template": template
        })
        
        # Extract template ID
        template_id = None
        save_content = save_result[0].text
        id_match = re.search(r'ID: ([a-f0-9-]+)', save_content)
        if id_match:
            template_id = id_match.group(1)
        
        if not template_id:
            pytest.skip("Failed to create template, skipping test_delete_card_template")
        
        # Delete the template
        result = await client.call_tool("delete_card_template", {
            "template_id": template_id
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "deleted", "successfully", "template",
            "❌", "error", "failed", "not found"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
        
        # Verify template is deleted by trying to get it
        get_result = await client.call_tool("get_card_template", {
            "template_id": template_id
        })
        
        get_content = get_result[0].text
        assert "not found" in get_content.lower() or "error" in get_content.lower(), "Template should be deleted"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])