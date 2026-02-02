"""
Google Chat testing utilities.

Includes:
- SmokeTestGenerator: Hardcoded smoke test card generation
- DAGStructureGenerator: NetworkX DAG-based random valid structure generation

Test Modules (run directly with: uv run python -m gchat.testing.<module>):
- test_build_component: Tests _build_component() universality and robustness
- test_auto_wrap: Tests DAG-based auto-wrapping (Button → ButtonList)
- test_return_instance: Tests return_instance feature for building hierarchies
- test_style_auto_application: Tests style metadata extraction and auto-application

Usage:
    # Generate random valid structures
    from gchat.testing import generate_dag_structure, generate_dag_card

    structure = generate_dag_structure("Section")
    print(structure.dsl)  # §[δ, Ƀ[ᵬ×2]]

    # Send test cards to webhook
    from gchat.testing import run_dag_smoke_test
    run_dag_smoke_test("https://chat.googleapis.com/v1/spaces/...", count=5)

    # Run all tests
    uv run python -m gchat.testing.test_build_component
    uv run python -m gchat.testing.test_auto_wrap
    uv run python -m gchat.testing.test_return_instance
    uv run python -m gchat.testing.test_style_auto_application
"""

from .dag_structure_generator import (
    COMPONENT_DEFAULTS,
    CURATED_MATERIAL_ICONS,
    WIDGET_HIERARCHY,
    ComponentSchema,
    DAGGeneratorConfig,
    DAGStructureGenerator,
    FieldInfo,
    GeneratedStructure,
    ParameterizedNode,
    ParameterizedStructure,
    generate_dag_card,
    generate_dag_structure,
    run_dag_smoke_test,
    run_dag_stress_test,
    run_stress_test,
    send_dag_cards_to_webhook,
    send_parameterized_cards_to_webhook,
)
from .smoke_test_generator import SmokeTestGenerator

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
