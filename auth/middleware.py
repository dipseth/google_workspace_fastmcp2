"""Authentication middleware for session management and service injection."""

import logging
import json
import base64
import secrets
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing_extensions import Any, Optional, Dict
from enum import Enum

from fastmcp.server.middleware import Middleware, MiddlewareContext
from google.oauth2.credentials import Credentials

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

logger = logging.getLogger(__name__)


class CredentialStorageMode(Enum):
    """Credential storage modes."""
    FILE_PLAINTEXT = "file_plaintext"        # Current: JSON files (backward compatible)
    FILE_ENCRYPTED = "file_encrypted"        # New: Encrypted JSON files
    MEMORY_ONLY = "memory_only"              # New: In-memory only (no persistence)
    MEMORY_WITH_BACKUP = "memory_with_backup" # New: Memory + encrypted backup


class AuthMiddleware(Middleware):
    """Enhanced middleware for secure credential management, session context, and service injection."""
    
    def __init__(self,
                 storage_mode: CredentialStorageMode = CredentialStorageMode.FILE_PLAINTEXT,
                 encryption_key: Optional[str] = None):
        """
        Initialize AuthMiddleware with configurable credential storage.
        
        Args:
            storage_mode: How to store credentials (file_plaintext, file_encrypted, memory_only, memory_with_backup)
            encryption_key: Custom encryption key (auto-generated if not provided for encrypted modes)
        """
        self._last_cleanup = datetime.now()
        self._cleanup_interval_minutes = 30
        self._service_injection_enabled = True
        
        # Credential storage configuration
        self._storage_mode = storage_mode
        self._memory_credentials: Dict[str, Credentials] = {}
        self._encryption_key = encryption_key
        
        # Initialize encryption if needed
        if storage_mode in [CredentialStorageMode.FILE_ENCRYPTED, CredentialStorageMode.MEMORY_WITH_BACKUP]:
            self._setup_encryption()
        
        logger.info(f"🔐 AuthMiddleware initialized with storage mode: {storage_mode.value}")
        
        # Log security recommendations
        if storage_mode == CredentialStorageMode.FILE_PLAINTEXT:
            logger.warning("⚠️ Using plaintext file storage - consider upgrading to FILE_ENCRYPTED for production")
    
    async def on_request(self, context: MiddlewareContext, call_next):
        """Handle incoming requests and set session context."""
        from .context import store_session_data, get_session_data
        
        # Try to extract session ID from various possible locations
        session_id = None
        
        # Try FastMCP context first
        if hasattr(context, 'fastmcp_context') and context.fastmcp_context:
            session_id = getattr(context.fastmcp_context, 'session_id', None)
        
        # Try to get from headers or other context
        if not session_id and hasattr(context, 'request'):
            # Try to extract from request headers or similar
            session_id = getattr(context.request, 'session_id', None)
        
        # Generate a default session ID if none found
        if not session_id:
            import uuid
            session_id = str(uuid.uuid4())
            logger.debug(f"Generated default session ID: {session_id}")
        
        set_session_context(session_id)
        logger.debug(f"Set session context: {session_id}")
        
        # Check if we have a stored user email for this session (from OAuth)
        user_email = get_session_data(session_id, "user_email")
        if user_email:
            set_user_email_context(user_email)
            logger.debug(f"Restored user email context from session: {user_email}")
        
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
            # Always clear all context when done
            clear_all_context()
    
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """
        Handle tool execution with session context and service injection.
        
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
            # Generate a session ID if missing
            import uuid
            session_id = str(uuid.uuid4())
            set_session_context(session_id)
            logger.debug(f"Generated session context for tool {tool_name}: {session_id}")
        
        # First try to get user email from session data (OAuth authenticated)
        user_email = None
        if session_id:
            user_email = get_session_data(session_id, "user_email")
            if user_email:
                logger.debug(f"Found user email from OAuth session for tool {tool_name}: {user_email}")
        
        # If not found in session, extract from tool arguments
        if not user_email:
            user_email = self._extract_user_email(context)
            if user_email:
                logger.debug(f"Extracted user email from tool arguments for tool {tool_name}: {user_email}")
                # Store it in session for future use
                if session_id:
                    store_session_data(session_id, "user_email", user_email)
        
        # Set user email context if found
        if user_email:
            set_user_email_context(user_email)
            logger.debug(f"Set user email context for tool {tool_name}: {user_email}")
        else:
            logger.debug(f"No user email available for tool {tool_name}")
        
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