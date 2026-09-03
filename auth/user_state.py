"""Per-principal state: one bucket per authenticated identity, in FastMCP's state store.

Under MCP 2026-07-28 every request is its own transport session, so anything
keyed by ``ctx.session_id`` (the module-level ``_session_store`` in
``auth/context.py``) is thrown away between calls. This module keys the state
that has to outlive a request by *who* is calling instead:

- an OAuth JWT, per-user API key, or Google tokeninfo token → the user's email
- the shared ``MCP_API_KEY`` → one admin bucket (every holder shares it, by design)
- no token at all (stdio / legacy no-auth deploys) → one anonymous bucket

The bucket lives in the server's ``session_state_store`` — the same
``AsyncKeyValue`` that ``ctx.set_state`` uses — so it survives restarts on the
disk store and is shared across replicas on Redis. Storage layout follows
FastMCP's ``Session`` (``session:{sha256(principal)}:_user`` holding
``{"state": {...}}``) so a handler that injects ``session: UserSession`` for the
same principal string would read the same record.

Why not FastMCP's ``UserSession`` directly: its principal is the token's
``(client_id, issuer, subject)`` triple. The ``client_id`` is the OAuth client
registration, which differs between Claude Desktop, Claude Code and claude.ai,
so one person would get one bucket per client. And the OAuth success page and
``/api/*`` routes address the bucket by email with no MCP bearer token in hand.
Keying by identity solves both; the ``Session`` machinery is reused for layout.

Handlers should call these helpers rather than ``store_session_data`` for any
value that must be visible on a later request. The sync ``_session_store`` stays
for same-request hand-offs (identity resolved in ``AuthMiddleware.on_call_tool``
and read by the tool body a few frames later).
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from fastmcp.server.dependencies import get_access_token, get_server
from fastmcp.server.sessions import _principal_segment, session_storage_key

from config.enhanced_logging import redact_email, setup_logger

from .types import AuthProvenance, SessionKey

logger = setup_logger()

# FastMCP 4.0.1 layout constants (fastmcp.server.sessions). Pinned here so a
# rename upstream shows up as a test failure, not silent data loss.
_STATE_KEY = "state"
_USER_SESSION_ID = "_user"

# Bucket keys. Plain strings because the bucket is JSON on the wire.
DISABLED_TOOLS_KEY = SessionKey.SESSION_DISABLED_TOOLS.value
STARTUP_APPLIED_KEY = "minimal_startup_applied"
STARTUP_SERVICES_KEY = "startup_services"
CLIENT_KEY = SessionKey.CLIENT.value
SAMPLING_CONFIG_KEY = SessionKey.SAMPLING_CONFIG.value
PRIVACY_MODE_KEY = SessionKey.PRIVACY_MODE.value
PRIVACY_FIELDS_KEY = SessionKey.PRIVACY_ADDITIONAL_FIELDS.value

SHARED_KEY_PRINCIPAL = "apikey:shared"

# Set once by server.py so code running outside a FastMCP request (Starlette
# routes, the OAuth callback) can still reach the store.
_server: Any = None


def set_server(mcp: Any) -> None:
    """Register the FastMCP instance whose state store holds the buckets."""
    global _server
    _server = mcp


def _state_store():
    """The server's ``PydanticAdapter[StateValue]``, task-aware when in a request."""
    try:
        return get_server()._state_store
    except RuntimeError:
        if _server is None:
            raise
        return _server._state_store


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def _token():
    try:
        return get_access_token()
    except Exception:
        return None


def principal_claims() -> dict:
    """Claims of the current request's access token, or ``{}``."""
    tok = _token()
    claims = getattr(tok, "claims", None) if tok is not None else None
    return dict(claims) if isinstance(claims, dict) else {}


def auth_provenance() -> Optional[str]:
    """``auth_method`` claim of the current token (``AuthProvenance`` value) or None."""
    method = principal_claims().get("auth_method")
    if not method:
        return None
    # ``str()`` of a str-mixin Enum is "AuthProvenance.API_KEY"; want "api_key".
    return str(getattr(method, "value", method))


