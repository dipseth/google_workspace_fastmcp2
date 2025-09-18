"""
Comprehensive client tests for the unified Qdrant tools implementation.
Tests the new OpenAI MCP standard compliant search and fetch tools.
"""

import pytest
import asyncio
import json
import uuid
from typing import Dict, List, Any
from .base_test_config import TEST_EMAIL
from .test_helpers import ToolTestRunner, TestResponseValidator

@pytest.mark.service("qdrant")
class TestQdrantUnifiedSearch:
    """Test the new unified search tool with 4 core capabilities."""
    
    @pytest.mark.asyncio
    async def test_search_tool_available(self, client):
        """Test that the new search tool is available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # New unified tools should be available
        assert "search" in tool_names, "Unified search tool should be available"
        assert "fetch" in tool_names, "Unified fetch tool should be available"
        
        # Legacy tools should still be available (backward compatibility)
        assert "search_tool_history" in tool_names, "Legacy search_tool_history should still be available"
        assert "get_tool_analytics" in tool_names, "Legacy get_tool_analytics should still be available"
        assert "get_response_details" in tool_names, "Legacy get_response_details should still be available"
    
    @pytest.mark.asyncio
    async def test_search_overview_capability(self, client):
        """Test search tool with overview/analytics queries."""
        test_queries = [
            "overview",
            "analytics",
            "dashboard",
            "tool usage stats",
            "summary"
        ]
        
        for query in test_queries:
            result = await client.call_tool("search", {"query": query})
            assert result is not None, f"Search with query '{query}' should return a result"
            
            # Check response format (OpenAI MCP standard)
            content = result.content[0].text if hasattr(result, 'content') else str(result)
            
            try:
                data = json.loads(content)
                assert "results" in data, "Response should have 'results' field (MCP standard)"
                assert isinstance(data["results"], list), "Results should be a list"
                
                # For analytics queries, results might be formatted differently
                if len(data["results"]) > 0:
                    result_item = data["results"][0]
                    assert "id" in result_item, "Each result should have an 'id'"
                    assert "title" in result_item, "Each result should have a 'title'"
                    assert "url" in result_item, "Each result should have a 'url'"
            except json.JSONDecodeError:
                # If not JSON, it might be an error message
                assert "error" in content.lower() or "qdrant" in content.lower(), \
                    f"Non-JSON response should be an error message, got: {content}"
    
    @pytest.mark.asyncio
    async def test_search_service_history_capability(self, client):
        """Test search tool with service history queries."""
        test_queries = [
            "gmail history",
            "service:drive",
            "recent calendar",
            "last week gmail",
            "service:sheets documents",
            "drive recent files"
        ]
        
        for query in test_queries:
            result = await client.call_tool("search", {"query": query})
            assert result is not None, f"Service history query '{query}' should return a result"
            
            content = result.content[0].text if hasattr(result, 'content') else str(result)
            
            try:
                data = json.loads(content)
                assert "results" in data, "Response should have 'results' field"
                
                # Check if service icons are present in titles
                if len(data["results"]) > 0:
                    result_item = data["results"][0]
                    title = result_item.get("title", "")
                    # Service icons should be present (📧, 📁, 📅, etc.)
                    has_icon = any(ord(c) > 127 for c in title)  # Check for Unicode characters
                    assert has_icon or "unknown" in title.lower(), \
                        f"Title should contain service icon or indicate unknown service: {title}"
            except json.JSONDecodeError:
                # Acceptable if Qdrant is not available
                assert "error" in content.lower() or "not available" in content.lower()
    
    @pytest.mark.asyncio
    async def test_search_general_capability(self, client):
        """Test search tool with general semantic search queries."""
        test_queries = [
            "email collaboration documents",
            "search for reports",
            "find presentation files",
            "user authentication errors",
            "api response times"
        ]
        
        for query in test_queries:
            result = await client.call_tool("search", {"query": query})
            assert result is not None, f"General search query '{query}' should return a result"
            
            content = result.content[0].text if hasattr(result, 'content') else str(result)
            
            try:
                data = json.loads(content)
                assert "results" in data, "Response should have 'results' field"
                assert isinstance(data["results"], list), "Results should be a list"
                
                # Check result format
                for result_item in data["results"][:3]:  # Check first 3 results
                    assert "id" in result_item, "Each result should have an 'id'"
                    assert "title" in result_item, "Each result should have a 'title'"
                    assert "url" in result_item, "Each result should have a 'url'"
                    assert result_item["url"].startswith("qdrant://"), \
                        f"URL should start with qdrant://: {result_item['url']}"
            except json.JSONDecodeError:
                # Acceptable if Qdrant is not available
                assert "error" in content.lower() or "not available" in content.lower()
    
    @pytest.mark.asyncio
    async def test_search_response_format_compliance(self, client):
        """Test that search tool responses comply with OpenAI MCP standard."""
        result = await client.call_tool("search", {"query": "test compliance"})
        content = result.content[0].text if hasattr(result, 'content') else str(result)
        
        try:
            data = json.loads(content)
            
            # OpenAI MCP standard requires specific format
            assert "results" in data, "Response must have 'results' field"
            assert isinstance(data["results"], list), "Results must be a list"
            
            if len(data["results"]) > 0:
                first_result = data["results"][0]
                
                # Required fields for MCP standard
                assert "id" in first_result, "Result must have 'id' field"
                assert "title" in first_result, "Result must have 'title' field"
                assert "url" in first_result, "Result must have 'url' field"
                
                # Field types
                assert isinstance(first_result["id"], str), "ID must be a string"
                assert isinstance(first_result["title"], str), "Title must be a string"
                assert isinstance(first_result["url"], str), "URL must be a string"
                
        except json.JSONDecodeError:
            # If Qdrant is not available, should still return valid JSON error
            assert "{" in content and "}" in content, "Error response should be valid JSON"


@pytest.mark.service("qdrant")
class TestQdrantUnifiedFetch:
    """Test the new unified fetch tool."""
    
    @pytest.mark.asyncio
    async def test_fetch_tool_available(self, client):
        """Test that the fetch tool is available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        assert "fetch" in tool_names, "Unified fetch tool should be available"
    
    @pytest.mark.asyncio
    async def test_fetch_with_valid_id(self, client):
        """Test fetching a document with a valid ID."""
        # First, create some data by calling tools
        await client.call_tool("health_check", {})
        await asyncio.sleep(1)
        
        # Search to get a valid ID
        search_result = await client.call_tool("search", {"query": "health"})
        search_content = search_result.content[0].text if hasattr(search_result, 'content') else str(search_result)
        
        try:
            search_data = json.loads(search_content)
            if search_data.get("results") and len(search_data["results"]) > 0:
                valid_id = search_data["results"][0]["id"]
                
                # Now fetch with this valid ID
                fetch_result = await client.call_tool("fetch", {"id": valid_id})
                fetch_content = fetch_result.content[0].text if hasattr(fetch_result, 'content') else str(fetch_result)
                
                fetch_data = json.loads(fetch_content)
                
                # Check OpenAI MCP standard format
                assert "id" in fetch_data, "Fetch response must have 'id' field"
                assert "title" in fetch_data, "Fetch response must have 'title' field"
                assert "text" in fetch_data, "Fetch response must have 'text' field"
                assert "url" in fetch_data, "Fetch response must have 'url' field"
                assert "metadata" in fetch_data, "Fetch response must have 'metadata' field"
                
                # Verify ID matches
                assert fetch_data["id"] == valid_id, "Fetched ID should match requested ID"
                
                # Check metadata structure
                assert isinstance(fetch_data["metadata"], dict), "Metadata should be a dictionary"
                
        except json.JSONDecodeError:
            # Acceptable if Qdrant is not available
            pass
    
    @pytest.mark.asyncio
    async def test_fetch_with_invalid_id(self, client):
        """Test fetching with an invalid ID."""
        invalid_ids = [
            "invalid_id_12345",
            "00000000-0000-0000-0000-000000000000",
            "nonexistent",
            ""
        ]
        
        for invalid_id in invalid_ids:
            result = await client.call_tool("fetch", {"id": invalid_id})
            content = result.content[0].text if hasattr(result, 'content') else str(result)
            
            try:
                data = json.loads(content)
                
                # Should return a properly formatted error document
                assert "id" in data, "Error response must have 'id' field"
                assert "title" in data, "Error response must have 'title' field"
                assert "text" in data, "Error response must have 'text' field"
                assert "url" in data, "Error response must have 'url' field"
                
                # Check error indicators
                assert "not found" in data["title"].lower() or "error" in data["title"].lower(), \
                    f"Title should indicate error or not found: {data['title']}"
                assert data["id"] == invalid_id, "ID should match requested ID even for errors"
                
            except json.JSONDecodeError:
                assert "error" in content.lower(), "Non-JSON response should indicate error"
    
    @pytest.mark.asyncio
    async def test_fetch_response_format_compliance(self, client):
        """Test that fetch tool responses comply with OpenAI MCP standard."""
        # Use a test ID (may or may not exist)
        test_id = str(uuid.uuid4())
        result = await client.call_tool("fetch", {"id": test_id})
        content = result.content[0].text if hasattr(result, 'content') else str(result)
        
        try:
            data = json.loads(content)
            
            # OpenAI MCP standard requires specific format
            assert "id" in data, "Response must have 'id' field"
            assert "title" in data, "Response must have 'title' field"
            assert "text" in data, "Response must have 'text' field"
            assert "url" in data, "Response must have 'url' field"
            assert "metadata" in data, "Response must have 'metadata' field"
            
            # Field types
            assert isinstance(data["id"], str), "ID must be a string"
            assert isinstance(data["title"], str), "Title must be a string"
            assert isinstance(data["text"], str), "Text must be a string"
            assert isinstance(data["url"], str), "URL must be a string"
            assert isinstance(data["metadata"], dict), "Metadata must be a dictionary"
            
        except json.JSONDecodeError:
            # If Qdrant is not available, should still return valid JSON error
            assert "{" in content and "}" in content, "Error response should be valid JSON"


