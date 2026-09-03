"""Tests for the Gmail elicitation fallback gate (gmail/compose.py).

``send_gmail_message`` and ``forward_gmail_message`` confirm untrusted
recipients with ``ctx.elicit``. When that cannot happen the send must fall back
to whatever ``gmail_elicitation_fallback`` says (block, allow, or draft) — but
only for "elicitation is impossible here", never for "the user's answer failed
to arrive", which is a real error the caller needs to see.
"""

import pytest

from gmail.compose import _is_elicitation_unsupported


class _ToolError(Exception):
    """Stands in for fastmcp.exceptions.ToolError without importing it."""


IMPOSSIBLE = [
    # FastMCP 4 on a 2026-07-28 connection: SEP-2577 removed the back-channel,
    # so ctx.elicit() raises before anything reaches the wire. This is the
    # regression case — the message says "unavailable", not "unsupported", so
    # substring matching on the older patterns missed it and the configured
    # fallback was silently skipped.
    _ToolError(
        "elicitation via server-initiated requests is unavailable on "
        "2026-07-28 connections."
    ),
    Exception("Method not found"),
    Exception("Unknown method: elicitation/create"),
    Exception("Elicitation not supported by this client"),
    AttributeError("'ClientSession' object has no attribute 'elicit'"),
    NotImplementedError("elicit"),
]

REAL_FAILURE = [
    Exception("connection reset by peer"),
    Exception("the user's browser closed the dialog"),
    ValueError("schema validation failed for field 'action'"),
]


@pytest.mark.parametrize(
    "exc", IMPOSSIBLE, ids=lambda e: type(e).__name__ + ":" + str(e)[:32]
)
def test_impossible_elicitation_takes_the_fallback(exc):
    assert _is_elicitation_unsupported(exc) is True


@pytest.mark.parametrize("exc", REAL_FAILURE, ids=lambda e: str(e)[:32])
def test_genuine_failure_is_surfaced(exc):
    assert _is_elicitation_unsupported(exc) is False
