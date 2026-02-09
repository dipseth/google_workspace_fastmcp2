#!/usr/bin/env python3
"""
Demonstrate Variation Generation with Google Chat webhook.

Shows:
1. DAG-based structural variations
2. Parameter variations
3. Caching of variation families
4. Sending sample variations to webhook
"""

import json
import os
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WEBHOOK_URL = os.environ.get(
    "TEST_CHAT_WEBHOOK",
    "https://chat.googleapis.com/v1/spaces/AAQAKl_yP9Y/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=Ie8-brhWHA9kE_2JiqKRDhqjadPHK4RNe15UcWwLXDA",
)


def snake_to_camel(s: str) -> str:
    components = s.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def convert_keys_to_camel(obj):
    if isinstance(obj, dict):
        return {snake_to_camel(k): convert_keys_to_camel(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_keys_to_camel(item) for item in obj]
    return obj


def send_card(payload: dict, description: str = "") -> bool:
    """Send a card to the webhook."""
    print(f"\n{'='*60}")
    print(f"SENDING: {description}")
    print(f"{'='*60}")

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


def demo_variation_generation():
    """Demonstrate variation generation from a base pattern."""
    print("\n" + "=" * 60)
    print("VARIATION GENERATION DEMO")
    print("=" * 60)

    from adapters.module_wrapper.variation_generator import (
        VariationGenerator,
        get_variation_generator,
    )
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()
    generator = get_variation_generator()

    # Base pattern
    base_pattern = {
        "card_id": "demo_base_pattern",
        "component_paths": ["Section", "DecoratedText", "ButtonList", "Button"],
        "instance_params": {
            "text": "Server Status",
            "top_label": "Status",
            "buttons": [
                {"text": "Refresh", "url": "https://example.com/refresh"},
                {"text": "Details", "url": "https://example.com/details"},
            ],
        },
        "card_description": "A status card with action buttons",
    }

    print(f"\n1️⃣  Base pattern:")
    print(f"   Components: {base_pattern['component_paths']}")
    print(f"   Params: {list(base_pattern['instance_params'].keys())}")

    # Generate variations
    print(f"\n2️⃣  Generating variations...")
    family = generator.generate_variations(
        pattern=base_pattern,
        num_structure_variations=3,
        num_param_variations=2,
    )

    print(f"   Generated {family.size} variations")
    print(f"   Parent key: {family.parent_key}")

    # Show variations by type
    print(f"\n3️⃣  Variations by type:")
    type_counts = {}
    for v in family.variations:
        type_counts[v.variation_type] = type_counts.get(v.variation_type, 0) + 1
        if v.variation_type != "original":
            print(f"   [{v.variation_type}] {v.cache_key}")
            print(f"      Components: {v.component_paths}")

    print(f"\n   Type counts: {type_counts}")

    # Cache stats
    from adapters.module_wrapper.component_cache import get_component_cache

    cache = get_component_cache()
    print(f"\n4️⃣  Cache stats after variation generation:")
    print(f"   {cache}")

    return family


def demo_feedbackloop_variations():
    """Demonstrate variation generation via FeedbackLoop."""
    print("\n" + "=" * 60)
    print("FEEDBACKLOOP VARIATION GENERATION")
    print("=" * 60)

    from gchat.feedback_loop import get_feedback_loop

    fl = get_feedback_loop()

    # Store a pattern with variations
    print("\n1️⃣  Storing pattern with variation generation...")
    point_id = fl.store_instance_pattern(
        card_description="Dashboard status card showing system health",
        component_paths=["Section", "DecoratedText", "DecoratedText", "ButtonList"],
        instance_params={
            "title": "System Health",
            "items": [
                {"text": "CPU: 45%", "top_label": "CPU"},
                {"text": "Memory: 67%", "top_label": "Memory"},
            ],
            "buttons": [{"text": "View Details"}],
        },
        content_feedback="positive",
        form_feedback="positive",
        card_id="fl_variation_demo",
        structure_description="Dashboard with multiple status items",
        generate_variations=True,
        num_structure_variations=3,
        num_param_variations=2,
    )

    print(f"   Stored pattern: {point_id[:8] if point_id else 'FAILED'}...")

    # Get a random variation
    print("\n2️⃣  Retrieving random variation...")
    variation = fl.get_cached_variation("fl_variation_demo")
    if variation:
        print(f"   Key: {variation['key']}")
        print(f"   Components: {variation['component_paths']}")
        print(f"   From cache: {variation.get('_from_cache', False)}")
    else:
        print("   No variation found")

    # Get a structure variation specifically
    print("\n3️⃣  Retrieving structure variation...")
    struct_var = fl.get_cached_variation("fl_variation_demo", "structure")
    if struct_var:
        print(f"   Key: {struct_var['key']}")
        print(f"   Components: {struct_var['component_paths']}")
    else:
        print("   No structure variation found")

    return point_id


def build_variation_showcase_card(family):
    """Build a card showing the variation family."""
    from card_framework.v2.card import CardHeader, CardWithId
    from card_framework.v2.message import Message
    from card_framework.v2.widgets.text_paragraph import TextParagraph
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    # Get cached classes
    Section = wrapper.get_cached_class("Section")
    DecoratedText = wrapper.get_cached_class("DecoratedText")

    # Build sections for each variation type
    sections = []

    # Header section
    sections.append(
        Section(
            header="Overview",
            widgets=[
                TextParagraph(
                    text=f"<b>Parent Key:</b> {family.parent_key}\n"
                    f"<b>Total Variations:</b> {family.size}"
                ),
            ],
        )
    )

    # Group by type
    by_type = {}
    for v in family.variations:
        by_type.setdefault(v.variation_type, []).append(v)

    for vtype, variations in by_type.items():
        widgets = []
        for i, v in enumerate(variations[:3]):  # Show max 3 per type
            components_str = " → ".join(v.component_paths[:4])
            if len(v.component_paths) > 4:
                components_str += "..."

            widgets.append(
                DecoratedText(
                    text=f"<code>{components_str}</code>",
                    top_label=f"v{i}: {v.cache_key.split(':')[-1]}",
                )
            )

        if widgets:
            emoji = {"original": "🎯", "structure": "🏗️", "parameter": "⚙️"}.get(
                vtype, "📦"
            )
            sections.append(
                Section(
                    header=f"{emoji} {vtype.title()} ({len(variations)})",
                    widgets=widgets,
                )
            )

    card = CardWithId(
        header=CardHeader(
            title="🔀 Variation Family",
            subtitle=f"{family.size} variations generated",
        ),
        sections=sections,
        _CardWithId__card_id="variation-showcase",
    )

    message = Message(cards_v2=[card])
    rendered = message.render()
    return convert_keys_to_camel(rendered)


def build_sample_variation_cards(family, max_cards: int = 2):
    """Build cards from actual variations to show they're valid."""
    from card_framework.v2.card import CardHeader, CardWithId
    from card_framework.v2.message import Message
    from card_framework.v2.widgets.on_click import OnClick, OpenLink
    from card_framework.v2.widgets.text_paragraph import TextParagraph
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    cards = []

    # Get one structure variation and one parameter variation
    variations_to_show = []
    for vtype in ["structure", "parameter"]:
        for v in family.variations:
            if v.variation_type == vtype:
                variations_to_show.append(v)
                break

    for v in variations_to_show[:max_cards]:
        # Get cached classes for this variation's components
        Section = wrapper.get_cached_class("Section")
        DecoratedText = wrapper.get_cached_class("DecoratedText")
        ButtonList = wrapper.get_cached_class("ButtonList")
        Button = wrapper.get_cached_class("Button")

        # Build widgets based on variation params
        params = v.instance_params
        widgets = []

        # Status widget
        text = params.get("text", "Sample Status")
        label = params.get("top_label", "Status")
        widgets.append(
            DecoratedText(
                text=f"<b>{text}</b>",
                top_label=label,
            )
        )

        # DSL notation
        if v.dsl_notation:
            widgets.append(TextParagraph(text=f"<i>DSL: {v.dsl_notation[:60]}...</i>"))

        # Add button if ButtonList in components
        if "ButtonList" in v.component_paths or "Button" in v.component_paths:
            buttons_data = params.get("buttons", [{"text": "Action"}])
            buttons = []
            for btn in buttons_data[:2]:
                btn_text = (
                    btn.get("text", "Click") if isinstance(btn, dict) else str(btn)
                )
                buttons.append(
                    Button(
                        text=btn_text,
                        on_click=OnClick(open_link=OpenLink(url="https://example.com")),
                    )
                )
            if buttons:
                widgets.append(ButtonList(buttons=buttons))

        # Build card
        emoji = "🏗️" if v.variation_type == "structure" else "⚙️"
        card = CardWithId(
            header=CardHeader(
                title=f"{emoji} {v.variation_type.title()} Variation",
                subtitle=f"Cache key: {v.cache_key}",
            ),
            sections=[Section(widgets=widgets)],
            _CardWithId__card_id=f"variation-{v.variation_id}",
        )

        message = Message(cards_v2=[card])
        rendered = message.render()
        cards.append(convert_keys_to_camel(rendered))

    return cards


def demo_summary_card(family, generator_stats):
    """Build a summary card for the variation system."""
    from card_framework.v2.card import CardHeader, CardWithId
    from card_framework.v2.message import Message
    from card_framework.v2.widgets.text_paragraph import TextParagraph
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    Section = wrapper.get_cached_class("Section")
    DecoratedText = wrapper.get_cached_class("DecoratedText")

    from adapters.module_wrapper.component_cache import get_component_cache

    cache = get_component_cache()
    cache_stats = cache.stats

    card = CardWithId(
        header=CardHeader(
            title="🎯 Variation System Summary",
            subtitle="DAG-based pattern expansion",
        ),
        sections=[
            Section(
                header="📊 Generator Stats",
                widgets=[
                    DecoratedText(
                        text=f"<b>{generator_stats['num_families']}</b>",
                        top_label="Pattern Families",
                    ),
                    DecoratedText(
                        text=f"<b>{generator_stats['total_variations']}</b>",
                        top_label="Total Variations",
                    ),
                    DecoratedText(
                        text=f"<b>{generator_stats['avg_variations_per_family']:.1f}</b>",
                        top_label="Avg per Family",
                    ),
                ],
            ),
            Section(
                header="💾 Cache Stats",
                widgets=[
                    DecoratedText(
                        text=f"<b>{cache_stats['l1_size']}</b> items",
                        top_label="L1 (Memory)",
                    ),
                    DecoratedText(
                        text=f"<b>{cache_stats['hit_rate']:.1%}</b>",
                        top_label="Hit Rate",
                    ),
                ],
            ),
            Section(
                header="🏗️ Architecture",
                widgets=[
                    TextParagraph(
                        text="<b>Structural Variations:</b> Swap siblings, add/remove widgets\n"
                        "<b>Parameter Variations:</b> Text, color, list modifications\n"
                        "<b>Caching:</b> All variations pre-cached for instant retrieval"
                    ),
                ],
            ),
        ],
        _CardWithId__card_id="variation-summary",
    )

    message = Message(cards_v2=[card])
    rendered = message.render()
    return convert_keys_to_camel(rendered)


if __name__ == "__main__":
    print("=" * 60)
    print("VARIATION GENERATION WEBHOOK DEMO")
    print("=" * 60)
    print(f"Webhook: {WEBHOOK_URL[:50]}...")

    results = []

    # 1. Generate variations
    family = demo_variation_generation()

    # 2. FeedbackLoop integration
    demo_feedbackloop_variations()

    # 3. Send showcase card
    payload1 = build_variation_showcase_card(family)
    result = send_card(payload1, "Variation Family Overview")
    results.append(("Family Overview", result))
    time.sleep(1)

    # 4. Send sample variation cards
    sample_cards = build_sample_variation_cards(family, max_cards=2)
    for i, payload in enumerate(sample_cards):
        result = send_card(payload, f"Sample Variation {i + 1}")
        results.append((f"Sample Variation {i + 1}", result))
        time.sleep(1)

    # 5. Send summary card
    from adapters.module_wrapper.variation_generator import get_variation_generator

    generator = get_variation_generator()
    payload3 = demo_summary_card(family, generator.stats)
    result = send_card(payload3, "Variation System Summary")
    results.append(("Summary Card", result))

    # Final summary
    print("\n" + "=" * 60)
    print("DEMO SUMMARY")
    print("=" * 60)

    for name, success in results:
        status = "✅" if success else "❌"
        print(f"  {status} {name}")

    print(f"\nTotal: {sum(1 for _, r in results if r)}/{len(results)} cards sent")
