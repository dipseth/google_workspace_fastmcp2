"""Tests for sampling tools and their initiation paths.

Covers areas not tested by test_sampling_middleware_unit.py:
- Validation agent execution (_run_validation_agent)
- Pre-validation DSL recovery flow (_pre_validate_dsl)
- LiteLLM handler message/tool/result conversion
- LiteLLM handler cost tracking (single call, not double)
- SessionAwareSamplingHandler routing
- on_call_tool middleware dispatch (pre/parallel validation, DSL enrichment)
- Draft variations flow via _generate_draft_variations mock
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import SamplingMessage as MCPSamplingMessage
from mcp.types import TextContent as MCPTextContent
from mcp.types import ToolResultContent, ToolUseContent

from middleware.sampling_middleware import (
    DSLToolConfig,
    EnhancedSamplingMiddleware,
    SamplingContext,
    ValidationAgentConfig,
    ValidationResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_config(
    dsl_type_label: str = "card",
    arg_key: str = "card_description",
    error_keywords: list | None = None,
) -> DSLToolConfig:
    """Build a minimal DSLToolConfig with mock callables."""
    mock_parse = MagicMock(
        return_value=MagicMock(is_valid=True, issues=[], suggestions=[], root_nodes=[])
    )
    mock_extract = MagicMock(return_value=None)
    return DSLToolConfig(
        arg_key=arg_key,
        parse_fn=mock_parse,
        extract_fn=mock_extract,
        result_type=MagicMock,
        description_attr=f"{dsl_type_label}_description",
        params_attr=f"{dsl_type_label}_params",
        params_arg_key=f"{dsl_type_label}_params",
        get_docs_fn=lambda: f"Mock {dsl_type_label} DSL docs",
        dsl_type_label=dsl_type_label,
        error_keywords=error_keywords,
    )


def _make_middleware_with_validation(
    enabled: bool = True,
    mode: str = "pre",
) -> EnhancedSamplingMiddleware:
    """Build middleware with validation agent registered."""
    mw = EnhancedSamplingMiddleware(
        dsl_tool_configs={
            "send_dynamic_card": _make_mock_config(
                "card", "card_description", ["card_description"]
            ),
        }
    )
    mw.register_validation_agent(
        "send_dynamic_card",
        ValidationAgentConfig(
            tool_name="send_dynamic_card",
            target_arg_keys=["card_description", "card_params"],
            get_system_prompt_fn=lambda args: "You are a validator.",
            mode=mode,
            enabled=enabled,
        ),
    )
    return mw


def _make_mock_context(tool_name: str, arguments: dict) -> MagicMock:
    """Build a mock MiddlewareContext for on_call_tool tests."""
    context = MagicMock()
    context.message.name = tool_name
    context.message.arguments = arguments
    context.fastmcp_context = MagicMock()
    # Mock get_tool to return a tool with no target tags
    mock_tool = MagicMock()
    mock_tool.tags = set()
    context.fastmcp_context.fastmcp.get_tool = AsyncMock(return_value=mock_tool)
    return context


# ===========================================================================
# Validation Agent — _run_validation_agent
# ===========================================================================


class TestRunValidationAgent:
    """Tests for the _run_validation_agent method."""

    @pytest.mark.asyncio
    async def test_returns_none_when_disabled(self):
        """Disabled config should short-circuit to None."""
        mw = _make_middleware_with_validation(enabled=False)
        config = mw._validation_configs["send_dynamic_card"]
        ctx = _make_mock_context("send_dynamic_card", {"card_description": "test"})
        result = await mw._run_validation_agent(ctx, "send_dynamic_card", config)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_target_args(self):
        """If none of the target arg keys are present, skip validation."""
        mw = _make_middleware_with_validation()
        config = mw._validation_configs["send_dynamic_card"]
        ctx = _make_mock_context("send_dynamic_card", {"unrelated_arg": "value"})
        result = await mw._run_validation_agent(ctx, "send_dynamic_card", config)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_validation_result_on_success(self):
        """When sampling returns a valid ValidationResult, it should be returned."""
        mw = _make_middleware_with_validation()
        config = mw._validation_configs["send_dynamic_card"]

        valid_result = ValidationResult(
            is_valid=True,
            confidence=0.95,
            issues=[],
        )
        # Mock the SamplingContext.sample to return a mock with .result
        mock_sampling_result = MagicMock()
        mock_sampling_result.result = valid_result

        ctx = _make_mock_context(
            "send_dynamic_card",
            {"card_description": "§[δ×2]", "card_params": {}},
        )

        with patch(
            "middleware.sampling_middleware.SamplingContext.sample",
            new_callable=AsyncMock,
            return_value=mock_sampling_result,
        ):
            result = await mw._run_validation_agent(ctx, "send_dynamic_card", config)

        assert result is not None
        assert result.is_valid is True
        assert result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_returns_none_on_sampling_failure(self):
        """Sampling failures should return None (advisory, never blocks)."""
        mw = _make_middleware_with_validation()
        config = mw._validation_configs["send_dynamic_card"]

        ctx = _make_mock_context(
            "send_dynamic_card",
            {"card_description": "§[δ×2]"},
        )

        with patch(
            "middleware.sampling_middleware.SamplingContext.sample",
            new_callable=AsyncMock,
            side_effect=Exception("LLM unavailable"),
        ):
            result = await mw._run_validation_agent(ctx, "send_dynamic_card", config)

        assert result is None

    @pytest.mark.asyncio
    async def test_structured_output_fallback_retries_without_result_type(self):
        """When structured output fails (final_response error), retry without
        result_type and parse JSON from text response."""
        from fastmcp.exceptions import ToolError

        mw = _make_middleware_with_validation()
        config = mw._validation_configs["send_dynamic_card"]

        ctx = _make_mock_context(
            "send_dynamic_card",
            {"card_description": "§[δ×2]", "card_params": {}},
        )

        # First call raises ToolError with "final_response" (structured output failure),
        # second call returns plain text JSON
        valid_json = json.dumps(
            {"is_valid": True, "confidence": 0.9, "issues": [], "suggestions": []}
        )
        mock_text_result = MagicMock()
        mock_text_result.result = None
        mock_text_result.text = valid_json

        call_count = 0

        async def _side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call with result_type — fail with structured output error
                raise ToolError(
                    "LLM sampling failed: Expected structured output of type "
                    "ValidationResult, but the LLM returned a text response "
                    "instead of calling the final_response tool."
                )
            # Second call without result_type — return text
            return mock_text_result

        with patch(
            "middleware.sampling_middleware.SamplingContext.sample",
            new_callable=AsyncMock,
            side_effect=_side_effect,
        ):
            result = await mw._run_validation_agent(
                ctx, "send_dynamic_card", config
            )

        assert result is not None
        assert result.is_valid is True
        assert result.confidence == 0.9
        assert call_count == 2  # Confirms retry happened

    @pytest.mark.asyncio
    async def test_structured_output_fallback_with_markdown_fenced_json(self):
        """Fallback should strip markdown code fences from text response."""
        from fastmcp.exceptions import ToolError

        mw = _make_middleware_with_validation()
        config = mw._validation_configs["send_dynamic_card"]

        ctx = _make_mock_context(
            "send_dynamic_card",
            {"card_description": "§[δ×2]", "card_params": {}},
        )

        fenced_json = '```json\n{"is_valid": false, "confidence": 0.7, "issues": ["bad structure"], "suggestions": ["fix it"]}\n```'
        mock_text_result = MagicMock()
        mock_text_result.result = None
        mock_text_result.text = fenced_json

        call_count = 0

        async def _side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ToolError(
                    "Expected structured output instead of calling the final_response tool."
                )
            return mock_text_result

        with patch(
            "middleware.sampling_middleware.SamplingContext.sample",
            new_callable=AsyncMock,
            side_effect=_side_effect,
        ):
            result = await mw._run_validation_agent(
                ctx, "send_dynamic_card", config
            )

        assert result is not None
        assert result.is_valid is False
        assert result.issues == ["bad structure"]

    @pytest.mark.asyncio
    async def test_returns_none_when_global_kill_switch_off(self):
        """Global sampling_validation_enabled=False should return None."""
        mw = _make_middleware_with_validation()
        config = mw._validation_configs["send_dynamic_card"]
        ctx = _make_mock_context(
            "send_dynamic_card",
            {"card_description": "test"},
        )

        with patch(
            "middleware.sampling_middleware._settings",
            create=True,
        ):
            with patch(
                "config.settings.settings",
                MagicMock(sampling_validation_enabled=False),
            ):
                result = await mw._run_validation_agent(
                    ctx, "send_dynamic_card", config
                )

        assert result is None


# ===========================================================================
# on_call_tool — validation dispatch
# ===========================================================================


class TestOnCallToolValidation:
    """Tests for the on_call_tool middleware dispatch."""

    @pytest.mark.asyncio
    async def test_pre_validation_applies_corrections_only_when_invalid(self):
        """Pre-validation should only apply corrections when is_valid=False."""
        mw = _make_middleware_with_validation(mode="pre")

        original_args = {
            "card_description": "§[δ×2]",
            "card_params": {"title": "Test"},
        }
        ctx = _make_mock_context("send_dynamic_card", dict(original_args))

        # Validation says valid but returns validated_input (echoed back)
        valid_result = ValidationResult(
            is_valid=True,
            confidence=1.0,
            validated_input={"card_description": "OVERWRITTEN"},
        )

        call_next = AsyncMock(return_value=MagicMock(content=[]))

        with patch.object(
            mw,
            "_run_validation_agent",
            new_callable=AsyncMock,
            return_value=valid_result,
        ):
            await mw.on_call_tool(ctx, call_next)

        # Arguments should NOT be overwritten because is_valid=True
        assert ctx.message.arguments["card_description"] == "§[δ×2]"

    @pytest.mark.asyncio
    async def test_pre_validation_applies_corrections_when_invalid(self):
        """Pre-validation should apply corrections when is_valid=False."""
        mw = _make_middleware_with_validation(mode="pre")

        ctx = _make_mock_context(
            "send_dynamic_card",
            {"card_description": "§[INVALID]", "card_params": {}},
        )

        invalid_result = ValidationResult(
            is_valid=False,
            confidence=0.8,
            validated_input={"card_description": "§[δ×2]"},
            issues=["Unknown symbol INVALID"],
        )

        call_next = AsyncMock(return_value=MagicMock(content=[]))

        with patch.object(
            mw,
            "_run_validation_agent",
            new_callable=AsyncMock,
            return_value=invalid_result,
        ):
            await mw.on_call_tool(ctx, call_next)

        # Arguments SHOULD be corrected because is_valid=False
        assert ctx.message.arguments["card_description"] == "§[δ×2]"

    @pytest.mark.asyncio
    async def test_parallel_validation_attaches_metadata(self):
        """Parallel validation should attach metadata to the result."""
        mw = EnhancedSamplingMiddleware(
            dsl_tool_configs={
                "qdrant_search": _make_mock_config("qdrant", "query"),
            }
        )
        mw.register_validation_agent(
            "qdrant_search",
            ValidationAgentConfig(
                tool_name="qdrant_search",
                target_arg_keys=["query"],
                get_system_prompt_fn=lambda args: "Validate query.",
                mode="parallel",
            ),
        )

        ctx = _make_mock_context("qdrant_search", {"query": "test search"})

        parallel_result = ValidationResult(
            is_valid=True,
            confidence=0.9,
        )

        # Create a mock ToolResult with meta support
        from fastmcp.tools.tool import ToolResult

        mock_tool_result = ToolResult(content=[])
        call_next = AsyncMock(return_value=mock_tool_result)

        with patch.object(
            mw,
            "_run_validation_agent",
            new_callable=AsyncMock,
            return_value=parallel_result,
        ):
            result = await mw.on_call_tool(ctx, call_next)

        # Metadata should be attached
        assert result.meta is not None
        assert result.meta["validation"]["is_valid"] is True

    @pytest.mark.asyncio
    async def test_no_context_skips_everything(self):
        """When fastmcp_context is None, should just call_next."""
        mw = _make_middleware_with_validation()
        ctx = MagicMock()
        ctx.message.name = "send_dynamic_card"
        ctx.fastmcp_context = None

        call_next = AsyncMock(return_value="passthrough")
        result = await mw.on_call_tool(ctx, call_next)

        assert result == "passthrough"
        call_next.assert_awaited_once_with(ctx)


# ===========================================================================
# Pre-validate DSL — recovery flow
# ===========================================================================


class TestPreValidateDsl:
    """Tests for the _pre_validate_dsl recovery flow."""

    @pytest.mark.asyncio
    async def test_skips_when_no_arg_key(self):
        """If the DSL arg key is missing from arguments, skip."""
        mw = EnhancedSamplingMiddleware(
            dsl_tool_configs={
                "send_dynamic_card": _make_mock_config("card", "card_description"),
            }
        )
        ctx = _make_mock_context("send_dynamic_card", {"other_arg": "value"})
        # Should not raise
        await mw._pre_validate_dsl(ctx, "send_dynamic_card")

    @pytest.mark.asyncio
    async def test_skips_when_no_dsl_extracted(self):
        """If extract_fn returns None, skip validation."""
        config = _make_mock_config("card", "card_description")
        config.extract_fn = MagicMock(return_value=None)
        mw = EnhancedSamplingMiddleware(dsl_tool_configs={"send_dynamic_card": config})
        ctx = _make_mock_context(
            "send_dynamic_card", {"card_description": "just plain text"}
        )
        await mw._pre_validate_dsl(ctx, "send_dynamic_card")
        config.extract_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_when_dsl_is_valid(self):
        """Valid DSL should pass through without recovery."""
        config = _make_mock_config("card", "card_description")
        config.extract_fn = MagicMock(return_value="§[δ×2]")
        config.parse_fn = MagicMock(return_value=MagicMock(is_valid=True, issues=[]))
        mw = EnhancedSamplingMiddleware(dsl_tool_configs={"send_dynamic_card": config})
        ctx = _make_mock_context("send_dynamic_card", {"card_description": "§[δ×2]"})
        await mw._pre_validate_dsl(ctx, "send_dynamic_card")
        # parse_fn called, but no recovery attempted
        config.parse_fn.assert_called_once_with("§[δ×2]")

    @pytest.mark.asyncio
    async def test_recovery_updates_arguments_on_success(self):
        """When recovery succeeds, arguments should be updated."""
        config = _make_mock_config("card", "card_description")
        config.extract_fn = MagicMock(return_value="§[INVALID]")
        config.parse_fn = MagicMock(
            return_value=MagicMock(is_valid=False, issues=["bad symbol"])
        )
        mw = EnhancedSamplingMiddleware(dsl_tool_configs={"send_dynamic_card": config})

        # Mock the recovery function
        recovered = MagicMock()
        recovered.card_description = "§[δ×2]"
        recovered.card_params = {"title": "Fixed"}

        ctx = _make_mock_context(
            "send_dynamic_card",
            {"card_description": "§[INVALID]", "card_params": {}},
        )

        with patch(
            "middleware.sampling_middleware._validate_and_recover_dsl",
            new_callable=AsyncMock,
            return_value=(recovered, []),
        ):
            await mw._pre_validate_dsl(ctx, "send_dynamic_card")

        assert ctx.message.arguments["card_description"] == "§[δ×2]"
        assert ctx.message.arguments["card_params"] == {"title": "Fixed"}

    @pytest.mark.asyncio
    async def test_recovery_failure_leaves_arguments_unchanged(self):
        """When recovery fails, original arguments stay."""
        config = _make_mock_config("card", "card_description")
        config.extract_fn = MagicMock(return_value="§[BAD]")
        config.parse_fn = MagicMock(
            return_value=MagicMock(is_valid=False, issues=["invalid"])
        )
        mw = EnhancedSamplingMiddleware(dsl_tool_configs={"send_dynamic_card": config})

        ctx = _make_mock_context(
            "send_dynamic_card",
            {"card_description": "§[BAD]", "card_params": {}},
        )

        with patch(
            "middleware.sampling_middleware._validate_and_recover_dsl",
            new_callable=AsyncMock,
            side_effect=Exception("recovery crashed"),
        ):
            await mw._pre_validate_dsl(ctx, "send_dynamic_card")

        # Original unchanged
        assert ctx.message.arguments["card_description"] == "§[BAD]"


# ===========================================================================
# LiteLLM handler — message conversion
# ===========================================================================


class TestLiteLLMMessageConversion:
    """Tests for LiteLLMSamplingHandler message conversion."""

    def _handler(self):
        from middleware.litellm_sampling_handler import LiteLLMSamplingHandler

        return LiteLLMSamplingHandler(default_model="test/model")

    def test_text_message_conversion(self):
        """TextContent messages should convert to role/content dicts."""
        handler = self._handler()
        messages = [
            MCPSamplingMessage(
                role="user",
                content=MCPTextContent(type="text", text="Hello"),
            ),
        ]
        result = handler._convert_messages(messages, system_prompt="Be helpful.")
        assert len(result) == 2
        assert result[0] == {"role": "system", "content": "Be helpful."}
        assert result[1] == {"role": "user", "content": "Hello"}

    def test_same_role_messages_merge(self):
        """Consecutive same-role text messages should be merged."""
        handler = self._handler()
        messages = [
            MCPSamplingMessage(
                role="user",
                content=MCPTextContent(type="text", text="First"),
            ),
            MCPSamplingMessage(
                role="user",
                content=MCPTextContent(type="text", text="Second"),
            ),
        ]
        result = handler._convert_messages(messages, system_prompt=None)
        assert len(result) == 1
        assert result[0]["content"] == "First\nSecond"

    def test_tool_use_content_conversion(self):
        """ToolUseContent should convert to assistant message with tool_calls."""
        handler = self._handler()
        messages = [
            MCPSamplingMessage(
                role="assistant",
                content=ToolUseContent(
                    type="tool_use",
                    id="call_123",
                    name="search",
                    input={"query": "test"},
                ),
            ),
        ]
        result = handler._convert_messages(messages, system_prompt=None)
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert len(result[0]["tool_calls"]) == 1
        tc = result[0]["tool_calls"][0]
        assert tc["id"] == "call_123"
        assert tc["function"]["name"] == "search"
        assert json.loads(tc["function"]["arguments"]) == {"query": "test"}

    def test_tool_result_content_conversion(self):
        """ToolResultContent should convert to tool role message."""
        handler = self._handler()
        messages = [
            MCPSamplingMessage(
                role="user",
                content=ToolResultContent(
                    type="tool_result",
                    toolUseId="call_123",
                    toolCallId="call_123",
                    content=[
                        MCPTextContent(type="text", text="Search found 5 results")
                    ],
                ),
            ),
        ]
        result = handler._convert_messages(messages, system_prompt=None)
        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "call_123"
        assert "Search found 5 results" in result[0]["content"]

    def test_no_system_prompt(self):
        """When system_prompt is None, no system message should be added."""
        handler = self._handler()
        messages = [
            MCPSamplingMessage(
                role="user",
                content=MCPTextContent(type="text", text="Hi"),
            ),
        ]
        result = handler._convert_messages(messages, system_prompt=None)
        assert len(result) == 1
        assert result[0]["role"] == "user"


# ===========================================================================
# LiteLLM handler — result conversion
# ===========================================================================


class TestLiteLLMResultConversion:
    """Tests for _to_result method."""

    def _handler(self):
        from middleware.litellm_sampling_handler import LiteLLMSamplingHandler

        return LiteLLMSamplingHandler(default_model="test/model")

    def _make_response(self, content="Hello", tool_calls=None, finish_reason="stop"):
        """Build a mock LiteLLM response."""
        message = MagicMock()
        message.content = content
        message.tool_calls = tool_calls
        choice = MagicMock()
        choice.message = message
        choice.finish_reason = finish_reason
        response = MagicMock()
        response.choices = [choice]
        response.model = "test/model"
        return response

    def test_text_result(self):
        """Plain text response should produce CreateMessageResult."""
        handler = self._handler()
        response = self._make_response(content="Hello world")
        result = handler._to_result(response, with_tools=False)
        assert result.role == "assistant"
        assert result.content.text == "Hello world"
        assert result.stopReason == "endTurn"

    def test_tool_call_result(self):
        """Response with tool calls should produce CreateMessageResultWithTools."""
        handler = self._handler()
        tc = MagicMock()
        tc.id = "call_456"
        tc.function.name = "search"
        tc.function.arguments = '{"query": "test"}'
        response = self._make_response(
            content=None, tool_calls=[tc], finish_reason="tool_calls"
        )
        result = handler._to_result(response, with_tools=True)
        assert result.stopReason == "toolUse"
        # Should have at least one ToolUseContent block
        tool_blocks = [
            b for b in result.content if getattr(b, "type", None) == "tool_use"
        ]
        assert len(tool_blocks) == 1
        assert tool_blocks[0].name == "search"

    def test_empty_response_gets_fallback(self):
        """Response with no content and no tool calls should get empty text block."""
        handler = self._handler()
        response = self._make_response(content=None, tool_calls=None)
        result = handler._to_result(response, with_tools=False)
        assert result.content.text == ""

    def test_stop_reason_mapping(self):
        """Various finish_reasons should map to correct MCP stop reasons."""
        handler = self._handler()
        assert handler._map_stop_reason("stop") == "endTurn"
        assert handler._map_stop_reason("tool_calls") == "toolUse"
        assert handler._map_stop_reason("length") == "maxTokens"
        assert handler._map_stop_reason(None) == "endTurn"
        assert handler._map_stop_reason("unknown_reason") == "endTurn"


# ===========================================================================
# LiteLLM handler — cost tracking (single, not double)
# ===========================================================================


class TestLiteLLMCostTracking:
    """Verify cost tracking calls track_sample_call exactly once."""

    @pytest.mark.asyncio
    async def test_tracks_once_with_token_counts(self):
        """When provider reports usage tokens, track with tokens only (not text too)."""
        from middleware.litellm_sampling_handler import LiteLLMSamplingHandler

        handler = LiteLLMSamplingHandler(default_model="openai/test")

        # Build mock response with usage
        usage = MagicMock()
        usage.prompt_tokens = 100
        usage.completion_tokens = 50
        usage.prompt_tokens_details = None

        message = MagicMock()
        message.content = "Response text"
        message.tool_calls = None
        choice = MagicMock()
        choice.message = message
        choice.finish_reason = "stop"

        response = MagicMock()
        response.choices = [choice]
        response.model = "openai/test"
        response.usage = usage

        with patch(
            "litellm.acompletion", new_callable=AsyncMock, return_value=response
        ):
            with patch(
                "middleware.payment.cost_tracker.track_sample_call"
            ) as mock_track:
                params = MagicMock()
                params.systemPrompt = None
                params.temperature = None
                params.maxTokens = 100
                params.stopSequences = None
                params.tools = None
                params.toolChoice = None

                messages = [
                    MCPSamplingMessage(
                        role="user",
                        content=MCPTextContent(type="text", text="test"),
                    ),
                ]

                await handler(messages, params, None)

                # Should be called exactly once (with token counts, not text)
                assert mock_track.call_count == 1
                call_kwargs = mock_track.call_args
                assert call_kwargs.kwargs.get("input_tokens", 0) == 100 or (
                    call_kwargs[1].get("input_tokens", 0) == 100
                    if len(call_kwargs) > 1
                    else False
                )

    @pytest.mark.asyncio
    async def test_tracks_once_with_text_fallback(self):
        """When provider reports no usage tokens, fall back to text estimation."""
        from middleware.litellm_sampling_handler import LiteLLMSamplingHandler

        handler = LiteLLMSamplingHandler(default_model="openai/test")

        # Build mock response WITHOUT usage
        usage = MagicMock()
        usage.prompt_tokens = 0
        usage.completion_tokens = 0

        message = MagicMock()
        message.content = "Response text"
        message.tool_calls = None
        choice = MagicMock()
        choice.message = message
        choice.finish_reason = "stop"

        response = MagicMock()
        response.choices = [choice]
        response.model = "openai/test"
        response.usage = usage

        with patch(
            "litellm.acompletion", new_callable=AsyncMock, return_value=response
        ):
            with patch(
                "middleware.payment.cost_tracker.track_sample_call"
            ) as mock_track:
                params = MagicMock()
                params.systemPrompt = None
                params.temperature = None
                params.maxTokens = 100
                params.stopSequences = None
                params.tools = None
                params.toolChoice = None

                messages = [
                    MCPSamplingMessage(
                        role="user",
                        content=MCPTextContent(type="text", text="test input"),
                    ),
                ]

                await handler(messages, params, None)

                # Should be called exactly once (text fallback)
                assert mock_track.call_count == 1
                call_args = mock_track.call_args
                # Should use input_text, not input_tokens
                assert "input_text" in (
                    call_args.kwargs if call_args.kwargs else {}
                ) or (len(call_args[0]) > 0 if call_args[0] else False)


# ===========================================================================
# SessionAwareSamplingHandler — routing
# ===========================================================================


class TestSessionAwareSamplingHandler:
    """Tests for per-user vs default handler routing."""

    @pytest.mark.asyncio
    async def test_routes_to_default_when_no_session_config(self):
        """Without session config, should fall through to default handler."""
        from middleware.session_sampling_handler import SessionAwareSamplingHandler

        default = AsyncMock(return_value="default_result")
        handler = SessionAwareSamplingHandler(default_handler=default)

        with patch.object(handler, "_get_session_sampling_config", return_value=None):
            result = await handler([], MagicMock(), None)

        assert result == "default_result"
        default.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_routes_to_per_user_when_config_present(self):
        """With session config, should route to per-user handler."""
        from middleware.session_sampling_handler import SessionAwareSamplingHandler

        default = AsyncMock(return_value="default_result")
        handler = SessionAwareSamplingHandler(default_handler=default)

        per_user_handler = AsyncMock(return_value="per_user_result")

        config = {"model": "anthropic/claude-sonnet-4-6", "api_key": "sk-test"}

        with patch.object(handler, "_get_session_sampling_config", return_value=config):
            with patch.object(
                handler, "_get_or_create_handler", return_value=per_user_handler
            ):
                result = await handler([], MagicMock(), None)

        assert result == "per_user_result"
        default.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_raises_when_no_default_and_no_session(self):
        """No default handler and no session config should raise RuntimeError."""
        from middleware.session_sampling_handler import SessionAwareSamplingHandler

        handler = SessionAwareSamplingHandler(default_handler=None)

        with patch.object(handler, "_get_session_sampling_config", return_value=None):
            with pytest.raises(RuntimeError, match="No sampling handler configured"):
                await handler([], MagicMock(), None)

    def test_handler_cache_reuses_instances(self):
        """Same config tuple should return cached handler instance."""
        from middleware.session_sampling_handler import SessionAwareSamplingHandler

        handler = SessionAwareSamplingHandler(default_handler=None)

        config = {"model": "openai/gpt-4", "api_key": "key1"}

        with patch(
            "middleware.litellm_sampling_handler.LiteLLMSamplingHandler"
        ) as MockHandler:
            mock_instance = MagicMock()
            MockHandler.return_value = mock_instance

            h1 = handler._get_or_create_handler(config)
            h2 = handler._get_or_create_handler(config)

        assert h1 is h2 is mock_instance
        # Constructor should be called only once
        MockHandler.assert_called_once()

    def test_get_or_create_handler_returns_none_without_model(self):
        """Config without model should return None."""
        from middleware.session_sampling_handler import SessionAwareSamplingHandler

        handler = SessionAwareSamplingHandler(default_handler=None)
        result = handler._get_or_create_handler({"api_key": "key1"})
        assert result is None


# ===========================================================================
# LiteLLM handler — tool conversion
# ===========================================================================


class TestLiteLLMToolConversion:
    """Tests for _convert_tools and _convert_tool_choice."""

    def _handler(self):
        from middleware.litellm_sampling_handler import LiteLLMSamplingHandler

        return LiteLLMSamplingHandler(default_model="test/model")

    def test_convert_tools(self):
        """MCP tool definitions should convert to OpenAI function format."""
        handler = self._handler()
        tool = MagicMock()
        tool.name = "search"
        tool.description = "Search for items"
        tool.inputSchema = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        }
        result = handler._convert_tools([tool])
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "search"
        assert result[0]["function"]["description"] == "Search for items"
        assert result[0]["function"]["parameters"]["type"] == "object"

    def test_convert_tools_adds_type_if_missing(self):
        """If inputSchema lacks 'type', it should be added."""
        handler = self._handler()
        tool = MagicMock()
        tool.name = "test"
        tool.description = ""
        tool.inputSchema = {"properties": {"x": {"type": "string"}}}
        result = handler._convert_tools([tool])
        assert result[0]["function"]["parameters"]["type"] == "object"

    def test_convert_tool_choice(self):
        """ToolChoice mapping should work correctly."""
        handler = self._handler()
        assert handler._convert_tool_choice(None) is None

        auto_choice = MagicMock()
        auto_choice.mode = "auto"
        assert handler._convert_tool_choice(auto_choice) == "auto"

        required_choice = MagicMock()
        required_choice.mode = "required"
        assert handler._convert_tool_choice(required_choice) == "required"


# ===========================================================================
# Attach validation metadata
# ===========================================================================


class TestAttachValidationMetadata:
    """Tests for _attach_validation_metadata."""

    def test_attaches_to_tool_result(self):
        """Should add validation dict to ToolResult.meta."""
        from fastmcp.tools.tool import ToolResult

        mw = EnhancedSamplingMiddleware()
        result = ToolResult(content=[])
        validation = ValidationResult(
            is_valid=True,
            confidence=0.95,
            issues=[],
            suggestions=["Use more widgets"],
            variations=[{"alt": 1}, {"alt": 2}],
        )

        enriched = mw._attach_validation_metadata(result, validation)
        assert enriched.meta["validation"]["is_valid"] is True
        assert enriched.meta["validation"]["confidence"] == 0.95
        assert enriched.meta["validation"]["suggestions"] == ["Use more widgets"]
        assert len(enriched.meta["validation"]["variations"]) == 2

    def test_noop_for_non_tool_result(self):
        """Non-ToolResult objects should pass through unchanged."""
        mw = EnhancedSamplingMiddleware()
        result = "not a ToolResult"
        validation = ValidationResult(is_valid=True)

        returned = mw._attach_validation_metadata(result, validation)
        assert returned == "not a ToolResult"

    def test_preserves_existing_meta(self):
        """Existing meta keys should not be lost."""
        from fastmcp.tools.tool import ToolResult

        mw = EnhancedSamplingMiddleware()
        result = ToolResult(content=[], meta={"existing_key": "value"})
        validation = ValidationResult(is_valid=True)

        enriched = mw._attach_validation_metadata(result, validation)
        assert enriched.meta["existing_key"] == "value"
        assert "validation" in enriched.meta


# ===========================================================================
# ValidationResult model
# ===========================================================================


class TestValidationResultModel:
    """Tests for the ValidationResult Pydantic model."""

    def test_defaults(self):
        """Default values should be sensible."""
        v = ValidationResult(is_valid=True)
        assert v.confidence == 1.0
        assert v.validated_input == {}
        assert v.issues == []
        assert v.suggestions == []
        assert v.variations == []

    def test_confidence_bounds(self):
        """Confidence should be bounded between 0.0 and 1.0."""
        v = ValidationResult(is_valid=True, confidence=0.5)
        assert v.confidence == 0.5

        with pytest.raises(Exception):
            ValidationResult(is_valid=True, confidence=1.5)

        with pytest.raises(Exception):
            ValidationResult(is_valid=True, confidence=-0.1)

    def test_json_roundtrip(self):
        """Should serialize and deserialize correctly."""
        v = ValidationResult(
            is_valid=False,
            confidence=0.7,
            validated_input={"card_description": "§[δ×2]"},
            issues=["Missing content"],
            suggestions=["Add card_params"],
        )
        json_str = v.model_dump_json()
        v2 = ValidationResult.model_validate_json(json_str)
        assert v2.is_valid == v.is_valid
        assert v2.confidence == v.confidence
        assert v2.validated_input == v.validated_input
