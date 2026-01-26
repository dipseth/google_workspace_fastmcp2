#!/usr/bin/env python3
"""
Migrate existing instance_patterns to include DSL notation.

This script:
1. Scrolls through all instance_patterns in mcp_gchat_cards_v7
2. Generates DSL notation from parent_paths
3. Updates relationship_text field
4. Re-embeds the relationships vector with DSL notation
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct

from config.qdrant_client import get_qdrant_client
from config.settings import settings
from gchat.card_framework_wrapper import get_card_framework_wrapper
from gchat.feedback_loop import FeedbackLoop

COLLECTION_NAME = settings.card_collection
BATCH_SIZE = 50


def migrate_instance_patterns():
    """Migrate all instance_patterns to include DSL notation."""
    print("=" * 60)
    print("INSTANCE PATTERN DSL MIGRATION")
    print("=" * 60)

    client = get_qdrant_client()
    wrapper = (
        get_card_framework_wrapper()
    )  # Get ModuleWrapper for canonical DSL generation
    fl = FeedbackLoop()

    # Count patterns
    count_result = client.count(
        collection_name=COLLECTION_NAME,
        count_filter=Filter(
            must=[
                FieldCondition(key="type", match=MatchValue(value="instance_pattern"))
            ]
        ),
    )
    total = count_result.count
    print(f"\nTotal instance_patterns to migrate: {total}")

    if total == 0:
        print("No patterns to migrate.")
        return

    # Scroll through all instance_patterns
    migrated = 0
    errors = 0
    offset = None

    while True:
        results = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="type", match=MatchValue(value="instance_pattern")
                    )
                ]
            ),
            limit=BATCH_SIZE,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )

        points, next_offset = results

        if not points:
            break

        # Process batch
        updated_points = []

        for point in points:
            try:
                payload = point.payload
                vectors = point.vector

                # Get parent_paths
                parent_paths = payload.get("parent_paths", [])
                structure_desc = payload.get("structure_description", "")

                if not parent_paths:
                    print(f"  ⚠️ {payload.get('name')}: No parent_paths, skipping")
                    continue

                # Generate DSL notation using ModuleWrapper (canonical implementation)
                dsl_text = wrapper.build_dsl_from_paths(parent_paths, structure_desc)

                # Check if already has DSL notation
                existing_rel_text = payload.get("relationship_text", "")
                if existing_rel_text and existing_rel_text.startswith("§["):
                    print(f"  ✓ {payload.get('name')}: Already has DSL, skipping")
                    continue

                # Re-embed relationships with DSL notation
                new_rel_vector = fl._embed_relationships(parent_paths, structure_desc)

                # Update payload
                new_payload = payload.copy()
                new_payload["relationship_text"] = dsl_text

                # Create updated point
                updated_point = PointStruct(
                    id=point.id,
                    vector={
                        "components": vectors.get("components", []),
                        "inputs": vectors.get("inputs", []),
                        "relationships": new_rel_vector,
                    },
                    payload=new_payload,
                )
                updated_points.append(updated_point)

                print(f"  📝 {payload.get('name')}: {dsl_text[:50]}...")
                migrated += 1

            except Exception as e:
                print(f"  ❌ Error processing {point.id}: {e}")
                errors += 1

        # Upsert batch
        if updated_points:
            client.upsert(
                collection_name=COLLECTION_NAME,
                points=updated_points,
            )
            print(f"  ✅ Upserted {len(updated_points)} points")

        # Progress
        print(
            f"\nProgress: {migrated + errors}/{total} processed ({migrated} migrated, {errors} errors)"
        )

        if next_offset is None:
            break
        offset = next_offset

    print("\n" + "=" * 60)
    print(f"MIGRATION COMPLETE")
    print(f"  Migrated: {migrated}")
    print(f"  Errors: {errors}")
    print(f"  Skipped: {total - migrated - errors}")
    print("=" * 60)


if __name__ == "__main__":
    migrate_instance_patterns()
