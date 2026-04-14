"""Cost tracking for sampling and Qdrant usage.

Uses a ContextVar to accumulate sampling costs within a single tool execution.
The Qdrant middleware reads accumulated costs after call_next() returns and
includes them in the stored payload for cost analytics.

Monthly budget enforcement: ``is_budget_exceeded()`` checks whether the current
calendar month's spend has crossed ``SAMPLING_MONTHLY_BUDGET_USD``.  The
sampling handler and middleware call this before making LLM requests.

Reactive keepalive support: ``record_sampling_activity()`` / ``seconds_since_last_activity()``
let the keepalive engine know when *real* (non-keepalive) sampling happened.
"""

from __future__ import annotations

import json as _json
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from config.enhanced_logging import setup_logger

logger = setup_logger()

# ── Monthly budget + reactive keepalive state ──────────────────────────────

_last_sampling_activity: float = 0.0  # epoch of last real (non-keepalive) sampling call
_monthly_costs: dict = {}  # {"2026-04": 3.21, ...}


def _current_month_key() -> str:
    """Return e.g. '2026-04'."""
    return time.strftime("%Y-%m")


def record_sampling_activity() -> None:
    """Mark that a real (non-keepalive) sampling call just happened."""
    global _last_sampling_activity
    _last_sampling_activity = time.time()


def seconds_since_last_activity() -> float:
    """Seconds since the last real sampling activity (inf if none)."""
    if _last_sampling_activity == 0.0:
        return float("inf")
    return time.time() - _last_sampling_activity


def add_monthly_cost(amount_usd: float) -> None:
    """Accumulate *amount_usd* into the current calendar month."""
    key = _current_month_key()
    _monthly_costs[key] = _monthly_costs.get(key, 0.0) + amount_usd


def get_monthly_cost() -> float:
    """Total sampling spend for the current calendar month."""
    return _monthly_costs.get(_current_month_key(), 0.0)


def is_budget_exceeded() -> bool:
    """Return True if the monthly budget has been exceeded.

    Returns False (unlimited) when budget is 0 or unset.
    """
    try:
        from config.settings import settings

        budget = settings.sampling_monthly_budget_usd
    except Exception:
        return False
    if budget <= 0:
        return False
    return get_monthly_cost() >= budget


def load_monthly_costs(path: str | Path | None = None) -> None:
    """Load persisted monthly costs from the sampling cost JSON file."""
    global _monthly_costs, _last_sampling_activity
    if path is None:
        try:
            from config.settings import settings

            path = settings.sampling_cost_persistence_file
        except Exception:
            return
    try:
        data = _json.loads(Path(path).read_text())
        # The file stores per-module stats; we read the top-level monthly_costs dict
        _monthly_costs.update(data.get("monthly_costs", {}))
        _last_sampling_activity = data.get("last_sampling_activity", 0.0)
    except (FileNotFoundError, _json.JSONDecodeError, Exception):
        pass


def save_monthly_costs(path: str | Path | None = None) -> None:
    """Persist monthly costs back into the sampling cost JSON file."""
    if path is None:
        try:
            from config.settings import settings

            path = settings.sampling_cost_persistence_file
        except Exception:
            return
    p = Path(path)
    try:
        data = _json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        data = {}
    data["monthly_costs"] = _monthly_costs
    data["last_sampling_activity"] = _last_sampling_activity
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_json.dumps(data, indent=2))
    except Exception as e:
        logger.debug("Failed to persist monthly costs: %s", e)


# ── Per-request cost accumulator via ContextVar ──────────────────────────


@dataclass
class _SamplingCosts:
    """Accumulated sampling costs for one tool execution."""

    sample_calls: int = 0
    total_input_chars: int = 0
    total_output_chars: int = 0
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_cached_tokens: int = 0
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
    cached_tokens: int = 0,
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
        cached_tokens: Number of input tokens served from provider cache (cost reduced to 10%).
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

    # Cached input tokens cost 10% of normal rate (Anthropic prompt caching)
    safe_cached = min(cached_tokens, in_tok)
    non_cached = max(0, in_tok - safe_cached)
    estimated_cost = (
        (non_cached * input_rate)
        + (safe_cached * input_rate * 0.1)
        + (out_tok * output_rate)
    )

    costs.sample_calls += 1
    costs.total_input_chars += len(input_text) if input_text else 0
    costs.total_output_chars += len(output_text) if output_text else 0
    costs.estimated_input_tokens += in_tok
    costs.estimated_output_tokens += out_tok
    costs.estimated_cached_tokens += safe_cached
    costs.estimated_cost_usd += estimated_cost
    if model:
        costs.model = model

    # Update monthly budget tracking
    add_monthly_cost(estimated_cost)
    record_sampling_activity()

    logger.debug(
        "Sampling cost tracked: +%d input/%d output tokens, "
        "+$%.6f (total calls=%d, total=$%.6f, month=$%.4f)",
        input_tokens,
        output_tokens,
        estimated_cost,
        costs.sample_calls,
        costs.estimated_cost_usd,
        get_monthly_cost(),
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
            "sampling_estimated_cached_tokens": 0,
            "cost_sampling_estimated": 0.0,
            "sampling_model": "",
        }
    return {
        "sampling_detected": True,
        "sampling_calls": costs.sample_calls,
        "sampling_estimated_input_tokens": costs.estimated_input_tokens,
        "sampling_estimated_output_tokens": costs.estimated_output_tokens,
        "sampling_estimated_cached_tokens": costs.estimated_cached_tokens,
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
