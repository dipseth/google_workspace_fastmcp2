"""
Security Audit Event Logger.

Provides structured JSON logging for security-relevant operations
using Python's logging module with a dedicated rotating file handler.

Event types:
- email_mismatch_rejected: Auth middleware rejected email mismatch
- email_mismatch_allowed_secondary: Allowed via dual-auth bridge
- qdrant_search: Search with tenant filter applied
- credential_access: Credential retrieval
- webhook_request: Outbound webhook POST
"""

import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

_audit_logger: logging.Logger | None = None


def _get_audit_logger() -> logging.Logger:
    """Get or create the security audit logger with rotating file handler."""
    global _audit_logger
    if _audit_logger is not None:
        return _audit_logger

    _audit_logger = logging.getLogger("security.audit")
    _audit_logger.setLevel(logging.INFO)
    _audit_logger.propagate = False

    log_dir = Path(os.getenv("AUDIT_LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_dir / "security_audit.jsonl",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _audit_logger.addHandler(handler)

    return _audit_logger


def log_security_event(
    event_type: str,
    user_email: str | None = None,
    details: dict | None = None,
) -> None:
    """Write a structured JSON line to the security audit log.

    Args:
        event_type: Category of security event (e.g. ``email_mismatch_rejected``)
        user_email: Email of the actor, if known
        details: Arbitrary metadata about the event
    """
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        "user_email": user_email,
        **(details or {}),
    }
    _get_audit_logger().info(json.dumps(record, default=str))
