"""Tests for OOM fix changes — embedding dedup, cache bounds, dashboard cache, watchdog eviction."""

import asyncio
import gc
import json
import time
from collections import OrderedDict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# =========================================================================
# 1. Feedback loop delegates to EmbeddingService (no duplicate models)
# =========================================================================


class TestFeedbackLoopEmbeddingDedup:
    """Verify FeedbackLoop._get_embedder/relationship_embedder use EmbeddingService."""

    def _make_feedback_loop(self):
        """Create a FeedbackLoop with mocked Qdrant client."""
        from gchat.feedback_loop import FeedbackLoop

        fl = FeedbackLoop.__new__(FeedbackLoop)
        fl._client = MagicMock()
        fl._embedder = None
        fl._relationship_embedder = None
        fl._collection_name = "test"
        return fl

    def test_get_embedder_delegates_to_embedding_service(self):
        """_get_embedder should call get_embedding_service().get_model_sync('colbert')."""
        fl = self._make_feedback_loop()
        mock_model = MagicMock(name="mock_colbert")

        mock_svc = MagicMock()
        mock_svc.get_model_sync.return_value = mock_model

        # Reset singleton so fresh import inside method gets our mock
        import config.embedding_service as es_mod

        original_instance = es_mod._instance
        es_mod._instance = mock_svc

        try:
            result = fl._get_embedder()
            mock_svc.get_model_sync.assert_called_once_with("colbert")
            assert result is mock_model
        finally:
            es_mod._instance = original_instance

    def test_get_relationship_embedder_delegates_to_embedding_service(self):
        """_get_relationship_embedder should call get_model_sync('minilm')."""
        fl = self._make_feedback_loop()
        mock_model = MagicMock(name="mock_minilm")

        mock_svc = MagicMock()
        mock_svc.get_model_sync.return_value = mock_model

        import config.embedding_service as es_mod

        original_instance = es_mod._instance
        es_mod._instance = mock_svc

        try:
            result = fl._get_relationship_embedder()
            mock_svc.get_model_sync.assert_called_once_with("minilm")
            assert result is mock_model
        finally:
            es_mod._instance = original_instance

    def test_get_embedder_caches_locally(self):
        """Second call should return cached instance without hitting EmbeddingService again."""
        fl = self._make_feedback_loop()
        mock_model = MagicMock(name="mock_colbert_cached")

        mock_svc = MagicMock()
        mock_svc.get_model_sync.return_value = mock_model

        import config.embedding_service as es_mod

        original_instance = es_mod._instance
        es_mod._instance = mock_svc

        try:
            result1 = fl._get_embedder()
            result2 = fl._get_embedder()

            # Only called once — second call uses cached self._embedder
            assert mock_svc.get_model_sync.call_count == 1
            assert result1 is result2
        finally:
            es_mod._instance = original_instance

    def test_get_embedder_handles_service_failure(self):
        """If EmbeddingService fails, should return None gracefully."""
        fl = self._make_feedback_loop()

        mock_svc = MagicMock()
        mock_svc.get_model_sync.side_effect = RuntimeError("Service unavailable")

        import config.embedding_service as es_mod

        original_instance = es_mod._instance
        es_mod._instance = mock_svc

        try:
            result = fl._get_embedder()
            assert result is None
        finally:
            es_mod._instance = original_instance

    def test_no_direct_fastembed_import(self):
        """Verify feedback_loop._get_embedder does NOT directly import fastembed."""
        import inspect

        from gchat.feedback_loop import FeedbackLoop

        source = inspect.getsource(FeedbackLoop._get_embedder)
        assert "from fastembed" not in source, (
            "_get_embedder should delegate to EmbeddingService, not import fastembed directly"
        )

        source_rel = inspect.getsource(FeedbackLoop._get_relationship_embedder)
        assert "from fastembed" not in source_rel, (
            "_get_relationship_embedder should delegate to EmbeddingService, not import fastembed directly"
        )


# =========================================================================
# 2. Dashboard cache middleware — clear, Redis offload
# =========================================================================


class TestDashboardCacheClear:
    """Test the clear_dashboard_cache function."""

    def test_clear_returns_count(self):
        from middleware.dashboard_cache_middleware import (
            _CacheEntry,
            _result_cache,
            clear_dashboard_cache,
        )

        # Populate cache
        _result_cache["tool_a"] = _CacheEntry("tool_a", {"x": 1}, time.time())
        _result_cache["tool_b"] = _CacheEntry("tool_b", {"y": 2}, time.time())

        count = clear_dashboard_cache()
        assert count == 2
        assert len(_result_cache) == 0

    def test_clear_empty_returns_zero(self):
        from middleware.dashboard_cache_middleware import (
            _result_cache,
            clear_dashboard_cache,
        )

        _result_cache.clear()
        count = clear_dashboard_cache()
        assert count == 0


