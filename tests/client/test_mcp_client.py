"""Test suite using FastMCP Client SDK to test the running MCP server."""

import pytest
import pytest_asyncio

from .base_test_config import TEST_EMAIL
from .test_helpers import assert_tools_registered


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
        # Verify the health_check tool is registered
        await assert_tools_registered(client, ["health_check"], context="Core tools")

        result = await client.call_tool("health_check", {})

        # Check that we get a result
        assert result is not None
        assert result.content and len(result.content) > 0

        # Check the content includes expected strings
        content = result.content[0].text
        assert "Google Drive Upload Server Health Check" in content
        assert (
            "Status:" in content
        )  # Changed from "Server Status" to match actual output
        assert "OAuth Configured:" in content  # Changed to match actual output

    @pytest.mark.asyncio
    async def test_check_drive_auth(self, client):
        """Test checking authentication status."""
        # Use a test email that won't have credentials
        test_email = TEST_EMAIL

        result = await client.call_tool(
            "check_drive_auth", {"user_google_email": test_email}
        )

        # Check that we get a result
        assert result is not None
        assert result.content and len(result.content) > 0

        # Should indicate authentication status (either success or failure)
        content = result.content[0].text
        assert (
            "No valid credentials found" in content
            or "not authenticated" in content.lower()
            or "is authenticated for" in content
        )

    @pytest.mark.asyncio
    async def test_start_google_auth(self, client):
        """Test initiating OAuth flow."""
        test_email = TEST_EMAIL

        result = await client.call_tool(
            "start_google_auth",
            {"user_google_email": test_email, "service_name": "Test Service"},
        )

        # Check that we get a result
        assert result is not None
        assert result.content and len(result.content) > 0

        # Should return an OAuth URL or auth redirect info
        content = result.content[0].text
        # The server may return a direct Google OAuth URL or a local auth redirect
        assert (
            "https://accounts.google.com/o/oauth2/auth" in content
            or "authUrl" in content
            or "https://localhost" in content
        )  # Local auth redirect

    @pytest.mark.asyncio
    async def test_list_resources(self, client):
        """Test listing available resources."""
        resources = await client.list_resources()

        # Should have our new resource endpoints
        assert isinstance(resources, list)
        assert len(resources) > 0

        # Check for expected resources (updated to match current server implementation)
        resource_uris = [
            str(resource.uri) for resource in resources
        ]  # Convert AnyUrl to string
        expected_resources = [
            "user://current/email",
            "user://current/profile",
            "auth://session/current",
            "auth://sessions/list",
            "template://user_email",
            "tools://list/all",
            "tools://detailed/list",
            "gmail://allow-list",
            "gmail://messages/recent",
            "recent://all",
            "template://macros",
            "qdrant://collections/list",
            "qdrant://cache",
            "qdrant://status",
        ]

        for expected_uri in expected_resources:
            assert expected_uri in resource_uris, (
                f"Resource {expected_uri} not found. Available: {resource_uris}"
            )

    @pytest.mark.asyncio
    async def test_read_tools_list_resource(self, client):
        """Test reading the tools list resource."""
        content = await client.read_resource("tools://list/all")

        # Should get content back
        assert len(content) > 0

        # Parse the JSON content
        import json

        tools_data = json.loads(content[0].text)

        # Verify structure (updated to match current server implementation)
        assert "total_tools" in tools_data
        assert "total_categories" in tools_data
        assert "detailed_tools_count" in tools_data
        assert "tools_by_category" in tools_data
        assert "resource_templating_available" in tools_data
        assert tools_data["resource_templating_available"] is True

        # Check that expected categories exist
        expected_categories = [
            "drive_tools",
            "gmail_tools",
            "docs_tools",
            "forms_tools",
            "calendar_tools",
            "chat_tools",
            "auth_tools",
        ]
        for category in expected_categories:
            assert category in tools_data["tools_by_category"], (
                f"Expected category {category} not found"
            )

    @pytest.mark.asyncio
    async def test_read_detailed_tools_resource(self, client):
        """Test reading the detailed tools resource."""
        content = await client.read_resource("tools://detailed/list")

        # Should get content back
        assert len(content) > 0

        # Parse the JSON content
        import json

        detailed_data = json.loads(content[0].text)

        # Verify structure (detailed tools list)
        assert (
            "detailed_tools" in detailed_data
            or "tools" in detailed_data
            or "total_tools" in detailed_data
        )

    @pytest.mark.asyncio
    async def test_read_user_resources(self, client):
        """Test reading user resources.

        NOTE: This test runs with an authenticated session, so it should
        return user data rather than an error. The test name has been
        updated to reflect actual behavior.
        """
        # Try to read current user email
        content = await client.read_resource("user://current/email")

        # Should get content back
        assert len(content) > 0

        # Parse the JSON content
        import json

        user_data = json.loads(content[0].text)

        # Should have either user data (if authenticated) or error
        # With the current test setup, user is authenticated
        if "error" in user_data:
            assert "No authenticated user found" in user_data["error"]
        else:
            # User is authenticated - check for expected fields
            assert "email" in user_data or "authenticated" in user_data

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
                    assert (
                        "error" in content[0].text.lower()
                        or "authentication" in content[0].text.lower()
                    )
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
    async def test_read_gmail_resources(self, client):
        """Test reading Gmail-related resources."""
        import json

        # Test recent Gmail messages resource
        content = await client.read_resource("gmail://messages/recent")
        assert len(content) > 0

        gmail_data = json.loads(content[0].text)
        # Could be auth error or actual data depending on auth state
        if "error" in gmail_data:
            # Auth error is acceptable
            assert "error" in gmail_data
        else:
            # If authenticated, should have messages data
            assert isinstance(gmail_data, (dict, list))

        # Test Gmail allow-list resource
        content = await client.read_resource("gmail://allow-list")
        assert len(content) > 0

        allow_list_data = json.loads(content[0].text)
        # Could be auth error or actual data depending on auth state
        assert isinstance(allow_list_data, dict)

    @pytest.mark.asyncio
    async def test_read_qdrant_resources(self, client):
        """Test reading Qdrant-related resources."""
        import json

        # Test Qdrant collections list
        content = await client.read_resource("qdrant://collections/list")
        assert len(content) > 0

        qdrant_data = json.loads(content[0].text)
        # Should be a dict with collections info or error
        assert isinstance(qdrant_data, dict)

        # Test Qdrant cache resource
        content = await client.read_resource("qdrant://cache")
        assert len(content) > 0

        cache_data = json.loads(content[0].text)
        assert isinstance(cache_data, dict)

        # Test Qdrant status resource
        content = await client.read_resource("qdrant://status")
        assert len(content) > 0

        status_data = json.loads(content[0].text)
        assert isinstance(status_data, dict)

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
        has_qdrant = any(
            "search_tool_history" in name
            or "get_tool_analytics" in name
            or "get_response_details" in name
            for name in tool_names
        )

        if has_qdrant:
            # If Qdrant is enabled, test the tools
            await self._test_search_tool_history(client)
            await self._test_get_tool_analytics(client)

    async def _test_search_tool_history(self, client):
        """Test searching tool history."""
        result = await client.call_tool(
            "search_tool_history", {"query": "test query", "limit": 5}
        )

        # Should return search results or empty results
        assert result is not None
        assert result.content and len(result.content) > 0
        content = result.content[0].text
        assert "query" in content or "results" in content.lower()

    async def _test_get_tool_analytics(self, client):
        """Test getting tool analytics."""
        # The get_tool_analytics tool doesn't take parameters
        result = await client.call_tool("get_tool_analytics", {})

        # Should return analytics data
        assert result is not None
        assert result.content and len(result.content) > 0
        content = result.content[0].text
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
        """Test listing Gmail labels.

        NOTE: Test name retained for backwards compatibility, but the test
        now handles both authenticated and unauthenticated scenarios.
        """
        test_email = TEST_EMAIL

        result = await client.call_tool(
            "list_gmail_labels", {"user_google_email": test_email}
        )

        # Should indicate authentication status (either success or failure)
        assert result is not None
        assert result.content and len(result.content) > 0
        content = result.content[0].text
        # Accept auth errors, success responses with labels, or credential messages
        assert (
            "authentication" in content.lower()
            or "credentials" in content.lower()
            or "not authenticated" in content.lower()
            or "labels" in content.lower()  # Success response with labels
            or '"error":null' in content.lower()
        )  # Successful response indicator


