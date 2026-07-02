"""Short-lived HMAC action tokens for server-rendered pages.

The OAuth success / settings pages are rendered server-side for an already
authenticated user, then make browser `fetch()` calls to state-changing
endpoints (``/api/revoke``, ``/api/sampling-config``, ``/api/privacy-mode``).
Those endpoints previously trusted the ``user_email`` in the request body with
no proof of ownership, so any anonymous caller could target any email.

This module issues a token bound to ``(purpose, subject_email, exp)`` and signed
with an HKDF-derived key from the server secret — the same primitive used by
``gmail/email_feedback/urls.py`` and payment receipts, with a distinct ``info``.
The page embeds the token; the endpoint verifies it (or accepts a per-user API
key Bearer that owns the target email — see ``authorize_action`` callers).

Tokens are stateless (no server storage) and expire quickly (default 1 hour),
which is ample for a page the user has open right after authenticating.
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
import time
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from config.enhanced_logging import setup_logger
from config.settings import settings

logger = setup_logger()

DEFAULT_TTL_SECONDS = 3600  # 1 hour — page is used right after auth

_hmac_key_cache: Optional[bytes] = None


def _get_server_secret() -> bytes:
    """Read the shared server secret (same file AuthMiddleware uses)."""
    secret_path = Path(settings.credentials_dir) / ".auth_encryption_key"
    if secret_path.exists():
        return secret_path.read_bytes().strip()
    import secrets as _secrets

    logger.warning(
        "No .auth_encryption_key found; action tokens using an ephemeral key "
        "(will not survive restarts)."
    )
    return _secrets.token_bytes(32)


def _get_hmac_key() -> bytes:
    global _hmac_key_cache
    if _hmac_key_cache is not None:
        return _hmac_key_cache
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"mcp-google-workspace-v1",
        info=b"action-token-hmac-v1",
    )
    _hmac_key_cache = hkdf.derive(_get_server_secret())
    return _hmac_key_cache


def _canonical(purpose: str, subject: str, exp: str) -> bytes:
    return f"{purpose}\n{subject.lower().strip()}\n{exp}".encode()


def sign_action_token(
    purpose: str, subject_email: str, ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> str:
    """Return ``<exp>.<hex_sig>`` binding an action to a subject email."""
    exp = str(int(time.time()) + ttl_seconds)
    sig = _hmac.new(
        _get_hmac_key(), _canonical(purpose, subject_email, exp), hashlib.sha256
    ).hexdigest()
    return f"{exp}.{sig}"


def verify_action_token(token: str, purpose: str, subject_email: str) -> bool:
    """Timing-safe verify of a token for ``(purpose, subject_email)``."""
    if not token or "." not in token:
        return False
    exp, _, sig = token.partition(".")
    try:
        if time.time() > int(exp):
            return False
    except (ValueError, TypeError):
        return False
    expected = _hmac.new(
        _get_hmac_key(), _canonical(purpose, subject_email, exp), hashlib.sha256
    ).hexdigest()
    return _hmac.compare_digest(sig, expected)


def sign_payload(purpose: str, parts: list[str]) -> str:
    """HMAC-sign an ordered list of string parts under a purpose (no expiry).

    Used for long-lived signed links (e.g. card-feedback buttons) where the
    signature binds the request parameters so they cannot be forged/tampered.
    """
    canonical = (purpose + "\n" + "\n".join((p or "").strip() for p in parts)).encode()
    return _hmac.new(_get_hmac_key(), canonical, hashlib.sha256).hexdigest()


def verify_payload(sig: str, purpose: str, parts: list[str]) -> bool:
    """Timing-safe verify of :func:`sign_payload`."""
    return _hmac.compare_digest(sig or "", sign_payload(purpose, parts))


def authorize_action(
    request,
    purpose: str,
    subject: str,
    *,
    body_token: str = "",
    subject_is_email: bool = True,
) -> tuple[bool, str]:
    """Authorize a state-changing request bound to ``subject``.

    ``subject`` is whatever the endpoint acts on — a target email (e.g. revoke)
    or a session id (e.g. privacy-mode / sampling-config).

    Accepts EITHER:
      1. A valid signed action token (``X-Action-Token`` header, or ``body_token``
         which the caller lifts from the JSON body) bound to ``(purpose, subject)``, OR
      2. When ``subject_is_email``: an ``Authorization: Bearer <per-user-api-key>``
         whose key resolves to an email that owns ``subject`` (self or a linked
         account).

    Returns ``(authorized, reason)``. ``reason`` is for logging only.
    """
    subj = (subject or "").strip()
    if not subj:
        return False, "no subject"

    # 1. Signed action token (header preferred, then body)
    token = request.headers.get("X-Action-Token") or body_token or ""
    if token and verify_action_token(token, purpose, subj):
        return True, "signed action token"

    # 2. Per-user API key Bearer that owns the subject email
    if subject_is_email:
        authz = request.headers.get("Authorization", "")
        if authz.startswith("Bearer "):
            key = authz[len("Bearer ") :].strip()
            try:
                from auth.user_api_keys import get_accessible_emails, lookup_key

                owner = lookup_key(key)
                if owner and subj.lower() in {
                    e.lower().strip() for e in get_accessible_emails(owner)
                }:
                    return True, "per-user api key ownership"
            except Exception as e:  # pragma: no cover - defensive
                logger.debug(f"action authz bearer check failed: {e}")

    return False, "no valid action token or owning bearer key"


__all__ = [
    "sign_action_token",
    "verify_action_token",
    "authorize_action",
    "DEFAULT_TTL_SECONDS",
]
