"""Photos scope step-up (auth/scope_step_up.py)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.auth import AccessToken
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

from auth import scope_step_up as ssu
from auth.scope_step_up import (
    ScopeStepUpMiddleware,
    has_photos_credentials,
    missing_photos_scopes,
    photos_required_scopes,
    scopes_for_principal,
)
from tools import elicitation as el
from tools.elicitation import ElicitationPrompt

BASE = ["openid", "https://www.googleapis.com/auth/drive"]


@pytest.fixture
def creds_dir(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "credentials_dir", str(tmp_path))
    return tmp_path


def _grant_photos(creds_dir, email, encrypted=False):
    from auth.google_auth import _get_credentials_path

    path = _get_credentials_path(email, "photos")
    if encrypted:
        path = path.with_suffix(".enc")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")


def _token(email, scopes):
    return AccessToken(
        token="t",
        client_id="c",
        scopes=list(scopes),
        claims={"email": email, "sub": "123"},
    )


class _As:
    def __init__(self, token):
        self._token = token

    async def __aenter__(self):
        self._reset = auth_context_var.set(
            AuthenticatedUser(self._token) if self._token else None
        )

    async def __aexit__(self, *exc):
        auth_context_var.reset(self._reset)


def _ctx(tool_name, tags=("photos",)):
    tool = SimpleNamespace(tags=set(tags))
    server = SimpleNamespace(get_tool=AsyncMock(return_value=tool))
    return SimpleNamespace(
        message=SimpleNamespace(name=tool_name),
        fastmcp_context=SimpleNamespace(fastmcp=server),
    )


# ---------------------------------------------------------------------------
# Scope minting
# ---------------------------------------------------------------------------


def test_photos_scopes_follow_the_photos_credential(creds_dir):
    photos = photos_required_scopes()
    assert photos and all("photoslibrary" in s for s in photos)

    assert has_photos_credentials("ann@example.com") is False
    assert scopes_for_principal("ann@example.com", BASE) == BASE

    _grant_photos(creds_dir, "ann@example.com")
    assert has_photos_credentials("Ann@Example.com") is True
    assert scopes_for_principal("ann@example.com", BASE) == BASE + photos

    _grant_photos(creds_dir, "bea@example.com", encrypted=True)
    assert has_photos_credentials("bea@example.com") is True

    # The shared key carries Photos regardless.
    assert scopes_for_principal(None, BASE, admin=True) == BASE + photos
    assert scopes_for_principal(None, BASE) == BASE
    assert missing_photos_scopes(_token("x", BASE)) == photos
    assert missing_photos_scopes(_token("x", BASE + photos)) == []


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_photos_tool_and_no_token_pass_through(creds_dir):
    mw = ScopeStepUpMiddleware()
    call_next = AsyncMock(return_value="ran")

    async with _As(_token("ann@example.com", BASE)):
        assert (
            await mw.on_call_tool(
                _ctx("search_drive_files", tags=("drive",)), call_next
            )
            == "ran"
        )
    async with _As(None):
        assert await mw.on_call_tool(_ctx("list_photos_albums"), call_next) == "ran"
    assert call_next.await_count == 2


@pytest.mark.asyncio
async def test_photos_tool_with_scopes_runs(creds_dir):
    mw = ScopeStepUpMiddleware()
    call_next = AsyncMock(return_value="albums")
    async with _As(_token("ann@example.com", BASE + photos_required_scopes())):
        assert await mw.on_call_tool(_ctx("list_photos_albums"), call_next) == "albums"


@pytest.mark.asyncio
async def test_shortfall_suspends_with_photos_only_link(creds_dir, monkeypatch):
    mw = ScopeStepUpMiddleware()
    call_next = AsyncMock(return_value="albums")
    seen = {}

    async def _url(email):
        seen["email"] = email
        return "https://accounts.google.com/o/oauth2/auth?scope=photos"

    import mcp_types

    ask = mcp_types.InputRequiredResult(
        resultType="input_required",
        inputRequests={},
        requestState="scope_step_up:photos:ann@example.com",
    )

    async def _prompt(*, message, url, request_state=None):
        seen["message"], seen["url"], seen["state"] = message, url, request_state
        return ElicitationPrompt("suspended", suspend=ask)

    monkeypatch.setattr(ssu, "_photos_auth_url", _url)
    monkeypatch.setattr(el, "prompt_for_oauth", _prompt)
    monkeypatch.setattr(el, "answered_oauth_prompt", lambda ctx=None: None)

    async with _As(_token("ann@example.com", BASE)):
        result = await mw.on_call_tool(_ctx("list_photos_albums"), call_next)

    # Same wrapper a guard tool's own ask gets, so the wire handler and the
    # Code Mode bridge treat it as an ask rather than tool content.
    from fastmcp.tools.base import InputRequiredToolResult

    assert isinstance(result, InputRequiredToolResult)
    assert result.input_required is ask
    call_next.assert_not_awaited()
    assert seen["email"] == "ann@example.com"
    assert seen["url"].endswith("scope=photos")
    assert "Photos" in seen["message"]
    assert seen["state"] == "scope_step_up:photos:ann@example.com"


@pytest.mark.asyncio
async def test_no_elicitation_gets_the_link_in_the_error(creds_dir, monkeypatch):
    mw = ScopeStepUpMiddleware()

    async def _url(email):
        return "https://auth.example/photos"

    async def _prompt(**kw):
        return ElicitationPrompt("unsupported")

    monkeypatch.setattr(ssu, "_photos_auth_url", _url)
    monkeypatch.setattr(el, "prompt_for_oauth", _prompt)
    monkeypatch.setattr(el, "answered_oauth_prompt", lambda ctx=None: None)

    async with _As(_token("ann@example.com", BASE)):
        with pytest.raises(ToolError, match="https://auth.example/photos"):
            await mw.on_call_tool(_ctx("list_photos_albums"), AsyncMock())


@pytest.mark.asyncio
async def test_handshake_completion_widens_token_and_runs(creds_dir, monkeypatch):
    mw = ScopeStepUpMiddleware()
    call_next = AsyncMock(return_value="albums")
    token = _token("ann@example.com", BASE)

    async def _url(email):
        _grant_photos(creds_dir, email)  # the user finishes OAuth during the push
        return "https://auth.example/photos"

    async def _prompt(**kw):
        return ElicitationPrompt("completed", action="accept")

    monkeypatch.setattr(ssu, "_photos_auth_url", _url)
    monkeypatch.setattr(el, "prompt_for_oauth", _prompt)
    monkeypatch.setattr(el, "answered_oauth_prompt", lambda ctx=None: None)

    async with _As(token):
        assert await mw.on_call_tool(_ctx("list_photos_albums"), call_next) == "albums"
    assert missing_photos_scopes(token) == []


@pytest.mark.asyncio
async def test_declined_and_unfinished_rerun_do_not_loop(creds_dir, monkeypatch):
    mw = ScopeStepUpMiddleware()

    async def _url(email):
        return "https://auth.example/photos"

    monkeypatch.setattr(ssu, "_photos_auth_url", _url)

    async def _declined(**kw):
        return ElicitationPrompt("declined", action="decline")

    monkeypatch.setattr(el, "prompt_for_oauth", _declined)
    monkeypatch.setattr(el, "answered_oauth_prompt", lambda ctx=None: None)
    async with _As(_token("ann@example.com", BASE)):
        with pytest.raises(ToolError, match="decline"):
            await mw.on_call_tool(_ctx("list_photos_albums"), AsyncMock())

    # Re-run after a 2026-07-28 prompt the user "accepted" without finishing:
    # the token still lacks Photos, so the answer is the link, not a new prompt.
    prompted = AsyncMock()
    monkeypatch.setattr(el, "prompt_for_oauth", prompted)
    monkeypatch.setattr(
        el, "answered_oauth_prompt", lambda ctx=None: SimpleNamespace(action="accept")
    )
    async with _As(_token("ann@example.com", BASE)):
        with pytest.raises(ToolError, match="did not complete"):
            await mw.on_call_tool(_ctx("list_photos_albums"), AsyncMock())
    prompted.assert_not_awaited()
