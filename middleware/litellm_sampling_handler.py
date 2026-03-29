"""LiteLLM-based sampling handler for FastMCP — routes to 100+ LLM providers.

Uses LiteLLM's acompletion() to provide an OpenAI-compatible interface that
routes to any supported provider (Venice AI, OpenAI, Anthropic, Groq, Together, etc.)
using a provider/model naming convention (e.g., 'openai/zai-org-glm-4.6').
"""

import json
from config.enhanced_logging import setup_logger
import os
import sys
from typing import Any

# Fix SSL certificate verification on macOS Python (missing root certs)
if sys.platform == "darwin":
    try:
        import certifi
        import litellm as _litellm_ssl_fix

        os.environ["SSL_CERT_FILE"] = certifi.where()
        os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
        _litellm_ssl_fix.ssl_verify = certifi.where()
    except ImportError:
        pass

from mcp.types import CreateMessageRequestParams as SamplingParams
from mcp.types import (
    CreateMessageResult,
    CreateMessageResultWithTools,
    SamplingMessage,
    TextContent,
    ToolResultContent,
    ToolUseContent,
)

logger = setup_logger()

# Anthropic model names that may appear behind any LiteLLM provider prefix.
# Venice AI, for example, exposes Claude models via its OpenAI-compatible
# endpoint (openai/claude-sonnet-4-6).  We need to recognise these so that
# Anthropic-specific features (prompt caching, cached-token tracking) are
# enabled regardless of the routing provider.
_ANTHROPIC_MODEL_STEMS = ("claude-",)

def is_anthropic_model(model: str) -> bool:
    """Return True if *model* is an Anthropic Claude model.

    Handles both direct Anthropic routing (``anthropic/claude-…``) and
    proxy routing through OpenAI-compatible providers like Venice AI
    (``openai/claude-…``).
    """
    # Strip the provider prefix (e.g. "anthropic/", "openai/")
    bare = model.split("/", 1)[-1] if "/" in model else model
    return any(bare.startswith(stem) for stem in _ANTHROPIC_MODEL_STEMS)

