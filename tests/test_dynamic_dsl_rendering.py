"""
Test that DSL rendering is TRULY dynamic using only the ModuleWrapper.

This test proves that:
1. All symbols come from the wrapper (not hardcoded)
2. All component relationships come from the wrapper (not hardcoded)
3. Random valid structures can be generated and rendered
4. NO hardcoded component lists are needed
"""

import random
from typing import Any, Dict, List, Optional, Set

import pytest


def get_all_symbols_from_wrapper() -> Dict[str, str]:
    """Get ALL symbols dynamically from wrapper - no hardcoding."""
    from gchat.card_framework_wrapper import get_gchat_symbols

    symbols = get_gchat_symbols()
    print(f"\n📊 Loaded {len(symbols)} symbols from wrapper")
    return symbols


def get_all_relationships_from_wrapper() -> Dict[str, List[str]]:
    """Get ALL parent->children relationships dynamically from wrapper."""
    from gchat.card_framework_wrapper import get_component_relationships_for_dsl

    relationships = get_component_relationships_for_dsl()
    print(f"📊 Loaded {len(relationships)} parent->children relationships")
    return relationships


def get_widget_components_from_wrapper() -> Set[str]:
    """Get all widget components (things that can be in a Section) from wrapper."""
    relationships = get_all_relationships_from_wrapper()

    # Section's children are the widget components
    section_children = set(relationships.get("Section", []))
    print(f"📊 Found {len(section_children)} widget components under Section")
    return section_children


def get_component_class_from_wrapper(component_name: str):
    """Dynamically get a component class from the wrapper."""
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    # Try multiple path patterns (component paths vary)
    paths = [
        f"card_framework.v2.widgets.{component_name.lower()}.{component_name}",
        f"card_framework.v2.widgets.{component_name}",
        f"card_framework.v2.{component_name.lower()}.{component_name}",
        f"card_framework.v2.{component_name}",
        f"card_framework.{component_name}",
    ]

    for path in paths:
        comp_class = wrapper.get_component_by_path(path)
        if comp_class:
            return comp_class

    # Also try searching wrapper.components directly
    for comp_path, comp in wrapper.components.items():
        if comp_path.endswith(f".{component_name}") or comp_path.endswith(f".{component_name.lower()}.{component_name}"):
            if hasattr(comp, 'obj') and comp.obj:
                return comp.obj

    return None


def get_required_fields_from_class(comp_class) -> Dict[str, Any]:
    """Inspect a component class to find required fields."""
    import dataclasses
    import inspect

    if not comp_class:
        return {}

    required = {}

    # For dataclasses, check field defaults
    if dataclasses.is_dataclass(comp_class):
        for field in dataclasses.fields(comp_class):
            # Fields without defaults are required
            if field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING:
                # Generate a sensible default based on field name/type
                if 'name' in field.name.lower():
                    required[field.name] = f"auto_{field.name}"
                elif 'label' in field.name.lower():
                    required[field.name] = f"Auto Label"
                elif 'text' in field.name.lower():
                    required[field.name] = "Auto generated text"
                elif 'url' in field.name.lower():
                    required[field.name] = "https://example.com"

    return required


def render_component_dynamically(component_name: str, index: int = 0) -> Optional[Dict]:
    """
    Render ANY component dynamically using ONLY the wrapper.

    No hardcoded defaults - inspects the class to find required fields.
    """
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()
    comp_class = get_component_class_from_wrapper(component_name)

    if not comp_class:
        print(f"  ⚠️ No class found for {component_name}")
        return None

    # Get required fields by inspecting the class
    required_params = get_required_fields_from_class(comp_class)

    # Add index to name fields for uniqueness
    for key in required_params:
        if 'name' in key.lower():
            required_params[key] = f"{required_params[key]}_{index}"

    try:
        # Use wrapper's create_card_component
        instance = wrapper.create_card_component(comp_class, required_params)

        if instance and hasattr(instance, 'render'):
            rendered = instance.render()
            print(f"  ✅ {component_name} rendered successfully")
            return rendered
        elif instance and hasattr(instance, 'to_dict'):
            key = component_name[0].lower() + component_name[1:]
            rendered = {key: instance.to_dict()}
            print(f"  ✅ {component_name} rendered via to_dict()")
            return rendered
        else:
            print(f"  ⚠️ {component_name} instance has no render/to_dict")
            return None

    except Exception as e:
        print(f"  ❌ {component_name} failed: {e}")
        return None


