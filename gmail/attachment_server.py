"""Secure temporary attachment storage with HMAC-signed download URLs.

Downloads Gmail attachments to a secure temp directory and generates
one-time-use signed URLs for retrieval. URLs expire after a configurable
TTL (default 15 minutes).

Security:
    - HMAC-SHA256 signed URLs (HKDF-derived key, distinct ``info``)
    - One-time use via ``ConsumedTokenStore``
    - Path traversal protection via ``os.path.realpath()``
    - UUID-prefixed filenames prevent collisions and guessing
    - Temp dir with ``0o700`` permissions
    - Eager + lazy file cleanup
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac as _hmac
import os
import time
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from config.enhanced_logging import setup_logger
from middleware.token_store import ConsumedTokenStore

logger = setup_logger()

DEFAULT_TTL_SECONDS = 900  # 15 minutes
CLEANUP_INTERVAL_SECONDS = 300  # 5 minutes
CLEANUP_MAX_AGE_SECONDS = 1200  # 20 minutes

_hmac_key_cache: Optional[bytes] = None
_consumed_downloads = ConsumedTokenStore(
    "attachment-download", default_ttl_seconds=DEFAULT_TTL_SECONDS
)
_cleanup_task: Optional[asyncio.Task] = None


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
        "No .auth_encryption_key found; attachment URLs using random ephemeral key. "
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
        info=b"attachment-download-hmac-v1",
    )
    _hmac_key_cache = hkdf.derive(secret.encode())
    return _hmac_key_cache


def _compute_signature(params: dict) -> str:
    """Compute HMAC-SHA256 over canonical query params (excluding ``sig``)."""
    data = {k: v for k, v in sorted(params.items()) if k != "sig"}
    canonical = "&".join(f"{k}={v}" for k, v in data.items())
    return _hmac.new(_get_hmac_key(), canonical.encode(), hashlib.sha256).hexdigest()


def _get_secure_temp_dir() -> str:
    """Get (and create) the secure temp directory for attachment files."""
    from config.settings import settings

    temp_dir = settings.attachment_temp_dir
    os.makedirs(temp_dir, mode=0o700, exist_ok=True)
    return temp_dir


def save_attachment(raw_bytes: bytes, filename: str) -> str:
    """Save attachment bytes to temp dir with UUID prefix.

    Args:
        raw_bytes: File content.
        filename: Original filename (sanitized).

    Returns:
        file_id: UUID string used to retrieve the file.
    """
    temp_dir = _get_secure_temp_dir()
    file_id = uuid.uuid4().hex
    safe_name = os.path.basename(filename) or "attachment"
    disk_name = f"{file_id}_{safe_name}"
    file_path = os.path.join(temp_dir, disk_name)

    with open(file_path, "wb") as f:
        f.write(raw_bytes)

    logger.info(
        "Attachment saved: %s (%d bytes)", file_id[:8], len(raw_bytes)
    )
    # Ensure cleanup task is running
    try:
        start_cleanup_task()
    except RuntimeError:
        pass  # No event loop yet — cleanup will happen on next save
    return file_id


def get_attachment_path(file_id: str) -> Optional[str]:
    """Resolve file path for a file_id with traversal protection.

    Returns:
        Absolute path if file exists and is within temp dir, else None.
    """
    temp_dir = _get_secure_temp_dir()
    # Find file matching the UUID prefix
    for entry in os.listdir(temp_dir):
        if entry.startswith(file_id):
            candidate = os.path.join(temp_dir, entry)
            resolved = os.path.realpath(candidate)
            if resolved.startswith(os.path.realpath(temp_dir)):
                return resolved
    return None


def cleanup_attachment(file_id: str) -> None:
    """Delete attachment file by file_id."""
    path = get_attachment_path(file_id)
    if path and os.path.exists(path):
        try:
            os.unlink(path)
            logger.debug("Attachment cleaned up: %s", file_id[:8])
        except OSError as e:
            logger.warning("Failed to clean up attachment %s: %s", file_id[:8], e)


def generate_attachment_url(
    base_url: str,
    file_id: str,
    filename: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    """Generate a signed download URL for a temp attachment.

    Args:
        base_url: Server base URL (e.g., ``https://server.example.com``).
        file_id: UUID from ``save_attachment()``.
        filename: Original filename for Content-Disposition.
        ttl_seconds: URL validity period.

    Returns:
        Full signed URL.
    """
    exp = int(time.time()) + ttl_seconds
    params = {
        "fid": file_id,
        "fn": filename,
        "exp": str(exp),
    }
    params["sig"] = _compute_signature(params)
    base = base_url.rstrip("/")
    return f"{base}/attachment-download?{urlencode(params)}"


def verify_attachment_url(
    file_id: str,
    filename: str,
    exp: str,
    sig: str,
) -> tuple[bool, str, str]:
    """Verify an attachment URL's signature, expiry, and one-time use.

    Returns:
        Tuple of (is_valid, file_id, error_message).
    """
    params = {
        "fid": file_id,
        "fn": filename,
        "exp": exp,
    }

    expected_sig = _compute_signature(params)
    if not _hmac.compare_digest(sig, expected_sig):
        return False, file_id, "Invalid signature"

    try:
        exp_ts = int(exp)
    except (ValueError, TypeError):
        return False, file_id, "Invalid expiry"

    if time.time() > exp_ts:
        return False, file_id, "Download link has expired"

    if _consumed_downloads.is_consumed_sync(file_id):
        return False, file_id, "Already downloaded"

    _consumed_downloads.consume_sync(file_id)
    return True, file_id, ""


async def _cleanup_expired_files() -> None:
    """Background task: periodically delete files older than max age."""
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            temp_dir = _get_secure_temp_dir()
            now = time.time()
            count = 0
            for entry in os.listdir(temp_dir):
                path = os.path.join(temp_dir, entry)
                try:
                    if now - os.path.getmtime(path) > CLEANUP_MAX_AGE_SECONDS:
                        os.unlink(path)
                        count += 1
                except OSError:
                    pass
            if count:
                logger.info("Attachment cleanup: removed %d expired files", count)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("Attachment cleanup error: %s", e)


def start_cleanup_task() -> None:
    """Start the background cleanup task (call once at server startup)."""
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_cleanup_expired_files())
        logger.info("Attachment cleanup task started")


def reset_state() -> None:
    """Clear state (for testing)."""
    _consumed_downloads.clear()
    global _hmac_key_cache
    _hmac_key_cache = None


__all__ = [
    "save_attachment",
    "get_attachment_path",
    "cleanup_attachment",
    "generate_attachment_url",
    "verify_attachment_url",
    "start_cleanup_task",
    "reset_state",
    "DEFAULT_TTL_SECONDS",
]
