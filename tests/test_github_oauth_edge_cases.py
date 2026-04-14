"""
Tests for GitHub OAuth edge cases.

Covers:
- Private/missing GitHub email handling
- GitHub user cache behavior with None email
- Extract upstream claims with missing fields
"""

import pytest

from auth.github_provider import SSOGitHubProvider


class TestGitHubPrivateEmail:
    """Tests for handling GitHub users with private/missing email."""

    def test_cache_stores_none_email(self):
        """GitHub user with private email should cache email as None."""
        provider = SSOGitHubProvider(
            client_id="test-id",
            client_secret="test-secret",
            base_url="http://localhost:8002",
        )
        # Simulate caching a user with private email (None)
        provider._github_user_cache["99999"] = {
            "login": "private-user",
            "email": None,
            "name": "Private User",
            "id": "99999",
            "avatar_url": "https://avatars.githubusercontent.com/u/99999",
            "starred_gating_repo": True,
        }
        cached = provider.get_cached_github_user("99999")
        assert cached is not None
        assert cached["email"] is None
        assert cached["login"] == "private-user"

    def test_cache_miss_returns_none(self):
        """Cache lookup for non-existent user returns None."""
        provider = SSOGitHubProvider(
            client_id="test-id",
            client_secret="test-secret",
            base_url="http://localhost:8002",
        )
        assert provider.get_cached_github_user("nonexistent") is None

    @pytest.mark.asyncio
    async def test_extract_claims_with_no_access_token(self):
        """Missing access_token in idp_tokens returns None claims."""
        provider = SSOGitHubProvider(
            client_id="test-id",
            client_secret="test-secret",
            base_url="http://localhost:8002",
        )
        result = await provider._extract_upstream_claims({})
        assert result is None

    @pytest.mark.asyncio
    async def test_extract_claims_with_empty_token(self):
        """Empty access_token in idp_tokens returns None claims."""
        provider = SSOGitHubProvider(
            client_id="test-id",
            client_secret="test-secret",
            base_url="http://localhost:8002",
        )
        result = await provider._extract_upstream_claims({"access_token": ""})
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_github_user_with_invalid_token(self):
        """Invalid token should return None without raising."""
        provider = SSOGitHubProvider(
            client_id="test-id",
            client_secret="test-secret",
            base_url="http://localhost:8002",
        )
        result = await provider._fetch_github_user("completely-invalid-token")
        assert result is None


class TestDualOAuthRouterEdgeCases:
    """Edge case tests for DualOAuthRouter."""

    def test_routes_with_no_providers(self):
        """Router with no providers should return empty routes."""
        from unittest.mock import MagicMock

        from auth.dual_oauth_provider import DualOAuthRouter

        router = DualOAuthRouter(
            google_provider=None,
            github_provider=None,
            settings=MagicMock(),
        )
        routes = router.get_custom_routes()
        # Should have no routes when both providers are None
        assert len(routes) == 0
