# Qdrant Collection Deduplication Fix

## Problem
The `card_framework_components_fastembed` Qdrant collection was accumulating duplicate entries on every server restart because:
1. The ModuleWrapper was using random UUIDs (`uuid.uuid4()`) for point IDs
2. Each restart would create new UUIDs for the same components
3. The collection would grow by ~2,855 components on each restart (17x duplication observed)

## Solution Implemented

### 1. Deterministic IDs
- Changed from random UUIDs to deterministic IDs based on component paths
- ID generation: `hashlib.sha256(f"{collection_name}:{component_path}".encode()).hexdigest()[:16]`
- This ensures the same component always gets the same ID across restarts

### 2. Version Tracking
- Added `indexed_at` timestamp to track when components were indexed
- Added `module_version` to track module version changes
- Enables identification of stale components for cleanup

### 3. Clear Collection Option
- Added `clear_collection` parameter to ModuleWrapper
- When `True`, deletes and recreates the collection before indexing
- Ensures a completely clean state with no duplicates

### 4. Configuration Controls
- Environment variable `CLEAR_CARD_COLLECTION_ON_STARTUP` to clear on startup
- Environment variable `FORCE_REINDEX_COMPONENTS` to force reindexing
- Provides flexibility without code changes

## Usage

### One-time Cleanup
Run the cleanup script to remove existing duplicates:
```bash
python scripts/clean_qdrant_duplicates.py
```

### Prevent Future Duplicates
The fix is automatic - deterministic IDs prevent duplicate accumulation.

### Force Clean Rebuild (if needed)
```bash
# Set environment variable before starting server
export CLEAR_CARD_COLLECTION_ON_STARTUP=true
python server.py
```

## Verification

Check collection status:
```python
from qdrant_client import QdrantClient

client = QdrantClient(host="localhost", port=6333)
info = client.get_collection("card_framework_components_fastembed")
print(f"Points in collection: {info.points_count}")
# Should be ~2,855 for card_framework.v2 components
```

## Technical Details

### Before Fix
- Random UUID generation: `id=str(uuid.uuid4())`
- No duplicate detection
- Collection grew unbounded

### After Fix
- Deterministic ID: `id=hashlib.sha256(f"{collection_name}:{path}".encode()).hexdigest()[:16]`
- Upsert replaces existing points with same ID
- Collection size remains constant

## Benefits
1. **Stable collection size** - No more unbounded growth
2. **Improved performance** - Smaller collection = faster searches
3. **Predictable behavior** - Same components get same IDs
4. **Easy cleanup** - Script to rebuild from scratch if needed
5. **Configurable** - Environment variables for control