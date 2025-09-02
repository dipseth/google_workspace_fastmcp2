"""SessionBridge for bridging FastMCP context to tool expectations.

This module provides a bridge between FastMCP 2.12.0's context and the
expectations of existing tools, synthesizing credentials and creating
Google service objects as needed.
"""

import logging
import os
from typing import Optional, Dict, Any, Union
from datetime import datetime, timedelta
import asyncio
from functools import lru_cache

from fastmcp import Context
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request

from auth.unified_session import UnifiedSession, SessionState

logger = logging.getLogger(__name__)


class ServiceCache:
    """Cache for Google service objects."""
    
    def __init__(self, ttl_seconds: int = 300):
        """Initialize service cache.
        
        Args:
            ttl_seconds: Time-to-live for cached services
        """
        self._cache: Dict[str, Any] = {}
        self._timestamps: Dict[str, datetime] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        """Get service from cache if not expired."""
        async with self._lock:
            if key not in self._cache:
                return None
            
            # Check if expired
            if datetime.utcnow() - self._timestamps[key] > self._ttl:
                del self._cache[key]
                del self._timestamps[key]
                return None
            
            return self._cache[key]
    
    async def set(self, key: str, service: Any):
        """Store service in cache."""
        async with self._lock:
            self._cache[key] = service
            self._timestamps[key] = datetime.utcnow()
    
    async def clear(self):
        """Clear all cached services."""
        async with self._lock:
            self._cache.clear()
            self._timestamps.clear()


