"""Neural content-to-slot assignment for card building.

Uses UnifiedTRN (pool_head) to reassign and reorder supply_map pools
before sequential consumption, fixing misrouted content items.
Falls back to SlotAffinityNet if UnifiedTRN checkpoint not found.

Domain-aware: loads pool vocabulary from checkpoint metadata via
DomainConfig, defaulting to gchat if not specified.

Integration: Called from builder_v2.py between supply_map construction
and context creation. Falls back to original supply_map on any error.
"""

from __future__ import annotations

import logging
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Module-level cache for the loaded model
_cached_model = None
_cached_model_meta: dict = {}
_cached_model_type: str = ""  # "unified" or "slot"
_cached_domain_config = None  # DomainConfig resolved from checkpoint
_model_load_attempted = False


def _extract_item_text(item: Any) -> str:
    """Extract text from a supply_map item (dict or string)."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("text", "title", "label", "subtitle", "styled"):
            val = item.get(key)
            if val and isinstance(val, str):
                return val
    return ""


def _rewrap_item(
    item: Any,
    source_pool: str,
    target_pool: str,
    domain_config: Any = None,
) -> dict:
    """Re-wrap a supply_map item for a different pool's expected schema.

    Uses DomainConfig rewrap_rules when available, falls back to
    hardcoded gchat rules for backward compatibility.
    """
    domain = domain_config if domain_config is not None else _get_domain_config()
    return domain.rewrap_item(item, source_pool, target_pool)


def _get_domain_config():
    """Get the resolved DomainConfig (from checkpoint or default gchat)."""
    global _cached_domain_config
    if _cached_domain_config is not None:
        return _cached_domain_config
    # Ensure model is loaded (which resolves domain config)
    _load_slot_model()
    if _cached_domain_config is not None:
        return _cached_domain_config
    # Fallback: gchat default
    from adapters.domain_config import GCHAT_DOMAIN

    return GCHAT_DOMAIN


def _load_slot_model():
    """Load UnifiedTRN (preferred) or SlotAffinityNet from checkpoint.

    Checks for UNIFIED_TRN_CHECKPOINT / SLOT_ASSIGNER_CHECKPOINT env vars,
    then falls back to default paths. UnifiedTRN is preferred because it
    was jointly trained on form+content+pool tasks.

    Resolves DomainConfig from checkpoint metadata when available.
    Cached after first call.
    """
    global _cached_model, _cached_model_meta, _cached_model_type
    global _cached_domain_config, _model_load_attempted

    if _model_load_attempted:
        return _cached_model

    _model_load_attempted = True

    try:
        import torch
    except ImportError:
        logger.debug("torch not available — slot assignment disabled")
        return None

    base_dir = Path(__file__).resolve().parent.parent.parent / "research" / "trm" / "h2"

    # ── Try UnifiedTRN first ──────────────────────────────────────
    # Priority: cloud artifact cache → env var → default local path
    unified_path = None
    try:
        from lifespans import get_model_artifact_paths

        artifact_paths = get_model_artifact_paths()
        if artifact_paths:
            for key in ("gchat", "default"):
                if key in artifact_paths and Path(artifact_paths[key]).exists():
                    unified_path = artifact_paths[key]
                    break
    except ImportError:
        pass

    if not unified_path:
        unified_path = os.environ.get("UNIFIED_TRN_CHECKPOINT")
    if not unified_path:
        candidate = base_dir / "checkpoints" / "best_model_unified.pt"
        if candidate.exists():
            unified_path = str(candidate)

    if unified_path and Path(unified_path).exists():
        try:
            from adapters.unified_trn import UnifiedTRN

            checkpoint = torch.load(unified_path, map_location="cpu", weights_only=True)
            model = UnifiedTRN(
                structural_dim=checkpoint.get("structural_dim", 17),
                content_dim=checkpoint.get("content_dim", 384),
                hidden=checkpoint.get("hidden", 64),
                n_pools=checkpoint.get("n_pools", 5),
                dropout=0.0,  # no dropout at inference
            )
            model.load_state_dict(checkpoint["model_state_dict"])
            model.eval()

            _cached_model = model
            _cached_model_meta = checkpoint
            _cached_model_type = "unified"

            # Resolve domain config from checkpoint metadata
            from adapters.domain_config import resolve_domain

            _cached_domain_config = resolve_domain(checkpoint=checkpoint)
            domain_id = _cached_domain_config.domain_id

            pool_acc = checkpoint.get(
                "best_pool_acc", checkpoint.get("val_pool_acc", 0)
            )
            content_acc = checkpoint.get("best_content_top1", 0)
            logger.info(
                f"Loaded UnifiedTRN (epoch {checkpoint.get('epoch')}, "
                f"domain={domain_id}, pools={_cached_domain_config.n_pools}, "
                f"pool={pool_acc:.1%}, content={content_acc:.1%})"
            )
            return model
        except ImportError as e:
            # The model class is missing, not the checkpoint. That is a packaging
            # bug (see tests/module/test_no_research_imports.py), not a normal
            # degradation path -- surface it loudly instead of quietly falling
            # back to heuristic content routing.
            logger.error(
                f"UnifiedTRN class unavailable ({e}) despite checkpoint at "
                f"{unified_path} — slot assignment will fall back to heuristics. "
                "This is a packaging bug: the model definition must be importable "
                "from adapters/unified_trn.py."
            )
        except Exception as e:
            logger.warning(f"Failed to load UnifiedTRN: {e} — trying SlotAffinityNet")

    # ── Fallback: SlotAffinityNet ─────────────────────────────────
    slot_path = os.environ.get("SLOT_ASSIGNER_CHECKPOINT")
    if not slot_path:
        candidate = base_dir / "checkpoints" / "best_model_slot.pt"
        if candidate.exists():
            slot_path = str(candidate)

    if not slot_path or not Path(slot_path).exists():
        logger.debug("No slot assigner checkpoint found — slot assignment disabled")
        return None

    try:
        from adapters.slot_assigner import SlotAffinityNet

        checkpoint = torch.load(slot_path, map_location="cpu", weights_only=True)
        model = SlotAffinityNet(
            content_dim=checkpoint.get("content_dim", 384),
            slot_embed_dim=checkpoint.get("slot_embed_dim", 16),
            n_slot_types=checkpoint.get("n_slot_types", 8),
            hidden=checkpoint.get("hidden_dim", 32),
        )
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()

        _cached_model = model
        _cached_model_meta = checkpoint
        _cached_model_type = "slot"

        # Resolve domain config from checkpoint metadata
        from adapters.domain_config import resolve_domain

        _cached_domain_config = resolve_domain(checkpoint=checkpoint)

        val_acc = checkpoint.get("val_accuracy", 0)
        logger.info(
            f"Loaded SlotAffinityNet (epoch {checkpoint.get('epoch')}, "
            f"domain={_cached_domain_config.domain_id}, val_acc={val_acc:.1%})"
        )
        return model
    except Exception as e:
        logger.warning(f"Failed to load slot assigner: {e}")
        return None


def _embed_texts(texts: List[str], wrapper: Any) -> Optional[Any]:
    """Embed texts using the wrapper's MiniLM embedder."""
    try:
        import numpy as np
        import torch

        # Try to get the embedder from the wrapper
        embedder = None
        if wrapper and hasattr(wrapper, "_relationships_embedder"):
            embedder = wrapper._relationships_embedder
        elif wrapper and hasattr(wrapper, "embedding_service"):
            svc = wrapper.embedding_service
            if hasattr(svc, "embed_dense_sync"):
                embeddings = svc.embed_dense_sync(texts)
                return torch.tensor(np.array(embeddings), dtype=torch.float32)

        if embedder is not None:
            embeddings = list(embedder.embed(texts))
            return torch.tensor(np.array(embeddings), dtype=torch.float32)

        # Fallback: load embedder directly
        from fastembed import TextEmbedding

        embedder = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
        embeddings = list(embedder.embed(texts))
        return torch.tensor(np.array(embeddings), dtype=torch.float32)
    except Exception as e:
        logger.debug(f"Embedding failed: {e}")
        return None


