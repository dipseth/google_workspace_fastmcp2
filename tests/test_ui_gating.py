"""Tests for client UI-capability gating (tools/client_capabilities.py).

The gate decides whether a tool spends the tokens to build an app card, so the
cases that matter are the ones where the two detection signals disagree: a
client that renders but never advertised the extension, and a client that
advertised nothing and is unknown.
"""

import logging
import types

import pytest

from config.settings import settings
from tools import client_capabilities as cc


class _FakeInfo:
    def __init__(self, name, version="1.0.0"):
        self.name = name
        self.version = version


class _FakeParams:
    def __init__(self, name, version="1.0.0"):
        self.client_info = _FakeInfo(name, version)


class _FakeSession:
    def __init__(self, params):
        self.client_params = params


class _FakeContext:
    def __init__(self, name, advertises, session_id="sess-1", version="1.0.0"):
        self.session = _FakeSession(_FakeParams(name, version) if name else None)
        self._advertises = advertises
        self.session_id = session_id

    def client_supports_extension(self, _extension_id):
        return self._advertises


@pytest.fixture
def connect(monkeypatch):
    """Install a fake client handshake for the duration of a test."""

    def _connect(name="unknown-client", advertises=False, session_id="sess-1"):
        ctx = _FakeContext(name, advertises, session_id)
        fake_module = types.SimpleNamespace(get_context=lambda: ctx)
        monkeypatch.setitem(
            __import__("sys").modules, "fastmcp.server.dependencies", fake_module
        )
        return ctx

    return _connect


@pytest.fixture(autouse=True)
def _gating_on(monkeypatch):
    monkeypatch.setattr(settings, "draft_preview_ui_gating", True)
    monkeypatch.setattr(
        settings, "draft_preview_ui_clients", "claude-ai,claudeai,claude-desktop"
    )
    cc._logged_sessions.clear()


# ── the two detection signals ──────────────────────────────────────


def test_advertised_extension_renders_card(connect):
    connect(name="some-unknown-host", advertises=True)
    assert cc.client_renders_ui() is True


def test_allowlisted_name_renders_without_advertising(connect):
    """The case that kept this flag off: renders, never advertised."""
    connect(name="claude-ai", advertises=False)
    assert cc.client_renders_ui() is True


def test_unknown_and_silent_client_gets_text(connect):
    connect(name="some-batch-script", advertises=False)
    assert cc.client_renders_ui() is False


def test_allowlist_matches_case_insensitively_as_substring(connect):
    connect(name="Claude-AI Desktop/2.1", advertises=False)
    assert cc.client_renders_ui() is True


def test_allowlist_is_configurable(connect, monkeypatch):
    connect(name="my-custom-host", advertises=False)
    assert cc.client_renders_ui() is False
    monkeypatch.setattr(settings, "draft_preview_ui_clients", "my-custom-host")
    assert cc.client_renders_ui() is True


# ── fail-open behaviour ────────────────────────────────────────────


def test_gating_disabled_always_renders(connect, monkeypatch):
    connect(name="some-batch-script", advertises=False)
    monkeypatch.setattr(settings, "draft_preview_ui_gating", False)
    assert cc.client_renders_ui() is True


def test_missing_handshake_renders_rather_than_downgrading(monkeypatch):
    """No session (background task, older FastMCP) must not strip a card."""
    monkeypatch.setattr(cc, "handshake_params", lambda: None)
    assert cc.client_renders_ui() is True


def test_handshake_without_client_info_is_treated_as_unknown(connect):
    ctx = connect(name="claude-ai", advertises=False)
    ctx.session.client_params.client_info = None
    support = cc.detect_ui_support()
    assert support.handshake_seen is True
    assert support.renders is False


# ── diagnostics ────────────────────────────────────────────────────


def test_detect_reports_raw_signals_ignoring_the_flag(connect, monkeypatch):
    connect(name="claude-ai", advertises=False)
    monkeypatch.setattr(settings, "draft_preview_ui_gating", False)
    support = cc.detect_ui_support()
    assert support.name == "claude-ai"
    assert support.advertises_extension is False
    assert support.name_allowlisted is True
    assert support.renders is True


