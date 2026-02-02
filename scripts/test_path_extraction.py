#!/usr/bin/env python3
"""
Test the _extract_paths_from_pattern fix.

Verifies that component paths can be extracted from:
1. component_paths field
2. parent_paths field
3. relationship_text DSL notation
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_extract_paths():
    """Test the path extraction from different pattern formats."""
    from gchat.card_builder import get_smart_card_builder

    builder = get_smart_card_builder()

    print("=" * 60)
    print("Testing _extract_paths_from_pattern")
    print("=" * 60)

    # Test 1: component_paths field present
    pattern1 = {
        "component_paths": ["Section", "DecoratedText", "ButtonList"],
        "parent_paths": [],
        "relationship_text": "",
    }
    result1 = builder._extract_paths_from_pattern(pattern1)
    print(f"\n1. component_paths field: {result1}")
    assert result1 == ["Section", "DecoratedText", "ButtonList"], f"Expected ['Section', 'DecoratedText', 'ButtonList'], got {result1}"
    print("   ✅ PASS")

    # Test 2: parent_paths field (full paths)
    pattern2 = {
        "component_paths": [],
        "parent_paths": [
            "card_framework.v2.sections.Section",
            "card_framework.v2.widgets.decorated_text.DecoratedText",
            "card_framework.v2.widgets.button_list.ButtonList",
        ],
        "relationship_text": "",
    }
    result2 = builder._extract_paths_from_pattern(pattern2)
    print(f"\n2. parent_paths field: {result2}")
    assert result2 == ["Section", "DecoratedText", "ButtonList"], f"Expected class names only, got {result2}"
    print("   ✅ PASS")

    # Test 3: relationship_text DSL notation
    pattern3 = {
        "component_paths": [],
        "parent_paths": [],
        "relationship_text": "§[δ, Ƀ, ᵬ] | Section DecoratedText ButtonList Button :: Card with text and buttons",
    }
    result3 = builder._extract_paths_from_pattern(pattern3)
    print(f"\n3. relationship_text: {result3}")
    assert "Section" in result3 and "DecoratedText" in result3, f"Expected to extract component names, got {result3}"
    print("   ✅ PASS")

    # Test 4: Real Qdrant pattern format (from our ad-hoc test)
    pattern4 = {
        "component_paths": [],
        "parent_paths": [],
        "relationship_text": "§[δ, ɨ, ᵬ] | DecoratedText Icon Button :: Decorated text with leading icon",
    }
    result4 = builder._extract_paths_from_pattern(pattern4)
    print(f"\n4. Real Qdrant format: {result4}")
    assert "DecoratedText" in result4, f"Expected DecoratedText, got {result4}"
    print("   ✅ PASS")

    # Test 5: Pattern with multipliers
    pattern5 = {
        "component_paths": [],
        "parent_paths": [],
        "relationship_text": "§[δ×3] | Section DecoratedText×3",
    }
    result5 = builder._extract_paths_from_pattern(pattern5)
    print(f"\n5. Pattern with multipliers: {result5}")
    assert "Section" in result5 and "DecoratedText" in result5, f"Expected Section and DecoratedText, got {result5}"
    print("   ✅ PASS")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    test_extract_paths()
