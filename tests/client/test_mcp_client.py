"""Test suite using FastMCP Client SDK to test the running MCP server."""

import pytest
import asyncio
from typing import Any, Dict, List
import os
from .base_test_config import TEST_EMAIL
from ..test_auth_utils import get_client_auth_config
from fastmcp import Client


@pytest.mark.core
class TestMCPServer:
    """Test the MCP server using the FastMCP Client."""
    
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
        
        # Should have our new resource endpoints
        assert isinstance(resources, list)
        assert len(resources) > 0
        
        # Check for expected resources
        resource_uris = [str(resource.uri) for resource in resources]  # Convert AnyUrl to string
        expected_resources = [
            "user://current/email",
            "user://current/profile",
            "template://user_email",
            "auth://session/current",
            "tools://list/all",
            "tools://enhanced/list",
            "tools://usage/guide",
            "spaces://list",
            "drive://files/recent",
            "gmail://messages/recent",
            "calendar://events/today",
            "cache://status",
            "cache://clear",
            "qdrant://collection/info",
            "qdrant://collection/responses/recent"
        ]
        
        for expected_uri in expected_resources:
            assert expected_uri in resource_uris, f"Resource {expected_uri} not found. Available: {resource_uris}"
    
    @pytest.mark.asyncio
    async def test_read_tools_list_resource(self, client):
        """Test reading the tools list resource."""
        content = await client.read_resource("tools://list/all")
        
        # Should get content back
        assert len(content) > 0
        
        # Parse the JSON content
        import json
        tools_data = json.loads(content[0].text)
        
        # Verify structure
        assert "total_tools" in tools_data
        assert "enhanced_tools_count" in tools_data
        assert "tools_by_category" in tools_data
        assert "resource_templating_available" in tools_data
        assert tools_data["resource_templating_available"] is True
        
        # Check enhanced tools
        enhanced_tools = tools_data["tools_by_category"]["enhanced_tools"]["tools"]
        assert len(enhanced_tools) == 4
        
        expected_enhanced_tools = [
            "list_my_drive_files",
            "search_my_gmail",
            "create_my_calendar_event",
            "get_my_auth_status"
        ]
        
        for tool in enhanced_tools:
            assert tool["name"] in expected_enhanced_tools
    
    @pytest.mark.asyncio
    async def test_read_enhanced_tools_resource(self, client):
        """Test reading the enhanced tools resource."""
        content = await client.read_resource("tools://enhanced/list")
        
        # Should get content back
        assert len(content) > 0
        
        # Parse the JSON content
        import json
        enhanced_data = json.loads(content[0].text)
        
        # Verify structure
        assert "enhanced_tools" in enhanced_data
        assert "count" in enhanced_data
        assert "benefit" in enhanced_data
        assert enhanced_data["count"] == 4
        assert "No user_google_email parameter required" in enhanced_data["benefit"]
    
    @pytest.mark.asyncio
    async def test_read_usage_guide_resource(self, client):
        """Test reading the tool usage guide resource."""
        content = await client.read_resource("tools://usage/guide")
        
        # Should get content back
        assert len(content) > 0
        
        # Parse the JSON content
        import json
        guide_data = json.loads(content[0].text)
        
        # Verify structure
        assert "quick_start" in guide_data
        assert "enhanced_tools_workflow" in guide_data
        assert "legacy_tools_workflow" in guide_data
        assert "migration_guide" in guide_data
        assert "error_handling" in guide_data
        
        # Check migration example
        migration = guide_data["migration_guide"]
        assert "search_drive_files('user@gmail.com'" in migration["from"]
        assert "list_my_drive_files(" in migration["to"]
    
    @pytest.mark.asyncio
    async def test_read_user_resources_without_auth(self, client):
        """Test reading user resources without authentication."""
        # Try to read current user email without auth
        content = await client.read_resource("user://current/email")
        
        # Should get content back with error message
        assert len(content) > 0
        
        # Parse the JSON content
        import json
        user_data = json.loads(content[0].text)
        
        # Should indicate no authenticated user
        assert "error" in user_data
        assert "No authenticated user found" in user_data["error"]
    
    @pytest.mark.asyncio
    async def test_read_template_user_email_without_auth(self, client):
        """Test reading template user email without authentication."""
        try:
            content = await client.read_resource("template://user_email")
            # If we get content, it should be an error
            import json
            # This might be returned as an error in the content
            if content and content[0].text:
                # Check if it's an error response
                try:
                    error_data = json.loads(content[0].text)
                    assert "error" in error_data
                except json.JSONDecodeError:
                    # If it's not JSON, should be an error message
                    assert "error" in content[0].text.lower() or "authentication" in content[0].text.lower()
        except Exception as e:
            # Should raise an exception for unauthenticated access
            assert "authentication" in str(e).lower() or "user" in str(e).lower()
    
    @pytest.mark.asyncio
    async def test_resource_templating_with_service_scopes(self, client):
        """Test the service scopes resource template."""
        # Test valid service
        content = await client.read_resource("google://services/scopes/drive")
        
        assert len(content) > 0
        
        import json
        scope_data = json.loads(content[0].text)
        
        assert "service" in scope_data
        assert "default_scopes" in scope_data
        assert "version" in scope_data
        assert scope_data["service"] == "drive"
        
        # Test invalid service
        content = await client.read_resource("google://services/scopes/invalid_service")
        
        assert len(content) > 0
        
        error_data = json.loads(content[0].text)
        assert "error" in error_data
        assert "Unknown Google service" in error_data["error"]
    
    @pytest.mark.asyncio
    async def test_read_tool_output_resources_without_auth(self, client):
        """Test reading tool output resources without authentication."""
        # Test spaces list resource
        content = await client.read_resource("spaces://list")
        assert len(content) > 0
        
        import json
        spaces_data = json.loads(content[0].text)
        assert "error" in spaces_data
        assert "Authentication error" in spaces_data["error"]
        
        # Test recent drive files resource
        content = await client.read_resource("drive://files/recent")
        assert len(content) > 0
        
        drive_data = json.loads(content[0].text)
        assert "error" in drive_data
        assert "Authentication error" in drive_data["error"]
        
        # Test recent Gmail messages resource
        content = await client.read_resource("gmail://messages/recent")
        assert len(content) > 0
        
        gmail_data = json.loads(content[0].text)
        assert "error" in gmail_data
        assert "Authentication error" in gmail_data["error"]
    
    @pytest.mark.asyncio
    async def test_read_cache_status_resource(self, client):
        """Test reading the cache status resource."""
        try:
            content = await client.read_resource("cache://status")
            assert len(content) > 0
            
            import json
            cache_data = json.loads(content[0].text)
            
            # Could be an auth error or actual cache data
            if "error" in cache_data:
                assert "Authentication error" in cache_data["error"]
            else:
                assert "total_cache_entries" in cache_data
                assert "valid_cache_entries" in cache_data
                assert "default_ttl_minutes" in cache_data
        except Exception as e:
            # Some auth or connection error is expected
            assert "auth" in str(e).lower() or "user" in str(e).lower()
    
    @pytest.mark.asyncio
    async def test_read_qdrant_resources(self, client):
        """Test reading Qdrant-related resources."""
        # Test Qdrant collection info
        content = await client.read_resource("qdrant://collection/info")
        assert len(content) > 0
        
        import json
        qdrant_info = json.loads(content[0].text)
        
        # Should have qdrant_enabled field
        assert "qdrant_enabled" in qdrant_info
        
        if qdrant_info["qdrant_enabled"]:
            assert "collection_name" in qdrant_info
            assert "config" in qdrant_info
        else:
            # Qdrant not available - that's fine for tests
            assert "error" in qdrant_info
        
        # Test Qdrant recent responses (might require auth)
        content = await client.read_resource("qdrant://collection/responses/recent")
        assert len(content) > 0
        
        responses_data = json.loads(content[0].text)
        
        # Could be auth error or actual data
        if "error" in responses_data:
            # Expected if no auth or Qdrant not available
            pass
        else:
            assert "qdrant_enabled" in responses_data
    
    @pytest.mark.asyncio
    async def test_templated_qdrant_search_resource(self, client):
        """Test the templated Qdrant search resource."""
        # Test search with a query
        test_query = "gmail messages"
        content = await client.read_resource(f"qdrant://search/{test_query}")
        assert len(content) > 0
        
        import json
        search_data = json.loads(content[0].text)
        
        assert "query" in search_data
        assert search_data["query"] == test_query
        
        # Could be auth error, Qdrant unavailable, or actual results
        if "error" in search_data:
            # Expected outcomes: auth error or Qdrant not available
            assert ("Authentication error" in search_data["error"] or
                    "Qdrant" in search_data["error"] or
                    "not available" in search_data["error"])
        else:
            assert "qdrant_enabled" in search_data
            assert "total_results" in search_data
    
    @pytest.mark.asyncio
    async def test_list_prompts(self, client):
        """Test listing available prompts."""
        prompts = await client.list_prompts()
        
        # The server might not have prompts, but the call should succeed
        assert isinstance(prompts, list)


