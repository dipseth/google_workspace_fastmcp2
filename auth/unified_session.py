"""UnifiedSession class for OAuth migration.

This module provides a unified session management interface that works with
both FastMCP 2.12.0 GoogleProvider and legacy OAuth flows.
"""

import logging

from config.enhanced_logging import setup_logger
logger = setup_logger()
import time
from typing import Optional, Dict, Any, Union
from datetime import datetime, timedelta
import jwt

from fastmcp import Context
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SessionState(BaseModel):
    """Session state model for tracking authentication status."""
    
    user_email: str = Field(..., description="User's email address")
    access_token: Optional[str] = Field(None, description="OAuth access token")
    refresh_token: Optional[str] = Field(None, description="OAuth refresh token")
    token_expiry: Optional[datetime] = Field(None, description="Token expiration time")
    scopes: list[str] = Field(default_factory=list, description="Granted OAuth scopes")
    session_id: str = Field(..., description="Unique session identifier")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Session creation time")
    last_accessed: datetime = Field(default_factory=datetime.utcnow, description="Last access time")
    auth_provider: str = Field("unknown", description="Authentication provider (google/legacy)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional session metadata")


class UnifiedSession:
    """Unified session management for OAuth migration.
    
    This class provides a consistent interface for session management
    across both FastMCP 2.12.0 GoogleProvider and legacy OAuth flows.
    """
    
    def __init__(self, context: Optional[Context] = None):
        """Initialize UnifiedSession.
        
        Args:
            context: FastMCP context object (when using GoogleProvider)
        """
        self.context = context
        self._session_state: Optional[SessionState] = None
        self._enhanced_logging = False
        
        # Check if enhanced logging is enabled
        import os
        self._enhanced_logging = os.getenv("ENHANCED_LOGGING", "false").lower() == "true"
        
        if self._enhanced_logging:
            logger.info("🔍 UnifiedSession initialized with enhanced logging")
    
    def extract_email_from_token(self, token: str) -> Optional[str]:
        """Extract email from JWT token claims.
        
        Args:
            token: JWT access token
            
        Returns:
            Email address if found, None otherwise
        """
        try:
            # Decode without verification to get claims (verification handled by provider)
            claims = jwt.decode(token, options={"verify_signature": False})
            
            # Try different claim names for email
            email = claims.get("email") or claims.get("sub") or claims.get("preferred_username")
            
            if self._enhanced_logging:
                logger.info(f"📧 Extracted email from token: {email}")
            
            return email
        except Exception as e:
            logger.error(f"Failed to extract email from token: {e}")
            return None
    
    def create_session_from_context(self, context: Context) -> SessionState:
        """Create session from FastMCP context (GoogleProvider).
        
        Args:
            context: FastMCP context with authentication info
            
        Returns:
            SessionState object
        """
        try:
            # Extract auth information from context
            auth_info = getattr(context, "auth", {})
            token = auth_info.get("token", "")
            
            # Extract email from token
            email = self.extract_email_from_token(token)
            if not email:
                raise ValueError("Could not extract email from token")
            
            # Create session state
            session_state = SessionState(
                user_email=email,
                access_token=token,
                refresh_token=auth_info.get("refresh_token"),
                token_expiry=self._calculate_expiry(auth_info.get("expires_in", 3600)),
                scopes=auth_info.get("scopes", []),
                session_id=self._generate_session_id(),
                auth_provider="google",
                metadata={
                    "client_id": auth_info.get("client_id"),
                    "issued_at": datetime.utcnow().isoformat()
                }
            )
            
            self._session_state = session_state
            
            if self._enhanced_logging:
                logger.info(f"✅ Created session for {email} from GoogleProvider context")
                logger.info(f"  Session ID: {session_state.session_id}")
                logger.info(f"  Scopes: {', '.join(session_state.scopes)}")
            
            return session_state
            
        except Exception as e:
            logger.error(f"Failed to create session from context: {e}")
            raise
    
    def create_session_from_legacy(self, user_email: str, credentials: Dict[str, Any]) -> SessionState:
        """Create session from legacy OAuth credentials.
        
        Args:
            user_email: User's email address
            credentials: Legacy OAuth credentials dictionary
            
        Returns:
            SessionState object
        """
        try:
            # Extract token information from legacy credentials
            session_state = SessionState(
                user_email=user_email,
                access_token=credentials.get("token"),
                refresh_token=credentials.get("refresh_token"),
                token_expiry=self._parse_legacy_expiry(credentials.get("expiry")),
                scopes=credentials.get("scopes", []),
                session_id=self._generate_session_id(),
                auth_provider="legacy",
                metadata={
                    "client_id": credentials.get("client_id"),
                    "token_uri": credentials.get("token_uri"),
                    "imported_at": datetime.utcnow().isoformat()
                }
            )
            
            self._session_state = session_state
            
            if self._enhanced_logging:
                logger.info(f"✅ Created session for {user_email} from legacy credentials")
                logger.info(f"  Session ID: {session_state.session_id}")
                logger.info(f"  Token expires: {session_state.token_expiry}")
            
            return session_state
            
        except Exception as e:
            logger.error(f"Failed to create session from legacy credentials: {e}")
            raise
    
    def get_current_session(self) -> Optional[SessionState]:
        """Get current session state.
        
        Returns:
            Current SessionState or None if no session
        """
        if self._session_state:
            # Update last accessed time
            self._session_state.last_accessed = datetime.utcnow()
        return self._session_state
    
    def is_session_valid(self) -> bool:
        """Check if current session is valid.
        
        Returns:
            True if session exists and token is not expired
        """
        if not self._session_state:
            return False
        
        # Check token expiry
        if self._session_state.token_expiry:
            if datetime.utcnow() >= self._session_state.token_expiry:
                if self._enhanced_logging:
                    logger.warning(f"⏰ Session expired for {self._session_state.user_email}")
                return False
        
        return True
    
    def needs_refresh(self, buffer_seconds: int = 300) -> bool:
        """Check if token needs refresh.
        
        Args:
            buffer_seconds: Refresh token this many seconds before expiry
            
        Returns:
            True if token should be refreshed
        """
        if not self._session_state or not self._session_state.token_expiry:
            return False
        
        # Check if we're within the buffer period
        refresh_time = self._session_state.token_expiry - timedelta(seconds=buffer_seconds)
        return datetime.utcnow() >= refresh_time
    
    def update_tokens(self, access_token: str, refresh_token: Optional[str] = None, 
                     expires_in: Optional[int] = None):
        """Update session tokens after refresh.
        
        Args:
            access_token: New access token
            refresh_token: New refresh token (if provided)
            expires_in: Token lifetime in seconds
        """
        if not self._session_state:
            raise ValueError("No active session to update")
        
        self._session_state.access_token = access_token
        if refresh_token:
            self._session_state.refresh_token = refresh_token
        if expires_in:
            self._session_state.token_expiry = self._calculate_expiry(expires_in)
        
        self._session_state.last_accessed = datetime.utcnow()
        
        if self._enhanced_logging:
            logger.info(f"🔄 Updated tokens for {self._session_state.user_email}")
    
    def clear_session(self):
        """Clear current session."""
        if self._session_state and self._enhanced_logging:
            logger.info(f"🗑️ Clearing session for {self._session_state.user_email}")
        self._session_state = None
    
    # Helper methods
    
    def _generate_session_id(self) -> str:
        """Generate unique session ID."""
        import uuid
        return f"session_{uuid.uuid4().hex[:16]}_{int(time.time())}"
    
    def _calculate_expiry(self, expires_in: int) -> datetime:
        """Calculate token expiry time."""
        return datetime.utcnow() + timedelta(seconds=expires_in)
    
    def _parse_legacy_expiry(self, expiry: Any) -> Optional[datetime]:
        """Parse legacy expiry format."""
        if not expiry:
            return None
        
        if isinstance(expiry, str):
            try:
                return datetime.fromisoformat(expiry.replace('Z', '+00:00'))
            except:
                pass
        elif isinstance(expiry, (int, float)):
            # Unix timestamp
            return datetime.fromtimestamp(expiry)
        elif isinstance(expiry, datetime):
            return expiry
        
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for serialization.
        
        Returns:
            Dictionary representation of session
        """
        if not self._session_state:
            return {}
        
        return self._session_state.model_dump(mode='json')
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UnifiedSession':
        """Create UnifiedSession from dictionary.
        
        Args:
            data: Dictionary with session data
            
        Returns:
            UnifiedSession instance
        """
        session = cls()
        if data:
            session._session_state = SessionState(**data)
        return session