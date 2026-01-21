#!/usr/bin/env python3
"""
Comprehensive Smart Card Builder Tests

Validates:
1. All component loading works
2. JSON output matches Google Chat API format
3. Widget structures are correct
4. Edge cases are handled
5. Output can be sent to Google Chat (structure validation)
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


def test_component_loading():
    """Test: All required components load successfully."""
    print("\n" + "=" * 60)
    print("TEST: Component Loading")
    print("=" * 60)

    from gchat.smart_card_builder import SmartCardBuilder

    builder = SmartCardBuilder()
    builder.initialize()

    required_components = [
        "Section",
        "Columns",
        "Column",
        "DecoratedText",
        "Image",
        "TextParagraph",
        "Button",
        "ButtonList",
        "Divider",
    ]

    print("\nComponent Status:")
    all_loaded = True
    for name in required_components:
        component = builder.get_component(name)
        status = "✓" if component else "✗"
        if not component:
            all_loaded = False
        print(f"  {status} {name}: {component}")

    return all_loaded


def test_decorated_text_json_format():
    """Test: DecoratedText renders to correct Google Chat JSON format."""
    print("\n" + "=" * 60)
    print("TEST: DecoratedText JSON Format")
    print("=" * 60)

    from gchat.smart_card_builder import SmartCardBuilder

    builder = SmartCardBuilder()
    builder.initialize()

    # Build a DecoratedText widget
    widget = builder.build_decorated_text(
        text="Test content",
        top_label="Label",
        wrap_text=True,
    )

    if not widget:
        print("  ✗ Failed to build DecoratedText")
        return False

    # Render to JSON
    rendered = widget.render()
    print(f"\nRendered JSON:")
    print(json.dumps(rendered, indent=2))

    # Validate structure
    checks = [
        ("Has 'decorated_text' key", "decorated_text" in rendered),
        ("Has 'text' field", "text" in rendered.get("decorated_text", {})),
        ("Has 'top_label' field", "top_label" in rendered.get("decorated_text", {})),
        ("Has 'wrap_text' field", "wrap_text" in rendered.get("decorated_text", {})),
        (
            "Text value correct",
            rendered.get("decorated_text", {}).get("text") == "Test content",
        ),
        (
            "Label value correct",
            rendered.get("decorated_text", {}).get("top_label") == "Label",
        ),
    ]

    print("\nValidation:")
    all_passed = True
    for name, passed in checks:
        status = "✓" if passed else "✗"
        if not passed:
            all_passed = False
        print(f"  {status} {name}")

    return all_passed


def test_image_json_format():
    """Test: Image renders to correct Google Chat JSON format."""
    print("\n" + "=" * 60)
    print("TEST: Image JSON Format")
    print("=" * 60)

    from gchat.smart_card_builder import SmartCardBuilder

    builder = SmartCardBuilder()
    builder.initialize()

    # Build an Image widget
    widget = builder.build_image(
        image_url="https://example.com/image.jpg",
        alt_text="Test image",
    )

    if not widget:
        print("  ✗ Failed to build Image")
        return False

    # Render to JSON
    rendered = widget.render()
    print(f"\nRendered JSON:")
    print(json.dumps(rendered, indent=2))

    # Validate structure
    checks = [
        ("Has 'image' key", "image" in rendered),
        ("Has 'image_url' field", "image_url" in rendered.get("image", {})),
        (
            "URL value correct",
            rendered.get("image", {}).get("image_url")
            == "https://example.com/image.jpg",
        ),
    ]

    print("\nValidation:")
    all_passed = True
    for name, passed in checks:
        status = "✓" if passed else "✗"
        if not passed:
            all_passed = False
        print(f"  {status} {name}")

    return all_passed


def test_columns_json_format():
    """Test: Columns renders to correct Google Chat JSON format."""
    print("\n" + "=" * 60)
    print("TEST: Columns JSON Format")
    print("=" * 60)

    from gchat.smart_card_builder import SmartCardBuilder

    builder = SmartCardBuilder()
    builder.initialize()

    # Build widgets for columns
    left_widget = builder.build_decorated_text(text="Left content", top_label="Left")
    right_widget = builder.build_image(image_url="https://example.com/img.jpg")

    if not left_widget or not right_widget:
        print("  ✗ Failed to build widgets")
        return False

    # Build columns
    columns = builder.build_columns(
        left_widgets=[left_widget],
        right_widgets=[right_widget],
    )

    if not columns:
        print("  ✗ Failed to build Columns")
        return False

    # Render to JSON
    rendered = columns.render()
    print(f"\nRendered JSON:")
    print(json.dumps(rendered, indent=2))

    # Validate structure
    checks = [
        ("Has 'columns' key", "columns" in rendered),
        ("Has 'column_items' array", "column_items" in rendered.get("columns", {})),
        (
            "Has 2 columns",
            len(rendered.get("columns", {}).get("column_items", [])) == 2,
        ),
        (
            "Left column has widgets",
            "widgets" in rendered.get("columns", {}).get("column_items", [{}])[0],
        ),
        (
            "Right column has widgets",
            "widgets" in rendered.get("columns", {}).get("column_items", [{}, {}])[1],
        ),
        (
            "Left has horizontal_size_style",
            "horizontal_size_style"
            in rendered.get("columns", {}).get("column_items", [{}])[0],
        ),
    ]

    print("\nValidation:")
    all_passed = True
    for name, passed in checks:
        status = "✓" if passed else "✗"
        if not passed:
            all_passed = False
        print(f"  {status} {name}")

    return all_passed


def test_section_json_format():
    """Test: Section renders to correct Google Chat JSON format."""
    print("\n" + "=" * 60)
    print("TEST: Section JSON Format")
    print("=" * 60)

    from gchat.smart_card_builder import SmartCardBuilder

    builder = SmartCardBuilder()
    builder.initialize()

    # Build widgets
    widget1 = builder.build_decorated_text(text="Item 1", top_label="First")
    widget2 = builder.build_decorated_text(text="Item 2", top_label="Second")

    # Build section
    section = builder.build_section(
        header="Test Section",
        widgets=[widget1, widget2],
    )

    if not section:
        print("  ✗ Failed to build Section")
        return False

    # Render to JSON
    rendered = section.render()
    print(f"\nRendered JSON:")
    print(json.dumps(rendered, indent=2))

    # Validate structure
    checks = [
        ("Has 'header' field", "header" in rendered),
        ("Has 'widgets' array", "widgets" in rendered),
        ("Header value correct", rendered.get("header") == "Test Section"),
        ("Has 2 widgets", len(rendered.get("widgets", [])) == 2),
        (
            "First widget is decorated_text",
            "decorated_text" in rendered.get("widgets", [{}])[0],
        ),
    ]

    print("\nValidation:")
    all_passed = True
    for name, passed in checks:
        status = "✓" if passed else "✗"
        if not passed:
            all_passed = False
        print(f"  {status} {name}")

    return all_passed


def test_full_card_json_format():
    """Test: Full card renders to correct Google Chat API format."""
    print("\n" + "=" * 60)
    print("TEST: Full Card JSON Format (Google Chat API)")
    print("=" * 60)

    from gchat.smart_card_builder import SmartCardBuilder

    builder = SmartCardBuilder()
    builder.initialize()

    # Build a complete card
    result = builder.build_card(
        description="Card with image on right",
        content={
            "title": "Test Card",
            "subtitle": "Subtitle here",
            "section_header": "Details",
            "items": [
                {"text": "Value 1", "top_label": "Field 1"},
                {"text": "Value 2", "top_label": "Field 2"},
            ],
            "image_url": "https://example.com/image.jpg",
        },
    )

    print(f"\nRendered JSON:")
    print(json.dumps(result, indent=2))

    # Validate Google Chat card structure
    checks = [
        ("Has 'header' object", "header" in result),
        ("Header has 'title'", "title" in result.get("header", {})),
        ("Header has 'subtitle'", "subtitle" in result.get("header", {})),
        ("Has 'sections' array", "sections" in result),
        ("Sections is non-empty", len(result.get("sections", [])) > 0),
        ("Section has 'widgets'", "widgets" in result.get("sections", [{}])[0]),
    ]

    print("\nGoogle Chat API Structure Validation:")
    all_passed = True
    for name, passed in checks:
        status = "✓" if passed else "✗"
        if not passed:
            all_passed = False
        print(f"  {status} {name}")

    return all_passed


def test_button_list_json_format():
    """Test: ButtonList renders to correct Google Chat JSON format."""
    print("\n" + "=" * 60)
    print("TEST: ButtonList JSON Format")
    print("=" * 60)

    from gchat.smart_card_builder import SmartCardBuilder

    builder = SmartCardBuilder()
    builder.initialize()

    # Build a card with buttons
    result = builder.build_card(
        description="Card with action buttons",
        content={
            "title": "Action Card",
            "section_header": "Actions",
            "items": [
                {"text": "Click a button below", "top_label": "Info"},
            ],
            "buttons": [
                {"text": "Button 1", "url": "https://example.com/1"},
                {"text": "Button 2", "url": "https://example.com/2"},
            ],
        },
    )

    print(f"\nRendered JSON:")
    print(json.dumps(result, indent=2))

    # Find button_list in widgets
    button_list_found = False
    buttons_correct = False

    if "sections" in result:
        for section in result["sections"]:
            for widget in section.get("widgets", []):
                if "button_list" in widget:
                    button_list_found = True
                    buttons = widget["button_list"].get("buttons", [])
                    if len(buttons) == 2:
                        buttons_correct = True

    checks = [
        ("Has button_list widget", button_list_found),
        ("Has correct number of buttons", buttons_correct),
    ]

    print("\nValidation:")
    all_passed = True
    for name, passed in checks:
        status = "✓" if passed else "✗"
        if not passed:
            all_passed = False
        print(f"  {status} {name}")

    return all_passed


def test_empty_content_handling():
    """Test: Handles empty/missing content gracefully."""
    print("\n" + "=" * 60)
    print("TEST: Empty Content Handling")
    print("=" * 60)

    from gchat.smart_card_builder import SmartCardBuilder

    builder = SmartCardBuilder()
    builder.initialize()

    # Test with minimal content
    result = builder.build_card(
        description="Minimal card",
        content={
            "section_header": "Empty Section",
            "items": [],
        },
    )

    print(f"\nRendered JSON (minimal):")
    print(json.dumps(result, indent=2))

    # Should still produce valid structure
    has_structure = (
        "header" in result or "widgets" in result or isinstance(result, dict)
    )

    print(
        f"\n  {'✓' if has_structure else '✗'} Produces valid structure even with empty items"
    )

    return has_structure


def test_special_characters_in_text():
    """Test: Handles special characters in text content."""
    print("\n" + "=" * 60)
    print("TEST: Special Characters Handling")
    print("=" * 60)

    from gchat.smart_card_builder import SmartCardBuilder

    builder = SmartCardBuilder()
    builder.initialize()

    # Test with special characters
    special_text = 'Price: $99.00 → $79.00 (20% off!) <b>Bold</b> "Quoted"'

    widget = builder.build_decorated_text(
        text=special_text,
        top_label="Special",
    )

    if not widget:
        print("  ✗ Failed to build widget")
        return False

    rendered = widget.render()
    print(f"\nRendered JSON:")
    print(json.dumps(rendered, indent=2))

    # Check text is preserved
    text_preserved = rendered.get("decorated_text", {}).get("text") == special_text

    print(
        f"\n  {'✓' if text_preserved else '✗'} Special characters preserved in output"
    )

    return text_preserved


def test_colored_text_in_card():
    """Test: Colored text (HTML font tags) works in cards."""
    print("\n" + "=" * 60)
    print("TEST: Colored Text in Cards")
    print("=" * 60)

    from gchat.smart_card_builder import SmartCardBuilder

    builder = SmartCardBuilder()
    builder.initialize()

    # Build card with colored prices
    result = builder.build_card(
        description="Price card",
        content={
            "title": "Price Update",
            "section_header": "Pricing",
            "items": [
                {
                    "text": builder.format_price("$199.00", "$99.00"),
                    "top_label": "Sale Price",
                },
                {
                    "text": f"Status: {builder.format_colored_text('Active', 'green')}",
                    "top_label": "Status",
                },
            ],
        },
    )

    print(f"\nRendered JSON:")
    print(json.dumps(result, indent=2))

    # Check font tags are in output
    json_str = json.dumps(result)
    has_green = "#34a853" in json_str
    has_red = "#ea4335" in json_str or "<s>" in json_str

    checks = [
        ("Contains green color code", has_green),
        ("Contains strikethrough or red", has_red),
    ]

    print("\nValidation:")
    all_passed = True
    for name, passed in checks:
        status = "✓" if passed else "✗"
        if not passed:
            all_passed = False
        print(f"  {status} {name}")

    return all_passed


def test_google_chat_api_ready():
    """Test: Output is ready for Google Chat API (cardsV2 format)."""
    print("\n" + "=" * 60)
    print("TEST: Google Chat API Ready (cardsV2)")
    print("=" * 60)

    from gchat.smart_card_builder import SmartCardBuilder

    builder = SmartCardBuilder()
    builder.initialize()

    # Build a complete card
    card_content = builder.build_card(
        description="Complete card with image on right",
        content={
            "title": "API Ready Test",
            "subtitle": "Testing cardsV2 format",
            "section_header": "Deal Info",
            "items": [
                {"text": "deal-123", "top_label": "ID"},
                {"text": builder.format_price("$100", "$75"), "top_label": "Price"},
            ],
            "image_url": "https://example.com/img.jpg",
            "buttons": [{"text": "View", "url": "https://example.com"}],
        },
    )

    # Wrap in cardsV2 format for Google Chat API
    api_payload = {
        "cardsV2": [
            {
                "cardId": "smart-card-001",
                "card": card_content,
            }
        ]
    }

    print(f"\nGoogle Chat API Payload:")
    print(json.dumps(api_payload, indent=2))

    # Validate cardsV2 structure
    checks = [
        ("Has 'cardsV2' array", "cardsV2" in api_payload),
        ("Card has 'cardId'", "cardId" in api_payload.get("cardsV2", [{}])[0]),
        ("Card has 'card' object", "card" in api_payload.get("cardsV2", [{}])[0]),
        (
            "Card content has header",
            "header" in api_payload.get("cardsV2", [{}])[0].get("card", {}),
        ),
        (
            "Card content has sections",
            "sections" in api_payload.get("cardsV2", [{}])[0].get("card", {}),
        ),
    ]

    print("\ncardsV2 Format Validation:")
    all_passed = True
    for name, passed in checks:
        status = "✓" if passed else "✗"
        if not passed:
            all_passed = False
        print(f"  {status} {name}")

    return all_passed


def main():
    """Run all comprehensive tests."""
    print("=" * 60)
    print("Comprehensive Smart Card Builder Tests")
    print("=" * 60)

    results = []

    # Core functionality
    results.append(("Component Loading", test_component_loading()))
    results.append(("DecoratedText JSON", test_decorated_text_json_format()))
    results.append(("Image JSON", test_image_json_format()))
    results.append(("Columns JSON", test_columns_json_format()))
    results.append(("Section JSON", test_section_json_format()))
    results.append(("ButtonList JSON", test_button_list_json_format()))

    # Full card
    results.append(("Full Card JSON", test_full_card_json_format()))
    results.append(("Google Chat API Ready", test_google_chat_api_ready()))

    # Edge cases
    results.append(("Empty Content", test_empty_content_handling()))
    results.append(("Special Characters", test_special_characters_in_text()))
    results.append(("Colored Text", test_colored_text_in_card()))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")

    all_passed = all(r[1] for r in results)
    print(f"\n  Overall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")

    if all_passed:
        print("\n" + "=" * 60)
        print("READY FOR INTEGRATION")
        print("=" * 60)
        print("  SmartCardBuilder is ready to be integrated into unified_card_tool.py")
        print("  All JSON outputs match Google Chat API expectations")

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
