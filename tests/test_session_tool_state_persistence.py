"""Tests for session tool-state persistence (auth/context.py).

A session-scoped disable is inherited by the next session for the same user,
so the persisted file is what a reconnect reads to decide which tools are off.
That makes one property essential: re-enabling a tool has to be *recordable*.
It was not — a cleared session was skipped when writing, and an all-clear wrote
nothing at all, so `list_gmail_labels` came back disabled after every restart
no matter how many times it was enabled.
"""

import json
from datetime import datetime

import pytest

from auth import context as ctx


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    """Redirect persistence at a temp file and start from an empty store."""
    path = tmp_path / "session_tool_states.json"
    monkeypatch.setattr(ctx, "_get_session_tool_state_path", lambda: path)
    monkeypatch.setattr(ctx, "_session_store", {})
    return path


def _session(disabled=(), email="user@example.com"):
    return {
        "session_disabled_tools": set(disabled),
        "last_accessed": datetime(2026, 8, 25, 12, 0, 0),
        "minimal_startup_applied": False,
        "user_email": email,
    }


def _written(path):
    return json.loads(path.read_text())


class TestClearedStateIsRecordable:
    def test_a_session_with_nothing_disabled_is_still_written(self, state_file):
        """The evidence that a tool was re-enabled must reach disk."""
        ctx._session_store["s1"] = _session(disabled=[])

        assert ctx.persist_session_tool_states() is True

        written = _written(state_file)
        assert "s1" in written
        assert written["s1"]["disabled_tools"] == []

    def test_clearing_the_last_disable_overwrites_the_stale_file(self, state_file):
        """The regression: an all-clear used to leave the old file untouched."""
        state_file.write_text(
            json.dumps(
                {
                    "old": {
                        "disabled_tools": ["list_gmail_labels"],
                        "last_accessed": "2026-08-25T11:00:00",
                        "minimal_startup_applied": False,
                        "user_email": "user@example.com",
                    }
                }
            )
        )
        # The live session had that tool re-enabled.
        ctx._session_store["new"] = _session(disabled=[])

        ctx.persist_session_tool_states()

        written = _written(state_file)
        assert "old" not in written
        assert written["new"]["disabled_tools"] == []

    def test_a_cleared_session_becomes_the_predecessor_that_is_inherited(
        self, state_file
    ):
        """End of the loop: the next reconnect must find the *clean* session."""
        ctx._session_store["dirty"] = _session(disabled=["list_gmail_labels"])
        ctx._session_store["dirty"]["last_accessed"] = datetime(2026, 8, 25, 11, 0, 0)
        ctx._session_store["clean"] = _session(disabled=[])
        ctx._session_store["clean"]["last_accessed"] = datetime(2026, 8, 25, 12, 0, 0)

        ctx.persist_session_tool_states()

        found = ctx.find_session_id_by_email("user@example.com")
        assert found == "clean"
        assert _written(state_file)[found]["disabled_tools"] == []


class TestDisablesStillPersist:
    def test_a_disabled_tool_is_written(self, state_file):
        ctx._session_store["s1"] = _session(disabled=["list_gmail_labels"])

        ctx.persist_session_tool_states()

        assert _written(state_file)["s1"]["disabled_tools"] == ["list_gmail_labels"]

    def test_an_empty_store_does_not_erase_the_file(self, state_file):
        """No live sessions means nothing to say — not 'everything is clear'."""
        state_file.write_text(json.dumps({"old": {"disabled_tools": ["x"]}}))

        assert ctx.persist_session_tool_states() is True

        assert _written(state_file) == {"old": {"disabled_tools": ["x"]}}
