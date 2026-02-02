"""
Test return_instance feature of _build_component.

Tests:
1. Building component instances (not JSON)
2. Building full Card hierarchy using instances
3. Sending to actual webhook to verify rendering
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


def test_return_instance():
    """Test return_instance feature."""
    from gchat.card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()
    wrapper = builder._get_wrapper()

    print("=" * 60)
    print("1. TEST RETURN_INSTANCE WITH BASIC COMPONENTS")
    print("=" * 60)

    # Test DecoratedText instance
    dt_instance = builder._build_component(
        "DecoratedText",
        {"text": "Hello from instance!", "wrap_text": True},
        return_instance=True,
    )
    print(f"DecoratedText instance: {type(dt_instance).__name__}")
    print(f"  Has render(): {hasattr(dt_instance, 'render')}")
    if dt_instance and hasattr(dt_instance, "render"):
        rendered = dt_instance.render()
        print(f"  Rendered: {json.dumps(rendered, indent=2)[:200]}")

    # Test Button instance
    btn_instance = builder._build_component(
        "Button",
        {"text": "Click Me", "url": "https://example.com"},
        return_instance=True,
    )
    print(f"\nButton instance: {type(btn_instance).__name__}")

    # Test Section instance
    section_instance = builder._build_component(
        "Section",
        {"header": "Test Section"},
        return_instance=True,
    )
    print(f"\nSection instance: {type(section_instance).__name__}")

    print("\n" + "=" * 60)
    print("2. BUILD FULL CARD USING INSTANCES")
    print("=" * 60)

    # Build child instances first
    header_instance = builder._build_component(
        "CardHeader",
        {"title": "🧪 Instance Test Card", "subtitle": "Built using return_instance=True"},
        return_instance=True,
    )
    print(f"CardHeader: {type(header_instance).__name__}")

    # Build widgets for section
    dt1 = builder._build_component(
        "DecoratedText",
        {"text": "This card was built using component instances!", "wrap_text": True},
        return_instance=True,
    )
    dt2 = builder._build_component(
        "DecoratedText",
        {"text": "Each widget is a real Python object, not a JSON dict.", "wrap_text": True},
        return_instance=True,
    )
    # Button must be inside ButtonList (not directly in Section widgets)
    btn = builder._build_component(
        "Button",
        {"text": "🎉 It Works!", "url": "https://example.com"},
        return_instance=True,
    )
    btn_list = builder._build_component(
        "ButtonList",
        {},
        return_instance=True,
        child_instances=[btn] if btn else None,
    )
    print(f"ButtonList: {type(btn_list).__name__ if btn_list else 'None'}")

    # Build Section with widget instances
    widgets = [w for w in [dt1, dt2, btn_list] if w]
    section_with_widgets = builder._build_component(
        "Section",
        {"header": "Component Instances"},
        return_instance=True,
        child_instances=widgets,
    )
    print(f"Section with widgets: {type(section_with_widgets).__name__}")
    if section_with_widgets and hasattr(section_with_widgets, "widgets"):
        print(f"  Widgets count: {len(section_with_widgets.widgets) if section_with_widgets.widgets else 0}")

    # Build Card with header and section instances
    card_instance = builder._build_component(
        "Card",
        {},
        return_instance=True,
        child_instances=[header_instance, section_with_widgets] if header_instance and section_with_widgets else None,
    )
    print(f"Card: {type(card_instance).__name__}")

    # Render the full card
    if card_instance and hasattr(card_instance, "render"):
        card_json = card_instance.render()
        # Convert to camelCase for Google Chat API
        card_json = builder._convert_to_camel_case(card_json)
        print(f"\nFull Card JSON:")
        print(json.dumps(card_json, indent=2))

        print("\n" + "=" * 60)
        print("3. SEND TO WEBHOOK")
        print("=" * 60)

        webhook_url = os.environ.get("TEST_CHAT_WEBHOOK")
        if not webhook_url:
            print("⚠️ TEST_CHAT_WEBHOOK not set, skipping webhook test")
            return card_json

        # Wrap in cardsV2 format
        import time
        message_payload = {
            "cardsV2": [
                {
                    "cardId": f"instance_test_{int(time.time())}",
                    "card": card_json.get("card", card_json),
                }
            ]
        }

        print(f"Sending to: {webhook_url[:60]}...")
        try:
            response = httpx.post(
                webhook_url,
                json=message_payload,
                timeout=30,
                verify=False,  # Disable SSL verification for testing
            )
            print(f"Response status: {response.status_code}")
            if response.status_code == 200:
                print("✅ Card sent successfully!")
                return card_json
            else:
                print(f"❌ Error: {response.text[:500]}")
        except Exception as e:
            print(f"❌ Request failed: {e}")

        return card_json
    else:
        print("❌ Card instance failed to build or has no render() method")
        return None


def test_full_card_with_multiple_sections():
    """Test building a more complex card with multiple sections."""
    from gchat.card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()

    print("\n" + "=" * 60)
    print("4. COMPLEX CARD WITH MULTIPLE SECTIONS")
    print("=" * 60)

    # Header
    header = builder._build_component(
        "CardHeader",
        {"title": "📊 Status Dashboard", "subtitle": "Built with instances"},
        return_instance=True,
    )

    # Section 1: Status info
    status_widgets = [
        builder._build_component("DecoratedText", {"text": "🟢 API: Online", "wrap_text": True}, return_instance=True),
        builder._build_component("DecoratedText", {"text": "🟢 Database: Connected", "wrap_text": True}, return_instance=True),
        builder._build_component("DecoratedText", {"text": "🟡 Cache: Warming up", "wrap_text": True}, return_instance=True),
    ]
    section1 = builder._build_component(
        "Section",
        {"header": "System Status"},
        return_instance=True,
        child_instances=[w for w in status_widgets if w],
    )

    # Section 2: Actions (buttons must be in ButtonList)
    btn1 = builder._build_component("Button", {"text": "🔄 Refresh", "url": "https://example.com/refresh"}, return_instance=True)
    btn2 = builder._build_component("Button", {"text": "📋 Logs", "url": "https://example.com/logs"}, return_instance=True)
    btn_list = builder._build_component(
        "ButtonList",
        {},
        return_instance=True,
        child_instances=[b for b in [btn1, btn2] if b],
    )
    section2 = builder._build_component(
        "Section",
        {"header": "Quick Actions"},
        return_instance=True,
        child_instances=[btn_list] if btn_list else [],
    )

    # Build Card
    card = builder._build_component(
        "Card",
        {},
        return_instance=True,
        child_instances=[c for c in [header, section1, section2] if c],
    )

    if card and hasattr(card, "render"):
        card_json = builder._convert_to_camel_case(card.render())
        print(f"Card JSON:")
        print(json.dumps(card_json, indent=2)[:800])

        # Send to webhook
        webhook_url = os.environ.get("TEST_CHAT_WEBHOOK")
        if webhook_url:
            import time
            message_payload = {
                "cardsV2": [
                    {
                        "cardId": f"dashboard_test_{int(time.time())}",
                        "card": card_json.get("card", card_json),
                    }
                ]
            }
            try:
                response = httpx.post(webhook_url, json=message_payload, timeout=30, verify=False)
                print(f"\n✅ Complex card sent! Status: {response.status_code}")
            except Exception as e:
                print(f"\n❌ Failed to send: {e}")
    else:
        print("❌ Card build failed")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    test_return_instance()
    test_full_card_with_multiple_sections()
