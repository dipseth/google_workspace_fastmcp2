"""Tests for X402 Payment Protocol middleware."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from middleware.payment.middleware import X402PaymentMiddleware
from middleware.payment.types import PaymentRequiredDetails, PaymentVerificationResult
from middleware.payment.verifier import X402Verifier


def _make_context(tool_name: str) -> MagicMock:
    """Create a mock middleware context with the given tool name."""
    context = MagicMock()
    context.message = MagicMock()
    context.message.name = tool_name
    return context


class TestX402Verifier:
    @pytest.mark.asyncio
    async def test_verify_valid_test_hash(self):
        verifier = X402Verifier()
        result = await verifier.verify_payment("test_valid_hash")
        assert result.verified is True
        assert result.tx_hash == "test_valid_hash"

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

        # Patch _get_session_id to return None (no session = no exemption)
        with patch.object(
            mw, "_get_session_id", new_callable=AsyncMock, return_value=None
        ):
            result = await mw.on_call_tool(context, call_next)
            call_next.assert_not_called()
            # Check it's a 402 payment required response
            assert "402" in result.content[0].text

    @pytest.mark.asyncio
    async def test_specific_gated_tools_ungated_passes(self):
        mw = self._make_middleware(gated_tools="tool_a,tool_b")
        call_next = AsyncMock(return_value="ok")
        context = _make_context("tool_c")

        # tool_c is not in the gated list, so it should pass through
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
            # Mock _is_session_exempt to return True (OAuth session)
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
                    assert "402" in result.content[0].text

    # --- Unit tests for helper methods ---

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

    def test_payment_verification_result(self):
        result = PaymentVerificationResult(
            verified=True, tx_hash="0xabc", amount="0.01"
        )
        assert result.verified is True
        assert result.error is None
