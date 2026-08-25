"""Auto-injection of `user_google_email` must respect the target's schema.

AuthMiddleware injects the caller's email into tool arguments. Injecting it
into a tool that does not declare the parameter makes Pydantic reject the
call with "Unexpected keyword argument", which makes every zero-argument
tool unreachable — `interactive_tool_manager` was, in a live session.
"""

import types

import pytest
from fastmcp import Client, FastMCP

from auth.middleware import AuthMiddleware, CredentialStorageMode

EMAIL = "someone@example.com"


@pytest.fixture
def server_and_middleware():
    mcp = FastMCP("test-injection")

    @mcp.tool
    def no_arg_tool() -> str:
        """Declares no parameters at all."""
        return "ran"

    @mcp.tool
    def email_tool(user_google_email: str = "") -> str:
        """Declares the parameter and needs it injected."""
        return f"ran as {user_google_email}"

    middleware = AuthMiddleware(storage_mode=CredentialStorageMode.FILE_ENCRYPTED)
    mcp.add_middleware(middleware)
    return mcp, middleware


def _context(mcp, name, arguments=None):
    return types.SimpleNamespace(
        message=types.SimpleNamespace(name=name, arguments=arguments or {}),
        fastmcp_context=types.SimpleNamespace(fastmcp=mcp),
    )


@pytest.mark.asyncio
async def test_no_arg_tool_is_left_alone(server_and_middleware):
    mcp, middleware = server_and_middleware
    ctx = _context(mcp, "no_arg_tool")
    await middleware._auto_inject_email_parameter(ctx, EMAIL)
    assert ctx.message.arguments == {}


@pytest.mark.asyncio
async def test_declared_parameter_is_still_injected(server_and_middleware):
    """The guard must not break the case injection exists for."""
    mcp, middleware = server_and_middleware
    ctx = _context(mcp, "email_tool")
    await middleware._auto_inject_email_parameter(ctx, EMAIL)
    assert ctx.message.arguments == {"user_google_email": EMAIL}


@pytest.mark.asyncio
async def test_no_arg_tool_is_actually_callable(server_and_middleware):
    """End to end: this is the call that failed validation before."""
    mcp, _ = server_and_middleware
    async with Client(mcp) as client:
        result = await client.call_tool("no_arg_tool", {})
    assert result.content[0].text == "ran"


@pytest.mark.asyncio
async def test_unreadable_schema_keeps_injecting(server_and_middleware):
    """Fail open: a lookup failure must not strip the parameter."""
    _, middleware = server_and_middleware
    ctx = types.SimpleNamespace(
        message=types.SimpleNamespace(name="unknown_tool", arguments={}),
        fastmcp_context=None,
    )
    await middleware._auto_inject_email_parameter(ctx, EMAIL)
    assert ctx.message.arguments == {"user_google_email": EMAIL}


@pytest.mark.asyncio
async def test_schema_lookup_is_cached(server_and_middleware):
    mcp, middleware = server_and_middleware
    await middleware._tool_accepts_email(_context(mcp, "no_arg_tool"), "no_arg_tool")
    assert middleware._accepts_email_cache["no_arg_tool"] is False
    await middleware._tool_accepts_email(_context(mcp, "email_tool"), "email_tool")
    assert middleware._accepts_email_cache["email_tool"] is True
