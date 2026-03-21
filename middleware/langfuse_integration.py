"""Langfuse v4 observability integration for LLM sampling.

Configures tracing for both LiteLLM and Anthropic sampling handlers
using the Langfuse Python SDK v4 (OTel-based).

- **LiteLLM path**: Uses ``litellm.callbacks = ["langfuse_otel"]`` which is
  the v4-recommended OTel callback.  Auto-reads LANGFUSE_PUBLIC_KEY,
  LANGFUSE_SECRET_KEY, and LANGFUSE_HOST from env.  Captures model, tokens,
  latency, and cost per call automatically.

- **Anthropic path**: Wraps the handler with Langfuse ``@observe()`` decorator
  and uses ``propagate_attributes()`` for user_id / session_id propagation
  (the v4 replacement for the deprecated ``update_current_trace()``).

- **Trace context propagation**: Uses a ``ContextVar`` (same pattern as
  ``cost_tracker.py``) to carry tool name, template, result type, and step
  index from the sampling middleware down to the LiteLLM handler without
  threading extra parameters through the call chain.

All env vars are read from settings (which loads from .env).
"""

from __future__ import annotations

import os
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Optional

from config.enhanced_logging import setup_logger

logger = setup_logger()

# ── Per-request sampling trace context via ContextVar ────────────────────────

@dataclass
class _SamplingTraceContext:
    """Trace metadata accumulated for one tool execution's sampling calls."""

    tool_name: str = ""
    trace_id: str = ""  # stable UUID for the entire tool execution
    template: str = ""  # SamplingTemplate.value if used
    result_type: str = ""  # Pydantic model class name for structured output
    step_index: int = 0  # incremented for multi-step / retry loops
    enhancement_level: str = ""  # e.g. "basic", "contextual", "historical"
    has_tools: bool = False  # whether the sampling call includes tool use
    input_char_count: int = 0  # approximate input size
    tool_tags: list = field(default_factory=list)
    phase: str = (
        ""  # e.g. "validation" — disambiguates sub-calls within a tool execution
    )

_current_trace: ContextVar[Optional[_SamplingTraceContext]] = ContextVar(
    "langfuse_trace_ctx", default=None
)

def reset_sampling_trace_context(
    tool_name: str = "",
    tool_tags: Optional[list] = None,
) -> None:
    """Reset the trace context for a new tool execution.

    Call this at the start of ``on_call_tool`` so every tool execution
    gets a fresh trace ID and step counter.
    """
    _current_trace.set(
        _SamplingTraceContext(
            tool_name=tool_name,
            trace_id=uuid.uuid4().hex,
            tool_tags=list(tool_tags or []),
        )
    )

def set_sampling_trace_context(
    *,
    template: str = "",
    result_type: str = "",
    enhancement_level: str = "",
    has_tools: bool = False,
    input_char_count: int = 0,
    phase: str = "",
) -> None:
    """Enrich the current trace context with per-sample-call details.

    Call this inside ``SamplingContext.sample()`` before dispatching so the
    LiteLLM handler can build meaningful generation names and trace_metadata.
    Creates a context if none exists (graceful fallback).
    """
    ctx = _current_trace.get()
    if ctx is None:
        ctx = _SamplingTraceContext()
        _current_trace.set(ctx)
    if template:
        ctx.template = template
    if result_type:
        ctx.result_type = result_type
    if enhancement_level:
        ctx.enhancement_level = enhancement_level
    if has_tools:
        ctx.has_tools = has_tools
    if input_char_count:
        ctx.input_char_count = input_char_count
    if phase:
        ctx.phase = phase

def get_sampling_trace_context() -> Optional[_SamplingTraceContext]:
    """Return the current trace context, or None if not set."""
    return _current_trace.get()

def increment_sampling_step() -> int:
    """Increment the step counter and return the new value.

    Call this at the top of each iteration in multi-step / retry loops
    so each LLM call gets a distinct generation name.
    """
    ctx = _current_trace.get()
    if ctx is None:
        ctx = _SamplingTraceContext(step_index=1)
        _current_trace.set(ctx)
        return 1
    ctx.step_index += 1
    return ctx.step_index

_langfuse_initialized = False