class SessionBridge:
    """Bridge between FastMCP context and tool expectations.
    
    This class maps FastMCP authentication context to the format expected
    by existing tools, synthesizes Google credentials, and manages service
    object creation with caching.
    """
    
    def __init__(self, unified_session: Optional[UnifiedSession] = None):
        """Initialize SessionBridge.
        
        Args:
            unified_session: UnifiedSession instance to use
        """
        self.unified_session = unified_session or UnifiedSession()
        self._service_cache = ServiceCache()
        self._enhanced_logging = os.getenv("ENHANCED_LOGGING", "false").lower() == "true"
        self._service_caching = os.getenv("SERVICE_CACHING", "false").lower() == "true"
        
        if self._enhanced_logging:
            logger.info("🌉 SessionBridge initialized")
            logger.info(f"  Service caching: {self._service_caching}")
    
    async def map_fastmcp_to_tool_context(self, context: Context) -> Dict[str, Any]:
        """Map FastMCP context to tool-expected format.
        
        Args:
            context: FastMCP context object
            
        Returns:
            Dictionary with mapped context for tools
        """
        try:
            # Create session from context
            session = self.unified_session.create_session_from_context(context)
            
            # Map to tool-expected format
            tool_context = {
                "user_google_email": session.user_email,
                "access_token": session.access_token,
                "refresh_token": session.refresh_token,
                "token_expiry": session.token_expiry.isoformat() if session.token_expiry else None,
                "scopes": session.scopes,
                "session_id": session.session_id,
                "auth_provider": session.auth_provider
            }
            
            if self._enhanced_logging:
                logger.info(f"📦 Mapped context for {session.user_email}")
                logger.info(f"  Session ID: {session.session_id}")
                logger.info(f"  Auth Provider: {session.auth_provider}")
            
            return tool_context
            
        except Exception as e:
            logger.error(f"Failed to map FastMCP context: {e}")
            raise
    
    def synthesize_credentials(self, session_state: SessionState) -> Credentials:
        """Synthesize Google credentials from session state.
        
        Args:
            session_state: Current session state
            
        Returns:
            Google Credentials object
        """
        try:
            # Create credentials from session state
            credentials = Credentials(
                token=session_state.access_token,
                refresh_token=session_state.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.getenv("FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID"),
                client_secret=os.getenv("FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET"),
                scopes=session_state.scopes or []
            )
            
            # Set expiry if available
            if session_state.token_expiry:
                credentials.expiry = session_state.token_expiry
            
            # Refresh if needed
            if credentials.expired and credentials.refresh_token:
                if self._enhanced_logging:
                    logger.info(f"🔄 Refreshing expired credentials for {session_state.user_email}")
                
                request = Request()
                credentials.refresh(request)
                
                # Update session with new tokens
                self.unified_session.update_tokens(
                    access_token=credentials.token,
                    refresh_token=credentials.refresh_token,
                    expires_in=3600  # Default to 1 hour
                )
            
            if self._enhanced_logging:
                logger.info(f"🔑 Synthesized credentials for {session_state.user_email}")
                logger.info(f"  Valid: {credentials.valid}")
                logger.info(f"  Expired: {credentials.expired}")
            
            return credentials
            
        except Exception as e:
            logger.error(f"Failed to synthesize credentials: {e}")
            raise
    
    async def get_service(self, service_name: str, version: str, 
                         session_state: Optional[SessionState] = None) -> Any:
        """Get or create a Google service object.
        
        Args:
            service_name: Name of the service (e.g., 'drive', 'gmail')
            version: API version (e.g., 'v3', 'v1')
            session_state: Session state to use (or current session)
            
        Returns:
            Google service object
        """
        try:
            # Use current session if not provided
            if not session_state:
                session_state = self.unified_session.get_current_session()
                if not session_state:
                    raise ValueError("No active session")
            
            # Create cache key
            cache_key = f"{session_state.user_email}:{service_name}:{version}"
            
            # Check cache if enabled
            if self._service_caching:
                cached_service = await self._service_cache.get(cache_key)
                if cached_service:
                    if self._enhanced_logging:
                        logger.info(f"✨ Using cached {service_name} service for {session_state.user_email}")
                    return cached_service
            
            # Synthesize credentials
            credentials = self.synthesize_credentials(session_state)
            
            # Build service
            if self._enhanced_logging:
                logger.info(f"🔧 Building {service_name} {version} service for {session_state.user_email}")
            
            service = build(service_name, version, credentials=credentials)
            
            # Cache if enabled
            if self._service_caching:
                await self._service_cache.set(cache_key, service)
                if self._enhanced_logging:
                    logger.info(f"💾 Cached {service_name} service for {session_state.user_email}")
            
            return service
            
        except Exception as e:
            logger.error(f"Failed to get/create service {service_name}: {e}")
            raise
    
    async def inject_user_email(self, context: Context, params: Dict[str, Any]) -> Dict[str, Any]:
        """Inject user_google_email into parameters for legacy tools.
        
        Args:
            context: FastMCP context
            params: Tool parameters
            
        Returns:
            Updated parameters with user_google_email
        """
        try:
            # Check if already has user_google_email
            if "user_google_email" in params:
                return params
            
            # Get session from context
            session = self.unified_session.create_session_from_context(context)
            
            # Inject user email
            params["user_google_email"] = session.user_email
            
            if self._enhanced_logging:
                logger.info(f"💉 Injected user_google_email: {session.user_email}")
            
            return params
            
        except Exception as e:
            logger.error(f"Failed to inject user_google_email: {e}")
            # Return original params if injection fails
            return params
    
    async def get_service_map(self, session_state: Optional[SessionState] = None) -> Dict[str, Any]:
        """Get a map of all available Google services.
        
        Args:
            session_state: Session state to use (or current session)
            
        Returns:
            Dictionary mapping service names to service objects
        """
        if not session_state:
            session_state = self.unified_session.get_current_session()
            if not session_state:
                raise ValueError("No active session")
        
        # Service configurations
        service_configs = {
            "drive": ("drive", "v3"),
            "gmail": ("gmail", "v1"),
            "calendar": ("calendar", "v3"),
            "docs": ("docs", "v1"),
            "sheets": ("sheets", "v4"),
            "slides": ("slides", "v1"),
            "forms": ("forms", "v1"),
            "chat": ("chat", "v1"),
            "photoslibrary": ("photoslibrary", "v1")
        }
        
        service_map = {}
        
        for name, (service_name, version) in service_configs.items():
            try:
                service = await self.get_service(service_name, version, session_state)
                service_map[name] = service
            except Exception as e:
                logger.warning(f"Could not create {name} service: {e}")
        
        if self._enhanced_logging:
            logger.info(f"📚 Created service map with {len(service_map)} services")
        
        return service_map
    
    async def clear_cache(self):
        """Clear all cached services."""
        await self._service_cache.clear()
        if self._enhanced_logging:
            logger.info("🗑️ Cleared service cache")
    
    def get_session_info(self) -> Dict[str, Any]:
        """Get current session information.
        
        Returns:
            Dictionary with session info
        """
        session = self.unified_session.get_current_session()
        if not session:
            return {"status": "no_session"}
        
        return {
            "status": "active",
            "user_email": session.user_email,
            "session_id": session.session_id,
            "auth_provider": session.auth_provider,
            "valid": self.unified_session.is_session_valid(),
            "needs_refresh": self.unified_session.needs_refresh(),
            "created_at": session.created_at.isoformat(),
            "last_accessed": session.last_accessed.isoformat()
        }