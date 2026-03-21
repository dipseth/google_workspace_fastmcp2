"""Payment flow URL generation and verification for browser/email payment UX.

Generates HMAC-signed payment tokens that bind a payment request to a specific
MCP session, tool, and amount. Mirrors the pattern in ``gmail/email_feedback/urls.py``.

URL structure:
    https://server/pay?sid=<session_prefix>&tool=<tool_name>&amt=<usdc_amount>&
    net=<network>&exp=<unix_ts>&sig=<hmac_hex>

Completion callback:
    POST /api/payment-complete?token=<payment_token>
    Body: { "payload_b64": "<base64 x402 signed payload>" }

Security features:
    - HKDF-SHA256 key derivation with ``info=b"payment-flow-hmac-v1"``
    - HMAC-SHA256 signature over canonical query params
    - TTL expiry (default 15 minutes)
    - One-time use (tracked in Redis or in-memory)
    - Timing-safe comparison via ``hmac.compare_digest()``
"""

from __future__ import annotations

import asyncio
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

_consumed_tokens = ConsumedTokenStore("payment", default_ttl_seconds=900)

# In-memory store for pending payment completions.
# Key: payment_token (sig), Value: asyncio.Event + payload data.
# In production, this is backed by Redis pub/sub.
_pending_payments: dict[str, dict] = {}


def _get_server_secret() -> str:
    """Read the server secret from ``.auth_encryption_key``.

    Raises:
        RuntimeError: If the key file does not exist. Payment flow
            must never operate with a hardcoded/fallback key.
    """
    secret_path = Path(".auth_encryption_key")
    if secret_path.exists():
        secret = secret_path.read_text().strip()
        if not secret:
            raise RuntimeError(
                "Payment flow requires a non-empty .auth_encryption_key file. "
                'Generate one with: python -c "import secrets; print(secrets.token_hex(32))" > .auth_encryption_key'
            )
        return secret
    raise RuntimeError(
        "Payment flow requires .auth_encryption_key but the file does not exist. "
        'Generate one with: python -c "import secrets; print(secrets.token_hex(32))" > .auth_encryption_key'
    )


def _get_hmac_key() -> bytes:
    """Derive a 32-byte HMAC key via HKDF-SHA256.

    Uses ``info=b"payment-flow-hmac-v1"`` to produce a key distinct
    from payment receipts, credential encryption, and email feedback.
    """
    global _hmac_key_cache
    if _hmac_key_cache is not None:
        return _hmac_key_cache

    secret = _get_server_secret()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"mcp-google-workspace-v1",
        info=b"payment-flow-hmac-v1",
    )
    _hmac_key_cache = hkdf.derive(secret.encode())
    return _hmac_key_cache


def _compute_signature(params: dict) -> str:
    """Compute HMAC-SHA256 over canonical query params (excluding ``sig``)."""
    data = {k: v for k, v in sorted(params.items()) if k != "sig"}
    canonical = "&".join(f"{k}={v}" for k, v in data.items())
    return _hmac.new(_get_hmac_key(), canonical.encode(), hashlib.sha256).hexdigest()


def generate_payment_url(
    base_url: str,
    session_id: str,
    tool_name: str,
    amount: str,
    network: str,
    recipient_wallet: str,
    chain_id: int,
    ttl_seconds: int = 900,
) -> str:
    """Generate a signed payment URL for the browser payment page.

    Args:
        base_url: Server base URL (e.g., ``https://server.example.com``).
        session_id: MCP session identifier.
        tool_name: Tool that triggered the payment requirement.
        amount: USDC amount required (human-readable, e.g., "0.01").
        network: CAIP-2 network identifier (e.g., "eip155:8453").
        recipient_wallet: Wallet address to receive payment.
        chain_id: Blockchain chain ID.
        ttl_seconds: URL validity period in seconds (default: 15 min).

    Returns:
        Full signed URL ready for browser redirect or email button.
    """
    exp = int(time.time()) + ttl_seconds
    params = {
        "sid": session_id[:16] if session_id else "anonymous",
        "tool": tool_name,
        "amt": amount,
        "net": network,
        "to": recipient_wallet,
        "cid": str(chain_id),
        "exp": str(exp),
    }
    params["sig"] = _compute_signature(params)

    base = base_url.rstrip("/")
    return f"{base}/pay?{urlencode(params)}"


