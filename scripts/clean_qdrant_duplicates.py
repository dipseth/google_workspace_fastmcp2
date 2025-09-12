#!/usr/bin/env python3
"""
Clean up duplicate entries in Qdrant collections.

This script removes duplicate components from Qdrant collections by:
1. Deleting and recreating the collection with proper indexing
2. Using deterministic IDs to prevent future duplicates
"""

import logging
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.module_wrapper import ModuleWrapper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def clean_card_framework_collection():
    """Clean and rebuild the card_framework_components_fastembed collection."""
    logger.info("🧹 Cleaning card_framework_components_fastembed collection...")
    
    try:
        # Create wrapper with clear_collection=True to remove duplicates
        wrapper = ModuleWrapper(
            module_or_name="card_framework.v2",
            collection_name="card_framework_components_fastembed",
            index_nested=True,
            index_private=False,
            max_depth=2,
            skip_standard_library=True,
            include_modules=["card_framework", "gchat"],
            exclude_modules=["numpy", "pandas", "matplotlib", "scipy"],
            force_reindex=True,  # Force reindex after clearing
            clear_collection=True  # Clear collection to remove duplicates
        )
        
        # Get component counts
        component_count = len(wrapper.components)
        logger.info(f"✅ Collection rebuilt with {component_count} unique components")
        
        # Verify no duplicates
        from qdrant_client import QdrantClient
        client = QdrantClient(host="localhost", port=6333)
        collection_info = client.get_collection("card_framework_components_fastembed")
        point_count = collection_info.points_count
        
        logger.info(f"📊 Collection stats:")
        logger.info(f"  - Unique components indexed: {component_count}")
        logger.info(f"  - Total points in collection: {point_count}")
        
        if point_count > component_count:
            logger.warning(f"⚠️ Still have duplicates: {point_count - component_count} extra points")
        else:
            logger.info(f"✅ No duplicates detected!")
            
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to clean collection: {e}", exc_info=True)
        return False


def main():
    """Main entry point."""
    logger.info("Starting Qdrant duplicate cleanup...")
    
    # Clean card framework collection
    success = clean_card_framework_collection()
    
    if success:
        logger.info("✅ Cleanup completed successfully!")
        logger.info("\n📝 To prevent future duplicates, the ModuleWrapper now uses:")
        logger.info("  - Deterministic IDs based on component paths")
        logger.info("  - Version tracking to identify stale components")
        logger.info("  - Proper upsert logic to replace existing entries")
    else:
        logger.error("❌ Cleanup failed. Check the logs for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()