"""JWT-enhanced Google Chat tools that use FastMCP Bearer Token authentication.

This module demonstrates the new JWT authentication pattern where user email
is extracted from JWT token claims instead of requiring parameters.
"""

import logging
import asyncio
from typing_extensions import Optional, List

from fastmcp import FastMCP
from googleapiclient.errors import HttpError

from auth.jwt_auth import get_user_email_from_token
from auth.service_helpers import get_service
from resources.user_resources import get_current_user_email_simple

# Import type definitions
from .chat_types import JWTSpaceInfo, JWTSpacesResponse

logger = logging.getLogger(__name__)


def setup_jwt_chat_tools(mcp: FastMCP) -> None:
    """Setup JWT-enhanced Chat tools that get user email from token claims."""
    
    @mcp.tool(
        name="list_spaces_jwt",
        description="List Google Chat spaces using JWT authentication - no email parameter needed!",
        tags={"jwt", "chat", "spaces", "authentication"},
        annotations={
            "title": "List Chat Spaces (JWT Auth)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def list_spaces_jwt(
        user_google_email: Optional[str] = None,
        page_size: int = 100,
        space_type: str = "all"
    ) -> JWTSpacesResponse:
        """
        Lists Google Chat spaces using multiple authentication methods.
        
        🎯 ENHANCED: Gets user email automatically from resources or JWT token!
        user_google_email parameter is now optional.
        
        Args:
            user_google_email: User's Google email address (optional - will auto-detect if not provided)
            page_size: Number of spaces to return (default: 100)
            space_type: Filter by space type: "all", "room", or "dm" (default: "all")
            
        Returns:
            JWTSpacesResponse: Structured list of Google Chat spaces accessible to the authenticated user
        """
        try:
            # 🎯 Multi-method email detection
            user_email = None
            auth_method = "unknown"
            
            # Method 1: Use provided email if given
            if user_google_email and user_google_email.strip():
                user_email = user_google_email.strip()
                auth_method = "provided_parameter"
                logger.info(f"🎯 [list_spaces_jwt] Using provided email: {user_email}")
            
            # Method 2: Try resource context (primary method)
            if not user_email:
                try:
                    user_email = get_current_user_email_simple()
                    auth_method = "resource_context"
                    logger.info(f"🎯 [list_spaces_jwt] Got email from resource context: {user_email}")
                except ValueError:
                    logger.info("🎯 [list_spaces_jwt] No resource context available, trying JWT...")
            
            # Method 3: Fallback to JWT token claims
            if not user_email:
                try:
                    user_email = get_user_email_from_token()
                    auth_method = "jwt_token"
                    logger.info(f"🎯 [list_spaces_jwt] Got email from JWT token: {user_email}")
                except Exception as jwt_error:
                    logger.warning(f"🎯 [list_spaces_jwt] JWT auth failed: {jwt_error}")
            
            # Final check
            if not user_email:
                return JWTSpacesResponse(
                    spaces=[],
                    count=0,
                    userEmail="",
                    authMethod="none",
                    filterApplied=space_type,
                    error="Authentication error: Could not determine user email. Please provide user_google_email parameter or ensure proper authentication is set up."
                )
            
            logger.info(f"🎯 [list_spaces_jwt] Using email: {user_email} (method: {auth_method})")
            
            # Get Google Chat service using the email from JWT
            logger.info(f"🔧 Creating Chat service for {user_email}")
            chat_service = await get_service("chat", user_email)
            
            if not chat_service:
                return JWTSpacesResponse(
                    spaces=[],
                    count=0,
                    userEmail=user_email,
                    authMethod=auth_method,
                    filterApplied=space_type,
                    error=f"Failed to create Google Chat service for {user_email}. Please check your credentials and permissions."
                )
            
            # Build filter based on space_type
            filter_param = None
            if space_type == "room":
                filter_param = "spaceType = SPACE"
            elif space_type == "dm":
                filter_param = "spaceType = DIRECT_MESSAGE"
            
            request_params = {"pageSize": page_size}
            if filter_param:
                request_params["filter"] = filter_param
            
            logger.info(f"🔍 Listing spaces with params: {request_params}")
            
            # Execute the request
            response = await asyncio.to_thread(
                chat_service.spaces().list(**request_params).execute
            )
            
            items = response.get('spaces', [])
            logger.info(f"📊 Found {len(items)} spaces for {user_email}")
            
            # Convert to structured format
            spaces: List[JWTSpaceInfo] = []
            for space in items:
                space_info: JWTSpaceInfo = {
                    "name": space.get('name', 'Unknown'),
                    "displayName": space.get('displayName', 'No display name'),
                    "type": space.get('type', 'Unknown'),
                    "spaceType": space.get('spaceType', 'Unknown'),
                    "threaded": space.get('threaded', False),
                    "spaceDetails": space.get('spaceDetails', {}),
                    "memberCount": len(space.get('members', [])) if 'members' in space else None
                }
                spaces.append(space_info)
            
            logger.info(f"✅ Successfully listed {len(spaces)} spaces for {user_email}")
            
            return JWTSpacesResponse(
                spaces=spaces,
                count=len(spaces),
                userEmail=user_email,
                authMethod=auth_method,
                filterApplied=space_type,
                error=None
            )
            
        except Exception as e:
            error_msg = f"Error listing Google Chat spaces: {str(e)}"
            logger.error(f"[list_spaces_jwt] {error_msg}")
            return JWTSpacesResponse(
                spaces=[],
                count=0,
                userEmail=user_email if 'user_email' in locals() else "",
                authMethod=auth_method if 'auth_method' in locals() else "unknown",
                filterApplied=space_type,
                error=error_msg
            )
    
    logger.info("✅ JWT-enhanced Chat tools registered")


if __name__ == "__main__":
    # Test import
    print("JWT Chat tools module loaded successfully")