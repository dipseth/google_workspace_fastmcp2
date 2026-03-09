#!/usr/bin/env python3
"""
Migrate existing instance_patterns to differentiate components vs inputs vectors.

Previously, store_instance_pattern() embedded card_description for BOTH the
inputs and components vectors (they were identical). This script re-embeds:
  - components: from parent_paths via _build_component_identity_text()
  - inputs: from instance_params via format_instance_params() + card_description

The relationships vector is left unchanged.

Usage:
    uv run python scripts/migrate_instance_pattern_vectors.py
    uv run python scripts/migrate_instance_pattern_vectors.py --dry-run
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct

from adapters.module_wrapper.pipeline_mixin import format_instance_params
from config.qdrant_client import get_qdrant_client
from config.settings import settings
from gchat.feedback_loop import FeedbackLoop

COLLECTION_NAME = settings.card_collection
BATCH_SIZE = 50


def migrate_instance_pattern_vectors(dry_run: bool = False):
    """Re-embed components and inputs vectors for all instance_patterns."""
    print("=" * 60)
    print("INSTANCE PATTERN VECTOR DIFFERENTIATION MIGRATION")
    if dry_run:
        print("  ** DRY RUN — no changes will be written **")
    print("=" * 60)

    client = get_qdrant_client()
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
    print(f"\nTotal instance_patterns: {total}")

    if total == 0:
        print("No patterns to migrate.")
        return

    migrated = 0
    skipped = 0
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

        updated_points = []

        for point in points:
            try:
                payload = point.payload
                vectors = point.vector
                name = payload.get("name", point.id)

                # Skip already-migrated points (they have inputs_text in payload)
                if payload.get("inputs_text"):
                    print(f"  - {name}: already migrated, skipping")
                    skipped += 1
                    continue

                parent_paths = payload.get("parent_paths", [])
                instance_params = payload.get("instance_params", {})
                card_description = payload.get("card_description", "")

                # Build component identity text and embed
                component_identity_text = fl._build_component_identity_text(
                    parent_paths
                )
                component_vectors = fl._embed_description(component_identity_text)
                if not component_vectors:
                    print(f"  ! {name}: failed to embed components, skipping")
                    errors += 1
                    continue

                # Build inputs text and embed
                inputs_text = format_instance_params(instance_params)
                if card_description:
                    inputs_text = f"{inputs_text} | {card_description}"
                inputs_vectors = fl._embed_description(inputs_text)
                if not inputs_vectors:
                    print(f"  ! {name}: failed to embed inputs, skipping")
                    errors += 1
                    continue

                # Keep existing relationships vector unchanged
                relationships_vector = vectors.get("relationships", [])

                # Update payload with debug fields
                new_payload = payload.copy()
                new_payload["component_identity_text"] = component_identity_text
                new_payload["inputs_text"] = inputs_text

                updated_point = PointStruct(
                    id=point.id,
                    vector={
                        "components": component_vectors,
                        "inputs": inputs_vectors,
                        "relationships": relationships_vector,
                    },
                    payload=new_payload,
                )
                updated_points.append(updated_point)

                print(
                    f"  + {name}: components='{component_identity_text[:40]}...', "
                    f"inputs='{inputs_text[:40]}...'"
                )
                migrated += 1

            except Exception as e:
                print(f"  ! Error processing {point.id}: {e}")
                errors += 1

        # Upsert batch
        if updated_points and not dry_run:
            client.upsert(
                collection_name=COLLECTION_NAME,
                points=updated_points,
            )
            print(f"  >> Upserted {len(updated_points)} points")
        elif updated_points and dry_run:
            print(f"  >> Would upsert {len(updated_points)} points (dry run)")

        processed = migrated + skipped + errors
        print(
            f"\nProgress: {processed}/{total} "
            f"({migrated} migrated, {skipped} skipped, {errors} errors)"
        )

        if next_offset is None:
            break
        offset = next_offset

    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE" + (" (DRY RUN)" if dry_run else ""))
    print(f"  Migrated: {migrated}")
    print(f"  Skipped:  {skipped}")
    print(f"  Errors:   {errors}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Re-embed instance_pattern components and inputs vectors"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to Qdrant",
    )
    args = parser.parse_args()
    migrate_instance_pattern_vectors(dry_run=args.dry_run)