def test_client_identity_is_logged_once_per_session(connect, caplog):
    connect(name="claude-ai", advertises=False, session_id="sess-abc")
    with caplog.at_level(logging.INFO, logger=cc.__name__):
        cc.client_renders_ui()
        cc.client_renders_ui()
    lines = [r for r in caplog.records if "[ui-gating]" in r.getMessage()]
    assert len(lines) == 1
    assert "claude-ai" in lines[0].getMessage()


def test_identity_is_logged_even_with_gating_disabled(connect, caplog, monkeypatch):
    """Turning the gate off must not take the telemetry with it.

    The allowlist is populated from this log line, so a run with gating off —
    the state you switch to *because* a client was wrongly downgraded — is the
    one that most needs to report what the client calls itself.
    """
    connect(name="some-unknown-host", advertises=False, session_id="sess-off")
    monkeypatch.setattr(settings, "draft_preview_ui_gating", False)
    with caplog.at_level(logging.INFO, logger=cc.__name__):
        assert cc.client_renders_ui() is True
    lines = [r.getMessage() for r in caplog.records if "[ui-gating]" in r.getMessage()]
    assert len(lines) == 1
    assert "some-unknown-host" in lines[0]
    assert "gating=False" in lines[0]


def test_logged_session_cache_stays_bounded(connect, caplog):
    cc._logged_sessions.update(str(i) for i in range(cc._LOGGED_SESSIONS_CAP))
    connect(name="claude-ai", advertises=False, session_id="fresh")
    cc.client_renders_ui()
    assert len(cc._logged_sessions) <= cc._LOGGED_SESSIONS_CAP


# ── inside a background-task worker (SEP-2663) ─────────────────────
#
# A worker restores the submitting request's HTTP headers and auth token but
# never its `initialize` params, so the handshake is unreachable there. Once
# `execute` is task-capable this is the path every tasked block takes.


@pytest.fixture
def in_worker(monkeypatch):
    """Simulate a task worker: no handshake, optional User-Agent."""

    def _worker(user_agent=None):
        monkeypatch.setattr(cc, "handshake_params", lambda: None)
        monkeypatch.setattr(cc, "_in_background_task", lambda: True)
        monkeypatch.setattr(cc, "_header_identity", lambda: user_agent)

    return _worker


def test_worker_with_no_identity_gets_text(in_worker):
    """The in-memory transport sends no headers: unknown must resolve to text."""
    in_worker(user_agent=None)
    assert cc.client_renders_ui() is False


def test_worker_identified_by_allowlisted_user_agent_renders(in_worker):
    in_worker(user_agent="Claude-AI Desktop/2.1")
    assert cc.client_renders_ui() is True


def test_worker_with_unknown_user_agent_gets_text(in_worker):
    in_worker(user_agent="python-httpx/0.27")
    assert cc.client_renders_ui() is False


def test_worker_reports_header_provenance(in_worker):
    in_worker(user_agent="claude-ai/1.0")
    support = cc.detect_ui_support()
    assert support.in_task is True
    assert support.via_headers is True
    assert support.handshake_seen is False
    assert support.name == "claude-ai/1.0"


def test_worker_gating_disabled_still_renders(in_worker, monkeypatch):
    """Fail-open must survive the worker path too."""
    in_worker(user_agent=None)
    monkeypatch.setattr(settings, "draft_preview_ui_gating", False)
    assert cc.client_renders_ui() is True


def test_no_session_outside_a_worker_still_renders(monkeypatch):
    """The pre-existing default is untouched when we are not in a task."""
    monkeypatch.setattr(cc, "handshake_params", lambda: None)
    monkeypatch.setattr(cc, "_in_background_task", lambda: False)
    assert cc.client_renders_ui() is True


# ── client_record(): what gets persisted per session ───────────────


def test_client_record_from_handshake(connect):
    connect(name="Claude-AI Desktop/2.1", advertises=True)
    rec = cc.client_record()
    assert rec["name"] == "Claude-AI Desktop/2.1"
    assert rec["version"] == "1.0.0"
    assert rec["source"] == "clientInfo"
    assert rec["ui_extension"] is True
    # The fake session declares no capabilities: unknown, not wrong.
    assert rec["protocol_version"] is None
    assert rec["elicitation"] == []
    assert rec["tasks"] is None
    assert rec["first_seen"]


