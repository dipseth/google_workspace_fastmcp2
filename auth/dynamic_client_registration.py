"""
OAuth 2.0 Dynamic Client Registration (RFC 7591) Implementation
"""
import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class DynamicClientRegistry:
    """In-memory dynamic client registration store"""
    
    def __init__(self):
        self.clients: Dict[str, Dict[str, Any]] = {}
        self.access_tokens: Dict[str, Dict[str, Any]] = {}
    
    def register_client(self, client_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Register a new OAuth client dynamically using real Google OAuth credentials"""
        
        # Import settings to get real Google OAuth credentials
        from config.settings import settings
        
        # Get the real Google OAuth client configuration
        try:
            oauth_config = settings.get_oauth_client_config()
            real_client_id = oauth_config['client_id']
            real_client_secret = oauth_config['client_secret']
            
            logger.info(f"📝 Using real Google OAuth credentials for DCR")
            logger.info(f"   Client ID: {real_client_id[:20]}...")
            
        except Exception as e:
            logger.error(f"❌ Failed to get Google OAuth credentials: {e}")
            # Fallback to fake credentials if real ones aren't available
            real_client_id = f"mcp_client_{secrets.token_urlsafe(16)}"
            real_client_secret = secrets.token_urlsafe(32)
            logger.warning(f"Using fallback fake credentials: {real_client_id}")
        
        # Generate other required fields
        registration_access_token = secrets.token_urlsafe(32)
        
        # Set defaults and validate metadata
        validated_metadata = self._validate_client_metadata(client_metadata)
        
        # Store client registration with REAL Google OAuth credentials
        client_info = {
            "client_id": real_client_id,           # Real Google client ID!
            "client_secret": real_client_secret,   # Real Google client secret!
            "client_id_issued_at": int(datetime.utcnow().timestamp()),
            "client_secret_expires_at": 0,  # Never expires
            "registration_access_token": registration_access_token,
            "registration_client_uri": f"http://localhost:8002/oauth/register/{real_client_id}",
            **validated_metadata
        }
        
        self.clients[real_client_id] = client_info
        
        logger.info(f"✅ Registered OAuth client with REAL Google credentials: {real_client_id[:20]}...")
        
        return client_info
    
    def get_client(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Get client information"""
        return self.clients.get(client_id)
    
    def update_client(self, client_id: str, client_metadata: Dict[str, Any], 
                     access_token: str) -> Dict[str, Any]:
        """Update client registration"""
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
        """Delete client registration"""
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
        
        # Set defaults
        validated = {
            "client_name": metadata.get("client_name", "MCP Inspector Client"),
            "redirect_uris": metadata.get("redirect_uris", ["http://localhost:3000/auth/callback"]),
            "grant_types": metadata.get("grant_types", ["authorization_code", "refresh_token"]),
            "response_types": metadata.get("response_types", ["code"]),
            "token_endpoint_auth_method": metadata.get("token_endpoint_auth_method", "client_secret_basic"),
            "scope": metadata.get("scope", "openid email profile https://www.googleapis.com/auth/drive"),
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