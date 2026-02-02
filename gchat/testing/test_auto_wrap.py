"""
Test auto_wrap feature of _build_component.

Tests the DAG-based automatic wrapping capability:
- Button with target_parent=Section → ButtonList[Button]
- Chip with target_parent=Section → ChipList[Chip]
- DecoratedText with target_parent=Section → no wrapping (direct child)
"""

import json
import os
import sys
import warnings
from pathlib import Path

import httpx

# Suppress SSL warnings for testing
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_auto_wrap_button():
    """Test auto_wrap for Button → ButtonList."""
    from gchat.smart_card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()

    print("=" * 60)
    print("TEST 1: Button auto_wrap → ButtonList")
    print("=" * 60)

    # Button should be auto-wrapped in ButtonList
    result = builder._build_component(
        "Button",
        {"text": "Click Me", "url": "https://example.com"},
        wrap_with_key=True,
        auto_wrap=True,
        target_parent="Section",
    )

    # Should be wrapped in buttonList
    assert "buttonList" in result, f"Expected buttonList wrapper, got: {list(result.keys())}"
    assert "buttons" in result["buttonList"], "Expected buttons array in buttonList"
    buttons = result["buttonList"]["buttons"]
    assert len(buttons) == 1, f"Expected 1 button, got {len(buttons)}"
    print("✅ Button correctly wrapped in ButtonList")
    print(f"   Output: {json.dumps(result, indent=2)[:300]}")

    return True


def test_auto_wrap_chip():
    """Test auto_wrap for Chip → ChipList."""
    from gchat.smart_card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()

    print("\n" + "=" * 60)
    print("TEST 2: Chip auto_wrap → ChipList")
    print("=" * 60)

    result = builder._build_component(
        "Chip",
        {"label": "Tag 1", "url": "https://example.com"},
        wrap_with_key=True,
        auto_wrap=True,
        target_parent="Section",
    )

    assert "chipList" in result, f"Expected chipList wrapper, got: {list(result.keys())}"
    print("✅ Chip correctly wrapped in ChipList")
    print(f"   Output: {json.dumps(result, indent=2)[:300]}")

    return True


def test_no_wrap_decorated_text():
    """Test that DecoratedText doesn't get wrapped (direct child of Section)."""
    from gchat.smart_card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()

    print("\n" + "=" * 60)
    print("TEST 3: DecoratedText - no wrapping needed")
    print("=" * 60)

    result = builder._build_component(
        "DecoratedText",
        {"text": "Direct child of Section", "wrapText": True},
        wrap_with_key=True,
        auto_wrap=True,
        target_parent="Section",
    )

    # Should NOT be wrapped - decoratedText is a valid direct child
    assert "decoratedText" in result, f"Expected decoratedText, got: {list(result.keys())}"
    assert "buttonList" not in result, "DecoratedText should not be wrapped"
    print("✅ DecoratedText not wrapped (correct)")
    print(f"   Output: {json.dumps(result, indent=2)[:200]}")

    return True


def test_auto_wrap_return_instance():
    """Test auto_wrap with return_instance=True."""
    from gchat.smart_card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()

    print("\n" + "=" * 60)
    print("TEST 4: auto_wrap + return_instance=True")
    print("=" * 60)

    # Button with return_instance should return a ButtonList instance
    instance = builder._build_component(
        "Button",
        {"text": "Instance Button", "url": "https://example.com"},
        auto_wrap=True,
        target_parent="Section",
        return_instance=True,
    )

    instance_name = type(instance).__name__
    assert instance_name == "ButtonList", f"Expected ButtonList instance, got: {instance_name}"
    print(f"✅ Returned instance type: {instance_name}")

    # Verify it can render
    if hasattr(instance, "render"):
        rendered = builder._convert_to_camel_case(instance.render())
        print(f"   Rendered: {json.dumps(rendered, indent=2)[:200]}")

    return True


def test_full_card_with_auto_wrap():
    """Test building a complete card using auto_wrap."""
    from gchat.smart_card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()

    print("\n" + "=" * 60)
    print("TEST 5: Full card with auto_wrap")
    print("=" * 60)

    # Build header
    header = builder._build_component(
        "CardHeader",
        {"title": "Auto-Wrap Test Card", "subtitle": "Using DAG-based wrapping"},
        return_instance=True,
    )

    # Build widgets - Button will be auto-wrapped
    dt = builder._build_component(
        "DecoratedText",
        {"text": "Text goes directly in Section", "wrapText": True},
        return_instance=True,
    )

    btn = builder._build_component(
        "Button",
        {"text": "Auto-Wrapped Button", "url": "https://example.com"},
        auto_wrap=True,
        target_parent="Section",
        return_instance=True,
    )

    # Build Section with mixed children
    section = builder._build_component(
        "Section",
        {"header": "Mixed Widgets"},
        return_instance=True,
        child_instances=[dt, btn],
    )

    # Build Card
    card = builder._build_component(
        "Card",
        {},
        return_instance=True,
        child_instances=[header, section],
    )

    # Render
    card_json = None
    if card and hasattr(card, "render"):
        card_json = builder._convert_to_camel_case(card.render())

        # Verify structure
        sections = card_json.get("card", {}).get("sections", [])
        assert len(sections) == 1, f"Expected 1 section, got {len(sections)}"

        widgets = sections[0].get("widgets", [])
        assert len(widgets) == 2, f"Expected 2 widgets, got {len(widgets)}"

        # First widget should be decoratedText
        assert "decoratedText" in widgets[0], "First widget should be decoratedText"
        # Second widget should be buttonList
        assert "buttonList" in widgets[1], "Second widget should be buttonList"

        print("✅ Card structure correct")
        print(f"   {len(widgets)} widgets: decoratedText, buttonList")

    return card_json


def test_send_to_webhook():
    """Send the auto-wrapped card to webhook."""
    import time

    card_json = test_full_card_with_auto_wrap()
    if not card_json:
        print("❌ No card JSON to send")
        return False

    print("\n" + "=" * 60)
    print("TEST 6: Send to Webhook")
    print("=" * 60)

    webhook_url = os.environ.get("TEST_CHAT_WEBHOOK")
    if not webhook_url:
        print("⚠️ TEST_CHAT_WEBHOOK not set, skipping webhook test")
        return True

    payload = {
        "cardsV2": [
            {
                "cardId": f"auto_wrap_test_{int(time.time())}",
                "card": card_json.get("card", card_json),
            }
        ]
    }

    try:
        response = httpx.post(webhook_url, json=payload, timeout=30, verify=False)
        if response.status_code == 200:
            print("✅ Card sent successfully!")
            return True
        else:
            print(f"❌ Error: {response.status_code} - {response.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return False


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    results = {
        "passed": 0,
        "failed": 0,
    }

    tests = [
        test_auto_wrap_button,
        test_auto_wrap_chip,
        test_no_wrap_decorated_text,
        test_auto_wrap_return_instance,
        test_send_to_webhook,
    ]

    for test in tests:
        try:
            if test():
                results["passed"] += 1
            else:
                results["failed"] += 1
        except AssertionError as e:
            print(f"❌ FAILED: {e}")
            results["failed"] += 1
        except Exception as e:
            print(f"❌ ERROR: {e}")
            results["failed"] += 1

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Passed: {results['passed']}")
    print(f"Failed: {results['failed']}")
