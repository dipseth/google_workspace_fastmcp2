"""Type definitions for x402 payment protocol."""

from typing import Optional

from pydantic import BaseModel, Field


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


class PaymentVerificationResult(BaseModel):
    """Result of payment verification."""

    verified: bool = Field(description="Whether the payment was verified")
    tx_hash: str = Field(description="Transaction hash that was verified")
    amount: Optional[str] = Field(default=None, description="Verified amount")
    settlement_tx_hash: Optional[str] = Field(
        default=None,
        description="On-chain settlement transaction hash from facilitator",
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
