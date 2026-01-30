#!/usr/bin/env python3
"""
Benchmark script for ColBERT token truncation optimization.

Tests the impact of truncating ColBERT query tokens on:
1. Query latency (speedup)
2. Result quality (overlap with full-token results)

KEY INSIGHT: This benchmark tests with DSL-prefixed queries because:
- Class components have symbols embedded: "ᵬ Name: Button..."
- DSL symbols at the START of queries should be preserved by truncation
- Truncating to first N% of tokens keeps these high-signal symbols

Usage:
    python scripts/test_colbert_truncation.py

The script:
1. Pulls real patterns from mcp_gchat_cards_v7 collection (with DSL in relationship_text)
2. Generates DSL-prefixed test queries using ModuleWrapper symbols
3. For each query, runs with 100%, 50%, 25%, 10% tokens
4. Reports latency and result overlap metrics
"""

import os
import sys
import time
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings


@dataclass
class BenchmarkResult:
    """Result from a single benchmark run."""

    description: str
    token_ratio: float
    full_tokens: int
    truncated_tokens: int
    query_latency_ms: float
    result_ids: list[str]
    result_scores: list[float]


@dataclass
class ComparisonMetrics:
    """Metrics comparing truncated results to full-token baseline."""

    token_ratio: float
    avg_speedup_percent: float
    avg_result_overlap_top5: float
    avg_result_overlap_top3: float
    avg_score_correlation: float
    sample_count: int


def get_module_wrapper():
    """Get the card_framework ModuleWrapper for DSL symbol access."""
    try:
        from gchat.card_framework_wrapper import get_card_framework_wrapper

        return get_card_framework_wrapper()
    except Exception as e:
        print(f"Failed to get ModuleWrapper: {e}")
        return None


def get_test_descriptions(limit: int = 30) -> list[dict[str, Any]]:
    """
    Pull real patterns from the Qdrant collection WITH DSL notation.

    Returns list of dicts with:
        - card_description: The description text
        - relationship_text: DSL notation (e.g., "§[δ, Ƀ[ᵬ×2]] | Section...")
        - dsl_query: DSL-prefixed query for testing truncation
        - id: Point ID
    """
    try:
        from qdrant_client import models

        from config.qdrant_client import get_qdrant_client

        client = get_qdrant_client()
        collection_name = settings.card_collection

        # Query for instance_pattern points that have relationship_text (DSL)
        results, _ = client.scroll(
            collection_name=collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="type", match=models.MatchValue(value="instance_pattern")
                    )
                ]
            ),
            limit=limit * 2,  # Fetch extra to filter
            with_payload=["card_description", "relationship_text", "structure_description"],
        )

        descriptions = []
        for point in results:
            desc = point.payload.get("card_description", "")
            dsl = point.payload.get("relationship_text", "")

            if desc and len(desc) > 10 and dsl:
                # Create DSL-prefixed query: "§[δ, Ƀ] Build a card with..."
                # This puts the high-signal DSL symbols at the START
                dsl_query = f"{dsl} {desc}"

                descriptions.append(
                    {
                        "card_description": desc,
                        "relationship_text": dsl,
                        "dsl_query": dsl_query,
                        "id": str(point.id),
                        "structure_description": point.payload.get(
                            "structure_description", ""
                        ),
                    }
                )

        # Sort by DSL query length to get variety
        descriptions.sort(key=lambda x: len(x["dsl_query"]))

        # Sample evenly across lengths
        if len(descriptions) > limit:
            step = len(descriptions) // limit
            descriptions = descriptions[::step][:limit]

        print(f"Loaded {len(descriptions)} test patterns with DSL from Qdrant")
        if descriptions:
            print(f"  Sample DSL: {descriptions[0]['relationship_text'][:60]}...")
        return descriptions

    except Exception as e:
        print(f"Failed to load descriptions from Qdrant: {e}")
        return []


