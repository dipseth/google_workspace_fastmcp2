"""X402 payment verifier -- bridges legacy tx_hash path to x402 SDK.

Phase 1 stub verification is retained when ``PAYMENT_TESTNET_STUBS`` is set
(for unit tests). Otherwise delegates to the x402ResourceServer SDK for
real verification via the facilitator.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Optional

from config.enhanced_logging import setup_logger
from middleware.payment.constants import TEST_VALID_TX_HASHES
from middleware.payment.types import PaymentVerificationResult

if TYPE_CHECKING:
    from x402.server import x402ResourceServer

logger = setup_logger()


class X402Verifier:
    """Verifies x402 payment transactions.

    Supports two modes:
    - Stub mode (test hashes): requires explicit PAYMENT_TESTNET_STUBS=true
    - SDK mode: when an x402ResourceServer is provided, delegates to the facilitator
    """

    def __init__(
        self,
        chain_id: int = 8453,
        rpc_url: str = "",
        verification_url: str = "",
        resource_server: Optional[x402ResourceServer] = None,
    ):
        self._chain_id = chain_id
        self._rpc_url = rpc_url
        self._verification_url = verification_url
        self._resource_server = resource_server
        self._testnet_stubs = (
            os.environ.get("PAYMENT_TESTNET_STUBS", "false").lower() == "true"
        )
        mode = "sdk" if resource_server else "stub"
        logger.info("X402Verifier initialized (chain_id=%d, mode=%s)", chain_id, mode)

    async def verify_payment(
        self,
        tx_hash: str,
        expected_amount: str = "",
        recipient_wallet: str = "",
    ) -> PaymentVerificationResult:
        """Verify a payment transaction.

        For legacy Path C clients that submit an on-chain tx_hash.
        """
        if not tx_hash:
            return PaymentVerificationResult(
                verified=False,
                tx_hash="",
                error="Transaction hash is required",
            )

        # Stub verification -- accept known test hashes (unit tests / testnet)
        if self._testnet_stubs and tx_hash in TEST_VALID_TX_HASHES:
            logger.info("Payment verified (test stub): tx_hash=%s", tx_hash)
            return PaymentVerificationResult(
                verified=True,
                tx_hash=tx_hash,
                amount=expected_amount or "0.01",
            )

        # SDK verification via facilitator (for real on-chain tx lookups)
        if self._resource_server:
            return await self._verify_via_sdk(
                tx_hash, expected_amount, recipient_wallet
            )

        # No SDK, no matching test hash
        logger.warning(
            "Payment verification failed: tx_hash=%s (no SDK configured)", tx_hash
        )
        return PaymentVerificationResult(
            verified=False,
            tx_hash=tx_hash,
            error=f"Transaction {tx_hash} could not be verified (no x402 SDK configured)",
        )

    async def _verify_via_sdk(
        self,
        tx_hash: str,
        expected_amount: str,
        recipient_wallet: str,
    ) -> PaymentVerificationResult:
        """Verify an on-chain transaction via the x402 facilitator.

        This is for Path C (legacy) clients who already sent USDC on-chain.
        The facilitator can look up the transaction and confirm it.
        """
        try:
            # For on-chain tx verification, we construct a minimal verification request
            # The facilitator's /verify endpoint can validate completed transactions
            from middleware.payment.constants import CAIP2_NETWORKS, USDC_CONTRACTS

            network = CAIP2_NETWORKS.get(self._chain_id, f"eip155:{self._chain_id}")
            usdc_contract = USDC_CONTRACTS.get(self._chain_id, "")

            # Use httpx to call the facilitator's verify endpoint directly
            # since the SDK's verify_payment expects a signed payload, not a tx hash
            import httpx

            facilitator_url = self._verification_url or "https://x402.org/facilitator"
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{facilitator_url}/verify",
                    json={
                        "txHash": tx_hash,
                        "network": network,
                        "asset": usdc_contract,
                        "amount": expected_amount,
                        "payTo": recipient_wallet,
                    },
                    timeout=30.0,
                )

            if resp.status_code == 200:
                data = resp.json()
                is_valid = data.get("isValid", False)
                if is_valid:
                    logger.info("Payment verified via facilitator: tx_hash=%s", tx_hash)
                    return PaymentVerificationResult(
                        verified=True,
                        tx_hash=tx_hash,
                        amount=expected_amount,
                    )

            logger.warning(
                "Payment verification failed via facilitator: tx_hash=%s, status=%d",
                tx_hash,
                resp.status_code,
            )
            return PaymentVerificationResult(
                verified=False,
                tx_hash=tx_hash,
                error=f"Facilitator rejected transaction {tx_hash}",
            )

        except Exception as e:
            logger.error("SDK verification error for tx_hash=%s: %s", tx_hash, e)
            return PaymentVerificationResult(
                verified=False,
                tx_hash=tx_hash,
                error=f"Verification error: {e}",
            )

    async def verify_payment_payload(
        self,
        payload_b64: str,
        expected_amount: str = "",
        recipient_wallet: str = "",
    ) -> PaymentVerificationResult:
        """Verify an x402-native base64-encoded payment payload.

        For x402-aware clients (Path A/B) calling verify_payment tool directly.
        """
        if not self._resource_server:
            return PaymentVerificationResult(
                verified=False,
                tx_hash="",
                error="x402 SDK not configured for payload verification",
            )

        try:
            import base64
            import json

            from config.settings import settings
            from middleware.payment.types import PaymentPayloadBuilder

            payload_json = base64.b64decode(payload_b64).decode("utf-8")
            payload_dict = json.loads(payload_json)

            # Use builder to construct proper SDK types
            payment_payload, payment_requirements = (
                PaymentPayloadBuilder.from_raw_payload(payload_dict, settings)
            )

            verify_result = await self._resource_server.verify_payment(
                payment_payload, payment_requirements
            )

            if not verify_result.is_valid:
                reason = getattr(verify_result, "invalid_reason", "Verification failed")
                return PaymentVerificationResult(
                    verified=False,
                    tx_hash="",
                    error=str(reason),
                )

            # Extract payer address from verify result
            payer_address = getattr(verify_result, "payer", "") or ""
            if hasattr(payer_address, "hex"):
                payer_address = str(payer_address)

            # Settle
            settle_result = await self._resource_server.settle_payment(
                payment_payload, payment_requirements
            )

            settle_tx = ""
            if settle_result:
                settle_dict = settle_result.model_dump(by_alias=True)
                settle_tx = settle_dict.get(
                    "txHash", settle_dict.get("transaction", "")
                )

            return PaymentVerificationResult(
                verified=True,
                tx_hash=settle_tx or "x402-settled",
                amount=expected_amount or settings.payment_usdc_amount,
                settlement_tx_hash=settle_tx,
                payer_address=payer_address,
            )

        except Exception as e:
            logger.error("x402 payload verification error: %s", e)
            return PaymentVerificationResult(
                verified=False,
                tx_hash="",
                error=f"Payload verification error: {e}",
            )
