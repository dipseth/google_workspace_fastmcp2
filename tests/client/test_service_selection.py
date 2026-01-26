"""Test service selection OAuth flow using standardized framework."""

import pytest

from .base_test_config import TEST_EMAIL


@pytest.mark.service("auth")
class TestServiceSelection:
    """Tests for service selection OAuth flow functionality."""

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
            assert (
                "description" in service_info
            ), f"Service {service_key} should have description"
            assert (
                "category" in service_info
            ), f"Service {service_key} should have category"
            assert (
                "required" in service_info
            ), f"Service {service_key} should have required flag"
            assert "scopes" in service_info, f"Service {service_key} should have scopes"
            assert isinstance(
                service_info["scopes"], list
            ), f"Service {service_key} scopes should be a list"

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
            assert (
                base_scope in combined_scopes
            ), f"Base scope {base_scope} should be included"

        # Should include service-specific scopes
        drive_scopes = ScopeRegistry.get_service_scopes("drive", "basic")
        gmail_scopes = ScopeRegistry.get_service_scopes("gmail", "basic")
        calendar_scopes = ScopeRegistry.get_service_scopes("calendar", "basic")

        # At least some service scopes should be present
        drive_present = any(scope in combined_scopes for scope in drive_scopes)
        gmail_present = any(scope in combined_scopes for scope in gmail_scopes)
        calendar_present = any(scope in combined_scopes for scope in calendar_scopes)

        assert drive_present, "Drive scopes should be included"
        assert gmail_present, "Gmail scopes should be included"
        assert calendar_present, "Calendar scopes should be included"

    @pytest.mark.asyncio
    async def test_oauth_with_service_selection_flow(self, client):
        """Test OAuth flow with service selection (without actual authentication)."""
        from auth.google_auth import _create_service_selection_url, initiate_oauth_flow

        test_email = TEST_EMAIL

        # Test service selection URL creation
        selection_url = await _create_service_selection_url(test_email, "custom")

        # Validate URL structure
        assert isinstance(selection_url, str), "Selection URL should be a string"
        assert (
            "/auth/services/select" in selection_url
        ), "URL should contain service selection path"
        assert "state=" in selection_url, "URL should contain state parameter"
        assert "flow_type=" in selection_url, "URL should contain flow_type parameter"

        # Test OAuth flow with service selection enabled
        oauth_url = await initiate_oauth_flow(
            user_email=test_email,
            service_name="Test Service",
            show_service_selection=True,
        )

        # Should return service selection URL when no services pre-selected
        assert (
            "/auth/services/select" in oauth_url
        ), "Should return service selection URL"

        # Test OAuth flow with pre-selected services
        oauth_url_direct = await initiate_oauth_flow(
            user_email=test_email,
            service_name="Test Service",
            selected_services=["drive", "gmail"],
            show_service_selection=False,
        )

        # Should return Google OAuth URL when services pre-selected
        assert (
            "accounts.google.com" in oauth_url_direct
        ), "Should return Google OAuth URL for pre-selected services"

    @pytest.mark.asyncio
    async def test_service_selection_callback_handling(self, client):
        """Test service selection callback handling."""
        from auth.google_auth import (
            _create_service_selection_url,
            _service_selection_cache,
            handle_service_selection_callback,
        )

        test_email = TEST_EMAIL

        # Create a service selection URL (which populates the cache)
        selection_url = await _create_service_selection_url(test_email, "custom")

        # Extract state from URL
        import urllib.parse

        parsed_url = urllib.parse.urlparse(selection_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        state = query_params.get("state", [None])[0]

        assert state is not None, "State should be present in selection URL"
        assert state in _service_selection_cache, "State should be in selection cache"

        # Test handling service selection callback
        selected_services = ["drive", "gmail", "calendar"]

        try:
            oauth_url = await handle_service_selection_callback(
                state, selected_services
            )

            # Should return a Google OAuth URL
            assert isinstance(oauth_url, str), "Callback should return OAuth URL"
            assert "accounts.google.com" in oauth_url, "Should return Google OAuth URL"

            # State should be consumed (removed from cache)
            assert (
                state not in _service_selection_cache
            ), "State should be removed from cache after use"

        except Exception as e:
            # This is expected in test environment without full OAuth setup
            assert "GoogleAuthError" in str(type(e)) or "OAuth" in str(
                e
            ), f"Should get OAuth-related error: {e}"

    @pytest.mark.asyncio
    async def test_service_selection_cache_cleanup(self, client):
        """Test that service selection cache cleans up expired entries."""
        from datetime import datetime, timedelta

        from auth.google_auth import (
            _cleanup_service_selection_cache,
            _service_selection_cache,
        )

        # Add an expired entry manually
        expired_state = "expired_test_state"
        expired_time = datetime.now() - timedelta(
            minutes=35
        )  # 35 minutes ago (should be cleaned)

        _service_selection_cache[expired_state] = {
            "user_email": TEST_EMAIL,
            "flow_type": "test",
            "timestamp": expired_time.isoformat(),
        }

        # Add a fresh entry
        fresh_state = "fresh_test_state"
        _service_selection_cache[fresh_state] = {
            "user_email": TEST_EMAIL,
            "flow_type": "test",
            "timestamp": datetime.now().isoformat(),
        }

        assert (
            len(_service_selection_cache) >= 2
        ), "Cache should have at least 2 entries"

        # Run cleanup
        _cleanup_service_selection_cache()

        # Expired entry should be removed, fresh entry should remain
        assert (
            expired_state not in _service_selection_cache
        ), "Expired entry should be removed"
        assert fresh_state in _service_selection_cache, "Fresh entry should remain"

        # Clean up test data
        _service_selection_cache.pop(fresh_state, None)

    @pytest.mark.asyncio
    async def test_auth_middleware_service_selection_integration(self, client):
        """Test AuthMiddleware service selection integration."""
        # This tests the context functions we added
        from auth.context import (
            get_google_provider,
            set_google_provider,
        )
        from auth.middleware import AuthMiddleware

        # Test GoogleProvider context management
        test_provider = "test_provider_instance"
        set_google_provider(test_provider)

        retrieved_provider = get_google_provider()
        assert (
            retrieved_provider == test_provider
        ), "Should retrieve the same GoogleProvider instance"

        # Test AuthMiddleware service selection methods
        middleware = AuthMiddleware()

        # Test enable/disable service selection
        middleware.enable_service_selection(True)
        assert (
            middleware._enable_service_selection == True
        ), "Service selection should be enabled"

        middleware.enable_service_selection(False)
        assert (
            middleware._enable_service_selection == False
        ), "Service selection should be disabled"

        # Clean up test data
        set_google_provider(None)
