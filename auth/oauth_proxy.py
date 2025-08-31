"""
OAuth Proxy for bridging MCP Dynamic Client Registration with Google OAuth.

This proxy generates temporary credentials for MCP clients and maps them internally
to real Google OAuth credentials, ensuring the real credentials are never exposed.
"""

import json
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing_extensions import Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import threading

logger = logging.getLogger(__name__)


@dataclass
class ProxyClient:
    """Represents a proxied OAuth client with temporary credentials."""
    temp_client_id: str
    temp_client_secret: str
    real_client_id: str
    real_client_secret: str
    client_metadata: Dict[str, Any]
    created_at: datetime
    last_accessed: Optional[datetime] = None
    registration_access_token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    # PKCE parameters stored during authorization for use in token exchange
    code_challenge: Optional[str] = None
    code_challenge_method: Optional[str] = None
    
    def is_expired(self, expiry_hours: int = 24) -> bool:
        """Check if this proxy client has expired."""
        age = datetime.now(timezone.utc) - self.created_at
        return age > timedelta(hours=expiry_hours)
    
    def store_pkce_params(self, code_challenge: Optional[str], code_challenge_method: Optional[str]):
        """Store PKCE parameters from authorization request."""
        self.code_challenge = code_challenge
        self.code_challenge_method = code_challenge_method


