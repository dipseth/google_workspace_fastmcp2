"""Tests for GitHub user cache TTL eviction."""

import time
from unittest.mock import patch

from auth.github_provider import _TTLDict


class TestTTLDict:
    """Test _TTLDict evict-on-read behavior."""

    def test_set_and_get(self):
        d = _TTLDict(ttl_seconds=3600)
        d["key1"] = {"login": "alice"}
        assert d.get("key1") == {"login": "alice"}

    def test_contains(self):
        d = _TTLDict(ttl_seconds=3600)
        d["key1"] = {"login": "alice"}
        assert "key1" in d
        assert "key2" not in d

    def test_get_default(self):
        d = _TTLDict(ttl_seconds=3600)
        assert d.get("missing") is None
        assert d.get("missing", "fallback") == "fallback"

    def test_eviction_after_ttl(self):
        d = _TTLDict(ttl_seconds=3600)
        d["key1"] = {"login": "alice"}
        # Simulate time passing beyond TTL
        d._data["key1"] = (time.time() - 3601, {"login": "alice"})
        assert d.get("key1") is None
        assert "key1" not in d
        # Entry should be deleted from internal data
        assert "key1" not in d._data

    def test_not_evicted_within_ttl(self):
        d = _TTLDict(ttl_seconds=3600)
        d["key1"] = {"login": "alice"}
        # Simulate time just within TTL
        d._data["key1"] = (time.time() - 3599, {"login": "alice"})
        assert d.get("key1") == {"login": "alice"}

    def test_overwrite_resets_timestamp(self):
        d = _TTLDict(ttl_seconds=3600)
        d["key1"] = {"v": 1}
        # Expire it
        d._data["key1"] = (time.time() - 3601, {"v": 1})
        # Overwrite
        d["key1"] = {"v": 2}
        assert d.get("key1") == {"v": 2}
