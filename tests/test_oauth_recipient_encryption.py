"""Tests for OAuth recipient encryption, user API key management, and cross-account linkage.

Covers:
- User API key generation, lookup, and revocation
- Key link window timing
- OAuth linkage preferences (enable/disable, passwords, google_sub)
- Pending link requests and consumption
- OAuth recipient key derivation (deterministic, password-sensitive)
- _resolve_oauth_recipient_key (respects linkage prefs)
- _try_decrypt_with_keys (primary + fallback key cascade)
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from auth.middleware import AuthMiddleware
from auth.user_api_keys import (
    consume_pending_links,
    generate_user_key,
    get_oauth_linkage,
    is_key_within_link_window,
    lookup_key,
    request_link,
    revoke_user_key,
    set_oauth_linkage,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_credentials_dir(tmp_path, monkeypatch):
    """Redirect all credential storage to a temp directory."""
    monkeypatch.setattr("config.settings.settings.credentials_dir", str(tmp_path))
    yield tmp_path


@pytest.fixture(autouse=True)
def _reset_registry(tmp_path):
    """Ensure no stale JSON files between tests (tmp_path is unique per test)."""
    yield


@pytest.fixture()
def auth_mw(tmp_path, monkeypatch):
    """AuthMiddleware with server-generated encryption key (no MCP_API_KEY)."""
    monkeypatch.delenv("MCP_API_KEY", raising=False)
    with patch("auth.middleware.settings") as mock_settings:
        mock_settings.credentials_dir = str(tmp_path)
        mock_settings.credential_storage_mode = "FILE_ENCRYPTED"
        mock_settings.enable_unified_auth = False
        mock_settings.drive_scopes = []
        mw = AuthMiddleware()
    # Re-patch settings for methods called after __init__ (e.g. _get_server_secret)
    monkeypatch.setattr("auth.middleware.settings.credentials_dir", str(tmp_path))
    return mw


# ===========================================================================
# TestUserApiKeyGeneration
# ===========================================================================


class TestUserApiKeyGeneration:
    def test_generate_returns_key(self):
        key = generate_user_key("alice@example.com")
        assert key is not None
        assert isinstance(key, str)
        assert len(key) > 10

    def test_generate_idempotent_without_force(self):
        generate_user_key("alice@example.com")
        second = generate_user_key("alice@example.com")
        assert second is None

    def test_generate_force_replaces(self):
        first = generate_user_key("alice@example.com")
        second = generate_user_key("alice@example.com", force=True)
        assert second is not None
        assert second != first
        # Old key should no longer resolve
        assert lookup_key(first) is None
        assert lookup_key(second) == "alice@example.com"

    def test_lookup_returns_email(self):
        key = generate_user_key("bob@example.com")
        assert lookup_key(key) == "bob@example.com"

    def test_lookup_wrong_key_returns_none(self):
        generate_user_key("alice@example.com")
        assert lookup_key("totally-bogus-token") is None

    def test_revoke_removes_key(self):
        key = generate_user_key("alice@example.com")
        assert revoke_user_key("alice@example.com") is True
        assert lookup_key(key) is None

    def test_revoke_nonexistent_returns_false(self):
        assert revoke_user_key("nobody@example.com") is False


# ===========================================================================
# TestKeyLinkWindow
# ===========================================================================


class TestKeyLinkWindow:
    def test_fresh_key_within_window(self):
        generate_user_key("alice@example.com")
        assert is_key_within_link_window("alice@example.com") is True

    def test_expired_key_outside_window(self, monkeypatch):
        generate_user_key("alice@example.com")
        import auth.user_api_keys as uak

        monkeypatch.setattr(uak, "_API_KEY_LINK_WINDOW_MINUTES", 0)
        assert is_key_within_link_window("alice@example.com") is False

    def test_legacy_entry_without_timestamp(self, _isolated_credentials_dir):
        """A plain-string registry entry (legacy) should be treated as outside window."""
        import auth.user_api_keys as uak

        key = "fake-legacy-key"
        key_hash = uak._hash_key(key)
        registry = {key_hash: "legacy@example.com"}  # legacy format: just email string
        uak._save_registry(registry)
        assert is_key_within_link_window("legacy@example.com") is False

    def test_nonexistent_email_returns_false(self):
        assert is_key_within_link_window("ghost@example.com") is False


# ===========================================================================
# TestOAuthLinkagePrefs
# ===========================================================================


class TestOAuthLinkagePrefs:
    def test_default_is_enabled(self):
        result = get_oauth_linkage("new@example.com")
        assert result["enabled"] is True
        assert result["has_password"] is False
        assert result["google_sub"] == ""

    def test_set_and_get_round_trip(self):
        set_oauth_linkage("alice@example.com", enabled=True, google_sub="12345")
        result = get_oauth_linkage("alice@example.com")
        assert result["enabled"] is True
        assert result["google_sub"] == "12345"

    def test_disable_linkage(self):
        set_oauth_linkage("alice@example.com", enabled=False)
        result = get_oauth_linkage("alice@example.com")
        assert result["enabled"] is False

    def test_password_sets_flag(self):
        set_oauth_linkage("alice@example.com", password="test123")
        result = get_oauth_linkage("alice@example.com")
        assert result["has_password"] is True

    def test_invalid_password_raises(self):
        with pytest.raises(ValueError, match="Password may only contain"):
            set_oauth_linkage("alice@example.com", password="bad chars!@#")

    def test_google_sub_preserved_on_update(self):
        set_oauth_linkage("alice@example.com", google_sub="sub-999")
        # Re-set without google_sub — should preserve existing
        set_oauth_linkage("alice@example.com", enabled=True)
        result = get_oauth_linkage("alice@example.com")
        assert result["google_sub"] == "sub-999"


# ===========================================================================
# TestRequestAndConsumePendingLinks
# ===========================================================================


class TestRequestAndConsumePendingLinks:
    def test_request_creates_pending(self, _isolated_credentials_dir):
        request_link("source@example.com", "target@example.com")
        from auth.user_api_keys import _load_pending_links

        pending = _load_pending_links()
        assert "target@example.com" in pending

    def test_self_link_noop(self, _isolated_credentials_dir):
        request_link("same@example.com", "same@example.com")
        from auth.user_api_keys import _load_pending_links

        pending = _load_pending_links()
        assert "same@example.com" not in pending

    def test_consume_activates_link(self):
        """With a registered source key, consuming pending links activates the link."""
        generate_user_key("source@example.com")
        request_link("source@example.com", "target@example.com")
        consume_pending_links("target@example.com")

        from auth.user_api_keys import get_accessible_emails

        assert "target@example.com" in get_accessible_emails("source@example.com")
        assert "source@example.com" in get_accessible_emails("target@example.com")

    def test_consume_without_source_key_skips(self):
        """Without a registered source key, pending link is NOT activated."""
        request_link("unregistered@example.com", "target@example.com")
        consume_pending_links("target@example.com")

        from auth.user_api_keys import get_accessible_emails

        assert "unregistered@example.com" not in get_accessible_emails(
            "target@example.com"
        )

    def test_consume_clears_pending(self, _isolated_credentials_dir):
        generate_user_key("source@example.com")
        request_link("source@example.com", "target@example.com")
        consume_pending_links("target@example.com")

        from auth.user_api_keys import _load_pending_links

        pending = _load_pending_links()
        assert "target@example.com" not in pending


# ===========================================================================
# TestDeriveOAuthRecipientKey
# ===========================================================================


class TestDeriveOAuthRecipientKey:
    def test_deterministic(self, auth_mw):
        k1 = auth_mw._derive_oauth_recipient_key("sub-123")
        k2 = auth_mw._derive_oauth_recipient_key("sub-123")
        assert k1 == k2

    def test_different_subs_different_keys(self, auth_mw):
        k1 = auth_mw._derive_oauth_recipient_key("sub-AAA")
        k2 = auth_mw._derive_oauth_recipient_key("sub-BBB")
        assert k1 != k2

    def test_password_changes_key(self, auth_mw):
        k_no_pw = auth_mw._derive_oauth_recipient_key("sub-123")
        k_with_pw = auth_mw._derive_oauth_recipient_key("sub-123", password="secret")
        assert k_no_pw != k_with_pw

    def test_different_passwords_different_keys(self, auth_mw):
        k_alpha = auth_mw._derive_oauth_recipient_key("sub-123", password="alpha")
        k_beta = auth_mw._derive_oauth_recipient_key("sub-123", password="beta")
        assert k_alpha != k_beta

    def test_returns_hex_64_chars(self, auth_mw):
        key = auth_mw._derive_oauth_recipient_key("sub-123")
        assert len(key) == 64
        int(key, 16)  # should not raise — valid hex


# ===========================================================================
# TestResolveOAuthRecipientKey
# ===========================================================================


class TestResolveOAuthRecipientKey:
    def test_returns_none_when_no_sub(self, auth_mw):
        assert auth_mw._resolve_oauth_recipient_key(None, "a@example.com") is None

    def test_returns_key_when_linkage_enabled(self, auth_mw):
        set_oauth_linkage("alice@example.com", enabled=True, google_sub="sub-1")
        key = auth_mw._resolve_oauth_recipient_key("sub-1", "alice@example.com")
        assert key is not None
        assert isinstance(key, str)

    def test_returns_none_when_disabled(self, auth_mw):
        set_oauth_linkage("alice@example.com", enabled=False)
        key = auth_mw._resolve_oauth_recipient_key("sub-1", "alice@example.com")
        assert key is None


# ===========================================================================
# TestTryDecryptWithKeys
# ===========================================================================


class TestTryDecryptWithKeys:
    """Round-trip tests using the real multi-recipient envelope format.

    Uses _save_per_user_encrypted to write proper {v:2, enc:"per_user", recipients:{...}}
    envelopes so _try_decrypt_with_keys exercises the real CEK-unwrap path.
    """

    @staticmethod
    def _mock_credentials():
        from google.oauth2.credentials import Credentials

        return Credentials(
            token="test-token",
            refresh_token="test-refresh",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="cid",
            client_secret="cs",
        )

    def test_decrypt_with_per_user_key(self, auth_mw, tmp_path):
        """Primary per-user key can decrypt its own envelope."""
        cred_file = tmp_path / "cred.enc"
        auth_mw._save_per_user_encrypted(
            cred_file, self._mock_credentials(), per_user_key="my-key"
        )
        result = auth_mw._try_decrypt_with_keys(
            cred_file,
            per_user_key="my-key",
            google_sub=None,
            normalized_email="alice@example.com",
        )
        assert result is not None
        assert result.token == "test-token"
        assert result.refresh_token == "test-refresh"

    def test_fallback_to_oauth_key(self, auth_mw, tmp_path):
        """OAuth recipient key decrypts when per_user_key is absent."""
        oauth_key = auth_mw._derive_oauth_recipient_key("sub-X")
        cred_file = tmp_path / "cred.enc"
        # Save with a primary key + OAuth recipient as additional
        auth_mw._save_per_user_encrypted(
            cred_file,
            self._mock_credentials(),
            per_user_key="owner-key",
            additional_keys=[oauth_key],
        )

        set_oauth_linkage("alice@example.com", enabled=True, google_sub="sub-X")

        # Try decrypt WITHOUT the owner key — should fall back to OAuth recipient
        result = auth_mw._try_decrypt_with_keys(
            cred_file,
            per_user_key=None,
            google_sub="sub-X",
            normalized_email="alice@example.com",
        )
        assert result is not None
        assert result.token == "test-token"

    def test_all_keys_fail_returns_none(self, auth_mw, tmp_path):
        """Wrong keys all fail — returns None instead of raising."""
        cred_file = tmp_path / "cred.enc"
        auth_mw._save_per_user_encrypted(
            cred_file, self._mock_credentials(), per_user_key="correct-key"
        )
        result = auth_mw._try_decrypt_with_keys(
            cred_file,
            per_user_key="wrong-key",
            google_sub=None,
            normalized_email="alice@example.com",
        )
        assert result is None


# ===========================================================================
# TestSaveCredentialsRoundTrip — end-to-end save→load with OAuth recipients
# ===========================================================================


class TestSaveCredentialsRoundTrip:
    """Tests the full save_credentials → load path including multi-recipient envelopes.

    This catches real bugs in the envelope format (HMAC, CEK wrap, recipient lookup).
    """

    @staticmethod
    def _mock_credentials():
        from google.oauth2.credentials import Credentials

        return Credentials(
            token="e2e-token",
            refresh_token="e2e-refresh",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="e2e-cid",
            client_secret="e2e-cs",
        )

    def test_owner_plus_linked_account_both_decrypt(self, auth_mw, tmp_path):
        """Both the owner key and a linked account key should decrypt the same envelope."""
        cred_file = tmp_path / "cred.enc"
        auth_mw._save_per_user_encrypted(
            cred_file,
            self._mock_credentials(),
            per_user_key="owner-key",
            additional_keys=["linked-key"],
        )

        # Owner decrypts
        r1 = auth_mw._try_decrypt_with_keys(
            cred_file,
            per_user_key="owner-key",
            google_sub=None,
            normalized_email="a@e.com",
        )
        assert r1 is not None
        assert r1.token == "e2e-token"

        # Linked account decrypts
        r2 = auth_mw._try_decrypt_with_keys(
            cred_file,
            per_user_key="linked-key",
            google_sub=None,
            normalized_email="b@e.com",
        )
        assert r2 is not None
        assert r2.token == "e2e-token"

    def test_envelope_hmac_prevents_tampering(self, auth_mw, tmp_path):
        """Modifying the envelope data should fail HMAC verification."""
        cred_file = tmp_path / "cred.enc"
        auth_mw._save_per_user_encrypted(
            cred_file, self._mock_credentials(), per_user_key="my-key"
        )

        # Tamper with the envelope
        envelope = json.loads(cred_file.read_text())
        envelope["data"] = envelope["data"][::-1]  # corrupt the ciphertext
        cred_file.write_text(json.dumps(envelope))

        result = auth_mw._try_decrypt_with_keys(
            cred_file,
            per_user_key="my-key",
            google_sub=None,
            normalized_email="a@e.com",
        )
        assert result is None
