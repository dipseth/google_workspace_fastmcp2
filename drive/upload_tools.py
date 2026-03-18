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

from config.enhanced_logging import setup_logger

logger = setup_logger()
import time
from pathlib import Path

from fastmcp import FastMCP
from pydantic import Field
from typing_extensions import Annotated, Any, List, Literal, Optional, Union

from auth.google_auth import GoogleAuthError, initiate_oauth_flow
from auth.scope_registry import ScopeRegistry
from auth.service_helpers import (
    get_service,
)

# Import service types for proper typing
from config.settings import settings

# Import our custom type for consistent parameter definition
from tools.common_types import UserGoogleEmailDrive

from .upload_types import (
    CheckAuthResponse,
    FileUploadInfo,
    FolderUploadSummary,
    StartAuthResponse,
    UploadFileResponse,
)
from .utils import DriveUploadError, upload_file_to_drive_api

# Default services — derived from the catalog (all non-required services).
DEFAULT_SERVICES = ScopeRegistry.get_default_services()


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
        tags={
            "auth",
            "oauth",
            "google",
            "services",
            "authentication",
            "setup",
            "browser",
        },
        annotations={
            "title": "Google Services OAuth Setup with Browser Support",
            "readOnlyHint": False,  # Modifies authentication state
            "destructiveHint": False,  # Creates auth tokens, doesn't destroy data
            "idempotentHint": True,  # Can be called multiple times safely
            "openWorldHint": True,  # Interacts with external Google OAuth services
        },
    )
    async def start_google_auth(
        user_google_email: Annotated[
            str, Field(description="Google email address for authentication")
        ] = "",
        service_name: Annotated[
            Optional[Union[str, list[str]]],
            Field(
                description=(
                    "Service specification for authentication. Can be:\n"
                    "- List of service names: ['drive', 'gmail', 'calendar'] for pre-selected services\n"
                    "- String display name: 'My Custom App' for custom labeling (no pre-selection)\n"
                    "- None/empty: Uses common service defaults"
                )
            ),
        ] = None,
        auto_open_browser: Annotated[
            bool, Field(description="Automatically open browser for authentication")
        ] = True,
        show_service_selection: Annotated[
            bool, Field(description="Show service selection UI before authentication")
        ] = True,
        auth_method: Annotated[
            Literal["file_credentials", "pkce_file", "pkce_memory"],
            Field(
                description=(
                    "Authentication method:\n"
                    "- 'pkce_file': PKCE with file storage (recommended, default)\n"
                    "- 'pkce_memory': PKCE with session-only storage\n"
                    "- 'file_credentials': Legacy credential file method"
                )
            ),
        ] = "pkce_file",
        cross_oauth_password: Annotated[
            Optional[str],
            Field(
                pattern=r"^[0-9A-Za-z_-]*$",
                description=(
                    "Passphrase for cross-OAuth account access. "
                    "Provide this when accessing a linked account that requires a passphrase. "
                    "Only alphanumeric, underscore, and hyphen allowed."
                ),
            ),
        ] = None,
    ) -> StartAuthResponse:
        """
        Initiate Google OAuth2 authentication flow for Google services access.

        This tool generates an OAuth2 authorization URL and optionally opens a browser
        for authentication. Supports service pre-selection and multiple auth methods.

        Parameter Patterns:
        ------------------
        # Common usage - pre-select multiple services:
        service_name=['drive', 'gmail', 'calendar']

        # Custom display name (no pre-selection):
        service_name='My Application Name'

        # Use defaults (common services pre-selected):
        service_name=None  # or omit parameter

        Authentication Methods:
        ----------------------
        - pkce_file: Most secure, persists across sessions (default)
        - pkce_memory: Secure, session-only (clears on server restart)
        - file_credentials: Legacy method for backward compatibility

        Args:
            user_google_email: Target Google email address for authentication
            service_name: Service specification (list, string display name, or None for defaults)
            auto_open_browser: Whether to automatically open browser (default: True)
            show_service_selection: Whether to show service selection UI (default: True)
            auth_method: Authentication method to use (default: 'pkce_file')

        Returns:
            StartAuthResponse: Structured response with auth URL, instructions, and metadata
        """
        # Stash cross-OAuth password in session for credential decryption
        if cross_oauth_password:
            try:
                from auth.context import get_session_context_sync, store_session_data
                from auth.types import SessionKey

                session_id = get_session_context_sync()
                if session_id:
                    store_session_data(
                        session_id,
                        SessionKey.OAUTH_LINKAGE_PASSWORD,
                        cross_oauth_password,
                    )
            except Exception as e:
                logger.debug(f"Could not stash cross-OAuth password: {e}")

        # DEBUG: Log all received parameters
        logger.info("🔧 TOOL DEBUG: start_google_auth called with parameters:")
        logger.info(
            f"🔧 TOOL DEBUG:   user_google_email = {user_google_email} (type: {type(user_google_email)})"
        )
        logger.info(
            f"🔧 TOOL DEBUG:   service_name = {service_name} (type: {type(service_name)})"
        )
        logger.info(
            f"🔧 TOOL DEBUG:   auto_open_browser = {auto_open_browser} (type: {type(auto_open_browser)})"
        )

        # Try to get user email from context if not provided
        if not user_google_email:
            logger.info(
                "🔧 TOOL DEBUG: user_google_email is None/empty, checking context"
            )
            from auth.context import get_user_email_context

            context_email = await get_user_email_context()
            logger.info(
                f"🔧 TOOL DEBUG: get_user_email_context() returned: {context_email}"
            )

            if context_email:
                user_google_email = context_email
                logger.info(
                    f"🔧 TOOL DEBUG: Using email from context: {user_google_email}"
                )
            else:
                logger.info("🔧 TOOL DEBUG: No email found in context either")

        logger.info(
            f"Starting OAuth flow for {user_google_email} (auto_open_browser={auto_open_browser})"
        )

        # Validate that user_google_email is provided
        if not user_google_email:
            logger.error(
                "🔧 TOOL DEBUG: ❌ Still no user_google_email after context check"
            )
            return StartAuthResponse(
                status="error",
                message="❌ Authentication Setup Failed",
                userEmail="",
                error="No user email provided. Please provide a Google email address to start authentication.",
            )

        try:
            # --- Credential pre-check: skip OAuth if valid creds already cover requested scopes ---
            from auth.google_auth import compare_scopes, get_valid_credentials

            existing_creds = get_valid_credentials(user_google_email)
            if existing_creds is not None:
                # Resolve requested scopes from service_name parameter
                if isinstance(service_name, list):
                    requested_services = service_name
                elif service_name is None or service_name == "":
                    requested_services = DEFAULT_SERVICES
                else:
                    requested_services = []  # custom display string — can't resolve scopes

                if requested_services:
                    requested_scopes = ScopeRegistry.get_scopes_for_services(
                        requested_services
                    )
                    sufficient, missing = compare_scopes(
                        getattr(existing_creds, "scopes", None), requested_scopes
                    )
                    if sufficient:
                        # If the per-user key was never revealed, fall through
                        # to OAuth so the success page can display it.
                        from auth.user_api_keys import was_key_revealed

                        key_unrevealed = not was_key_revealed(user_google_email)
                        if key_unrevealed:
                            logger.info(
                                f"Credentials for {user_google_email} are valid but "
                                f"per-user API key was never revealed — proceeding "
                                f"with OAuth so success page can display it"
                            )
                        else:
                            import urllib.parse

                            from auth.context import get_session_context
                            from config.settings import settings as _settings

                            current_session_id = await get_session_context()
                            logger.info(
                                f"Credentials for {user_google_email} already cover requested scopes "
                                f"— skipping OAuth flow"
                            )

                            status_url = (
                                f"{_settings.base_url}/auth/status-check"
                                f"?email={urllib.parse.quote(user_google_email)}"
                            )
                            browser_opened = False
                            if auto_open_browser:
                                try:
                                    import webbrowser

                                    browser_opened = webbrowser.open(status_url)
                                except Exception:
                                    pass

                            return StartAuthResponse(
                                status="already_authenticated",
                                message=(
                                    f"Valid credentials already exist for {user_google_email}. "
                                    f"Status page opened in browser."
                                ),
                                authUrl=status_url,
                                clickableLink=f"[View credential status]({status_url})",
                                userEmail=user_google_email,
                                sessionId=current_session_id,
                                serviceName=requested_services,
                                scopesIncluded=list(existing_creds.scopes or []),
                                instructions=[
                                    "Browser opened with credential status page"
                                    if browser_opened
                                    else f"Open this URL to view credential status: {status_url}"
                                ],
                            )
                    else:
                        logger.info(
                            f"Credentials for {user_google_email} missing scopes "
                            f"{missing} — proceeding with scope-upgrade OAuth"
                        )

            # Handle service_name parameter for pre-selection and display
            if isinstance(service_name, list):
                # List of specific services provided - these will be PRE-SELECTED in the UI
                pre_selected_services = service_name
                display_service_name = f"{len(service_name)} Pre-selected Services"
                logger.info(
                    f"🎯 Will pre-select services in UI: {pre_selected_services}"
                )
            elif service_name is None or service_name == "":
                # No pre-selection - let user choose from common defaults
                pre_selected_services = list(DEFAULT_SERVICES)
                display_service_name = "Google Services (Common Pre-selected)"
                logger.info(
                    f"🎯 Will pre-select common services in UI: {pre_selected_services}"
                )
            else:
                # Single service display name (backward compatibility) - no pre-selection
                pre_selected_services = []
                display_service_name = str(service_name)
                logger.info(
                    f"🎯 Service display name, no pre-selection: {display_service_name}"
                )

            # ALWAYS force service selection UI (selected_services=None)
            # The UI will handle pre-selection with its existing JavaScript
            auth_url = await initiate_oauth_flow(
                user_email=user_google_email,
                service_name=display_service_name,
                selected_services=None,  # Force UI to show
                show_service_selection=show_service_selection,
                use_pkce=(auth_method != "file_credentials"),
                auth_method=auth_method,
            )

            # Attempt to open browser automatically if requested
            browser_opened = False
            browser_error = None

            if auto_open_browser:
                try:
                    import webbrowser

                    browser_opened = webbrowser.open(auth_url)
                    logger.info(
                        "✅ Browser opened automatically for OAuth authentication"
                    )
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
                    f"⚠️ **After auth**: pass user_google_email='{user_google_email}' explicitly in all tool calls for this account",
                    "",
                    "💡 **For CLI clients**: You can also poll authentication status:",
                    f"   GET {settings.base_url}/oauth/status",
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
                    f"⚠️ **After auth**: pass user_google_email='{user_google_email}' explicitly in all tool calls for this account",
                    "",
                    "💡 **For CLI clients**: You can poll authentication status:",
                    f"   GET {settings.base_url}/oauth/status",
                ]
                message = "🔐 **Google Services Authentication Required**"
                if browser_error:
                    instructions.insert(
                        0, f"⚠️ Auto-browser open failed: {browser_error}"
                    )

            # Normalize service_name to list format for response
            service_names_list: Optional[list[str]] = None
            if isinstance(service_name, list):
                service_names_list = service_name
            elif isinstance(service_name, str) and service_name:
                # If it's a display string, don't include it as service names
                service_names_list = None

            # Get current session ID for reconnection support
            from auth.context import get_session_context

            current_session_id = await get_session_context()

            response = StartAuthResponse(
                status="success",
                message=message,
                authUrl=auth_url,
                clickableLink=f"[🚀 Click here to authenticate]({auth_url})",
                userEmail=user_google_email,
                sessionId=current_session_id,
                serviceName=service_names_list,
                instructions=instructions,
                scopesIncluded=[
                    "Google Drive (file management)",
                    "Gmail (email access)",
                    "Google Docs (document editing)",
                    "Google Sheets (spreadsheet access)",
                    "Google Slides (presentation management)",
                    "Google Calendar (event management)",
                    "And more Google services",
                ],
                note=(
                    "The authentication will be linked to your current session and provide "
                    "access to all Google services. Save your sessionId to reconnect with "
                    "the same tool state using ?uuid= parameter.\n\n"
                    f"⚠️ IMPORTANT: After authentication completes, you MUST pass "
                    f"user_google_email='{user_google_email}' explicitly in all subsequent "
                    f"tool calls for this account. Do NOT omit user_google_email or the "
                    f"server will default to the primary session account."
                ),
            )

            # Add browser-specific fields
            if hasattr(response, "__dict__"):
                response.__dict__["browserOpened"] = browser_opened
                response.__dict__["pollingEndpoint"] = (
                    f"{settings.base_url}/oauth/status"
                )
                if browser_error:
                    response.__dict__["browserError"] = browser_error

            return response

        except Exception as e:
            error_msg = f"Failed to start authentication: {e}"
            logger.error(error_msg, exc_info=True)
            return StartAuthResponse(
                status="error",
                message="❌ Authentication Setup Failed",
                userEmail=user_google_email,
                error=str(e),
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
            "openWorldHint": True,  # Verifies against external Google services
        },
    )
    async def check_drive_auth(
        user_google_email: UserGoogleEmailDrive = None,
        cross_oauth_password: Annotated[
            Optional[str],
            Field(
                description=(
                    "Passphrase for cross-OAuth account access. "
                    "Required when the linked account owner set a passphrase "
                    "during their start_google_auth setup. "
                    "Only alphanumeric, underscore, and hyphen allowed."
                )
            ),
        ] = None,
    ) -> CheckAuthResponse:
        """
        Verify Google Drive authentication status for a specific user account.

        This tool checks whether the specified user has valid, active Google Drive
        authentication credentials. It attempts to access the Drive service to
        validate the authentication state without performing any Drive operations.

        When accessing a linked account that has a cross-OAuth passphrase set,
        provide the passphrase via the cross_oauth_password parameter.

        Args:
            user_google_email: Google email address to verify authentication status for
            cross_oauth_password: Passphrase for cross-OAuth access to linked accounts

        Returns:
            CheckAuthResponse: Structured response indicating authentication state

        Raises:
            Handles GoogleAuthError for invalid/missing credentials and generic exceptions
        """
        # Stash cross-OAuth password in session for credential decryption
        if cross_oauth_password:
            try:
                from auth.context import get_session_context_sync, store_session_data
                from auth.types import SessionKey

                session_id = get_session_context_sync()
                if session_id:
                    store_session_data(
                        session_id,
                        SessionKey.OAUTH_LINKAGE_PASSWORD,
                        cross_oauth_password,
                    )
            except Exception as e:
                logger.debug(f"Could not stash cross-OAuth password: {e}")

        logger.info(f"Checking authentication for {user_google_email}")

        # Get current session ID for reconnection support
        from auth.context import get_session_context

        current_session_id = await get_session_context()

        # ── Detect session auth method and linked accounts ──
        auth_method = None
        key_bound_email = None
        linked_accounts = None

        try:
            from fastmcp.server.dependencies import get_access_token

            from auth.types import AuthProvenance

            try:
                access_token = get_access_token()
                if hasattr(access_token, "claims"):
                    claims = access_token.claims or {}
                    method = claims.get("auth_method")
                    if method == AuthProvenance.API_KEY:
                        auth_method = AuthProvenance.API_KEY
                    elif method == AuthProvenance.USER_API_KEY:
                        auth_method = AuthProvenance.USER_API_KEY
                        key_bound_email = claims.get("email")
                    else:
                        auth_method = AuthProvenance.OAUTH
            except RuntimeError:
                auth_method = AuthProvenance.OAUTH
        except Exception:
            pass

        # Resolve linked accounts for per-user key sessions
        if auth_method == AuthProvenance.USER_API_KEY and key_bound_email:
            try:
                from auth.user_api_keys import get_accessible_emails

                accessible = get_accessible_emails(key_bound_email)
                # Linked = accessible minus the key's own email
                others = sorted(e for e in accessible if e != key_bound_email.lower())
                if others:
                    linked_accounts = others
            except Exception:
                pass

        # Validate that user_google_email is provided
        if not user_google_email:
            return CheckAuthResponse(
                authenticated=False,
                userEmail="",
                sessionId=current_session_id,
                authMethod=auth_method,
                keyBoundEmail=key_bound_email,
                linkedAccounts=linked_accounts,
                message="No user email provided. Please provide a Google email address to check authentication status.",
                error="Missing user_google_email parameter",
            )

        try:
            # Use service helpers for better service management
            drive_service = await get_service("drive", user_google_email)

            # Test basic Drive access to verify authentication
            import asyncio

            await asyncio.to_thread(drive_service.about().get(fields="user").execute)

            # Try to read credential scopes
            cred_scopes = None
            try:
                from auth.middleware import AuthMiddleware

                mw = AuthMiddleware()
                creds = mw.load_credentials(user_google_email)
                if creds and creds.scopes:
                    cred_scopes = sorted(creds.scopes)
            except Exception:
                pass

            # Look up cross-OAuth linkage info for this account
            oauth_linkage_info = None
            try:
                from auth.user_api_keys import get_oauth_linkage
                from drive.upload_types import CrossOAuthLinkageInfo

                linkage = get_oauth_linkage(user_google_email)
                oauth_linkage_info = CrossOAuthLinkageInfo(
                    enabled=linkage.get("enabled", True),
                    has_password=linkage.get("has_password", False),
                )
            except Exception:
                pass

            msg = f"{user_google_email} is authenticated for Google Drive."
            if linked_accounts:
                msg += f" This key also has access to: {', '.join(linked_accounts)}."
            if oauth_linkage_info and oauth_linkage_info.has_password:
                msg += " Cross-OAuth access requires a passphrase (use cross_oauth_password parameter)."
            msg += " Save your sessionId to reconnect with the same tool state using ?uuid= parameter."

            return CheckAuthResponse(
                authenticated=True,
                userEmail=user_google_email,
                sessionId=current_session_id,
                authMethod=auth_method,
                keyBoundEmail=key_bound_email,
                linkedAccounts=linked_accounts,
                scopes=cred_scopes,
                crossOAuthLinkage=oauth_linkage_info,
                message=msg,
            )
        except GoogleAuthError:
            return CheckAuthResponse(
                authenticated=False,
                userEmail=user_google_email,
                sessionId=current_session_id,
                authMethod=auth_method,
                keyBoundEmail=key_bound_email,
                linkedAccounts=linked_accounts,
                message=f"{user_google_email} is not authenticated for Google Drive. Use the `start_google_auth` tool to authenticate.",
            )
        except Exception as e:
            error_msg = f"Error checking authentication: {e}"
            logger.error(f"❌ {error_msg}")
            return CheckAuthResponse(
                authenticated=False,
                userEmail=user_google_email,
                sessionId=current_session_id,
                authMethod=auth_method,
                keyBoundEmail=key_bound_email,
                linkedAccounts=linked_accounts,
                message="",
                error=error_msg,
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
            "openWorldHint": True,
        },
    )
    async def upload_to_drive(
        path: Annotated[
            Optional[str],
            Field(
                description="Local filesystem path to the file or folder to upload (supports ~ expansion)"
            ),
        ] = None,
        folder_id: Annotated[
            str,
            Field(
                description="Google Drive folder ID where file will be uploaded (default: 'root' for root folder)"
            ),
        ] = "root",
        filename: Annotated[
            Optional[str],
            Field(
                description="Custom filename for the uploaded file (optional - uses original filename if not provided)"
            ),
        ] = None,
        user_google_email: UserGoogleEmailDrive = None,
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

        # Validate required path parameter
        if not path:
            return UploadFileResponse(
                success=False,
                userEmail="",
                message="",
                error=(
                    "Missing required parameter 'path'. Please provide the local file path to upload.\n"
                    "Example: upload_to_drive(path='/path/to/file.txt', user_google_email='user@example.com')"
                ),
            )

        # Get user email from middleware context if not provided
        if not user_google_email:
            user_google_email = await get_user_email_context()
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
                    ),
                )
            logger.info(
                f"🔑 Using authenticated user from unified context: {user_google_email}"
            )

        logger.info(
            f"Upload request: {path} -> Drive folder {folder_id} for {user_google_email}"
        )

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
                    user_email=user_google_email,
                )
            else:
                # Single file upload
                result = await upload_file_to_drive_api(
                    service=drive_service,
                    file_path=local_path,
                    folder_id=folder_id,
                    custom_filename=filename,
                )

                # Build file info
                file_info: FileUploadInfo = {
                    "fileId": result["id"],
                    "fileName": result["name"],
                    "filePath": str(local_path),
                    "fileSize": local_path.stat().st_size,
                    "mimeType": result.get("mimeType", "application/octet-stream"),
                    "folderId": folder_id,
                    "driveUrl": f"https://drive.google.com/file/d/{result['id']}/view",
                    "webViewLink": result.get(
                        "webViewLink",
                        f"https://drive.google.com/file/d/{result['id']}/view",
                    ),
                }

                logger.info(f"Upload successful: {result['name']} (ID: {result['id']})")

                return UploadFileResponse(
                    success=True,
                    userEmail=user_google_email,
                    fileInfo=file_info,
                    message=f"Successfully uploaded {result['name']} to Google Drive",
                )

        except GoogleAuthError as e:
            error_msg = f"Authentication error: {e}"
            logger.error(f"❌ {error_msg}")
            return UploadFileResponse(
                success=False, userEmail=user_google_email, message="", error=error_msg
            )
        except DriveUploadError as e:
            error_msg = f"Upload error: {e}"
            logger.error(f"❌ {error_msg}")
            return UploadFileResponse(
                success=False, userEmail=user_google_email, message="", error=error_msg
            )
        except FileNotFoundError:
            error_msg = f"Path not found: {path}"
            logger.error(f"❌ {error_msg}")
            return UploadFileResponse(
                success=False, userEmail=user_google_email, message="", error=error_msg
            )
        except PermissionError:
            error_msg = f"Permission denied accessing: {path}"
            logger.error(f"❌ {error_msg}")
            return UploadFileResponse(
                success=False, userEmail=user_google_email, message="", error=error_msg
            )
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            return UploadFileResponse(
                success=False, userEmail=user_google_email, message="", error=error_msg
            )


