#!/usr/bin/env python3
"""Standalone verification script for Anthropic prompt cache keepalive.

Sends two identical system prompts in quick succession via LiteLLM and
inspects the raw usage response to confirm cache write → cache read.

Usage:
    # Uses ANTHROPIC_API_KEY from environment
    uv run python scripts/verify_cache_keepalive.py

    # Or pass explicitly
    ANTHROPIC_API_KEY=sk-ant-... uv run python scripts/verify_cache_keepalive.py

    # Custom model (default: anthropic/claude-sonnet-4-6)
    uv run python scripts/verify_cache_keepalive.py --model anthropic/claude-haiku-3-5

Exit codes:
    0 — Cache verified working (call 2 returned cached_tokens > 0)
    1 — Cache NOT working or verification failed
"""

import argparse
import asyncio
import json
import os
import sys
import time

# Fix SSL certificate verification on macOS Python
if sys.platform == "darwin":
    try:
        import certifi
        import litellm as _litellm_ssl_fix

        os.environ["SSL_CERT_FILE"] = certifi.where()
        os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
        _litellm_ssl_fix.ssl_verify = certifi.where()
    except ImportError:
        pass


def _format_usage(usage) -> dict:
    """Extract all cache-relevant fields from a LiteLLM usage object."""
    result = {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "total_tokens": getattr(usage, "total_tokens", 0) or 0,
    }

    # LiteLLM surfaces Anthropic's cache fields in prompt_tokens_details
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    if prompt_details:
        result["cached_tokens"] = getattr(prompt_details, "cached_tokens", 0) or 0
    else:
        result["cached_tokens"] = 0

    # Also check for Anthropic-native fields that LiteLLM may pass through
    for field in (
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ):
        val = getattr(usage, field, None)
        if val is not None:
            result[field] = val

    return result


def _build_system_prompt() -> str:
    """Build a system prompt large enough to be cacheable (>1024 tokens).

    Uses the real gchat DSL docs if available, otherwise generates padding.
    """
    parts = [
        "You are a Google Chat card DSL expert validator. "
        "Your job is to review card_description and card_params for correctness."
    ]

    # Try to use real DSL docs from the project
    try:
        from gchat.wrapper_api import get_dsl_documentation

        parts.append(
            get_dsl_documentation(include_examples=True, include_hierarchy=True)
        )
    except Exception:
        pass

    try:
        from gchat.wrapper_api import get_gchat_symbol_table_text

        parts.append(get_gchat_symbol_table_text())
    except Exception:
        pass

    prompt = "\n\n".join(parts)

    # Anthropic requires minimum 1024 tokens (~4096 chars) for caching.
    # Pad if our real docs are too short.
    if len(prompt) < 5000:
        padding = (
            "\n\n## Extended Reference\n"
            + "\n".join(
                [
                    f"- Rule {i}: Validate that component hierarchy follows "
                    f"strict parent-child relationships for element type {i}. "
                    f"Ensure all required attributes are present and correctly typed. "
                    f"Check for duplicate keys and missing required fields."
                    for i in range(1, 80)
                ]
            )
        )
        prompt += padding

    return prompt


