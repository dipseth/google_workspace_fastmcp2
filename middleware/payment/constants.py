"""Constants for x402 payment protocol."""

# USDC contract addresses per chain ID
USDC_CONTRACTS = {
    8453: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # Base mainnet
    84532: "0x036CbD53842c5426634e7929541eC2318f3dCF7e",  # Base Sepolia testnet
    1: "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # Ethereum mainnet
}

# x402 v2 standard HTTP header names
X402_HEADER_PAYMENT_REQUIRED = "PAYMENT-REQUIRED"
X402_HEADER_PAYMENT_SIGNATURE = "PAYMENT-SIGNATURE"
X402_HEADER_PAYMENT_RESPONSE = "PAYMENT-RESPONSE"

# Legacy custom headers (kept for backward compatibility)
X402_HEADER_TX_HASH = "X-Payment-Tx-Hash"
X402_HEADER_CHAIN_ID = "X-Payment-Chain-Id"

# CAIP-2 network identifier mapping  (chain_id → CAIP-2 string)
CAIP2_NETWORKS = {
    84532: "eip155:84532",  # Base Sepolia (testnet)
    8453: "eip155:8453",  # Base mainnet
    1: "eip155:1",  # Ethereum mainnet
}

# MCP tool argument key used to pass x402 payment payload (any transport)
X402_TOOL_ARG_KEY = "_x402_payment"

# MCP resource URL prefix for on-chain tool identification
MCP_RESOURCE_URL_PREFIX = "mcp://workspace.mcp/tool/"

# Tools that are always exempt from payment (infrastructure tools)
# Includes MCP server wrapper/proxy tools (execute, search, get_schema, tags)
# which are meta-tools — inner tool calls via execute still go through middleware.
PAYMENT_EXEMPT_TOOLS = frozenset(
    {
        "verify_payment",
        "manage_tools",
        "get_server_info",
        "check_drive_auth",
        "start_google_auth",
        "set_privacy_mode",
        # MCP server proxy/wrapper tools
        "execute",
        "search",
        "get_schema",
        "tags",
    }
)

# Known test transaction hashes for stub verifier (unit tests only)
TEST_VALID_TX_HASHES = frozenset(
    {
        "test_valid_hash",
        "0xtest_valid_payment_hash",
    }
)
