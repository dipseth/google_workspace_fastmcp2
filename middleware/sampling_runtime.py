"""Server-side LLM sampling runtime.

FastMCP 4 removed server-initiated sampling (``ctx.sample`` / ``ctx.sample_step``,
SEP-2577): the sessionless MCP protocol has no channel for a server to push a
request to its client. This server's dynamic tools (card draft variations, DSL
recovery, email pre-validation, structured validation agents) are built on that
API, so the machinery lives here instead and always dispatches to a
server-configured handler (LiteLLM / Anthropic, per-user routed).

Public API mirrors the FastMCP 3 context methods so call sites change one line::

    from middleware.sampling_runtime import sample, sample_step

    result = await sample(ctx, "Summarise this", result_type=Summary, tools=[search])
    result.text      # raw text, or JSON for structured output
    result.result    # parsed ``Summary``

The handler is registered once at startup with :func:`set_sampling_handler`
and receives ``(messages, params, request_context)`` exactly as FastMCP 3's
fallback handler did.

Derived from ``fastmcp/server/sampling/run.py`` and ``sampling_tool.py`` in
FastMCP 3.4.7 (Copyright Prefect Technologies, Inc., Apache License 2.0), with
the client wire path removed and protocol fields moved to the MCP SDK v2
snake_case names.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Literal, Optional, cast

import anyio
from fastmcp import settings
from fastmcp.exceptions import AuthorizationError, ToolError
from fastmcp.server.dependencies import get_access_token
from fastmcp.telemetry import get_tracer
from fastmcp.tools.base import ToolResult
from fastmcp.tools.function_parsing import ParsedFunction
from fastmcp.tools.function_tool import FunctionTool
from fastmcp.tools.tool_transform import TransformedTool
from fastmcp.utilities.async_utils import gather
from fastmcp.utilities.json_schema import compress_schema
from fastmcp.utilities.types import FastMCPBaseModel, get_cached_typeadapter
from mcp.types import CreateMessageRequestParams as SamplingParams
from mcp.types import (
    CreateMessageResult,
    CreateMessageResultWithTools,
    ModelHint,
    ModelPreferences,
    SamplingMessage,
    SamplingMessageContentBlock,
    TextContent,
    ToolChoice,
    ToolResultContent,
    ToolUseContent,
)
from mcp.types import Tool as SDKTool
from opentelemetry.trace import SpanKind, Status, StatusCode
from pydantic import ConfigDict, ValidationError
from typing_extensions import TypeVar

from config.enhanced_logging import setup_logger

if TYPE_CHECKING:
    from fastmcp.server.context import Context

logger = setup_logger()

ResultT = TypeVar("ResultT")

#: Consecutive ``final_response`` validation retries before aborting.
_MAX_VALIDATION_RETRIES = 3
#: Retries when the LLM answers with text instead of calling ``final_response``.
_MAX_TEXT_RESPONSE_RETRIES = 3
#: Hard cap on sampling-loop iterations.
_MAX_ITERATIONS = 100

ToolChoiceOption = Literal["auto", "required", "none"]

#: ``(messages, params, request_context) -> CreateMessageResult | ...WithTools | str``
SamplingHandler = Callable[..., Any]


# ─── Handler registry ────────────────────────────────────────────────────────

_sampling_handler: Optional[SamplingHandler] = None


def set_sampling_handler(handler: Optional[SamplingHandler]) -> None:
    """Register the server-side sampling handler (called once at startup)."""
    global _sampling_handler
    _sampling_handler = handler


def get_sampling_handler() -> Optional[SamplingHandler]:
    return _sampling_handler


def sampling_available() -> bool:
    """True when a sampling handler is registered.

    Whether a given call can actually be served is the handler's decision:
    ``SessionAwareSamplingHandler`` may route through the server default, the
    caller's own provider config, or a header override, and raises when none
    applies. Peeking at its default here would refuse bring-your-own-key
    deployments that have no server key at all.
    """
    return _sampling_handler is not None


# ─── Types ───────────────────────────────────────────────────────────────────


class SamplingTool(FastMCPBaseModel):
    """A tool the LLM may call during sampling (schema + executor)."""

    name: str
    description: str | None = None
    parameters: dict[str, Any]
    fn: Callable[..., Any]
    sequential: bool = False

    model_config = ConfigDict(arbitrary_types_allowed=True)

    async def run(self, arguments: dict[str, Any] | None = None) -> Any:
        result = self.fn(**(arguments or {}))
        if inspect.isawaitable(result):
            result = await result
        return result

    def _to_sdk_tool(self) -> SDKTool:
        return SDKTool(
            name=self.name,
            description=self.description,
            input_schema=self.parameters,
        )

    @classmethod
    def from_function(
        cls,
        fn: Callable[..., Any],
        *,
        name: str | None = None,
        description: str | None = None,
        sequential: bool = False,
    ) -> SamplingTool:
        parsed = ParsedFunction.from_function(fn, validate=True)
        if name is None and parsed.name == "<lambda>":
            raise ValueError("You must provide a name for lambda functions")
        return cls(
            name=name or parsed.name,
            description=description if description is not None else parsed.description,
            parameters=parsed.input_schema,
            fn=parsed.fn,
            sequential=sequential,
        )

    @classmethod
    def from_callable_tool(
        cls,
        tool: FunctionTool | TransformedTool,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> SamplingTool:
        """Wrap a server tool so the LLM can call it during sampling.

        Per-tool ``auth=`` checks are enforced exactly as the server dispatcher
        would, so an auth-protected tool cannot be invoked via sampling without
        authorization.
        """
        if not isinstance(tool, (FunctionTool, TransformedTool)):
            raise TypeError(
                f"Expected FunctionTool or TransformedTool, got {type(tool).__name__}."
            )

        async def wrapper(**kwargs: Any) -> Any:
            if getattr(tool, "auth", None) is not None:
                from fastmcp.server.auth import AuthContext, run_auth_checks
                from fastmcp.server.context import _current_transport

                if _current_transport.get() != "stdio":
                    token = get_access_token()
                    auth_ctx = AuthContext(token=token, component=tool)
                    if not await run_auth_checks(tool.auth, auth_ctx):
                        raise AuthorizationError(
                            f"Authorization failed for tool '{tool.name}': "
                            "insufficient permissions"
                        )

            result = await tool.run(kwargs)
            if isinstance(result, ToolResult):
                if result.structured_content is not None:
                    if tool.output_schema and tool.output_schema.get(
                        "x-fastmcp-wrap-result"
                    ):
                        return result.structured_content.get("result")
                    return result.structured_content
                if result.content:
                    first = result.content[0]
                    if isinstance(first, TextContent):
                        return first.text
            return result

        return cls(
            name=name or tool.name,
            description=description or tool.description,
            parameters=tool.parameters,
            fn=wrapper,
        )


@dataclass
class SamplingResult(Generic[ResultT]):
    """Result of :func:`sample`.

    ``text`` is the raw text (or JSON for structured output); ``result`` is the
    typed value (``str`` for text, the parsed ``result_type`` otherwise);
    ``history`` is every message exchanged.
    """

    text: str | None
    result: ResultT
    history: list[SamplingMessage]


@dataclass
class SampleStep:
    """Result of one :func:`sample_step` call."""

    response: CreateMessageResult | CreateMessageResultWithTools
    history: list[SamplingMessage]

    @property
    def is_tool_use(self) -> bool:
        if isinstance(self.response, CreateMessageResultWithTools):
            return self.response.stop_reason == "toolUse"
        return False

    @property
    def text(self) -> str | None:
        content = self.response.content
        if isinstance(content, list):
            for block in content:
                if isinstance(block, TextContent):
                    return block.text
            return None
        if isinstance(content, TextContent):
            return content.text
        return None

    @property
    def tool_calls(self) -> list[ToolUseContent]:
        content = self.response.content
        if isinstance(content, list):
            return [c for c in content if isinstance(c, ToolUseContent)]
        if isinstance(content, ToolUseContent):
            return [content]
        return []


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _parse_model_preferences(
    model_preferences: ModelPreferences | str | list[str] | None,
) -> ModelPreferences | None:
    if model_preferences is None:
        return None
    if isinstance(model_preferences, ModelPreferences):
        return model_preferences
    if isinstance(model_preferences, str):
        return ModelPreferences(hints=[ModelHint(name=model_preferences)])
    if isinstance(model_preferences, list):
        if not all(isinstance(h, str) for h in model_preferences):
            raise ValueError("All elements of model_preferences list must be strings.")
        return ModelPreferences(hints=[ModelHint(name=h) for h in model_preferences])
    raise ValueError(
        "model_preferences must be one of: ModelPreferences, str, list[str], or None."
    )


def prepare_messages(
    messages: str | Sequence[str | SamplingMessage],
) -> list[SamplingMessage]:
    if isinstance(messages, str):
        return [
            SamplingMessage(
                content=TextContent(text=messages, type="text"), role="user"
            )
        ]
    return [
        SamplingMessage(content=TextContent(text=m, type="text"), role="user")
        if isinstance(m, str)
        else m
        for m in messages
    ]


def prepare_tools(
    tools: Sequence[SamplingTool | FunctionTool | TransformedTool | Callable[..., Any]]
    | None,
) -> list[SamplingTool] | None:
    if tools is None:
        return None
    out: list[SamplingTool] = []
    for t in tools:
        if isinstance(t, SamplingTool):
            out.append(t)
        elif isinstance(t, (FunctionTool, TransformedTool)):
            out.append(SamplingTool.from_callable_tool(t))
        elif callable(t):
            out.append(SamplingTool.from_function(t))
        else:
            raise TypeError(
                f"Expected SamplingTool, FunctionTool, TransformedTool, or callable, got {type(t)}"
            )
    return out or None


def extract_tool_calls(
    response: CreateMessageResult | CreateMessageResultWithTools,
) -> list[ToolUseContent]:
    content = response.content
    if isinstance(content, list):
        return [c for c in content if isinstance(c, ToolUseContent)]
    if isinstance(content, ToolUseContent):
        return [content]
    return []


def create_final_response_tool(result_type: type) -> SamplingTool:
    """Synthetic ``final_response`` tool whose schema is ``result_type``."""
    type_adapter = get_cached_typeadapter(result_type)
    schema = compress_schema(type_adapter.json_schema(), prune_titles=True)
    if schema.get("type") != "object":
        schema = {
            "type": "object",
            "properties": {"value": schema},
            "required": ["value"],
        }

    def final_response(**kwargs: Any) -> dict[str, Any]:
        return kwargs

    return SamplingTool(
        name="final_response",
        description=(
            "Call this tool to provide your final response. "
            "Use this when you have completed the task and are ready to return the result."
        ),
        parameters=schema,
        fn=final_response,
    )


def _tool_result(
    tool_use_id: str, text: str, *, is_error: bool = False
) -> ToolResultContent:
    return ToolResultContent(
        type="tool_result",
        tool_use_id=tool_use_id,
        content=[TextContent(type="text", text=text)],
        is_error=is_error,
    )


async def _execute_tool_calls(
    tool_calls: list[ToolUseContent],
    tool_map: dict[str, SamplingTool],
    mask_error_details: bool = False,
    tool_concurrency: int | None = None,
) -> list[ToolResultContent]:
    """Run the LLM's tool calls and return results in the same order."""
    if tool_concurrency is not None and tool_concurrency < 0:
        raise ValueError(
            "tool_concurrency must be None, 0 (unlimited), or a positive integer, "
            f"got {tool_concurrency}"
        )

    async def _one(tool_use: ToolUseContent) -> ToolResultContent:
        tool = tool_map.get(tool_use.name)
        if tool is None:
            return _tool_result(
                tool_use.id, f"Error: Unknown tool '{tool_use.name}'", is_error=True
            )
        tracer = get_tracer()
        with tracer.start_as_current_span(
            f"sampling tool {tool_use.name}", kind=SpanKind.INTERNAL
        ) as span:
            if span.is_recording():
                span.set_attribute("gen_ai.tool.name", tool_use.name)
                span.set_attribute("fastmcp.tool.use_id", tool_use.id)
            try:
                value = await tool.run(tool_use.input)
                return _tool_result(tool_use.id, str(value))
            except ToolError as e:
                if span.is_recording():
                    span.set_attribute("error.type", "tool_error")
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                logger.warning(f"Error calling sampling tool '{tool_use.name}': {e}")
                return _tool_result(tool_use.id, str(e), is_error=True)
            except Exception as e:
                if span.is_recording():
                    span.set_attribute("error.type", type(e).__qualname__)
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                logger.exception(f"Error calling sampling tool '{tool_use.name}'")
                text = (
                    f"Error executing tool '{tool_use.name}'"
                    if mask_error_details
                    else f"Error executing tool '{tool_use.name}': {e}"
                )
                return _tool_result(tool_use.id, text, is_error=True)

    requires_sequential = any(
        tool.sequential
        for tool_use in tool_calls
        if (tool := tool_map.get(tool_use.name)) is not None
    )
    if tool_concurrency is None or requires_sequential:
        return [await _one(tc) for tc in tool_calls]
    if tool_concurrency == 0:
        return await gather(*[_one(tc) for tc in tool_calls])

    semaphore = anyio.Semaphore(tool_concurrency)

    async def bounded(tool_use: ToolUseContent) -> ToolResultContent:
        async with semaphore:
            return await _one(tool_use)

    return await gather(*[bounded(tc) for tc in tool_calls])


