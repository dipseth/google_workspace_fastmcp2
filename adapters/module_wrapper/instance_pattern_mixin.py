"""
Instance Pattern Mixin for ModuleWrapper

Provides generic instance pattern storage, variation generation, and caching
for any module wrapper. This is module-agnostic - works with card_framework,
json, or any other wrapped module.

Instance patterns represent successful usages of module components with
specific parameter values. They can be stored, varied, and cached for
fast retrieval.

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │              InstancePatternMixin                            │
    │                                                              │
    │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
    │  │ store_pattern│ →  │ generate_    │ →  │ cache_pattern│   │
    │  │              │    │ variations   │    │              │   │
    │  └──────────────┘    └──────────────┘    └──────────────┘   │
    │         ↓                   ↓                   ↓            │
    │  ┌──────────────────────────────────────────────────────┐   │
    │  │                   Qdrant / Cache                      │   │
    │  │  • instance_pattern points (Qdrant)                   │   │
    │  │  • variation families (L1/L2 cache)                   │   │
    │  │  • component class references                         │   │
    │  └──────────────────────────────────────────────────────┘   │
    └─────────────────────────────────────────────────────────────┘

Expects from other mixins:
    - QdrantMixin: client, collection_name
    - EmbeddingMixin: embedder, embed methods
    - SymbolsMixin: build_dsl_from_paths, symbol_mapping
    - CacheMixin: cache_pattern, get_cached_entry
    - RelationshipsMixin: relationships (for variation generation)
"""

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type

from adapters.module_wrapper.types import (
    CacheKey,
    ComponentPaths,
    DSLNotation,
    Payload,
    RelationshipDict,
    TimestampedMixin,
)

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class InstancePattern:
    """
    Represents a stored instance pattern.

    An instance pattern captures a successful usage of module components
    with specific parameter values.
    """

    pattern_id: str
    component_paths: ComponentPaths
    instance_params: Payload
    description: str = ""
    dsl_notation: Optional[DSLNotation] = None
    feedback: Optional[str] = None  # "positive", "negative", None
    metadata: Payload = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_payload(self) -> Payload:
        """Convert to Qdrant payload format."""
        return {
            "name": f"instance_pattern_{self.pattern_id[:8]}",
            "type": "instance_pattern",
            "pattern_id": self.pattern_id,
            "component_paths": self.component_paths,
            "instance_params": self.instance_params,
            "description": self.description,
            "dsl_notation": self.dsl_notation,
            "feedback": self.feedback,
            "timestamp": datetime.fromtimestamp(self.created_at).isoformat(),
            **self.metadata,
        }


@dataclass
class PatternVariation:
    """A single variation of an instance pattern."""

    variation_id: str
    variation_type: str  # "structure", "parameter", "combined"
    component_paths: ComponentPaths
    instance_params: Payload
    parent_id: str
    dsl_notation: Optional[DSLNotation] = None
    cache_key: Optional[CacheKey] = None
    created_at: float = field(default_factory=time.time)


@dataclass
class VariationFamily:
    """Collection of variations derived from a source pattern."""

    parent_id: str
    source_pattern: InstancePattern
    variations: List[PatternVariation] = field(default_factory=list)
    cache_keys: List[CacheKey] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.variations)


# =============================================================================
# STRUCTURE VARIATOR (Generic)
# =============================================================================


