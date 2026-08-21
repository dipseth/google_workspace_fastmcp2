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
        self.clientInfo = _FakeInfo(name, version)


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
    monkeypatch.setattr(cc, "_handshake_params", lambda: None)
    assert cc.client_renders_ui() is True


def test_handshake_without_client_info_is_treated_as_unknown(connect):
    ctx = connect(name="claude-ai", advertises=False)
    ctx.session.client_params.clientInfo = None
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


def test_logged_session_cache_stays_bounded(connect, caplog):
    cc._logged_sessions.update(str(i) for i in range(cc._LOGGED_SESSIONS_CAP))
    connect(name="claude-ai", advertises=False, session_id="fresh")
    cc.client_renders_ui()
    assert len(cc._logged_sessions) <= cc._LOGGED_SESSIONS_CAP