def is_shared_key() -> bool:
    """True when the request authenticated with the shared ``MCP_API_KEY``."""
    return auth_provenance() == AuthProvenance.API_KEY


def principal_email() -> Optional[str]:
    """Email of the current principal from token claims (``email``, then ``sub``).

    Replaces the JWT → GitHub → GoogleProvider → session-storage walk for every
    request that carries a token. Returns None for the shared key (its ``sub``
    is not an address) and for tokenless requests.
    """
    tok = _token()
    if tok is None:
        return None
    claims = getattr(tok, "claims", None) or {}
    if claims.get("auth_method") == AuthProvenance.API_KEY:
        return None
    email = claims.get("email") or claims.get("google_email")
    if not email:
        sub = getattr(tok, "subject", None) or claims.get("sub")
        if isinstance(sub, str) and "@" in sub:
            email = sub
    return email.lower().strip() if isinstance(email, str) and email else None


def principal_sub() -> Optional[str]:
    """Google account id (``sub``) from token claims, when the token carries one."""
    claims = principal_claims()
    sub = claims.get("sub")
    if not sub:
        return None
    sub = str(sub)
    # Per-user keys and tokeninfo tokens put the email in ``sub``; the OAuth JWT
    # puts Google's numeric account id there. Only the latter is a Google sub.
    return None if "@" in sub else sub


def principal_for_email(email: str) -> str:
    """The bucket principal string for a user identified by email."""
    return f"user:{email.lower().strip()}"


def principal_id() -> Optional[str]:
    """The current request's bucket principal, or None when there is no token.

    None collapses to FastMCP's shared ``anon`` segment: without a token there
    is no isolation wall, which is the right answer for a single-user stdio or
    legacy no-auth deploy and never happens on an authenticated HTTP server.
    """
    tok = _token()
    if tok is None:
        return None
    claims = getattr(tok, "claims", None) or {}
    if claims.get("auth_method") == AuthProvenance.API_KEY:
        return SHARED_KEY_PRINCIPAL
    email = principal_email()
    if email:
        return principal_for_email(email)
    sub = getattr(tok, "subject", None) or claims.get("sub")
    if sub:
        return f"sub:{sub}"
    return f"client:{getattr(tok, 'client_id', '') or 'unknown'}"


# ---------------------------------------------------------------------------
# Bucket
# ---------------------------------------------------------------------------


def _jsonable(value: Any) -> Any:
    """Coerce the few non-JSON types this codebase stores into JSON shapes."""
    if isinstance(value, (set, frozenset)):
        return sorted(_jsonable(v) for v in value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(getattr(k, "value", k)): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, bytes):
        raise TypeError("bytes are not stored in the user bucket")
    return value


def _key(key: Any) -> str:
    return str(getattr(key, "value", key))


class UserBucket:
    """Async read/write access to one principal's state dict.

    ``load``/``save`` move the whole dict; ``get``/``set``/``update``/``delete``
    are read-modify-write over it. State is small and driven serially by one
    agent, so the race between concurrent writers is accepted (as FastMCP's
    ``Session`` accepts it).
    """

    def __init__(self, principal: Optional[str], store: Any = None) -> None:
        self.principal = principal
        self._store = store
        self.key = session_storage_key(principal, _USER_SESSION_ID)

    @property
    def segment(self) -> str:
        return _principal_segment(self.principal)

    def _adapter(self):
        return self._store if self._store is not None else _state_store()

    async def _load_raw(self) -> dict:
        result = await self._adapter().get(key=self.key)
        if result is None:
            return {}
        value = result.value
        return dict(value) if isinstance(value, dict) else {}

    async def load(self) -> dict:
        """The state dict (a copy). Empty when the principal has no record."""
        raw = await self._load_raw()
        state = raw.get(_STATE_KEY)
        return dict(state) if isinstance(state, dict) else {}

    async def save(self, state: dict) -> None:
        from fastmcp.server.server import StateValue

        raw = await self._load_raw()
        raw[_STATE_KEY] = _jsonable(state)
        await self._adapter().put(key=self.key, value=StateValue(value=raw))

    async def get(self, key: Any, default: Any = None) -> Any:
        return (await self.load()).get(_key(key), default)

    async def set(self, key: Any, value: Any) -> None:
        await self.update({_key(key): value})

    async def update(self, mapping: dict) -> None:
        state = await self.load()
        for k, v in mapping.items():
            state[_key(k)] = v
        await self.save(state)

    async def delete(self, key: Any) -> None:
        state = await self.load()
        if _key(key) in state:
            del state[_key(key)]
            await self.save(state)

    async def clear(self) -> None:
        await self.save({})


