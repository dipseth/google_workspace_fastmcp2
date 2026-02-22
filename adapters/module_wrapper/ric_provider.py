"""
RIC Text Provider Protocol

Defines the contract for generating the 3 RIC (Rich Information Content) text
representations used by the v7 embedding pipeline:

  1. component_text  -> "What IS this?"        -> components vector (ColBERT 128d)
  2. inputs_text     -> "What does it accept?"  -> inputs vector    (ColBERT 128d)
  3. relationships_text -> "How does it relate?" -> relationships vector (MiniLM 384d)

Providers return RAW text. The pipeline applies symbol wrapping uniformly
(ColBERT vectors get "{symbol} {text} {symbol}").

The default IntrospectionProvider wraps the existing helper functions in
pipeline_mixin.py so existing embeddings are identical.
"""

import logging
from typing import Any, Dict, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class RICTextProvider(Protocol):
    """Generates the 3 RIC text representations for a component type.

    Providers return RAW text. The wrapper applies symbol wrapping
    uniformly (ColBERT vectors get "{symbol} {text} {symbol}").
    """

    @property
    def component_type(self) -> str:
        """Which component_type this handles ('class', 'tool', 'api_endpoint', etc.)"""
        ...

    def component_text(self, name: str, metadata: Dict[str, Any]) -> str:
        """Identity: 'What IS this component?' -> components vector (ColBERT 128d)"""
        ...

    def inputs_text(self, name: str, metadata: Dict[str, Any]) -> str:
        """Values: 'What does it accept/produce?' -> inputs vector (ColBERT 128d)"""
        ...

    def relationships_text(self, name: str, metadata: Dict[str, Any]) -> str:
        """Graph: 'How does it relate to others?' -> relationships vector (MiniLM 384d)"""
        ...


class IntrospectionProvider:
    """Default RIC text provider for introspected Python components.

    Handles component_type: class, function, variable.

    Wraps the existing helper functions (extract_input_values,
    build_compact_relationship_text) so text output is identical
    to the previous inline code in run_ingestion_pipeline().
    """

    @property
    def component_type(self) -> str:
        return "class"  # Also handles function/variable via fallback

    def component_text(self, name: str, metadata: Dict[str, Any]) -> str:
        """Build component identity text.

        Reproduces the inline logic from pipeline_mixin.py lines 433-435:
            f"Name: {component.name}\\nType: {component.component_type}\\nPath: {component.full_path}"
            + optional docstring
        """
        comp_type = metadata.get("component_type", "class")
        full_path = metadata.get("full_path", name)
        docstring = metadata.get("docstring", "")

        text = f"Name: {name}\nType: {comp_type}\nPath: {full_path}"
        if docstring:
            text += f"\nDocumentation: {docstring[:500]}"
        return text

    def inputs_text(self, name: str, metadata: Dict[str, Any]) -> str:
        """Build inputs text by delegating to extract_input_values.

        Requires metadata["component"] to contain the ModuleComponent object,
        OR falls back to basic text from metadata fields.
        """
        component = metadata.get("component")
        if component is not None:
            from adapters.module_wrapper.pipeline_mixin import extract_input_values
            return extract_input_values(component)

        # Fallback for non-live components (e.g. Qdrant payload reconstruction)
        comp_type = metadata.get("component_type", "class")
        return f"{name} {comp_type}"

    def relationships_text(self, name: str, metadata: Dict[str, Any]) -> str:
        """Build relationship text.

        Uses structure_validator enriched text when available (same as
        pipeline_mixin.py lines 452-465), otherwise falls back to
        build_compact_relationship_text().
        """
        # Check for enriched text from structure validator
        structure_validator = metadata.get("structure_validator")
        comp_type = metadata.get("component_type", "class")
        symbols = metadata.get("symbols", {})

        if (
            structure_validator
            and comp_type == "class"
            and name in symbols
        ):
            return structure_validator.get_enriched_relationship_text(name)

        # Fall back to compact relationship text
        from adapters.module_wrapper.pipeline_mixin import build_compact_relationship_text

        rels = metadata.get("relationships", [])
        return build_compact_relationship_text(name, rels, comp_type)


__all__ = [
    "RICTextProvider",
    "IntrospectionProvider",
]
