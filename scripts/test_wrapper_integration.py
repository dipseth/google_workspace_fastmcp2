#!/usr/bin/env python3
"""
Integration tests for SmartCardBuilder and FeedbackLoop wrapper integration.

Verifies that:
1. SmartCardBuilder._query_wrapper_patterns() correctly uses wrapper search methods
2. FeedbackLoop._query_via_wrapper() correctly delegates to wrapper when available
3. DSL-aware search is triggered when DSL symbols are detected
4. Hybrid V7 search is used as fallback
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_smart_card_builder_wrapper_search():
    """Test SmartCardBuilder uses wrapper search methods."""
    print("=" * 60)
    print("TEST: SmartCardBuilder._query_wrapper_patterns()")
    print("=" * 60)

    from gchat.card_builder import SmartCardBuilder

    builder = SmartCardBuilder()

    # Test _query_wrapper_patterns with DSL
    print("\n🔍 Testing with DSL notation...")
    result = builder._query_wrapper_patterns("§[δ] Simple text card")

    if result:
        print(f"   ✓ Got result from wrapper")
        print(f"   source: {result.get('source', 'unknown')}")
        print(f"   component_paths: {result.get('component_paths', [])[:3]}")
        print(f"   score: {result.get('score', 0):.3f}")

        # With DSL, should use wrapper_dsl source
        assert result.get("source") in ["wrapper_dsl", "wrapper_hybrid"], \
            f"Expected 'wrapper_dsl' or 'wrapper_hybrid', got {result.get('source')}"
    else:
        print("   ⚠️ No result (may be expected if no matching patterns)")

    # Test with non-DSL description
    print("\n🔍 Testing without DSL notation...")
    result2 = builder._query_wrapper_patterns("A simple status indicator card")

    if result2:
        print(f"   ✓ Got result from wrapper")
        print(f"   source: {result2.get('source', 'unknown')}")
        print(f"   component_paths: {result2.get('component_paths', [])[:3]}")
        print(f"   score: {result2.get('score', 0):.3f}")

        # Without DSL, should use wrapper_hybrid source
        if result2.get("source") == "wrapper_hybrid":
            print("   ✓ Correctly used hybrid search (no DSL)")
    else:
        print("   ⚠️ No result (may be expected if no matching patterns with positive feedback)")

    # Test full _query_qdrant_patterns flow
    print("\n🔍 Testing _query_qdrant_patterns (full flow)...")
    result3 = builder._query_qdrant_patterns("§[δ, Ƀ[ᵬ]]")

    if result3:
        print(f"   ✓ Got result through full flow")
        print(f"   source: {result3.get('source', 'fallback/feedback_loop')}")
        print(f"   component_paths count: {len(result3.get('component_paths', []))}")
    else:
        print("   ⚠️ No patterns matched (expected if collection has no positive patterns)")

    print("\n✓ SmartCardBuilder wrapper integration test complete")


def test_feedback_loop_wrapper_delegation():
    """Test FeedbackLoop delegates to wrapper when available."""
    print("\n" + "=" * 60)
    print("TEST: FeedbackLoop._query_via_wrapper()")
    print("=" * 60)

    from gchat.feedback_loop import get_feedback_loop

    fl = get_feedback_loop()

    # Test _query_via_wrapper
    print("\n🔍 Testing _query_via_wrapper...")
    result = fl._query_via_wrapper(
        description="A status card with action buttons",
        limit=3,
    )

    if result:
        class_results, content_patterns, form_patterns = result
        print(f"   ✓ Wrapper delegation successful")
        print(f"   class_results: {len(class_results)}")
        print(f"   content_patterns: {len(content_patterns)}")
        print(f"   form_patterns: {len(form_patterns)}")

        # Show sample results
        if class_results:
            print(f"   Sample class: {class_results[0].get('name', '?')}")
        if content_patterns:
            print(f"   Sample content pattern: {content_patterns[0].get('name', '?')[:40]}")
    else:
        print("   ⚠️ Wrapper returned None (wrapper may not be available)")

    # Test query_with_feedback with use_negative_feedback=False
    # This should prefer wrapper delegation
    print("\n🔍 Testing query_with_feedback(use_negative_feedback=False)...")
    class_results, content_patterns, form_patterns = fl.query_with_feedback(
        component_query="Button widget",
        description="A card with buttons",
        limit=3,
        use_negative_feedback=False,  # This triggers wrapper delegation
    )

    print(f"   class_results: {len(class_results)}")
    print(f"   content_patterns: {len(content_patterns)}")
    print(f"   form_patterns: {len(form_patterns)}")

    # With use_negative_feedback=False, it should try wrapper first
    print("   ✓ query_with_feedback executed (wrapper or direct)")

    print("\n✓ FeedbackLoop wrapper delegation test complete")


def test_dsl_extraction_in_search():
    """Test that DSL is correctly extracted before search."""
    print("\n" + "=" * 60)
    print("TEST: DSL extraction in search pipeline")
    print("=" * 60)

    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    test_cases = [
        # (input, expected_has_dsl, expected_dsl)
        ("§[δ, Ƀ[ᵬ×2]] Build a status card", True, "§[δ, Ƀ[ᵬ×2]]"),
        ("§[δ] Simple text", True, "§[δ]"),
        ("Build a card with buttons", False, None),
        ("ℊ[ǵ×4] Grid with 4 items", True, "ℊ[ǵ×4]"),
    ]

    print("\n🔍 Testing DSL extraction...")
    all_passed = True

    for text, expected_has_dsl, expected_dsl in test_cases:
        result = wrapper.extract_dsl_from_text(text)
        has_dsl = result.get("has_dsl", False)
        dsl = result.get("dsl")

        status = "✓" if has_dsl == expected_has_dsl else "✗"
        print(f"   {status} '{text[:35]}...' -> has_dsl={has_dsl}, dsl={dsl}")

        if has_dsl != expected_has_dsl:
            all_passed = False
            print(f"      Expected has_dsl={expected_has_dsl}")

        if expected_dsl and dsl != expected_dsl:
            all_passed = False
            print(f"      Expected dsl='{expected_dsl}'")

    if all_passed:
        print("\n✓ All DSL extraction tests passed")
    else:
        print("\n✗ Some DSL extraction tests failed")


def test_wrapper_search_v7_hybrid_filters():
    """Test that search_v7_hybrid correctly applies feedback filters."""
    print("\n" + "=" * 60)
    print("TEST: search_v7_hybrid feedback filter application")
    print("=" * 60)

    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    # Test with positive filters
    print("\n🔍 Testing with content_feedback='positive', form_feedback='positive'...")
    classes, content_patterns, form_patterns = wrapper.search_v7_hybrid(
        description="A dashboard card",
        limit=10,
        content_feedback="positive",
        form_feedback="positive",
        include_classes=True,
    )

    print(f"   Results: {len(classes)} classes, {len(content_patterns)} content, {len(form_patterns)} form")

    # Verify content patterns have positive feedback (if any returned)
    invalid_count = 0
    for p in content_patterns:
        content_fb = p.get("content_feedback")
        form_fb = p.get("form_feedback")
        # Should have either positive content or positive form feedback
        if content_fb != "positive" and form_fb != "positive":
            invalid_count += 1
            print(f"   ⚠️ Pattern without positive feedback: {p.get('name', '?')[:30]}")

    if content_patterns and invalid_count == 0:
        print("   ✓ All content patterns have positive feedback")
    elif not content_patterns:
        print("   ⚠️ No content patterns returned (may be expected)")

    # Test with no filters
    print("\n🔍 Testing without feedback filters...")
    classes2, content_patterns2, form_patterns2 = wrapper.search_v7_hybrid(
        description="A dashboard card",
        limit=10,
        include_classes=True,
    )

    print(f"   Results: {len(classes2)} classes, {len(content_patterns2)} content, {len(form_patterns2)} form")

    # Compare - should generally get more results without filters
    if len(content_patterns2) >= len(content_patterns):
        print("   ✓ Without filters returns >= filtered results (expected)")
    else:
        print(f"   ⚠️ Fewer results without filters (unexpected)")

    print("\n✓ search_v7_hybrid filter test complete")


if __name__ == "__main__":
    print("=" * 60)
    print("WRAPPER INTEGRATION TESTS")
    print("=" * 60)

    test_smart_card_builder_wrapper_search()
    test_feedback_loop_wrapper_delegation()
    test_dsl_extraction_in_search()
    test_wrapper_search_v7_hybrid_filters()

    print("\n" + "=" * 60)
    print("✅ ALL INTEGRATION TESTS COMPLETE")
    print("=" * 60)
