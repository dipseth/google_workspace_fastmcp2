"""Enhanced tools that use resource templating instead of manual user_google_email parameters.

This module demonstrates the new pattern for tools that automatically get the
authenticated user's email from resources instead of requiring it as a parameter.
"""

import logging
from typing_extensions import List, Optional

from fastmcp import FastMCP
from resources.user_resources import get_current_user_email_simple
from auth.context import request_google_service, get_injected_service
from auth.google_auth import get_all_stored_users

logger = logging.getLogger(__name__)


async def _detect_authenticated_user() -> Optional[str]:
    """Detect authenticated user when session context is unavailable.
    
    This fallback method tries to find a valid authenticated user
    by checking stored credentials.
    
    Returns:
        Email of authenticated user or None if none found
    """
    try:
        # Get all users with stored credentials
        stored_users = get_all_stored_users()
        
        if not stored_users:
            logger.warning("No stored users found")
            return None
            
        # For now, use the first valid user (could be enhanced to be smarter)
        from auth.google_auth import get_valid_credentials
        
        for user_email in stored_users:
            credentials = get_valid_credentials(user_email)
            if credentials and not credentials.expired:
                logger.info(f"Found valid credentials for user: {user_email}")
                return user_email
                
        # If no non-expired credentials, try the first user anyway
        # (credentials might be refreshable)
        first_user = stored_users[0]
        logger.info(f"Using first stored user as fallback: {first_user}")
        return first_user
        
    except Exception as e:
        logger.error(f"Error detecting authenticated user: {e}")
        return None


def setup_enhanced_tools(mcp: FastMCP) -> None:
    """Setup enhanced tools that use resource templating."""
    

    @mcp.tool()
    async def get_my_auth_status() -> str:
        """Get the current user's authentication status and available services.
        
        This tool demonstrates how to use multiple resource templates.
        
        Returns:
            Detailed authentication status
        """
        try:
            # Try to get user email from resource context first
            try:
                user_email = get_current_user_email_simple()
                logger.info(f"✅ Got user email from context: {user_email}")
            except ValueError:
                # Fallback: Extract email from available credentials
                logger.warning("⚠️ No user context available, attempting to detect authenticated user...")
                user_email = await _detect_authenticated_user()
                if not user_email:
                    return "❌ Authentication error: No authenticated user found in current session. Please ensure the user is authenticated with start_google_auth tool first."
            
            # Import here to avoid circular imports
            from auth.google_auth import get_valid_credentials
            from auth.service_helpers import SERVICE_DEFAULTS
            
            # Check credentials
            credentials = get_valid_credentials(user_email)
            
            if not credentials:
                return f"❌ No valid credentials found for {user_email}. Please authenticate first."
            
            # Build comprehensive status
            auth_info = {
                "user_email": user_email,
                "authenticated": True,
                "credentials_valid": not credentials.expired,
                "expires_at": credentials.expiry.isoformat() if credentials.expiry else None,
                "scopes": credentials.scopes or [],
                "available_services": list(SERVICE_DEFAULTS.keys()),
                "has_refresh_token": credentials.refresh_token is not None
            }
            
            if credentials.expired:
                auth_info["status"] = "Credentials expired but can be refreshed"
            else:
                auth_info["status"] = "Fully authenticated and ready"
            
            return f"✅ Authentication status for {user_email}:\n\n{auth_info}"
            
        except ValueError as e:
            return f"❌ Authentication error: {str(e)}"
        except Exception as e:
            logger.error(f"Error checking auth status: {e}")
            return f"❌ Error checking authentication: {str(e)}"
    
    logger.info("✅ Enhanced tools with resource templating registered")


# Helper function for backwards compatibility
def get_user_email_from_context_or_param(user_google_email: Optional[str] = None) -> str:
    """Helper function for gradual migration of existing tools.
    
    This function allows tools to work with both the old pattern (passing user_google_email)
    and the new pattern (using resource context). Useful during migration period.
    
    Args:
        user_google_email: Optional user email parameter (legacy pattern)
    
    Returns:
        User email from parameter or context
        
    Raises:
        ValueError: If no user email available from either source
    """
    if user_google_email:
        # Legacy pattern: use provided parameter
        return user_google_email
    
    try:
        # New pattern: get from resource context
        return get_current_user_email_simple()
    except ValueError:
        raise ValueError(
            "No user email available. Either pass user_google_email parameter "
            "or ensure user is authenticated in current session."
        )