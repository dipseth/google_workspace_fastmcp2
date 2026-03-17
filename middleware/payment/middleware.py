"""X402PaymentMiddleware -- gates tool access behind stablecoin payments.

Supports three client paths:
  A. x402-native via HTTP header  (PAYMENT-SIGNATURE on StreamableHTTP)
  B. x402-native via tool argument (_x402_payment on any transport inc. stdio)
  C. Legacy tx_hash via verify_payment tool call

Flow:
  1. Check if the tool is exempt
  2. Check if the session has auth-based exemption (OAuth/per-user key)
  3. Check if the session has a valid (non-expired) payment verification
  4. Check for x402 payment payload (header or tool arg)
     → verify via SDK, execute tool, settle, cache receipt in session
  5. If none of the above -> return x402-compliant 402 response
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from fastmcp.server.middleware import Middleware
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from config.enhanced_logging import setup_logger
from config.settings import settings
from middleware.payment.constants import (
    PAYMENT_EXEMPT_TOOLS,
    USDC_CONTRACTS,
    X402_TOOL_ARG_KEY,
)
from middleware.payment.types import PaymentRequiredDetails

if TYPE_CHECKING:
    from x402.server import x402ResourceServer

logger = setup_logger()


@dataclass
class _PendingSettlement:
    """Settlement data returned from verify, consumed by settle.

    Returned by value (not stored on self) to avoid race conditions
    under concurrent requests.
    """

    payload: Any  # x402 PaymentPayload
    requirements: Any  # x402 PaymentRequirements
    session_id: str | None
    payer_address: str
    tool_name: str


class X402PaymentMiddleware(Middleware):
    """Gates tool access behind x402 stablecoin payment verification.

    Args:
        gated_tools: Comma-separated tool names to gate. Empty = all tools.
        free_for_oauth: If True, OAuth/per-user-key sessions bypass payment.
        session_ttl_minutes: How long a verified payment lasts.
        resource_server: Optional x402ResourceServer for SDK-based verify/settle.
    """

    def __init__(
        self,
        gated_tools: str = "",
        free_for_oauth: bool = True,
        session_ttl_minutes: int = 60,
        resource_server: Optional[x402ResourceServer] = None,
    ) -> None:
        self._gated_tools: frozenset[str] | None = None
        if gated_tools:
            self._gated_tools = frozenset(
                t.strip() for t in gated_tools.split(",") if t.strip()
            )
        self._free_for_oauth = free_for_oauth
        self._session_ttl_seconds = session_ttl_minutes * 60
        self._resource_server = resource_server
        logger.info(
            "X402PaymentMiddleware initialized (gated=%s, free_for_oauth=%s, ttl=%dm, sdk=%s)",
            self._gated_tools or "all",
            self._free_for_oauth,
            session_ttl_minutes,
            "yes" if resource_server else "no",
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
        """Check if session has a valid (non-expired) payment with valid receipt."""
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

            # Optional: verify receipt HMAC for defense-in-depth
            receipt_dict = get_session_data(
                session_id, SessionKey.PAYMENT_RECEIPT, default=None
            )
            if receipt_dict:
                try:
                    from middleware.payment.receipt import verify_receipt_hmac
                    from middleware.payment.types import PaymentReceipt

                    receipt = PaymentReceipt(**receipt_dict)
                    if not verify_receipt_hmac(receipt):
                        logger.warning(
                            "Payment receipt HMAC invalid for session %s", session_id
                        )
                        return False
                except Exception:
                    pass  # Receipt validation is defense-in-depth, not blocking

            return True
        except Exception:
            return False

    def _extract_payment_payload(self, context) -> Optional[str]:
        """Extract x402 payment payload from HTTP header or tool argument.

        Returns base64-encoded payload string, or None.
        """
        # Path A: HTTP header (StreamableHTTP transport)
        try:
            ctx = context.fastmcp_context
            if hasattr(ctx, "_request") and ctx._request is not None:
                request = ctx._request
                if hasattr(request, "headers"):
                    header_val = request.headers.get("payment-signature")
                    if isinstance(header_val, str) and header_val:
                        logger.debug("x402 payment found in HTTP header")
                        return header_val
        except Exception:
            pass

        # Path B: Tool argument (_x402_payment key)
        try:
            args = context.message.arguments or {}
            if isinstance(args, dict) and X402_TOOL_ARG_KEY in args:
                val = args[X402_TOOL_ARG_KEY]
                if isinstance(val, str) and val:
                    logger.debug("x402 payment found in tool argument")
                    return val
        except Exception:
            pass

        return None

    def _strip_payment_arg(self, context) -> None:
        """Remove _x402_payment from tool arguments so tools never see it."""
        try:
            args = context.message.arguments
            if args and X402_TOOL_ARG_KEY in args:
                del args[X402_TOOL_ARG_KEY]
        except Exception:
            pass

    async def _verify_and_settle(
        self,
        payload_b64: str,
        session_id: str | None,
        tool_name: str = "",
    ) -> tuple[Optional[ToolResult], Optional[_PendingSettlement]]:
        """Verify payment via x402 SDK.

        Returns (error_result, pending_settlement):
        - On failure: (ToolResult with error, None)
        - On success: (None, _PendingSettlement for post-execution settle)
        """
        if not self._resource_server:
            logger.warning(
                "x402 payment payload received but no resource_server configured"
            )
            return None, None  # Fall through to legacy 402

        try:
            from middleware.payment.receipt import build_payer_identity, hash_email
            from middleware.payment.types import PaymentPayloadBuilder

            # Decode payload
            payload_json = base64.b64decode(payload_b64).decode("utf-8")
            payload_dict = json.loads(payload_json)

            # Get user email hash for non-PII extensions
            user_email_hash = ""
            if session_id:
                try:
                    from auth.context import get_session_data
                    from auth.types import SessionKey

                    email = get_session_data(
                        session_id, SessionKey.USER_EMAIL, default=""
                    )
                    if email:
                        user_email_hash = hash_email(email)
                except Exception:
                    pass

            # Build proper SDK types via builder
            payment_payload, payment_requirements = (
                PaymentPayloadBuilder.from_raw_payload(
                    payload_dict,
                    settings,
                    tool_name=tool_name,
                    session_id=session_id or "",
                    user_email_hash=user_email_hash,
                )
            )

            # Verify via facilitator
            verify_result = await self._resource_server.verify_payment(
                payment_payload, payment_requirements
            )

            if not verify_result.is_valid:
                reason = getattr(verify_result, "invalid_reason", "Verification failed")
                logger.warning("x402 payment verification failed: %s", reason)
                return (
                    ToolResult(
                        content=[
                            TextContent(
                                type="text",
                                text=f"402 Payment Required\n\nPayment verification failed: {reason}",
                            )
                        ],
                    ),
                    None,
                )

            # Extract payer wallet address from verify result
            payer_address = getattr(verify_result, "payer", "") or ""
            if hasattr(payer_address, "hex"):
                payer_address = str(payer_address)

            # Cache payment + receipt in session
            self._cache_payment_in_session(
                session_id,
                payer_address=payer_address,
                tool_name=tool_name,
            )

            pending = _PendingSettlement(
                payload=payment_payload,
                requirements=payment_requirements,
                session_id=session_id,
                payer_address=payer_address,
                tool_name=tool_name,
            )
            return None, pending

        except Exception as e:
            logger.error("x402 payment verify error: %s", e, exc_info=True)
            return (
                ToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=f"402 Payment Required\n\nPayment processing error: {e}",
                        )
                    ],
                ),
                None,
            )

    async def _settle_payment(
        self, result: ToolResult, pending: Optional[_PendingSettlement]
    ) -> ToolResult:
        """Settle a verified payment after successful tool execution.

        Adds PAYMENT-RESPONSE data and payer info to result meta.
        """
        if not pending or not self._resource_server:
            return result

        try:
            settle_result = await self._resource_server.settle_payment(
                pending.payload, pending.requirements
            )

            # Extract settlement tx hash
            tx_hash = ""
            settle_b64 = ""
            if settle_result:
                settle_dict = settle_result.model_dump(by_alias=True)
                tx_hash = settle_dict.get("txHash", settle_dict.get("transaction", ""))
                settle_b64 = base64.b64encode(json.dumps(settle_dict).encode()).decode()

            # Update session with settlement data
            session_id = pending.session_id
            if session_id and tx_hash:
                try:
                    from auth.context import store_session_data
                    from auth.types import SessionKey

                    store_session_data(
                        session_id, SessionKey.PAYMENT_SETTLE_TX_HASH, tx_hash
                    )
                    store_session_data(session_id, SessionKey.PAYMENT_TX_HASH, tx_hash)
                except Exception as e:
                    logger.warning("Could not store settlement hash: %s", e)

            # Attach x402 response data to result meta
            if result.meta is None:
                result.meta = {}
            result.meta["x402"] = {
                "version": 2,
                "settled": True,
                "paymentResponse": settle_b64,
                "payer": pending.payer_address,
            }

        except Exception as e:
            logger.error("x402 payment settlement error: %s", e, exc_info=True)
            if result.meta is None:
                result.meta = {}
            result.meta["x402"] = {
                "version": 2,
                "settled": False,
                "settlementError": str(e),
            }

        return result

    def _cache_payment_in_session(
        self,
        session_id: str | None,
        payer_address: str = "",
        tool_name: str = "",
        tx_hash: str = "",
    ) -> None:
        """Store payment verification + HMAC-signed receipt in session."""
        if not session_id:
            return
        try:
            from auth.context import store_session_data
            from auth.types import SessionKey
            from middleware.payment.constants import MCP_RESOURCE_URL_PREFIX
            from middleware.payment.receipt import (
                build_payer_identity,
                create_payment_receipt,
            )

            now = time.time()
            store_session_data(session_id, SessionKey.PAYMENT_VERIFIED, True)
            store_session_data(session_id, SessionKey.PAYMENT_VERIFIED_AT, now)
            store_session_data(
                session_id, SessionKey.PAYMENT_NETWORK, settings.payment_network
            )

            # Build and store payer identity + HMAC-signed receipt
            payer = build_payer_identity(session_id, payer_address)
            receipt = create_payment_receipt(
                payer=payer,
                tool_name=tool_name,
                amount=settings.payment_usdc_amount,
                network=settings.payment_network,
                tx_hash=tx_hash,
                ttl_seconds=self._session_ttl_seconds,
                resource_url=f"{MCP_RESOURCE_URL_PREFIX}{tool_name}"
                if tool_name
                else "",
            )

            store_session_data(
                session_id, SessionKey.PAYMENT_PAYER_ADDRESS, payer_address
            )
            store_session_data(
                session_id, SessionKey.PAYMENT_RECEIPT, receipt.model_dump()
            )
            store_session_data(
                session_id, SessionKey.PAYMENT_RECEIPT_HMAC, receipt.hmac
            )

        except Exception as e:
            logger.warning("Could not cache payment in session: %s", e)

    def _make_payment_required_response(self) -> ToolResult:
        """Build an x402-compliant 402 Payment Required response."""
        chain_id = settings.payment_chain_id
        network = settings.payment_network
        usdc_contract = USDC_CONTRACTS.get(chain_id, "")

        details = PaymentRequiredDetails(
            recipient_wallet=settings.payment_recipient_wallet,
            amount=settings.payment_usdc_amount,
            chain_id=chain_id,
            usdc_contract=usdc_contract,
            network=network,
            scheme=settings.payment_scheme,
        )

        message = (
            f"402 Payment Required\n\n"
            f"This tool requires a USDC payment to access.\n\n"
            f"Payment details:\n"
            f"  Recipient: {details.recipient_wallet}\n"
            f"  Amount: {details.amount} USDC\n"
            f"  Network: {details.network}\n"
            f"  Chain: {details.chain_id}\n"
            f"  USDC Contract: {details.usdc_contract}\n"
            f"  Scheme: {details.scheme}\n\n"
            f"x402-aware clients: sign an EIP-3009 TransferWithAuthorization and "
            f"include the base64-encoded payload as a PAYMENT-SIGNATURE header "
            f"or _x402_payment tool argument.\n\n"
            f"Legacy clients: send USDC on-chain, then call "
            f"verify_payment(tx_hash='your_tx_hash') to unlock access."
        )

        from middleware.payment.x402_server import (
            build_payment_requirements,
            encode_payment_requirements,
        )

        requirements = build_payment_requirements(settings)
        requirements_b64 = encode_payment_requirements(requirements)

        return ToolResult(
            content=[TextContent(type="text", text=message)],
            meta={
                "x402": {
                    "version": 2,
                    "paymentRequired": requirements_b64,
                }
            },
        )

    async def _get_session_id(self, context) -> Optional[str]:
        """Extract session ID from context."""
        try:
            from auth.context import get_session_context

            return await get_session_context()
        except Exception:
            try:
                ctx = context.fastmcp_context
                return ctx.session_id if ctx else None
            except Exception:
                return None

    async def on_call_tool(self, context, call_next):
        """Gate tool access behind payment verification."""
        tool_name = context.message.name

        # 1. Check if this tool is gated
        if not self._is_tool_gated(tool_name):
            return await call_next(context)

        # 2. Check session-level auth exemption
        session_id = await self._get_session_id(context)

        if self._is_session_exempt(session_id):
            return await call_next(context)

        # 3. Check if payment is already verified for this session (cached)
        if self._is_payment_verified(session_id):
            return await call_next(context)

        # 4. Check for x402 payment payload (Path A: header, Path B: tool arg)
        payment_payload = self._extract_payment_payload(context)
        if payment_payload:
            self._strip_payment_arg(context)

            error_result, pending = await self._verify_and_settle(
                payment_payload, session_id, tool_name
            )
            if error_result:
                return error_result

            # Verification passed — execute tool, then settle
            result = await call_next(context)
            return await self._settle_payment(result, pending)

        # 5. Not verified, no payment payload -- return 402 response
        logger.info(
            "Payment required for tool '%s' (session=%s)",
            tool_name,
            session_id or "unknown",
        )
        return self._make_payment_required_response()