def generate_synthetic_dsl_queries(wrapper, count: int = 10) -> list[dict[str, Any]]:
    """
    Generate synthetic DSL-prefixed test queries using ModuleWrapper symbols.

    Args:
        wrapper: ModuleWrapper instance with symbol_mapping
        count: Number of queries to generate

    Returns:
        List of test query dicts
    """
    if not wrapper:
        return []

    symbols = getattr(wrapper, "symbol_mapping", {})
    if not symbols:
        print("No symbol mapping available")
        return []

    print(f"Using {len(symbols)} DSL symbols from ModuleWrapper")

    # Common component combinations for testing
    test_patterns = [
        (["Section", "DecoratedText"], "Show a simple text message"),
        (["Section", "DecoratedText", "ButtonList", "Button"], "Card with action buttons"),
        (["Section", "DecoratedText", "DecoratedText", "DecoratedText"], "Card with multiple text items"),
        (["Section", "Grid", "GridItem"], "Grid layout with items"),
        (["Section", "DecoratedText", "Image"], "Card with image and text"),
        (["Section", "ButtonList", "Button", "Button"], "Card with two buttons"),
        (["Section", "ChipList", "Chip"], "Card with selectable chips"),
        (["Section", "Columns", "Column"], "Multi-column layout"),
        (["Section", "DecoratedText", "Divider", "ButtonList"], "Card with divider"),
        (["Section", "TextParagraph", "ButtonList", "Button"], "Simple text with button"),
    ]

    queries = []
    for i, (components, description) in enumerate(test_patterns[:count]):
        # Build DSL notation using wrapper
        dsl = wrapper.build_dsl_from_paths(components, "")

        # Create DSL-prefixed query
        dsl_query = f"{dsl} {description}"

        queries.append(
            {
                "card_description": description,
                "relationship_text": dsl,
                "dsl_query": dsl_query,
                "id": f"synthetic_{i}",
                "components": components,
            }
        )

    print(f"Generated {len(queries)} synthetic DSL queries")
    if queries:
        print(f"  Sample: {queries[0]['dsl_query'][:70]}...")

    return queries


def benchmark_query(
    feedback_loop, query: str, token_ratio: float, show_tokens: bool = False
) -> BenchmarkResult:
    """
    Run a single benchmark query with the given token ratio.

    Args:
        feedback_loop: FeedbackLoop instance
        query: The query string (should be DSL-prefixed for best results)
        token_ratio: Fraction of tokens to use (0.0-1.0)
        show_tokens: If True, print token details for debugging
    """
    # Get embedder to count tokens
    embedder = feedback_loop._get_embedder()
    if not embedder:
        raise RuntimeError("Could not get ColBERT embedder")

    # Count full tokens and show what gets truncated
    vectors_raw = list(embedder.query_embed(query))[0]
    full_token_count = len(vectors_raw)

    # Calculate truncated count
    if token_ratio < 1.0:
        truncated_count = max(1, int(full_token_count * token_ratio))
    else:
        truncated_count = full_token_count

    if show_tokens and token_ratio == 1.0:
        # Show what tokens are in the query (useful for understanding DSL placement)
        print(f"    Full query ({full_token_count} tokens): {query[:80]}...")

    # Time the query
    start_time = time.perf_counter()
    class_results, content_patterns, _ = feedback_loop.query_with_feedback(
        component_query=query,
        description=query,
        limit=10,
        use_negative_feedback=False,  # Disable for cleaner benchmark
        token_ratio=token_ratio,
    )
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    # Combine results (prioritize content patterns, then class results)
    all_results = content_patterns + class_results
    result_ids = [str(r.get("id", "")) for r in all_results[:10]]
    result_scores = [r.get("score", 0.0) for r in all_results[:10]]

    return BenchmarkResult(
        description=query[:50] + "..." if len(query) > 50 else query,
        token_ratio=token_ratio,
        full_tokens=full_token_count,
        truncated_tokens=truncated_count,
        query_latency_ms=elapsed_ms,
        result_ids=result_ids,
        result_scores=result_scores,
    )


def calculate_overlap(baseline_ids: list[str], test_ids: list[str], top_n: int) -> float:
    """Calculate overlap ratio for top N results."""
    if not baseline_ids or not test_ids:
        return 0.0

    baseline_set = set(baseline_ids[:top_n])
    test_set = set(test_ids[:top_n])

    if not baseline_set:
        return 1.0  # No baseline to compare

    overlap = len(baseline_set & test_set)
    return overlap / len(baseline_set)


