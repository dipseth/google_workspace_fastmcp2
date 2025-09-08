"""
OAuth 2.0 Dynamic Client Registration (RFC 7591) Implementation

This module now uses the OAuth Proxy to generate temporary credentials
for MCP clients, ensuring real Google OAuth credentials are never exposed.
"""
import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing_extensions import Dict, Any, Optional

# Import OAuth Proxy for secure credential management
from .oauth_proxy import oauth_proxy

# Import centralized scope registry
from .scope_registry import ScopeRegistry

# No more hardcoded scopes - use scope_registry
_FALLBACK_DCR_SCOPE = ""  # Empty fallback


def _get_dcr_default_scope() -> str:
    """
    Get default scope string for Dynamic Client Registration from scope registry.
    
    This function uses the centralized scope registry to build DCR scope strings.
    
    Returns:
        Default scope string for DCR from scope registry
    """
    try:
        # Use oauth_comprehensive from scope registry
        scopes = ScopeRegistry.get_oauth_scopes([])  # Services list ignored - uses comprehensive
        return " ".join(scopes)
    except Exception as e:
        logger.warning(f"Error getting DCR scope defaults from registry: {e}")
        # Minimal fallback scopes
        return "openid email profile"

logger = logging.getLogger(__name__)

class DynamicClientRegistry:
    """In-memory dynamic client registration store"""
    
    def __init__(self):
        self.clients: Dict[str, Dict[str, Any]] = {}
        self.access_tokens: Dict[str, Dict[str, Any]] = {}
    
    def register_client(self, client_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Register a new OAuth client dynamically using the OAuth Proxy.
        
        This method now uses the OAuth Proxy to generate temporary credentials
        for MCP clients, ensuring real Google OAuth credentials are never exposed.
        """
        
        # Import settings to get real Google OAuth credentials (for internal use only)
        from config.settings import settings
        
        # Get the real Google OAuth client configuration (never exposed to clients)
        try:
            # First validate that OAuth is configured
            if not settings.is_oauth_configured():
                raise ValueError("OAuth is not configured. Please set GOOGLE_CLIENT_SECRETS_FILE or GOOGLE_CLIENT_ID/SECRET")
            
            oauth_config = settings.get_oauth_client_config()
            real_client_id = oauth_config.get('client_id')
            real_client_secret = oauth_config.get('client_secret')
            
            if not real_client_id or not real_client_secret:
                raise ValueError(f"OAuth configuration incomplete: client_id={'present' if real_client_id else 'missing'}, client_secret={'present' if real_client_secret else 'missing'}")
            
            logger.info(f"📝 Retrieved Google OAuth credentials for proxy mapping")
            logger.info(f"   Real Client ID (internal): {real_client_id[:20]}...")
            
        except Exception as e:
            logger.error(f"❌ Failed to get Google OAuth credentials: {e}")
            # Re-raise the error with more context
            raise ValueError(f"OAuth configuration error: {str(e)}. Please ensure GOOGLE_CLIENT_SECRETS_FILE points to a valid OAuth client secrets JSON file.")
        
        # Set defaults and validate metadata
        validated_metadata = self._validate_client_metadata(client_metadata)
        
        # Use OAuth Proxy to register the client with TEMPORARY credentials
        proxy_registration = oauth_proxy.register_proxy_client(
            real_client_id=real_client_id,
            real_client_secret=real_client_secret,
            client_metadata=validated_metadata
        )
        
        # Store the proxy registration in our local registry
        temp_client_id = proxy_registration['client_id']
        self.clients[temp_client_id] = proxy_registration
        
        logger.info(f"✅ Registered OAuth client via proxy with temporary credentials")
        logger.info(f"   Temp Client ID: {temp_client_id}")
        logger.info(f"   Real credentials are securely mapped internally")
        
        # DIAGNOSTIC LOG: OAuth Proxy debugging
        logger.info(f"🔍 PROXY_DEBUG: Returning proxy registration to MCP Inspector:")
        logger.info(f"🔍 PROXY_DEBUG: - temp_client_id: {temp_client_id}")
        logger.info(f"🔍 PROXY_DEBUG: - temp_client_secret: PRESENT (length: {len(proxy_registration.get('client_secret', ''))})")
        logger.info(f"🔍 PROXY_DEBUG: - Real credentials: NEVER EXPOSED ✅")
        logger.info(f"🔍 PROXY_DEBUG: - token_endpoint_auth_method: {proxy_registration.get('token_endpoint_auth_method')}")
        logger.info(f"🔍 PROXY_DEBUG: - Full response keys: {list(proxy_registration.keys())}")
        
        return proxy_registration
    
    def get_client(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Get client information (works with both temp and real client IDs)"""
        # First check local registry
        client = self.clients.get(client_id)
        if client:
            return client
        
        # If not found and it's a proxy client ID, check the proxy
        if client_id.startswith("mcp_"):
            proxy_client = oauth_proxy.get_proxy_client(client_id)
            if proxy_client:
                # Return the temporary credentials info
                return {
                    "client_id": proxy_client.temp_client_id,
                    "client_secret": proxy_client.temp_client_secret,
                    "client_id_issued_at": int(proxy_client.created_at.timestamp()),
                    "client_secret_expires_at": 0,
                    "registration_access_token": proxy_client.registration_access_token,
                    "registration_client_uri": f"{settings.base_url}/oauth/register/{proxy_client.temp_client_id}",
                    **proxy_client.client_metadata
                }
        
        return None
    
    def update_client(self, client_id: str, client_metadata: Dict[str, Any],
                     access_token: str) -> Dict[str, Any]:
        """Update client registration (works with proxy clients)"""
        # Check if this is a proxy client
        if client_id.startswith("mcp_"):
            # Use OAuth Proxy to update
            updated_info = oauth_proxy.update_proxy_client(
                temp_client_id=client_id,
                client_metadata=client_metadata,
                access_token=access_token
            )
            
            if not updated_info:
                raise ValueError("Client not found or invalid token")
            
            # Update local registry
            self.clients[client_id] = updated_info
            logger.info(f"📝 Updated proxy OAuth client: {client_id}")
            
            return updated_info
        else:
            # Legacy path for direct clients (backward compatibility)
            client = self.clients.get(client_id)
            if not client:
                raise ValueError("Client not found")
            
            if client.get("registration_access_token") != access_token:
                raise ValueError("Invalid registration access token")
            
            # Update metadata
            validated_metadata = self._validate_client_metadata(client_metadata)
            client.update(validated_metadata)
            
            logger.info(f"📝 Updated OAuth client: {client_id}")
            
            return client
    
    def delete_client(self, client_id: str, access_token: str) -> bool:
        """Delete client registration (works with proxy clients)"""
        # Check if this is a proxy client
        if client_id.startswith("mcp_"):
            # Use OAuth Proxy to delete
            success = oauth_proxy.delete_proxy_client(
                temp_client_id=client_id,
                access_token=access_token
            )
            
            if success:
                # Remove from local registry if present
                self.clients.pop(client_id, None)
                logger.info(f"🗑️ Deleted proxy OAuth client: {client_id}")
            
            return success
        else:
            # Legacy path for direct clients (backward compatibility)
            client = self.clients.get(client_id)
            if not client:
                return False
            
            if client.get("registration_access_token") != access_token:
                raise ValueError("Invalid registration access token")
            
            del self.clients[client_id]
            logger.info(f"🗑️ Deleted OAuth client: {client_id}")
            
            return True
    
    def _validate_client_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and set defaults for client metadata"""
        
        # Default redirect URIs for common MCP clients
        default_redirect_uris = [
            "http://localhost:3000/auth/callback",  # MCP Inspector
            "https://claude.ai/api/mcp/auth_callback",  # Claude.ai current
            "https://claude.com/api/mcp/auth_callback",  # Claude.ai future
        ]
        
        # Set defaults
        validated = {
            "client_name": metadata.get("client_name", "MCP Client"),
            "redirect_uris": metadata.get("redirect_uris", default_redirect_uris),
            "grant_types": metadata.get("grant_types", ["authorization_code", "refresh_token"]),
            "response_types": metadata.get("response_types", ["code"]),
            "token_endpoint_auth_method": metadata.get("token_endpoint_auth_method", "client_secret_basic"),
            "scope": metadata.get("scope", _get_dcr_default_scope()),
        }
        
        # Add any additional metadata
        for key, value in metadata.items():
            if key not in validated:
                validated[key] = value
        
        return validated

# Global registry instance
client_registry = DynamicClientRegistry()

def handle_client_registration(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle POST /oauth/register request"""
    return client_registry.register_client(request_data)

def handle_client_configuration(client_id: str, method: str, 
                              access_token: Optional[str] = None,
                              request_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Handle client configuration requests (GET/PUT/DELETE)"""
    
    if method == "GET":
        client = client_registry.get_client(client_id)
        if not client:
            raise ValueError("Client not found")
        
        if client.get("registration_access_token") != access_token:
            raise ValueError("Invalid registration access token")
        
        return client
    
    elif method == "PUT":
        if not request_data:
            raise ValueError("Request data required for PUT")
        
        return client_registry.update_client(client_id, request_data, access_token)
    
    elif method == "DELETE":
        success = client_registry.delete_client(client_id, access_token)
        if not success:
            raise ValueError("Client not found")
        
        return {"message": "Client deleted successfully"}
    
    else:
        raise ValueError(f"Unsupported method: {method}")