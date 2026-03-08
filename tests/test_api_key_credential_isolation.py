"""Tests for API key credential isolation.

Validates that API key sessions cannot inherit OAuth credentials from
other users and can only access credentials they created via start_google_auth.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auth.dual_auth_bridge import DualAuthBridge


@pytest.fixture(autouse=True)
def _reset_dual_auth_bridge():
    """Reset the global DualAuthBridge singleton between tests."""
    import auth.dual_auth_bridge as dab_module

    old = dab_module._dual_auth_bridge
    dab_module._dual_auth_bridge = None
    yield
    dab_module._dual_auth_bridge = old


@pytest.fixture(autouse=True)
def _reset_session_store():
    """Reset the session store between tests."""
    from auth.context import _session_store

    _session_store.clear()
    yield
    _session_store.clear()


@pytest.fixture(autouse=True)
def _reset_account_links():
    """Remove the account links file between tests."""
    from auth.user_api_keys import _links_path

    path = _links_path()
    yield
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# DualAuthBridge: api_key_owned_accounts
# ---------------------------------------------------------------------------


class TestDualAuthBridgeApiKeyAccounts:
    """Test the API key account ownership tracking."""

    def test_register_and_check(self):
        bridge = DualAuthBridge()
        assert not bridge.is_api_key_owned_account("alice@example.com")

        bridge.register_api_key_account("alice@example.com")
        assert bridge.is_api_key_owned_account("alice@example.com")

    def test_case_insensitive(self):
        bridge = DualAuthBridge()
        bridge.register_api_key_account("Alice@Example.COM")
        assert bridge.is_api_key_owned_account("alice@example.com")
        assert bridge.is_api_key_owned_account("ALICE@EXAMPLE.COM")

    def test_unknown_email_rejected(self):
        bridge = DualAuthBridge()
        bridge.register_api_key_account("alice@example.com")
        assert not bridge.is_api_key_owned_account("bob@example.com")

    def test_multiple_accounts(self):
        bridge = DualAuthBridge()
        bridge.register_api_key_account("alice@example.com")
        bridge.register_api_key_account("bob@example.com")
        assert bridge.is_api_key_owned_account("alice@example.com")
        assert bridge.is_api_key_owned_account("bob@example.com")
        assert not bridge.is_api_key_owned_account("eve@example.com")


# ---------------------------------------------------------------------------
# AuthMiddleware: _detect_auth_provenance
# ---------------------------------------------------------------------------


class TestDetectAuthProvenance:
    """Test that API key tokens are correctly identified."""

    def test_api_key_token_detected(self):
        from auth.middleware import AuthMiddleware

        mw = AuthMiddleware()

        mock_token = MagicMock()
        mock_token.claims = {"sub": "api-key-user", "auth_method": "api_key"}

        with (
            patch(
                "auth.middleware.get_access_token", return_value=mock_token, create=True
            ),
            patch(
                "fastmcp.server.dependencies.get_access_token", return_value=mock_token
            ),
        ):
            result = mw._detect_auth_provenance()
        assert result == "api_key"

    def test_oauth_token_not_flagged(self):
        from auth.middleware import AuthMiddleware

        mw = AuthMiddleware()

        mock_token = MagicMock()
        mock_token.claims = {"sub": "12345", "email": "user@example.com"}

        with patch(
            "fastmcp.server.dependencies.get_access_token", return_value=mock_token
        ):
            result = mw._detect_auth_provenance()
        assert result is None

    def test_user_api_key_detected(self):
        """Per-user API keys should return 'user_api_key' provenance."""
        from auth.middleware import AuthMiddleware

        mw = AuthMiddleware()

        mock_token = MagicMock()
        mock_token.claims = {
            "sub": "user@example.com",
            "email": "user@example.com",
            "auth_method": "user_api_key",
        }

        with patch(
            "fastmcp.server.dependencies.get_access_token", return_value=mock_token
        ):
            result = mw._detect_auth_provenance()
        assert result == "user_api_key"

    def test_no_token_returns_none(self):
        from auth.middleware import AuthMiddleware

        mw = AuthMiddleware()

        with patch(
            "fastmcp.server.dependencies.get_access_token",
            side_effect=RuntimeError("no context"),
        ):
            result = mw._detect_auth_provenance()
        assert result is None


# ---------------------------------------------------------------------------
# Integration: credential isolation guard
# ---------------------------------------------------------------------------


class TestCredentialIsolationGuard:
    """Test that the on_call_tool guard blocks unauthorized API key access."""

    @pytest.mark.asyncio
    async def test_api_key_blocked_for_unowned_email(self):
        """API key session should be blocked from using another user's credentials."""
        from auth.middleware import AuthMiddleware

        mw = AuthMiddleware()

        # Simulate: API key session, email resolved from tool args, not owned
        mock_context = MagicMock()
        mock_context.message.name = "search_drive_files"
        mock_context.message.arguments = {"user_google_email": "victim@example.com"}

        mock_call_next = AsyncMock()

        # Patch the extraction chain so:
        # - _detect_auth_provenance returns "api_key"
        # - _extract_user_from_jwt_token returns None (API key has no email)
        # - _extract_user_from_google_provider returns None
        # - _extract_user_email returns "victim@example.com" (from tool args)
        # - _load_oauth_authentication_data is never called (blocked)
        with (
            patch.object(mw, "_detect_auth_provenance", return_value="api_key"),
            patch.object(mw, "_extract_user_from_jwt_token", return_value=None),
            patch.object(
                mw,
                "_extract_user_from_google_provider",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(mw, "_extract_user_email", return_value="victim@example.com"),
            patch.object(mw, "_load_oauth_authentication_data", return_value=None),
            patch("auth.audit.log_security_event") as mock_audit,
        ):
            with pytest.raises(ValueError, match="API key sessions can only access"):
                await mw.on_call_tool(mock_context, mock_call_next)

            # Verify the security event was logged
            mock_audit.assert_called_once()
            assert mock_audit.call_args[0][0] == "api_key_credential_access_blocked"

        # call_next should NOT have been reached
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_key_allowed_for_owned_email(self):
        """API key session should be allowed for credentials it created."""
        from auth.middleware import AuthMiddleware

        mw = AuthMiddleware()
        # Pre-register the email as API-key-owned
        mw._dual_auth_bridge.register_api_key_account("myemail@example.com")

        mock_context = MagicMock()
        mock_context.message.name = "search_drive_files"
        mock_context.message.arguments = {"user_google_email": "myemail@example.com"}

        mock_call_next = AsyncMock(return_value="success")

        with (
            patch.object(mw, "_detect_auth_provenance", return_value="api_key"),
            patch.object(mw, "_extract_user_from_jwt_token", return_value=None),
            patch.object(
                mw,
                "_extract_user_from_google_provider",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(mw, "_extract_user_email", return_value="myemail@example.com"),
            patch.object(mw, "_load_oauth_authentication_data", return_value=None),
            patch.object(mw, "_bridge_credentials_if_needed", new_callable=AsyncMock),
            patch.object(mw, "_inject_services", new_callable=AsyncMock),
        ):
            result = await mw.on_call_tool(mock_context, mock_call_next)

        mock_call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_api_key_start_google_auth_registers_email(self):
        """start_google_auth should register the email as API-key-owned."""
        from auth.middleware import AuthMiddleware

        mw = AuthMiddleware()

        mock_context = MagicMock()
        mock_context.message.name = "start_google_auth"
        mock_context.message.arguments = {"user_google_email": "newuser@example.com"}

        mock_call_next = AsyncMock(return_value="auth started")

        with (
            patch.object(mw, "_detect_auth_provenance", return_value="api_key"),
            patch.object(mw, "_extract_user_from_jwt_token", return_value=None),
            patch.object(
                mw,
                "_extract_user_from_google_provider",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(mw, "_extract_user_email", return_value="newuser@example.com"),
            patch.object(mw, "_load_oauth_authentication_data", return_value=None),
            patch.object(mw, "_bridge_credentials_if_needed", new_callable=AsyncMock),
            patch.object(mw, "_inject_services", new_callable=AsyncMock),
        ):
            await mw.on_call_tool(mock_context, mock_call_next)

        # Email should now be registered as API-key-owned
        assert mw._dual_auth_bridge.is_api_key_owned_account("newuser@example.com")

        # Subsequent tool calls with this email should be allowed
        mock_context.message.name = "search_drive_files"
        with (
            patch.object(mw, "_detect_auth_provenance", return_value="api_key"),
            patch.object(mw, "_extract_user_from_jwt_token", return_value=None),
            patch.object(
                mw,
                "_extract_user_from_google_provider",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(mw, "_extract_user_email", return_value="newuser@example.com"),
            patch.object(mw, "_load_oauth_authentication_data", return_value=None),
            patch.object(mw, "_bridge_credentials_if_needed", new_callable=AsyncMock),
            patch.object(mw, "_inject_services", new_callable=AsyncMock),
        ):
            await mw.on_call_tool(mock_context, mock_call_next)

        # Should have been called (not blocked)
        assert mock_call_next.call_count == 2

    @pytest.mark.asyncio
    async def test_oauth_user_unaffected(self):
        """OAuth-authenticated users should not be affected by the guard."""
        from auth.middleware import AuthMiddleware

        mw = AuthMiddleware()

        mock_context = MagicMock()
        mock_context.message.name = "search_drive_files"
        mock_context.message.arguments = {"user_google_email": "oauth_user@example.com"}

        mock_call_next = AsyncMock(return_value="success")

        # OAuth user: provenance is None (not api_key)
        with (
            patch.object(mw, "_detect_auth_provenance", return_value=None),
            patch.object(
                mw,
                "_extract_user_from_jwt_token",
                return_value="oauth_user@example.com",
            ),
            patch.object(mw, "_bridge_credentials_if_needed", new_callable=AsyncMock),
            patch.object(mw, "_inject_services", new_callable=AsyncMock),
        ):
            await mw.on_call_tool(mock_context, mock_call_next)

        # Should succeed without any API key checks
        mock_call_next.assert_called_once()


# ---------------------------------------------------------------------------
# OAuth file fallback blocked for API key sessions
# ---------------------------------------------------------------------------


class TestOAuthFileFallbackBlocked:
    """Test that _load_oauth_authentication_data is skipped for API key sessions."""

    @pytest.mark.asyncio
    async def test_oauth_file_fallback_skipped_for_api_key(self):
        """API key session should NOT inherit email from OAuth file."""
        from auth.middleware import AuthMiddleware

        mw = AuthMiddleware()

        mock_context = MagicMock()
        mock_context.message.name = "list_drive_files"
        mock_context.message.arguments = {}

        mock_call_next = AsyncMock(return_value="ok")

        # API key session with no email resolved anywhere
        with (
            patch.object(mw, "_detect_auth_provenance", return_value="api_key"),
            patch.object(mw, "_extract_user_from_jwt_token", return_value=None),
            patch.object(
                mw,
                "_extract_user_from_google_provider",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(mw, "_extract_user_email", return_value=None),
            patch.object(mw, "_load_oauth_authentication_data") as mock_load,
            patch.object(mw, "_inject_services", new_callable=AsyncMock),
        ):
            # Should not raise — just proceed with no user email
            await mw.on_call_tool(mock_context, mock_call_next)

            # The OAuth file fallback should NOT have been called
            mock_load.assert_not_called()

    @pytest.mark.asyncio
    async def test_oauth_file_fallback_skipped_for_user_api_key(self):
        """Per-user API key session should NOT inherit email from OAuth file."""
        from auth.middleware import AuthMiddleware

        mw = AuthMiddleware()

        mock_context = MagicMock()
        mock_context.message.name = "list_drive_files"
        mock_context.message.arguments = {}

        mock_call_next = AsyncMock(return_value="ok")

        with (
            patch.object(mw, "_detect_auth_provenance", return_value="user_api_key"),
            patch.object(
                mw, "_extract_user_from_jwt_token", return_value="keyowner@example.com"
            ),
            patch.object(mw, "_load_oauth_authentication_data") as mock_load,
            patch.object(mw, "_bridge_credentials_if_needed", new_callable=AsyncMock),
            patch.object(mw, "_inject_services", new_callable=AsyncMock),
        ):
            await mw.on_call_tool(mock_context, mock_call_next)
            mock_load.assert_not_called()


# ---------------------------------------------------------------------------
# Account linking (per-user API keys)
# ---------------------------------------------------------------------------


class TestAccountLinking:
    """Test the per-user API key account linking feature."""

    def test_link_and_get_accessible(self):
        from auth.user_api_keys import get_accessible_emails, link_accounts

        link_accounts("alice@example.com", "bob@example.com")
        alice_access = get_accessible_emails("alice@example.com")
        bob_access = get_accessible_emails("bob@example.com")

        assert "alice@example.com" in alice_access
        assert "bob@example.com" in alice_access
        assert "alice@example.com" in bob_access
        assert "bob@example.com" in bob_access

    def test_unlinked_email_not_accessible(self):
        from auth.user_api_keys import get_accessible_emails, link_accounts

        link_accounts("alice@example.com", "bob@example.com")
        eve_access = get_accessible_emails("eve@example.com")
        assert eve_access == {"eve@example.com"}

    def test_self_link_noop(self):
        from auth.user_api_keys import get_accessible_emails, link_accounts

        link_accounts("alice@example.com", "alice@example.com")
        assert get_accessible_emails("alice@example.com") == {"alice@example.com"}

    def test_unlink(self):
        from auth.user_api_keys import (
            get_accessible_emails,
            link_accounts,
            unlink_accounts,
        )

        link_accounts("alice@example.com", "bob@example.com")
        assert "bob@example.com" in get_accessible_emails("alice@example.com")

        unlink_accounts("alice@example.com", "bob@example.com")
        assert get_accessible_emails("alice@example.com") == {"alice@example.com"}
        assert get_accessible_emails("bob@example.com") == {"bob@example.com"}

    def test_multiple_links(self):
        from auth.user_api_keys import get_accessible_emails, link_accounts

        link_accounts("alice@example.com", "bob@example.com")
        link_accounts("alice@example.com", "charlie@example.com")
        alice_access = get_accessible_emails("alice@example.com")

        assert alice_access == {
            "alice@example.com",
            "bob@example.com",
            "charlie@example.com",
        }
        # bob only has alice (not charlie — links are NOT transitive)
        assert get_accessible_emails("bob@example.com") == {
            "bob@example.com",
            "alice@example.com",
        }

    def test_case_insensitive(self):
        from auth.user_api_keys import get_accessible_emails, link_accounts

        link_accounts("Alice@Example.COM", "bob@example.com")
        assert "bob@example.com" in get_accessible_emails("alice@example.com")


class TestPerUserKeyCredentialGuard:
    """Test that per-user API key sessions enforce account access boundaries."""

    @pytest.mark.asyncio
    async def test_user_key_blocked_for_unlinked_email(self):
        """Per-user key should be blocked from accessing an unlinked account."""
        from auth.middleware import AuthMiddleware

        mw = AuthMiddleware()

        mock_context = MagicMock()
        mock_context.message.name = "search_drive_files"
        mock_context.message.arguments = {"user_google_email": "stranger@example.com"}

        mock_call_next = AsyncMock()

        with (
            patch.object(mw, "_detect_auth_provenance", return_value="user_api_key"),
            patch.object(
                mw, "_extract_user_from_jwt_token", return_value="keyowner@example.com"
            ),
            patch.object(
                mw,
                "_extract_user_from_google_provider",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(mw, "_extract_user_email", return_value=None),
            patch.object(mw, "_load_oauth_authentication_data", return_value=None),
            patch.object(mw, "_auto_inject_email_parameter", new_callable=AsyncMock),
            patch("auth.audit.log_security_event"),
        ):
            with pytest.raises(ValueError, match="does not have access to"):
                await mw.on_call_tool(mock_context, mock_call_next)

        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_user_key_allowed_for_own_email(self):
        """Per-user key should access its own bound email."""
        from auth.middleware import AuthMiddleware

        mw = AuthMiddleware()

        mock_context = MagicMock()
        mock_context.message.name = "search_drive_files"
        mock_context.message.arguments = {"user_google_email": "keyowner@example.com"}

        mock_call_next = AsyncMock(return_value="ok")

        with (
            patch.object(mw, "_detect_auth_provenance", return_value="user_api_key"),
            patch.object(
                mw, "_extract_user_from_jwt_token", return_value="keyowner@example.com"
            ),
            patch.object(
                mw,
                "_extract_user_from_google_provider",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                mw, "_extract_user_email", return_value="keyowner@example.com"
            ),
            patch.object(mw, "_load_oauth_authentication_data", return_value=None),
            patch.object(mw, "_bridge_credentials_if_needed", new_callable=AsyncMock),
            patch.object(mw, "_inject_services", new_callable=AsyncMock),
        ):
            await mw.on_call_tool(mock_context, mock_call_next)

        mock_call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_user_key_start_auth_links_accounts(self):
        """start_google_auth via per-user key should link the new email."""
        from auth.middleware import AuthMiddleware
        from auth.user_api_keys import get_accessible_emails

        mw = AuthMiddleware()

        mock_context = MagicMock()
        mock_context.message.name = "start_google_auth"
        mock_context.message.arguments = {"user_google_email": "second@example.com"}

        mock_call_next = AsyncMock(return_value="auth started")

        with (
            patch.object(mw, "_detect_auth_provenance", return_value="user_api_key"),
            patch.object(
                mw, "_extract_user_from_jwt_token", return_value="keyowner@example.com"
            ),
            patch.object(
                mw,
                "_extract_user_from_google_provider",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(mw, "_extract_user_email", return_value=None),
            patch.object(mw, "_load_oauth_authentication_data", return_value=None),
            patch.object(mw, "_auto_inject_email_parameter", new_callable=AsyncMock),
            patch.object(mw, "_bridge_credentials_if_needed", new_callable=AsyncMock),
            patch.object(mw, "_inject_services", new_callable=AsyncMock),
        ):
            await mw.on_call_tool(mock_context, mock_call_next)

        # Accounts should now be linked
        assert "second@example.com" in get_accessible_emails("keyowner@example.com")
        assert "keyowner@example.com" in get_accessible_emails("second@example.com")

        # Subsequent access to second@example.com should be allowed
        mock_context.message.name = "search_drive_files"
        mock_context.message.arguments = {"user_google_email": "second@example.com"}
        with (
            patch.object(mw, "_detect_auth_provenance", return_value="user_api_key"),
            patch.object(
                mw, "_extract_user_from_jwt_token", return_value="keyowner@example.com"
            ),
            patch.object(
                mw,
                "_extract_user_from_google_provider",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(mw, "_extract_user_email", return_value=None),
            patch.object(mw, "_load_oauth_authentication_data", return_value=None),
            patch.object(mw, "_auto_inject_email_parameter", new_callable=AsyncMock),
            patch.object(mw, "_bridge_credentials_if_needed", new_callable=AsyncMock),
            patch.object(mw, "_inject_services", new_callable=AsyncMock),
        ):
            await mw.on_call_tool(mock_context, mock_call_next)

        assert mock_call_next.call_count == 2
