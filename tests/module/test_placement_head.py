"""Learned placement head on the domain checkpoint takes precedence over prototypes."""

import pytest

torch = pytest.importorskip("torch")

from gchat.card_builder import slot_assignment as sa  # noqa: E402


def test_placement_shape_features_are_position_free():
    f = sa.placement_shape_features("<b>Hi</b> see https://x.y")
    assert len(f) == 4 and all(0.0 <= v <= 1.0 for v in f)


def test_placement_item_text_falls_back_to_image_alt():
    assert sa.placement_item_text({"src": "https://i/x.png", "alt": "Logo"}) == "Logo"
    assert sa.placement_item_text({"text": "Body"}) == "Body"


def test_head_scores_requested_components(monkeypatch):
    blocks = ["ImageBlock", "TextBlock"]
    dim = 384 + 4
    # Head that prefers ImageBlock for bare URLs (last shape feature) only.
    w1 = torch.zeros(1, dim)
    w1[0, dim - 1] = 10.0
    head = {
        "blocks": blocks,
        "w1": w1,
        "b1": torch.zeros(1),
        "w2": torch.tensor([[1.0], [-1.0]]),
        "b2": torch.zeros(2),
    }
    monkeypatch.setitem(
        sa._domain_model_cache, "email", (None, {"placement_head": head})
    )
    monkeypatch.setattr(
        sa, "_embed_texts", lambda texts, w: torch.ones(len(texts), 384)
    )
    m = sa._placement_head_scores(
        [{"src": "https://i/x.png"}, {"text": "hello"}],
        ["TextBlock", "ImageBlock"],
        "email",
        None,
    )
    assert m[0][1] > m[0][0]  # URL item -> ImageBlock
    assert m[1][0] >= m[1][1]  # text item -> TextBlock (ties allowed)
    # Unknown (content-less) component is scored out, not fatal.
    m2 = sa._placement_head_scores(
        [{"text": "hello"}], ["TextBlock", "DividerBlock"], "email", None
    )
    assert m2[0][1] == -1e9


def test_no_head_or_unknown_component_returns_none(monkeypatch):
    monkeypatch.setitem(sa._domain_model_cache, "email", (None, {}))
    assert (
        sa._placement_head_scores([{"text": "x"}], ["TextBlock"], "email", None) is None
    )
    head = {"blocks": ["TextBlock"], "w1": None, "b1": None, "w2": None, "b2": None}
    monkeypatch.setitem(
        sa._domain_model_cache, "email", (None, {"placement_head": head})
    )
    assert (
        sa._placement_head_scores([{"text": "x"}], ["HeroBlock"], "email", None) is None
    )
