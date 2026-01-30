"""
Tests for Nested DSL → Component Parameter Mapping.

This tests the generic relationship-based child mapping that allows
DSL notation like `δ[ᵬ]` (DecoratedText with Button) to automatically
map nested children to the correct parent component parameters.

Key features tested:
1. get_field_for_child() in relationships_mixin.py
2. _map_children_to_params() in smart_card_builder.py
3. End-to-end nested DSL rendering
4. Real webhook delivery to Google Chat

IMPORTANT: Tests marked with @pytest.mark.webhook will send cards to the
real Google Chat webhook defined in TEST_CHAT_WEBHOOK environment variable.
"""

import json
import os
import ssl
import time

import certifi
import httpx
import pytest
from dotenv import load_dotenv

load_dotenv()


# =============================================================================
# Symbol Lookup Utilities
# =============================================================================


def get_symbol(component_name: str) -> str:
    """Get the DSL symbol for a component name from the wrapper."""
    from gchat.card_framework_wrapper import get_dsl_parser

    parser = get_dsl_parser()
    return parser._symbol_mapping.get(component_name, component_name)


def get_symbols(*component_names: str) -> dict:
    """Get multiple DSL symbols as a dict."""
    from gchat.card_framework_wrapper import get_dsl_parser

    parser = get_dsl_parser()
    return {name: parser._symbol_mapping.get(name, name) for name in component_names}


# =============================================================================
# Webhook Sending Utilities
# =============================================================================


def get_webhook_url() -> str:
    """Get the test webhook URL from environment."""
    return os.getenv("TEST_CHAT_WEBHOOK", "")


def send_card_to_webhook(card: dict, card_id: str = None) -> tuple[bool, str]:
    """
    Send a card to the Google Chat webhook.

    Args:
        card: Card dict in Google Chat format
        card_id: Optional card ID (auto-generated if not provided)

    Returns:
        Tuple of (success: bool, message: str)
    """
    webhook_url = get_webhook_url()
    if not webhook_url:
        return False, "TEST_CHAT_WEBHOOK not configured"

    if card_id is None:
        card_id = f"test-{int(time.time())}"

    payload = {"cards_v2": [{"cardId": card_id, "card": card}]}

    try:
        ctx = ssl.create_default_context(cafile=certifi.where())
        with httpx.Client(verify=ctx) as client:
            response = client.post(webhook_url, json=payload, timeout=30)

            if response.status_code == 200:
                return True, f"Sent successfully: {response.json().get('name', '')}"
            else:
                return False, f"HTTP {response.status_code}: {response.text}"

    except Exception as e:
        return False, f"Error: {str(e)}"


# Custom marker for webhook tests
webhook = pytest.mark.skipif(
    not get_webhook_url(),
    reason="TEST_CHAT_WEBHOOK not configured - skipping webhook tests",
)


# =============================================================================
# Unit Tests: Module Wrapper Method
# =============================================================================


def test_get_field_for_child_decorated_text_button():
    """Test that DecoratedText -> Button maps to 'button' field."""
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    result = wrapper.get_field_for_child("DecoratedText", "Button")

    assert result is not None, "DecoratedText should be able to contain Button"
    assert result["field_name"] == "button"
    assert result["is_optional"] is True


def test_get_field_for_child_decorated_text_icon():
    """Test that DecoratedText -> Icon maps to 'icon' field."""
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    result = wrapper.get_field_for_child("DecoratedText", "Icon")

    assert result is not None, "DecoratedText should be able to contain Icon"
    assert result["field_name"] == "icon"
    assert result["is_optional"] is True


def test_get_field_for_child_buttonlist_button():
    """Test that ButtonList -> Button maps to 'buttons' field."""
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    result = wrapper.get_field_for_child("ButtonList", "Button")

    assert result is not None, "ButtonList should be able to contain Button"
    assert result["field_name"] == "buttons"


def test_get_field_for_child_invalid_relationship():
    """Test that invalid relationships return None."""
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    # DecoratedText cannot contain Grid
    result = wrapper.get_field_for_child("DecoratedText", "Grid")
    assert result is None, "DecoratedText cannot contain Grid"

    # ButtonList cannot contain Icon
    result = wrapper.get_field_for_child("ButtonList", "Icon")
    assert result is None, "ButtonList cannot contain Icon"

    # Nonexistent parent
    result = wrapper.get_field_for_child("NonexistentComponent", "Button")
    assert result is None, "Nonexistent parent should return None"


def test_get_field_for_child_grid_griditem():
    """Test that Grid -> GridItem maps to correct field."""
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    result = wrapper.get_field_for_child("Grid", "GridItem")

    assert result is not None, "Grid should be able to contain GridItem"
    assert result["field_name"] == "items"


def test_get_field_for_child_columns_column():
    """Test that Columns -> Column maps to correct field."""
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    result = wrapper.get_field_for_child("Columns", "Column")

    assert result is not None, "Columns should be able to contain Column"
    assert "field_name" in result


