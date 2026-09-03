"""Tests for url-mode OAuth elicitation (tools/elicitation.py).

The interesting axis is the protocol era, because the same request travels two
incompatible shapes: pushed over the back-channel on handshake connections,
returned as an ``InputRequiredResult`` on 2026-07-28. Everything that is not a
url-capable client on a live connection must degrade to ``unsupported`` so the
caller keeps its clickable-link response.
"""

import asyncio

import pytest

from tools import elicitation as oe


class _FakeElicitation:
    def __init__(self, form=None, url=None):
        self.form = form
        self.url = url


class _FakeCapabilities:
    def __init__(self, elicitation=None):
        self.elicitation = elicitation


class _FakeSession:
    def __init__(self, capabilities, protocol_version, url_result=None):
        self.client_capabilities = capabilities
        self.protocol_version = protocol_version
        self._url_result = url_result
        self.calls = []

    async def elicit_url(
        self, *, message, url, elicitation_id, related_request_id=None
    ):
        self.calls.append(
            {"message": message, "url": url, "elicitation_id": elicitation_id}
        )
        if isinstance(self._url_result, Exception):
            raise self._url_result
        return self._url_result


class _FakeResult:
    def __init__(self, action):
        self.action = action


class _FakeContext:
    def __init__(self, session, input_responses=None, request_id="req-1"):
        self.session = session
        self.input_responses = input_responses
        self.request_id = request_id


def _ctx(protocol_version, *, url_capable=True, url_result=None, responses=None):
    elicitation = _FakeElicitation(
        form={} if not url_capable else {}, url={} if url_capable else None
    )
    return _FakeContext(
        _FakeSession(_FakeCapabilities(elicitation), protocol_version, url_result),
        input_responses=responses,
    )


def _patch(monkeypatch, ctx):
    monkeypatch.setattr(oe, "_context", lambda: ctx)


# ── Capability gating ────────────────────────────────────────────────────


def test_no_context_is_unsupported(monkeypatch):
    _patch(monkeypatch, None)
    assert oe.url_elicitation_supported() is False


def test_form_only_client_is_unsupported(monkeypatch):
    _patch(monkeypatch, _ctx("2025-11-25", url_capable=False))
    assert oe.url_elicitation_supported() is False


def test_url_capable_client_is_supported(monkeypatch):
    _patch(monkeypatch, _ctx("2025-11-25"))
    assert oe.url_elicitation_supported() is True


def _bare_ctx(protocol_version, responses=None):
    """``elicitation: {}`` — no form, no url — as Claude Code declares it."""
    return _FakeContext(
        _FakeSession(_FakeCapabilities(_FakeElicitation()), protocol_version),
        input_responses=responses,
    )


def test_bare_declaration_is_not_url_capable(monkeypatch):
    """The client SDK's own reading: Claude Code's MCP SDK throws "Client does
    not support URL-mode elicitation requests" against its bare declaration,
    client-side, before any dialog opens."""
    _patch(monkeypatch, _bare_ctx("2026-07-28"))
    assert oe.url_elicitation_supported() is False


def test_bare_declaration_is_form_capable(monkeypatch):
    _patch(monkeypatch, _bare_ctx("2026-07-28"))
    assert oe.form_elicitation_supported() is True


def test_explicit_form_only_is_form_capable(monkeypatch):
    _patch(monkeypatch, _ctx("2026-07-28", url_capable=False))
    assert oe.form_elicitation_supported() is True


def test_no_elicitation_at_all_supports_neither(monkeypatch):
    _patch(
        monkeypatch,
        _FakeContext(_FakeSession(_FakeCapabilities(None), "2026-07-28")),
    )
    assert oe.url_elicitation_supported() is False
    assert oe.form_elicitation_supported() is False


# ── Form-mode fallback (form-only client on 2026-07-28) ──────────────────


@pytest.mark.asyncio
async def test_form_only_modern_client_gets_a_form_prompt_carrying_the_link(
    monkeypatch,
):
    _patch(monkeypatch, _bare_ctx("2026-07-28"))

    prompt = await oe.prompt_for_oauth("Sign in", "https://accounts.google.com/x")

    assert prompt.outcome == "suspended"
    request = prompt.suspend.input_requests[oe.OAUTH_INPUT_KEY]
    params = request.params.model_dump(by_alias=True)
    assert params["mode"] == "form"
    assert "https://accounts.google.com/x" in params["message"]
    assert params["requestedSchema"] == oe.OAUTH_FORM_SCHEMA


@pytest.mark.asyncio
async def test_form_only_handshake_client_keeps_the_link(monkeypatch):
    """A handshake-era form push is a different interaction; not attempted."""
    ctx = _bare_ctx("2025-11-25")
    _patch(monkeypatch, ctx)

    prompt = await oe.prompt_for_oauth("Sign in", "https://example.com/auth")

    assert prompt.outcome == "unsupported"
    assert ctx.session.calls == []


def test_form_answer_is_read_like_the_url_answer(monkeypatch):
    answer = _FakeResult("accept")
    _patch(monkeypatch, _bare_ctx("2026-07-28", responses={oe.OAUTH_INPUT_KEY: answer}))
    assert oe.answered_oauth_prompt() is answer


