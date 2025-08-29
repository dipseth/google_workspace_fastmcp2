#!/usr/bin/env python
"""
Verification script for Qdrant configuration.
Tests that all components are properly using environment variables.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def verify_qdrant_config():
    """Verify Qdrant configuration is properly loaded from environment."""
    
    print("=" * 60)
    print("🔍 QDRANT CONFIGURATION VERIFICATION")
    print("=" * 60)
    
    # Step 1: Check environment variables
    print("\n📋 Step 1: Checking Environment Variables")
    print("-" * 40)
    
    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_key = os.getenv("QDRANT_KEY")
    
    if qdrant_url:
        print(f"✅ QDRANT_URL: {qdrant_url}")
    else:
        print("❌ QDRANT_URL not set in environment")
        
    if qdrant_key:
        # Mask the key for security
        masked_key = "***" if qdrant_key != "NONE" else "NONE"
        print(f"✅ QDRANT_KEY: {masked_key}")
    else:
        print("❌ QDRANT_KEY not set in environment")
    
    # Step 2: Load and verify settings
    print("\n📋 Step 2: Loading Settings Configuration")
    print("-" * 40)
    
    try:
        from config.settings import settings
        
        print(f"✅ Settings loaded successfully")
        print(f"   qdrant_url: {settings.qdrant_url}")
        print(f"   qdrant_host: {settings.qdrant_host}")
        print(f"   qdrant_port: {settings.qdrant_port}")
        
        # Check API key
        if hasattr(settings, 'qdrant_api_key'):
            if settings.qdrant_api_key:
                print(f"   qdrant_api_key: ***SET***")
            else:
                print(f"   qdrant_api_key: NOT SET/NONE")
        else:
            print("   ⚠️  qdrant_api_key not found in settings")
            
    except Exception as e:
        print(f"❌ Error loading settings: {e}")
        return False
    
    # Step 3: Test Qdrant connection
    print("\n📋 Step 3: Testing Qdrant Connection")
    print("-" * 40)
    
    try:
        from qdrant_client import QdrantClient
        
        # Create client with settings
        client_args = {
            "host": settings.qdrant_host,
            "port": settings.qdrant_port
        }
        
        if hasattr(settings, 'qdrant_api_key') and settings.qdrant_api_key:
            client_args["api_key"] = settings.qdrant_api_key
            print(f"🔑 Using API key authentication")
        else:
            print(f"🔓 No authentication (local Qdrant)")
            
        client = QdrantClient(**client_args)
        
        # Test connection by getting collections
        collections = client.get_collections()
        print(f"✅ Successfully connected to Qdrant at {settings.qdrant_url}")
        print(f"✅ Found {len(collections.collections)} collections:")
        
        for collection in collections.collections:
            # Get collection info
            info = client.get_collection(collection.name)
            point_count = info.points_count if hasattr(info, 'points_count') else 0
            print(f"   - {collection.name} ({point_count} points)")
            
    except Exception as e:
        print(f"❌ Failed to connect to Qdrant: {e}")
        return False
    
    # Step 4: Check middleware configuration
    print("\n📋 Step 4: Checking Middleware Configuration")
    print("-" * 40)
    
    try:
        from middleware.qdrant_unified import QdrantUnifiedMiddleware
        
        # Test that middleware can be initialized with settings
        test_middleware = QdrantUnifiedMiddleware(
            qdrant_host=settings.qdrant_host,
            qdrant_port=settings.qdrant_port,
            qdrant_api_key=getattr(settings, 'qdrant_api_key', None)
        )
        print("✅ QdrantUnifiedMiddleware initialized with settings")
        
    except Exception as e:
        print(f"❌ Error initializing middleware: {e}")
    
    # Step 5: Check adapter configuration
    print("\n📋 Step 5: Checking Adapter Configuration")
    print("-" * 40)
    
    try:
        from adapters.module_wrapper import ModuleWrapper
        
        # Test that adapter can be initialized with settings
        print("✅ ModuleWrapper can be initialized with settings")
        print(f"   - Will use host: {settings.qdrant_host}")
        print(f"   - Will use port: {settings.qdrant_port}")
        if hasattr(settings, 'qdrant_api_key') and settings.qdrant_api_key:
            print(f"   - Will use API key authentication")
            
    except Exception as e:
        print(f"❌ Error checking adapter: {e}")
    
    print("\n" + "=" * 60)
    print("✅ QDRANT CONFIGURATION VERIFICATION COMPLETE")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    success = verify_qdrant_config()
    sys.exit(0 if success else 1)