def configure_langfuse() -> bool:
    """Set up Langfuse env vars and return True if configured.

    Must be called early (before LiteLLM imports) so that LiteLLM's
    ``langfuse_otel`` callback picks up the env vars.

    OTel TracerProvider is configured by otel_lifespan at server startup.
    """
    global _langfuse_initialized
    if _langfuse_initialized:
        return True

    try:
        from config.settings import settings

        if not settings.langfuse_enabled:
            logger.debug("Langfuse not configured — skipping")
            return False

        # Core credentials
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
        os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)

        _langfuse_initialized = True
        logger.info(
            "Langfuse v4 observability configured (host=%s)", settings.langfuse_host
        )

        # OTel TracerProvider is configured by otel_lifespan at server startup

        return True

    except Exception as e:
        logger.warning("Failed to configure Langfuse: %s", e)
        return False

def enable_litellm_langfuse() -> bool:
    """Enable the Langfuse OTel callback on LiteLLM.

    Uses ``"langfuse_otel"`` — the v4-recommended callback that sends
    spans via OpenTelemetry.  Falls back to ``"langfuse"`` (legacy) if
    the OTel callback is unavailable.

    Call this after ``configure_langfuse()`` and before any
    ``litellm.acompletion()``.
    """
    if not _langfuse_initialized:
        if not configure_langfuse():
            return False

    try:
        import litellm

        callback_name = "langfuse_otel"
        current = litellm.callbacks or []

        if callback_name not in current:
            litellm.callbacks = list(current) + [callback_name]
            logger.info("Langfuse OTel callback enabled on LiteLLM")
        return True

    except Exception as e:
        logger.warning("Failed to enable LiteLLM Langfuse callback: %s", e)
        return False

def wrap_anthropic_handler_with_langfuse(handler: Any) -> Any:
    """Wrap an Anthropic sampling handler with Langfuse ``@observe`` tracing.

    Uses ``propagate_attributes()`` (v4 API) to push ``user_id`` and
    ``session_id`` to all child spans within the trace.

    Args:
        handler: The AnthropicSamplingHandler callable (or tracking wrapper).

    Returns:
        A wrapped callable that traces each sampling call in Langfuse,
        or the original handler if Langfuse is unavailable.
    """
    if not _langfuse_initialized:
        if not configure_langfuse():
            return handler

    try:
        from langfuse import observe, propagate_attributes

        @observe(name="anthropic_sampling")
        async def _traced_handler(messages, params, context):
            # Propagate MCP session context + trace context into the Langfuse trace
            user_id = ""
            session_id = ""
            try:
                from auth.context import (
                    get_session_context_sync,
                    get_user_email_context_sync,
                )

                user_id = get_user_email_context_sync() or ""
                session_id = get_session_context_sync() or ""
            except Exception:
                pass

            trace_ctx = get_sampling_trace_context()
            tool_name = trace_ctx.tool_name if trace_ctx else ""
            step_index = trace_ctx.step_index if trace_ctx else 0
            phase = trace_ctx.phase if trace_ctx else ""
            trace_meta = {
                "source": "mcp-google-workspace",
                "mcp_tool": tool_name,
            }
            if trace_ctx:
                if trace_ctx.template:
                    trace_meta["template"] = trace_ctx.template
                if trace_ctx.result_type:
                    trace_meta["result_type"] = trace_ctx.result_type
                if step_index > 0:
                    trace_meta["step_index"] = str(step_index)
                if trace_ctx.phase:
                    trace_meta["phase"] = trace_ctx.phase

            # Build generation name with phase/step info
            obs_name = f"mcp::{tool_name}" if tool_name else "anthropic_sampling"
            if phase:
                obs_name = f"{obs_name}::{phase}"
            elif step_index > 0:
                obs_name = f"{obs_name}::step_{step_index}"

            with propagate_attributes(
                user_id=user_id or "unknown",
                session_id=session_id,
                tags=["mcp", "anthropic"],
                metadata={k: str(v) for k, v in trace_meta.items()},
            ):
                return await handler(messages, params, context)

        logger.info("Anthropic handler wrapped with Langfuse v4 @observe")
        return _traced_handler

    except Exception as e:
        logger.warning("Failed to wrap Anthropic handler with Langfuse: %s", e)
        return handler

# ── OTEL span management for parent-child hierarchy ──────────────────────

def start_tool_span(tool_name: str):
    """Create a ``sampling::{tool_name}`` span and attach it to the OTEL context.

    Returns a tuple of ``(span, token)`` where *token* is the context token
    that must be passed to :func:`end_span` to detach the context.

    If OTEL is not configured, returns ``(None, None)`` (no-op).
    """
    try:
        from opentelemetry import context as otel_context

        from middleware.otel_setup import get_mcp_tracer

        tracer = get_mcp_tracer()
        span = tracer.start_span(
            f"sampling::{tool_name}",
            attributes={"mcp.tool": tool_name, "mcp.component": "sampling"},
        )
        ctx = otel_context.set_value("current-span", span)
        # Also set as the active span via trace API
        from opentelemetry.trace import set_span_in_context

        ctx = set_span_in_context(span, ctx)
        token = otel_context.attach(ctx)
        return span, token
    except Exception:
        return None, None

