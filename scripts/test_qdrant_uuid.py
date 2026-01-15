#!/usr/bin/env python3
"""Test script to verify UUID format is valid for Qdrant."""

import hashlib

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams


# Create deterministic UUID-formatted ID
def create_deterministic_uuid(collection_name: str, path: str) -> str:
    """Create a deterministic UUID-formatted ID from collection name and path."""
    id_string = f"{collection_name}:{path}"
    hash_hex = hashlib.sha256(id_string.encode()).hexdigest()
    # Format as UUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    uuid_id = f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"
    return uuid_id


def test_qdrant_uuid():
    """Test if Qdrant accepts our UUID format."""
    client = QdrantClient(host="localhost", port=6333)

    # Create a test collection
    test_collection = "test_uuid_format"

    try:
        # Delete collection if it exists
        try:
            client.delete_collection(test_collection)
            print(f"✅ Deleted existing test collection: {test_collection}")
        except:
            pass

        # Create test collection
        client.create_collection(
            collection_name=test_collection,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
        print(f"✅ Created test collection: {test_collection}")

        # Create test point with UUID-formatted ID
        test_path = "test.component.path"
        uuid_id = create_deterministic_uuid(test_collection, test_path)
        print(f"📝 Generated UUID: {uuid_id}")

        # Create a test point
        point = PointStruct(
            id=uuid_id,
            vector=[0.1] * 384,  # Dummy vector
            payload={"path": test_path, "test": True},
        )

        # Try to upsert the point
        client.upsert(collection_name=test_collection, points=[point])
        print(f"✅ Successfully upserted point with UUID ID: {uuid_id}")

        # Verify the point was stored
        result = client.retrieve(collection_name=test_collection, ids=[uuid_id])

        if result and len(result) > 0:
            print("✅ Successfully retrieved point with UUID ID")
            print(f"   Payload: {result[0].payload}")
        else:
            print("❌ Failed to retrieve point")

        # Clean up
        client.delete_collection(test_collection)
        print("✅ Cleaned up test collection")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        # Clean up on error
        try:
            client.delete_collection(test_collection)
        except:
            pass
        return False


if __name__ == "__main__":
    print("🧪 Testing Qdrant UUID format...")
    success = test_qdrant_uuid()
    if success:
        print("\n✅ UUID format is valid for Qdrant!")
    else:
        print("\n❌ UUID format test failed")
