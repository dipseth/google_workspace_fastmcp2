"""Redis-backed consumed token store with in-memory fallback.

Provides one-time-use token tracking for payment flow and email feedback.
Uses Redis ``SETEX`` when available, falls back to an in-memory set.

Usage::

    from middleware.token_store import ConsumedTokenStore

    store = ConsumedTokenStore("payment", default_ttl_seconds=900)
    if store.is_consumed_sync("token123"):
        ...  # already used
    store.consume_sync("token123")
"""

from __future__ import annotations

import time
from typing import Any, Optional

from config.enhanced_logging import setup_logger

logger = setup_logger()

# Module-level Redis client — shared across all stores
_redis_client: Optional[Any] = None


def set_redis_client(client: Any) -> None:
    """Set the shared Redis client for all ConsumedTokenStore instances."""
    global _redis_client
    _redis_client = client
    logger.info("Token store: Redis client configured")


class ConsumedTokenStore:
    """One-time-use token tracker backed by Redis with in-memory fallback.

    Args:
        namespace: Key namespace (e.g. ``"payment"``, ``"email-feedback"``).
        default_ttl_seconds: Default TTL for consumed tokens.
    """

    def __init__(self, namespace: str, default_ttl_seconds: int = 900):
        self._namespace = namespace
        self._default_ttl = default_ttl_seconds
        # In-memory fallback: maps token_key -> expiry timestamp
        self._memory: dict[str, float] = {}

    def _redis_key(self, token_key: str) -> str:
        return f"gw-mcp:tokens:{self._namespace}:{token_key}"

    # ── Async API ─────────────────────────────────────────────────────

    async def is_consumed(self, token_key: str) -> bool:
        """Check if a token has been consumed (async, Redis-first)."""
        if _redis_client is not None:
            try:
                result = await _redis_client.get(self._redis_key(token_key))
                if result is not None:
                    return True
            except Exception as e:
                logger.debug("Redis get failed, falling back to memory: %s", e)
        return self._memory_check(token_key)

    async def consume(self, token_key: str, ttl: int | None = None) -> None:
        """Mark a token as consumed (async, Redis-first)."""
        ttl = ttl or self._default_ttl
        if _redis_client is not None:
            try:
                await _redis_client.setex(self._redis_key(token_key), ttl, b"1")
                return
            except Exception as e:
                logger.debug("Redis setex failed, falling back to memory: %s", e)
        self._memory_consume(token_key, ttl)

    # ── Sync API (for current sync verify functions) ──────────────────

    def is_consumed_sync(self, token_key: str) -> bool:
        """Check if a token has been consumed (sync, memory-only)."""
        if _redis_client is not None:
            try:
                import asyncio

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Can't block — use memory fallback
                    pass
                else:
                    return loop.run_until_complete(self.is_consumed(token_key))
            except RuntimeError:
                pass
        return self._memory_check(token_key)

    def consume_sync(self, token_key: str, ttl: int | None = None) -> None:
        """Mark a token as consumed (sync, memory-only)."""
        ttl = ttl or self._default_ttl
        if _redis_client is not None:
            try:
                import asyncio

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    pass
                else:
                    loop.run_until_complete(self.consume(token_key, ttl))
                    return
            except RuntimeError:
                pass
        self._memory_consume(token_key, ttl)

    # ── In-memory implementation ──────────────────────────────────────

    def _memory_check(self, token_key: str) -> bool:
        """Check in-memory store, evicting expired entries."""
        exp = self._memory.get(token_key)
        if exp is None:
            return False
        if time.time() > exp:
            del self._memory[token_key]
            return False
        return True

    def _memory_consume(self, token_key: str, ttl: int) -> None:
        """Store in memory with expiry timestamp."""
        self._memory[token_key] = time.time() + ttl

    def __contains__(self, token_key: str) -> bool:
        """Support ``token_key in store`` syntax (sync, memory-only)."""
        return self.is_consumed_sync(token_key)

    def add(self, token_key: str) -> None:
        """Support ``store.add(token_key)`` syntax (sync, memory-only)."""
        self.consume_sync(token_key)

    def clear(self) -> None:
        """Clear all consumed tokens (for testing)."""
        self._memory.clear()


__all__ = ["ConsumedTokenStore", "set_redis_client"]