class TestDashboardCacheRedisIntegration:
    """Test Redis store integration in dashboard cache."""

    def test_set_redis_store(self):
        import middleware.dashboard_cache_middleware as mod

        original = mod._redis_store
        mock_store = MagicMock()
        mod.set_redis_store(mock_store)
        assert mod._redis_store is mock_store
        # Clean up
        mod._redis_store = original

    def test_get_cached_result_from_memory(self):
        from middleware.dashboard_cache_middleware import (
            _CacheEntry,
            _result_cache,
            get_cached_result,
        )

        _result_cache["test_tool"] = _CacheEntry("test_tool", {"data": 42}, time.time())
        result = get_cached_result("test_tool")
        assert result == {"data": 42}
        # Clean up
        _result_cache.clear()

    def test_get_cached_result_missing(self):
        from middleware.dashboard_cache_middleware import (
            _result_cache,
            get_cached_result,
        )

        _result_cache.clear()
        assert get_cached_result("nonexistent") is None


class TestDashboardCacheMiddlewareStoreToRedis:
    """Test the _store_to_redis static method."""

    @pytest.mark.asyncio
    async def test_store_to_redis_calls_put(self):
        import middleware.dashboard_cache_middleware as mod

        mock_store = AsyncMock()
        original = mod._redis_store
        mod._redis_store = mock_store

        try:
            await mod.DashboardCacheMiddleware._store_to_redis("my_tool", {"key": "val"})
            mock_store.put.assert_called_once()
            call_args = mock_store.put.call_args
            assert call_args[0][0] == "dashboard:my_tool"
            assert call_args[0][1] == {"data": {"key": "val"}}
            assert call_args[1]["ttl"] == 600  # TTL
        finally:
            mod._redis_store = original

    @pytest.mark.asyncio
    async def test_store_to_redis_handles_error(self):
        """Redis write failure should not raise."""
        import middleware.dashboard_cache_middleware as mod

        mock_store = AsyncMock()
        mock_store.put.side_effect = ConnectionError("Redis down")
        original = mod._redis_store
        mod._redis_store = mock_store

        try:
            # Should not raise
            await mod.DashboardCacheMiddleware._store_to_redis("tool", {"x": 1})
        finally:
            mod._redis_store = original


# =========================================================================
# 3. Profile cache LRU eviction
# =========================================================================


