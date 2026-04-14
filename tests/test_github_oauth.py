"""Tests for GitHub OAuth integration and alpha access gating.

Tests cover:
- Alpha gating: repo star check, email allowlist
- SSOGitHubProvider: subclass behavior, user caching
- DualOAuthRouter: provider selection page, route registration
- AuthMiddleware: GitHub auth provenance detection
"""

import pytest

from auth.alpha_gating import (
    AlphaAccessDenied,
    check_google_email_allowlist,
)
from auth.types import AuthProvenance, SessionKey

# ─── Alpha Gating: Email Allowlist ────────────────────────────────────────────


class TestGoogleEmailAllowlist:
    """Tests for Google OAuth email allowlist checking."""

    def test_empty_allowlist_allows_all(self):
        assert check_google_email_allowlist("anyone@example.com", "") is True

    def test_email_on_allowlist(self):
        assert (
            check_google_email_allowlist(
                "alice@gmail.com", "alice@gmail.com,bob@gmail.com"
            )
            is True
        )

    def test_email_not_on_allowlist(self):
        assert (
            check_google_email_allowlist(
                "eve@gmail.com", "alice@gmail.com,bob@gmail.com"
            )
            is False
        )

    def test_case_insensitive(self):
        assert (
            check_google_email_allowlist("Alice@Gmail.COM", "alice@gmail.com") is True
        )

    def test_whitespace_handling(self):
        assert (
            check_google_email_allowlist(
                "alice@gmail.com", " alice@gmail.com , bob@gmail.com "
            )
            is True
        )


# ─── Alpha Gating: Repo Star Check ───────────────────────────────────────────


class TestGitHubStarCheck:
    """Tests for GitHub repo star checking."""

    @pytest.mark.asyncio
    async def test_no_repo_configured_returns_true(self):
        from auth.alpha_gating import check_github_star

        result = await check_github_star("fake-token", "")
        assert result is True

    @pytest.mark.asyncio
    async def test_star_check_with_invalid_token(self):
        """Invalid token should return False (401 from GitHub)."""
        from auth.alpha_gating import check_github_star

        result = await check_github_star("invalid-token-xxx", "octocat/Hello-World")
        assert result is False


# ─── Alpha Gating: Enforce ────────────────────────────────────────────────────


class TestEnforceAlphaAccess:
    """Tests for the enforce_alpha_access function."""

    @pytest.mark.asyncio
    async def test_alpha_mode_disabled_allows_all(self):
        from unittest.mock import MagicMock

        from auth.alpha_gating import enforce_alpha_access

        mock_settings = MagicMock()
        mock_settings.alpha_mode = False

        # Should not raise
        await enforce_alpha_access(
            provider="github",
            github_token="fake",
            settings=mock_settings,
        )

    @pytest.mark.asyncio
    async def test_google_email_on_allowlist_passes(self):
        from unittest.mock import MagicMock

        from auth.alpha_gating import enforce_alpha_access

        mock_settings = MagicMock()
        mock_settings.alpha_mode = True
        mock_settings.alpha_google_email_allowlist = "allowed@gmail.com"

        await enforce_alpha_access(
            provider="google",
            google_email="allowed@gmail.com",
            settings=mock_settings,
        )

    @pytest.mark.asyncio
    async def test_google_email_not_on_allowlist_raises(self):
        from unittest.mock import MagicMock

        from auth.alpha_gating import enforce_alpha_access

        mock_settings = MagicMock()
        mock_settings.alpha_mode = True
        mock_settings.alpha_google_email_allowlist = "allowed@gmail.com"

        with pytest.raises(AlphaAccessDenied) as exc_info:
            await enforce_alpha_access(
                provider="google",
                google_email="not-allowed@gmail.com",
                settings=mock_settings,
            )
        assert "not on the alpha access list" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_github_no_token_raises(self):
        from unittest.mock import MagicMock

        from auth.alpha_gating import enforce_alpha_access

        mock_settings = MagicMock()
        mock_settings.alpha_mode = True

        with pytest.raises(AlphaAccessDenied):
            await enforce_alpha_access(
                provider="github",
                github_token=None,
                settings=mock_settings,
            )


# ─── Auth Types ───────────────────────────────────────────────────────────────


