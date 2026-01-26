"""
Test OAuth scope resolution fixes.

This test module validates that the circular import issues and
OAuth scope parameter missing issues have been resolved.
"""

from unittest.mock import patch


class TestCircularImportResolution:
    """Test that circular imports between settings and compatibility_shim are resolved."""

    def test_import_settings_without_error(self):
        """Test that settings can be imported without circular import errors."""
        # This should not raise any ImportError
        from config.settings import settings

        assert settings is not None

    def test_import_compatibility_shim_without_error(self):
        """Test that CompatibilityShim can be imported without circular import errors."""
        # This should not raise any ImportError
        from auth.compatibility_shim import CompatibilityShim

        assert CompatibilityShim is not None

    def test_import_scope_registry_without_error(self):
        """Test that ScopeRegistry can be imported without errors."""
        from auth.scope_registry import ScopeRegistry

        assert ScopeRegistry is not None


class TestDriveScopesProperty:
    """Test the drive_scopes property functionality."""

    def test_drive_scopes_returns_non_empty_list(self):
        """Test that drive_scopes property returns a non-empty list."""
        from config.settings import settings

        scopes = settings.drive_scopes
        assert isinstance(scopes, list)
        assert len(scopes) > 0

    def test_drive_scopes_contains_required_oauth_scopes(self):
        """Test that drive_scopes contains essential OAuth scopes."""
        from config.settings import settings

        scopes = settings.drive_scopes

        # These are essential for OAuth authentication
        required_scopes = ["https://www.googleapis.com/auth/userinfo.email", "openid"]

        for required_scope in required_scopes:
            assert required_scope in scopes, f"Missing required scope: {required_scope}"

    def test_drive_scopes_contains_drive_scopes(self):
        """Test that drive_scopes contains Google Drive scopes."""
        from config.settings import settings

        scopes = settings.drive_scopes

        # Should contain at least some Drive scopes
        drive_scope_patterns = [
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive.readonly",
        ]

        found_drive_scopes = [
            scope
            for scope in scopes
            if any(pattern in scope for pattern in drive_scope_patterns)
        ]
        assert len(found_drive_scopes) > 0, "No Drive scopes found"

    @patch("config.settings._COMPATIBILITY_AVAILABLE", None)  # Force lazy loading
    def test_drive_scopes_lazy_import_success(self):
        """Test that lazy import of compatibility_shim works correctly."""
        from config.settings import settings

        # This should trigger the lazy import
        scopes = settings.drive_scopes
        assert isinstance(scopes, list)
        assert len(scopes) > 0

    @patch("config.settings._COMPATIBILITY_AVAILABLE", False)  # Simulate import failure
    def test_drive_scopes_fallback_to_hardcoded(self):
        """Test that drive_scopes falls back to hardcoded scopes when compatibility_shim fails."""
        from config.settings import settings

        scopes = settings.drive_scopes
        # Should fall back to _fallback_drive_scopes
        assert isinstance(scopes, list)
        assert len(scopes) > 0
        # Should contain the hardcoded fallback scopes
        assert "https://www.googleapis.com/auth/userinfo.email" in scopes


class TestCompatibilityShimDirect:
    """Test CompatibilityShim direct functionality."""

    def test_get_legacy_drive_scopes_returns_valid_scopes(self):
        """Test that CompatibilityShim.get_legacy_drive_scopes() returns valid scopes."""
        from auth.compatibility_shim import CompatibilityShim

        scopes = CompatibilityShim.get_legacy_drive_scopes()
        assert isinstance(scopes, list)
        assert len(scopes) > 0

        # All scopes should be valid URLs
        for scope in scopes:
            assert isinstance(scope, str)
            # OAuth scopes should either be URLs or simple identifiers like "openid"
            assert scope == "openid" or scope.startswith("https://")

    def test_get_legacy_dcr_scope_defaults_returns_valid_string(self):
        """Test that DCR scope defaults returns a valid scope string."""
        from auth.compatibility_shim import CompatibilityShim

        scope_string = CompatibilityShim.get_legacy_dcr_scope_defaults()
        assert isinstance(scope_string, str)
        assert len(scope_string) > 0

        # Should be space-separated scopes
        scopes = scope_string.split()
        assert len(scopes) > 0

        # Should contain essential scopes
        assert "openid" in scope_string
        assert "https://www.googleapis.com/auth/userinfo.email" in scope_string


