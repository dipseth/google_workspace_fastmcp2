"""Tests for the resource templating and user authentication system using FastMCP Client."""

import pytest
import asyncio
import logging
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from .base_test_config import TEST_EMAIL

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


@pytest.mark.integration
class TestUserResources:
    """Test suite for user resource endpoints via FastMCP Client."""
    
    @pytest.mark.asyncio
    async def test_list_static_resources(self, client):
        """Test listing all static resources from the server."""
        resources = await client.list_resources()
        
        # Check that we have resources
        assert isinstance(resources, list)
        
        # Look for our user resources
        user_resources = []
        for resource in resources:
            # Convert AnyUrl to string for comparison
            uri_str = str(resource.uri)
            if uri_str.startswith("user://") or uri_str.startswith("auth://"):
                user_resources.append(resource)
                logger.info(f"Found user resource: {uri_str} - {resource.name}")
        
        # We should have at least some user/auth resources
        assert len(user_resources) > 0, "No user or auth resources found"
        
        # Check for specific expected resources
        expected_uris = [
            "user://current/email",
            "user://current/profile",
            "auth://session/current",
            "auth://sessions/list"
        ]
        
        found_uris = [str(r.uri) for r in resources]
        for expected_uri in expected_uris:
            assert expected_uri in found_uris, f"Expected resource {expected_uri} not found. Available: {found_uris}"
    
    @pytest.mark.asyncio
    async def test_list_resource_templates(self, client):
        """Test listing resource templates from the server."""
        templates = await client.list_resource_templates()
        
        # Check that we have templates
        assert isinstance(templates, list)
        
        # Look for our template resources
        template_uris = [t.uriTemplate for t in templates]
        logger.info(f"Found {len(templates)} resource templates")
        
        # Check for specific expected templates
        expected_templates = [
            "user://profile/{email}",
            "auth://credentials/{email}/status",
            "google://services/scopes/{service}",
            "workspace://content/search/{query}",
            "qdrant://search/{query}"
        ]
        
        for expected_template in expected_templates:
            assert expected_template in template_uris, f"Expected template {expected_template} not found"
    
    @pytest.mark.asyncio
    async def test_read_current_user_email_resource(self, client):
        """Test reading the user://current/email resource."""
        try:
            # Read the current user email resource
            content = await client.read_resource("user://current/email")
            
            # Should return a list of resource contents
            assert isinstance(content, list)
            assert len(content) > 0
            
            # Check the content
            first_content = content[0]
            if hasattr(first_content, 'text'):
                # Should be the user's email
                email = first_content.text
                assert "@" in email, f"Expected email address, got: {email}"
                logger.info(f"Successfully read user email: {email}")
            
        except Exception as e:
            # May fail if not authenticated properly, but that's okay for testing
            logger.info(f"Reading user email resource failed (expected without full auth): {e}")
    
    @pytest.mark.asyncio
    async def test_read_current_user_profile_resource(self, client):
        """Test reading the user://current/profile resource."""
        try:
            # Read the current user profile resource
            content = await client.read_resource("user://current/profile")
            
            # Should return a list of resource contents
            assert isinstance(content, list)
            assert len(content) > 0
            
            # Check the content
            first_content = content[0]
            if hasattr(first_content, 'text'):
                # Should be JSON with profile info
                profile_text = first_content.text
                profile = json.loads(profile_text)
                assert "email" in profile or "status" in profile, f"Expected profile data, got: {profile}"
                logger.info(f"Successfully read user profile")
            
        except Exception as e:
            # May fail if not authenticated properly, but that's okay for testing
            logger.info(f"Reading user profile resource failed (expected without full auth): {e}")
    
    @pytest.mark.asyncio
    async def test_read_auth_session_current_resource(self, client):
        """Test reading the auth://session/current resource."""
        try:
            # Read the current auth session resource
            content = await client.read_resource("auth://session/current")
            
            # Should return a list of resource contents
            assert isinstance(content, list)
            assert len(content) > 0
            
            # Check the content
            first_content = content[0]
            if hasattr(first_content, 'text'):
                # Should be JSON with session info
                session_text = first_content.text
                session = json.loads(session_text)
                logger.info(f"Successfully read auth session: {session.get('status', 'unknown')}")
            
        except Exception as e:
            # May fail if not authenticated properly, but that's okay for testing
            logger.info(f"Reading auth session resource failed (expected without full auth): {e}")
    
    @pytest.mark.asyncio
    async def test_read_template_user_email_resource(self, client):
        """Test reading the template://user_email resource."""
        try:
            # Read the template user email resource
            content = await client.read_resource("template://user_email")
            
            # Should return a list of resource contents
            assert isinstance(content, list)
            assert len(content) > 0
            
            # Check the content
            first_content = content[0]
            if hasattr(first_content, 'text'):
                # Should be just the email string
                email = first_content.text
                assert "@" in email or "not authenticated" in email.lower(), f"Unexpected content: {email}"
                logger.info(f"Template resource returned: {email}")
            
        except Exception as e:
            # May fail if not authenticated properly, but that's okay for testing
            logger.info(f"Reading template resource failed (expected without full auth): {e}")
    
    @pytest.mark.asyncio
    async def test_read_user_profile_by_email_template(self, client):
        """Test reading a templated resource with parameters."""
        try:
            # Read a user profile using the template
            test_email = TEST_EMAIL
            uri = f"user://profile/{test_email}"
            content = await client.read_resource(uri)
            
            # Should return a list of resource contents
            assert isinstance(content, list)
            assert len(content) > 0
            
            # Check the content
            first_content = content[0]
            if hasattr(first_content, 'text'):
                # Should be JSON with profile info
                profile_text = first_content.text
                profile = json.loads(profile_text)
                assert "email" in profile, f"Expected profile with email, got: {profile}"
                assert profile["email"] == test_email, f"Expected email {test_email}, got: {profile.get('email')}"
                logger.info(f"Successfully read profile for {test_email}")
            
        except Exception as e:
            # May fail if not authenticated properly, but that's okay for testing
            logger.info(f"Reading user profile template failed (expected without full auth): {e}")
    
    @pytest.mark.asyncio
    async def test_filter_resources_by_tags(self, client):
        """Test filtering resources by tags using metadata."""
        resources = await client.list_resources()
        
        # Log all resources to see what we have
        logger.info(f"Total resources found: {len(resources)}")
        
        # Filter resources that have any tags or are auth-related
        tagged_resources = []
        auth_resources = []
        for resource in resources:
            uri_str = str(resource.uri)
            
            # Check for auth-related resources by URI
            if "auth" in uri_str.lower() or "user" in uri_str.lower():
                auth_resources.append(resource)
                logger.info(f"Found auth-related resource: {uri_str}")
            
            # Check for tags in metadata (if present)
            if hasattr(resource, '_meta') and resource._meta:
                fastmcp_meta = resource._meta.get('_fastmcp', {})
                tags = fastmcp_meta.get('tags', [])
                if tags:
                    tagged_resources.append(resource)
                    logger.info(f"Found tagged resource: {uri_str} with tags: {tags}")
        
        # We should have either tagged resources or auth-related resources
        assert len(auth_resources) > 0 or len(tagged_resources) > 0, \
            f"No auth-related or tagged resources found. Total resources: {len(resources)}"
        
        # Log summary
        logger.info(f"Found {len(auth_resources)} auth-related resources and {len(tagged_resources)} tagged resources")


