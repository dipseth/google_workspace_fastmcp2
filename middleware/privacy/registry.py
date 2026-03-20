"""Vault lifecycle management — session → PrivacyVault registry.

Thread-safe module-level registry.  Vaults are lazily created on first tool
response that needs privacy and destroyed when the session expires.
"""

from __future__ import annotations

import threading
from typing import Optional

from config.enhanced_logging import setup_logger
from middleware.privacy.vault import PrivacyVault

logger = setup_logger()

_vault_registry: dict[str, PrivacyVault] = {}
_registry_lock = threading.Lock()

def get_or_create_vault(session_id: str, fernet_key: bytes) -> PrivacyVault:
    """Return existing vault for *session_id* or create a new one."""
    with _registry_lock:
        vault = _vault_registry.get(session_id)
        if vault is not None:
            return vault
        vault = PrivacyVault(session_id, fernet_key)
        _vault_registry[session_id] = vault
        logger.info("Privacy vault created for session %s", session_id)
        return vault

def get_vault(session_id: str) -> Optional[PrivacyVault]:
    """Return the vault for *session_id* if it exists, else ``None``."""
    with _registry_lock:
        return _vault_registry.get(session_id)

def destroy_vault(session_id: str) -> None:
    """Destroy and remove the vault for *session_id*."""
    with _registry_lock:
        vault = _vault_registry.pop(session_id, None)
    if vault is not None:
        vault.destroy()
        logger.info("Privacy vault destroyed for session %s", session_id)

def cleanup_expired_vaults(active_session_ids: set[str]) -> int:
    """Remove vaults whose sessions are no longer active.

    Called from ``auth.context.cleanup_expired_sessions`` so vault lifetime
    is tied to session lifetime.

    Returns:
        Number of vaults cleaned up.
    """
    to_remove: list[str] = []
    with _registry_lock:
        for sid in list(_vault_registry):
            if sid not in active_session_ids:
                to_remove.append(sid)
        removed_vaults = [_vault_registry.pop(sid) for sid in to_remove]

    for vault in removed_vaults:
        vault.destroy()

    if to_remove:
        logger.info("Cleaned up %d expired privacy vaults", len(to_remove))
    return len(to_remove)
