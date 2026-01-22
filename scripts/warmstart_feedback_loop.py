#!/usr/bin/env python3
"""
Warm-Start Feedback Loop with Known-Good Card Patterns

This script pre-populates the feedback loop with working instance patterns
extracted from the test suite. These patterns serve as "warm start" data
to help the system immediately benefit from proven card structures.

Usage:
    uv run python scripts/warmstart_feedback_loop.py [--dry-run]
"""

import os
import sys

from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()


# Known-good patterns extracted from test suite
WARM_START_PATTERNS = [
    # Pattern 1: Simple DecoratedText card
    # From: test_smart_card_builder_comprehensive.py::test_decorated_text_json_format
    {
        "card_description": 'First section titled "Details" showing "Test content" with label "Label"',
        "component_paths": [
            "card_framework.v2.widgets.decorated_text.DecoratedText",
        ],
        "instance_params": {
            "text": "Test content",
            "top_label": "Label",
            "wrap_text": True,
        },
        "feedback": "positive",
        "source": "test_smart_card_builder_comprehensive::test_decorated_text_json_format",
    },
    # Pattern 2: Card with action buttons
    # From: test_smart_card_builder_comprehensive.py::test_button_list_json_format
    {
        "card_description": 'Card with action buttons showing "Click a button below" with two buttons "Button 1" and "Button 2"',
        "component_paths": [
            "card_framework.v2.widgets.decorated_text.DecoratedText",
            "card_framework.v2.widgets.button_list.ButtonList",
        ],
        "instance_params": {
            "title": "Action Card",
            "section_header": "Actions",
            "items": [{"text": "Click a button below", "top_label": "Info"}],
            "buttons": [
                {"text": "Button 1", "url": "https://example.com/1"},
                {"text": "Button 2", "url": "https://example.com/2"},
            ],
        },
        "feedback": "positive",
        "source": "test_smart_card_builder_comprehensive::test_button_list_json_format",
    },
    # Pattern 3: Grid of images - photo gallery style
    # Used for displaying multiple images in a grid layout
    {
        "card_description": "A grid of images showing a photo gallery with multiple pictures",
        "component_paths": [
            "card_framework.v2.widgets.grid.Grid",
            "card_framework.v2.widgets.grid.GridItem",
            "card_framework.v2.widgets.grid.ImageComponent",
        ],
        "instance_params": {
            "layout_type": "grid",
            "column_count": 2,
            "grid_images": True,  # Signal to use build_grid_from_images
        },
        "feedback": "positive",
        "source": "warmstart::grid_image_gallery",
    },
    # Pattern 4: Image grid with titles
    {
        "card_description": "Display images in a 2 column grid with titles under each image",
        "component_paths": [
            "card_framework.v2.widgets.grid.Grid",
            "card_framework.v2.widgets.grid.GridItem",
            "card_framework.v2.widgets.grid.ImageComponent",
        ],
        "instance_params": {
            "layout_type": "grid",
            "column_count": 2,
            "grid_images": True,
        },
        "feedback": "positive",
        "source": "warmstart::grid_with_titles",
    },
    # Pattern 5: Thumbnail gallery
    {
        "card_description": "Show thumbnails in a gallery format",
        "component_paths": [
            "card_framework.v2.widgets.grid.Grid",
            "card_framework.v2.widgets.grid.GridItem",
        ],
        "instance_params": {
            "layout_type": "grid",
            "column_count": 3,
            "grid_images": True,
        },
        "feedback": "positive",
        "source": "warmstart::thumbnail_gallery",
    },
]


