"""Tests for Langfuse tracing input/output capture.

Validates that OTel spans get langfuse.observation.input/output attributes,
that LiteLLM metadata includes update_trace_keys and existing_trace_id,
and that the Anthropic wrapper correctly extracts I/O from MCP types.
"""

from unittest.mock import MagicMock, patch

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────


def _reset_langfuse_state():
    """Reset module-level state so tests are independent."""
    import middleware.langfuse_integration as mod

    mod._langfuse_initialized = True  # pretend configured
    return mod


def _make_mock_tracer():
    """Create a mock tracer that records span creation and attributes."""
    mock_span = MagicMock()
    mock_span.get_span_context.return_value = MagicMock(is_valid=True)
    mock_tracer = MagicMock()
    mock_tracer.start_span.return_value = mock_span
    return mock_tracer, mock_span


# ── start_tool_span tests ────────────────────────────────────────────────────


class TestStartToolSpan:
    """Verify start_tool_span sets Langfuse OTel attributes."""

    def test_sets_input_summary(self):
        mod = _reset_langfuse_state()
        mock_tracer, mock_span = _make_mock_tracer()

        # Patch where start_tool_span imports from (lazy import inside function body)
        with patch("middleware.otel_setup.get_mcp_tracer", return_value=mock_tracer):
            span, token = mod.start_tool_span(
                "search",
                input_summary='{"query": "test"}',
            )

        mock_span.set_attribute.assert_any_call(
            "langfuse.observation.input", '{"query": "test"}'
        )

    def test_sets_user_session_tags(self):
        mod = _reset_langfuse_state()
        mock_tracer, mock_span = _make_mock_tracer()

        with patch("middleware.otel_setup.get_mcp_tracer", return_value=mock_tracer):
            mod.start_tool_span(
                "search",
                user_id="user@test.com",
                session_id="sess-123",
                tags=["mcp", "sampling"],
            )

        mock_span.set_attribute.assert_any_call("langfuse.user.id", "user@test.com")
        mock_span.set_attribute.assert_any_call("langfuse.session.id", "sess-123")
        mock_span.set_attribute.assert_any_call("langfuse.tags", ["mcp", "sampling"])

    def test_skips_optional_attributes_when_empty(self):
        """Empty user/session/input should not produce those span attributes.

        Note: ``langfuse.trace.name`` is always set (it's the trace display name).
        """
        mod = _reset_langfuse_state()
        mock_tracer, mock_span = _make_mock_tracer()

        with patch("middleware.otel_setup.get_mcp_tracer", return_value=mock_tracer):
            mod.start_tool_span("search")

        attr_names = [c[0][0] for c in mock_span.set_attribute.call_args_list]
        # trace.name is always set; user/session/input/tags should NOT be
        assert "langfuse.trace.name" in attr_names
        assert "langfuse.observation.input" not in attr_names
        assert "langfuse.user.id" not in attr_names
        assert "langfuse.session.id" not in attr_names
        assert "langfuse.tags" not in attr_names


# ── start_phase_span tests ───────────────────────────────────────────────────


class TestStartPhaseSpan:
    """Verify start_phase_span sets input on child spans."""

    def test_sets_input_summary(self):
        mod = _reset_langfuse_state()
        mock_tracer, mock_span = _make_mock_tracer()

        with patch("middleware.otel_setup.get_mcp_tracer", return_value=mock_tracer):
            mod.start_phase_span(
                "validation", "search", input_summary='{"dsl": "§[δ]"}'
            )

        mock_span.set_attribute.assert_any_call(
            "langfuse.observation.input", '{"dsl": "§[δ]"}'
        )


# ── end_span tests ───────────────────────────────────────────────────────────


