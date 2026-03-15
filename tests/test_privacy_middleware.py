"""Tests for the privacy middleware — vault, scanner, and middleware integration."""

from __future__ import annotations

import json
import secrets

import pytest

from middleware.privacy.constants import (
    ENCRYPTED_CIPHER_KEY,
    ENCRYPTED_MARKER_KEY,
    PRIVATE_TOKEN_PATTERN,
)
from middleware.privacy.registry import (
    _registry_lock,
    _vault_registry,
    cleanup_expired_vaults,
    destroy_vault,
    get_or_create_vault,
    get_vault,
)
from middleware.privacy.scanner import (
    resolve_tokens_in_value,
    scan_and_encrypt_content,
    scan_and_encrypt_dict,
    scan_and_encrypt_structured,
    scan_and_encrypt_text,
)
from middleware.privacy.vault import PrivacyVault, derive_privacy_vault_key

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_vault(session_id: str = "test-session") -> PrivacyVault:
    """Create a vault with a random key for testing."""
    key = derive_privacy_vault_key(
        session_id,
        auth_material=secrets.token_bytes(32),
        server_secret=b"test-server-secret-for-unit-tests",
    )
    return PrivacyVault(session_id, key)


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------


class TestKeyDerivation:
    def test_deterministic_output(self):
        """Same inputs produce the same key."""
        auth = b"same-auth-material"
        secret = b"same-server-secret"
        k1 = derive_privacy_vault_key("sid1", auth, secret)
        k2 = derive_privacy_vault_key("sid1", auth, secret)
        assert k1 == k2

    def test_different_sessions_different_keys(self):
        auth = b"same-auth-material"
        secret = b"same-server-secret"
        k1 = derive_privacy_vault_key("sid-a", auth, secret)
        k2 = derive_privacy_vault_key("sid-b", auth, secret)
        assert k1 != k2

    def test_different_auth_material_different_keys(self):
        secret = b"same-server-secret"
        k1 = derive_privacy_vault_key("sid", b"auth-a", secret)
        k2 = derive_privacy_vault_key("sid", b"auth-b", secret)
        assert k1 != k2


# ---------------------------------------------------------------------------
# Vault encrypt / decrypt
# ---------------------------------------------------------------------------


class TestVault:
    def test_round_trip(self):
        vault = _make_vault()
        token = vault.encrypt_and_store("alice@example.com", type_hint="email")
        assert token.startswith("[PRIVATE:")
        assert token.endswith("]")

        m = PRIVATE_TOKEN_PATTERN.match(token)
        assert m
        token_id = m.group(1)
        plaintext = vault.decrypt(token_id)
        assert plaintext == "alice@example.com"

    def test_deduplication(self):
        vault = _make_vault()
        t1 = vault.encrypt_and_store("bob@co.com")
        t2 = vault.encrypt_and_store("bob@co.com")
        assert t1 == t2

    def test_different_values_different_tokens(self):
        vault = _make_vault()
        t1 = vault.encrypt_and_store("alice@co.com")
        t2 = vault.encrypt_and_store("bob@co.com")
        assert t1 != t2

    def test_decrypt_unknown_token(self):
        vault = _make_vault()
        assert vault.decrypt("token_999") is None

    def test_ciphertext_b64(self):
        vault = _make_vault()
        vault.encrypt_and_store("secret-value")
        ct = vault.get_ciphertext_b64("token_0")
        assert ct is not None
        assert len(ct) > 0

    def test_stats(self):
        vault = _make_vault()
        vault.encrypt_and_store("v1")
        vault.encrypt_and_store("v2")
        vault.encrypt_and_store("v1")  # dedup
        stats = vault.stats()
        assert stats["tokens_created"] == 2
        assert stats["vault_size"] == 2
        assert stats["mode"] == "encrypted"

    def test_session_isolation(self):
        """Vault A cannot decrypt vault B's tokens."""
        vault_a = _make_vault("session-a")
        vault_b = _make_vault("session-b")

        vault_a.encrypt_and_store("shared-value")
        # vault_b has no token_0
        assert vault_b.decrypt("token_0") is None

    def test_destroy_clears_state(self):
        vault = _make_vault()
        vault.encrypt_and_store("data")
        vault.destroy()
        assert vault.decrypt("token_0") is None
        assert vault.stats()["vault_size"] == 0


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def setup_method(self):
        # Clear registry between tests
        with _registry_lock:
            _vault_registry.clear()

    def test_get_or_create(self):
        key = derive_privacy_vault_key("s1", b"auth", b"secret")
        vault = get_or_create_vault("s1", key)
        assert vault is not None
        assert vault.session_id == "s1"
        # Second call returns same instance
        vault2 = get_or_create_vault("s1", key)
        assert vault is vault2

    def test_get_nonexistent(self):
        assert get_vault("nonexistent") is None

    def test_destroy(self):
        key = derive_privacy_vault_key("s2", b"auth", b"secret")
        get_or_create_vault("s2", key)
        destroy_vault("s2")
        assert get_vault("s2") is None

    def test_cleanup_expired(self):
        key1 = derive_privacy_vault_key("active", b"a", b"s")
        key2 = derive_privacy_vault_key("expired", b"b", b"s")
        get_or_create_vault("active", key1)
        get_or_create_vault("expired", key2)

        cleaned = cleanup_expired_vaults({"active"})
        assert cleaned == 1
        assert get_vault("active") is not None
        assert get_vault("expired") is None


# ---------------------------------------------------------------------------
# Scanner — text
# ---------------------------------------------------------------------------


