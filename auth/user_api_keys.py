"""Per-user API key management for MCP credential access.

When a user completes OAuth, the server generates a unique API key tied to
that user's email. The key can be used as ``Authorization: Bearer <key>``
to connect to the MCP server and automatically resolve to that user's
credentials — no separate ``start_google_auth`` step needed.

Account linking:
When a user authenticates a second email in a session that was started with
a per-user key, the two emails are linked bidirectionally.  Either key can
then access credentials for both accounts.

Security model:
- Keys are generated via ``secrets.token_urlsafe(32)``
- Only the SHA-256 hash of the key is stored on disk
- The plaintext key is returned once to the user (in the OAuth success page)
- Lookup is ``O(n)`` over the key registry (small N, fast hash comparison)
- Account links are stored separately and checked at access time
"""

import hashlib
import json
import logging
import secrets
import threading
from pathlib import Path
from typing import Optional, Set

from config.settings import settings

logger = logging.getLogger(__name__)

_REGISTRY_FILENAME = ".user_api_keys.json"
_LINKS_FILENAME = ".user_api_key_links.json"
_lock = threading.Lock()


def _registry_path() -> Path:
    return Path(settings.credentials_dir) / _REGISTRY_FILENAME


def _links_path() -> Path:
    return Path(settings.credentials_dir) / _LINKS_FILENAME


def _hash_key(key: str) -> str:
    """SHA-256 hash of the plaintext key."""
    return hashlib.sha256(key.encode()).hexdigest()


def _load_registry() -> dict:
    """Load the key registry from disk. Returns {hash: email}."""
    path = _registry_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Could not load user API key registry: {e}")
        return {}


def _save_registry(registry: dict) -> None:
    """Persist the key registry to disk with restrictive permissions."""
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(registry, f, indent=2)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _load_links() -> dict:
    """Load account links from disk. Returns {email: [linked_emails]}."""
    path = _links_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Could not load account links: {e}")
        return {}


def _save_links(links: dict) -> None:
    """Persist account links to disk with restrictive permissions."""
    path = _links_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(links, f, indent=2)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def generate_user_key(user_email: str) -> str:
    """Generate a new API key for a user, replacing any existing key.

    Args:
        user_email: The email to bind this key to.

    Returns:
        The plaintext key (shown once to the user, never stored).
    """
    email = user_email.lower().strip()
    key = secrets.token_urlsafe(32)
    key_hash = _hash_key(key)

    with _lock:
        registry = _load_registry()

        # Remove any previous key for this email
        registry = {h: e for h, e in registry.items() if e != email}

        # Store the new hash → email mapping
        registry[key_hash] = email
        _save_registry(registry)

    logger.info(f"🔑 Generated per-user API key for {email}")
    return key


def lookup_key(token: str) -> Optional[str]:
    """Look up a token against the user key registry.

    Args:
        token: The plaintext bearer token from the client.

    Returns:
        The email address if the token matches a registered key, None otherwise.
    """
    token_hash = _hash_key(token)

    with _lock:
        registry = _load_registry()

    return registry.get(token_hash)


def revoke_user_key(user_email: str) -> bool:
    """Revoke the API key for a user.

    Returns True if a key was found and revoked.
    """
    email = user_email.lower().strip()

    with _lock:
        registry = _load_registry()
        before = len(registry)
        registry = {h: e for h, e in registry.items() if e != email}
        _save_registry(registry)

    revoked = len(registry) < before
    if revoked:
        logger.info(f"🔑 Revoked API key for {email}")
    return revoked


# ---------------------------------------------------------------------------
# Account linking
# ---------------------------------------------------------------------------


def link_accounts(email_a: str, email_b: str) -> None:
    """Bidirectionally link two email accounts.

    After linking, a per-user key for either email can access
    credentials for both.
    """
    a = email_a.lower().strip()
    b = email_b.lower().strip()
    if a == b:
        return

    with _lock:
        links = _load_links()
        # Add b to a's list
        a_links = set(links.get(a, []))
        a_links.add(b)
        links[a] = sorted(a_links)
        # Add a to b's list
        b_links = set(links.get(b, []))
        b_links.add(a)
        links[b] = sorted(b_links)
        _save_links(links)

    logger.info(f"🔗 Linked accounts: {a} ↔ {b}")


def get_accessible_emails(email: str) -> Set[str]:
    """Return all emails accessible to a key bound to the given email.

    Always includes the email itself, plus any linked accounts.
    """
    e = email.lower().strip()

    with _lock:
        links = _load_links()

    accessible = {e}
    accessible.update(links.get(e, []))
    return accessible


def unlink_accounts(email_a: str, email_b: str) -> bool:
    """Remove a bidirectional link between two accounts.

    Returns True if a link was found and removed.
    """
    a = email_a.lower().strip()
    b = email_b.lower().strip()

    with _lock:
        links = _load_links()
        changed = False

        a_links = set(links.get(a, []))
        if b in a_links:
            a_links.discard(b)
            links[a] = sorted(a_links) if a_links else []
            if not links[a]:
                del links[a]
            changed = True

        b_links = set(links.get(b, []))
        if a in b_links:
            b_links.discard(a)
            links[b] = sorted(b_links) if b_links else []
            if not links[b]:
                del links[b]
            changed = True

        if changed:
            _save_links(links)
            logger.info(f"🔗 Unlinked accounts: {a} ↔ {b}")

    return changed
