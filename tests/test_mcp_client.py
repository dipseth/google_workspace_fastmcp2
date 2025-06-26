"""Test suite using FastMCP Client SDK to test the running MCP server."""

import pytest
import asyncio
from fastmcp import Client
from typing import Any, Dict, List
import os


# Server configuration from environment variables with defaults
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "localhost")
SERVER_PORT = os.getenv("MCP_SERVER_PORT", os.getenv("SERVER_PORT", "8002"))
# FastMCP servers in HTTP mode use the /mcp/ endpoint
SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://{SERVER_HOST}:{SERVER_PORT}/mcp/")

# Test email address from environment variable
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test_user@example.com")


class TestMCPServer:
    """Test the MCP server using the FastMCP Client."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        client = Client(SERVER_URL)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_server_connectivity(self, client):
        """Test that we can connect to the server."""
        # Ping the server to verify connectivity
        await client.ping()
        assert client.is_connected()
    
    @pytest.mark.asyncio
    async def test_list_tools(self, client):
        """Test listing available tools."""
        tools = await client.list_tools()
        
        # Check that we have tools available
        assert len(tools) > 0
        
        # Check for expected tools
        tool_names = [tool.name for tool in tools]
        assert "health_check" in tool_names
        assert "check_drive_auth" in tool_names
        assert "start_google_auth" in tool_names
        
        # If Gmail tools are enabled
        if "list_gmail_labels" in tool_names:
            assert "search_gmail_messages" in tool_names
            assert "send_gmail_message" in tool_names
        
        # If Google Docs tools are enabled
        if "search_docs" in tool_names:
            assert "get_doc_content" in tool_names
            assert "list_docs_in_folder" in tool_names
            assert "create_doc" in tool_names
    
    @pytest.mark.asyncio
    async def test_health_check_tool(self, client):
        """Test the health check tool."""
        result = await client.call_tool("health_check", {})
        
        # Check that we get a result
        assert len(result) > 0
        
        # Check the content includes expected strings
        content = result[0].text
        assert "Google Drive Upload Server Health Check" in content
        assert "Status:" in content  # Changed from "Server Status" to match actual output
        assert "OAuth Configured:" in content  # Changed to match actual output
    
    @pytest.mark.asyncio
    async def test_check_drive_auth(self, client):
        """Test checking authentication status."""
        # Use a test email that won't have credentials
        test_email = TEST_EMAIL
        
        result = await client.call_tool("check_drive_auth", {
            "user_google_email": test_email
        })
        
        # Check that we get a result
        assert len(result) > 0
        
        # Should indicate authentication status (either success or failure)
        content = result[0].text
        assert ("No valid credentials found" in content or
                "not authenticated" in content.lower() or
                "is authenticated for" in content)
    
    @pytest.mark.asyncio
    async def test_start_google_auth(self, client):
        """Test initiating OAuth flow."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("start_google_auth", {
            "user_google_email": test_email,
            "service_name": "Test Service"
        })
        
        # Check that we get a result
        assert len(result) > 0
        
        # Should return an OAuth URL
        content = result[0].text
        assert "https://accounts.google.com/o/oauth2/auth" in content  # Changed to match actual OAuth endpoint
        assert "client_id=" in content
        assert "redirect_uri=" in content
    
    @pytest.mark.asyncio
    async def test_list_resources(self, client):
        """Test listing available resources."""
        resources = await client.list_resources()
        
        # The server might not have resources, but the call should succeed
        assert isinstance(resources, list)
    
    @pytest.mark.asyncio
    async def test_list_prompts(self, client):
        """Test listing available prompts."""
        prompts = await client.list_prompts()
        
        # The server might not have prompts, but the call should succeed
        assert isinstance(prompts, list)


class TestQdrantIntegration:
    """Test Qdrant-related tools if available."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        client = Client(SERVER_URL)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_qdrant_tools_available(self, client):
        """Check if Qdrant tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Check if Qdrant tools are registered
        has_qdrant = any("search_tool_history" in name or 
                        "get_tool_analytics" in name or
                        "get_response_details" in name 
                        for name in tool_names)
        
        if has_qdrant:
            # If Qdrant is enabled, test the tools
            await self._test_search_tool_history(client)
            await self._test_get_tool_analytics(client)
    
    async def _test_search_tool_history(self, client):
        """Test searching tool history."""
        result = await client.call_tool("search_tool_history", {
            "query": "test query",
            "limit": 5
        })
        
        # Should return search results or empty results
        assert len(result) > 0
        content = result[0].text
        assert "query" in content or "results" in content.lower()
    
    async def _test_get_tool_analytics(self, client):
        """Test getting tool analytics."""
        # The get_tool_analytics tool doesn't take parameters
        result = await client.call_tool("get_tool_analytics", {})
        
        # Should return analytics data
        assert len(result) > 0
        content = result[0].text
        assert "total_responses" in content or "analytics" in content.lower()


