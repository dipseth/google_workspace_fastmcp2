#!/usr/bin/env python3
"""Standalone test for the payment flow POC.

Tests the full lifecycle without needing the MCP server running:
1. Payment URL generation + signature verification
2. Paywall HTML page rendering (x402 SDK + fallback)
3. Pending payment tracking (register → complete → cleanup)
4. Payment email builder (MJML rendering)
5. Async event-based completion flow

Run: python scripts/test_payment_flow.py
"""

import asyncio
import sys
from urllib.parse import parse_qs, urlparse


def test_url_generation():
    """Test signed payment URL generation and verification."""
    from middleware.payment.payment_flow import (
        generate_payment_url,
        reset_state,
        verify_payment_token,
    )

    reset_state()

    url = generate_payment_url(
        base_url="https://mcp.example.com",
        session_id="test-session-abc123",
        tool_name="send_dynamic_card",
        amount="0.01",
        network="eip155:84532",
        recipient_wallet="0x1234567890abcdef1234567890abcdef12345678",
        chain_id=84532,
    )

    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "mcp.example.com"
    assert parsed.path == "/pay"
    assert "sig" in params
    assert params["tool"][0] == "send_dynamic_card"
    assert params["amt"][0] == "0.01"

    # Verify signature
    is_valid, err = verify_payment_token(
        session_id=params["sid"][0],
        tool_name=params["tool"][0],
        amount=params["amt"][0],
        network=params["net"][0],
        exp=params["exp"][0],
        sig=params["sig"][0],
        recipient_wallet=params["to"][0],
        chain_id=params["cid"][0],
        consume=False,
    )
    assert is_valid, f"Token should be valid, got: {err}"

    # Tampered amount should fail
    is_valid2, err2 = verify_payment_token(
        session_id=params["sid"][0],
        tool_name=params["tool"][0],
        amount="999.99",  # tampered
        network=params["net"][0],
        exp=params["exp"][0],
        sig=params["sig"][0],
        recipient_wallet=params["to"][0],
        chain_id=params["cid"][0],
        consume=False,
    )
    assert not is_valid2, "Tampered amount should fail"

    # Expired token
    url_expired = generate_payment_url(
        base_url="https://mcp.example.com",
        session_id="test-session",
        tool_name="test",
        amount="0.01",
        network="eip155:84532",
        recipient_wallet="0xabc",
        chain_id=84532,
        ttl_seconds=-1,
    )
    p2 = parse_qs(urlparse(url_expired).query)
    is_valid3, err3 = verify_payment_token(
        session_id=p2["sid"][0],
        tool_name=p2["tool"][0],
        amount=p2["amt"][0],
        network=p2["net"][0],
        exp=p2["exp"][0],
        sig=p2["sig"][0],
        recipient_wallet=p2["to"][0],
        chain_id=p2["cid"][0],
    )
    assert not is_valid3 and "expired" in err3.lower()

    reset_state()
    print("  [PASS] URL generation + signature verification")


def test_pending_payment_lifecycle():
    """Test the asyncio Event-based pending payment flow."""

    async def _test():
        from middleware.payment.payment_flow import (
            cleanup_pending_payment,
            complete_pending_payment,
            get_pending_payment,
            register_pending_payment,
            reset_state,
        )

        reset_state()

        token = "test-token-12345"
        event = register_pending_payment(token, "session-abc")

        assert not event.is_set(), "Event should not be set yet"
        assert get_pending_payment(token) is not None

        # Simulate browser completing payment
        ok = complete_pending_payment(token, "base64-signed-payload")
        assert ok, "Should succeed"
        assert event.is_set(), "Event should be set after completion"

        pending = get_pending_payment(token)
        assert pending["payload_b64"] == "base64-signed-payload"
        assert pending["completed_at"] is not None

        # Unknown token
        assert not complete_pending_payment("bogus", "data")

        # Cleanup
        cleanup_pending_payment(token)
        assert get_pending_payment(token) is None

        reset_state()

    asyncio.run(_test())
    print("  [PASS] Pending payment lifecycle (register → complete → cleanup)")


def test_async_wait_flow():
    """Test that awaiting the event works with timeout."""

    async def _test():
        from middleware.payment.payment_flow import (
            complete_pending_payment,
            register_pending_payment,
            reset_state,
        )

        reset_state()

        token = "wait-test-token"
        event = register_pending_payment(token, "session-xyz")

        # Simulate payment arriving after 100ms
        async def delayed_complete():
            await asyncio.sleep(0.1)
            complete_pending_payment(token, "delayed-payload")

        task = asyncio.create_task(delayed_complete())

        # Wait for completion (should resolve in ~100ms)
        try:
            await asyncio.wait_for(event.wait(), timeout=2.0)
            assert event.is_set()
            print("  [PASS] Async wait-for-completion (event signaled in ~100ms)")
        except asyncio.TimeoutError:
            print("  [FAIL] Timed out waiting for payment event")
            sys.exit(1)

        await task
        reset_state()

    asyncio.run(_test())


