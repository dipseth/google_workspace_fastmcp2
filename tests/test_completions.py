"""Argument completion (resources/completions.py) via ``client.complete()``."""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP
from mcp_types import PromptReference, ResourceTemplateReference

from prompts.gchat_prompts import setup_gchat_prompts
from prompts.gsheets_prompts import setup_gsheets_prompts
from resources import completions
from resources.chat_digest_resources import setup_chat_digest_resources
from resources.completions import setup_completions

DIGEST = "chat://digest/space/{space_code}{?hours,limit}"

SPACES = [
    {"code": "AAAAWvjq2HE", "name": "Engineering"},
    {"code": "AAAA1234", "name": "Announcements"},
    {"code": "BBBB9999", "name": "Eng leads"},
]


@pytest.fixture
def mcp(monkeypatch):
    server = FastMCP("completion-test")

    async def _spaces():
        return list(SPACES)

    monkeypatch.setattr(completions, "_list_spaces", _spaces)
    # FastMCP 4.2 answers completion only for a prompt or template the caller
    # can see, so the real ones are registered here, under their real names.
    setup_chat_digest_resources(server)
    setup_gchat_prompts(server)
    setup_gsheets_prompts(server)
    setup_completions(server)
    return server


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ("auto", "legacy"))
async def test_template_space_code_and_query_params(mcp, mode):
    async with Client(mcp, mode=mode) as c:
        ref = ResourceTemplateReference(uri=DIGEST)
        assert (
            await c.complete(ref, {"name": "space_code", "value": "AAAA"})
        ).values == [
            "AAAAWvjq2HE",
            "AAAA1234",
        ]
        assert (await c.complete(ref, {"name": "space_code", "value": ""})).values == [
            "AAAAWvjq2HE",
            "AAAA1234",
            "BBBB9999",
        ]
        assert (await c.complete(ref, {"name": "hours", "value": "4"})).values == [
            "4",
            "48",
        ]
        assert (await c.complete(ref, {"name": "limit", "value": ""})).values == [
            "5",
            "10",
            "25",
            "50",
        ]


@pytest.mark.asyncio
async def test_prompt_arguments(mcp):
    async with Client(mcp) as c:
        ref = PromptReference(name="smart_contextual_chat_card")
        assert (
            await c.complete(ref, {"name": "target_space", "value": "eng"})
        ).values == [
            "Engineering",
            "Eng leads",
        ]
        assert (
            await c.complete(ref, {"name": "card_purpose", "value": "re"})
        ).values == ["report"]
        ref = PromptReference(name="professional_sheets_dashboard")
        assert (
            "financial summary"
            in (await c.complete(ref, {"name": "dashboard_theme", "value": "f"})).values
        )


@pytest.mark.asyncio
async def test_unknown_reference_and_failures_are_empty(mcp, monkeypatch):
    async with Client(mcp) as c:
        other = ResourceTemplateReference(uri="gmail://messages/{id}")
        assert (await c.complete(other, {"name": "id", "value": ""})).values == []
        ref = PromptReference(name="no_such_prompt")
        assert (await c.complete(ref, {"name": "x", "value": ""})).values == []

        async def _boom():
            raise RuntimeError("chat api down")

        monkeypatch.setattr(completions, "_list_spaces", _boom)
        ref = ResourceTemplateReference(uri=DIGEST)
        assert (
            await c.complete(ref, {"name": "space_code", "value": "A"})
        ).values == []


@pytest.mark.asyncio
async def test_a_prompt_the_server_does_not_serve_gets_no_completions():
    """The handler knows the prompt; FastMCP 4.2 still answers nothing for it."""
    server = FastMCP("handler-only")
    setup_completions(server)

    async with Client(server) as c:
        ref = PromptReference(name="smart_contextual_chat_card")
        assert (
            await c.complete(ref, {"name": "card_purpose", "value": ""})
        ).values == []


@pytest.mark.asyncio
async def test_space_list_is_cached_per_principal(monkeypatch):
    """The Chat API is hit once per five minutes per user, not per keystroke."""
    from auth import user_state

    user_state.set_server(FastMCP("cache"))
    calls = {"n": 0}

    class _Exec:
        def execute(self):
            calls["n"] += 1
            return {"spaces": [{"name": "spaces/X1", "displayName": "X"}]}

    class _Spaces:
        def list(self, pageSize):
            return _Exec()

    class _Service:
        def spaces(self):
            return _Spaces()

    async def _service(email):
        return _Service()

    import gchat.chat_tools as chat_tools

    monkeypatch.setattr(chat_tools, "_get_chat_service_with_fallback", _service)
    monkeypatch.setattr(completions, "_current_email", lambda: "kim@example.com")

    assert await completions._list_spaces() == [{"code": "X1", "name": "X"}]
    assert await completions._list_spaces() == [{"code": "X1", "name": "X"}]
    assert calls["n"] == 1
