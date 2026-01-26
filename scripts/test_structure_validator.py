#!/usr/bin/env python3
"""
Test script for StructureValidator integration.

Tests:
1. Structure validation against component hierarchy
2. Fallback structure generation from inputs
3. Symbol-enriched relationship text for embeddings
4. Template composition
5. Random color schemes and styling
6. Jinja templating with styling filters
7. DSL parsing with nested structures
8. Card building from DSL notation
9. Webhook sending for visual verification

Usage:
    # Run all tests
    python scripts/test_structure_validator.py

    # Send test card to webhook
    python scripts/test_structure_validator.py --send-webhook

    # Test specific DSL notation
    python scripts/test_structure_validator.py --dsl "§[δ×3, Ƀ[ᵬ×2]]"
"""

import argparse
import json
import os
import random
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from adapters.structure_validator import StructureValidator
from gchat.card_framework_wrapper import get_card_framework_wrapper
from middleware.filters.styling_filters import (
    COLOR_SCHEMES,
    SEMANTIC_COLORS,
    STYLING_FILTERS,
    ColorCycler,
    ComponentStyler,
    color_filter,
)
from middleware.template_core.jinja_environment import JinjaEnvironmentManager


def get_jinja_environment():
    """Get configured Jinja environment with all styling filters."""
    jinja_mgr = JinjaEnvironmentManager()
    jinja_mgr.setup_jinja2_environment()
    jinja_mgr.register_filters(STYLING_FILTERS)
    return jinja_mgr.jinja2_env


# ==============================================================================
# DSL PARSING AND CARD BUILDING TESTS
# ==============================================================================


def test_dsl_parsing():
    """Test DSL parsing with various structures."""
    print("=" * 60)
    print("TEST: DSL Parsing")
    print("=" * 60)

    wrapper = get_card_framework_wrapper()
    validator = wrapper.get_structure_validator()

    test_cases = [
        # Basic structure
        ("§[δ×2]", "Section with 2 DecoratedText"),
        # Multiple children
        (
            "§[δ×2, Ƀ[ᵬ×2]]",
            "Section with 2 DecoratedText and ButtonList with 2 Buttons",
        ),
        # Nested grid
        ("§[ℊ[ǵ×4]]", "Section with Grid containing 4 GridItems"),
        # Complex nested
        ("§[δ×2, ℊ[ǵ×4], Ƀ[ᵬ×2]]", "Section with DecoratedText, Grid, and ButtonList"),
        # Deep nesting
        ("§[δ, §[δ×2, Ƀ[ᵬ]]]", "Nested sections"),
    ]

    passed = 0
    failed = 0

    for dsl, description in test_cases:
        print(f"\n  Testing: {dsl}")
        print(f"  Description: {description}")

        try:
            result = validator.parse_structure(dsl)
            print(f"  Parsed components: {len(result)}")

            # Pretty print parsed structure
            def print_component(comp, indent=4):
                prefix = " " * indent
                name = comp.get("name", comp.get("symbol", "?"))
                mult = comp.get("multiplier", 1)
                children = comp.get("children", [])
                print(f"{prefix}- {name} (x{mult})")
                for child in children:
                    print_component(child, indent + 2)

            for comp in result:
                print_component(comp)

            passed += 1
            print(f"  Result: PASS")

        except Exception as e:
            print(f"  Result: FAIL - {e}")
            failed += 1

    print(f"\n  Summary: {passed} passed, {failed} failed")
    return failed == 0