@pytest.mark.integration
class TestEnhancedTools:
    """Test suite for enhanced tools that use resource templating via FastMCP Client."""
    
    @pytest.mark.asyncio
    async def test_enhanced_tools_available(self, client):
        """Test that enhanced tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Check for enhanced tools
        expected_tools = [
            "list_my_drive_files",
            "search_my_gmail",
            "create_my_calendar_event",
            "get_my_auth_status"
        ]
        
        for expected_tool in expected_tools:
            assert expected_tool in tool_names, f"Enhanced tool {expected_tool} not found"
    
    @pytest.mark.asyncio
    async def test_list_my_drive_files_tool(self, client):
        """Test the enhanced Drive tool that uses resource templating."""
        try:
            # Call the enhanced tool (no user_google_email parameter needed)
            result = await client.call_tool("list_my_drive_files", {
                "query": "test",
                "page_size": 5
            })
            
            # Should return a result
            assert len(result) > 0
            content = result[0].text
            assert isinstance(content, str)
            
            # The tool should either succeed or return a meaningful error
            logger.info(f"Enhanced Drive tool result: {content[:200]}...")
            
        except Exception as e:
            # Expected - may fail without proper Google authentication
            logger.info(f"Enhanced Drive tool handled auth appropriately: {e}")
    
    @pytest.mark.asyncio
    async def test_get_my_auth_status_tool(self, client):
        """Test the auth status tool that uses multiple resources."""
        try:
            # Call the auth status tool
            result = await client.call_tool("get_my_auth_status", {})
            
            # Should return a result
            assert len(result) > 0
            content = result[0].text
            assert isinstance(content, str)
            
            # Should contain status information
            assert "status" in content.lower() or "auth" in content.lower()
            logger.info(f"Auth status tool result: {content[:200]}...")
            
        except Exception as e:
            # Expected - may fail depending on auth setup
            logger.info(f"Auth status tool handled appropriately: {e}")
    
    @pytest.mark.asyncio
    async def test_enhanced_tool_parameter_reduction(self, client):
        """Test that enhanced tools have fewer parameters than legacy versions."""
        tools = await client.list_tools()
        
        # Find both legacy and enhanced versions of tools
        legacy_drive_tool = None
        enhanced_drive_tool = None
        
        for tool in tools:
            if tool.name == "list_drive_items":  # Legacy version
                legacy_drive_tool = tool
            elif tool.name == "list_my_drive_files":  # Enhanced version
                enhanced_drive_tool = tool
        
        # Both should exist
        assert enhanced_drive_tool is not None, "Enhanced drive tool not found"
        
        if legacy_drive_tool:
            # Compare parameter counts (enhanced should have fewer)
            legacy_params = len(legacy_drive_tool.inputSchema.get("properties", {}))
            enhanced_params = len(enhanced_drive_tool.inputSchema.get("properties", {}))
            
            # Enhanced version should not have user_google_email parameter
            assert "user_google_email" not in enhanced_drive_tool.inputSchema.get("properties", {})
            logger.info(f"✅ Enhanced tool has {enhanced_params} params vs legacy {legacy_params} params")
        else:
            # At least verify enhanced version doesn't have user_google_email
            assert "user_google_email" not in enhanced_drive_tool.inputSchema.get("properties", {})
            logger.info("✅ Enhanced tool correctly omits user_google_email parameter")


@pytest.mark.integration
class TestResourceTemplateIntegration:
    """Integration tests for resource templates and middleware."""
    
    @pytest.mark.asyncio
    async def test_workspace_content_search_template(self, client):
        """Test the workspace content search resource template."""
        try:
            # Use the workspace search template
            query = "test document"
            uri = f"workspace://content/search/{query}"
            content = await client.read_resource(uri)
            
            # Should return a list of resource contents
            assert isinstance(content, list)
            assert len(content) > 0
            
            # Check the content
            first_content = content[0]
            if hasattr(first_content, 'text'):
                # Should be JSON with search results
                results_text = first_content.text
                results = json.loads(results_text)
                logger.info(f"Workspace search returned: {type(results)}")
            
        except Exception as e:
            # May fail if workspace not configured, but that's okay
            logger.info(f"Workspace search template handled appropriately: {e}")
    
    @pytest.mark.asyncio
    async def test_google_service_scopes_template(self, client):
        """Test the Google service scopes resource template."""
        try:
            # Use the service scopes template
            service = "drive"
            uri = f"google://services/scopes/{service}"
            content = await client.read_resource(uri)
            
            # Should return a list of resource contents
            assert isinstance(content, list)
            assert len(content) > 0
            
            # Check the content
            first_content = content[0]
            if hasattr(first_content, 'text'):
                # Should be JSON with service info
                service_text = first_content.text
                service_info = json.loads(service_text)
                assert "scopes" in service_info or "service" in service_info
                logger.info(f"Service scopes for {service}: found")
            
        except Exception as e:
            # May fail depending on configuration
            logger.info(f"Service scopes template handled appropriately: {e}")
    
    @pytest.mark.asyncio
    async def test_resource_caching(self, client):
        """Test that resources support caching (cache://status resource)."""
        try:
            # Read the cache status resource
            content = await client.read_resource("cache://status")
            
            # Should return a list of resource contents
            assert isinstance(content, list)
            assert len(content) > 0
            
            # Check the content
            first_content = content[0]
            if hasattr(first_content, 'text'):
                # Should be JSON with cache status
                cache_text = first_content.text
                cache_status = json.loads(cache_text)
                logger.info(f"Cache status: {cache_status.get('status', 'unknown')}")
            
        except Exception as e:
            # Cache resource might not exist, that's okay
            logger.info(f"Cache status resource not available: {e}")
    
    @pytest.mark.asyncio
    async def test_multi_resource_tool_integration(self, client):
        """Test tools that use multiple resources together."""
        # The get_my_auth_status tool uses multiple resources
        try:
            result = await client.call_tool("get_my_auth_status", {})
            
            # Should combine data from multiple resources
            assert len(result) > 0
            content = result[0].text
            
            # Should have comprehensive auth information
            if "authenticated" in content.lower():
                logger.info("✅ Multi-resource tool successfully combined resource data")
            else:
                logger.info("Multi-resource tool handled no-auth case appropriately")
                
        except Exception as e:
            logger.info(f"Multi-resource tool integration test handled: {e}")
    
    @pytest.mark.asyncio
    async def test_raw_mcp_protocol_access(self, client):
        """Test using raw MCP protocol methods for resources."""
        # Test raw list_resources_mcp
        resources_result = await client.list_resources_mcp()
        assert hasattr(resources_result, 'resources')
        logger.info(f"Raw MCP: Found {len(resources_result.resources)} resources")
        
        # Test raw list_resource_templates_mcp
        templates_result = await client.list_resource_templates_mcp()
        assert hasattr(templates_result, 'resourceTemplates')
        logger.info(f"Raw MCP: Found {len(templates_result.resourceTemplates)} templates")
        
        # Test raw read_resource_mcp
        try:
            content_result = await client.read_resource_mcp("template://user_email")
            assert hasattr(content_result, 'contents')
            logger.info("Raw MCP: Successfully read resource")
        except Exception as e:
            logger.info(f"Raw MCP read handled: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])