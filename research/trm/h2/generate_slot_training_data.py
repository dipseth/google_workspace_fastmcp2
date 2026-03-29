"""Generate training data for SlotAffinityNet.

Produces (content_text, slot_type, label) training pairs from:
  A) Synthetic data — CONTENT_AFFINITY + CONTENT_TEXT_TEMPLATES (existing)
  B) Real card builds — instance_pattern points from Qdrant (optional)

Usage:
    cd research/trm/poc
    PYTHONPATH="$(pwd)/.." .venv/bin/python -m h2.generate_slot_training_data \
        --output ../h2/slot_training_data.json

    # With Qdrant real data:
    PYTHONPATH="$(pwd)/.." .venv/bin/python -m h2.generate_slot_training_data \
        --output ../h2/slot_training_data.json \
        --include-qdrant --collection mcp_gchat_cards_v8
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "poc"))

from .generate_training_data import CONTENT_AFFINITY, CONTENT_TEXT_TEMPLATES
from .slot_assigner import COMPONENT_TO_POOL, POOL_VOCAB

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _split_template(template: str) -> list[str]:
    """Split a template string into individual content items."""
    items = [item.strip() for item in template.split(",")]
    return [item for item in items if item]


def generate_synthetic_pairs(
    rng: random.Random,
    augment_factor: int = 3,
) -> list[dict[str, Any]]:
    """Generate (content_text, slot_type, label) pairs from CONTENT_AFFINITY + templates.

    For each component type with templates:
    - Split templates into individual items
    - Each item + its component's slot type = positive (1.0)
    - Each item + a random different slot type = negative (0.0)
    """
    pairs: list[dict[str, Any]] = []
    all_pools = list(POOL_VOCAB.keys())

    # Collect (item_text, pool_key) from templates
    positive_items: list[tuple[str, str]] = []

    for comp_name, templates in CONTENT_TEXT_TEMPLATES.items():
        pool_key = COMPONENT_TO_POOL.get(comp_name)
        if not pool_key or pool_key not in POOL_VOCAB:
            continue

        for template in templates:
            items = _split_template(template)
            for item in items:
                positive_items.append((item, pool_key))

    # Also add items from CONTENT_AFFINITY patterns (individual words → short content)
    for comp_name, affinity in CONTENT_AFFINITY.items():
        pool_key = COMPONENT_TO_POOL.get(comp_name)
        if not pool_key or pool_key not in POOL_VOCAB:
            continue
        if affinity.get("type") in ("structural",):
            continue

        patterns = affinity.get("patterns", [])
        for pattern in patterns:
            # Capitalize for realism
            positive_items.append((pattern.title(), pool_key))

    logger.info(f"Collected {len(positive_items)} positive (item, pool) pairs")

    # Generate augmented pairs
    for _ in range(augment_factor):
        for item_text, pool_key in positive_items:
            pool_id = POOL_VOCAB[pool_key]

            # Positive pair
            pairs.append({
                "content_text": item_text,
                "slot_type": pool_key,
                "slot_type_id": pool_id,
                "label": 1.0,
                "source": "synthetic",
            })

            # Hard negative: same content, random different pool
            neg_pools = [p for p in all_pools if p != pool_key]
            neg_pool = rng.choice(neg_pools)
            pairs.append({
                "content_text": item_text,
                "slot_type": neg_pool,
                "slot_type_id": POOL_VOCAB[neg_pool],
                "label": 0.0,
                "source": "synthetic_neg",
            })

    # Add cross-pool confusion pairs (harder negatives)
    confusion_pairs = [
        ("Status: Online", "chips"),         # Status could be a chip filter
        ("Deploy", "content_texts"),         # Deploy verb as label
        ("High Priority", "buttons"),        # Priority as button
        ("API Gateway", "chips"),            # Service name as tag
        ("v2.0.0", "chips"),                # Version as tag
        ("Submit", "content_texts"),         # Action verb as label
        ("Active", "buttons"),              # Status as action
        ("web-server-01", "buttons"),       # Server name as button text
    ]
    for text, wrong_pool in confusion_pairs:
        for _ in range(augment_factor * 2):  # Extra weight on confusion
            pairs.append({
                "content_text": text,
                "slot_type": wrong_pool,
                "slot_type_id": POOL_VOCAB[wrong_pool],
                "label": 0.0,
                "source": "confusion_neg",
            })

    return pairs


def generate_qdrant_pairs(
    collection: str = "mcp_gchat_cards_v8",
) -> list[dict[str, Any]]:
    """Extract real (content_item, slot_type) pairs from Qdrant instance patterns."""
    pairs: list[dict[str, Any]] = []

    try:
        from qdrant_client import QdrantClient
    except ImportError:
        logger.warning("qdrant-client not installed, skipping Qdrant pairs")
        return pairs

    url = os.environ.get("QDRANT_URL")
    key = os.environ.get("QDRANT_KEY") or os.environ.get("QDRANT_API_KEY")
    if not url:
        logger.warning("QDRANT_URL not set, skipping Qdrant pairs")
        return pairs

    client = QdrantClient(url=url, api_key=key)

    # Scroll all instance_pattern points
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    offset = None
    points = []
    while True:
        result = client.scroll(
            collection_name=collection,
            scroll_filter=Filter(
                must=[FieldCondition(key="type", match=MatchValue(value="instance_pattern"))]
            ),
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        batch, next_offset = result
        points.extend(batch)
        if next_offset is None:
            break
        offset = next_offset

    logger.info(f"Qdrant: fetched {len(points)} instance_pattern points")

    all_pools = list(POOL_VOCAB.keys())

    for point in points:
        payload = point.payload or {}
        component_paths = payload.get("component_paths", [])
        instance_params = payload.get("instance_params", {})

        if not component_paths or not instance_params:
            continue

        # Determine primary pool from component_paths
        pool_key = None
        for path in component_paths:
            comp = path.split("/")[-1] if "/" in path else path
            if comp in COMPONENT_TO_POOL:
                pool_key = COMPONENT_TO_POOL[comp]
                break

        if not pool_key or pool_key not in POOL_VOCAB:
            continue

        # Extract content items from instance_params
        content_items = _extract_items_from_params(instance_params)
        if not content_items:
            continue

        for item_text in content_items:
            if not item_text or len(item_text) < 2:
                continue

            # Positive pair
            pairs.append({
                "content_text": item_text,
                "slot_type": pool_key,
                "slot_type_id": POOL_VOCAB[pool_key],
                "label": 1.0,
                "source": "qdrant",
            })

            # Negative pair
            neg_pool = random.choice([p for p in all_pools if p != pool_key])
            pairs.append({
                "content_text": item_text,
                "slot_type": neg_pool,
                "slot_type_id": POOL_VOCAB[neg_pool],
                "label": 0.0,
                "source": "qdrant_neg",
            })

    return pairs


def _extract_items_from_params(params: dict) -> list[str]:
    """Extract individual content text items from instance_params."""
    texts = []
    for key, val in params.items():
        if key in ("dsl", "component_count", "style_metadata", "jinja_applied"):
            continue
        if isinstance(val, str) and len(val) > 1:
            texts.append(val)
        elif isinstance(val, list):
            for item in val[:10]:  # Cap at 10 items
                if isinstance(item, dict):
                    for field in ("text", "title", "label", "subtitle"):
                        fval = item.get(field)
                        if fval and isinstance(fval, str):
                            texts.append(fval)
                elif isinstance(item, str) and len(item) > 1:
                    texts.append(item)
    return texts


def embed_pairs(
    pairs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add MiniLM embeddings to each pair."""
    try:
        from fastembed import TextEmbedding
    except ImportError:
        logger.error("fastembed not installed — cannot embed")
        raise

    embedder = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")

    # Deduplicate texts for efficiency
    unique_texts = list({p["content_text"] for p in pairs})
    logger.info(f"Embedding {len(unique_texts)} unique texts...")

    embeddings = list(embedder.embed(unique_texts))
    text_to_emb = {text: emb.tolist() for text, emb in zip(unique_texts, embeddings)}

    for pair in pairs:
        pair["content_embedding"] = text_to_emb[pair["content_text"]]

    return pairs