class StructureVariator:
    """
    Generates structural variations using component relationships.

    Works with any module wrapper that has a relationships dict.
    """

    def __init__(self, relationships: RelationshipDict):
        """
        Args:
            relationships: Dict mapping parent component → list of valid children
        """
        self.relationships: RelationshipDict = relationships
        self._sibling_cache: Dict[str, List[str]] = {}

    def get_valid_children(self, component_name: str) -> List[str]:
        """Get valid children for a component."""
        return self.relationships.get(component_name, [])

    def get_siblings(self, component_name: str) -> List[str]:
        """Get sibling components (components with same parent)."""
        if component_name in self._sibling_cache:
            return self._sibling_cache[component_name]

        siblings = set()
        for parent, children in self.relationships.items():
            if component_name in children:
                siblings.update(children)

        siblings.discard(component_name)
        result = list(siblings)
        self._sibling_cache[component_name] = result
        return result

    def swap_sibling(
        self,
        component_paths: ComponentPaths,
        target_index: Optional[int] = None,
    ) -> Optional[ComponentPaths]:
        """Swap a component with a valid sibling."""
        import random

        if not component_paths:
            return None

        names = [p.split(".")[-1] if "." in p else p for p in component_paths]

        if target_index is None:
            target_index = random.randint(0, len(names) - 1)

        target = names[target_index]
        siblings = self.get_siblings(target)

        if not siblings:
            return None

        replacement = random.choice(siblings)
        new_names = names.copy()
        new_names[target_index] = replacement

        return new_names

    def add_child(
        self,
        component_paths: ComponentPaths,
        parent_name: Optional[str] = None,
    ) -> Optional[ComponentPaths]:
        """Add a valid child component."""
        import random

        names = [p.split(".")[-1] if "." in p else p for p in component_paths]

        if not names:
            return None

        if parent_name is None:
            parent_name = random.choice(names)

        valid_children = self.get_valid_children(parent_name)
        if not valid_children:
            return None

        existing = set(names)
        available = [c for c in valid_children if c not in existing]

        if not available:
            return None

        new_child = random.choice(available)
        new_names = names.copy()

        try:
            parent_idx = names.index(parent_name)
            new_names.insert(parent_idx + 1, new_child)
        except ValueError:
            new_names.append(new_child)

        return new_names

    def remove_optional(
        self,
        component_paths: ComponentPaths,
        required: Optional[Set[str]] = None,
    ) -> Optional[ComponentPaths]:
        """Remove a non-required component."""
        import random

        if len(component_paths) <= 1:
            return None

        names = [p.split(".")[-1] if "." in p else p for p in component_paths]
        required = required or set()

        removable = [n for n in names if n not in required]

        if not removable:
            return None

        to_remove = random.choice(removable)
        new_names = [n for n in names if n != to_remove]

        return new_names if new_names else None

    def expand_repeated(
        self,
        component_paths: ComponentPaths,
        repeatable: Optional[List[str]] = None,
        max_expand: int = 2,
    ) -> Optional[ComponentPaths]:
        """Add more instances of a repeatable component."""
        import random

        names = [p.split(".")[-1] if "." in p else p for p in component_paths]
        repeatable = repeatable or []

        candidates = [n for n in names if n in repeatable]

        if not candidates:
            return None

        to_repeat = random.choice(candidates)
        count = random.randint(1, max_expand)

        new_names = names.copy()
        try:
            idx = names.index(to_repeat)
            for _ in range(count):
                new_names.insert(idx + 1, to_repeat)
        except ValueError:
            pass

        return new_names

    def generate_variations(
        self,
        component_paths: ComponentPaths,
        num_variations: int = 3,
        required_components: Optional[Set[str]] = None,
        repeatable_components: Optional[List[str]] = None,
    ) -> List[ComponentPaths]:
        """Generate multiple structural variations."""
        import random

        variations = []
        strategies = [
            lambda p: self.swap_sibling(p),
            lambda p: self.add_child(p),
            lambda p: self.remove_optional(p, required_components),
            lambda p: self.expand_repeated(p, repeatable_components),
        ]

        attempts = 0
        max_attempts = num_variations * 4

        while len(variations) < num_variations and attempts < max_attempts:
            attempts += 1
            strategy = random.choice(strategies)

            try:
                result = strategy(component_paths)
                if result and result not in variations and result != component_paths:
                    variations.append(result)
            except Exception as e:
                logger.debug(f"Variation strategy failed: {e}")

        return variations


# =============================================================================
# PARAMETER VARIATOR (Generic)
# =============================================================================


