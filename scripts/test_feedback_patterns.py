#!/usr/bin/env python3
"""
Test script to demonstrate the MODULAR feedback component assembly.

Run: python scripts/test_feedback_patterns.py
"""

import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gchat.smart_card_builder import (
    CLICKABLE_COMPONENTS,
    DUAL_COMPONENTS,
    LAYOUT_WRAPPERS,
    TEXT_COMPONENTS,
    SmartCardBuilderV2,
)


def main():
    """Generate cards with modular feedback assembly to see variety."""
    builder = SmartCardBuilderV2()

    print("=" * 70)
    print("MODULAR FEEDBACK COMPONENT ASSEMBLY")
    print("=" * 70)

    print(f"\nText components ({len(TEXT_COMPONENTS)}):")
    for c in TEXT_COMPONENTS:
        print(f"  • {c}")

    print(f"\nClickable components ({len(CLICKABLE_COMPONENTS)}):")
    for c in CLICKABLE_COMPONENTS:
        print(f"  • {c}")

    print(f"\nDual components ({len(DUAL_COMPONENTS)}):")
    for c in DUAL_COMPONENTS:
        print(f"  • {c}")

    print(f"\nLayout wrappers ({len(LAYOUT_WRAPPERS)}):")
    for c in LAYOUT_WRAPPERS:
        print(f"  • {c}")

    # Calculate theoretical combinations
    # For each feedback type: text_options × click_options + dual_options
    text_click_combos = len(TEXT_COMPONENTS) * len(CLICKABLE_COMPONENTS)
    dual_combos = len(DUAL_COMPONENTS)
    per_feedback = text_click_combos + dual_combos

    # Two feedbacks × layouts × orders
    total = per_feedback * per_feedback * len(LAYOUT_WRAPPERS) * 2
    print(f"\n📊 Theoretical combinations: {total:,}")
    print(
        f"   ({per_feedback} content × {per_feedback} form × {len(LAYOUT_WRAPPERS)} layouts × 2 orders)"
    )

    # Generate cards to show random selection
    print("\n" + "-" * 70)
    print("Generating 15 sample cards to show assembly variety...\n")

    content_text_seen = Counter()
    content_click_seen = Counter()
    form_text_seen = Counter()
    form_click_seen = Counter()
    layout_seen = Counter()
    orders_seen = Counter()

    for i in range(15):
        card = builder.build(
            description=f"Test card #{i + 1} with some content",
            title=f"Sample Card #{i + 1}",
        )

        sections = card.get("sections", [])
        if len(sections) >= 2:
            last_section = sections[-1]
            assembly = last_section.get("_feedback_assembly", {})

            if assembly:
                content_text_seen[assembly.get("content_text", "?")] += 1
                content_click_seen[assembly.get("content_click", "?")] += 1
                form_text_seen[assembly.get("form_text", "?")] += 1
                form_click_seen[assembly.get("form_click", "?")] += 1
                layout_seen[assembly.get("layout", "?")] += 1
                orders_seen["C→F" if assembly.get("content_first") else "F→C"] += 1

                # Count widgets
                widgets = last_section.get("widgets", [])
                widget_types = []
                for w in widgets:
                    if "textParagraph" in w:
                        widget_types.append("txt")
                    elif "decoratedText" in w:
                        has_btn = "button" in w.get("decoratedText", {})
                        widget_types.append("dec+btn" if has_btn else "dec")
                    elif "buttonList" in w:
                        btn_count = len(w["buttonList"].get("buttons", []))
                        widget_types.append(f"btn({btn_count})")
                    elif "chipList" in w:
                        chip_count = len(w["chipList"].get("chips", []))
                        widget_types.append(f"chip({chip_count})")
                    elif "grid" in w:
                        widget_types.append("grid")
                    elif "divider" in w:
                        widget_types.append("---")
                    elif "columns" in w:
                        widget_types.append("cols")

                order_str = "C→F" if assembly.get("content_first") else "F→C"
                layout = assembly.get("layout", "?")[:6]
                print(
                    f"Card {i + 1:2d}: [{order_str}] {layout:8s} → {' → '.join(widget_types)}"
                )

    print()
    print("-" * 70)
    print("COMPONENT USAGE SUMMARY:")
    print("-" * 70)

    print(f"\nContent text types ({len(content_text_seen)}):")
    for k, v in content_text_seen.most_common():
        print(f"  {k}: {v}x")

    print(f"\nContent click types ({len(content_click_seen)}):")
    for k, v in content_click_seen.most_common():
        print(f"  {k}: {v}x")

    print(f"\nForm text types ({len(form_text_seen)}):")
    for k, v in form_text_seen.most_common():
        print(f"  {k}: {v}x")

    print(f"\nForm click types ({len(form_click_seen)}):")
    for k, v in form_click_seen.most_common():
        print(f"  {k}: {v}x")

    print(f"\nLayouts ({len(layout_seen)}):")
    for k, v in layout_seen.most_common():
        print(f"  {k}: {v}x")

    print(f"\nOrder distribution:")
    for k, v in orders_seen.most_common():
        print(f"  {k}: {v}x")

    # Unique combinations seen
    unique = (
        len(content_text_seen)
        * len(content_click_seen)
        * len(form_text_seen)
        * len(form_click_seen)
        * len(layout_seen)
        * len(orders_seen)
    )
    print(f"\n📊 Unique combinations observed: ~{unique}")
    print(f"   (from {total:,} possible)")

    # Show one full feedback section
    if sections and len(sections) >= 2:
        print("\n" + "=" * 70)
        print("SAMPLE FEEDBACK SECTION (last generated)")
        print("=" * 70)
        feedback_section = sections[-1]
        clean_section = {"widgets": feedback_section.get("widgets", [])}
        print(json.dumps(clean_section, indent=2))


if __name__ == "__main__":
    main()