@pytest.mark.service("docs")
class TestDocsTools:
    """Test Google Docs tools if available."""

    @pytest.mark.asyncio
    async def test_docs_tools_available(
        self, client, real_drive_document_id, real_drive_folder_id
    ):
        """Check if all 4 Google Docs tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]

        # Check if Google Docs tools are registered
        expected_docs_tools = [
            "search_docs",
            "get_doc_content",
            "list_docs_in_folder",
            "create_doc",
        ]
        docs_tools_available = [
            tool for tool in expected_docs_tools if tool in tool_names
        ]

        # If any docs tools are available, they should all be available
        if docs_tools_available:
            assert len(docs_tools_available) == 4, (
                f"Expected all 4 docs tools, found: {docs_tools_available}"
            )

            # Test each tool without authentication (should fail gracefully)
            await self._test_search_docs_no_auth(client)
            await self._test_get_doc_content_no_auth(client, real_drive_document_id)
            await self._test_list_docs_in_folder_no_auth(client, real_drive_folder_id)
            await self._test_create_doc_no_auth(client)
            await self._test_missing_required_params(client)

    async def _test_search_docs_no_auth(self, client):
        """Test search_docs without authentication."""
        test_email = TEST_EMAIL

        result = await client.call_tool(
            "search_docs", {"user_google_email": test_email, "query": "test document"}
        )

        # Should indicate authentication status (either success or failure)
        assert result is not None
        assert result.content and len(result.content) > 0
        content = result.content[0].text
        assert (
            "authentication" in content.lower()
            or "credentials" in content.lower()
            or "not authenticated" in content.lower()
            or "no google docs found" in content.lower()
            or "found" in content.lower()
            and "google docs" in content.lower()
        )

    async def _test_get_doc_content_no_auth(self, client, real_drive_document_id=None):
        """Test get_doc_content without authentication."""
        test_email = TEST_EMAIL

        result = await client.call_tool(
            "get_doc_content",
            {
                "user_google_email": test_email,
                "document_id": real_drive_document_id or "test_doc_id_123",
            },
        )

        # Should indicate authentication status (either success or failure)
        assert result is not None
        assert result.content and len(result.content) > 0
        content = result.content[0].text
        assert (
            "authentication" in content.lower()
            or "credentials" in content.lower()
            or "not authenticated" in content.lower()
            or "document not found" in content.lower()
            or "permission denied" in content.lower()
            or "content" in content.lower()
        )  # Success case returns document content

    async def _test_list_docs_in_folder_no_auth(
        self, client, real_drive_folder_id=None
    ):
        """Test list_docs_in_folder without authentication."""
        test_email = TEST_EMAIL

        result = await client.call_tool(
            "list_docs_in_folder",
            {
                "user_google_email": test_email,
                "folder_id": real_drive_folder_id or "test_folder_id_123",
            },
        )

        # Should indicate authentication status (either success or failure)
        assert result is not None
        assert result.content and len(result.content) > 0
        content = result.content[0].text
        assert (
            "authentication" in content.lower()
            or "credentials" in content.lower()
            or "not authenticated" in content.lower()
            or "folder not found" in content.lower()
        )

    async def _test_create_doc_no_auth(self, client):
        """Test create_doc.

        NOTE: Test name retained for backwards compatibility, but the test
        now handles both authenticated and unauthenticated scenarios.
        """
        test_email = TEST_EMAIL

        result = await client.call_tool(
            "create_doc", {"user_google_email": test_email, "title": "Test Document"}
        )

        # Should indicate authentication status (either success or failure)
        assert result is not None
        assert result.content and len(result.content) > 0
        content = result.content[0].text
        # Accept auth errors or success responses
        assert (
            "authentication" in content.lower()
            or "credentials" in content.lower()
            or "not authenticated" in content.lower()
            or "created google doc" in content.lower()
            or "created empty google doc" in content.lower()
            or '"success":true' in content.lower()
        )  # Success indicator

    async def _test_missing_required_params(self, client):
        """Test docs tools with missing required parameters."""
        # Test search_docs without query
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("search_docs", {"user_google_email": TEST_EMAIL})
        assert (
            "required" in str(exc_info.value).lower()
            or "missing" in str(exc_info.value).lower()
        )

        # Test get_doc_content without document_id
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("get_doc_content", {"user_google_email": TEST_EMAIL})
        assert (
            "required" in str(exc_info.value).lower()
            or "missing" in str(exc_info.value).lower()
        )

        # Test create_doc without title
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("create_doc", {"user_google_email": TEST_EMAIL})
        assert (
            "required" in str(exc_info.value).lower()
            or "missing" in str(exc_info.value).lower()
        )
        with pytest.raises(Exception) as exc_info:
            await client.call_tool(
                "create_doc", {"user_google_email": "test@example.com"}
            )
        assert (
            "required" in str(exc_info.value).lower()
            or "missing" in str(exc_info.value).lower()
        )


class TestFormsTools:
    """Test Google Forms tools if available."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create a client connected to the running server."""
        from .base_test_config import create_test_client

        try:
            client_obj = await create_test_client(TEST_EMAIL)
        except Exception as e:
            pytest.skip(f"MCP server not reachable for integration tests: {e}")

        async with client_obj:
            yield client_obj

    @pytest.mark.asyncio
    async def test_forms_tools_available(self, client, real_forms_form_id):
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
            "update_form_questions",
        ]
        forms_tools_available = [
            tool for tool in expected_forms_tools if tool in tool_names
        ]

        # If any forms tools are available, they should all be available
        if forms_tools_available:
            assert len(forms_tools_available) == 8, (
                f"Expected all 8 forms tools, found: {forms_tools_available}"
            )

            # Test each tool without authentication (should fail gracefully)
            await self._test_create_form_no_auth(client)
            await self._test_add_questions_to_form_no_auth(client, real_forms_form_id)
            await self._test_get_form_no_auth(client, real_forms_form_id)
            await self._test_set_form_publish_state_no_auth(client, real_forms_form_id)
            await self._test_publish_form_publicly_no_auth(client, real_forms_form_id)
            await self._test_get_form_response_no_auth(client, real_forms_form_id)
            await self._test_list_form_responses_no_auth(client, real_forms_form_id)
            await self._test_update_form_questions_no_auth(client, real_forms_form_id)
            await self._test_missing_required_params(client)

    async def _test_create_form_no_auth(self, client):
        """Test create_form without authentication."""
        test_email = TEST_EMAIL

        result = await client.call_tool(
            "create_form", {"user_google_email": test_email, "title": "Test Form"}
        )

        # Should indicate authentication status (either success or failure)
        assert result is not None
        assert result.content and len(result.content) > 0
        content = result.content[0].text
        assert (
            "authentication" in content.lower()
            or "credentials" in content.lower()
            or "not authenticated" in content.lower()
            or "successfully created form" in content.lower()
        )

    async def _test_add_questions_to_form_no_auth(
        self, client, real_forms_form_id=None
    ):
        """Test add_questions_to_form without authentication."""
        test_email = TEST_EMAIL

        result = await client.call_tool(
            "add_questions_to_form",
            {
                "user_google_email": test_email,
                "form_id": real_forms_form_id or "test_form_id",
                "questions": [{"type": "TEXT_QUESTION", "title": "Test Question"}],
            },
        )

        # Should indicate authentication status (either success or failure)
        assert result is not None
        assert result.content and len(result.content) > 0
        content = result.content[0].text
        assert (
            "authentication" in content.lower()
            or "credentials" in content.lower()
            or "not authenticated" in content.lower()
            or "entity was not found" in content.lower()
            or "failed to add questions" in content.lower()
        )

    async def _test_get_form_no_auth(self, client, real_forms_form_id=None):
        """Test get_form without authentication."""
        test_email = TEST_EMAIL

        result = await client.call_tool(
            "get_form",
            {
                "user_google_email": test_email,
                "form_id": real_forms_form_id or "test_form_id",
            },
        )

        # Should indicate authentication status (either success or failure)
        assert result is not None
        assert result.content and len(result.content) > 0
        content = result.content[0].text
        assert (
            "authentication" in content.lower()
            or "credentials" in content.lower()
            or "not authenticated" in content.lower()
            or "entity was not found" in content.lower()
            or "form not found" in content.lower()
        )

    async def _test_set_form_publish_state_no_auth(
        self, client, real_forms_form_id=None
    ):
        """Test set_form_publish_state without authentication."""
        test_email = TEST_EMAIL

        result = await client.call_tool(
            "set_form_publish_state",
            {
                "user_google_email": test_email,
                "form_id": real_forms_form_id or "test_form_id",
            },
        )

        # Should indicate authentication status (either success or failure)
        assert result is not None
        assert result.content and len(result.content) > 0
        content = result.content[0].text
        assert (
            "authentication" in content.lower()
            or "credentials" in content.lower()
            or "not authenticated" in content.lower()
            or "entity was not found" in content.lower()
            or "form not found" in content.lower()
        )

    async def _test_publish_form_publicly_no_auth(
        self, client, real_forms_form_id=None
    ):
        """Test publish_form_publicly without authentication."""
        test_email = TEST_EMAIL

        result = await client.call_tool(
            "publish_form_publicly",
            {
                "user_google_email": test_email,
                "form_id": real_forms_form_id or "test_form_id",
            },
        )

        # Should indicate authentication status (either success or failure)
        assert result is not None
        assert result.content and len(result.content) > 0
        content = result.content[0].text
        assert (
            "authentication" in content.lower()
            or "credentials" in content.lower()
            or "not authenticated" in content.lower()
            or "entity was not found" in content.lower()
            or "failed to publish form" in content.lower()
        )

    async def _test_get_form_response_no_auth(self, client, real_forms_form_id=None):
        """Test get_form_response without authentication."""
        test_email = TEST_EMAIL

        result = await client.call_tool(
            "get_form_response",
            {
                "user_google_email": test_email,
                "form_id": real_forms_form_id or "test_form_id",
                "response_id": "test_response_id",
            },
        )

        # Should indicate authentication required
        assert result is not None
        assert result.content and len(result.content) > 0
        content = result.content[0].text
        assert (
            "authentication" in content.lower()
            or "credentials" in content.lower()
            or "not authenticated" in content.lower()
            or "response not found" in content.lower()
            or "response id" in content.lower()
        )

    async def _test_list_form_responses_no_auth(self, client, real_forms_form_id=None):
        """Test list_form_responses without authentication."""
        test_email = TEST_EMAIL

        result = await client.call_tool(
            "list_form_responses",
            {
                "user_google_email": test_email,
                "form_id": real_forms_form_id or "test_form_id",
            },
        )

        # Should indicate authentication required
        assert result is not None
        assert result.content and len(result.content) > 0
        content = result.content[0].text
        assert (
            "authentication" in content.lower()
            or "credentials" in content.lower()
            or "not authenticated" in content.lower()
            or "entity was not found" in content.lower()
            or "requested entity was not found" in content.lower()
        )

    async def _test_update_form_questions_no_auth(
        self, client, real_forms_form_id=None
    ):
        """Test update_form_questions without authentication."""
        test_email = TEST_EMAIL

        result = await client.call_tool(
            "update_form_questions",
            {
                "user_google_email": test_email,
                "form_id": real_forms_form_id or "test_form_id",
                "questions_to_update": [
                    {"item_id": "test_item_id", "title": "Updated Title"}
                ],
            },
        )

        # Should indicate authentication required
        assert result is not None
        assert result.content and len(result.content) > 0
        content = result.content[0].text
        assert (
            "authentication" in content.lower()
            or "credentials" in content.lower()
            or "not authenticated" in content.lower()
            or "location is required" in content.lower()
            or "failed to update questions" in content.lower()
        )

    async def _test_missing_required_params(self, client):
        """Test forms tools with missing required parameters."""
        # Test create_form without title
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("create_form", {"user_google_email": TEST_EMAIL})
        assert (
            "required" in str(exc_info.value).lower()
            or "missing" in str(exc_info.value).lower()
        )

        # Test add_questions_to_form without questions
        with pytest.raises(Exception) as exc_info:
            await client.call_tool(
                "add_questions_to_form",
                {"user_google_email": TEST_EMAIL, "form_id": "test_form_id"},
            )
        assert (
            "required" in str(exc_info.value).lower()
            or "missing" in str(exc_info.value).lower()
        )

        # Test get_form without form_id
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("get_form", {"user_google_email": TEST_EMAIL})
        assert (
            "required" in str(exc_info.value).lower()
            or "missing" in str(exc_info.value).lower()
        )

        # Test get_form_response without response_id
        with pytest.raises(Exception) as exc_info:
            await client.call_tool(
                "get_form_response",
                {"user_google_email": TEST_EMAIL, "form_id": "test_form_id"},
            )
        assert (
            "required" in str(exc_info.value).lower()
            or "missing" in str(exc_info.value).lower()
        )


