"""FastMCP JWT Bearer Token authentication setup for Google Workspace Platform.

This module provides development-ready JWT authentication with Google email claims.
For production, replace RSAKeyPair with proper certificate infrastructure.
Updated to use FastMCP 2's JWTVerifier pattern and centralized scope registry.
"""

# FastMCP 2 JWT verification imports
from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair
from typing_extensions import Dict, List, Optional, Union

# Import centralized scope registry
from auth.scope_registry import ScopeRegistry
from config.enhanced_logging import setup_logger

logger = setup_logger()

# Global key pair for development (in production, use proper key management)
_key_pair: Optional[RSAKeyPair] = None
_auth_provider: Optional[JWTVerifier] = None


def setup_jwt_auth() -> JWTVerifier:
    """Setup JWT authentication for development using FastMCP 2's JWTVerifier.

    Returns:
        Configured JWTVerifier instance
    """
    global _key_pair, _auth_provider

    if _auth_provider is not None:
        return _auth_provider

    # Generate RSA key pair for development
    _key_pair = RSAKeyPair.generate()

    # Get required scopes from the registry - using the base Google access scope
    # This maintains backward compatibility with the original ["google:access"] requirement
    base_scopes = [
        ScopeRegistry.GOOGLE_API_SCOPES["base"]["userinfo_email"],
        ScopeRegistry.GOOGLE_API_SCOPES["base"]["openid"],
    ]

    # Configure the JWT verifier using FastMCP 2 pattern
    _auth_provider = JWTVerifier(
        public_key=_key_pair.public_key,
        issuer="https://fastmcp-google-workspace.dev",
        audience="google-workspace-server",
        required_scopes=base_scopes,  # Using registry scopes instead of hardcoded
    )

    logger.info("✅ JWT authentication configured using FastMCP 2 JWTVerifier")
    logger.info("🔑 Public key configured for token validation")
    logger.info(f"📋 Required scopes from registry: {base_scopes}")

    return _auth_provider


def generate_user_token(
    user_email: str,
    scopes: Optional[Union[List[str], str]] = None,
    expires_in_seconds: int = 3600,
) -> str:
    """Generate a JWT token for a specific Google user.

    Args:
        user_email: The user's Google email address
        scopes: OAuth scopes to include in token. Can be:
            - None: Uses comprehensive OAuth scopes from registry
            - List[str]: List of scope URLs or registry references
            - str: Name of a scope group from the registry
        expires_in_seconds: Token expiration time in seconds

    Returns:
        JWT token string

    Raises:
        RuntimeError: If auth is not set up yet
    """
    global _key_pair

    if _key_pair is None:
        raise RuntimeError("JWT auth not initialized. Call setup_jwt_auth() first.")

    # Use scope registry to get scopes instead of hardcoded values
    if scopes is None:
        # Default to comprehensive OAuth scopes for development tokens
        # This provides broad access similar to the previous hardcoded scopes
        resolved_scopes = ScopeRegistry.resolve_scope_group("oauth_comprehensive")
        logger.debug("Using comprehensive OAuth scopes from registry")
    elif isinstance(scopes, str):
        # If a string is provided, treat it as a scope group name
        try:
            resolved_scopes = ScopeRegistry.resolve_scope_group(scopes)
            logger.debug(f"Resolved scope group '{scopes}' from registry")
        except ValueError:
            # If not a valid group, treat as a single scope URL
            resolved_scopes = [scopes]
            logger.debug(f"Using single scope: {scopes}")
    else:
        # For list of scopes, resolve any registry references
        resolved_scopes = []
        for scope in scopes:
            if scope.startswith("http"):
                # Direct scope URL
                resolved_scopes.append(scope)
            elif "." in scope:
                # Registry reference like "drive.full"
                try:
                    service, scope_name = scope.split(".", 1)
                    if (
                        service in ScopeRegistry.GOOGLE_API_SCOPES
                        and scope_name in ScopeRegistry.GOOGLE_API_SCOPES[service]
                    ):
                        resolved_scopes.append(
                            ScopeRegistry.GOOGLE_API_SCOPES[service][scope_name]
                        )
                    else:
                        # Fallback to treating as direct scope
                        resolved_scopes.append(scope)
                except ValueError:
                    resolved_scopes.append(scope)
            else:
                # Assume it's a direct scope
                resolved_scopes.append(scope)
        logger.debug(f"Resolved {len(scopes)} scopes to {len(resolved_scopes)} URLs")

    # Create token with user email in additional claims
    token = _key_pair.create_token(
        subject=f"google-user-{user_email}",
        issuer="https://fastmcp-google-workspace.dev",
        audience="google-workspace-server",
        scopes=resolved_scopes,
        expires_in_seconds=expires_in_seconds,
        additional_claims={
            "email": user_email,  # This is the key part!
            "google_email": user_email,
            "auth_type": "google_oauth",
            "platform": "fastmcp-google-workspace",
        },
    )

    logger.info(f"🎫 Generated JWT token for user: {user_email}")
    logger.debug(f"Token includes {len(resolved_scopes)} scopes from registry")

    return token


