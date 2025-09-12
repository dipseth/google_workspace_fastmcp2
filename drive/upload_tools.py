"""
Google Drive upload tools for FastMCP2.

This module provides comprehensive Google Drive integration tools for FastMCP2 servers,
including file upload capabilities, OAuth2 authentication management, and status veri        
        Upload a local file or folder to Google Drive with unified authentication support.
        
        This tool demonstrates the unified OAuth architecture where user_google_email
        is automatically injected by the middleware when authenticated via GoogleProvider.
        
        Args:
            path: Local filesystem path to the file or folder to upload (supports ~ expansion)
            folder_id: Google Drive folder ID destination (defaults to "root" folder)
            filename: Optional custom name for uploaded file/folder (preserves original if not provided)
            user_google_email: User's Google email (auto-injected by unified auth middleware)
        
        Returns:
            UploadFileResponse: Structured response with upload results including file metadata Features:
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
from config.enhanced_logging import setup_logger
logger = setup_logger()
import time
from pathlib import Path
from typing_extensions import Optional, Any, List, Annotated, Union, Literal
from fastmcp import FastMCP
from pydantic import BaseModel, Field


# Import our custom type for consistent parameter definition
from tools.common_types import UserGoogleEmailDrive, GoogleServiceNames
from config.settings import settings

# Import service types for proper typing
from auth.service_types import GoogleServiceDisplayName, AuthenticationMethod, GoogleServiceName

from auth.google_auth import initiate_oauth_flow, GoogleAuthError
from auth.service_helpers import (
    get_service,
    request_service,
    get_injected_service,
    get_drive_service,
    list_supported_services,
    get_service_defaults
)
from .utils import upload_file_to_drive_api, format_upload_result, DriveUploadError
from .upload_types import (
    UploadFileResponse,
    FileUploadInfo,
    FolderUploadSummary,
    StartAuthResponse,
    CheckAuthResponse
)
from .auth_models import GoogleAuthConfig




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
        name="start_google_auth",
        description="Initiate Google OAuth2 authentication flow for Google services with automatic browser opening (Drive, Gmail, Docs, Sheets, Slides, Calendar, etc.)",
        tags={"auth", "oauth", "google", "services", "authentication", "setup", "browser"},
        annotations={
            "title": "Google Services OAuth Setup with Browser Support",
            "readOnlyHint": False,  # Modifies authentication state
            "destructiveHint": False,  # Creates auth tokens, doesn't destroy data
            "idempotentHint": True,  # Can be called multiple times safely
            "openWorldHint": True  # Interacts with external Google OAuth services
        }
    )

    async def start_google_auth(
        user_google_email: str = '',
        service_name:  list[str] = ['drive', 'gmail', 'calendar', 'docs', 'sheets', 'slides', 'photos', 'chat', 'forms'],
        auto_open_browser: Annotated[bool, Field(description="Automatically open browser for authentication (default: True)")] = True,
        use_pkce: Annotated[bool, Field(description="Use PKCE for authentication (default: True, deprecated - use auth_method instead)")] = True,
        show_service_selection: Annotated[bool, Field(description="Show service selection page before authentication (default: True)")] = True,
        auth_method: Annotated[Literal['file_credentials', 'pkce_file', 'pkce_memory'], Field(description="Authentication method: 'file_credentials' (legacy), 'pkce_file' (PKCE + file storage), 'pkce_memory' (PKCE + session only)")] = 'pkce_file'
    ) -> StartAuthResponse:
        """
        Initiate Google OAuth2 authentication flow for Google services access with automatic browser opening.
        
        This tool generates an OAuth2 authorization URL and can automatically open the browser
        for authentication. Supports both single services and service lists with PKCE or credential-based authentication.
        
        Args:
            user_google_email: Target Google email address for authentication
            service_name: Service name(s) for authentication. Defaults to all services if None.
            auto_open_browser: Whether to automatically open the browser (default: True)
        
        Returns:
            StartAuthResponse: Structured response containing auth URL, instructions, and metadata
            
        Raises:
            Handles generic exceptions during OAuth flow initiation
        """
        # DEBUG: Log all received parameters
        logger.info(f"🔧 TOOL DEBUG: start_google_auth called with parameters:")
        logger.info(f"🔧 TOOL DEBUG:   user_google_email = {user_google_email} (type: {type(user_google_email)})")
        logger.info(f"🔧 TOOL DEBUG:   service_name = {service_name} (type: {type(service_name)})")
        logger.info(f"🔧 TOOL DEBUG:   auto_open_browser = {auto_open_browser} (type: {type(auto_open_browser)})")
        
        # Try to get user email from context if not provided
        if not user_google_email:
            logger.info(f"🔧 TOOL DEBUG: user_google_email is None/empty, checking context")
            from auth.context import get_user_email_context
            context_email = get_user_email_context()
            logger.info(f"🔧 TOOL DEBUG: get_user_email_context() returned: {context_email}")
            
            if context_email:
                user_google_email = context_email
                logger.info(f"🔧 TOOL DEBUG: Using email from context: {user_google_email}")
            else:
                logger.info(f"🔧 TOOL DEBUG: No email found in context either")
        
        logger.info(f"Starting OAuth flow for {user_google_email} (auto_open_browser={auto_open_browser})")
        
        # Validate that user_google_email is provided
        if not user_google_email:
            logger.error(f"🔧 TOOL DEBUG: ❌ Still no user_google_email after context check")
            return StartAuthResponse(
                status="error",
                message="❌ Authentication Setup Failed",
                userEmail="",
                error="No user email provided. Please provide a Google email address to start authentication.",
                templateApplied=False
            )
        
        try:
            # Backward compatibility mapping for use_pkce
            if use_pkce and auth_method == 'file_credentials':
                logger.warning("Overriding auth_method to 'pkce_file' since use_pkce=True")
                auth_method = 'pkce_file'
            elif not use_pkce and auth_method in ['pkce_file', 'pkce_memory']:
                logger.warning("Overriding auth_method to 'file_credentials' since use_pkce=False")
                auth_method = 'file_credentials'

            # ALWAYS show service selection UI, but use service_name for pre-selection
            if isinstance(service_name, list):
                # List of specific services provided - these will be PRE-SELECTED in the UI
                pre_selected_services = service_name
                display_service_name = f"{len(service_name)} Pre-selected Services"
                logger.info(f"🎯 Will pre-select services in UI: {pre_selected_services}")
            elif service_name is None:
                # No pre-selection - let user choose from common defaults
                pre_selected_services = ['drive', 'gmail', 'calendar', 'docs', 'sheets']  # Common defaults
                display_service_name = "Google Services (Common Pre-selected)"
                logger.info(f"🎯 Will pre-select common services in UI: {pre_selected_services}")
            else:
                # Single service display name (backward compatibility) - no pre-selection
                pre_selected_services = []
                display_service_name = str(service_name)
                logger.info(f"🎯 Service display name, no pre-selection: {display_service_name}")
            
            # ALWAYS force service selection UI (selected_services=None)
            # The UI will handle pre-selection with its existing JavaScript
            auth_url = await initiate_oauth_flow(
                user_email=user_google_email,
                service_name=display_service_name,
                selected_services=None,  # Force UI to show
                show_service_selection=show_service_selection,
                use_pkce=(auth_method != 'file_credentials'),
                auth_method=auth_method
            )
            
            # Attempt to open browser automatically if requested
            browser_opened = False
            browser_error = None
            
            if auto_open_browser:
                try:
                    import webbrowser
                    browser_opened = webbrowser.open(auth_url)
                    logger.info(f"✅ Browser opened automatically for OAuth authentication")
                except Exception as e:
                    browser_error = str(e)
                    logger.warning(f"⚠️ Failed to open browser automatically: {e}")
            
            # Build instructions based on whether browser was opened
            if browser_opened:
                instructions = [
                    "🌐 **Browser opened automatically** - complete authentication there",
                    f"Sign in with: {user_google_email}",
                    "Grant permissions for Google services (Drive, Gmail, Docs, Sheets, Slides, Calendar, etc.)",
                    "Wait for the success page",
                    "Return here and retry your operation",
                    "",
                    "💡 **For CLI clients**: You can also poll authentication status:",
                    f"   GET {settings.base_url}/oauth/status"
                ]
                message = "🔐 **Browser Opened - Complete Authentication**"
            else:
                instructions = [
                    f"🔗 Click the authentication link: {auth_url}",
                    f"Sign in with: {user_google_email}",
                    "Grant permissions for Google services (Drive, Gmail, Docs, Sheets, Slides, Calendar, etc.)",
                    "Wait for the success page",
                    "Return here and retry your operation",
                    "",
                    "💡 **For CLI clients**: You can poll authentication status:",
                    f"   GET {settings.base_url}/oauth/status"
                ]
                message = "🔐 **Google Services Authentication Required**"
                if browser_error:
                    instructions.insert(0, f"⚠️ Auto-browser open failed: {browser_error}")
            
            response = StartAuthResponse(
                status="success",
                message=message,
                authUrl=auth_url,
                clickableLink=f"[🚀 Click here to authenticate]({auth_url})",
                userEmail=user_google_email,
                serviceName=service_name,
                instructions=instructions,
                scopesIncluded=[
                    "Google Drive (file management)",
                    "Gmail (email access)",
                    "Google Docs (document editing)",
                    "Google Sheets (spreadsheet access)",
                    "Google Slides (presentation management)",
                    "Google Calendar (event management)",
                    "And more Google services"
                ],
                note="The authentication will be linked to your current session and provide access to all Google services."
            )
            
            # Add browser-specific fields
            if hasattr(response, '__dict__'):
                response.__dict__['browserOpened'] = browser_opened
                response.__dict__['pollingEndpoint'] = f"{settings.base_url}/oauth/status"
                if browser_error:
                    response.__dict__['browserError'] = browser_error
            
            return response
            
        except Exception as e:
            error_msg = f"Failed to start authentication: {e}"
            logger.error(error_msg, exc_info=True)
            return StartAuthResponse(
                status="error",
                message="❌ Authentication Setup Failed",
                userEmail=user_google_email,
                error=str(e)
            )
    
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
    async def check_drive_auth(
        user_google_email: UserGoogleEmailDrive = None
    ) -> CheckAuthResponse:
        """
        Verify Google Drive authentication status for a specific user account.
        
        This tool checks whether the specified user has valid, active Google Drive
        authentication credentials. It attempts to access the Drive service to
        validate the authentication state without performing any Drive operations.
        
        Args:
            user_google_email: Google email address to verify authentication status for
            
        Returns:
            CheckAuthResponse: Structured response indicating authentication state
                 
        Raises:
            Handles GoogleAuthError for invalid/missing credentials and generic exceptions
        """
        logger.info(f"Checking authentication for {user_google_email}")
        
        # Validate that user_google_email is provided
        if not user_google_email:
            return CheckAuthResponse(
                authenticated=False,
                userEmail="",
                message="No user email provided. Please provide a Google email address to check authentication status.",
                error="Missing user_google_email parameter"
            )
        
        try:
            # Use service helpers for better service management
            drive_service = await get_service("drive", user_google_email)
            
            # Test basic Drive access to verify authentication
            import asyncio
            await asyncio.to_thread(
                drive_service.about().get(fields='user').execute
            )
            
            return CheckAuthResponse(
                authenticated=True,
                userEmail=user_google_email,
                message=f"{user_google_email} is authenticated for Google Drive"
            )
        except GoogleAuthError:
            return CheckAuthResponse(
                authenticated=False,
                userEmail=user_google_email,
                message=f"{user_google_email} is not authenticated for Google Drive. Use the `start_google_auth` tool to authenticate."
            )
        except Exception as e:
            error_msg = f"Error checking authentication: {e}"
            logger.error(f"❌ {error_msg}")
            return CheckAuthResponse(
                authenticated=False,
                userEmail=user_google_email,
                message="",
                error=error_msg
            )

    @mcp.tool(
        name="upload_to_drive",
        description="Upload a local file or folder to Google Drive with UNIFIED authentication (no email parameter needed when authenticated via GoogleProvider)",
        tags={"upload", "drive", "file", "folder", "storage", "google", "unified"},
        annotations={
            "title": "Google Drive File/Folder Upload (Unified Auth)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def upload_to_drive(
        path: Annotated[str, Field(description="Local filesystem path to the file or folder to upload (supports ~ expansion)")],
        folder_id: Annotated[str, Field(description="Google Drive folder ID where file will be uploaded (default: 'root' for root folder)")] = 'root',
        filename: Annotated[Optional[str], Field(description="Custom filename for the uploaded file (optional - uses original filename if not provided)")] = None,
        user_google_email: UserGoogleEmailDrive = None
    ) -> UploadFileResponse:
        """
        Upload a local file or folder to Google Drive with unified authentication support.
        
        This tool demonstrates the unified OAuth architecture where user_google_email
        is automatically injected by the middleware when authenticated via GoogleProvider.
        
        Args:
            path: Local filesystem path to the file or folder to upload (supports ~ expansion)
            folder_id: Google Drive folder ID destination (defaults to "root" folder)
            filename: Optional custom name for uploaded file/folder (preserves original if not provided)
            user_google_email: User's Google email (auto-injected by unified auth middleware)
        
        Returns:
            UploadFileResponse: Structured response with upload details or error information
            
        Note:
            When authenticated via FastMCP GoogleProvider, the user_google_email parameter
            is automatically injected by the unified authentication middleware, so you don't
            need to provide it manually!
        """
        from auth.context import get_user_email_context
        
        # Get user email from middleware context if not provided
        if not user_google_email:
            user_google_email = get_user_email_context()
            if not user_google_email:
                return UploadFileResponse(
                    success=False,
                    userEmail="",
                    message="",
                    error=(
                        "No authenticated user found. Please either:\n"
                        "1. Authenticate via GoogleProvider (unified auth), or\n"
                        "2. Provide the user_google_email parameter, or\n"
                        "3. Use the start_google_auth tool to authenticate"
                    )
                )
            logger.info(f"🔑 Using authenticated user from unified context: {user_google_email}")
        
        logger.info(f"Upload request: {path} -> Drive folder {folder_id} for {user_google_email}")
        
        try:
            # Validate and convert path
            local_path = Path(path).expanduser().resolve()
            
            if not local_path.exists():
                raise FileNotFoundError(f"Path not found: {path}")
            
            # Get authenticated Drive service using service helpers
            drive_service = await get_service("drive", user_google_email)
            
            # Check if it's a directory
            if local_path.is_dir():
                return await _upload_folder_to_drive(
                    drive_service=drive_service,
                    folder_path=local_path,
                    parent_folder_id=folder_id,
                    custom_folder_name=filename,
                    user_email=user_google_email
                )
            else:
                # Single file upload
                result = await upload_file_to_drive_api(
                    service=drive_service,
                    file_path=local_path,
                    folder_id=folder_id,
                    custom_filename=filename
                )
                
                # Build file info
                file_info: FileUploadInfo = {
                    "fileId": result['id'],
                    "fileName": result['name'],
                    "filePath": str(local_path),
                    "fileSize": local_path.stat().st_size,
                    "mimeType": result.get('mimeType', 'application/octet-stream'),
                    "folderId": folder_id,
                    "driveUrl": f"https://drive.google.com/file/d/{result['id']}/view",
                    "webViewLink": result.get('webViewLink', f"https://drive.google.com/file/d/{result['id']}/view")
                }
                
                logger.info(f"Upload successful: {result['name']} (ID: {result['id']})")
                
                return UploadFileResponse(
                    success=True,
                    userEmail=user_google_email,
                    fileInfo=file_info,
                    message=f"Successfully uploaded {result['name']} to Google Drive"
                )
            
        except GoogleAuthError as e:
            error_msg = f"Authentication error: {e}"
            logger.error(f"❌ {error_msg}")
            return UploadFileResponse(
                success=False,
                userEmail=user_google_email,
                message="",
                error=error_msg
            )
        except DriveUploadError as e:
            error_msg = f"Upload error: {e}"
            logger.error(f"❌ {error_msg}")
            return UploadFileResponse(
                success=False,
                userEmail=user_google_email,
                message="",
                error=error_msg
            )
        except FileNotFoundError as e:
            error_msg = f"Path not found: {path}"
            logger.error(f"❌ {error_msg}")
            return UploadFileResponse(
                success=False,
                userEmail=user_google_email,
                message="",
                error=error_msg
            )
        except PermissionError:
            error_msg = f"Permission denied accessing: {path}"
            logger.error(f"❌ {error_msg}")
            return UploadFileResponse(
                success=False,
                userEmail=user_google_email,
                message="",
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            return UploadFileResponse(
                success=False,
                userEmail=user_google_email,
                message="",
                error=error_msg
            )


async def _upload_folder_to_drive(
    drive_service: Any,
    folder_path: Path,
    parent_folder_id: str,
    custom_folder_name: Optional[str],
    user_email: str
) -> UploadFileResponse:
    """
    Recursively upload a folder and its contents to Google Drive.
    
    Args:
        drive_service: Authenticated Google Drive service
        folder_path: Path to the local folder
        parent_folder_id: Parent folder ID in Google Drive
        custom_folder_name: Optional custom name for the folder
        user_email: User's email address
        
    Returns:
        UploadFileResponse: Response with all uploaded files information
    """
    start_time = time.time()
    uploaded_files: List[FileUploadInfo] = []
    warnings: List[str] = []
    total_size = 0
    failed_count = 0
    
    try:
        # Create the root folder in Drive
        folder_name = custom_folder_name or folder_path.name
        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_folder_id]
        }
        
        import asyncio
        folder_result = await asyncio.to_thread(
            drive_service.files().create(
                body=folder_metadata,
                fields='id, name, webViewLink'
            ).execute
        )
        
        root_folder_id = folder_result['id']
        logger.info(f"Created folder '{folder_name}' with ID: {root_folder_id}")
        
        # Walk through the folder structure
        for item_path in folder_path.rglob('*'):
            if item_path.is_file():
                try:
                    # Calculate relative path for folder structure
                    relative_path = item_path.relative_to(folder_path)
                    relative_parent = relative_path.parent
                    
                    # Determine the parent folder ID (create nested folders if needed)
                    current_parent_id = root_folder_id
                    if str(relative_parent) != '.':
                        # Need to create nested folder structure
                        parts = relative_parent.parts
                        for part in parts:
                            # Check if folder exists or create it
                            query = f"name='{part}' and '{current_parent_id}' in parents and mimeType='application/vnd.google-apps.folder'"
                            existing = await asyncio.to_thread(
                                drive_service.files().list(
                                    q=query,
                                    fields='files(id)'
                                ).execute
                            )
                            
                            if existing.get('files'):
                                current_parent_id = existing['files'][0]['id']
                            else:
                                # Create the folder
                                folder_meta = {
                                    'name': part,
                                    'mimeType': 'application/vnd.google-apps.folder',
                                    'parents': [current_parent_id]
                                }
                                new_folder = await asyncio.to_thread(
                                    drive_service.files().create(
                                        body=folder_meta,
                                        fields='id'
                                    ).execute
                                )
                                current_parent_id = new_folder['id']
                    
                    # Upload the file
                    result = await upload_file_to_drive_api(
                        service=drive_service,
                        file_path=item_path,
                        folder_id=current_parent_id
                    )
                    
                    file_size = item_path.stat().st_size
                    total_size += file_size
                    
                    file_info: FileUploadInfo = {
                        "fileId": result['id'],
                        "fileName": result['name'],
                        "filePath": str(item_path),
                        "fileSize": file_size,
                        "mimeType": result.get('mimeType', 'application/octet-stream'),
                        "folderId": current_parent_id,
                        "driveUrl": f"https://drive.google.com/file/d/{result['id']}/view",
                        "webViewLink": result.get('webViewLink', f"https://drive.google.com/file/d/{result['id']}/view")
                    }
                    uploaded_files.append(file_info)
                    logger.info(f"Uploaded: {item_path.name}")
                    
                except Exception as e:
                    failed_count += 1
                    warning = f"Failed to upload {item_path}: {str(e)}"
                    warnings.append(warning)
                    logger.warning(warning)
        
        upload_duration = time.time() - start_time
        
        # Build summary
        folder_summary: FolderUploadSummary = {
            "totalFiles": len(uploaded_files) + failed_count,
            "successfulUploads": len(uploaded_files),
            "failedUploads": failed_count,
            "totalSize": total_size,
            "uploadDuration": upload_duration
        }
        
        return UploadFileResponse(
            success=True,
            userEmail=user_email,
            filesUploaded=uploaded_files,
            folderSummary=folder_summary,
            message=f"Successfully uploaded folder '{folder_name}' with {len(uploaded_files)} files to Google Drive",
            warnings=warnings if warnings else None
        )
        
    except Exception as e:
        error_msg = f"Failed to upload folder: {str(e)}"
        logger.error(error_msg)
        return UploadFileResponse(
            success=False,
            userEmail=user_email,
            message="",
            error=error_msg
        )


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
            
            # Handle the callback with PKCE support
            # Retrieve code_verifier from PKCE manager if PKCE was used
            code_verifier = None
            try:
                from auth.pkce_utils import pkce_manager
                code_verifier = pkce_manager.get_code_verifier(state)
                logger.info(f"🔐 Retrieved PKCE code verifier for callback: {code_verifier[:10]}...")
            except KeyError:
                logger.info(f"🔐 No PKCE session found for state: {state} (non-PKCE flow)")
            except Exception as e:
                logger.warning(f"🔐 Error retrieving PKCE code verifier: {e}")
            
            user_email, credentials = await handle_oauth_callback(
                authorization_response=str(request.url),
                state=state,
                code_verifier=code_verifier  # Pass the PKCE code verifier to fix "Missing code verifier" error
            )
            
            # Store user email in session context for future requests
            from auth.context import get_session_context, store_session_data
            session_id = get_session_context()
            if session_id:
                store_session_data(session_id, "user_email", user_email)
                logger.info(f"Stored user email {user_email} in session {session_id}")
            else:
                logger.warning(f"No session context available to store user email for {user_email}")
            
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