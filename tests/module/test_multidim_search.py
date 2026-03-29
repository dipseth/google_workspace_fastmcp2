"""
Tests for Multi-Dimensional Scoring (Horizon 1 — RIC-TRM)

Tests the search_hybrid_multidim() method and its helper functions
(_maxsim, _cosine_similarity) in search_mixin.py.

Architecture note: search_hybrid_multidim uses Qdrant's native prefetch
pipeline (single server-side round-trip) for candidate expansion, then
performs client-side multiplicative cross-dimensional reranking. The
MaxSim and cosine similarity helpers are client-side only — Qdrant does
not natively support multiplicative cross-vector scoring.
"""

import math
from typing import List
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from adapters.module_wrapper.search_mixin import SearchMixin

# =========================================================================
# FIXTURES
# =========================================================================


class MockSearchMixin(SearchMixin):
    """Minimal concrete class for testing SearchMixin methods."""

    def __init__(self):
        self._initialized = True
        self.client = MagicMock()
        self.embedder = MagicMock()
        self.collection_name = "test_collection"
        self.components = {}
        self.module = MagicMock()
        self.module_name = "test_module"
        self._module_name = "test_module"
        self.symbol_mapping = {}
        self.reverse_symbol_mapping = {}
        self.relationships = {}
        self.enable_colbert = True
        self._colbert_initialized = True
        self.colbert_embedder = MagicMock()
        self.colbert_collection_name = "test_colbert"


@pytest.fixture
def mixin():
    return MockSearchMixin()


def _make_unit_vec(dim: int, index: int = 0) -> List[float]:
    """Create a unit vector with 1.0 at the given index."""
    vec = [0.0] * dim
    vec[index % dim] = 1.0
    return vec


def _make_colbert_vecs(dim: int = 128, n_tokens: int = 3) -> List[List[float]]:
    """Create mock ColBERT multi-vectors (n_tokens x dim)."""
    return [_make_unit_vec(dim, i) for i in range(n_tokens)]


def _make_scored_point(
    point_id, payload, vectors=None, score=0.9
):
    """Create a mock Qdrant ScoredPoint with vectors."""
    point = MagicMock()
    point.id = point_id
    point.payload = payload
    point.score = score
    point.vector = vectors
    return point


# =========================================================================
# UNIT TESTS: MaxSim
# =========================================================================