def _pin_policy() -> Tuple[str, float]:
    """Resolve the pinning policy from the environment.

    "always" (default, legacy): an item stays in its current pool whenever that
        pool still has unmet demand -- the model is never consulted for items
        that happen to land somewhere with room. Misrouted content stays
        misrouted whenever supply counts line up with DSL demand.

    "confidence": consult the model first. An item is released for rerouting
        only when the model confidently prefers a *different, still-demanded*
        pool. Releasing an item hands its slot back to remaining_demand, so the
        number of unassigned items and the unmet demand stay balanced and no
        pool can be starved by the reroute.

    Calibration caveat (measured 2026-07-25 on mw_slot_training_data.json):
        pool_head probabilities are saturated, not calibrated. train_unified.py
        uses label_smoothing=0.1 over 5 pools, capping the true-class target at
        ~0.92, and observed max-probs span only 0.896-0.959 (median 0.928).
        Top-1-vs-current margin does not separate either: correct-but-moved
        items scored 0.900-0.905, inside the 0.835-0.910 range of genuine fixes.
        So SLOT_REROUTE_CONFIDENCE is effectively an on/off switch, not a dial —
        anything below ~0.89 releases on every disagreement, anything above
        ~0.96 releases nothing. It is kept as an escape hatch, not a tuning knob.
        Making it a real dial needs a calibrated pool_head (temperature scaling,
        or dropping label smoothing) evaluated on a frozen eval set.

    Configuration (both resolve the same two knobs):
        .env / Settings   slot_pin_mode, slot_reroute_confidence
        process env       SLOT_PIN_MODE, SLOT_REROUTE_CONFIDENCE  (takes priority)

    Note pydantic-settings reads .env into Settings but does *not* populate
    os.environ, so .env alone is invisible to a bare os.environ lookup -- hence
    the Settings fallback below. Values are "always" / 0.70 if neither is set.
    """
    default_mode, default_threshold = "always", 0.70
    try:
        from config.settings import settings

        default_mode = getattr(settings, "slot_pin_mode", default_mode)
        default_threshold = getattr(
            settings, "slot_reroute_confidence", default_threshold
        )
    except Exception as e:  # settings unavailable (e.g. isolated unit tests)
        logger.debug(f"Settings unavailable for pin policy, using defaults: {e}")

    mode = os.environ.get("SLOT_PIN_MODE", str(default_mode)).strip().lower()
    if mode not in ("always", "confidence"):
        logger.warning(f"Unknown SLOT_PIN_MODE={mode!r} — falling back to 'always'")
        mode = "always"

    raw = os.environ.get("SLOT_REROUTE_CONFIDENCE", str(default_threshold))
    try:
        threshold = float(raw)
    except ValueError:
        logger.warning(f"Invalid SLOT_REROUTE_CONFIDENCE={raw!r} — using 0.70")
        threshold = 0.70
    threshold = min(max(threshold, 0.0), 1.0)

    return mode, threshold