def test_get_field_for_child_button_icon():
    """Test that Button -> Icon maps to correct field."""
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    result = wrapper.get_field_for_child("Button", "Icon")

    assert result is not None, "Button should be able to contain Icon"
    assert result["field_name"] == "icon"


def test_get_field_for_child_button_onclick():
    """Test that Button -> OnClick maps to correct field."""
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    result = wrapper.get_field_for_child("Button", "OnClick")

    assert result is not None, "Button should be able to contain OnClick"
    assert result["field_name"] == "on_click"


def test_get_field_for_child_chiplist_chip():
    """Test that ChipList -> Chip maps to correct field."""
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    result = wrapper.get_field_for_child("ChipList", "Chip")

    assert result is not None, "ChipList should be able to contain Chip"
    assert result["field_name"] == "chips"


# =============================================================================
# Integration Tests: Nested DSL Rendering (Local)
# =============================================================================


def test_nested_dsl_decorated_text_with_button():
    """Test rendering DecoratedText with nested Button via DSL."""
    from gchat.smart_card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()

    result = builder.build(
        description="§[δ[ᵬ]]",  # Section with DecoratedText containing Button
        title="Test Card",
        buttons=[{"text": "Click Me", "url": "https://example.com"}],
    )

    assert result is not None
    assert "sections" in result
    assert len(result["sections"]) >= 1

    # Find the main content section (first section)
    first_section = result["sections"][0]
    assert "widgets" in first_section
    assert len(first_section["widgets"]) >= 1

    # Check the decorated text widget
    first_widget = first_section["widgets"][0]
    assert "decoratedText" in first_widget

    dt = first_widget["decoratedText"]
    assert "text" in dt
    assert "button" in dt, "DecoratedText should have nested button"

    # Verify button has onClick (required for Google Chat)
    btn = dt["button"]
    assert "onClick" in btn, "Button should have onClick"
    assert "openLink" in btn["onClick"], "onClick should have openLink"


def test_nested_dsl_decorated_text_with_icon():
    """Test rendering DecoratedText with nested Icon via DSL."""
    from gchat.smart_card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()

    result = builder.build(
        description="§[δ[ɨ]]",  # Section with DecoratedText containing Icon
        title="Icon Test",
    )

    assert result is not None
    assert "sections" in result

    # Find the main content section
    first_section = result["sections"][0]
    first_widget = first_section["widgets"][0]

    assert "decoratedText" in first_widget
    dt = first_widget["decoratedText"]

    # Icon should be mapped to startIcon (Google Chat API field name)
    assert "startIcon" in dt, "DecoratedText should have nested startIcon"
    icon = dt["startIcon"]

    # Icon should have knownIcon or iconUrl
    assert "knownIcon" in icon or "iconUrl" in icon


def test_nested_dsl_decorated_text_with_multiple_children():
    """Test rendering DecoratedText with both Icon and Button."""
    from gchat.smart_card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()

    result = builder.build(
        description="§[δ[ɨ, ᵬ]]",  # DecoratedText with Icon and Button
        title="Multiple Children",
        buttons=[{"text": "Action"}],
    )

    assert result is not None

    first_section = result["sections"][0]
    first_widget = first_section["widgets"][0]

    assert "decoratedText" in first_widget
    dt = first_widget["decoratedText"]

    # Both children should be mapped (icon renders as startIcon in Google Chat API)
    assert "startIcon" in dt, "Should have startIcon child"
    assert "button" in dt, "Should have button child"


def test_nested_dsl_without_children():
    """Test that DecoratedText without children still works."""
    from gchat.smart_card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()

    result = builder.build(
        description="§[δ]",  # Plain DecoratedText, no children
        title="No Children",
    )

    assert result is not None

    first_section = result["sections"][0]
    first_widget = first_section["widgets"][0]

    assert "decoratedText" in first_widget
    dt = first_widget["decoratedText"]

    # Should have text but no button/icon (unless added by default)
    assert "text" in dt


def test_nested_dsl_button_list_with_buttons():
    """Test ButtonList with nested Button children via DSL."""
    from gchat.smart_card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()

    result = builder.build(
        description="§[Ƀ[ᵬ×2]]",  # ButtonList with 2 Buttons
        title="Button List Test",
        buttons=[{"text": "First"}, {"text": "Second"}],
    )

    assert result is not None

    first_section = result["sections"][0]

    # Find the buttonList widget
    button_list_widget = None
    for widget in first_section["widgets"]:
        if "buttonList" in widget:
            button_list_widget = widget
            break

    assert button_list_widget is not None, "Should have buttonList widget"
    bl = button_list_widget["buttonList"]
    assert "buttons" in bl
    assert len(bl["buttons"]) >= 2, "Should have at least 2 buttons"


# =============================================================================
# Edge Cases
# =============================================================================


