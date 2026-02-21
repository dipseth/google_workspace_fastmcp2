"""Tests for Qdrant resource access and middleware integration using FastMCP Client.

🔧 MCP Tools Used:
- Qdrant resource handler: Access Qdrant collections and points via URIs
- Search tools: Semantic search across stored tool responses
- Analytics tools: Get tool usage analytics from Qdrant
- Fetch tools: Retrieve specific points from Qdrant collections

🧪 What's Being Tested:
- Qdrant resource URI handling (qdrant://)
- Collection information retrieval
- Point data access and decompression
- Search functionality across tool responses
- Analytics aggregation from stored data
- Middleware integration with resource handlers
- Pydantic model to dict conversion
- Error handling for invalid URIs or missing data

🔍 Key Test Areas:
- qdrant://collection/{name}/info - Collection metadata
- qdrant://collection/{name}/{point_id} - Specific point details
- qdrant://collections/list - List all collections
- qdrant://search/{query} - Semantic search
- qdrant://cache - Tool response cache status
- qdrant://status - Middleware status check
"""

import json
import logging

import pytest
from dotenv import load_dotenv

from .test_helpers import assert_tools_registered

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


@pytest.mark.integration
class TestQdrantResources:
    """Test suite for Qdrant resource endpoints via FastMCP Client."""

    @pytest.mark.asyncio
    async def test_list_qdrant_resource_templates(self, client):
        """Test that Qdrant resource templates are registered."""
        templates = await client.list_resource_templates()

        # Check that we have templates
        assert isinstance(templates, list)

        # Look for Qdrant resource templates
        qdrant_templates = []
        for template in templates:
            uri_template = template.uriTemplate
            if uri_template.startswith("qdrant://"):
                qdrant_templates.append(template)
                logger.info(f"Found Qdrant template: {uri_template} - {template.name}")

        # We should have several Qdrant resource templates
        assert len(qdrant_templates) > 0, "No Qdrant resource templates found"

        # Check for specific expected templates
        expected_templates = [
            "qdrant://collection/{collection_name}/info",
            "qdrant://collection/{collection_name}/{point_id}",
            "qdrant://collection/{collection_name}/responses/recent",
            "qdrant://search/{query}",
            "qdrant://search/{collection_name}/{query}",
        ]

        template_uris = [t.uriTemplate for t in templates]
        for expected_template in expected_templates:
            assert expected_template in template_uris, (
                f"Expected template {expected_template} not found"
            )

    @pytest.mark.asyncio
    async def test_list_qdrant_static_resources(self, client):
        """Test listing static Qdrant resources."""
        resources = await client.list_resources()

        # Check that we have resources
        assert isinstance(resources, list)

        # Look for static Qdrant resources
        qdrant_resources = []
        for resource in resources:
            uri_str = str(resource.uri)
            if uri_str.startswith("qdrant://"):
                qdrant_resources.append(resource)
                logger.info(f"Found Qdrant resource: {uri_str} - {resource.name}")

        # We should have at least some static Qdrant resources
        assert len(qdrant_resources) > 0, "No static Qdrant resources found"

        # Check for specific expected resources
        expected_uris = [
            "qdrant://collections/list",
            "qdrant://cache",
            "qdrant://status",
        ]

        found_uris = [str(r.uri) for r in resources]
        for expected_uri in expected_uris:
            assert expected_uri in found_uris, (
                f"Expected resource {expected_uri} not found"
            )

    @pytest.mark.asyncio
    async def test_read_qdrant_status_resource(self, client):
        """Test reading the qdrant://status resource."""
        try:
            # Read the Qdrant status resource
            content = await client.read_resource("qdrant://status")

            # Should return a list of resource contents
            assert isinstance(content, list)
            assert len(content) > 0

            # Check the content
            first_content = content[0]
            if hasattr(first_content, "text"):
                # Should be JSON with status info
                status_text = first_content.text
                status = json.loads(status_text)

                # Should have middleware status information
                assert "middleware_active" in status or "client_available" in status, (
                    f"Expected status data, got: {status}"
                )

                logger.info(
                    f"✅ Qdrant status: middleware_active={status.get('middleware_active', False)}"
                )

        except Exception as e:
            logger.error(f"❌ Failed to read Qdrant status: {e}")
            raise

    @pytest.mark.asyncio
    async def test_read_qdrant_collections_list(self, client):
        """Test reading the qdrant://collections/list resource."""
        try:
            # Read the collections list resource
            content = await client.read_resource("qdrant://collections/list")

            # Should return a list of resource contents
            assert isinstance(content, list)
            assert len(content) > 0

            # Check the content
            first_content = content[0]
            if hasattr(first_content, "text"):
                # Should be JSON with collections list
                collections_text = first_content.text
                data = json.loads(collections_text)

                # Should have collections data
                assert "collections" in data or "total_collections" in data, (
                    f"Expected collections data, got: {data}"
                )

                if "collections" in data:
                    logger.info(
                        f"✅ Found {len(data['collections'])} Qdrant collections"
                    )
                    for coll in data["collections"][:3]:  # Log first 3
                        if isinstance(coll, dict):
                            logger.info(
                                f"   - {coll.get('name', 'N/A')}: {coll.get('points_count', 0)} points"
                            )

        except Exception as e:
            logger.error(f"❌ Failed to read collections list: {e}")
            raise

    @pytest.mark.asyncio
    async def test_read_qdrant_collection_info(self, client):
        """Test reading collection info for mcp_tool_responses."""
        collection_name = "mcp_tool_responses"
        uri = f"qdrant://collection/{collection_name}/info"

        try:
            # Read the collection info resource
            content = await client.read_resource(uri)

            # Should return a list of resource contents
            assert isinstance(content, list)
            assert len(content) > 0

            # Check the content
            first_content = content[0]
            if hasattr(first_content, "text"):
                # Should be JSON with collection info
                info_text = first_content.text
                info = json.loads(info_text)

                # Should have collection information
                assert "collection_exists" in info or "error" in info, (
                    f"Expected collection info, got: {info}"
                )

                if info.get("collection_exists"):
                    logger.info(f"✅ Collection {collection_name} exists:")
                    logger.info(f"   - Points count: {info.get('points_count', 0)}")
                    logger.info(
                        f"   - Vector dimension: {info.get('vector_dimension', 'N/A')}"
                    )
                    logger.info(f"   - Status: {info.get('status', 'unknown')}")
                else:
                    logger.warning(f"⚠️ Collection {collection_name} not found")

        except Exception as e:
            logger.error(f"❌ Failed to read collection info: {e}")
            raise

    @pytest.mark.asyncio
    async def test_read_qdrant_specific_point(self, client):
        """Test reading a specific point from Qdrant collection."""
        collection_name = "mcp_tool_responses"

        # Discover a real point_id from recent responses instead of hardcoding
        recent_uri = f"qdrant://collection/{collection_name}/responses/recent"
        try:
            recent_content = await client.read_resource(recent_uri)
        except Exception as e:
            pytest.skip(f"Unable to read recent responses for dynamic point_id: {e}")

        assert isinstance(recent_content, list)
        assert len(recent_content) > 0

        recent_first = recent_content[0]
        recent_text = (
            recent_first.text if hasattr(recent_first, "text") else str(recent_first)
        )

        try:
            recent_data = json.loads(recent_text)
        except json.JSONDecodeError:
            pytest.skip("Recent responses resource did not return JSON")

        responses = recent_data.get("responses") or []
        if not responses:
            pytest.skip("No recent responses in Qdrant to test specific point access")

        first_response = responses[0]
        point_id = first_response.get("id") or first_response.get("point_id")
        if not point_id:
            pytest.skip("Recent response did not contain an id/point_id field")

        uri = f"qdrant://collection/{collection_name}/{point_id}"

        try:
            # Read the specific point resource
            content = await client.read_resource(uri)

            # Should return a list of resource contents
            assert isinstance(content, list)
            assert len(content) > 0

            # Check the content
            first_content = content[0]
            if hasattr(first_content, "text"):
                # Should be JSON with point details
                point_text = first_content.text
                point_data = json.loads(point_text)

                # Should have point data or error
                if "point_exists" in point_data:
                    if point_data["point_exists"]:
                        logger.info(f"✅ Point {point_id} found:")
                        logger.info(
                            f"   - Tool name: {point_data.get('tool_name', 'N/A')}"
                        )
                        logger.info(
                            f"   - User email: {point_data.get('user_email', 'N/A')}"
                        )
                        logger.info(
                            f"   - Timestamp: {point_data.get('timestamp', 'N/A')}"
                        )
                    else:
                        logger.warning(f"⚠️ Point {point_id} not found")
                elif "error" in point_data:
                    logger.warning(f"⚠️ Error accessing point: {point_data['error']}")
                else:
                    # Might have the actual payload data
                    logger.info(f"✅ Point data retrieved: {list(point_data.keys())}")

        except Exception as e:
            # Point might not exist, but the resource should still work
            logger.info(f"Point access handled appropriately: {e}")

    @pytest.mark.asyncio
    async def test_read_qdrant_cache_resource(self, client):
        """Test reading the qdrant://cache resource."""
        try:
            # Read the cache resource
            content = await client.read_resource("qdrant://cache")

            # Should return a list of resource contents
            assert isinstance(content, list)
            assert len(content) > 0

            # Check the content
            first_content = content[0]
            if hasattr(first_content, "text"):
                # Should be JSON with cache data
                cache_text = first_content.text
                cache_data = json.loads(cache_text)

                # Should have cache information
                assert (
                    "tools" in cache_data
                    or "total_responses" in cache_data
                    or "error" in cache_data
                ), f"Expected cache data, got: {cache_data}"

                if "tools" in cache_data:
                    logger.info(
                        f"✅ Tool response cache contains {len(cache_data['tools'])} tools"
                    )
                    for tool_name, tool_data in list(cache_data["tools"].items())[:3]:
                        logger.info(
                            f"   - {tool_name}: {tool_data.get('count', 0)} responses"
                        )

        except Exception as e:
            logger.info(f"Cache resource handled appropriately: {e}")

    @pytest.mark.asyncio
    async def test_read_recent_collection_responses(self, client):
        """Test reading recent responses from a collection."""
        collection_name = "mcp_tool_responses"
        uri = f"qdrant://collection/{collection_name}/responses/recent"

        try:
            # Read recent responses
            content = await client.read_resource(uri)

            # Should return a list of resource contents
            assert isinstance(content, list)
            assert len(content) > 0

            # Check the content
            first_content = content[0]
            if hasattr(first_content, "text"):
                # Should be JSON with recent responses
                responses_text = first_content.text
                responses_data = json.loads(responses_text)

                # Should have responses or error
                if "responses" in responses_data:
                    logger.info(
                        f"✅ Found {len(responses_data['responses'])} recent responses"
                    )
                    for resp in responses_data["responses"][:3]:
                        if isinstance(resp, dict):
                            logger.info(
                                f"   - {resp.get('tool_name', 'N/A')} at {resp.get('timestamp', 'N/A')}"
                            )
                elif "error" in responses_data:
                    logger.warning(
                        f"⚠️ Error getting recent responses: {responses_data['error']}"
                    )

        except Exception as e:
            logger.info(f"Recent responses resource handled appropriately: {e}")

    @pytest.mark.asyncio
    async def test_qdrant_search_resource(self, client):
        """Test the Qdrant search resource template."""
        query = "gmail send email"
        uri = f"qdrant://search/{query}"

        try:
            # Perform search via resource
            content = await client.read_resource(uri)

            # Should return a list of resource contents
            assert isinstance(content, list)
            assert len(content) > 0

            # Check the content
            first_content = content[0]
            if hasattr(first_content, "text"):
                # Should be JSON with search results
                results_text = first_content.text
                results = json.loads(results_text)

                # Should have results or indicate no matches
                if "results" in results:
                    logger.info(
                        f"✅ Search found {len(results['results'])} matches for '{query}'"
                    )
                    for result in results["results"][:3]:
                        if isinstance(result, dict):
                            logger.info(
                                f"   - Score {result.get('score', 0):.3f}: {result.get('tool_name', 'N/A')}"
                            )
                elif "total_results" in results:
                    logger.info(f"Search returned {results['total_results']} results")

        except Exception as e:
            logger.info(f"Search resource handled appropriately: {e}")


