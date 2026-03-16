"""Privacy middleware — encryption-first PII protection for tool responses.

Provides session-scoped Fernet encryption of sensitive values in tool responses,
with cosmetic masking ([PRIVATE:token_N]) for LLM-facing content and encrypted
ciphertext in structured_content for round-trip capability.
"""

from middleware.privacy.middleware import PrivacyMiddleware
from middleware.privacy.vault import PrivacyVault

__all__ = ["PrivacyMiddleware", "PrivacyVault"]
