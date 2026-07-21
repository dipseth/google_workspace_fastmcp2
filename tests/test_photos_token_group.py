"""
Tests for per-service token-group credential storage.

Google requires Photos Library scopes to be authorized in their own OAuth
flow (they cannot be combined with Drive scopes). That means a Photos-only
token and a Workspace token can exist for the same account at the same time,
so credential storage is namespaced by "token group": the default
"workspace" group keeps the existing file layout, while separate-auth
services (photos) store their tokens under
``credentials_dir/token_groups/<group>/``.

These tests use the plaintext fallback storage path (no AuthMiddleware
registered) and require no OAuth config or external infrastructure.
"""

import json
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from google.oauth2.credentials import Credentials

from auth.google_auth import (
    DEFAULT_TOKEN_GROUP,
    GoogleAuthError,
    _get_credentials_path,
    _load_credentials,
    _save_credentials,
    get_token_group_credentials_dir,
    get_valid_credentials,
)
from auth.scope_registry import ScopeRegistry
from config.settings import settings


@pytest.fixture
def temp_credentials_dir():
    """Point settings.credentials_dir at a temp directory with dummy OAuth config."""
    temp_dir = tempfile.mkdtemp()
    original_dir = settings.credentials_dir
    original_client_id = settings.google_client_id
    original_client_secret = settings.google_client_secret
    settings.credentials_dir = temp_dir
    # _load_credentials needs an OAuth client config to rebuild Credentials
    settings.google_client_id = "test_client_id"
    settings.google_client_secret = "test_client_secret"
    # Force the plaintext storage path: other test modules may have
    # registered a global AuthMiddleware (encrypted storage), which would
    # divert saves away from the files these tests assert on.
    with patch("auth.context.get_auth_middleware", return_value=None):
        yield temp_dir
    settings.credentials_dir = original_dir
    settings.google_client_id = original_client_id
    settings.google_client_secret = original_client_secret
    shutil.rmtree(temp_dir, ignore_errors=True)


def _mock_creds(token: str, scopes: list[str]) -> Mock:
    creds = Mock(spec=Credentials)
    creds.token = token
    creds.refresh_token = f"{token}_refresh"
    creds.token_uri = "https://oauth2.googleapis.com/token"
    creds.client_id = "test_client_id"
    creds.client_secret = "test_client_secret"
    creds.scopes = scopes
    # Naive UTC to match google-auth's Credentials.expiry convention
    # (needs_refresh compares against datetime.utcnow())
    creds.expiry = datetime.utcnow() + timedelta(hours=1)
    creds.expired = False
    creds.valid = True
    return creds


WORKSPACE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
PHOTOS_SCOPES = ["https://www.googleapis.com/auth/photoslibrary.appendonly"]


class TestTokenGroupResolution:
    def test_photos_maps_to_its_own_group(self):
        assert ScopeRegistry.get_token_group_for_service("photos") == "photos"

    def test_photoslibrary_alias_maps_to_photos_group(self):
        assert ScopeRegistry.get_token_group_for_service("photoslibrary") == "photos"

    def test_regular_services_map_to_default_group(self):
        for service in ("drive", "gmail", "calendar", "sheets"):
            assert (
                ScopeRegistry.get_token_group_for_service(service)
                == ScopeRegistry.DEFAULT_TOKEN_GROUP
            )

    def test_photos_only_flow_maps_to_photos_group(self):
        assert ScopeRegistry.get_token_group_for_services(["photos"]) == "photos"

    def test_mixed_flow_maps_to_default_group(self):
        # get_scopes_for_services drops photos from mixed requests, so the
        # resulting token is a Workspace token.
        assert (
            ScopeRegistry.get_token_group_for_services(["drive", "photos"])
            == ScopeRegistry.DEFAULT_TOKEN_GROUP
        )

    def test_empty_flow_maps_to_default_group(self):
        assert (
            ScopeRegistry.get_token_group_for_services([])
            == ScopeRegistry.DEFAULT_TOKEN_GROUP
        )

    def test_registry_and_google_auth_agree_on_default_group(self):
        assert ScopeRegistry.DEFAULT_TOKEN_GROUP == DEFAULT_TOKEN_GROUP