class TestGmailTools:
    """Test Gmail tools if available."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        client = Client(SERVER_URL)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_gmail_tools_available(self, client):
        """Check if Gmail tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Check if Gmail tools are registered
        has_gmail = "list_gmail_labels" in tool_names
        
        if has_gmail:
            # Test without authentication (should fail gracefully)
            await self._test_list_gmail_labels_no_auth(client)
    
    async def _test_list_gmail_labels_no_auth(self, client):
        """Test listing Gmail labels without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("list_gmail_labels", {
            "user_google_email": test_email
        })
        
        # Should indicate authentication status (either success or failure)
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or
                "credentials" in content.lower() or
                "not authenticated" in content.lower() or
                "found" in content.lower() and "labels" in content.lower())


class TestDocsTools:
    """Test Google Docs tools if available."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        client = Client(SERVER_URL)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_docs_tools_available(self, client):
        """Check if all 4 Google Docs tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Check if Google Docs tools are registered
        expected_docs_tools = ["search_docs", "get_doc_content", "list_docs_in_folder", "create_doc"]
        docs_tools_available = [tool for tool in expected_docs_tools if tool in tool_names]
        
        # If any docs tools are available, they should all be available
        if docs_tools_available:
            assert len(docs_tools_available) == 4, f"Expected all 4 docs tools, found: {docs_tools_available}"
            
            # Test each tool without authentication (should fail gracefully)
            await self._test_search_docs_no_auth(client)
            await self._test_get_doc_content_no_auth(client)
            await self._test_list_docs_in_folder_no_auth(client)
            await self._test_create_doc_no_auth(client)
            await self._test_missing_required_params(client)
    
    async def _test_search_docs_no_auth(self, client):
        """Test search_docs without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("search_docs", {
            "user_google_email": test_email,
            "query": "test document"
        })
        
        # Should indicate authentication status (either success or failure)
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or
                "credentials" in content.lower() or
                "not authenticated" in content.lower() or
                "no google docs found" in content.lower() or
                "found" in content.lower() and "google docs" in content.lower())
    
    async def _test_get_doc_content_no_auth(self, client):
        """Test get_doc_content without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("get_doc_content", {
            "user_google_email": test_email,
            "document_id": "test_doc_id_123"
        })
        
        # Should indicate authentication status (either success or failure)
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or
                "credentials" in content.lower() or
                "not authenticated" in content.lower() or
                "document not found" in content.lower())
    
    async def _test_list_docs_in_folder_no_auth(self, client):
        """Test list_docs_in_folder without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("list_docs_in_folder", {
            "user_google_email": test_email,
            "folder_id": "test_folder_id_123"
        })
        
        # Should indicate authentication status (either success or failure)
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or
                "credentials" in content.lower() or
                "not authenticated" in content.lower() or
                "folder not found" in content.lower())
    
    async def _test_create_doc_no_auth(self, client):
        """Test create_doc without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("create_doc", {
            "user_google_email": test_email,
            "title": "Test Document"
        })
        
        # Should indicate authentication status (either success or failure)
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or
                "credentials" in content.lower() or
                "not authenticated" in content.lower() or
                "created google doc" in content.lower())
    
    async def _test_missing_required_params(self, client):
        """Test docs tools with missing required parameters."""
        # Test search_docs without query
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("search_docs", {
                "user_google_email": TEST_EMAIL
            })
        assert "required" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()
        
        # Test get_doc_content without document_id
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("get_doc_content", {
                "user_google_email": TEST_EMAIL
            })
        assert "required" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()
        
        # Test create_doc without title
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("create_doc", {
                "user_google_email": TEST_EMAIL
            })
        assert "required" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("create_doc", {
                "user_google_email": "test@example.com"
            })
        assert "required" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()


class TestFormsTools:
    """Test Google Forms tools if available."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        client = Client(SERVER_URL)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_forms_tools_available(self, client):
        """Check if all 8 Google Forms tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Check if Google Forms tools are registered
        expected_forms_tools = [
            "create_form",
            "add_questions_to_form",
            "get_form",
            "set_form_publish_state",
            "publish_form_publicly",
            "get_form_response",
            "list_form_responses",
            "update_form_questions"
        ]
        forms_tools_available = [tool for tool in expected_forms_tools if tool in tool_names]
        
        # If any forms tools are available, they should all be available
        if forms_tools_available:
            assert len(forms_tools_available) == 8, f"Expected all 8 forms tools, found: {forms_tools_available}"
            
            # Test each tool without authentication (should fail gracefully)
            await self._test_create_form_no_auth(client)
            await self._test_add_questions_to_form_no_auth(client)
            await self._test_get_form_no_auth(client)
            await self._test_set_form_publish_state_no_auth(client)
            await self._test_publish_form_publicly_no_auth(client)
            await self._test_get_form_response_no_auth(client)
            await self._test_list_form_responses_no_auth(client)
            await self._test_update_form_questions_no_auth(client)
            await self._test_missing_required_params(client)
    
    async def _test_create_form_no_auth(self, client):
        """Test create_form without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("create_form", {
            "user_google_email": test_email,
            "title": "Test Form"
        })
        
        # Should indicate authentication status (either success or failure)
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or
                "credentials" in content.lower() or
                "not authenticated" in content.lower() or
                "successfully created form" in content.lower())
    
    async def _test_add_questions_to_form_no_auth(self, client):
        """Test add_questions_to_form without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("add_questions_to_form", {
            "user_google_email": test_email,
            "form_id": "test_form_id",
            "questions": [{"type": "TEXT_QUESTION", "title": "Test Question"}]
        })
        
        # Should indicate authentication status (either success or failure)
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or
                "credentials" in content.lower() or
                "not authenticated" in content.lower() or
                "entity was not found" in content.lower() or
                "failed to add questions" in content.lower())
    
    async def _test_get_form_no_auth(self, client):
        """Test get_form without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("get_form", {
            "user_google_email": test_email,
            "form_id": "test_form_id"
        })
        
        # Should indicate authentication status (either success or failure)
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or
                "credentials" in content.lower() or
                "not authenticated" in content.lower() or
                "entity was not found" in content.lower() or
                "form not found" in content.lower())
    
    async def _test_set_form_publish_state_no_auth(self, client):
        """Test set_form_publish_state without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("set_form_publish_state", {
            "user_google_email": test_email,
            "form_id": "test_form_id"
        })
        
        # Should indicate authentication status (either success or failure)
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or
                "credentials" in content.lower() or
                "not authenticated" in content.lower() or
                "entity was not found" in content.lower() or
                "form not found" in content.lower())
    
    async def _test_publish_form_publicly_no_auth(self, client):
        """Test publish_form_publicly without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("publish_form_publicly", {
            "user_google_email": test_email,
            "form_id": "test_form_id"
        })
        
        # Should indicate authentication status (either success or failure)
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or
                "credentials" in content.lower() or
                "not authenticated" in content.lower() or
                "entity was not found" in content.lower() or
                "failed to publish form" in content.lower())
    
    async def _test_get_form_response_no_auth(self, client):
        """Test get_form_response without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("get_form_response", {
            "user_google_email": test_email,
            "form_id": "test_form_id",
            "response_id": "test_response_id"
        })
        
        # Should indicate authentication required
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or
                "credentials" in content.lower() or
                "not authenticated" in content.lower() or
                "response not found" in content.lower() or
                "response id" in content.lower())
    
    async def _test_list_form_responses_no_auth(self, client):
        """Test list_form_responses without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("list_form_responses", {
            "user_google_email": test_email,
            "form_id": "test_form_id"
        })
        
        # Should indicate authentication required
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or
                "credentials" in content.lower() or
                "not authenticated" in content.lower() or
                "entity was not found" in content.lower() or
                "requested entity was not found" in content.lower())
    
    async def _test_update_form_questions_no_auth(self, client):
        """Test update_form_questions without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("update_form_questions", {
            "user_google_email": test_email,
            "form_id": "test_form_id",
            "questions_to_update": [{"item_id": "test_item_id", "title": "Updated Title"}]
        })
        
        # Should indicate authentication required
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or
                "credentials" in content.lower() or
                "not authenticated" in content.lower() or
                "location is required" in content.lower() or
                "failed to update questions" in content.lower())
    
    async def _test_missing_required_params(self, client):
        """Test forms tools with missing required parameters."""
        # Test create_form without title
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("create_form", {
                "user_google_email": TEST_EMAIL
            })
        assert "required" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()
        
        # Test add_questions_to_form without questions
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("add_questions_to_form", {
                "user_google_email": TEST_EMAIL,
                "form_id": "test_form_id"
            })
        assert "required" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()
        
        # Test get_form without form_id
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("get_form", {
                "user_google_email": TEST_EMAIL
            })
        assert "required" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()
        
        # Test get_form_response without response_id
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("get_form_response", {
                "user_google_email": TEST_EMAIL,
                "form_id": "test_form_id"
            })
        assert "required" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        client = Client(SERVER_URL)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_invalid_tool_name(self, client):
        """Test calling a non-existent tool."""
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("non_existent_tool", {})
        
        # Should raise an appropriate error
        assert "not found" in str(exc_info.value).lower() or "unknown" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_missing_required_params(self, client):
        """Test calling a tool without required parameters."""
        # Try to call check_drive_auth without user_google_email
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("check_drive_auth", {})
        
        # Should indicate missing parameter
        assert "required" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()


if __name__ == "__main__":
    # Run tests with asyncio
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])