def create_test_tokens() -> Dict[str, str]:
    """Create test tokens for development using scope registry.

    Returns:
        Dict mapping user emails to their JWT tokens with comprehensive scopes
    """
    test_users = ["sethrivers@riversunlimited.xyz", "test@example.com"]

    tokens = {}
    for user_email in test_users:
        try:
            # Use comprehensive OAuth scopes from registry for test tokens
            token = generate_user_token(
                user_email,
                scopes="oauth_comprehensive",  # Using scope group from registry
            )
            tokens[user_email] = token
            logger.info(
                f"✅ Created test token for {user_email} with comprehensive scopes"
            )
        except Exception as e:
            logger.error(f"❌ Failed to create token for {user_email}: {e}")

    return tokens


def get_user_email_from_token() -> str:
    """Get user email from current JWT token context.

    This is the replacement for get_current_user_email_simple() that
    works with JWT token claims instead of session context.

    Returns:
        User's email address from JWT claims

    Raises:
        RuntimeError: If no token or no email claim found
    """
    from fastmcp.server.dependencies import get_access_token

    try:
        access_token = get_access_token()

        # Try to get email from additional claims
        if hasattr(access_token, "raw_token"):
            import jwt

            # Decode without verification to get claims (already verified by FastMCP)
            claims = jwt.decode(
                access_token.raw_token, options={"verify_signature": False}
            )

            user_email = claims.get("email") or claims.get("google_email")
            if user_email:
                logger.debug(f"✅ Got user email from JWT claims: {user_email}")
                return user_email

        # Fallback: try to extract from subject
        client_id = access_token.client_id
        if client_id and client_id.startswith("google-user-"):
            user_email = client_id.replace("google-user-", "")
            logger.debug(f"✅ Extracted user email from subject: {user_email}")
            return user_email

        raise RuntimeError(
            f"No email found in JWT token claims or subject: {client_id}"
        )

    except Exception as e:
        logger.error(f"❌ Failed to get user email from JWT token: {e}")
        raise RuntimeError(
            f"Authentication error: Could not extract user email from JWT token: {e}"
        )


if __name__ == "__main__":
    # Development test using FastMCP 2 JWTVerifier and scope registry
    auth_verifier = setup_jwt_auth()
    tokens = create_test_tokens()

    print("\n🎫 Test JWT Tokens Generated with Scope Registry:")
    print(f"Verifier Type: {type(auth_verifier).__name__}")
    print(f"Issuer: {auth_verifier.issuer}")
    print(f"Audience: {auth_verifier.audience}")

    for email, token in tokens.items():
        print(f"\nUser: {email}")
        print(f"Token (first 50 chars): {token[:50]}...")

        # Demonstrate scope group usage
        print("\n📋 Available Scope Groups:")
        for group_name in [
            "drive_basic",
            "gmail_basic",
            "calendar_basic",
            "office_suite",
        ]:
            scopes = ScopeRegistry.resolve_scope_group(group_name)
            print(f"  - {group_name}: {len(scopes)} scopes")
