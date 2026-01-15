"""
PKCE (Proof Key for Code Exchange) utilities for OAuth 2.1 flows.

This module provides utilities for generating and validating PKCE parameters
as defined in RFC 7636, enhancing security for OAuth flows.
"""

import base64
import hashlib
import secrets

from typing_extensions import Any, Dict, Tuple

from config.enhanced_logging import setup_logger

logger = setup_logger()


def generate_code_verifier(length: int = 128) -> str:
    """
    Generate a cryptographically random code verifier for PKCE.

    Args:
        length: Length of the code verifier (43-128 characters)

    Returns:
        URL-safe base64-encoded code verifier string

    Raises:
        ValueError: If length is not between 43 and 128
    """
    if not 43 <= length <= 128:
        raise ValueError("Code verifier length must be between 43 and 128 characters")

    # Generate random bytes (length * 3/4 bytes for base64 encoding)
    random_bytes = secrets.token_bytes(length * 3 // 4)

    # Base64 URL-safe encode and remove padding
    code_verifier = base64.urlsafe_b64encode(random_bytes).decode("utf-8").rstrip("=")

    # Ensure exact length
    code_verifier = code_verifier[:length]

    logger.debug(
        f"Generated PKCE code verifier: {code_verifier[:10]}... (length: {len(code_verifier)})"
    )
    return code_verifier


def generate_code_challenge(code_verifier: str, method: str = "S256") -> str:
    """
    Generate a code challenge from a code verifier.

    Args:
        code_verifier: The code verifier string
        method: Challenge method ("S256" or "plain")

    Returns:
        Code challenge string

    Raises:
        ValueError: If method is not supported
    """
    if method == "S256":
        # SHA256 hash and base64 URL-safe encode
        digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    elif method == "plain":
        # Plain text (not recommended for security)
        code_challenge = code_verifier
    else:
        raise ValueError(f"Unsupported code challenge method: {method}")

    logger.debug(
        f"Generated PKCE code challenge using {method}: {code_challenge[:10]}..."
    )
    return code_challenge


def generate_pkce_pair(length: int = 128, method: str = "S256") -> Tuple[str, str]:
    """
    Generate a complete PKCE code verifier and challenge pair.

    Args:
        length: Length of the code verifier (43-128 characters)
        method: Challenge method ("S256" or "plain")

    Returns:
        Tuple of (code_verifier, code_challenge)
    """
    code_verifier = generate_code_verifier(length)
    code_challenge = generate_code_challenge(code_verifier, method)

    logger.info(f"Generated PKCE pair using {method} method")
    return code_verifier, code_challenge


def validate_code_verifier(
    code_verifier: str, code_challenge: str, method: str = "S256"
) -> bool:
    """
    Validate that a code verifier matches the code challenge.

    Args:
        code_verifier: The code verifier to validate
        code_challenge: The expected code challenge
        method: Challenge method used ("S256" or "plain")

    Returns:
        True if the code verifier is valid, False otherwise
    """
    try:
        expected_challenge = generate_code_challenge(code_verifier, method)
        is_valid = secrets.compare_digest(expected_challenge, code_challenge)

        logger.debug(f"PKCE validation result: {'VALID' if is_valid else 'INVALID'}")
        return is_valid
    except Exception as e:
        logger.error(f"PKCE validation error: {e}")
        return False


def create_authorization_params(
    client_id: str,
    redirect_uri: str,
    scope: str,
    state: str = None,
    use_pkce: bool = True,
) -> Dict[str, Any]:
    """
    Create authorization URL parameters with optional PKCE.

    Args:
        client_id: OAuth client ID
        redirect_uri: Redirect URI for callback
        scope: OAuth scopes (space-separated)
        state: Optional state parameter
        use_pkce: Whether to include PKCE parameters

    Returns:
        Dictionary of authorization parameters including PKCE if enabled
    """
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
    }

    if state:
        params["state"] = state

    pkce_data = None
    if use_pkce:
        code_verifier, code_challenge = generate_pkce_pair()
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"

        # Return PKCE data separately for storage
        pkce_data = {
            "code_verifier": code_verifier,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        logger.info(f"Created authorization params with PKCE for client: {client_id}")
    else:
        logger.info(
            f"Created authorization params without PKCE for client: {client_id}"
        )

    return {"params": params, "pkce_data": pkce_data}


class PKCEManager:
    """
    Manager class for handling PKCE parameters throughout OAuth flows.

    This class provides a convenient interface for generating, storing,
    and retrieving PKCE parameters during OAuth authorization flows.
    """

    def __init__(self):
        self._storage = {}

    def create_pkce_session(
        self, session_id: str, method: str = "S256"
    ) -> Dict[str, str]:
        """
        Create a new PKCE session with generated parameters.

        Args:
            session_id: Unique session identifier
            method: PKCE challenge method

        Returns:
            Dictionary with code_challenge and method for authorization URL
        """
        code_verifier, code_challenge = generate_pkce_pair(method=method)

        self._storage[session_id] = {
            "code_verifier": code_verifier,
            "code_challenge": code_challenge,
            "code_challenge_method": method,
        }

        logger.info(f"Created PKCE session: {session_id}")

        return {"code_challenge": code_challenge, "code_challenge_method": method}

    def get_code_verifier(self, session_id: str) -> str:
        """
        Retrieve the code verifier for a session.

        Args:
            session_id: Session identifier

        Returns:
            Code verifier string

        Raises:
            KeyError: If session not found
        """
        if session_id not in self._storage:
            raise KeyError(f"PKCE session not found: {session_id}")

        return self._storage[session_id]["code_verifier"]

    def validate_and_consume(self, session_id: str, code_challenge: str) -> str:
        """
        Validate a session and consume the PKCE parameters.

        Args:
            session_id: Session identifier
            code_challenge: Expected code challenge

        Returns:
            Code verifier for token exchange

        Raises:
            KeyError: If session not found
            ValueError: If validation fails
        """
        if session_id not in self._storage:
            raise KeyError(f"PKCE session not found: {session_id}")

        session_data = self._storage[session_id]
        stored_challenge = session_data["code_challenge"]

        if not secrets.compare_digest(stored_challenge, code_challenge):
            raise ValueError("PKCE code challenge validation failed")

        # Consume the session (remove it)
        code_verifier = session_data["code_verifier"]
        del self._storage[session_id]

        logger.info(f"PKCE session validated and consumed: {session_id}")
        return code_verifier

    def cleanup_expired_sessions(self, max_age_seconds: int = 3600):
        """
        Clean up expired PKCE sessions.

        Args:
            max_age_seconds: Maximum age of sessions to keep
        """
        # Note: This is a simple implementation. In production, you'd want
        # to store creation timestamps and implement proper cleanup.
        logger.debug(
            f"PKCE session cleanup not implemented (sessions: {len(self._storage)})"
        )


# Global PKCE manager instance
pkce_manager = PKCEManager()
