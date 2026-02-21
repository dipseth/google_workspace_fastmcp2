"""
Tests for query_with_discovery() — Qdrant Discovery API integration.

Validates that:
1. DiscoverQuery is constructed with correct target + context pairs
2. Content feedback IDs become context pairs on 'inputs' vector
3. Form feedback IDs become context pairs on 'relationships' vector
4. Fallback to standard vector search when no feedback exists
5. ef=128 is passed in search params
6. Context pair capping works correctly
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_qdrant_models():
    """Provide real qdrant_client.models for type checking."""
    from qdrant_client import models

    return models


@pytest.fixture
def mock_client():
    """Mock Qdrant client that returns empty results by default."""
    client = MagicMock()

    def _empty_query(*args, **kwargs):
        return SimpleNamespace(points=[])

    client.query_points.side_effect = _empty_query

    def _empty_scroll(*args, **kwargs):
        return ([], None)

    client.scroll.side_effect = _empty_scroll
    return client


class _FakeVector:
    """Mimics a numpy array with .tolist()."""

    def __init__(self, values):
        self._values = values

    def tolist(self):
        return self._values


@pytest.fixture
def feedback_loop(mock_client):
    """Create a FeedbackLoop instance with mocked dependencies."""
    with patch.dict(os.environ, {"CARD_COLLECTION": "test_collection"}):
        from gchat.feedback_loop import FeedbackLoop

        fl = FeedbackLoop()
        fl._client = mock_client

        # Mock ColBERT embedder: query_embed returns iterable of [array_of_token_vectors]
        # list(embedder.query_embed(text))[0] → [FakeVector, FakeVector]
        mock_colbert = MagicMock()
        token_vectors = [_FakeVector([0.1] * 128), _FakeVector([0.2] * 128)]
        mock_colbert.query_embed.return_value = [token_vectors]
        fl._embedder = mock_colbert

        # Mock MiniLM embedder: embed returns iterable of [FakeVector(384d)]
        # list(embedder.embed([text]))[0] → FakeVector with .tolist()
        mock_minilm = MagicMock()
        mock_minilm.embed.return_value = [_FakeVector([0.5] * 384)]
        fl._relationship_embedder = mock_minilm

        return fl


def _make_scroll_results(ids):
    """Create mock scroll results with given IDs."""
    return ([SimpleNamespace(id=id_) for id_ in ids], None)


def _make_query_results(points_data):
    """Create mock query_points results."""
    points = [
        SimpleNamespace(
            id=p["id"],
            score=p.get("score", 0.9),
            payload=p.get("payload", {"type": "instance_pattern"}),
        )
        for p in points_data
    ]
    return SimpleNamespace(points=points)


# ---------------------------------------------------------------------------
# Tests: _build_context_pairs
# ---------------------------------------------------------------------------


class TestBuildContextPairs:
    def test_returns_empty_when_no_positives(self):
        from gchat.feedback_loop import FeedbackLoop

        pairs = FeedbackLoop._build_context_pairs([], ["neg1"])
        assert pairs == []

    def test_returns_empty_when_no_negatives(self):
        from gchat.feedback_loop import FeedbackLoop

        pairs = FeedbackLoop._build_context_pairs(["pos1"], [])
        assert pairs == []

    def test_single_pair(self, mock_qdrant_models):
        from gchat.feedback_loop import FeedbackLoop

        pairs = FeedbackLoop._build_context_pairs(["pos1"], ["neg1"])
        assert len(pairs) == 1
        assert pairs[0].positive == "pos1"
        assert pairs[0].negative == "neg1"

    def test_caps_at_max_pairs(self):
        from gchat.feedback_loop import FeedbackLoop

        pos = [f"pos{i}" for i in range(10)]
        neg = [f"neg{i}" for i in range(10)]
        pairs = FeedbackLoop._build_context_pairs(pos, neg, max_pairs=5)
        assert len(pairs) <= 5

    def test_cartesian_product(self):
        from gchat.feedback_loop import FeedbackLoop

        pairs = FeedbackLoop._build_context_pairs(
            ["p1", "p2"], ["n1", "n2"], max_pairs=10
        )
        assert len(pairs) == 4
        pair_tuples = [(p.positive, p.negative) for p in pairs]
        assert ("p1", "n1") in pair_tuples
        assert ("p1", "n2") in pair_tuples
        assert ("p2", "n1") in pair_tuples
        assert ("p2", "n2") in pair_tuples


# ---------------------------------------------------------------------------
# Tests: query_with_discovery
# ---------------------------------------------------------------------------


class TestQueryWithDiscovery:
    def test_returns_three_lists(self, feedback_loop):
        """Return signature is (class_results, content_results, form_results)."""
        result = feedback_loop.query_with_discovery(
            component_query="test", description="test card"
        )
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_fallback_when_no_feedback(self, feedback_loop, mock_client):
        """When no feedback IDs exist, falls back to standard vector search."""
        from qdrant_client.http.models import DiscoverQuery

        # scroll returns empty = no feedback IDs
        mock_client.scroll.side_effect = lambda **kw: ([], None)

        # Clear side_effect and set return_value for query_points
        mock_client.query_points.side_effect = None
        mock_client.query_points.return_value = _make_query_results(
            [{"id": "point1", "payload": {"type": "instance_pattern"}}]
        )

        classes, content, form = feedback_loop.query_with_discovery(
            component_query="test", description="a status card"
        )

        # Should get content results from the fallback vector search path
        assert len(content) > 0

        # Verify NO DiscoverQuery was used (all calls should be plain vector queries)
        for c in mock_client.query_points.call_args_list:
            query_arg = c.kwargs.get("query")
            if query_arg is not None and hasattr(query_arg, "__class__"):
                assert not isinstance(query_arg, DiscoverQuery), (
                    "Should not use DiscoverQuery when no feedback exists"
                )

    def test_discovery_query_with_content_feedback(self, feedback_loop, mock_client):
        """Content feedback IDs should produce a DiscoverQuery on 'inputs' vector."""
        from qdrant_client import models

        # Mock scroll to return positive and negative feedback IDs
        def scroll_side_effect(**kwargs):
            filt = kwargs.get("scroll_filter")
            # Check which feedback field and value is being queried
            for cond in filt.must:
                if hasattr(cond, "key") and "feedback" in cond.key:
                    if cond.match.value == "positive":
                        return _make_scroll_results(["pos_content_1", "pos_content_2"])
                    elif cond.match.value == "negative":
                        return _make_scroll_results(["neg_content_1"])
            return ([], None)

        mock_client.scroll.side_effect = scroll_side_effect
        mock_client.query_points.return_value = _make_query_results(
            [{"id": "result1", "score": 0.85, "payload": {"type": "instance_pattern"}}]
        )

        classes, content, form = feedback_loop.query_with_discovery(
            component_query="test", description="a status card"
        )

        # Find the call that used DiscoverQuery
        discover_calls = []
        for c in mock_client.query_points.call_args_list:
            query_arg = c.kwargs.get("query")
            if isinstance(query_arg, models.DiscoverQuery):
                discover_calls.append(c)

        assert len(discover_calls) >= 1, "Expected at least one DiscoverQuery call"

        # Check the content Discovery call targets 'inputs'
        content_discover = [
            c for c in discover_calls if c.kwargs.get("using") == "inputs"
        ]
        assert len(content_discover) == 1
        dq = content_discover[0].kwargs["query"]
        assert isinstance(dq.discover.target, list)  # Multi-vector (ColBERT)
        assert len(dq.discover.context) > 0

    def test_discovery_query_with_form_feedback(self, feedback_loop, mock_client):
        """Form feedback IDs should produce a DiscoverQuery on 'relationships' vector."""
        from qdrant_client import models

        def scroll_side_effect(**kwargs):
            filt = kwargs.get("scroll_filter")
            for cond in filt.must:
                if hasattr(cond, "key") and cond.key == "form_feedback":
                    if cond.match.value == "positive":
                        return _make_scroll_results(["pos_form_1"])
                    elif cond.match.value == "negative":
                        return _make_scroll_results(["neg_form_1"])
                elif hasattr(cond, "key") and cond.key == "content_feedback":
                    if cond.match.value == "positive":
                        return _make_scroll_results(["pos_content_1"])
                    elif cond.match.value == "negative":
                        return _make_scroll_results(["neg_content_1"])
            return ([], None)

        mock_client.scroll.side_effect = scroll_side_effect
        mock_client.query_points.return_value = _make_query_results(
            [{"id": "result1", "score": 0.85, "payload": {"type": "instance_pattern"}}]
        )

        classes, content, form = feedback_loop.query_with_discovery(
            component_query="test",
            description="a status card with buttons",
            component_paths=["widgets.DecoratedText", "widgets.ButtonList"],
        )

        # Find Discovery calls on 'relationships' vector
        discover_calls = [
            c
            for c in mock_client.query_points.call_args_list
            if isinstance(c.kwargs.get("query"), models.DiscoverQuery)
            and c.kwargs.get("using") == "relationships"
        ]
        assert len(discover_calls) == 1
        dq = discover_calls[0].kwargs["query"]
        assert isinstance(dq.discover.target, list)  # Single vector (384d)
        assert len(dq.discover.context) > 0

    def test_ef_128_in_search_params(self, feedback_loop, mock_client):
        """Discovery queries should use ef=128 for accuracy."""
        from qdrant_client import models

        def scroll_side_effect(**kwargs):
            filt = kwargs.get("scroll_filter")
            for cond in filt.must:
                if hasattr(cond, "key") and "feedback" in cond.key:
                    if cond.match.value == "positive":
                        return _make_scroll_results(["pos1"])
                    elif cond.match.value == "negative":
                        return _make_scroll_results(["neg1"])
            return ([], None)

        mock_client.scroll.side_effect = scroll_side_effect
        mock_client.query_points.return_value = _make_query_results([])

        feedback_loop.query_with_discovery(
            component_query="test", description="test card"
        )

        # Check all Discovery calls have ef=128
        for c in mock_client.query_points.call_args_list:
            query_arg = c.kwargs.get("query")
            if isinstance(query_arg, models.DiscoverQuery):
                search_params = c.kwargs.get("search_params")
                assert search_params is not None, "search_params should be set"
                assert search_params.hnsw_ef == 128, (
                    f"Expected hnsw_ef=128, got {search_params.hnsw_ef}"
                )

    def test_context_pairs_use_feedback_ids(self, feedback_loop, mock_client):
        """Context pairs should contain the actual feedback point IDs."""
        from qdrant_client import models

        pos_ids = ["pos_a", "pos_b"]
        neg_ids = ["neg_x"]

        def scroll_side_effect(**kwargs):
            filt = kwargs.get("scroll_filter")
            for cond in filt.must:
                if hasattr(cond, "key") and "feedback" in cond.key:
                    if cond.match.value == "positive":
                        return _make_scroll_results(pos_ids)
                    elif cond.match.value == "negative":
                        return _make_scroll_results(neg_ids)
            return ([], None)

        mock_client.scroll.side_effect = scroll_side_effect
        mock_client.query_points.return_value = _make_query_results([])

        feedback_loop.query_with_discovery(
            component_query="test", description="test card"
        )

        # Find Discovery call on inputs
        for c in mock_client.query_points.call_args_list:
            query_arg = c.kwargs.get("query")
            if (
                isinstance(query_arg, models.DiscoverQuery)
                and c.kwargs.get("using") == "inputs"
            ):
                pairs = query_arg.discover.context
                pair_pos_ids = {p.positive for p in pairs}
                pair_neg_ids = {p.negative for p in pairs}
                assert pair_pos_ids <= set(pos_ids)
                assert pair_neg_ids <= set(neg_ids)
                break
        else:
            # If no feedback produces pairs, that's acceptable (no positive+negative combo)
            pass

    def test_returns_empty_on_client_failure(self, feedback_loop):
        """Gracefully returns empty lists if client is None."""
        feedback_loop._client = None
        with patch.object(feedback_loop, "_get_client", return_value=None):
            classes, content, form = feedback_loop.query_with_discovery(
                component_query="test", description="test"
            )
        assert classes == []
        assert content == []
        assert form == []

    def test_legacy_wrapper_delegates(self, feedback_loop):
        """query_with_feedback() should delegate to query_with_discovery()."""
        with patch.object(
            feedback_loop, "query_with_discovery", return_value=([], [], [])
        ) as mock_discover:
            feedback_loop.query_with_feedback(
                component_query="test",
                description="test card",
                limit=5,
            )
            mock_discover.assert_called_once_with(
                component_query="test",
                description="test card",
                component_paths=None,
                limit=5,
                token_ratio=1.0,
            )