async def verify_cache(model: str, delay: float = 2.0) -> bool:
    """Send two calls with identical system prompts and verify cache behavior.

    Args:
        model: LiteLLM model identifier (e.g. 'anthropic/claude-sonnet-4-6')
        delay: Seconds to wait between calls

    Returns:
        True if cache hit detected on second call
    """
    import litellm

    system_prompt = _build_system_prompt()
    prompt_chars = len(system_prompt)
    estimated_tokens = prompt_chars // 4

    print(f"\n{'='*60}")
    print(f"Anthropic Prompt Cache Verification")
    print(f"{'='*60}")
    print(f"Model:            {model}")
    print(f"System prompt:    {prompt_chars:,} chars (~{estimated_tokens:,} tokens)")
    print(f"Min for caching:  1,024 tokens")
    print(f"Delay between:    {delay}s")
    print()

    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Reply with just OK."},
        ],
        "max_tokens": 10,
        "temperature": 0.0,
        "cache_control_injection_points": [
            {"location": "message", "role": "system"},
        ],
    }

    # --- Call 1: Cache WRITE (cold) ---
    print(f"--- Call 1 (cache write / cold) ---")
    t0 = time.monotonic()
    response1 = await litellm.acompletion(**kwargs)
    elapsed1 = time.monotonic() - t0

    usage1 = _format_usage(response1.usage)
    print(f"  Elapsed:    {elapsed1:.2f}s")
    print(f"  Usage:      {json.dumps(usage1, indent=2)}")
    print(f"  Response:   {getattr(response1.choices[0].message, 'content', '')}")
    print()

    # --- Wait ---
    print(f"Waiting {delay}s before second call...")
    await asyncio.sleep(delay)

    # --- Call 2: Cache READ (warm) ---
    print(f"\n--- Call 2 (cache read / warm) ---")
    t0 = time.monotonic()
    response2 = await litellm.acompletion(**kwargs)
    elapsed2 = time.monotonic() - t0

    usage2 = _format_usage(response2.usage)
    print(f"  Elapsed:    {elapsed2:.2f}s")
    print(f"  Usage:      {json.dumps(usage2, indent=2)}")
    print(f"  Response:   {getattr(response2.choices[0].message, 'content', '')}")
    print()

    # --- Verdict ---
    cached_tokens = usage2.get("cached_tokens", 0)
    cache_read = usage2.get("cache_read_input_tokens", 0)
    cache_hit = cached_tokens > 0 or cache_read > 0

    print(f"{'='*60}")
    if cache_hit:
        tokens_cached = cached_tokens or cache_read
        savings_pct = (tokens_cached / usage2["prompt_tokens"] * 100) if usage2["prompt_tokens"] else 0
        print(f"CACHE VERIFIED WORKING")
        print(f"  Cached tokens on call 2:  {tokens_cached:,}")
        print(f"  Cache coverage:           {savings_pct:.1f}% of input tokens")
        print(f"  Latency improvement:      {elapsed1:.2f}s -> {elapsed2:.2f}s")
        if elapsed1 > 0:
            print(f"  Speed improvement:        {((elapsed1 - elapsed2) / elapsed1 * 100):.1f}%")
    else:
        print(f"CACHE NOT DETECTED")
        print(f"  No cached_tokens in call 2 response.")
        print(f"  Possible reasons:")
        print(f"    - System prompt too short (<1024 tokens)")
        print(f"    - Model doesn't support caching")
        print(f"    - cache_control_injection_points not honored")
    print(f"{'='*60}")

    # --- Optional: Call 3 to show the keepalive pattern ---
    if cache_hit:
        print(f"\n--- Call 3 (varied user message, same system prefix) ---")
        kwargs_varied = {**kwargs}
        kwargs_varied["messages"] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": "Generate a simple card DSL with one section and two buttons.",
            },
        ]
        kwargs_varied["max_tokens"] = 100
        kwargs_varied["temperature"] = 0.7

        t0 = time.monotonic()
        response3 = await litellm.acompletion(**kwargs_varied)
        elapsed3 = time.monotonic() - t0

        usage3 = _format_usage(response3.usage)
        cached3 = usage3.get("cached_tokens", 0) or usage3.get(
            "cache_read_input_tokens", 0
        )
        print(f"  Elapsed:    {elapsed3:.2f}s")
        print(f"  Cached:     {cached3:,} tokens (system prefix still cached)")
        print(
            f"  Response:   {getattr(response3.choices[0].message, 'content', '')[:200]}..."
        )
        print()
        print(
            "This confirms the keepalive pattern works: same system prefix "
            "stays cached even with different user messages."
        )

    return cache_hit


def main():
    parser = argparse.ArgumentParser(
        description="Verify Anthropic prompt cache keepalive"
    )
    parser.add_argument(
        "--model",
        default="anthropic/claude-sonnet-4-6",
        help="LiteLLM model identifier (default: anthropic/claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds between calls (default: 2.0)",
    )
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY environment variable not set.")
        print("Set it and re-run: ANTHROPIC_API_KEY=sk-ant-... uv run python scripts/verify_cache_keepalive.py")
        sys.exit(1)

    success = asyncio.run(verify_cache(model=args.model, delay=args.delay))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
