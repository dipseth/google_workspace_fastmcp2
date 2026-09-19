"""Client-filesystem upload staging: keyed by who is calling, stateless per replica.

Under MCP 2026-07-28 — and through Code Mode on the claude.ai connector — the
issue call and the finalize call of ``upload_to_drive`` arrive on different
transport sessions. Keyed by ``session_id`` the finalize call never found the
staged bytes and answered "upload pending" forever.

With more than one replica the three requests of an upload (issue, PUT,
finalize) may each land on a different process, so nothing about an upload may
live in memory. ``_new_replica()`` stands in for "another process": it drops
every module-level cache, leaving only what replicas really share — the
``.auth_encryption_key`` file and the staging store.
"""

from __future__ import annotations

import os
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastmcp import FastMCP
from fastmcp.server.auth.auth import AccessToken
from google.api_core.exceptions import NotFound
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

from auth import context as auth_context
from auth.types import AuthProvenance
from drive import upload_staging, upload_tools
from photos import advanced_tools as photos_tools
from tools.drive_upload_endpoints import setup_drive_upload_endpoints


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
    (tmp_path / ".auth_encryption_key").write_text("shared-by-every-replica")
    monkeypatch.setattr(
        upload_tools.settings, "drive_upload_temp_dir", str(tmp_path / "staging")
    )
    monkeypatch.setattr(upload_tools.settings, "drive_upload_staging_uri", "")
    monkeypatch.setattr(upload_tools.settings, "drive_upload_ttl_seconds", 900)
    upload_staging.reset_state()
    yield
    upload_staging.reset_state()


def _new_replica() -> None:
    upload_staging.reset_state()


def _session(monkeypatch, session_id: str | None) -> None:
    """Pretend the current request arrived on this transport session."""

    async def fake() -> str | None:
        return session_id

    monkeypatch.setattr(auth_context, "get_session_context", fake)


def _query(url: str) -> tuple[str, str]:
    q = parse_qs(urlparse(url).query)
    return q["t"][0], q["sig"][0]


async def _put(url: str, data: bytes) -> None:
    """What ``PUT /drive-upload`` does with a signed URL."""
    valid, error, payload = upload_staging.verify_upload_url(*_query(url))
    assert valid, error
    incoming = upload_staging.incoming_path(payload["uid"])
    with open(incoming, "wb") as f:
        f.write(data)
    await upload_staging.commit_staged(payload, incoming, len(data))


def _fake_drive(monkeypatch) -> dict:
    uploaded: dict = {}

    async def fake_get_service(service, email):
        return object()

    async def fake_upload(service, content, filename, folder_id, mime_type):
        uploaded.update(content=content, filename=filename, folder_id=folder_id)
        return {"id": "file-1", "name": filename, "mimeType": mime_type}

    monkeypatch.setattr(upload_tools, "get_service", fake_get_service)
    monkeypatch.setattr(upload_tools, "upload_content_to_drive_api", fake_upload)
    return uploaded


# ---------------------------------------------------------------------------
# Owner
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Two-phase upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_each_request_of_an_upload_can_land_on_a_different_replica(monkeypatch):
    uploaded = _fake_drive(monkeypatch)

    async with _As(oauth_token("alice@example.com")):
        _session(monkeypatch, "session-1")
        pending = await upload_tools._handle_client_fs_upload(
            "/Users/alice/report.pdf", "folder-9", None, "alice@example.com"
        )
        assert pending["success"] is False
        url = pending["pendingUpload"]["uploadUrl"]

        _new_replica()
        await _put(url, b"%PDF-bytes")

        _new_replica()
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
    # Consumed: the next call for the same path starts over.
    assert (
        await upload_staging.find_staged(
            "user:alice@example.com", "/Users/alice/report.pdf"
        )
        is None
    )
    assert os.listdir(upload_tools.settings.drive_upload_temp_dir) == []


@pytest.mark.asyncio
async def test_finalize_overrides_win_over_the_values_signed_at_issue(monkeypatch):
    uploaded = _fake_drive(monkeypatch)
    _session(monkeypatch, "session-1")
    async with _As(oauth_token("alice@example.com")):
        pending = await upload_tools._handle_client_fs_upload(
            "/tmp/a.txt", "folder-1", "first.txt", "alice@example.com"
        )
        await _put(pending["pendingUpload"]["uploadUrl"], b"hi")
        await upload_tools._handle_client_fs_upload(
            "/tmp/a.txt", "folder-2", "second.txt", "alice@example.com"
        )
    assert uploaded["folder_id"] == "folder-2"
    assert uploaded["filename"] == "second.txt"