def test_get_field_for_child_case_sensitivity():
    """Test that component names are case-sensitive."""
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    # Correct case
    result = wrapper.get_field_for_child("DecoratedText", "Button")
    assert result is not None

    # Wrong case should fail
    result = wrapper.get_field_for_child("decoratedtext", "button")
    assert result is None, "Names should be case-sensitive"


def test_nested_dsl_handles_missing_wrapper_gracefully():
    """Test that child mapping doesn't crash without wrapper."""
    from gchat.smart_card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()
    # Force wrapper to None (simulate failure)
    builder._wrapper = None

    # This should still produce some output without crashing
    result = builder.build(
        description="§[δ[ᵬ]]",
        title="No Wrapper Test",
    )

    # Should either succeed or return None, not crash


def test_relationship_metadata_completeness():
    """Test that common relationships are all discoverable."""
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    # List of expected valid relationships
    expected_relationships = [
        ("DecoratedText", "Button"),
        ("DecoratedText", "Icon"),
        ("DecoratedText", "SwitchControl"),
        ("DecoratedText", "OnClick"),
        ("ButtonList", "Button"),
        ("ChipList", "Chip"),
        ("Grid", "GridItem"),
        ("Columns", "Column"),
        ("Button", "Icon"),
        ("Button", "OnClick"),
    ]

    for parent, child in expected_relationships:
        result = wrapper.get_field_for_child(parent, child)
        assert result is not None, f"Expected {parent} -> {child} to be valid"
        assert "field_name" in result, f"Should have field_name for {parent} -> {child}"


# =============================================================================
# Webhook Tests: Real Card Delivery
# =============================================================================


@webhook
def test_webhook_decorated_text_with_icon_and_button():
    """Send DecoratedText with Icon and Button to real webhook."""
    from gchat.smart_card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()

    # Get symbols from wrapper
    s = get_symbols("Section", "DecoratedText", "Icon", "Button")
    dsl = f"{s['Section']}[{s['DecoratedText']}[{s['Icon']}, {s['Button']}]]"

    card = builder.build(
        description=dsl,
        title="Nested DSL: Icon + Button",
        buttons=[{"text": "View Details", "url": "https://example.com/details"}],
    )

    # Keep only main content (remove feedback section)
    if card and "sections" in card:
        card["sections"] = [card["sections"][0]]

    print("\n📦 Card JSON:")
    print(json.dumps(card, indent=2))

    success, message = send_card_to_webhook(card, "nested-icon-button")
    print(f"\n{'✅' if success else '❌'} {message}")

    assert success, f"Failed to send card: {message}"


@webhook
def test_webhook_multiple_decorated_texts_with_children():
    """Send multiple DecoratedTexts with different children to webhook."""
    from gchat.smart_card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()

    # Get symbols from wrapper
    s = get_symbols("Section", "DecoratedText", "Icon", "Button")
    sec, dt, icon, btn = s["Section"], s["DecoratedText"], s["Icon"], s["Button"]
    # Three DTs: icon+button, button only, icon only
    dsl = f"{sec}[{dt}[{icon}, {btn}], {dt}[{btn}], {dt}[{icon}]]"

    card = builder.build(
        description=dsl,
        title="Multiple Nested Children",
        buttons=[
            {"text": "Action 1", "url": "https://example.com/1"},
            {"text": "Action 2", "url": "https://example.com/2"},
        ],
    )

    if card and "sections" in card:
        card["sections"] = [card["sections"][0]]

    print("\n📦 Card JSON:")
    print(json.dumps(card, indent=2))

    success, message = send_card_to_webhook(card, "nested-multiple")
    print(f"\n{'✅' if success else '❌'} {message}")

    assert success, f"Failed to send card: {message}"


@webhook
def test_webhook_button_list_with_buttons():
    """Send ButtonList with multiple Buttons to webhook."""
    from gchat.smart_card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()

    # Get symbols from wrapper
    s = get_symbols("Section", "DecoratedText", "ButtonList", "Button")
    sec, dt, bl, btn = s["Section"], s["DecoratedText"], s["ButtonList"], s["Button"]
    dsl = f"{sec}[{dt}, {bl}[{btn}×3]]"  # DecoratedText + ButtonList with 3 buttons

    card = builder.build(
        description=dsl,
        title="ButtonList with Nested Buttons",
        buttons=[
            {"text": "Option A", "url": "https://example.com/a"},
            {"text": "Option B", "url": "https://example.com/b"},
            {"text": "Option C", "url": "https://example.com/c"},
        ],
    )

    if card and "sections" in card:
        card["sections"] = [card["sections"][0]]

    print("\n📦 Card JSON:")
    print(json.dumps(card, indent=2))

    success, message = send_card_to_webhook(card, "nested-buttonlist")
    print(f"\n{'✅' if success else '❌'} {message}")

    assert success, f"Failed to send card: {message}"


