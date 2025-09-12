#!/usr/bin/env python3
"""
Test script to verify Qdrant middleware uses the correct configuration from settings.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging to see the debug output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s:%(lineno)d [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)

async def test_qdrant_config():
    """Test that middleware uses correct Qdrant configuration."""
    try:
        # Import settings to see what's loaded
        from config.settings import settings
        
        print(f"🔧 Settings loaded:")
        print(f"   qdrant_url: {settings.qdrant_url}")
        print(f"   qdrant_host: {settings.qdrant_host}")
        print(f"   qdrant_port: {settings.qdrant_port}")
        print(f"   qdrant_api_key: {'***' if settings.qdrant_api_key else 'None'}")
        
        # Import and create middleware instance
        from middleware.qdrant_unified import QdrantUnifiedMiddleware
        
        print(f"\n🧪 Creating QdrantUnifiedMiddleware with settings...")
        middleware = QdrantUnifiedMiddleware(
            qdrant_host=settings.qdrant_host,
            qdrant_port=settings.qdrant_port,
            qdrant_api_key=settings.qdrant_api_key,
            qdrant_url=settings.qdrant_url,
            collection_name="test_collection",
            auto_discovery=True,
            ports=[settings.qdrant_port, 6333, 6335, 6334]
        )
        
        print(f"\n✅ Middleware created successfully")
        print(f"   Configured host: {middleware.qdrant_host}")
        print(f"   Configured port: {middleware.qdrant_port}")
        print(f"   Configured URL: {middleware.qdrant_url}")
        print(f"   API key configured: {'Yes' if middleware.qdrant_api_key else 'No'}")
        print(f"   Auto-discovery enabled: {middleware.auto_discovery}")
        
        # Test initialization (this will try to connect)
        print(f"\n🔗 Testing initialization...")
        try:
            await middleware.initialize()
            print(f"✅ Middleware initialized successfully!")
            print(f"   Connected URL: {middleware.discovered_url}")
            print(f"   Client available: {middleware.client is not None}")
            print(f"   Embedder available: {middleware.embedder is not None}")
        except Exception as e:
            print(f"⚠️ Initialization failed (expected if no Qdrant available): {e}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_qdrant_config())