"""Tests for ConsumedTokenStore (Redis-backed with in-memory fallback)."""

import time
from unittest.mock import AsyncMock, patch

import pytest

from middleware.token_store import ConsumedTokenStore


class TestConsumedTokenStoreMemory:
    """Test in-memory fallback (no Redis)."""

    def setup_method(self):
        self.store = ConsumedTokenStore("test", default_ttl_seconds=60)

    def test_not_consumed_initially(self):
        assert not self.store.is_consumed_sync("tok1")
        assert "tok1" not in self.store

    def test_consume_then_check(self):
        self.store.consume_sync("tok1")
        assert self.store.is_consumed_sync("tok1")
        assert "tok1" in self.store

    def test_add_set_compat(self):
        self.store.add("tok2")
        assert "tok2" in self.store

    def test_ttl_expiry(self):
        self.store.consume_sync("tok3", ttl=1)
        assert self.store.is_consumed_sync("tok3")
        # Simulate time passing
        self.store._memory["tok3"] = time.time() - 2
        assert not self.store.is_consumed_sync("tok3")

    def test_clear(self):
        self.store.consume_sync("tok4")
        self.store.clear()
        assert not self.store.is_consumed_sync("tok4")

    def test_different_namespaces_isolated(self):
        store_a = ConsumedTokenStore("ns-a", default_ttl_seconds=60)
        store_b = ConsumedTokenStore("ns-b", default_ttl_seconds=60)
        store_a.consume_sync("shared_key")
        assert store_a.is_consumed_sync("shared_key")
        assert not store_b.is_consumed_sync("shared_key")


@pytest.mark.asyncio
class TestConsumedTokenStoreAsync:
    """Test async API with mocked Redis."""

    async def test_async_consume_and_check_memory(self):
        store = ConsumedTokenStore("async-test", default_ttl_seconds=60)
        assert not await store.is_consumed("tok1")
        await store.consume("tok1")
        # Memory fallback stores it
        assert store._memory_check("tok1")

    async def test_async_redis_path(self):
        """When Redis is available, uses Redis."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

        store = ConsumedTokenStore("redis-test", default_ttl_seconds=300)
        with patch("middleware.token_store._redis_client", mock_redis):
            assert not await store.is_consumed("tok1")
            mock_redis.get.assert_called_once()

            await store.consume("tok1", ttl=120)
            mock_redis.setex.assert_called_once_with(
                "gw-mcp:tokens:redis-test:tok1", 120, b"1"
            )

    async def test_async_redis_fallback_on_error(self):
        """Falls back to memory when Redis raises."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=ConnectionError("gone"))
        mock_redis.setex = AsyncMock(side_effect=ConnectionError("gone"))

        store = ConsumedTokenStore("fallback-test", default_ttl_seconds=60)
        with patch("middleware.token_store._redis_client", mock_redis):
            await store.consume("tok1")
            assert store._memory_check("tok1")