_CURRENT = object()


def user_bucket(principal: Any = _CURRENT) -> UserBucket:
    """The bucket for ``principal`` (default: the current request's principal)."""
    if principal is _CURRENT:
        principal = principal_id()
    return UserBucket(principal)


def bucket_for_email(email: str) -> UserBucket:
    """The bucket a Starlette route or OAuth callback addresses for ``email``."""
    return UserBucket(principal_for_email(email))


async def bucket_get(key: Any, default: Any = None) -> Any:
    """Read one key from the current principal's bucket; store errors read as ``default``."""
    try:
        return await user_bucket().get(key, default)
    except Exception as exc:
        logger.warning(f"User bucket read failed for {_key(key)}: {exc}")
        return default


async def bucket_set(key: Any, value: Any) -> bool:
    """Write one key to the current principal's bucket; returns False on store error."""
    try:
        await user_bucket().set(key, value)
        return True
    except Exception as exc:
        logger.warning(f"User bucket write failed for {_key(key)}: {exc}")
        return False


async def bucket_update(mapping: dict) -> bool:
    try:
        await user_bucket().update(mapping)
        return True
    except Exception as exc:
        logger.warning(f"User bucket write failed for {sorted(mapping)}: {exc}")
        return False


# ---------------------------------------------------------------------------
# Disabled tools (SessionToolFilteringMiddleware, manage_tools scope=session)
# ---------------------------------------------------------------------------


def _legacy_state_path() -> Optional[Path]:
    try:
        from .context import _get_session_tool_state_path

        return _get_session_tool_state_path()
    except Exception:
        return None


def import_legacy_disabled_tools(email: Optional[str]) -> Optional[set]:
    """One-time import from the retired ``session_tool_states.json``.

    Returns the disabled set of the most recently accessed entry recorded for
    ``email``, or None when the file has nothing for that user. Called only for
    a bucket that has never recorded a disabled set; the caller writes the
    result (even an empty one) so the file is never consulted again for them.
    """
    if not email:
        return None
    path = _legacy_state_path()
    if path is None or not path.exists():
        return None
    try:
        entries = json.loads(path.read_text())
    except Exception as exc:
        logger.debug(f"Legacy session state file unreadable: {exc}")
        return None
    best: Optional[tuple[datetime, list]] = None
    for state in entries.values():
        if not isinstance(state, dict):
            continue
        if (state.get("user_email") or "").lower().strip() != email.lower().strip():
            continue
        try:
            seen = datetime.fromisoformat(state.get("last_accessed", ""))
        except (TypeError, ValueError):
            seen = datetime.min
        if best is None or seen > best[0]:
            best = (seen, list(state.get("disabled_tools") or []))
    if best is None:
        return None
    logger.info(
        f"Imported {len(best[1])} disabled tools for {redact_email(email)} "
        f"from legacy session_tool_states.json"
    )
    return set(best[1])


def disabled_tools_from_state(state: dict, email: Optional[str] = None) -> set:
    """The disabled set held in a loaded bucket state (legacy import on first sight)."""
    if DISABLED_TOOLS_KEY in state:
        return set(state.get(DISABLED_TOOLS_KEY) or [])
    imported = import_legacy_disabled_tools(email)
    return imported if imported is not None else set()


async def get_disabled_tools(bucket: Optional[UserBucket] = None) -> set:
    bucket = bucket or user_bucket()
    try:
        state = await bucket.load()
    except Exception as exc:
        logger.warning(f"Disabled-tools read failed (treating as none): {exc}")
        return set()
    return disabled_tools_from_state(state, principal_email())


