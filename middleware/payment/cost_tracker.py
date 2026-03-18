"""Cost tracking for sampling and Qdrant usage.

Uses a ContextVar to accumulate sampling costs within a single tool execution.
The Qdrant middleware reads accumulated costs after call_next() returns and
includes them in the stored payload for cost analytics.
"""

from __future__ import annotations

import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional

from config.enhanced_logging import setup_logger

logger = setup_logger()

# ── Per-request cost accumulator via ContextVar ──────────────────────────


@dataclass
class _SamplingCosts:
    """Accumulated sampling costs for one tool execution."""

    sample_calls: int = 0
    total_input_chars: int = 0
    total_output_chars: int = 0
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    model: str = ""


_current_costs: ContextVar[Optional[_SamplingCosts]] = ContextVar(
    "sampling_costs", default=None
)


def reset() -> None:
    """Reset the cost accumulator for a new tool execution."""
    _current_costs.set(_SamplingCosts())


def track_sample_call(
    input_text: str = "",
    output_text: str = "",
    model: str = "",
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Record a single sampling call's cost estimate.

    Accepts either actual token counts (from provider usage data) or
    text for heuristic estimation (~4 chars per token).

    Args:
        input_text: The prompt/input text (used for estimation if input_tokens=0).
        output_text: The response text (used for estimation if output_tokens=0).
        model: Model identifier (for logging; rates come from settings).
        input_tokens: Actual input token count from provider (overrides text estimation).
        output_tokens: Actual output token count from provider (overrides text estimation).
    """
    costs = _current_costs.get()
    if costs is None:
        costs = _SamplingCosts()
        _current_costs.set(costs)

    # Use actual token counts if provided, otherwise estimate from text
    if input_tokens > 0 or output_tokens > 0:
        in_tok = input_tokens
        out_tok = output_tokens
    else:
        input_chars = len(input_text) if input_text else 0
        output_chars = len(output_text) if output_text else 0
        # Heuristic: ~4 chars ≈ 1 token for English text
        in_tok = max(1, input_chars // 4)
        out_tok = max(1, output_chars // 4)

    # Load rates from settings (import here to avoid circular imports)
    try:
        from config.settings import settings

        input_rate = settings.sampling_input_token_rate
        output_rate = settings.sampling_output_token_rate
    except Exception:
        # Fallback to Claude Sonnet rates
        input_rate = 0.000003
        output_rate = 0.000015

    estimated_cost = (in_tok * input_rate) + (out_tok * output_rate)

    costs.sample_calls += 1
    costs.total_input_chars += len(input_text) if input_text else 0
    costs.total_output_chars += len(output_text) if output_text else 0
    costs.estimated_input_tokens += in_tok
    costs.estimated_output_tokens += out_tok
    costs.estimated_cost_usd += estimated_cost
    if model:
        costs.model = model

    logger.debug(
        "Sampling cost tracked: +%d input/%d output tokens, "
        "+$%.6f (total calls=%d, total=$%.6f)",
        input_tokens,
        output_tokens,
        estimated_cost,
        costs.sample_calls,
        costs.estimated_cost_usd,
    )


def get_current_costs() -> dict:
    """Return accumulated costs for the current tool execution.

    Returns a dict suitable for merging into the Qdrant payload:
        sampling_detected: bool
        sampling_calls: int
        sampling_estimated_input_tokens: int
        sampling_estimated_output_tokens: int
        cost_sampling_estimated: float  (USD)
        sampling_model: str
    """
    costs = _current_costs.get()
    if costs is None or costs.sample_calls == 0:
        return {
            "sampling_detected": False,
            "sampling_calls": 0,
            "sampling_estimated_input_tokens": 0,
            "sampling_estimated_output_tokens": 0,
            "cost_sampling_estimated": 0.0,
            "sampling_model": "",
        }
    return {
        "sampling_detected": True,
        "sampling_calls": costs.sample_calls,
        "sampling_estimated_input_tokens": costs.estimated_input_tokens,
        "sampling_estimated_output_tokens": costs.estimated_output_tokens,
        "cost_sampling_estimated": round(costs.estimated_cost_usd, 8),
        "sampling_model": costs.model,
    }


# ── Qdrant operation cost estimation ─────────────────────────────────────


def estimate_qdrant_cost(operation: str = "upsert") -> float:
    """Estimate Qdrant cost per operation.

    Based on rough cloud pricing estimates. The actual cost depends on
    deployment — this provides a baseline for tracking and refinement.

    Args:
        operation: One of "upsert", "search", "embed".

    Returns:
        Estimated USD cost for the operation.
    """
    try:
        from config.settings import settings

        costs = {
            "upsert": settings.qdrant_cost_per_upsert,
            "search": settings.qdrant_cost_per_search,
        }
    except Exception:
        costs = {
            "upsert": 0.0001,
            "search": 0.00005,
        }

    # Embed cost is always a fixed estimate (CPU time)
    costs["embed"] = 0.0001

    return costs.get(operation, 0.0)
