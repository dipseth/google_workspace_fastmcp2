"""Deciding whether the connected MCP client can render an app card.

A view spec is worthless to a client that cannot draw it, and it is not free:
the view travels in ``structuredContent``, which some hosts also surface to the
model. Two signals from the client's ``initialize`` handshake answer "can this
client render?", in order of authority:

1. **Capability negotiation** — the client advertised the MCP Apps UI extension
   (``io.modelcontextprotocol/ui``). Protocol-correct, but under-reported: a
   host can render MCP UI without declaring the extension, and FastMCP's own
   ``Client`` is one that does not declare it.
2. **``client_info.name``** from the same handshake, matched against an
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
    #: True when this call runs in a background-task worker (SEP-2663). The
    #: worker restores HTTP headers and the auth token, never the handshake.
    in_task: bool = False
    #: True when ``name`` came from the ``User-Agent`` header rather than the
    #: handshake's ``clientInfo`` — the only identity a worker can see.
    via_headers: bool = False

    @property
    def renders(self) -> bool:
        """True when either signal says the client can draw a card."""
        return self.advertises_extension or self.name_allowlisted


def handshake_params():
    """The client's ``initialize`` params, or None outside a live session."""
    try:
        from fastmcp.server.dependencies import get_context

        return get_context().session.client_params
    except Exception:
        return None


def _in_background_task() -> bool:
    """True inside a SEP-2663 task worker, where no handshake is reachable."""
    try:
        from fastmcp.server.dependencies import get_context

        return bool(get_context().is_background_task)
    except Exception:
        return False


def _header_identity() -> str | None:
    """The client's ``User-Agent``, the one identity a task worker restores.

    The task snapshot carries the submitting request's HTTP headers and auth
    token but not its ``initialize`` params, so ``clientInfo`` is gone by the
    time a worker runs. A real HTTP client still names itself here; the
    in-memory transport sends no headers at all and yields None.
    """
    try:
        from fastmcp.server.dependencies import get_http_headers

        headers = get_http_headers(include_all=True) or {}
        value = headers.get("user-agent") or headers.get("User-Agent")
        return value.strip() if value else None
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
    params = handshake_params()
    if params is None:
        if not _in_background_task():
            return UISupport()
        # A worker leg: the handshake is unreachable by construction, so fall
        # back to the header identity the task snapshot did restore.
        agent = _header_identity()
        support = UISupport(
            name=agent,
            name_allowlisted=_name_allowlisted(agent),
            in_task=True,
            via_headers=agent is not None,
        )
        _log_identity_once(support)
        return support

    # MCP SDK v2 names the field client_info; keep the camelCase fallback for
    # handshake objects from older SDK builds.
    info = getattr(params, "client_info", None) or getattr(params, "clientInfo", None)
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
    if support.in_task:
        # Inside a task worker "unknown" must resolve to text. The result is
        # delivered through `tasks/result`, and a view spec handed to a host
        # that cannot draw it is the exact failure this gate exists to stop;
        # plain text is correct everywhere. A client the headers do identify
        # as UI-capable still gets its card.
        return support.renders
    if not support.handshake_seen:
        # No session at all (unit test, older FastMCP): keep rendering, since
        # silently downgrading a card that works is worse than paying for one
        # that was not needed.
        return True

    return support.renders


def _elicitation_modes(elicitation) -> list[str]:
    """The modes an ``ElicitationCapability`` declares, in a fixed order.

    A bare ``elicitation: {}`` is the pre-2025-11-25 declaration, from before
    the form/url split, and means form mode: that is what the SDK's own
    ``check_client_capability`` accepts, and it is what Claude Code sends
    (``{roots: {listChanged: true}, elicitation: {}}``, unconditionally).
    Reporting it as no modes at all misdescribed every such client.
    """
    if elicitation is None:
        return []
    modes = [m for m in ("form", "url") if getattr(elicitation, m, None) is not None]
    return modes or ["form"]


def _declared_extensions(params) -> dict:
    """Extensions the client declared in its ``initialize`` capabilities.

    SDK v2 has ``extensions`` as a real field on ``ClientCapabilities``; older
    clients serialized it as an extra key, which pydantic keeps in
    ``model_extra``. Mirrors FastMCP's own ``client_supports_extension``.
    """
    from collections.abc import Mapping

    caps = getattr(params, "capabilities", None)
    ext = getattr(caps, "extensions", None)
    if ext is None:
        ext = (getattr(caps, "model_extra", None) or {}).get("extensions")
    return dict(ext) if isinstance(ext, Mapping) else {}