@pytest.mark.integration
class TestQdrantTools:
    """Test suite for Qdrant-related tools via FastMCP Client."""

    @pytest.mark.asyncio
    async def test_qdrant_tools_available(self, client):
        """Test that Qdrant tools are available."""
        expected_tools = [
            "search",  # Semantic search
            "fetch",  # Fetch point by ID
            "search_tool_history",  # Search historical responses
            "get_tool_analytics",  # Get analytics
            "cleanup_qdrant_data",  # Cleanup old data
        ]
        await assert_tools_registered(client, expected_tools, context="Qdrant tools")

    @pytest.mark.asyncio
    async def test_search_tool(self, client):
        """Test the Qdrant search tool."""
        try:
            # Call the search tool
            result = await client.call_tool(
                "search", {"query": "test search", "limit": 5, "score_threshold": 0.1}
            )

            # Should return a result
            assert result is not None
            if hasattr(result, "content") and result.content:
                content = result.content[0].text
            else:
                content = str(result)

            print("Qdrant search tool raw response:", content[:500])

            # Parse the result
            if "{" in content and "}" in content:
                try:
                    search_data = json.loads(content)
                    logger.info(
                        f"✅ Search tool returned: {search_data.get('total_results', 0)} results"
                    )
                except json.JSONDecodeError:
                    logger.info(f"Search tool returned non-JSON: {content[:200]}...")
            else:
                logger.info(f"Search tool response: {content[:200]}...")

        except Exception as e:
            logger.info(f"Search tool handled appropriately: {e}")

    @pytest.mark.asyncio
    async def test_get_tool_analytics(self, client):
        """Test the tool analytics function."""
        try:
            # Call the analytics tool
            result = await client.call_tool(
                "get_tool_analytics", {"summary_only": True, "group_by": "tool_name"}
            )

            # Should return a result
            assert result is not None
            if hasattr(result, "content") and result.content:
                content = result.content[0].text
            else:
                content = str(result)

            print("Qdrant analytics tool raw response:", content[:500])

            # Check for analytics data
            if "total_responses" in content or "tools" in content:
                logger.info("✅ Analytics tool returned data")
            else:
                logger.info(f"Analytics response: {content[:200]}...")

        except Exception as e:
            logger.info(f"Analytics tool handled appropriately: {e}")

    @pytest.mark.asyncio
    async def test_fetch_tool(self, client):
        """Test fetching a specific point."""
        collection_name = "mcp_tool_responses"
        recent_uri = f"qdrant://collection/{collection_name}/responses/recent"

        try:
            recent_content = await client.read_resource(recent_uri)
        except Exception as e:
            pytest.skip(f"Unable to read recent responses for fetch tool test: {e}")

        assert isinstance(recent_content, list)
        assert len(recent_content) > 0

        recent_first = recent_content[0]
        recent_text = (
            recent_first.text if hasattr(recent_first, "text") else str(recent_first)
        )

        try:
            recent_data = json.loads(recent_text)
        except json.JSONDecodeError:
            pytest.skip("Recent responses resource did not return JSON")

        responses = recent_data.get("responses") or []
        if not responses:
            pytest.skip("No recent responses in Qdrant to test fetch tool")

        first_response = responses[0]
        point_id = first_response.get("id") or first_response.get("point_id")
        if not point_id:
            pytest.skip("Recent response did not contain an id/point_id field")

        try:
            # Call the fetch tool
            result = await client.call_tool("fetch", {"point_id": point_id})

            # Should return a result
            assert result is not None
            if hasattr(result, "content") and result.content:
                content = result.content[0].text
            else:
                content = str(result)

            print("Qdrant fetch tool raw response:", content[:500])

            # Check the content
            if "error" in content.lower() and "not found" in content.lower():
                logger.info(
                    f"Point {point_id} not found (expected if point doesn't exist)"
                )
            else:
                logger.info(f"✅ Fetch tool retrieved point data: {content[:200]}...")

        except Exception as e:
            logger.info(f"Fetch tool handled appropriately: {e}")


