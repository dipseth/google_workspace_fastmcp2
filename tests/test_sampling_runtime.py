"""Tests for the server-side sampling runtime (FastMCP 4 has no ctx.sample)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastmcp.exceptions import ToolError
from mcp.types import (
    CreateMessageResult,
    CreateMessageResultWithTools,
    TextContent,
    ToolResultContent,
    ToolUseContent,
)
from pydantic import BaseModel

from middleware import sampling_runtime as rt


class _Ctx:
    """Minimal stand-in for fastmcp Context (server name + request context)."""

    fastmcp = SimpleNamespace(name="test-server")
    request_context = SimpleNamespace(protocol_version="2025-06-18")


class Answer(BaseModel):
    city: str
    population: int


def _text_result(text: str) -> CreateMessageResult:
    return CreateMessageResult(
        role="assistant",
        content=TextContent(type="text", text=text),
        model="fake",
        stop_reason="endTurn",
    )


def _tool_use_result(name: str, args: dict, call_id: str = "call_1"):
    return CreateMessageResultWithTools(
        role="assistant",
        content=[ToolUseContent(type="tool_use", id=call_id, name=name, input=args)],
        model="fake",
        stop_reason="toolUse",
    )


@pytest.fixture(autouse=True)
def _reset_handler():
    previous = rt.get_sampling_handler()
    yield
    rt.set_sampling_handler(previous)


async def test_no_handler_raises_tool_error():
    rt.set_sampling_handler(None)
    with pytest.raises(ToolError):
        await rt.sample(_Ctx(), "hello")


async def test_plain_text_sample_returns_text_result():
    seen = {}

    async def handler(messages, params, request_context):
        seen["params"] = params
        seen["request_context"] = request_context
        return _text_result("hi there")

    rt.set_sampling_handler(handler)
    result = await rt.sample(
        _Ctx(), "hello", system_prompt="be brief", max_tokens=42, temperature=0.1
    )
    assert result.text == "hi there"
    assert result.result == "hi there"
    # snake_case SDK v2 params reach the handler; request context is forwarded
    assert seen["params"].system_prompt == "be brief"
    assert seen["params"].max_tokens == 42
    assert seen["params"].temperature == 0.1
    assert seen["request_context"] is _Ctx.request_context
    assert [m.role for m in result.history] == ["user", "assistant"]


async def test_string_handler_result_is_wrapped():
    async def handler(messages, params, request_context):
        return "plain string"

    rt.set_sampling_handler(handler)
    result = await rt.sample(_Ctx(), "hello")
    assert result.text == "plain string"


async def test_structured_output_via_final_response_tool():
    calls = []

    async def handler(messages, params, request_context):
        calls.append(params)
        assert any(t.name == "final_response" for t in params.tools)
        assert params.tool_choice.mode == "required"
        return _tool_use_result(
            "final_response", {"city": "Oslo", "population": 700000}
        )

    rt.set_sampling_handler(handler)
    result = await rt.sample(_Ctx(), "which city?", result_type=Answer)
    assert isinstance(result.result, Answer)
    assert result.result.city == "Oslo"
    assert '"population": 700000' in result.text
    assert len(calls) == 1


async def test_structured_output_retries_on_validation_error():
    attempts = []

    async def handler(messages, params, request_context):
        attempts.append(list(messages))  # snapshot: the runtime appends to it
        if len(attempts) == 1:
            return _tool_use_result("final_response", {"city": "Oslo"})  # missing field
        return _tool_use_result("final_response", {"city": "Oslo", "population": 1})

    rt.set_sampling_handler(handler)
    result = await rt.sample(_Ctx(), "which city?", result_type=Answer)
    assert result.result.population == 1
    # The validation error was fed back as a tool result before the retry
    fed_back = attempts[1][-1].content
    assert isinstance(fed_back, list) and isinstance(fed_back[0], ToolResultContent)
    assert fed_back[0].is_error is True


async def test_tool_loop_executes_tools_and_feeds_results_back():
    executed = []

    def lookup(term: str) -> str:
        """Look something up."""
        executed.append(term)
        return f"result for {term}"

    rounds = []

    async def handler(messages, params, request_context):
        rounds.append(list(messages))  # snapshot: the runtime appends to it
        if len(rounds) == 1:
            assert [t.name for t in params.tools] == ["lookup"]
            assert (
                params.tools[0].input_schema["properties"]["term"]["type"] == "string"
            )
            return _tool_use_result("lookup", {"term": "fastmcp"}, call_id="c1")
        return _text_result("done")

    rt.set_sampling_handler(handler)
    result = await rt.sample(_Ctx(), "search", tools=[lookup])
    assert result.text == "done"
    assert executed == ["fastmcp"]
    tool_msg = rounds[1][-1]
    assert tool_msg.role == "user"
    assert tool_msg.content[0].tool_use_id == "c1"
    assert tool_msg.content[0].content[0].text == "result for fastmcp"


async def test_sample_step_without_execution_returns_tool_calls():
    async def handler(messages, params, request_context):
        return _tool_use_result("lookup", {"term": "x"})

    def lookup(term: str) -> str:
        raise AssertionError("must not run when execute_tools=False")

    rt.set_sampling_handler(handler)
    step = await rt.sample_step(_Ctx(), "go", tools=[lookup], execute_tools=False)
    assert step.is_tool_use
    assert [c.name for c in step.tool_calls] == ["lookup"]
    assert step.text is None


def test_sampling_available_only_checks_registration():
    rt.set_sampling_handler(None)
    assert rt.sampling_available() is False
    # A wrapper with no server default can still serve from a per-user config
    # or a header override, so it counts as available; the wrapper itself
    # raises when nothing applies.
    rt.set_sampling_handler(SimpleNamespace(default_handler=None))
    assert rt.sampling_available() is True
    rt.set_sampling_handler(SimpleNamespace(default_handler=object()))
    assert rt.sampling_available() is True


# ── Request-header model override (evals) ────────────────────────────────────


def _fake_headers(headers: dict):
    return {k.lower(): v for k, v in headers.items()}


def test_header_override_is_off_by_default():
    from middleware.session_sampling_handler import SessionAwareSamplingHandler

    handler = SessionAwareSamplingHandler(default_handler=None)
    with (
        patch("config.settings.settings.sampling_allow_header_override", False),
        patch(
            "fastmcp.server.dependencies.get_http_headers",
            return_value=_fake_headers({"X-Sampling-Model": "openai/gpt-x"}),
        ),
    ):
        assert handler._get_request_override_config() is None


def test_header_override_reads_model_base_and_key_when_enabled():
    from middleware.session_sampling_handler import SessionAwareSamplingHandler

    handler = SessionAwareSamplingHandler(default_handler=None)
    with (
        patch("config.settings.settings.sampling_allow_header_override", True),
        patch(
            "fastmcp.server.dependencies.get_http_headers",
            return_value=_fake_headers(
                {
                    "X-Sampling-Model": "openai/gpt-x",
                    "X-Sampling-Api-Base": "https://llm.example/v1",
                    "X-Sampling-Api-Key": "sk-test",
                }
            ),
        ),
    ):
        assert handler._get_request_override_config() == {
            "model": "openai/gpt-x",
            "api_base": "https://llm.example/v1",
            "api_key": "sk-test",
        }


# ── App-only tool filtering ──────────────────────────────────────────────────


def test_is_app_only_reads_meta_ui_visibility():
    from middleware.app_visibility_middleware import is_app_only

    assert is_app_only(SimpleNamespace(meta={"ui": {"visibility": ["app"]}})) is True
    assert (
        is_app_only(SimpleNamespace(meta={"ui": {"visibility": ["app", "model"]}}))
        is False
    )
    assert is_app_only(SimpleNamespace(meta={"ui": {}})) is False
    assert is_app_only(SimpleNamespace(meta=None)) is False