def calculate_score_correlation(
    baseline_scores: list[float], test_scores: list[float]
) -> float:
    """Calculate simple correlation between score rankings."""
    if not baseline_scores or not test_scores:
        return 0.0

    # Normalize scores
    min_len = min(len(baseline_scores), len(test_scores))
    if min_len == 0:
        return 0.0

    # Simple rank correlation: check if relative ordering is preserved
    correct_order = 0
    total_pairs = 0

    for i in range(min_len):
        for j in range(i + 1, min_len):
            total_pairs += 1
            # Check if same relative ordering
            baseline_order = baseline_scores[i] >= baseline_scores[j]
            test_order = test_scores[i] >= test_scores[j]
            if baseline_order == test_order:
                correct_order += 1

    return correct_order / total_pairs if total_pairs > 0 else 1.0


def run_benchmark(test_data: list[dict[str, Any]]) -> dict[float, ComparisonMetrics]:
    """
    Run full benchmark across all DSL queries and token ratios.

    Args:
        test_data: List of dicts with 'dsl_query', 'relationship_text', 'card_description'
    """
    from gchat.feedback_loop import get_feedback_loop

    feedback_loop = get_feedback_loop()

    token_ratios = [1.0, 0.5, 0.25, 0.1]
    results_by_ratio: dict[float, list[BenchmarkResult]] = {r: [] for r in token_ratios}
    baseline_results: dict[str, BenchmarkResult] = {}  # query -> baseline result

    print("\nRunning benchmarks with DSL-prefixed queries...")
    print("-" * 70)

    for i, data in enumerate(test_data):
        # Use DSL-prefixed query for testing truncation effectiveness
        dsl_query = data.get("dsl_query", data.get("card_description", ""))
        dsl_part = data.get("relationship_text", "")[:30]
        desc_part = data.get("card_description", "")[:40]

        print(f"\n[{i + 1}/{len(test_data)}] DSL: {dsl_part}... + \"{desc_part}...\"")

        # Run for each token ratio
        for ratio in token_ratios:
            try:
                # Show token details only for first query at baseline
                show_tokens = (i == 0 and ratio == 1.0)
                result = benchmark_query(feedback_loop, dsl_query, ratio, show_tokens)
                results_by_ratio[ratio].append(result)

                if ratio == 1.0:
                    baseline_results[result.description] = result

                status = "baseline" if ratio == 1.0 else f"{result.truncated_tokens}/{result.full_tokens} tokens"
                print(
                    f"  {ratio:.0%}: {result.query_latency_ms:6.1f}ms, "
                    f"{len(result.result_ids)} results ({status})"
                )

            except Exception as e:
                print(f"  {ratio:.0%}: FAILED - {e}")

    # Calculate comparison metrics
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    metrics: dict[float, ComparisonMetrics] = {}

    for ratio in token_ratios:
        ratio_results = results_by_ratio[ratio]
        if not ratio_results:
            continue

        speedups = []
        overlaps_top5 = []
        overlaps_top3 = []
        correlations = []

        for result in ratio_results:
            baseline = baseline_results.get(result.description[:50] + "..." if len(result.description) > 50 else result.description)
            if not baseline:
                # Find baseline by matching truncated description
                for desc, base in baseline_results.items():
                    if desc.startswith(result.description[:30]):
                        baseline = base
                        break

            if baseline and baseline.query_latency_ms > 0:
                # Speedup (negative means slower)
                speedup = (
                    (baseline.query_latency_ms - result.query_latency_ms)
                    / baseline.query_latency_ms
                    * 100
                )
                speedups.append(speedup)

                # Overlap
                overlaps_top5.append(
                    calculate_overlap(baseline.result_ids, result.result_ids, 5)
                )
                overlaps_top3.append(
                    calculate_overlap(baseline.result_ids, result.result_ids, 3)
                )

                # Score correlation
                correlations.append(
                    calculate_score_correlation(
                        baseline.result_scores, result.result_scores
                    )
                )

        metrics[ratio] = ComparisonMetrics(
            token_ratio=ratio,
            avg_speedup_percent=sum(speedups) / len(speedups) if speedups else 0,
            avg_result_overlap_top5=sum(overlaps_top5) / len(overlaps_top5)
            if overlaps_top5
            else 0,
            avg_result_overlap_top3=sum(overlaps_top3) / len(overlaps_top3)
            if overlaps_top3
            else 0,
            avg_score_correlation=sum(correlations) / len(correlations)
            if correlations
            else 0,
            sample_count=len(ratio_results),
        )

    return metrics