@pytest.mark.asyncio
async def test_unsupported_client_falls_back(monkeypatch):
    _patch(monkeypatch, _ctx("2025-11-25", url_capable=False))
    prompt = await oe.prompt_for_oauth("m", "https://example.com/auth")
    assert prompt.outcome == "unsupported"
    assert prompt.handled is False


# ── 2026-07-28: return an InputRequiredResult ────────────────────────────


@pytest.mark.asyncio
async def test_modern_protocol_suspends(monkeypatch):
    _patch(monkeypatch, _ctx("2026-07-28"))
    prompt = await oe.prompt_for_oauth(
        "Authorize access",
        "https://accounts.google.com/o/oauth2/auth",
        request_state="s",
    )

    assert prompt.outcome == "suspended"
    assert prompt.handled is True

    wire = prompt.suspend.model_dump(by_alias=True, exclude_none=True)
    assert wire["resultType"] == "input_required"
    assert wire["requestState"] == "s"

    params = wire["inputRequests"][oe.OAUTH_INPUT_KEY]["params"]
    assert params["mode"] == "url"
    assert params["url"] == "https://accounts.google.com/o/oauth2/auth"
    assert params["message"] == "Authorize access"
    assert params["elicitationId"]


@pytest.mark.asyncio
async def test_modern_protocol_never_uses_the_back_channel(monkeypatch):
    ctx = _ctx("2026-07-28")
    _patch(monkeypatch, ctx)
    await oe.prompt_for_oauth("m", "https://example.com/auth")
    assert ctx.session.calls == []


# ── Handshake era: push over the back-channel ────────────────────────────


@pytest.mark.asyncio
async def test_handshake_accept_completes(monkeypatch):
    ctx = _ctx("2025-11-25", url_result=_FakeResult("accept"))
    _patch(monkeypatch, ctx)
    prompt = await oe.prompt_for_oauth("m", "https://example.com/auth")

    assert prompt.outcome == "completed"
    assert prompt.handled is True
    assert ctx.session.calls[0]["url"] == "https://example.com/auth"


@pytest.mark.parametrize("action", ["decline", "cancel"])
@pytest.mark.asyncio
async def test_handshake_refusal_declines(monkeypatch, action):
    _patch(monkeypatch, _ctx("2025-11-25", url_result=_FakeResult(action)))
    prompt = await oe.prompt_for_oauth("m", "https://example.com/auth")

    assert prompt.outcome == "declined"
    assert prompt.action == action
    # A refusal is not "handled": the caller must not pretend it succeeded,
    # but it also must not fall through to the link response.
    assert prompt.handled is False


@pytest.mark.asyncio
async def test_unanswered_prompt_falls_back(monkeypatch):
    """A client that never answers must not pin the tool call open."""
    ctx = _ctx("2025-11-25", url_result=_FakeResult("accept"))

    async def _never_answers(**_kwargs):
        await asyncio.sleep(10)

    ctx.session.elicit_url = _never_answers
    _patch(monkeypatch, ctx)
    monkeypatch.setattr(oe, "ELICIT_TIMEOUT_SECONDS", 0.01)

    prompt = await oe.prompt_for_oauth("m", "https://example.com/auth")
    assert prompt.outcome == "unsupported"


@pytest.mark.asyncio
async def test_back_channel_error_falls_back(monkeypatch):
    _patch(monkeypatch, _ctx("2025-11-25", url_result=RuntimeError("no back-channel")))
    prompt = await oe.prompt_for_oauth("m", "https://example.com/auth")
    assert prompt.outcome == "unsupported"


# ── Nested calls (Code Mode) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_nested_call_never_suspends(monkeypatch):
    """A suspend result would reach Code Mode's sandbox as an empty value."""
    ctx = _ctx("2026-07-28")
    _patch(monkeypatch, ctx)

    with oe.suppress_elicitation():
        prompt = await oe.prompt_for_oauth("m", "https://example.com/auth")

    assert prompt.outcome == "unsupported"
    assert prompt.suspend is None


@pytest.mark.asyncio
async def test_suppression_is_scoped(monkeypatch):
    """Leaving the block restores normal behavior for the next call."""
    _patch(monkeypatch, _ctx("2026-07-28"))

    with oe.suppress_elicitation():
        pass

    prompt = await oe.prompt_for_oauth("m", "https://example.com/auth")
    assert prompt.outcome == "suspended"


# ── Reading the answer on the re-run ─────────────────────────────────────


def test_answer_absent_on_first_round(monkeypatch):
    _patch(monkeypatch, _ctx("2026-07-28"))
    assert oe.answered_oauth_prompt() is None


def test_answer_read_from_input_responses(monkeypatch):
    answer = _FakeResult("accept")
    _patch(monkeypatch, _ctx("2026-07-28", responses={oe.OAUTH_INPUT_KEY: answer}))
    assert oe.answered_oauth_prompt() is answer


def test_answer_ignores_other_keys(monkeypatch):
    _patch(
        monkeypatch,
        _ctx("2026-07-28", responses={"something_else": _FakeResult("accept")}),
    )
    assert oe.answered_oauth_prompt() is None
