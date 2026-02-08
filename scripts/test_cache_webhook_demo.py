#!/usr/bin/env python3
"""
Demonstrate Component Cache with real Google Chat webhook.

Shows:
1. Fast component retrieval via cache
2. Building cards with cached classes
3. Cache hit rates and performance
4. Sending results to webhook
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


def demo_cache_performance():
    """Demonstrate cache performance with timing."""
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    print("\n" + "=" * 60)
    print("COMPONENT CACHE PERFORMANCE DEMO")
    print("=" * 60)

    wrapper = get_card_framework_wrapper()

    # Time first access (cache miss - needs resolution)
    print("\n1️⃣  First access (cold cache)...")
    components_to_test = [
        "Section",
        "DecoratedText",
        "ButtonList",
        "Button",
        "TextParagraph",
    ]

    cold_times = []
    for name in components_to_test:
        start = time.perf_counter()
        cls = wrapper.get_cached_class(name)
        elapsed = (time.perf_counter() - start) * 1000
        cold_times.append(elapsed)
        print(f"   {name}: {elapsed:.2f}ms {'✓' if cls else '✗'}")

    # Time second access (cache hit)
    print("\n2️⃣  Second access (warm cache)...")
    warm_times = []
    for name in components_to_test:
        start = time.perf_counter()
        cls = wrapper.get_cached_class(name)
        elapsed = (time.perf_counter() - start) * 1000
        warm_times.append(elapsed)
        print(f"   {name}: {elapsed:.3f}ms {'✓' if cls else '✗'}")

    # Stats
    avg_cold = sum(cold_times) / len(cold_times)
    avg_warm = sum(warm_times) / len(warm_times)
    speedup = avg_cold / avg_warm if avg_warm > 0 else 0

    print(f"\n📊 Performance:")
    print(f"   Cold avg: {avg_cold:.2f}ms")
    print(f"   Warm avg: {avg_warm:.3f}ms")
    print(f"   Speedup: {speedup:.0f}x faster")

    stats = wrapper.cache_stats
    print(f"\n📈 Cache Stats:")
    print(f"   L1 size: {stats['l1_size']}")
    print(f"   L1 hits: {stats['l1_hits']}")
    print(f"   Hit rate: {stats['hit_rate']:.1%}")

    return {
        "cold_avg_ms": avg_cold,
        "warm_avg_ms": avg_warm,
        "speedup": speedup,
        "hit_rate": stats["hit_rate"],
    }


def demo_build_card_from_cache():
    """Build a card using only cached components."""
    from card_framework.v2.card import CardHeader, CardWithId
    from card_framework.v2.message import Message
    from card_framework.v2.widgets.on_click import OnClick, OpenLink

    from gchat.card_framework_wrapper import get_card_framework_wrapper

    print("\n" + "=" * 60)
    print("BUILD CARD FROM CACHED COMPONENTS")
    print("=" * 60)

    wrapper = get_card_framework_wrapper()

    # Cache a pattern
    print("\n1️⃣  Caching component pattern...")
    entry = wrapper.cache_pattern(
        key="demo_status_card",
        component_paths=["Section", "DecoratedText", "ButtonList", "Button"],
        instance_params={
            "title": "Cache Demo",
            "status": "Online",
        },
    )

    print(f"   Cached: {entry.key}")
    print(f"   Classes: {list(entry.component_classes.keys())}")

    # Build card using cached classes
    print("\n2️⃣  Building card from cached classes...")

    # Get core widget classes from cache (the main benefit)
    Section = entry.component_classes.get("Section")
    DecoratedText = entry.component_classes.get("DecoratedText")
    ButtonList = entry.component_classes.get("ButtonList")
    Button = entry.component_classes.get("Button")

    # Build widgets
    status_widget = DecoratedText(
        text='<font color="#00C853">● Online</font>',
        top_label="System Status",
        wrap_text=True,
    )

    cache_stats_widget = DecoratedText(
        text=f"<b>L1 Cache:</b> {wrapper.cache_stats['l1_size']} items",
        top_label="Cache Info",
    )

    hit_rate_widget = DecoratedText(
        text=f"<b>Hit Rate:</b> {wrapper.cache_stats['hit_rate']:.1%}",
        top_label="Performance",
    )

    # Buttons
    buttons = ButtonList(
        buttons=[
            Button(
                text="View Docs",
                on_click=OnClick(open_link=OpenLink(url="https://github.com")),
            ),
            Button(
                text="Refresh",
                on_click=OnClick(open_link=OpenLink(url="https://google.com")),
            ),
        ]
    )

    # Build card
    card = CardWithId(
        header=CardHeader(
            title="🚀 Component Cache Demo",
            subtitle="Built with cached components",
        ),
        sections=[
            Section(header="Status", widgets=[status_widget]),
            Section(
                header="Cache Metrics", widgets=[cache_stats_widget, hit_rate_widget]
            ),
            Section(widgets=[buttons]),
        ],
        _CardWithId__card_id="cache-demo-card",
    )

    message = Message(cards_v2=[card])

    # Render and convert to camelCase
    rendered = message.render()
    payload = convert_keys_to_camel(rendered)

    print(
        f"   Built card with {len(payload['cardsV2'][0]['card']['sections'])} sections"
    )

    return payload


def demo_pattern_caching():
    """Demonstrate pattern caching via FeedbackLoop."""
    from card_framework.v2.card import CardHeader
    from card_framework.v2.widgets.text_paragraph import TextParagraph

    from gchat.card_framework_wrapper import get_card_framework_wrapper
    from gchat.feedback_loop import get_feedback_loop

    print("\n" + "=" * 60)
    print("PATTERN CACHING VIA FEEDBACKLOOP")
    print("=" * 60)

    fl = get_feedback_loop()
    wrapper = get_card_framework_wrapper()

    # Get cached classes for building (core widgets)
    Section = wrapper.get_cached_class("Section")
    DecoratedText = wrapper.get_cached_class("DecoratedText")

    from card_framework.v2.card import CardWithId
    from card_framework.v2.message import Message

    # Cache a pattern through feedback loop
    print("\n1️⃣  Caching pattern via FeedbackLoop...")
    test_pattern = {
        "card_id": "fl_demo_pattern",
        "component_paths": ["Section", "TextParagraph", "DecoratedText"],
        "instance_params": {
            "text": "This pattern was cached!",
            "top_label": "Demo",
        },
        "card_description": "A demo pattern showing feedback loop caching",
        "dsl_notation": "§[τ, δ]",
    }

    cache_key = fl._cache_pattern(test_pattern)
    print(f"   Cached with key: {cache_key}")

    # Retrieve and verify
    print("\n2️⃣  Retrieving cached pattern...")
    cached = fl.get_cached_pattern("fl_demo_pattern")

    if cached:
        print(f"   Retrieved: {cached['key']}")
        print(f"   From cache: {cached.get('_from_cache', False)}")
        print(f"   Components: {cached['component_paths']}")
        print(
            f"   Classes available: {list(cached.get('component_classes', {}).keys())}"
        )

        # Build a card showing the cached info
        card = CardWithId(
            header=CardHeader(
                title="📦 Pattern Cache Demo",
                subtitle="Cached via FeedbackLoop",
            ),
            sections=[
                Section(
                    widgets=[
                        TextParagraph(text=f"<b>Key:</b> {cached['key']}"),
                        TextParagraph(
                            text=f"<b>DSL:</b> <code>{cached.get('dsl_notation', 'N/A')}</code>"
                        ),
                        TextParagraph(
                            text=f"<b>Components:</b> {', '.join(cached['component_paths'])}"
                        ),
                    ]
                ),
                Section(
                    header="Cache Status",
                    widgets=[
                        DecoratedText(
                            text='<font color="#00C853">✓ Retrieved from cache</font>',
                            top_label="Status",
                        ),
                    ],
                ),
            ],
            _CardWithId__card_id="pattern-cache-demo",
        )

        message = Message(cards_v2=[card])
        rendered = message.render()
        return convert_keys_to_camel(rendered)

    return None


def demo_summary_card(perf_stats: dict):
    """Build a summary card with all demo results."""
    from card_framework.v2.card import CardHeader, CardWithId
    from card_framework.v2.message import Message
    from card_framework.v2.widgets.on_click import OnClick, OpenLink
    from card_framework.v2.widgets.text_paragraph import TextParagraph

    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    # Get core widget classes from cache (demonstrating the benefit)
    Section = wrapper.get_cached_class("Section")
    DecoratedText = wrapper.get_cached_class("DecoratedText")
    ButtonList = wrapper.get_cached_class("ButtonList")
    Button = wrapper.get_cached_class("Button")

    stats = wrapper.cache_stats

    card = CardWithId(
        header=CardHeader(
            title="🎯 Component Cache Summary",
            subtitle="Tiered caching: L1 (memory) → L2 (pickle) → L3 (resolve)",
        ),
        sections=[
            Section(
                header="⚡ Performance",
                widgets=[
                    DecoratedText(
                        text=f"<b>{perf_stats['speedup']:.0f}x</b> faster",
                        top_label="Cache Speedup",
                    ),
                    DecoratedText(
                        text=f"Cold: {perf_stats['cold_avg_ms']:.2f}ms → Warm: {perf_stats['warm_avg_ms']:.3f}ms",
                        top_label="Avg Retrieval Time",
                    ),
                ],
            ),
            Section(
                header="📊 Cache Stats",
                widgets=[
                    DecoratedText(
                        text=f"<b>{stats['l1_size']}</b> components",
                        top_label="L1 (Memory) Size",
                    ),
                    DecoratedText(
                        text=f"<b>{stats['l2_size']}</b> entries",
                        top_label="L2 (Pickle) Size",
                    ),
                    DecoratedText(
                        text=f"<b>{stats['hit_rate']:.1%}</b>",
                        top_label="Hit Rate",
                    ),
                ],
            ),
            Section(
                header="🏗️ Architecture",
                widgets=[
                    TextParagraph(
                        text="<b>L1:</b> LRU memory cache (instant)\n"
                        "<b>L2:</b> Pickle spillover (persistent)\n"
                        "<b>L3:</b> Path resolution (fallback)"
                    ),
                ],
            ),
            Section(
                widgets=[
                    ButtonList(
                        buttons=[
                            Button(
                                text="View Source",
                                on_click=OnClick(
                                    open_link=OpenLink(url="https://github.com")
                                ),
                            ),
                        ]
                    ),
                ]
            ),
        ],
        _CardWithId__card_id="cache-summary",
    )

    message = Message(cards_v2=[card])
    rendered = message.render()
    return convert_keys_to_camel(rendered)


if __name__ == "__main__":
    print("=" * 60)
    print("COMPONENT CACHE WEBHOOK DEMO")
    print("=" * 60)
    print(f"Webhook: {WEBHOOK_URL[:50]}...")

    results = []

    # 1. Performance demo (internal, no webhook)
    perf_stats = demo_cache_performance()

    # 2. Build and send card from cache
    payload1 = demo_build_card_from_cache()
    if payload1:
        result = send_card(payload1, "Card built from cached components")
        results.append(("Cache Build Demo", result))
        time.sleep(1)

    # 3. Pattern caching demo
    payload2 = demo_pattern_caching()
    if payload2:
        result = send_card(payload2, "Pattern cached via FeedbackLoop")
        results.append(("Pattern Cache Demo", result))
        time.sleep(1)

    # 4. Summary card
    payload3 = demo_summary_card(perf_stats)
    if payload3:
        result = send_card(payload3, "Cache system summary")
        results.append(("Summary Card", result))

    # Final summary
    print("\n" + "=" * 60)
    print("DEMO SUMMARY")
    print("=" * 60)

    for name, success in results:
        status = "✅" if success else "❌"
        print(f"  {status} {name}")

    print(f"\nTotal: {sum(1 for _, r in results if r)}/{len(results)} cards sent")
