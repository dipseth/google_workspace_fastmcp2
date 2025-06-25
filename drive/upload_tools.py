"""
Google Drive upload tools for FastMCP2.

This module provides comprehensive Google Drive integration tools for FastMCP2 servers,
including file upload capabilities, OAuth2 authentication management, and status verification.

Key Features:
- Secure file upload to Google Drive with folder management
- OAuth2 authentication flow initiation and management
- Authentication status verification and error handling
- Comprehensive error handling with user-friendly messages
- Support for custom filenames and folder destinations

Tool Categories:
- Upload Tools: File upload with authentication and validation
- Auth Tools: OAuth2 setup and status verification
- Utility Functions: Helper functions for setup and callback handling

Dependencies:
- google-api-python-client: Google Drive API integration
- google-auth-oauthlib: OAuth2 authentication flow
- fastmcp: FastMCP server framework
"""

import logging
from pathlib import Path
from typing import Optional, Any
from fastmcp import FastMCP

from auth.google_auth import get_drive_service, initiate_oauth_flow, GoogleAuthError
from auth.service_helpers import get_service, request_service, get_injected_service
from .utils import upload_file_to_drive_api, format_upload_result, DriveUploadError

logger = logging.getLogger(__name__)


def setup_drive_tools(mcp: FastMCP) -> None:
    """
    Register Google Drive tools with the FastMCP server.
    
    This function registers three main tools:
    1. upload_file_to_drive: Core file upload functionality
    2. start_google_auth: OAuth2 authentication initiation
    3. check_drive_auth: Authentication status verification
    
    Args:
        mcp: FastMCP server instance to register tools with
        
    Returns:
        None: Tools are registered as side effects
    """
    
    @mcp.tool(
        name="upload_file_to_drive",
        description="Upload a local file to Google Drive with authentication and folder management",
        tags={"upload", "drive", "file", "storage", "google"},
        annotations={
            "title": "Google Drive File Upload",
            "readOnlyHint": False,  # Modifies environment by uploading files
            "destructiveHint": False,  # Creates new files, doesn't destroy existing data
            "idempotentHint": False,  # Multiple uploads create duplicates
            "openWorldHint": True  # Interacts with external Google Drive API
        }
    )
    async def upload_file_to_drive(
        user_google_email: str,
        filepath: str,
        folder_id: str = "root",
        filename: Optional[str] = None
    ) -> str:
        """
        Upload a local file to Google Drive with comprehensive error handling.
        
        This tool handles file validation, authentication, and upload to Google Drive.
        It supports custom filenames and folder destinations, with detailed error reporting.
        
        Args:
            user_google_email: Google email address for authentication (must be pre-authenticated)
            filepath: Local filesystem path to the file to upload (supports ~ expansion)
            folder_id: Google Drive folder ID destination (defaults to "root" folder)
            filename: Optional custom filename for uploaded file (preserves original if not provided)
        
        Returns:
            str: Formatted success message with Google Drive link or detailed error message
            
        Raises:
            Handles GoogleAuthError, DriveUploadError, FileNotFoundError, PermissionError
        """
        logger.info(f"Upload request: {filepath} -> Drive folder {folder_id} for {user_google_email}")
        
        try:
            # Validate and convert file path
            file_path = Path(filepath).expanduser().resolve()
            
            # Get authenticated Drive service
            drive_service = await get_drive_service(user_google_email)
            
            # Upload file
            result = await upload_file_to_drive_api(
                service=drive_service,
                file_path=file_path,
                folder_id=folder_id,
                custom_filename=filename
            )
            
            # Format and return result
            response = format_upload_result(result, file_path)
            logger.info(f"Upload successful: {result['name']} (ID: {result['id']})")
            return response
            
        except GoogleAuthError as e:
            error_msg = f"❌ Authentication error: {e}"
            logger.error(error_msg)
            return error_msg
        except DriveUploadError as e:
            error_msg = f"❌ Upload error: {e}"
            logger.error(error_msg)
            return error_msg
        except FileNotFoundError:
            error_msg = f"❌ File not found: {filepath}"
            logger.error(error_msg)
            return error_msg
        except PermissionError:
            error_msg = f"❌ Permission denied accessing file: {filepath}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error: {e}"
            logger.error(error_msg, exc_info=True)
            return error_msg
    
    @mcp.tool(
        name="start_google_auth",
        description="Initiate Google OAuth2 authentication flow for Google Drive API access",
        tags={"auth", "oauth", "google", "drive", "authentication", "setup"},
        annotations={
            "title": "Google Drive OAuth Setup",
            "readOnlyHint": False,  # Modifies authentication state
            "destructiveHint": False,  # Creates auth tokens, doesn't destroy data
            "idempotentHint": True,  # Can be called multiple times safely
            "openWorldHint": True  # Interacts with external Google OAuth services
        }
    )
    async def start_google_auth(
        user_google_email: str,
        service_name: str = "Google Drive"
    ) -> str:
        """
        Initiate Google OAuth2 authentication flow for Google Drive API access.
        
        This tool generates an OAuth2 authorization URL and provides step-by-step
        instructions for users to authenticate their Google account. The authentication
        process grants the application permission to access Google Drive on behalf
        of the specified user.
        
        Args:
            user_google_email: Target Google email address for authentication
            service_name: Human-readable service name for display in auth flow (defaults to "Google Drive")
        
        Returns:
            str: Formatted instructions containing the OAuth2 authorization URL and step-by-step guide
            
        Raises:
            Handles generic exceptions during OAuth flow initiation
        """
        logger.info(f"Starting OAuth flow for {user_google_email}")
        
        try:
            auth_url = await initiate_oauth_flow(
                user_email=user_google_email,
                service_name=service_name
            )
            
            return (
                f"🔐 **Google Drive Authentication Required**\n\n"
                f"Please complete the following steps:\n"
                f"1. Click this link: {auth_url}\n"
                f"2. Sign in with: {user_google_email}\n"
                f"3. Grant Google Drive permissions\n"
                f"4. Wait for the success page\n"
                f"5. Return here and retry your upload\n\n"
                f"The authentication will be linked to your current session."
            )
            
        except Exception as e:
            error_msg = f"❌ Failed to start authentication: {e}"
            logger.error(error_msg, exc_info=True)
            return error_msg
    
    @mcp.tool(
        name="check_drive_auth",
        description="Verify Google Drive authentication status for a specific user account",
        tags={"auth", "check", "status", "google", "drive", "verification"},
        annotations={
            "title": "Google Drive Auth Status Check",
            "readOnlyHint": True,  # Only reads authentication state, doesn't modify
            "destructiveHint": False,  # Safe read-only operation
            "idempotentHint": True,  # Multiple calls return same result
            "openWorldHint": True  # Verifies against external Google services
        }
    )
    async def check_drive_auth(user_google_email: str) -> str:
        """
        Verify Google Drive authentication status for a specific user account.
        
        This tool checks whether the specified user has valid, active Google Drive
        authentication credentials. It attempts to access the Drive service to
        validate the authentication state without performing any Drive operations.
        
        Args:
            user_google_email: Google email address to verify authentication status for
            
        Returns:
            str: Clear status message indicating authentication state:
                 - Success: Confirms valid authentication
                 - Failure: Indicates missing auth with instructions to authenticate
                 - Error: Reports any technical issues during verification
                 
        Raises:
            Handles GoogleAuthError for invalid/missing credentials and generic exceptions
        """
        logger.info(f"Checking authentication for {user_google_email}")
        
        try:
            # Try to get the Drive service - this will fail if not authenticated
            await get_drive_service(user_google_email)
            return f"✅ {user_google_email} is authenticated for Google Drive"
        except GoogleAuthError:
            return (
                f"❌ {user_google_email} is not authenticated for Google Drive\n"
                f"Use the `start_google_auth` tool to authenticate."
            )
        except Exception as e:
            error_msg = f"❌ Error checking authentication: {e}"
            logger.error(error_msg)
            return error_msg

