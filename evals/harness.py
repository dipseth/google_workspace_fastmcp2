"""Client, sampling-handler, and usage-collection plumbing for cross-model evals.

The eval runner connects to the running MCP server as a FastMCP client and
attaches a *client-side* sampling handler per model config.  Every
``ctx.sample()`` a dynamic tool makes on the server is fulfilled by the eval
process with the model under test, so the model is the only variable between
runs.  A LiteLLM ``CustomLogger`` records per-call token usage, latency, and
cost while an eval item is active.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx
from litellm.integrations.custom_logger import CustomLogger


class SamplingUsageCollector(CustomLogger):
    """Collect per-call LLM usage from LiteLLM while an eval item is active.

    Eval items run strictly sequentially, so a single active bucket is enough.
    ``begin()`` before the tool call, ``end()`` after — every LiteLLM
    completion in between (client-side sampling calls triggered by the server)
    is attributed to that item.
    """

    def __init__(self) -> None:
        super().__init__()
        self._bucket: Optional[dict] = None

    def begin(self, item_id: str, model_label: str) -> None:
        self._bucket = {
            "item_id": item_id,
            "model_label": model_label,
            "calls": [],
            "failures": 0,
        }

    def end(self) -> dict:
        bucket, self._bucket = self._bucket, None
        return bucket or {"calls": [], "failures": 0}

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        bucket = self._bucket
        if bucket is None:
            return
        usage = getattr(response_obj, "usage", None)
        cost = kwargs.get("response_cost")
        if cost is None:
            try:
                import litellm

                cost = litellm.completion_cost(completion_response=response_obj)
            except Exception:
                cost = 0.0
        try:
            latency_s = (end_time - start_time).total_seconds()
        except Exception:
            latency_s = 0.0
        bucket["calls"].append(
            {
                "model": kwargs.get("model", ""),
                "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                "cost_usd": float(cost or 0.0),
                "latency_s": latency_s,
            }
        )

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        if self._bucket is not None:
            self._bucket["failures"] += 1


def install_collector() -> SamplingUsageCollector:
    """Register a fresh collector on LiteLLM's callback list."""
    import litellm

    collector = SamplingUsageCollector()
    litellm.callbacks = list(litellm.callbacks or []) + [collector]
    return collector


def summarize_usage(bucket: dict) -> dict:
    calls = bucket.get("calls", [])
    return {
        "sampling_calls": len(calls),
        "sampling_failures": bucket.get("failures", 0),
        "prompt_tokens": sum(c["prompt_tokens"] for c in calls),
        "completion_tokens": sum(c["completion_tokens"] for c in calls),
        "total_tokens": sum(c["prompt_tokens"] + c["completion_tokens"] for c in calls),
        "cost_usd": round(sum(c["cost_usd"] for c in calls), 6),
        "llm_latency_s": round(sum(c["latency_s"] for c in calls), 3),
    }


def build_sampling_handler(model_cfg: dict):
    """Create a LiteLLMSamplingHandler for one model config from models.json."""
    from middleware.litellm_sampling_handler import LiteLLMSamplingHandler

    api_key = None
    if model_cfg.get("api_key_env"):
        api_key = os.getenv(model_cfg["api_key_env"]) or None
    return LiteLLMSamplingHandler(
        default_model=model_cfg["model"],
        api_key=api_key,
        api_base=model_cfg.get("api_base"),
    )


def server_url() -> str:
    return os.getenv("MCP_SERVER_URL", "https://localhost:8002/mcp")


def auth_token() -> Optional[str]:
    # MCP_API_KEY (server primary) before TEST_MCP_API_KEY — the test key can
    # go stale when the server's key rotates, and evals need a live session.
    for env in ("EVAL_MCP_API_KEY", "MCP_API_KEY", "TEST_MCP_API_KEY"):
        key = (os.getenv(env) or "").strip()
        if key:
            return key
    return None


def make_client(sampling_handler):
    """FastMCP client against the local server with TLS verify off (dev certs).

    Advertises the sampling.tools capability — without it, structured-output
    sampling (validation agents, draft variations) silently falls back to the
    *server's* handler and the model under test never gets exercised.
    """
    import mcp.types as mcp_types
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    sampling_caps = mcp_types.SamplingCapability(
        tools=mcp_types.SamplingToolsCapability()
    )

    def _httpx_client_factory(**kwargs) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            verify=os.getenv("MCP_TEST_TLS_VERIFY", "false").lower() == "true",
            headers=kwargs.get("headers"),
            timeout=kwargs.get("timeout") or httpx.Timeout(120.0),
            auth=kwargs.get("auth"),
            follow_redirects=kwargs.get("follow_redirects", True),
        )

    url = server_url()
    if url.lower().startswith("https"):
        transport = StreamableHttpTransport(
            url, auth=auth_token(), httpx_client_factory=_httpx_client_factory
        )
        return Client(
            transport,
            timeout=300.0,
            sampling_handler=sampling_handler,
            sampling_capabilities=sampling_caps,
        )
    return Client(
        url,
        auth=auth_token(),
        timeout=300.0,
        sampling_handler=sampling_handler,
        sampling_capabilities=sampling_caps,
    )


def result_to_text(result: Any, limit: int = 8000) -> str:
    """Flatten a CallToolResult into a text blob for judging/trace display."""
    try:
        data = getattr(result, "data", None)
        if data is not None:
            if hasattr(data, "model_dump"):
                data = data.model_dump()
            return json.dumps(data, default=str, ensure_ascii=False)[:limit]
    except Exception:
        pass
    try:
        parts = [
            block.text
            for block in getattr(result, "content", []) or []
            if hasattr(block, "text")
        ]
        if parts:
            return "\n".join(parts)[:limit]
    except Exception:
        pass
    return str(result)[:limit]