@pytest.mark.asyncio
async def test_another_user_cannot_finalize_the_same_path(monkeypatch):
    _fake_drive(monkeypatch)
    _session(monkeypatch, "session-1")
    async with _As(oauth_token("alice@example.com")):
        pending = await upload_tools._handle_client_fs_upload(
            "/tmp/shared-name.txt", "root", None, "alice@example.com"
        )
    await _put(pending["pendingUpload"]["uploadUrl"], b"alice's bytes")

    async with _As(oauth_token("mallory@example.com")):
        theirs = await upload_tools._handle_client_fs_upload(
            "/tmp/shared-name.txt", "root", None, "alice@example.com"
        )

    assert theirs["success"] is False
    assert "pendingUpload" in theirs
    assert (
        await upload_staging.find_staged(
            "user:alice@example.com", "/tmp/shared-name.txt"
        )
        is not None
    )


@pytest.mark.asyncio
async def test_staged_bytes_older_than_the_ttl_are_not_served(monkeypatch):
    ticket = await upload_staging.issue_upload(
        "https://mcp.test", "user:a@example.com", "/tmp/a.txt", "root", None, 900
    )
    await _put(ticket.url, b"old")
    assert await upload_staging.find_staged("user:a@example.com", "/tmp/a.txt")

    real_time = time.time
    monkeypatch.setattr(upload_staging.time, "time", lambda: real_time() + 901)
    assert await upload_staging.find_staged("user:a@example.com", "/tmp/a.txt") is None
    assert await upload_staging.read_staged_bytes(ticket.key) is None


@pytest.mark.asyncio
async def test_photos_staging_survives_a_replica_hop_and_cleans_up(monkeypatch):
    paths = ["/Users/alice/a.jpg", "/Users/alice/b.png"]
    async with _As(oauth_token("alice@example.com")):
        _session(monkeypatch, "session-1")
        first = await photos_tools._stage_client_fs_photos(paths, "alice@example.com")
        pending = first.pending_response.pending_uploads
        assert [p["file"] for p in pending] == paths

        _new_replica()
        await _put(pending[0]["uploadUrl"], b"jpeg")

        # One of two staged: still pending, and only for the missing file.
        _new_replica()
        half = await photos_tools._stage_client_fs_photos(paths, "alice@example.com")
        assert [p["file"] for p in half.pending_response.pending_uploads] == [paths[1]]
        await _put(half.pending_response.pending_uploads[0]["uploadUrl"], b"png")

        _new_replica()
        _session(monkeypatch, "session-2")
        ready = await photos_tools._stage_client_fs_photos(paths, "alice@example.com")

    assert ready.pending_response is None
    assert [os.path.basename(p) for p in ready.local_paths] == ["a.jpg", "b.png"]
    with open(ready.local_paths[0], "rb") as f:
        assert f.read() == b"jpeg"
    assert ready.path_map[ready.local_paths[1]] == paths[1]

    temp_dir = ready.temp_dir
    await ready.cleanup()
    assert not os.path.exists(temp_dir)
    assert os.listdir(upload_tools.settings.drive_upload_temp_dir) == []


# ---------------------------------------------------------------------------
# Signed URL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signed_url_is_one_time_and_tamper_evident():
    ticket = await upload_staging.issue_upload(
        "https://mcp.test/", "user:a@example.com", "/tmp/a.txt", "root", None, 900
    )
    assert ticket.url.startswith("https://mcp.test/drive-upload?")
    token, sig = _query(ticket.url)

    flipped = ("A" if token[0] != "A" else "B") + token[1:]
    assert upload_staging.verify_upload_url(flipped, sig)[1] == "Invalid signature"
    assert upload_staging.verify_upload_url(token, "0" * 64)[1] == "Invalid signature"

    valid, _, payload = upload_staging.verify_upload_url(token, sig)
    assert valid and payload["k"] == ticket.key
    assert upload_staging.verify_upload_url(token, sig)[1] == "Upload URL already used"


@pytest.mark.asyncio
async def test_expired_url_is_rejected(monkeypatch):
    ticket = await upload_staging.issue_upload(
        "https://mcp.test", "user:a@example.com", "/tmp/a.txt", "root", None, 900
    )
    real_time = time.time
    monkeypatch.setattr(upload_staging.time, "time", lambda: real_time() + 901)
    assert (
        upload_staging.verify_upload_url(*_query(ticket.url))[1]
        == "Upload link has expired"
    )


@pytest.mark.asyncio
async def test_a_replica_with_a_different_secret_rejects_the_url(tmp_path):
    ticket = await upload_staging.issue_upload(
        "https://mcp.test", "user:a@example.com", "/tmp/a.txt", "root", None, 900
    )
    _new_replica()
    (tmp_path / ".auth_encryption_key").write_text("not-the-same-secret")
    assert (
        upload_staging.verify_upload_url(*_query(ticket.url))[1] == "Invalid signature"
    )


def test_object_key_is_stable_and_separates_owners_and_paths():
    key = upload_staging.object_key("user:a@example.com", "/tmp/a.txt")
    assert key == upload_staging.object_key("user:a@example.com", "/tmp/a.txt")
    assert key != upload_staging.object_key("user:b@example.com", "/tmp/a.txt")
    assert key != upload_staging.object_key("user:a@example.com", "/tmp/b.txt")
    assert upload_staging._KEY_RE.match(key)


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------