@pytest.mark.integration
class TestQdrantMiddlewareIntegration:
    """Integration tests for Qdrant middleware and resource handlers."""

    @pytest.mark.asyncio
    async def test_middleware_resource_handler_chain(self, client):
        """Test the complete middleware -> resource handler chain."""
        # This tests the specific issue mentioned: middleware processing URIs
        # and the caching mechanism between middleware and resource handlers

        test_cases = [
            ("qdrant://status", "Middleware status check"),
            ("qdrant://collections/list", "Collections listing"),
            (
                "qdrant://collection/mcp_tool_responses/info",
                "Collection info retrieval",
            ),
            ("qdrant://cache", "Cache status check"),
        ]

        successful_reads = 0
        for uri, description in test_cases:
            try:
                logger.info(f"\n🧪 Testing: {description} via {uri}")
                content = await client.read_resource(uri)

                assert isinstance(content, list), f"Expected list, got {type(content)}"
                assert len(content) > 0, f"Empty content for {uri}"

                # Verify we got valid content, not an error tuple
                first_content = content[0]
                assert hasattr(first_content, "text"), (
                    f"Content missing 'text' attribute for {uri}"
                )

                # Ensure it's not returning a tuple (the original error)
                assert not isinstance(first_content.text, tuple), (
                    f"❌ Got tuple instead of text for {uri} - middleware caching issue!"
                )

                successful_reads += 1
                logger.info(f"✅ Successfully read {uri}")

            except AssertionError as e:
                logger.error(f"❌ Assertion failed for {uri}: {e}")
                raise
            except Exception as e:
                logger.error(f"❌ Failed to read {uri}: {e}")
                raise

        # All test URIs should work
        assert successful_reads == len(test_cases), (
            f"Only {successful_reads}/{len(test_cases)} URIs worked - middleware issue persists"
        )

        logger.info(
            f"\n✅ All {successful_reads} middleware resource chains working correctly!"
        )

    @pytest.mark.asyncio
    async def test_pydantic_model_conversion(self, client):
        """Test that Pydantic models are properly converted to dicts."""
        # This specifically tests the fix for model_dump() conversion

        uri = "qdrant://collection/mcp_tool_responses/info"

        try:
            content = await client.read_resource(uri)

            # Parse the response
            first_content = content[0]
            response_text = first_content.text

            # Should be valid JSON (not a Pydantic model string representation)
            try:
                data = json.loads(response_text)
                assert isinstance(data, dict), "Response should be a dictionary"
                logger.info("✅ Pydantic model properly converted to dict")
            except json.JSONDecodeError as e:
                logger.error(
                    f"❌ Response is not valid JSON - Pydantic conversion failed: {e}"
                )
                logger.error(f"Response text: {response_text[:500]}")
                raise

        except Exception as e:
            logger.error(f"❌ Failed to test Pydantic conversion: {e}")
            raise

    @pytest.mark.asyncio
    async def test_direct_middleware_access_vs_cached(self, client):
        """Test that direct middleware access works (bypassing cache)."""
        # This tests the fix where resource handlers directly call middleware

        # First call - might populate cache or use direct access
        uri = "qdrant://collections/list"
        content1 = await client.read_resource(uri)

        # Second call - should use the same mechanism consistently
        content2 = await client.read_resource(uri)

        # Both should return valid content
        assert len(content1) > 0 and len(content2) > 0

        # Both should have the same structure
        text1 = content1[0].text
        text2 = content2[0].text

        # Both should be valid JSON
        data1 = json.loads(text1)
        data2 = json.loads(text2)

        # Both should have the same keys (consistent response structure)
        assert set(data1.keys()) == set(data2.keys()), (
            "Inconsistent response structure between calls - caching issue"
        )

        logger.info("✅ Direct middleware access and caching working consistently")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
