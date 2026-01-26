#!/usr/bin/env python3
"""
Test DSL notation searches against v7 Qdrant collection.

Verifies that symbol-enriched relationship_text enables semantic matching
of DSL patterns like Ƀ[ᵬ×2] to ButtonList with 2 Buttons.

FINDINGS:
---------
1. Text search on relationship_text works for:
   - Symbol + name queries: "§ Section", "ᵬ Button"
   - DSL patterns: "Ƀ[ᵬ]", "ℊ[ǵ"

2. Semantic search on relationships vector (MiniLM) works for:
   - Natural language: "ButtonList contains Button" (0.909 score)
   - Symbol + NL: "ᵬ Button" (0.634 score)
   - DO NOT query with symbols alone - they will be ignored

3. DSL-annotated card_params (e.g., "δ:status": "All systems operational"):
   - Use StructureValidator.reverse_symbols for symbol → component mapping
   - Query the `inputs` vector (ColBERT) with the VALUES, not symbols
   - DSL keys are for SLOT MAPPING only, not querying

4. NEVER hardcode DSL symbol mappings - use StructureValidator
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gchat.card_framework_wrapper import get_card_framework_wrapper


def test_dsl_searches():
    """Test various DSL notation searches."""
    print("=" * 60)
    print("DSL NOTATION SEARCH TESTS")
    print("=" * 60)

    # Get wrapper with v7 collection
    wrapper = get_card_framework_wrapper()
    collection = wrapper.collection_name
    print(f"\nUsing collection: {collection}")

    # DSL test queries
    dsl_queries = [
        # Symbol-only queries
        ("ᵬ", "Button symbol"),
        ("Ƀ", "ButtonList symbol"),
        ("§", "Section symbol"),
        ("δ", "DecoratedText symbol"),
        ("ℊ", "Grid symbol"),
        # DSL structure patterns
        ("Ƀ[ᵬ]", "ButtonList containing Button"),
        ("Ƀ[ᵬ×2]", "ButtonList with 2 Buttons"),
        ("§[δ]", "Section with DecoratedText"),
        ("§[δ, Ƀ[ᵬ]]", "Section with DecoratedText and ButtonList"),
        # Mixed queries (DSL + natural language)
        ("ᵬ Button", "Button with symbol"),
        ("Ƀ ButtonList contains Button", "ButtonList description"),
        ("ℊ Grid items", "Grid with items"),
    ]

    print("\n" + "-" * 60)
    print("Testing search_by_relationship (MiniLM on 'relationships' vector)")
    print("-" * 60)

    for query, description in dsl_queries:
        print(f"\n🔍 Query: '{query}' ({description})")
        results = wrapper.search_by_relationship(query, limit=3)

        if results:
            for i, r in enumerate(results, 1):
                name = r.get("name", "?")
                score = r.get("score", 0)
                rel_text = r.get("relationship_text", "")[:80]
                child_classes = r.get("child_classes", [])
                print(f"   {i}. {name} (score: {score:.3f})")
                if rel_text:
                    print(f"      relationship_text: {rel_text}...")
                if child_classes:
                    print(f"      children: {child_classes[:5]}")
        else:
            print("   ❌ No results")

    # Test a few with the regular search method for comparison
    print("\n" + "-" * 60)
    print("Comparison: Regular semantic search")
    print("-" * 60)

    comparison_queries = ["Button", "ButtonList", "Section", "Grid"]
    for query in comparison_queries:
        print(f"\n🔍 Query: '{query}'")
        results = wrapper.search(query, limit=2)
        for i, r in enumerate(results, 1):
            print(
                f"   {i}. {r.get('name', r.get('path', '?'))} (score: {r.get('score', 0):.3f})"
            )

    # Direct Qdrant query to verify relationship_text content
    print("\n" + "-" * 60)
    print("Verifying relationship_text in collection")
    print("-" * 60)

    if wrapper.client:
        # Get a few points and show their relationship_text
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        # Get Button specifically
        try:
            results = wrapper.client.scroll(
                collection_name=collection,
                scroll_filter=Filter(
                    must=[FieldCondition(key="name", match=MatchValue(value="Button"))]
                ),
                limit=1,
                with_payload=True,
            )
            points, _ = results
            if points:
                p = points[0]
                payload = p.payload
                print(f"\n✓ Button point found (id: {p.id})")
                print(f"  name: {payload.get('name')}")
                print(
                    f"  relationship_text: {payload.get('relationship_text', 'EMPTY')}"
                )
                relationships = payload.get("relationships", {})
                print(
                    f"  relationships.compact_text: {relationships.get('compact_text', 'EMPTY')}"
                )
                print(
                    f"  relationships.symbol_enriched: {relationships.get('symbol_enriched')}"
                )
                print(
                    f"  relationships.child_classes: {relationships.get('child_classes', [])}"
                )
        except Exception as e:
            print(f"❌ Error querying Button: {e}")

        # Get ButtonList specifically
        try:
            results = wrapper.client.scroll(
                collection_name=collection,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(key="name", match=MatchValue(value="ButtonList"))
                    ]
                ),
                limit=1,
                with_payload=True,
            )
            points, _ = results
            if points:
                p = points[0]
                payload = p.payload
                print(f"\n✓ ButtonList point found (id: {p.id})")
                print(f"  name: {payload.get('name')}")
                print(
                    f"  relationship_text: {payload.get('relationship_text', 'EMPTY')}"
                )
                relationships = payload.get("relationships", {})
                print(
                    f"  relationships.compact_text: {relationships.get('compact_text', 'EMPTY')}"
                )
                print(
                    f"  relationships.symbol_enriched: {relationships.get('symbol_enriched')}"
                )
                print(
                    f"  relationships.child_classes: {relationships.get('child_classes', [])}"
                )
        except Exception as e:
            print(f"❌ Error querying ButtonList: {e}")

    # Test DSL card_params parsing
    print("\n" + "-" * 60)
    print("Testing DSL card_params parsing")
    print("-" * 60)

    from gchat.smart_card_builder import get_smart_card_builder

    builder = get_smart_card_builder()

    card_params = {
        "δ:status": "All systems operational",
        "δ:metric": "99.9% uptime",
        "ᵬ:1": "Refresh",
        "ᵬ:2": "Details | https://example.com",
        "title": "Dashboard",
        "subtitle": "System Status",
    }

    regular, dsl_slots = builder._parse_dsl_card_params(card_params)

    print(f"\n✓ Regular params: {list(regular.keys())}")
    print(f"✓ DSL slots parsed: {len(dsl_slots)}")
    for key, info in dsl_slots.items():
        print(f"  {key} → {info['component']}[{info['slot_name']}]")

    # Search by content values
    patterns = builder._search_patterns_by_content_values(dsl_slots, limit=3)
    print(f"\n✓ Found {len(patterns)} matching patterns via inputs vector:")
    for p in patterns[:2]:
        print(f"  - {p.get('name')}: score={p.get('score', 0):.2f}")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    test_dsl_searches()
