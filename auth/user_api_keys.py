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
import hmac
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
_PENDING_LINKS_FILENAME = ".user_api_key_pending_links.json"
_LINK_METADATA_FILENAME = ".user_api_key_link_metadata.json"
_OAUTH_LINKAGE_FILENAME = ".oauth_linkage_prefs.json"
_lock = threading.Lock()


def _registry_path() -> Path:
    return Path(settings.credentials_dir) / _REGISTRY_FILENAME


def _links_path() -> Path:
    return Path(settings.credentials_dir) / _LINKS_FILENAME


def _link_metadata_path() -> Path:
    return Path(settings.credentials_dir) / _LINK_METADATA_FILENAME


def _link_meta_key(a: str, b: str) -> str:
    """Canonical key for a pair of emails (sorted for consistency)."""
    return "::".join(sorted([a.lower().strip(), b.lower().strip()]))


def _load_link_metadata() -> dict:
    """Load link metadata. Returns {pair_key: {method, linked_at}}."""
    path = _link_metadata_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_link_metadata(meta: dict) -> None:
    path = _link_metadata_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(meta, f, indent=2)
    try:
        path.chmod(0o600)
    except OSError as e:
        logger.warning(f"⚠️ Could not set permissions on {path}: {e}")


def _hash_key(key: str) -> str:
    """SHA-256 hash of the plaintext key."""
    return hashlib.sha256(key.encode()).hexdigest()


def _reg_email(entry) -> str:
    """Extract email from a registry entry (supports legacy str and new dict formats)."""
    if isinstance(entry, dict):
        return entry.get("email", "")
    return entry  # legacy: value is just the email string


def _reg_created_at(entry) -> str:
    """Extract created_at from a registry entry. Empty string for legacy entries."""
    if isinstance(entry, dict):
        return entry.get("created_at", "")
    return ""


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
    except OSError as e:
        logger.warning(f"⚠️ Could not set permissions on {path}: {e}")


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
    except OSError as e:
        logger.warning(f"⚠️ Could not set permissions on {path}: {e}")


