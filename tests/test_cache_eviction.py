"""Tests for bounded cache eviction in CacheManager."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from middleware.template_core.cache_manager import CacheManager


class TestCacheEviction:
    """Tests for max_entries enforcement and FIFO eviction."""

    def test_eviction_triggers_at_max_entries(self):
        """Cache evicts oldest entries when max_entries is exceeded."""
        cm = CacheManager(max_entries=3)

        cm.cache_resource("a", "data_a")
        cm.cache_resource("b", "data_b")
        cm.cache_resource("c", "data_c")
        assert len(cm._resource_cache) == 3

        # Adding a 4th entry should evict the oldest (a)
        cm.cache_resource("d", "data_d")
        assert len(cm._resource_cache) == 3
        assert cm.get_cached_resource("a") is None
        assert cm.get_cached_resource("d") == "data_d"

    def test_eviction_preserves_fifo_order(self):
        """Evicted entries are the oldest by insertion order."""
        cm = CacheManager(max_entries=2)

        cm.cache_resource("first", 1)
        cm.cache_resource("second", 2)
        cm.cache_resource("third", 3)

        # 'first' should be evicted, 'second' and 'third' remain
        assert cm.get_cached_resource("first") is None
        assert cm.get_cached_resource("second") == 2
        assert cm.get_cached_resource("third") == 3

    def test_eviction_removes_expired_before_oldest(self):
        """Expired entries are cleaned up before evicting valid ones."""
        cm = CacheManager(max_entries=3, cache_ttl_seconds=1)

        # Insert 3 entries
        cm.cache_resource("old1", "data1")
        cm.cache_resource("old2", "data2")
        cm.cache_resource("valid", "data3")

        # Expire the first two entries by backdating
        past = datetime.now() - timedelta(seconds=10)
        cm._resource_cache["old1"]["expires_at"] = past
        cm._resource_cache["old2"]["expires_at"] = past

        # Adding a new entry should evict expired ones first, keeping 'valid'
        cm.cache_resource("new", "data4")
        assert len(cm._resource_cache) == 2
        assert cm.get_cached_resource("valid") == "data3"
        assert cm.get_cached_resource("new") == "data4"

    def test_overflow_by_multiple_entries(self):
        """Adding many entries beyond capacity evicts enough to stay at max."""
        cm = CacheManager(max_entries=3)

        for i in range(10):
            cm.cache_resource(f"key_{i}", i)

        assert len(cm._resource_cache) == 3
        # The last 3 entries should remain
        assert cm.get_cached_resource("key_7") == 7
        assert cm.get_cached_resource("key_8") == 8
        assert cm.get_cached_resource("key_9") == 9

    def test_update_existing_key_does_not_grow_cache(self):
        """Updating an existing key doesn't increase cache size."""
        cm = CacheManager(max_entries=3)

        cm.cache_resource("a", 1)
        cm.cache_resource("b", 2)
        cm.cache_resource("c", 3)

        # Update existing key
        cm.cache_resource("b", 99)
        assert len(cm._resource_cache) == 3
        assert cm.get_cached_resource("b") == 99


class TestCacheCleanup:
    """Tests for cleanup_expired_entries."""

    def test_cleanup_removes_expired(self):
        """cleanup_expired_entries removes only expired entries."""
        cm = CacheManager(cache_ttl_seconds=1)

        cm.cache_resource("expired", "old")
        cm.cache_resource("valid", "new")

        # Expire one entry
        cm._resource_cache["expired"]["expires_at"] = datetime.now() - timedelta(
            seconds=10
        )

        removed = cm.cleanup_expired_entries()
        assert removed == 1
        assert cm.get_cached_resource("expired") is None
        assert cm.get_cached_resource("valid") == "new"

    def test_cleanup_returns_zero_when_nothing_expired(self):
        """cleanup_expired_entries returns 0 if nothing is expired."""
        cm = CacheManager(cache_ttl_seconds=300)
        cm.cache_resource("a", 1)
        cm.cache_resource("b", 2)

        removed = cm.cleanup_expired_entries()
        assert removed == 0

    def test_cleanup_noop_when_caching_disabled(self):
        """cleanup_expired_entries is a no-op when caching is disabled."""
        cm = CacheManager(enable_caching=False)
        assert cm.cleanup_expired_entries() == 0


class TestCacheTTL:
    """Tests for TTL-based expiration on lookup."""

    def test_expired_entry_returns_none_on_get(self):
        """get_cached_resource returns None and removes expired entry."""
        cm = CacheManager(cache_ttl_seconds=1)
        cm.cache_resource("key", "value")

        # Backdate expiry
        cm._resource_cache["key"]["expires_at"] = datetime.now() - timedelta(seconds=5)

        assert cm.get_cached_resource("key") is None
        assert "key" not in cm._resource_cache

    def test_valid_entry_returns_data(self):
        """get_cached_resource returns data for non-expired entries."""
        cm = CacheManager(cache_ttl_seconds=300)
        cm.cache_resource("key", {"nested": "data"})
        assert cm.get_cached_resource("key") == {"nested": "data"}

    def test_caching_disabled_skips_all_operations(self):
        """When caching is disabled, get and set are no-ops."""
        cm = CacheManager(enable_caching=False)
        cm.cache_resource("key", "value")
        assert cm.get_cached_resource("key") is None
        assert len(cm._resource_cache) == 0