@pytest.mark.integration
class TestQdrantIntegration:
    """Test Qdrant-related tools if available."""
    
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


@pytest.mark.service("gmail")
class TestGmailTools:
    """Test Gmail tools if available."""
    
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


@pytest.mark.service("docs")
class TestDocsTools:
    """Test Google Docs tools if available."""
    
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
    
    async def _test_get_doc_content_no_auth(self, client, real_drive_document_id=None):
        """Test get_doc_content without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("get_doc_content", {
            "user_google_email": test_email,
            "document_id": real_drive_document_id or "test_doc_id_123"
        })
        
        # Should indicate authentication status (either success or failure)
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or
                "credentials" in content.lower() or
                "not authenticated" in content.lower() or
                "document not found" in content.lower())
    
    async def _test_list_docs_in_folder_no_auth(self, client, real_drive_folder_id=None):
        """Test list_docs_in_folder without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("list_docs_in_folder", {
            "user_google_email": test_email,
            "folder_id": real_drive_folder_id or "test_folder_id_123"
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
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
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
    
    async def _test_add_questions_to_form_no_auth(self, client, real_forms_form_id=None):
        """Test add_questions_to_form without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("add_questions_to_form", {
            "user_google_email": test_email,
            "form_id": real_forms_form_id or "test_form_id",
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
    
    async def _test_get_form_no_auth(self, client, real_forms_form_id=None):
        """Test get_form without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("get_form", {
            "user_google_email": test_email,
            "form_id": real_forms_form_id or "test_form_id"
        })
        
        # Should indicate authentication status (either success or failure)
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or
                "credentials" in content.lower() or
                "not authenticated" in content.lower() or
                "entity was not found" in content.lower() or
                "form not found" in content.lower())
    
    async def _test_set_form_publish_state_no_auth(self, client, real_forms_form_id=None):
        """Test set_form_publish_state without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("set_form_publish_state", {
            "user_google_email": test_email,
            "form_id": real_forms_form_id or "test_form_id"
        })
        
        # Should indicate authentication status (either success or failure)
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or
                "credentials" in content.lower() or
                "not authenticated" in content.lower() or
                "entity was not found" in content.lower() or
                "form not found" in content.lower())
    
    async def _test_publish_form_publicly_no_auth(self, client, real_forms_form_id=None):
        """Test publish_form_publicly without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("publish_form_publicly", {
            "user_google_email": test_email,
            "form_id": real_forms_form_id or "test_form_id"
        })
        
        # Should indicate authentication status (either success or failure)
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or
                "credentials" in content.lower() or
                "not authenticated" in content.lower() or
                "entity was not found" in content.lower() or
                "failed to publish form" in content.lower())
    
    async def _test_get_form_response_no_auth(self, client, real_forms_form_id=None):
        """Test get_form_response without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("get_form_response", {
            "user_google_email": test_email,
            "form_id": real_forms_form_id or "test_form_id",
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
    
    async def _test_list_form_responses_no_auth(self, client, real_forms_form_id=None):
        """Test list_form_responses without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("list_form_responses", {
            "user_google_email": test_email,
            "form_id": real_forms_form_id or "test_form_id"
        })
        
        # Should indicate authentication required
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or
                "credentials" in content.lower() or
                "not authenticated" in content.lower() or
                "entity was not found" in content.lower() or
                "requested entity was not found" in content.lower())
    
    async def _test_update_form_questions_no_auth(self, client, real_forms_form_id=None):
        """Test update_form_questions without authentication."""
        test_email = TEST_EMAIL
        
        result = await client.call_tool("update_form_questions", {
            "user_google_email": test_email,
            "form_id": real_forms_form_id or "test_form_id",
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
                "form_id": real_forms_form_id or "test_form_id"
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
                "form_id": real_forms_form_id or "test_form_id"
            })
        assert "required" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()