async def call_sampling_handler(
    context: Context,
    messages: list[SamplingMessage],
    *,
    system_prompt: str | None,
    temperature: float | None,
    max_tokens: int,
    model_preferences: ModelPreferences | str | list[str] | None,
    sdk_tools: list[SDKTool] | None,
    tool_choice: ToolChoice | None,
) -> CreateMessageResult | CreateMessageResultWithTools:
    """One LLM call through the registered server-side handler."""
    handler = _sampling_handler
    if handler is None:
        raise ToolError(
            "LLM sampling is not configured on this server "
            "(set VENICE_INFERENCE_KEY, LITELLM_API_KEY, or ANTHROPIC_API_KEY)"
        )

    params = SamplingParams(
        messages=messages,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        model_preferences=_parse_model_preferences(model_preferences),
        tools=sdk_tools,
        tool_choice=tool_choice,
    )
    result = handler(messages, params, getattr(context, "request_context", None))
    if inspect.isawaitable(result):
        result = await result

    if isinstance(result, str):
        return CreateMessageResult(
            role="assistant",
            content=TextContent(type="text", text=result),
            model="unknown",
            stop_reason="endTurn",
        )
    return cast("CreateMessageResult | CreateMessageResultWithTools", result)


# ─── Public API ──────────────────────────────────────────────────────────────


