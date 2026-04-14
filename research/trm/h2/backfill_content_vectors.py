"""Backfill content vectors on existing instance_pattern points in Qdrant.

Fixes the gap where instance patterns stored before the supply_map fix
(2026-03-25) have has_content_vector=false and zero content vectors.

Usage:
    cd research/trm/poc
    PYTHONPATH="$(pwd)/.." .venv/bin/python -m h2.backfill_content_vectors \
        --collection mcp_gchat_cards_v8 \
        --dry-run

    # Actually write to Qdrant:
    PYTHONPATH="$(pwd)/.." .venv/bin/python -m h2.backfill_content_vectors \
        --collection mcp_gchat_cards_v8
"""

import argparse
import os
import sys

import numpy as np

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))
except ImportError:
    pass  # dotenv not available in research venv; env vars set externally


def backfill(collection: str, dry_run: bool = True):
    """Backfill content vectors on instance_pattern points."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        FieldCondition,
        Filter,
        MatchValue,
        PointIdsList,
        PointVectors,
        SetPayloadOperation,
    )

    from adapters.module_wrapper.pipeline_mixin import (
        extract_content_text_from_params,
    )

    url = os.getenv("QDRANT_URL")
    key = os.getenv("QDRANT_KEY")
    if not url:
        print("ERROR: QDRANT_URL not set in .env")
        sys.exit(1)

    client = QdrantClient(url=url, api_key=key)

    # Check collection schema
    info = client.get_collection(collection)
    vectors_config = info.config.params.vectors
    if not isinstance(vectors_config, dict) or "content" not in vectors_config:
        print(
            f"ERROR: Collection {collection} does not have 'content' named vector.\n"
            "Start the MCP server first to trigger 3→4 vector schema migration."
        )
        sys.exit(1)

    print(f"Collection: {collection} ({info.points_count} total points)")
    print(f"Named vectors: {list(vectors_config.keys())}")

    # Scroll all instance_pattern points
    all_points = []
    offset = None
    while True:
        results, next_offset = client.scroll(
            collection_name=collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="type", match=MatchValue(value="instance_pattern")
                    )
                ]
            ),
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=["content"],
        )
        all_points.extend(results)
        if next_offset is None:
            break
        offset = next_offset

    print(f"Found {len(all_points)} instance_pattern points")

    # Load MiniLM embedder
    from fastembed import TextEmbedding

    embedder = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
    print("Loaded MiniLM embedder")

    # Process each point
    needs_backfill = []
    already_has = 0
    no_content = 0

    for point in all_points:
        payload = point.payload or {}

        # Skip if already has content vector
        if payload.get("has_content_vector"):
            already_has += 1
            continue

        # Also check if vector is non-zero (in case payload flag is missing)
        content_vec = point.vector
        if isinstance(content_vec, dict):
            content_vec = content_vec.get("content")
        if content_vec and isinstance(content_vec, list):
            norm = float(np.linalg.norm(content_vec))
            if norm > 1e-6:
                already_has += 1
                continue

        # Extract content text from instance_params
        instance_params = payload.get("instance_params", {})
        card_description = payload.get("card_description", "")

        content_text = extract_content_text_from_params(
            instance_params, card_description
        )

        if not content_text:
            no_content += 1
            continue

        needs_backfill.append(
            {
                "id": point.id,
                "content_text": content_text,
                "title": instance_params.get("title", "?"),
            }
        )

    print(f"\nSummary:")
    print(f"  Already has content vector: {already_has}")
    print(f"  No content to extract: {no_content}")
    print(f"  Needs backfill: {len(needs_backfill)}")

    if not needs_backfill:
        print("\nNothing to backfill.")
        return

    # Show what we'd backfill
    for item in needs_backfill[:10]:
        print(
            f"  {str(item['id'])[:8]} | {item['title'][:40]} | {item['content_text'][:60]}"
        )
    if len(needs_backfill) > 10:
        print(f"  ... and {len(needs_backfill) - 10} more")

    if dry_run:
        print("\n[DRY RUN] No changes written. Run without --dry-run to apply.")
        return

    # Embed and upsert
    texts = [item["content_text"] for item in needs_backfill]
    print(f"\nEmbedding {len(texts)} content texts...")
    embeddings = list(embedder.embed(texts))

    updated = 0
    failed = 0
    for item, emb in zip(needs_backfill, embeddings):
        content_vec = emb.tolist() if hasattr(emb, "tolist") else list(emb)
        try:
            # Update the content vector
            client.update_vectors(
                collection_name=collection,
                points=[
                    PointVectors(
                        id=item["id"],
                        vector={"content": content_vec},
                    )
                ],
            )

            # Update payload flags
            client.set_payload(
                collection_name=collection,
                payload={
                    "has_content_vector": True,
                    "content_embedding_meta": {
                        "model": "minilm_384",
                        "encrypted": False,
                        "backfilled": True,
                    },
                },
                points=[item["id"]],
            )
            updated += 1
        except Exception as e:
            print(f"  FAILED {str(item['id'])[:8]}: {e}")
            failed += 1

    print(f"\nBackfill complete: {updated} updated, {failed} failed")


def main():
    parser = argparse.ArgumentParser(
        description="Backfill content vectors on existing instance patterns"
    )
    parser.add_argument(
        "--collection",
        default="mcp_gchat_cards_v8",
        help="Qdrant collection name",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without writing",
    )
    args = parser.parse_args()

    backfill(collection=args.collection, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