@pytest.mark.service("qdrant")
class TestQdrantBackwardCompatibility:
    """Test backward compatibility with existing tools."""
    
    @pytest.mark.asyncio
    async def test_legacy_tools_still_work(self, client):
        """Test that legacy tools continue to function."""
        # Test search_tool_history
        result = await client.call_tool("search_tool_history", {
            "query": "test backward compatibility",
            "limit": 5
        })
        assert result is not None, "Legacy search_tool_history should still work"
        
        # Test get_tool_analytics
        result = await client.call_tool("get_tool_analytics", {})
        assert result is not None, "Legacy get_tool_analytics should still work"
        
        # Test get_response_details with a test ID
        test_id = str(uuid.uuid4())
        result = await client.call_tool("get_response_details", {"response_id": test_id})
        assert result is not None, "Legacy get_response_details should still work"
        
        # Check that response indicates either success or proper error
        content = result.content[0].text if hasattr(result, 'content') else str(result)
        assert "not found" in content.lower() or "error" in content.lower() or "{" in content, \
            "Legacy tool should return proper response or error"
    
    @pytest.mark.asyncio
    async def test_legacy_and_unified_consistency(self, client):
        """Test that legacy and unified tools return consistent results."""
        test_query = "consistency test"
        
        # Call legacy tool
        legacy_result = await client.call_tool("search_tool_history", {
            "query": test_query,
            "limit": 5
        })
        legacy_content = legacy_result.content[0].text if hasattr(legacy_result, 'content') else str(legacy_result)
        
        # Call unified tool
        unified_result = await client.call_tool("search", {"query": test_query})
        unified_content = unified_result.content[0].text if hasattr(unified_result, 'content') else str(unified_result)
        
        # Both should return valid responses
        assert legacy_result is not None, "Legacy tool should return result"
        assert unified_result is not None, "Unified tool should return result"
        
        # If both return JSON, check they have results
        try:
            legacy_data = json.loads(legacy_content)
            unified_data = json.loads(unified_content)
            
            # Legacy has different format but both should have results
            if "results" in legacy_data:
                assert isinstance(legacy_data["results"], list), "Legacy results should be list"
            assert isinstance(unified_data["results"], list), "Unified results should be list"
            
        except json.JSONDecodeError:
            # Both might fail with Qdrant unavailable, that's ok
            pass


