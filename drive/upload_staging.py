"""Secure staging for client→server→Drive uploads with HMAC-signed PUT URLs.

This is the *inbound* mirror of ``gmail/attachment_server.py``. When
``settings.drive_upload_client_fs`` is enabled, ``upload_to_drive`` cannot
read from the server's local filesystem — the path lives on the client.
Instead the tool issues an HMAC-signed PUT URL; the client uploads file
content there; ``upload_to_drive`` is re-called and finalizes the Drive
upload from the staged bytes.

Security:
    - HMAC-SHA256 signed URLs (HKDF-derived key, distinct ``info`` from
      attachment downloads)
    - One-time use via ``ConsumedTokenStore``
    - UUID-prefixed filenames prevent collisions and guessing
    - Path traversal protection via ``os.path.realpath()``
    - Temp dir with ``0o700`` permissions
    - Eager + lazy file cleanup
    - Allocations bound to ``(session_id, client_path)`` so phase 2 of the
      tool call can locate the staged bytes without an extra parameter
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac as _hmac
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from config.enhanced_logging import setup_logger
from middleware.token_store import ConsumedTokenStore

logger = setup_logger()

CLEANUP_INTERVAL_SECONDS = 300  # 5 minutes
_hmac_key_cache: Optional[bytes] = None
_consumed_uploads = ConsumedTokenStore("drive-upload", default_ttl_seconds=900)
_cleanup_task: Optional[asyncio.Task] = None


@dataclass
class _Allocation:
    upload_id: str
    session_id: str
    client_path: str
    filename: str
    mime_type: str
    folder_id: str
    user_email: str
    custom_filename: Optional[str]
    allocated_at: float = field(default_factory=time.time)
    received: bool = False


# upload_id -> _Allocation
_allocations: dict[str, _Allocation] = {}
# (session_id, client_path) -> upload_id
_session_index: dict[tuple[str, str], str] = {}


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
        "URLs will NOT survive server restarts."
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


def _compute_signature(params: dict) -> str:
    """Compute HMAC-SHA256 over canonical query params (excluding ``sig``)."""
    data = {k: v for k, v in sorted(params.items()) if k != "sig"}
    canonical = "&".join(f"{k}={v}" for k, v in data.items())
    return _hmac.new(_get_hmac_key(), canonical.encode(), hashlib.sha256).hexdigest()


def _get_temp_dir() -> str:
    from config.settings import settings

    temp_dir = settings.drive_upload_temp_dir
    os.makedirs(temp_dir, mode=0o700, exist_ok=True)
    return temp_dir


def allocate_upload(
    session_id: str,
    client_path: str,
    user_email: str,
    folder_id: str,
    custom_filename: Optional[str],
) -> _Allocation:
    """Reserve an upload slot for a (session_id, client_path) tuple.

    If an allocation already exists for the same tuple and hasn't received
    bytes yet, it is returned as-is (idempotent re-issue). If it already
    received bytes, the existing allocation is returned so the tool can
    finalize. If it expired, a fresh allocation replaces it.
    """
    import mimetypes

    _evict_expired()

    key = (session_id, client_path)
    existing_id = _session_index.get(key)
    if existing_id and existing_id in _allocations:
        return _allocations[existing_id]

    upload_id = uuid.uuid4().hex
    filename = custom_filename or os.path.basename(client_path) or "upload"
    mime_type, _ = mimetypes.guess_type(filename)
    alloc = _Allocation(
        upload_id=upload_id,
        session_id=session_id,
        client_path=client_path,
        filename=filename,
        mime_type=mime_type or "application/octet-stream",
        folder_id=folder_id,
        user_email=user_email,
        custom_filename=custom_filename,
    )
    _allocations[upload_id] = alloc
    _session_index[key] = upload_id

    try:
        start_cleanup_task()
    except RuntimeError:
        pass
    return alloc


def get_allocation(upload_id: str) -> Optional[_Allocation]:
    return _allocations.get(upload_id)


def find_allocation_by_path(session_id: str, client_path: str) -> Optional[_Allocation]:
    """Look up an allocation by (session_id, client_path)."""
    upload_id = _session_index.get((session_id, client_path))
    if not upload_id:
        return None
    return _allocations.get(upload_id)


def generate_upload_url(
    base_url: str,
    upload_id: str,
    ttl_seconds: int,
) -> tuple[str, int]:
    """Generate a signed PUT URL for a staged upload allocation.

    Returns:
        (url, exp_timestamp)
    """
    exp = int(time.time()) + ttl_seconds
    params = {
        "uid": upload_id,
        "exp": str(exp),
    }
    params["sig"] = _compute_signature(params)
    base = base_url.rstrip("/")
    return f"{base}/drive-upload?{urlencode(params)}", exp


def verify_upload_url(
    upload_id: str, exp: str, sig: str
) -> tuple[bool, str, Optional[_Allocation]]:
    """Verify PUT-URL signature, expiry, and one-time use.

    Returns ``(is_valid, error_message, allocation)``. The allocation
    reference is captured *before* the token is consumed, so a TTL
    eviction firing between this call and the endpoint's use of the
    allocation cannot strand a consumed token without an allocation.
    """
    params = {"uid": upload_id, "exp": exp}
    expected = _compute_signature(params)
    if not _hmac.compare_digest(sig, expected):
        return False, "Invalid signature", None

    try:
        exp_ts = int(exp)
    except (ValueError, TypeError):
        return False, "Invalid expiry", None

    if time.time() > exp_ts:
        return False, "Upload link has expired", None

    if _consumed_uploads.is_consumed_sync(upload_id):
        return False, "Upload URL already used", None

    alloc = _allocations.get(upload_id)
    if alloc is None:
        return False, "Unknown upload id", None

    _consumed_uploads.consume_sync(upload_id)
    return True, "", alloc


def staged_path(upload_id: str) -> str:
    """Return the on-disk path where bytes for this upload are stored."""
    temp_dir = _get_temp_dir()
    alloc = _allocations.get(upload_id)
    suffix = alloc.filename if alloc else "upload"
    safe_suffix = os.path.basename(suffix).replace("/", "_") or "upload"
    return os.path.join(temp_dir, f"{upload_id}_{safe_suffix}")


def mark_received(upload_id: str, byte_count: int) -> None:
    alloc = _allocations.get(upload_id)
    if alloc:
        alloc.received = True
        logger.info(
            "Drive upload staged: %s (%d bytes) for %s",
            upload_id[:8],
            byte_count,
            alloc.user_email,
        )


def read_staged_bytes(upload_id: str) -> Optional[bytes]:
    """Read the staged bytes for a finalized upload."""
    alloc = _allocations.get(upload_id)
    if not alloc or not alloc.received:
        return None
    path = staged_path(upload_id)
    resolved = os.path.realpath(path)
    temp_dir = os.path.realpath(_get_temp_dir())
    if not resolved.startswith(temp_dir):
        return None
    if not os.path.exists(resolved):
        return None
    with open(resolved, "rb") as f:
        return f.read()


def consume_allocation(upload_id: str) -> None:
    """Remove allocation, session-index entry, and on-disk file."""
    alloc = _allocations.pop(upload_id, None)
    if alloc:
        _session_index.pop((alloc.session_id, alloc.client_path), None)
    path = staged_path(upload_id)
    try:
        if os.path.exists(path):
            os.unlink(path)
    except OSError as e:
        logger.warning("Failed to clean up staged upload %s: %s", upload_id[:8], e)


def _evict_expired() -> int:
    """Drop allocations + files older than the configured TTL."""
    from config.settings import settings

    ttl = settings.drive_upload_ttl_seconds
    now = time.time()
    expired = [
        uid for uid, alloc in _allocations.items() if now - alloc.allocated_at > ttl
    ]
    for uid in expired:
        consume_allocation(uid)
    if expired:
        logger.info(
            "Drive upload cleanup: removed %d expired allocations", len(expired)
        )
    return len(expired)


async def _cleanup_loop() -> None:
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            _evict_expired()
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
    _allocations.clear()
    _session_index.clear()
    global _hmac_key_cache
    _hmac_key_cache = None


__all__ = [
    "allocate_upload",
    "get_allocation",
    "find_allocation_by_path",
    "generate_upload_url",
    "verify_upload_url",
    "staged_path",
    "mark_received",
    "read_staged_bytes",
    "consume_allocation",
    "start_cleanup_task",
    "reset_state",
]
