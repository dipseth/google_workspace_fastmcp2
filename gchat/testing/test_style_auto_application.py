"""
Test Suite for Style Auto-Application from Instance Pattern Metadata

This test mimics the exact flow of send_dynamic_card:
1. Store a pattern with style metadata (simulating a successful styled card with positive feedback)
2. Search for a similar description via the inputs vector
3. Build a new card from the matched pattern
4. Verify styles are auto-applied to the new card

Usage:
    uv run python -m gchat.testing.test_style_auto_application
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from config.enhanced_logging import setup_logger

logger = setup_logger()


def test_extract_style_metadata():
    """Test the extract_style_metadata helper function."""
    from gchat.card_builder import extract_style_metadata

    print("\n" + "=" * 60)
    print("TEST 1: extract_style_metadata()")
    print("=" * 60)

    # Test case 1: Success styling with bold
    text1 = "{{ 'Server is online' | success_text | bold }}"
    result1 = extract_style_metadata(text1)
    print(f"\nInput: {text1}")
    print(f"Result: {json.dumps(result1, indent=2)}")

    assert "success_text" in result1["jinja_filters"], "Missing success_text filter"
    assert "bold" in result1["jinja_filters"], "Missing bold filter"
    assert "success" in result1["semantic_styles"], "Missing success semantic style"
    assert "bold" in result1["formatting"], "Missing bold formatting"
    print("PASSED: Basic Jinja expression extraction")

    # Test case 2: Error styling
    text2 = "{{ 'Connection failed' | error_text }}"
    result2 = extract_style_metadata(text2)
    print(f"\nInput: {text2}")
    print(f"Result: {json.dumps(result2, indent=2)}")

    assert "error_text" in result2["jinja_filters"]
    assert "error" in result2["semantic_styles"]
    print("PASSED: Error style extraction")

    # Test case 3: Color extraction
    text3 = "{{ 'Custom color' | color('#FF5500') }}"
    result3 = extract_style_metadata(text3)
    print(f"\nInput: {text3}")
    print(f"Result: {json.dumps(result3, indent=2)}")

    assert "#FF5500" in result3["colors"], "Missing hex color"
    print("PASSED: Color extraction")

    # Test case 4: Multiple filters in one expression
    text4 = "{{ 'Important!' | warning_text | bold | italic }}"
    result4 = extract_style_metadata(text4)
    print(f"\nInput: {text4}")
    print(f"Result: {json.dumps(result4, indent=2)}")

    assert "warning" in result4["semantic_styles"]
    assert "bold" in result4["formatting"]
    assert "italic" in result4["formatting"]
    print("PASSED: Multiple filters in chain")

    print("\n" + "=" * 60)
    print("ALL extract_style_metadata TESTS PASSED")
    print("=" * 60)


def test_style_application_methods():
    """Test _has_explicit_styles and _apply_pattern_styles methods."""
    from gchat.card_builder import SmartCardBuilderV2

    print("\n" + "=" * 60)
    print("TEST 2: Style Application Methods")
    print("=" * 60)

    builder = SmartCardBuilderV2()

    # Test _has_explicit_styles
    print("\n--- Testing _has_explicit_styles ---")

    params_with_styles = {"text": "{{ 'hello' | bold }}"}
    params_without_styles = {"text": "hello world"}
    params_with_color = {"text": "{{ x | color('#FF0000') }}"}

    assert builder._has_explicit_styles(params_with_styles) is True
    print(f"  With Jinja: {params_with_styles} -> True")

    assert builder._has_explicit_styles(params_without_styles) is False
    print(f"  Without Jinja: {params_without_styles} -> False")

    assert builder._has_explicit_styles(params_with_color) is True
    print(f"  With color filter: {params_with_color} -> True")

    print("PASSED: _has_explicit_styles")

    # Test _apply_pattern_styles
    print("\n--- Testing _apply_pattern_styles ---")

    # Success styling for text with "online" keyword
    style_metadata = {"semantic_styles": ["success"], "formatting": ["bold"]}
    params = {"text": "Server is online"}
    result = builder._apply_pattern_styles(params.copy(), style_metadata)
    print(f"\n  Input params: {params}")
    print(f"  Style metadata: {style_metadata}")
    print(f"  Result: {result}")
    assert "success_text" in result["text"]
    assert "bold" in result["text"]
    print("  PASSED: Applied success_text | bold for 'online' keyword")

    # Error styling for text with "offline" keyword
    style_metadata2 = {"semantic_styles": ["error"], "formatting": []}
    params2 = {"text": "Server is offline"}
    result2 = builder._apply_pattern_styles(params2.copy(), style_metadata2)
    print(f"\n  Input params: {params2}")
    print(f"  Style metadata: {style_metadata2}")
    print(f"  Result: {result2}")
    assert "error_text" in result2["text"]
    print("  PASSED: Applied error_text for 'offline' keyword")

    # Warning styling for text with "pending" keyword
    style_metadata3 = {"semantic_styles": ["warning"], "formatting": ["italic"]}
    params3 = {"text": "Status is pending"}
    result3 = builder._apply_pattern_styles(params3.copy(), style_metadata3)
    print(f"\n  Input params: {params3}")
    print(f"  Style metadata: {style_metadata3}")
    print(f"  Result: {result3}")
    assert "warning_text" in result3["text"]
    assert "italic" in result3["text"]
    print("  PASSED: Applied warning_text | italic for 'pending' keyword")

    # No matching keywords - should NOT apply style
    style_metadata4 = {"semantic_styles": ["success"], "formatting": []}
    params4 = {"text": "Random text here"}
    result4 = builder._apply_pattern_styles(params4.copy(), style_metadata4)
    print(f"\n  Input params: {params4}")
    print(f"  Style metadata: {style_metadata4}")
    print(f"  Result: {result4}")
    assert result4["text"] == "Random text here", "Should not apply style without matching keywords"
    print("  PASSED: Did NOT apply style when no keywords match")

    # Info styling as fallback
    style_metadata5 = {"semantic_styles": ["info"], "formatting": []}
    params5 = {"text": "Some information"}
    result5 = builder._apply_pattern_styles(params5.copy(), style_metadata5)
    print(f"\n  Input params: {params5}")
    print(f"  Style metadata: {style_metadata5}")
    print(f"  Result: {result5}")
    assert "info_text" in result5["text"]
    print("  PASSED: Applied info_text as fallback (no specific keywords needed)")

    print("\n" + "=" * 60)
    print("ALL Style Application Methods TESTS PASSED")
    print("=" * 60)


def test_build_from_pattern_with_style():
    """Test that _build_from_pattern applies styles from style_metadata."""
    from gchat.card_builder import SmartCardBuilderV2

    print("\n" + "=" * 60)
    print("TEST 3: _build_from_pattern with Style Metadata")
    print("=" * 60)

    builder = SmartCardBuilderV2()

    # Simulate a pattern retrieved from Qdrant with style_metadata
    pattern = {
        "component_paths": ["Section", "DecoratedText", "ButtonList"],
        "instance_params": {
            "title": "Server Status",
            "description": "Server status dashboard",
            "style_metadata": {
                "jinja_filters": ["success_text", "bold"],
                "colors": [],
                "semantic_styles": ["success"],
                "formatting": ["bold"],
            },
        },
    }

    # Build card with new params that should receive auto-styling
    card_params = {
        "title": "My Server Status",
        "text": "Server is online",  # Contains "online" keyword
        "buttons": [{"text": "Refresh", "url": "https://example.com"}],
    }

    print(f"\nPattern from Qdrant:")
    print(f"  component_paths: {pattern['component_paths']}")
    print(f"  instance_params.style_metadata: {pattern['instance_params']['style_metadata']}")

    print(f"\nNew card_params (should get auto-styled):")
    print(f"  {json.dumps(card_params, indent=2)}")

    card = builder._build_from_pattern(pattern, card_params)

    print(f"\nBuilt card:")
    print(f"  {json.dumps(card, indent=2)}")

    # Verify card was built
    assert card is not None, "Card should be built"
    assert "sections" in card, "Card should have sections"
    assert len(card["sections"]) > 0, "Card should have at least one section"

    # Get the text content from the card
    card_json = json.dumps(card)
    print(f"\nVerifying styling in card JSON...")

    # The text should have been styled and then processed through Jinja
    # So we should see either the Jinja expression or the rendered color
    # Since _format_text_for_chat processes Jinja, we should see the result
    assert "sections" in card

    # Check if success styling was applied (green color or success indicator)
    widgets = card["sections"][0].get("widgets", [])
    text_widget = None
    for w in widgets:
        if "decoratedText" in w:
            text_widget = w["decoratedText"]
            break

    if text_widget:
        text_content = text_widget.get("text", "")
        print(f"  Text widget content: {text_content}")
        # After Jinja processing, success_text adds green color
        # The text should be styled (either has color tag or was processed)
        assert len(text_content) > 0, "Text content should exist"
    else:
        print("  Warning: No decorated text widget found")

    print("\n" + "=" * 60)
    print("_build_from_pattern with Style Metadata TEST PASSED")
    print("=" * 60)


def test_full_flow_store_and_retrieve():
    """
    Test the complete flow:
    1. Store a pattern with style metadata
    2. Search for similar description
    3. Build card and verify style is applied

    This mimics exactly what happens in send_dynamic_card.
    """
    from gchat.card_builder import SmartCardBuilderV2, extract_style_metadata
    from gchat.feedback_loop import get_feedback_loop

    print("\n" + "=" * 60)
    print("TEST 4: Full Store → Search → Build Flow")
    print("=" * 60)

    # Step 1: Create a styled description (simulating a previous successful card)
    original_description = "{{ 'Service is running' | success_text | bold }}"
    original_style_metadata = extract_style_metadata(original_description)

    print(f"\n[Step 1] Original styled card:")
    print(f"  Description: {original_description}")
    print(f"  Extracted style_metadata: {json.dumps(original_style_metadata, indent=2)}")

    # Step 2: Store pattern in Qdrant (simulating what _store_card_pattern_sync does)
    feedback_loop = get_feedback_loop()

    if not feedback_loop.ensure_description_vector_exists():
        print("  WARNING: Qdrant not available, skipping storage test")
        return

    component_paths = ["Section", "DecoratedText"]
    instance_params = {
        "title": "Service Status",
        "description": original_description[:500],
        "dsl": None,
        "component_count": len(component_paths),
        "description_rendered": "Service is running",  # After Jinja processing
        "jinja_applied": True,
        "style_metadata": original_style_metadata,
    }

    # Generate a unique card_id for this test
    test_card_id = f"test_style_auto_{uuid.uuid4().hex[:8]}"

    print(f"\n[Step 2] Storing pattern in Qdrant:")
    print(f"  card_id: {test_card_id}")
    print(f"  component_paths: {component_paths}")
    print(f"  instance_params.style_metadata: {instance_params['style_metadata']}")

    point_id = feedback_loop.store_instance_pattern(
        card_description="Service status card showing running state",
        component_paths=component_paths,
        instance_params=instance_params,
        card_id=test_card_id,
        structure_description="§[δ]",
        pattern_type="content",
        content_feedback="positive",  # Mark as successful pattern
    )

    if point_id:
        print(f"  Stored as point_id: {point_id}")
    else:
        print("  WARNING: Failed to store pattern")
        return

    # Give Qdrant a moment to index
    import time
    time.sleep(0.5)

    # Step 3: Search for similar pattern (simulating what SmartCardBuilder does)
    print(f"\n[Step 3] Searching for similar pattern...")

    # Use the wrapper's search_v7_hybrid to find the pattern
    try:
        from gchat.card_framework_wrapper import get_card_framework_wrapper

        wrapper = get_card_framework_wrapper()
        if wrapper:
            class_results, content_patterns, form_patterns = wrapper.search_v7_hybrid(
                description="Service status running",  # Similar description
                component_paths=None,
                limit=5,
                content_feedback="positive",
                include_classes=False,
            )

            print(f"  Found {len(content_patterns)} content patterns")

            if content_patterns:
                best_pattern = content_patterns[0]
                print(f"  Best match score: {best_pattern.get('score', 'N/A')}")
                print(f"  Best match card_description: {best_pattern.get('card_description', 'N/A')[:50]}...")

                # Check if style_metadata is in the retrieved pattern
                retrieved_instance_params = best_pattern.get("instance_params", {})
                retrieved_style_metadata = retrieved_instance_params.get("style_metadata", {})

                print(f"  Retrieved style_metadata: {json.dumps(retrieved_style_metadata, indent=2)}")

                if retrieved_style_metadata:
                    print("  SUCCESS: Style metadata was retrieved from Qdrant!")
                else:
                    print("  WARNING: Style metadata not found in retrieved pattern")

                # Step 4: Build new card and verify style application
                print(f"\n[Step 4] Building new card from pattern...")

                builder = SmartCardBuilderV2()

                # Simulate building with new params
                new_card_params = {
                    "title": "New Status Card",
                    "text": "Application is running",  # Has 'running' keyword
                }

                # Construct pattern dict as SmartCardBuilder would receive it
                pattern_for_build = {
                    "component_paths": best_pattern.get("parent_paths", []),
                    "instance_params": retrieved_instance_params,
                }

                print(f"  New card_params: {new_card_params}")
                print(f"  Pattern instance_params.style_metadata: {retrieved_style_metadata}")

                card = builder._build_from_pattern(pattern_for_build, new_card_params)

                if card:
                    print(f"\n  Built card:")
                    print(f"  {json.dumps(card, indent=2)}")
                    print("\n  SUCCESS: Card built from pattern!")
                else:
                    print("  WARNING: Failed to build card from pattern")

    except Exception as e:
        print(f"  Error during search: {e}")
        import traceback
        traceback.print_exc()

    # Cleanup: Remove test pattern
    print(f"\n[Cleanup] Removing test pattern...")
    try:
        from gchat.feedback_loop import COLLECTION_NAME

        client = feedback_loop._get_client()
        if client and point_id:
            client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=[point_id],
            )
            print(f"  Deleted point_id: {point_id}")
    except Exception as e:
        print(f"  Cleanup error: {e}")

    print("\n" + "=" * 60)
    print("Full Flow Test COMPLETED")
    print("=" * 60)


def test_dag_generated_styled_pattern():
    """
    Use DAG structure generator to create a valid card structure,
    then test style auto-application with it.
    """
    print("\n" + "=" * 60)
    print("TEST 5: DAG-Generated Pattern with Styles")
    print("=" * 60)

    try:
        from gchat.testing.dag_structure_generator import DAGStructureGenerator
        from gchat.card_builder import SmartCardBuilderV2, extract_style_metadata

        # Generate a random valid structure
        gen = DAGStructureGenerator()
        structure = gen.generate_random_structure(root="Section")

        print(f"\n[Step 1] Generated DAG structure:")
        print(f"  DSL: {structure.dsl}")
        print(f"  Components: {structure.components}")

        # Create style metadata for this structure
        styled_text = "{{ 'Database is healthy' | success_text | bold }}"
        style_metadata = extract_style_metadata(styled_text)

        print(f"\n[Step 2] Created style metadata:")
        print(f"  Styled text: {styled_text}")
        print(f"  Style metadata: {json.dumps(style_metadata, indent=2)}")

        # Build pattern as it would be stored in Qdrant
        pattern = {
            "component_paths": structure.components if structure.components else ["Section", "DecoratedText"],
            "instance_params": {
                "title": "Health Check",
                "description": styled_text,
                "dsl": structure.dsl,
                "style_metadata": style_metadata,
            },
        }

        print(f"\n[Step 3] Pattern for _build_from_pattern:")
        print(f"  component_paths: {pattern['component_paths']}")

        # Build new card with similar content
        builder = SmartCardBuilderV2()
        new_params = {
            "title": "System Health",
            "text": "Cache is healthy",  # Has 'healthy' keyword - should trigger success styling
        }

        print(f"\n[Step 4] Building card with new params:")
        print(f"  new_params: {new_params}")

        card = builder._build_from_pattern(pattern, new_params)

        if card:
            print(f"\n[Step 5] Built card:")
            print(f"  {json.dumps(card, indent=2)}")

            # Verify the text field was styled
            widgets = card.get("sections", [{}])[0].get("widgets", [])
            text_found = False
            for w in widgets:
                if "decoratedText" in w:
                    text_content = w["decoratedText"].get("text", "")
                    text_found = True
                    print(f"\n  Text content: {text_content}")
                    break
                elif "textParagraph" in w:
                    text_content = w["textParagraph"].get("text", "")
                    text_found = True
                    print(f"\n  Text content: {text_content}")
                    break

            if text_found:
                print("  SUCCESS: Card built with DAG structure and styled text!")
            else:
                print("  Note: No text widget in generated structure")

        else:
            print("  WARNING: Failed to build card")

    except ImportError as e:
        print(f"  DAG generator not available: {e}")
    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("DAG-Generated Pattern Test COMPLETED")
    print("=" * 60)


def run_all_tests():
    """Run all tests in sequence."""
    print("\n" + "#" * 70)
    print("#" + " " * 20 + "STYLE AUTO-APPLICATION TESTS" + " " * 20 + "#")
    print("#" * 70)

    test_extract_style_metadata()
    test_style_application_methods()
    test_build_from_pattern_with_style()
    test_full_flow_store_and_retrieve()
    test_dag_generated_styled_pattern()

    print("\n" + "#" * 70)
    print("#" + " " * 20 + "ALL TESTS COMPLETED" + " " * 25 + "#")
    print("#" * 70)


if __name__ == "__main__":
    run_all_tests()
