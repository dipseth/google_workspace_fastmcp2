"""JWT-enhanced Google Chat tools that use FastMCP Bearer Token authentication.

This module demonstrates the new JWT authentication pattern where user email
is extracted from JWT token claims instead of requiring parameters.
"""

import logging
import asyncio
from typing import Optional

from fastmcp import FastMCP
from googleapiclient.errors import HttpError

from auth.jwt_auth import get_user_email_from_token
from auth.service_helpers import get_service

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
        page_size: int = 100,
        space_type: str = "all"
    ) -> str:
        """
        Lists Google Chat spaces using JWT authentication.
        
        🎯 ENHANCED: Gets user email automatically from JWT token claims!
        No user_google_email parameter required.
        
        Args:
            page_size: Number of spaces to return (default: 100)
            space_type: Filter by space type: "all", "room", or "dm" (default: "all")
            
        Returns:
            JSON formatted list of Google Chat spaces accessible to the authenticated user
        """
        try:
            # 🎫 Get user email from JWT token automatically
            user_email = get_user_email_from_token()
            logger.info(f"🎯 [list_spaces_jwt] JWT auth successful for: {user_email}")
            
            # Get Google Chat service using the email from JWT
            logger.info(f"🔧 Creating Chat service for {user_email}")
            chat_service = await get_service("chat", user_email)
            
            if not chat_service:
                return f"❌ Failed to create Google Chat service for {user_email}. Please check your credentials and permissions."
            
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
            
            spaces = response.get('spaces', [])
            logger.info(f"📊 Found {len(spaces)} spaces for {user_email}")
            
            if not spaces:
                return f"✅ No Google Chat spaces found for {user_email} with filter '{space_type}'"
            
            # Format results
            formatted_spaces = []
            for space in spaces:
                space_info = {
                    "name": space.get('name', 'Unknown'),
                    "displayName": space.get('displayName', 'No display name'),
                    "type": space.get('type', 'Unknown'),
                    "spaceType": space.get('spaceType', 'Unknown'),
                    "threaded": space.get('threaded', False),
                    "spaceDetails": space.get('spaceDetails', {}),
                    "memberCount": len(space.get('members', [])) if 'members' in space else None
                }
                formatted_spaces.append(space_info)
            
            result = {
                "user_email": user_email,
                "auth_method": "JWT Bearer Token",
                "total_spaces": len(spaces),
                "filter_applied": space_type,
                "spaces": formatted_spaces
            }
            
            logger.info(f"✅ Successfully listed {len(spaces)} spaces for {user_email}")
            return f"✅ Found {len(spaces)} Google Chat spaces for {user_email}:\n\n{result}"
            
        except Exception as e:
            error_msg = f"❌ Error listing Google Chat spaces: {str(e)}"
            logger.error(f"[list_spaces_jwt] {error_msg}")
            return error_msg
    
    logger.info("✅ JWT-enhanced Chat tools registered")


if __name__ == "__main__":
    # Test import
    print("JWT Chat tools module loaded successfully")