def setup_oauth_callback_handler(mcp: FastMCP) -> None:
    """
    Setup OAuth2 callback route handler for FastMCP2 server.
    
    This function registers a custom HTTP route to handle OAuth2 callback responses
    from Google's authentication service. The callback processes authorization codes
    and completes the authentication flow.
    
    Route Details:
    - Path: /oauth2callback
    - Method: GET
    - Purpose: Complete OAuth2 flow after user authorization
    
    Args:
        mcp: FastMCP server instance to register the route with
        
    Returns:
        None: Route handler is registered as a side effect
    """
    
    @mcp.custom_route("/oauth2callback", methods=["GET"])
    async def oauth_callback(request: Any) -> Any:
        """
        Handle OAuth2 callback from Google authentication service.
        
        This endpoint processes the OAuth2 callback after a user completes
        authentication with Google. It extracts the authorization code,
        validates the state parameter, and completes the credential exchange.
        
        Query Parameters Expected:
        - code: Authorization code from Google
        - state: CSRF protection state parameter
        - error: Error code if authentication failed
        
        Args:
            request: HTTP request object containing query parameters
            
        Returns:
            HTMLResponse: Success page or error page based on authentication result
        """
        from auth.google_auth import handle_oauth_callback
        from starlette.responses import HTMLResponse
        
        try:
            # Extract parameters from query string
            query_params = dict(request.query_params)
            state = query_params.get("state")
            code = query_params.get("code")
            error = query_params.get("error")
            
            if error:
                return HTMLResponse(_create_error_response(f"Authentication failed: {error}"))
            
            if not code or not state:
                return HTMLResponse(_create_error_response("Missing authorization code or state"))
            
            # Handle the callback
            user_email, credentials = await handle_oauth_callback(
                authorization_response=str(request.url),
                state=state
            )
            
            return HTMLResponse(_create_success_response(user_email))
            
        except Exception as e:
            logger.error(f"OAuth callback error: {e}", exc_info=True)
            return HTMLResponse(_create_error_response(f"Authentication failed: {e}"))