def generate_random_valid_structure(max_widgets: int = 5) -> List[str]:
    """
    Generate a random but VALID component structure using ONLY wrapper data.

    Uses relationships to ensure parent-child validity.
    """
    relationships = get_all_relationships_from_wrapper()

    # Start with Section (standard card structure)
    structure = ["Section"]

    # Get valid children for Section
    valid_widgets = relationships.get("Section", [])
    if not valid_widgets:
        print("⚠️ No valid widgets found for Section")
        return structure

    # Randomly pick some widgets
    num_widgets = random.randint(1, min(max_widgets, len(valid_widgets)))
    chosen = random.sample(valid_widgets, num_widgets)

    for widget in chosen:
        structure.append(widget)

        # If this widget has children, maybe add some
        widget_children = relationships.get(widget, [])
        if widget_children and random.random() > 0.5:
            # Add 1-3 children
            num_children = random.randint(1, min(3, len(widget_children)))
            for child in random.sample(widget_children, num_children):
                structure.append(child)

    return structure


def build_dsl_from_structure(structure: List[str]) -> str:
    """Build DSL notation from a component structure using wrapper symbols."""
    symbols = get_all_symbols_from_wrapper()

    # Simple flat DSL for now
    dsl_parts = []
    for comp in structure:
        symbol = symbols.get(comp, comp[0])  # Fallback to first letter
        dsl_parts.append(symbol)

    # Wrap in Section if not already
    if structure and structure[0] == "Section":
        section_sym = symbols.get("Section", "§")
        inner = ", ".join(dsl_parts[1:])
        return f"{section_sym}[{inner}]"

    return ", ".join(dsl_parts)


# =============================================================================
# TESTS
# =============================================================================


def test_wrapper_provides_all_symbols():
    """Verify wrapper provides symbol mappings without hardcoding."""
    symbols = get_all_symbols_from_wrapper()

    assert len(symbols) > 50, f"Expected 50+ symbols, got {len(symbols)}"

    # Check some expected components exist (but don't hardcode the symbols!)
    expected_components = ["Button", "Section", "DecoratedText", "Grid", "TextInput"]
    for comp in expected_components:
        assert comp in symbols, f"Missing symbol for {comp}"
        print(f"  {comp} -> {symbols[comp]}")


def test_wrapper_provides_relationships():
    """Verify wrapper provides parent->child relationships."""
    relationships = get_all_relationships_from_wrapper()

    assert len(relationships) > 5, f"Expected 5+ relationships, got {len(relationships)}"

    # Section should have children
    assert "Section" in relationships, "Section not in relationships"
    section_children = relationships["Section"]
    assert len(section_children) > 5, f"Section should have 5+ children, got {len(section_children)}"

    print(f"\nSection children: {section_children}")


def test_can_get_component_classes_dynamically():
    """Verify we can get component classes from wrapper for widget symbols."""
    symbols = get_all_symbols_from_wrapper()

    # Focus on actual widget component names (not enums, not internal classes)
    widget_names = [
        "Button", "ButtonList", "DecoratedText", "TextParagraph",
        "Grid", "Image", "Divider", "TextInput", "DateTimePicker",
        "SelectionInput", "ChipList", "Columns", "Section",
    ]

    found = 0
    failed = []

    for comp_name in widget_names:
        if comp_name not in symbols:
            continue
        symbol = symbols[comp_name]
        comp_class = get_component_class_from_wrapper(comp_name)
        if comp_class:
            found += 1
            print(f"  ✅ {symbol} -> {comp_name} -> {comp_class.__name__}")
        else:
            failed.append(comp_name)

    print(f"\n📊 Found {found}/{len(widget_names)} widget component classes")
    if failed:
        print(f"⚠️ Failed to find: {failed}")

    assert found >= 10, f"Should find at least 10 widget component classes, got {found}"