def generate_payment_token(
    session_id: str,
    tool_name: str,
    amount: str,
    network: str,
    ttl_seconds: int = 900,
) -> str:
    """Generate a standalone HMAC token for payment completion callback.

    This token is used as the key for the /api/payment-complete endpoint.
    The browser payment page posts the x402 signed payload to this endpoint
    with this token, linking the browser payment back to the MCP session.

    Returns:
        HMAC signature string (hex) that serves as the payment token.
    """
    exp = int(time.time()) + ttl_seconds
    params = {
        "sid": session_id[:16] if session_id else "anonymous",
        "tool": tool_name,
        "amt": amount,
        "net": network,
        "exp": str(exp),
    }
    return _compute_signature(params)


def verify_payment_token(
    session_id: str,
    tool_name: str,
    amount: str,
    network: str,
    exp: str,
    sig: str,
    recipient_wallet: str = "",
    chain_id: str = "",
    consume: bool = True,
) -> tuple[bool, str]:
    """Verify a payment URL's signature, expiry, and one-time use.

    All params must match what was used in ``generate_payment_url()``.

    Returns:
        Tuple of (is_valid, error_message). On success, error_message is "".
    """
    params = {
        "sid": session_id[:16] if session_id else "anonymous",
        "tool": tool_name,
        "amt": amount,
        "net": network,
        "to": recipient_wallet,
        "cid": chain_id,
        "exp": exp,
    }

    # Verify signature (timing-safe)
    expected_sig = _compute_signature(params)
    if not _hmac.compare_digest(sig, expected_sig):
        logger.warning("Invalid payment flow signature for session %s", session_id[:8])
        return False, "Invalid signature"

    # Check expiry
    try:
        exp_ts = int(exp)
    except (ValueError, TypeError):
        return False, "Invalid expiry"

    if time.time() > exp_ts:
        logger.info("Expired payment token for session %s", session_id[:8])
        return False, "Payment link has expired"

    # Check one-time use
    token_key = f"{session_id}:{tool_name}:{amount}:{exp}"
    if token_key in _consumed_tokens:
        logger.info("Already consumed payment token for session %s", session_id[:8])
        return False, "Payment already processed"

    if consume:
        _consumed_tokens.add(token_key)

    return True, ""


# ---------------------------------------------------------------------------
# Pending payment tracking (in-memory for POC, Redis for production)
# ---------------------------------------------------------------------------


def register_pending_payment(payment_token: str, session_id: str) -> asyncio.Event:
    """Register a pending payment and return an Event to await completion.

    The middleware calls this before opening the browser/sending email,
    then awaits the returned Event. When the browser POSTs to
    /api/payment-complete, the endpoint calls ``complete_pending_payment()``
    which sets the Event and stores the x402 payload.
    """
    event = asyncio.Event()
    _pending_payments[payment_token] = {
        "event": event,
        "session_id": session_id,
        "payload_b64": None,
        "completed_at": None,
    }
    return event


def complete_pending_payment(payment_token: str, payload_b64: str) -> bool:
    """Called by /api/payment-complete when browser payment finishes.

    Stores the x402 signed payload and signals the waiting middleware.

    Returns:
        True if the token was found and completed, False otherwise.
    """
    pending = _pending_payments.get(payment_token)
    if not pending:
        logger.warning(
            "Payment completion for unknown token: %s...", payment_token[:16]
        )
        return False

    pending["payload_b64"] = payload_b64
    pending["completed_at"] = time.time()
    pending["event"].set()
    logger.info("Payment completed for token %s...", payment_token[:16])
    return True


def get_pending_payment(payment_token: str) -> Optional[dict]:
    """Retrieve pending payment data (including the x402 payload after completion)."""
    return _pending_payments.get(payment_token)


def cleanup_pending_payment(payment_token: str) -> None:
    """Remove a pending payment entry after processing."""
    _pending_payments.pop(payment_token, None)


def reset_state() -> None:
    """Clear all state (for testing)."""
    _consumed_tokens.clear()
    _pending_payments.clear()
    global _hmac_key_cache
    _hmac_key_cache = None


__all__ = [
    "generate_payment_url",
    "generate_payment_token",
    "verify_payment_token",
    "register_pending_payment",
    "complete_pending_payment",
    "get_pending_payment",
    "cleanup_pending_payment",
    "reset_state",
]