class TestAuthTypes:
    """Tests for updated auth types."""

    def test_github_oauth_provenance_exists(self):
        assert AuthProvenance.GITHUB_OAUTH == "github_oauth"

    def test_github_session_keys_exist(self):
        assert SessionKey.GITHUB_LOGIN == "github_login"
        assert SessionKey.GITHUB_EMAIL == "github_email"
        assert SessionKey.GITHUB_USER_ID == "github_user_id"
        assert SessionKey.GITHUB_STARRED_REPO == "github_starred_repo"


# ─── SSOGitHubProvider ───────────────────────────────────────────────────────


class TestSSOGitHubProvider:
    """Tests for the SSOGitHubProvider subclass."""

    def test_provider_init(self):
        from auth.github_provider import SSOGitHubProvider

        provider = SSOGitHubProvider(
            client_id="test-id",
            client_secret="test-secret",
            base_url="http://localhost:8002",
            gating_repo="myorg/myrepo",
            alpha_mode=True,
        )
        assert provider._gating_repo == "myorg/myrepo"
        assert provider._alpha_mode is True
        assert provider._github_user_cache.get("nonexistent") is None

    def test_get_cached_user_returns_none_for_unknown(self):
        from auth.github_provider import SSOGitHubProvider

        provider = SSOGitHubProvider(
            client_id="test-id",
            client_secret="test-secret",
            base_url="http://localhost:8002",
        )
        assert provider.get_cached_github_user("12345") is None

    def test_get_cached_user_returns_data(self):
        from auth.github_provider import SSOGitHubProvider

        provider = SSOGitHubProvider(
            client_id="test-id",
            client_secret="test-secret",
            base_url="http://localhost:8002",
        )
        provider._github_user_cache["12345"] = {
            "login": "testuser",
            "email": "test@example.com",
        }
        cached = provider.get_cached_github_user("12345")
        assert cached["login"] == "testuser"


# ─── DualOAuthRouter ─────────────────────────────────────────────────────────


class TestDualOAuthRouter:
    """Tests for the dual OAuth provider selection router."""

    def test_routes_with_both_providers(self):
        from unittest.mock import MagicMock

        from auth.dual_oauth_provider import DualOAuthRouter

        router = DualOAuthRouter(
            google_provider=MagicMock(),
            github_provider=MagicMock(),
            settings=MagicMock(),
        )
        routes = router.get_custom_routes()
        paths = [r.path for r in routes]
        assert "/auth/github/authorize" in paths
        assert "/auth/github/callback" in paths
        assert "/auth/select" in paths
        assert "/auth/select/google" in paths

    def test_routes_github_only(self):
        from unittest.mock import MagicMock

        from auth.dual_oauth_provider import DualOAuthRouter

        router = DualOAuthRouter(
            google_provider=None,
            github_provider=MagicMock(),
            settings=MagicMock(),
        )
        routes = router.get_custom_routes()
        paths = [r.path for r in routes]
        assert "/auth/github/authorize" in paths
        assert "/auth/github/callback" in paths
        assert "/auth/select" not in paths  # No select page without both providers

    def test_provider_select_html_both_providers(self):
        from auth.dual_oauth_provider import build_provider_select_html

        html = build_provider_select_html(
            server_name="Test Server",
            google_url="/authorize",
            github_url="/auth/github/authorize",
            alpha_mode=True,
            github_gating_repo="myorg/myrepo",
        )
        assert "Test Server" in html
        assert "ALPHA" in html
        assert "Continue with Google" in html
        assert "Continue with GitHub" in html
        assert "myorg/myrepo" in html

    def test_provider_select_html_google_only(self):
        from auth.dual_oauth_provider import build_provider_select_html

        html = build_provider_select_html(
            server_name="Test Server",
            google_url="/authorize",
            github_url=None,
        )
        assert "Continue with Google" in html
        assert "Continue with GitHub" not in html


# ─── Config Settings ──────────────────────────────────────────────────────────


class TestGitHubSettings:
    """Tests for GitHub OAuth settings."""

    def test_settings_fields_exist(self):
        """Verify all GitHub/alpha settings fields are defined."""
        from config.settings import Settings

        s = Settings()
        # These fields should exist (values depend on .env)
        assert hasattr(s, "github_oauth_client_id")
        assert hasattr(s, "github_oauth_client_secret")
        assert hasattr(s, "github_oauth_required_scopes")
        assert hasattr(s, "github_oauth_gating_repo")
        assert hasattr(s, "alpha_mode")
        assert hasattr(s, "alpha_google_email_allowlist")
        assert hasattr(s, "alpha_github_require_star")
