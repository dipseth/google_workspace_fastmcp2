"""Authentication middleware for session management and service injection."""

import logging

from config.enhanced_logging import setup_logger
logger = setup_logger()
import json
import base64
import secrets
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing_extensions import Any, Optional, Dict
from enum import Enum

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.dependencies import get_context
from google.oauth2.credentials import Credentials

# Try to import GoogleProvider - it might not be available
try:
    from fastmcp.server.auth.providers.google import GoogleProvider
    GOOGLE_PROVIDER_AVAILABLE = True
except ImportError:
    GoogleProvider = None
    GOOGLE_PROVIDER_AVAILABLE = False

from .context import (
    set_session_context,
    clear_session_context,
    clear_all_context,
    cleanup_expired_sessions,
    get_session_context,
    set_user_email_context,
    get_user_email_context,
    _get_pending_service_requests,
    _set_injected_service,
    _set_service_error
)
from .service_manager import get_google_service, GoogleServiceError
from config.settings import settings
from .dual_auth_bridge import get_dual_auth_bridge

logger = logging.getLogger(__name__)


class CredentialStorageMode(Enum):
    """Credential storage modes."""
    FILE_PLAINTEXT = "file_plaintext"        # Current: JSON files (backward compatible)
    FILE_ENCRYPTED = "file_encrypted"        # New: Encrypted JSON files
    MEMORY_ONLY = "memory_only"              # New: In-memory only (no persistence)
    MEMORY_WITH_BACKUP = "memory_with_backup" # New: Memory + encrypted backup


