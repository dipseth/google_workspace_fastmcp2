"""Unit tests for middleware.payment.cost_tracker."""

import pytest

from middleware.payment.cost_tracker import (
    estimate_qdrant_cost,
    get_current_costs,
    reset,
    track_sample_call,
)


class TestCostTracker:
    """Tests for the ContextVar-based sampling cost tracker."""

    def setup_method(self):
        reset()

    def test_reset_returns_empty_costs(self):
        costs = get_current_costs()
        assert costs["sampling_detected"] is False
        assert costs["sampling_calls"] == 0
        assert costs["cost_sampling_estimated"] == 0.0

    def test_single_sample_call(self):
        track_sample_call(
            input_text="Hello, how are you?",
            output_text="I am doing well, thank you!",
            model="claude-sonnet-4-6",
        )
        costs = get_current_costs()
        assert costs["sampling_detected"] is True
        assert costs["sampling_calls"] == 1
        assert costs["sampling_model"] == "claude-sonnet-4-6"
        assert costs["cost_sampling_estimated"] > 0
        assert costs["sampling_estimated_input_tokens"] > 0
        assert costs["sampling_estimated_output_tokens"] > 0

    def test_multiple_sample_calls_accumulate(self):
        track_sample_call("prompt one", "response one")
        track_sample_call("prompt two", "response two")
        track_sample_call("prompt three", "response three")

        costs = get_current_costs()
        assert costs["sampling_calls"] == 3
        assert costs["sampling_detected"] is True
        assert costs["cost_sampling_estimated"] > 0

    def test_reset_clears_accumulated_costs(self):
        track_sample_call("prompt", "response")
        assert get_current_costs()["sampling_calls"] == 1

        reset()
        costs = get_current_costs()
        assert costs["sampling_calls"] == 0
        assert costs["sampling_detected"] is False

    def test_token_estimation_heuristic(self):
        # 400 chars ≈ 100 tokens
        input_text = "x" * 400
        output_text = "y" * 200
        track_sample_call(input_text, output_text)

        costs = get_current_costs()
        assert costs["sampling_estimated_input_tokens"] == 100
        assert costs["sampling_estimated_output_tokens"] == 50

    def test_empty_input_output(self):
        track_sample_call("", "")
        costs = get_current_costs()
        assert costs["sampling_detected"] is True
        assert costs["sampling_calls"] == 1
        # Minimum 1 token each
        assert costs["sampling_estimated_input_tokens"] == 1
        assert costs["sampling_estimated_output_tokens"] == 1

    def test_actual_token_counts_override_heuristic(self):
        """When actual token counts are provided, they override text estimation."""
        track_sample_call(
            input_text="short",
            output_text="short",
            model="openai/gpt-4",
            input_tokens=500,
            output_tokens=200,
        )
        costs = get_current_costs()
        assert costs["sampling_estimated_input_tokens"] == 500
        assert costs["sampling_estimated_output_tokens"] == 200
        assert costs["sampling_model"] == "openai/gpt-4"

    def test_actual_tokens_zero_falls_back_to_heuristic(self):
        """When actual token counts are 0, text estimation is used."""
        track_sample_call(
            input_text="x" * 400,
            output_text="y" * 200,
            input_tokens=0,
            output_tokens=0,
        )
        costs = get_current_costs()
        assert costs["sampling_estimated_input_tokens"] == 100
        assert costs["sampling_estimated_output_tokens"] == 50

    def test_cost_fields_structure(self):
        """Verify returned dict has all expected keys."""
        costs = get_current_costs()
        expected_keys = {
            "sampling_detected",
            "sampling_calls",
            "sampling_estimated_input_tokens",
            "sampling_estimated_output_tokens",
            "cost_sampling_estimated",
            "sampling_model",
        }
        assert set(costs.keys()) == expected_keys


class TestQdrantCostEstimation:
    """Tests for Qdrant operation cost estimation."""

    def test_upsert_cost(self):
        cost = estimate_qdrant_cost("upsert")
        assert cost > 0
        assert isinstance(cost, float)

    def test_search_cost(self):
        cost = estimate_qdrant_cost("search")
        assert cost > 0

    def test_embed_cost(self):
        cost = estimate_qdrant_cost("embed")
        assert cost > 0

    def test_unknown_operation(self):
        cost = estimate_qdrant_cost("nonexistent")
        assert cost == 0.0

    def test_search_cheaper_than_upsert(self):
        assert estimate_qdrant_cost("search") <= estimate_qdrant_cost("upsert")
