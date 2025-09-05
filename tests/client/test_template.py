"""Template for creating new standardized client tests.

Copy this file and rename it to test_<your_service>_<description>.py
Follow this pattern for consistent, compliant tests.
"""

import pytest
from .test_helpers import ToolTestRunner, TestResponseValidator, print_test_result, get_common_test_tools


@pytest.mark.service("template")  # Replace with your service: gmail, drive, docs, etc.
class TestTemplateService:
    """Test template for Google Workspace service tools.
    
    Replace 'TemplateService' with your service name.
    Example: TestGmailTools, TestDriveOperations, etc.
    """
    
    @pytest.mark.asyncio
    async def test_service_tools_availability(self, client):
        """Test that expected service tools are available."""
        # Replace 'template' with your service name
        expected_tools = get_common_test_tools("template")
        
        if not expected_tools:
            pytest.skip("No common tools defined for this service")
        
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        print(f"\n🔍 Testing availability of {len(expected_tools)} service tools")
        
        for tool_name in expected_tools:
            if tool_name in tool_names:
                print(f"   ✅ {tool_name} - Available")
            else:
                print(f"   ❌ {tool_name} - Missing")
                
        # At least some tools should be available
        available_count = sum(1 for tool in expected_tools if tool in tool_names)
        assert available_count > 0, f"Expected at least some tools from {expected_tools}"
        print(f"   📊 {available_count}/{len(expected_tools)} tools available")
    
    @pytest.mark.asyncio
    async def test_primary_tool_auth_patterns(self, client):
        """Test authentication patterns for primary service tool."""
        # Replace with your primary tool name
        primary_tool = "your_primary_tool_name"
        
        # Get test runner
        from .base_test_config import TEST_EMAIL
        runner = ToolTestRunner(client, TEST_EMAIL)
        
        # Check if tool exists
        if not await runner.test_tool_availability(primary_tool):
            pytest.skip(f"Primary tool {primary_tool} not available")
        
        print(f"\n🔑 Testing authentication patterns for {primary_tool}")
        
        # Test both auth patterns
        # Replace {} with any required parameters for your tool
        auth_results = await runner.test_auth_patterns(primary_tool, {})
        
        print_test_result("Explicit email parameter", auth_results["explicit_email"])
        print_test_result("Middleware injection", auth_results["middleware_injection"])
        
        # Both patterns should work or give valid auth-related responses
        explicit_valid = (auth_results["explicit_email"]["success"] or 
                         auth_results["explicit_email"]["is_auth_related"])
        
        middleware_valid = (auth_results["middleware_injection"]["success"] or 
                           auth_results["middleware_injection"]["param_required_at_client"])
        
        assert explicit_valid, "Explicit email pattern should work or give auth error"
        assert middleware_valid, "Middleware pattern should work or be handled properly"
        
        print(f"✅ Authentication patterns validated for {primary_tool}")
    
    @pytest.mark.asyncio
    async def test_tool_with_sample_params(self, client):
        """Test a tool with realistic sample parameters."""
        # Replace with your tool and parameters
        tool_name = "your_tool_name"
        sample_params = {
            # Add your tool's sample parameters here
            # "param1": "value1",
            # "param2": "value2"
        }
        
        from .base_test_config import TEST_EMAIL
        runner = ToolTestRunner(client, TEST_EMAIL)
        
        if not await runner.test_tool_availability(tool_name):
            pytest.skip(f"Tool {tool_name} not available")
        
        print(f"\n🧪 Testing {tool_name} with sample parameters")
        
        result = await runner.test_tool_with_explicit_email(tool_name, sample_params)
        print_test_result(f"{tool_name} execution", result)
        
        # Should get either success or valid auth error
        assert result["success"] or result["is_auth_related"], \
            f"Tool should execute or give auth error. Content: {result['content'][:200]}"
    
    @pytest.mark.asyncio
    @pytest.mark.auth_required
    async def test_authenticated_workflow(self, client):
        """Test a complete workflow requiring authentication.
        
        This test is marked as auth_required and will be skipped if no auth is available.
        """
        from .base_test_config import TEST_EMAIL
        runner = ToolTestRunner(client, TEST_EMAIL)
        
        print(f"\n🔐 Testing authenticated workflow")
        
        # Replace with your workflow steps
        workflow_steps = [
            # ("tool_name", {"param": "value"}),
            # ("another_tool", {"param2": "value2"}),
        ]
        
        if not workflow_steps:
            pytest.skip("No workflow steps defined")
        
        results = []
        for tool_name, params in workflow_steps:
            if not await runner.test_tool_availability(tool_name):
                pytest.skip(f"Workflow tool {tool_name} not available")
            
            result = await runner.test_tool_with_explicit_email(tool_name, params)
            results.append((tool_name, result))
            print_test_result(f"Workflow step: {tool_name}", result)
        
        # At least one step should work (or give auth error)
        valid_results = [r for _, r in results if r["success"] or r["is_auth_related"]]
        assert len(valid_results) > 0, "At least one workflow step should be valid"
        
        print(f"✅ Workflow tested: {len(valid_results)}/{len(results)} steps valid")


@pytest.mark.service("template")  # Replace with your service
class TestTemplateServiceIntegration:
    """Integration tests for service-specific workflows."""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_service_integration_workflow(self, client):
        """Test integration between multiple service tools."""
        print(f"\n🔄 Testing service integration workflow")
        
        # Replace with your integration test logic
        # Example: Create document → Share via email → Schedule calendar reminder
        
        pytest.skip("Replace with your integration test logic")
    
    @pytest.mark.asyncio
    async def test_backward_compatibility(self, client):
        """Test that service maintains backward compatibility."""
        print(f"\n🔄 Testing backward compatibility")
        
        # Test that old parameter patterns still work
        # Replace with service-specific compatibility tests
        
        pytest.skip("Replace with backward compatibility tests")


# Example of how to create service-specific test classes
@pytest.mark.service("example")
class TestExampleServiceTools:
    """Example showing how to customize for a specific service."""
    
    @pytest.mark.asyncio
    async def test_gmail_labels_example(self, client):
        """Example test for Gmail labels functionality."""
        from .base_test_config import TEST_EMAIL
        runner = ToolTestRunner(client, TEST_EMAIL)
        
        tool_name = "list_gmail_labels"
        
        if not await runner.test_tool_availability(tool_name):
            pytest.skip(f"Gmail tool {tool_name} not available")
        
        print(f"\n📧 Testing Gmail labels functionality")
        
        # Test the tool
        result = await runner.test_tool_with_explicit_email(tool_name, {})
        print_test_result("Gmail labels test", result, verbose=True)
        
        # Validate Gmail-specific response
        if result["success"]:
            is_gmail_response = TestResponseValidator.validate_service_response(
                result["content"], "gmail"
            )
            assert is_gmail_response or result["is_auth_related"], \
                "Should get Gmail-specific response or auth error"
        
        print("✅ Gmail labels test completed")


if __name__ == "__main__":
    # Run this specific test file
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])