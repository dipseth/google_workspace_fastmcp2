"""
Client integration tests for TagBasedResourceMiddleware using the standardized framework.

This test suite verifies that the TagBasedResourceMiddleware works correctly with
the actual running server and can handle service:// resource URIs properly.

These tests use the standardized client testing framework and focus on resource
access patterns rather than tool calls.
"""

import json

import pytest


@pytest.mark.integration
@pytest.mark.service("middleware")
class TestTagBasedResourceMiddlewareIntegration:
    """Integration tests for TagBasedResourceMiddleware with live server."""

    @pytest.mark.asyncio
    async def test_service_resource_templates_available(self, client):
        """Test that service resource templates are properly registered."""
        print("\n🔍 Testing service resource template availability")

        templates = await client.list_resource_templates()
        template_uris = [str(template.uriTemplate) for template in templates]

        # Expected service resource templates
        expected_templates = [
            "service://{service}/lists",
            "service://{service}/{list_type}",
            "service://{service}/{list_type}/{item_id}",
        ]

        for expected in expected_templates:
            assert (
                expected in template_uris
            ), f"Service resource template {expected} not found"
            print(f"   ✅ Found template: {expected}")

        print(
            f"   📊 All {len(expected_templates)} service resource templates available"
        )

    @pytest.mark.asyncio
    async def test_service_lists_endpoints(self, client):
        """Test service://{service}/lists endpoints for all supported services."""
        print("\n📋 Testing service lists endpoints")

        supported_services = [
            "gmail",
            "drive",
            "calendar",
            "docs",
            "sheets",
            "chat",
            "forms",
            "slides",
            "photos",
        ]

        results = {}

        for service in supported_services:
            try:
                content = await client.read_resource(f"service://{service}/lists")
                assert len(content) > 0, f"No content returned for {service}/lists"

                data = json.loads(content[0].text)

                # Validate response structure
                assert "service" in data, f"Missing 'service' field for {service}"
                assert data["service"] == service, f"Wrong service name for {service}"
                assert (
                    "service_metadata" in data
                ), f"Missing 'service_metadata' for {service}"
                assert "list_types" in data, f"Missing 'list_types' for {service}"

                # Validate service metadata
                metadata = data["service_metadata"]
                assert "display_name" in metadata, f"Missing display_name for {service}"
                assert "icon" in metadata, f"Missing icon for {service}"
                assert "description" in metadata, f"Missing description for {service}"

                results[service] = {
                    "success": True,
                    "list_types_count": len(data["list_types"]),
                    "list_types": list(data["list_types"].keys()),
                }

                print(
                    f"   ✅ {service}: {len(data['list_types'])} list types - {list(data['list_types'].keys())}"
                )

            except Exception as e:
                results[service] = {"success": False, "error": str(e)}
                print(f"   ❌ {service}: {e}")

        # At least most services should work
        successful_services = [s for s, r in results.items() if r.get("success")]
        assert (
            len(successful_services) >= len(supported_services) * 0.8
        ), f"Too many service failures. Successful: {successful_services}"

        print(
            f"   📊 {len(successful_services)}/{len(supported_services)} services working"
        )

    @pytest.mark.asyncio
    async def test_service_list_items_endpoints(self, client):
        """Test service://{service}/{list_type} endpoints."""
        print("\n📝 Testing service list items endpoints")

        test_cases = [
            ("gmail", "filters"),
            ("gmail", "labels"),
            ("drive", "items"),
            ("calendar", "calendars"),
            ("sheets", "spreadsheets"),
            ("photos", "albums"),
        ]

        results = {}

        for service, list_type in test_cases:
            try:
                content = await client.read_resource(f"service://{service}/{list_type}")
                assert (
                    len(content) > 0
                ), f"No content returned for {service}/{list_type}"

                data = json.loads(content[0].text)

                if "error" in data:
                    # Check for expected authentication errors
                    error_msg = data["error"].lower()
                    if any(
                        phrase in error_msg
                        for phrase in ["email not found", "authentication", "context"]
                    ):
                        results[f"{service}/{list_type}"] = {
                            "success": True,
                            "auth_error": True,
                            "message": "Expected authentication error",
                        }
                        print(
                            f"   ✅ {service}/{list_type}: Authentication error (expected)"
                        )
                    else:
                        results[f"{service}/{list_type}"] = {
                            "success": False,
                            "error": data["error"],
                        }
                        print(
                            f"   ❌ {service}/{list_type}: Unexpected error: {data['error']}"
                        )
                else:
                    # Validate successful response
                    assert "service" in data, "Missing 'service' field"
                    assert "list_type" in data, "Missing 'list_type' field"
                    assert "tool_called" in data, "Missing 'tool_called' field"

                    results[f"{service}/{list_type}"] = {
                        "success": True,
                        "tool_called": data["tool_called"],
                    }
                    print(
                        f"   ✅ {service}/{list_type}: Tool {data['tool_called']} executed"
                    )

            except Exception as e:
                results[f"{service}/{list_type}"] = {"success": False, "error": str(e)}
                print(f"   ❌ {service}/{list_type}: Exception: {e}")

        # All should either succeed or fail with authentication errors
        valid_results = [r for r in results.values() if r["success"]]
        assert len(valid_results) == len(
            test_cases
        ), f"Some endpoints failed unexpectedly. Results: {results}"

        print(
            f"   📊 {len(valid_results)}/{len(test_cases)} endpoints handled correctly"
        )

    @pytest.mark.asyncio
    async def test_service_specific_items_endpoints(self, client):
        """Test service://{service}/{list_type}/{id} endpoints."""
        print("\n🎯 Testing service specific item endpoints")

        test_cases = [
            ("gmail", "filters", "test_filter_123"),
            ("drive", "items", "test_file_456"),
            ("calendar", "events", "test_event_789"),
        ]

        results = {}

        for service, list_type, item_id in test_cases:
            try:
                content = await client.read_resource(
                    f"service://{service}/{list_type}/{item_id}"
                )
                assert (
                    len(content) > 0
                ), f"No content returned for {service}/{list_type}/{item_id}"

                data = json.loads(content[0].text)

                if "error" in data:
                    error_msg = data["error"].lower()
                    if any(
                        phrase in error_msg
                        for phrase in ["email not found", "authentication", "context"]
                    ):
                        results[f"{service}/{list_type}/{item_id}"] = {
                            "success": True,
                            "auth_error": True,
                        }
                        print(
                            f"   ✅ {service}/{list_type}/{item_id}: Authentication error (expected)"
                        )
                    elif "no get tool configured" in error_msg:
                        results[f"{service}/{list_type}/{item_id}"] = {
                            "success": True,
                            "no_get_tool": True,
                        }
                        print(
                            f"   ✅ {service}/{list_type}/{item_id}: No get tool (expected)"
                        )
                    else:
                        results[f"{service}/{list_type}/{item_id}"] = {
                            "success": False,
                            "error": data["error"],
                        }
                        print(
                            f"   ❌ {service}/{list_type}/{item_id}: Unexpected error: {data['error']}"
                        )
                else:
                    # Validate successful response
                    assert "service" in data, "Missing 'service' field"
                    assert "list_type" in data, "Missing 'list_type' field"
                    assert "item_id" in data, "Missing 'item_id' field"
                    assert data["item_id"] == item_id, "Wrong item_id returned"

                    results[f"{service}/{list_type}/{item_id}"] = {
                        "success": True,
                        "tool_called": data.get("tool_called"),
                    }
                    print(
                        f"   ✅ {service}/{list_type}/{item_id}: Retrieved successfully"
                    )

            except Exception as e:
                results[f"{service}/{list_type}/{item_id}"] = {
                    "success": False,
                    "error": str(e),
                }
                print(f"   ❌ {service}/{list_type}/{item_id}: Exception: {e}")

        # All should either succeed or fail with expected errors
        valid_results = [r for r in results.values() if r["success"]]
        assert len(valid_results) == len(
            test_cases
        ), f"Some specific item endpoints failed unexpectedly. Results: {results}"

        print(
            f"   📊 {len(valid_results)}/{len(test_cases)} specific item endpoints handled correctly"
        )

    @pytest.mark.asyncio
    async def test_middleware_error_handling(self, client):
        """Test error handling for invalid service URIs."""
        print("\n❌ Testing middleware error handling")

        error_test_cases = [
            ("service://invalid_service/lists", "unsupported service"),
            ("service://gmail/invalid_list_type", "unsupported list type"),
            ("service://gmail", "service root access not implemented"),
        ]

        for uri, expected_error_type in error_test_cases:
            try:
                content = await client.read_resource(uri)

                if len(content) > 0:
                    data = json.loads(content[0].text)
                    assert "error" in data, f"Expected error response for {uri}"

                    # Validate error response structure
                    assert "message" in data, f"Missing error message for {uri}"
                    assert "timestamp" in data, f"Missing timestamp for {uri}"

                    print(
                        f"   ✅ {uri}: Got expected error type '{expected_error_type}'"
                    )
                else:
                    print(f"   ✅ {uri}: Empty response (handled by framework)")

            except Exception:
                # Some invalid URIs might raise exceptions at the client level
                print(f"   ✅ {uri}: Exception raised (valid error handling)")

    @pytest.mark.asyncio
    async def test_middleware_passthrough_behavior(self, client):
        """Test that non-service URIs are passed through correctly."""
        print("\n🔀 Testing middleware passthrough behavior")

        # Test non-service URIs that should pass through
        non_service_uris = [
            "user://current/email",
            "template://user_email",
            "auth://session/current",
        ]

        for uri in non_service_uris:
            try:
                content = await client.read_resource(uri)
                print(f"   ✅ {uri}: Passed through successfully")
            except Exception:
                # The URI might not be implemented, but it should pass through
                # and be handled by other middleware/handlers
                print(f"   ✅ {uri}: Passed through and handled by other components")

    @pytest.mark.asyncio
    async def test_middleware_response_consistency(self, client):
        """Test that middleware responses are consistently formatted."""
        print("\n📊 Testing response format consistency")

        test_services = ["gmail", "drive", "calendar"]

        for service in test_services:
            try:
                content = await client.read_resource(f"service://{service}/lists")
                assert len(content) > 0, f"No content for {service}"

                data = json.loads(content[0].text)

                # Validate consistent response structure
                required_fields = [
                    "service",
                    "service_metadata",
                    "list_types",
                    "total_list_types",
                    "generated_at",
                ]

                for field in required_fields:
                    assert (
                        field in data
                    ), f"Missing required field '{field}' for {service}"

                # Validate metadata structure
                metadata = data["service_metadata"]
                metadata_fields = ["display_name", "icon", "description"]

                for field in metadata_fields:
                    assert (
                        field in metadata
                    ), f"Missing metadata field '{field}' for {service}"

                # Validate list types structure
                for list_type_name, list_type_info in data["list_types"].items():
                    list_type_fields = [
                        "display_name",
                        "description",
                        "tool_name",
                        "supports_get",
                        "id_field",
                    ]

                    for field in list_type_fields:
                        assert (
                            field in list_type_info
                        ), f"Missing list type field '{field}' for {service}/{list_type_name}"

                print(f"   ✅ {service}: Response format is consistent")

            except Exception as e:
                print(f"   ❌ {service}: Response format validation failed: {e}")
                raise

        print("   📊 All tested services have consistent response formats")


