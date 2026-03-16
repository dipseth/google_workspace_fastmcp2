"""Tests for X402 Payment Protocol middleware (x402 SDK v2 upgrade)."""

import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from middleware.payment.constants import X402_TOOL_ARG_KEY
from middleware.payment.middleware import X402PaymentMiddleware
from middleware.payment.types import (
    PaymentRequiredDetails,
    PaymentVerificationResult,
    X402PaymentContext,
)
from middleware.payment.verifier import X402Verifier


def _make_context(tool_name: str, arguments: dict | None = None) -> MagicMock:
    """Create a mock middleware context with the given tool name."""
    context = MagicMock()
    context.message = MagicMock()
    context.message.name = tool_name
    context.message.arguments = arguments or {}
    return context


def _make_payment_payload_b64() -> str:
    """Create a fake base64-encoded x402 payment payload for testing."""
    payload = {
        "x402Version": 2,
        "payload": {
            "signature": "0xfakesig",
            "authorization": {
                "from": "0xPayer",
                "to": "0xPayee",
                "value": "10000",
                "validAfter": "0",
                "validBefore": "9999999999",
                "nonce": "0x1234",
            },
        },
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


# ── X402Verifier Tests ──────────────────────────────────────────────────


class TestX402Verifier:
    @pytest.mark.asyncio
    async def test_verify_valid_test_hash(self):
        verifier = X402Verifier()
        result = await verifier.verify_payment("test_valid_hash")
        assert result.verified is True
        assert result.tx_hash == "test_valid_hash"

    @pytest.mark.asyncio
    async def test_verify_second_test_hash(self):
        verifier = X402Verifier()
        result = await verifier.verify_payment("0xtest_valid_payment_hash")
        assert result.verified is True

    @pytest.mark.asyncio
    async def test_verify_invalid_hash(self):
        verifier = X402Verifier()
        result = await verifier.verify_payment("0xinvalid")
        assert result.verified is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_verify_empty_hash(self):
        verifier = X402Verifier()
        result = await verifier.verify_payment("")
        assert result.verified is False
        assert result.error == "Transaction hash is required"

    @pytest.mark.asyncio
    async def test_verify_with_stubs_disabled(self):
        """When testnet stubs are disabled and no SDK, all hashes fail."""
        with patch.dict("os.environ", {"PAYMENT_TESTNET_STUBS": "false"}):
            verifier = X402Verifier()
            result = await verifier.verify_payment("test_valid_hash")
            assert result.verified is False

    @pytest.mark.asyncio
    async def test_verify_with_resource_server(self):
        """SDK mode delegates to facilitator for unknown hashes."""
        mock_server = MagicMock()
        verifier = X402Verifier(resource_server=mock_server)

        # Non-test hash with SDK should attempt SDK verification
        with patch.object(
            verifier, "_verify_via_sdk", new_callable=AsyncMock
        ) as mock_sdk:
            mock_sdk.return_value = PaymentVerificationResult(
                verified=True, tx_hash="0xreal", amount="0.01"
            )
            # Disable stubs so we fall through to SDK
            verifier._testnet_stubs = False
            result = await verifier.verify_payment("0xreal")
            assert result.verified is True
            mock_sdk.assert_called_once()


# ── Middleware Integration Tests ────────────────────────────────────────


class TestX402PaymentMiddleware:
    def _make_middleware(self, **kwargs):
        defaults = {
            "gated_tools": "",
            "free_for_oauth": True,
            "session_ttl_minutes": 60,
        }
        defaults.update(kwargs)
        return X402PaymentMiddleware(**defaults)

    @pytest.mark.asyncio
    async def test_exempt_tool_passes_through(self):
        mw = self._make_middleware()
        call_next = AsyncMock(return_value="result")
        context = _make_context("verify_payment")

        result = await mw.on_call_tool(context, call_next)
        call_next.assert_called_once_with(context)

    @pytest.mark.asyncio
    async def test_gated_tool_returns_402(self):
        mw = self._make_middleware()
        call_next = AsyncMock()
        context = _make_context("list_spaces")

        with patch.object(
            mw, "_get_session_id", new_callable=AsyncMock, return_value=None
        ):
            result = await mw.on_call_tool(context, call_next)
            call_next.assert_not_called()
            assert "402" in result.content[0].text

    @pytest.mark.asyncio
    async def test_402_response_has_x402_meta(self):
        """402 responses include structured x402 v2 meta with paymentRequired."""
        mw = self._make_middleware()
        call_next = AsyncMock()
        context = _make_context("list_spaces")

        with patch.object(
            mw, "_get_session_id", new_callable=AsyncMock, return_value=None
        ):
            result = await mw.on_call_tool(context, call_next)
            assert result.meta is not None
            assert "x402" in result.meta
            assert result.meta["x402"]["version"] == 2
            assert "paymentRequired" in result.meta["x402"]
            # paymentRequired should be base64-decodable
            req_b64 = result.meta["x402"]["paymentRequired"]
            req_dict = json.loads(base64.b64decode(req_b64))
            assert req_dict["x402Version"] == 2
            assert len(req_dict["accepts"]) > 0

    @pytest.mark.asyncio
    async def test_402_response_text_mentions_network(self):
        """402 text includes network and scheme info for x402 clients."""
        mw = self._make_middleware()
        call_next = AsyncMock()
        context = _make_context("list_spaces")

        with patch.object(
            mw, "_get_session_id", new_callable=AsyncMock, return_value=None
        ):
            result = await mw.on_call_tool(context, call_next)
            text = result.content[0].text
            assert "Network:" in text
            assert "Scheme:" in text
            assert "EIP-3009" in text

    @pytest.mark.asyncio
    async def test_specific_gated_tools_ungated_passes(self):
        mw = self._make_middleware(gated_tools="tool_a,tool_b")
        call_next = AsyncMock(return_value="ok")
        context = _make_context("tool_c")

        result = await mw.on_call_tool(context, call_next)
        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_specific_gated_tool_blocked(self):
        mw = self._make_middleware(gated_tools="tool_a,tool_b")
        call_next = AsyncMock()
        context = _make_context("tool_a")

        with patch.object(
            mw, "_get_session_id", new_callable=AsyncMock, return_value=None
        ):
            result = await mw.on_call_tool(context, call_next)
            call_next.assert_not_called()
            assert "402" in result.content[0].text

    @pytest.mark.asyncio
    async def test_oauth_session_exempt(self):
        mw = self._make_middleware()
        call_next = AsyncMock(return_value="ok")
        context = _make_context("list_spaces")

        with patch.object(
            mw, "_get_session_id", new_callable=AsyncMock, return_value="session-123"
        ):
            with patch.object(mw, "_is_session_exempt", return_value=True):
                result = await mw.on_call_tool(context, call_next)
                call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_verified_payment_passes(self):
        mw = self._make_middleware()
        call_next = AsyncMock(return_value="ok")
        context = _make_context("list_spaces")

        with patch.object(
            mw, "_get_session_id", new_callable=AsyncMock, return_value="session-123"
        ):
            with patch.object(mw, "_is_session_exempt", return_value=False):
                with patch.object(mw, "_is_payment_verified", return_value=True):
                    result = await mw.on_call_tool(context, call_next)
                    call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_unverified_payment_returns_402(self):
        mw = self._make_middleware()
        call_next = AsyncMock()
        context = _make_context("list_spaces")

        with patch.object(
            mw, "_get_session_id", new_callable=AsyncMock, return_value="session-123"
        ):
            with patch.object(mw, "_is_session_exempt", return_value=False):
                with patch.object(mw, "_is_payment_verified", return_value=False):
                    result = await mw.on_call_tool(context, call_next)
                    call_next.assert_not_called()
                    assert "402" in result.content[0].text

    # ── Dual-path extraction tests ──

    @pytest.mark.asyncio
    async def test_payment_extracted_from_tool_arg(self):
        """Path B: x402 payment payload in tool argument triggers verify+settle."""
        payload_b64 = _make_payment_payload_b64()
        mw = self._make_middleware()
        mock_tool_result = MagicMock()
        mock_tool_result.meta = None
        call_next = AsyncMock(return_value=mock_tool_result)
        # Use a real dict for arguments so isinstance checks pass
        context = _make_context(
            "list_spaces", arguments={X402_TOOL_ARG_KEY: payload_b64, "query": "test"}
        )
        # Prevent Path A (HTTP header) from firing by making fastmcp_context._request None
        context.fastmcp_context._request = None

        with patch.object(
            mw, "_get_session_id", new_callable=AsyncMock, return_value="s1"
        ):
            with patch.object(mw, "_is_session_exempt", return_value=False):
                with patch.object(mw, "_is_payment_verified", return_value=False):
                    with patch.object(
                        mw,
                        "_verify_and_settle",
                        new_callable=AsyncMock,
                        return_value=None,
                    ) as mock_verify:
                        with patch.object(
                            mw,
                            "_settle_payment",
                            new_callable=AsyncMock,
                            return_value=mock_tool_result,
                        ):
                            result = await mw.on_call_tool(context, call_next)
                            mock_verify.assert_called_once_with(payload_b64, "s1")
                            call_next.assert_called_once()
                            # _x402_payment should be stripped from args
                            assert X402_TOOL_ARG_KEY not in context.message.arguments

    @pytest.mark.asyncio
    async def test_payment_verification_failure_returns_402(self):
        """If SDK verification fails, return error without executing tool."""
        from fastmcp.tools.tool import ToolResult
        from mcp.types import TextContent

        payload_b64 = _make_payment_payload_b64()
        mw = self._make_middleware()
        call_next = AsyncMock()
        context = _make_context(
            "list_spaces", arguments={X402_TOOL_ARG_KEY: payload_b64}
        )

        error_result = ToolResult(
            content=[TextContent(type="text", text="402 Payment Required\n\nFailed")]
        )

        with patch.object(
            mw, "_get_session_id", new_callable=AsyncMock, return_value="s1"
        ):
            with patch.object(mw, "_is_session_exempt", return_value=False):
                with patch.object(mw, "_is_payment_verified", return_value=False):
                    with patch.object(
                        mw,
                        "_verify_and_settle",
                        new_callable=AsyncMock,
                        return_value=error_result,
                    ):
                        result = await mw.on_call_tool(context, call_next)
                        call_next.assert_not_called()
                        assert "402" in result.content[0].text

    # ── Settlement flow tests ──

    @pytest.mark.asyncio
    async def test_settle_payment_adds_meta(self):
        """Settlement attaches x402 response data to result meta."""
        from fastmcp.tools.tool import ToolResult
        from mcp.types import TextContent

        mw = self._make_middleware()

        mock_settle_result = MagicMock()
        mock_settle_result.model_dump.return_value = {"txHash": "0xsettled123"}

        mock_resource_server = MagicMock()
        mock_resource_server.settle_payment = AsyncMock(return_value=mock_settle_result)
        mw._resource_server = mock_resource_server

        mw._pending_settlement = {
            "payload": MagicMock(),
            "requirements": MagicMock(),
            "session_id": "s1",
        }

        tool_result = ToolResult(
            content=[TextContent(type="text", text="Tool output")],
        )

        with patch("auth.context.store_session_data"):
            result = await mw._settle_payment(tool_result)

        assert result.meta is not None
        assert result.meta["x402"]["version"] == 2
        assert result.meta["x402"]["settled"] is True
        assert result.meta["x402"]["paymentResponse"] != ""

    @pytest.mark.asyncio
    async def test_settle_payment_error_logged_not_fatal(self):
        """Settlement errors don't crash the tool response."""
        from fastmcp.tools.tool import ToolResult
        from mcp.types import TextContent

        mw = self._make_middleware()

        mock_resource_server = MagicMock()
        mock_resource_server.settle_payment = AsyncMock(
            side_effect=Exception("network error")
        )
        mw._resource_server = mock_resource_server

        mw._pending_settlement = {
            "payload": MagicMock(),
            "requirements": MagicMock(),
            "session_id": "s1",
        }

        tool_result = ToolResult(
            content=[TextContent(type="text", text="Tool output")],
        )

        result = await mw._settle_payment(tool_result)
        assert result.meta["x402"]["settled"] is False
        assert "settlementError" in result.meta["x402"]
        # Tool output is preserved
        assert result.content[0].text == "Tool output"

    # ── Session caching tests ──

    @pytest.mark.asyncio
    async def test_session_cached_after_x402_payment(self):
        """After x402 payment, session is cached so subsequent calls pass."""
        mw = self._make_middleware()

        with patch("auth.context.store_session_data") as mock_store:
            mw._cache_payment_in_session("session-abc")
            # Should store PAYMENT_VERIFIED, PAYMENT_VERIFIED_AT, PAYMENT_NETWORK
            assert mock_store.call_count == 3

    # ── Unit tests for helper methods ──

    def test_is_tool_gated_exempt_tool(self):
        mw = self._make_middleware()
        assert mw._is_tool_gated("verify_payment") is False
        assert mw._is_tool_gated("manage_tools") is False

    def test_is_tool_gated_all_tools(self):
        mw = self._make_middleware()  # gated_tools="" means all
        assert mw._is_tool_gated("list_spaces") is True
        assert mw._is_tool_gated("some_random_tool") is True

    def test_is_tool_gated_specific_list(self):
        mw = self._make_middleware(gated_tools="tool_a,tool_b")
        assert mw._is_tool_gated("tool_a") is True
        assert mw._is_tool_gated("tool_b") is True
        assert mw._is_tool_gated("tool_c") is False

    def test_is_session_exempt_no_session(self):
        mw = self._make_middleware()
        assert mw._is_session_exempt(None) is False

    def test_is_session_exempt_free_for_oauth_disabled(self):
        mw = self._make_middleware(free_for_oauth=False)
        assert mw._is_session_exempt("session-123") is False

    def test_is_session_exempt_oauth(self):
        mw = self._make_middleware()
        with patch("auth.context.get_session_data") as mock_get:
            from auth.types import AuthProvenance

            mock_get.return_value = AuthProvenance.OAUTH
            assert mw._is_session_exempt("session-123") is True

    def test_is_session_exempt_user_api_key(self):
        mw = self._make_middleware()
        with patch("auth.context.get_session_data") as mock_get:
            from auth.types import AuthProvenance

            mock_get.return_value = AuthProvenance.USER_API_KEY
            assert mw._is_session_exempt("session-123") is True

    def test_is_session_exempt_shared_api_key(self):
        mw = self._make_middleware()
        with patch("auth.context.get_session_data") as mock_get:
            from auth.types import AuthProvenance

            mock_get.return_value = AuthProvenance.API_KEY
            assert mw._is_session_exempt("session-123") is False

    def test_is_payment_verified_no_session(self):
        mw = self._make_middleware()
        assert mw._is_payment_verified(None) is False

    def test_is_payment_verified_true(self):
        mw = self._make_middleware()
        with patch("auth.context.get_session_data") as mock_get:
            from auth.types import SessionKey

            def side_effect(session_id, key, default=None):
                if key == SessionKey.PAYMENT_VERIFIED:
                    return True
                if key == SessionKey.PAYMENT_VERIFIED_AT:
                    return time.time()  # Just now
                return default

            mock_get.side_effect = side_effect
            assert mw._is_payment_verified("session-123") is True

    def test_is_payment_verified_expired(self):
        mw = self._make_middleware(session_ttl_minutes=1)
        with patch("auth.context.get_session_data") as mock_get:
            from auth.types import SessionKey

            def side_effect(session_id, key, default=None):
                if key == SessionKey.PAYMENT_VERIFIED:
                    return True
                if key == SessionKey.PAYMENT_VERIFIED_AT:
                    return time.time() - 120  # 2 minutes ago, TTL is 1 min
                return default

            mock_get.side_effect = side_effect
            assert mw._is_payment_verified("session-123") is False

    def test_is_payment_verified_not_verified(self):
        mw = self._make_middleware()
        with patch("auth.context.get_session_data") as mock_get:
            mock_get.return_value = False
            assert mw._is_payment_verified("session-123") is False

    def test_strip_payment_arg(self):
        """_strip_payment_arg removes _x402_payment from arguments."""
        mw = self._make_middleware()
        context = _make_context(
            "tool_a", arguments={X402_TOOL_ARG_KEY: "abc", "q": "test"}
        )
        mw._strip_payment_arg(context)
        assert X402_TOOL_ARG_KEY not in context.message.arguments
        assert context.message.arguments["q"] == "test"


# ── Type Tests ──────────────────────────────────────────────────────────


class TestPaymentTypes:
    def test_payment_required_details(self):
        details = PaymentRequiredDetails(
            recipient_wallet="0xabc",
            amount="0.01",
            chain_id=8453,
            usdc_contract="0x833...",
        )
        assert details.recipient_wallet == "0xabc"
        assert details.verify_tool == "verify_payment"

    def test_payment_required_details_with_network(self):
        details = PaymentRequiredDetails(
            recipient_wallet="0xabc",
            amount="0.01",
            chain_id=84532,
            usdc_contract="0x036...",
            network="eip155:84532",
            scheme="exact",
        )
        assert details.network == "eip155:84532"
        assert details.scheme == "exact"

    def test_payment_verification_result(self):
        result = PaymentVerificationResult(
            verified=True, tx_hash="0xabc", amount="0.01"
        )
        assert result.verified is True
        assert result.error is None
        assert result.settlement_tx_hash is None

    def test_payment_verification_result_with_settlement(self):
        result = PaymentVerificationResult(
            verified=True,
            tx_hash="0xabc",
            amount="0.01",
            settlement_tx_hash="0xsettled",
        )
        assert result.settlement_tx_hash == "0xsettled"

    def test_x402_payment_context(self):
        ctx = X402PaymentContext(
            payload_b64="dGVzdA==",
            source="header",
        )
        assert ctx.source == "header"


# ── x402 Server Factory Tests ──────────────────────────────────────────


class TestX402ServerFactory:
    def test_build_payment_requirements(self):
        from middleware.payment.x402_server import build_payment_requirements

        mock_settings = MagicMock()
        mock_settings.payment_scheme = "exact"
        mock_settings.payment_network = "eip155:84532"
        mock_settings.payment_usdc_amount = "0.01"
        mock_settings.payment_recipient_wallet = "0xWallet"
        mock_settings.payment_chain_id = 84532

        reqs = build_payment_requirements(mock_settings)
        assert reqs["x402Version"] == 2
        assert len(reqs["accepts"]) == 1
        assert reqs["accepts"][0]["scheme"] == "exact"
        assert reqs["accepts"][0]["network"] == "eip155:84532"
        assert reqs["accepts"][0]["payTo"] == "0xWallet"

    def test_encode_payment_requirements(self):
        from middleware.payment.x402_server import encode_payment_requirements

        reqs = {"x402Version": 2, "accepts": []}
        encoded = encode_payment_requirements(reqs)
        decoded = json.loads(base64.b64decode(encoded))
        assert decoded == reqs

    def test_build_payment_options(self):
        from middleware.payment.x402_server import build_payment_options

        mock_settings = MagicMock()
        mock_settings.payment_scheme = "exact"
        mock_settings.payment_network = "eip155:84532"
        mock_settings.payment_recipient_wallet = "0xWallet"
        mock_settings.payment_usdc_amount = "0.05"

        options = build_payment_options(mock_settings)
        assert len(options) == 1
        assert options[0].scheme == "exact"
        assert options[0].network == "eip155:84532"