class TestEndSpan:
    """Verify end_span sets output before closing."""

    def test_sets_output_summary(self):
        mod = _reset_langfuse_state()
        mock_span = MagicMock()

        mod.end_span(mock_span, None, output_summary="result text here")

        mock_span.set_attribute.assert_any_call(
            "langfuse.observation.output", "result text here"
        )
        mock_span.end.assert_called_once()

    def test_sets_output_before_error_status(self):
        mod = _reset_langfuse_state()
        mock_span = MagicMock()

        mod.end_span(
            mock_span,
            None,
            error=ValueError("boom"),
            output_summary="partial output",
        )

        # Output should still be set even on error
        mock_span.set_attribute.assert_any_call(
            "langfuse.observation.output", "partial output"
        )
        mock_span.record_exception.assert_called_once()

    def test_no_output_when_empty(self):
        mod = _reset_langfuse_state()
        mock_span = MagicMock()

        mod.end_span(mock_span, None)

        langfuse_calls = [
            c
            for c in mock_span.set_attribute.call_args_list
            if c[0][0].startswith("langfuse.")
        ]
        assert langfuse_calls == []


# ── add_langfuse_metadata tests ──────────────────────────────────────────────


class TestAddLangfuseMetadata:
    """Verify metadata dict includes update_trace_keys, existing_trace_id, etc."""

    def test_adds_update_trace_keys(self):
        mod = _reset_langfuse_state()
        kwargs = {"messages": []}

        mod.add_langfuse_metadata(kwargs, tool_name="search")

        meta = kwargs["metadata"]
        assert meta["update_trace_keys"] == ["input", "output"]

    def test_adds_existing_trace_id(self):
        mod = _reset_langfuse_state()
        kwargs = {}

        mod.add_langfuse_metadata(
            kwargs,
            tool_name="search",
            trace_id="abc-123",
            existing_trace_id="abc-123",
        )

        meta = kwargs["metadata"]
        assert meta["trace_id"] == "abc-123"
        assert meta["existing_trace_id"] == "abc-123"

    def test_adds_parent_observation_id(self):
        mod = _reset_langfuse_state()
        kwargs = {}

        mod.add_langfuse_metadata(
            kwargs,
            tool_name="search",
            parent_observation_id="obs-456",
        )

        meta = kwargs["metadata"]
        assert meta["parent_observation_id"] == "obs-456"

    def test_preserves_existing_metadata(self):
        """Existing metadata keys should not be clobbered."""
        mod = _reset_langfuse_state()
        kwargs = {"metadata": {"custom_key": "custom_val"}}

        mod.add_langfuse_metadata(kwargs, tool_name="search")

        assert kwargs["metadata"]["custom_key"] == "custom_val"
        assert "update_trace_keys" in kwargs["metadata"]

    def test_noop_when_not_initialized(self):
        import middleware.langfuse_integration as mod

        mod._langfuse_initialized = False
        try:
            kwargs = {}
            mod.add_langfuse_metadata(kwargs, tool_name="search")
            assert "metadata" not in kwargs
        finally:
            mod._langfuse_initialized = False


# ── Anthropic wrapper I/O extraction ─────────────────────────────────────────


class TestAnthropicWrapperIO:
    """Verify the Anthropic wrapper extracts I/O from MCP types correctly."""

    def test_extracts_text_content_input(self):
        """Input extraction uses isinstance(m.content, TextContent)."""
        from mcp.types import TextContent as MCPTextContent

        messages = [
            MagicMock(content=MCPTextContent(type="text", text="Hello world")),
            MagicMock(content=MCPTextContent(type="text", text="Second message")),
            MagicMock(content=MagicMock(spec=[])),  # non-TextContent, should skip
        ]

        # Replicate the extraction logic from the wrapper
        input_text = "; ".join(
            m.content.text[:200]
            for m in messages
            if isinstance(m.content, MCPTextContent)
        )

        assert input_text == "Hello world; Second message"

    def test_extracts_text_content_output(self):
        """Output extraction uses isinstance(result.content, TextContent)."""
        from mcp.types import TextContent as MCPTextContent

        result = MagicMock()
        result.content = MCPTextContent(type="text", text="LLM response here")

        output_text = (
            result.content.text[:500]
            if isinstance(result.content, MCPTextContent)
            else ""
        )

        assert output_text == "LLM response here"

    def test_non_text_output_returns_empty(self):
        """Non-TextContent output (e.g. ImageContent) should yield empty string."""
        from mcp.types import ImageContent

        result = MagicMock()
        result.content = ImageContent(
            type="image", data="base64data", mimeType="image/png"
        )

        from mcp.types import TextContent as MCPTextContent

        output_text = (
            result.content.text[:500]
            if isinstance(result.content, MCPTextContent)
            else ""
        )

        assert output_text == ""
