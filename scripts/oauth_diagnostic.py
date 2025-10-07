#!/usr/bin/env python3
"""
OAuth Configuration Diagnostic Tool

This script checks the OAuth configuration and identifies any issues.
"""

import os
import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def main():
    print("🔍 OAuth Configuration Diagnostic")
    print("=" * 50)
    
    try:
        # Check if we can import the settings
        print("📋 Loading configuration...")
        from config.settings import settings
        print("✅ Settings loaded successfully")
        
        # Check OAuth configuration
        print("\n🔐 Checking OAuth Configuration:")
        print(f"  Google Client Secrets File: {settings.google_client_secrets_file}")
        print(f"  Google Client ID: {'SET' if settings.google_client_id else 'NOT SET'}")
        print(f"  Google Client Secret: {'SET' if settings.google_client_secret else 'NOT SET'}")
        print(f"  OAuth Redirect URI: {settings.oauth_redirect_uri}")
        print(f"  Dynamic OAuth Redirect URI: {settings.dynamic_oauth_redirect_uri}")
        print(f"  Base URL: {settings.base_url}")
        print(f"  Protocol: {settings.protocol}")
        
        # Check if OAuth is configured
        is_configured = settings.is_oauth_configured()
        print(f"\n🎯 OAuth Configured: {'✅ YES' if is_configured else '❌ NO'}")
        
        if is_configured:
            try:
                # Try to get OAuth client config
                oauth_config = settings.get_oauth_client_config()
                print("✅ OAuth client configuration retrieved")
                print(f"  Client ID: {oauth_config['client_id'][:20]}...")
                print(f"  Client Secret: {'SET' if oauth_config['client_secret'] else 'NOT SET'}")
                print(f"  Auth URI: {oauth_config.get('auth_uri', 'NOT SET')}")
                print(f"  Token URI: {oauth_config.get('token_uri', 'NOT SET')}")
                print(f"  Redirect URIs: {len(oauth_config.get('redirect_uris', []))} configured")
            except Exception as e:
                print(f"❌ Error getting OAuth config: {e}")
        else:
            print("⚠️  OAuth is not configured. You need to either:")
            print("     1. Set GOOGLE_CLIENT_SECRETS_FILE environment variable, OR")
            print("     2. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables")
        
        # Check environment variables
        print("\n🌍 Environment Variables:")
        env_vars = [
            'GOOGLE_CLIENT_SECRETS_FILE',
            'GOOGLE_CLIENT_ID',
            'GOOGLE_CLIENT_SECRET',
            'OAUTH_REDIRECT_URI',
            'BASE_URL',
            'SERVER_PORT',
            'ENABLE_HTTPS',
            'USE_GOOGLE_OAUTH',
            'ENABLE_JWT_AUTH'
        ]
        
        for var in env_vars:
            value = os.getenv(var)
            if value:
                # Mask sensitive values
                if 'SECRET' in var or 'CLIENT_ID' in var:
                    display_value = f"{'SET' if value else 'NOT SET'} ({'*' * min(len(value), 20)})"
                else:
                    display_value = value
                print(f"  {var}: {display_value}")
            else:
                print(f"  {var}: NOT SET")
        
        # Check credentials directory
        print(f"\n📂 Credentials Directory: {settings.credentials_dir}")
        creds_path = Path(settings.credentials_dir)
        if creds_path.exists():
            print("✅ Credentials directory exists")
            # List credential files (without exposing content)
            cred_files = list(creds_path.glob("*"))
            print(f"  Files found: {len(cred_files)}")
            for file in cred_files:
                print(f"    - {file.name}")
        else:
            print("❌ Credentials directory does not exist")
            print(f"  Will be created at: {creds_path.absolute()}")
        
        # Check Google OAuth client secrets file if specified
        if settings.google_client_secrets_file:
            secrets_path = Path(settings.google_client_secrets_file)
            print(f"\n📄 Google OAuth Secrets File: {secrets_path}")
            if secrets_path.exists():
                print("✅ OAuth secrets file exists")
                try:
                    with open(secrets_path, 'r') as f:
                        secrets_data = json.load(f)
                    
                    if 'web' in secrets_data:
                        web_config = secrets_data['web']
                        print("✅ 'web' configuration found")
                        print(f"  Client ID: {web_config.get('client_id', 'NOT SET')[:20]}...")
                        print(f"  Client Secret: {'SET' if web_config.get('client_secret') else 'NOT SET'}")
                        print(f"  Redirect URIs: {len(web_config.get('redirect_uris', []))} configured")
                    elif 'installed' in secrets_data:
                        installed_config = secrets_data['installed']  
                        print("✅ 'installed' configuration found")
                        print(f"  Client ID: {installed_config.get('client_id', 'NOT SET')[:20]}...")
                        print(f"  Client Secret: {'SET' if installed_config.get('client_secret') else 'NOT SET'}")
                        print(f"  Redirect URIs: {len(installed_config.get('redirect_uris', []))} configured")
                    else:
                        print("❌ OAuth secrets file missing 'web' or 'installed' configuration")
                        
                except json.JSONDecodeError as e:
                    print(f"❌ OAuth secrets file contains invalid JSON: {e}")
                except Exception as e:
                    print(f"❌ Error reading OAuth secrets file: {e}")
            else:
                print(f"❌ OAuth secrets file does not exist at: {secrets_path.absolute()}")
        
        # Test OAuth proxy
        print("\n🔄 Testing OAuth Proxy:")
        try:
            from auth.oauth_proxy import oauth_proxy
            stats = oauth_proxy.get_stats()
            print("✅ OAuth Proxy is working")
            print(f"  Active proxy clients: {stats['active_proxy_clients']}")
            print(f"  Oldest client age: {stats.get('oldest_client_age', 'N/A')}")
            print(f"  Newest client age: {stats.get('newest_client_age', 'N/A')}")
        except Exception as e:
            print(f"❌ OAuth Proxy error: {e}")
        
        # Test dynamic client registration
        print("\n📝 Testing Dynamic Client Registration:")
        try:
            from auth.dynamic_client_registration import client_registry
            print("✅ Dynamic Client Registration is available")
            
            # Test a simple registration (won't work without OAuth config but will show errors)
            if is_configured:
                test_metadata = {
                    "client_name": "Test MCP Client",
                    "redirect_uris": ["http://localhost:3000/auth/callback"]
                }
                print("🧪 Testing client registration...")
                try:
                    result = client_registry.register_client(test_metadata)
                    temp_client_id = result.get('client_id')
                    print(f"✅ Test registration successful: {temp_client_id}")
                    
                    # Clean up the test client
                    try:
                        access_token = result.get('registration_access_token')
                        if access_token:
                            client_registry.delete_client(temp_client_id, access_token)
                            print("✅ Test client cleaned up")
                    except Exception as cleanup_e:
                        print(f"⚠️  Cleanup warning: {cleanup_e}")
                        
                except Exception as reg_e:
                    print(f"❌ Test registration failed: {reg_e}")
            else:
                print("⚠️  Skipping registration test - OAuth not configured")
                
        except Exception as e:
            print(f"❌ Dynamic Client Registration error: {e}")
        
        # Summary and recommendations
        print("\n" + "=" * 50)
        print("📋 SUMMARY AND RECOMMENDATIONS:")
        
        if not is_configured:
            print("❌ CRITICAL: OAuth is not configured!")
            print("   You need to:")
            print("   1. Create a Google OAuth 2.0 client in Google Cloud Console")
            print("   2. Download the client secrets JSON file")
            print("   3. Set GOOGLE_CLIENT_SECRETS_FILE environment variable")
            print("   OR")
            print("   3. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables")
        else:
            print("✅ OAuth is configured and should work!")
            print("   Your server should be able to handle OAuth flows.")
            
            # Additional checks
            if not settings.enable_https and 'https' in settings.dynamic_oauth_redirect_uri:
                print("⚠️  WARNING: HTTPS is disabled but redirect URI uses HTTPS")
                print("   Consider setting ENABLE_HTTPS=true or updating OAUTH_REDIRECT_URI")
            
            if settings.server_host == "localhost" and settings.dynamic_oauth_redirect_uri:
                print("✅ Local development setup detected")
                print(f"   Redirect URI: {settings.dynamic_oauth_redirect_uri}")
        
        print("\n🚀 To test the server:")
        print("   1. Run: uv run fastmcp dev")
        print("   2. Check: http://localhost:8002/.well-known/oauth-protected-resource/mcp")
        print("   3. Test registration: POST http://localhost:8002/oauth/register")
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())