"""FastMCP JWT Bearer Token authentication setup for Google Workspace Platform.

This module provides development-ready JWT authentication with Google email claims.
For production, replace RSAKeyPair with proper certificate infrastructure.
"""

import logging
from typing import Optional, Dict, Any
from pathlib import Path

from fastmcp.server.auth import BearerAuthProvider
from fastmcp.server.auth.providers.bearer import RSAKeyPair

logger = logging.getLogger(__name__)

# Global key pair for development (in production, use proper key management)
_key_pair: Optional[RSAKeyPair] = None
_auth_provider: Optional[BearerAuthProvider] = None

def setup_jwt_auth() -> BearerAuthProvider:
    """Setup JWT authentication for development.
    
    Returns:
        Configured BearerAuthProvider instance
    """
    global _key_pair, _auth_provider
    
    if _auth_provider is not None:
        return _auth_provider
    
    # Generate RSA key pair for development
    _key_pair = RSAKeyPair.generate()
    
    # Configure the auth provider
    _auth_provider = BearerAuthProvider(
        public_key=_key_pair.public_key,
        issuer="https://fastmcp-google-workspace.dev",
        audience="google-workspace-server",
        required_scopes=["google:access"]
    )
    
    logger.info("✅ JWT Bearer Token authentication configured for development")
    logger.info(f"🔑 Public key configured for token validation")
    
    return _auth_provider


def generate_user_token(
    user_email: str,
    scopes: Optional[list[str]] = None,
    expires_in_seconds: int = 3600
) -> str:
    """Generate a JWT token for a specific Google user.
    
    Args:
        user_email: The user's Google email address
        scopes: OAuth scopes to include in token
        expires_in_seconds: Token expiration time in seconds
        
    Returns:
        JWT token string
        
    Raises:
        RuntimeError: If auth is not set up yet
    """
    global _key_pair
    
    if _key_pair is None:
        raise RuntimeError("JWT auth not initialized. Call setup_jwt_auth() first.")
    
    if scopes is None:
        scopes = [
            "google:access",
            "drive:read", 
            "drive:write",
            "gmail:read",
            "gmail:write", 
            "calendar:read",
            "calendar:write",
            "chat:read",
            "chat:write"
        ]
    
    # Create token with user email in additional claims
    token = _key_pair.create_token(
        subject=f"google-user-{user_email}",
        issuer="https://fastmcp-google-workspace.dev",
        audience="google-workspace-server",
        scopes=scopes,
        expires_in_seconds=expires_in_seconds,
        additional_claims={
            "email": user_email,  # This is the key part!
            "google_email": user_email,
            "auth_type": "google_oauth",
            "platform": "fastmcp-google-workspace"
        }
    )
    
    logger.info(f"🎫 Generated JWT token for user: {user_email}")
    logger.debug(f"Token scopes: {scopes}")
    
    return token


def create_test_tokens() -> Dict[str, str]:
    """Create test tokens for development.
    
    Returns:
        Dict mapping user emails to their JWT tokens
    """
    test_users = [
        "sethrivers@riversunlimited.xyz",
        "test@example.com"
    ]
    
    tokens = {}
    for user_email in test_users:
        try:
            token = generate_user_token(user_email)
            tokens[user_email] = token
            logger.info(f"✅ Created test token for {user_email}")
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
        if hasattr(access_token, 'raw_token'):
            import jwt
            
            # Decode without verification to get claims (already verified by FastMCP)
            claims = jwt.decode(access_token.raw_token, options={"verify_signature": False})
            
            user_email = claims.get('email') or claims.get('google_email')
            if user_email:
                logger.debug(f"✅ Got user email from JWT claims: {user_email}")
                return user_email
        
        # Fallback: try to extract from subject
        client_id = access_token.client_id
        if client_id and client_id.startswith("google-user-"):
            user_email = client_id.replace("google-user-", "")
            logger.debug(f"✅ Extracted user email from subject: {user_email}")
            return user_email
            
        raise RuntimeError(f"No email found in JWT token claims or subject: {client_id}")
        
    except Exception as e:
        logger.error(f"❌ Failed to get user email from JWT token: {e}")
        raise RuntimeError(f"Authentication error: Could not extract user email from JWT token: {e}")


if __name__ == "__main__":
    # Development test
    auth_provider = setup_jwt_auth()
    tokens = create_test_tokens()
    
    print("\n🎫 Test JWT Tokens Generated:")
    for email, token in tokens.items():
        print(f"\nUser: {email}")
        print(f"Token: {token[:50]}...")