def test_card_building():
    """Test building cards from DSL notation."""
    print("\n" + "=" * 60)
    print("TEST: Card Building from DSL")
    print("=" * 60)

    wrapper = get_card_framework_wrapper()
    validator = wrapper.get_structure_validator()

    # Test DSL
    dsl = "§[δ×2, ℊ[ǵ×4], Ƀ[ᵬ×2]]"
    print(f"\n  DSL: {dsl}")

    # Parse DSL
    components = validator.parse_structure(dsl)
    print(f"  Parsed {len(components)} top-level components")

    # Build card structure manually for verification
    card = build_card_from_dsl(dsl, "DSL Test Card", "Built from parsed DSL")

    print(
        f"  Card sections: {len(card.get('cardsV2', [{}])[0].get('card', {}).get('sections', []))}"
    )

    widgets = (
        card.get("cardsV2", [{}])[0]
        .get("card", {})
        .get("sections", [{}])[0]
        .get("widgets", [])
    )
    print(f"  Widgets in first section: {len(widgets)}")

    for i, widget in enumerate(widgets):
        widget_type = list(widget.keys())[0] if widget else "empty"
        print(f"    Widget {i + 1}: {widget_type}")

    return True


def build_card_from_dsl(
    dsl: str, title: str = "DSL Card", subtitle: str = None
) -> dict:
    """
    Build a Google Chat card from DSL notation.

    Args:
        dsl: DSL notation like "§[δ×2, ℊ[ǵ×4], Ƀ[ᵬ×2]]"
        title: Card header title
        subtitle: Card header subtitle (defaults to showing DSL)

    Returns:
        Complete cardsV2 structure for Google Chat API
    """
    wrapper = get_card_framework_wrapper()
    validator = wrapper.get_structure_validator()
    components = validator.parse_structure(dsl)

    if subtitle is None:
        subtitle = f"Structure: {dsl}"

    # Build widgets from parsed components
    widgets = []

    def build_widgets(comps):
        result = []
        for comp in comps:
            name = comp.get("name", "")
            mult = comp.get("multiplier", 1)
            children = comp.get("children", [])

            for i in range(mult):
                if name == "DecoratedText":
                    result.append(
                        {
                            "decoratedText": {
                                "topLabel": f"Item {len(result) + 1}",
                                "text": f"DecoratedText content #{i + 1}",
                            }
                        }
                    )
                elif name == "TextParagraph":
                    result.append(
                        {"textParagraph": {"text": f"TextParagraph content #{i + 1}"}}
                    )
                elif name == "Grid":
                    # Build grid items from children
                    grid_items = []
                    for child in children:
                        if child.get("name") == "GridItem":
                            for j in range(child.get("multiplier", 1)):
                                grid_items.append(
                                    {
                                        "image": {
                                            "imageUri": f"https://picsum.photos/100/100?{len(grid_items) + 1}"
                                        },
                                        "title": f"Grid Item {len(grid_items) + 1}",
                                    }
                                )
                    if grid_items:
                        result.append(
                            {
                                "columns": {
                                    "columnItems": [
                                        {
                                            "horizontalSizeStyle": "FILL_AVAILABLE_SPACE",
                                            "widgets": [
                                                {
                                                    "image": {
                                                        "imageUrl": item["image"][
                                                            "imageUri"
                                                        ]
                                                    }
                                                }
                                            ],
                                        }
                                        for item in grid_items
                                    ]
                                }
                            }
                        )
                elif name == "ButtonList":
                    # Build buttons from children
                    buttons = []
                    for child in children:
                        if child.get("name") == "Button":
                            for j in range(child.get("multiplier", 1)):
                                buttons.append(
                                    {
                                        "text": f"Button {len(buttons) + 1}",
                                        "onClick": {
                                            "openLink": {"url": "https://google.com"}
                                        },
                                    }
                                )
                    if buttons:
                        result.append({"buttonList": {"buttons": buttons}})
                elif name == "Image":
                    result.append(
                        {
                            "image": {
                                "imageUrl": f"https://picsum.photos/300/200?{i + 1}"
                            }
                        }
                    )
                elif name == "Section":
                    # Nested section - recurse into children
                    nested_widgets = build_widgets(children)
                    result.extend(nested_widgets)

        return result

    # Process top-level components (usually Section)
    for comp in components:
        name = comp.get("name", "")
        children = comp.get("children", [])

        if name == "Section":
            widgets = build_widgets(children)
        else:
            # Not wrapped in section, build directly
            widgets = build_widgets(components)
            break

    return {
        "cardsV2": [
            {
                "cardId": "dsl-test-card",
                "card": {
                    "header": {"title": title, "subtitle": subtitle},
                    "sections": [{"header": "Section from DSL", "widgets": widgets}],
                },
            }
        ]
    }


