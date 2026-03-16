"""X402PaymentMiddleware -- gates tool access behind stablecoin payments.

Checks whether the current session has a verified payment before allowing
tool execution. If not, returns a 402-style response with payment instructions.

Flow:
  1. Check if payment gating is enabled
  2. Check if the tool is exempt
  3. Check if the session has auth-based exemption (OAuth/per-user key)
  4. Check if the session has a valid (non-expired) payment verification
  5. If not -> return payment required response
  6. If yes -> call_next
"""

from __future__ import annotations

import time
from typing import Optional

from fastmcp.server.middleware import Middleware
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from config.enhanced_logging import setup_logger
from config.settings import settings
from middleware.payment.constants import PAYMENT_EXEMPT_TOOLS, USDC_CONTRACTS
from middleware.payment.types import PaymentRequiredDetails

logger = setup_logger()


class X402PaymentMiddleware(Middleware):
    """Gates tool access behind x402 stablecoin payment verification.

    Args:
        gated_tools: Comma-separated tool names to gate. Empty = all tools.
        free_for_oauth: If True, OAuth/per-user-key sessions bypass payment.
        session_ttl_minutes: How long a verified payment lasts.
    """

    def __init__(
        self,
        gated_tools: str = "",
        free_for_oauth: bool = True,
        session_ttl_minutes: int = 60,
    ) -> None:
        self._gated_tools: frozenset[str] | None = None
        if gated_tools:
            self._gated_tools = frozenset(
                t.strip() for t in gated_tools.split(",") if t.strip()
            )
        self._free_for_oauth = free_for_oauth
        self._session_ttl_seconds = session_ttl_minutes * 60
        logger.info(
            "X402PaymentMiddleware initialized (gated=%s, free_for_oauth=%s, ttl=%dm)",
            self._gated_tools or "all",
            self._free_for_oauth,
            session_ttl_minutes,
        )

    def _is_tool_gated(self, tool_name: str) -> bool:
        """Check if this tool requires payment."""
        if tool_name in PAYMENT_EXEMPT_TOOLS:
            return False
        if self._gated_tools is None:
            return True  # All tools gated when no specific list
        return tool_name in self._gated_tools

    def _is_session_exempt(self, session_id: str | None) -> bool:
        """Check if session has auth-based payment exemption."""
        if not self._free_for_oauth or not session_id:
            return False
        try:
            from auth.context import get_session_data
            from auth.types import AuthProvenance, SessionKey

            provenance = get_session_data(
                session_id, SessionKey.AUTH_PROVENANCE, default=None
            )
            if provenance in (AuthProvenance.OAUTH, AuthProvenance.USER_API_KEY):
                return True
        except Exception:
            pass
        return False

    def _is_payment_verified(self, session_id: str | None) -> bool:
        """Check if session has a valid (non-expired) payment."""
        if not session_id:
            return False
        try:
            from auth.context import get_session_data
            from auth.types import SessionKey

            verified = get_session_data(
                session_id, SessionKey.PAYMENT_VERIFIED, default=False
            )
            if not verified:
                return False

            verified_at = get_session_data(
                session_id, SessionKey.PAYMENT_VERIFIED_AT, default=0.0
            )
            if time.time() - float(verified_at) > self._session_ttl_seconds:
                logger.info("Payment expired for session %s", session_id)
                return False

            return True
        except Exception:
            return False

    def _make_payment_required_response(self) -> ToolResult:
        """Build a 402 Payment Required response with payment instructions."""
        chain_id = settings.payment_chain_id
        usdc_contract = USDC_CONTRACTS.get(chain_id, "")

        details = PaymentRequiredDetails(
            recipient_wallet=settings.payment_recipient_wallet,
            amount=settings.payment_usdc_amount,
            chain_id=chain_id,
            usdc_contract=usdc_contract,
        )

        message = (
            f"402 Payment Required\n\n"
            f"This tool requires a USDC payment to access.\n\n"
            f"Payment details:\n"
            f"  Recipient: {details.recipient_wallet}\n"
            f"  Amount: {details.amount} USDC\n"
            f"  Chain: {details.chain_id}\n"
            f"  USDC Contract: {details.usdc_contract}\n\n"
            f"After sending payment, call verify_payment(tx_hash='your_tx_hash') "
            f"to unlock access."
        )

        return ToolResult(
            content=[TextContent(type="text", text=message)],
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

    async def on_call_tool(self, context, call_next):
        """Gate tool access behind payment verification."""
        tool_name = context.message.name

        # Check if this tool is gated
        if not self._is_tool_gated(tool_name):
            return await call_next(context)

        # Check session-level auth exemption
        session_id = await self._get_session_id(context)

        if self._is_session_exempt(session_id):
            return await call_next(context)

        # Check if payment is verified for this session
        if self._is_payment_verified(session_id):
            return await call_next(context)

        # Not verified -- return 402 response
        logger.info(
            "Payment required for tool '%s' (session=%s)",
            tool_name,
            session_id or "unknown",
        )
        return self._make_payment_required_response()
