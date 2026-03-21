"""
Signed redirect URL generation and verification for email feedback buttons.

Uses HMAC-SHA256 with HKDF-derived keys (same server secret as auth/payment)
but with a distinct ``info`` parameter for email feedback.

URL structure:
    https://server/email-feedback?eid=<email_id>&action=<positive|negative>&
    type=<content|layout>&exp=<unix_ts>&sig=<hmac_hex>

Security features:
    - HKDF-SHA256 key derivation with ``info=b"email-feedback-hmac-v1"``
    - HMAC-SHA256 signature over canonical query params
    - TTL expiry (default 30 days)
    - One-time use (tracked via consumed token set)
    - Timing-safe comparison via ``hmac.compare_digest()``
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from config.enhanced_logging import setup_logger

logger = setup_logger()

# Cache derived HMAC key (read file + HKDF once per process)
_hmac_key_cache: Optional[bytes] = None

# One-time-use token tracking (Redis-backed with in-memory fallback).
from middleware.token_store import ConsumedTokenStore

_consumed_tokens = ConsumedTokenStore("email-feedback", default_ttl_seconds=30 * 24 * 3600)

# Default TTL: 30 days
DEFAULT_TTL_SECONDS = 30 * 24 * 3600


def _get_server_secret() -> str:
    """Read the server secret from ``.auth_encryption_key``.

    Same file that ``AuthMiddleware._get_server_secret()`` and
    ``payment/receipt.py`` use.
    """
    secret_path = Path(".auth_encryption_key")
    if secret_path.exists():
        return secret_path.read_text().strip()
    import secrets as _secrets

    fallback = _secrets.token_urlsafe(32)
    logger.warning(
        "No .auth_encryption_key found; email feedback HMAC using random ephemeral key. "
        "Feedback URLs will NOT survive server restarts. "
        "Create .auth_encryption_key for persistent HMAC signing."
    )
    return fallback


def _get_hmac_key() -> bytes:
    """Derive a 32-byte HMAC key via HKDF-SHA256.

    Uses ``info=b"email-feedback-hmac-v1"`` to produce a key distinct
    from payment receipts and credential encryption.
    """
    global _hmac_key_cache
    if _hmac_key_cache is not None:
        return _hmac_key_cache

    secret = _get_server_secret()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"mcp-google-workspace-v1",
        info=b"email-feedback-hmac-v1",
    )
    _hmac_key_cache = hkdf.derive(secret.encode())
    return _hmac_key_cache


def _compute_signature(params: dict) -> str:
    """Compute HMAC-SHA256 over canonical query params (excluding ``sig``)."""
    data = {k: v for k, v in sorted(params.items()) if k != "sig"}
    canonical = "&".join(f"{k}={v}" for k, v in data.items())
    return _hmac.new(_get_hmac_key(), canonical.encode(), hashlib.sha256).hexdigest()


def generate_feedback_url(
    base_url: str,
    email_id: str,
    action: str,
    feedback_type: str = "content",
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    """Generate a signed redirect URL for an email feedback button.

    Args:
        base_url: Server base URL (e.g., ``https://server.example.com``).
        email_id: Unique identifier for the email/pattern.
        action: Feedback action — ``"positive"`` or ``"negative"``.
        feedback_type: ``"content"`` (rates data accuracy) or
            ``"layout"`` (rates formatting/design).
        ttl_seconds: URL validity period in seconds.

    Returns:
        Full signed URL ready to use as ``ButtonBlock.url``.
    """
    exp = int(time.time()) + ttl_seconds
    params = {
        "eid": email_id,
        "action": action,
        "type": feedback_type,
        "exp": str(exp),
    }
    params["sig"] = _compute_signature(params)

    # Strip trailing slash from base_url
    base = base_url.rstrip("/")
    return f"{base}/email-feedback?{urlencode(params)}"


def verify_feedback_url(
    email_id: str,
    action: str,
    feedback_type: str,
    exp: str,
    sig: str,
    consume: bool = True,
) -> tuple[bool, str]:
    """Verify a feedback URL's signature, expiry, and one-time use.

    Args:
        email_id: The ``eid`` query param.
        action: The ``action`` query param.
        feedback_type: The ``type`` query param.
        exp: The ``exp`` query param (unix timestamp string).
        sig: The ``sig`` query param (HMAC hex digest).
        consume: If True, mark the token as consumed (one-time use).

    Returns:
        Tuple of (is_valid, error_message). On success, error_message is "".
    """
    # Reconstruct params for signature verification
    params = {
        "eid": email_id,
        "action": action,
        "type": feedback_type,
        "exp": exp,
    }

    # Verify signature (timing-safe)
    expected_sig = _compute_signature(params)
    if not _hmac.compare_digest(sig, expected_sig):
        logger.warning(f"Invalid feedback signature for email {email_id[:8]}...")
        return False, "Invalid signature"

    # Check expiry
    try:
        exp_ts = int(exp)
    except (ValueError, TypeError):
        return False, "Invalid expiry"

    if time.time() > exp_ts:
        logger.info(f"Expired feedback token for email {email_id[:8]}...")
        return False, "Feedback link has expired"

    # Check one-time use
    token_key = f"{email_id}:{action}:{feedback_type}:{exp}"
    if token_key in _consumed_tokens:
        logger.info(f"Already consumed feedback token for email {email_id[:8]}...")
        return False, "Feedback already recorded"

    # Mark as consumed
    if consume:
        _consumed_tokens.add(token_key)

    return True, ""


def reset_consumed_tokens() -> None:
    """Clear consumed token cache (for testing)."""
    _consumed_tokens.clear()


__all__ = [
    "generate_feedback_url",
    "verify_feedback_url",
    "reset_consumed_tokens",
    "DEFAULT_TTL_SECONDS",
]
