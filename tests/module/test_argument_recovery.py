"""Unit tests for the general-purpose argument recovery agent."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, ValidationError

from middleware.sampling_middleware import EnhancedSamplingMiddleware

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeToolArgs(BaseModel):
    model_config = {"extra": "forbid"}
    query: str
    page_size: int = 10


def _make_validation_error() -> ValidationError:
    """Create a real Pydantic ValidationError for unexpected keyword arg."""
    try:
        _FakeToolArgs(query="test", max_results=5)  # type: ignore[call-arg]
    except ValidationError as exc:
        return exc
    raise AssertionError("Expected ValidationError")


def _make_context(arguments: dict) -> MagicMock:
    """Build a fake MiddlewareContext with tool arguments."""
    ctx = MagicMock()
    ctx.message.arguments = dict(arguments)
    ctx.message.tool_name = "search_gmail_messages"

    # FastMCP context with tool schema
    tool = MagicMock()
    tool.parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Gmail search query"},
            "page_size": {
                "type": "integer",
                "description": "Maximum number of messages to return",
                "default": 10,
            },
        },
        "required": ["query"],
    }
    tool.description = "Search messages in Gmail"
    ctx.fastmcp_context.fastmcp.get_tool = AsyncMock(return_value=tool)
    return ctx


def _make_middleware() -> EnhancedSamplingMiddleware:
    """Create a minimal middleware instance for testing."""
    mw = object.__new__(EnhancedSamplingMiddleware)
    mw.enable_debug = False
    mw._dsl_configs = {}
    mw._validation_configs = {}
    return mw


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestArgumentRecovery:
    @pytest.mark.asyncio
    async def test_successful_recovery(self):
        """LLM returns corrected args, retry succeeds."""
        mw = _make_middleware()
        ctx = _make_context({"query": "from:test@example.com", "max_results": 5})
        error = _make_validation_error()

        corrected = {"query": "from:test@example.com", "page_size": 5}
        expected_result = MagicMock()

        # Mock SamplingContext.sample to return corrected JSON
        mock_sample_result = MagicMock()
        mock_sample_result.text = json.dumps(corrected)

        call_next = AsyncMock(return_value=expected_result)

        with (
            patch("middleware.sampling_middleware.SamplingContext") as MockSamplingCtx,
            patch(
                "config.settings.settings",
                SimpleNamespace(sampling_argument_recovery_enabled=True),
            ),
        ):
            instance = MockSamplingCtx.return_value
            instance.sample = AsyncMock(return_value=mock_sample_result)

            result = await mw._attempt_argument_recovery(
                ctx, "search_gmail_messages", error, call_next
            )

        assert result is expected_result
        # Verify args were corrected before retry
        assert ctx.message.arguments == corrected

    @pytest.mark.asyncio
    async def test_recovery_returns_none_on_bad_json(self):
        """LLM returns garbage — recovery returns None."""
        mw = _make_middleware()
        ctx = _make_context({"query": "test", "max_results": 5})
        error = _make_validation_error()
        call_next = AsyncMock()

        mock_sample_result = MagicMock()
        mock_sample_result.text = "this is not json"

        with (
            patch("middleware.sampling_middleware.SamplingContext") as MockSamplingCtx,
            patch(
                "config.settings.settings",
                SimpleNamespace(sampling_argument_recovery_enabled=True),
            ),
        ):
            instance = MockSamplingCtx.return_value
            instance.sample = AsyncMock(return_value=mock_sample_result)

            result = await mw._attempt_argument_recovery(
                ctx, "search_gmail_messages", error, call_next
            )

        assert result is None
        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_recovery_disabled_via_setting(self):
        """When setting is disabled, returns None immediately."""
        mw = _make_middleware()
        ctx = _make_context({"query": "test"})
        error = _make_validation_error()
        call_next = AsyncMock()

        with patch(
            "config.settings.settings",
            SimpleNamespace(sampling_argument_recovery_enabled=False),
        ):
            result = await mw._attempt_argument_recovery(
                ctx, "search_gmail_messages", error, call_next
            )

        assert result is None
        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_retry_failure_returns_none_and_restores_args(self):
        """If retry also fails, returns None and restores original args."""
        mw = _make_middleware()
        original_args = {"query": "test", "max_results": 5}
        ctx = _make_context(original_args)
        error = _make_validation_error()

        corrected = {"query": "test", "page_size": 5}
        mock_sample_result = MagicMock()
        mock_sample_result.text = json.dumps(corrected)

        call_next = AsyncMock(side_effect=Exception("still broken"))

        with (
            patch("middleware.sampling_middleware.SamplingContext") as MockSamplingCtx,
            patch(
                "config.settings.settings",
                SimpleNamespace(sampling_argument_recovery_enabled=True),
            ),
        ):
            instance = MockSamplingCtx.return_value
            instance.sample = AsyncMock(return_value=mock_sample_result)

            result = await mw._attempt_argument_recovery(
                ctx, "search_gmail_messages", error, call_next
            )

        assert result is None
        # Original args should be restored
        assert ctx.message.arguments == original_args

    @pytest.mark.asyncio
    async def test_strips_markdown_fences(self):
        """LLM wraps JSON in code fences — should still parse."""
        mw = _make_middleware()
        ctx = _make_context({"query": "test", "max_results": 5})
        error = _make_validation_error()

        corrected = {"query": "test", "page_size": 5}
        expected_result = MagicMock()

        mock_sample_result = MagicMock()
        mock_sample_result.text = f"```json\n{json.dumps(corrected)}\n```"

        call_next = AsyncMock(return_value=expected_result)

        with (
            patch("middleware.sampling_middleware.SamplingContext") as MockSamplingCtx,
            patch(
                "config.settings.settings",
                SimpleNamespace(sampling_argument_recovery_enabled=True),
            ),
        ):
            instance = MockSamplingCtx.return_value
            instance.sample = AsyncMock(return_value=mock_sample_result)

            result = await mw._attempt_argument_recovery(
                ctx, "search_gmail_messages", error, call_next
            )

        assert result is expected_result
