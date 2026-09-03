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


class TestClientIsRecordedPerSession:
    """Which client drove a session is written next to its tool state.

    Captured once per session by AuthMiddleware.on_initialize under
    SessionKey.CLIENT; the file is how you learn, after the fact, which host
    (and which protocol era / elicitation modes) a given session used.
    """

    RECORD = {
        "name": "claude-code",
        "version": "2.1.258",
        "source": "clientInfo",
        "user_agent": None,
        "protocol_version": "2026-07-28",
        "ui_extension": False,
        "elicitation": [],
        "tasks": False,
        "oauth_client_name": "Claude Code",
        "first_seen": "2026-09-02T15:08:52+00:00",
    }

    def test_client_record_is_written(self, state_file):
        ctx._session_store["s1"] = {**_session(), "client": self.RECORD}

        assert ctx.persist_session_tool_states() is True

        assert _written(state_file)["s1"]["client"] == self.RECORD

    def test_a_session_known_only_by_its_client_is_not_written(self, state_file):
        """Under 2026-07-28 every request is its own session, so a line per
        client-only session would be one identity-less entry per
        server/discover or resources/list. The client rides on sessions with
        identity or state."""
        ctx._session_store["anon"] = {
            "session_disabled_tools": set(),
            "last_accessed": datetime(2026, 9, 2, 8, 0, 0),
            "minimal_startup_applied": False,
            "user_email": None,
            "client": self.RECORD,
        }

        assert ctx.persist_session_tool_states() is True

        assert "anon" not in _written(state_file)

    def test_absent_client_writes_null_not_a_missing_key(self, state_file):
        ctx._session_store["s1"] = _session()

        ctx.persist_session_tool_states()

        assert _written(state_file)["s1"]["client"] is None

    def test_restore_from_previous_session_does_not_inherit_client(self, state_file):
        """A successor session may be a different host; it records its own."""
        state_file.write_text(
            json.dumps(
                {
                    "old": {
                        "disabled_tools": ["list_gmail_labels"],
                        "last_accessed": "2026-09-02T07:00:00",
                        "minimal_startup_applied": False,
                        "user_email": "user@example.com",
                        "client": self.RECORD,
                    }
                }
            )
        )

        assert ctx.restore_session_tool_state_by_email("new", "user@example.com")

        assert "client" not in ctx._session_store["new"]
        assert ctx._session_store["new"]["session_disabled_tools"] == {
            "list_gmail_labels"
        }


def _bare_auth_middleware():
    """An AuthMiddleware with only the state on_request/on_initialize touch."""
    import threading

    from auth.middleware import AuthMiddleware

    m = AuthMiddleware.__new__(AuthMiddleware)
    m._session_lock = threading.Lock()
    m._active_sessions = {}
    m._google_provider = None
    m._github_provider = None
    m._last_cleanup = datetime.now()
    m._cleanup_interval_minutes = 30
    return m


def _request(method="tools/list"):
    from types import SimpleNamespace

    return SimpleNamespace(message=None, method=method, type="request")


async def _call_next(_ctx):
    return ["tools"]


def _visible_handshake(monkeypatch, name="claude-code", version="2.1.258"):
    from types import SimpleNamespace

    from tools import client_capabilities as cc

    params = SimpleNamespace(client_info=SimpleNamespace(name=name, version=version))
    monkeypatch.setattr(cc, "handshake_params", lambda: params)


PREDECESSOR = {
    "old": {
        "disabled_tools": ["list_gmail_labels"],
        "last_accessed": "2026-09-02T07:00:00",
        "minimal_startup_applied": False,
        "user_email": "user@example.com",
        "client": None,
    }
}