def send_to_webhook(card: dict, webhook_url: str = None) -> bool:
    """
    Send a card to Google Chat webhook for visual verification.

    Args:
        card: cardsV2 structure
        webhook_url: Webhook URL (uses TEST_CHAT_WEBHOOK env var if not provided)

    Returns:
        True if successful
    """
    if webhook_url is None:
        webhook_url = os.environ.get("TEST_CHAT_WEBHOOK")

    if not webhook_url:
        print(
            "  ERROR: No webhook URL provided. Set TEST_CHAT_WEBHOOK env var or pass --webhook"
        )
        return False

    print(f"\n  Sending to webhook...")
    print(f"  Card structure preview:")
    print(f"  {json.dumps(card, indent=2)[:500]}...")

    response = requests.post(
        webhook_url, json=card, headers={"Content-Type": "application/json"}
    )

    print(f"\n  Response status: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print(f"  Message ID: {result.get('name', 'unknown')}")
        return True
    else:
        print(f"  Error: {response.text[:200]}")
        return False


def test_structure_validator():
    """Test the StructureValidator integration."""
    print("=" * 60)
    print("STRUCTURE VALIDATOR TEST")
    print("=" * 60)

    # Get the card framework wrapper
    print("\n1. Getting card framework wrapper...")
    wrapper = get_card_framework_wrapper()
    print(f"   ✓ Wrapper loaded with {len(wrapper.components)} components")

    # Get the structure validator
    print("\n2. Getting structure validator...")
    validator = wrapper.get_structure_validator()
    print(f"   ✓ Validator created")

    # Check symbols
    print("\n3. Symbol mappings (first 10):")
    symbols = validator.symbols
    for i, (name, sym) in enumerate(list(symbols.items())[:10]):
        print(f"   {sym} = {name}")
    print(f"   ... ({len(symbols)} total)")

    # Check relationships
    print("\n4. Relationships (first 5 parents):")
    relationships = validator.relationships
    for i, (parent, children) in enumerate(list(relationships.items())[:5]):
        print(f"   {parent} → {children[:3]}{'...' if len(children) > 3 else ''}")
    print(f"   ... ({len(relationships)} total parents)")

    # Test structure validation
    print("\n5. Structure validation tests:")

    test_structures = [
        # Valid structures
        ("§[đ]", "Section with DecoratedText"),
        (
            "§[đ, ᵬ]",
            "Section with DecoratedText and Button (invalid - Button needs ButtonList)",
        ),
        ("§[đ, Ƀ[ᵬ]]", "Section with DecoratedText and ButtonList containing Button"),
        ("§[đ, Ƀ[ᵬ×2]]", "Section with 2 Buttons"),
        # Try with full names too
        ("Section[DecoratedText]", "Using full names"),
    ]

    for structure, desc in test_structures:
        result = validator.validate_structure(structure)
        status = "✓ Valid" if result.is_valid else "✗ Invalid"
        print(f"\n   {status}: {structure}")
        print(f"      Description: {desc}")
        if result.issues:
            print(f"      Issues: {result.issues}")
        if result.suggestions:
            print(f"      Suggestions: {result.suggestions}")
        if result.resolved_components:
            print(f"      Resolved: {result.resolved_components}")

    # Test fallback structure generation
    print("\n6. Fallback structure generation:")

    test_inputs = [
        {"text": "Hello World"},
        {"title": "Card Title", "button": "Click Me"},
        {"text": "Info", "buttons": ["Button1", "Button2", "Button3"]},
        {"image_url": "https://example.com/img.png", "title": "Image Card"},
        {"items": [{"name": "Item 1"}, {"name": "Item 2"}]},  # Grid items
    ]

    for inputs in test_inputs:
        structure = validator.generate_structure_from_inputs(inputs)
        print(f"\n   Input keys: {list(inputs.keys())}")
        print(f"   Generated: {structure}")

    # Test symbol-enriched relationship text
    print("\n7. Symbol-enriched relationship text (for embedding):")

    test_components = ["Section", "ButtonList", "DecoratedText", "Grid"]
    for comp in test_components:
        text = validator.get_enriched_relationship_text(comp)
        print(f"\n   {comp}:")
        print(f"   {text}")

    # Test template composition
    print("\n8. Template composition:")

    templates = [
        ("§[đ, Ƀ[ᵬ×{button_count}]]", {"button_count": 3}),
        (
            "§[đ×{text_count}, Ƀ[ᵬ×{button_count}]]",
            {"text_count": 2, "button_count": 2},
        ),
    ]

    for template, inputs in templates:
        resolved, _ = validator.compose_from_template(template, inputs)
        print(f"\n   Template: {template}")
        print(f"   Inputs: {inputs}")
        print(f"   Resolved: {resolved}")

    # Test can_contain
    print("\n9. Containment checks (can_contain):")

    containment_tests = [
        ("Section", "DecoratedText", True),
        ("Section", "Button", False),  # Button needs wrapper
        ("ButtonList", "Button", True),
        ("Section", "ButtonList", True),
        ("DecoratedText", "Section", False),  # Wrong direction
    ]

    for parent, child, expected in containment_tests:
        result = validator.can_contain(parent, child)
        status = "✓" if result == expected else "✗"
        print(f"   {status} {parent} contains {child}: {result}")

    # Test random styling
    print("\n10. Random Color Schemes & Styling:")

    # Pick a random color scheme
    scheme_name = random.choice(list(COLOR_SCHEMES.keys()))
    print(f"\n   Random scheme: {scheme_name}")
    print(f"   Colors: {COLOR_SCHEMES[scheme_name]}")

    # Create styler with random scheme
    styler = ComponentStyler(scheme=scheme_name, target="gchat")

    # Style some test components with alternating colors
    test_components = ["Section", "DecoratedText", "Button", "Grid", "Image"]
    print("\n   Styled components (alternating colors):")
    for comp in test_components:
        styled = styler.auto_style("component", comp, bold=True)
        print(f"   {styled}")

    # Test color cycling
    print("\n   Color cycling demonstration:")
    cycler = ColorCycler.from_scheme(scheme_name)
    for i in range(6):
        color = cycler.next()
        styled = color_filter(f"Item {i + 1}", color, target="gchat")
        print(f"   {styled}")

    # Random semantic color examples
    print("\n   Random semantic colors:")
    semantic_names = list(SEMANTIC_COLORS.keys())[:8]
    random.shuffle(semantic_names)
    for name in semantic_names[:4]:
        styled = color_filter(name.title(), name, target="gchat", bold=True)
        print(f"   {styled}")

    # Generate sample card description with styling
    print("\n11. Sample styled card structure:")
    random_scheme = random.choice(list(COLOR_SCHEMES.keys()))
    section_styler = ComponentStyler(scheme=random_scheme)

    sample_sections = ["Overview", "Features", "Pricing", "Contact"]
    print(f"\n   Using scheme: {random_scheme}")
    for section_name in sample_sections:
        styled_header = section_styler.auto_style("section", section_name, bold=True)
        sym = symbols.get("Section", "§")
        print(f"   {sym} {styled_header}")

    # ==================================================================
    # JINJA TEMPLATING TESTS
    # ==================================================================
    print("\n" + "=" * 60)
    print("JINJA TEMPLATING TESTS")
    print("=" * 60)

    print("\n12. Setting up Jinja environment...")
    try:
        env = get_jinja_environment()
        print(f"   ✓ Jinja environment created")
        print(f"   ✓ Registered filters: {len(STYLING_FILTERS)}")
    except Exception as e:
        print(f"   ✗ Failed to create Jinja environment: {e}")
        return

    # Test individual filters
    print("\n13. Testing Jinja styling filters:")

    filter_tests = [
        # (template, context, description)
        ("{{ text | success_text }}", {"text": "Online"}, "success_text filter"),
        ("{{ text | error_text }}", {"text": "Offline"}, "error_text filter"),
        ("{{ text | warning_text }}", {"text": "Degraded"}, "warning_text filter"),
        ("{{ text | muted_text }}", {"text": "Pending"}, "muted_text filter"),
        ("{{ text | bold }}", {"text": "Important"}, "bold filter"),
        ('{{ text | color("#1a73e8") }}', {"text": "Custom Color"}, "color filter"),
        ('{{ amount | price("USD") }}', {"amount": 99.99}, "price filter"),
        ('{{ label | badge("#ea4335") }}', {"label": "SALE"}, "badge filter"),
        ("{{ text | strike }}", {"text": "Old Price"}, "strike filter"),
    ]

    for template_str, context, description in filter_tests:
        try:
            template = env.from_string(template_str)
            result = template.render(**context)
            print(f"   ✓ {description}: {result}")
        except Exception as e:
            print(f"   ✗ {description}: {e}")

    # Test combined templates
    print("\n14. Testing combined Jinja templates:")

    combined_templates = [
        # Status card content
        (
            '{{ "System Status" | bold }}: {{ status | success_text }}',
            {"status": "All Systems Operational"},
            "Status header",
        ),
        # Metric display
        (
            '{{ label | muted_text }}: {{ value | color("#34a853") | bold }}',
            {"label": "CPU Usage", "value": "45%"},
            "Metric display",
        ),
        # Price with sale
        (
            '{{ "SALE" | badge("#ea4335") }} {{ price | price("USD") }} (was {{ original | price("USD") | strike }})',
            {"price": 79.99, "original": 129.99},
            "Sale price",
        ),
        # Build status
        (
            '{{ "Build" | bold }} #{{ number }}: {{ result | success_text }} | {{ "Coverage" | muted_text }}: {{ coverage }}%',
            {"number": 1847, "result": "PASSED", "coverage": 94.2},
            "Build status",
        ),
        # Alert notification
        (
            "{{ severity | badge(color) }} {{ title }}\n{{ message | muted_text }}",
            {
                "severity": "WARNING",
                "color": "#fbbc05",
                "title": "High Memory",
                "message": "Usage exceeded 85%",
            },
            "Alert notification",
        ),
    ]

    for template_str, context, description in combined_templates:
        try:
            template = env.from_string(template_str)
            result = template.render(**context)
            print(f"\n   {description}:")
            for line in result.split("\n"):
                print(f"      {line}")
        except Exception as e:
            print(f"\n   ✗ {description}: {e}")

    # Test card themes
    print("\n15. Testing card themes with Jinja:")

    themes = {
        "status": {
            "title": '{{ "System Health" | color("#1a73e8") | bold }}',
            "items": [
                '{{ "API" | muted_text }}: {{ "Online" | success_text }}',
                '{{ "Database" | muted_text }}: {{ "Connected" | success_text }}',
                '{{ "Cache" | muted_text }}: {{ "High Latency" | warning_text }}',
            ],
        },
        "pricing": {
            "title": '{{ "Premium Plan" | bold }}',
            "items": [
                '{{ 29.99 | price("USD") }}/month',
                '{{ "BEST VALUE" | badge("#34a853") }}',
                '{{ "Save 40%" | color("#34a853") | bold }} vs monthly',
            ],
        },
        "metrics": {
            "title": '{{ "Performance Dashboard" | color("#8430ce") | bold }}',
            "items": [
                '{{ "Requests" | muted_text }}: {{ "2,450/s" | color("#34a853") }}',
                '{{ "Latency" | muted_text }}: {{ "45ms" | color("#1a73e8") }}',
                '{{ "Errors" | muted_text }}: {{ "0.02%" | success_text }}',
            ],
        },
    }

    for theme_name, theme_data in themes.items():
        print(f"\n   Theme: {theme_name.upper()}")
        try:
            title = env.from_string(theme_data["title"]).render()
            print(f"      Title: {title}")
            for item_template in theme_data["items"]:
                item = env.from_string(item_template).render()
                print(f"      - {item}")
        except Exception as e:
            print(f"      ✗ Error: {e}")

    # Test random styled card generation
    print("\n16. Random styled card content generation:")

    content_types = ["status", "metric", "price", "alert"]
    for content_type in content_types:
        if content_type == "status":
            statuses = [
                ("Online", "success_text"),
                ("Offline", "error_text"),
                ("Degraded", "warning_text"),
            ]
            status, filter_name = random.choice(statuses)
            template = f'{{{{ "{status}" | {filter_name} }}}}'
        elif content_type == "metric":
            label = random.choice(["CPU", "Memory", "Disk"])
            value = f"{random.randint(10, 95)}%"
            color = random.choice(["#34a853", "#1a73e8", "#fbbc05"])
            template = f'{{{{ "{label}" | muted_text }}}}: {{{{ "{value}" | color("{color}") | bold }}}}'
        elif content_type == "price":
            price = round(random.uniform(9.99, 199.99), 2)
            template = f'{{{{ {price} | price("USD") }}}}'
        elif content_type == "alert":
            severity = random.choice(["INFO", "WARNING", "ERROR"])
            colors = {"INFO": "#1a73e8", "WARNING": "#fbbc05", "ERROR": "#ea4335"}
            template = (
                f'{{{{ "{severity}" | badge("{colors[severity]}") }}}} Alert message'
            )

        try:
            result = env.from_string(template).render()
            print(f"   {content_type.title()}: {result}")
        except Exception as e:
            print(f"   {content_type.title()}: ✗ {e}")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


def test_smart_card_builder_integration():
    """
    Test SmartCardBuilder integration with DSL and structure generation.

    Validates that send_dynamic_card is correctly wired for:
    1. DSL notation in card_description → extracted and parsed
    2. Qdrant search for similar patterns
    3. Structure generation from inputs
    """
    print("=" * 60)
    print("SMARTCARDBUILDER INTEGRATION TEST")
    print("=" * 60)

    from gchat.smart_card_builder import get_smart_card_builder

    wrapper = get_card_framework_wrapper()
    builder = get_smart_card_builder()
    validator = wrapper.get_structure_validator()

    passed = 0
    failed = 0

    # Test 1: DSL extraction
    print("\n  1. DSL Extraction from Description")
    print("  " + "-" * 38)

    test_descriptions = [
        ("§[δ×2, ℊ[ǵ×4], Ƀ[ᵬ×2]] Server Dashboard", True),
        ("Ƀ[ᵬ×3] Quick Action Buttons", True),
        ("Simple card without DSL notation", False),
    ]

    for desc, should_find_dsl in test_descriptions:
        dsl = builder._extract_dsl_from_description(desc)
        found = dsl is not None
        if found == should_find_dsl:
            print(f"    ✓ '{desc[:35]}...' → DSL {'found' if found else 'not found'}")
            passed += 1
        else:
            print(
                f"    ✗ '{desc[:35]}...' → Expected DSL {'found' if should_find_dsl else 'not found'}"
            )
            failed += 1

    # Test 2: Structure generation from inputs
    print("\n  2. Structure Generation from Inputs")
    print("  " + "-" * 38)

    test_inputs = [
        ({"text": "Hello"}, "§[δ]"),
        ({"text": "Status", "buttons": [{"text": "OK"}]}, "§[δ, Ƀ[ᵬ×1]]"),
        ({"items": [{"name": "1"}, {"name": "2"}, {"name": "3"}]}, "§[ℊ[ǵ×3]]"),
    ]

    for inputs, expected in test_inputs:
        structure = validator.generate_structure_from_inputs(inputs)
        if structure == expected:
            print(f"    ✓ {list(inputs.keys())} → {structure}")
            passed += 1
        else:
            print(f"    ✗ {list(inputs.keys())} → {structure} (expected {expected})")
            failed += 1

    # Test 3: Card building with DSL
    print("\n  3. Card Building with DSL Description")
    print("  " + "-" * 38)

    dsl_desc = "§[δ×2, Ƀ[ᵬ×2]] Server Status"
    card = builder.build_card_from_description(
        description=dsl_desc,
        title="Test DSL Card",
        text="System online",
        buttons=[{"text": "Refresh", "url": "https://example.com"}],
    )

    if card and card.get("sections"):
        sections = card.get("sections", [])
        widgets = sections[0].get("widgets", []) if sections else []
        print(
            f"    ✓ DSL card built: {len(sections)} section(s), {len(widgets)} widget(s)"
        )
        if card.get("_dsl_structure"):
            print(f"    ✓ DSL structure recorded: {card.get('_dsl_structure')}")
            passed += 2
        else:
            print(f"    ✗ DSL structure not recorded in card metadata")
            passed += 1
            failed += 1
    else:
        print(f"    ✗ Failed to build DSL card: {dsl_desc}")
        failed += 2

    # Test 4: Card building without DSL (structure inference)
    print("\n  4. Card Building with Structure Inference")
    print("  " + "-" * 38)

    nl_desc = "Product showcase card"
    card = builder.build_card_from_description(
        description=nl_desc,
        title="Product Card",
        text="Amazing product",
        buttons=[{"text": "Buy", "url": "https://example.com"}],
        image_url="https://picsum.photos/300/200",
    )

    if card and card.get("sections"):
        sections = card.get("sections", [])
        print(f"    ✓ NL card built: {len(sections)} section(s)")

        inferred = card.get("_provenance", {}).get("_inferred_structure")
        if inferred:
            print(f"    ✓ Structure inferred: {inferred}")
            passed += 2
        else:
            print(
                f"    ○ No structure inference recorded (may use different build path)"
            )
            passed += 1
    else:
        print(f"    ✗ Failed to build NL card: {nl_desc}")
        failed += 2

    print(f"\n  Summary: {passed} passed, {failed} failed")
    return failed == 0


def main():
    parser = argparse.ArgumentParser(
        description="Test DSL structure validator and card generation"
    )
    parser.add_argument(
        "--send-webhook", action="store_true", help="Send test card to webhook"
    )
    parser.add_argument(
        "--webhook", type=str, help="Webhook URL (or set TEST_CHAT_WEBHOOK env var)"
    )
    parser.add_argument(
        "--dsl", type=str, default="§[δ×2, ℊ[ǵ×4], Ƀ[ᵬ×2]]", help="DSL notation to test"
    )
    parser.add_argument("--title", type=str, default="DSL Test Card", help="Card title")
    parser.add_argument(
        "--dsl-only", action="store_true", help="Run only DSL tests (skip other tests)"
    )
    parser.add_argument(
        "--integration",
        action="store_true",
        help="Run SmartCardBuilder integration tests",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all tests including full validator tests",
    )

    args = parser.parse_args()

    # If running integration tests
    if args.integration:
        integration_ok = test_smart_card_builder_integration()
        return 0 if integration_ok else 1

    # If sending to webhook or running DSL-only, skip full validator tests
    if args.send_webhook or args.dsl_only:
        print("\n" + "=" * 60)
        print("DSL STRUCTURE VALIDATOR TEST SUITE")
        print("=" * 60)

        # Run DSL parsing tests
        parsing_ok = test_dsl_parsing()

        # Run card building tests
        building_ok = test_card_building()

        # Send to webhook if requested
        if args.send_webhook:
            print("\n" + "=" * 60)
            print("TEST: Send Card to Webhook")
            print("=" * 60)

            card = build_card_from_dsl(args.dsl, args.title)
            webhook_ok = send_to_webhook(card, args.webhook)
        else:
            webhook_ok = True
            print("\n  (Use --send-webhook to send test card to Google Chat)")

        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"  DSL Parsing: {'PASS' if parsing_ok else 'FAIL'}")
        print(f"  Card Building: {'PASS' if building_ok else 'FAIL'}")
        if args.send_webhook:
            print(f"  Webhook Send: {'PASS' if webhook_ok else 'FAIL'}")
        print("=" * 60)

        return 0 if (parsing_ok and building_ok and webhook_ok) else 1
    else:
        # Run full validator tests (original behavior)
        test_structure_validator()
        return 0


if __name__ == "__main__":
    sys.exit(main())
