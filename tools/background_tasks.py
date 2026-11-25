"""Registering the background-tasks extension (SEP-2663) with this server's defaults."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from fastmcp import FastMCP

logger = logging.getLogger(__name__)

#: How long a finished task's state and result are kept. FastMCP's default is
#: 15 minutes; Claude asks server authors for at least an hour, because a user
#: can return to a finished task long after it ended. A deployment that sets
#: ``FASTMCP_DOCKET_EXECUTION_TTL`` keeps its own value.
RESULT_RETENTION = timedelta(hours=1)


def _execution_ttl() -> Optional[timedelta]:
    """This server's retention, or None when the deployment configured one."""
    from fastmcp_tasks.settings import DocketSettings

    if "execution_ttl" in DocketSettings().model_fields_set:
        return None
    return RESULT_RETENTION


def ensure_tasks_extension(mcp: FastMCP) -> bool:
    """Register the tasks extension on *mcp* unless it already is.

    A ``task=True`` tool cannot be served without it — FastMCP refuses the
    connection at lifespan start — so whatever marks a tool task-capable must
    also guarantee the extension. Idempotent: ``server.py`` registers it first
    in production, and a bare ``FastMCP`` (tests, embedding) gets it from Code
    Mode's setup. Returns False when ``fastmcp-tasks`` is not installed, in
    which case task-capable tools simply run inline.
    """
    try:
        from fastmcp_tasks import TasksExtension
    except ImportError as exc:
        logger.warning(
            f"fastmcp-tasks not installed; task=True tools run inline: {exc}"
        )
        return False
    try:
        mcp.add_extension(TasksExtension(execution_ttl=_execution_ttl()))
    except ValueError:
        # Already registered; FastMCP raises ValueError for a duplicate identifier.
        pass
    return True