async def sample_step(
    context: Context,
    messages: str | Sequence[str | SamplingMessage],
    *,
    system_prompt: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    model_preferences: ModelPreferences | str | list[str] | None = None,
    tools: Sequence[SamplingTool | FunctionTool | TransformedTool | Callable[..., Any]]
    | None = None,
    tool_choice: ToolChoiceOption | str | None = None,
    execute_tools: bool = True,
    mask_error_details: bool | None = None,
    tool_concurrency: int | None = None,
) -> SampleStep:
    """Exactly one LLM call, optionally executing the tools it requested.

    Mirrors FastMCP 3's ``ctx.sample_step``; ``context`` is the tool's
    ``Context`` and is used for the server name and request context only.
    """
    current_messages = prepare_messages(messages)
    sampling_tools = prepare_tools(tools)
    sdk_tools = [t._to_sdk_tool() for t in sampling_tools] if sampling_tools else None
    tool_map = {t.name: t for t in sampling_tools} if sampling_tools else {}

    effective_tool_choice: ToolChoice | None = None
    if tool_choice is not None:
        if tool_choice not in ("auto", "required", "none"):
            raise ValueError(
                f"Invalid tool_choice: {tool_choice!r}. Must be 'auto', 'required', or 'none'."
            )
        effective_tool_choice = ToolChoice(mode=cast(ToolChoiceOption, tool_choice))

    tracer = get_tracer()
    with tracer.start_as_current_span(
        "sampling create_message",
        kind=SpanKind.CLIENT,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        if span.is_recording():
            span.set_attribute("mcp.method.name", "sampling/createMessage")
            server_name = getattr(getattr(context, "fastmcp", None), "name", "")
            span.set_attribute("fastmcp.server.name", server_name or "")
        try:
            response = await call_sampling_handler(
                context,
                current_messages,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens if max_tokens is not None else 512,
                model_preferences=model_preferences,
                sdk_tools=sdk_tools,
                tool_choice=effective_tool_choice,
            )
        except Exception as e:
            if span.is_recording():
                span.set_attribute("error.type", type(e).__qualname__)
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
            raise

    is_tool_use = (
        isinstance(response, CreateMessageResultWithTools)
        and response.stop_reason == "toolUse"
    )
    current_messages.append(SamplingMessage(role="assistant", content=response.content))

    if not is_tool_use or not execute_tools:
        return SampleStep(response=response, history=current_messages)

    step_tool_calls = extract_tool_calls(response)
    if step_tool_calls:
        effective_mask = (
            mask_error_details
            if mask_error_details is not None
            else bool(settings.mask_error_details)
        )
        tool_results = await _execute_tool_calls(
            step_tool_calls,
            tool_map,
            mask_error_details=effective_mask,
            tool_concurrency=tool_concurrency,
        )
        if tool_results:
            current_messages.append(
                SamplingMessage(
                    role="user",
                    content=cast(list[SamplingMessageContentBlock], tool_results),
                )
            )
    return SampleStep(response=response, history=current_messages)


async def sample(
    context: Context,
    messages: str | Sequence[str | SamplingMessage],
    *,
    system_prompt: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    model_preferences: ModelPreferences | str | list[str] | None = None,
    tools: Sequence[SamplingTool | FunctionTool | TransformedTool | Callable[..., Any]]
    | None = None,
    result_type: type[ResultT] | None = None,
    mask_error_details: bool | None = None,
    tool_concurrency: int | None = None,
) -> SamplingResult[Any]:
    """Run sampling to completion (tool loop + optional structured output).

    Mirrors FastMCP 3's ``ctx.sample``. With ``tools``, tool calls are executed
    and fed back until the LLM answers. With ``result_type``, a synthetic
    ``final_response`` tool captures the structured answer, which is validated
    and returned as ``.result`` (``.text`` carries its JSON).
    """
    sampling_tools = prepare_tools(tools)

    structured = result_type is not None and result_type is not str
    tool_choice: str | None = None
    if structured:
        sampling_tools = list(sampling_tools or [])
        sampling_tools.append(create_final_response_tool(result_type))  # type: ignore[arg-type]
        tool_choice = "required"

    current_messages: str | Sequence[str | SamplingMessage] = messages
    text_response_retries = 0
    consecutive_validation_failures = 0

    for _ in range(_MAX_ITERATIONS):
        step = await sample_step(
            context,
            messages=current_messages,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            model_preferences=model_preferences,
            tools=sampling_tools,
            tool_choice=tool_choice,
            mask_error_details=mask_error_details,
            tool_concurrency=tool_concurrency,
        )

        had_final_response = False
        if structured and step.is_tool_use:
            for tool_call in step.tool_calls:
                if tool_call.name != "final_response":
                    continue
                had_final_response = True
                type_adapter = get_cached_typeadapter(result_type)
                input_data = tool_call.input
                original_schema = compress_schema(
                    type_adapter.json_schema(), prune_titles=True
                )
                if (
                    original_schema.get("type") != "object"
                    and isinstance(input_data, dict)
                    and "value" in input_data
                ):
                    input_data = input_data["value"]
                try:
                    validated = type_adapter.validate_python(input_data)
                    text = json.dumps(type_adapter.dump_python(validated, mode="json"))
                    return SamplingResult(
                        text=text, result=validated, history=step.history
                    )
                except ValidationError as e:
                    consecutive_validation_failures += 1
                    if consecutive_validation_failures > _MAX_VALIDATION_RETRIES:
                        raise RuntimeError(
                            "Structured output validation failed "
                            f"{consecutive_validation_failures} consecutive times for "
                            f"type {result_type.__name__}: {e}"  # type: ignore[union-attr]
                        ) from e
                    step.history.append(
                        SamplingMessage(
                            role="user",
                            content=[
                                _tool_result(
                                    tool_call.id,
                                    f"Validation error: {e}. Please try again with valid data.",
                                    is_error=True,
                                )
                            ],
                        )
                    )

        if not had_final_response:
            consecutive_validation_failures = 0

        if not step.is_tool_use:
            if structured:
                text_response_retries += 1
                if text_response_retries > _MAX_TEXT_RESPONSE_RETRIES:
                    raise RuntimeError(
                        f"Expected structured output of type {result_type.__name__}, "  # type: ignore[union-attr]
                        "but the LLM returned a text response instead of calling "
                        f"the final_response tool ({text_response_retries} attempts)."
                    )
                step.history.append(
                    SamplingMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                "You must call the `final_response` tool to provide "
                                "your answer. Do not respond with text — use the tool."
                            ),
                        ),
                    )
                )
                current_messages = step.history
                continue
            return SamplingResult(
                text=step.text,
                result=cast(Any, step.text if step.text else ""),
                history=step.history,
            )

        current_messages = step.history
        if not structured:
            tool_choice = None

    raise RuntimeError(f"Sampling exceeded maximum iterations ({_MAX_ITERATIONS})")


__all__ = [
    "SampleStep",
    "SamplingResult",
    "SamplingTool",
    "call_sampling_handler",
    "get_sampling_handler",
    "sample",
    "sample_step",
    "sampling_available",
    "set_sampling_handler",
]
