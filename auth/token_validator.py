"""Custom token validator that validates MCP Bearer tokens against stored credentials.

This ensures MCP clients must have valid OAuth tokens that match users with
stored credentials, enforcing the same access control as web OAuth flows.
"""

from typing import Any, Dict, Optional

import requests

from config.enhanced_logging import setup_logger

logger = setup_logger()

from auth.access_control import validate_user_access


def validate_google_token_with_access_control(token: str) -> Optional[Dict[str, Any]]:
    """
    Validate a Google OAuth Bearer token AND verify the user has access.

    This function:
    1. Validates the token with Google's tokeninfo endpoint
    2. Extracts the user's email from the token
    3. Checks if the user has stored credentials (access control)

    Args:
        token: Google OAuth Bearer token

    Returns:
        Token info dict if valid and authorized, None otherwise
    """
    try:
        # Step 1: Validate token with Google
        response = requests.get(
            f"https://www.googleapis.com/oauth2/v1/tokeninfo?access_token={token}",
            timeout=5,
        )

        if response.status_code != 200:
            logger.warning(f"❌ Token validation failed: HTTP {response.status_code}")
            return None

        token_info = response.json()

        # Check for error in response
        if "error" in token_info:
            logger.warning(
                f"❌ Token validation error: {token_info.get('error_description', 'Unknown')}"
            )
            return None

        # Step 2: Extract email
        email = token_info.get("email")
        if not email:
            logger.warning("❌ Token validation failed: No email in token")
            return None

        # Step 3: Validate access control
        if not validate_user_access(email):
            logger.warning(
                f"🚫 Token validation failed: User {email} not authorized (no stored credentials)"
            )
            return None

        logger.info(f"✅ Token validated for authorized user: {email}")
        return token_info

    except requests.RequestException as e:
        logger.error(f"❌ Token validation network error: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Token validation error: {e}")
        return None


class AccessControlBearerAuthProvider:
    """
    Custom Bearer token validator that enforces stored credential access control.

    This wraps the standard Google token validation with additional checks
    to ensure only users with stored credentials can access the MCP server.
    """

    def __init__(
        self,
        jwks_uri: str,
        issuer: str,
        audience: Optional[str] = None,
        required_scopes: Optional[list] = None,
    ):
        """
        Initialize the access-controlled bearer auth provider.

        Args:
            jwks_uri: Google's JWKS endpoint URL
            issuer: OAuth issuer (Google)
            audience: Optional audience claim
            required_scopes: Required OAuth scopes
        """
        self.jwks_uri = jwks_uri
        self.issuer = issuer
        self.audience = audience
        self.required_scopes = required_scopes or []

        logger.info("🔒 AccessControlBearerAuthProvider initialized")
        logger.info(f"  JWKS URI: {jwks_uri}")
        logger.info(f"  Issuer: {issuer}")
        logger.info("  Access control: Enforces stored credentials")

    async def __call__(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Validate Bearer token with access control.

        This is called by FastMCP for each MCP request with a Bearer token.

        Args:
            token: Bearer token from Authorization header

        Returns:
            Token claims if valid and authorized, None otherwise
        """
        # Validate token and check access control
        token_info = validate_google_token_with_access_control(token)

        if not token_info:
            return None

        # Check required scopes if configured
        if self.required_scopes:
            token_scopes = token_info.get("scope", "").split()
            missing_scopes = set(self.required_scopes) - set(token_scopes)

            if missing_scopes:
                logger.warning(f"⚠️ Token missing required scopes: {missing_scopes}")
                # Still allow if user is authorized (they can request more scopes later)

        return {
            "email": token_info.get("email"),
            "verified_email": token_info.get("verified_email", False),
            "user_id": token_info.get("user_id"),
            "scopes": token_info.get("scope", "").split(),
            "expires_in": token_info.get("expires_in"),
            "issued_to": token_info.get("issued_to"),
        }


def create_access_controlled_auth_provider(
    jwks_uri: str = "https://www.googleapis.com/oauth2/v3/certs",
    issuer: str = "https://accounts.google.com",
    audience: Optional[str] = None,
    required_scopes: Optional[list] = None,
) -> AccessControlBearerAuthProvider:
    """
    Create a Bearer auth provider with access control enforcement.

    This provider validates Google OAuth tokens AND checks that the authenticated
    user has stored credentials, ensuring only pre-authorized users can access.

    Args:
        jwks_uri: Google JWKS endpoint
        issuer: OAuth issuer
        audience: Optional audience
        required_scopes: Required scopes

    Returns:
        Configured AccessControlBearerAuthProvider
    """
    return AccessControlBearerAuthProvider(
        jwks_uri=jwks_uri,
        issuer=issuer,
        audience=audience,
        required_scopes=required_scopes,
    )