def main():
    parser = argparse.ArgumentParser(description="Generate SlotAffinityNet training data")
    parser.add_argument("--output", type=str, required=True, help="Output JSON path")
    parser.add_argument("--augment-factor", type=int, default=3,
                        help="Augmentation factor for synthetic pairs")
    parser.add_argument("--include-qdrant", action="store_true",
                        help="Include real card builds from Qdrant")
    parser.add_argument("--collection", type=str, default="mcp_gchat_cards_v8",
                        help="Qdrant collection for real data")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skip-embeddings", action="store_true",
                        help="Skip embedding generation (for testing)")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    # Generate synthetic pairs
    pairs = generate_synthetic_pairs(rng, augment_factor=args.augment_factor)
    logger.info(f"Synthetic pairs: {len(pairs)}")

    # Optionally add Qdrant pairs
    if args.include_qdrant:
        qdrant_pairs = generate_qdrant_pairs(args.collection)
        pairs.extend(qdrant_pairs)
        logger.info(f"Qdrant pairs: {len(qdrant_pairs)}, total: {len(pairs)}")

    # Shuffle
    rng.shuffle(pairs)

    # Embed
    if not args.skip_embeddings:
        pairs = embed_pairs(pairs)

    # Summary stats
    pos = sum(1 for p in pairs if p["label"] > 0.5)
    neg = len(pairs) - pos
    by_type = {}
    for p in pairs:
        t = p["slot_type"]
        by_type[t] = by_type.get(t, 0) + 1

    logger.info(f"Total: {len(pairs)} pairs ({pos} positive, {neg} negative)")
    logger.info(f"By slot type: {json.dumps(by_type, indent=2)}")

    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(pairs, f)
    logger.info(f"Saved to {output_path} ({output_path.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
