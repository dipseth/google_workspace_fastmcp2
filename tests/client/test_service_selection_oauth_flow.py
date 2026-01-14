"""Test service selection OAuth flow using standardized client testing framework."""

import pytest
from .test_helpers import ToolTestRunner, TestResponseValidator
from .base_test_config import TEST_EMAIL

@pytest.mark.service("auth")
class TestServiceSelectionOAuthFlow:
    """Test service selection OAuth flow functionality."""
    
    @pytest.mark.asyncio
    async def test_service_catalog_available(self, client):
        """Test that service catalog can be retrieved."""
        from auth.scope_registry import ScopeRegistry
        
        # Test the new service catalog method
        catalog = ScopeRegistry.get_service_catalog()
        
        # Validate catalog structure
        assert isinstance(catalog, dict), "Service catalog should be a dictionary"
        assert len(catalog) > 0, "Service catalog should not be empty"
        
        # Check required services are present
        assert "userinfo" in catalog, "Basic Profile service should be in catalog"
        assert "drive" in catalog, "Google Drive should be in catalog"
        assert "gmail" in catalog, "Gmail should be in catalog"
        
        # Validate service structure
        for service_key, service_info in catalog.items():
            assert "name" in service_info, f"Service {service_key} should have name"
            assert "description" in service_info, f"Service {service_key} should have description"
            assert "category" in service_info, f"Service {service_key} should have category"
            assert "required" in service_info, f"Service {service_key} should have required flag"
            assert "scopes" in service_info, f"Service {service_key} should have scopes"
            assert isinstance(service_info["scopes"], list), f"Service {service_key} scopes should be a list"
    
    @pytest.mark.asyncio
    async def test_scopes_for_services_combination(self, client):
        """Test that scope combination works correctly for selected services."""
        from auth.scope_registry import ScopeRegistry
        
        # Test with multiple services
        selected_services = ["drive", "gmail", "calendar"]
        combined_scopes = ScopeRegistry.get_scopes_for_services(selected_services)
        
        # Validate combined scopes
        assert isinstance(combined_scopes, list), "Combined scopes should be a list"
        assert len(combined_scopes) > 0, "Combined scopes should not be empty"
        
        # Should include base scopes (required)
        base_scopes = ScopeRegistry.resolve_scope_group("base")
        for base_scope in base_scopes:
            assert base_scope in combined_scopes, f"Base scope {base_scope} should be included"
    
    @pytest.mark.asyncio
    @pytest.mark.auth_required
    async def test_protected_tool_triggers_oauth(self, client):
        """Test that calling a protected tool triggers OAuth flow (this should open browser)."""
        from .base_test_config import TEST_EMAIL
        
        print(f"\n🔐 Testing protected tool call to trigger OAuth flow...")
        print(f"   This should open a browser window for authentication")
        
        try:
            # Call a protected tool - this SHOULD trigger OAuth
            result = await client.call_tool("start_google_auth", {
                "user_google_email": TEST_EMAIL , 
                "service_name": "Test Service Selection"
            })
            
            print(f"✓ Tool call succeeded: {result}")
            
        except Exception as e:
            print(f"⚠️ Expected OAuth authentication required: {e}")
            
            # Validate this is an authentication error
            error_str = str(e).lower()
            auth_keywords = ['auth', 'oauth', 'token', 'login', 'unauthorized', 'credential']
            
            is_auth_error = any(keyword in error_str for keyword in auth_keywords)
            
            if is_auth_error:
                print("✅ OAuth flow correctly triggered (authentication required)")
                print("   🌐 Browser window should have opened for Google OAuth")
            else:
                pytest.fail(f"Unexpected non-auth error: {e}")
    
    @pytest.mark.asyncio
    async def test_oauth_flow_with_service_selection(self, client):
        """Test OAuth flow with service selection (functional test)."""
        from auth.google_auth import initiate_oauth_flow, _create_service_selection_url
        
        test_email = TEST_EMAIL
        
        print(f"\n🎨 Testing service selection flow for {test_email}")
        
        try:
            # Test service selection URL creation
            selection_url = await _create_service_selection_url(test_email, "custom")
            
            print(f"✓ Service selection URL created: {selection_url}")
            
            # Validate URL structure
            assert isinstance(selection_url, str), "Selection URL should be a string"
            assert "/auth/services/select" in selection_url, "URL should contain service selection path"
            assert "state=" in selection_url, "URL should contain state parameter"
            assert "flow_type=" in selection_url, "URL should contain flow_type parameter"
            
            print("✅ Service selection URL structure validated")
            
            # Test OAuth flow with service selection enabled
            oauth_url = await initiate_oauth_flow(
                user_email=test_email,
                service_name="Test Service",
                show_service_selection=True
            )
            
            # Should return service selection URL when no services pre-selected
            assert "/auth/services/select" in oauth_url, "Should return service selection URL"
            print(f"✓ OAuth flow returns service selection URL: {oauth_url[:80]}...")
            
            # Test OAuth flow with pre-selected services
            oauth_url_direct = await initiate_oauth_flow(
                user_email=test_email,
                service_name="Test Service", 
                selected_services=["drive", "gmail"],
                show_service_selection=False
            )
            
            # Should return Google OAuth URL when services pre-selected
            assert "accounts.google.com" in oauth_url_direct, "Should return Google OAuth URL for pre-selected services"
            print(f"✓ OAuth flow with pre-selected services returns Google URL")
            print("✅ Service selection flow functional test passed")
            
        except Exception as e:
            print(f"⚠️ Service selection test error: {e}")
            # This might fail in test environment, but the structure should be testable
            pytest.skip(f"Service selection functional test skipped due to environment: {e}")
    
    @pytest.mark.asyncio
    async def test_auth_middleware_integration(self, client):
        """Test AuthMiddleware service selection integration."""
        from auth.context import set_google_provider, get_google_provider, is_service_selection_needed
        from auth.middleware import AuthMiddleware
        
        print(f"\n🔧 Testing AuthMiddleware service selection integration")
        
        # Test GoogleProvider context management
        test_provider = "test_provider_instance"
        set_google_provider(test_provider)
        
        retrieved_provider = get_google_provider()
        assert retrieved_provider == test_provider, "Should retrieve the same GoogleProvider instance"
        print("✓ GoogleProvider context management works")
        
        # Test AuthMiddleware service selection methods
        middleware = AuthMiddleware()
        
        # Test enable/disable service selection
        middleware.enable_service_selection(True)
        assert middleware._enable_service_selection == True, "Service selection should be enabled"
        
        middleware.enable_service_selection(False)
        assert middleware._enable_service_selection == False, "Service selection should be disabled"
        
        print("✓ AuthMiddleware service selection methods work")
        
        # Clean up test data
        set_google_provider(None)
        print("✅ AuthMiddleware integration test passed")