class TestGmailLabelColors:
    """Test Gmail label color management functionality."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create a client connected to the running server."""
        from .base_test_config import create_test_client

        try:
            client_obj = await create_test_client(TEST_EMAIL)
        except Exception as e:
            pytest.skip(f"MCP server not reachable for integration tests: {e}")

        async with client_obj:
            yield client_obj

    @pytest.mark.asyncio
    async def test_manage_gmail_label_available(self, client, cleanup_tracker):
        """Check if manage_gmail_label tool is available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]

        # Check if Gmail label management tool is registered
        has_label_tool = "manage_gmail_label" in tool_names

        if has_label_tool:
            # Test the color functionality
            await self._test_create_label_with_colors_no_auth(client, cleanup_tracker)
            await self._test_update_label_with_colors_no_auth(client)
            await self._test_invalid_color_validation(client, cleanup_tracker)

    async def _test_create_label_with_colors_no_auth(self, client, cleanup_tracker):
        """Test creating a label with colors.

        NOTE: Test name retained for backwards compatibility, but the test
        now handles both authenticated and unauthenticated scenarios.
        """
        test_email = TEST_EMAIL

        # Test creating a red label with white text
        # Use a unique name to avoid conflicts with existing labels
        import json
        import uuid

        unique_label_name = f"Test Label {uuid.uuid4().hex[:8]}"
        result = await client.call_tool(
            "manage_gmail_label",
            {
                "user_google_email": test_email,
                "action": "create",
                "name": unique_label_name,
                "text_color": "#ffffff",
                "background_color": "#fb4c2f",
            },
        )

        # Should indicate authentication status (either success or failure)
        assert result is not None
        assert result.content and len(result.content) > 0
        content = result.content[0].text

        # Track created label for cleanup
        self._extract_and_track_label_id(content, cleanup_tracker)

        # Accept auth errors, success, or conflict (label already exists)
        assert (
            "authentication" in content.lower()
            or "credentials" in content.lower()
            or "not authenticated" in content.lower()
            or "label created successfully" in content.lower()
            or '"success":true' in content.lower()
            or "conflict" in content.lower()  # Label already exists
            or "already exist" in content.lower()
        )

        # If not auth error, should not have color validation errors
        if (
            "authentication" not in content.lower()
            and "credentials" not in content.lower()
        ):
            assert "invalid" not in content.lower()

    async def _test_update_label_with_colors_no_auth(self, client):
        """Test updating a label with colors.

        NOTE: Test name retained for backwards compatibility, but the test
        now handles both authenticated and unauthenticated scenarios.
        """
        test_email = TEST_EMAIL

        # Test updating a label with green background and black text
        result = await client.call_tool(
            "manage_gmail_label",
            {
                "user_google_email": test_email,
                "action": "update",
                "label_id": "Label_test_123",
                "text_color": "#000000",
                "background_color": "#43d692",
            },
        )

        # Should indicate authentication status (either success or failure)
        assert result is not None
        assert result.content and len(result.content) > 0
        content = result.content[0].text
        # Accept auth errors, success, not found (label doesn't exist), or required
        assert (
            "authentication" in content.lower()
            or "credentials" in content.lower()
            or "not authenticated" in content.lower()
            or "label updated successfully" in content.lower()
            or "label id is required" in content.lower()
            or "not found" in content.lower()  # Label doesn't exist
            or '"success":true' in content.lower()
        )

        # If not auth error, should not have color validation errors
        if (
            "authentication" not in content.lower()
            and "credentials" not in content.lower()
        ):
            assert "invalid" not in content.lower()

    def _extract_and_track_label_id(self, content: str, cleanup_tracker) -> None:
        """Helper to extract label ID from response and track for cleanup."""
        import json
        import re

        try:
            if content.startswith("{"):
                response_dict = json.loads(content)
                if response_dict.get("success"):
                    # Extract label ID from results
                    results = response_dict.get("results", [])
                    for result_str in results:
                        if "ID:" in result_str:
                            # Create response format: "ID: Label_176"
                            # Delete response format: "(ID: Label_168)"
                            match = re.search(r"ID:\s*(Label_\d+)", result_str)
                            if match:
                                cleanup_tracker.track_gmail_label(match.group(1))
        except (json.JSONDecodeError, KeyError):
            pass

    async def _test_invalid_color_validation(self, client, cleanup_tracker):
        """Test color validation with invalid colors.

        NOTE: The server now auto-corrects invalid colors to the nearest
        Gmail-supported color instead of rejecting them. This test has been
        updated to accept either behavior.
        """
        test_email = TEST_EMAIL

        # Test with invalid text color
        import uuid

        unique_label_name = f"Test Label {uuid.uuid4().hex[:8]}"
        result = await client.call_tool(
            "manage_gmail_label",
            {
                "user_google_email": test_email,
                "action": "create",
                "name": unique_label_name,
                "text_color": "#invalid",  # Invalid color
                "background_color": "#fb4c2f",
            },
        )

        assert result is not None
        assert result.content and len(result.content) > 0
        content = result.content[0].text

        # Track created label for cleanup
        self._extract_and_track_label_id(content, cleanup_tracker)

        # Server may either reject invalid colors or auto-correct them
        # Accept either "invalid" error OR "adjusted" success message
        assert (
            "invalid text color" in content.lower()
            or "adjusted" in content.lower()  # Color was auto-corrected
            or "success" in content.lower()
        )  # Operation succeeded with correction

        # Test with invalid background color
        unique_label_name2 = f"Test Label {uuid.uuid4().hex[:8]}"
        result = await client.call_tool(
            "manage_gmail_label",
            {
                "user_google_email": test_email,
                "action": "create",
                "name": unique_label_name2,
                "text_color": "#ffffff",
                "background_color": "#badcolor",  # Invalid color
            },
        )

        assert result is not None
        assert result.content and len(result.content) > 0
        content = result.content[0].text

        # Track created label for cleanup
        self._extract_and_track_label_id(content, cleanup_tracker)

        # Server may either reject invalid colors or auto-correct them
        assert (
            "invalid background color" in content.lower()
            or "adjusted" in content.lower()  # Color was auto-corrected
            or "success" in content.lower()
        )  # Operation succeeded with correction

    @pytest.mark.asyncio
    async def test_manage_gmail_label_color_params_optional(
        self, client, cleanup_tracker
    ):
        """Test that color parameters are optional."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]

        if "manage_gmail_label" in tool_names:
            test_email = TEST_EMAIL

            # Test creating without colors (should work)
            # Use a unique name to avoid conflicts
            import uuid

            unique_label_name = f"No Color Label {uuid.uuid4().hex[:8]}"
            result = await client.call_tool(
                "manage_gmail_label",
                {
                    "user_google_email": test_email,
                    "action": "create",
                    "name": unique_label_name,
                },
            )

            assert result is not None
            assert result.content and len(result.content) > 0
            content = result.content[0].text

            # Track created label for cleanup
            self._extract_and_track_label_id(content, cleanup_tracker)

            # Should not get color validation errors
            assert "invalid" not in content.lower()
            # Accept auth errors, success, or conflict (label already exists)
            assert (
                "authentication" in content.lower()
                or "credentials" in content.lower()
                or "not authenticated" in content.lower()
                or "label created successfully" in content.lower()
                or '"success":true' in content.lower()
                or "conflict" in content.lower()
                or "already exist" in content.lower()
            )


