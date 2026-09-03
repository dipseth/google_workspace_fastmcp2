"""Per-principal state (auth/user_state.py) and the middleware that reads it.

Under MCP 2026-07-28 every request is its own transport session, so the tests
here open *separate* in-process clients for what used to be "the same session"
and assert that state set on one is honored on the next. Each test runs on both
protocol eras: ``Client(mcp)`` negotiates 2026-07-28, ``mode="legacy"`` forces
the handshake.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.auth import AccessToken
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

from auth import user_state
from auth.types import AuthProvenance, SessionKey
from middleware.session_tool_filtering_middleware import (
    SessionToolFilteringMiddleware,
)

ERAS = ("auto", "legacy")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def oauth_token(email: str, sub: str | None = None) -> AccessToken:
    return AccessToken(
        token=f"jwt-{email}",
        client_id="https://claude.ai/oauth/some-client",
        scopes=["openid"],
        claims={"sub": sub or "1234567890", "email": email, "iss": "test"},
    )


def user_key_token(email: str) -> AccessToken:
    return AccessToken(
        token=f"key-{email}",
        client_id=f"user-key-{email}",
        scopes=["openid"],
        claims={
            "sub": email,
            "email": email,
            "auth_method": AuthProvenance.USER_API_KEY,
        },
    )


def shared_key_token() -> AccessToken:
    return AccessToken(
        token="admin-key",
        client_id="api-key-client",
        scopes=["openid"],
        claims={"sub": "api-key-user", "auth_method": AuthProvenance.API_KEY},
    )


class _As:
    """``async with _As(token):`` — run the block as that principal."""

    def __init__(self, token: AccessToken | None):
        self._token = token

    async def __aenter__(self):
        self._reset = auth_context_var.set(
            AuthenticatedUser(self._token) if self._token else None
        )
        return self

    async def __aexit__(self, *exc):
        auth_context_var.reset(self._reset)


def make_server(
    *, minimal: bool = False, default_services: list[str] | None = None
) -> FastMCP:
    """A tiny server with the filtering middleware and a manage-style tool."""
    mcp = FastMCP("user-state-test")
    mcp.add_middleware(
        SessionToolFilteringMiddleware(
            protected_tools={"manage"},
            minimal_startup=minimal,
            default_enabled_services=default_services,
        )
    )

    @mcp.tool
    def list_gmail_labels() -> str:
        return "labels"

    @mcp.tool
    def search_drive_files() -> str:
        return "files"

    @mcp.tool
    async def manage(action: str, tool: str = "") -> list[str]:
        if action == "disable":
            await user_state.disable_tools([tool])
        elif action == "enable":
            await user_state.enable_tools([tool])
        elif action == "clear":
            await user_state.clear_disabled_tools()
        return sorted(await user_state.get_disabled_tools())

    return mcp


async def tool_names(client: Client) -> set[str]:
    return {t.name for t in await client.list_tools()}


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_principal_mapping():
    async with _As(oauth_token("Alice@Example.com")):
        assert user_state.principal_id() == "user:alice@example.com"
        assert user_state.principal_email() == "alice@example.com"
        assert user_state.principal_sub() == "1234567890"
        assert user_state.is_shared_key() is False
    async with _As(user_key_token("bob@example.com")):
        assert user_state.principal_id() == "user:bob@example.com"
        assert user_state.principal_sub() is None  # email in sub is not a Google sub
    async with _As(shared_key_token()):
        assert user_state.principal_id() == user_state.SHARED_KEY_PRINCIPAL
        assert user_state.principal_email() is None
        assert user_state.is_shared_key() is True
    async with _As(None):
        assert user_state.principal_id() is None
        assert user_state.principal_email() is None


def test_fastmcp_private_layout_pins():
    """auth/user_state.py mirrors FastMCP 4.0.1's Session layout; fail loudly if it moves."""
    from fastmcp.server import sessions

    assert sessions._STATE_KEY == user_state._STATE_KEY == "state"
    assert sessions._USER_SESSION_ID == user_state._USER_SESSION_ID == "_user"
    assert sessions.session_storage_key("p", "_user").startswith("session:")
    assert callable(sessions._current_user_session)


# ---------------------------------------------------------------------------
# Bucket
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bucket_roundtrip_and_json_coercion():
    user_state.set_server(FastMCP("bucket"))
    async with _As(oauth_token("alice@example.com")):
        bucket = user_state.user_bucket()
        await bucket.update(
            {
                SessionKey.SESSION_DISABLED_TOOLS: {"b", "a"},
                "when": datetime(2026, 9, 3, 12, 0, 0),
                "fields": frozenset({"x"}),
            }
        )
        state = await bucket.load()
        assert state["session_disabled_tools"] == ["a", "b"]
        assert state["when"] == "2026-09-03T12:00:00"
        assert state["fields"] == ["x"]
        assert await bucket.get(SessionKey.SESSION_DISABLED_TOOLS) == ["a", "b"]
        await bucket.delete("when")
        assert "when" not in await bucket.load()
        # Same principal string from a route context reads the same record.
        assert await user_state.bucket_for_email("Alice@Example.com").get("fields") == [
            "x"
        ]