def _create_success_response(user_email: str) -> str:
    """
    Create a success HTML response for completed OAuth2 authentication.
    
    Generates a user-friendly HTML page confirming successful authentication
    with Google Drive. The page includes visual success indicators and
    clear instructions for the user to proceed.
    
    Args:
        user_email: Authenticated Google email address to display
        
    Returns:
        str: Complete HTML document with success message and styling
    """
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Authentication Successful</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; text-align: center; }}
            .success {{ color: #28a745; }}
            .container {{ max-width: 600px; margin: 0 auto; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="success">✅ Authentication Successful!</h1>
            <p>Successfully authenticated: <strong>{user_email}</strong></p>
            <p>You can now close this window and return to your application.</p>
            <p>Your Google Drive upload server is ready to use!</p>
        </div>
    </body>
    </html>
    """


def _create_error_response(error_message: str) -> str:
    """
    Create an error HTML response for failed OAuth2 authentication attempts.
    
    Generates a user-friendly HTML error page when OAuth2 authentication fails.
    The page includes clear error messaging, visual error indicators, and
    guidance for retry attempts.
    
    Args:
        error_message: Detailed error message to display to the user
        
    Returns:
        str: Complete HTML document with error message and styling
    """
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Authentication Error</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; text-align: center; }}
            .error {{ color: #dc3545; }}
            .container {{ max-width: 600px; margin: 0 auto; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="error">❌ Authentication Error</h1>
            <p>{error_message}</p>
            <p>Please try the authentication process again.</p>
        </div>
    </body>
    </html>
    """