def start_phase_span(phase: str, tool_name: str = ""):
    """Create a child span for a sampling phase (validation, dsl_recovery, main_sampling).

    Must be called while a parent tool span is active (via :func:`start_tool_span`).
    Returns ``(span, token)`` — pass to :func:`end_span`.
    """
    try:
        from opentelemetry import context as otel_context

        from middleware.otel_setup import get_mcp_tracer

        tracer = get_mcp_tracer()
        span_name = f"sampling::{tool_name}::{phase}" if tool_name else f"sampling::{phase}"
        span = tracer.start_span(
            span_name,
            attributes={
                "mcp.tool": tool_name,
                "mcp.phase": phase,
                "mcp.component": "sampling",
            },
        )
        from opentelemetry.trace import set_span_in_context

        ctx = set_span_in_context(span)
        token = otel_context.attach(ctx)
        return span, token
    except Exception:
        return None, None

def end_span(span, token, error: Optional[Exception] = None) -> None:
    """End a span and detach its context token.

    Args:
        span: The OTEL span returned by :func:`start_tool_span` / :func:`start_phase_span`.
        token: The context token to detach.
        error: If provided, the exception is recorded on the span and status set to ERROR.
    """
    if span is None:
        return
    try:
        from opentelemetry import context as otel_context
        from opentelemetry.trace import StatusCode

        if error is not None:
            span.set_status(StatusCode.ERROR, str(error))
            span.record_exception(error)
        else:
            span.set_status(StatusCode.OK)
        span.end()
        if token is not None:
            otel_context.detach(token)
    except Exception:
        pass

def add_langfuse_metadata(
    kwargs: dict,
    *,
    tool_name: str = "",
    session_id: str = "",
    user_email: str = "",
    generation_name: str = "",
    trace_name: str = "",
    trace_id: str = "",
    trace_metadata: Optional[dict] = None,
) -> dict:
    """Add Langfuse trace metadata to LiteLLM kwargs.

    The ``langfuse_otel`` callback maps these keys to Langfuse span attributes:

    - ``generation_name`` → observation/span name in Langfuse
    - ``trace_name``      → parent trace name
    - ``trace_id``        → links all spans from one tool execution to one trace
    - ``session_id``      → groups traces under a session
    - ``trace_user_id``   → user identifier
    - ``tags``            → searchable tags in Langfuse UI
    - ``trace_metadata``  → arbitrary key-value business context dict

    Args:
        kwargs: The ``litellm.acompletion()`` kwargs dict (mutated in place).
        tool_name: MCP tool name (used to build default generation_name).
        session_id: MCP session ID.
        user_email: Authenticated user email.
        generation_name: Override for the observation name (e.g. includes step).
        trace_name: Parent trace name — defaults to ``mcp::{tool_name}``.
        trace_id: UUID linking all LLM calls from one tool execution.
        trace_metadata: Free-form dict with business context (template, result_type, etc.).

    Returns:
        The kwargs dict with metadata added.
    """
    if not _langfuse_initialized:
        return kwargs

    metadata = kwargs.get("metadata", {}) or {}

    # Generation / observation name
    if generation_name:
        metadata["generation_name"] = generation_name
    elif tool_name:
        metadata["generation_name"] = f"mcp::{tool_name}"

    # Parent trace name
    if trace_name:
        metadata["trace_name"] = trace_name
    elif tool_name:
        metadata["trace_name"] = f"mcp::{tool_name}"

    # Trace ID links all spans within one tool execution
    if trace_id:
        metadata["trace_id"] = trace_id

    if session_id:
        metadata["session_id"] = session_id
    if user_email:
        metadata["trace_user_id"] = user_email

    metadata["tags"] = ["mcp", "sampling"]

    # Business context dict — convert all values to str for Langfuse v4 validation
    if trace_metadata:
        safe_meta = {
            k: str(v) for k, v in trace_metadata.items() if v is not None and v != ""
        }
        if safe_meta:
            metadata["trace_metadata"] = safe_meta

    kwargs["metadata"] = metadata
    return kwargs