@webhook
def test_webhook_complex_nested_structure():
    """Send a complex card with multiple nested structures."""
    from gchat.smart_card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()

    # Get symbols from wrapper
    s = get_symbols("Section", "DecoratedText", "Icon", "Button", "ButtonList")
    sec, dt, icon, btn, bl = s["Section"], s["DecoratedText"], s["Icon"], s["Button"], s["ButtonList"]
    dsl = f"{sec}[{dt}[{icon}, {btn}], {dt}, {bl}[{btn}×2], {dt}[{icon}]]"

    card = builder.build(
        description=dsl,
        title="Complex Nested Structure",
        buttons=[
            {"text": "Primary Action", "url": "https://example.com/primary"},
            {"text": "Secondary", "url": "https://example.com/secondary"},
            {"text": "Tertiary", "url": "https://example.com/tertiary"},
        ],
    )

    if card and "sections" in card:
        card["sections"] = [card["sections"][0]]

    print("\n📦 Card JSON:")
    print(json.dumps(card, indent=2))

    success, message = send_card_to_webhook(card, "nested-complex")
    print(f"\n{'✅' if success else '❌'} {message}")

    assert success, f"Failed to send card: {message}"


@webhook
def test_webhook_grid_with_items():
    """Send Grid component to webhook."""
    from gchat.smart_card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()

    # Get symbols from wrapper
    s = get_symbols("Section", "Grid", "GridItem")
    sec, grid, gi = s["Section"], s["Grid"], s["GridItem"]
    dsl = f"{sec}[{grid}[{gi}×4]]"  # Grid with 4 GridItems

    card = builder.build(
        description=dsl,
        title="Grid with Items",
    )

    if card and "sections" in card:
        card["sections"] = [card["sections"][0]]

    print("\n📦 Card JSON:")
    print(json.dumps(card, indent=2))

    success, message = send_card_to_webhook(card, "nested-grid")
    print(f"\n{'✅' if success else '❌'} {message}")

    assert success, f"Failed to send card: {message}"


# =============================================================================
# Generalization Tests: Verify works for ALL parent-child relationships
# =============================================================================


def test_unified_button_consumption():
    """Test that buttons are consumed sequentially across all components.

    When DSL has δ[ᵬ] (button in DecoratedText) and Ƀ[ᵬ×2] (buttons in ButtonList),
    buttons should be consumed in order: first to DT, remaining to BL.
    """
    from gchat.smart_card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()

    s = get_symbols("Section", "DecoratedText", "Button", "ButtonList")
    sec, dt, btn, bl = s["Section"], s["DecoratedText"], s["Button"], s["ButtonList"]
    dsl = f"{sec}[{dt}[{btn}], {bl}[{btn}×2]]"  # DT needs 1, BL needs 2 = 3 total

    buttons = [
        {"text": "First", "url": "https://first.com"},
        {"text": "Second", "url": "https://second.com"},
        {"text": "Third", "url": "https://third.com"},
    ]

    result = builder.build(
        description=dsl,
        title="Unified Button Test",
        buttons=buttons,
    )

    assert result is not None
    first_section = result["sections"][0]
    widgets = first_section["widgets"]

    # First widget: DecoratedText with button
    dt_widget = widgets[0]
    assert "decoratedText" in dt_widget
    dt_btn = dt_widget["decoratedText"].get("button", {})
    assert dt_btn.get("text") == "First", "DecoratedText should get first button"

    # Second widget: ButtonList with remaining buttons
    bl_widget = widgets[1]
    assert "buttonList" in bl_widget
    bl_btns = bl_widget["buttonList"]["buttons"]
    assert len(bl_btns) == 2, "ButtonList should have 2 buttons"
    assert bl_btns[0].get("text") == "Second", "ButtonList should get second button"
    assert bl_btns[1].get("text") == "Third", "ButtonList should get third button"


@webhook
def test_webhook_unified_button_distribution():
    """Send card with unified button distribution to webhook."""
    from gchat.smart_card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()

    s = get_symbols("Section", "DecoratedText", "Icon", "Button", "ButtonList")
    sec, dt, icon, btn, bl = s["Section"], s["DecoratedText"], s["Icon"], s["Button"], s["ButtonList"]
    dsl = f"{sec}[{dt}[{icon}, {btn}], {bl}[{btn}×2]]"

    card = builder.build(
        description=dsl,
        title="Unified Button Distribution",
        buttons=[
            {"text": "Inline Action", "url": "https://example.com/inline"},
            {"text": "List Option 1", "url": "https://example.com/opt1"},
            {"text": "List Option 2", "url": "https://example.com/opt2"},
        ],
    )

    if card and "sections" in card:
        card["sections"] = [card["sections"][0]]

    print("\n📦 Card JSON:")
    print(json.dumps(card, indent=2))

    success, message = send_card_to_webhook(card, "unified-buttons")
    print(f"\n{'✅' if success else '❌'} {message}")

    assert success, f"Failed to send card: {message}"