def _should_release(
    scores: Any,
    source_pool: str,
    remaining_demand: Dict[str, int],
    vocab: Dict[str, int],
    threshold: float,
) -> bool:
    """True when the model confidently wants this item in a different pool.

    Deliberately conservative — every guard here fails toward pinning:
      * no score for the item  -> pin
      * model agrees with the current pool -> pin
      * the preferred pool has no unmet demand -> pin (nowhere to move it)
      * confidence below threshold -> pin
    """
    if scores is None:
        return False

    try:
        import torch

        probs = torch.softmax(scores, dim=-1)
        best_id = int(probs.argmax())
        confidence = float(probs[best_id])
    except Exception as e:  # never let the policy break card building
        logger.debug(f"Release check failed, pinning instead: {e}")
        return False

    id_to_pool = {v: k for k, v in vocab.items()}
    preferred = id_to_pool.get(best_id)

    if preferred is None or preferred == source_pool:
        return False
    if remaining_demand.get(preferred, 0) <= 0:
        return False

    return confidence >= threshold


def _get_constants(domain_config: Any = None):
    """Get pool vocab, component-to-pool, and specificity order from DomainConfig."""
    domain = domain_config if domain_config is not None else _get_domain_config()
    return domain.pool_vocab, domain.component_to_pool, domain.specificity_order


