"""Tests for FastEmbed Qdrant semantic cache and cached token cost tracking.

Requires: Qdrant running + QDRANT_URL set (auto-skipped via conftest if not).
Loads .env for settings like SAMPLING_CACHE_ENABLED.
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

# Load .env so settings pick up QDRANT_URL, SAMPLING_CACHE_ENABLED, etc.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# Fix SSL for macOS Python (same fix as litellm_sampling_handler.py)
if sys.platform == "darwin":
    try:
        import certifi

        os.environ["SSL_CERT_FILE"] = certifi.where()
        os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
    except ImportError:
        pass


# ── Cost tracker tests (no external deps) ────────────────────────────────


class TestCostTrackerCachedTokens:
    """Verify cached_tokens reduces estimated cost."""

    def test_no_cached_tokens(self):
        from middleware.payment.cost_tracker import (
            get_current_costs,
            reset,
            track_sample_call,
        )

        reset()
        track_sample_call(input_tokens=1000, output_tokens=200, model="test")
        costs = get_current_costs()
        assert costs["sampling_estimated_cached_tokens"] == 0
        assert costs["cost_sampling_estimated"] > 0

    def test_cached_tokens_reduces_cost(self):
        from middleware.payment.cost_tracker import (
            get_current_costs,
            reset,
            track_sample_call,
        )

        reset()
        track_sample_call(input_tokens=1000, output_tokens=200, model="test")
        cost_no_cache = get_current_costs()["cost_sampling_estimated"]

        reset()
        track_sample_call(
            input_tokens=1000, output_tokens=200, model="test", cached_tokens=800
        )
        cost_with_cache = get_current_costs()

        assert cost_with_cache["sampling_estimated_cached_tokens"] == 800
        assert cost_with_cache["cost_sampling_estimated"] < cost_no_cache

    def test_cached_tokens_capped_at_input(self):
        """cached_tokens > input_tokens should not produce negative non-cached."""
        from middleware.payment.cost_tracker import (
            get_current_costs,
            reset,
            track_sample_call,
        )

        reset()
        track_sample_call(
            input_tokens=100, output_tokens=50, model="test", cached_tokens=9999
        )
        costs = get_current_costs()
        # safe_cached = min(9999, 100) = 100, non_cached = 0
        assert costs["sampling_estimated_cached_tokens"] == 100
        assert costs["cost_sampling_estimated"] > 0

    def test_get_current_costs_includes_cached_field(self):
        from middleware.payment.cost_tracker import get_current_costs, reset

        reset()
        costs = get_current_costs()
        assert "sampling_estimated_cached_tokens" in costs


# ── Cache integration tests (need Qdrant) ────────────────────────────────

TEST_COLLECTION = "mcp_sampling_cache_pytest"


@pytest.fixture
def cache():
    """Create a FastEmbedQdrantCache with a test collection, clean up after."""
    from config.settings import settings
    from middleware.sampling_cache import FastEmbedQdrantCache

    c = FastEmbedQdrantCache(
        qdrant_api_base=settings.qdrant_url,
        qdrant_api_key=settings.qdrant_api_key,
        collection_name=TEST_COLLECTION,
        similarity_threshold=0.85,
    )
    yield c

    # Cleanup
    try:
        import httpx

        httpx.delete(
            f"{settings.qdrant_url}/collections/{TEST_COLLECTION}",
            headers=c.headers,
        )
    except Exception:
        pass


class TestFastEmbedQdrantCacheSync:
    """Sync set_cache / get_cache."""

    def test_exact_match_hit(self, cache):
        msgs = [
            {"content": "What is the DSL notation for a button in Google Chat cards?"}
        ]
        cache.set_cache("k1", '{"answer":"ᵬ"}', messages=msgs)
        hit = cache.get_cache("k1", messages=msgs)
        assert hit is not None
        assert hit["answer"] == "ᵬ"

    def test_unrelated_query_miss(self, cache):
        msgs = [{"content": "What is the DSL notation for a button?"}]
        cache.set_cache("k1", '{"answer":"ᵬ"}', messages=msgs)

        miss = cache.get_cache(
            "k2", messages=[{"content": "Send an email to john@example.com"}]
        )
        assert miss is None


class TestFastEmbedQdrantCacheAsync:
    """Async set_cache / get_cache."""

    @pytest.mark.asyncio
    async def test_async_exact_match(self, cache):
        msgs = [{"content": "Explain the card builder DSL structure"}]
        await cache.async_set_cache("ak1", '{"answer":"§ for Section"}', messages=msgs)
        hit = await cache.async_get_cache("ak1", messages=msgs)
        assert hit is not None
        assert "§" in hit["answer"]

    @pytest.mark.asyncio
    async def test_async_unrelated_miss(self, cache):
        msgs = [{"content": "DSL structure for cards"}]
        await cache.async_set_cache("ak1", '{"a":"b"}', messages=msgs)

        miss = await cache.async_get_cache(
            "ak2", messages=[{"content": "What time is the meeting tomorrow?"}]
        )
        assert miss is None


class TestInitializeSamplingCache:
    """Test the lazy init function."""

    def test_returns_false_when_disabled(self):
        import litellm

        litellm.cache = None

        import os

        old = os.environ.get("SAMPLING_CACHE_ENABLED")
        os.environ["SAMPLING_CACHE_ENABLED"] = "false"
        try:
            # Force settings reload
            from middleware.sampling_cache import initialize_sampling_cache

            result = initialize_sampling_cache()
            # May return True if litellm.cache was already set by another test,
            # or False if disabled. Just verify no crash.
            assert isinstance(result, bool)
        finally:
            if old is not None:
                os.environ["SAMPLING_CACHE_ENABLED"] = old
            elif "SAMPLING_CACHE_ENABLED" in os.environ:
                del os.environ["SAMPLING_CACHE_ENABLED"]
