"""
CRITICAL SECURITY PATCH: Session Isolation and Authentication
This module provides enhanced security for multi-tenant MCP deployments.
"""

import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, UTC
from typing import Dict, Optional, Set, Tuple, Any
from pathlib import Path
import logging

from config.enhanced_logging import setup_logger
logger = setup_logger()

class SessionSecurityManager:
    """
    Enhanced session security manager with isolation and authentication.
    
    Features:
    - Per-connection session isolation
    - Connection fingerprinting
    - Session-bound credentials
    - Authentication token requirement
    - Audit logging
    """
    
    def __init__(self, session_secret: Optional[str] = None):
        """Initialize the security manager with a secret key."""
        self.session_secret = session_secret or secrets.token_hex(32)
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        self.session_credentials: Dict[str, Set[str]] = {}  # session_id -> allowed_emails
        self.connection_fingerprints: Dict[str, str] = {}  # session_id -> fingerprint
        self.failed_attempts: Dict[str, int] = {}  # ip_address -> count
        self.audit_log_path = Path("logs/security_audit.jsonl")
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Security configuration
        self.max_failed_attempts = 5
        self.session_timeout_minutes = 30
        self.require_reauthentication_hours = 4
        self.allow_session_reuse = False  # CRITICAL: Disabled by default
        
        logger.info("🔒 SessionSecurityManager initialized with enhanced security")
    
    def generate_session_token(self, session_id: str, user_email: Optional[str] = None) -> str:
        """
        Generate a secure session token bound to session ID and optionally user.
        
        Args:
            session_id: The session identifier
            user_email: Optional user email to bind to token
            
        Returns:
            Secure session token
        """
        timestamp = str(int(time.time()))
        payload = f"{session_id}:{user_email or 'anonymous'}:{timestamp}"
        
        # Create HMAC signature
        signature = hmac.new(
            self.session_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        token = f"{payload}:{signature}"
        
        self._audit_log({
            "event": "session_token_generated",
            "session_id": session_id,
            "user_email": user_email,
            "timestamp": timestamp
        })
        
        return token
    
    def verify_session_token(self, token: str, session_id: str) -> Tuple[bool, Optional[str]]:
        """
        Verify a session token and extract user information.
        
        Args:
            token: The session token to verify
            session_id: Expected session ID
            
        Returns:
            Tuple of (is_valid, user_email)
        """
        try:
            parts = token.split(":")
            if len(parts) != 4:
                return False, None
            
            token_session_id, user_email, timestamp, provided_signature = parts
            
            # Verify session ID matches
            if token_session_id != session_id:
                self._audit_log({
                    "event": "session_token_mismatch",
                    "expected_session": session_id,
                    "token_session": token_session_id
                })
                return False, None
            
            # Verify signature
            payload = f"{token_session_id}:{user_email}:{timestamp}"
            expected_signature = hmac.new(
                self.session_secret.encode(),
                payload.encode(),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(provided_signature, expected_signature):
                self._audit_log({
                    "event": "invalid_session_token_signature",
                    "session_id": session_id
                })
                return False, None
            
            # Check token age (optional expiry check)
            token_age = time.time() - int(timestamp)
            if token_age > (self.session_timeout_minutes * 60):
                self._audit_log({
                    "event": "expired_session_token",
                    "session_id": session_id,
                    "age_seconds": token_age
                })
                return False, None
            
            return True, user_email if user_email != "anonymous" else None
            
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            return False, None
    
    def create_connection_fingerprint(self, connection_info: Dict[str, Any]) -> str:
        """
        Create a fingerprint for a connection based on various factors.
        
        Args:
            connection_info: Dictionary containing connection details
                - ip_address: Client IP
                - user_agent: Client user agent
                - tls_info: TLS connection info
                
        Returns:
            Connection fingerprint hash
        """
        # Combine connection characteristics
        fingerprint_data = json.dumps({
            "ip": connection_info.get("ip_address", "unknown"),
            "user_agent": connection_info.get("user_agent", "unknown"),
            "tls_version": connection_info.get("tls_info", {}).get("version", "unknown"),
            "cipher_suite": connection_info.get("tls_info", {}).get("cipher", "unknown")
        }, sort_keys=True)
        
        # Create hash fingerprint
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()
        
        return fingerprint
    
    def validate_session_access(
        self,
        session_id: str,
        user_email: str,
        connection_fingerprint: Optional[str] = None
    ) -> bool:
        """
        Validate if a session can access credentials for a specific user.
        
        Args:
            session_id: Session identifier
            user_email: User email to access
            connection_fingerprint: Optional connection fingerprint
            
        Returns:
            True if access is allowed, False otherwise
        """
        # Check if session exists
        if session_id not in self.active_sessions:
            self._audit_log({
                "event": "invalid_session_access_attempt",
                "session_id": session_id,
                "user_email": user_email
            })
            return False
        
        session_data = self.active_sessions[session_id]
        
        # Check session expiry
        if datetime.now(UTC) > session_data.get("expires_at", datetime.min):
            self._audit_log({
                "event": "expired_session_access_attempt",
                "session_id": session_id,
                "user_email": user_email
            })
            return False
        
        # Check if user is authorized for this session
        allowed_emails = self.session_credentials.get(session_id, set())
        if user_email not in allowed_emails:
            self._audit_log({
                "event": "unauthorized_credential_access",
                "session_id": session_id,
                "requested_email": user_email,
                "allowed_emails": list(allowed_emails)
            })
            return False
        
        # Validate connection fingerprint if provided
        if connection_fingerprint and session_id in self.connection_fingerprints:
            if self.connection_fingerprints[session_id] != connection_fingerprint:
                self._audit_log({
                    "event": "connection_fingerprint_mismatch",
                    "session_id": session_id,
                    "user_email": user_email
                })
                return False
        
        # Update last access time
        session_data["last_accessed"] = datetime.now(UTC)
        
        self._audit_log({
            "event": "successful_credential_access",
            "session_id": session_id,
            "user_email": user_email
        })
        
        return True
    
    def register_authenticated_session(
        self,
        session_id: str,
        user_email: str,
        connection_fingerprint: Optional[str] = None,
        expires_in_minutes: Optional[int] = None
    ) -> str:
        """
        Register a newly authenticated session with credentials.
        
        Args:
            session_id: Session identifier
            user_email: Authenticated user email
            connection_fingerprint: Optional connection fingerprint
            expires_in_minutes: Optional custom expiry time
            
        Returns:
            Session token for future authentication
        """
        expires_at = datetime.now(UTC) + timedelta(
            minutes=expires_in_minutes or self.session_timeout_minutes
        )
        
        self.active_sessions[session_id] = {
            "created_at": datetime.now(UTC),
            "expires_at": expires_at,
            "last_accessed": datetime.now(UTC),
            "authenticated_user": user_email,
            "authentication_method": "oauth"
        }
        
        # Register allowed credentials for this session
        if session_id not in self.session_credentials:
            self.session_credentials[session_id] = set()
        self.session_credentials[session_id].add(user_email)
        
        # Store connection fingerprint
        if connection_fingerprint:
            self.connection_fingerprints[session_id] = connection_fingerprint
        
        # Generate session token
        token = self.generate_session_token(session_id, user_email)
        
        self._audit_log({
            "event": "session_registered",
            "session_id": session_id,
            "user_email": user_email,
            "expires_at": expires_at.isoformat(),
            "has_fingerprint": bool(connection_fingerprint)
        })
        
        return token
    
    def revoke_session(self, session_id: str) -> bool:
        """
        Revoke a session and all associated credentials.
        
        Args:
            session_id: Session to revoke
            
        Returns:
            True if session was revoked, False if not found
        """
        if session_id in self.active_sessions:
            user_email = self.active_sessions[session_id].get("authenticated_user")
            
            del self.active_sessions[session_id]
            
            if session_id in self.session_credentials:
                del self.session_credentials[session_id]
            
            if session_id in self.connection_fingerprints:
                del self.connection_fingerprints[session_id]
            
            self._audit_log({
                "event": "session_revoked",
                "session_id": session_id,
                "user_email": user_email
            })
            
            return True
        
        return False
    
    def check_rate_limit(self, identifier: str, max_attempts: Optional[int] = None) -> bool:
        """
        Check if an identifier (IP, user, etc.) has exceeded rate limits.
        
        Args:
            identifier: Unique identifier to check
            max_attempts: Optional custom limit
            
        Returns:
            True if within limits, False if exceeded
        """
        max_attempts = max_attempts or self.max_failed_attempts
        current_attempts = self.failed_attempts.get(identifier, 0)
        
        if current_attempts >= max_attempts:
            self._audit_log({
                "event": "rate_limit_exceeded",
                "identifier": identifier,
                "attempts": current_attempts
            })
            return False
        
        return True
    
    def record_failed_attempt(self, identifier: str) -> None:
        """Record a failed authentication attempt."""
        self.failed_attempts[identifier] = self.failed_attempts.get(identifier, 0) + 1
        
        self._audit_log({
            "event": "failed_authentication_attempt",
            "identifier": identifier,
            "total_attempts": self.failed_attempts[identifier]
        })
    
    def reset_failed_attempts(self, identifier: str) -> None:
        """Reset failed attempts for an identifier."""
        if identifier in self.failed_attempts:
            del self.failed_attempts[identifier]
    
    def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions and return count removed.
        
        Returns:
            Number of sessions cleaned up
        """
        now = datetime.now(UTC)
        expired_sessions = []
        
        for session_id, session_data in self.active_sessions.items():
            if now > session_data.get("expires_at", datetime.min):
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            self.revoke_session(session_id)
        
        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
        
        return len(expired_sessions)
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a session (for debugging/monitoring)."""
        if session_id not in self.active_sessions:
            return None
        
        session_data = self.active_sessions[session_id].copy()
        session_data["allowed_users"] = list(self.session_credentials.get(session_id, set()))
        session_data["has_fingerprint"] = session_id in self.connection_fingerprints
        
        return session_data
    
    def _audit_log(self, event_data: Dict[str, Any]) -> None:
        """
        Write an audit log entry.
        
        Args:
            event_data: Event information to log
        """
        try:
            event_data["timestamp"] = datetime.now(UTC).isoformat()
            
            with open(self.audit_log_path, "a") as f:
                f.write(json.dumps(event_data) + "\n")
            
            # Also log important events to application logger
            event_type = event_data.get("event", "unknown")
            if event_type in [
                "unauthorized_credential_access",
                "rate_limit_exceeded",
                "connection_fingerprint_mismatch",
                "invalid_session_token_signature"
            ]:
                logger.warning(f"SECURITY ALERT: {event_type} - {json.dumps(event_data)}")
        
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")


# Global instance for easy access
_security_manager: Optional[SessionSecurityManager] = None

def get_security_manager() -> SessionSecurityManager:
    """Get or create the global security manager instance."""
    global _security_manager
    if _security_manager is None:
        _security_manager = SessionSecurityManager()
    return _security_manager


def require_authenticated_session(session_id: str, user_email: str) -> bool:
    """
    Decorator/helper to require authenticated session for credential access.
    
    Args:
        session_id: Current session ID
        user_email: User email to access
        
    Returns:
        True if access allowed, raises exception otherwise
    """
    security_manager = get_security_manager()
    
    if not security_manager.validate_session_access(session_id, user_email):
        raise PermissionError(
            f"Session {session_id} is not authorized to access credentials for {user_email}. "
            "Please authenticate first."
        )
    
    return True