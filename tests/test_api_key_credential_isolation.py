"""Tests for API key credential isolation and crypto-bound encryption.

Validates that API key sessions cannot inherit OAuth credentials from
other users and can only access credentials they created via start_google_auth.

Also validates that credential encryption is derived from MCP_API_KEY when
set, creating a cryptographic binding between the API secret and stored
credentials.
"""

import base64
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auth.dual_auth_bridge import DualAuthBridge
from auth.types import AuthProvenance


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
    """Remove the account links and pending links files between tests."""
    from auth.user_api_keys import _links_path, _pending_links_path

    yield
    for path in [_links_path(), _pending_links_path()]:
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
        mock_token.claims = {
            "sub": "api-key-user",
            "auth_method": AuthProvenance.API_KEY,
        }

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
            "auth_method": AuthProvenance.USER_API_KEY,
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
        """API key session should be blocked from using another user's credentials.

        The shared API key has no email claim, so user_email is None.
        The guard reads user_google_email from tool arguments directly.
        """
        from auth.middleware import AuthMiddleware

        mw = AuthMiddleware()

        mock_context = MagicMock()
        mock_context.message.name = "search_drive_files"
        mock_context.message.arguments = {"user_google_email": "victim@example.com"}

        mock_call_next = AsyncMock()

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
            patch.object(mw, "_load_oauth_authentication_data", return_value=None),
            patch("auth.audit.log_security_event") as mock_audit,
        ):
            with pytest.raises(ValueError, match="API key sessions can only access"):
                await mw.on_call_tool(mock_context, mock_call_next)

            mock_audit.assert_called_once()
            assert mock_audit.call_args[0][0] == "api_key_credential_access_blocked"

        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_key_allowed_for_owned_email(self):
        """API key session should be allowed for credentials it created via start_google_auth.

        Ownership is tracked per-session (stored in session data), not globally.
        """
        from auth.middleware import AuthMiddleware

        mw = AuthMiddleware()

        mock_context = MagicMock()
        mock_call_next = AsyncMock(return_value="success")

        # Step 1: Call start_google_auth to register ownership
        mock_context.message.name = "start_google_auth"
        mock_context.message.arguments = {"user_google_email": "myemail@example.com"}

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
            patch.object(mw, "_load_oauth_authentication_data", return_value=None),
            patch.object(mw, "_bridge_credentials_if_needed", new_callable=AsyncMock),
            patch.object(mw, "_inject_services", new_callable=AsyncMock),
        ):
            await mw.on_call_tool(mock_context, mock_call_next)

        # Step 2: Now access the same email — should be allowed
        mock_context.message.name = "search_drive_files"
        mock_context.message.arguments = {"user_google_email": "myemail@example.com"}

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
            patch.object(mw, "_load_oauth_authentication_data", return_value=None),
            patch.object(mw, "_bridge_credentials_if_needed", new_callable=AsyncMock),
            patch.object(mw, "_inject_services", new_callable=AsyncMock),
        ):
            await mw.on_call_tool(mock_context, mock_call_next)

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
    async def test_session_level_linking_creates_pending_link(self):
        """Two start_google_auth calls in the same session should create a pending link.

        The link is deferred — only activated when the second OAuth completes
        (via consume_pending_links).  This works for ANY auth type, not just
        per-user key sessions.
        """
        from auth.middleware import AuthMiddleware
        from auth.user_api_keys import (
            consume_pending_links,
            get_accessible_emails,
        )

        mw = AuthMiddleware()

        mock_context = MagicMock()
        mock_call_next = AsyncMock(return_value="auth started")

        common_patches = {
            "_detect_auth_provenance": patch.object(
                mw, "_detect_auth_provenance", return_value="user_api_key"
            ),
            "_extract_jwt": patch.object(
                mw, "_extract_user_from_jwt_token", return_value="keyowner@example.com"
            ),
            "_extract_gp": patch.object(
                mw,
                "_extract_user_from_google_provider",
                new_callable=AsyncMock,
                return_value=None,
            ),
            "_extract_email": patch.object(
                mw, "_extract_user_email", return_value=None
            ),
            "_load_oauth": patch.object(
                mw, "_load_oauth_authentication_data", return_value=None
            ),
            "_auto_inject": patch.object(
                mw, "_auto_inject_email_parameter", new_callable=AsyncMock
            ),
            "_bridge": patch.object(
                mw, "_bridge_credentials_if_needed", new_callable=AsyncMock
            ),
            "_inject": patch.object(mw, "_inject_services", new_callable=AsyncMock),
        }

        # Step 1: First start_google_auth — records keyowner in session
        mock_context.message.name = "start_google_auth"
        mock_context.message.arguments = {"user_google_email": "keyowner@example.com"}

        with (
            common_patches["_detect_auth_provenance"],
            common_patches["_extract_jwt"],
            common_patches["_extract_gp"],
            common_patches["_extract_email"],
            common_patches["_load_oauth"],
            common_patches["_auto_inject"],
            common_patches["_bridge"],
            common_patches["_inject"],
        ):
            await mw.on_call_tool(mock_context, mock_call_next)

        # Step 2: Second start_google_auth — creates pending link
        mock_context.message.name = "start_google_auth"
        mock_context.message.arguments = {"user_google_email": "second@example.com"}

        with (
            common_patches["_detect_auth_provenance"],
            common_patches["_extract_jwt"],
            common_patches["_extract_gp"],
            common_patches["_extract_email"],
            common_patches["_load_oauth"],
            common_patches["_auto_inject"],
            common_patches["_bridge"],
            common_patches["_inject"],
        ):
            await mw.on_call_tool(mock_context, mock_call_next)

        # Link should NOT be active yet (deferred until OAuth completes)
        assert "second@example.com" not in get_accessible_emails("keyowner@example.com")

        # Simulate OAuth completion — this is what _save_credentials calls
        consume_pending_links("second@example.com")

        # NOW accounts should be linked
        assert "second@example.com" in get_accessible_emails("keyowner@example.com")
        assert "keyowner@example.com" in get_accessible_emails("second@example.com")

        # Step 3: Subsequent access to second@example.com should be allowed
        mock_context.message.name = "search_drive_files"
        mock_context.message.arguments = {"user_google_email": "second@example.com"}
        with (
            common_patches["_detect_auth_provenance"],
            common_patches["_extract_jwt"],
            common_patches["_extract_gp"],
            common_patches["_extract_email"],
            common_patches["_load_oauth"],
            common_patches["_auto_inject"],
            common_patches["_bridge"],
            common_patches["_inject"],
        ):
            await mw.on_call_tool(mock_context, mock_call_next)

        assert mock_call_next.call_count == 3


