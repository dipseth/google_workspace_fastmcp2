"""Sensitive value detection and recursive encrypt/mask for tool responses.

Two composable strategies:
1. **Field-name heuristics** — zero-config, matches known PII field names.
2. **Value-pattern regex** — catches email addresses regardless of field name.

Provides ``scan_and_encrypt`` (Phase B outbound) and ``resolve_tokens``
(Phase A inbound) for the PrivacyMiddleware.
"""

from __future__ import annotations

import json
from typing import Any

from config.enhanced_logging import setup_logger
from middleware.privacy.constants import (
    ENCRYPTED_CIPHER_KEY,
    ENCRYPTED_MARKER_KEY,
    PRIVACY_FIELD_PATTERNS,
    PRIVACY_VALUE_PATTERNS,
    PRIVATE_TOKEN_PATTERN,
)
from middleware.privacy.vault import PrivacyVault

logger = setup_logger()

def _is_privacy_field(key: str) -> bool:
    """Check if a dict key matches a known PII field name."""
    return key in PRIVACY_FIELD_PATTERNS

def _contains_pii_value(value: str) -> bool:
    """Check if a string value matches any PII regex pattern."""
    return any(p.search(value) for p in PRIVACY_VALUE_PATTERNS)

def _encrypt_value(value: str, vault: PrivacyVault, type_hint: str = "") -> str:
    """Encrypt a single string value, returning the masked token."""
    return vault.encrypt_and_store(value, type_hint=type_hint)

def _encrypt_value_structured(
    value: str, vault: PrivacyVault, type_hint: str = ""
) -> dict:
    """Encrypt a value and return the structured sentinel dict."""
    token_str = vault.encrypt_and_store(value, type_hint=type_hint)
    # Extract token_id from "[PRIVATE:token_N]"
    m = PRIVATE_TOKEN_PATTERN.match(token_str)
    token_id = m.group(1) if m else token_str
    ct_b64 = vault.get_ciphertext_b64(token_id)
    return {
        ENCRYPTED_MARKER_KEY: token_id,
        ENCRYPTED_CIPHER_KEY: ct_b64 or "",
    }

# ------------------------------------------------------------------
# Phase B: scan_and_encrypt (outbound — tool response → masked)
# ------------------------------------------------------------------

def scan_and_encrypt_text(text: str, vault: PrivacyVault) -> str:
    """Replace PII values in a plain-text string with masked tokens."""
    result = text
    for pattern in PRIVACY_VALUE_PATTERNS:
        for match in pattern.finditer(text):
            pii_value = match.group(0)
            masked = _encrypt_value(pii_value, vault, type_hint="email")
            result = result.replace(pii_value, masked)
    return result

def scan_and_encrypt_dict(
    data: dict,
    vault: PrivacyVault,
    *,
    structured: bool = False,
    additional_fields: frozenset[str] | None = None,
    strict: bool = False,
) -> dict:
    """Recursively scan a dict, encrypting sensitive values.

    Args:
        data: The dict to scan.
        vault: Session-scoped PrivacyVault.
        structured: If True, produce ``{__private, __enc}`` sentinel dicts
                    instead of ``[PRIVATE:token_N]`` strings.
        additional_fields: Extra field names to treat as PII.
        strict: If True, encrypt ALL string values (strict mode).
    """
    out: dict = {}
    effective_fields = PRIVACY_FIELD_PATTERNS
    if additional_fields:
        effective_fields = effective_fields | additional_fields

    for key, value in data.items():
        is_pii_key = key in effective_fields

        if isinstance(value, str):
            if strict or is_pii_key or _contains_pii_value(value):
                if structured:
                    out[key] = _encrypt_value_structured(
                        value, vault, type_hint=key if is_pii_key else ""
                    )
                else:
                    out[key] = _encrypt_value(
                        value, vault, type_hint=key if is_pii_key else ""
                    )
            else:
                out[key] = value
        elif isinstance(value, dict):
            out[key] = scan_and_encrypt_dict(
                value,
                vault,
                structured=structured,
                additional_fields=additional_fields,
                strict=strict,
            )
        elif isinstance(value, list):
            out[key] = scan_and_encrypt_list(
                value,
                vault,
                structured=structured,
                additional_fields=additional_fields,
                strict=strict,
                parent_key=key,
            )
        else:
            out[key] = value
    return out

