#!/usr/bin/env python3
"""
Ad-hoc test of different Qdrant vectors for card DSL parsing.

Tests:
1. 'components' vector - component identity search
2. 'inputs' vector - content/parameter search
3. 'relationships' vector - structure/DSL search

Goal: Understand what each vector returns and how to simplify DSL parsing
by relying more on Qdrant results.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.qdrant_client import get_qdrant_client


def main():
    print("=" * 70)
    print("AD-HOC QDRANT VECTOR SEARCH TESTS")
    print("=" * 70)

    client = get_qdrant_client()
    collection = "mcp_gchat_cards_v7"

    # Check collection info
    info = client.get_collection(collection)
    print(f"\nCollection: {collection}")
    print(f"Points: {info.points_count}")
    print(f"Vectors: {list(info.config.params.vectors.keys())}")

    # Test queries
    test_queries = [
        # DSL symbol queries
        "§ Section with decorated text",
        "δ DecoratedText with icon",
        "Ƀ ButtonList containing buttons",
        "ᵬ Button with URL",
        # Natural language
        "card with title subtitle and buttons",
        "section header with icon and text",
        # DSL patterns
        "§[δ, Ƀ[ᵬ×2]]",
        "Ƀ[ᵬ×2]",
    ]

    print("\n" + "=" * 70)
    print("1. COMPONENTS VECTOR SEARCH (ColBERT - component identity)")
    print("=" * 70)

    try:
        from fastembed import LateInteractionTextEmbedding

        colbert = LateInteractionTextEmbedding(model_name="colbert-ir/colbertv2.0")

        for query in test_queries[:4]:
            print(f"\n🔍 Query: '{query}'")
            vectors = list(colbert.query_embed(query))[0]
            vectors_list = [v.tolist() for v in vectors]

            from qdrant_client import models

            results = client.query_points(
                collection_name=collection,
                query=vectors_list,
                using="components",
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="type", match=models.MatchValue(value="class")
                        )
                    ]
                ),
                limit=3,
                with_payload=True,
            )

            for p in results.points:
                print(
                    f"   • {p.payload.get('name', '?')} (score: {p.score:.3f}) - {p.payload.get('type')}"
                )
                if p.payload.get("relationship_text"):
                    print(f"     rel: {p.payload.get('relationship_text')[:60]}...")
    except Exception as e:
        print(f"   ❌ ColBERT search failed: {e}")

    print("\n" + "=" * 70)
    print("2. INPUTS VECTOR SEARCH (ColBERT - content/parameters)")
    print("=" * 70)

    try:
        for query in test_queries[:4]:
            print(f"\n🔍 Query: '{query}'")
            vectors = list(colbert.query_embed(query))[0]
            vectors_list = [v.tolist() for v in vectors]

            results = client.query_points(
                collection_name=collection,
                query=vectors_list,
                using="inputs",
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="type",
                            match=models.MatchValue(value="instance_pattern"),
                        )
                    ]
                ),
                limit=3,
                with_payload=True,
            )

            for p in results.points:
                name = p.payload.get("name", "?")
                feedback = p.payload.get("content_feedback", p.payload.get("feedback"))
                struct = p.payload.get("structure_description", "")[:50]
                print(f"   • {name} (score: {p.score:.3f}) feedback={feedback}")
                if struct:
                    print(f"     struct: {struct}...")
    except Exception as e:
        print(f"   ❌ Inputs search failed: {e}")

    print("\n" + "=" * 70)
    print("3. RELATIONSHIPS VECTOR SEARCH (MiniLM - structure)")
    print("=" * 70)

    try:
        from fastembed import TextEmbedding

        minilm = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")

        for query in test_queries:
            print(f"\n🔍 Query: '{query}'")
            vector = list(minilm.embed([query]))[0].tolist()

            results = client.query_points(
                collection_name=collection,
                query=vector,
                using="relationships",
                limit=3,
                with_payload=True,
            )

            for p in results.points:
                name = p.payload.get("name", "?")
                ptype = p.payload.get("type", "?")
                rel_text = p.payload.get("relationship_text", "")[:60]
                print(f"   • {name} (score: {p.score:.3f}) type={ptype}")
                if rel_text:
                    print(f"     rel_text: {rel_text}...")
    except Exception as e:
        print(f"   ❌ Relationships search failed: {e}")

    print("\n" + "=" * 70)
    print("4. INSTANCE PATTERNS WITH POSITIVE FEEDBACK")
    print("=" * 70)

    try:
        # Just scroll and show some positive feedback patterns
        results, _ = client.scroll(
            collection_name=collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="type", match=models.MatchValue(value="instance_pattern")
                    ),
                    models.FieldCondition(
                        key="content_feedback", match=models.MatchValue(value="positive")
                    ),
                ]
            ),
            limit=5,
            with_payload=True,
        )

        print(f"\n Found {len(results)} positive content patterns:")
        for p in results:
            name = p.payload.get("name", "?")
            struct = p.payload.get("structure_description", "")[:80]
            comp_paths = p.payload.get("component_paths", [])
            print(f"\n   • {name}")
            print(f"     structure: {struct}")
            print(f"     paths: {comp_paths[:5]}")
    except Exception as e:
        print(f"   ❌ Pattern scroll failed: {e}")

    print("\n" + "=" * 70)
    print("5. DSL-ANNOTATED PATTERNS (checking for symbol-enriched data)")
    print("=" * 70)

    try:
        # Search for patterns that have DSL symbols in relationship_text
        results, _ = client.scroll(
            collection_name=collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="relationship_text",
                        match=models.MatchText(text="§"),  # Section symbol
                    )
                ]
            ),
            limit=5,
            with_payload=True,
        )

        print(f"\n Found {len(results)} patterns with § symbol:")
        for p in results:
            name = p.payload.get("name", "?")
            rel_text = p.payload.get("relationship_text", "")[:100]
            print(f"\n   • {name}")
            print(f"     rel_text: {rel_text}")

        # Search for δ (DecoratedText)
        results, _ = client.scroll(
            collection_name=collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="relationship_text",
                        match=models.MatchText(text="δ"),
                    )
                ]
            ),
            limit=3,
            with_payload=True,
        )
        print(f"\n Found {len(results)} patterns with δ symbol:")
        for p in results:
            print(f"   • {p.payload.get('name', '?')}: {p.payload.get('relationship_text', '')[:80]}")

    except Exception as e:
        print(f"   ❌ DSL pattern search failed: {e}")

    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
