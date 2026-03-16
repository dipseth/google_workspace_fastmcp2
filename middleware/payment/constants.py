"""Constants for x402 payment protocol."""

# USDC contract addresses per chain ID
USDC_CONTRACTS = {
    8453: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # Base mainnet
    84532: "0x036CbD53842c5426634e7929541eC2318f3dCF7e",  # Base Sepolia testnet
    1: "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # Ethereum mainnet
}

# HTTP header names for x402 protocol
X402_HEADER_TX_HASH = "X-Payment-Tx-Hash"
X402_HEADER_CHAIN_ID = "X-Payment-Chain-Id"

# Tools that are always exempt from payment (infrastructure tools)
PAYMENT_EXEMPT_TOOLS = frozenset(
    {
        "verify_payment",
        "manage_tools",
        "get_server_info",
        "check_drive_auth",
        "start_google_auth",
        "set_privacy_mode",
    }
)

# Known test transaction hashes for stub verifier
TEST_VALID_TX_HASHES = frozenset(
    {
        "test_valid_hash",
        "0xtest_valid_payment_hash",
    }
)