def test_timeout_flow():
    """Test that timeout works when payment never arrives."""

    async def _test():
        from middleware.payment.payment_flow import (
            register_pending_payment,
            reset_state,
        )

        reset_state()

        token = "timeout-test-token"
        event = register_pending_payment(token, "session-timeout")

        try:
            await asyncio.wait_for(event.wait(), timeout=0.2)
            print("  [FAIL] Should have timed out")
            sys.exit(1)
        except asyncio.TimeoutError:
            print("  [PASS] Timeout works correctly (0.2s)")

        reset_state()

    asyncio.run(_test())


def test_paywall_html():
    """Test payment page HTML rendering."""
    from tools.payment_endpoints import _build_fallback_payment_page

    html = _build_fallback_payment_page(
        tool_name="send_dynamic_card",
        amount="0.01",
        network="eip155:84532",
        recipient="0x1234567890abcdef1234567890abcdef12345678",
        chain_id=84532,
        session_prefix="test-sess",
        sig="abc123sig",
    )

    assert "Payment Required" in html
    assert "send_dynamic_card" in html
    assert "0.01" in html
    assert "TESTNET" in html
    assert "Connect Wallet" in html
    assert "EIP712Domain" in html
    assert "abc123sig" in html  # payment token embedded
    assert "TransferWithAuthorization" in html
    print("  [PASS] Fallback payment page HTML")

    # Try SDK paywall (may or may not work depending on x402 SDK state)
    try:
        from tools.payment_endpoints import _build_paywall_html

        sdk_html = _build_paywall_html(
            tool_name="send_dynamic_card",
            amount="0.01",
            network="eip155:84532",
            recipient="0x1234567890abcdef1234567890abcdef12345678",
            chain_id=84532,
            session_prefix="test-sess",
            sig="abc123sig",
        )
        assert len(sdk_html) > 1000
        print(f"  [PASS] SDK paywall page ({len(sdk_html):,} chars)")
    except Exception as exc:
        print(f"  [SKIP] SDK paywall: {exc}")


def test_payment_email():
    """Test MJML payment email rendering."""
    from middleware.payment.payment_email import build_payment_email

    result = build_payment_email(
        tool_name="send_dynamic_card",
        amount="0.01",
        network="eip155:84532",
        recipient_wallet="0x1234567890abcdef1234567890abcdef12345678",
        payment_url="https://mcp.example.com/pay?token=test123",
        recipient_email="user@example.com",
    )

    assert result["subject"] == "Payment Required: $0.01 USDC for send_dynamic_card"
    assert len(result["blocks"]) >= 8
    assert result["recipient_email"] == "user@example.com"

    spec = result["spec"]
    render = spec.render()
    assert render.success, f"MJML render failed: {render.diagnostics}"
    assert "Pay" in render.html
    assert "test123" in render.html
    assert "0.01" in render.html
    print(f"  [PASS] Payment email MJML ({len(render.html):,} chars)")


def test_one_time_use():
    """Test that tokens are consumed on first use."""
    from middleware.payment.payment_flow import (
        generate_payment_url,
        reset_state,
        verify_payment_token,
    )

    reset_state()

    url = generate_payment_url(
        base_url="https://test.com",
        session_id="consume-test",
        tool_name="tool1",
        amount="0.01",
        network="eip155:84532",
        recipient_wallet="0xabc",
        chain_id=84532,
    )
    params = parse_qs(urlparse(url).query)

    # First use — consume
    ok1, _ = verify_payment_token(
        session_id=params["sid"][0],
        tool_name=params["tool"][0],
        amount=params["amt"][0],
        network=params["net"][0],
        exp=params["exp"][0],
        sig=params["sig"][0],
        recipient_wallet=params["to"][0],
        chain_id=params["cid"][0],
        consume=True,
    )
    assert ok1

    # Second use — should be rejected
    ok2, err2 = verify_payment_token(
        session_id=params["sid"][0],
        tool_name=params["tool"][0],
        amount=params["amt"][0],
        network=params["net"][0],
        exp=params["exp"][0],
        sig=params["sig"][0],
        recipient_wallet=params["to"][0],
        chain_id=params["cid"][0],
        consume=True,
    )
    assert not ok2 and "already" in err2.lower()

    reset_state()
    print("  [PASS] One-time token consumption")


if __name__ == "__main__":
    print("\n=== Payment Flow POC Tests ===\n")

    tests = [
        ("URL Generation & Verification", test_url_generation),
        ("Pending Payment Lifecycle", test_pending_payment_lifecycle),
        ("Async Wait-for-Completion", test_async_wait_flow),
        ("Timeout Handling", test_timeout_flow),
        ("Paywall HTML Rendering", test_paywall_html),
        ("Payment Email (MJML)", test_payment_email),
        ("One-Time Token Use", test_one_time_use),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            print(f"\n{name}:")
            fn()
            passed += 1
        except Exception as exc:
            print(f"  [FAIL] {exc}")
            import traceback

            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
    print("All tests passed!\n")