async def _upload_folder_to_drive(
    drive_service: Any,
    folder_path: Path,
    parent_folder_id: str,
    custom_folder_name: Optional[str],
    user_email: str,
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
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_folder_id],
        }

        import asyncio

        folder_result = await asyncio.to_thread(
            drive_service.files()
            .create(body=folder_metadata, fields="id, name, webViewLink")
            .execute
        )

        root_folder_id = folder_result["id"]
        logger.info(f"Created folder '{folder_name}' with ID: {root_folder_id}")

        # Walk through the folder structure
        for item_path in folder_path.rglob("*"):
            if item_path.is_file():
                try:
                    # Calculate relative path for folder structure
                    relative_path = item_path.relative_to(folder_path)
                    relative_parent = relative_path.parent

                    # Determine the parent folder ID (create nested folders if needed)
                    current_parent_id = root_folder_id
                    if str(relative_parent) != ".":
                        # Need to create nested folder structure
                        parts = relative_parent.parts
                        for part in parts:
                            # Check if folder exists or create it
                            query = f"name='{part}' and '{current_parent_id}' in parents and mimeType='application/vnd.google-apps.folder'"
                            existing = await asyncio.to_thread(
                                drive_service.files()
                                .list(q=query, fields="files(id)")
                                .execute
                            )

                            if existing.get("files"):
                                current_parent_id = existing["files"][0]["id"]
                            else:
                                # Create the folder
                                folder_meta = {
                                    "name": part,
                                    "mimeType": "application/vnd.google-apps.folder",
                                    "parents": [current_parent_id],
                                }
                                new_folder = await asyncio.to_thread(
                                    drive_service.files()
                                    .create(body=folder_meta, fields="id")
                                    .execute
                                )
                                current_parent_id = new_folder["id"]

                    # Upload the file
                    result = await upload_file_to_drive_api(
                        service=drive_service,
                        file_path=item_path,
                        folder_id=current_parent_id,
                    )

                    file_size = item_path.stat().st_size
                    total_size += file_size

                    file_info: FileUploadInfo = {
                        "fileId": result["id"],
                        "fileName": result["name"],
                        "filePath": str(item_path),
                        "fileSize": file_size,
                        "mimeType": result.get("mimeType", "application/octet-stream"),
                        "folderId": current_parent_id,
                        "driveUrl": f"https://drive.google.com/file/d/{result['id']}/view",
                        "webViewLink": result.get(
                            "webViewLink",
                            f"https://drive.google.com/file/d/{result['id']}/view",
                        ),
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
            "uploadDuration": upload_duration,
        }

        return UploadFileResponse(
            success=True,
            userEmail=user_email,
            filesUploaded=uploaded_files,
            folderSummary=folder_summary,
            message=f"Successfully uploaded folder '{folder_name}' with {len(uploaded_files)} files to Google Drive",
            warnings=warnings if warnings else None,
        )

    except Exception as e:
        error_msg = f"Failed to upload folder: {str(e)}"
        logger.error(error_msg)
        return UploadFileResponse(
            success=False, userEmail=user_email, message="", error=error_msg
        )


def setup_oauth_callback_handler(mcp: FastMCP) -> None:
    """
    Setup OAuth2 callback route handler for FastMCP2 server.

    NOTE: This function is now deprecated. The OAuth callback handler
    has been moved to auth/fastmcp_oauth_endpoints.py where it belongs
    with all other OAuth endpoints.

    Args:
        mcp: FastMCP server instance to register the route with

    Returns:
        None: No-op - callback handler is now in fastmcp_oauth_endpoints.py
    """
    logger.info(
        "ℹ️ OAuth callback handler registration skipped - now handled in fastmcp_oauth_endpoints.py"
    )
    pass


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
