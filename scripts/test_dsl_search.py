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

    from gchat.card_builder import get_smart_card_builder

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


def test_extract_dsl_from_text():
    """Test the new extract_dsl_from_text method."""
    print("\n" + "=" * 60)
    print("TEST: extract_dsl_from_text()")
    print("=" * 60)

    wrapper = get_card_framework_wrapper()

    test_cases = [
        # DSL at start
        "§[δ, Ƀ[ᵬ×2]] Build a status card with buttons",
        # DSL with pipe separator
        "§[δ] | DecoratedText :: Simple text card",
        # Complex nested DSL
        "§[Ȼ[Ɔ[δ], Ɔ[δ]]] Two column layout",
        # No DSL - plain text
        "Build a card with action buttons",
        # Inline symbols (not structured DSL)
        "Use δ for text and ᵬ for buttons",
    ]

    for text in test_cases:
        result = wrapper.extract_dsl_from_text(text)
        print(f"\n🔍 Input: {text[:55]}...")
        print(f"   has_dsl: {result['has_dsl']}")
        if result["has_dsl"]:
            print(f"   dsl: {result['dsl']}")
            print(f"   description: {result['description'][:40]}...")
            comp_names = [c["name"] for c in result["components"]]
            print(f"   components: {comp_names}")
        else:
            if result.get("inline_symbols"):
                print(f"   inline_symbols: {result['inline_symbols'][:3]}")


def test_search_by_dsl():
    """Test the new search_by_dsl method with ColBERT."""
    print("\n" + "=" * 60)
    print("TEST: search_by_dsl() with ColBERT vectors")
    print("=" * 60)

    wrapper = get_card_framework_wrapper()

    test_queries = [
        ("§[δ] Simple text card", "components", "class"),
        ("§[δ, Ƀ[ᵬ×2]] Card with buttons", "components", "class"),
        ("§[δ, Ƀ[ᵬ×2]] Card with buttons", "inputs", "instance_pattern"),
    ]

    for query, vector_name, type_filter in test_queries:
        print(f"\n🔍 Query: {query[:45]}...")
        print(f"   Vector: {vector_name}, Filter: {type_filter}")

        results = wrapper.search_by_dsl(
            text=query,
            limit=5,
            vector_name=vector_name,
            type_filter=type_filter,
            token_ratio=1.0,
        )

        if results:
            for r in results[:3]:
                print(f"   ✓ {r['name']:<25} score={r['score']:.3f} type={r['type']}")
        else:
            print("   ❌ No results")


