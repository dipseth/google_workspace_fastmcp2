"""_query_grouped_candidates: fused query + client-side per-type caps."""

from types import SimpleNamespace

from adapters.module_wrapper.search_mixin._hybrid_helpers import (
    _query_grouped_candidates,
)


def _pt(name, typ):
    return SimpleNamespace(id=name, payload={"name": name, "type": typ}, vector=None)


class _Client:
    def __init__(self, points):
        self.points = points
        self.calls = []

    def query_points(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(points=self.points)

    def retrieve(self, ids, **kw):
        return [SimpleNamespace(id=i, vector={"v": i}) for i in ids]


def _wrapper(points, n_prefetch=3):
    client = _Client(points)
    return SimpleNamespace(
        client=client,
        collection_name="c",
        _build_prefetch_list=lambda *a, **k: ["pf"] * n_prefetch,
    )


def test_caps_each_type_and_keeps_fused_order():
    fused = [
        _pt("A", "class"),
        _pt("p1", "instance_pattern"),
        _pt("B", "class"),
        _pt("C", "class"),
        _pt("p2", "instance_pattern"),
    ]
    w = _wrapper(fused)
    out = _query_grouped_candidates(w, None, None, 20, group_size=2)
    # Types ordered by best hit; within a type, fused order; capped at group_size.
    assert [p.payload["name"] for p in out] == ["A", "B", "p1", "p2"]
    # Limit covers every prefetched point so no type is crowded out.
    assert w.client.calls[0]["limit"] == 60
    # Vectors are fetched afterwards, only for kept points.
    assert w.client.calls[0]["with_vectors"] is False
    assert [p.vector for p in out] == [{"v": n} for n in ("A", "B", "p1", "p2")]


def test_at_most_five_types():
    fused = [_pt(f"x{i}", f"t{i}") for i in range(7)]
    out = _query_grouped_candidates(_wrapper(fused), None, None, 20, group_size=10)
    assert [p.payload["type"] for p in out] == ["t0", "t1", "t2", "t3", "t4"]


def test_categorize_dedupes_same_name_classes():
    from adapters.module_wrapper.search_mixin._hybrid_helpers import (
        _categorize_scored_results,
    )

    def pt(name, path):
        return SimpleNamespace(
            id=path, payload={"name": name, "type": "class", "full_path": path}
        )

    scored = [
        (0.9, 0, 0, 0, 0, pt("DividerStyle", "a.Card.DividerStyle")),
        (0.8, 0, 0, 0, 0, pt("DividerStyle", "a.CardWithId.DividerStyle")),
        (0.7, 0, 0, 0, 0, pt("Divider", "a.Divider")),
    ]
    classes, _, _ = _categorize_scored_results(None, scored, limit=10)
    assert [c["name"] for c in classes] == ["DividerStyle", "Divider"]
    assert classes[0]["full_path"] == "a.Card.DividerStyle"
    assert classes[0]["alt_full_paths"] == ["a.CardWithId.DividerStyle"]