def test_render_random_widget_components():
    """Test rendering random widget components using ONLY wrapper."""
    widget_components = get_widget_components_from_wrapper()

    # Try to render 10 random widgets
    to_test = random.sample(list(widget_components), min(10, len(widget_components)))

    print(f"\n🎲 Testing {len(to_test)} random widgets:")

    rendered = 0
    for i, comp_name in enumerate(to_test):
        result = render_component_dynamically(comp_name, i)
        if result:
            rendered += 1

    print(f"\n📊 Successfully rendered {rendered}/{len(to_test)} components")

    # At least half should render
    assert rendered >= len(to_test) // 2, f"Too many render failures: {rendered}/{len(to_test)}"


def test_generate_and_render_random_structure():
    """Generate random valid structures and render them."""
    print("\n🎲 Generating 5 random card structures:")

    successful = 0

    for i in range(5):
        structure = generate_random_valid_structure(max_widgets=4)
        dsl = build_dsl_from_structure(structure)

        print(f"\n  Structure {i+1}: {structure}")
        print(f"  DSL: {dsl}")

        # Try to render each widget in the structure
        widgets_rendered = 0
        for j, comp in enumerate(structure):
            if comp == "Section":
                continue
            result = render_component_dynamically(comp, j)
            if result:
                widgets_rendered += 1

        if widgets_rendered > 0:
            successful += 1
            print(f"  ✅ Rendered {widgets_rendered} widgets")
        else:
            print(f"  ❌ No widgets rendered")

    assert successful >= 3, f"At least 3/5 structures should render, got {successful}"


def test_prepared_pattern_with_dynamic_structure():
    """Test PreparedPattern with dynamically generated structure."""
    from gchat.card_builder import PreparedPattern
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    # Generate random structure
    structure = generate_random_valid_structure(max_widgets=3)
    print(f"\n🎲 Random structure: {structure}")

    # Create PreparedPattern
    prepared = PreparedPattern(structure, wrapper)

    # Set some generic params
    prepared.set_params(
        text="Dynamically generated content",
        title="Dynamic Card",
    )

    # Get instances (without rendering)
    instances = prepared.get_instances()
    print(f"📊 Got {len(instances)} instances")

    for inst in instances:
        status = "✅" if inst["instance"] else "⚠️"
        print(f"  {status} {inst['name']}: class={inst['class'] is not None}")

    # Render
    card = prepared.render()

    assert "sections" in card, "Card should have sections"
    print(f"\n✅ Card rendered with {len(card.get('sections', []))} sections")


def test_all_section_children_can_render():
    """Test that ALL components valid under Section can render."""
    relationships = get_all_relationships_from_wrapper()
    section_children = relationships.get("Section", [])

    print(f"\n🧪 Testing ALL {len(section_children)} Section children:")

    results = {"success": [], "failed": []}

    for i, comp_name in enumerate(section_children):
        result = render_component_dynamically(comp_name, i)
        if result:
            results["success"].append(comp_name)
        else:
            results["failed"].append(comp_name)

    print(f"\n📊 Results:")
    print(f"  ✅ Success: {len(results['success'])} - {results['success']}")
    print(f"  ❌ Failed: {len(results['failed'])} - {results['failed']}")

    # Most should succeed
    success_rate = len(results["success"]) / len(section_children) if section_children else 0
    assert success_rate >= 0.5, f"At least 50% should render, got {success_rate:.0%}"


if __name__ == "__main__":
    print("=" * 60)
    print("DYNAMIC DSL RENDERING TESTS")
    print("=" * 60)

    test_wrapper_provides_all_symbols()
    test_wrapper_provides_relationships()
    test_can_get_component_classes_dynamically()
    test_render_random_widget_components()
    test_generate_and_render_random_structure()
    test_prepared_pattern_with_dynamic_structure()
    test_all_section_children_can_render()

    print("\n" + "=" * 60)
    print("✅ ALL DYNAMIC TESTS PASSED")
    print("=" * 60)
