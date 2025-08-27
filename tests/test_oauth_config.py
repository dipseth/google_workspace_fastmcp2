#!/usr/bin/env python3
"""Test script to verify OAuth configuration is loaded correctly."""

import sys
import os
from pathlib import Path

# Add the project directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

def test_oauth_config():
    """Test OAuth configuration loading."""
    
    print("=" * 70)
    print("OAuth Configuration Test")
    print("=" * 70)
    
    # Check environment variables
    print("\n1. Environment Variables:")
    print(f"   GOOGLE_CLIENT_SECRETS_FILE: {os.environ.get('GOOGLE_CLIENT_SECRETS_FILE', 'NOT SET')}")
    print(f"   GOOGLE_CLIENT_ID: {os.environ.get('GOOGLE_CLIENT_ID', 'NOT SET')}")
    print(f"   GOOGLE_CLIENT_SECRET: {'SET' if os.environ.get('GOOGLE_CLIENT_SECRET') else 'NOT SET'}")
    print(f"   CREDENTIAL_STORAGE_MODE: {os.environ.get('CREDENTIAL_STORAGE_MODE', 'NOT SET')}")
    
    # Try to load settings
    print("\n2. Loading Settings...")
    try:
        from config.settings import settings
        print("   ✓ Settings loaded successfully")
        
        # Check OAuth configuration
        print("\n3. OAuth Configuration Status:")
        print(f"   google_client_secrets_file: {settings.google_client_secrets_file}")
        print(f"   is_oauth_configured: {settings.is_oauth_configured()}")
        
        # Check if file exists
        if settings.google_client_secrets_file:
            file_path = Path(settings.google_client_secrets_file)
            print(f"   File exists: {file_path.exists()}")
            if file_path.exists():
                print(f"   File size: {file_path.stat().st_size} bytes")
        
        # Try to get OAuth config
        print("\n4. Attempting to get OAuth client config...")
        try:
            oauth_config = settings.get_oauth_client_config()
            print("   ✓ OAuth config loaded successfully")
            print(f"   client_id: {oauth_config.get('client_id', 'MISSING')[:20]}..." if oauth_config.get('client_id') else "   client_id: MISSING")
            print(f"   client_secret: {'PRESENT' if oauth_config.get('client_secret') else 'MISSING'}")
            print(f"   auth_uri: {oauth_config.get('auth_uri', 'MISSING')}")
            print(f"   token_uri: {oauth_config.get('token_uri', 'MISSING')}")
        except Exception as e:
            print(f"   ✗ Failed to get OAuth config: {e}")
            
    except Exception as e:
        print(f"   ✗ Failed to load settings: {e}")
        import traceback
        traceback.print_exc()
    
    # Test Dynamic Client Registration
    print("\n5. Testing Dynamic Client Registration...")
    try:
        from auth.dynamic_client_registration import DynamicClientRegistry
        registry = DynamicClientRegistry()
        
        test_metadata = {
            "client_name": "Test MCP Client",
            "redirect_uris": ["http://localhost:3000/callback"]
        }
        
        print("   Attempting to register a test client...")
        try:
            result = registry.register_client(test_metadata)
            print("   ✓ Client registration successful!")
            print(f"   client_id: {result.get('client_id', 'MISSING')[:20]}...")
            print(f"   client_secret: {'PRESENT' if result.get('client_secret') else 'MISSING'}")
        except Exception as e:
            print(f"   ✗ Client registration failed: {e}")
            
    except Exception as e:
        print(f"   ✗ Failed to test Dynamic Client Registration: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("Test Complete")
    print("=" * 70)


if __name__ == "__main__":
    test_oauth_config()