def reassign_supply_map(
    supply_map: Dict[str, list],
    demands: Dict[str, int],
    wrapper: Any = None,
    domain_config: Any = None,
) -> Dict[str, list]:
    """Reassign and reorder supply_map pools using SlotAffinityNet.

    Phase A: Cross-pool routing — move items to the pool matching
             the DSL's demanded slot types.
    Phase B: Within-pool ordering — sort items by affinity score.

    Args:
        supply_map: {pool_key: [items]} — the original supply_map
        demands: {component_name: count} — what the DSL demands
        wrapper: ModuleWrapper instance (for embedder access)
        domain_config: Optional DomainConfig override. When provided,
            uses this config instead of the checkpoint/cache default.
            Enables domain-agnostic slot assignment across gchat, email, etc.

    Returns:
        Reassigned supply_map (new dict, original unchanged).
        On any error, returns the original supply_map.
    """
    import torch

    VOCAB, COMP_TO_POOL, SPEC_ORDER = _get_constants(domain_config)

    model = _load_slot_model()
    if model is None:
        return supply_map

    # Flatten all items from all pools (domain-driven pool keys)
    all_items: List[Tuple[Any, str]] = []  # (item, source_pool)
    for pool_key in VOCAB:
        for item in supply_map.get(pool_key, []):
            all_items.append((item, pool_key))

    if len(all_items) <= 1:
        return supply_map  # Nothing to reassign

    # Extract text from all items
    texts = [_extract_item_text(item) for item, _ in all_items]

    # Skip items with no text
    valid_mask = [bool(t) for t in texts]
    valid_texts = [t for t, v in zip(texts, valid_mask) if v]

    if not valid_texts:
        return supply_map

    # Embed all texts
    embeddings = _embed_texts(valid_texts, wrapper)
    if embeddings is None:
        return supply_map

    # Score all items against all slot types
    with torch.no_grad():
        if _cached_model_type == "unified":
            # UnifiedTRN: use pool_head in build mode
            structural_zeros = torch.zeros(embeddings.shape[0], 17)
            result = model(structural_zeros, embeddings, mode="build")
            scores = result["pool_logits"]  # [N_valid, 5]
        else:
            # SlotAffinityNet: legacy path
            scores = model.score_all_slots(embeddings)  # [N_valid, n_slot_types]

    # Build score map for valid items only
    valid_idx = 0
    item_scores: List[Optional[Any]] = []
    for v in valid_mask:
        if v:
            item_scores.append(scores[valid_idx])  # [n_slot_types]
            valid_idx += 1
        else:
            item_scores.append(None)

    # Phase A: Greedy cross-pool assignment
    # Convert component demands to pool demands
    pool_demands: Dict[str, int] = {}
    for comp_name, count in demands.items():
        pool_key = COMP_TO_POOL.get(comp_name)
        if pool_key:
            pool_demands[pool_key] = pool_demands.get(pool_key, 0) + count

    # Build demand list sorted by specificity
    demand_slots: List[Tuple[str, int]] = []  # (pool_key, count)
    for pool_key in SPEC_ORDER:
        count = pool_demands.get(pool_key, 0)
        if count > 0:
            demand_slots.append((pool_key, count))

    # ── Pin items that already match their demand pool ─────────
    # If supply_count <= demand_count for a pool, ALL items in that pool
    # are pinned (kept in place). Only overflow or items in non-demanded
    # pools are candidates for neural rerouting.
    assigned = [False] * len(all_items)
    new_pools: Dict[str, List[Any]] = {k: [] for k in VOCAB}
    remaining_demand: Dict[str, int] = dict(pool_demands)

    pin_mode, reroute_confidence = _pin_policy()
    released = 0

    for i, (item, source_pool) in enumerate(all_items):
        demand_for_pool = remaining_demand.get(source_pool, 0)
        if demand_for_pool <= 0:
            continue

        # Under "confidence" mode the model gets a say *before* the pin:
        # an item is released for rerouting only when the model confidently
        # prefers a different pool that is itself demanded.
        if pin_mode == "confidence" and _should_release(
            item_scores[i], source_pool, remaining_demand, VOCAB, reroute_confidence
        ):
            released += 1
            continue

        # This item's pool is demanded and not yet full — pin it
        new_pools[source_pool].append(item)
        assigned[i] = True
        remaining_demand[source_pool] = demand_for_pool - 1

    pinned = sum(assigned)
    unpinned = len(all_items) - pinned
    if released:
        logger.info(
            f"🧠 Slot assignment: {released} item(s) released for rerouting by the "
            f"model (pin_mode=confidence, threshold={reroute_confidence:.2f})"
        )
    if unpinned > 0:
        logger.debug(f"🧠 Slot assignment: {pinned} pinned, {unpinned} to reroute")

    # ── Neural reroute only the unpinned items ───────────────
    # Rebuild demand_slots with remaining (unfilled) demand
    demand_slots_remaining: List[Tuple[str, int]] = []
    for pool_key in SPEC_ORDER:
        count = remaining_demand.get(pool_key, 0)
        if count > 0:
            demand_slots_remaining.append((pool_key, count))

    if demand_slots_remaining:
        for target_pool, count in demand_slots_remaining:
            if target_pool not in VOCAB:
                continue
            slot_id = VOCAB[target_pool]

            # Score unassigned items for this slot type
            candidates: List[Tuple[int, float]] = []
            for i, (item, source_pool) in enumerate(all_items):
                if assigned[i] or item_scores[i] is None:
                    continue
                score = item_scores[i][slot_id].item()
                candidates.append((i, score))

            # Pick top-N by score
            candidates.sort(key=lambda x: x[1], reverse=True)
            for idx, _score in candidates[:count]:
                item, source_pool = all_items[idx]
                if source_pool != target_pool:
                    item = _rewrap_item(item, source_pool, target_pool, domain_config)
                new_pools[target_pool].append(item)
                assigned[idx] = True

    # Fallback: unassigned items go back to their original pool
    for i, (item, source_pool) in enumerate(all_items):
        if not assigned[i]:
            new_pools[source_pool].append(item)

    # Phase B: Within-pool ordering by affinity score
    # (Items already in order from greedy assignment, but original-pool
    #  fallback items need sorting too)
    # For now, the greedy assignment order is good enough —
    # highest-affinity items are first in each pool.

    # Preserve any pools we didn't touch (e.g., image_url)
    result = dict(supply_map)
    for pool_key in new_pools:
        result[pool_key] = new_pools[pool_key]

    # Log what changed
    changes = []
    for pool_key in VOCAB:
        old_count = len(supply_map.get(pool_key, []))
        new_count = len(new_pools.get(pool_key, []))
        if old_count != new_count:
            changes.append(f"{pool_key}: {old_count}→{new_count}")
    if changes:
        logger.info(f"🧠 Slot reassignment: {', '.join(changes)}")
    else:
        logger.debug("🧠 Slot assignment: no routing changes needed")

    return result