class TestRecordingDoesNotWriteBeforeTheRestore:
    """Storing the client record must not touch the file by itself.

    The file is rewritten from the live store, so the first write of a fresh
    process replaces what the previous process left — including the
    predecessor that the tools/list restore looks up by email. Writing from
    the first request (server/discover under 2026-07-28) wiped that history
    and left every session with user_email null and no inherited tool state.
    """

    def test_record_client_once_stores_without_writing(self, state_file, monkeypatch):
        from auth.middleware import AuthMiddleware
        from tools import client_capabilities as cc

        state_file.write_text(json.dumps(PREDECESSOR))
        monkeypatch.setattr(cc, "client_record", lambda: {"name": "claude-code"})

        AuthMiddleware._record_client_once("s1")

        assert ctx._session_store["s1"]["client"] == {
            "name": "claude-code",
            "oauth_client_name": None,
        }
        assert _written(state_file) == PREDECESSOR

    def test_record_client_once_is_idempotent(self, state_file, monkeypatch):
        from auth.middleware import AuthMiddleware
        from tools import client_capabilities as cc

        calls = []
        monkeypatch.setattr(
            cc, "client_record", lambda: calls.append(1) or {"name": "x"}
        )

        AuthMiddleware._record_client_once("s1")
        AuthMiddleware._record_client_once("s1")

        assert len(calls) == 1

    def test_record_client_once_carries_the_oauth_name(self, state_file, monkeypatch):
        """The CIMD client_name is the one human-readable name an OAuth session has."""
        from auth.middleware import AuthMiddleware
        from tools import client_capabilities as cc

        monkeypatch.setattr(cc, "client_record", lambda: {"name": "claude-code"})

        AuthMiddleware._record_client_once("s1", oauth_client_name="Claude Code")

        assert ctx._session_store["s1"]["client"]["oauth_client_name"] == "Claude Code"

    def test_a_ready_record_is_stored_as_given(self, state_file, monkeypatch):
        from auth.middleware import AuthMiddleware
        from tools import client_capabilities as cc

        monkeypatch.setattr(cc, "client_record", lambda: {"name": "wrong"})

        AuthMiddleware._record_client_once("s1", {"name": "claude-code"})

        assert ctx._session_store["s1"]["client"]["name"] == "claude-code"

    async def test_first_requests_of_a_fresh_process_keep_the_predecessor(
        self, state_file, monkeypatch
    ):
        """The regression: the 2026-07-28 opener passes through without a
        session, and the tools/list that follows — its own session under that
        protocol — records the client and must still inherit the predecessor's
        email and disabled tools."""
        state_file.write_text(json.dumps(PREDECESSOR))
        _visible_handshake(monkeypatch)

        monkeypatch.setattr(ctx, "get_session_context_sync", lambda: "discover")
        await _bare_auth_middleware().on_request(
            _request("server/discover"), _call_next
        )
        # server/discover is not a component request: no session, no write.
        assert "discover" not in ctx._session_store
        assert _written(state_file) == PREDECESSOR  # untouched so far

        monkeypatch.setattr(ctx, "get_session_context_sync", lambda: "listing")
        await _bare_auth_middleware().on_request(_request("tools/list"), _call_next)
        assert ctx.restore_session_tool_state_by_email("listing", "user@example.com")

        written = _written(state_file)
        assert written["listing"]["user_email"] == "user@example.com"
        assert written["listing"]["disabled_tools"] == ["list_gmail_labels"]
        assert written["listing"]["client"]["name"] == "claude-code"
        # Identity-less and state-less: not worth a line of its own.
        assert "discover" not in written


class TestAUserWithNoHistoryIsSeeded:
    """A restore that finds no predecessor still writes the session's identity.

    Only sessions with identity or state are written, and the file is
    rewritten from the live store. So a user with nothing on disk — a fresh
    install, or a file a previous process wrote without them — would never
    re-enter it until a manual enable/disable, and every later reconnect
    would keep finding nothing to inherit.
    """

    def test_no_predecessor_seeds_the_email_and_writes(self, state_file):
        assert (
            ctx.restore_session_tool_state_by_email("s1", "user@example.com") is False
        )

        written = _written(state_file)
        assert written["s1"]["user_email"] == "user@example.com"
        assert written["s1"]["disabled_tools"] == []

    def test_the_seeded_session_is_the_next_predecessor(self, state_file):
        ctx.restore_session_tool_state_by_email("s1", "user@example.com")

        assert ctx.find_session_id_by_email("user@example.com") == "s1"

    async def test_seeding_keeps_the_client_recorded_on_that_request(
        self, state_file, monkeypatch
    ):
        """The fix as a user sees it: after a wiped file, the first tools/list
        comes back with both the email and the client."""
        state_file.write_text(json.dumps({}))
        _visible_handshake(monkeypatch)
        monkeypatch.setattr(ctx, "get_session_context_sync", lambda: "listing")

        await _bare_auth_middleware().on_request(_request("tools/list"), _call_next)
        ctx.restore_session_tool_state_by_email("listing", "user@example.com")

        written = _written(state_file)["listing"]
        assert written["user_email"] == "user@example.com"
        assert written["client"]["name"] == "claude-code"