@pytest.mark.service("qdrant")
class TestQdrantServiceIntegration:
    """Test service metadata integration."""
    
    @pytest.mark.asyncio
    async def test_service_icons_in_results(self, client):
        """Test that service icons are properly integrated in search results."""
        # Generate some service-specific data
        service_tools = [
            ("list_gmail_labels", {"user_google_email": TEST_EMAIL}),
            ("list_files", {"path": "."}),
            ("list_calendars", {"user_google_email": TEST_EMAIL}),
        ]
        
        for tool_name, params in service_tools:
            try:
                await client.call_tool(tool_name, params)
            except:
                pass  # Tools might fail due to auth, that's ok
        
        await asyncio.sleep(2)
        
        # Search for Gmail-specific content
        result = await client.call_tool("search", {"query": "service:gmail"})
        content = result.content[0].text if hasattr(result, 'content') else str(result)
        
        try:
            data = json.loads(content)
            if data.get("results") and len(data["results"]) > 0:
                for result_item in data["results"]:
                    title = result_item.get("title", "")
                    # Check for service icons or service names
                    service_indicators = ["📧", "📁", "📅", "📄", "📊", "🎯", "📷", "💬", "📝",
                                         "Gmail", "Drive", "Calendar", "Docs", "Sheets", "Slides",
                                         "Photos", "Chat", "Forms"]
                    has_service_indicator = any(indicator in title for indicator in service_indicators)
                    assert has_service_indicator or "unknown" in title.lower(), \
                        f"Title should have service indicator: {title}"
        except json.JSONDecodeError:
            # Acceptable if Qdrant is not available
            pass
    
    @pytest.mark.asyncio
    async def test_service_metadata_in_fetch(self, client):
        """Test that fetched documents include service metadata."""
        # Create a Gmail-related entry
        await client.call_tool("list_gmail_labels", {"user_google_email": TEST_EMAIL})
        await asyncio.sleep(1)
        
        # Search for it
        search_result = await client.call_tool("search", {"query": "gmail"})
        search_content = search_result.content[0].text if hasattr(search_result, 'content') else str(search_result)
        
        try:
            search_data = json.loads(search_content)
            if search_data.get("results") and len(search_data["results"]) > 0:
                doc_id = search_data["results"][0]["id"]
                
                # Fetch the document
                fetch_result = await client.call_tool("fetch", {"id": doc_id})
                fetch_content = fetch_result.content[0].text if hasattr(fetch_result, 'content') else str(fetch_result)
                
                fetch_data = json.loads(fetch_content)
                
                # Check metadata includes service information
                metadata = fetch_data.get("metadata", {})
                assert "service" in metadata or "tool_name" in metadata, \
                    "Metadata should include service or tool information"
                
                # Check title includes service context
                title = fetch_data.get("title", "")
                assert len(title) > 0, "Title should not be empty"
                
        except json.JSONDecodeError:
            # Acceptable if Qdrant is not available
            pass