def scan_and_encrypt_list(
    data: list,
    vault: PrivacyVault,
    *,
    structured: bool = False,
    additional_fields: frozenset[str] | None = None,
    strict: bool = False,
    parent_key: str = "",
) -> list:
    """Recursively scan a list, encrypting sensitive values."""
    out: list = []
    is_pii_parent = parent_key in PRIVACY_FIELD_PATTERNS

    for item in data:
        if isinstance(item, str):
            if strict or is_pii_parent or _contains_pii_value(item):
                if structured:
                    out.append(
                        _encrypt_value_structured(item, vault, type_hint=parent_key)
                    )
                else:
                    out.append(_encrypt_value(item, vault, type_hint=parent_key))
            else:
                out.append(item)
        elif isinstance(item, dict):
            out.append(
                scan_and_encrypt_dict(
                    item,
                    vault,
                    structured=structured,
                    additional_fields=additional_fields,
                    strict=strict,
                )
            )
        elif isinstance(item, list):
            out.append(
                scan_and_encrypt_list(
                    item,
                    vault,
                    structured=structured,
                    additional_fields=additional_fields,
                    strict=strict,
                )
            )
        else:
            out.append(item)
    return out

def scan_and_encrypt_content(
    content: list,
    vault: PrivacyVault,
    *,
    additional_fields: frozenset[str] | None = None,
    strict: bool = False,
) -> list:
    """Scan ToolResult.content (list of TextContent blocks), encrypting PII.

    TextContent blocks may contain plain text or JSON-encoded text.
    JSON text is parsed, recursively scanned, and re-serialized.
    """
    from mcp.types import TextContent

    masked: list = []
    for block in content:
        if not isinstance(block, TextContent):
            masked.append(block)
            continue

        text = block.text
        # Try JSON parse first — many tool responses embed JSON in text
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                encrypted = scan_and_encrypt_dict(
                    parsed,
                    vault,
                    structured=False,
                    additional_fields=additional_fields,
                    strict=strict,
                )
                masked.append(TextContent(type="text", text=json.dumps(encrypted)))
                continue
            elif isinstance(parsed, list):
                encrypted = scan_and_encrypt_list(
                    parsed,
                    vault,
                    structured=False,
                    additional_fields=additional_fields,
                    strict=strict,
                )
                masked.append(TextContent(type="text", text=json.dumps(encrypted)))
                continue
        except (json.JSONDecodeError, TypeError):
            pass

        # Plain text — apply value-pattern regex
        masked_text = scan_and_encrypt_text(text, vault)
        masked.append(TextContent(type="text", text=masked_text))

    return masked

def scan_and_encrypt_structured(
    data: Any,
    vault: PrivacyVault,
    *,
    additional_fields: frozenset[str] | None = None,
    strict: bool = False,
) -> Any:
    """Scan structured_content, producing ``{__private, __enc}`` sentinels."""
    if isinstance(data, dict):
        return scan_and_encrypt_dict(
            data,
            vault,
            structured=True,
            additional_fields=additional_fields,
            strict=strict,
        )
    if isinstance(data, list):
        return scan_and_encrypt_list(
            data,
            vault,
            structured=True,
            additional_fields=additional_fields,
            strict=strict,
        )
    if isinstance(data, str):
        if strict or _contains_pii_value(data):
            return _encrypt_value_structured(data, vault)
    return data

# ------------------------------------------------------------------
# Phase A: resolve_tokens (inbound — [PRIVATE:token_N] → plaintext)
# ------------------------------------------------------------------

def resolve_tokens_in_value(value: Any, vault: PrivacyVault) -> Any:
    """Recursively resolve ``[PRIVATE:token_N]`` tokens back to plaintext."""
    if isinstance(value, str):
        return _resolve_string_tokens(value, vault)
    if isinstance(value, dict):
        return {k: resolve_tokens_in_value(v, vault) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_tokens_in_value(item, vault) for item in value]
    return value

def _resolve_string_tokens(text: str, vault: PrivacyVault) -> str:
    """Replace all ``[PRIVATE:token_N]`` in *text* with decrypted plaintext."""
    resolution_errors: list[str] = []

    def _replace(match):
        token_id = match.group(1)
        plaintext = vault.decrypt(token_id)
        if plaintext is None:
            resolution_errors.append(token_id)
            return match.group(0)  # leave token in place
        return plaintext

    result = PRIVATE_TOKEN_PATTERN.sub(_replace, text)
    if resolution_errors:
        logger.warning(
            "Privacy: could not resolve tokens %s (session=%s)",
            resolution_errors,
            vault.session_id,
        )
    return result
