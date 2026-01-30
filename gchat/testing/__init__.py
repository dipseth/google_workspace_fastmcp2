"""
Google Chat testing utilities.

Includes:
- SmokeTestGenerator: Hardcoded smoke test card generation
- DAGStructureGenerator: NetworkX DAG-based random valid structure generation

Usage:
    # Generate random valid structures
    from gchat.testing import generate_dag_structure, generate_dag_card

    structure = generate_dag_structure("Section")
    print(structure.dsl)  # §[δ, Ƀ[ᵬ×2]]

    # Send test cards to webhook
    from gchat.testing import run_dag_smoke_test
    run_dag_smoke_test("https://chat.googleapis.com/v1/spaces/...", count=5)
"""

from .smoke_test_generator import SmokeTestGenerator
from .dag_structure_generator import (
    DAGStructureGenerator,
    DAGGeneratorConfig,
    GeneratedStructure,
    ParameterizedStructure,
    ParameterizedNode,
    FieldInfo,
    ComponentSchema,
    generate_dag_card,
    generate_dag_structure,
    send_dag_cards_to_webhook,
    send_parameterized_cards_to_webhook,
    run_dag_smoke_test,
    run_dag_stress_test,
    run_stress_test,
    WIDGET_HIERARCHY,
    CURATED_MATERIAL_ICONS,
    COMPONENT_DEFAULTS,
)

__all__ = [
    # Smoke testing
    "SmokeTestGenerator",
    # DAG-based generation
    "DAGStructureGenerator",
    "DAGGeneratorConfig",
    "GeneratedStructure",
    "ParameterizedStructure",
    "ParameterizedNode",
    "FieldInfo",
    "ComponentSchema",
    "generate_dag_card",
    "generate_dag_structure",
    "send_dag_cards_to_webhook",
    "send_parameterized_cards_to_webhook",
    "run_dag_smoke_test",
    "run_dag_stress_test",
    "run_stress_test",
    "WIDGET_HIERARCHY",
    "CURATED_MATERIAL_ICONS",
    "COMPONENT_DEFAULTS",
]
