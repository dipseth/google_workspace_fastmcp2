"""Security regression tests for the auth review (2026-07).

These assert the SECURE / post-fix behavior. Before the fixes land, the
vulnerable-endpoint tests are expected to FAIL — that failure IS the
reproduction of each finding. After the corresponding fix, they should pass.

Run against a locally running server (HTTPS on localhost:8002):
    uv run python server.py           # in one shell
    uv run pytest tests/client/test_security_auth_review.py -v

Notes on safety: destructive endpoints are probed only with a clearly-fake
victim email that owns no real data.
"""

import os

import httpx
import pytest
from dotenv import dotenv_values

_ENV = dotenv_values(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
BASE = os.getenv("SEC_TEST_BASE_URL", "https://localhost:8002")
FAKE_VICTIM = "nonexistent-victim-probe@example.com"


def _client():
    return httpx.Client(verify=False, timeout=15, follow_redirects=False)


@pytest.mark.security
class TestUnauthenticatedEndpoints:
    """Findings: /oauth/status leak, /api/revoke, /card-feedback unsigned."""

    def test_oauth_status_requires_auth(self):
        """/oauth/status must not leak the authenticated identity to anonymous callers."""
        with _client() as c:
            r = c.get(f"{BASE}/oauth/status")
        # Secure: either requires auth (401/403) or does not disclose an email.
        if r.status_code == 200:
            body = r.text.lower()
            assert "user_email" not in body or '"user_email":null' in body.replace(
                " ", ""
            ), (
                f"VULN: /oauth/status disclosed identity to anonymous caller: {r.text[:200]}"
            )

    def test_revoke_requires_authenticated_owner(self):
        """/api/revoke must reject callers who don't prove ownership of the target email."""
        with _client() as c:
            r = c.post(
                f"{BASE}/api/revoke",
                json={
                    "user_email": FAKE_VICTIM,
                    "confirmation_email": FAKE_VICTIM,
                    "items": ["links"],
                },
            )
        assert r.status_code in (401, 403), (
            f"VULN: /api/revoke processed an unauthenticated request (HTTP {r.status_code}): {r.text[:200]}"
        )

    def test_privacy_mode_requires_auth(self):
        # Well-formed payload so the request reaches the auth gate (not input
        # validation): a guessed session id + valid mode, but no action token.
        with _client() as c:
            r = c.post(
                f"{BASE}/api/privacy-mode",
                json={"session_id": "guessed-session-id", "mode": "disabled"},
            )
        assert r.status_code in (401, 403), (
            f"VULN: /api/privacy-mode accepted an unauthenticated request (HTTP {r.status_code}): {r.text[:200]}"
        )

    def test_sampling_config_requires_auth(self):
        with _client() as c:
            r = c.post(
                f"{BASE}/api/sampling-config",
                json={
                    "session_id": "guessed-session-id",
                    "user_email": FAKE_VICTIM,
                    "model": "x",
                    "api_base": "http://evil.example",
                },
            )
        assert r.status_code in (401, 403), (
            f"VULN: /api/sampling-config accepted an unauthenticated request (HTTP {r.status_code}): {r.text[:200]}"
        )

    def test_card_feedback_requires_signature(self):
        """/card-feedback must verify an HMAC-signed URL like /email-feedback does."""
        with _client() as c:
            r = c.get(
                f"{BASE}/card-feedback",
                params={"card_id": "probe-fake", "feedback": "positive"},
            )
        assert r.status_code in (400, 401, 403), (
            f"VULN: /card-feedback accepted an unsigned request (HTTP {r.status_code})"
        )


@pytest.mark.security
class TestOAuthFlow:
    def test_callback_rejects_unknown_state(self):
        """handle_oauth_callback must reject an unknown state instead of fabricating one."""
        with _client() as c:
            r = c.get(
                f"{BASE}/oauth2callback",
                params={"code": "fake-code", "state": "unknown-random-state-xyz"},
            )
        body = r.text.lower()
        # Secure: rejected specifically for invalid/unknown state, NOT forwarded to Google
        # (a "malformed auth code" / invalid_grant error means the fail-open path ran).
        assert "invalid_grant" not in body and "malformed auth code" not in body, (
            "VULN: unknown OAuth state was not rejected; callback proceeded to token exchange (fail-open state)."
        )

    def test_github_callback_escapes_reflected_error(self):
        """GitHub callback must HTML-escape reflected query params (no reflected XSS)."""
        marker = "<script>alert(1)</script>PROBE"
        with _client() as c:
            r = c.get(f"{BASE}/auth/github/callback", params={"error": marker})
        assert marker not in r.text, (
            "VULN: GitHub callback reflected an unescaped <script> payload (reflected XSS)."
        )