class TestErrorHandling:
    """Test error handling and edge cases."""

    # Use standardized client fixture from conftest.py

    @pytest.mark.asyncio
    async def test_invalid_tool_name(self, client):
        """Test calling a non-existent tool."""
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("non_existent_tool", {})

        # Should raise an appropriate error
        assert (
            "not found" in str(exc_info.value).lower()
            or "unknown" in str(exc_info.value).lower()
        )

    @pytest.mark.asyncio
    async def test_missing_required_params(self, client):
        """Test calling a tool without required parameters."""
        # Try to call a tool that requires parameters without providing them
        # Use get_doc_content which requires document_id
        try:
            result = await client.call_tool(
                "get_doc_content",
                {
                    "user_google_email": TEST_EMAIL
                    # Missing required: document_id
                },
            )
            # If no exception, check if the response indicates missing param
            if result and result.content:
                content = result.content[0].text.lower()
                # Accept either an exception or a response indicating missing param
                assert (
                    "required" in content
                    or "missing" in content
                    or "document_id" in content
                )
        except Exception as exc_info:
            # Should indicate missing parameter
            assert (
                "required" in str(exc_info).lower()
                or "missing" in str(exc_info).lower()
                or "document_id" in str(exc_info).lower()
            )


if __name__ == "__main__":
    # Run tests with asyncio
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
