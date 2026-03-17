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
     → verify via SDK, execute tool, settle, cache in session
  5. If none of the above -> return x402-compliant 402 response
"""

from __future__ import annotations

import base64
import json
import time
from typing import TYPE_CHECKING, Optional

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
                # arguments is a dict; remove our internal key
                del args[X402_TOOL_ARG_KEY]
        except Exception:
            pass

    async def _verify_and_settle(
        self, payload_b64: str, session_id: str | None
    ) -> Optional[ToolResult]:
        """Verify payment via x402 SDK and return error ToolResult or None on success.

        On success, caches the payment in session and returns None (caller should proceed).
        On failure, returns a 402 ToolResult with error details.
        """
        if not self._resource_server:
            logger.warning(
                "x402 payment payload received but no resource_server configured"
            )
            return None  # Fall through to legacy 402

        try:
            from x402 import PaymentPayload, PaymentRequirements, ResourceInfo

            from middleware.payment.x402_server import build_payment_requirements

            # Decode the base64 payment payload
            payload_json = base64.b64decode(payload_b64).decode("utf-8")
            payload_dict = json.loads(payload_json)

            # Get SDK-enhanced requirements (includes EIP-712 domain in extra)
            reqs_dict = build_payment_requirements(settings)
            accepts_list = reqs_dict.get("accepts", [{}])
            req_data = accepts_list[0] if accepts_list else {}
            payment_requirements = PaymentRequirements(**req_data)

            # Build the accepted field from payload
            accepted_data = payload_dict.get("accepted", {})
            accepted = PaymentRequirements(
                scheme=accepted_data.get("scheme", settings.payment_scheme),
                network=accepted_data.get("network", settings.payment_network),
                asset=accepted_data.get("asset", req_data.get("asset", "")),
                amount=accepted_data.get(
                    "maxAmountRequired", accepted_data.get("amount", "0")
                ),
                payTo=accepted_data.get("payTo", settings.payment_recipient_wallet),
                maxTimeoutSeconds=int(accepted_data.get("maxTimeoutSeconds", 300)),
                extra=accepted_data.get("extra", req_data.get("extra", {})),
            )

            # Build ResourceInfo if present
            resource_data = payload_dict.get("resource")
            resource = None
            if resource_data:
                resource = ResourceInfo(
                    url=resource_data.get("url", ""),
                    method=resource_data.get("method", "POST"),
                )

            # Build PaymentPayload with proper SDK types
            payment_payload = PaymentPayload(
                x402Version=payload_dict.get("x402Version", 2),
                payload=payload_dict.get("payload", {}),
                accepted=accepted,
                resource=resource,
            )

            # Verify
            verify_result = await self._resource_server.verify_payment(
                payment_payload, payment_requirements
            )

            if not verify_result.is_valid:
                reason = getattr(verify_result, "invalid_reason", "Verification failed")
                logger.warning("x402 payment verification failed: %s", reason)
                return ToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=f"402 Payment Required\n\nPayment verification failed: {reason}",
                        )
                    ],
                )

            # Verification passed — we'll settle AFTER the tool executes
            # Cache the payment data for post-execution settlement
            self._pending_settlement = {
                "payload": payment_payload,
                "requirements": payment_requirements,
                "session_id": session_id,
            }

            # Cache payment in session
            self._cache_payment_in_session(session_id)

            return None  # Success — caller should proceed with call_next

        except Exception as e:
            logger.error("x402 payment verify error: %s", e, exc_info=True)
            return ToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=f"402 Payment Required\n\nPayment processing error: {e}",
                    )
                ],
            )

    async def _settle_payment(self, result: ToolResult) -> ToolResult:
        """Settle a verified payment after successful tool execution.

        Adds PAYMENT-RESPONSE data to result meta.
        """
        pending = getattr(self, "_pending_settlement", None)
        if not pending or not self._resource_server:
            return result

        try:
            settle_result = await self._resource_server.settle_payment(
                pending["payload"], pending["requirements"]
            )

            # Store settlement tx hash in session
            session_id = pending.get("session_id")
            if session_id and settle_result:
                try:
                    from auth.context import store_session_data
                    from auth.types import SessionKey

                    settle_dump = (
                        settle_result.model_dump(by_alias=True)
                        if hasattr(settle_result, "model_dump")
                        else {}
                    )
                    tx_hash = settle_dump.get("txHash", settle_dump.get("tx_hash", ""))
                    if tx_hash:
                        store_session_data(
                            session_id, SessionKey.PAYMENT_SETTLE_TX_HASH, tx_hash
                        )
                except Exception as e:
                    logger.warning("Could not store settlement hash: %s", e)

            # Encode settlement for response meta
            settle_b64 = ""
            if settle_result:
                try:
                    settle_dict = (
                        settle_result.model_dump(by_alias=True)
                        if hasattr(settle_result, "model_dump")
                        else {}
                    )
                    settle_b64 = base64.b64encode(
                        json.dumps(settle_dict).encode()
                    ).decode()
                except Exception:
                    pass

            # Attach x402 response data to result meta
            if result.meta is None:
                result.meta = {}
            result.meta["x402"] = {
                "version": 2,
                "settled": True,
                "paymentResponse": settle_b64,
            }

        except Exception as e:
            logger.error("x402 payment settlement error: %s", e, exc_info=True)
            # Tool already executed — don't fail the response, just log
            if result.meta is None:
                result.meta = {}
            result.meta["x402"] = {
                "version": 2,
                "settled": False,
                "settlementError": str(e),
            }
        finally:
            self._pending_settlement = None

        return result

    def _cache_payment_in_session(self, session_id: str | None) -> None:
        """Store payment verification in session data."""
        if not session_id:
            return
        try:
            from auth.context import store_session_data
            from auth.types import SessionKey

            store_session_data(session_id, SessionKey.PAYMENT_VERIFIED, True)
            store_session_data(session_id, SessionKey.PAYMENT_VERIFIED_AT, time.time())
            store_session_data(
                session_id, SessionKey.PAYMENT_NETWORK, settings.payment_network
            )
        except Exception as e:
            logger.warning("Could not cache payment in session: %s", e)

    def _make_payment_required_response(self) -> ToolResult:
        """Build an x402-compliant 402 Payment Required response.

        Returns a ToolResult with:
        - Human-readable text in content (backward compatible with any MCP client)
        - x402 v2 structured data in meta (for x402-aware clients)
        """
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

        # Build x402 v2 payment requirements for structured meta
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
            # Fallback: try native context session_id
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
            # Strip the _x402_payment arg so downstream tools don't see it
            self._strip_payment_arg(context)

            # Verify via SDK
            error_result = await self._verify_and_settle(payment_payload, session_id)
            if error_result:
                return error_result

            # Verification passed — execute tool, then settle
            result = await call_next(context)
            return await self._settle_payment(result)

        # 5. Not verified, no payment payload -- return 402 response
        logger.info(
            "Payment required for tool '%s' (session=%s)",
            tool_name,
            session_id or "unknown",
        )
        return self._make_payment_required_response()
