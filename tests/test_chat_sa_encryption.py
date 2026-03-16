"""Tests for per-user Chat service account encryption and loading."""

import json
import secrets
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Minimal service account JSON for testing
FAKE_SA_JSON = {
    "type": "service_account",
    "project_id": "test-project",
    "private_key_id": "key123",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----\n",
    "client_email": "test@test-project.iam.gserviceaccount.com",
    "client_id": "123456789",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
}


@pytest.fixture
def sa_env(tmp_path):
    """Set up a temp credentials dir with server secret, return (middleware, dir)."""
    creds_dir = str(tmp_path)

    # Write server secret for HKDF derivation
    secret_path = tmp_path / ".auth_encryption_key"
    with open(secret_path, "wb") as f:
        f.write(secrets.token_bytes(32))

    from cryptography.fernet import Fernet

    from auth.middleware import AuthMiddleware, CredentialStorageMode

    with patch("auth.middleware.settings") as mock_settings:
        mock_settings.credentials_dir = creds_dir
        mock_settings.drive_scopes = []

        mw = AuthMiddleware(storage_mode=CredentialStorageMode.FILE_ENCRYPTED)
        mw._fernet = Fernet(Fernet.generate_key())
        mw._key_source = "explicit"

    yield mw, creds_dir


def _normalize_passthrough(email: str) -> str:
    return email.lower()


class TestSaveChatServiceAccount:
    def test_save_and_load_roundtrip(self, sa_env):
        mw, creds_dir = sa_env
        sa_json_str = json.dumps(FAKE_SA_JSON)
        per_user_key = "test-user-api-key-12345"

        with (
            patch(
                "auth.google_auth._normalize_email", side_effect=_normalize_passthrough
            ),
            patch("auth.middleware.settings") as ms,
        ):
            ms.credentials_dir = creds_dir

            mw.save_chat_service_account(
                "user@example.com",
                sa_json_str,
                per_user_key=per_user_key,
            )
            loaded = mw.load_chat_service_account(
                "user@example.com",
                per_user_key=per_user_key,
            )

        assert loaded is not None
        assert loaded["type"] == "service_account"
        assert loaded["project_id"] == "test-project"
        assert loaded["client_email"] == "test@test-project.iam.gserviceaccount.com"

    def test_load_missing_file_returns_none(self, sa_env):
        mw, creds_dir = sa_env

        with (
            patch(
                "auth.google_auth._normalize_email", side_effect=_normalize_passthrough
            ),
            patch("auth.middleware.settings") as ms,
        ):
            ms.credentials_dir = creds_dir
            result = mw.load_chat_service_account(
                "nobody@example.com", per_user_key="k"
            )

        assert result is None

    def test_wrong_key_cannot_decrypt(self, sa_env):
        mw, creds_dir = sa_env
        sa_json_str = json.dumps(FAKE_SA_JSON)

        with (
            patch(
                "auth.google_auth._normalize_email", side_effect=_normalize_passthrough
            ),
            patch("auth.middleware.settings") as ms,
        ):
            ms.credentials_dir = creds_dir

            mw.save_chat_service_account(
                "user@example.com",
                sa_json_str,
                per_user_key="correct-key",
            )
            loaded = mw.load_chat_service_account(
                "user@example.com",
                per_user_key="wrong-key",
            )

        assert loaded is None

    def test_envelope_file_format(self, sa_env):
        mw, creds_dir = sa_env
        sa_json_str = json.dumps(FAKE_SA_JSON)

        with (
            patch(
                "auth.google_auth._normalize_email", side_effect=_normalize_passthrough
            ),
            patch("auth.middleware.settings") as ms,
        ):
            ms.credentials_dir = creds_dir

            mw.save_chat_service_account(
                "user@example.com",
                sa_json_str,
                per_user_key="test-key",
            )

        sa_path = Path(creds_dir) / "user_at_example_com_chat_sa.enc"
        assert sa_path.exists()

        with open(sa_path) as f:
            envelope = json.load(f)

        assert envelope["v"] == 2
        assert envelope["enc"] == "per_user"
        assert envelope["type"] == "chat_service_account"
        assert "recipients" in envelope
        assert "data" in envelope
        assert "hmac" in envelope


class TestSessionKeyEnum:
    def test_chat_sa_key_exists(self):
        from auth.types import SessionKey

        assert hasattr(SessionKey, "CHAT_SERVICE_ACCOUNT_JSON")
        assert SessionKey.CHAT_SERVICE_ACCOUNT_JSON == "chat_service_account_json"
