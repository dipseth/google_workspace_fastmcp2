#!/usr/bin/env python3
"""Test whether Venice AI can proxy Anthropic models with prompt caching.

Sends requests to Venice's OpenAI-compatible endpoint using an Anthropic
model identifier and checks if cache_control_injection_points are honored.

Usage:
    uv run python scripts/test_venice_anthropic_cache.py
"""

import asyncio
import json
import os
import sys
import time

# Fix SSL on macOS
if sys.platform == "darwin":
    try:
        import certifi
        import litellm as _ssl

        os.environ["SSL_CERT_FILE"] = certifi.where()
        os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
        _ssl.ssl_verify = certifi.where()
    except ImportError:
        pass


def _format_usage(usage) -> dict:
    """Extract all available usage fields."""
    if not usage:
        return {"error": "no usage object"}
    result = {}
    # Standard fields
    for f in (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
    ):
        val = getattr(usage, f, None)
        if val is not None:
            result[f] = val

    # Anthropic cache fields
    for f in (
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ):
        val = getattr(usage, f, None)
        if val is not None:
            result[f] = val

    # LiteLLM prompt_tokens_details
    details = getattr(usage, "prompt_tokens_details", None)
    if details:
        result["prompt_tokens_details"] = {
            k: getattr(details, k, None)
            for k in ("cached_tokens", "audio_tokens")
            if getattr(details, k, None) is not None
        }

    # Dump any other attributes we might not know about
    for attr in dir(usage):
        if attr.startswith("_"):
            continue
        if attr in result or attr in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "prompt_tokens_details",
        ):
            continue
        val = getattr(usage, attr, None)
        if val is not None and not callable(val):
            result[f"_extra_{attr}"] = str(val)[:200]

    return result


def _build_large_system_prompt() -> str:
    """Build a system prompt >1024 tokens to be cacheable."""
    lines = [
        "You are a helpful assistant that validates structured data formats.",
        "",
        "## Validation Rules Reference",
        "",
    ]
    # Generate enough content to exceed 1024 tokens
    for i in range(1, 100):
        lines.append(
            f"- Rule {i}: Validate field_{i} ensures type correctness, "
            f"range constraints [0..{i * 100}], required attributes "
            f"(name, type, description), and cross-references with "
            f"related fields. Enforce strict ordering and uniqueness."
        )
    return "\n".join(lines)


VENICE_BASE = "https://api.venice.ai/api/v1"

# Venice exposes Anthropic models via OpenAI-compatible endpoint.
# LiteLLM needs "openai/" prefix to route through a custom api_base.
MODELS_TO_TRY = [
    "openai/claude-sonnet-4-6",
    "openai/claude-opus-4-5",
]


async def test_model(model: str, api_key: str, system_prompt: str) -> dict:
    """Test a single model through Venice with cache control."""
    import litellm

    litellm.drop_params = True  # Let Venice ignore unknown params gracefully

    print(f"\n--- Testing model: {model} ---")

    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Reply with just OK."},
        ],
        "max_tokens": 10,
        "temperature": 0.0,
        "api_key": api_key,
        "api_base": VENICE_BASE,
        "cache_control_injection_points": [
            {"location": "message", "role": "system"},
        ],
    }

    # Call 1 — potential cache write
    try:
        t0 = time.monotonic()
        r1 = await litellm.acompletion(**kwargs)
        e1 = time.monotonic() - t0

        u1 = _format_usage(r1.usage)
        content1 = getattr(r1.choices[0].message, "content", "") if r1.choices else ""
        print(f"  Call 1 ({e1:.2f}s): {json.dumps(u1, indent=4)}")
        print(f"  Response: {content1}")

        # Call 2 — potential cache read
        await asyncio.sleep(2)
        t0 = time.monotonic()
        r2 = await litellm.acompletion(**kwargs)
        e2 = time.monotonic() - t0

        u2 = _format_usage(r2.usage)
        content2 = getattr(r2.choices[0].message, "content", "") if r2.choices else ""
        print(f"  Call 2 ({e2:.2f}s): {json.dumps(u2, indent=4)}")
        print(f"  Response: {content2}")

        # Check for cache evidence
        cached = (
            u2.get("cache_read_input_tokens", 0)
            or (u2.get("prompt_tokens_details", {}) or {}).get("cached_tokens", 0)
            or 0
        )
        return {
            "model": model,
            "success": True,
            "cached_on_call2": cached,
            "usage_call1": u1,
            "usage_call2": u2,
        }

    except Exception as e:
        err_str = str(e)[:300]
        print(f"  FAILED: {err_str}")
        return {"model": model, "success": False, "error": err_str}


async def main():
    api_key = os.environ.get("VENICE_INFERENCE_KEY")
    if not api_key:
        print("ERROR: VENICE_INFERENCE_KEY not set")
        sys.exit(1)

    system_prompt = _build_large_system_prompt()
    est_tokens = len(system_prompt) // 4
    print(f"System prompt: {len(system_prompt):,} chars (~{est_tokens:,} tokens)")
    print(f"Venice endpoint: {VENICE_BASE}")
    print(f"Models to test: {MODELS_TO_TRY}")

    results = []
    for model in MODELS_TO_TRY:
        result = await test_model(model, api_key, system_prompt)
        results.append(result)
        if result.get("success") and result.get("cached_on_call2", 0) > 0:
            print(f"\n  >>> CACHE HIT DETECTED with {model}! <<<")
            break  # Found a working combo

    print(f"\n{'=' * 60}")
    print("Summary:")
    for r in results:
        status = "OK" if r["success"] else "FAIL"
        cached = r.get("cached_on_call2", "N/A")
        print(f"  {r['model']}: {status}, cached_tokens={cached}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
