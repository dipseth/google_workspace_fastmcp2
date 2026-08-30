"""Deciding whether the connected MCP client can render an app card.

A view spec is worthless to a client that cannot draw it, and it is not free:
the view travels in ``structuredContent``, which some hosts also surface to the
model. Two signals from the client's ``initialize`` handshake answer "can this
client render?", in order of authority:

1. **Capability negotiation** — the client advertised the MCP Apps UI extension
   (``io.modelcontextprotocol/ui``). Protocol-correct, but under-reported: a
   host can render MCP UI without declaring the extension, and FastMCP's own
   ``Client`` is one that does not declare it.
2. **``clientInfo.name``** from the same handshake, matched against an
   allowlist. A heuristic — a client may send whatever name it likes — but this
   decides how many tokens a response spends, not what anyone may access, so a
   wrong guess costs payload rather than granting anything.

Either signal is enough. When the handshake is unavailable at all (background
task, unit test, older FastMCP) the answer is "render", because silently
downgrading a card that works is worse than paying for one that was not needed.

OAuth is deliberately not consulted here. Under dynamic client registration the
``client_id`` is minted per registration rather than per product, so auth
identifies the *user*, not the software they are running.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from config.settings import settings

logger = logging.getLogger(__name__)

# Sessions whose client identity has already been logged, so a long-lived
# connection reports itself once instead of on every tool call. Bounded because
# a long-running server would otherwise accumulate one entry per session.
_logged_sessions: set[str] = set()
_LOGGED_SESSIONS_CAP = 512


@dataclass(frozen=True)
class UISupport:
    """What the initialize handshake says about the client's UI support."""

    name: str | None = None
    version: str | None = None
    advertises_extension: bool = False
    name_allowlisted: bool = False
    handshake_seen: bool = False

    @property
    def renders(self) -> bool:
        """True when either signal says the client can draw a card."""
        return self.advertises_extension or self.name_allowlisted


def _handshake_params():
    """The client's ``initialize`` params, or None outside a live session."""
    try:
        from fastmcp.server.dependencies import get_context

        return get_context().session.client_params
    except Exception:
        return None


def _advertises_ui_extension() -> bool:
    try:
        from fastmcp.apps.config import UI_EXTENSION_ID
        from fastmcp.server.dependencies import get_context

        return bool(get_context().client_supports_extension(UI_EXTENSION_ID))
    except Exception:
        return False


def _name_allowlisted(name: str | None) -> bool:
    """Match ``name`` against the configured allowlist.

    Entries match case-insensitively as substrings, so ``claude-ai`` covers
    ``claude-ai`` and a bare ``claude`` would cover every Claude surface.
    """
    if not name:
        return False
    normalized = name.strip().lower()
    entries = (e.strip().lower() for e in settings.draft_preview_ui_clients.split(","))
    return any(entry and entry in normalized for entry in entries)


def detect_ui_support() -> UISupport:
    """Read the client's UI support from the handshake, ignoring the gate flag.

    Reports what was actually detected, so a diagnostic caller sees the truth
    even when gating is disabled. Use :func:`client_renders_ui` to decide
    whether to build a card.
    """
    params = _handshake_params()
    if params is None:
        return UISupport()

    info = getattr(params, "clientInfo", None)
    name = getattr(info, "name", None)
    version = getattr(info, "version", None)
    support = UISupport(
        name=name,
        version=version,
        advertises_extension=_advertises_ui_extension(),
        name_allowlisted=_name_allowlisted(name),
        handshake_seen=True,
    )
    # Report here rather than from the gate. Switching the gate off is exactly
    # when you need to know what a client calls itself — that is how you get a
    # name for the allowlist — and gating off used to short-circuit before the
    # log line ever ran, leaving no way to find the name but a shell on the
    # server.
    _log_identity_once(support)
    return support


def client_renders_ui() -> bool:
    """True when the connected client should be handed a full app card."""
    # Detect before consulting the flag so the identity is observed either way.
    support = detect_ui_support()

    if not settings.draft_preview_ui_gating:
        return True
    if not support.handshake_seen:
        return True

    return support.renders


def _log_identity_once(support: UISupport) -> None:
    """Report the client's identity once per session.

    The allowlist is a guess until a real client is observed, so this line is
    how you find out what a host actually calls itself.
    """
    try:
        from fastmcp.server.dependencies import get_context

        session_id = str(get_context().session_id)
    except Exception:
        session_id = ""

    if session_id:
        if session_id in _logged_sessions:
            return
        if len(_logged_sessions) >= _LOGGED_SESSIONS_CAP:
            _logged_sessions.clear()
        _logged_sessions.add(session_id)

    gating = settings.draft_preview_ui_gating
    logger.info(
        "[ui-gating] client=%s version=%s advertises_extension=%s allowlisted=%s "
        "gating=%s -> %s",
        support.name or "(unnamed)",
        support.version or "(unknown)",
        support.advertises_extension,
        support.name_allowlisted,
        gating,
        "card" if (support.renders or not gating) else "text-only",
    )
