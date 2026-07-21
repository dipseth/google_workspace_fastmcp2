"""
Test Photos Library scope handling after Google's 2025 API changes.

Google retired the broad photoslibrary/photoslibrary.readonly scopes
(post March 31, 2025) and rejects authorization requests that combine
Photos Library scopes with other Google API scopes
(400 invalid_request: "scopes that cannot be requested together").

These tests are pure registry logic and require no OAuth config or
external infrastructure, so they run in every environment.
"""


class TestPhotosScopeSeparation:
    def test_registry_contains_no_retired_photos_scopes(self):
        """Retired photoslibrary scopes must not exist anywhere in the registry."""
        from auth.scope_registry import ScopeRegistry

        all_scopes = set()
        for service_scopes in ScopeRegistry.GOOGLE_API_SCOPES.values():
            all_scopes.update(service_scopes.values())

        retired_found = all_scopes & ScopeRegistry.RETIRED_SCOPES
        assert not retired_found, f"Retired scopes still registered: {retired_found}"

    def test_oauth_comprehensive_has_no_photos_scopes(self):
        """The combined flow must not request Photos scopes alongside Drive."""
        from auth.scope_registry import ScopeRegistry

        scopes = ScopeRegistry.resolve_scope_group("oauth_comprehensive")
        photos_scopes = [s for s in scopes if "auth/photoslibrary" in s]
        assert photos_scopes == [], (
            f"oauth_comprehensive must not contain Photos scopes "
            f"(Google rejects the mix with Drive scopes): {photos_scopes}"
        )
        # Sanity check that Drive scopes are still present
        assert any("auth/drive" in s for s in scopes)

    def test_photos_basic_group_uses_valid_scopes_only(self):
        """photos_basic should resolve to the surviving app-created scopes."""
        from auth.scope_registry import ScopeRegistry

        scopes = ScopeRegistry.resolve_scope_group("photos_basic")
        expected = {
            "https://www.googleapis.com/auth/photoslibrary.appendonly",
            "https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata",
            "https://www.googleapis.com/auth/photoslibrary.edit.appcreateddata",
        }
        assert expected <= set(scopes)
        assert not (set(scopes) & ScopeRegistry.RETIRED_SCOPES)

    def test_get_scopes_for_services_drops_photos_from_mixed_request(self):
        """Photos must be excluded when combined with other services."""
        from auth.scope_registry import ScopeRegistry

        scopes = ScopeRegistry.get_scopes_for_services(["drive", "photos"])
        assert not any("auth/photoslibrary" in s for s in scopes)
        assert any("auth/drive" in s for s in scopes)

    def test_get_scopes_for_services_honors_photos_only_request(self):
        """A photos-only selection should still yield Photos scopes."""
        from auth.scope_registry import ScopeRegistry

        scopes = ScopeRegistry.get_scopes_for_services(["photos"])
        assert any("auth/photoslibrary" in s for s in scopes)
        # Base identity scopes are always included and are allowed with Photos
        assert "https://www.googleapis.com/auth/userinfo.email" in scopes

    def test_validate_scope_combination_rejects_photos_drive_mix(self):
        """Validation must flag Photos + Drive in one request as invalid."""
        from auth.scope_registry import ScopeRegistry

        result = ScopeRegistry.validate_scope_combination(
            [
                "https://www.googleapis.com/auth/userinfo.email",
                "openid",
                "https://www.googleapis.com/auth/photoslibrary.appendonly",
                "https://www.googleapis.com/auth/drive.file",
            ]
        )
        assert not result.is_valid
        assert any("cannot be requested together" in w for w in result.warnings)

    def test_validate_scope_combination_allows_photos_only(self):
        """A photos-only combination (plus base scopes) is valid."""
        from auth.scope_registry import ScopeRegistry

        result = ScopeRegistry.validate_scope_combination(
            [
                "https://www.googleapis.com/auth/userinfo.email",
                "openid",
                "https://www.googleapis.com/auth/photoslibrary.appendonly",
                "https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata",
            ]
        )
        assert result.is_valid

    def test_settings_drive_scopes_have_no_photos_scopes(self):
        """settings.drive_scopes (combined bundle) must be Photos-free."""
        from config.settings import settings

        scopes = settings.drive_scopes
        photos_scopes = [s for s in scopes if "auth/photoslibrary" in s]
        assert photos_scopes == []

    def test_settings_fallback_scopes_have_no_photos_scopes(self):
        """The hardcoded fallback bundle must also be Photos-free."""
        from config.settings import settings

        photos_scopes = [
            s for s in settings._fallback_drive_scopes if "auth/photoslibrary" in s
        ]
        assert photos_scopes == []

    def test_legacy_photos_mappings_resolve_to_valid_scopes(self):
        """Compatibility shim photos mappings must use surviving scopes."""
        from auth.compatibility_shim import CompatibilityShim
        from auth.scope_registry import ScopeRegistry

        groups = CompatibilityShim.get_legacy_scope_groups()
        for key in (
            "photos_read",
            "photos_append",
            "photoslibrary_read",
            "photoslibrary_append",
            "photoslibrary_readonly_appcreated",
            "photoslibrary_edit_appcreated",
        ):
            assert key in groups, f"Missing legacy mapping: {key}"
            assert groups[key] not in ScopeRegistry.RETIRED_SCOPES, (
                f"Legacy mapping {key} resolves to retired scope {groups[key]}"
            )
