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


# ---------------------------------------------------------------------------
# MCP App backend tools reach the wire as ``<hash>_<local_name>``. get_tool()
# does not resolve that form, so the guard used to fall through to its
# fail-open default and inject into a tool that never declared the parameter —
# the dashboard card's on-mount rows fetch died with "Unexpected keyword
# argument user_google_email" in a live Desktop session.
# ---------------------------------------------------------------------------


@pytest.fixture
def app_server_and_middleware():
    from fastmcp import FastMCPApp
    from fastmcp.server.providers.addressing import hashed_backend_name

    mcp = FastMCP("test-app-injection")
    app = FastMCPApp("Probe")

    @app.tool()
    def keyed_only(key: str) -> dict:
        """Declares no email parameter — like dashboard_rows."""
        return {"key": key}

    @app.tool()
    def wants_email(user_google_email: str = "") -> dict:
        return {"email": user_google_email}

    mcp.add_provider(app)
    middleware = AuthMiddleware(storage_mode=CredentialStorageMode.FILE_ENCRYPTED)
    mcp.add_middleware(middleware)
    names = {
        "keyed_only": hashed_backend_name("Probe", "keyed_only"),
        "wants_email": hashed_backend_name("Probe", "wants_email"),
    }
    return mcp, middleware, names


@pytest.mark.asyncio
async def test_hashed_app_tool_without_the_parameter_is_left_alone(
    app_server_and_middleware,
):
    mcp, middleware, names = app_server_and_middleware
    ctx = _context(mcp, names["keyed_only"], {"key": "k"})
    await middleware._auto_inject_email_parameter(ctx, EMAIL)
    assert ctx.message.arguments == {"key": "k"}
    assert middleware._accepts_email_cache[names["keyed_only"]] is False


@pytest.mark.asyncio
async def test_hashed_app_tool_that_declares_it_is_still_injected(
    app_server_and_middleware,
):
    mcp, middleware, names = app_server_and_middleware
    ctx = _context(mcp, names["wants_email"])
    await middleware._auto_inject_email_parameter(ctx, EMAIL)
    assert ctx.message.arguments == {"user_google_email": EMAIL}


@pytest.mark.asyncio
async def test_dashboard_rows_is_callable_through_the_auth_middleware():
    """The Desktop repro: the card's on-mount fetch, with injection live."""
    from fastmcp.server.providers.addressing import hashed_backend_name

    from middleware import dashboard_cache_middleware as dc
    from tools.ui_apps import DASHBOARD_ROWS_APP, create_dashboard_rows_app

    mcp = FastMCP("test-rows-injection")
    mcp.add_provider(create_dashboard_rows_app())
    mcp.add_middleware(
        AuthMiddleware(storage_mode=CredentialStorageMode.FILE_ENCRYPTED)
    )
    key = dc.stash_dashboard_data("list_gmail_labels", {"labels": [{"name": "x"}]})

    async with Client(mcp) as client:
        result = await client.call_tool(
            hashed_backend_name(DASHBOARD_ROWS_APP, "dashboard_rows"), {"key": key}
        )
    assert result.structured_content["count"] == 1
    assert result.structured_content["rows"][0]["name"] == "x"
