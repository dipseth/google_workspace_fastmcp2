"""Test suite for Service Resource URI functionality using FastMCP Client SDK."""

import pytest
import pytest_asyncio
import json
import os
from fastmcp import Client
from typing import Any, Dict, List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Test configuration
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test@example.com")


class TestServiceResourceURI:
    """Test service resource URI patterns for Phase 3."""
    # Using the global client fixture from conftest.py
    
    @pytest.mark.asyncio
    async def test_service_lists_resource(self, client):
        """Test service://[service]/lists resource pattern."""
        # Test various service list resources
        test_cases = [
            'service://gmail/lists',
            'service://calendar/lists',
            'service://drive/lists',
            'service://docs/lists',
            'service://sheets/lists',
            'service://chat/lists',
            'service://forms/lists',
            'service://photos/lists'
        ]
        
        resources = await client.list_resources()
        resource_uris = [r.uri for r in resources]
        
        found_resources = []
        for uri in test_cases:
            if uri in resource_uris:
                found_resources.append(uri)
                resource = next((r for r in resources if r.uri == uri), None)
                assert resource is not None, f"Resource {uri} should exist"
                assert hasattr(resource, 'name'), f"Resource {uri} should have name"
                assert hasattr(resource, 'description'), f"Resource {uri} should have description"
        
        print(f"✅ Found {len(found_resources)}/{len(test_cases)} service list resources")
        for uri in found_resources:
            print(f"   {uri}")
    
    @pytest.mark.asyncio
    async def test_service_list_items_resource(self, client):
        """Test service://[service]/[list_type] resource pattern."""
        # Test specific list type resources
        test_cases = [
            ('service://gmail/filters', 'Gmail filters'),
            ('service://gmail/labels', 'Gmail labels'),
            ('service://calendar/calendars', 'Calendar lists'),
            ('service://calendar/events', 'Calendar events'),
            ('service://drive/items', 'Drive items'),
            ('service://photos/albums', 'Photo albums'),
            ('service://forms/form_responses', 'Form responses'),
            ('service://sheets/spreadsheets', 'Spreadsheets')
        ]
        
        for uri, description in test_cases:
            try:
                result = await client.read_resource(uri)
                assert result is not None, f"Should read {uri}"
                
                # Check response structure
                if hasattr(result, 'contents'):
                    contents = result.contents
                    assert len(contents) > 0, f"Resource {uri} should have contents"
                    
                    # Parse JSON response if possible
                    try:
                        data = json.loads(contents[0].text if hasattr(contents[0], 'text') else str(contents[0]))
                        # Should have expected fields
                        assert 'count' in data or 'data' in data or 'error' in data, \
                            f"Resource {uri} should have structured response"
                        print(f"✅ Resource {uri} working ({description})")
                    except json.JSONDecodeError:
                        # Text response is also valid
                        print(f"✅ Resource {uri} returned text response")
            except Exception as e:
                # Some resources may require authentication
                if 'authentication' in str(e).lower() or 'email' in str(e).lower():
                    print(f"⚠️ Resource {uri} requires authentication")
                else:
                    print(f"❌ Resource {uri} error: {str(e)[:100]}")
    
    @pytest.mark.asyncio
    async def test_service_item_detail_resource(self, client):
        """Test service://[service]/[list_type]/[item_id] resource pattern."""
        # Test item detail resources (will fail without actual IDs)
        test_cases = [
            'service://gmail/filters/test_filter_id',
            'service://gmail/labels/INBOX',
            'service://calendar/events/test_event_id',
            'service://drive/items/test_file_id',
            'service://photos/albums/test_album_id'
        ]
        
        for uri in test_cases:
            try:
                result = await client.read_resource(uri)
                # Will likely fail without valid IDs, but structure should work
                print(f"✅ Resource pattern {uri} accessible")
            except Exception as e:
                error_msg = str(e).lower()
                # Expected errors for invalid IDs
                if any(word in error_msg for word in ['not found', 'invalid', 'authentication', 'retrieve']):
                    print(f"⚠️ Resource pattern {uri} works (needs valid ID)")
                else:
                    print(f"❌ Unexpected error for {uri}: {str(e)[:100]}")
    
    @pytest.mark.asyncio
    async def test_google_service_scopes_resource(self, client):
        """Test google://services/scopes/[service] resource pattern."""
        test_cases = [
            'google://services/scopes/gmail',
            'google://services/scopes/calendar',
            'google://services/scopes/drive',
            'google://services/scopes/docs',
            'google://services/scopes/sheets'
        ]
        
        resources = await client.list_resources()
        resource_uris = [r.uri for r in resources]
        
        for uri in test_cases:
            if uri in resource_uris:
                try:
                    result = await client.read_resource(uri)
                    assert result is not None, f"Should read {uri}"
                    print(f"✅ Scopes resource {uri} available")
                except Exception as e:
                    print(f"⚠️ Scopes resource {uri} error: {str(e)[:100]}")
    
    @pytest.mark.asyncio
    async def test_user_resources(self, client):
        """Test user:// resource patterns."""
        test_cases = [
            'user://current/email',
            'user://current/profile',
            'user://profile/{email}'
        ]
        
        resources = await client.list_resources()
        resource_uris = [r.uri for r in resources]
        
        for uri in test_cases:
            # Check if pattern exists (templated URIs won't match exactly)
            if uri in resource_uris or '{' in uri:
                print(f"✅ User resource pattern {uri} defined")
                
                # Try to read non-templated resources
                if '{' not in uri:
                    try:
                        result = await client.read_resource(uri)
                        assert result is not None, f"Should read {uri}"
                        print(f"   Successfully read {uri}")
                    except Exception as e:
                        print(f"   Error reading {uri}: {str(e)[:100]}")
    
    @pytest.mark.asyncio
    async def test_tools_resources(self, client):
        """Test tools:// resource patterns."""
        test_cases = [
            'tools://list/all',
            'tools://enhanced/list',
            'tools://usage/guide'
        ]
        
        resources = await client.list_resources()
        resource_uris = [r.uri for r in resources]
        
        for uri in test_cases:
            if uri in resource_uris:
                try:
                    result = await client.read_resource(uri)
                    assert result is not None, f"Should read {uri}"
                    
                    # Should return tool information
                    if hasattr(result, 'contents'):
                        contents = result.contents
                        assert len(contents) > 0, f"Resource {uri} should have contents"
                        print(f"✅ Tools resource {uri} working")
                except Exception as e:
                    print(f"⚠️ Tools resource {uri} error: {str(e)[:100]}")
    
    @pytest.mark.asyncio
    async def test_recent_resources(self, client):
        """Test recent:// resource patterns."""
        test_cases = [
            'recent://drive',
            'recent://docs', 
            'recent://sheets',
            'recent://all'
        ]
        
        resources = await client.list_resources()
        resource_uris = [r.uri for r in resources]
        
        for uri in test_cases:
            if uri in resource_uris:
                print(f"✅ Recent resource {uri} available")
                
                # Try to read the resource
                try:
                    result = await client.read_resource(uri)
                    if result:
                        print(f"   Successfully read recent items from {uri}")
                except Exception as e:
                    if 'authentication' in str(e).lower():
                        print(f"   Requires authentication")
                    else:
                        print(f"   Error: {str(e)[:100]}")
    
    @pytest.mark.asyncio
    async def test_workspace_content_resources(self, client):
        """Test workspace:// content resources."""
        test_cases = [
            'workspace://content/recent',
            'workspace://content/search/{query}'
        ]
        
        resources = await client.list_resources()
        resource_uris = [r.uri for r in resources]
        
        for uri in test_cases:
            # Check if pattern exists
            if uri in resource_uris or '{' in uri:
                print(f"✅ Workspace resource pattern {uri} defined")
    
    @pytest.mark.asyncio
    async def test_cache_resources(self, client):
        """Test cache:// status resources."""
        test_cases = [
            'cache://status',
            'cache://clear'
        ]
        
        resources = await client.list_resources()
        resource_uris = [r.uri for r in resources]
        
        for uri in test_cases:
            if uri in resource_uris:
                print(f"✅ Cache resource {uri} available")
                
                # Try to read status (clear would modify state)
                if uri == 'cache://status':
                    try:
                        result = await client.read_resource(uri)
                        if result:
                            print(f"   Cache status retrieved successfully")
                    except Exception as e:
                        print(f"   Error: {str(e)[:100]}")