class TestFirstRequestRecordsTheClient:
    """Under MCP 2026-07-28 there is no initialize: every request is
    self-contained, carrying clientInfo in its ``_meta``, so the first request
    of any kind is where the client gets recorded. That is the request a
    connect-and-idle client (Claude Code listing tools) actually sends.
    """

    async def test_a_tools_list_records_a_visible_handshake(
        self, state_file, monkeypatch
    ):
        monkeypatch.setattr(ctx, "get_session_context_sync", lambda: "s1")
        _visible_handshake(monkeypatch)

        result = await _bare_auth_middleware().on_request(_request(), _call_next)

        assert result == ["tools"]
        record = ctx._session_store["s1"]["client"]
        assert record["name"] == "claude-code"
        assert record["version"] == "2.1.258"

    async def test_the_oauth_client_name_rides_along(self, state_file, monkeypatch):
        """The CIMD client_name ("Claude Code") is the human-readable identity."""
        monkeypatch.setattr(ctx, "get_session_context_sync", lambda: "s1")
        _visible_handshake(monkeypatch)
        m = _bare_auth_middleware()
        m._capture_mcp_client_identity = lambda: (
            "https://claude.ai/oauth/claude-code-client-metadata",
            "Claude Code",
        )

        await m.on_request(_request(), _call_next)

        record = ctx._session_store["s1"]["client"]
        assert record["name"] == "claude-code"
        assert record["oauth_client_name"] == "Claude Code"

    async def test_a_request_before_the_handshake_is_readable_waits(
        self, state_file, monkeypatch
    ):
        """A legacy `initialize` commits client_params only after the chain
        returns; recording now would freeze an unnamed client for the session."""
        from tools import client_capabilities as cc

        monkeypatch.setattr(ctx, "get_session_context_sync", lambda: "s1")
        monkeypatch.setattr(cc, "handshake_params", lambda: None)

        await _bare_auth_middleware().on_request(_request("initialize"), _call_next)

        assert "client" not in ctx._session_store.get("s1", {})

    async def test_a_non_session_method_records_nothing(self, state_file, monkeypatch):
        monkeypatch.setattr(ctx, "get_session_context_sync", lambda: "s1")
        _visible_handshake(monkeypatch)

        await _bare_auth_middleware().on_request(_request("ping"), _call_next)

        assert "s1" not in ctx._session_store


class TestInitializeRecordsTheClient:
    """Handshake-era clients open with ``initialize``. The SDK commits
    ``session.client_params`` only after the initialize chain returns, so the
    record has to come from the request itself.
    """

    @staticmethod
    def _handshake(**caps):
        from types import SimpleNamespace

        from mcp import types as mt

        params = mt.InitializeRequestParams(
            protocol_version="2025-11-25",
            capabilities=mt.ClientCapabilities.model_validate(caps),
            client_info=mt.Implementation(name="claude-code", version="2.1.258"),
        )
        message = mt.InitializeRequest(method="initialize", params=params)
        return SimpleNamespace(message=message, method="initialize")

    @staticmethod
    def _result(version="2026-07-28"):
        from mcp import types as mt

        return mt.InitializeResult(
            protocol_version=version,
            capabilities=mt.ServerCapabilities(),
            server_info=mt.Implementation(name="srv", version="1"),
        )

    async def test_initialize_records_the_client(self, state_file, monkeypatch):
        monkeypatch.setattr(ctx, "get_session_context_sync", lambda: "s1")
        result = self._result()

        async def call_next(_ctx):
            return result

        context = self._handshake(
            elicitation={"form": {}}, extensions={"io.modelcontextprotocol/tasks": {}}
        )
        assert await _bare_auth_middleware().on_initialize(context, call_next) is result

        record = ctx._session_store["s1"]["client"]
        assert record["name"] == "claude-code"
        assert record["version"] == "2.1.258"
        assert record["protocol_version"] == "2026-07-28"  # negotiated, not requested
        assert record["elicitation"] == ["form"]
        assert record["tasks"] is True
        assert record["ui_extension"] is False
        assert record["oauth_client_name"] is None

    async def test_initialize_record_is_not_overwritten_by_a_later_tool_call(
        self, state_file, monkeypatch
    ):
        from auth import middleware as mw
        from tools import client_capabilities as cc

        monkeypatch.setattr(ctx, "get_session_context_sync", lambda: "s1")
        monkeypatch.setattr(cc, "client_record", lambda: {"name": "from-session"})

        async def call_next(_ctx):
            return self._result()

        await _bare_auth_middleware().on_initialize(self._handshake(), call_next)
        mw.AuthMiddleware._record_client_once("s1")

        assert ctx._session_store["s1"]["client"]["name"] == "claude-code"

    async def test_initialize_without_a_session_still_returns_the_result(
        self, state_file, monkeypatch
    ):
        monkeypatch.setattr(ctx, "get_session_context_sync", lambda: None)
        result = self._result()

        async def call_next(_ctx):
            return result

        assert (
            await _bare_auth_middleware().on_initialize(self._handshake(), call_next)
            is result
        )
        assert ctx._session_store == {}