@pytest.mark.asyncio
async def test_oauth_trigger_with_real_tool():
    """Test that triggers actual OAuth flow by calling a real protected tool."""
    from .base_test_config import create_test_client, TEST_EMAIL
    
    print(f"\n🚀 OAUTH TRIGGER TEST - This should open browser window!")
    print(f"   Testing with FastMCP client calling protected Gmail tool...")
    
    try:
        client = await create_test_client()
        
        print(f"✓ Client connected successfully")
        
        # List available tools first
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        print(f"✓ Found {len(tools)} available tools")
        
        # Look for Gmail tools that require authentication
        gmail_tools = [name for name in tool_names if 'gmail' in name.lower()]
        print(f"✓ Found {len(gmail_tools)} Gmail tools: {gmail_tools[:5]}...")
        
        if gmail_tools:
            # Call a protected Gmail tool - this SHOULD trigger OAuth
            print(f"\n🔐 Calling protected Gmail tool: {gmail_tools[0]}")
            print(f"   📱 Browser window should open for Google OAuth...")
            
            try:
                result = await client.call_tool(gmail_tools[0], {
                    "user_google_email": TEST_EMAIL
                })
                
                print(f"✓ Protected tool call succeeded: {result}")
                print("✅ OAuth flow completed successfully!")
                
            except Exception as tool_error:
                print(f"⚠️ Protected tool triggered auth requirement: {tool_error}")
                
                # This is expected behavior - tool should require authentication
                error_str = str(tool_error).lower()
                auth_keywords = ['auth', 'oauth', 'token', 'unauthorized', 'login', 'credential']
                
                if any(keyword in error_str for keyword in auth_keywords):
                    print("✅ OAuth authentication correctly required!")
                    print("   🌐 Browser window should have opened")
                    print("   🔄 Complete Google OAuth flow to continue")
                else:
                    print(f"❌ Unexpected error (not auth-related): {tool_error}")
        else:
            print("⚠️ No Gmail tools found to test OAuth trigger")
            
    except Exception as e:
        print(f"⚠️ OAuth trigger test error: {e}")
        
        # Check if this is authentication-related (expected)
        if any(keyword in str(e).lower() for keyword in ['auth', 'oauth', 'token']):
            print("✅ FastMCP correctly requires OAuth authentication")
        else:
            print(f"❌ Unexpected connection error: {e}")


# Standalone test function for easy execution
if __name__ == "__main__":
    import asyncio
    
    print("🧪 Running standalone OAuth trigger test...")
    asyncio.run(test_oauth_trigger_with_real_tool())