class TestTokenGroupPaths:
    def test_default_group_keeps_legacy_layout(self, temp_credentials_dir):
        path = _get_credentials_path("user@example.com")
        assert (
            path == Path(temp_credentials_dir) / "user_at_example_com_credentials.json"
        )

    def test_photos_group_uses_isolated_subdirectory(self, temp_credentials_dir):
        path = _get_credentials_path("user@example.com", token_group="photos")
        assert (
            path
            == Path(temp_credentials_dir)
            / "token_groups"
            / "photos"
            / "user_at_example_com_credentials.json"
        )

    def test_group_dir_sanitizes_hostile_names(self, temp_credentials_dir):
        hostile = get_token_group_credentials_dir("../../etc")
        assert Path(temp_credentials_dir) in hostile.parents

        with pytest.raises(GoogleAuthError):
            get_token_group_credentials_dir("../..")


class TestTokenGroupStorageIsolation:
    def test_photos_save_does_not_overwrite_workspace_token(self, temp_credentials_dir):
        email = "user@example.com"
        _save_credentials(email, _mock_creds("workspace_token", WORKSPACE_SCOPES))
        _save_credentials(
            email, _mock_creds("photos_token", PHOTOS_SCOPES), token_group="photos"
        )

        workspace_path = _get_credentials_path(email)
        photos_path = _get_credentials_path(email, token_group="photos")
        assert workspace_path.exists()
        assert photos_path.exists()
        assert workspace_path != photos_path

        with open(workspace_path) as f:
            workspace_data = json.load(f)
        with open(photos_path) as f:
            photos_data = json.load(f)

        assert workspace_data["token"] == "workspace_token"
        assert workspace_data["token_group"] == DEFAULT_TOKEN_GROUP
        assert photos_data["token"] == "photos_token"
        assert photos_data["token_group"] == "photos"

    def test_load_reads_from_requested_group(self, temp_credentials_dir):
        email = "user@example.com"
        _save_credentials(email, _mock_creds("workspace_token", WORKSPACE_SCOPES))
        _save_credentials(
            email, _mock_creds("photos_token", PHOTOS_SCOPES), token_group="photos"
        )

        workspace_creds = _load_credentials(email)
        photos_creds = _load_credentials(email, token_group="photos")

        assert workspace_creds is not None
        assert photos_creds is not None
        assert workspace_creds.token == "workspace_token"
        assert photos_creds.token == "photos_token"
        assert set(photos_creds.scopes) == set(PHOTOS_SCOPES)

    def test_missing_group_returns_none_without_falling_back(
        self, temp_credentials_dir
    ):
        email = "user@example.com"
        _save_credentials(email, _mock_creds("workspace_token", WORKSPACE_SCOPES))

        # Workspace token exists, but the photos slot is empty — loading the
        # photos group must NOT silently return the Workspace token.
        assert _load_credentials(email, token_group="photos") is None
        assert get_valid_credentials(email, token_group="photos") is None

    def test_get_valid_credentials_routes_by_group(self, temp_credentials_dir):
        email = "user@example.com"
        _save_credentials(
            email, _mock_creds("photos_token", PHOTOS_SCOPES), token_group="photos"
        )

        creds = get_valid_credentials(email, token_group="photos")
        assert creds is not None
        assert creds.token == "photos_token"
        assert get_valid_credentials(email) is None


class TestMiddlewareMemoryKeyNamespacing:
    def test_default_group_uses_bare_email(self):
        from auth.middleware import AuthMiddleware

        assert (
            AuthMiddleware._memory_key("user@example.com", DEFAULT_TOKEN_GROUP)
            == "user@example.com"
        )

    def test_separate_group_is_namespaced(self):
        from auth.middleware import AuthMiddleware

        assert (
            AuthMiddleware._memory_key("user@example.com", "photos")
            == "user@example.com::photos"
        )


def _real_creds(token: str, scopes: list[str]) -> Credentials:
    """A real Credentials object (encryption serializes/rebuilds real fields)."""
    return Credentials(
        token=token,
        refresh_token=f"{token}_refresh",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="test_client_id",
        client_secret="test_client_secret",
        scopes=scopes,
    )