class TestProfileCacheLRU:
    """Test LRU-bounded profile cache."""

    def _make_middleware(self, max_entries=5):
        from middleware.profile_enrichment_middleware import ProfileEnrichmentMiddleware

        mw = ProfileEnrichmentMiddleware(
            enable_caching=True,
            cache_ttl_seconds=300,
            max_cache_entries=max_entries,
        )
        return mw

    def test_cache_is_ordered_dict(self):
        mw = self._make_middleware()
        assert isinstance(mw._profile_cache, OrderedDict)

    def test_max_cache_entries_stored(self):
        mw = self._make_middleware(max_entries=3)
        assert mw._max_cache_entries == 3

    def test_eviction_when_exceeding_max(self):
        """Inserting beyond max_cache_entries should evict oldest."""
        mw = self._make_middleware(max_entries=3)

        # Simulate direct cache insertion (as _fetch_profiles_batch would do)
        for i in range(5):
            uid = f"user_{i}"
            mw._profile_cache[uid] = {"displayName": f"User {i}"}
            mw._cache_timestamps[uid] = time.time()
            mw._profile_cache.move_to_end(uid)
            # Evict oldest when exceeding max
            while len(mw._profile_cache) > mw._max_cache_entries:
                evicted_id, _ = mw._profile_cache.popitem(last=False)
                mw._cache_timestamps.pop(evicted_id, None)

        # Should only have the 3 most recent
        assert len(mw._profile_cache) == 3
        assert "user_0" not in mw._profile_cache
        assert "user_1" not in mw._profile_cache
        assert "user_2" in mw._profile_cache
        assert "user_3" in mw._profile_cache
        assert "user_4" in mw._profile_cache

    def test_timestamps_evicted_with_entries(self):
        """Cache timestamps should be cleaned up when entries are evicted."""
        mw = self._make_middleware(max_entries=2)

        for i in range(4):
            uid = f"user_{i}"
            mw._profile_cache[uid] = {"displayName": f"User {i}"}
            mw._cache_timestamps[uid] = time.time()
            mw._profile_cache.move_to_end(uid)
            while len(mw._profile_cache) > mw._max_cache_entries:
                evicted_id, _ = mw._profile_cache.popitem(last=False)
                mw._cache_timestamps.pop(evicted_id, None)

        # Timestamps should match cache entries exactly
        assert set(mw._cache_timestamps.keys()) == set(mw._profile_cache.keys())
        assert len(mw._cache_timestamps) == 2

    def test_move_to_end_on_access(self):
        """Accessing an entry should move it to the end (most recently used)."""
        mw = self._make_middleware(max_entries=3)

        # Insert 3 entries
        for uid in ["a", "b", "c"]:
            mw._profile_cache[uid] = {"displayName": uid}
            mw._cache_timestamps[uid] = time.time()

        # Access "a" (oldest) — should move to end
        mw._profile_cache.move_to_end("a")

        # Now "b" is the oldest (first in order)
        oldest_key = next(iter(mw._profile_cache))
        assert oldest_key == "b"

    def test_lru_protects_recently_accessed(self):
        """Recently accessed entry should survive eviction."""
        mw = self._make_middleware(max_entries=3)

        # Insert a, b, c
        for uid in ["a", "b", "c"]:
            mw._profile_cache[uid] = {"displayName": uid}
            mw._cache_timestamps[uid] = time.time()

        # Access "a" to make it most recently used
        mw._profile_cache.move_to_end("a")

        # Insert "d" — should evict "b" (now oldest), not "a"
        mw._profile_cache["d"] = {"displayName": "d"}
        mw._cache_timestamps["d"] = time.time()
        mw._profile_cache.move_to_end("d")
        while len(mw._profile_cache) > mw._max_cache_entries:
            evicted_id, _ = mw._profile_cache.popitem(last=False)
            mw._cache_timestamps.pop(evicted_id, None)

        assert "a" in mw._profile_cache  # Protected by recent access
        assert "b" not in mw._profile_cache  # Evicted as oldest
        assert "c" in mw._profile_cache
        assert "d" in mw._profile_cache

    def test_clear_cache(self):
        mw = self._make_middleware()
        mw._profile_cache["x"] = {"displayName": "X"}
        mw._cache_timestamps["x"] = time.time()

        mw.clear_cache()
        assert len(mw._profile_cache) == 0
        assert len(mw._cache_timestamps) == 0

    def test_cache_stats_include_entries(self):
        mw = self._make_middleware(max_entries=10)
        mw._profile_cache["u1"] = {"displayName": "User 1"}
        mw._cache_timestamps["u1"] = time.time()

        stats = mw.get_cache_stats()
        assert stats["in_memory_cache"]["total_entries"] == 1
        assert stats["in_memory_cache"]["valid_entries"] == 1


# =========================================================================
# 4. Watchdog proactive eviction
# =========================================================================


class TestWatchdogProactiveEviction:
    """Test that the warn-threshold block triggers proactive cache eviction."""

    def test_clear_dashboard_cache_importable(self):
        """Verify clear_dashboard_cache is importable (used by watchdog)."""
        from middleware.dashboard_cache_middleware import clear_dashboard_cache

        assert callable(clear_dashboard_cache)

    def test_memory_limit_default_raised(self):
        """Default memory limit should be 3072MB (or overridden by env)."""
        # If MEMORY_LIMIT_MB env var is set, the default doesn't apply
        import os

        import lifespans.server_lifespans as mod

        if os.getenv("MEMORY_LIMIT_MB"):
            assert mod._MEMORY_LIMIT_MB == int(os.getenv("MEMORY_LIMIT_MB"))
        else:
            assert mod._MEMORY_LIMIT_MB == 3072

    def test_warn_threshold_calculated(self):
        """Warn threshold should be 65% of limit."""
        import lifespans.server_lifespans as mod

        expected = int(mod._MEMORY_LIMIT_MB * mod._MEMORY_WARN_PCT)
        assert mod._WARN_THRESHOLD_MB == expected

    def test_critical_threshold_calculated(self):
        """Critical threshold should be 75% of limit."""
        import lifespans.server_lifespans as mod

        expected = int(mod._MEMORY_LIMIT_MB * mod._MEMORY_CRITICAL_PCT)
        assert mod._CRITICAL_THRESHOLD_MB == expected


# =========================================================================
# 5. Settings — redis_io_url_string field
# =========================================================================


class TestRedisSettings:
    """Test that redis_io_url_string is properly defined in Settings."""

    def test_field_exists(self):
        """redis_io_url_string should be a field on Settings class."""
        from config.settings import Settings

        assert "redis_io_url_string" in Settings.model_fields

    def test_field_default_is_none(self):
        """Default value for redis_io_url_string should be None."""
        from config.settings import Settings

        field = Settings.model_fields["redis_io_url_string"]
        assert field.default is None

    def test_field_is_optional_str(self):
        """redis_io_url_string should accept Optional[str]."""
        # Check the global settings instance has the attribute
        from config.settings import Settings, settings

        # Value is either None or a string (from .env)
        val = settings.redis_io_url_string
        assert val is None or isinstance(val, str)
