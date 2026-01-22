#!/usr/bin/env python3
"""
Test Smart Card Builder

Demonstrates:
1. Smart inference - automatically detecting content types (prices, IDs, dates, URLs)
2. Layout hints - detecting "image on right", "columns", etc. from natural language
3. Component composition - building proper component trees
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


def test_smart_inference():
    """Test: Smart inference maps content to correct component parameters."""
    print("\n" + "=" * 60)
    print("TEST: Smart Content Inference")
    print("=" * 60)

    from gchat.smart_card_builder import SmartCardBuilder

    builder = SmartCardBuilder()
    builder.initialize()

    # Test different content types
    test_cases = [
        ("$99.00", "price"),
        ("$199.99 sale", "price"),
        ('<font color="#34a853">$99.00</font>', "colored_price"),
        ("ID: deal-12345-abc", "id"),
        ("2026-01-19", "date"),
        ("01/19/2026", "date"),
        ("user@example.com", "email"),
        ("https://example.com/page", "url"),
        ("https://img.example.com/photo.jpg", "image"),
        ("https://cdn.example.com/image.webp", "image"),
        ("Just some regular text", "text"),
    ]

    print("\nContent Type Inference:")
    print("-" * 60)

    all_passed = True
    for text, expected_type in test_cases:
        result = builder.infer_content_type(text)
        status = "✓" if result["type"] == expected_type else "✗"
        if result["type"] != expected_type:
            all_passed = False

        print(f"  {status} '{text[:40]}...' => {result['type']}")
        print(f"      Component: {result['suggested_component']}")
        print(f"      Params: {list(result['suggested_params'].keys())}")
        print()

    return all_passed


def test_layout_inference():
    """Test: Layout hints detected from natural language."""
    print("\n" + "=" * 60)
    print("TEST: Layout Inference from Natural Language")
    print("=" * 60)

    from gchat.smart_card_builder import SmartCardBuilder

    builder = SmartCardBuilder()

    test_cases = [
        ("Show a simple card with text", "standard"),
        ("Two column layout with details", "columns"),
        ("Display with image on the right side", "columns_image_right"),
        ("Card with side by side content", "columns"),
        ("Put image on left and text on right", "columns_image_left"),
        ("Left side image, right side details", "columns_image_left"),
        ("Deal card with image on right", "columns_image_right"),
        ("Split view with columns", "columns"),
    ]

    print("\nLayout Detection:")
    print("-" * 60)

    all_passed = True
    for description, expected_layout in test_cases:
        result = builder.infer_layout(description)
        status = "✓" if result["layout_type"] == expected_layout else "✗"
        if result["layout_type"] != expected_layout:
            all_passed = False

        print(f"  {status} '{description}'")
        print(f"      Layout: {result['layout_type']}")
        if result["column_config"]:
            print(f"      Config: {result['column_config']}")
        print()

    return all_passed


def test_build_card_standard():
    """Test: Build a standard layout card."""
    print("\n" + "=" * 60)
    print("TEST: Build Standard Layout Card")
    print("=" * 60)

    from gchat.smart_card_builder import SmartCardBuilder

    builder = SmartCardBuilder()
    builder.initialize()

    # Build card with smart inference
    result = builder.build_card(
        description="A simple deal notification card",
        content={
            "title": "Deal Update",
            "subtitle": "New pricing available",
            "section_header": "Deal Details",
            "items": [
                "ID: deal-12345-abc",
                "$99.00",
                "2026-01-19",
            ],
        },
    )

    print("\nGenerated JSON:")
    print(json.dumps(result, indent=2))

    # Verify structure
    has_header = "header" in result
    has_sections = "sections" in result
    has_widgets = has_sections and len(result["sections"]) > 0

    print(f"\nValidation:")
    print(f"  Has header: {has_header}")
    print(f"  Has sections: {has_sections}")
    print(f"  Has widgets: {has_widgets}")

    return has_header and has_sections and has_widgets


def test_build_card_columns_image_right():
    """Test: Build a columns layout with image on right."""
    print("\n" + "=" * 60)
    print("TEST: Build Columns Layout (Image Right)")
    print("=" * 60)

    from gchat.smart_card_builder import SmartCardBuilder

    builder = SmartCardBuilder()
    builder.initialize()

    # Build card - layout inferred from description
    result = builder.build_card(
        description="Show deal info with image on the right side",
        content={
            "title": "Groupon Deal",
            "subtitle": "Limited Time Offer",
            "section_header": "Spa Treatment",
            "items": [
                {"text": "deal-spa-12345", "top_label": "Deal ID"},
                {
                    "text": builder.format_price("$199.00", "$99.00"),
                    "top_label": "Price",
                },
                {"text": "Hot stone massage - 60 minutes", "top_label": "Description"},
            ],
            "image_url": "https://img.grouponcdn.com/iam/27v19pzxCz4ZSauQc96KTAQdvidV/27-2048x1229/v1/t1024x619.webp",
        },
    )

    print("\nGenerated JSON:")
    print(json.dumps(result, indent=2))

    # Check for columns structure
    has_columns = False
    if "sections" in result:
        section = result["sections"][0]
        if "widgets" in section:
            for widget in section["widgets"]:
                if "columns" in widget:
                    has_columns = True
                    print(
                        f"\n✓ Found columns layout with {len(widget['columns']['column_items'])} columns"
                    )
                    break

    return has_columns


def test_build_card_with_buttons():
    """Test: Build a card with action buttons."""
    print("\n" + "=" * 60)
    print("TEST: Build Card with Buttons")
    print("=" * 60)

    from gchat.smart_card_builder import SmartCardBuilder

    builder = SmartCardBuilder()
    builder.initialize()

    result = builder.build_card(
        description="Action card with buttons",
        content={
            "title": "Action Required",
            "section_header": "Review Request",
            "items": [
                {"text": "PR #123 needs review", "top_label": "Pull Request"},
                {"text": "feat: Add smart card builder", "top_label": "Title"},
            ],
            "buttons": [
                {"text": "View PR", "url": "https://github.com/org/repo/pull/123"},
                {
                    "text": "Approve",
                    "url": "https://github.com/org/repo/pull/123/approve",
                },
            ],
        },
    )

    print("\nGenerated JSON:")
    print(json.dumps(result, indent=2))

    # Check for button_list
    has_buttons = False
    if "sections" in result:
        section = result["sections"][0]
        if "widgets" in section:
            for widget in section["widgets"]:
                if "button_list" in widget:
                    has_buttons = True
                    print(f"\n✓ Found button_list with buttons")
                    break

    return has_buttons


def test_colored_price_formatting():
    """Test: Price formatting with colors."""
    print("\n" + "=" * 60)
    print("TEST: Colored Price Formatting")
    print("=" * 60)

    from gchat.smart_card_builder import SmartCardBuilder

    builder = SmartCardBuilder()

    # Test price formatting
    formatted = builder.format_price("$199.00", "$99.00")
    print(f"\nformat_price('$199.00', '$99.00'):")
    print(f"  Result: {formatted}")

    # Test colored text
    success = builder.format_colored_text("Success!", "green")
    error = builder.format_colored_text("Error!", "red")
    print(f"\nformat_colored_text('Success!', 'green'):")
    print(f"  Result: {success}")
    print(f"\nformat_colored_text('Error!', 'red'):")
    print(f"  Result: {error}")

    return '<font color="#34a853">' in formatted and "<s>" in formatted


def test_full_deal_card():
    """Test: Build a complete deal card like the screenshot."""
    print("\n" + "=" * 60)
    print("TEST: Full Deal Card (Like Screenshot)")
    print("=" * 60)

    from gchat.smart_card_builder import SmartCardBuilder

    builder = SmartCardBuilder()
    builder.initialize()

    # Build a card matching the screenshot layout
    result = builder.build_card(
        description="Deal card with image on right side showing price update",
        content={
            "title": "Price Update Test",
            "subtitle": "Image URL rendering",
            "section_header": "Sale Date: 2026-01-19",
            "items": [
                {"text": "6178c673-28b7-4879-aad8-6a70e0a6072e", "top_label": "ID"},
                {
                    "text": f'{builder.format_colored_text("$105.00", "green")} → {builder.format_colored_text("$94.50", "red")}',
                    "top_label": "Price",
                },
                {
                    "text": "4219281f-84c2-441b-b152-57515a514153",
                    "top_label": "Quote ID",
                },
                {"text": "Program price deleted successfully", "top_label": "Status"},
            ],
            "image_url": "https://img.grouponcdn.com/iam/27v19pzxCz4ZSauQc96KTAQdvidV/27-2048x1229/v1/t1024x619.webp",
            "buttons": [
                {"text": "View Deal", "url": "https://example.com/deal/123"},
            ],
        },
    )

    print("\nGenerated JSON:")
    print(json.dumps(result, indent=2))

    # Validate structure
    valid = (
        "header" in result
        and result["header"].get("title") == "Price Update Test"
        and "sections" in result
        and len(result["sections"]) > 0
    )

    if valid:
        print("\n✓ Card structure is valid and matches expected layout")

    return valid


def main():
    """Run all tests."""
    print("=" * 60)
    print("Smart Card Builder Tests")
    print("=" * 60)
    print("\nThis demonstrates:")
    print("  1. Smart inference - auto-detect content types")
    print("  2. Layout hints - detect 'columns', 'image on right' from text")
    print("  3. Component composition - build proper widget trees")
    print("  4. Render to JSON - via card_framework .render()")

    results = []

    # Run tests
    results.append(("Smart Inference", test_smart_inference()))
    results.append(("Layout Inference", test_layout_inference()))
    results.append(("Standard Card", test_build_card_standard()))
    results.append(("Columns Image Right", test_build_card_columns_image_right()))
    results.append(("Card with Buttons", test_build_card_with_buttons()))
    results.append(("Colored Prices", test_colored_price_formatting()))
    results.append(("Full Deal Card", test_full_deal_card()))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")

    all_passed = all(r[1] for r in results)
    print(f"\n  Overall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
