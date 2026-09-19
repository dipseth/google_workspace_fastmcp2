"""Secure staging for client→server→Drive uploads with HMAC-signed PUT URLs.

This is the *inbound* mirror of ``gmail/attachment_server.py``. When
``settings.drive_upload_client_fs`` is enabled, ``upload_to_drive`` cannot
read from the server's local filesystem — the path lives on the client.
Instead the tool issues an HMAC-signed PUT URL; the client uploads file
content there; ``upload_to_drive`` is re-called and finalizes the Drive
upload from the staged bytes.

No upload state lives in process memory, so the three requests of one upload
(issue, PUT, finalize) may each land on a different replica:

    - The signed URL carries everything the PUT endpoint needs — object key,
      filename, destination — so it needs no allocation record to look up.
    - The staged object is named ``HMAC(owner, client_path)``. The finalize
      call recomputes that name and looks; there is no index to consult.
    - ``owner`` is the authenticated principal, not the transport session:
      under MCP 2026-07-28 (and Code Mode through the claude.ai connector)
      every request is its own session.

What replicas must share for that to hold:

    - ``.auth_encryption_key`` — it signs the URLs *and* names the objects.
    - The staging store: ``DRIVE_UPLOAD_TEMP_DIR`` on a shared volume, or
      ``DRIVE_UPLOAD_STAGING_URI=gs://bucket/prefix``.
    - Redis, for one-time use of a URL across replicas (``ConsumedTokenStore``
      falls back to per-process memory without it).

Security:
    - HMAC-SHA256 signed URLs (HKDF-derived key, distinct ``info`` from
      attachment downloads); the whole payload is signed as one token
    - One-time use via ``ConsumedTokenStore``
    - Object names are hex digests the client cannot choose; validated before
      they touch a path
    - Staging dir with ``0o700`` permissions
    - Eager + lazy cleanup; staged bytes older than the TTL are never served
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac as _hmac
import json
import mimetypes
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol
from urllib.parse import urlencode, urlparse

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from config.enhanced_logging import setup_logger
from middleware.token_store import ConsumedTokenStore

logger = setup_logger()

CLEANUP_INTERVAL_SECONDS = 300  # 5 minutes
_hmac_key_cache: Optional[bytes] = None
_consumed_uploads = ConsumedTokenStore("drive-upload", default_ttl_seconds=900)
_cleanup_task: Optional[asyncio.Task] = None

_KEY_RE = re.compile(r"^[0-9a-f]{64}$")
_UPLOAD_ID_RE = re.compile(r"^[0-9a-f]{32}$")
# Names this module writes; the sweep touches nothing else in the directory.
_OWN_FILE_RE = re.compile(
    r"^(?:[0-9a-f]{64}\.(?:bin|json)|\.incoming-[0-9a-f]{32}|\.meta-[0-9a-f]{32})$"
)


@dataclass
class UploadTicket:
    """A signed PUT URL issued for one ``(owner, client_path)``."""

    upload_id: str
    key: str
    url: str
    expires_at: int
    filename: str


@dataclass
class StagedUpload:
    """Bytes a client has PUT, waiting for the finalize call."""

    key: str
    filename: str
    mime_type: str
    folder_id: str
    custom_filename: Optional[str]
    size: int
    received_at: float


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


def _get_server_secret() -> str:
    """Read the server secret from ``.auth_encryption_key``."""
    secret_path = Path(".auth_encryption_key")
    if secret_path.exists():
        secret = secret_path.read_text().strip()
        if secret:
            return secret
    import secrets as _secrets

    fallback = _secrets.token_urlsafe(32)
    logger.warning(
        "No .auth_encryption_key found; drive upload URLs using random ephemeral key. "
        "URLs will NOT survive server restarts or verify on another replica."
    )
    return fallback


def _get_hmac_key() -> bytes:
    """Derive a 32-byte HMAC key via HKDF-SHA256."""
    global _hmac_key_cache
    if _hmac_key_cache is not None:
        return _hmac_key_cache

    secret = _get_server_secret()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"mcp-google-workspace-v1",
        info=b"drive-upload-hmac-v1",
    )
    _hmac_key_cache = hkdf.derive(secret.encode())
    return _hmac_key_cache


def _sign(data: bytes) -> str:
    return _hmac.new(_get_hmac_key(), data, hashlib.sha256).hexdigest()


def object_key(owner: str, client_path: str) -> str:
    """Name of the staged object for ``(owner, client_path)``.

    Deterministic, so the finalize call finds the bytes without a lookup
    table, and keyed, so it reveals neither the owner nor the path.
    """
    return _sign(b"object\0" + owner.encode() + b"\0" + client_path.encode())


async def staging_owner(user_email: Optional[str]) -> Optional[str]:
    """Who a staged upload belongs to, stable across the two tool calls.

    A per-user token (OAuth JWT, per-user API key) → its principal, which the
    caller cannot choose. The shared ``MCP_API_KEY`` is one principal for every
    holder, so the target account splits it. With no token at all (legacy
    no-auth HTTP) the transport session is the only handle there is.
    """
    from auth.context import get_session_context
    from auth.user_state import SHARED_KEY_PRINCIPAL, principal_id

    principal = principal_id()
    if principal and principal != SHARED_KEY_PRINCIPAL:
        return principal
    if principal:
        return f"{principal}:{(user_email or '').lower().strip()}"
    session_id = await get_session_context()
    return f"session:{session_id}" if session_id else None


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------


class StagingStore(Protocol):
    """Where staged bytes live. Methods block; call them via ``to_thread``."""

    def incoming_path(self, upload_id: str) -> str:
        """Local path the PUT endpoint streams to before ``commit``."""

    def commit(self, key: str, incoming: str, meta: dict) -> None:
        """Publish ``incoming`` as ``key``. Meta is written last: its presence
        means the bytes are complete."""

    def read_meta(self, key: str) -> Optional[dict]: ...

    def read_bytes(self, key: str) -> Optional[bytes]: ...

    def delete(self, key: str) -> None: ...

    def evict_expired(self, ttl_seconds: int) -> int: ...


def _sweep_dir(root: str, ttl_seconds: int) -> int:
    """Unlink files in ``root`` older than the TTL (abandoned PUTs included)."""
    cutoff = time.time() - ttl_seconds
    removed = 0
    try:
        entries = list(os.scandir(root))
    except OSError:
        return 0
    for entry in entries:
        try:
            if not _OWN_FILE_RE.match(entry.name):
                continue
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                os.unlink(entry.path)
                removed += 1
        except OSError:
            pass
    return removed


class DirectoryStore:
    """Staging in a directory: local disk, or a volume every replica mounts."""

    def __init__(self, root: str) -> None:
        self._root = root
        os.makedirs(root, mode=0o700, exist_ok=True)

    def _path(self, name: str) -> str:
        return os.path.join(self._root, name)

    def incoming_path(self, upload_id: str) -> str:
        # Same directory as the target, so commit is an atomic rename.
        return self._path(f".incoming-{upload_id}")

    def commit(self, key: str, incoming: str, meta: dict) -> None:
        os.replace(incoming, self._path(f"{key}.bin"))
        tmp = self._path(f".meta-{uuid.uuid4().hex}")
        with open(tmp, "w") as f:
            json.dump(meta, f)
        os.replace(tmp, self._path(f"{key}.json"))

    def read_meta(self, key: str) -> Optional[dict]:
        try:
            with open(self._path(f"{key}.json")) as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def read_bytes(self, key: str) -> Optional[bytes]:
        try:
            with open(self._path(f"{key}.bin"), "rb") as f:
                return f.read()
        except OSError:
            return None

    def delete(self, key: str) -> None:
        # Meta first: a reader that still sees it must still find the bytes.
        for name in (f"{key}.json", f"{key}.bin"):
            try:
                os.unlink(self._path(name))
            except FileNotFoundError:
                pass
            except OSError as e:
                logger.warning("Failed to clean up staged upload %s: %s", key[:8], e)

    def evict_expired(self, ttl_seconds: int) -> int:
        return _sweep_dir(self._root, ttl_seconds)


class GcsStore:
    """Staging in a Cloud Storage bucket (``gs://bucket/prefix``).

    Needs ``google-cloud-storage`` and application default credentials.
    Expiry of abandoned objects is the bucket's job: give it a lifecycle rule
    that deletes objects under the prefix after a day.
    """

    def __init__(self, bucket: Any, prefix: str, scratch_dir: str) -> None:
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._scratch = scratch_dir
        os.makedirs(scratch_dir, mode=0o700, exist_ok=True)

    @classmethod
    def from_uri(cls, uri: str, scratch_dir: str) -> "GcsStore":
        try:
            from google.cloud import storage as gcs_storage
        except ImportError as e:
            raise RuntimeError(
                "DRIVE_UPLOAD_STAGING_URI is a gs:// URI but google-cloud-storage "
                "is not installed."
            ) from e
        parsed = urlparse(uri)
        return cls(gcs_storage.Client().bucket(parsed.netloc), parsed.path, scratch_dir)

    def _blob(self, name: str) -> Any:
        return self._bucket.blob(f"{self._prefix}/{name}" if self._prefix else name)

    def incoming_path(self, upload_id: str) -> str:
        return os.path.join(self._scratch, f".incoming-{upload_id}")

    def commit(self, key: str, incoming: str, meta: dict) -> None:
        try:
            self._blob(f"{key}.bin").upload_from_filename(incoming)
            self._blob(f"{key}.json").upload_from_string(
                json.dumps(meta), content_type="application/json"
            )
        finally:
            try:
                os.unlink(incoming)
            except OSError:
                pass

    def _download(self, name: str) -> Optional[bytes]:
        from google.api_core.exceptions import NotFound

        try:
            return self._blob(name).download_as_bytes()
        except NotFound:
            return None

    def read_meta(self, key: str) -> Optional[dict]:
        raw = self._download(f"{key}.json")
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return None

    def read_bytes(self, key: str) -> Optional[bytes]:
        return self._download(f"{key}.bin")

    def delete(self, key: str) -> None:
        from google.api_core.exceptions import NotFound

        for name in (f"{key}.json", f"{key}.bin"):
            try:
                self._blob(name).delete()
            except NotFound:
                pass

    def evict_expired(self, ttl_seconds: int) -> int:
        # Only the local scratch files of abandoned PUTs; see class docstring.
        return _sweep_dir(self._scratch, ttl_seconds)


_store: Optional[StagingStore] = None


def get_store() -> StagingStore:
    global _store
    if _store is None:
        from config.settings import settings

        uri = settings.drive_upload_staging_uri
        if uri.startswith("gs://"):
            _store = GcsStore.from_uri(uri, settings.drive_upload_temp_dir)
        elif uri:
            raise RuntimeError(
                f"Unsupported DRIVE_UPLOAD_STAGING_URI {uri!r}: use gs://bucket/prefix, "
                "or leave it empty and point DRIVE_UPLOAD_TEMP_DIR at the staging dir."
            )
        else:
            _store = DirectoryStore(settings.drive_upload_temp_dir)
    return _store


# ---------------------------------------------------------------------------
# Phase 1: issue a signed URL
# ---------------------------------------------------------------------------


async def issue_upload(
    base_url: str,
    owner: str,
    client_path: str,
    folder_id: str,
    custom_filename: Optional[str],
    ttl_seconds: int,
) -> UploadTicket:
    """Sign a one-time PUT URL for ``(owner, client_path)``.

    Every call issues a fresh URL. Several may be outstanding for the same
    pair; each writes the same object, and the last PUT wins.
    """
    await asyncio.to_thread(get_store().evict_expired, ttl_seconds)
    start_cleanup_task()

    filename = custom_filename or os.path.basename(client_path) or "upload"
    mime_type, _ = mimetypes.guess_type(filename)
    upload_id = uuid.uuid4().hex
    key = object_key(owner, client_path)
    exp = int(time.time()) + ttl_seconds
    payload = {
        "uid": upload_id,
        "k": key,
        "exp": exp,
        "fn": filename,
        "mt": mime_type or "application/octet-stream",
        "fid": folder_id,
        "cfn": custom_filename,
    }
    token = (
        base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        )
        .decode()
        .rstrip("=")
    )
    query = urlencode({"t": token, "sig": _sign(token.encode())})
    url = f"{base_url.rstrip('/')}/drive-upload?{query}"
    return UploadTicket(
        upload_id=upload_id, key=key, url=url, expires_at=exp, filename=filename
    )


# ---------------------------------------------------------------------------
# PUT endpoint
# ---------------------------------------------------------------------------


def verify_upload_url(token: str, sig: str) -> tuple[bool, str, Optional[dict]]:
    """Verify PUT-URL signature, expiry, and one-time use.

    Returns ``(is_valid, error_message, payload)``. Nothing in the token is
    read before the signature checks out.
    """
    if not _hmac.compare_digest(sig, _sign(token.encode())):
        return False, "Invalid signature", None

    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        upload_id, key, exp_ts = payload["uid"], payload["k"], int(payload["exp"])
    except (ValueError, KeyError, TypeError):
        return False, "Malformed upload token", None

    if not _UPLOAD_ID_RE.match(str(upload_id)) or not _KEY_RE.match(str(key)):
        return False, "Malformed upload token", None

    if time.time() > exp_ts:
        return False, "Upload link has expired", None

    if _consumed_uploads.is_consumed_sync(upload_id):
        return False, "Upload URL already used", None

    _consumed_uploads.consume_sync(upload_id)
    return True, "", payload


def incoming_path(upload_id: str) -> str:
    """Local path the PUT endpoint streams the request body to."""
    return get_store().incoming_path(upload_id)


async def commit_staged(payload: dict, incoming: str, byte_count: int) -> None:
    """Publish a completed PUT so any replica's finalize call can find it."""
    meta = {
        "filename": payload.get("fn") or "upload",
        "mime_type": payload.get("mt") or "application/octet-stream",
        "folder_id": payload.get("fid") or "",
        "custom_filename": payload.get("cfn"),
        "size": byte_count,
        "received_at": time.time(),
    }
    await asyncio.to_thread(get_store().commit, payload["k"], incoming, meta)
    logger.info(
        "Drive upload staged: %s (%d bytes)", str(payload["uid"])[:8], byte_count
    )


# ---------------------------------------------------------------------------
# Phase 2: finalize
# ---------------------------------------------------------------------------


async def find_staged(owner: str, client_path: str) -> Optional[StagedUpload]:
    """The bytes staged for ``(owner, client_path)``, if a PUT completed."""
    from config.settings import settings

    key = object_key(owner, client_path)
    meta = await asyncio.to_thread(get_store().read_meta, key)
    if not meta:
        return None
    try:
        staged = StagedUpload(
            key=key,
            filename=meta["filename"],
            mime_type=meta["mime_type"],
            folder_id=meta.get("folder_id") or "",
            custom_filename=meta.get("custom_filename"),
            size=int(meta.get("size", 0)),
            received_at=float(meta["received_at"]),
        )
    except (KeyError, TypeError, ValueError):
        await discard_staged(key)
        return None
    if time.time() - staged.received_at > settings.drive_upload_ttl_seconds:
        await discard_staged(key)
        return None
    return staged


async def read_staged_bytes(key: str) -> Optional[bytes]:
    if not _KEY_RE.match(key):
        return None
    return await asyncio.to_thread(get_store().read_bytes, key)


async def discard_staged(key: str) -> None:
    """Remove staged bytes and their meta."""
    if _KEY_RE.match(key):
        await asyncio.to_thread(get_store().delete, key)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


async def _cleanup_loop() -> None:
    from config.settings import settings

    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            removed = await asyncio.to_thread(
                get_store().evict_expired, settings.drive_upload_ttl_seconds
            )
            if removed:
                logger.info("Drive upload cleanup: removed %d expired files", removed)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("Drive upload cleanup error: %s", e)


def start_cleanup_task() -> None:
    """Start the background cleanup task (idempotent, no-op without a loop)."""
    global _cleanup_task
    if _cleanup_task is not None and not _cleanup_task.done():
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    _cleanup_task = asyncio.create_task(_cleanup_loop())
    logger.info("Drive upload cleanup task started")


def reset_state() -> None:
    """Clear state (for testing)."""
    _consumed_uploads.clear()
    global _hmac_key_cache, _store
    _hmac_key_cache = None
    _store = None


__all__ = [
    "UploadTicket",
    "StagedUpload",
    "StagingStore",
    "DirectoryStore",
    "GcsStore",
    "staging_owner",
    "object_key",
    "get_store",
    "issue_upload",
    "verify_upload_url",
    "incoming_path",
    "commit_staged",
    "find_staged",
    "read_staged_bytes",
    "discard_staged",
    "start_cleanup_task",
    "reset_state",
]