class AuthMiddleware(Middleware):
    """Enhanced middleware for secure credential management, session context, service injection, and FastMCP GoogleProvider integration."""
    
    def __init__(self,
                 storage_mode: CredentialStorageMode = CredentialStorageMode.FILE_ENCRYPTED,
                 encryption_key: Optional[str] = None,
                 google_provider: Optional['GoogleProvider'] = None):
        """
        Initialize AuthMiddleware with configurable credential storage and GoogleProvider integration.
        
        Args:
            storage_mode: How to store credentials (file_plaintext, file_encrypted, memory_only, memory_with_backup)
            encryption_key: Custom encryption key (auto-generated if not provided for encrypted modes)
            google_provider: FastMCP 2.12.0 GoogleProvider instance for unified authentication
        """
        self._last_cleanup = datetime.now()
        self._cleanup_interval_minutes = 30
        self._service_injection_enabled = True
        
        # Credential storage configuration
        self._storage_mode = storage_mode
        self._memory_credentials: Dict[str, Credentials] = {}
        self._encryption_key = encryption_key
        
        # GoogleProvider integration for unified authentication
        self._google_provider = google_provider
        self._unified_auth_enabled = bool(google_provider and settings.enable_unified_auth)
        
        # Initialize dual auth bridge
        self._dual_auth_bridge = get_dual_auth_bridge()
        
        # Initialize encryption if needed
        if storage_mode in [CredentialStorageMode.FILE_ENCRYPTED, CredentialStorageMode.MEMORY_WITH_BACKUP]:
            self._setup_encryption()
        
        logger.info(f"🔐 AuthMiddleware initialized with storage mode: {storage_mode.value}")
        
        if self._unified_auth_enabled:
            logger.info("✅ Unified authentication enabled (FastMCP GoogleProvider integration)")
            logger.info("🔄 GoogleProvider ↔ Legacy Tool Bridge active")
            logger.info("🌉 Dual Auth Bridge initialized for multi-account support")
        else:
            logger.info("⭕ Unified authentication disabled (no GoogleProvider or enable_unified_auth=False)")
        
        # Log security recommendations
        if storage_mode == CredentialStorageMode.FILE_PLAINTEXT:
            logger.warning("⚠️ Using plaintext file storage - consider upgrading to FILE_ENCRYPTED for production")
    
    async def on_request(self, context: MiddlewareContext, call_next):
        """Handle incoming requests and set session context."""
        from .context import store_session_data, get_session_data, list_sessions
        
        # FIRST: Check if we already have a session context set
        existing_session = get_session_context()
        if existing_session:
            session_id = existing_session
            logger.info(f"✅ Reusing existing session context: {session_id}")
        else:
            # Try to extract session ID from various possible locations
            session_id = None
            
            # Try FastMCP context first
            if hasattr(context, 'fastmcp_context') and context.fastmcp_context:
                session_id = getattr(context.fastmcp_context, 'session_id', None)
            
            # Try to get from headers or other context
            if not session_id and hasattr(context, 'request'):
                # Try to extract from request headers or similar
                session_id = getattr(context.request, 'session_id', None)
            
            # If still no session, check if we have any active sessions and use the most recent
            if not session_id:
                active_sessions = list_sessions()
                if active_sessions:
                    # Use the most recently used session
                    session_id = active_sessions[-1]
                    logger.info(f"♻️ Reusing most recent active session: {session_id}")
                else:
                    # Generate a new session ID only if absolutely necessary
                    import uuid
                    session_id = str(uuid.uuid4())
                    logger.info(f"🆕 Generated new session ID (no active sessions found): {session_id}")
        
        set_session_context(session_id)
        logger.info(f"🔍 DEBUG: Set session context: {session_id}")
        
        # Check if we have a stored user email for this session (from OAuth)
        user_email = get_session_data(session_id, "user_email")
        if user_email:
            set_user_email_context(user_email)
            logger.info(f"🔍 DEBUG: Restored user email context from session: {user_email}")
        else:
            logger.info(f"🔍 DEBUG: No stored user email found for session: {session_id}")
        
        # Periodic cleanup of expired sessions
        now = datetime.now()
        if (now - self._last_cleanup).total_seconds() > (self._cleanup_interval_minutes * 60):
            try:
                cleanup_expired_sessions(settings.session_timeout_minutes)
                self._last_cleanup = now
                logger.debug("Performed periodic session cleanup")
            except Exception as e:
                logger.error(f"Error during session cleanup: {e}")
        
        try:
            result = await call_next(context)
            return result
        except Exception as e:
            logger.error(f"Error in request processing: {e}")
            raise
        finally:
            # Don't clear session context - we need it to persist!
            # Only clear service requests to avoid memory leaks
            try:
                ctx = get_context()
                ctx.set_state("service_requests", {})
            except RuntimeError:
                pass
            logger.debug(f"🔍 DEBUG: Preserving session context {session_id} for future requests")
    
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """
        Handle tool execution with session context, service injection, and unified GoogleProvider authentication.
        
        This method implements the unified OAuth architecture by:
        1. Extracting user context from GoogleProvider if available
        2. Auto-injecting user_google_email into tool calls
        3. Bridging credentials between authentication systems
        4. Providing seamless tool execution
        
        Args:
            context: MiddlewareContext containing tool call information
            call_next: Function to continue the middleware chain
        """
        from .context import store_session_data, get_session_data
        
        tool_name = getattr(context.message, 'name', 'unknown')
        logger.debug(f"Processing tool call: {tool_name}")
        
        # Session context should already be set by on_request
        session_id = get_session_context()
        if not session_id:
            # This shouldn't happen, but handle gracefully
            # Check for any active sessions first
            from .context import list_sessions
            active_sessions = list_sessions()
            if active_sessions:
                session_id = active_sessions[-1]
                set_session_context(session_id)
                logger.info(f"♻️ Reactivated session for tool {tool_name}: {session_id}")
            else:
                # Only generate new if absolutely necessary
                import uuid
                session_id = str(uuid.uuid4())
                set_session_context(session_id)
                logger.warning(f"⚠️ Had to generate new session for tool {tool_name}: {session_id}")
        else:
            logger.info(f"✅ Using existing session for tool {tool_name}: {session_id}")
        
        # FastMCP Pattern: FIRST try JWT token (following FastMCP examples)
        user_email = None
        logger.info(f"🔍 Starting user extraction for tool {tool_name}")
        
        # JWT AUTH: Primary authentication method following FastMCP pattern
        user_email = self._extract_user_from_jwt_token()
        if user_email:
            logger.info(f"🎫 Extracted user from JWT token for tool {tool_name}: {user_email}")
            # Register as primary account in dual auth bridge
            self._dual_auth_bridge.set_primary_account(user_email)
            # Store in session for future use
            if session_id:
                store_session_data(session_id, "user_email", user_email)
            # Set context immediately
            set_user_email_context(user_email)
            # Auto-inject into tool arguments if missing
            await self._auto_inject_email_parameter(context, user_email)
        else:
            logger.debug(f"No JWT token authentication found for tool {tool_name}")
        
        # UNIFIED AUTH: Secondary - try GoogleProvider if configured
        if not user_email and self._unified_auth_enabled:
            user_email = await self._extract_user_from_google_provider()
            if user_email:
                logger.info(f"🔑 Extracted user from GoogleProvider for tool {tool_name}: {user_email}")
                # Store in session for future use
                if session_id:
                    store_session_data(session_id, "user_email", user_email)
                # Set context immediately
                set_user_email_context(user_email)
                # Auto-inject into tool arguments if missing
                await self._auto_inject_email_parameter(context, user_email)
            else:
                logger.debug(f"No GoogleProvider authentication found for tool {tool_name}")
        
        # LEGACY AUTH: Fallback to session data (OAuth authenticated)
        if not user_email and session_id:
            user_email = get_session_data(session_id, "user_email")
            if user_email:
                logger.info(f"✅ Retrieved user email from session storage for tool {tool_name}: {user_email}")
                # Also set it in context for immediate use
                set_user_email_context(user_email)
                # Auto-inject into tool arguments
                await self._auto_inject_email_parameter(context, user_email)
            else:
                logger.info(f"⚠️ No user email in session storage for session {session_id}")
        
        # OAUTH FILE FALLBACK: Check for stored OAuth authentication data
        if not user_email:
            user_email = self._load_oauth_authentication_data()
            if user_email:
                logger.info(f"✅ Retrieved user email from OAuth authentication file for tool {tool_name}: {user_email}")
                # Register as secondary account in dual auth bridge
                self._dual_auth_bridge.add_secondary_account(user_email)
                # Store in session for future use
                if session_id:
                    store_session_data(session_id, "user_email", user_email)
                # Set context immediately
                set_user_email_context(user_email)
                # Auto-inject into tool arguments if missing
                await self._auto_inject_email_parameter(context, user_email)
            else:
                logger.debug(f"No OAuth authentication file found for tool {tool_name}")
        
        # LEGACY AUTH: Fallback to tool arguments
        if not user_email:
            user_email = self._extract_user_email(context)
            if user_email:
                logger.info(f"🔍 DEBUG: Extracted user email from tool arguments for tool {tool_name}: {user_email}")
                # Check if this is a known account or register as secondary
                if not (self._dual_auth_bridge.is_primary_account(user_email) or
                        self._dual_auth_bridge.is_secondary_account(user_email)):
                    self._dual_auth_bridge.add_secondary_account(user_email)
                # Store it in session for future use
                if session_id:
                    store_session_data(session_id, "user_email", user_email)
            else:
                logger.info(f"🔍 DEBUG: No user email found in tool arguments for tool {tool_name}")
        
        # Set user email context if found
        if user_email:
            set_user_email_context(user_email)
            logger.info(f"🔍 DEBUG: Set user email context for tool {tool_name}: {user_email}")
            
            # Bridge credentials if needed (GoogleProvider → Legacy)
            if self._unified_auth_enabled:
                await self._bridge_credentials_if_needed(user_email)
        else:
            logger.info(f"🔍 DEBUG: No user email available for tool {tool_name}")
        
        # Handle service injection if enabled
        if self._service_injection_enabled:
            await self._inject_services(tool_name, user_email)
        
        try:
            result = await call_next(context)
            logger.debug(f"Tool {tool_name} executed successfully")
            return result
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            raise
    
    async def on_read_resource(self, context: MiddlewareContext, call_next):
        """
        Handle resource access with session context and unified GoogleProvider authentication.
        
        This method implements the unified OAuth architecture for resource access by:
        1. Extracting user context from GoogleProvider if available
        2. Setting user email context for resource authentication
        3. Bridging credentials between authentication systems
        4. Ensuring resources work immediately after OAuth authentication
        
        Args:
            context: MiddlewareContext containing resource access information
            call_next: Function to continue the middleware chain
        """
        from .context import store_session_data, get_session_data
        
        resource_uri = getattr(context, 'uri', 'unknown')
        logger.debug(f"Processing resource access: {resource_uri}")
        
        # Session context should already be set by on_request
        session_id = get_session_context()
        if not session_id:
            # This shouldn't happen, but handle gracefully
            # Check for any active sessions first
            from .context import list_sessions
            active_sessions = list_sessions()
            if active_sessions:
                session_id = active_sessions[-1]
                set_session_context(session_id)
                logger.info(f"♻️ Reactivated session for resource {resource_uri}: {session_id}")
            else:
                # Only generate new if absolutely necessary
                import uuid
                session_id = str(uuid.uuid4())
                set_session_context(session_id)
                logger.warning(f"⚠️ Had to generate new session for resource {resource_uri}: {session_id}")
        else:
            logger.info(f"✅ Using existing session for resource {resource_uri}: {session_id}")
        
        # FastMCP Pattern: FIRST try JWT token (following FastMCP examples)
        user_email = None
        logger.info(f"🔍 Starting user extraction for resource {resource_uri}")
        
        # JWT AUTH: Primary authentication method following FastMCP pattern
        user_email = self._extract_user_from_jwt_token()
        if user_email:
            logger.info(f"🎫 Extracted user from JWT token for resource {resource_uri}: {user_email}")
            # Store in session for future use
            if session_id:
                store_session_data(session_id, "user_email", user_email)
            # Set context immediately
            set_user_email_context(user_email)
        else:
            logger.debug(f"No JWT token authentication found for resource {resource_uri}")
        
        # UNIFIED AUTH: Secondary - try GoogleProvider if configured
        if not user_email and self._unified_auth_enabled:
            user_email = await self._extract_user_from_google_provider()
            if user_email:
                logger.info(f"🔑 Extracted user from GoogleProvider for resource {resource_uri}: {user_email}")
                # Store in session for future use
                if session_id:
                    store_session_data(session_id, "user_email", user_email)
                # Set context immediately
                set_user_email_context(user_email)
            else:
                logger.debug(f"No GoogleProvider authentication found for resource {resource_uri}")
        
        # LEGACY AUTH: Fallback to session data (OAuth authenticated)
        if not user_email and session_id:
            user_email = get_session_data(session_id, "user_email")
            if user_email:
                logger.info(f"✅ Retrieved user email from session storage for resource {resource_uri}: {user_email}")
                # Also set it in context for immediate use
                set_user_email_context(user_email)
            else:
                logger.info(f"⚠️ No user email in session storage for session {session_id}")
        
        # OAUTH FILE FALLBACK: Check for stored OAuth authentication data
        if not user_email:
            user_email = self._load_oauth_authentication_data()
            if user_email:
                logger.info(f"✅ Retrieved user email from OAuth authentication file for resource {resource_uri}: {user_email}")
                # Store in session for future use
                if session_id:
                    store_session_data(session_id, "user_email", user_email)
                # Set context immediately
                set_user_email_context(user_email)
            else:
                logger.debug(f"No OAuth authentication file found for resource {resource_uri}")
        
        # Set user email context if found
        if user_email:
            set_user_email_context(user_email)
            logger.info(f"🔍 DEBUG: Set user email context for resource {resource_uri}: {user_email}")
            
            # Bridge credentials if needed (GoogleProvider → Legacy)
            if self._unified_auth_enabled:
                await self._bridge_credentials_if_needed(user_email)
        else:
            logger.info(f"🔍 DEBUG: No user email available for resource {resource_uri}")
        
        try:
            result = await call_next(context)
            logger.debug(f"Resource {resource_uri} accessed successfully")
            return result
        except Exception as e:
            logger.error(f"Error accessing resource {resource_uri}: {e}")
            raise
    
    def _extract_user_email(self, context: MiddlewareContext) -> str:
        """
        Extract user email from tool arguments.
        
        Common parameter names: user_email, user_google_email, email
        """
        try:
            # Get arguments from the message
            if hasattr(context.message, 'arguments') and context.message.arguments:
                args = context.message.arguments
                
                # Try common user email parameter names
                for param_name in ['user_email', 'user_google_email', 'email', 'google_email']:
                    if param_name in args and args[param_name]:
                        return args[param_name]
            
            logger.debug("No user email found in tool arguments")
            return None
            
        except Exception as e:
            logger.warning(f"Error extracting user email from tool arguments: {e}")
            return None
    
    async def _inject_services(self, tool_name: str, user_email: str):
        """
        Inject requested Google services into the context using secure credential loading.
        
        Args:
            tool_name: Name of the tool being executed
            user_email: User's email address for service authentication
        """
        if not user_email:
            logger.debug(f"No user email available for service injection in tool: {tool_name}")
            return
        
        # Get pending service requests
        pending_requests = _get_pending_service_requests()
        
        if not pending_requests:
            logger.debug(f"No pending service requests for tool: {tool_name}")
            return
        
        logger.info(f"🔧 Injecting {len(pending_requests)} Google services for tool: {tool_name} (storage: {self._storage_mode.value})")
        
        # Fulfill each service request
        for service_key, service_data in pending_requests.items():
            try:
                service_type = service_data["service_type"]
                scopes = service_data["scopes"]
                version = service_data["version"]
                cache_enabled = service_data["cache_enabled"]
                
                logger.debug(f"Creating {service_type} service for {user_email}")
                
                # Create the Google service using the new credential management
                service = await get_google_service(
                    user_email=user_email,
                    service_type=service_type,
                    scopes=scopes,
                    version=version,
                    cache_enabled=cache_enabled
                )
                
                # Inject the service into context
                _set_injected_service(service_key, service)
                
                logger.info(
                    f"✅ Successfully injected {service_type} service "
                    f"for {user_email} in tool {tool_name}"
                )
                
            except GoogleServiceError as e:
                error_msg = f"Failed to create {service_data['service_type']} service: {str(e)}"
                logger.error(f"❌ Service injection error for {tool_name}: {error_msg}")
                _set_service_error(service_key, error_msg)
                
            except Exception as e:
                error_msg = f"Unexpected error creating {service_data['service_type']} service: {str(e)}"
                logger.error(f"❌ Service injection error for {tool_name}: {error_msg}")
                _set_service_error(service_key, error_msg)
    
    def enable_service_injection(self, enabled: bool = True):
        """Enable or disable automatic service injection."""
        self._service_injection_enabled = enabled
        logger.info(f"Service injection {'enabled' if enabled else 'disabled'}")
    
    def _setup_encryption(self):
        """Setup encryption for secure credential storage."""
        try:
            if self._encryption_key:
                # Use provided key
                key_bytes = base64.urlsafe_b64decode(self._encryption_key.encode())
            else:
                # Generate or load encryption key
                key_path = Path(settings.credentials_dir) / ".auth_encryption_key"
                
                if key_path.exists():
                    with open(key_path, "rb") as f:
                        key_bytes = f.read()
                else:
                    # Generate new key
                    key_bytes = base64.urlsafe_b64encode(secrets.token_bytes(32))
                    key_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    with open(key_path, "wb") as f:
                        f.write(key_bytes)
                    
                    # Set restrictive permissions
                    try:
                        key_path.chmod(0o600)
                    except (OSError, AttributeError):
                        logger.warning("Could not set restrictive permissions on encryption key")
            
            # Import here to avoid dependency issues if cryptography not installed
            from cryptography.fernet import Fernet
            self._fernet = Fernet(key_bytes)
            logger.info("✅ Encryption initialized for secure credential storage")
            
        except ImportError:
            logger.error("❌ cryptography package required for encrypted storage. Install with: pip install cryptography")
            logger.info("🔄 Falling back to plaintext storage...")
            self._storage_mode = CredentialStorageMode.FILE_PLAINTEXT
        except Exception as e:
            logger.error(f"❌ Failed to setup encryption: {e}")
            logger.info("🔄 Falling back to plaintext storage...")
            self._storage_mode = CredentialStorageMode.FILE_PLAINTEXT
    
    def _encrypt_credentials(self, credentials: Credentials) -> str:
        """Encrypt credentials for secure storage."""
        if not hasattr(self, '_fernet'):
            raise RuntimeError("Encryption not initialized")
        
        creds_data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes,
            "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
            "encrypted_at": datetime.now().isoformat(),
            "storage_mode": self._storage_mode.value
        }
        
        json_data = json.dumps(creds_data).encode()
        encrypted_data = self._fernet.encrypt(json_data)
        return base64.urlsafe_b64encode(encrypted_data).decode()
    
    def _decrypt_credentials(self, encrypted_data: str) -> Credentials:
        """Decrypt and reconstruct credentials."""
        if not hasattr(self, '_fernet'):
            raise RuntimeError("Encryption not initialized")
        
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted_data = self._fernet.decrypt(encrypted_bytes)
            creds_data = json.loads(decrypted_data.decode())
            
            credentials = Credentials(
                token=creds_data["token"],
                refresh_token=creds_data["refresh_token"],
                token_uri=creds_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=creds_data["client_id"],
                client_secret=creds_data["client_secret"],
                scopes=creds_data.get("scopes", settings.drive_scopes)
            )
            
            if creds_data.get("expiry"):
                credentials.expiry = datetime.fromisoformat(creds_data["expiry"])
            
            return credentials
            
        except Exception as e:
            logger.error(f"Failed to decrypt credentials: {e}")
            raise
    
    def save_credentials(self, user_email: str, credentials: Credentials) -> None:
        """
        Save credentials using the configured storage mode.
        
        Args:
            user_email: User's email address
            credentials: Google OAuth credentials
        """
        logger.info(f"💾 Saving credentials for {user_email} using {self._storage_mode.value}")
        
        if self._storage_mode == CredentialStorageMode.MEMORY_ONLY:
            # Store only in memory
            self._memory_credentials[user_email] = credentials
            logger.debug(f"Stored credentials in memory for {user_email}")
            
        elif self._storage_mode == CredentialStorageMode.FILE_PLAINTEXT:
            # Backward compatibility - use existing file-based storage
            from .google_auth import _save_credentials
            _save_credentials(user_email, credentials)
            
        elif self._storage_mode == CredentialStorageMode.FILE_ENCRYPTED:
            # Encrypted file storage
            safe_email = user_email.replace("@", "_at_").replace(".", "_")
            creds_path = Path(settings.credentials_dir) / f"{safe_email}_credentials.enc"
            creds_path.parent.mkdir(parents=True, exist_ok=True)
            
            encrypted_data = self._encrypt_credentials(credentials)
            
            with open(creds_path, "w") as f:
                f.write(encrypted_data)
            
            # Set restrictive permissions
            try:
                creds_path.chmod(0o600)
            except (OSError, AttributeError):
                logger.warning("Could not set restrictive permissions on credential file")
            
            logger.info(f"✅ Saved encrypted credentials for {user_email}")
            
        elif self._storage_mode == CredentialStorageMode.MEMORY_WITH_BACKUP:
            # Store in memory + encrypted backup
            self._memory_credentials[user_email] = credentials
            
            # Also save encrypted backup
            safe_email = user_email.replace("@", "_at_").replace(".", "_")
            backup_path = Path(settings.credentials_dir) / f"{safe_email}_backup.enc"
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            
            encrypted_data = self._encrypt_credentials(credentials)
            
            with open(backup_path, "w") as f:
                f.write(encrypted_data)
            
            try:
                backup_path.chmod(0o600)
            except (OSError, AttributeError):
                pass
            
            logger.info(f"✅ Saved credentials in memory + encrypted backup for {user_email}")
    
    def load_credentials(self, user_email: str) -> Optional[Credentials]:
        """
        Load credentials using the configured storage mode.
        
        Args:
            user_email: User's email address
            
        Returns:
            Credentials if found, None otherwise
        """
        if self._storage_mode == CredentialStorageMode.MEMORY_ONLY:
            return self._memory_credentials.get(user_email)
            
        elif self._storage_mode == CredentialStorageMode.MEMORY_WITH_BACKUP:
            # Try memory first
            if user_email in self._memory_credentials:
                return self._memory_credentials[user_email]
            
            # Fall back to encrypted backup
            safe_email = user_email.replace("@", "_at_").replace(".", "_")
            backup_path = Path(settings.credentials_dir) / f"{safe_email}_backup.enc"
            
            if backup_path.exists():
                try:
                    with open(backup_path, "r") as f:
                        encrypted_data = f.read()
                    
                    credentials = self._decrypt_credentials(encrypted_data)
                    # Restore to memory
                    self._memory_credentials[user_email] = credentials
                    logger.info(f"🔄 Restored credentials from backup for {user_email}")
                    return credentials
                    
                except Exception as e:
                    logger.error(f"Failed to load credential backup for {user_email}: {e}")
            
            return None
            
        elif self._storage_mode == CredentialStorageMode.FILE_ENCRYPTED:
            safe_email = user_email.replace("@", "_at_").replace(".", "_")
            creds_path = Path(settings.credentials_dir) / f"{safe_email}_credentials.enc"
            
            if not creds_path.exists():
                return None
            
            try:
                with open(creds_path, "r") as f:
                    encrypted_data = f.read()
                
                return self._decrypt_credentials(encrypted_data)
                
            except Exception as e:
                logger.error(f"Failed to load encrypted credentials for {user_email}: {e}")
                return None
                
        elif self._storage_mode == CredentialStorageMode.FILE_PLAINTEXT:
            # Backward compatibility - use existing file-based storage
            from .google_auth import _load_credentials
            return _load_credentials(user_email)
        
        return None
    
    def get_storage_mode(self) -> CredentialStorageMode:
        """Get the current credential storage mode."""
        return self._storage_mode
    
    def get_credential_summary(self) -> Dict[str, Any]:
        """Get summary of stored credentials for debugging."""
        summary = {
            "storage_mode": self._storage_mode.value,
            "memory_credentials": list(self._memory_credentials.keys()),
            "file_credentials": []
        }
        
        # Check file-based credentials
        try:
            creds_dir = Path(settings.credentials_dir)
            if creds_dir.exists():
                for pattern in ["*_credentials.json", "*_credentials.enc", "*_backup.enc"]:
                    for file_path in creds_dir.glob(pattern):
                        safe_email = file_path.stem.replace("_credentials", "").replace("_backup", "")
                        email = safe_email.replace("_at_", "@").replace("_", ".")
                        summary["file_credentials"].append({
                            "email": email,
                            "file": file_path.name,
                            "encrypted": file_path.suffix == ".enc"
                        })
        except Exception as e:
            summary["file_error"] = str(e)
        
        return summary

    def is_service_injection_enabled(self) -> bool:
        """Check if service injection is enabled."""
        return self._service_injection_enabled
    
    def migrate_credentials(self, target_mode: CredentialStorageMode) -> Dict[str, str]:
        """
        Migrate existing credentials to a different storage mode.
        
        Args:
            target_mode: Target storage mode to migrate to
            
        Returns:
            Dictionary with migration results per user
        """
        results = {}
        
        # Get current credentials
        current_summary = self.get_credential_summary()
        
        # Find all users with credentials
        all_users = set()
        
        # Add users from memory
        all_users.update(current_summary.get("memory_credentials", []))
        
        # Add users from files
        for file_info in current_summary.get("file_credentials", []):
            all_users.add(file_info["email"])
        
        logger.info(f"🔄 Migrating {len(all_users)} users to {target_mode.value}")
        
        # Migrate each user
        for user_email in all_users:
            try:
                # Load credentials using current mode
                credentials = self.load_credentials(user_email)
                
                if credentials:
                    # Temporarily switch to target mode
                    old_mode = self._storage_mode
                    self._storage_mode = target_mode
                    
                    # Save using new mode
                    self.save_credentials(user_email, credentials)
                    
                    # Restore original mode for next user
                    self._storage_mode = old_mode
                    
                    results[user_email] = f"✅ Migrated to {target_mode.value}"
                else:
                    results[user_email] = "⚠️ No credentials found"
                    
            except Exception as e:
                results[user_email] = f"❌ Migration failed: {str(e)}"
                logger.error(f"Failed to migrate credentials for {user_email}: {e}")
        
        # Update to target mode
        self._storage_mode = target_mode
        logger.info(f"✅ Migration completed. New storage mode: {target_mode.value}")
        
        return results
    
    async def _extract_user_from_google_provider(self) -> Optional[str]:
        """
        Extract user email from FastMCP 2.12.0 GoogleProvider token context.
        
        This implements the unified OAuth architecture by extracting authenticated 
        user information from GoogleProvider without requiring manual email parameters.
        
        Returns:
            User email address if authenticated via GoogleProvider, None otherwise
        """
        if not self._google_provider:
            return None
        
        try:
            # Get current FastMCP context
            ctx = get_context()
            
            # Method 1: Check for GoogleProvider authentication token
            # The exact API may vary based on FastMCP 2.12.0 implementation
            token_info = getattr(ctx, '_auth_token', None)
            if token_info:
                # Extract email from token claims
                claims = getattr(token_info, 'claims', {})
                user_email = claims.get('email')
                
                if user_email:
                    logger.debug(f"📧 Found user email in GoogleProvider token claims: {user_email}")
                    return user_email
            
            # Method 2: Check FastMCP context state for user info
            # This might be set by GoogleProvider after authentication
            user_email = ctx.get_state('authenticated_user_email')
            if user_email:
                logger.debug(f"📧 Found user email in GoogleProvider context state: {user_email}")
                return user_email
            
            # Method 3: Alternative - Check if GoogleProvider has current user info
            if hasattr(self._google_provider, 'get_current_user'):
                try:
                    current_user = await self._google_provider.get_current_user()
                    if current_user and hasattr(current_user, 'email'):
                        logger.debug(f"📧 Found user email via GoogleProvider.get_current_user: {current_user.email}")
                        return current_user.email
                except Exception as e:
                    logger.debug(f"Could not get current user from GoogleProvider: {e}")
            
            return None
            
        except Exception as e:
            logger.debug(f"🔍 Could not extract user from GoogleProvider: {e}")
            return None
    
    async def _bridge_credentials_if_needed(self, user_email: str) -> None:
        """
        Bridge GoogleProvider credentials to legacy credential system if needed.
        
        This ensures that tools expecting legacy credentials can still work
        with GoogleProvider authentication. This is a key part of the unified
        OAuth architecture that maintains backward compatibility.
        
        Args:
            user_email: User's email address
        """
        try:
            # Check if user already has valid legacy credentials
            from .google_auth import get_valid_credentials
            existing_credentials = get_valid_credentials(user_email)
            if existing_credentials and not existing_credentials.expired:
                logger.debug(f"✅ User {user_email} has valid legacy credentials, no bridging needed")
                return
            
            # If no valid legacy credentials, try to bridge from GoogleProvider
            if settings.credential_migration:
                logger.info(f"🔄 Bridging GoogleProvider credentials to legacy system for {user_email}")
                
                # Use dual auth bridge for credential bridging
                bridged_credentials = self._dual_auth_bridge.bridge_credentials(user_email, "memory")
                if bridged_credentials:
                    logger.info(f"✅ Successfully bridged credentials for {user_email}")
                else:
                    logger.debug(f"⚠️ Could not bridge credentials for {user_email}")
            
        except Exception as e:
            logger.warning(f"⚠️ Could not bridge credentials for {user_email}: {e}")
    
    async def _auto_inject_email_parameter(self, context: MiddlewareContext, user_email: str) -> None:
        """
        Automatically inject user_google_email parameter into tool calls.
        
        This makes tools that require user_google_email work automatically
        without the user having to provide the parameter manually. This is
        a core feature of the unified OAuth architecture.
        
        Args:
            context: The middleware context containing the tool call
            user_email: User's email address to inject
        """
        try:
            logger.info(f"🔧 DEBUG: _auto_inject_email_parameter called with user_email: {user_email}")
            
            # Check if this is a tool call and has arguments
            if hasattr(context.message, 'arguments') and context.message.arguments:
                arguments = context.message.arguments
                logger.info(f"🔧 DEBUG: Found tool arguments: {arguments}")
                
                # Auto-inject user_google_email if not provided or is None
                if 'user_google_email' not in arguments or arguments.get('user_google_email') is None:
                    arguments['user_google_email'] = user_email
                    logger.info(f"🔧 DEBUG: ✅ Auto-injected user_google_email={user_email} into tool call (was {arguments.get('user_google_email', 'not present')})")
                else:
                    logger.info(f"🔧 DEBUG: user_google_email already has value: {arguments.get('user_google_email')}")
            else:
                logger.info(f"🔧 DEBUG: ❌ No tool arguments found or message doesn't have arguments")
            
        except Exception as e:
            logger.info(f"⚠️ DEBUG: Could not auto-inject email parameter: {e}")
    
    def set_google_provider(self, google_provider: Optional['GoogleProvider']) -> None:
        """
        Set or update the GoogleProvider instance for unified authentication.
        
        Args:
            google_provider: GoogleProvider instance from FastMCP 2.12.0
        """
        self._google_provider = google_provider
        self._unified_auth_enabled = bool(google_provider and settings.enable_unified_auth)
        
        if self._unified_auth_enabled:
            logger.info("✅ GoogleProvider updated - unified authentication enabled")
        else:
            logger.info("⭕ GoogleProvider cleared - unified authentication disabled")
    
    def is_unified_auth_enabled(self) -> bool:
        """Check if unified authentication is enabled."""
        return self._unified_auth_enabled
    
    def _extract_user_from_jwt_token(self) -> Optional[str]:
        """
        Extract user email from JWT token using FastMCP's standard pattern.
        
        This follows the official FastMCP example pattern:
        1. Use get_access_token() from FastMCP dependencies
        2. Extract email from token claims
        3. Return user email for automatic injection
        
        Returns:
            User email address if found in JWT token, None otherwise
        """
        try:
            # Follow the FastMCP pattern exactly as shown in examples
            from fastmcp.server.dependencies import get_access_token
            
            access_token = get_access_token()
            
            # Check if we have token claims (GoogleProvider or JWT)
            if hasattr(access_token, 'claims'):
                # Direct access to claims (GoogleProvider pattern)
                user_email = access_token.claims.get('email') or access_token.claims.get('google_email')
                if user_email:
                    logger.debug(f"📧 Extracted user email from token claims: {user_email}")
                    return user_email
            
            # Try raw token decoding (JWT pattern)
            if hasattr(access_token, 'raw_token'):
                import jwt
                # Decode without verification (already verified by FastMCP)
                claims = jwt.decode(access_token.raw_token, options={"verify_signature": False})
                user_email = claims.get('email') or claims.get('google_email')
                if user_email:
                    logger.debug(f"📧 Extracted user email from JWT raw token: {user_email}")
                    return user_email
            
            # Fallback: extract from client_id/subject
            if hasattr(access_token, 'client_id'):
                client_id = access_token.client_id
                if client_id and client_id.startswith("google-user-"):
                    user_email = client_id.replace("google-user-", "")
                    logger.debug(f"📧 Extracted user email from client_id: {user_email}")
                    return user_email
            
            return None
            
        except Exception as e:
            # This is expected if no token is present
            logger.debug(f"No JWT/token authentication available: {e}")
            return None
    
    def _load_oauth_authentication_data(self) -> Optional[str]:
        """
        Load OAuth authentication data from persistent storage.
        
        This checks for OAuth authentication data stored by the OAuth endpoint
        when authentication completes outside of the FastMCP request context.
        
        Returns:
            User email address if found in OAuth authentication file, None otherwise
        """
        try:
            from pathlib import Path
            import json
            from datetime import datetime, timedelta
            
            oauth_data_path = Path(settings.credentials_dir) / ".oauth_authentication.json"
            
            if not oauth_data_path.exists():
                logger.debug("No OAuth authentication file found")
                return None
            
            with open(oauth_data_path, "r") as f:
                oauth_data = json.load(f)
            
            authenticated_email = oauth_data.get("authenticated_email")
            authenticated_at_str = oauth_data.get("authenticated_at")
            
            if not authenticated_email:
                logger.debug("OAuth authentication file exists but no email found")
                return None
            
            # Check if authentication is still recent (within 24 hours)
            if authenticated_at_str:
                try:
                    authenticated_at = datetime.fromisoformat(authenticated_at_str)
                    age = datetime.now() - authenticated_at
                    if age > timedelta(hours=24):
                        logger.warning(f"OAuth authentication is stale (age: {age}), may need re-authentication")
                        # Still return it but warn - credentials might need refresh
                except Exception as e:
                    logger.debug(f"Could not parse authentication timestamp: {e}")
            
            logger.info(f"📂 Loaded OAuth authentication data for: {authenticated_email}")
            return authenticated_email
            
        except Exception as e:
            logger.debug(f"Could not load OAuth authentication data: {e}")
            return None


