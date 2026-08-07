"""Tests for x402 payment receipt HMAC signing and identity binding."""

import secrets
from unittest.mock import patch

import pytest

import middleware.payment.receipt as receipt_module
from middleware.payment.receipt import (
    build_payer_identity,
    compute_receipt_hmac,
    create_payment_receipt,
    hash_email,
    verify_receipt_hmac,
)
from middleware.payment.types import PayerIdentity, PaymentReceipt


@pytest.fixture(autouse=True)
def _isolated_receipt_key(tmp_path, monkeypatch):
    """Receipt HMAC reads .auth_encryption_key from the CWD.

    Give each test an isolated temp key so the suite is self-contained
    (no dependency on a developer's real key file), and reset the derived
    HMAC key cache so tests never reuse a key from another CWD.
    """
    (tmp_path / ".auth_encryption_key").write_text(secrets.token_hex(32))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(receipt_module, "_hmac_key_cache", None)
    yield
    receipt_module._hmac_key_cache = None


class TestReceiptHMAC:
    def test_create_receipt_has_valid_hmac(self):
        payer = PayerIdentity(
            wallet_address="0xdedB30a0A415551f128d530A9cB7C5f42663d0Ff",
            user_email="test@example.com",
            auth_provenance="api_key",
        )
        receipt = create_payment_receipt(
            payer=payer,
            tool_name="search_gmail_messages",
            amount="0.001",
            network="eip155:84532",
            tx_hash="0xabc123",
            ttl_seconds=3600,
        )
        assert receipt.hmac != ""
        assert verify_receipt_hmac(receipt)

    def test_receipt_hmac_detects_tampering(self):
        payer = PayerIdentity(wallet_address="0xabc")
        receipt = create_payment_receipt(
            payer=payer,
            tool_name="list_spaces",
            amount="0.001",
            network="eip155:84532",
            tx_hash="0x123",
            ttl_seconds=3600,
        )
        assert verify_receipt_hmac(receipt)

        # Tamper with the receipt
        tampered = receipt.model_copy()
        tampered.amount = "999.0"
        assert not verify_receipt_hmac(tampered)

    def test_receipt_hmac_empty_fails(self):
        receipt = PaymentReceipt(
            payer=PayerIdentity(wallet_address="0x1"),
            hmac="",
        )
        assert not verify_receipt_hmac(receipt)

    def test_compute_receipt_hmac_deterministic(self):
        data = {"payer": {"wallet_address": "0x1"}, "amount": "0.001"}
        h1 = compute_receipt_hmac(data)
        h2 = compute_receipt_hmac(data)
        assert h1 == h2

    def test_compute_receipt_hmac_excludes_hmac_field(self):
        data = {"amount": "0.001", "hmac": "old_hmac"}
        h1 = compute_receipt_hmac(data)
        data2 = {"amount": "0.001", "hmac": "different_hmac"}
        h2 = compute_receipt_hmac(data2)
        assert h1 == h2  # hmac field is excluded


class TestPayerIdentity:
    def test_build_payer_identity_with_session(self):
        with patch("auth.context.get_session_data") as mock_get:
            from auth.types import AuthProvenance, SessionKey

            def side_effect(sid, key, default=None):
                return {
                    SessionKey.USER_EMAIL: "user@example.com",
                    SessionKey.GOOGLE_SUB: "1234567890",
                    SessionKey.AUTH_PROVENANCE: AuthProvenance.OAUTH,
                }.get(key, default)

            mock_get.side_effect = side_effect
            payer = build_payer_identity("session-1", "0xWallet")

            assert payer.wallet_address == "0xWallet"
            assert payer.user_email == "user@example.com"
            assert payer.google_sub == "1234567890"
            assert "oauth" in payer.auth_provenance.lower()

    def test_build_payer_identity_no_session(self):
        payer = build_payer_identity("", "0xWallet")
        assert payer.wallet_address == "0xWallet"
        assert payer.user_email is None
        assert payer.google_sub is None

    def test_build_payer_identity_api_key_session(self):
        with patch("auth.context.get_session_data") as mock_get:
            from auth.types import AuthProvenance, SessionKey

            def side_effect(sid, key, default=None):
                return {
                    SessionKey.AUTH_PROVENANCE: AuthProvenance.API_KEY,
                }.get(key, default)

            mock_get.side_effect = side_effect
            payer = build_payer_identity("session-2", "0xAddr")

            assert payer.wallet_address == "0xAddr"
            assert payer.user_email is None
            assert "api_key" in payer.auth_provenance.lower()


class TestHashEmail:
    def test_hash_email_produces_16_chars(self):
        result = hash_email("test@example.com")
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_email_case_insensitive(self):
        assert hash_email("Test@Example.com") == hash_email("test@example.com")

    def test_hash_email_empty(self):
        assert hash_email("") == ""

    def test_hash_email_different_emails_differ(self):
        assert hash_email("a@b.com") != hash_email("c@d.com")