# ---------------------------------------------------------------------------
# Crypto-binding: MCP_API_KEY-derived encryption
# ---------------------------------------------------------------------------


class TestCryptoBinding:
    """Test that credential encryption is derived from MCP_API_KEY."""

    def test_derive_fernet_key_deterministic(self):
        """Same secret should always produce the same derived key."""
        from auth.middleware import AuthMiddleware

        key1 = AuthMiddleware._derive_fernet_key("test-secret-key-123")
        key2 = AuthMiddleware._derive_fernet_key("test-secret-key-123")
        assert key1 == key2

    def test_derive_fernet_key_different_secrets(self):
        """Different secrets should produce different derived keys."""
        from auth.middleware import AuthMiddleware

        key1 = AuthMiddleware._derive_fernet_key("secret-a")
        key2 = AuthMiddleware._derive_fernet_key("secret-b")
        assert key1 != key2

    def test_derive_fernet_key_valid_for_fernet(self):
        """Derived key should be a valid Fernet key (32 bytes, base64url-encoded)."""
        from auth.middleware import AuthMiddleware

        key = AuthMiddleware._derive_fernet_key("my-api-key")
        raw = base64.urlsafe_b64decode(key)
        assert len(raw) == 32

    def test_setup_encryption_uses_mcp_api_key(self):
        """When MCP_API_KEY is set, encryption key should be derived from it."""
        from auth.middleware import AuthMiddleware

        with patch.dict(os.environ, {"MCP_API_KEY": "test-api-key-for-encryption"}):
            mw = AuthMiddleware()

        assert mw._key_source == "mcp_api_key"
        expected_key = AuthMiddleware._derive_fernet_key("test-api-key-for-encryption")
        from cryptography.fernet import Fernet

        expected_fernet = Fernet(expected_key)
        test_data = b"test credential data"
        encrypted = mw._fernet.encrypt(test_data)
        assert expected_fernet.decrypt(encrypted) == test_data

    def test_setup_encryption_falls_back_to_server_key(self, tmp_path):
        """When MCP_API_KEY is not set, should fall back to server-generated key."""
        from auth.middleware import AuthMiddleware

        with (
            patch.dict(os.environ, {}, clear=False),
            patch("auth.middleware.settings") as mock_settings,
        ):
            os.environ.pop("MCP_API_KEY", None)
            mock_settings.credentials_dir = str(tmp_path)
            mock_settings.credential_storage_mode = "FILE_ENCRYPTED"
            mock_settings.enable_unified_auth = False
            mock_settings.drive_scopes = []
            mw = AuthMiddleware()

        assert mw._key_source == "server_key"
        assert (tmp_path / ".auth_encryption_key").exists()

    def test_encrypt_decrypt_round_trip_with_derived_key(self):
        """Credentials encrypted with MCP_API_KEY-derived key should decrypt correctly."""
        from auth.middleware import AuthMiddleware

        with patch.dict(os.environ, {"MCP_API_KEY": "round-trip-test-key"}):
            mw = AuthMiddleware()

        mock_creds = MagicMock()
        mock_creds.token = "access-token-123"
        mock_creds.refresh_token = "refresh-token-456"
        mock_creds.token_uri = "https://oauth2.googleapis.com/token"
        mock_creds.client_id = "client-id"
        mock_creds.client_secret = "client-secret"
        mock_creds.scopes = ["https://www.googleapis.com/auth/drive"]
        mock_creds.expiry = None

        encrypted = mw._encrypt_credentials(mock_creds)
        decrypted = mw._decrypt_credentials(encrypted)

        assert decrypted.token == "access-token-123"
        assert decrypted.refresh_token == "refresh-token-456"

    def test_wrong_api_key_cannot_decrypt(self):
        """Credentials encrypted with one MCP_API_KEY should not be decryptable with another."""
        from cryptography.fernet import InvalidToken

        from auth.middleware import AuthMiddleware

        with patch.dict(os.environ, {"MCP_API_KEY": "key-alpha"}):
            mw_a = AuthMiddleware()

        mock_creds = MagicMock()
        mock_creds.token = "secret-token"
        mock_creds.refresh_token = "secret-refresh"
        mock_creds.token_uri = "https://oauth2.googleapis.com/token"
        mock_creds.client_id = "cid"
        mock_creds.client_secret = "cs"
        mock_creds.scopes = []
        mock_creds.expiry = None

        encrypted = mw_a._encrypt_credentials(mock_creds)

        with patch.dict(os.environ, {"MCP_API_KEY": "key-beta"}):
            mw_b = AuthMiddleware()

        if hasattr(mw_b, "_legacy_fernet"):
            del mw_b._legacy_fernet

        with pytest.raises((InvalidToken, Exception)):
            mw_b._decrypt_credentials(encrypted)

    def test_legacy_key_migration(self, tmp_path):
        """Credentials encrypted with old server key should still decrypt after switching to MCP_API_KEY."""
        from auth.middleware import AuthMiddleware

        # Step 1: Encrypt with server key (no MCP_API_KEY)
        with (
            patch.dict(os.environ, {}, clear=False),
            patch("auth.middleware.settings") as mock_settings,
        ):
            os.environ.pop("MCP_API_KEY", None)
            mock_settings.credentials_dir = str(tmp_path)
            mock_settings.credential_storage_mode = "FILE_ENCRYPTED"
            mock_settings.enable_unified_auth = False
            mock_settings.drive_scopes = []
            mw_old = AuthMiddleware()

        assert mw_old._key_source == "server_key"

        mock_creds = MagicMock()
        mock_creds.token = "legacy-token"
        mock_creds.refresh_token = "legacy-refresh"
        mock_creds.token_uri = "https://oauth2.googleapis.com/token"
        mock_creds.client_id = "cid"
        mock_creds.client_secret = "cs"
        mock_creds.scopes = []
        mock_creds.expiry = None

        encrypted_with_server_key = mw_old._encrypt_credentials(mock_creds)

        # Step 2: Switch to MCP_API_KEY — old .auth_encryption_key still exists
        with (
            patch.dict(os.environ, {"MCP_API_KEY": "new-derived-key"}),
            patch("auth.middleware.settings") as mock_settings,
        ):
            mock_settings.credentials_dir = str(tmp_path)
            mock_settings.credential_storage_mode = "FILE_ENCRYPTED"
            mock_settings.enable_unified_auth = False
            mock_settings.drive_scopes = []
            mw_new = AuthMiddleware()

        assert mw_new._key_source == "mcp_api_key"
        assert hasattr(mw_new, "_legacy_fernet")

        decrypted = mw_new._decrypt_credentials(encrypted_with_server_key)
        assert decrypted.token == "legacy-token"
        assert decrypted.refresh_token == "legacy-refresh"
