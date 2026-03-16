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
    GOOGLE_SUB = "google_sub"  # Google account ID (immutable, non-public)
    OAUTH_LINKAGE_PASSWORD = (
        "oauth_linkage_password"  # Cross-OAuth passphrase (runtime)
    )
    PRIVACY_MODE = "privacy_mode"  # "disabled" | "auto" | "strict"
    PRIVACY_ADDITIONAL_FIELDS = (
        "privacy_additional_fields"  # frozenset[str] of extra field names
    )
    PRIVACY_VAULT_SEED = (
        "privacy_vault_seed"  # Random bytes for shared API key sessions
    )

    # Payment / x402 protocol
    PAYMENT_VERIFIED = "payment_verified"  # bool
    PAYMENT_TX_HASH = "payment_tx_hash"  # str
    PAYMENT_VERIFIED_AT = "payment_verified_at"  # float (timestamp)
    PAYMENT_AMOUNT = "payment_amount"  # str (USDC amount)
    PAYMENT_SETTLE_TX_HASH = "payment_settle_tx_hash"  # str (facilitator settlement)
    PAYMENT_NETWORK = "payment_network"  # str (CAIP-2 network id)

    # Chat service account (per-user encrypted)
    CHAT_SERVICE_ACCOUNT_JSON = "chat_service_account_json"  # dict (in-memory cache)