class ParameterVariator:
    """
    Generates parameter variations for instance patterns.

    Works with any parameter dictionary.
    """

    def __init__(self, custom_variators: Optional[Dict[str, Callable]] = None):
        """
        Args:
            custom_variators: Dict mapping param name patterns → variation functions
        """
        self.custom_variators = custom_variators or {}

    def vary_string(self, value: str) -> str:
        """Generate a string variation."""
        import random

        variations = [
            lambda v: v.upper(),
            lambda v: v.lower(),
            lambda v: v.title(),
            lambda v: f"[{v}]",
            lambda v: f"• {v}",
            lambda v: v[: len(v) // 2] + "..." if len(v) > 10 else v,
        ]

        return random.choice(variations)(value)

    def vary_number(self, value: float, variance: float = 0.2) -> float:
        """Generate a numeric variation."""
        import random

        factor = random.uniform(1 - variance, 1 + variance)
        return value * factor

    def vary_list(self, value: list, max_items: int = 10) -> list:
        """Generate a list variation."""
        import random

        if not value:
            return value

        variations = [
            lambda v: random.sample(v, len(v)),  # Shuffle
            lambda v: v[: max(1, len(v) - 1)],  # Truncate
            lambda v: [v[0]] + v if v else v,  # Duplicate first
            lambda v: list(reversed(v)),  # Reverse
        ]

        return random.choice(variations)(value)[:max_items]

    def vary_dict(self, value: dict) -> dict:
        """Recursively vary a dictionary."""
        return self.vary_params(value)

    def vary_params(
        self,
        params: Payload,
        vary_keys: Optional[List[str]] = None,
        max_keys_to_vary: int = 3,
    ) -> Payload:
        """
        Generate a variation of parameters.

        Args:
            params: Source parameters
            vary_keys: Specific keys to vary (random selection if None)
            max_keys_to_vary: Max number of keys to vary

        Returns:
            New params dict with variations
        """
        import random

        new_params = params.copy()
        keys_to_vary = vary_keys or list(params.keys())

        num_to_vary = min(len(keys_to_vary), random.randint(1, max_keys_to_vary))
        selected_keys = random.sample(keys_to_vary, num_to_vary)

        for key in selected_keys:
            value = params.get(key)

            if value is None:
                continue

            # Check for custom variator
            for pattern, variator in self.custom_variators.items():
                if pattern in key.lower():
                    try:
                        new_params[key] = variator(value)
                        break
                    except Exception:
                        pass
            else:
                # Use default variators
                if isinstance(value, str):
                    new_params[key] = self.vary_string(value)
                elif isinstance(value, list):
                    new_params[key] = self.vary_list(value)
                elif isinstance(value, dict):
                    new_params[key] = self.vary_dict(value)
                elif isinstance(value, bool):
                    if random.random() < 0.3:
                        new_params[key] = not value
                elif isinstance(value, (int, float)):
                    new_params[key] = type(value)(self.vary_number(float(value)))

        return new_params

    def generate_variations(
        self,
        params: Payload,
        num_variations: int = 3,
    ) -> List[Payload]:
        """Generate multiple parameter variations."""
        variations = []
        seen_hashes = set()

        attempts = 0
        max_attempts = num_variations * 3

        while len(variations) < num_variations and attempts < max_attempts:
            attempts += 1

            varied = self.vary_params(params)
            param_hash = hashlib.md5(str(sorted(varied.items())).encode()).hexdigest()

            if param_hash not in seen_hashes:
                seen_hashes.add(param_hash)
                variations.append(varied)

        return variations


# =============================================================================
# INSTANCE PATTERN MIXIN
# =============================================================================


class InstancePatternMixin:
    """
    Mixin providing instance pattern management for ModuleWrapper.

    Expects the following attributes on self:
    - client: Qdrant client (from QdrantMixin)
    - collection_name: str (from QdrantMixin)
    - relationships: Dict[str, List[str]] (from RelationshipsMixin)
    - symbol_mapping: Dict[str, str] (from SymbolsMixin)
    - build_dsl_from_paths: Callable (from SymbolsMixin)
    - _get_component_cache: Callable (from CacheMixin)
    - get_component_by_path: Callable (from ModuleWrapperBase)
    """

    # Configuration
    _pattern_config = {
        "max_patterns": 500,
        "default_structure_variations": 3,
        "default_param_variations": 2,
        "required_components": set(),  # Components that can't be removed
        "repeatable_components": [],  # Components that can be duplicated
    }

    def configure_patterns(
        self,
        max_patterns: Optional[int] = None,
        default_structure_variations: Optional[int] = None,
        default_param_variations: Optional[int] = None,
        required_components: Optional[Set[str]] = None,
        repeatable_components: Optional[List[str]] = None,
    ) -> None:
        """
        Configure instance pattern behavior.

        Args:
            max_patterns: Maximum patterns to keep in storage
            default_structure_variations: Default number of structure variations
            default_param_variations: Default number of parameter variations
            required_components: Components that can't be removed in variations
            repeatable_components: Components that can be duplicated in variations
        """
        if max_patterns is not None:
            self._pattern_config["max_patterns"] = max_patterns
        if default_structure_variations is not None:
            self._pattern_config["default_structure_variations"] = (
                default_structure_variations
            )
        if default_param_variations is not None:
            self._pattern_config["default_param_variations"] = default_param_variations
        if required_components is not None:
            self._pattern_config["required_components"] = required_components
        if repeatable_components is not None:
            self._pattern_config["repeatable_components"] = repeatable_components

    def _get_structure_variator(self) -> StructureVariator:
        """Get or create structure variator."""
        if not hasattr(self, "_structure_variator"):
            relationships = getattr(self, "relationships", {})
            self._structure_variator = StructureVariator(relationships)
        return self._structure_variator

    def _get_param_variator(self) -> ParameterVariator:
        """Get or create parameter variator."""
        if not hasattr(self, "_param_variator"):
            self._param_variator = ParameterVariator()
        return self._param_variator

    def _get_variation_families(self) -> Dict[str, VariationFamily]:
        """Get variation families registry."""
        if not hasattr(self, "_variation_families"):
            self._variation_families = {}
        return self._variation_families

    def _generate_pattern_id(self, pattern: InstancePattern) -> str:
        """Generate a unique pattern ID."""
        content = (
            f"{pattern.component_paths}{pattern.instance_params}{pattern.description}"
        )
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _build_pattern_dsl(
        self, component_paths: ComponentPaths
    ) -> Optional[DSLNotation]:
        """Build DSL notation for a pattern."""
        if hasattr(self, "build_dsl_from_paths"):
            try:
                return self.build_dsl_from_paths(component_paths)
            except Exception:
                pass
        return None

    def store_instance_pattern(
        self,
        component_paths: ComponentPaths,
        instance_params: Payload,
        description: str = "",
        feedback: Optional[str] = None,
        metadata: Optional[Payload] = None,
        generate_variations: bool = True,
        num_structure_variations: Optional[int] = None,
        num_param_variations: Optional[int] = None,
        cache_pattern: bool = True,
    ) -> Optional[str]:
        """
        Store an instance pattern.

        Args:
            component_paths: List of component paths/names used
            instance_params: Parameters used to instantiate components
            description: Human-readable description
            feedback: Feedback status ("positive", "negative", None)
            metadata: Additional metadata to store
            generate_variations: Whether to generate and cache variations
            num_structure_variations: Override for structure variation count
            num_param_variations: Override for parameter variation count
            cache_pattern: Whether to cache the pattern

        Returns:
            Pattern ID if stored successfully, None on error
        """
        # Build pattern
        pattern = InstancePattern(
            pattern_id=str(uuid.uuid4()),
            component_paths=component_paths,
            instance_params=instance_params,
            description=description,
            dsl_notation=self._build_pattern_dsl(component_paths),
            feedback=feedback,
            metadata=metadata or {},
        )

        # Store to Qdrant if available
        stored = self._store_pattern_to_qdrant(pattern)

        # Cache the pattern
        if cache_pattern and hasattr(self, "cache_pattern"):
            try:
                self.cache_pattern(
                    key=pattern.pattern_id,
                    component_paths=component_paths,
                    instance_params=instance_params,
                    dsl_notation=pattern.dsl_notation,
                    structure_description=description,
                )
            except Exception as e:
                logger.warning(f"Failed to cache pattern: {e}")

        # Generate variations if requested (skip only for explicitly negative feedback)
        if generate_variations and feedback != "negative":
            self.generate_pattern_variations(
                pattern=pattern,
                num_structure_variations=num_structure_variations,
                num_param_variations=num_param_variations,
                cache_variations=True,
            )

        return pattern.pattern_id if stored else None

    def _store_pattern_to_qdrant(self, pattern: InstancePattern) -> bool:
        """Store pattern to Qdrant collection."""
        client = getattr(self, "client", None)
        collection_name = getattr(self, "collection_name", None)

        if not client or not collection_name:
            logger.debug("Qdrant not available for pattern storage")
            return True  # Still return True - pattern exists in memory

        try:
            # Get embedder
            embedder = getattr(self, "embedder", None)
            if not embedder:
                logger.warning("No embedder available for pattern storage")
                return False

            # Build embedding text
            embedding_text = self._build_pattern_embedding_text(pattern)

            # Generate embedding
            try:
                vectors_raw = list(embedder.embed([embedding_text]))[0]
                vectors = vectors_raw.tolist()
            except Exception as e:
                logger.warning(f"Failed to embed pattern: {e}")
                return False

            # Create point
            from qdrant_client.models import PointStruct

            point = PointStruct(
                id=pattern.pattern_id,
                vector=vectors,
                payload=pattern.to_payload(),
            )

            # Upsert
            client.upsert(
                collection_name=collection_name,
                points=[point],
            )

            logger.info(f"Stored instance pattern: {pattern.pattern_id[:8]}...")
            return True

        except Exception as e:
            logger.error(f"Failed to store pattern to Qdrant: {e}")
            return False

    def _build_pattern_embedding_text(self, pattern: InstancePattern) -> str:
        """Build text for pattern embedding."""
        parts = []

        # Add DSL
        if pattern.dsl_notation:
            parts.append(pattern.dsl_notation)

        # Add component names
        names = [p.split(".")[-1] if "." in p else p for p in pattern.component_paths]
        parts.append(" ".join(names))

        # Add description
        if pattern.description:
            parts.append(pattern.description[:100])

        # Add key param values
        for key, value in pattern.instance_params.items():
            if isinstance(value, str) and len(value) < 50:
                parts.append(f"{key}={value}")

        return " | ".join(parts)

    def generate_pattern_variations(
        self,
        pattern: InstancePattern,
        num_structure_variations: Optional[int] = None,
        num_param_variations: Optional[int] = None,
        cache_variations: bool = True,
    ) -> VariationFamily:
        """
        Generate variations of an instance pattern.

        Uses the relationship DAG for structural variations and
        parameter variators for value variations.

        Args:
            pattern: Source pattern
            num_structure_variations: Number of structural variations
            num_param_variations: Number of parameter variations per structure
            cache_variations: Whether to cache generated variations

        Returns:
            VariationFamily containing all variations
        """
        config = self._pattern_config
        num_struct = num_structure_variations or config["default_structure_variations"]
        num_param = num_param_variations or config["default_param_variations"]

        # Create family
        family = VariationFamily(
            parent_id=pattern.pattern_id,
            source_pattern=pattern,
        )

        # Get variators
        struct_variator = self._get_structure_variator()
        param_variator = self._get_param_variator()

        # Generate structural variations
        struct_variations = struct_variator.generate_variations(
            pattern.component_paths,
            num_struct,
            config["required_components"],
            config["repeatable_components"],
        )

        # Include original structure
        all_structures = [pattern.component_paths] + struct_variations

        # For each structure, generate parameter variations
        variation_idx = 0
        for struct_idx, struct_paths in enumerate(all_structures):
            # Generate param variations
            if struct_idx == 0:
                param_sets = [
                    pattern.instance_params
                ] + param_variator.generate_variations(
                    pattern.instance_params, num_param - 1
                )
            else:
                param_sets = param_variator.generate_variations(
                    pattern.instance_params, num_param
                )

            for param_idx, params in enumerate(param_sets):
                var_type = (
                    "original"
                    if struct_idx == 0 and param_idx == 0
                    else "structure" if struct_idx > 0 else "parameter"
                )

                variation = PatternVariation(
                    variation_id=f"{pattern.pattern_id}:v{variation_idx}",
                    variation_type=var_type,
                    component_paths=struct_paths,
                    instance_params=params,
                    parent_id=pattern.pattern_id,
                    dsl_notation=self._build_pattern_dsl(struct_paths),
                    cache_key=f"{pattern.pattern_id}:v{variation_idx}",
                )

                family.variations.append(variation)
                family.cache_keys.append(variation.cache_key)

                # Cache the variation
                if cache_variations:
                    self._cache_variation(variation)

                variation_idx += 1

        # Store family
        self._get_variation_families()[pattern.pattern_id] = family

        logger.info(
            f"Generated {family.size} variations for {pattern.pattern_id[:8]}... "
            f"({num_struct} structures × {num_param} params)"
        )

        return family

    def _cache_variation(self, variation: PatternVariation) -> bool:
        """Cache a single variation."""
        if not hasattr(self, "cache_pattern"):
            return False

        try:
            self.cache_pattern(
                key=variation.cache_key,
                component_paths=variation.component_paths,
                instance_params=variation.instance_params,
                dsl_notation=variation.dsl_notation,
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to cache variation: {e}")
            return False

    def get_variation_family(self, pattern_id: str) -> Optional[VariationFamily]:
        """Get a variation family by parent pattern ID."""
        return self._get_variation_families().get(pattern_id)

    def get_random_variation(
        self,
        pattern_id: str,
        variation_type: Optional[str] = None,
    ) -> Optional[PatternVariation]:
        """
        Get a random variation from a family.

        Args:
            pattern_id: Parent pattern ID
            variation_type: Optional filter ("structure", "parameter", "original")

        Returns:
            Random variation or None
        """
        import random

        family = self.get_variation_family(pattern_id)
        if not family:
            return None

        if variation_type:
            matching = [
                v for v in family.variations if v.variation_type == variation_type
            ]
            return random.choice(matching) if matching else None

        return random.choice(family.variations) if family.variations else None

    def get_cached_variation(
        self,
        pattern_id: str,
        variation_type: Optional[str] = None,
    ) -> Optional[Payload]:
        """
        Get a cached variation with hydrated component classes.

        Args:
            pattern_id: Parent pattern ID
            variation_type: Optional type filter

        Returns:
            Dict with component_classes or None
        """
        variation = self.get_random_variation(pattern_id, variation_type)
        if not variation:
            return None

        # Get from cache
        if hasattr(self, "get_cached_entry"):
            entry = self.get_cached_entry(
                variation.cache_key, variation.component_paths
            )
            if entry:
                return {
                    "key": entry.key,
                    "component_paths": entry.component_paths,
                    "instance_params": entry.instance_params,
                    "dsl_notation": entry.dsl_notation,
                    "component_classes": entry.component_classes,
                    "variation_type": variation.variation_type,
                    "_from_cache": True,
                }

        return None

    @property
    def pattern_stats(self) -> Payload:
        """Get instance pattern statistics."""
        families = self._get_variation_families()
        total_variations = sum(f.size for f in families.values())

        return {
            "num_families": len(families),
            "total_variations": total_variations,
            "avg_variations_per_family": (
                total_variations / len(families) if families else 0
            ),
            "config": self._pattern_config,
        }
