#!/usr/bin/env python3
"""Test prompt caching: Venice-proxied Claude vs direct Anthropic Claude.

Sends identical system prompts twice per path and checks for cache hits.

Usage:
    uv run python scripts/test_cache_both_paths.py
"""

import asyncio
import json
import os
import sys
import time

if sys.platform == "darwin":
    try:
        import certifi
        import litellm as _ssl

        os.environ["SSL_CERT_FILE"] = certifi.where()
        os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
        _ssl.ssl_verify = certifi.where()
    except ImportError:
        pass


def _usage(u) -> dict:
    if not u:
        return {}
    r = {
        "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
    }
    for f in ("cache_creation_input_tokens", "cache_read_input_tokens"):
        v = getattr(u, f, None)
        if v is not None:
            r[f] = v
    d = getattr(u, "prompt_tokens_details", None)
    if d:
        ct = getattr(d, "cached_tokens", 0) or 0
        if ct:
            r["cached_tokens"] = ct
    return r


def _system_prompt() -> str:
    lines = [
        "You are a validation expert for structured data formats.",
        "",
        "## Reference Rules",
        "",
    ]
    for i in range(1, 80):
        lines.append(
            f"- Rule {i}: field_{i} must be type-checked with range "
            f"[0..{i * 100}], required attrs (name, type, desc), "
            f"cross-ref related fields, enforce ordering and uniqueness."
        )
    return "\n".join(lines)


async def test_path(label: str, model: str, api_key: str, api_base: str | None):
    import litellm

    litellm.drop_params = True

    prompt = _system_prompt()
    print(f"\n{'='*50}")
    print(f"  {label}")
    print(f"  model={model}")
    print(f"  api_base={api_base or '(default)'}")
    print(f"  prompt ~{len(prompt)//4} tokens")
    print(f"{'='*50}")

    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Reply OK."},
        ],
        "max_tokens": 5,
        "temperature": 0.0,
        "api_key": api_key,
        "cache_control_injection_points": [
            {"location": "message", "role": "system"},
        ],
    }
    if api_base:
        kwargs["api_base"] = api_base

    # Call 1
    t0 = time.monotonic()
    r1 = await litellm.acompletion(**kwargs)
    e1 = time.monotonic() - t0
    u1 = _usage(r1.usage)
    print(f"  Call 1 ({e1:.2f}s): {json.dumps(u1)}")

    await asyncio.sleep(2)

    # Call 2
    t0 = time.monotonic()
    r2 = await litellm.acompletion(**kwargs)
    e2 = time.monotonic() - t0
    u2 = _usage(r2.usage)
    cached = u2.get("cached_tokens", 0) or u2.get("cache_read_input_tokens", 0)
    print(f"  Call 2 ({e2:.2f}s): {json.dumps(u2)}")

    if cached > 0:
        print(f"  --> CACHE HIT: {cached} tokens cached")
    else:
        print(f"  --> NO CACHE HIT")

    return cached > 0


async def main():
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    venice_key = os.environ.get("VENICE_INFERENCE_KEY", "")

    results = {}

    # Path 1: Venice-proxied Claude Sonnet
    if venice_key:
        try:
            ok = await test_path(
                label="Venice-proxied Claude Sonnet",
                model="openai/claude-sonnet-4-6",
                api_key=venice_key,
                api_base="https://api.venice.ai/api/v1",
            )
            results["Venice (openai/claude-sonnet-4-6)"] = ok
        except Exception as e:
            print(f"  FAILED: {str(e)[:200]}")
            results["Venice (openai/claude-sonnet-4-6)"] = False
    else:
        print("\nSkipping Venice: VENICE_INFERENCE_KEY not set")

    # Path 2: Direct Anthropic Claude Sonnet
    if anthropic_key:
        try:
            ok = await test_path(
                label="Direct Anthropic Claude Sonnet",
                model="anthropic/claude-sonnet-4-6",
                api_key=anthropic_key,
                api_base=None,
            )
            results["Anthropic (anthropic/claude-sonnet-4-6)"] = ok
        except Exception as e:
            print(f"  FAILED: {str(e)[:200]}")
            results["Anthropic (anthropic/claude-sonnet-4-6)"] = False
    else:
        print("\nSkipping Anthropic: ANTHROPIC_API_KEY not set")

    # Summary
    print(f"\n{'='*50}")
    print("SUMMARY")
    print(f"{'='*50}")
    for path, ok in results.items():
        status = "CACHE WORKS" if ok else "NO CACHE"
        print(f"  {path}: {status}")
    print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(main())