class OAuthProxy:
    """
    OAuth Proxy that bridges between MCP's Dynamic Client Registration expectations
    and Google's fixed OAuth credentials.
    
    Key features:
    - Generates unique temporary credentials for each MCP client
    - Maps temporary credentials to real Google OAuth credentials
    - Never exposes real Google credentials to external clients
    - Handles token exchange with proper credential mapping
    - Includes cleanup for expired proxy clients
    """
    
    def __init__(self):
        """Initialize the OAuth Proxy with empty registries."""
        # Map temp_client_id -> ProxyClient
        self._proxy_clients: Dict[str, ProxyClient] = {}
        # Lock for thread-safe operations
        self._lock = threading.Lock()
        # Cleanup interval in seconds (default: 1 hour)
        self._cleanup_interval = 3600
        self._last_cleanup = time.time()
        
        logger.info("🔐 OAuth Proxy initialized")
    
    def register_proxy_client(self, 
                             real_client_id: str,
                             real_client_secret: str,
                             client_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Register a new proxy client with temporary credentials.
        
        Args:
            real_client_id: The real Google OAuth client ID
            real_client_secret: The real Google OAuth client secret
            client_metadata: Client metadata from DCR request
            
        Returns:
            Dictionary containing temporary credentials and registration info
        """
        with self._lock:
            # Generate unique temporary credentials
            temp_client_id = f"mcp_{secrets.token_urlsafe(16)}"
            temp_client_secret = secrets.token_urlsafe(32)
            
            # Create proxy client
            proxy_client = ProxyClient(
                temp_client_id=temp_client_id,
                temp_client_secret=temp_client_secret,
                real_client_id=real_client_id,
                real_client_secret=real_client_secret,
                client_metadata=client_metadata,
                created_at=datetime.now(timezone.utc)
            )
            
            # Store the mapping
            self._proxy_clients[temp_client_id] = proxy_client
            
            logger.info(f"🎫 Created proxy client mapping:")
            logger.info(f"   Temp ID: {temp_client_id}")
            logger.info(f"   Real ID: {real_client_id[:20]}...")
            logger.info(f"   Metadata: {client_metadata.get('client_name', 'Unknown')}")
            
            # Perform cleanup if needed
            self._cleanup_expired_clients()
            
            # Return temporary credentials (never expose real ones!)
            return {
                "client_id": temp_client_id,
                "client_secret": temp_client_secret,
                "client_id_issued_at": int(proxy_client.created_at.timestamp()),
                "client_secret_expires_at": 0,  # Never expires
                "registration_access_token": proxy_client.registration_access_token,
                "registration_client_uri": f"http://localhost:8002/oauth/register/{temp_client_id}",
                **client_metadata
            }
    
    def get_real_credentials(self, temp_client_id: str, temp_client_secret: str) -> Optional[Tuple[str, str]]:
        """
        Get real Google OAuth credentials for a given temporary client.
        
        Args:
            temp_client_id: Temporary client ID
            temp_client_secret: Temporary client secret for validation
            
        Returns:
            Tuple of (real_client_id, real_client_secret) if valid, None otherwise
        """
        with self._lock:
            proxy_client = self._proxy_clients.get(temp_client_id)
            
            if not proxy_client:
                logger.warning(f"❌ No proxy client found for temp_id: {temp_client_id}")
                return None
            
            # Check if this is a public client (no authentication required)
            auth_method = proxy_client.client_metadata.get('token_endpoint_auth_method', 'client_secret_post')
            is_public_client = auth_method == 'none'
            
            # DIAGNOSTIC LOGGING for client_secret validation issue
            logger.info(f"🔍 DIAGNOSTIC - Client secret validation for: {temp_client_id}")
            logger.info(f"   Received client_secret: '{temp_client_secret}'")
            logger.info(f"   Received length: {len(temp_client_secret)}")
            logger.info(f"   Stored client_secret: '{proxy_client.temp_client_secret}'")
            logger.info(f"   Stored length: {len(proxy_client.temp_client_secret)}")
            logger.info(f"   Auth method: {auth_method}")
            logger.info(f"   Is public client: {is_public_client}")
            logger.info(f"   Secrets match: {proxy_client.temp_client_secret == temp_client_secret}")
            
            # Validate the temporary secret (skip for public clients)
            if is_public_client:
                logger.info(f"✅ Public client - skipping client_secret validation: {temp_client_id}")
            elif proxy_client.temp_client_secret != temp_client_secret:
                logger.warning(f"❌ Invalid temp secret for client: {temp_client_id}")
                logger.warning(f"   Expected: '{proxy_client.temp_client_secret}'")
                logger.warning(f"   Received: '{temp_client_secret}'")
                return None
            
            # Check if expired
            if proxy_client.is_expired():
                logger.warning(f"❌ Proxy client expired: {temp_client_id}")
                del self._proxy_clients[temp_client_id]
                return None
            
            # Update last accessed time
            proxy_client.last_accessed = datetime.now(timezone.utc)
            
            logger.info(f"✅ Retrieved real credentials for proxy client: {temp_client_id}")
            return (proxy_client.real_client_id, proxy_client.real_client_secret)
    
    def get_proxy_client(self, temp_client_id: str) -> Optional[ProxyClient]:
        """
        Get a proxy client by temporary client ID.
        
        Args:
            temp_client_id: Temporary client ID
            
        Returns:
            ProxyClient if found, None otherwise
        """
        with self._lock:
            return self._proxy_clients.get(temp_client_id)
    
    def validate_registration_token(self, temp_client_id: str, access_token: str) -> bool:
        """
        Validate a registration access token for a proxy client.
        
        Args:
            temp_client_id: Temporary client ID
            access_token: Registration access token to validate
            
        Returns:
            True if valid, False otherwise
        """
        with self._lock:
            proxy_client = self._proxy_clients.get(temp_client_id)
            if not proxy_client:
                return False
            
            return proxy_client.registration_access_token == access_token
    
    def update_proxy_client(self, 
                           temp_client_id: str, 
                           client_metadata: Dict[str, Any],
                           access_token: str) -> Optional[Dict[str, Any]]:
        """
        Update a proxy client's metadata.
        
        Args:
            temp_client_id: Temporary client ID
            client_metadata: Updated client metadata
            access_token: Registration access token for validation
            
        Returns:
            Updated client info if successful, None otherwise
        """
        with self._lock:
            proxy_client = self._proxy_clients.get(temp_client_id)
            
            if not proxy_client:
                logger.warning(f"❌ No proxy client found for update: {temp_client_id}")
                return None
            
            if proxy_client.registration_access_token != access_token:
                logger.warning(f"❌ Invalid registration token for update: {temp_client_id}")
                return None
            
            # Update metadata
            proxy_client.client_metadata.update(client_metadata)
            proxy_client.last_accessed = datetime.now(timezone.utc)
            
            logger.info(f"📝 Updated proxy client metadata: {temp_client_id}")
            
            # Return updated info with temporary credentials
            return {
                "client_id": temp_client_id,
                "client_secret": proxy_client.temp_client_secret,
                "client_id_issued_at": int(proxy_client.created_at.timestamp()),
                "client_secret_expires_at": 0,
                "registration_access_token": proxy_client.registration_access_token,
                "registration_client_uri": f"http://localhost:8002/oauth/register/{temp_client_id}",
                **proxy_client.client_metadata
            }
    
    def delete_proxy_client(self, temp_client_id: str, access_token: str) -> bool:
        """
        Delete a proxy client.
        
        Args:
            temp_client_id: Temporary client ID
            access_token: Registration access token for validation
            
        Returns:
            True if deleted, False otherwise
        """
        with self._lock:
            proxy_client = self._proxy_clients.get(temp_client_id)
            
            if not proxy_client:
                return False
            
            if proxy_client.registration_access_token != access_token:
                logger.warning(f"❌ Invalid registration token for deletion: {temp_client_id}")
                return False
            
            del self._proxy_clients[temp_client_id]
            logger.info(f"🗑️ Deleted proxy client: {temp_client_id}")
            
            return True
    
    def _cleanup_expired_clients(self):
        """Remove expired proxy clients (called periodically)."""
        current_time = time.time()
        
        # Only cleanup every interval
        if current_time - self._last_cleanup < self._cleanup_interval:
            return
        
        self._last_cleanup = current_time
        
        # Find and remove expired clients
        expired_clients = [
            client_id for client_id, client in self._proxy_clients.items()
            if client.is_expired()
        ]
        
        for client_id in expired_clients:
            del self._proxy_clients[client_id]
            logger.info(f"🧹 Cleaned up expired proxy client: {client_id}")
        
        if expired_clients:
            logger.info(f"🧹 Cleaned up {len(expired_clients)} expired proxy clients")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the proxy."""
        with self._lock:
            active_clients = len(self._proxy_clients)
            oldest_client = None
            newest_client = None
            
            if self._proxy_clients:
                clients_by_age = sorted(
                    self._proxy_clients.values(),
                    key=lambda c: c.created_at
                )
                oldest_client = clients_by_age[0].created_at
                newest_client = clients_by_age[-1].created_at
            
            return {
                "active_proxy_clients": active_clients,
                "oldest_client_age": (
                    (datetime.now(timezone.utc) - oldest_client).total_seconds()
                    if oldest_client else None
                ),
                "newest_client_age": (
                    (datetime.now(timezone.utc) - newest_client).total_seconds()
                    if newest_client else None
                )
            }


# Global OAuth Proxy instance
oauth_proxy = OAuthProxy()


def handle_token_exchange(auth_code: str,
                         client_id: str,
                         client_secret: str,
                         redirect_uri: str,
                         code_verifier: Optional[str] = None) -> Dict[str, Any]:
    """
    Handle token exchange using the OAuth Proxy.
    
    This function intercepts token exchange requests and maps temporary
    credentials to real Google OAuth credentials before forwarding the request.
    
    Args:
        auth_code: Authorization code from OAuth flow
        client_id: Client ID (could be temporary from proxy)
        client_secret: Client secret (could be temporary from proxy)
        redirect_uri: Redirect URI for the OAuth flow
        code_verifier: PKCE code verifier (optional, used with PKCE flows)
        
    Returns:
        Token response from Google OAuth
        
    Raises:
        ValueError: If credentials are invalid or token exchange fails
    """
    import requests
    from config.settings import settings
    
    # Check if this is a proxy client (starts with "mcp_")
    if client_id.startswith("mcp_"):
        logger.info(f"🔄 Token exchange for proxy client: {client_id}")
        
        # Get real credentials from proxy
        real_credentials = oauth_proxy.get_real_credentials(client_id, client_secret)
        
        if not real_credentials:
            raise ValueError("Invalid proxy client credentials")
        
        real_client_id, real_client_secret = real_credentials
        logger.info(f"✅ Mapped to real client: {real_client_id[:20]}...")
        
        # Get proxy client to check for stored PKCE parameters
        proxy_client = oauth_proxy.get_proxy_client(client_id)
        if proxy_client and proxy_client.code_challenge and not code_verifier:
            logger.warning(f"🔐 PKCE was used in authorization but code_verifier not provided in token exchange")
            logger.info(f"   code_challenge: {proxy_client.code_challenge[:10]}...")
            logger.info(f"   code_challenge_method: {proxy_client.code_challenge_method}")
            # Note: code_verifier must come from client, we can't generate it
    else:
        # Direct usage of real credentials (for backward compatibility)
        logger.info(f"🔄 Token exchange with direct credentials: {client_id[:20]}...")
        real_client_id = client_id
        real_client_secret = client_secret
    
    # Perform token exchange with Google using real credentials
    token_url = "https://oauth2.googleapis.com/token"
    
    data = {
        "code": auth_code,
        "client_id": real_client_id,
        "client_secret": real_client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }
    
    # Add PKCE code_verifier if provided
    if code_verifier:
        data["code_verifier"] = code_verifier
        logger.info(f"🔐 Including PKCE code_verifier in token exchange: {code_verifier[:10]}...")
    
    try:
        # DIAGNOSTIC: Log the exact token exchange request
        logger.info(f"🔍 DEBUG: Token exchange request:")
        logger.info(f"   URL: {token_url}")
        logger.info(f"   auth_code: {auth_code[:20]}...")
        logger.info(f"   real_client_id: {real_client_id[:20]}...")
        logger.info(f"   redirect_uri: {redirect_uri}")
        logger.info(f"   grant_type: authorization_code")
        
        response = requests.post(token_url, data=data)
        response.raise_for_status()
        
        token_data = response.json()
        logger.info("✅ Token exchange successful")
        
        return token_data
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Token exchange failed: {e}")
        logger.error(f"🔍 DEBUG: Request data was: {data}")
        if hasattr(e, 'response') and e.response:
            logger.error(f"   Response status: {e.response.status_code}")
            logger.error(f"   Response body: {e.response.text}")
        raise ValueError(f"Token exchange failed: {str(e)}")


def refresh_access_token(refresh_token: str,
                        client_id: str,
                        client_secret: str) -> Dict[str, Any]:
    """
    Refresh an access token using the OAuth Proxy.
    
    Args:
        refresh_token: Refresh token from previous authentication
        client_id: Client ID (could be temporary from proxy)
        client_secret: Client secret (could be temporary from proxy)
        
    Returns:
        New token response from Google OAuth
        
    Raises:
        ValueError: If credentials are invalid or refresh fails
    """
    import requests
    
    # Check if this is a proxy client
    if client_id.startswith("mcp_"):
        logger.info(f"🔄 Token refresh for proxy client: {client_id}")
        
        # Get real credentials from proxy
        real_credentials = oauth_proxy.get_real_credentials(client_id, client_secret)
        
        if not real_credentials:
            raise ValueError("Invalid proxy client credentials")
        
        real_client_id, real_client_secret = real_credentials
        logger.info(f"✅ Mapped to real client for refresh: {real_client_id[:20]}...")
    else:
        # Direct usage of real credentials
        real_client_id = client_id
        real_client_secret = client_secret
    
    # Perform token refresh with Google using real credentials
    token_url = "https://oauth2.googleapis.com/token"
    
    data = {
        "refresh_token": refresh_token,
        "client_id": real_client_id,
        "client_secret": real_client_secret,
        "grant_type": "refresh_token"
    }
    
    try:
        response = requests.post(token_url, data=data)
        response.raise_for_status()
        
        token_data = response.json()
        logger.info("✅ Token refresh successful")
        
        return token_data
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Token refresh failed: {e}")
        if hasattr(e, 'response') and e.response:
            logger.error(f"   Response: {e.response.text}")
        raise ValueError(f"Token refresh failed: {str(e)}")