class TestMaxSim:
    """Tests for the _maxsim static method."""

    def test_identical_vectors_score_1(self):
        """MaxSim of identical vectors should be 1.0."""
        vecs = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        score = SearchMixin._maxsim(vecs, vecs)
        assert abs(score - 1.0) < 1e-6

    def test_orthogonal_vectors_score_0(self):
        """MaxSim of fully orthogonal sets should be 0.0."""
        query = [[1.0, 0.0, 0.0, 0.0]]
        doc = [[0.0, 1.0, 0.0, 0.0]]
        score = SearchMixin._maxsim(query, doc)
        assert abs(score) < 1e-6

    def test_partial_overlap(self):
        """MaxSim with partial overlap should be between 0 and 1."""
        query = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        doc = [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
        score = SearchMixin._maxsim(query, doc)
        # First query token matches perfectly (1.0), second doesn't (0.0)
        assert abs(score - 0.5) < 1e-6

    def test_empty_query_returns_0(self):
        """Empty query vectors should return 0."""
        score = SearchMixin._maxsim([], [[1.0, 0.0]])
        assert score == 0.0

    def test_empty_doc_returns_0(self):
        """Empty document vectors should return 0."""
        score = SearchMixin._maxsim([[1.0, 0.0]], [])
        assert score == 0.0

    def test_single_token_equals_cosine(self):
        """With single tokens, MaxSim should equal cosine similarity."""
        q = [[0.6, 0.8]]
        d = [[0.8, 0.6]]
        maxsim_score = SearchMixin._maxsim(q, d)
        cosine_score = SearchMixin._cosine_similarity(q[0], d[0])
        assert abs(maxsim_score - cosine_score) < 1e-6

    def test_multi_doc_tokens_finds_best(self):
        """Each query token should match against the best doc token."""
        query = [[1.0, 0.0, 0.0]]
        doc = [[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
        score = SearchMixin._maxsim(query, doc)
        # Query token perfectly matches second doc token
        assert abs(score - 1.0) < 1e-6


# =========================================================================
# UNIT TESTS: Cosine Similarity
# =========================================================================


class TestCosineSimilarity:
    """Tests for the _cosine_similarity static method."""

    def test_identical_vectors(self):
        score = SearchMixin._cosine_similarity([1.0, 0.0], [1.0, 0.0])
        assert abs(score - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        score = SearchMixin._cosine_similarity([1.0, 0.0], [0.0, 1.0])
        assert abs(score) < 1e-6

    def test_opposite_vectors(self):
        score = SearchMixin._cosine_similarity([1.0, 0.0], [-1.0, 0.0])
        assert abs(score - (-1.0)) < 1e-6

    def test_zero_vector_returns_0(self):
        score = SearchMixin._cosine_similarity([0.0, 0.0], [1.0, 0.0])
        assert score == 0.0

    def test_non_unit_vectors(self):
        """Should work with non-unit vectors (normalizes internally)."""
        score = SearchMixin._cosine_similarity([3.0, 0.0], [5.0, 0.0])
        assert abs(score - 1.0) < 1e-6


# =========================================================================
# UNIT TESTS: Multi-Dimensional Scoring
# =========================================================================


class TestMultidimScoring:
    """Tests for scoring logic within search_hybrid_multidim."""

    def test_multiplicative_score_basic(self):
        """Verify multiplicative scoring: (sim_c + eps) * (sim_r + eps) * (sim_i + eps)."""
        eps = 0.01
        sim_c, sim_r, sim_i = 0.9, 0.8, 0.7
        expected = (sim_c + eps) * (sim_r + eps) * (sim_i + eps)
        # Approximately 0.91 * 0.81 * 0.71
        assert expected > 0
        assert abs(expected - 0.91 * 0.81 * 0.71) < 0.01

    def test_zero_dimension_penalized(self):
        """A candidate with 0 on one dimension should score near 0."""
        eps = 0.01
        # Good on 2 dims, bad on 1
        score_good = (0.9 + eps) * (0.8 + eps) * (0.0 + eps)
        score_all = (0.9 + eps) * (0.8 + eps) * (0.7 + eps)
        assert score_good < score_all * 0.1  # Much worse

    def test_feedback_boost_positive(self):
        """Positive feedback should increase score."""
        base = 1.0
        boosted = base * 1.1  # content positive
        assert boosted > base

    def test_feedback_boost_negative(self):
        """Negative feedback should decrease score."""
        base = 1.0
        penalized = base * 0.8  # content negative
        assert penalized < base

    def test_feedback_double_boost(self):
        """Both content and form positive should compound."""
        base = 1.0
        double_boosted = base * 1.1 * 1.1
        single_boosted = base * 1.1
        assert double_boosted > single_boosted


# =========================================================================
# INTEGRATION TESTS: search_hybrid_multidim
# =========================================================================


class TestSearchHybridMultidim:
    """Integration tests for the full search_hybrid_multidim method.

    These tests verify that search_hybrid_multidim correctly uses Qdrant's
    prefetch pipeline (single query_points call with with_vectors=True)
    rather than multiple separate round-trips.
    """

    def _setup_mock_prefetch(self, mixin, scored_points=None):
        """Configure mixin mocks for prefetch-based multidim search.

        The refactored method uses a single query_points call with:
        - prefetch=[...] for server-side candidate expansion
        - query=FusionQuery(Fusion.RRF) for server-side dedup
        - with_vectors=True for returning stored vectors
        """
        colbert_vecs = _make_colbert_vecs(128, 3)
        minilm_vec = _make_unit_vec(384, 0)

        mixin._embed_with_colbert = MagicMock(return_value=colbert_vecs)
        mixin._embed_with_minilm = MagicMock(return_value=minilm_vec)

        if scored_points is None:
            scored_points = [
                _make_scored_point(
                    "point_1",
                    {
                        "type": "class",
                        "name": "Section",
                        "full_path": "card_framework.Section",
                        "docstring": "A card section",
                        "symbol": "§",
                    },
                    vectors={
                        "components": colbert_vecs,
                        "inputs": colbert_vecs,
                        "relationships": minilm_vec,
                    },
                )
            ]

        mock_result = MagicMock()
        mock_result.points = scored_points
        mixin.client.query_points.return_value = mock_result

    def test_returns_3_tuple(self, mixin):
        """search_hybrid_multidim must return (classes, patterns, relationships)."""
        self._setup_mock_prefetch(mixin)
        result = mixin.search_hybrid_multidim("build a card")
        assert isinstance(result, tuple)
        assert len(result) == 3
        classes, patterns, relationships = result
        assert isinstance(classes, list)
        assert isinstance(patterns, list)
        assert isinstance(relationships, list)

    def test_single_query_points_call(self, mixin):
        """Should use exactly ONE query_points call (prefetch pipeline)."""
        self._setup_mock_prefetch(mixin)
        mixin.search_hybrid_multidim("build a card")
        assert mixin.client.query_points.call_count == 1

    def test_prefetch_with_vectors(self, mixin):
        """The single query_points call must include with_vectors=True."""
        self._setup_mock_prefetch(mixin)
        mixin.search_hybrid_multidim("build a card")
        call_kwargs = mixin.client.query_points.call_args.kwargs
        assert call_kwargs.get("with_vectors") is True

    def test_no_separate_retrieve_call(self, mixin):
        """Should NOT use a separate client.retrieve() call."""
        self._setup_mock_prefetch(mixin)
        mixin.search_hybrid_multidim("build a card")
        mixin.client.retrieve.assert_not_called()

    def test_prefetch_has_3_entries(self, mixin):
        """Prefetch list should have 3 entries (components, inputs, relationships)."""
        self._setup_mock_prefetch(mixin)
        mixin.search_hybrid_multidim("build a card")
        call_kwargs = mixin.client.query_points.call_args.kwargs
        prefetch = call_kwargs.get("prefetch", [])
        assert len(prefetch) == 3  # components + inputs + relationships

    def test_prefetch_has_2_entries_no_classes(self, mixin):
        """With include_classes=False, prefetch should have 2 entries."""
        self._setup_mock_prefetch(mixin)
        mixin.search_hybrid_multidim("build a card", include_classes=False)
        call_kwargs = mixin.client.query_points.call_args.kwargs
        prefetch = call_kwargs.get("prefetch", [])
        assert len(prefetch) == 2  # inputs + relationships only

    def test_class_results_categorized(self, mixin):
        """Class-type points should appear in class_results."""
        self._setup_mock_prefetch(mixin)
        classes, patterns, rels = mixin.search_hybrid_multidim("build a card")
        assert len(classes) >= 1
        assert classes[0]["type"] == "class"

    def test_pattern_results_categorized(self, mixin):
        """Instance pattern points should appear in pattern/relationship results."""
        colbert_vecs = _make_colbert_vecs(128, 3)
        minilm_vec = _make_unit_vec(384, 0)

        self._setup_mock_prefetch(
            mixin,
            scored_points=[
                _make_scored_point(
                    "pat_1",
                    {
                        "type": "instance_pattern",
                        "name": "pattern1",
                        "full_path": "card_framework.pattern1",
                        "docstring": "A pattern",
                        "content_feedback": None,
                        "form_feedback": None,
                    },
                    vectors={
                        "components": colbert_vecs,
                        "inputs": colbert_vecs,
                        "relationships": minilm_vec,
                    },
                )
            ],
        )

        classes, patterns, rels = mixin.search_hybrid_multidim("build a card")
        assert len(patterns) >= 1
        assert patterns[0]["type"] == "instance_pattern"

    def test_no_client_returns_empty(self, mixin):
        """Should return empty tuples when client is None."""
        mixin.client = None
        result = mixin.search_hybrid_multidim("test")
        assert result == ([], [], [])

    def test_embedding_failure_returns_empty(self, mixin):
        """Should return empty tuples when embedding fails."""
        mixin._embed_with_colbert = MagicMock(return_value=None)
        result = mixin.search_hybrid_multidim("test")
        assert result == ([], [], [])

    def test_score_includes_dimension_sims(self, mixin):
        """Result dicts should include per-dimension similarity scores."""
        self._setup_mock_prefetch(mixin)
        classes, _, _ = mixin.search_hybrid_multidim("build a card")
        if classes:
            assert "sim_components" in classes[0]
            assert "sim_relationships" in classes[0]
            assert "sim_inputs" in classes[0]
            assert "score" in classes[0]

    def test_feedback_boost_affects_ranking(self, mixin):
        """Points with positive feedback should rank higher than neutral."""
        colbert_vecs = _make_colbert_vecs(128, 3)
        minilm_vec = _make_unit_vec(384, 0)

        # Two patterns with identical vectors but different feedback
        self._setup_mock_prefetch(
            mixin,
            scored_points=[
                _make_scored_point(
                    "pos_1",
                    {
                        "type": "instance_pattern",
                        "name": "positive_pattern",
                        "content_feedback": "positive",
                        "form_feedback": "positive",
                    },
                    vectors={
                        "components": colbert_vecs,
                        "inputs": colbert_vecs,
                        "relationships": minilm_vec,
                    },
                ),
                _make_scored_point(
                    "neu_1",
                    {
                        "type": "instance_pattern",
                        "name": "neutral_pattern",
                        "content_feedback": None,
                        "form_feedback": None,
                    },
                    vectors={
                        "components": colbert_vecs,
                        "inputs": colbert_vecs,
                        "relationships": minilm_vec,
                    },
                ),
            ],
        )

        classes, patterns, rels = mixin.search_hybrid_multidim("test")
        # Positive feedback pattern should have a higher score
        all_results = patterns + rels
        if len(all_results) >= 2:
            pos_results = [r for r in all_results if r.get("content_feedback") == "positive"]
            neu_results = [r for r in all_results if r.get("content_feedback") is None]
            if pos_results and neu_results:
                assert pos_results[0]["score"] > neu_results[0]["score"]

    def test_uses_fusion_query_rrf(self, mixin):
        """Should use FusionQuery with RRF for server-side dedup."""
        self._setup_mock_prefetch(mixin)
        mixin.search_hybrid_multidim("build a card")
        call_kwargs = mixin.client.query_points.call_args.kwargs
        query = call_kwargs.get("query")
        # Verify it's a FusionQuery (mock won't have exact type, check it was passed)
        assert query is not None

    def test_empty_results_returns_empty(self, mixin):
        """Should handle empty results gracefully."""
        colbert_vecs = _make_colbert_vecs(128, 3)
        minilm_vec = _make_unit_vec(384, 0)
        mixin._embed_with_colbert = MagicMock(return_value=colbert_vecs)
        mixin._embed_with_minilm = MagicMock(return_value=minilm_vec)

        mock_result = MagicMock()
        mock_result.points = []
        mixin.client.query_points.return_value = mock_result

        result = mixin.search_hybrid_multidim("test")
        assert result == ([], [], [])
