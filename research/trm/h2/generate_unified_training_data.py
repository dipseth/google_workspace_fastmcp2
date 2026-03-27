"""Generate unified training data for UnifiedTRN.

Combines MWQueryGroups (search mode) + slot training data (build mode)
into a single format. Adds content embeddings to search groups.

Usage:
    cd research/trm/poc
    PYTHONPATH="$(pwd)/.." .venv/bin/python -m h2.generate_unified_training_data \
        --search-data ../h2/mw_synthetic_groups_v5_hard2.json \
        --build-data ../h2/slot_training_data.json \
        --output ../h2/unified_training_data.json
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np

from .unified_trn import FEATURE_NAMES_V5

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


from .slot_assigner import POOL_VOCAB

# Map document content_type → pool (for enrichment from external collections)
CONTENT_TYPE_TO_POOL: dict[str, str] = {
    "list": "grid_items",              # Lists → grid items
    "table": "grid_items",             # Tables → structured grid
    "pricing_table": "grid_items",     # Pricing → structured grid
    "prose": "content_texts",          # Prose → text content
    "objection_response": "content_texts",  # Responses → text
    "compliance_checklist": "chips",   # Checklists → chip-like tags
    "merchant_archetype": "carousel_cards",  # Profiles → card-like
}


def extract_qdrant_build_pairs(collection: str) -> list[dict]:
    """Extract content + embeddings from a Qdrant document collection as build training pairs."""
    import os
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        logger.warning("qdrant-client not available")
        return []

    url = os.environ.get("QDRANT_URL")
    key = os.environ.get("QDRANT_KEY") or os.environ.get("QDRANT_API_KEY")
    if not url:
        logger.warning("QDRANT_URL not set")
        return []

    client = QdrantClient(url=url, api_key=key, check_compatibility=False)

    # Scroll all points with vectors
    pairs = []
    offset = None
    while True:
        points, next_offset = client.scroll(
            collection_name=collection, limit=100, offset=offset,
            with_payload=True, with_vectors=True,
        )
        for p in points:
            payload = p.payload or {}
            content = payload.get("content", "")
            content_type = payload.get("content_type", "")

            pool = CONTENT_TYPE_TO_POOL.get(content_type)
            if not pool or pool not in POOL_VOCAB:
                continue

            # Use the stored embedding directly
            vec = p.vector
            if isinstance(vec, dict):
                vec = vec.get("default") or list(vec.values())[0]
            if vec is None or len(vec) != 384:
                continue

            # Extract a short content snippet (first 200 chars) as content_text
            snippet = content[:200].strip()
            if not snippet:
                continue

            pool_id = POOL_VOCAB[pool]
            pairs.append({
                "content_text": snippet,
                "content_embedding": list(vec) if not isinstance(vec, list) else vec,
                "slot_type": pool,
                "slot_type_id": pool_id,
                "label": 1.0,
                "source": f"qdrant_{collection}",
            })

        if next_offset is None:
            break
        offset = next_offset

    logger.info(f"Extracted {len(pairs)} build pairs from {collection}")

    # Add negatives
    import random as rng_mod
    all_pools = list(POOL_VOCAB.keys())
    negatives = []
    for p in pairs:
        neg_pool = rng_mod.choice([x for x in all_pools if x != p["slot_type"]])
        negatives.append({
            "content_text": p["content_text"],
            "content_embedding": p["content_embedding"],
            "slot_type": neg_pool,
            "slot_type_id": POOL_VOCAB[neg_pool],
            "label": 0.0,
            "source": f"qdrant_{collection}_neg",
        })
    pairs.extend(negatives)

    return pairs


def add_content_embeddings(groups: list[dict]) -> list[dict]:
    """Add MiniLM content embeddings to search groups that have content_text."""
    texts_to_embed = []
    group_indices = []

    for i, g in enumerate(groups):
        ct = g.get("content_text", "")
        if ct:
            texts_to_embed.append(ct)
            group_indices.append(i)

    if not texts_to_embed:
        logger.warning("No groups have content_text — content embeddings will be zeros")
        return groups

    logger.info(f"Embedding {len(texts_to_embed)} content texts...")
    try:
        from fastembed import TextEmbedding
        embedder = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
        embeddings = list(embedder.embed(texts_to_embed))
    except ImportError:
        logger.error("fastembed not available — cannot embed content texts")
        raise

    for idx, emb in zip(group_indices, embeddings):
        groups[idx]["content_embedding"] = emb.tolist()

    logger.info(f"Added content embeddings to {len(group_indices)}/{len(groups)} groups")
    return groups


def extract_structural_features(candidate: dict) -> list[float]:
    """Extract 17D structural features from a candidate dict."""
    return [candidate.get(f, 0.0) for f in FEATURE_NAMES_V5]


def main():
    parser = argparse.ArgumentParser(description="Generate UnifiedTRN training data")
    parser.add_argument("--search-data", type=str, required=True,
                        help="MWQueryGroups JSON (mw_synthetic_groups_v5_hard2.json)")
    parser.add_argument("--build-data", type=str, required=True,
                        help="Slot training data JSON (slot_training_data.json)")
    parser.add_argument("--output", type=str, required=True,
                        help="Output unified JSON path")
    parser.add_argument("--skip-embeddings", action="store_true",
                        help="Skip embedding (use if content_embedding already present)")
    parser.add_argument("--enrich-collection", type=str, default=None,
                        help="Qdrant collection to enrich build data (e.g., dev_playbook_cosmetic_injections)")
    args = parser.parse_args()

    # Load search data
    with open(args.search_data) as f:
        search_groups = json.load(f)
    logger.info(f"Loaded {len(search_groups)} search groups")

    # Add content embeddings if needed
    has_emb = any("content_embedding" in g for g in search_groups)
    if not has_emb and not args.skip_embeddings:
        search_groups = add_content_embeddings(search_groups)

    # Verify structural features exist
    sample_cand = search_groups[0]["candidates"][0]
    feat_keys = [f for f in FEATURE_NAMES_V5 if f in sample_cand]
    logger.info(f"Found {len(feat_keys)}/{len(FEATURE_NAMES_V5)} feature keys in candidates")

    # Load build data
    with open(args.build_data) as f:
        build_pairs = json.load(f)
    logger.info(f"Loaded {len(build_pairs)} build pairs")

    # Verify build data has embeddings
    if build_pairs and "content_embedding" not in build_pairs[0]:
        logger.error("Build data missing content_embedding — run generate_slot_training_data.py first")
        return

    # Optionally enrich with Qdrant document collection
    if args.enrich_collection:
        qdrant_build = extract_qdrant_build_pairs(args.enrich_collection)
        if qdrant_build:
            build_pairs.extend(qdrant_build)
            logger.info(f"Enriched with {len(qdrant_build)} Qdrant build pairs, total: {len(build_pairs)}")

    # Package into unified format
    unified = {
        "search_groups": search_groups,
        "build_pairs": build_pairs,
        "metadata": {
            "n_search_groups": len(search_groups),
            "n_search_with_content": sum(1 for g in search_groups if g.get("content_embedding")),
            "n_build_pairs": len(build_pairs),
            "structural_dim": len(FEATURE_NAMES_V5),
            "content_dim": 384,
            "feature_names": FEATURE_NAMES_V5,
        },
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(unified, f)
    logger.info(f"Saved to {output_path} ({output_path.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