async def set_disabled_tools(
    tools: Iterable[str], bucket: Optional[UserBucket] = None
) -> bool:
    bucket = bucket or user_bucket()
    try:
        await bucket.set(DISABLED_TOOLS_KEY, sorted(set(tools)))
        return True
    except Exception as exc:
        logger.warning(f"Disabled-tools write failed: {exc}")
        return False


async def disable_tools(names: Iterable[str]) -> bool:
    bucket = user_bucket()
    current = await get_disabled_tools(bucket)
    return await set_disabled_tools(current | set(names), bucket)


async def enable_tools(names: Iterable[str]) -> bool:
    bucket = user_bucket()
    current = await get_disabled_tools(bucket)
    return await set_disabled_tools(current - set(names), bucket)


async def clear_disabled_tools() -> bool:
    return await set_disabled_tools(set(), user_bucket())


async def is_tool_disabled(tool_name: str) -> bool:
    return tool_name in await get_disabled_tools()


# ---------------------------------------------------------------------------
# TTL caches (per principal) and OAuth flow state (global)
# ---------------------------------------------------------------------------


def _cache_key(name: str) -> str:
    return f"cache:{_principal_segment(principal_id())}:{name}"


async def cache_get(name: str) -> Any:
    """A per-principal cached value, or None when absent or expired."""
    try:
        result = await _state_store().get(key=_cache_key(name))
    except Exception as exc:
        logger.debug(f"Cache read failed for {name}: {exc}")
        return None
    return result.value if result is not None else None


async def cache_set(name: str, value: Any, ttl_seconds: float) -> None:
    """Cache ``value`` for the current principal with a store-enforced TTL."""
    from fastmcp.server.server import StateValue

    try:
        await _state_store().put(
            key=_cache_key(name),
            value=StateValue(value=_jsonable(value)),
            ttl=ttl_seconds,
        )
    except Exception as exc:
        logger.debug(f"Cache write failed for {name}: {exc}")


OAUTH_STATE_TTL_SECONDS = 600


async def oauth_state_set(state: str, data: dict) -> None:
    """Keep OAuth-flow data under the flow's ``state`` string for ten minutes."""
    from fastmcp.server.server import StateValue

    try:
        await _state_store().put(
            key=f"oauth-state:{state}",
            value=StateValue(value=_jsonable(data)),
            ttl=OAUTH_STATE_TTL_SECONDS,
        )
    except Exception as exc:
        logger.debug(f"OAuth state write failed: {exc}")


async def oauth_state_get(state: str) -> Optional[dict]:
    try:
        result = await _state_store().get(key=f"oauth-state:{state}")
    except Exception as exc:
        logger.debug(f"OAuth state read failed: {exc}")
        return None
    value = result.value if result is not None else None
    return dict(value) if isinstance(value, dict) else None


def now() -> float:
    return time.time()


__all__ = [
    "CLIENT_KEY",
    "DISABLED_TOOLS_KEY",
    "PRIVACY_FIELDS_KEY",
    "PRIVACY_MODE_KEY",
    "SAMPLING_CONFIG_KEY",
    "SHARED_KEY_PRINCIPAL",
    "STARTUP_APPLIED_KEY",
    "STARTUP_SERVICES_KEY",
    "UserBucket",
    "auth_provenance",
    "bucket_for_email",
    "bucket_get",
    "bucket_set",
    "bucket_update",
    "cache_get",
    "cache_set",
    "clear_disabled_tools",
    "disable_tools",
    "disabled_tools_from_state",
    "enable_tools",
    "get_disabled_tools",
    "import_legacy_disabled_tools",
    "is_shared_key",
    "is_tool_disabled",
    "oauth_state_get",
    "oauth_state_set",
    "principal_claims",
    "principal_email",
    "principal_for_email",
    "principal_id",
    "principal_sub",
    "set_disabled_tools",
    "set_server",
    "user_bucket",
]
