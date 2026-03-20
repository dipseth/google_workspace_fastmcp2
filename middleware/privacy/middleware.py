"""PrivacyMiddleware — encryption-first PII protection for MCP tool responses.

Sits after all data-producing middleware (ProfileEnrichment, TagBased) and
before ResponseLimiting so the LLM sees masked tokens and the wire carries
encrypted ciphertext, while server-side storage (Qdrant) retains plaintext.

Two phases per ``on_call_tool``:
  Phase A (inbound):  resolve [PRIVATE:token_N] in arguments → plaintext
  Phase B (outbound): scan response → encrypt sensitive values → mask content

Per-session toggle: sessions can override the server default via
``SessionKey.PRIVACY_MODE`` (set by the ``set_privacy_mode`` tool).
"""

from __future__ import annotations

import secrets
from typing import Optional

from fastmcp.server.middleware import Middleware
from fastmcp.tools.tool import ToolResult

from config.enhanced_logging import setup_logger
from middleware.privacy.constants import PRIVACY_FIELD_PATTERNS
from middleware.privacy.registry import get_or_create_vault, get_vault
from middleware.privacy.scanner import (
    resolve_tokens_in_value,
    scan_and_encrypt_content,
    scan_and_encrypt_structured,
)
from middleware.privacy.vault import derive_privacy_vault_key

logger = setup_logger()