def test_client_record_from_worker_identifies_by_user_agent(in_worker):
    in_worker(user_agent="python-httpx2/2.12.0")
    rec = cc.client_record()
    assert rec["source"] == "user-agent"
    assert rec["name"] == "python-httpx2/2.12.0"
    assert rec["ui_extension"] is False


def test_client_record_is_json_serializable(connect):
    import json

    connect(name="some-host", advertises=False)
    json.dumps(cc.client_record())  # must not raise


# ── client_record_from_handshake(): the initialize-time record ─────


class _FakeCaps:
    def __init__(self, extensions=None, elicitation=None, tasks=None):
        self.extensions = extensions
        self.elicitation = elicitation
        self.tasks = tasks


class _FakeHandshake:
    def __init__(
        self,
        name="claude-code",
        version="2.1.258",
        protocol_version="2025-11-25",
        capabilities=None,
    ):
        self.client_info = _FakeInfo(name, version)
        self.protocol_version = protocol_version
        self.capabilities = capabilities or _FakeCaps()


def test_handshake_record_reads_the_request_not_the_session(monkeypatch):
    """At initialize the SDK has not committed client_params; the request is all there is."""
    monkeypatch.setattr(cc, "handshake_params", lambda: None)

    rec = cc.client_record_from_handshake(
        _FakeHandshake(name="claude-code"), negotiated_version="2026-07-28"
    )

    assert rec["name"] == "claude-code"
    assert rec["version"] == "2.1.258"
    assert rec["source"] == "clientInfo"
    assert rec["protocol_version"] == "2026-07-28"  # negotiated beats requested


def test_handshake_record_falls_back_to_the_requested_version():
    rec = cc.client_record_from_handshake(_FakeHandshake(protocol_version="2025-06-18"))
    assert rec["protocol_version"] == "2025-06-18"


def test_handshake_record_reads_extensions_and_elicitation():
    caps = _FakeCaps(
        extensions={
            "io.modelcontextprotocol/ui": {},
            "io.modelcontextprotocol/tasks": {},
        },
        elicitation=types.SimpleNamespace(form={}, url=None),
    )
    rec = cc.client_record_from_handshake(_FakeHandshake(capabilities=caps))
    assert rec["ui_extension"] is True
    assert rec["tasks"] is True
    assert rec["elicitation"] == ["form"]


def test_bare_elicitation_declaration_means_form_mode():
    """Claude Code sends ``elicitation: {}`` — the pre-2025-11-25 shape — and
    must not be recorded as a client with no elicitation at all."""
    caps = _FakeCaps(elicitation=types.SimpleNamespace(form=None, url=None))
    rec = cc.client_record_from_handshake(_FakeHandshake(capabilities=caps))
    assert rec["elicitation"] == ["form"]


def test_no_elicitation_declaration_means_no_modes():
    rec = cc.client_record_from_handshake(
        _FakeHandshake(capabilities=_FakeCaps(elicitation=None))
    )
    assert rec["elicitation"] == []


def test_handshake_record_reads_the_core_tasks_capability():
    """2026-07-28 moved tasks into ClientCapabilities proper."""
    rec = cc.client_record_from_handshake(
        _FakeHandshake(capabilities=_FakeCaps(tasks=object()))
    )
    assert rec["tasks"] is True


def test_handshake_record_reads_legacy_extra_extensions():
    """Older clients serialized ``extensions`` as an extra key."""
    caps = types.SimpleNamespace(
        extensions=None,
        model_extra={"extensions": {"io.modelcontextprotocol/ui": {}}},
        elicitation=None,
    )
    rec = cc.client_record_from_handshake(_FakeHandshake(capabilities=caps))
    assert rec["ui_extension"] is True


def test_handshake_record_is_json_serializable():
    import json

    json.dumps(cc.client_record_from_handshake(_FakeHandshake()))  # must not raise
