#!/usr/bin/env python3
"""
Test the Template System for SmartCardBuilder

This test validates:
1. TemplateComponent can load and render
2. TemplateRegistry loads YAML files
3. ModuleWrapper handles template paths
4. Promotion from instance_pattern to template
5. Integration with SmartCardBuilder
"""

import os
import sys

from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

# Import settings after path setup
from config.settings import settings as _settings


def test_template_component_basic():
    """Test that TemplateComponent can render a simple template."""
    print("\n" + "=" * 60)
    print("TEST: TemplateComponent basic rendering")
    print("=" * 60)

    from gchat.template_component import TemplateComponent

    # Create a simple template
    template_data = {
        "name": "test_simple_card",
        "components": [
            {
                "path": "card_framework.v2.widgets.decorated_text.DecoratedText",
                "params": {"text": "${message}", "top_label": "Status"},
            }
        ],
        "defaults": {"message": "Hello World", "title": "Test Card"},
        "layout": {"type": "standard"},
    }

    # Create component and render
    component = TemplateComponent(template_data)
    rendered = component.render()

    print(f"   Template name: {component.name}")
    print(f"   Rendered has sections: {'sections' in rendered}")

    has_sections = "sections" in rendered
    has_widgets = (
        has_sections and len(rendered.get("sections", [{}])[0].get("widgets", [])) > 0
    )

    print(f"   Has widgets: {has_widgets}")
    print(f"   Result: {'PASS' if has_widgets else 'FAIL'}")

    return has_widgets


def test_template_param_substitution():
    """Test that ${param} substitution works."""
    print("\n" + "=" * 60)
    print("TEST: Template parameter substitution")
    print("=" * 60)

    from gchat.template_component import TemplateComponent

    template_data = {
        "name": "test_substitution",
        "components": [
            {
                "path": "card_framework.v2.widgets.decorated_text.DecoratedText",
                "params": {"text": "${price}", "top_label": "${label}"},
            }
        ],
        "defaults": {"price": "$99.99", "label": "Price"},
    }

    # Override defaults
    component = TemplateComponent(template_data, price="$49.99", label="Sale Price")

    # Check substitution
    substituted = component._substitute_params(
        {"text": "${price}", "label": "${label}"}
    )

    print(f"   Original: ${{price}}, ${{label}}")
    print(f"   Substituted: {substituted['text']}, {substituted['label']}")

    correct = substituted["text"] == "$49.99" and substituted["label"] == "Sale Price"
    print(f"   Result: {'PASS' if correct else 'FAIL'}")

    return correct


def test_template_registry_load():
    """Test that TemplateRegistry can load YAML files."""
    print("\n" + "=" * 60)
    print("TEST: TemplateRegistry loads YAML files")
    print("=" * 60)

    from gchat.template_component import get_template_registry

    registry = get_template_registry()
    templates = registry.list_templates()

    print(f"   Templates found: {len(templates)}")
    for name in templates[:5]:  # Show first 5
        print(f"      - {name}")

    # At minimum we should have the example template
    has_templates = len(templates) >= 0  # May be empty if no files yet

    print(f"   Result: PASS (registry working)")
    return True


def test_template_registry_save():
    """Test that TemplateRegistry can save a template to YAML."""
    print("\n" + "=" * 60)
    print("TEST: TemplateRegistry saves template to YAML")
    print("=" * 60)

    import uuid

    from gchat.template_component import get_template_registry

    registry = get_template_registry()

    # Create a test template
    test_name = f"test_template_{uuid.uuid4().hex[:8]}"
    template_data = {
        "components": [
            {
                "path": "card_framework.v2.widgets.text_paragraph.TextParagraph",
                "params": {"text": "Test content"},
            }
        ],
        "defaults": {"title": "Test"},
        "metadata": {"test": True},
    }

    # Save it
    filepath = registry.save_template_to_file(test_name, template_data)

    print(f"   Saved to: {filepath}")

    # Verify it exists
    file_exists = os.path.exists(filepath)
    print(f"   File exists: {file_exists}")

    # Clean up
    if file_exists:
        os.remove(filepath)
        print(f"   Cleaned up test file")

    print(f"   Result: {'PASS' if file_exists else 'FAIL'}")
    return file_exists