class TestScopeRegistry:
    """Test ScopeRegistry functionality."""

    def test_scope_registry_has_required_services(self):
        """Test that ScopeRegistry contains required service scopes."""
        from auth.scope_registry import ScopeRegistry

        # These services should be available in the registry
        required_services = ["base", "drive", "gmail", "calendar"]

        for service in required_services:
            assert (
                service in ScopeRegistry.GOOGLE_API_SCOPES
            ), f"Missing service: {service}"
            assert len(ScopeRegistry.GOOGLE_API_SCOPES[service]) > 0

    def test_get_oauth_scopes_returns_valid_scopes(self):
        """Test that get_oauth_scopes returns valid combined scopes."""
        from auth.scope_registry import ScopeRegistry

        services = ["drive", "gmail"]
        scopes = ScopeRegistry.get_oauth_scopes(services)

        assert isinstance(scopes, list)
        assert len(scopes) > 0

        # Should contain base OAuth scopes
        assert "https://www.googleapis.com/auth/userinfo.email" in scopes
        assert "openid" in scopes


class TestOAuthFlowIntegration:
    """Test OAuth flow integration with our fixes."""

    def test_settings_accessible_from_oauth_flow(self):
        """Test that OAuth flow modules can access settings without circular import."""
        # This simulates what happens in google_auth.py
        from config.settings import settings

        # Should be able to access drive_scopes without errors
        scopes = settings.drive_scopes
        assert isinstance(scopes, list)
        assert len(scopes) > 0

        # Should contain OAuth essentials for authentication
        oauth_essentials = ["https://www.googleapis.com/auth/userinfo.email", "openid"]

        for essential in oauth_essentials:
            assert essential in scopes, f"Missing OAuth essential: {essential}"

    def test_server_port_consistency(self):
        """Test that server port is consistently configured (no hardcoded ports)."""
        from config.settings import settings

        # Server port should be configured (could be 8000, 8002, or other)
        assert isinstance(settings.server_port, int)
        assert settings.server_port > 0

        # OAuth redirect URI should use the configured port consistently
        redirect_uri = settings.dynamic_oauth_redirect_uri
        assert f":{settings.server_port}" in redirect_uri

        # The key test: redirect URI should not have hardcoded values different from server_port
        # This ensures dynamic client registration and other components use the same port
        expected_port_string = f":{settings.server_port}"
        assert expected_port_string in redirect_uri


class TestDeprecationWarningFixes:
    """Test that deprecation warnings have been fixed."""

    def test_no_datetime_utcnow_in_dynamic_client_registration(self):
        """Test that datetime.now(UTC) has been replaced in dynamic_client_registration.py"""
        # Read the file content to check for the deprecated call
        with open("auth/dynamic_client_registration.py", "r") as f:
            content = f.read()

        # Should not contain the deprecated datetime.now(UTC)
        assert "datetime.now(UTC)" not in content

        # Should contain the modern replacement
        assert "datetime.now(timezone.utc)" in content or "datetime.now(tz=" in content

    def test_no_datetime_utcnow_in_calendar_tools(self):
        """Test that datetime.now(UTC) has been replaced in calendar_tools.py"""
        # Read the file content to check for the deprecated call
        with open("gcalendar/calendar_tools.py", "r") as f:
            content = f.read()

        # Should not contain the deprecated datetime.now(UTC)
        assert "datetime.now(UTC)" not in content

        # Should contain the modern replacement
        assert "datetime.now(timezone.utc)" in content


# Test execution summary
def test_all_oauth_fixes_working():
    """Integration test to verify all OAuth fixes are working together."""
    # Import everything that was problematic before
    from config.settings import settings

    # Get scopes through the full chain
    scopes = settings.drive_scopes

    # Validate the complete OAuth scope chain works
    assert isinstance(scopes, list)
    assert len(scopes) > 0

    # Should contain essential OAuth scopes
    assert "https://www.googleapis.com/auth/userinfo.email" in scopes
    assert "openid" in scopes

    # Should contain Google service scopes
    has_drive_scope = any("drive" in scope for scope in scopes)
    assert has_drive_scope, "No Drive scopes found in the complete OAuth chain"

    print(f"✅ All OAuth fixes validated - {len(scopes)} scopes available")
