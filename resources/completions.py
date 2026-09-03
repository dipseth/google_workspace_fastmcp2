"""Argument completion (``completion/complete``) for prompts and resource templates.

One server-level handler, registered with ``@mcp.completion``; registering it
declares the ``completions`` capability on both protocol eras. Completion
fires per keystroke, so anything that costs an API call is cached in the
caller's per-principal bucket for five minutes (``auth/user_state.py``), and
nothing here ever raises: any failure is an empty candidate list.

Covered references:

- ``chat://digest/space/{space_code}{?hours,limit}`` — ``space_code`` from the
  user's Chat spaces, ``hours`` and ``limit`` from fixed sets.
- ``smart_contextual_chat_card`` — ``target_space`` from the user's spaces
  (display names, which is what the prompt indexes ``chat://spaces/list`` by),
  ``card_purpose`` from the documented set.
- ``professional_chat_dashboard``, ``smart_contextual_sheets_card``,
  ``professional_sheets_dashboard`` — the documented example values.

Identity comes from the request token (``principal_email``); the OAuth-file
fallback covers tokenless local runs. ``AuthMiddleware.on_call_tool`` does not
run for ``completion/complete``, so nothing else resolves the user here.
"""

from __future__ import annotations

import asyncio
from typing import Any, Iterable, Optional

from mcp_types import PromptReference, ResourceTemplateReference

from config.enhanced_logging import setup_logger

logger = setup_logger()

MAX_VALUES = 100
SPACES_CACHE_KEY = "chat_spaces"
SPACES_CACHE_TTL_SECONDS = 300
SPACES_PAGE_SIZE = 100

DIGEST_TEMPLATE_PREFIX = "chat://digest/space/"

STATIC_VALUES: dict[tuple[str, str], list[str]] = {
    ("resource", "hours"): ["1", "4", "12", "24", "48", "168"],
    ("resource", "limit"): ["5", "10", "25", "50"],
    ("smart_contextual_chat_card", "card_purpose"): [
        "status update",
        "dashboard",
        "report",
        "notification",
        "announcement",
    ],
    ("professional_chat_dashboard", "dashboard_theme"): [
        "status overview",
        "weekly report",
        "project status",
        "team metrics",
    ],
    ("smart_contextual_sheets_card", "data_focus"): [
        "summary analysis",
        "trends",
        "performance",
        "comparison",
        "forecast",
    ],
    ("professional_sheets_dashboard", "dashboard_theme"): [
        "performance analytics",
        "financial summary",
        "sales metrics",
        "project status",
    ],
}

# Prompt arguments completed from the user's Chat spaces (display names).
SPACE_NAME_ARGUMENTS: set[tuple[str, str]] = {
    ("smart_contextual_chat_card", "target_space"),
}


def _filter(values: Iterable[str], prefix: str) -> list[str]:
    """Case-insensitive prefix filter, capped at the MCP maximum."""
    needle = (prefix or "").lower()
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or value in seen:
            continue
        if needle and not value.lower().startswith(needle):
            continue
        seen.add(value)
        out.append(value)
        if len(out) >= MAX_VALUES:
            break
    return out


def _current_email() -> Optional[str]:
    from auth.context import get_user_email_context_sync
    from auth.user_state import principal_email

    return principal_email() or get_user_email_context_sync()


async def _list_spaces() -> list[dict[str, str]]:
    """The caller's Chat spaces as ``{"code", "name"}`` records, cached 5 minutes."""
    from auth.user_state import cache_get, cache_set

    cached = await cache_get(SPACES_CACHE_KEY)
    if isinstance(cached, list):
        return cached

    email = _current_email()
    if not email:
        return []

    from gchat.chat_tools import _get_chat_service_with_fallback

    chat_service = await _get_chat_service_with_fallback(email)
    if chat_service is None:
        return []

    def _fetch() -> list[dict[str, str]]:
        response = chat_service.spaces().list(pageSize=SPACES_PAGE_SIZE).execute()
        spaces = []
        for space in response.get("spaces", []) or []:
            name = space.get("name") or ""
            spaces.append(
                {
                    "code": name.split("/")[-1] if name else "",
                    "name": space.get("displayName") or "",
                }
            )
        return spaces

    spaces = await asyncio.to_thread(_fetch)
    await cache_set(SPACES_CACHE_KEY, spaces, SPACES_CACHE_TTL_SECONDS)
    return spaces


async def complete_argument(ref: Any, argument: Any, context: Any = None) -> list[str]:
    """Candidate values for ``argument`` of ``ref``; ``[]`` for anything unknown."""
    name = getattr(argument, "name", "") or ""
    value = getattr(argument, "value", "") or ""

    if isinstance(ref, ResourceTemplateReference):
        if not (ref.uri or "").startswith(DIGEST_TEMPLATE_PREFIX):
            return []
        if name == "space_code":
            spaces = await _list_spaces()
            return _filter((s.get("code") or "" for s in spaces), value)
        return _filter(STATIC_VALUES.get(("resource", name), []), value)

    if isinstance(ref, PromptReference):
        key = (ref.name, name)
        if key in SPACE_NAME_ARGUMENTS:
            spaces = await _list_spaces()
            return _filter((s.get("name") or "" for s in spaces), value)
        return _filter(STATIC_VALUES.get(key, []), value)

    return []


def setup_completions(mcp) -> None:
    """Register the completion handler on ``mcp``."""

    @mcp.completion
    async def complete(ref, argument, context=None):
        try:
            return await complete_argument(ref, argument, context)
        except Exception as exc:
            # Per keystroke; a failure is silence, never an error to the client.
            logger.debug(f"completion/complete failed: {exc}")
            return []

    logger.info(
        "✅ Argument completion registered (chat digest template, Chat/Sheets prompts)"
    )