@pytest.mark.asyncio
async def test_bucket_read_failure_reads_as_default(monkeypatch):
    user_state.set_server(FastMCP("bucket"))

    class Boom:
        async def get(self, **kw):
            raise RuntimeError("store down")

    monkeypatch.setattr(user_state, "_state_store", lambda: Boom())
    async with _As(oauth_token("alice@example.com")):
        assert await user_state.bucket_get("k", "dflt") == "dflt"
        assert await user_state.get_disabled_tools() == set()


@pytest.mark.asyncio
async def test_cache_helpers_are_per_principal():
    user_state.set_server(FastMCP("bucket"))
    async with _As(oauth_token("alice@example.com")):
        await user_state.cache_set("chat_spaces", ["s1"], ttl_seconds=300)
        assert await user_state.cache_get("chat_spaces") == ["s1"]
    async with _As(oauth_token("bob@example.com")):
        assert await user_state.cache_get("chat_spaces") is None


@pytest.mark.asyncio
async def test_oauth_state_helpers():
    user_state.set_server(FastMCP("bucket"))
    await user_state.oauth_state_set("st-1", {"custom_client_id": "cid"})
    assert (await user_state.oauth_state_get("st-1"))["custom_client_id"] == "cid"
    assert await user_state.oauth_state_get("missing") is None


# ---------------------------------------------------------------------------
# Disabled tools across connections and eras
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ERAS)
async def test_disable_on_one_connection_hides_and_blocks_on_another(mode):
    mcp = make_server()
    alice = oauth_token("alice@example.com")

    async with _As(alice):
        async with Client(mcp, mode=mode) as c1:
            assert "search_drive_files" in await tool_names(c1)
            res = await c1.call_tool(
                "manage", {"action": "disable", "tool": "search_drive_files"}
            )
            assert res.data == ["search_drive_files"]

        # A second connection — under 2026-07-28 a fresh session id per request.
        async with Client(mcp, mode=mode) as c2:
            names = await tool_names(c2)
            assert "search_drive_files" not in names
            assert {"manage", "list_gmail_labels"} <= names
            with pytest.raises(ToolError, match="disabled"):
                await c2.call_tool("search_drive_files", {})
            # Protected tools always run.
            await c2.call_tool("manage", {"action": "list"})

        async with Client(mcp, mode=mode) as c3:
            await c3.call_tool(
                "manage", {"action": "enable", "tool": "search_drive_files"}
            )
            assert "search_drive_files" in await tool_names(c3)
            assert (await c3.call_tool("search_drive_files", {})).data == "files"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ERAS)
async def test_principals_do_not_share_disabled_tools(mode):
    mcp = make_server()

    async with _As(oauth_token("alice@example.com")):
        async with Client(mcp, mode=mode) as c:
            await c.call_tool(
                "manage", {"action": "disable", "tool": "search_drive_files"}
            )

    async with _As(oauth_token("bob@example.com")):
        async with Client(mcp, mode=mode) as c:
            assert "search_drive_files" in await tool_names(c)

    # The shared admin key is its own bucket, distinct from every OAuth user.
    async with _As(shared_key_token()):
        async with Client(mcp, mode=mode) as c:
            assert "search_drive_files" in await tool_names(c)
            await c.call_tool(
                "manage", {"action": "disable", "tool": "list_gmail_labels"}
            )

    async with _As(oauth_token("alice@example.com")):
        async with Client(mcp, mode=mode) as c:
            names = await tool_names(c)
            assert "list_gmail_labels" in names
            assert "search_drive_files" not in names

    # Per-user key and OAuth JWT for the same email are the same principal.
    async with _As(user_key_token("alice@example.com")):
        async with Client(mcp, mode=mode) as c:
            assert "search_drive_files" not in await tool_names(c)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ERAS)
async def test_minimal_startup_applies_once_per_principal(mode):
    mcp = make_server(minimal=True, default_services=["gmail"])

    async with _As(oauth_token("carol@example.com")):
        async with Client(mcp, mode=mode) as c:
            names = await tool_names(c)
            assert names == {"manage", "list_gmail_labels"}
            await c.call_tool(
                "manage", {"action": "enable", "tool": "search_drive_files"}
            )

        # A returning user is not re-restricted.
        async with Client(mcp, mode=mode) as c:
            assert "search_drive_files" in await tool_names(c)

    async with _As(oauth_token("dave@example.com")):
        async with Client(mcp, mode=mode) as c:
            assert "search_drive_files" not in await tool_names(c)


