"""Build the FastMCP ``session_state_store`` for this deployment.

One ``AsyncKeyValue`` backs both ``ctx.set_state`` (which writes its own
24-hour TTL) and the per-principal buckets in ``auth/user_state.py`` (which
write no TTL). The store is picked from ``FASTMCP_STATE_STORE``:

- ``redis``  — ``REDIS_IO_URL_STRING``; shared across replicas.
- ``disk``   — a file-tree store under ``credentials_dir/fastmcp-state``;
  survives restarts on single-container deploys (Glama, the prod CT) where
  the retired ``session_tool_states.json`` used to do that job.
- ``memory`` — process-local; tests and throwaway runs.
- ``auto`` (default) — ``redis`` when a Redis URL is configured, else ``disk``.

Every store is wrapped in a ``TTLClampWrapper`` so bucket writes get a
retention ceiling and no write can exceed it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config.enhanced_logging import setup_logger

logger = setup_logger()

STATE_PREFIX = "gw-mcp-state"
MIN_TTL_SECONDS = 60
MAX_TTL_SECONDS = 30 * 24 * 3600
MISSING_TTL_SECONDS = MAX_TTL_SECONDS


def _wrap(store: Any) -> Any:
    from key_value.aio.wrappers.ttl_clamp import TTLClampWrapper

    return TTLClampWrapper(
        key_value=store,
        min_ttl=MIN_TTL_SECONDS,
        max_ttl=MAX_TTL_SECONDS,
        missing_ttl=MISSING_TTL_SECONDS,
    )


def build_state_store(settings: Any) -> tuple[Any, str]:
    """Return ``(store, kind)`` for ``FastMCP(session_state_store=store)``."""
    kind = (getattr(settings, "fastmcp_state_store", "auto") or "auto").lower()
    redis_url = getattr(settings, "redis_io_url_string", None)
    if kind == "auto":
        kind = "redis" if redis_url else "disk"

    if kind == "redis":
        if not redis_url:
            logger.warning(
                "FASTMCP_STATE_STORE=redis but REDIS_IO_URL_STRING is unset; using disk"
            )
            kind = "disk"
        else:
            try:
                from key_value.aio.stores.redis import RedisStore
                from key_value.aio.wrappers.prefix_collections import (
                    PrefixCollectionsWrapper,
                )

                store = PrefixCollectionsWrapper(
                    key_value=RedisStore(url=redis_url), prefix=STATE_PREFIX
                )
                return _wrap(store), "redis"
            except Exception as exc:
                logger.warning(f"Redis state store unavailable ({exc}); using disk")
                kind = "disk"

    if kind == "disk":
        try:
            from key_value.aio.stores.filetree import FileTreeStore

            directory = (
                Path(getattr(settings, "fastmcp_state_dir", "") or "")
                or Path(settings.credentials_dir) / "fastmcp-state"
            )
            directory.mkdir(parents=True, exist_ok=True)
            return _wrap(FileTreeStore(data_directory=directory)), "disk"
        except Exception as exc:
            logger.warning(f"Disk state store unavailable ({exc}); using memory")
            kind = "memory"

    from key_value.aio.stores.memory import MemoryStore

    return _wrap(MemoryStore()), "memory"


def build_test_state_store() -> Any:
    """A fresh in-memory store with the production TTL wrapper, for tests."""
    from key_value.aio.stores.memory import MemoryStore

    return _wrap(MemoryStore())
