"""Shared type definitions for the auth subsystem.

Centralizes enums and constants used across middleware, user_api_keys,
google_auth, and tool implementations to prevent typo-prone string literals.
"""

from enum import Enum


class AuthProvenance(str, Enum):
    """How the current MCP session authenticated.

    Used by middleware to decide credential isolation rules and by tools
    (e.g. check_drive_auth) to report session state.

    Inherits from ``str`` so comparisons like ``provenance == AuthProvenance.API_KEY``
    and ``provenance == "api_key"`` both work, easing migration.
    """

    API_KEY = "api_key"  # Shared MCP_API_KEY (admin token)
    USER_API_KEY = "user_api_key"  # Per-user key (generated on OAuth)
    OAUTH = "oauth"  # Browser-based OAuth flow


class SessionKey(str, Enum):
    """Keys used with ``store_session_data`` / ``get_session_data``.

    Centralised here so every read/write site references the same constant
    instead of a bare string literal.
    """

    USER_EMAIL = "user_email"
    AUTH_PROVENANCE = "auth_provenance"
    API_KEY_OWNED_ACCOUNTS = "api_key_owned_accounts"
    SESSION_AUTHED_EMAILS = "session_authed_emails"
    SESSION_DISABLED_TOOLS = "session_disabled_tools"
    SERVICE_SELECTION_NEEDED = "service_selection_needed"
    CREDENTIALS = "credentials"
    PER_USER_ENCRYPTION_KEY = (
        "per_user_encryption_key"  # Derived Fernet key bytes (in-memory only)
    )