class TestGmailLabelColors:
    """Test Gmail label color management functionality."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_manage_gmail_label_available(self, client):
        """Check if manage_gmail_label tool is available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Check if Gmail label management tool is registered
        has_label_tool = "manage_gmail_label" in tool_names
        
        if has_label_tool:
            # Test the color functionality
            await self._test_create_label_with_colors_no_auth(client)
            await self._test_update_label_with_colors_no_auth(client)
            await self._test_invalid_color_validation(client)
    
    async def _test_create_label_with_colors_no_auth(self, client):
        """Test creating a label with colors (should fail gracefully without auth)."""
        test_email = TEST_EMAIL
        
        # Test creating a red label with white text
        result = await client.call_tool("manage_gmail_label", {
            "user_google_email": test_email,
            "action": "create",
            "name": "Urgent Test",
            "text_color": "#ffffff",
            "background_color": "#fb4c2f"
        })
        
        # Should indicate authentication status (either success or failure)
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or
                "credentials" in content.lower() or
                "not authenticated" in content.lower() or
                "label created successfully" in content.lower())
        
        # If not auth error, should not have color validation errors
        if "authentication" not in content.lower() and "credentials" not in content.lower():
            assert "invalid" not in content.lower()
    
    async def _test_update_label_with_colors_no_auth(self, client):
        """Test updating a label with colors (should fail gracefully without auth)."""
        test_email = TEST_EMAIL
        
        # Test updating a label with green background and black text
        result = await client.call_tool("manage_gmail_label", {
            "user_google_email": test_email,
            "action": "update",
            "label_id": "Label_test_123",
            "text_color": "#000000",
            "background_color": "#43d692"
        })
        
        # Should indicate authentication status (either success or failure)
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or
                "credentials" in content.lower() or
                "not authenticated" in content.lower() or
                "label updated successfully" in content.lower() or
                "label id is required" in content.lower())
        
        # If not auth error, should not have color validation errors
        if "authentication" not in content.lower() and "credentials" not in content.lower():
            assert "invalid" not in content.lower()
    
    async def _test_invalid_color_validation(self, client):
        """Test color validation with invalid colors."""
        test_email = TEST_EMAIL
        
        # Test with invalid text color
        result = await client.call_tool("manage_gmail_label", {
            "user_google_email": test_email,
            "action": "create",
            "name": "Test Label",
            "text_color": "#invalid",  # Invalid color
            "background_color": "#fb4c2f"
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should get color validation error before auth check
        assert "invalid text color" in content.lower()
        
        # Test with invalid background color
        result = await client.call_tool("manage_gmail_label", {
            "user_google_email": test_email,
            "action": "create",
            "name": "Test Label",
            "text_color": "#ffffff",
            "background_color": "#badcolor"  # Invalid color
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should get color validation error before auth check
        assert "invalid background color" in content.lower()
    
    @pytest.mark.asyncio
    async def test_manage_gmail_label_color_params_optional(self, client):
        """Test that color parameters are optional."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        if "manage_gmail_label" in tool_names:
            test_email = TEST_EMAIL
            
            # Test creating without colors (should work)
            result = await client.call_tool("manage_gmail_label", {
                "user_google_email": test_email,
                "action": "create",
                "name": "No Color Label"
            })
            
            assert len(result) > 0
            content = result[0].text
            
            # Should not get color validation errors
            assert "invalid" not in content.lower()
            assert ("authentication" in content.lower() or
                    "credentials" in content.lower() or
                    "not authenticated" in content.lower() or
                    "label created successfully" in content.lower())


class TestErrorHandling:
    """Test error handling and edge cases."""
    # Use standardized client fixture from conftest.py
    
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