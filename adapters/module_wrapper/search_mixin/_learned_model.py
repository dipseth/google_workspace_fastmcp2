"""Learned model loading, checkpoint resolution, and DAG construction."""

from typing import Optional

from config.enhanced_logging import setup_logger

logger = setup_logger()


@classmethod
def _resolve_checkpoint_path(cls, domain: str | None = None) -> str | None:
    """Resolve checkpoint path from cloud artifacts, registry, or env vars.

    Priority:
      0. Model artifact cache (downloaded from cloud via model_artifact_lifespan)
      1. LEARNED_SCORER_REGISTRY JSON (domain->path mapping)
      2. LEARNED_SCORER_CHECKPOINT (single path, any domain)
      3. Default: best_model_unified.pt (UnifiedTRN)
      4. Fallback: best_model_mw.pt (DualHeadScorerMW)
    """
    import json as _json
    import os

    # Priority 0: Cloud-downloaded artifacts (from model_artifact_lifespan)
    try:
        from lifespans import get_model_artifact_paths

        artifact_paths = get_model_artifact_paths()
        if artifact_paths:
            # Try domain-specific artifact first
            if domain and domain in artifact_paths:
                path = artifact_paths[domain]
                if os.path.exists(path):
                    logger.debug(f"Using cloud artifact for domain={domain}: {path}")
                    return path
            # Try 'default' key (single-URI mode)
            if "default" in artifact_paths:
                path = artifact_paths["default"]
                if os.path.exists(path):
                    logger.debug(f"Using cloud artifact (default): {path}")
                    return path
            # Try first available
            for d, path in artifact_paths.items():
                if os.path.exists(path):
                    logger.debug(f"Using cloud artifact (domain={d}): {path}")
                    return path
    except ImportError:
        pass  # lifespans not available (e.g., during testing)

    # Priority 1: LEARNED_SCORER_REGISTRY JSON
    registry_json = os.environ.get("LEARNED_SCORER_REGISTRY")
    if registry_json:
        try:
            registry = _json.loads(registry_json)
            if domain and domain in registry:
                path = registry[domain]
                if os.path.exists(path):
                    return path
            # Fallback to first available in registry
            for d, path in registry.items():
                if os.path.exists(path):
                    return path
        except _json.JSONDecodeError:
            logger.warning("LEARNED_SCORER_REGISTRY is not valid JSON")

    # Priority 2: Single checkpoint path
    checkpoint_path = os.environ.get("LEARNED_SCORER_CHECKPOINT")
    if checkpoint_path and os.path.exists(checkpoint_path):
        return checkpoint_path

    # Priority 3-4: Default file paths — prefer UnifiedTRN, fall back to DualHead
    from pathlib import Path

    base_dirs = [
        Path(__file__).parent.parent.parent.parent,
        Path.cwd(),
    ]
    checkpoint_names = [
        "best_model_unified.pt",  # UnifiedTRN (preferred)
        "best_model_mw.pt",  # DualHeadScorerMW (fallback)
    ]
    for name in checkpoint_names:
        for base in base_dirs:
            p = base / "research" / "trm" / "h2" / "checkpoints" / name
            if p.exists():
                return str(p)

    return None