def generate_user_key(user_email: str, *, force: bool = False) -> Optional[str]:
    """Generate a new API key for a user.

    By default, if a key already exists for this email, returns ``None``
    so that re-authentication (from another session/client) does NOT
    invalidate an active key.  Pass ``force=True`` to replace the
    existing key (e.g. explicit key rotation).

    Args:
        user_email: The email to bind this key to.
        force: If True, replace any existing key. Default False.

    Returns:
        The plaintext key (shown once to the user, never stored),
        or ``None`` if a key already exists and *force* is False.
    """
    email = user_email.lower().strip()

    with _lock:
        registry = _load_registry()

        # Check if a key already exists for this email
        if not force:
            for _hash, entry in registry.items():
                if _reg_email(entry) == email:
                    logger.debug(
                        f"🔑 Per-user API key already exists for {email} — skipping generation"
                    )
                    return None

        key = secrets.token_urlsafe(32)
        key_hash = _hash_key(key)

        # Remove any previous key for this email
        registry = {h: e for h, e in registry.items() if _reg_email(e) != email}

        # Store the new hash → email + created_at mapping
        from datetime import datetime, timezone

        registry[key_hash] = {
            "email": email,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_registry(registry)

    logger.info(f"🔑 Generated per-user API key for {email}")
    return key


_API_KEY_LINK_WINDOW_MINUTES = 30


def is_key_within_link_window(user_email: str) -> bool:
    """Check if the per-user API key for this email was created within the linking window.

    API key sessions can only create account links within this window.
    After it expires, OAuth is required to establish new links.
    """
    from datetime import datetime, timezone

    email = user_email.lower().strip()

    with _lock:
        registry = _load_registry()

    for _hash, entry in registry.items():
        if _reg_email(entry) == email:
            created_str = _reg_created_at(entry)
            if not created_str:
                # Legacy entry without timestamp — deny linking
                return False
            try:
                created = datetime.fromisoformat(created_str)
                elapsed = (datetime.now(timezone.utc) - created).total_seconds()
                return elapsed <= _API_KEY_LINK_WINDOW_MINUTES * 60
            except (ValueError, TypeError):
                return False
    return False


def lookup_key(token: str) -> Optional[str]:
    """Look up a token against the user key registry.

    Uses timing-safe comparison to prevent side-channel attacks on hash prefixes.

    Args:
        token: The plaintext bearer token from the client.

    Returns:
        The email address if the token matches a registered key, None otherwise.
    """
    token_hash = _hash_key(token)

    with _lock:
        registry = _load_registry()

    for stored_hash, entry in registry.items():
        if hmac.compare_digest(token_hash, stored_hash):
            return _reg_email(entry)
    return None


def revoke_user_key(user_email: str) -> bool:
    """Revoke the API key for a user.

    Returns True if a key was found and revoked.
    """
    email = user_email.lower().strip()

    with _lock:
        registry = _load_registry()
        before = len(registry)
        registry = {h: e for h, e in registry.items() if _reg_email(e) != email}
        _save_registry(registry)

    revoked = len(registry) < before
    if revoked:
        logger.info(f"🔑 Revoked API key for {email}")
    return revoked


# ---------------------------------------------------------------------------
# Account linking
# ---------------------------------------------------------------------------


def link_accounts(email_a: str, email_b: str, method: str = "session") -> None:
    """Bidirectionally link two email accounts.

    After linking, a per-user key for either email can access
    credentials for both.

    Args:
        email_a: First email address.
        email_b: Second email address.
        method: How the link was established — "session" (same MCP session)
                or "oauth" (OAuth user called start_google_auth for other email).
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

        # Store link metadata
        from datetime import datetime, timezone

        meta = _load_link_metadata()
        mk = _link_meta_key(a, b)
        existing = meta.get(mk)
        if existing and existing.get("method") != method:
            # Upgrade to "both" if linked via a different method too
            meta[mk] = {
                "method": "both",
                "methods": sorted(set([existing.get("method", "session"), method])),
                "linked_at": existing.get("linked_at"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        elif not existing:
            meta[mk] = {
                "method": method,
                "linked_at": datetime.now(timezone.utc).isoformat(),
            }
        _save_link_metadata(meta)

    logger.info(f"🔗 Linked accounts: {a} ↔ {b} (method={method})")


# ---------------------------------------------------------------------------
# Pending links (deferred until OAuth completes)
# ---------------------------------------------------------------------------


def _pending_links_path() -> Path:
    return Path(settings.credentials_dir) / _PENDING_LINKS_FILENAME


def _load_pending_links() -> dict:
    """Load pending links. Returns {target_email: [source_emails]}."""
    path = _pending_links_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_pending_links(pending: dict) -> None:
    path = _pending_links_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(pending, f, indent=2)
    try:
        path.chmod(0o600)
    except OSError as e:
        logger.warning(f"⚠️ Could not set permissions on {path}: {e}")


def request_link(source_email: str, target_email: str, method: str = "session") -> None:
    """Record a pending link request. Executed when target_email completes OAuth.

    Args:
        source_email: The email of the key owner requesting the link.
        target_email: The email being authenticated (link deferred until OAuth completes).
        method: How the link was established — "session" or "oauth".
    """
    s = source_email.lower().strip()
    t = target_email.lower().strip()
    if s == t:
        return

    with _lock:
        pending = _load_pending_links()
        # Store as {target: {source: method}} for method tracking
        target_pending = pending.get(t, {})
        if isinstance(target_pending, list):
            # Migrate legacy format [source_emails] → {source: method}
            target_pending = {src: "session" for src in target_pending}
        target_pending[s] = method
        pending[t] = target_pending
        _save_pending_links(pending)

    logger.info(
        f"🔗 Pending link request: {s} → {t} (method={method}, awaiting OAuth completion)"
    )


def consume_pending_links(completed_email: str) -> None:
    """Execute any pending links for an email that just completed OAuth.

    Called from _save_credentials after OAuth succeeds.  Only links where
    the source email has a registered per-user key are activated — this
    prevents orphan link requests from being consumed.
    """
    e = completed_email.lower().strip()

    with _lock:
        pending = _load_pending_links()
        raw_sources = pending.pop(e, {})
        if raw_sources:
            _save_pending_links(pending)
        # Load registry once to verify source emails have keys
        registry = _load_registry()

    registered_emails = {_reg_email(e) for e in registry.values()}

    # Handle both legacy [source_emails] and new {source: method} formats
    if isinstance(raw_sources, list):
        source_methods = {src: "session" for src in raw_sources}
    else:
        source_methods = raw_sources

    for source, method in source_methods.items():
        if source not in registered_emails:
            logger.warning(
                f"🔗 Skipping pending link {source} → {e}: "
                f"source has no registered per-user key"
            )
            continue
        link_accounts(source, e, method=method)
        logger.info(f"🔗 Executed deferred link: {source} ↔ {e} (method={method})")


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


def get_link_method(email_a: str, email_b: str) -> str:
    """Return how two emails were linked: 'session', 'oauth', or 'both'.

    Returns empty string if no metadata found.
    """
    mk = _link_meta_key(email_a, email_b)
    with _lock:
        meta = _load_link_metadata()
    entry = meta.get(mk, {})
    return entry.get("method", "")


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


# =========================================================================
# OAuth Cross-Linkage Preferences
# =========================================================================


def _oauth_linkage_path() -> Path:
    return Path(settings.credentials_dir) / _OAUTH_LINKAGE_FILENAME


def _get_linkage_fernet():
    """Get a Fernet instance for encrypting/decrypting linkage prefs.

    Derives from the same server secret used by AuthMiddleware, ensuring
    google_sub and passwords are encrypted at rest.
    """
    import base64

    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    secret_path = Path(settings.credentials_dir) / ".auth_encryption_key"
    if not secret_path.exists():
        # No server secret yet — can't encrypt.  Caller should handle.
        return None
    server_secret = secret_path.read_bytes().strip()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"oauth-linkage-prefs-salt-v1",
        info=b"oauth-linkage-prefs-encryption-v1",
    )
    key = base64.urlsafe_b64encode(hkdf.derive(server_secret))
    return Fernet(key)


def _load_oauth_linkage_prefs() -> dict:
    path = _oauth_linkage_path()
    if not path.exists():
        return {}
    try:
        raw = path.read_bytes()
        # Try encrypted format first
        fernet = _get_linkage_fernet()
        if fernet:
            try:
                decrypted = fernet.decrypt(raw)
                return json.loads(decrypted)
            except Exception:
                pass
        # Fall back to plaintext (legacy / migration)
        return json.loads(raw)
    except Exception:
        return {}


def _save_oauth_linkage_prefs(prefs: dict) -> None:
    path = _oauth_linkage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(prefs, indent=2).encode()
    fernet = _get_linkage_fernet()
    if fernet:
        data = fernet.encrypt(data)
    path.write_bytes(data)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def set_oauth_linkage(
    email: str,
    enabled: bool = True,
    password: str = "",
    google_sub: str = "",
) -> None:
    """Set cross-OAuth linkage preference for an email.

    Args:
        email: The account email.
        enabled: Whether OAuth sessions can decrypt this account's credentials.
        password: Optional passphrase added to the OAuth recipient key derivation.
            Only alphanumeric, underscore, and hyphen allowed.  Empty = no password.
        google_sub: Google's immutable account ID.  Persisted so cross-account
            decryption works after server restarts.
    """
    import re

    normalized = email.lower().strip()
    if password and not re.fullmatch(r"[0-9A-Za-z_-]*", password):
        raise ValueError("Password may only contain 0-9, A-Z, a-z, _, -")

    with _lock:
        prefs = _load_oauth_linkage_prefs()
        entry: dict = {"enabled": enabled, "has_password": bool(password)}
        if password:
            entry["password"] = password
        if google_sub:
            entry["google_sub"] = google_sub
        elif normalized in prefs and "google_sub" in prefs[normalized]:
            # Preserve existing google_sub if not provided
            entry["google_sub"] = prefs[normalized]["google_sub"]
        prefs[normalized] = entry
        _save_oauth_linkage_prefs(prefs)

    logger.info(
        f"OAuth linkage for {normalized}: enabled={enabled}, "
        f"password={'set' if password else 'none'}, "
        f"google_sub={'set' if google_sub else 'preserved' if entry.get('google_sub') else 'none'}"
    )


def get_oauth_linkage(email: str) -> dict:
    """Get cross-OAuth linkage preference for an email.

    Returns:
        {"enabled": bool, "has_password": bool, "password": str, "google_sub": str}
        Defaults to enabled=True, no password, no sub if not set.
    """
    normalized = email.lower().strip()
    with _lock:
        prefs = _load_oauth_linkage_prefs()
    default = {"enabled": True, "has_password": False, "password": "", "google_sub": ""}
    entry = prefs.get(normalized, default)
    entry.setdefault("password", "")
    entry.setdefault("google_sub", "")
    return entry