class LiteLLMSamplingHandler:
    """FastMCP sampling handler that routes through LiteLLM.

    Implements the SamplingHandler callable protocol, converting MCP sampling
    types to/from LiteLLM's acompletion() call.

    Args:
        default_model: LiteLLM model identifier in provider/model format.
        api_key: API key for the target provider.
        api_base: Custom API base URL for OpenAI-compatible providers.
    """

    def __init__(
        self,
        default_model: str = "openai/zai-org-glm-4.6",
        api_key: str | None = None,
        api_base: str | None = None,
    ):
        self.default_model = default_model
        self.api_key = api_key
        self.api_base = api_base
        self._langfuse_attempted = False
        self._cache_attempted = False

    async def __call__(
        self,
        messages: list[SamplingMessage],
        params: SamplingParams,
        context: Any,
    ) -> CreateMessageResult | CreateMessageResultWithTools:
        import litellm

        # Enable Langfuse callback on first call (lazy init)
        if not self._langfuse_attempted:
            self._langfuse_attempted = True
            try:
                from middleware.langfuse_integration import enable_litellm_langfuse

                enable_litellm_langfuse()
            except Exception:
                pass

        # Lazy semantic cache init (same pattern as Langfuse)
        if not self._cache_attempted:
            self._cache_attempted = True
            try:
                from middleware.sampling_cache import initialize_sampling_cache

                initialize_sampling_cache()
            except Exception:
                pass

        # Convert MCP messages to LiteLLM (OpenAI) format
        litellm_messages = self._convert_messages(messages, params.systemPrompt)

        # Build kwargs
        kwargs: dict[str, Any] = {
            "model": self.default_model,
            "messages": litellm_messages,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if params.temperature is not None:
            kwargs["temperature"] = params.temperature
        if params.maxTokens:
            kwargs["max_tokens"] = params.maxTokens
        if params.stopSequences:
            kwargs["stop"] = params.stopSequences

        # Tools
        has_tools = bool(params.tools)
        if has_tools:
            kwargs["tools"] = self._convert_tools(params.tools)
            # Disable semantic cache for tool-use calls — cached tool_call
            # responses replay with stale IDs and cause infinite iteration
            # loops in the sampling middleware.
            kwargs["cache"] = {"no-cache": True, "no-store": True}
        if params.toolChoice:
            tc = self._convert_tool_choice(params.toolChoice)
            if tc is not None:
                kwargs["tool_choice"] = tc

        # Provider-side prompt caching: for Anthropic models (direct or proxied)
        if is_anthropic_model(self.default_model):
            kwargs["cache_control_injection_points"] = [
                {"location": "message", "role": "system"},
            ]

        # Add Langfuse trace metadata (session, user, tool context)
        try:
            from auth.context import (
                get_session_context_sync,
                get_user_email_context_sync,
            )
            from middleware.langfuse_integration import (
                add_langfuse_metadata,
                get_sampling_trace_context,
            )

            trace_ctx = get_sampling_trace_context()
            tool_name = trace_ctx.tool_name if trace_ctx else ""
            step_index = trace_ctx.step_index if trace_ctx else 0

            # Build generation name — include step/phase for multi-step tools
            phase = trace_ctx.phase if trace_ctx else ""
            if phase and tool_name:
                gen_name = f"mcp::{tool_name}::{phase}"
            elif step_index > 0 and tool_name:
                gen_name = f"mcp::{tool_name}::step_{step_index}"
            elif trace_ctx and trace_ctx.template and "recovery" in trace_ctx.template:
                gen_name = f"mcp::{tool_name}::dsl_recovery::attempt_{step_index}"
            else:
                gen_name = f"mcp::{tool_name}" if tool_name else "mcp::sampling"

            trace_meta: dict = {"mcp_tool": tool_name or "unknown"}
            if trace_ctx:
                if trace_ctx.template:
                    trace_meta["template"] = trace_ctx.template
                if trace_ctx.result_type:
                    trace_meta["result_type"] = trace_ctx.result_type
                if trace_ctx.enhancement_level:
                    trace_meta["enhancement_level"] = trace_ctx.enhancement_level
                if trace_ctx.has_tools:
                    trace_meta["has_tools"] = "true"
                if trace_ctx.input_char_count:
                    trace_meta["input_char_count"] = str(trace_ctx.input_char_count)
                if step_index > 0:
                    trace_meta["step_index"] = str(step_index)
                if trace_ctx.phase:
                    trace_meta["phase"] = trace_ctx.phase
                if trace_ctx.search_mode:
                    trace_meta["search_mode"] = trace_ctx.search_mode

            add_langfuse_metadata(
                kwargs,
                tool_name=tool_name,
                session_id=get_session_context_sync() or "",
                user_email=get_user_email_context_sync() or "",
                generation_name=gen_name,
                trace_name=f"mcp::{tool_name}" if tool_name else "mcp::sampling",
                trace_id=trace_ctx.trace_id if trace_ctx else "",
                trace_metadata=trace_meta,
            )

            # Forward-looking: propagate current OTEL span as parent for LiteLLM
            # Currently ignored by LiteLLM's langfuse_otel callback, but positions
            # us for when that limitation is lifted.
            try:
                from opentelemetry import trace as otel_trace

                current_span = otel_trace.get_current_span()
                if current_span.get_span_context().is_valid:
                    kwargs.setdefault("metadata", {})["litellm_parent_otel_span"] = (
                        current_span
                    )
            except Exception:
                pass
        except Exception:
            pass

        logger.debug(
            "LiteLLM sampling: model=%s, messages=%d, tools=%d",
            self.default_model,
            len(litellm_messages),
            len(params.tools) if params.tools else 0,
        )

        response = await litellm.acompletion(**kwargs)

        # Track sampling cost using actual token usage from provider
        try:
            from middleware.payment.cost_tracker import track_sample_call

            usage = getattr(response, "usage", None)
            model_name = (
                getattr(response, "model", self.default_model) or self.default_model
            )
            if usage and (
                getattr(usage, "prompt_tokens", 0)
                or getattr(usage, "completion_tokens", 0)
            ):
                # Use actual token counts from provider
                cached_tokens = 0
                if is_anthropic_model(self.default_model):
                    prompt_details = getattr(usage, "prompt_tokens_details", None)
                    cached_tokens = (
                        getattr(prompt_details, "cached_tokens", 0) or 0
                        if prompt_details
                        else 0
                    )
                track_sample_call(
                    input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                    model=model_name,
                    cached_tokens=cached_tokens,
                )
            else:
                # Fallback: estimate from message text lengths when provider
                # doesn't report token usage
                input_text = " ".join(
                    m.get("content", "")
                    for m in litellm_messages
                    if isinstance(m.get("content"), str)
                )
                output_text = ""
                if response.choices:
                    output_text = (
                        getattr(response.choices[0].message, "content", "") or ""
                    )
                track_sample_call(
                    input_text=input_text,
                    output_text=output_text,
                    model=model_name,
                )
        except Exception as e:
            logger.debug("Cost tracking failed (non-fatal): %s", e)

        # Log cached tokens for Anthropic models (direct or Venice-proxied).
        if is_anthropic_model(self.default_model):
            try:
                usage = getattr(response, "usage", None)
                if usage:
                    prompt_details = getattr(usage, "prompt_tokens_details", None)
                    ct = (
                        getattr(prompt_details, "cached_tokens", 0) or 0
                        if prompt_details
                        else 0
                    )
                    if ct > 0:
                        logger.info(
                            "Anthropic cache hit: %d cached tokens (model=%s)",
                            ct,
                            self.default_model,
                        )
            except Exception:
                pass

        # Convert response back to MCP types
        return self._to_result(response, with_tools=has_tools)

    # ── Message conversion ──────────────────────────────────────────────

    def _convert_messages(
        self,
        messages: list[SamplingMessage],
        system_prompt: str | None,
    ) -> list[dict[str, Any]]:
        """Convert MCP SamplingMessages to OpenAI-format message dicts."""
        result: list[dict[str, Any]] = []

        if system_prompt:
            result.append({"role": "system", "content": system_prompt})

        for msg in messages:
            role = msg.role  # "user" or "assistant"
            content = msg.content

            if isinstance(content, TextContent):
                # Check if there's already a same-role message we can merge into
                if (
                    result
                    and result[-1]["role"] == role
                    and isinstance(result[-1].get("content"), str)
                ):
                    result[-1]["content"] += "\n" + content.text
                else:
                    result.append({"role": role, "content": content.text})

            elif isinstance(content, ToolUseContent):
                # Assistant requesting a tool call
                tool_call = {
                    "id": content.id,
                    "type": "function",
                    "function": {
                        "name": content.name,
                        "arguments": json.dumps(content.input)
                        if isinstance(content.input, dict)
                        else str(content.input),
                    },
                }
                # Merge into existing assistant message or create new one
                if result and result[-1]["role"] == "assistant":
                    last = result[-1]
                    if "tool_calls" not in last:
                        last["tool_calls"] = []
                    last["tool_calls"].append(tool_call)
                    # OpenAI requires content to be null/absent when tool_calls present
                    if last.get("content") == "":
                        last.pop("content", None)
                else:
                    result.append(
                        {
                            "role": "assistant",
                            "tool_calls": [tool_call],
                        }
                    )

            elif isinstance(content, ToolResultContent):
                # Tool result — goes as a "tool" role message
                tool_content = content.content
                if isinstance(tool_content, list):
                    # Extract text from content blocks
                    parts = []
                    for block in tool_content:
                        if isinstance(block, TextContent):
                            parts.append(block.text)
                        elif hasattr(block, "text"):
                            parts.append(block.text)
                        else:
                            parts.append(str(block))
                    tool_content = "\n".join(parts)
                elif not isinstance(tool_content, str):
                    tool_content = json.dumps(tool_content) if tool_content else ""

                result.append(
                    {
                        "role": "tool",
                        "tool_call_id": content.toolCallId,
                        "content": tool_content,
                    }
                )
            else:
                # Fallback: treat as text
                result.append({"role": role, "content": str(content)})

        return result

    # ── Tool conversion ─────────────────────────────────────────────────

    def _convert_tools(self, tools: list) -> list[dict[str, Any]]:
        """Convert MCP Tool definitions to OpenAI-format tool dicts."""
        result = []
        for tool in tools:
            schema = tool.inputSchema if hasattr(tool, "inputSchema") else {}
            if isinstance(schema, dict) and "type" not in schema:
                schema = {**schema, "type": "object"}

            result.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": schema,
                    },
                }
            )
        return result

    def _convert_tool_choice(self, tool_choice: Any) -> str | None:
        """Convert MCP ToolChoice to OpenAI tool_choice string."""
        if tool_choice is None:
            return None
        mode = getattr(tool_choice, "mode", None) or str(tool_choice)
        mapping = {
            "auto": "auto",
            "required": "required",
            "none": "none",
        }
        return mapping.get(mode, "auto")

    # ── Response conversion ─────────────────────────────────────────────

    def _to_result(
        self, response: Any, *, with_tools: bool
    ) -> CreateMessageResult | CreateMessageResultWithTools:
        """Convert LiteLLM ModelResponse to MCP result type."""
        choice = response.choices[0]
        message = choice.message
        stop_reason = self._map_stop_reason(choice.finish_reason)

        content_blocks: list[TextContent | ToolUseContent] = []

        # Extract text content
        if message.content:
            content_blocks.append(TextContent(type="text", text=message.content))

        # Extract tool calls
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    arguments = {}

                content_blocks.append(
                    ToolUseContent(
                        type="tool_use",
                        id=tc.id,
                        name=tc.function.name,
                        input=arguments,
                    )
                )

        # Ensure at least one content block
        if not content_blocks:
            content_blocks.append(TextContent(type="text", text=""))

        model = getattr(response, "model", self.default_model) or self.default_model

        if with_tools:
            return CreateMessageResultWithTools(
                role="assistant",
                content=content_blocks,
                model=model,
                stopReason=stop_reason,
            )

        return CreateMessageResult(
            role="assistant",
            content=content_blocks[0],  # Single content block for non-tool results
            model=model,
            stopReason=stop_reason,
        )

    def _map_stop_reason(self, finish_reason: str | None) -> str:
        """Map OpenAI finish_reason to MCP stop reason."""
        mapping = {
            "stop": "endTurn",
            "tool_calls": "toolUse",
            "length": "maxTokens",
            "content_filter": "endTurn",
            "function_call": "toolUse",
        }
        return mapping.get(finish_reason or "stop", "endTurn")
