#!/usr/bin/env python3
"""
Test the complete MCP Inspector OAuth flow to diagnose the client_secret issue.
This simulates exactly what MCP Inspector does:
1. Call Dynamic Client Registration endpoint
2. Use returned credentials for token exchange
"""

import os
import sys
import json
import requests
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Manually load .env file to ensure environment variables are available
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    print(f"Loading .env file from: {env_path}")
    load_dotenv(env_path, override=True)

def test_mcp_inspector_flow():
    """Test the complete MCP Inspector OAuth flow."""
    
    print("="*70)
    print("MCP Inspector OAuth Flow Test")
    print("="*70)
    
    # Step 1: Simulate Dynamic Client Registration
    print("\n1. Testing Dynamic Client Registration:")
    
    server_url = "http://localhost:8000"  # Adjust if your server runs on a different port
    
    # Make DCR request
    dcr_url = f"{server_url}/oauth/register"
    dcr_payload = {
        "client_name": "MCP Inspector Test Client",
        "redirect_uris": [
            "http://127.0.0.1:6274/oauth/callback/debug",
            "http://localhost:3000/auth/callback"
        ]
    }
    
    print(f"   POST {dcr_url}")
    print(f"   Payload: {json.dumps(dcr_payload, indent=2)}")
    
    try:
        response = requests.post(dcr_url, json=dcr_payload)
        response.raise_for_status()
        
        client_info = response.json()
        print(f"   ✓ DCR Response received:")
        print(f"   client_id: {client_info.get('client_id', 'MISSING')}")
        print(f"   client_secret: {'PRESENT' if client_info.get('client_secret') else 'MISSING'}")
        
        if not client_info.get('client_secret'):
            print("   ❌ ERROR: client_secret is missing from DCR response!")
            return
        
    except Exception as e:
        print(f"   ❌ DCR Request failed: {e}")
        print("   Make sure your FastMCP server is running on port 8000")
        return
    
    # Step 2: Show what MCP Inspector should do with these credentials
    print("\n2. What MCP Inspector should do for token exchange:")
    print("   When exchanging authorization code for tokens at Google's endpoint,")
    print("   MCP Inspector should include these parameters:")
    print(f"   - client_id: {client_info.get('client_id')}")
    print(f"   - client_secret: {client_info.get('client_secret')}")
    print("   - code: [authorization code from user]")
    print("   - redirect_uri: [matching redirect URI]")
    print("   - grant_type: authorization_code")
    
    # Step 3: Test if we can use these credentials
    print("\n3. Testing if credentials work with Google OAuth:")
    
    # Try to build authorization URL with the client_id
    auth_url = (
        "https://accounts.google.com/o/oauth2/auth?"
        f"client_id={client_info.get('client_id')}&"
        f"redirect_uri={dcr_payload['redirect_uris'][0]}&"
        "response_type=code&"
        "scope=openid+email+profile"
    )
    
    print(f"   Authorization URL would be:")
    print(f"   {auth_url[:100]}...")
    
    print("\n4. Diagnosis:")
    if client_info.get('client_secret'):
        print("   ✓ Our server IS providing client_secret correctly")
        print("   ✓ The issue is likely that MCP Inspector is not using it")
        print("   Possible causes:")
        print("     - MCP Inspector might not be storing the client_secret from DCR")
        print("     - MCP Inspector might not be sending client_secret in token request")
        print("     - There might be a format/encoding issue with the credentials")
    else:
        print("   ❌ Our server is NOT providing client_secret")
        print("   This needs to be fixed in the DCR endpoint")

if __name__ == "__main__":
    # First, check if the server is accessible
    try:
        response = requests.get("http://localhost:8000/.well-known/oauth-protected-resource", timeout=2)
        print("✓ FastMCP server is accessible")
    except:
        print("❌ Cannot reach FastMCP server. Please start it with:")
        print("   uv run mcp start")
        sys.exit(1)
    
    test_mcp_inspector_flow()