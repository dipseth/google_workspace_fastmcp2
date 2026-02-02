#!/usr/bin/env python3
"""
Test Button parameters using card_framework via ModuleWrapper.

Tests all Button fields against the Google Chat webhook:
- text, icon (knownIcon, materialIcon)
- color (RGB), type (OUTLINED, FILLED, FILLED_TONAL, BORDERLESS)
- onClick (openLink), disabled, altText

Uses the wrapped module components (including custom components like Carousel)
instead of direct imports, demonstrating the full ModuleWrapper pipeline.
"""

import json
import os
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gchat.card_framework_wrapper import get_card_framework_wrapper

WEBHOOK_URL = os.environ.get(
    "TEST_CHAT_WEBHOOK",
    "https://chat.googleapis.com/v1/spaces/AAQAKl_yP9Y/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=Ie8-brhWHA9kE_2JiqKRDhqjadPHK4RNe15UcWwLXDA",
)


def snake_to_camel(s: str) -> str:
    """Convert snake_case to camelCase."""
    components = s.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def convert_keys_to_camel(obj):
    """Recursively convert dict keys from snake_case to camelCase."""
    if isinstance(obj, dict):
        return {snake_to_camel(k): convert_keys_to_camel(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_keys_to_camel(item) for item in obj]
    return obj


class WrappedComponents:
    """
    Helper to access card_framework components via ModuleWrapper.

    Provides easy access to both standard and custom components.
    """

    def __init__(self):
        self.wrapper = get_card_framework_wrapper()
        self.module = self.wrapper.module
        self._cache = {}

    def get(self, name: str):
        """Get a component class by name."""
        if name in self._cache:
            return self._cache[name]

        # Search for the component
        results = self.wrapper.search(name, limit=1)
        if results and results[0].get("component"):
            cls = results[0]["component"]
            self._cache[name] = cls
            return cls

        # Try direct path lookup
        for path in [
            f"card_framework.v2.widgets.{name.lower()}.{name}",
            f"card_framework.v2.{name.lower()}.{name}",
            f"card_framework.v2.widgets.{name}",
            f"card_framework.v2.{name}",
        ]:
            cls = self.wrapper.get_component_by_path(path)
            if cls:
                self._cache[name] = cls
                return cls

        return None

    @property
    def Button(self):
        return self.get("Button")

    @property
    def ButtonList(self):
        return self.get("ButtonList")

    @property
    def Icon(self):
        return self.get("Icon")

    @property
    def Color(self):
        return self.get("Color")

    @property
    def OnClick(self):
        return self.get("OnClick")

    @property
    def OpenLink(self):
        return self.get("OpenLink")

    @property
    def TextParagraph(self):
        return self.get("TextParagraph")

    @property
    def DecoratedText(self):
        return self.get("DecoratedText")

    @property
    def Section(self):
        return self.get("Section")

    @property
    def Card(self):
        return self.get("Card")

    @property
    def CardHeader(self):
        return self.get("CardHeader")

    @property
    def Message(self):
        return self.get("Message")

    @property
    def CardWithId(self):
        """CardWithId is in card_framework.v2.card module."""
        if "CardWithId" not in self._cache:
            from card_framework.v2.card import CardWithId

            self._cache["CardWithId"] = CardWithId
        return self._cache["CardWithId"]

    # Custom components (registered via wrapper)
    @property
    def Carousel(self):
        return self.get("Carousel")

    @property
    def CarouselCard(self):
        return self.get("CarouselCard")

    @property
    def NestedWidget(self):
        return self.get("NestedWidget")

    def get_symbol(self, name: str) -> str:
        """Get the DSL symbol for a component."""
        return self.wrapper.symbol_mapping.get(name, "")


# Global instance
components = None


def get_components() -> WrappedComponents:
    """Get the wrapped components singleton."""
    global components
    if components is None:
        components = WrappedComponents()
    return components


def send_message(message, description: str = "") -> bool:
    """Render message and send to webhook."""
    print(f"\n{'='*60}")
    print(f"TEST: {description}")
    print(f"{'='*60}")

    # Render and convert to camelCase
    rendered = message.render()
    payload = convert_keys_to_camel(rendered)

    print(f"Payload preview: {json.dumps(payload, indent=2)[:400]}...")

    try:
        response = httpx.post(
            WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30.0,
        )

        if response.status_code == 200:
            print(f"✅ SUCCESS")
            return True
        else:
            print(f"❌ FAILED ({response.status_code})")
            print(f"Error: {response.text[:300]}")
            return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


def test_button_types():
    """Test all Button type variants."""
    c = get_components()

    Button = c.Button
    ButtonList = c.ButtonList
    OnClick = c.OnClick
    OpenLink = c.OpenLink
    CardHeader = c.CardHeader
    Section = c.Section
    CardWithId = c.CardWithId
    Message = c.Message

    buttons = [
        Button(
            text="OUTLINED (default)",
            type_=Button.Type.OUTLINED,
            on_click=OnClick(open_link=OpenLink(url="https://google.com")),
        ),
        Button(
            text="FILLED",
            type_=Button.Type.FILLED,
            on_click=OnClick(open_link=OpenLink(url="https://google.com")),
        ),
        Button(
            text="FILLED_TONAL",
            type_=Button.Type.FILLED_TONAL,
            on_click=OnClick(open_link=OpenLink(url="https://google.com")),
        ),
        Button(
            text="BORDERLESS",
            type_=Button.Type.BORDERLESS,
            on_click=OnClick(open_link=OpenLink(url="https://google.com")),
        ),
    ]

    card = CardWithId(
        header=CardHeader(title="Button Types (Wrapped)", subtitle="Via ModuleWrapper"),
        sections=[Section(widgets=[ButtonList(buttons=buttons)])],
        _CardWithId__card_id="button-types-wrapped",
    )

    return send_message(Message(cards_v2=[card]), "Button Type Variants (Wrapped)")


def test_button_colors():
    """Test Button color parameter (forces FILLED type)."""
    c = get_components()

    Button = c.Button
    ButtonList = c.ButtonList
    Color = c.Color
    OnClick = c.OnClick
    OpenLink = c.OpenLink
    CardHeader = c.CardHeader
    Section = c.Section
    CardWithId = c.CardWithId
    Message = c.Message

    buttons = [
        Button(
            text="Red",
            color=Color(red=1.0, green=0.0, blue=0.0),
            on_click=OnClick(open_link=OpenLink(url="https://google.com")),
        ),
        Button(
            text="Green",
            color=Color(red=0.0, green=0.7, blue=0.0),
            on_click=OnClick(open_link=OpenLink(url="https://google.com")),
        ),
        Button(
            text="Blue",
            color=Color(red=0.0, green=0.4, blue=0.9),
            on_click=OnClick(open_link=OpenLink(url="https://google.com")),
        ),
        Button(
            text="Purple",
            color=Color(red=0.6, green=0.2, blue=0.8),
            on_click=OnClick(open_link=OpenLink(url="https://google.com")),
        ),
    ]

    card = CardWithId(
        header=CardHeader(
            title="Button Colors (Wrapped)", subtitle="RGB via ModuleWrapper"
        ),
        sections=[Section(widgets=[ButtonList(buttons=buttons)])],
        _CardWithId__card_id="button-colors-wrapped",
    )

    return send_message(Message(cards_v2=[card]), "Button Colors (Wrapped)")


def test_button_icons():
    """Test Button with knownIcon and materialIcon."""
    c = get_components()

    Button = c.Button
    ButtonList = c.ButtonList
    Icon = c.Icon
    OnClick = c.OnClick
    OpenLink = c.OpenLink
    CardHeader = c.CardHeader
    Section = c.Section
    CardWithId = c.CardWithId
    Message = c.Message

    buttons = [
        Button(
            text="Known: STAR",
            icon=Icon(known_icon=Icon.KnownIcon.STAR),
            on_click=OnClick(open_link=OpenLink(url="https://google.com")),
        ),
        Button(
            text="Known: BOOKMARK",
            icon=Icon(known_icon=Icon.KnownIcon.BOOKMARK),
            on_click=OnClick(open_link=OpenLink(url="https://google.com")),
        ),
        Button(
            text="Material: settings",
            icon=Icon(material_icon=Icon.MaterialIcon(name="settings")),
            on_click=OnClick(open_link=OpenLink(url="https://google.com")),
        ),
        Button(
            text="Material: refresh",
            icon=Icon(material_icon=Icon.MaterialIcon(name="refresh")),
            on_click=OnClick(open_link=OpenLink(url="https://google.com")),
        ),
    ]

    card = CardWithId(
        header=CardHeader(title="Button Icons (Wrapped)", subtitle="Via ModuleWrapper"),
        sections=[Section(widgets=[ButtonList(buttons=buttons)])],
        _CardWithId__card_id="button-icons-wrapped",
    )

    return send_message(Message(cards_v2=[card]), "Button Icons (Wrapped)")


def test_button_states():
    """Test disabled and altText parameters."""
    c = get_components()

    Button = c.Button
    ButtonList = c.ButtonList
    OnClick = c.OnClick
    OpenLink = c.OpenLink
    CardHeader = c.CardHeader
    Section = c.Section
    CardWithId = c.CardWithId
    Message = c.Message

    buttons = [
        Button(
            text="Enabled",
            disabled=False,
            alt_text="This button is enabled and clickable",
            on_click=OnClick(open_link=OpenLink(url="https://google.com")),
        ),
        Button(
            text="Disabled",
            disabled=True,
            alt_text="This button is disabled",
            on_click=OnClick(open_link=OpenLink(url="https://google.com")),
        ),
    ]

    card = CardWithId(
        header=CardHeader(
            title="Button States (Wrapped)", subtitle="Via ModuleWrapper"
        ),
        sections=[Section(widgets=[ButtonList(buttons=buttons)])],
        _CardWithId__card_id="button-states-wrapped",
    )

    return send_message(Message(cards_v2=[card]), "Button Disabled/AltText (Wrapped)")


def test_full_button():
    """Test Button with all parameters combined."""
    c = get_components()

    Button = c.Button
    ButtonList = c.ButtonList
    Icon = c.Icon
    Color = c.Color
    OnClick = c.OnClick
    OpenLink = c.OpenLink
    TextParagraph = c.TextParagraph
    CardHeader = c.CardHeader
    Section = c.Section
    CardWithId = c.CardWithId
    Message = c.Message

    btn = Button(
        text="Full Featured Button",
        icon=Icon(material_icon=Icon.MaterialIcon(name="rocket_launch")),
        color=Color(red=0.1, green=0.5, blue=0.8),
        on_click=OnClick(open_link=OpenLink(url="https://google.com")),
        disabled=False,
        alt_text="A fully configured button with icon, color, and link",
        type_=Button.Type.FILLED,
    )

    # Show DSL symbols for components used
    symbols_text = (
        f"Symbols: Button={c.get_symbol('Button')}, Icon={c.get_symbol('Icon')}"
    )

    card = CardWithId(
        header=CardHeader(
            title="Full Button (Wrapped)", subtitle="All params via ModuleWrapper"
        ),
        sections=[
            Section(
                widgets=[
                    TextParagraph(
                        text=f"<b>Button with all parameters:</b><br>{symbols_text}"
                    ),
                    ButtonList(buttons=[btn]),
                ]
            )
        ],
        _CardWithId__card_id="button-full-wrapped",
    )

    return send_message(Message(cards_v2=[card]), "Full Button Parameters (Wrapped)")


def test_wrapped_component_info():
    """Test that we can access component info from wrapper."""
    c = get_components()
    wrapper = c.wrapper

    # Show component info
    print("\n" + "=" * 60)
    print("WRAPPED COMPONENT INFO")
    print("=" * 60)

    components_to_check = ["Button", "Icon", "Color", "OnClick", "Section", "Card"]

    for name in components_to_check:
        cls = c.get(name)
        symbol = c.get_symbol(name)
        print(f"  {name}: {cls.__name__ if cls else 'NOT FOUND'} (symbol: {symbol})")

    # Check custom components
    print("\nCustom Components (Google Chat API only):")
    custom = ["Carousel", "CarouselCard", "NestedWidget"]
    for name in custom:
        symbol = c.get_symbol(name)
        # Custom components are registered but may not have Python classes
        print(f"  {name}: symbol={symbol}")

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("BUTTON PARAMETERS TEST")
    print("Using ModuleWrapper for component access")
    print("=" * 60)

    # First show component info
    test_wrapped_component_info()

    tests = [
        test_button_types,
        test_button_colors,
        test_button_icons,
        test_button_states,
        test_full_button,
    ]

    results = []
    for test in tests:
        result = test()
        results.append((test.__name__, result))
        time.sleep(1)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    failed = len(results) - passed

    for name, result in results:
        status = "✅" if result else "❌"
        print(f"  {status} {name}")

    print(f"\nTotal: {passed} passed, {failed} failed")