def test_sweep_removes_only_expired_files_it_owns(tmp_path):
    root = tmp_path / "shared-volume"
    store = upload_staging.DirectoryStore(str(root))
    key = "a" * 64
    incoming = store.incoming_path("b" * 32)
    with open(incoming, "wb") as f:
        f.write(b"x")
    store.commit(key, incoming, {"filename": "x"})
    abandoned = store.incoming_path("c" * 32)
    open(abandoned, "wb").close()
    foreign = root / "someone-elses-file.txt"
    foreign.write_text("keep me")

    old = time.time() - 1000
    for name in os.listdir(root):
        os.utime(root / name, (old, old))

    assert store.evict_expired(900) == 3
    assert os.listdir(root) == ["someone-elses-file.txt"]


def test_staged_files_are_owner_only_even_in_a_loose_directory(tmp_path):
    root = tmp_path / "shared-volume"
    root.mkdir(mode=0o755)
    store = upload_staging.DirectoryStore(str(root))
    incoming = store.incoming_path("b" * 32)
    with open(incoming, "wb") as f:
        f.write(b"x")
    os.chmod(incoming, 0o644)
    store.commit("a" * 64, incoming, {"filename": "x"})
    modes = {
        name: oct(os.stat(root / name).st_mode & 0o777) for name in os.listdir(root)
    }
    assert modes == {"a" * 64 + ".bin": "0o600", "a" * 64 + ".json": "0o600"}


def test_unsupported_staging_uri_is_an_error(monkeypatch):
    monkeypatch.setattr(
        upload_tools.settings, "drive_upload_staging_uri", "s3://bucket/x"
    )
    with pytest.raises(RuntimeError, match="Unsupported DRIVE_UPLOAD_STAGING_URI"):
        upload_staging.get_store()


class _FakeBlob:
    def __init__(self, objects: dict, name: str):
        self._objects, self._name = objects, name

    def upload_from_filename(self, filename):
        with open(filename, "rb") as f:
            self._objects[self._name] = f.read()

    def upload_from_string(self, data, content_type=None):
        self._objects[self._name] = data.encode()

    def download_as_bytes(self):
        if self._name not in self._objects:
            raise NotFound(self._name)
        return self._objects[self._name]

    def delete(self):
        if self._name not in self._objects:
            raise NotFound(self._name)
        del self._objects[self._name]


class _FakeBucket:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def blob(self, name):
        return _FakeBlob(self.objects, name)


def test_gcs_store_round_trip_against_a_fake_bucket(tmp_path):
    bucket = _FakeBucket()
    store = upload_staging.GcsStore(bucket, "/staging/", str(tmp_path / "scratch"))
    key = "d" * 64
    assert store.read_meta(key) is None and store.read_bytes(key) is None

    incoming = store.incoming_path("e" * 32)
    with open(incoming, "wb") as f:
        f.write(b"payload")
    store.commit(key, incoming, {"filename": "p.bin"})

    assert sorted(bucket.objects) == [f"staging/{key}.bin", f"staging/{key}.json"]
    assert not os.path.exists(incoming)
    assert store.read_bytes(key) == b"payload"
    assert store.read_meta(key) == {"filename": "p.bin"}

    store.delete(key)
    store.delete(key)  # already gone: not an error
    assert bucket.objects == {}


# ---------------------------------------------------------------------------
# HTTP endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_endpoint_stages_bytes_for_finalize(monkeypatch):
    mcp = FastMCP("upload-endpoint-test")
    setup_drive_upload_endpoints(mcp)
    monkeypatch.setattr(upload_tools.settings, "drive_upload_max_size_mb", 1)

    ticket = await upload_staging.issue_upload(
        "http://mcp.test", "user:a@example.com", "/tmp/photo.jpg", "root", None, 900
    )
    big = await upload_staging.issue_upload(
        "http://mcp.test", "user:a@example.com", "/tmp/big.bin", "root", None, 900
    )

    transport = httpx.ASGITransport(app=mcp.http_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://mcp.test") as c:
        assert (await c.put("/drive-upload")).status_code == 400
        assert (await c.put("/drive-upload?t=abc&sig=def")).status_code == 403

        ok = await c.put(ticket.url, content=b"jpeg-bytes")
        assert ok.status_code == 200, ok.text
        assert ok.json()["bytes"] == 10
        assert ok.json()["filename"] == "photo.jpg"

        assert (await c.put(ticket.url, content=b"again")).status_code == 410

        too_big = await c.put(big.url, content=b"x" * (1024 * 1024 + 1))
        assert too_big.status_code == 413

    _new_replica()
    staged = await upload_staging.find_staged("user:a@example.com", "/tmp/photo.jpg")
    assert staged is not None and staged.mime_type == "image/jpeg"
    assert await upload_staging.read_staged_bytes(staged.key) == b"jpeg-bytes"
    assert (
        await upload_staging.find_staged("user:a@example.com", "/tmp/big.bin") is None
    )