class TestScannerText:
    def test_email_in_plain_text(self):
        vault = _make_vault()
        result = scan_and_encrypt_text("Contact alice@example.com for info", vault)
        assert "alice@example.com" not in result
        assert "[PRIVATE:" in result

    def test_no_pii_unchanged(self):
        vault = _make_vault()
        text = "This is a normal message with no PII"
        assert scan_and_encrypt_text(text, vault) == text

    def test_multiple_emails(self):
        vault = _make_vault()
        text = "From bob@co.com to alice@co.com about Q3"
        result = scan_and_encrypt_text(text, vault)
        assert "bob@co.com" not in result
        assert "alice@co.com" not in result
        tokens = PRIVATE_TOKEN_PATTERN.findall(result)
        assert len(tokens) == 2


# ---------------------------------------------------------------------------
# Scanner — dict
# ---------------------------------------------------------------------------


class TestScannerDict:
    def test_pii_field_encrypted(self):
        vault = _make_vault()
        data = {"email": "alice@co.com", "subject": "Hello"}
        result = scan_and_encrypt_dict(data, vault)
        assert "[PRIVATE:" in result["email"]
        assert result["subject"] == "Hello"

    def test_nested_dict(self):
        vault = _make_vault()
        data = {"user": {"displayName": "Alice", "id": "123"}}
        result = scan_and_encrypt_dict(data, vault)
        assert "[PRIVATE:" in result["user"]["displayName"]
        assert result["user"]["id"] == "123"

    def test_email_value_in_non_pii_field(self):
        """Email pattern detected in value even if field name is not PII."""
        vault = _make_vault()
        data = {"someField": "contact alice@example.com"}
        result = scan_and_encrypt_dict(data, vault)
        assert "alice@example.com" not in result["someField"]

    def test_list_values(self):
        vault = _make_vault()
        data = {"recipients": ["alice@co.com", "bob@co.com"]}
        result = scan_and_encrypt_dict(data, vault)
        assert all("[PRIVATE:" in v for v in result["recipients"])

    def test_structured_mode(self):
        vault = _make_vault()
        data = {"email": "alice@co.com"}
        result = scan_and_encrypt_dict(data, vault, structured=True)
        assert isinstance(result["email"], dict)
        assert ENCRYPTED_MARKER_KEY in result["email"]
        assert ENCRYPTED_CIPHER_KEY in result["email"]

    def test_additional_fields(self):
        vault = _make_vault()
        data = {"customField": "secret-value", "other": "public"}
        result = scan_and_encrypt_dict(
            data, vault, additional_fields=frozenset({"customField"})
        )
        assert "[PRIVATE:" in result["customField"]
        assert result["other"] == "public"

    def test_strict_mode(self):
        vault = _make_vault()
        data = {"anything": "everything gets encrypted", "num": 42}
        result = scan_and_encrypt_dict(data, vault, strict=True)
        assert "[PRIVATE:" in result["anything"]
        assert result["num"] == 42  # non-strings unchanged


# ---------------------------------------------------------------------------
# Scanner — content blocks
# ---------------------------------------------------------------------------


class TestScannerContent:
    def test_json_text_content(self):
        from mcp.types import TextContent

        vault = _make_vault()
        content = [
            TextContent(
                type="text",
                text=json.dumps({"from": "bob@co.com", "subject": "Hi"}),
            )
        ]
        result = scan_and_encrypt_content(content, vault)
        parsed = json.loads(result[0].text)
        assert "bob@co.com" not in parsed["from"]
        assert parsed["subject"] == "Hi"

    def test_plain_text_content(self):
        from mcp.types import TextContent

        vault = _make_vault()
        content = [TextContent(type="text", text="Email from alice@co.com")]
        result = scan_and_encrypt_content(content, vault)
        assert "alice@co.com" not in result[0].text
        assert "[PRIVATE:" in result[0].text


# ---------------------------------------------------------------------------
# Scanner — structured content
# ---------------------------------------------------------------------------


class TestScannerStructured:
    def test_dict_produces_sentinels(self):
        vault = _make_vault()
        data = {"sender": "bob@co.com", "subject": "Q3 Report"}
        result = scan_and_encrypt_structured(data, vault)
        assert isinstance(result["sender"], dict)
        assert result["sender"][ENCRYPTED_MARKER_KEY].startswith("token_")
        assert result["sender"][ENCRYPTED_CIPHER_KEY]
        assert result["subject"] == "Q3 Report"


# ---------------------------------------------------------------------------
# Token resolution (Phase A)
# ---------------------------------------------------------------------------


class TestTokenResolution:
    def test_resolve_in_string(self):
        vault = _make_vault()
        token = vault.encrypt_and_store("alice@example.com")
        resolved = resolve_tokens_in_value(token, vault)
        assert resolved == "alice@example.com"

    def test_resolve_in_dict(self):
        vault = _make_vault()
        token = vault.encrypt_and_store("bob@co.com")
        data = {"to": token, "subject": "Hi"}
        resolved = resolve_tokens_in_value(data, vault)
        assert resolved["to"] == "bob@co.com"
        assert resolved["subject"] == "Hi"

    def test_resolve_in_list(self):
        vault = _make_vault()
        t1 = vault.encrypt_and_store("a@co.com")
        t2 = vault.encrypt_and_store("b@co.com")
        resolved = resolve_tokens_in_value([t1, t2], vault)
        assert resolved == ["a@co.com", "b@co.com"]

    def test_unknown_token_left_in_place(self):
        vault = _make_vault()
        text = "Send to [PRIVATE:token_999]"
        resolved = resolve_tokens_in_value(text, vault)
        assert resolved == text  # unresolvable token left as-is

    def test_mixed_text_with_tokens(self):
        vault = _make_vault()
        token = vault.encrypt_and_store("alice@co.com")
        text = f"Message to {token} about Q3"
        resolved = resolve_tokens_in_value(text, vault)
        assert resolved == "Message to alice@co.com about Q3"
