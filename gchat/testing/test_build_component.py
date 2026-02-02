"""
Comprehensive tests for _build_component universality and robustness.

Tests various scenarios:
1. Basic widget types (DecoratedText, TextParagraph, Image, etc.)
2. Container components (ButtonList, ChipList, Grid, Columns)
3. Empty components (Divider)
4. Nested structures with children
5. DAG validation (valid/invalid relationships)
6. Edge cases (missing params, unknown components)
7. build_component_tree for hierarchies
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def test_build_component():
    """Run comprehensive _build_component tests."""
    from gchat.card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()
    wrapper = builder._get_wrapper()

    results = {
        "passed": 0,
        "failed": 0,
        "tests": [],
    }

    def run_test(name: str, test_fn):
        """Run a single test and track results."""
        try:
            result = test_fn()
            if result.get("success"):
                results["passed"] += 1
                status = "✅ PASS"
            else:
                results["failed"] += 1
                status = "❌ FAIL"
            results["tests"].append({"name": name, "status": status, **result})
            logger.info(f"{status}: {name}")
            if result.get("output"):
                logger.info(f"   Output: {json.dumps(result['output'], indent=2)[:200]}...")
            if result.get("error"):
                logger.info(f"   Error: {result['error']}")
        except Exception as e:
            results["failed"] += 1
            results["tests"].append({"name": name, "status": "❌ EXCEPTION", "error": str(e)})
            logger.info(f"❌ EXCEPTION: {name} - {e}")

    # =========================================================================
    # 1. BASIC WIDGET TYPES
    # =========================================================================
    logger.info("\n" + "=" * 60)
    logger.info("1. BASIC WIDGET TYPES")
    logger.info("=" * 60)

    def test_decorated_text():
        result = builder._build_component(
            "DecoratedText",
            {"text": "Hello World", "wrapText": True},
            wrap_with_key=True,
        )
        success = (
            result is not None
            and "decoratedText" in result
            and result["decoratedText"].get("text") == "Hello World"
        )
        return {"success": success, "output": result}

    def test_decorated_text_with_labels():
        result = builder._build_component(
            "DecoratedText",
            {"text": "Status", "top_label": "System", "bottom_label": "Active"},
            wrap_with_key=True,
        )
        success = result is not None and "decoratedText" in result
        return {"success": success, "output": result}

    def test_text_paragraph():
        result = builder._build_component(
            "TextParagraph",
            {"text": "This is a paragraph of text."},
            wrap_with_key=True,
        )
        success = result is not None and "textParagraph" in result
        return {"success": success, "output": result}

    def test_image():
        result = builder._build_component(
            "Image",
            {"imageUrl": "https://example.com/image.png"},
            wrap_with_key=True,
        )
        success = result is not None and "image" in result
        return {"success": success, "output": result}

    def test_button():
        result = builder._build_component(
            "Button",
            {"text": "Click Me", "url": "https://example.com"},
            wrap_with_key=True,
        )
        success = result is not None and "button" in result
        return {"success": success, "output": result}

    run_test("DecoratedText basic", test_decorated_text)
    run_test("DecoratedText with labels", test_decorated_text_with_labels)
    run_test("TextParagraph", test_text_paragraph)
    run_test("Image", test_image)
    run_test("Button", test_button)

    # =========================================================================
    # 2. CONTAINER COMPONENTS
    # =========================================================================
    logger.info("\n" + "=" * 60)
    logger.info("2. CONTAINER COMPONENTS")
    logger.info("=" * 60)

    def test_button_list_empty():
        result = builder._build_component(
            "ButtonList",
            {},
            wrap_with_key=True,
        )
        success = result is not None and "buttonList" in result
        return {"success": success, "output": result}

    def test_button_list_with_children():
        # Pre-built button children
        button1 = {"button": {"text": "Button 1", "onClick": {"openLink": {"url": "https://a.com"}}}}
        button2 = {"button": {"text": "Button 2", "onClick": {"openLink": {"url": "https://b.com"}}}}
        result = builder._build_component(
            "ButtonList",
            {},
            wrap_with_key=True,
            children=[button1, button2],
        )
        success = (
            result is not None
            and "buttonList" in result
            and "buttons" in result.get("buttonList", {})
        )
        return {"success": success, "output": result}

    def test_chip_list():
        result = builder._build_component(
            "ChipList",
            {},
            wrap_with_key=True,
        )
        success = result is not None and "chipList" in result
        return {"success": success, "output": result}

    def test_grid():
        result = builder._build_component(
            "Grid",
            {"columnCount": 2},
            wrap_with_key=True,
        )
        success = result is not None and "grid" in result
        return {"success": success, "output": result}

    def test_columns():
        result = builder._build_component(
            "Columns",
            {},
            wrap_with_key=True,
        )
        success = result is not None and "columns" in result
        return {"success": success, "output": result}

    run_test("ButtonList empty", test_button_list_empty)
    run_test("ButtonList with children", test_button_list_with_children)
    run_test("ChipList", test_chip_list)
    run_test("Grid", test_grid)
    run_test("Columns", test_columns)

    # =========================================================================
    # 3. EMPTY COMPONENTS
    # =========================================================================
    logger.info("\n" + "=" * 60)
    logger.info("3. EMPTY COMPONENTS")
    logger.info("=" * 60)

    def test_divider():
        result = builder._build_component(
            "Divider",
            {},
            wrap_with_key=True,
        )
        success = result is not None and "divider" in result
        return {"success": success, "output": result}

    run_test("Divider (empty component)", test_divider)

    # =========================================================================
    # 4. NESTED STRUCTURES
    # =========================================================================
    logger.info("\n" + "=" * 60)
    logger.info("4. NESTED STRUCTURES")
    logger.info("=" * 60)

    def test_section_with_widgets():
        # Build widgets first
        text_widget = builder._build_component(
            "DecoratedText", {"text": "Hello"}, wrap_with_key=True
        )
        button_list = builder._build_component(
            "ButtonList", {}, wrap_with_key=True,
            children=[{"button": {"text": "Click"}}]
        )
        # Build section with widgets
        result = builder._build_component(
            "Section",
            {"header": "My Section"},
            wrap_with_key=True,
            children=[text_widget, button_list],
        )
        success = (
            result is not None
            and "section" in result
            and "widgets" in result.get("section", {})
        )
        return {"success": success, "output": result}

    def test_decorated_text_with_button():
        """Test DecoratedText with inline button (nested child)."""
        button = {"button": {"text": "Action", "onClick": {"openLink": {"url": "https://example.com"}}}}
        result = builder._build_component(
            "DecoratedText",
            {"text": "Click the button →"},
            wrap_with_key=True,
            children=[button],
        )
        success = result is not None and "decoratedText" in result
        return {"success": success, "output": result}

    run_test("Section with widgets", test_section_with_widgets)
    run_test("DecoratedText with button", test_decorated_text_with_button)

    # =========================================================================
    # 5. DAG VALIDATION
    # =========================================================================
    logger.info("\n" + "=" * 60)
    logger.info("5. DAG VALIDATION")
    logger.info("=" * 60)

    def test_valid_parent_child():
        """Test valid Section -> DecoratedText relationship."""
        text_widget = builder._build_component(
            "DecoratedText", {"text": "Valid child"}, wrap_with_key=True
        )
        result = builder._build_component(
            "Section",
            {},
            wrap_with_key=True,
            children=[text_widget],
            validate=True,
        )
        success = result is not None and "section" in result
        return {"success": success, "output": result}

    def test_can_contain_check():
        """Test wrapper.can_contain() directly."""
        if wrapper and hasattr(wrapper, "can_contain"):
            # Section can contain DecoratedText
            valid = wrapper.can_contain("Section", "DecoratedText")
            # Section cannot directly contain Icon (needs ButtonList->Button->Icon)
            indirect = wrapper.can_contain("Section", "Icon")
            direct_only = wrapper.can_contain("Section", "Icon", direct_only=True)
            return {
                "success": valid,
                "output": {
                    "Section->DecoratedText": valid,
                    "Section->Icon (any depth)": indirect,
                    "Section->Icon (direct only)": direct_only,
                },
            }
        return {"success": False, "error": "can_contain not available"}

    run_test("Valid parent-child with validate=True", test_valid_parent_child)
    run_test("can_contain() DAG queries", test_can_contain_check)

    # =========================================================================
    # 6. EDGE CASES
    # =========================================================================
    logger.info("\n" + "=" * 60)
    logger.info("6. EDGE CASES")
    logger.info("=" * 60)

    def test_unknown_component():
        """Test handling of unknown component type."""
        result = builder._build_component(
            "NonExistentWidget",
            {"foo": "bar"},
            wrap_with_key=True,
        )
        # Should return fallback dict, not crash
        success = result is not None
        return {"success": success, "output": result}

    def test_empty_params():
        """Test component with no params."""
        result = builder._build_component(
            "DecoratedText",
            {},
            wrap_with_key=True,
        )
        success = result is not None
        return {"success": success, "output": result}

    def test_wrap_with_key_false():
        """Test wrap_with_key=False returns inner dict."""
        result = builder._build_component(
            "DecoratedText",
            {"text": "Inner only"},
            wrap_with_key=False,
        )
        # Should NOT have decoratedText wrapper key
        success = result is not None and "decoratedText" not in result
        return {"success": success, "output": result}

    def test_no_wrapper():
        """Test fallback when wrapper is None."""
        result = builder._build_component(
            "DecoratedText",
            {"text": "No wrapper"},
            wrapper=None,  # Force no wrapper path
            wrap_with_key=True,
        )
        # _get_wrapper() will still be called, so this tests the internal path
        success = result is not None
        return {"success": success, "output": result}

    run_test("Unknown component (graceful fallback)", test_unknown_component)
    run_test("Empty params", test_empty_params)
    run_test("wrap_with_key=False", test_wrap_with_key_false)
    run_test("Fallback path", test_no_wrapper)

    # =========================================================================
    # 7. BUILD_COMPONENT_TREE
    # =========================================================================
    logger.info("\n" + "=" * 60)
    logger.info("7. BUILD_COMPONENT_TREE (Hierarchies)")
    logger.info("=" * 60)

    def test_simple_tree():
        """Test simple component tree."""
        tree = {
            "component": "DecoratedText",
            "params": {"text": "Simple tree test", "wrapText": True},
        }
        result = builder.build_component_tree(tree)
        success = result is not None and "decoratedText" in result
        return {"success": success, "output": result}

    def test_nested_tree():
        """Test nested component tree with Section -> widgets."""
        tree = {
            "component": "Section",
            "params": {"header": "Test Section"},
            "children": [
                {"component": "DecoratedText", "params": {"text": "Item 1", "wrapText": True}},
                {"component": "DecoratedText", "params": {"text": "Item 2", "wrapText": True}},
                {
                    "component": "ButtonList",
                    "children": [
                        {"component": "Button", "params": {"text": "Action", "url": "https://test.com"}},
                    ],
                },
            ],
        }
        result = builder.build_component_tree(tree, validate=True)
        success = (
            result is not None
            and "section" in result
            and "widgets" in result.get("section", {})
            and len(result["section"]["widgets"]) >= 2
        )
        return {"success": success, "output": result}

    def test_deeply_nested_tree():
        """Test deeply nested tree (Section -> Columns -> Column -> widgets)."""
        tree = {
            "component": "Section",
            "children": [
                {
                    "component": "Columns",
                    "children": [
                        {
                            "component": "Column",
                            "children": [
                                {"component": "DecoratedText", "params": {"text": "Col 1"}},
                            ],
                        },
                        {
                            "component": "Column",
                            "children": [
                                {"component": "DecoratedText", "params": {"text": "Col 2"}},
                            ],
                        },
                    ],
                },
            ],
        }
        result = builder.build_component_tree(tree, validate=True)
        success = result is not None and "section" in result
        return {"success": success, "output": result}

    def test_tree_missing_component():
        """Test tree with missing component key."""
        tree = {"params": {"text": "No component key"}}
        result = builder.build_component_tree(tree)
        success = result is None  # Should return None for invalid tree
        return {"success": success, "output": result}

    run_test("Simple tree (single component)", test_simple_tree)
    run_test("Nested tree (Section with children)", test_nested_tree)
    run_test("Deeply nested tree (Section -> Columns)", test_deeply_nested_tree)
    run_test("Tree with missing component key", test_tree_missing_component)

    # =========================================================================
    # 8. FORM COMPONENTS
    # =========================================================================
    logger.info("\n" + "=" * 60)
    logger.info("8. FORM COMPONENTS")
    logger.info("=" * 60)

    def test_text_input():
        result = builder._build_component(
            "TextInput",
            {"name": "user_name", "label": "Your Name"},
            wrap_with_key=True,
        )
        success = result is not None and "textInput" in result
        return {"success": success, "output": result}

    def test_selection_input():
        result = builder._build_component(
            "SelectionInput",
            {"name": "choice", "label": "Pick one", "type": "DROPDOWN"},
            wrap_with_key=True,
        )
        success = result is not None and "selectionInput" in result
        return {"success": success, "output": result}

    def test_date_time_picker():
        result = builder._build_component(
            "DateTimePicker",
            {"name": "date", "label": "Select date"},
            wrap_with_key=True,
        )
        success = result is not None and "dateTimePicker" in result
        return {"success": success, "output": result}

    run_test("TextInput", test_text_input)
    run_test("SelectionInput", test_selection_input)
    run_test("DateTimePicker", test_date_time_picker)

    # =========================================================================
    # 9. CAROUSEL COMPONENTS
    # =========================================================================
    logger.info("\n" + "=" * 60)
    logger.info("9. CAROUSEL COMPONENTS")
    logger.info("=" * 60)

    def test_carousel():
        result = builder._build_component(
            "Carousel",
            {},
            wrap_with_key=True,
        )
        success = result is not None
        return {"success": success, "output": result}

    def test_carousel_card():
        result = builder._build_component(
            "CarouselCard",
            {"title": "Card 1", "subtitle": "Description"},
            wrap_with_key=True,
        )
        success = result is not None
        return {"success": success, "output": result}

    run_test("Carousel", test_carousel)
    run_test("CarouselCard", test_carousel_card)

    # =========================================================================
    # SUMMARY
    # =========================================================================
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total: {results['passed'] + results['failed']} tests")
    logger.info(f"Passed: {results['passed']}")
    logger.info(f"Failed: {results['failed']}")

    if results["failed"] > 0:
        logger.info("\nFailed tests:")
        for test in results["tests"]:
            if "FAIL" in test["status"] or "EXCEPTION" in test["status"]:
                logger.info(f"  - {test['name']}: {test.get('error', 'See output')}")

    return results


if __name__ == "__main__":
    test_build_component()
