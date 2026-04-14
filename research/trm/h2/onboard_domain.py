"""Onboard a new domain into the TRM/learned scorer pipeline.

Orchestrates the full lifecycle:
  1. Verify Qdrant collection has class points with RIC vectors
  2. Auto-detect component hierarchy and suggest DomainConfig (if not registered)
  3. Generate synthetic training data
  4. Generate slot/pool training data (if content templates exist)
  5. Merge into unified training format
  6. Train UnifiedTRN model
  7. Report metrics and checkpoint path

Usage:
    PYTHONPATH=. uv run python research/trm/h2/onboard_domain.py \
        --domain gchat --collection mcp_gchat_cards_v8

    # For a new domain (auto-detect config from Qdrant):
    PYTHONPATH=. uv run python research/trm/h2/onboard_domain.py \
        --domain my_module --collection my_module_components --auto-detect
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s [onboard] %(message)s")
logger = logging.getLogger(__name__)

# Ensure project root is on path
_project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_project_root))

_h2_dir = Path(__file__).resolve().parent


def verify_qdrant_collection(collection: str) -> dict:
    """Verify a Qdrant collection exists and has class points with RIC vectors.

    Returns dict with: n_points, has_components, has_inputs, has_relationships,
    component_names (list of unique component names found).
    """
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import FieldCondition, Filter, MatchValue
    except ImportError:
        logger.error("qdrant-client not installed")
        return {"error": "qdrant-client not installed"}

    url = os.environ.get("QDRANT_URL")
    key = os.environ.get("QDRANT_KEY") or os.environ.get("QDRANT_API_KEY")
    if not url:
        return {"error": "QDRANT_URL not set"}

    client = QdrantClient(url=url, api_key=key)

    try:
        info = client.get_collection(collection)
    except Exception as e:
        return {"error": f"Collection '{collection}' not found: {e}"}

    n_points = info.points_count or 0

    # Sample some points to check vector names and extract component names
    result = client.scroll(
        collection_name=collection,
        scroll_filter=Filter(
            must=[FieldCondition(key="type", match=MatchValue(value="class"))]
        ),
        limit=200,
        with_payload=True,
        with_vectors=False,
    )
    points, _ = result
    component_names = sorted(
        set(p.payload.get("name", "") for p in points if p.payload)
    )

    # Check named vectors from collection config
    vectors_config = info.config.params.vectors if info.config else {}
    has_components = "components" in (vectors_config or {})
    has_inputs = "inputs" in (vectors_config or {})
    has_relationships = "relationships" in (vectors_config or {})

    return {
        "n_points": n_points,
        "n_class_points": len(points),
        "has_components": has_components,
        "has_inputs": has_inputs,
        "has_relationships": has_relationships,
        "component_names": component_names,
    }


def auto_detect_domain_config(
    collection: str,
    domain_id: str,
) -> Optional[Dict[str, Any]]:
    """Auto-detect a DomainConfig skeleton from Qdrant collection data.

    Scrolls the collection, extracts component types, and suggests
    pool groupings based on parent/child relationships.

    Returns a dict suitable for constructing a DomainConfig, or None on failure.
    """
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import FieldCondition, Filter, MatchValue
    except ImportError:
        return None

    url = os.environ.get("QDRANT_URL")
    key = os.environ.get("QDRANT_KEY") or os.environ.get("QDRANT_API_KEY")
    if not url:
        return None

    client = QdrantClient(url=url, api_key=key)

    # Scroll all class points
    all_points = []
    offset = None
    while True:
        result = client.scroll(
            collection_name=collection,
            scroll_filter=Filter(
                must=[FieldCondition(key="type", match=MatchValue(value="class"))]
            ),
            limit=200,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        batch, next_offset = result
        all_points.extend(batch)
        if next_offset is None:
            break
        offset = next_offset

    if not all_points:
        logger.warning(f"No class points found in '{collection}'")
        return None

    # Extract component metadata
    components = {}
    for point in all_points:
        payload = point.payload or {}
        name = payload.get("name", "")
        if not name:
            continue
        components[name] = {
            "parent": payload.get("parent"),
            "component_type": payload.get("component_type", "class"),
            "docstring": (payload.get("docstring") or "")[:100],
        }

    # Group into pools: containers (have children) vs leaves
    parents = set()
    leaves = set()
    for name, info in components.items():
        parent = info.get("parent")
        if parent:
            parents.add(parent)

    for name in components:
        if name in parents:
            # This component has children — it's a container
            pass
        else:
            leaves.add(name)

    # Create pool vocab: one pool per leaf type, containers get "structural"
    pool_vocab = {}
    component_to_pool = {}
    pool_idx = 0

    # Group leaves by first word of component type (rough heuristic)
    leaf_groups: Dict[str, List[str]] = {}
    for leaf in sorted(leaves):
        # Use lowercase first word as group key
        group_key = leaf.lower().rstrip("s")  # Simple depluralization
        if group_key not in leaf_groups:
            leaf_groups[group_key] = []
        leaf_groups[group_key].append(leaf)

    for group_key, members in leaf_groups.items():
        pool_name = f"{group_key}s"  # Pluralize
        pool_vocab[pool_name] = pool_idx
        for member in members:
            component_to_pool[member] = pool_name
        pool_idx += 1

    # Add catch-all for containers
    for name in sorted(components):
        if name not in component_to_pool:
            component_to_pool[name] = "structural"
    if "structural" not in pool_vocab:
        pool_vocab["structural"] = pool_idx

    specificity_order = list(pool_vocab.keys())

    skeleton = {
        "domain_id": domain_id,
        "pool_vocab": pool_vocab,
        "component_to_pool": component_to_pool,
        "specificity_order": specificity_order,
        "n_components": len(components),
        "n_pools": len(pool_vocab),
    }

    logger.info(
        f"Auto-detected config: {len(components)} components → {len(pool_vocab)} pools"
    )
    for pool_name, idx in pool_vocab.items():
        members = [k for k, v in component_to_pool.items() if v == pool_name]
        logger.info(
            f"  Pool '{pool_name}' ({idx}): {members[:5]}{'...' if len(members) > 5 else ''}"
        )

    return skeleton


def run_step(
    step_name: str,
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
) -> bool:
    """Run a subprocess step with logging."""
    logger.info(f"=== {step_name} ===")
    logger.info(f"  cmd: {' '.join(cmd)}")

    run_env = dict(os.environ)
    if env:
        run_env.update(env)

    result = subprocess.run(
        cmd,
        cwd=str(_project_root),
        env=run_env,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logger.error(f"  FAILED (exit {result.returncode})")
        if result.stderr:
            for line in result.stderr.strip().split("\n")[-10:]:
                logger.error(f"    {line}")
        return False

    # Show last few lines of stdout
    if result.stdout:
        for line in result.stdout.strip().split("\n")[-5:]:
            logger.info(f"  {line}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Onboard a domain into the TRM/learned scorer pipeline"
    )
    parser.add_argument(
        "--domain",
        required=True,
        help="Domain ID (e.g., 'gchat', 'email', or a new domain name)",
    )
    parser.add_argument(
        "--collection",
        required=True,
        help="Qdrant collection containing class points with RIC vectors",
    )
    parser.add_argument(
        "--auto-detect",
        action="store_true",
        help="Auto-detect DomainConfig from Qdrant data (for new domains)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=500,
        help="Number of synthetic structures to generate",
    )
    parser.add_argument("--epochs", type=int, default=150, help="Training epochs")
    parser.add_argument(
        "--feature-version",
        type=int,
        default=5,
        choices=[2, 3, 5],
        help="Feature version for training data",
    )
    parser.add_argument(
        "--skip-training",
        action="store_true",
        help="Generate data only, skip model training",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify collection and show config, don't run pipeline",
    )
    args = parser.parse_args()

    # Step 1: Verify Qdrant collection
    logger.info(f"\n{'=' * 60}")
    logger.info(f"Onboarding domain: {args.domain}")
    logger.info(f"Collection: {args.collection}")
    logger.info(f"{'=' * 60}\n")

    logger.info("=== Step 1: Verify Qdrant collection ===")
    info = verify_qdrant_collection(args.collection)

    if "error" in info:
        logger.error(f"  {info['error']}")
        sys.exit(1)

    logger.info(
        f"  Points: {info['n_points']} total, {info['n_class_points']} class points"
    )
    logger.info(
        f"  RIC vectors: components={info['has_components']}, "
        f"inputs={info['has_inputs']}, relationships={info['has_relationships']}"
    )
    logger.info(
        f"  Components: {info['component_names'][:10]}{'...' if len(info['component_names']) > 10 else ''}"
    )

    if info["n_class_points"] == 0:
        logger.error("No class points found — index components first via ModuleWrapper")
        sys.exit(1)

    # Step 2: Check or auto-detect DomainConfig
    logger.info("\n=== Step 2: Check DomainConfig ===")
    from research.trm.h2.domain_config import (
        DomainConfig,
        get_domain,
        list_domains,
        register_domain,
    )

    if args.domain in list_domains():
        domain = get_domain(args.domain)
        logger.info(
            f"  Domain '{args.domain}' already registered: {domain.n_pools} pools"
        )
    elif args.auto_detect:
        logger.info(f"  Domain '{args.domain}' not registered — auto-detecting...")
        skeleton = auto_detect_domain_config(args.collection, args.domain)
        if not skeleton:
            logger.error("  Auto-detection failed")
            sys.exit(1)

        # Create and register the domain
        domain = DomainConfig(
            domain_id=skeleton["domain_id"],
            pool_vocab=skeleton["pool_vocab"],
            component_to_pool=skeleton["component_to_pool"],
            specificity_order=skeleton["specificity_order"],
        )
        register_domain(domain)
        logger.info(f"  Registered domain '{args.domain}' with {domain.n_pools} pools")
        logger.info(
            f"  NOTE: Add content_affinity and content_templates to domain_config.py for V5 features"
        )

        # Save skeleton for reference
        skeleton_path = _h2_dir / f"domain_skeleton_{args.domain}.json"
        with open(skeleton_path, "w") as f:
            json.dump(skeleton, f, indent=2)
        logger.info(f"  Skeleton saved to {skeleton_path}")
    else:
        logger.error(
            f"  Domain '{args.domain}' not registered. "
            f"Either add it to domain_config.py or use --auto-detect."
        )
        logger.info(f"  Registered domains: {list_domains()}")
        sys.exit(1)

    if args.dry_run:
        logger.info("\n=== Dry run complete ===")
        return

    # Step 3: Generate training data
    fv = args.feature_version
    prefix = f"{args.domain}_" if args.domain != "gchat" else "mw_"
    data_path = _h2_dir / f"{prefix}synthetic_groups_v{fv}.json"

    success = run_step(
        "Step 3: Generate training data",
        [
            sys.executable,
            "-m",
            "research.trm.h2.generate_training_data",
            "--domain",
            args.domain,
            "--collection",
            args.collection,
            "--count",
            str(args.count),
            "--feature-version",
            str(fv),
            "--output",
            str(data_path),
        ],
    )
    if not success:
        logger.error("Training data generation failed")
        sys.exit(1)

    # Step 4: Generate slot training data (if domain has content templates)
    slot_data_path = _h2_dir / f"{prefix}slot_training_data.json"
    domain = get_domain(args.domain)

    if domain.has_content_knowledge:
        success = run_step(
            "Step 4: Generate slot training data",
            [
                sys.executable,
                "-m",
                "research.trm.h2.generate_slot_training_data",
                "--domain",
                args.domain,
                "--collection",
                args.collection,
                "--output",
                str(slot_data_path),
            ],
        )
        if not success:
            logger.warning(
                "Slot training data generation failed — continuing without it"
            )
            slot_data_path = None
    else:
        logger.info("\n=== Step 4: Skipped (no content_templates in domain config) ===")
        slot_data_path = None

    # Step 5: Merge into unified format
    unified_path = _h2_dir / f"{prefix}unified_training_data.json"
    merge_cmd = [
        sys.executable,
        "-m",
        "research.trm.h2.generate_unified_training_data",
        "--search-data",
        str(data_path),
        "--output",
        str(unified_path),
    ]
    if slot_data_path and slot_data_path.exists():
        merge_cmd.extend(["--build-data", str(slot_data_path)])

    success = run_step("Step 5: Merge into unified format", merge_cmd)
    if not success:
        logger.warning("Unified merge failed — using search data directly")
        unified_path = data_path

    # Step 6: Train model
    if args.skip_training:
        logger.info("\n=== Step 6: Skipped (--skip-training) ===")
    else:
        train_cmd = [
            sys.executable,
            "-m",
            "research.trm.h2.train_unified",
            "--domain",
            args.domain,
            "--search-data",
            str(data_path),
            "--epochs",
            str(args.epochs),
            "--checkpoint-dir",
            str(_h2_dir / "checkpoints"),
        ]
        if slot_data_path and slot_data_path.exists():
            train_cmd.extend(["--build-data", str(slot_data_path)])

        success = run_step("Step 6: Train UnifiedTRN", train_cmd)
        if not success:
            logger.error("Training failed")
            sys.exit(1)

    # Step 7: Report
    logger.info(f"\n{'=' * 60}")
    logger.info(f"Onboarding complete: {args.domain}")
    logger.info(f"{'=' * 60}")
    logger.info(f"  Domain: {args.domain}")
    logger.info(f"  Collection: {args.collection}")
    logger.info(f"  Training data: {data_path}")
    if slot_data_path and slot_data_path.exists():
        logger.info(f"  Slot data: {slot_data_path}")
    checkpoint_path = _h2_dir / "checkpoints" / "best_model_unified.pt"
    if checkpoint_path.exists() and not args.skip_training:
        logger.info(f"  Checkpoint: {checkpoint_path}")
    logger.info(f"\nTo use the trained model, set:")
    logger.info(f"  LEARNED_SCORER_CHECKPOINT={checkpoint_path}")


if __name__ == "__main__":
    main()