@pytest.mark.asyncio
async def test_legacy_file_is_imported_once(_session_tool_state_in_tmp):
    path = _session_tool_state_in_tmp
    path.write_text(
        json.dumps(
            {
                "old-session": {
                    "disabled_tools": ["search_drive_files"],
                    "last_accessed": "2026-08-25T11:00:00",
                    "minimal_startup_applied": False,
                    "user_email": "erin@example.com",
                },
                "older": {
                    "disabled_tools": ["list_gmail_labels"],
                    "last_accessed": "2026-08-20T11:00:00",
                    "minimal_startup_applied": False,
                    "user_email": "erin@example.com",
                },
            }
        )
    )
    mcp = make_server()
    try:
        async with _As(oauth_token("erin@example.com")):
            async with Client(mcp) as c:
                names = await tool_names(c)
                assert "search_drive_files" not in names
                assert "list_gmail_labels" in names  # only the newest entry
                await c.call_tool("manage", {"action": "clear"})
            # The file is never read again for this user.
            path.write_text(
                json.dumps(
                    {
                        "s": {
                            "disabled_tools": ["list_gmail_labels"],
                            "last_accessed": "2026-09-01T11:00:00",
                            "user_email": "erin@example.com",
                        }
                    }
                )
            )
            async with Client(mcp) as c:
                assert {"list_gmail_labels", "search_drive_files"} <= await tool_names(
                    c
                )
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Sampling config, payment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sampling_config_read_from_bucket_on_later_request():
    from middleware.session_sampling_handler import (
        SessionAwareSamplingHandler,
        public_sampling_config,
    )

    user_state.set_server(FastMCP("sampling"))
    handler = SessionAwareSamplingHandler(default_handler=None)
    cfg = {"model": "openai/gpt-4o", "api_key": "sk-secret", "api_base": "https://x"}

    async with _As(oauth_token("fay@example.com")):
        # What /api/sampling-config writes: the public part only.
        public = public_sampling_config(cfg)
        assert "api_key" not in public and public["has_api_key"] is True
        await user_state.bucket_set(user_state.SAMPLING_CONFIG_KEY, public)

    # No shared transport session: a brand-new request for the same principal.
    async with _As(oauth_token("fay@example.com")):
        resolved = await handler._get_session_sampling_config()
        assert resolved == {"model": "openai/gpt-4o", "api_base": "https://x"}

    async with _As(oauth_token("gus@example.com")):
        assert await handler._get_session_sampling_config() is None

    async with _As(oauth_token("fay@example.com")):
        await user_state.bucket_set(user_state.SAMPLING_CONFIG_KEY, {})  # cleared
        assert await handler._get_session_sampling_config() is None


@pytest.fixture
def _receipt_env(tmp_path, monkeypatch):
    """Receipts need a server secret; give this test an isolated one."""
    import secrets

    import middleware.payment.payment_flow as payment_flow_module
    import middleware.payment.receipt as receipt_module

    (tmp_path / ".auth_encryption_key").write_text(secrets.token_hex(32))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(receipt_module, "_hmac_key_cache", None)
    monkeypatch.setattr(payment_flow_module, "_hmac_key_cache", None)
    yield
    receipt_module._hmac_key_cache = None
    payment_flow_module._hmac_key_cache = None


@pytest.mark.asyncio
async def test_payment_verified_on_request_n_honored_on_n_plus_1(_receipt_env):
    from middleware.payment.middleware import X402PaymentMiddleware

    user_state.set_server(FastMCP("payment"))
    mw = X402PaymentMiddleware(
        gated_tools="", free_for_oauth=False, session_ttl_minutes=60
    )

    async with _As(oauth_token("hal@example.com")):
        assert await mw._is_payment_verified("req-1") is False
        await mw._cache_payment_in_session(
            "req-1", payer_address="0xabc", tool_name="t"
        )
    async with _As(oauth_token("hal@example.com")):
        assert await mw._is_payment_verified("req-2") is True
    async with _As(oauth_token("ivy@example.com")):
        assert await mw._is_payment_verified("req-3") is False


# ---------------------------------------------------------------------------
# Workstream B: cache hints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hints_let_a_modern_client_skip_refetch():
    from fastmcp.server.middleware import Middleware
    from mcp.client.caching import CacheConfig

    class Counter(Middleware):
        calls = 0

        async def on_list_tools(self, context, call_next):
            self.calls += 1
            return await call_next(context)

    mcp = FastMCP("hints", cache_ttl=30, cache_scope="private")
    counter = Counter()
    mcp.add_middleware(counter)

    @mcp.tool
    def ping() -> str:
        return "pong"

    async with Client(mcp, cache=CacheConfig()) as c:
        await c.list_tools()
        await c.list_tools()
    assert counter.calls == 1

    # Handshake-era clients never honor hints, so nothing changes for them.
    counter.calls = 0
    async with Client(mcp, mode="legacy", cache=CacheConfig()) as c:
        await c.list_tools()
        await c.list_tools()
    assert counter.calls == 2
