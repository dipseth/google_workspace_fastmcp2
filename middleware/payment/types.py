"""Type definitions for x402 payment protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from config.settings import Settings


class PaymentRequiredDetails(BaseModel):
    """Details returned in a 402 Payment Required response."""

    recipient_wallet: str = Field(description="Wallet address to send payment to")
    amount: str = Field(description="Required USDC amount")
    chain_id: int = Field(description="Blockchain chain ID")
    usdc_contract: str = Field(description="USDC contract address")
    network: str = Field(default="", description="CAIP-2 network identifier")
    scheme: str = Field(default="exact", description="x402 payment scheme")
    verify_tool: str = Field(
        default="verify_payment",
        description="Tool name to call after payment (legacy path)",
    )


class PaymentProof(BaseModel):
    """Payment proof submitted by client."""

    tx_hash: str = Field(description="Transaction hash")
    chain_id: int = Field(default=8453, description="Chain ID of the transaction")


class PayerIdentity(BaseModel):
    """Identity of the payer, combining on-chain wallet and session auth data."""

    wallet_address: str = Field(
        default="", description="EVM address that signed the payment"
    )
    user_email: Optional[str] = Field(
        default=None, description="Authenticated session email (if available)"
    )
    google_sub: Optional[str] = Field(
        default=None, description="Google account ID (if OAuth session)"
    )
    auth_provenance: Optional[str] = Field(
        default=None, description="How the session authenticated"
    )


class PaymentReceipt(BaseModel):
    """HMAC-signed receipt binding payment to user identity."""

    payer: PayerIdentity
    tool_name: str = Field(default="", description="Tool that triggered payment")
    amount: str = Field(default="", description="USDC amount paid")
    network: str = Field(default="", description="CAIP-2 network")
    tx_hash: str = Field(default="", description="Settlement tx hash")
    verified_at: float = Field(
        default=0.0, description="Unix timestamp of verification"
    )
    expires_at: float = Field(default=0.0, description="Unix timestamp of expiry")
    resource_url: str = Field(
        default="", description="Resource URL embedded in on-chain payload"
    )
    hmac: str = Field(default="", description="HMAC-SHA256 keyed with server secret")


class PaymentVerificationResult(BaseModel):
    """Result of payment verification."""

    verified: bool = Field(description="Whether the payment was verified")
    tx_hash: str = Field(description="Transaction hash that was verified")
    amount: Optional[str] = Field(default=None, description="Verified amount")
    settlement_tx_hash: Optional[str] = Field(
        default=None,
        description="On-chain settlement transaction hash from facilitator",
    )
    payer_address: Optional[str] = Field(
        default=None, description="Wallet address from VerifyResponse/SettleResponse"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if verification failed",
    )


class X402PaymentContext(BaseModel):
    """Parsed x402 payment data passed through middleware."""

    payload_b64: str = Field(description="Base64-encoded x402 payment payload")
    source: str = Field(
        description="How the payment was submitted: 'header' or 'tool_arg'"
    )


class PaymentPayloadBuilder:
    """Constructs x402 SDK types from raw dicts.

    Eliminates duplicated PaymentPayload/PaymentRequirements construction
    between middleware.py and verifier.py.
    """

    @staticmethod
    def from_raw_payload(
        payload_dict: dict,
        settings: Settings,
        tool_name: str = "",
        session_id: str = "",
        user_email_hash: str = "",
    ) -> tuple:
        """Build (PaymentPayload, PaymentRequirements) from a decoded payload dict.

        Returns a tuple of (PaymentPayload, PaymentRequirements) using proper
        SDK types with EIP-712 domain info.
        """
        from x402 import PaymentPayload, PaymentRequirements, ResourceInfo

        from middleware.payment.constants import MCP_RESOURCE_URL_PREFIX
        from middleware.payment.x402_server import build_payment_requirements

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

        # Build ResourceInfo with MCP-specific URL for on-chain memo
        resource_data = payload_dict.get("resource")
        if resource_data:
            resource = ResourceInfo(
                url=resource_data.get(
                    "url", f"{MCP_RESOURCE_URL_PREFIX}{tool_name}" if tool_name else ""
                ),
            )
        elif tool_name:
            resource = ResourceInfo(url=f"{MCP_RESOURCE_URL_PREFIX}{tool_name}")
        else:
            resource = None

        # Build extensions with non-PII session binding
        extensions = payload_dict.get("extensions")
        if not extensions and (session_id or user_email_hash):
            import hashlib
            import time as _t

            extensions = {
                "mcpBinding": {
                    "sessionPrefix": session_id[:8] if session_id else "",
                    "emailHash": user_email_hash[:16] if user_email_hash else "",
                    "timestamp": int(_t.time()),
                }
            }

        payment_payload = PaymentPayload(
            x402Version=payload_dict.get("x402Version", 2),
            payload=payload_dict.get("payload", {}),
            accepted=accepted,
            resource=resource,
            extensions=extensions,
        )

        return payment_payload, payment_requirements