def create_enhanced_auth_middleware(
    storage_mode: CredentialStorageMode = CredentialStorageMode.FILE_PLAINTEXT,
    encryption_key: Optional[str] = None,
    google_provider: Optional['GoogleProvider'] = None
) -> AuthMiddleware:
    """
    Factory function to create AuthMiddleware with unified authentication support.
    
    This factory creates the enhanced AuthMiddleware that bridges FastMCP 2.12.0 
    GoogleProvider with existing tool architecture, implementing the unified OAuth design.
    
    Args:
        storage_mode: Credential storage mode
        encryption_key: Optional encryption key
        google_provider: GoogleProvider instance for unified auth
        
    Returns:
        Configured AuthMiddleware with unified authentication capabilities
    """
    middleware = AuthMiddleware(
        storage_mode=storage_mode,
        encryption_key=encryption_key,
        google_provider=google_provider
    )
    
    if middleware.is_unified_auth_enabled():
        logger.info("🎯 Unified OAuth Architecture Active:")
        logger.info("  ✅ FastMCP GoogleProvider → Legacy Tool Bridge")
        logger.info("  ✅ Automatic user context injection")
        logger.info("  ✅ Backward compatibility maintained")
        logger.info("  ✅ No tool signature changes required")
        logger.info("  🔄 Phase 1 migration successfully implemented")
    
    return middleware