def verify_pattern_renders(pattern: dict) -> bool:
    """Verify that a pattern actually renders correctly."""
    from gchat.smart_card_builder import SmartCardBuilder

    builder = SmartCardBuilder()
    builder.initialize()

    description = pattern["card_description"]
    print(f"   Testing: {description[:50]}...")

    try:
        # Try to build the card from description
        card = builder.build_card_from_description(
            description=description,
            title="Warm Start Test",
        )

        # Check we got valid output
        if not card:
            print(f"   ❌ No card returned")
            return False

        # Check it has sections
        sections = card.get("sections", [])
        if not sections:
            print(f"   ❌ Card has no sections")
            return False

        # Check for widgets in first section
        widgets = sections[0].get("widgets", [])
        if not widgets:
            print(f"   ❌ First section has no widgets")
            return False

        print(
            f"   ✅ Card rendered: {len(sections)} section(s), {len(widgets)} widget(s)"
        )
        return True

    except Exception as e:
        print(f"   ❌ Render failed: {e}")
        return False


def store_pattern(pattern: dict, dry_run: bool = False) -> bool:
    """Store a pattern in the feedback loop."""
    from gchat.feedback_loop import get_feedback_loop

    feedback_loop = get_feedback_loop()

    print(f"\n   Storing pattern: {pattern['card_description'][:50]}...")
    print(f"   Components: {len(pattern['component_paths'])}")
    print(f"   Feedback: {pattern['feedback']}")
    print(f"   Source: {pattern['source']}")

    if dry_run:
        print(f"   [DRY RUN] Would store pattern")
        return True

    point_id = feedback_loop.store_instance_pattern(
        card_description=pattern["card_description"],
        component_paths=pattern["component_paths"],
        instance_params=pattern["instance_params"],
        feedback=pattern["feedback"],
        user_email="warmstart@system.local",
        card_id=f"warmstart-{pattern['source'].split('::')[1] if '::' in pattern['source'] else 'unknown'}",
    )

    if point_id:
        print(f"   ✅ Stored with ID: {point_id[:8]}...")
        return True
    else:
        print(f"   ❌ Failed to store pattern")
        return False


def verify_retrieval():
    """Verify that stored patterns can be retrieved."""
    from gchat.feedback_loop import get_feedback_loop

    feedback_loop = get_feedback_loop()

    print("\n🔍 Verifying pattern retrieval...")

    # Try to find patterns for similar descriptions
    test_queries = [
        "Show some text with a label",
        "Card with two action buttons",
    ]

    for query in test_queries:
        print(f"\n   Query: '{query}'")

        proven = feedback_loop.get_proven_params_for_description(
            description=query,
            min_score=0.3,  # Lower threshold for warm start
        )

        if proven:
            print(f"   ✅ Found proven params: {list(proven.keys())}")
        else:
            print(f"   ⚠️ No proven params found (score may be too low)")


def main():
    """Run warm-start population."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Warm-start feedback loop with known-good patterns"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify retrieval, don't store new patterns",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Warm-Start Feedback Loop with Known-Good Patterns")
    print("=" * 60)

    if args.dry_run:
        print("\n🔶 DRY RUN MODE - No changes will be made")

    if args.verify_only:
        verify_retrieval()
        return 0

    # Step 1: Verify patterns render correctly
    print("\n📋 Step 1: Verifying patterns render correctly...")
    patterns_to_store = []

    for pattern in WARM_START_PATTERNS:
        if verify_pattern_renders(pattern):
            patterns_to_store.append(pattern)
        else:
            print(f"   ⚠️ Skipping pattern that failed to render")

    if not patterns_to_store:
        print("\n❌ No patterns passed verification!")
        return 1

    print(f"\n   {len(patterns_to_store)}/{len(WARM_START_PATTERNS)} patterns verified")

    # Step 2: Store verified patterns
    print("\n📦 Step 2: Storing patterns in feedback loop...")

    stored = 0
    for pattern in patterns_to_store:
        if store_pattern(pattern, args.dry_run):
            stored += 1

    print(f"\n   Stored {stored}/{len(patterns_to_store)} patterns")

    # Step 3: Verify retrieval works
    if not args.dry_run:
        verify_retrieval()

    # Summary
    print("\n" + "=" * 60)
    print("✅ Warm-start complete!")
    print("=" * 60)
    print(f"\n   Patterns stored: {stored}")
    print(f"   These patterns will now boost similar queries in the feedback loop")

    return 0


if __name__ == "__main__":
    sys.exit(main())
