"""
Variation Generator - Thin Wrapper for Backwards Compatibility

This module provides backwards-compatible convenience functions for variation
generation. The actual implementation is in instance_pattern_mixin.py.

For new code, prefer using the ModuleWrapper methods directly:
    wrapper.store_instance_pattern(..., generate_variations=True)
    wrapper.generate_pattern_variations(pattern)
    wrapper.get_cached_variation(pattern_id)

This module is maintained for backwards compatibility with existing code
that uses VariationGenerator and related classes directly.
"""

import logging
from typing import Any, Dict, List, Optional

from adapters.module_wrapper.types import (
    ComponentPaths,
    DSLNotation,
    Payload,
    RelationshipDict,
)

logger = logging.getLogger(__name__)

# Re-export from instance_pattern_mixin for backwards compatibility
from adapters.module_wrapper.instance_pattern_mixin import (
    InstancePattern,
    ParameterVariator,
    StructureVariator,
    VariationFamily,
)
from adapters.module_wrapper.instance_pattern_mixin import (
    PatternVariation as Variation,  # Alias for backwards compatibility
)


class VariationGenerator:
    """
    Backwards-compatible variation generator.

    Wraps the generic InstancePatternMixin functionality for use with
    any ModuleWrapper instance.

    For new code, prefer using wrapper methods directly:
        wrapper.generate_pattern_variations(pattern)
        wrapper.get_cached_variation(pattern_id)
    """

    def __init__(self, wrapper=None):
        """
        Initialize the variation generator.

        Args:
            wrapper: ModuleWrapper instance (optional, will be fetched lazily)
        """
        self.wrapper = wrapper
        self._initialized = False

    def _ensure_wrapper(self):
        """Ensure wrapper is available."""
        if self.wrapper is None:
            try:
                from gchat.card_framework_wrapper import get_card_framework_wrapper
                self.wrapper = get_card_framework_wrapper()
            except ImportError:
                logger.warning("Could not get card_framework_wrapper")

        return self.wrapper

    def generate_variations(
        self,
        pattern: Payload,
        num_structure_variations: int = 3,
        num_param_variations: int = 2,
        cache_variations: bool = True,
    ) -> Optional[VariationFamily]:
        """
        Generate variations of a pattern.

        Delegates to the wrapper's InstancePatternMixin methods.

        Args:
            pattern: Pattern dict with component_paths and instance_params
            num_structure_variations: Number of structural variations
            num_param_variations: Number of parameter variations per structure
            cache_variations: Whether to cache variations

        Returns:
            VariationFamily or None
        """
        wrapper = self._ensure_wrapper()
        if not wrapper:
            logger.warning("No wrapper available for variation generation")
            return None

        # Convert dict pattern to InstancePattern
        component_paths = pattern.get("component_paths") or pattern.get("parent_paths", [])
        instance_params = pattern.get("instance_params", {})
        description = pattern.get("card_description", "")
        pattern_id = pattern.get("card_id") or pattern.get("id", "")

        instance_pattern = InstancePattern(
            pattern_id=pattern_id,
            component_paths=component_paths,
            instance_params=instance_params,
            description=description,
            dsl_notation=pattern.get("dsl_notation"),
            feedback=pattern.get("feedback") or pattern.get("content_feedback"),
        )

        # Delegate to wrapper's mixin method
        if hasattr(wrapper, "generate_pattern_variations"):
            return wrapper.generate_pattern_variations(
                pattern=instance_pattern,
                num_structure_variations=num_structure_variations,
                num_param_variations=num_param_variations,
                cache_variations=cache_variations,
            )

        # Fallback: use structure/param variators directly
        struct_variator = StructureVariator(getattr(wrapper, "relationships", {}))
        param_variator = ParameterVariator()

        family = VariationFamily(
            parent_id=instance_pattern.pattern_id,
            source_pattern=instance_pattern,
        )

        # Generate structure variations
        struct_variations = struct_variator.generate_variations(
            component_paths,
            num_structure_variations,
        )

        all_structures = [component_paths] + struct_variations

        variation_idx = 0
        for struct_idx, struct_paths in enumerate(all_structures):
            if struct_idx == 0:
                param_sets = [instance_params] + param_variator.generate_variations(
                    instance_params, num_param_variations - 1
                )
            else:
                param_sets = param_variator.generate_variations(
                    instance_params, num_param_variations
                )

            for param_idx, params in enumerate(param_sets):
                var_type = (
                    "original" if struct_idx == 0 and param_idx == 0 else
                    "structure" if struct_idx > 0 else "parameter"
                )

                variation = Variation(
                    variation_id=f"{instance_pattern.pattern_id}:v{variation_idx}",
                    variation_type=var_type,
                    component_paths=struct_paths,
                    instance_params=params,
                    parent_id=instance_pattern.pattern_id,
                    cache_key=f"{instance_pattern.pattern_id}:v{variation_idx}",
                )

                family.variations.append(variation)
                family.cache_keys.append(variation.cache_key)
                variation_idx += 1

        return family

    def get_family(self, parent_key: str) -> Optional[VariationFamily]:
        """Get a variation family by parent key."""
        wrapper = self._ensure_wrapper()
        if wrapper and hasattr(wrapper, "get_variation_family"):
            return wrapper.get_variation_family(parent_key)
        return None

    def get_random_variation(self, parent_key: str) -> Optional[Variation]:
        """Get a random variation from a family."""
        wrapper = self._ensure_wrapper()
        if wrapper and hasattr(wrapper, "get_random_variation"):
            return wrapper.get_random_variation(parent_key)
        return None

    def get_variation_by_type(
        self,
        parent_key: str,
        variation_type: str,
    ) -> Optional[Variation]:
        """Get a variation of specific type from a family."""
        wrapper = self._ensure_wrapper()
        if wrapper and hasattr(wrapper, "get_random_variation"):
            return wrapper.get_random_variation(parent_key, variation_type)
        return None

    def list_families(self) -> List[str]:
        """List all tracked family keys."""
        wrapper = self._ensure_wrapper()
        if wrapper and hasattr(wrapper, "_get_variation_families"):
            return list(wrapper._get_variation_families().keys())
        return []

    @property
    def stats(self) -> Payload:
        """Get generator statistics."""
        wrapper = self._ensure_wrapper()
        if wrapper and hasattr(wrapper, "pattern_stats"):
            return wrapper.pattern_stats
        return {
            "num_families": 0,
            "total_variations": 0,
            "avg_variations_per_family": 0,
        }


# =============================================================================
# CONVENIENCE FUNCTIONS (Backwards Compatibility)
# =============================================================================

_generator_instance: Optional[VariationGenerator] = None


def get_variation_generator() -> VariationGenerator:
    """
    Get the singleton variation generator.

    For new code, prefer using wrapper methods directly.
    """
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = VariationGenerator()
    return _generator_instance


def generate_and_cache_variations(
    pattern: Payload,
    num_structure_variations: int = 3,
    num_param_variations: int = 2,
) -> Optional[VariationFamily]:
    """
    Convenience function to generate and cache variations.

    For new code, prefer using wrapper methods directly.

    Args:
        pattern: Source pattern
        num_structure_variations: Structural variations count
        num_param_variations: Parameter variations per structure

    Returns:
        VariationFamily with all generated variations
    """
    generator = get_variation_generator()
    return generator.generate_variations(
        pattern,
        num_structure_variations,
        num_param_variations,
    )