def test_search_by_dsl_with_truncation():
    """Test token truncation optimization."""
    print("\n" + "=" * 60)
    print("TEST: search_by_dsl() with token truncation")
    print("=" * 60)

    import time

    wrapper = get_card_framework_wrapper()
    query = "§[δ, Ƀ[ᵬ×2]] Build a status card with action buttons"

    print(f"\nQuery: {query}")
    print("-" * 50)

    baseline_names = None
    for ratio in [1.0, 0.5, 0.25]:
        start = time.perf_counter()
        results = wrapper.search_by_dsl(
            text=query,
            limit=5,
            vector_name="components",
            type_filter="class",
            token_ratio=ratio,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        result_names = [r["name"] for r in results[:5]]

        if ratio == 1.0:
            baseline_names = result_names
            overlap = "baseline"
        else:
            overlap_count = len(set(result_names) & set(baseline_names or []))
            overlap = f"{overlap_count}/5 overlap"

        print(
            f"   {ratio:.0%} tokens: {elapsed_ms:6.1f}ms, {len(results)} results ({overlap})"
        )


def test_search_by_dsl_hybrid():
    """Test hybrid search returning both classes and patterns."""
    print("\n" + "=" * 60)
    print("TEST: search_by_dsl_hybrid()")
    print("=" * 60)

    wrapper = get_card_framework_wrapper()
    query = "§[δ, Ƀ[ᵬ×2]] Status indicator with action buttons"

    print(f"\nQuery: {query}")

    results = wrapper.search_by_dsl_hybrid(
        text=query,
        limit=5,
        token_ratio=0.5,
    )

    qi = results["query_info"]
    print(f"\n📋 Query Info:")
    print(f"   DSL: {qi.get('dsl')}")
    print(f"   Description: {qi.get('description')[:40]}...")

    print(f"\n📦 Class Results ({len(results['classes'])}):")
    for r in results["classes"][:3]:
        print(f"   {r['name']:<25} score={r['score']:.3f}")

    print(f"\n📄 Pattern Results ({len(results['patterns'])}):")
    for r in results["patterns"][:3]:
        desc = r.get("card_description", "")[:35]
        print(f"   {r['name']:<25} score={r['score']:.3f} - {desc}...")


def test_search_v7_hybrid_with_feedback_filters():
    """Test search_v7_hybrid with content/form feedback filters."""
    print("\n" + "=" * 60)
    print("TEST: search_v7_hybrid() with feedback filters")
    print("=" * 60)

    wrapper = get_card_framework_wrapper()

    # Test with positive content feedback filter
    print("\n🔍 Testing with content_feedback='positive'...")
    classes, patterns, rels = wrapper.search_v7_hybrid(
        description="A status card with buttons",
        limit=5,
        content_feedback="positive",
        form_feedback="positive",
    )

    print(
        f"   With filters: {len(classes)} classes, {len(patterns)} patterns, {len(rels)} relationships"
    )

    # Show pattern feedback values
    for i, p in enumerate(patterns[:3], 1):
        content_fb = p.get("content_feedback", "none")
        form_fb = p.get("form_feedback", "none")
        print(
            f"   {i}. {p.get('name', '?')[:30]} - content={content_fb}, form={form_fb}"
        )

    # Test without feedback filters for comparison
    print("\n🔍 Testing without feedback filters...")
    classes2, patterns2, rels2 = wrapper.search_v7_hybrid(
        description="A status card with buttons",
        limit=5,
    )

    print(
        f"   Without filters: {len(classes2)} classes, {len(patterns2)} patterns, {len(rels2)} relationships"
    )

    # Compare counts
    print("\n📊 Comparison:")
    print(f"   With feedback filters: {len(patterns)} patterns")
    print(f"   Without filters: {len(patterns2)} patterns")
    if len(patterns2) > len(patterns):
        print("   ✓ More results without filters (expected)")


def test_search_patterns_for_card():
    """Test the new search_patterns_for_card convenience function."""
    print("\n" + "=" * 60)
    print("TEST: search_patterns_for_card()")
    print("=" * 60)

    from gchat.card_framework_wrapper import search_patterns_for_card

    # Test with DSL
    print("\n🔍 Testing with DSL notation...")
    result = search_patterns_for_card("§[δ, Ƀ[ᵬ×2]] Build a card")
    print(f"   has_dsl: {result['has_dsl']}")
    print(f"   dsl: {result.get('dsl', 'N/A')}")
    print(f"   patterns found: {len(result.get('patterns', []))}")
    print(f"   classes found: {len(result.get('classes', []))}")

    assert result["has_dsl"] is True, "Expected has_dsl=True with DSL notation"
    assert result["dsl"] == "§[δ, Ƀ[ᵬ×2]]", f"DSL mismatch: {result['dsl']}"

    # Test without DSL
    print("\n🔍 Testing without DSL notation...")
    result2 = search_patterns_for_card("A card with decorated text")
    print(f"   has_dsl: {result2['has_dsl']}")
    print(f"   patterns found: {len(result2.get('patterns', []))}")
    print(f"   classes found: {len(result2.get('classes', []))}")

    assert result2["has_dsl"] is False, "Expected has_dsl=False without DSL notation"

    # Test with require_positive_feedback=False
    print("\n🔍 Testing with require_positive_feedback=False...")
    result3 = search_patterns_for_card(
        "A status indicator card",
        require_positive_feedback=False,
    )
    print(f"   has_dsl: {result3['has_dsl']}")
    print(f"   patterns found: {len(result3.get('patterns', []))}")

    print("\n✓ search_patterns_for_card tests passed")


def test_search_v7_include_classes_flag():
    """Test include_classes parameter."""
    print("\n" + "=" * 60)
    print("TEST: search_v7_hybrid() with include_classes flag")
    print("=" * 60)

    wrapper = get_card_framework_wrapper()

    # With classes
    print("\n🔍 Testing with include_classes=True...")
    classes, patterns, _ = wrapper.search_v7_hybrid(
        description="Button widget",
        include_classes=True,
        limit=5,
    )
    print(f"   Classes returned: {len(classes)}")
    for c in classes[:3]:
        print(f"   - {c.get('name', '?')} (type={c.get('type', '?')})")

    # Without classes
    print("\n🔍 Testing with include_classes=False...")
    classes2, patterns2, _ = wrapper.search_v7_hybrid(
        description="Button widget",
        include_classes=False,
        limit=5,
    )
    print(f"   Classes returned: {len(classes2)}")

    # Verify the flag works
    print("\n📊 Comparison:")
    print(f"   include_classes=True: {len(classes)} classes")
    print(f"   include_classes=False: {len(classes2)} classes")

    assert len(classes) > 0, "Expected classes with include_classes=True"
    assert len(classes2) == 0, (
        f"Expected 0 classes with include_classes=False, got {len(classes2)}"
    )

    print("\n✓ include_classes flag tests passed")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--new":
        # Test only the new methods
        print("Testing NEW ModuleWrapper DSL search methods")
        print("=" * 60)
        test_extract_dsl_from_text()
        test_search_by_dsl()
        test_search_by_dsl_with_truncation()
        test_search_by_dsl_hybrid()
        # New tests for feedback filters and convenience functions
        test_search_v7_hybrid_with_feedback_filters()
        test_search_patterns_for_card()
        test_search_v7_include_classes_flag()
        print("\n✅ New method tests complete!")
    else:
        # Run original tests
        test_dsl_searches()
        # Also run new tests
        test_extract_dsl_from_text()
        test_search_by_dsl()
        test_search_by_dsl_with_truncation()
        test_search_by_dsl_hybrid()
        # New tests for feedback filters and convenience functions
        test_search_v7_hybrid_with_feedback_filters()
        test_search_patterns_for_card()
        test_search_v7_include_classes_flag()