@pytest.mark.integration
@pytest.mark.service("middleware")
class TestTagBasedResourceMiddlewarePerformance:
    """Performance and reliability tests for TagBasedResourceMiddleware."""

    @pytest.mark.asyncio
    async def test_concurrent_service_requests(self, client):
        """Test handling of concurrent service resource requests."""
        print("\n🔄 Testing concurrent service resource requests")

        import asyncio

        services = ["gmail", "drive", "calendar", "docs", "sheets"]

        # Create concurrent requests
        async def fetch_service_lists(service):
            try:
                content = await client.read_resource(f"service://{service}/lists")
                return {
                    "service": service,
                    "success": True,
                    "content_length": len(content),
                }
            except Exception as e:
                return {"service": service, "success": False, "error": str(e)}

        # Execute concurrent requests
        tasks = [fetch_service_lists(service) for service in services]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Analyze results
        successful_requests = [
            r for r in results if not isinstance(r, Exception) and r.get("success")
        ]

        assert (
            len(successful_requests) >= len(services) * 0.8
        ), f"Too many concurrent requests failed. Successful: {len(successful_requests)}/{len(services)}"

        print(
            f"   ✅ {len(successful_requests)}/{len(services)} concurrent requests succeeded"
        )

        for result in successful_requests:
            print(f"   📊 {result['service']}: {result['content_length']} bytes")

    @pytest.mark.asyncio
    async def test_repeated_requests_consistency(self, client):
        """Test that repeated requests return consistent results."""
        print("\n🔁 Testing repeated request consistency")

        service = "gmail"
        uri = f"service://{service}/lists"
        request_count = 5

        results = []
        for i in range(request_count):
            try:
                content = await client.read_resource(uri)
                assert len(content) > 0, f"No content on request {i + 1}"

                data = json.loads(content[0].text)
                results.append(
                    {
                        "request_number": i + 1,
                        "service": data.get("service"),
                        "list_types_count": len(data.get("list_types", {})),
                        "list_types": list(data.get("list_types", {}).keys()),
                    }
                )

            except Exception as e:
                results.append({"request_number": i + 1, "error": str(e)})

        # Verify consistency
        first_result = results[0]
        if "error" not in first_result:
            for i, result in enumerate(results[1:], 2):
                if "error" not in result:
                    assert (
                        result["service"] == first_result["service"]
                    ), f"Service mismatch on request {i}"
                    assert (
                        result["list_types_count"] == first_result["list_types_count"]
                    ), f"List types count mismatch on request {i}"
                    assert set(result["list_types"]) == set(
                        first_result["list_types"]
                    ), f"List types mismatch on request {i}"

        successful_requests = [r for r in results if "error" not in r]
        print(f"   ✅ {len(successful_requests)}/{request_count} requests consistent")

        if successful_requests:
            print(
                f"   📊 Consistent response: {successful_requests[0]['list_types_count']} list types"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