def _capabilities() -> dict:
    """What the connection negotiated: era, elicitation modes, tasks opt-in.

    Read on the same call that identifies the client, so one observation per
    session answers what a host can do. Each part degrades independently —
    ``None`` for the era or tasks, an empty mode list — rather than failing.
    """
    era: str | None = None
    modes: list[str] = []
    tasks: bool | None = None
    try:
        from fastmcp.server.dependencies import get_context

        ctx = get_context()
        try:
            era = str(ctx.session.protocol_version)
        except Exception:
            pass
        try:
            modes = _elicitation_modes(
                getattr(ctx.session.client_capabilities, "elicitation", None)
            )
        except Exception:
            pass
        try:
            from fastmcp.utilities.tasks import TASKS_EXTENSION_ID

            tasks = ctx.client_extension_settings(TASKS_EXTENSION_ID) is not None
        except Exception:
            pass
    except Exception:
        pass
    return {"protocol_version": era, "elicitation": modes, "tasks": tasks}


def _capability_summary() -> str:
    """:func:`_capabilities` as one short token string for the log line."""
    c = _capabilities()
    tasks = {True: "yes", False: "no"}.get(c["tasks"], "?")
    return (
        f"era={c['protocol_version'] or '?'} "
        f"elicit={'+'.join(c['elicitation']) or 'none'} tasks={tasks}"
    )


def client_record() -> dict:
    """The connected client, as a JSON-ready record for per-session storage.

    Combines the handshake identity (:func:`detect_ui_support`) with the
    negotiated capabilities (:func:`_capabilities`) and the ``User-Agent``,
    which is the only identity a task worker later sees — recording both lets
    a worker-leg log line be mapped back to the client that submitted it.
    Safe outside a request: every field simply reads as unknown.
    """
    from datetime import datetime, timezone

    support = detect_ui_support()
    caps = _capabilities()
    return {
        "name": support.name,
        "version": support.version,
        "source": "user-agent" if support.via_headers else "clientInfo",
        "user_agent": _header_identity(),
        "protocol_version": caps["protocol_version"],
        "ui_extension": support.advertises_extension,
        "elicitation": caps["elicitation"],
        "tasks": caps["tasks"],
        "first_seen": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def client_record_from_handshake(params, negotiated_version: str | None = None) -> dict:
    """:func:`client_record`, read from the ``initialize`` request itself.

    ``initialize`` is the one request every client sends, so it is where a
    session's client should be recorded — but the SDK commits
    ``session.client_params`` only after the whole initialize chain has
    returned, so at that point :func:`client_record` (which reads the session)
    sees no handshake at all. Read the request instead. ``negotiated_version``
    is the server's answer from the ``InitializeResult`` and beats the version
    the client asked for.
    """
    from datetime import datetime, timezone

    try:
        from fastmcp.apps.config import UI_EXTENSION_ID as ui_ext_id
    except Exception:
        ui_ext_id = "io.modelcontextprotocol/ui"
    try:
        from fastmcp.utilities.tasks import TASKS_EXTENSION_ID as tasks_ext_id
    except Exception:
        tasks_ext_id = "io.modelcontextprotocol/tasks"

    info = getattr(params, "client_info", None) or getattr(params, "clientInfo", None)
    caps = getattr(params, "capabilities", None)
    declared = _declared_extensions(params)
    era = negotiated_version or getattr(params, "protocol_version", None)
    return {
        "name": getattr(info, "name", None),
        "version": getattr(info, "version", None),
        "source": "clientInfo",
        "user_agent": _header_identity(),
        "protocol_version": str(era) if era else None,
        "ui_extension": ui_ext_id in declared,
        "elicitation": _elicitation_modes(getattr(caps, "elicitation", None)),
        # Either the 2026-07-28 core capability or the SEP-2663 extension.
        "tasks": getattr(caps, "tasks", None) is not None or tasks_ext_id in declared,
        "first_seen": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _log_identity_once(support: UISupport) -> None:
    """Report the client's identity and capabilities once per session.

    The allowlist is a guess until a real client is observed, so this line is
    how you find out what a host actually calls itself — and, since the same
    call can read the negotiated capabilities, what it can do.
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
        "[ui-gating] client=%s version=%s source=%s %s ui_extension=%s "
        "allowlisted=%s gating=%s -> %s",
        support.name or "(unnamed)",
        support.version or "(unknown)",
        "user-agent (task worker)"
        if support.via_headers
        else "none (task worker)"
        if support.in_task
        else "clientInfo",
        _capability_summary(),
        support.advertises_extension,
        support.name_allowlisted,
        gating,
        "card" if (support.renders or not gating) else "text-only",
    )