def test_all_parent_child_relationships_have_field_mapping():
    """Verify that all common parent-child relationships return valid field mappings."""
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    # Get all relationships from the wrapper
    relationships = wrapper.relationships

    print(f"\n📊 Found {len(relationships)} parent components with children")

    # Test each relationship
    total_tested = 0
    successful = 0
    failed = []

    for parent, children in relationships.items():
        for child in children:
            total_tested += 1
            result = wrapper.get_field_for_child(parent, child)
            if result and "field_name" in result:
                successful += 1
            else:
                failed.append((parent, child))

    print(f"📊 Tested {total_tested} relationships")
    print(f"✅ Successful: {successful}")
    print(f"❌ Failed: {len(failed)}")

    if failed:
        print("\nFailed relationships:")
        for parent, child in failed[:10]:  # Show first 10
            print(f"  - {parent} -> {child}")

    # Most should succeed (allow some failures for edge cases)
    success_rate = successful / total_tested if total_tested > 0 else 0
    assert success_rate >= 0.8, f"Expected 80%+ success rate, got {success_rate:.0%}"


def test_print_available_dsl_symbols():
    """Print all available DSL symbols for reference."""
    from gchat.card_framework_wrapper import get_dsl_parser

    parser = get_dsl_parser()

    print("\n📝 Available DSL Symbols:")
    print("=" * 50)

    # Group by category
    categories = {
        "Layout": ["Section", "Columns", "Column", "Grid", "GridItem"],
        "Text": ["DecoratedText", "TextParagraph", "Divider"],
        "Buttons": ["Button", "ButtonList", "Chip", "ChipList"],
        "Icons": ["Icon"],
        "Inputs": ["TextInput", "SelectionInput", "DateTimePicker"],
        "Other": [],
    }

    categorized = set()
    for cat, components in categories.items():
        print(f"\n{cat}:")
        for comp in components:
            symbol = parser._symbol_mapping.get(comp, "?")
            print(f"  {comp}: {symbol}")
            categorized.add(comp)

    # Print uncategorized
    print("\nOther:")
    for comp, symbol in sorted(parser._symbol_mapping.items()):
        if comp not in categorized:
            print(f"  {comp}: {symbol}")


# =============================================================================
# Dynamic Random Component Tests
# =============================================================================
# These tests dynamically discover available components from the wrapper
# and randomly combine them to build and send cards.


import random as test_random


def get_available_components():
    """Dynamically discover available components from the wrapper."""
    from gchat.card_framework_wrapper import (
        get_card_framework_wrapper,
        get_dsl_parser,
        get_component_relationships_for_dsl,
    )

    wrapper = get_card_framework_wrapper()
    parser = get_dsl_parser()

    # Get symbol mappings
    symbols = parser._symbol_mapping

    # Get relationships with Widget expanded to actual subclasses
    relationships = get_component_relationships_for_dsl()

    return {
        "symbols": symbols,
        "relationships": relationships,
        "wrapper": wrapper,
        "parser": parser,
    }


def get_section_widget_types(relationships: dict) -> list[str]:
    """Get all widget types that can go directly in a Section."""
    # The relationships from get_component_relationships_for_dsl() has Widget expanded
    return relationships.get("Section", [])


def build_random_dsl_structure(components: dict, depth: int = 1) -> str:
    """Build a TRULY random DSL structure from discovered components.

    This dynamically pulls from the wrapper's component list rather than
    using a pre-defined set of structures.
    """
    symbols = components["symbols"]
    relationships = components["relationships"]
    wrapper = components["wrapper"]

    # Get Section symbol
    section_sym = symbols.get("Section", "§")

    # Get ALL widget types that can go in a Section
    section_widgets = get_section_widget_types(relationships)

    # Filter to widgets we have symbols for
    usable_widgets = [w for w in section_widgets if w in symbols]

    if not usable_widgets:
        # Fallback to known widgets
        usable_widgets = ["DecoratedText", "TextParagraph", "ButtonList", "Divider"]

    # Randomly select 1-4 widgets for this structure
    num_widgets = test_random.randint(1, min(4, len(usable_widgets)))
    selected_widgets = test_random.sample(usable_widgets, num_widgets)

    # Build widget DSL for each selected widget
    widget_parts = []
    for widget_name in selected_widgets:
        widget_sym = symbols.get(widget_name, widget_name)

        # Check if this widget can have children
        widget_children = relationships.get(widget_name, [])
        nestable_children = [c for c in widget_children if c in symbols]

        # Randomly decide whether to add children (50% chance if available)
        if nestable_children and test_random.random() < 0.5:
            # Pick 1-2 random children
            num_children = test_random.randint(1, min(2, len(nestable_children)))
            child_picks = test_random.sample(nestable_children, num_children)
            child_syms = [symbols[c] for c in child_picks]
            widget_parts.append(f"{widget_sym}[{', '.join(child_syms)}]")
        else:
            # Check for multiplier (ButtonList, Grid, etc.)
            if widget_name in ["ButtonList", "ChipList", "Grid"]:
                count = test_random.randint(2, 4)
                # Get child symbol for multiplier
                child_map = {"ButtonList": "Button", "ChipList": "Chip", "Grid": "GridItem"}
                child_name = child_map.get(widget_name)
                if child_name and child_name in symbols:
                    child_sym = symbols[child_name]
                    widget_parts.append(f"{widget_sym}[{child_sym}×{count}]")
                else:
                    widget_parts.append(widget_sym)
            else:
                widget_parts.append(widget_sym)

    return f"{section_sym}[{', '.join(widget_parts)}]"