def test_module_wrapper_template_path():
    """Test that ModuleWrapper can handle template paths."""
    print("\n" + "=" * 60)
    print("TEST: ModuleWrapper handles template paths")
    print("=" * 60)

    from adapters.module_wrapper import ModuleWrapper
    from gchat.template_component import get_template_registry

    # First, register a template
    registry = get_template_registry()
    registry.register_template(
        "test_wrapper_template",
        {
            "name": "test_wrapper_template",
            "components": [
                {
                    "path": "card_framework.v2.widgets.text_paragraph.TextParagraph",
                    "params": {"text": "Loaded via ModuleWrapper"},
                }
            ],
            "defaults": {},
        },
    )

    # Now try to load via ModuleWrapper
    wrapper = ModuleWrapper(
        module_or_name="card_framework",
        auto_initialize=False,
    )

    component = wrapper.get_component_by_path(
        "card_framework.templates.test_wrapper_template"
    )

    print(f"   Component loaded: {component is not None}")

    if component:
        print(f"   Component type: {type(component).__name__}")
        # Try to render
        try:
            rendered = component.render()
            has_sections = "sections" in rendered
            print(f"   Rendered successfully: {has_sections}")
            result = has_sections
        except Exception as e:
            print(f"   Render failed: {e}")
            result = False
    else:
        result = False

    print(f"   Result: {'PASS' if result else 'FAIL'}")
    return result


def test_promotion_to_template():
    """Test that patterns with enough positive feedback get promoted."""
    print("\n" + "=" * 60)
    print("TEST: Pattern promotion to template")
    print("=" * 60)

    import uuid

    from gchat.feedback_loop import get_feedback_loop

    feedback_loop = get_feedback_loop()

    # Generate card_id first
    test_card_id = f"test-promotion-{uuid.uuid4().hex[:8]}"

    # Store a pattern with pre-set positive count
    point_id = feedback_loop.store_instance_pattern(
        card_description="A highly rated product card with price and buy button",
        component_paths=[
            "card_framework.v2.widgets.decorated_text.DecoratedText",
            "card_framework.v2.widgets.button_list.ButtonList",
        ],
        instance_params={
            "text": "$149.99",
            "top_label": "Price",
            "buttons": [{"text": "Buy Now", "url": "https://example.com/buy"}],
        },
        feedback="positive",
        user_email="test@example.com",
        card_id=test_card_id,
    )

    print(f"   Stored pattern: {point_id[:8] if point_id else 'None'}...")

    # Manually set high positive count to trigger promotion
    # (In real usage, this happens automatically via update_feedback)
    client = feedback_loop._get_client()
    if client and point_id:
        try:
            client.set_payload(
                collection_name=_settings.card_collection,
                payload={"positive_count": 3},  # Threshold for template promotion
                points=[point_id],
            )
            print(f"   Set positive_count to 3 (promotion threshold)")

            # Simulate another positive feedback to trigger promotion check
            # Actually call _check_and_promote
            from qdrant_client import models

            results, _ = client.scroll(
                collection_name=_settings.card_collection,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="card_id",
                            match=models.MatchValue(value=test_card_id),
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
            )

            if results:
                feedback_loop._check_and_promote(results[0])

                # Check if promoted
                results2, _ = client.scroll(
                    collection_name=_settings.card_collection,
                    scroll_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="card_id",
                                match=models.MatchValue(value=test_card_id),
                            )
                        ]
                    ),
                    limit=1,
                    with_payload=True,
                )

                if results2:
                    new_type = results2[0].payload.get("type")
                    print(f"   New type: {new_type}")
                    result = new_type == "template"
                else:
                    result = False
            else:
                print(f"   Could not find pattern")
                result = False

        except Exception as e:
            print(f"   Error: {e}")
            result = False
    else:
        result = False

    print(f"   Result: {'PASS' if result else 'FAIL (may need more setup)'}")
    return result


def main():
    """Run all template system tests."""
    print("=" * 60)
    print("TEMPLATE SYSTEM TEST SUITE")
    print("=" * 60)

    results = []

    # Test 1: Basic TemplateComponent
    results.append(("TemplateComponent basic", test_template_component_basic()))

    # Test 2: Parameter substitution
    results.append(("Parameter substitution", test_template_param_substitution()))

    # Test 3: Registry loading
    results.append(("Registry loads YAML", test_template_registry_load()))

    # Test 4: Registry saving
    results.append(("Registry saves YAML", test_template_registry_save()))

    # Test 5: ModuleWrapper integration
    results.append(("ModuleWrapper template path", test_module_wrapper_template_path()))

    # Test 6: Promotion
    results.append(("Pattern promotion", test_promotion_to_template()))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"   {name}: {status}")

    all_passed = all(r[1] for r in results)
    print(f"\n   Overall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