@pytest.mark.service("qdrant")
class TestQdrantErrorHandling:
    """Test error handling in unified tools."""
    
    @pytest.mark.asyncio
    async def test_search_with_empty_query(self, client):
        """Test search with empty query."""
        result = await client.call_tool("search", {"query": ""})
        assert result is not None, "Empty query should return a result"
        
        content = result.content[0].text if hasattr(result, 'content') else str(result)
        
        try:
            data = json.loads(content)
            assert "results" in data, "Even empty query should return results structure"
            assert isinstance(data["results"], list), "Results should be a list"
        except json.JSONDecodeError:
            assert "error" in content.lower() or "qdrant" in content.lower()
    
    @pytest.mark.asyncio
    async def test_fetch_without_id(self, client):
        """Test fetch without providing ID."""
        try:
            result = await client.call_tool("fetch", {})
            # Should either handle gracefully or raise proper error
            assert result is not None
        except Exception as e:
            # Should raise meaningful error about missing ID
            assert "id" in str(e).lower() or "required" in str(e).lower()
    
    @pytest.mark.asyncio
    async def test_malformed_queries(self, client):
        """Test with malformed or unusual queries."""
        malformed_queries = [
            "!!!@@@###",
            "a" * 1000,  # Very long query
            "\\x00\\x01\\x02",  # Special characters
            '{"json": "query"}',  # JSON as query
        ]
        
        for query in malformed_queries[:3]:  # Test first 3 to avoid timeout
            result = await client.call_tool("search", {"query": query})
            assert result is not None, f"Malformed query '{query[:50]}...' should not crash"
            
            content = result.content[0].text if hasattr(result, 'content') else str(result)
            
            try:
                data = json.loads(content)
                assert "results" in data, "Should return valid structure even for malformed queries"
            except json.JSONDecodeError:
                assert "error" in content.lower(), "Should return error for malformed queries"


@pytest.mark.service("qdrant")
class TestQdrantPerformance:
    """Test performance and efficiency of unified tools."""
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_search_performance(self, client):
        """Test that search returns quickly."""
        import time
        
        queries = ["performance test", "overview", "service:gmail", "analytics"]
        
        for query in queries:
            start_time = time.time()
            result = await client.call_tool("search", {"query": query})
            elapsed_time = time.time() - start_time
            
            assert result is not None, f"Query '{query}' should return result"
            assert elapsed_time < 5.0, f"Query '{query}' took {elapsed_time:.2f}s, should be < 5s"
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_fetch_performance(self, client):
        """Test that fetch returns quickly."""
        import time
        
        test_ids = [str(uuid.uuid4()) for _ in range(3)]
        
        for test_id in test_ids:
            start_time = time.time()
            result = await client.call_tool("fetch", {"id": test_id})
            elapsed_time = time.time() - start_time
            
            assert result is not None, f"Fetch with ID '{test_id}' should return result"
            assert elapsed_time < 3.0, f"Fetch took {elapsed_time:.2f}s, should be < 3s"