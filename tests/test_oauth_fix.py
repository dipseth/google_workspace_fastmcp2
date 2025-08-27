#!/usr/bin/env python3
"""Test to verify the OAuth fix is working correctly."""

import sys
import os
from pathlib import Path
import json

# Add the project directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_oauth_with_mcp_context():
    """Test OAuth configuration in MCP context."""
    
    print("=" * 70)
    print("OAuth MCP Context Test")
    print("=" * 70)
    
    # Load .env file manually to ensure environment variables are set
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        print(f"\n1. Loading .env file from: {env_file}")
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # Only set if not already in environment
                    if key not in os.environ:
                        os.environ[key] = value.strip('"').strip("'")
                        print(f"   Set {key}")
    
    # Now test the OAuth configuration
    print("\n2. Testing OAuth Configuration after .env load:")
    from config.settings import settings
    
    print(f"   google_client_secrets_file: {settings.google_client_secrets_file}")
    print(f"   credential_storage_mode: {settings.credential_storage_mode}")
    
    try:
        oauth_config = settings.get_oauth_client_config()
        print("   ✓ OAuth config loaded successfully")
        print(f"   client_id: {oauth_config.get('client_id', 'MISSING')[:20]}...")
        print(f"   client_secret: {'PRESENT' if oauth_config.get('client_secret') else 'MISSING'}")
    except Exception as e:
        print(f"   ✗ Failed to get OAuth config: {e}")
        return False
    
    # Test the fixed Dynamic Client Registration
    print("\n3. Testing Fixed Dynamic Client Registration:")
    try:
        from auth.dynamic_client_registration import DynamicClientRegistry
        registry = DynamicClientRegistry()
        
        test_metadata = {
            "client_name": "MCP Inspector Client",
            "redirect_uris": ["http://localhost:3000/auth/callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "scope": "openid email profile https://www.googleapis.com/auth/drive.file"
        }
        
        result = registry.register_client(test_metadata)
        print("   ✓ Client registration successful!")
        print(f"   client_id: {result.get('client_id', 'MISSING')[:20]}...")
        print(f"   client_secret: {'PRESENT' if result.get('client_secret') else 'MISSING'}")
        return True
        
    except Exception as e:
        print(f"   ✗ Client registration failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    success = test_oauth_with_mcp_context()
    sys.exit(0 if success else 1)