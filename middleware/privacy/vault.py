"""PrivacyVault — per-session encrypted store for sensitive values.

Each vault is bound to a session via an HKDF-derived Fernet key.  Values are
encrypted on ingestion and can only be decrypted within the same session.
Deduplication uses a keyed HMAC so the same plaintext always maps to the same
token within a session, but cross-session correlation is infeasible.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import threading
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken

from config.enhanced_logging import setup_logger

logger = setup_logger()

def derive_privacy_vault_key(
    session_id: str,
    auth_material: bytes,
    server_secret: bytes,
) -> bytes:
    """Derive a Fernet key for a privacy vault.

    Domain-separated from credential encryption via a distinct HKDF info tag.

    Args:
        session_id: Current MCP session identifier.
        auth_material: Bearer token bytes or random seed.
        server_secret: Server-side secret from ``.auth_encryption_key``.

    Returns:
        Base64url-encoded 32-byte key suitable for ``Fernet(key)``.
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=server_secret + session_id.encode(),
        info=b"privacy-vault-v1",
    )
    return base64.urlsafe_b64encode(hkdf.derive(auth_material))

class PrivacyVault:
    """Per-session store mapping opaque tokens to Fernet-encrypted ciphertexts.

    Thread-safe: all mutable state is guarded by ``_lock``.
    """

    __slots__ = (
        "_session_id",
        "_fernet",
        "_fernet_key_bytes",
        "_token_counter",
        "_store",
        "_type_hints",
        "_dedup_index",
        "_created_at",
        "_lock",
    )

    def __init__(self, session_id: str, fernet_key: bytes) -> None:
        self._session_id = session_id
        self._fernet = Fernet(fernet_key)
        # Store as mutable bytearray so destroy() can safely zero the key
        self._fernet_key_bytes = bytearray(fernet_key)
        self._token_counter = 0
        self._store: dict[str, bytes] = {}
        self._type_hints: dict[str, str] = {}
        self._dedup_index: dict[str, str] = {}
        self._created_at = datetime.now(timezone.utc)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encrypt_and_store(self, value: str, type_hint: str = "") -> str:
        """Encrypt *value*, store the ciphertext, return ``[PRIVATE:token_N]``.

        If the same *value* was already encrypted in this vault, the existing
        token is returned (dedup via keyed HMAC).
        """
        dedup_key = self._hmac_value(value)

        with self._lock:
            existing = self._dedup_index.get(dedup_key)
            if existing is not None:
                return f"[PRIVATE:{existing}]"

            token_id = f"token_{self._token_counter}"
            self._token_counter += 1

            ciphertext = self._fernet.encrypt(value.encode("utf-8"))
            self._store[token_id] = ciphertext
            if type_hint:
                self._type_hints[token_id] = type_hint
            self._dedup_index[dedup_key] = token_id

        return f"[PRIVATE:{token_id}]"

    def get_ciphertext_b64(self, token_id: str) -> str | None:
        """Return the base64-encoded ciphertext for *token_id*, or ``None``."""
        with self._lock:
            ct = self._store.get(token_id)
        if ct is None:
            return None
        return ct.decode("ascii") if isinstance(ct, bytes) else ct

    def decrypt(self, token_id: str) -> str | None:
        """Decrypt the ciphertext for *token_id*, returning plaintext or ``None``."""
        with self._lock:
            ct = self._store.get(token_id)
        if ct is None:
            logger.warning(
                "Privacy vault: unknown token %s (session=%s)",
                token_id,
                self._session_id,
            )
            return None
        try:
            return self._fernet.decrypt(ct).decode("utf-8")
        except InvalidToken:
            logger.error(
                "Privacy vault: decrypt failed for %s (session=%s)",
                token_id,
                self._session_id,
            )
            return None

    def stats(self) -> dict:
        """Return instrumentation dict for ``result.meta.privacy``."""
        with self._lock:
            return {
                "mode": "encrypted",
                "tokens_created": self._token_counter,
                "vault_size": len(self._store),
                "session_id": self._session_id,
                "created_at": self._created_at.isoformat(),
            }

    @property
    def session_id(self) -> str:
        return self._session_id

    def destroy(self) -> None:
        """Wipe vault state.  Zero the key bytearray and clear all stores."""
        with self._lock:
            self._store.clear()
            self._type_hints.clear()
            self._dedup_index.clear()
            # Zero the mutable key bytearray in-place (safe, no ctypes needed)
            for i in range(len(self._fernet_key_bytes)):
                self._fernet_key_bytes[i] = 0

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _hmac_value(self, value: str) -> str:
        """Keyed HMAC for dedup — prevents cross-session correlation."""
        return hmac.new(
            self._fernet_key_bytes,
            value.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