class TestEncryptedEnvelopeTokenGroups:
    """Token-group files use the same multi-recipient crypto envelope
    (v2, per-user split-key + HMAC) as Workspace credential files."""

    EMAIL = "user@example.com"
    KEY = "test-bearer-key-abc123"

    def _middleware(self):
        from auth.middleware import AuthMiddleware, CredentialStorageMode

        return AuthMiddleware(storage_mode=CredentialStorageMode.FILE_ENCRYPTED)

    def test_photos_group_saves_per_user_envelope(self, temp_credentials_dir):
        middleware = self._middleware()
        middleware.save_credentials(
            self.EMAIL,
            _real_creds("photos_secret_token", PHOTOS_SCOPES),
            per_user_key=self.KEY,
            token_group="photos",
        )

        enc_path = (
            Path(temp_credentials_dir)
            / "token_groups"
            / "photos"
            / "user_at_example_com_credentials.enc"
        )
        assert enc_path.exists()

        raw = enc_path.read_text()
        envelope = json.loads(raw)
        assert envelope["v"] == 2
        assert envelope["enc"] == "per_user"
        assert len(envelope.get("recipients", {})) >= 1
        assert "hmac" in envelope
        # The token itself must never appear in plaintext on disk
        assert "photos_secret_token" not in raw

    def test_photos_envelope_decrypts_only_with_key(self, temp_credentials_dir):
        middleware = self._middleware()
        middleware.save_credentials(
            self.EMAIL,
            _real_creds("photos_secret_token", PHOTOS_SCOPES),
            per_user_key=self.KEY,
            token_group="photos",
        )

        loaded = middleware.load_credentials(
            self.EMAIL, per_user_key=self.KEY, token_group="photos"
        )
        assert loaded is not None
        assert loaded.token == "photos_secret_token"

        # No key → locked; wrong key → locked
        assert middleware.load_credentials(self.EMAIL, token_group="photos") is None
        assert (
            middleware.load_credentials(
                self.EMAIL, per_user_key="wrong-key", token_group="photos"
            )
            is None
        )

    def test_workspace_and_photos_envelopes_are_independent(self, temp_credentials_dir):
        middleware = self._middleware()
        middleware.save_credentials(
            self.EMAIL,
            _real_creds("workspace_secret", WORKSPACE_SCOPES),
            per_user_key=self.KEY,
        )
        middleware.save_credentials(
            self.EMAIL,
            _real_creds("photos_secret", PHOTOS_SCOPES),
            per_user_key=self.KEY,
            token_group="photos",
        )

        workspace = middleware.load_credentials(self.EMAIL, per_user_key=self.KEY)
        photos = middleware.load_credentials(
            self.EMAIL, per_user_key=self.KEY, token_group="photos"
        )
        assert workspace is not None and workspace.token == "workspace_secret"
        assert photos is not None and photos.token == "photos_secret"

    def test_add_recipient_works_on_group_envelope(self, temp_credentials_dir):
        middleware = self._middleware()
        middleware.save_credentials(
            self.EMAIL,
            _real_creds("photos_secret", PHOTOS_SCOPES),
            per_user_key=self.KEY,
            token_group="photos",
        )
        enc_path = (
            Path(temp_credentials_dir)
            / "token_groups"
            / "photos"
            / "user_at_example_com_credentials.enc"
        )

        second_key = "linked-account-key-xyz789"
        assert middleware.add_recipient_to_encrypted_file(
            enc_path, self.KEY, second_key
        )
        loaded = middleware.load_credentials(
            self.EMAIL, per_user_key=second_key, token_group="photos"
        )
        assert loaded is not None
        assert loaded.token == "photos_secret"

    def test_group_envelope_appears_in_inventory(self, temp_credentials_dir):
        middleware = self._middleware()
        middleware.save_credentials(
            self.EMAIL,
            _real_creds("photos_secret", PHOTOS_SCOPES),
            per_user_key=self.KEY,
            token_group="photos",
        )

        inventory = middleware.get_envelope_inventory(self.EMAIL)
        group_entries = [e for e in inventory if "photos token group" in e["label"]]
        assert len(group_entries) == 1
        assert group_entries[0]["enc_type"] == "per_user"
        assert group_entries[0]["has_hmac"] is True


class TestServiceManagerRouting:
    @pytest.mark.asyncio
    async def test_photos_service_without_photos_token_gives_specific_error(
        self, temp_credentials_dir
    ):
        from auth.service_manager import GoogleServiceError, get_google_service

        email = "user@example.com"
        # A Workspace token exists but there is no photos-group token
        _save_credentials(email, _mock_creds("workspace_token", WORKSPACE_SCOPES))

        with pytest.raises(GoogleServiceError) as exc_info:
            await get_google_service(
                user_email=email,
                service_type="photos",
                scopes=PHOTOS_SCOPES,
                cache_enabled=False,
            )

        message = str(exc_info.value)
        assert "Separate Authorization Required" in message
        assert '["photos"]' in message