@classmethod
def _load_learned_model(cls, domain: str | None = None):
    """Load the trained scorer model (cached at class level).

    Supports three architectures (auto-detected from checkpoint):
      - UnifiedTRN: structural(17D) + content(384D) → form/content/halt/pool heads
      - DualHeadScorerMW: features(17D) → form_score + content_score
      - SimilarityScorerMW: features(9D) → single score

    Args:
        domain: Optional domain ID for registry-based checkpoint lookup.
    """
    if cls._learned_model is not None:
        return cls._learned_model

    try:
        import torch
        import torch.nn as nn
    except ImportError:
        logger.warning("torch not installed -- learned scorer unavailable")
        return None

    class _ScorerMLP(nn.Module):
        """Single-head MLP (SimilarityScorerMW)."""

        def __init__(self, input_dim=9, hidden_dim=32, dropout=0.15):
            super().__init__()
            self.mlp = nn.Sequential(
                nn.Linear(input_dim, hidden_dim),
                nn.SiLU(),
                nn.Dropout(dropout),
                nn.Linear(hidden_dim, hidden_dim),
                nn.SiLU(),
                nn.Dropout(dropout),
                nn.Linear(hidden_dim, 1),
            )

        def forward(self, x):
            return self.mlp(x)

    class _DualHeadMLP(nn.Module):
        """Dual-head MLP (DualHeadScorerMW)."""

        def __init__(
            self,
            input_dim=17,
            hidden_dim=48,
            head_dim=24,
            dropout=0.15,
        ):
            super().__init__()
            self.backbone = nn.Sequential(
                nn.Linear(input_dim, hidden_dim),
                nn.SiLU(),
                nn.Dropout(dropout),
                nn.Linear(hidden_dim, hidden_dim),
                nn.SiLU(),
                nn.Dropout(dropout),
            )
            self.form_head = nn.Sequential(
                nn.Linear(hidden_dim, head_dim),
                nn.SiLU(),
                nn.Linear(head_dim, 1),
            )
            self.content_head = nn.Sequential(
                nn.Linear(hidden_dim, head_dim),
                nn.SiLU(),
                nn.Linear(head_dim, 1),
            )

        def forward(self, x):
            shared = self.backbone(x)
            return self.form_head(shared), self.content_head(shared)

    # Resolve checkpoint path (supports registry, env var, or default)
    import os

    checkpoint_path = cls._resolve_checkpoint_path(domain=domain)

    if not checkpoint_path:
        logger.warning(
            "Learned scorer checkpoint not found. "
            "Set LEARNED_SCORER_CHECKPOINT or LEARNED_SCORER_REGISTRY."
        )
        return None

    try:
        ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        model_type = ckpt.get("model_type", "similarity_mw")
        cls._learned_feature_version = ckpt.get(
            "feature_version", 5 if model_type == "unified" else 1
        )
        cls._learned_model_domain = ckpt.get("domain_id")

        if model_type in ("unified", "unified_trn"):
            # UnifiedTRN: dual-encoder with 4 task heads
            from research.trm.h2.unified_trn import UnifiedTRN

            model = UnifiedTRN(
                structural_dim=ckpt.get("structural_dim", 17),
                content_dim=ckpt.get("content_dim", 384),
                hidden=ckpt.get("hidden", 64),
                n_pools=ckpt.get("n_pools", 5),
                dropout=0.0,  # no dropout at inference
            )
            cls._learned_model_type = "unified"

        elif model_type == "dual_head":
            hidden_dim = ckpt.get("hidden_dim", 48)
            head_dim = ckpt.get("head_dim", 24)
            model = _DualHeadMLP(
                input_dim=ckpt.get("input_dim", 17),
                hidden_dim=hidden_dim,
                head_dim=head_dim,
                dropout=ckpt.get("dropout", 0.15),
            )
            cls._learned_model_type = "dual_head"

        else:
            model = _ScorerMLP(
                input_dim=ckpt.get("input_dim", 9),
                hidden_dim=ckpt.get("hidden_dim", 32),
                dropout=ckpt.get("dropout", 0.15),
            )
            cls._learned_model_type = "single"

        model.load_state_dict(ckpt["model_state_dict"])
        model.eval()
        cls._learned_model = model
        n_params = sum(p.numel() for p in model.parameters())
        domain_str = cls._learned_model_domain or "unknown"
        logger.info(
            f"Loaded {cls._learned_model_type} scorer "
            f"from {checkpoint_path} "
            f"(domain={domain_str}, params={n_params}, "
            f"V{cls._learned_feature_version})"
        )
        return model
    except Exception as e:
        logger.error(f"Failed to load learned scorer: {e}")
        return None


def _ensure_learned_dag(self):
    """Lazily load DAG for structural feature computation (V2 only)."""
    cls = type(self)
    if cls._learned_dag_loaded:
        return
    try:
        # Use self (the wrapper instance) directly -- it has the graph
        # Force graph build if needed
        graph = (
            self.get_relationship_graph()
            if hasattr(self, "get_relationship_graph")
            else None
        )
        all_names = (
            list(self._name_to_idx.keys()) if hasattr(self, "_name_to_idx") else []
        )

        if not all_names:
            # No graph data available -- structural features will be zero.
            # This is acceptable; the model handles missing structural features
            # gracefully via the similarity-only features (V3 features 0-8).
            logger.info("No DAG components found -- structural features will be zero")
            source = self
        else:
            source = self

        for comp_name in all_names:
            cls._learned_dag_children[comp_name] = set(source.get_children(comp_name))
            cls._learned_dag_parents[comp_name] = set(source.get_parents(comp_name))

        # BFS depth
        roots = [n for n in all_names if not cls._learned_dag_parents.get(n)]
        if not roots:
            roots = [
                n for n in all_names if len(cls._learned_dag_parents.get(n, set())) <= 1
            ]
        visited = {}
        queue = [(r, 0) for r in roots]
        while queue:
            node, depth = queue.pop(0)
            if node in visited:
                continue
            visited[node] = depth
            for child in cls._learned_dag_children.get(node, set()):
                queue.append((child, depth + 1))
        cls._learned_dag_depth = visited
        cls._learned_dag_loaded = True
        logger.info(
            f"Loaded DAG for learned scorer: {len(all_names)} components, max_depth={max(visited.values()) if visited else 0}"
        )
    except Exception as e:
        logger.warning(f"Could not load DAG for structural features: {e}")
        cls._learned_dag_loaded = True  # prevent retries


def _collection_has_content_vector(self) -> bool:
    """Check if collection schema has the 'content' named vector.

    Cached after first check to avoid repeated collection_info calls.
    Prevents errors when running against old 3-vector collections.
    """
    if self.__class__._has_content_vector is not None:
        return self.__class__._has_content_vector
    try:
        info = self.client.get_collection(self.collection_name)
        vectors_config = info.config.params.vectors
        if isinstance(vectors_config, dict) and "content" in vectors_config:
            self.__class__._has_content_vector = True
        else:
            self.__class__._has_content_vector = False
    except Exception:
        self.__class__._has_content_vector = False
    return self.__class__._has_content_vector