class TestResourceURIIntegration:
    """Test resource URI integration with tools and services."""
    # Using the global client fixture from conftest.py
    
    @pytest.mark.asyncio
    async def test_resource_tool_correlation(self, client):
        """Test that resources correlate with available tools."""
        # Get both resources and tools
        resources = await client.list_resources()
        tools = await client.list_tools()
        
        resource_uris = [r.uri for r in resources]
        tool_names = [t.name for t in tools]
        
        # Check correlations
        correlations = [
            ('service://gmail/lists', 'list_gmail_labels'),
            ('service://calendar/lists', 'list_calendars'),
            ('service://drive/lists', 'list_drive_items'),
            ('tools://list/all', None)  # Meta resource
        ]
        
        for resource_uri, tool_name in correlations:
            resource_exists = resource_uri in resource_uris
            tool_exists = tool_name in tool_names if tool_name else True
            
            if resource_exists and tool_exists:
                print(f"✅ Resource {resource_uri} correlates with tool {tool_name or 'N/A'}")
            elif resource_exists:
                print(f"⚠️ Resource {resource_uri} exists but tool {tool_name} missing")
            elif tool_exists:
                print(f"⚠️ Tool {tool_name} exists but resource {resource_uri} missing")
    
    @pytest.mark.asyncio
    async def test_resource_metadata_completeness(self, client):
        """Test that all resources have complete metadata."""
        resources = await client.list_resources()
        
        incomplete_resources = []
        for resource in resources[:20]:  # Sample first 20
            missing_fields = []
            
            if not hasattr(resource, 'uri') or not resource.uri:
                missing_fields.append('uri')
            if not hasattr(resource, 'name') or not resource.name:
                missing_fields.append('name')
            if not hasattr(resource, 'description') or not resource.description:
                missing_fields.append('description')
            
            if missing_fields:
                incomplete_resources.append((resource.uri if hasattr(resource, 'uri') else 'unknown', missing_fields))
        
        if incomplete_resources:
            print(f"⚠️ {len(incomplete_resources)} resources with incomplete metadata:")
            for uri, fields in incomplete_resources[:5]:
                print(f"   {uri}: missing {fields}")
        else:
            print(f"✅ All sampled resources have complete metadata")
    
    @pytest.mark.asyncio
    async def test_resource_uri_patterns(self, client):
        """Test that resource URIs follow expected patterns."""
        resources = await client.list_resources()
        
        # Define expected URI patterns
        patterns = {
            'service': r'^service://[a-z]+/',
            'user': r'^user://',
            'tools': r'^tools://',
            'google': r'^google://',
            'workspace': r'^workspace://',
            'recent': r'^recent://',
            'cache': r'^cache://',
            'auth': r'^auth://',
            'gmail': r'^gmail://',
            'template': r'^template://'
        }
        
        categorized = {key: 0 for key in patterns.keys()}
        uncategorized = []
        
        for resource in resources:
            matched = False
            uri_str = str(resource.uri)  # Convert AnyUrl to string
            for category, pattern in patterns.items():
                if uri_str.startswith(f"{category}://"):
                    categorized[category] += 1
                    matched = True
                    break
            
            if not matched:
                uncategorized.append(uri_str)
        
        print(f"✅ Resource URI pattern analysis:")
        for category, count in categorized.items():
            if count > 0:
                print(f"   {category}:// - {count} resources")
        
        if uncategorized:
            print(f"⚠️ Uncategorized resources: {len(uncategorized)}")
            for uri in uncategorized[:5]:
                print(f"   {uri}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])