class PrivacyMiddleware(Middleware):
    """Encrypts sensitive values in tool responses, masks them for the LLM.

    Args:
        mode: ``"disabled"``, ``"auto"`` (field heuristics + value patterns),
              or ``"strict"`` (encrypt all string values).
              Acts as the server-wide default; individual sessions can
              override via ``SessionKey.PRIVACY_MODE``.
        additional_fields: Comma-separated extra field names to treat as PII.
        exclude_tools: Comma-separated tool names to skip privacy processing.
    """

    def __init__(
        self,
        mode: str = "auto",
        additional_fields: str = "",
        exclude_tools: str = "",
    ) -> None:
        self._mode = mode
        self._strict = mode == "strict"
        self._additional_fields: frozenset[str] | None = None
        if additional_fields:
            extras = frozenset(
                f.strip() for f in additional_fields.split(",") if f.strip()
            )
            self._additional_fields = extras if extras else None
        self._exclude_tools: frozenset[str] = frozenset(
            t.strip() for t in exclude_tools.split(",") if t.strip()
        )
        logger.info(
            "PrivacyMiddleware initialized (mode=%s, exclude=%s)",
            self._mode,
            self._exclude_tools or "none",
        )

    def _should_process(self, tool_name: str) -> bool:
        """Return True if this tool's response should be privacy-processed."""
        return tool_name not in self._exclude_tools

    def _get_effective_mode(self, session_id: str | None) -> str:
        """Return the privacy mode for this session.

        Checks session-level override first, falls back to server default.
        """
        if session_id:
            try:
                from auth.context import get_session_data
                from auth.types import SessionKey

                session_mode = get_session_data(
                    session_id, SessionKey.PRIVACY_MODE, default=None
                )
                if session_mode is not None:
                    return session_mode
            except Exception:
                pass
        return self._mode

    def _get_effective_additional_fields(
        self, session_id: str | None
    ) -> frozenset[str] | None:
        """Merge server-level and session-level additional fields.

        Session can store extra field names via ``SessionKey.PRIVACY_ADDITIONAL_FIELDS``.
        The special value ``"__content__"`` expands to ``PRIVACY_CONTENT_FIELDS``.
        """
        merged: set[str] = (
            set(self._additional_fields) if self._additional_fields else set()
        )

        if session_id:
            try:
                from auth.context import get_session_data
                from auth.types import SessionKey

                session_fields = get_session_data(
                    session_id, SessionKey.PRIVACY_ADDITIONAL_FIELDS, default=None
                )
                if session_fields:
                    if "__content__" in session_fields:
                        from middleware.privacy.constants import PRIVACY_CONTENT_FIELDS

                        merged |= PRIVACY_CONTENT_FIELDS
                        session_fields = session_fields - {"__content__"}
                    merged |= session_fields
            except Exception:
                pass

        return frozenset(merged) if merged else None

    async def on_call_tool(self, context, call_next):
        """Two-phase privacy processing around tool execution."""
        session_id = await self._get_session_id(context)

        # Phase A: resolve [PRIVATE:token_N] → plaintext in arguments
        # (needed even when disabled, for in-flight tokens from a prior enabled state)
        if context.message.arguments:
            vault = get_vault(session_id) if session_id else None
            if vault:
                context.message.arguments = resolve_tokens_in_value(
                    context.message.arguments, vault
                )

        # Determine effective mode for this session
        effective_mode = self._get_effective_mode(session_id)

        # Short-circuit: excluded tools and disabled mode bypass Phase B entirely
        if effective_mode == "disabled" or not self._should_process(
            context.message.name
        ):
            return await call_next(context)

        # Execute tool
        result = await call_next(context)

        # Phase B: encrypt + mask response (only when enabled)
        if not session_id:
            return result

        if result is None:
            return result

        vault = await self._ensure_vault(session_id, context)
        if vault is None:
            return result

        effective_strict = effective_mode == "strict"
        effective_fields = self._get_effective_additional_fields(session_id)

        # Process content blocks (what LLM reads — masked text)
        masked_content = result.content
        if result.content:
            try:
                masked_content = scan_and_encrypt_content(
                    result.content,
                    vault,
                    additional_fields=effective_fields,
                    strict=effective_strict,
                )
            except Exception:
                logger.exception(
                    "Privacy: error scanning content — suppressing response to prevent PII leak"
                )
                from mcp.types import TextContent

                masked_content = [
                    TextContent(type="text", text="[PRIVACY_ERROR: content redacted]")
                ]

        # Process structured_content (encrypted sentinels for round-trip)
        encrypted_structured = result.structured_content
        if result.structured_content:
            try:
                encrypted_structured = scan_and_encrypt_structured(
                    result.structured_content,
                    vault,
                    additional_fields=effective_fields,
                    strict=effective_strict,
                )
            except Exception:
                logger.exception(
                    "Privacy: error scanning structured_content — suppressing to prevent PII leak"
                )
                encrypted_structured = None

        # Build updated meta
        meta = dict(result.meta) if result.meta else {}
        meta["privacy"] = vault.stats()

        return ToolResult(
            content=masked_content,
            structured_content=encrypted_structured,
            meta=meta,
        )

    async def _get_session_id(self, context) -> Optional[str]:
        """Extract session ID from context."""
        try:
            from auth.context import get_session_context

            return await get_session_context()
        except Exception:
            # Fallback: try native context session_id
            try:
                ctx = context.fastmcp_context
                return ctx.session_id if ctx else None
            except Exception:
                return None

    async def _ensure_vault(self, session_id: str, context) -> Optional["PrivacyVault"]:
        """Get or create a vault for the session, deriving the key if needed."""
        existing = get_vault(session_id)
        if existing is not None:
            return existing

        fernet_key = await self._derive_key(session_id, context)
        if fernet_key is None:
            logger.warning("Privacy: could not derive key for session %s", session_id)
            return None

        return get_or_create_vault(session_id, fernet_key)

    async def _derive_key(self, session_id: str, context) -> Optional[bytes]:
        """Derive the Fernet key for this session's vault."""
        try:
            from auth.context import get_session_data
            from auth.types import AuthProvenance, SessionKey

            server_secret = self._get_server_secret()
            if server_secret is None:
                return None

            provenance = get_session_data(
                session_id, SessionKey.AUTH_PROVENANCE, default=None
            )

            # For per-user key or OAuth sessions, use the encryption key
            if provenance in (AuthProvenance.USER_API_KEY, AuthProvenance.OAUTH):
                enc_key = get_session_data(
                    session_id, SessionKey.PER_USER_ENCRYPTION_KEY, default=None
                )
                if enc_key and isinstance(enc_key, bytes):
                    return derive_privacy_vault_key(session_id, enc_key, server_secret)

            # For shared API key sessions or fallback: use a random seed
            seed = get_session_data(
                session_id, SessionKey.PRIVACY_VAULT_SEED, default=None
            )
            if seed is None:
                seed = secrets.token_bytes(32)
                from auth.context import store_session_data

                store_session_data(session_id, SessionKey.PRIVACY_VAULT_SEED, seed)
            return derive_privacy_vault_key(session_id, seed, server_secret)

        except Exception:
            logger.exception(
                "Privacy: key derivation failed for session %s", session_id
            )
            return None

    def _get_server_secret(self) -> Optional[bytes]:
        """Read the server secret used as HKDF salt."""
        try:
            from auth.context import get_auth_middleware

            mw = get_auth_middleware()
            if mw and hasattr(mw, "_get_server_secret"):
                return mw._get_server_secret()

            # Direct fallback: read from file
            from pathlib import Path

            from config.settings import settings

            key_path = Path(settings.credentials_dir) / ".auth_encryption_key"
            if key_path.exists():
                with open(key_path, "rb") as f:
                    return f.read()
        except Exception:
            logger.exception("Privacy: could not read server secret")
        return None
