"""Payment receipt creation and HMAC verification.

Creates HMAC-signed receipts that cryptographically bind x402 payments
to the authenticated user identity.  Reuses the same server secret as
``AuthMiddleware`` (the ``.auth_encryption_key`` file) but derives a
distinct HMAC key via HKDF with ``info=b"payment-receipt-hmac-v1"``.
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
import json
import time
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from config.enhanced_logging import setup_logger
from middleware.payment.types import PayerIdentity, PaymentReceipt

logger = setup_logger()

# Cache the derived HMAC key so we only read the file + run HKDF once.
_hmac_key_cache: Optional[bytes] = None


def _get_server_secret() -> str:
    """Read the server secret from ``.auth_encryption_key``.

    Same file that ``AuthMiddleware._get_server_secret()`` uses.

    Raises:
        RuntimeError: If the key file does not exist. Receipt HMAC
            must never operate with a hardcoded/fallback key.
    """
    secret_path = Path(".auth_encryption_key")
    if secret_path.exists():
        secret = secret_path.read_text().strip()
        if not secret:
            raise RuntimeError(
                "Payment receipts require a non-empty .auth_encryption_key file. "
                'Generate one with: python -c "import secrets; print(secrets.token_hex(32))" > .auth_encryption_key'
            )
        return secret
    raise RuntimeError(
        "Payment receipts require .auth_encryption_key but the file does not exist. "
        'Generate one with: python -c "import secrets; print(secrets.token_hex(32))" > .auth_encryption_key'
    )


def _get_hmac_key() -> bytes:
    """Derive a 32-byte HMAC key from the server secret via HKDF-SHA256.

    Uses ``info=b"payment-receipt-hmac-v1"`` to produce a key distinct
    from the credential-encryption key derived by AuthMiddleware.
    """
    global _hmac_key_cache
    if _hmac_key_cache is not None:
        return _hmac_key_cache

    secret = _get_server_secret()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"mcp-google-workspace-v1",
        info=b"payment-receipt-hmac-v1",
    )
    _hmac_key_cache = hkdf.derive(secret.encode())
    return _hmac_key_cache


def compute_receipt_hmac(receipt_dict: dict) -> str:
    """Compute HMAC-SHA256 over a receipt dict (excluding the ``hmac`` field).

    The dict is JSON-serialized with sorted keys for canonical form.
    """
    data = {k: v for k, v in receipt_dict.items() if k != "hmac"}
    canonical = json.dumps(data, sort_keys=True, default=str)
    return _hmac.new(_get_hmac_key(), canonical.encode(), hashlib.sha256).hexdigest()


def verify_receipt_hmac(receipt: PaymentReceipt) -> bool:
    """Verify that a receipt's HMAC is valid."""
    if not receipt.hmac:
        return False
    expected = compute_receipt_hmac(receipt.model_dump())
    return _hmac.compare_digest(receipt.hmac, expected)


def build_payer_identity(session_id: str, wallet_address: str) -> PayerIdentity:
    """Build a PayerIdentity from session data and on-chain wallet address."""
    user_email = None
    google_sub = None
    auth_provenance = None

    try:
        from auth.context import get_session_data
        from auth.types import SessionKey

        user_email = get_session_data(session_id, SessionKey.USER_EMAIL, default=None)
        google_sub = get_session_data(session_id, SessionKey.GOOGLE_SUB, default=None)
        provenance = get_session_data(
            session_id, SessionKey.AUTH_PROVENANCE, default=None
        )
        auth_provenance = str(provenance) if provenance else None
    except Exception:
        pass

    return PayerIdentity(
        wallet_address=wallet_address,
        user_email=user_email,
        google_sub=google_sub,
        auth_provenance=auth_provenance,
    )


def hash_email(email: str) -> str:
    """SHA-256 hash of an email, truncated to 16 hex chars.

    Safe for on-chain/facilitator metadata — not reversible.
    """
    if not email:
        return ""
    return hashlib.sha256(email.lower().encode()).hexdigest()[:16]


def create_payment_receipt(
    payer: PayerIdentity,
    tool_name: str,
    amount: str,
    network: str,
    tx_hash: str,
    ttl_seconds: int,
    resource_url: str = "",
) -> PaymentReceipt:
    """Create an HMAC-signed payment receipt."""
    now = time.time()
    receipt = PaymentReceipt(
        payer=payer,
        tool_name=tool_name,
        amount=amount,
        network=network,
        tx_hash=tx_hash,
        verified_at=now,
        expires_at=now + ttl_seconds,
        resource_url=resource_url,
    )
    receipt.hmac = compute_receipt_hmac(receipt.model_dump())

    # Fire-and-forget: store receipt in Qdrant for audit/analytics
    try:
        from middleware.payment.receipt_store import store_receipt_async

        store_receipt_async(receipt.model_dump())
    except Exception:
        pass  # Never block payment flow on storage

    return receipt
