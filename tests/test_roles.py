"""Roles claim: admin gating for tools (auth/access_control.py)."""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.auth import AccessToken
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

from auth import access_control
from auth.access_control import ADMIN, is_admin, roles_for_provenance, roles_from_claims
from auth.types import AuthProvenance


def _token(claims: dict, client_id: str = "c") -> AccessToken:
    return AccessToken(token="t", client_id=client_id, scopes=["openid"], claims=claims)


class _As:
    def __init__(self, token):
        self._token = token

    async def __aenter__(self):
        self._reset = auth_context_var.set(
            AuthenticatedUser(self._token) if self._token else None
        )

    async def __aexit__(self, *exc):
        auth_context_var.reset(self._reset)


def test_roles_helpers():
    assert roles_for_provenance(AuthProvenance.API_KEY) == ["admin"]
    assert roles_for_provenance(AuthProvenance.USER_API_KEY) == ["user"]
    assert roles_for_provenance(None) == ["user"]
    assert roles_from_claims({"roles": "admin"}) == ["admin"]
    assert roles_from_claims({"roles": ["user"]}) == ["user"]
    assert roles_from_claims({}) == []
    assert roles_from_claims(None) == []


@pytest.mark.asyncio
async def test_is_admin_reads_claim_with_provenance_fallback():
    async with _As(_token({"roles": ["admin"], "sub": "api-key-user"})):
        assert is_admin() is True
    async with _As(_token({"roles": ["user"], "email": "a@x.com"})):
        assert is_admin() is False
    # A JWT minted before the claim existed: shared-key provenance still counts.
    async with _As(
        _token({"sub": "api-key-user", "auth_method": AuthProvenance.API_KEY})
    ):
        assert is_admin() is True
    async with _As(_token({"roles": [], "auth_method": AuthProvenance.API_KEY})):
        assert is_admin() is False
    async with _As(None):
        assert is_admin() is False


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ("auto", "legacy"))
async def test_admin_tool_is_hidden_and_denied_for_users(mode):
    mcp = FastMCP("roles")

    @mcp.tool(auth=ADMIN)
    def rotate_keys() -> str:
        return "rotated"

    @mcp.tool
    def ping() -> str:
        return "pong"

    async with _As(
        _token({"roles": ["admin"], "sub": "api-key-user"}, "api-key-client")
    ):
        async with Client(mcp, mode=mode) as c:
            assert {t.name for t in await c.list_tools()} == {"rotate_keys", "ping"}
            assert (await c.call_tool("rotate_keys", {})).data == "rotated"

    async with _As(_token({"roles": ["user"], "email": "a@x.com"})):
        async with Client(mcp, mode=mode) as c:
            assert {t.name for t in await c.list_tools()} == {"ping"}
            with pytest.raises(ToolError):
                await c.call_tool("rotate_keys", {})


def test_admin_check_is_a_role_check():
    assert access_control.ADMIN is ADMIN
    assert ADMIN.required_roles == frozenset({"admin"})
