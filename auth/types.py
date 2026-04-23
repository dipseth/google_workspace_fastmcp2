"""Shared type definitions for the auth subsystem.

Centralizes enums and constants used across middleware, user_api_keys,
google_auth, and tool implementations to prevent typo-prone string literals.
"""

from enum import Enum
from typing import Any


# Aliases a caller can pass in place of their own email. Case/whitespace-insensitive —
# always match via is_me_alias() below, never via raw literal comparison.
ME_ALIASES = frozenset({"me", "myself"})


def is_me_alias(value: Any) -> bool:
    """True if value is a 'me'/'myself'-style self-reference (case and whitespace insensitive)."""
    return isinstance(value, str) and value.strip().lower() in ME_ALIASES


class AuthProvenance(str, Enum):
    """How the current MCP session authenticated.

    Used by middleware to decide credential isolation rules and by tools
    (e.g. check_drive_auth) to report session state.

    Inherits from ``str`` so comparisons like ``provenance == AuthProvenance.API_KEY``
    and ``provenance == "api_key"`` both work, easing migration.
    """

    API_KEY = "api_key"  # Shared MCP_API_KEY (admin token)
    USER_API_KEY = "user_api_key"  # Per-user key (generated on OAuth)
    OAUTH = "oauth"  # Browser-based OAuth flow (Google)
    GITHUB_OAUTH = "github_oauth"  # GitHub OAuth flow


class SessionKey(str, Enum):
    """Keys used with ``store_session_data`` / ``get_session_data``.

    Centralised here so every read/write site references the same constant
    instead of a bare string literal.
    """

    USER_EMAIL = "user_email"
    AUTH_PROVENANCE = "auth_provenance"
    IDENTITY_NOTIFIED = "identity_notified"  # Last email we sent resources/updated for (dedup)
    IDENTITY_SOURCE = "identity_source"  # Which extraction path resolved the identity: "jwt" | "google_provider" | "session" | "oauth_file"
    MCP_CLIENT_ID = "mcp_client_id"  # DCR/CIMD client_id URL of the connecting MCP client (e.g. "https://claude.ai/oauth/claude-code-client-metadata")
    MCP_CLIENT_NAME = "mcp_client_name"  # Human-friendly client_name from the CIMD document (e.g. "Claude Code"), if resolvable
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
    PAYMENT_PAYER_ADDRESS = "payment_payer_address"  # str (EVM wallet that paid)
    PAYMENT_RECEIPT = "payment_receipt"  # dict (HMAC-signed PaymentReceipt)
    PAYMENT_RECEIPT_HMAC = "payment_receipt_hmac"  # str (HMAC for validation)

    # Chat service account (per-user encrypted)
    CHAT_SERVICE_ACCOUNT_JSON = "chat_service_account_json"  # dict (in-memory cache)

    # Per-user sampling configuration (in-memory cache, encrypted on disk)
    SAMPLING_CONFIG = "sampling_config"  # dict: {model, api_key, api_base}

    # LLM-guessed email from start_google_auth (unverified, for display only)
    REQUESTED_EMAIL = "requested_email"

    # GitHub OAuth session data
    GITHUB_LOGIN = "github_login"  # str (GitHub username)
    GITHUB_EMAIL = "github_email"  # str (GitHub email, may be None)
    GITHUB_USER_ID = "github_user_id"  # str (GitHub numeric user ID)
    GITHUB_STARRED_REPO = (
        "github_starred_repo"  # bool (has user starred the gating repo)
    )