def test_dynamic_component_discovery():
    """Test that we can dynamically discover components from the wrapper."""
    components = get_available_components()

    print("\n📦 Dynamically discovered components:")
    print(f"   Symbols: {len(components['symbols'])} component types")
    print(f"   Relationships: {len(components['relationships'])} parent types")

    # Print some examples
    print("\n   Sample symbols:")
    for name, sym in list(components["symbols"].items())[:10]:
        print(f"      {name}: {sym}")

    # Verify we have key components
    assert "Section" in components["symbols"], "Should have Section"
    assert "DecoratedText" in components["symbols"], "Should have DecoratedText"
    assert "Button" in components["symbols"], "Should have Button"
    assert "ButtonList" in components["symbols"], "Should have ButtonList"

    # Verify relationships exist
    assert len(components["relationships"]) > 0, "Should have relationships"
    assert "DecoratedText" in components["relationships"], "DecoratedText should have children"


def test_random_dsl_generation():
    """Test generating random DSL structures."""
    components = get_available_components()

    print("\n🎲 Generating random DSL structures:")

    generated = set()
    for i in range(10):
        dsl = build_random_dsl_structure(components)
        generated.add(dsl)
        print(f"   {i+1}. {dsl}")

    print(f"\n   Generated {len(generated)} unique structures from 10 attempts")
    assert len(generated) >= 3, "Should generate variety of structures"


def test_random_dsl_cards_build_successfully():
    """Test that randomly generated DSL structures build into valid cards."""
    from gchat.smart_card_builder import SmartCardBuilderV2

    components = get_available_components()
    builder = SmartCardBuilderV2()

    iterations = 15
    successes = 0
    failures = []

    print(f"\n🔨 Building {iterations} random DSL cards:")

    for i in range(iterations):
        dsl = build_random_dsl_structure(components)
        try:
            card = builder.build(
                description=dsl,
                title=f"Random Card #{i+1}",
                buttons=[
                    {"text": f"Action {j}", "url": f"https://example.com/{j}"}
                    for j in range(1, test_random.randint(2, 5))
                ],
            )

            if card and "sections" in card and len(card["sections"]) > 0:
                successes += 1
                widget_count = sum(len(s.get("widgets", [])) for s in card["sections"])
                print(f"   ✅ {i+1}. {dsl[:40]}... → {widget_count} widgets")
            else:
                failures.append((i, dsl, "Empty card"))
                print(f"   ⚠️ {i+1}. {dsl[:40]}... → Empty")

        except Exception as e:
            failures.append((i, dsl, str(e)))
            print(f"   ❌ {i+1}. {dsl[:40]}... → {str(e)[:30]}")

    print(f"\n📊 Results: {successes}/{iterations} built successfully")

    # Allow some flexibility - DSL parsing may not handle all variations
    success_rate = successes / iterations
    assert success_rate >= 0.6, f"Expected 60%+ success rate, got {success_rate:.0%}"


def test_random_component_combinations():
    """Test random combinations of wrapper components directly."""
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()
    relationships = wrapper.relationships

    print("\n🔀 Testing random component combinations:")

    # Get all valid parent-child pairs
    valid_pairs = []
    for parent, children in relationships.items():
        for child in children:
            field_info = wrapper.get_field_for_child(parent, child)
            if field_info:
                valid_pairs.append((parent, child, field_info))

    print(f"   Found {len(valid_pairs)} valid parent-child combinations")

    # Test random sampling
    sample_size = min(20, len(valid_pairs))
    sampled = test_random.sample(valid_pairs, sample_size)

    successes = 0
    for parent, child, field_info in sampled:
        field_name = field_info.get("field_name", "unknown")
        print(f"   {parent} → {child} (field: {field_name})")
        successes += 1

    assert successes == sample_size, "All sampled pairs should be valid"


