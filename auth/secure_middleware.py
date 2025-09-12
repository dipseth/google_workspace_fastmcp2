"""
SECURE AUTH MIDDLEWARE - Critical Security Update
Replaces the vulnerable AuthMiddleware with secure session management.
"""

import logging
import uuid
from typing import Optional, Dict, Any
from datetime import datetime

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.dependencies import get_context
from google.oauth2.credentials import Credentials

from .middleware import CredentialStorageMode, AuthMiddleware
from .security_patch import get_security_manager, require_authenticated_session
from .context import (
    set_session_context,
    get_session_context,
    set_user_email_context,
    get_user_email_context,
    store_session_data,
    get_session_data,
    list_sessions
)
from config.settings import settings

logger = logging.getLogger(__name__)


class SecureAuthMiddleware(AuthMiddleware):
    """
    Secure version of AuthMiddleware with enhanced session protection.
    
    CRITICAL CHANGES:
    - No automatic session reuse
    - Required authentication tokens
    - Session-bound credentials
    - Connection fingerprinting
    - Audit logging
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.security_manager = get_security_manager()
        
        # Disable automatic session reuse
        self.security_manager.allow_session_reuse = False
        
        # Track connection info
        self.connection_info: Dict[str, Any] = {}
        
        logger.info("🔒 SecureAuthMiddleware initialized - Session reuse DISABLED")
    
    async def on_request(self, context: MiddlewareContext, call_next):
        """
        Handle incoming requests with secure session management.
        
        CRITICAL CHANGES:
        - New sessions require authentication
        - No automatic reuse of existing sessions
        - Connection fingerprinting
        """
        # Extract connection information
        connection_info = self._extract_connection_info(context)
        fingerprint = self.security_manager.create_connection_fingerprint(connection_info)
        
        # Check for session token in headers/context
        session_token = self._extract_session_token(context)
        
        if session_token:
            # Validate existing session with token
            session_id = self._extract_session_id_from_token(session_token)
            is_valid, user_email = self.security_manager.verify_session_token(
                session_token, session_id
            )
            
            if is_valid:
                # Valid session token - allow access
                set_session_context(session_id)
                if user_email:
                    set_user_email_context(user_email)
                    store_session_data(session_id, "user_email", user_email)
                
                logger.info(f"✅ Authenticated session validated: {session_id[:8]}... for {user_email}")
            else:
                # Invalid token - create new unauthenticated session
                session_id = self._create_new_session()
                set_session_context(session_id)
                logger.warning(f"⚠️ Invalid session token - created new session: {session_id[:8]}...")
        else:
            # No token - create new unauthenticated session
            session_id = self._create_new_session()
            set_session_context(session_id)
            logger.info(f"🆕 New unauthenticated session created: {session_id[:8]}...")
        
        # Store connection fingerprint
        store_session_data(session_id, "connection_fingerprint", fingerprint)
        
        # Cleanup expired sessions periodically
        if hasattr(self, '_last_cleanup'):
            if (datetime.now() - self._last_cleanup).total_seconds() > 300:  # 5 minutes
                self.security_manager.cleanup_expired_sessions()
                self._last_cleanup = datetime.now()
        else:
            self._last_cleanup = datetime.now()
        
        try:
            result = await call_next(context)
            return result
        except Exception as e:
            logger.error(f"Error in request processing: {e}")
            raise
        finally:
            # Keep session context for persistence
            logger.debug(f"Request completed for session: {session_id[:8]}...")
    
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """
        Handle tool execution with secure credential access.
        
        CRITICAL CHANGES:
        - Credentials require authenticated session
        - No automatic email extraction from old sessions
        - Audit logging for all credential access
        """
        tool_name = getattr(context.message, 'name', 'unknown')
        session_id = get_session_context()
        
        if not session_id:
            # This should not happen with secure middleware
            logger.error(f"⚠️ No session context for tool {tool_name}")
            raise PermissionError("No session context - authentication required")
        
        # Get connection fingerprint
        fingerprint = get_session_data(session_id, "connection_fingerprint")
        
        # Check for authenticated user
        user_email = get_user_email_context()
        
        if not user_email:
            # Try to extract from tool arguments (backward compatibility)
            user_email = self._extract_user_email(context)
            
            if user_email:
                # Validate session can access these credentials
                try:
                    if not self.security_manager.validate_session_access(
                        session_id, user_email, fingerprint
                    ):
                        logger.error(f"❌ Session {session_id[:8]}... not authorized for {user_email}")
                        raise PermissionError(
                            f"Session not authorized to access credentials for {user_email}. "
                            "Please authenticate first."
                        )
                except KeyError:
                    # Session not authenticated for any user
                    logger.error(f"❌ Unauthenticated session attempted to access {user_email}")
                    raise PermissionError(
                        "Authentication required. Please use start_google_auth tool first."
                    )
        
        # If we have a user email, set context and inject
        if user_email:
            set_user_email_context(user_email)
            await self._auto_inject_email_parameter(context, user_email)
            
            # Service injection if enabled
            if self._service_injection_enabled:
                await self._inject_services(tool_name, user_email)
        
        try:
            result = await call_next(context)
            logger.debug(f"Tool {tool_name} executed successfully for session {session_id[:8]}...")
            return result
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            raise
    
    def save_credentials(self, user_email: str, credentials: Credentials) -> None:
        """
        Save credentials with session authorization.
        
        CRITICAL CHANGE: Register session as authorized for these credentials.
        """
        # Save credentials normally
        super().save_credentials(user_email, credentials)
        
        # Register session authorization
        session_id = get_session_context()
        if session_id:
            fingerprint = get_session_data(session_id, "connection_fingerprint")
            token = self.security_manager.register_authenticated_session(
                session_id=session_id,
                user_email=user_email,
                connection_fingerprint=fingerprint,
                expires_in_minutes=settings.session_timeout_minutes
            )
            
            # Store token for client
            store_session_data(session_id, "session_token", token)
            store_session_data(session_id, "authenticated_at", datetime.now().isoformat())
            
            logger.info(f"✅ Session {session_id[:8]}... authorized for {user_email}")
    
    def load_credentials(self, user_email: str) -> Optional[Credentials]:
        """
        Load credentials with session validation.
        
        CRITICAL CHANGE: Validate session authorization before loading.
        """
        session_id = get_session_context()
        
        if not session_id:
            logger.error("No session context when loading credentials")
            return None
        
        # Check if session is authorized for this user
        fingerprint = get_session_data(session_id, "connection_fingerprint")
        
        try:
            if not self.security_manager.validate_session_access(
                session_id, user_email, fingerprint
            ):
                logger.error(f"Session {session_id[:8]}... not authorized for {user_email}")
                return None
        except Exception as e:
            logger.error(f"Session validation error: {e}")
            return None
        
        # Load credentials normally
        return super().load_credentials(user_email)
    
    def _create_new_session(self) -> str:
        """Create a new unique session ID."""
        return str(uuid.uuid4())
    
    def _extract_connection_info(self, context: MiddlewareContext) -> Dict[str, Any]:
        """Extract connection information from context."""
        info = {
            "ip_address": "unknown",
            "user_agent": "unknown",
            "tls_info": {}
        }
        
        # Try to extract from context (implementation depends on FastMCP version)
        if hasattr(context, 'request'):
            request = context.request
            if hasattr(request, 'client'):
                info["ip_address"] = getattr(request.client, 'host', 'unknown')
            if hasattr(request, 'headers'):
                info["user_agent"] = request.headers.get('user-agent', 'unknown')
        
        return info
    
    def _extract_session_token(self, context: MiddlewareContext) -> Optional[str]:
        """Extract session token from request."""
        # Try various locations
        if hasattr(context, 'request'):
            request = context.request
            
            # Check headers
            if hasattr(request, 'headers'):
                token = request.headers.get('x-session-token')
                if token:
                    return token
                
                # Check Authorization header
                auth_header = request.headers.get('authorization', '')
                if auth_header.startswith('Session '):
                    return auth_header[8:]
        
        # Check context state
        try:
            ctx = get_context()
            return ctx.get_state('session_token')
        except:
            pass
        
        return None
    
    def _extract_session_id_from_token(self, token: str) -> str:
        """Extract session ID from token."""
        try:
            parts = token.split(":")
            if len(parts) >= 1:
                return parts[0]
        except:
            pass
        
        return str(uuid.uuid4())  # Fallback to new session


def create_secure_auth_middleware(**kwargs) -> SecureAuthMiddleware:
    """
    Factory function to create secure authentication middleware.
    
    This replaces the vulnerable create_enhanced_auth_middleware.
    """
    # Force secure storage mode if not specified
    if 'storage_mode' not in kwargs:
        kwargs['storage_mode'] = CredentialStorageMode.FILE_ENCRYPTED
    
    middleware = SecureAuthMiddleware(**kwargs)
    
    logger.info("🔒 SECURITY UPDATE APPLIED:")
    logger.info("  ✅ Session reuse disabled")
    logger.info("  ✅ Authentication tokens required")
    logger.info("  ✅ Session-bound credentials")
    logger.info("  ✅ Connection fingerprinting enabled")
    logger.info("  ✅ Audit logging active")
    logger.info("  🛡️ Multi-tenant security enabled")
    
    return middleware