def print_metrics_table(metrics: dict[float, ComparisonMetrics]) -> None:
    """Print a formatted metrics table."""
    print("\n" + "-" * 70)
    print(
        f"{'Token Ratio':<12} {'Speedup':<10} {'Top-5 Overlap':<14} "
        f"{'Top-3 Overlap':<14} {'Score Corr.':<12} {'Samples':<8}"
    )
    print("-" * 70)

    for ratio in sorted(metrics.keys(), reverse=True):
        m = metrics[ratio]
        speedup_str = f"{m.avg_speedup_percent:+.1f}%" if ratio != 1.0 else "baseline"
        print(
            f"{m.token_ratio:<12.0%} {speedup_str:<10} {m.avg_result_overlap_top5:<14.1%} "
            f"{m.avg_result_overlap_top3:<14.1%} {m.avg_score_correlation:<12.1%} "
            f"{m.sample_count:<8}"
        )

    print("-" * 70)


def print_recommendations(metrics: dict[float, ComparisonMetrics]) -> None:
    """Print optimization recommendations based on metrics."""
    print("\nRECOMMENDATIONS:")
    print("-" * 70)

    for ratio in [0.5, 0.25, 0.1]:
        if ratio not in metrics:
            continue

        m = metrics[ratio]
        speedup = m.avg_speedup_percent
        overlap = m.avg_result_overlap_top5

        if overlap >= 0.9 and speedup >= 20:
            verdict = "RECOMMENDED"
            reason = f"{speedup:.0f}% faster with {overlap:.0%} result quality"
        elif overlap >= 0.8 and speedup >= 40:
            verdict = "CONSIDER"
            reason = f"Good trade-off: {speedup:.0f}% faster, {overlap:.0%} quality"
        elif overlap < 0.7:
            verdict = "NOT RECOMMENDED"
            reason = f"Quality too low ({overlap:.0%})"
        else:
            verdict = "MARGINAL"
            reason = f"Speedup ({speedup:.0f}%) may not justify quality loss ({overlap:.0%})"

        print(f"  {ratio:.0%} tokens: {verdict}")
        print(f"    {reason}")


def main():
    """Main entry point."""
    print("=" * 70)
    print("ColBERT Token Truncation Benchmark (DSL-Prefixed Queries)")
    print("=" * 70)
    print(f"\nCollection: {settings.card_collection}")
    print("\nThis benchmark tests with DSL symbols at the START of queries.")
    print("Hypothesis: Truncation preserves high-signal DSL symbols in first tokens.")

    # Get ModuleWrapper for DSL symbol access
    wrapper = get_module_wrapper()

    # Try to load real patterns with DSL from Qdrant
    test_data = get_test_descriptions(limit=20)

    if not test_data:
        print("\nNo real patterns found. Generating synthetic DSL queries...")
        test_data = generate_synthetic_dsl_queries(wrapper, count=10)

    if not test_data:
        print("\nERROR: Could not generate test data. Check ModuleWrapper availability.")
        return

    if len(test_data) < 5:
        print(f"\nWARNING: Only {len(test_data)} test queries available.")
        print("Results may not be statistically significant.")

    # Show symbol mapping sample
    if wrapper:
        symbols = getattr(wrapper, "symbol_mapping", {})
        if symbols:
            sample_symbols = list(symbols.items())[:5]
            print(f"\nDSL Symbol samples: {dict(sample_symbols)}")

    # Run benchmark
    metrics = run_benchmark(test_data)

    # Print results
    print_metrics_table(metrics)
    print_recommendations(metrics)

    print("\n" + "=" * 70)
    print("INTERPRETATION:")
    print("-" * 70)
    print("If DSL symbols are in the first tokens, truncation should:")
    print("  - Preserve the §, δ, ᵬ symbols that strongly match class embeddings")
    print("  - Maintain high overlap even at 25-50% token ratios")
    print("  - Show better quality than plain text truncation")
    print("=" * 70)

    print("\nDone!")


if __name__ == "__main__":
    main()