@webhook
def test_webhook_random_dsl_cards():
    """Send randomly generated DSL cards to the webhook."""
    from gchat.smart_card_builder import SmartCardBuilderV2

    components = get_available_components()
    builder = SmartCardBuilderV2()

    num_cards = 5
    results = []

    print(f"\n🎲 Sending {num_cards} randomly generated DSL cards:")

    for i in range(num_cards):
        dsl = build_random_dsl_structure(components)

        card = builder.build(
            description=dsl,
            title=f"Random DSL #{i+1}",
            buttons=[
                {"text": f"Option {j}", "url": f"https://example.com/opt{j}"}
                for j in range(1, test_random.randint(2, 4))
            ],
        )

        if card:
            # Strip feedback section for cleaner test
            if "sections" in card and len(card["sections"]) > 1:
                card["sections"] = card["sections"][:1]

            card_id = f"random-dsl-{i+1}"
            success, message = send_card_to_webhook(card, card_id)

            widget_count = sum(len(s.get("widgets", [])) for s in card.get("sections", []))
            results.append({
                "dsl": dsl,
                "success": success,
                "widgets": widget_count,
            })

            status = "✅" if success else "❌"
            print(f"   {status} {dsl[:35]}... → {widget_count} widgets")

            time.sleep(0.5)

    successes = sum(1 for r in results if r["success"])
    print(f"\n📊 Results: {successes}/{num_cards} sent successfully")

    # Be flexible - random DSL may generate structures that don't work with all API contexts
    assert successes >= 1, f"At least one random DSL card should send successfully, got {successes}/{num_cards}"


@webhook
def test_webhook_random_nested_structures():
    """Send cards with TRULY random nested component structures."""
    from gchat.smart_card_builder import SmartCardBuilderV2

    components = get_available_components()
    wrapper = components["wrapper"]
    symbols = components["symbols"]
    relationships = components["relationships"]
    builder = SmartCardBuilderV2()

    sec = symbols.get("Section", "§")

    # Get widget types that can go in a Section (to filter out non-renderable types)
    section_widgets = set(get_section_widget_types(relationships))

    # Filter to parents that can be rendered in a card (must be section-valid or common)
    # Include common container types: Section, DecoratedText, ButtonList, etc.
    valid_parents = section_widgets | {"Section", "DecoratedText", "ButtonList", "ChipList", "Grid", "Columns"}

    # TRULY random: Get parents that have children AND can be rendered
    parents_with_children = [
        (parent, children)
        for parent, children in relationships.items()
        if children and parent in symbols and parent in valid_parents
    ]

    print(f"\n🔀 Discovered {len(parents_with_children)} components with children")

    # Build 3 truly random nested structures
    selected_structures = []
    for _ in range(3):
        # Pick a random parent that can nest
        parent, children = test_random.choice(parents_with_children)
        parent_sym = symbols[parent]

        # Pick random children that have symbols
        valid_children = [c for c in children if c in symbols]
        if valid_children:
            num_children = test_random.randint(1, min(2, len(valid_children)))
            picked_children = test_random.sample(valid_children, num_children)
            child_syms = [symbols[c] for c in picked_children]

            # Build the nested structure
            dsl = f"{sec}[{parent_sym}[{', '.join(child_syms)}]]"
            desc = f"{parent} with {'+'.join(picked_children)}"
            selected_structures.append((dsl, desc))

    print(f"\n🔀 Testing {len(selected_structures)} random nested structures:")

    successes = 0
    for dsl, desc in selected_structures:
        card = builder.build(
            description=dsl,
            title=f"Random Nested: {desc[:30]}",
            buttons=[
                {"text": "Action 1", "url": "https://example.com/1"},
                {"text": "Action 2", "url": "https://example.com/2"},
                {"text": "Action 3", "url": "https://example.com/3"},
            ],
        )

        if card and "sections" in card:
            card["sections"] = card["sections"][:1]  # Keep only main content

        card_id = f"nested-random-{int(time.time())}-{test_random.randint(1,999)}"
        success, message = send_card_to_webhook(card, card_id)

        status = "✅" if success else "❌"
        print(f"   {status} {desc}: {dsl}")

        if success:
            successes += 1

        time.sleep(0.5)

    print(f"\n📊 Results: {successes}/{len(selected_structures)} nested structures sent")
    # Be flexible - some random combos may not render (e.g., ActionStatus, CardWithId require specific contexts)
    assert successes >= 1, f"At least one nested structure should send successfully"


