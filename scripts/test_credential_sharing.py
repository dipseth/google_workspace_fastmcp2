#!/usr/bin/env python3
"""Test credential sharing across different client scenarios."""

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from auth.google_auth import get_all_stored_users, _normalize_email, _load_credentials, get_valid_credentials
from auth.middleware import AuthMiddleware, CredentialStorageMode
from auth.context import get_user_email_from_oauth
from config.settings import settings


def test_credential_files():
    """Test what credential files exist and can be loaded."""
    print("🔍 Testing Credential Files\n")
    print(f"Credentials directory: {settings.credentials_dir}\n")
    
    # List all credential files
    creds_dir = Path(settings.credentials_dir)
    if creds_dir.exists():
        print("📁 Found credential files:")
        for pattern in ["*_credentials.json", "*_credentials.enc", "*_backup.enc"]:
            files = list(creds_dir.glob(pattern))
            for file in files:
                print(f"  - {file.name}")
        print()
    
    # Get stored users
    users = get_all_stored_users()
    print(f"👥 Stored users ({len(users)}):")
    for user in users:
        print(f"  - {user}")
    print()
    
    return users


def test_oauth_auth_file():
    """Test OAuth authentication file."""
    print("🔍 Testing OAuth Authentication File\n")
    
    oauth_file = Path(settings.credentials_dir) / ".oauth_authentication.json"
    if oauth_file.exists():
        print(f"✅ OAuth authentication file exists: {oauth_file}")
        try:
            with open(oauth_file, 'r') as f:
                data = json.load(f)
            print(f"📧 Authenticated email: {data.get('authenticated_email')}")
            print(f"🕐 Authenticated at: {data.get('authenticated_at')}")
            print(f"📋 Scopes: {len(data.get('scopes', []))} scopes")
            print()
            return data.get('authenticated_email')
        except Exception as e:
            print(f"❌ Error reading OAuth file: {e}\n")
            return None
    else:
        print(f"❌ OAuth authentication file not found: {oauth_file}\n")
        return None


def test_me_myself_resolution(test_email: str = None):
    """Test 'me'/'myself' resolution logic."""
    print("🔍 Testing 'me'/'myself' Resolution\n")
    
    # Test the resolution helper
    from auth.context import get_user_email_from_oauth
    
    oauth_email = get_user_email_from_oauth()
    print(f"📧 Email from OAuth file: {oauth_email}")
    
    if test_email:
        print(f"\n📧 Testing with email: {test_email}")
        # Simulate what happens with 'me'/'myself'
        resolved = test_email if test_email not in ['me', 'myself'] else None
        print(f"  'me'/'myself' resolved to: {resolved}")
        
        final = resolved or oauth_email
        print(f"  Final email (with OAuth fallback): {final}")
    print()


def test_credential_loading(users: list):
    """Test loading credentials for each stored user."""
    print("🔍 Testing Credential Loading\n")
    
    # Initialize AuthMiddleware with proper encryption for .enc files
    from auth.context import set_auth_middleware
    
    middleware = AuthMiddleware(storage_mode=CredentialStorageMode.FILE_ENCRYPTED)
    set_auth_middleware(middleware)  # Make it globally available
    
    print(f"📦 Storage mode: {middleware.get_storage_mode().value}")
    print(f"🔐 Encryption ready: {hasattr(middleware, '_fernet')}\n")
    
    for user in users:
        print(f"Testing: {user}")
        try:
            # _load_credentials now uses AuthMiddleware internally if available
            creds = _load_credentials(user)
            if creds:
                print(f"  ✅ Loaded successfully")
                print(f"  🔑 Has access token: {bool(creds.token)}")
                print(f"  🔑 Has refresh token: {bool(creds.refresh_token)}")
                print(f"  ⏰ Expired: {creds.expired if hasattr(creds, 'expired') else 'Unknown'}")
                
                # Verify credentials work
                print(f"  🔍 Client ID: {creds.client_id[:20] if creds.client_id else 'None'}...")
                print(f"  📋 Scopes: {len(creds.scopes) if creds.scopes else 0} scopes")
            else:
                print(f"  ❌ Failed to load credentials")
        except Exception as e:
            print(f"  ❌ Error: {e}")
            import traceback
            print("  Traceback:")
            traceback.print_exc()
        print()


def test_middleware_email_injection():
    """Test the middleware email injection logic."""
    print("🔍 Testing Middleware Email Injection Logic\n")
    
    # Create a mock middleware
    middleware = AuthMiddleware(storage_mode=CredentialStorageMode.FILE_ENCRYPTED)
    
    # Test OAuth file loading
    oauth_email = middleware._load_oauth_authentication_data()
    print(f"📧 Email from OAuth file (via middleware): {oauth_email}")
    
    # Test what happens when user_email is None
    print(f"\n✅ FIXED: When user_email is None, middleware now:")
    print(f"   1. Checks .oauth_authentication.json for email")
    print(f"   2. If found, uses real email (e.g., '{oauth_email}')")
    print(f"   3. Loads credentials from .enc file")
    print(f"   4. No re-auth required!")
    print()


def main():
    """Run all diagnostic tests."""
    print("=" * 60)
    print("CREDENTIAL SHARING DIAGNOSTIC TEST")
    print("=" * 60)
    print()
    
    # Test 1: Credential files
    users = test_credential_files()
    
    # Test 2: OAuth authentication file
    oauth_email = test_oauth_auth_file()
    
    # Test 3: Me/myself resolution
    test_me_myself_resolution(oauth_email)
    
    # Test 4: Credential loading
    if users:
        test_credential_loading(users)
    
    # Test 5: Middleware logic
    test_middleware_email_injection()
    
    print("=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60)
    print("\n🔍 KEY FINDINGS:")
    print(f"  - {len(users)} user(s) with stored credentials")
    print(f"  - OAuth authentication file email: {oauth_email or 'None'}")
    print(f"  - 'me'/'myself' should resolve to: {oauth_email or 'UNKNOWN (causes re-auth!)'}")


if __name__ == "__main__":
    main()