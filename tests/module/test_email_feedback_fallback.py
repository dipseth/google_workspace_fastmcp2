"""
Tests for email feedback HMAC fallback secret behavior.

Covers:
- Ephemeral key generation when .auth_encryption_key is missing
- URL verification fails across key regeneration (server restart simulation)
"""

import os
from urllib.parse import parse_qs, urlparse

import pytest


def _parse_feedback_url(url: str) -> dict:
    """Extract query params from a generated feedback URL."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    return {k: v[0] for k, v in qs.items()}


class TestFallbackSecretBehavior:
    """Test that missing .auth_encryption_key produces ephemeral keys."""

    def setup_method(self):
        """Reset consumed tokens and HMAC key cache before each test."""
        from gmail.email_feedback.urls import reset_consumed_tokens

        reset_consumed_tokens()
        # Reset the cached HMAC key so each test can get a fresh one
        import gmail.email_feedback.urls as urls_mod

        urls_mod._hmac_key_cache = None

    def test_fallback_generates_random_key(self):
        """Without .auth_encryption_key, _get_server_secret returns a random string."""
        from gmail.email_feedback.urls import _get_server_secret

        key_path = ".auth_encryption_key"
        if os.path.exists(key_path):
            pytest.skip("Cannot test fallback when .auth_encryption_key exists")

        secret1 = _get_server_secret()
        # The fallback should NOT be the old hardcoded value
        assert secret1 != "email-feedback-fallback-key"
        # Should be a non-empty string
        assert len(secret1) > 16

    def test_url_roundtrip_with_stable_key(self):
        """URL generated and verified with same key should succeed."""
        from gmail.email_feedback.urls import (
            generate_feedback_url,
            verify_feedback_url,
        )

        url = generate_feedback_url(
            base_url="https://example.com",
            email_id="test123",
            action="positive",
            feedback_type="content",
        )
        params = _parse_feedback_url(url)
        valid, reason = verify_feedback_url(
            email_id=params["eid"],
            action=params["action"],
            feedback_type=params["type"],
            exp=params["exp"],
            sig=params["sig"],
            consume=False,
        )
        assert valid is True, f"Verification failed: {reason}"

    def test_url_invalid_after_key_reset(self):
        """URL generated before key reset should fail verification after reset."""
        from gmail.email_feedback.urls import generate_feedback_url

        url = generate_feedback_url(
            base_url="https://example.com",
            email_id="test456",
            action="negative",
            feedback_type="style",
        )
        params = _parse_feedback_url(url)

        # Simulate server restart by clearing the cached key
        import gmail.email_feedback.urls as urls_mod

        urls_mod._hmac_key_cache = None

        # Only test this if we're using the fallback (no .auth_encryption_key file)
        if os.path.exists(".auth_encryption_key"):
            pytest.skip(
                "Key file exists — URL will still verify since key is persistent"
            )

        from gmail.email_feedback.urls import verify_feedback_url

        valid, reason = verify_feedback_url(
            email_id=params["eid"],
            action=params["action"],
            feedback_type=params["type"],
            exp=params["exp"],
            sig=params["sig"],
            consume=False,
        )
        # With a new random fallback key, old URLs should fail
        assert valid is False
        assert "signature" in reason.lower() or "invalid" in reason.lower()
