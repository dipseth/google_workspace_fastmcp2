"""X402 payment verifier -- stub implementation for Phase 1."""

from config.enhanced_logging import setup_logger
from middleware.payment.constants import TEST_VALID_TX_HASHES
from middleware.payment.types import PaymentVerificationResult

logger = setup_logger()


class X402Verifier:
    """Verifies x402 payment transactions.

    Phase 1: Stub verifier that accepts known test hashes.
    Phase 2: Will add on-chain verification via web3.py or x402 SDK.
    """

    def __init__(
        self,
        chain_id: int = 8453,
        rpc_url: str = "",
        verification_url: str = "",
    ):
        self._chain_id = chain_id
        self._rpc_url = rpc_url
        self._verification_url = verification_url
        logger.info("X402Verifier initialized (chain_id=%d, phase=stub)", chain_id)

    async def verify_payment(
        self,
        tx_hash: str,
        expected_amount: str = "",
        recipient_wallet: str = "",
    ) -> PaymentVerificationResult:
        """Verify a payment transaction.

        Phase 1: Accepts test hashes. Rejects everything else.
        """
        if not tx_hash:
            return PaymentVerificationResult(
                verified=False,
                tx_hash="",
                error="Transaction hash is required",
            )

        # Phase 1: Stub verification -- accept known test hashes
        if tx_hash in TEST_VALID_TX_HASHES:
            logger.info("Payment verified (stub): tx_hash=%s", tx_hash)
            return PaymentVerificationResult(
                verified=True,
                tx_hash=tx_hash,
                amount=expected_amount or "0.01",
            )

        # Phase 2 placeholder: on-chain verification would go here
        logger.warning("Payment verification failed (stub): tx_hash=%s", tx_hash)
        return PaymentVerificationResult(
            verified=False,
            tx_hash=tx_hash,
            error=f"Transaction {tx_hash} could not be verified (stub verifier -- Phase 1)",
        )
