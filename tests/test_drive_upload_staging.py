"""Client-filesystem upload staging is keyed by who is calling, not by session.

Under MCP 2026-07-28 — and through Code Mode on the claude.ai connector — the
allocate call and the finalize call of ``upload_to_drive`` arrive on different
transport sessions. Keyed by ``session_id`` the finalize call never found the
staged bytes and answered "upload pending" forever.
"""

from __future__ import annotations

import pytest
from fastmcp.server.auth.auth import AccessToken
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

from auth import context as auth_context
from auth.types import AuthProvenance
from drive import upload_staging, upload_tools


def oauth_token(email: str) -> AccessToken:
    return AccessToken(
        token=f"jwt-{email}",
        client_id="https://claude.ai/oauth/some-client",
        scopes=["openid"],
        claims={"sub": "1234567890", "email": email, "iss": "test"},
    )


def shared_key_token() -> AccessToken:
    return AccessToken(
        token="admin-key",
        client_id="api-key-client",
        scopes=["openid"],
        claims={"sub": "api-key-user", "auth_method": AuthProvenance.API_KEY},
    )


class _As:
    """``async with _As(token):`` — run the block as that principal."""

    def __init__(self, token: AccessToken | None):
        self._token = token

    async def __aenter__(self):
        self._reset = auth_context_var.set(
            AuthenticatedUser(self._token) if self._token else None
        )
        return self

    async def __aexit__(self, *exc):
        auth_context_var.reset(self._reset)


@pytest.fixture(autouse=True)
def _staging_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        upload_tools.settings, "drive_upload_temp_dir", str(tmp_path / "staging")
    )
    upload_staging.reset_state()
    yield
    upload_staging.reset_state()


def _session(monkeypatch, session_id: str | None) -> None:
    """Pretend the current request arrived on this transport session."""

    async def fake() -> str | None:
        return session_id

    monkeypatch.setattr(auth_context, "get_session_context", fake)


def _put(upload_id: str, data: bytes) -> None:
    """What ``PUT /drive-upload`` does once the signed URL verifies."""
    with open(upload_staging.staged_path(upload_id), "wb") as f:
        f.write(data)
    upload_staging.mark_received(upload_id, len(data))


@pytest.mark.asyncio
async def test_owner_is_the_principal_not_the_session(monkeypatch):
    async with _As(oauth_token("Alice@Example.com")):
        _session(monkeypatch, "session-1")
        first = await upload_staging.staging_owner("alice@example.com")
        _session(monkeypatch, "session-2")
        second = await upload_staging.staging_owner("alice@example.com")
    assert first == second == "user:alice@example.com"


@pytest.mark.asyncio
async def test_owner_ignores_a_caller_supplied_email(monkeypatch):
    _session(monkeypatch, "session-1")
    async with _As(oauth_token("mallory@example.com")):
        owner = await upload_staging.staging_owner("alice@example.com")
    assert owner == "user:mallory@example.com"


@pytest.mark.asyncio
async def test_shared_key_owner_splits_by_target_account(monkeypatch):
    _session(monkeypatch, "session-1")
    async with _As(shared_key_token()):
        alice = await upload_staging.staging_owner("Alice@Example.com")
        bob = await upload_staging.staging_owner("bob@example.com")
    assert alice == "apikey:shared:alice@example.com"
    assert alice != bob


@pytest.mark.asyncio
async def test_tokenless_owner_falls_back_to_the_session(monkeypatch):
    async with _As(None):
        _session(monkeypatch, "session-1")
        assert await upload_staging.staging_owner("a@example.com") == (
            "session:session-1"
        )
        _session(monkeypatch, None)
        assert await upload_staging.staging_owner("a@example.com") is None


@pytest.mark.asyncio
async def test_finalize_finds_bytes_staged_on_another_session(monkeypatch):
    uploaded = {}

    async def fake_get_service(service, email):
        return object()

    async def fake_upload(service, content, filename, folder_id, mime_type):
        uploaded.update(content=content, filename=filename, folder_id=folder_id)
        return {"id": "file-1", "name": filename, "mimeType": mime_type}

    monkeypatch.setattr(upload_tools, "get_service", fake_get_service)
    monkeypatch.setattr(upload_tools, "upload_content_to_drive_api", fake_upload)

    async with _As(oauth_token("alice@example.com")):
        _session(monkeypatch, "session-1")
        pending = await upload_tools._handle_client_fs_upload(
            "/Users/alice/report.pdf", "folder-9", None, "alice@example.com"
        )
        assert pending["success"] is False
        upload_id = pending["pendingUpload"]["uploadId"]

        _put(upload_id, b"%PDF-bytes")

        _session(monkeypatch, "session-2")
        done = await upload_tools._handle_client_fs_upload(
            "/Users/alice/report.pdf", "root", None, "alice@example.com"
        )

    assert done["success"] is True, done
    assert done["fileInfo"]["fileId"] == "file-1"
    assert uploaded == {
        "content": b"%PDF-bytes",
        "filename": "report.pdf",
        "folder_id": "folder-9",
    }
    assert upload_staging.get_allocation(upload_id) is None


@pytest.mark.asyncio
async def test_another_user_cannot_finalize_the_same_path(monkeypatch):
    _session(monkeypatch, "session-1")
    async with _As(oauth_token("alice@example.com")):
        pending = await upload_tools._handle_client_fs_upload(
            "/tmp/shared-name.txt", "root", None, "alice@example.com"
        )
    _put(pending["pendingUpload"]["uploadId"], b"alice's bytes")

    async with _As(oauth_token("mallory@example.com")):
        theirs = await upload_tools._handle_client_fs_upload(
            "/tmp/shared-name.txt", "root", None, "alice@example.com"
        )

    assert theirs["success"] is False
    assert theirs["pendingUpload"]["uploadId"] != pending["pendingUpload"]["uploadId"]