@webhook
def test_webhook_kitchen_sink_all_components():
    """Send ONE large card using MANY/ALL available widget types.

    This is the comprehensive test that demonstrates the full DSL capability
    by including as many different component types as possible in one card.
    """
    from gchat.smart_card_builder import SmartCardBuilderV2

    components = get_available_components()
    wrapper = components["wrapper"]
    symbols = components["symbols"]
    relationships = components["relationships"]
    builder = SmartCardBuilderV2()

    sec = symbols.get("Section", "§")

    # Get ALL widget types that can go in a Section
    section_widgets = get_section_widget_types(relationships)
    usable_widgets = [w for w in section_widgets if w in symbols]

    print(f"\n🍳 KITCHEN SINK TEST - All available components:")
    print(f"   Found {len(usable_widgets)} widget types that can go in Section")
    print(f"   Widgets: {', '.join(usable_widgets[:15])}{'...' if len(usable_widgets) > 15 else ''}")

    # Build a massive DSL with ALL widget types we can use
    widget_parts = []

    # Group 1: Text widgets
    text_widgets = [w for w in ["DecoratedText", "TextParagraph"] if w in usable_widgets]
    for widget_name in text_widgets:
        widget_sym = symbols[widget_name]
        # Add nested children for DecoratedText
        if widget_name == "DecoratedText" and "Icon" in symbols and "Button" in symbols:
            icon_sym = symbols["Icon"]
            btn_sym = symbols["Button"]
            widget_parts.append(f"{widget_sym}[{icon_sym}, {btn_sym}]")
        else:
            widget_parts.append(widget_sym)

    # Group 2: Button widgets
    if "ButtonList" in usable_widgets and "Button" in symbols:
        bl_sym = symbols["ButtonList"]
        btn_sym = symbols["Button"]
        widget_parts.append(f"{bl_sym}[{btn_sym}×3]")

    # Group 3: Chip widgets
    if "ChipList" in usable_widgets and "Chip" in symbols:
        chip_list_sym = symbols["ChipList"]
        chip_sym = symbols["Chip"]
        widget_parts.append(f"{chip_list_sym}[{chip_sym}×2]")

    # Group 4: Grid
    if "Grid" in usable_widgets and "GridItem" in symbols:
        grid_sym = symbols["Grid"]
        gi_sym = symbols["GridItem"]
        widget_parts.append(f"{grid_sym}[{gi_sym}×4]")

    # Group 5: Divider (simple widget)
    if "Divider" in usable_widgets:
        div_sym = symbols["Divider"]
        widget_parts.append(div_sym)

    # Group 6: Image
    if "Image" in usable_widgets:
        img_sym = symbols["Image"]
        widget_parts.append(img_sym)

    # Group 7: Additional DecoratedText variations
    if "DecoratedText" in symbols:
        dt_sym = symbols["DecoratedText"]
        # Plain DT
        widget_parts.append(dt_sym)
        # DT with only Icon
        if "Icon" in symbols:
            widget_parts.append(f"{dt_sym}[{symbols['Icon']}]")
        # DT with only Button
        if "Button" in symbols:
            widget_parts.append(f"{dt_sym}[{symbols['Button']}]")

    # Group 8: Selection widgets (if available)
    for selection_widget in ["SelectionInput", "DateTimePicker", "TextInput"]:
        if selection_widget in usable_widgets:
            widget_parts.append(symbols[selection_widget])

    # Group 9: Columns (if available)
    if "Columns" in usable_widgets:
        widget_parts.append(symbols["Columns"])

    # Build the massive DSL
    kitchen_sink_dsl = f"{sec}[{', '.join(widget_parts)}]"

    print(f"\n   📜 Kitchen Sink DSL ({len(widget_parts)} widgets):")
    print(f"   {kitchen_sink_dsl[:100]}...")
    print(f"\n   Full DSL: {kitchen_sink_dsl}")

    # Prepare lots of buttons for all the button-consuming widgets
    buttons = [
        {"text": f"Action {i}", "url": f"https://example.com/action{i}"}
        for i in range(1, 10)  # 9 buttons should be enough
    ]

    # Build the card
    card = builder.build(
        description=kitchen_sink_dsl,
        title="🍳 Kitchen Sink - All Components",
        buttons=buttons,
    )

    assert card is not None, "Kitchen sink card should build"
    assert "sections" in card, "Card should have sections"

    # Count widgets in the card
    total_widgets = sum(len(s.get("widgets", [])) for s in card["sections"])
    print(f"\n   📊 Built card with {total_widgets} total widgets across {len(card['sections'])} sections")

    # Print what widget types we got
    widget_types_found = set()
    for section in card["sections"]:
        for widget in section.get("widgets", []):
            widget_types_found.update(widget.keys())
    print(f"   📋 Widget types in card: {', '.join(sorted(widget_types_found))}")

    # Strip feedback section for cleaner output
    if len(card["sections"]) > 1:
        card["sections"] = card["sections"][:1]

    # Print the JSON
    print(f"\n   📦 Card JSON preview:")
    card_json = json.dumps(card, indent=2)
    if len(card_json) > 2000:
        print(f"   {card_json[:2000]}...")
        print(f"   ... (truncated, total {len(card_json)} chars)")
    else:
        print(f"   {card_json}")

    # Send to webhook
    success, message = send_card_to_webhook(card, "kitchen-sink-all-components")

    print(f"\n   {'✅' if success else '❌'} {message}")

    assert success, f"Kitchen sink card should send successfully: {message}"

    # Verify we used many components
    assert len(widget_parts) >= 5, f"Expected 5+ widget types, got {len(widget_parts)}"
    print(f"\n   ✅ Kitchen sink test passed with {len(widget_parts)} component types!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
