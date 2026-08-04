"""Tests for the slot-assignment pinning policy.

`reassign_supply_map` historically pinned any item whose *source* pool still had
unmet demand, without consulting the model. Because the supply_map is normally
built to match DSL demand, that guard was active almost always and the model was
consulted almost never -- misrouted content stayed misrouted.

SLOT_PIN_MODE=confidence lets the model release an item for rerouting when it
prefers a different, still-demanded pool. Default stays "always" (legacy).
"""

from __future__ import annotations

import pytest

from adapters.domain_config import GCHAT_DOMAIN
from gchat.card_builder.slot_assignment import _pin_policy, _should_release

VOCAB = GCHAT_DOMAIN.pool_vocab


@pytest.fixture(autouse=True)
def _clear_pin_env(monkeypatch):
    monkeypatch.delenv("SLOT_PIN_MODE", raising=False)
    monkeypatch.delenv("SLOT_REROUTE_CONFIDENCE", raising=False)


# ── Policy resolution ────────────────────────────────────────────────


def test_default_policy_is_legacy_always():
    mode, threshold = _pin_policy()
    assert mode == "always"
    assert threshold == pytest.approx(0.70)


def test_confidence_mode_opt_in(monkeypatch):
    monkeypatch.setenv("SLOT_PIN_MODE", "confidence")
    monkeypatch.setenv("SLOT_REROUTE_CONFIDENCE", "0.85")
    mode, threshold = _pin_policy()
    assert mode == "confidence"
    assert threshold == pytest.approx(0.85)


@pytest.mark.parametrize("bad", ["", "yolo", "CONFIDENCE_PLUS"])
def test_unknown_mode_falls_back_to_always(monkeypatch, bad):
    monkeypatch.setenv("SLOT_PIN_MODE", bad)
    assert _pin_policy()[0] == "always"


def test_mode_is_case_and_space_insensitive(monkeypatch):
    monkeypatch.setenv("SLOT_PIN_MODE", "  Confidence  ")
    assert _pin_policy()[0] == "confidence"


def test_invalid_threshold_falls_back(monkeypatch):
    monkeypatch.setenv("SLOT_REROUTE_CONFIDENCE", "not-a-number")
    assert _pin_policy()[1] == pytest.approx(0.70)


@pytest.mark.parametrize("raw,expected", [("-1", 0.0), ("5", 1.0)])
def test_threshold_is_clamped(monkeypatch, raw, expected):
    monkeypatch.setenv("SLOT_REROUTE_CONFIDENCE", raw)
    assert _pin_policy()[1] == pytest.approx(expected)


# ── Release decision ─────────────────────────────────────────────────


def _logits(**pool_weights):
    """Build a logit vector over the gchat pools."""
    torch = pytest.importorskip("torch")
    vec = [0.0] * len(VOCAB)
    for pool, weight in pool_weights.items():
        vec[VOCAB[pool]] = weight
    return torch.tensor(vec)


def test_releases_when_model_confidently_prefers_a_demanded_pool():
    scores = _logits(buttons=12.0)
    assert _should_release(scores, "content_texts", {"buttons": 1}, VOCAB, 0.7)


def test_pins_when_model_agrees_with_current_pool():
    scores = _logits(content_texts=12.0)
    assert not _should_release(scores, "content_texts", {"buttons": 1}, VOCAB, 0.7)


def test_pins_when_preferred_pool_has_no_unmet_demand():
    """Anti-starvation: never pull an item out toward a pool with no free slot."""
    scores = _logits(buttons=12.0)
    assert not _should_release(scores, "content_texts", {"buttons": 0}, VOCAB, 0.7)
    assert not _should_release(scores, "content_texts", {}, VOCAB, 0.7)


def test_pins_when_confidence_below_threshold():
    scores = _logits(buttons=0.15)  # near-uniform -> low max prob
    assert not _should_release(scores, "content_texts", {"buttons": 1}, VOCAB, 0.7)


def test_pins_when_scores_missing():
    assert not _should_release(None, "content_texts", {"buttons": 1}, VOCAB, 0.7)


def test_pins_when_scoring_raises():
    """A malformed score tensor must never break card building."""

    class Exploding:
        def argmax(self):
            raise RuntimeError("boom")

    assert not _should_release(Exploding(), "content_texts", {"buttons": 1}, VOCAB, 0.7)


# ── End-to-end through reassign_supply_map ───────────────────────────


def _misrouted_supply_map():
    return {
        "content_texts": ["Deploy to Production", "All systems operational."],
        "buttons": ["The deployment pipeline completed without errors.", "View Logs"],
        "chips": [],
        "grid_items": [],
        "carousel_cards": [],
    }


def _texts(pool):
    return [x if isinstance(x, str) else x.get("text") for x in pool]


def _reassign():
    from gchat.card_builder.slot_assignment import _load_slot_model

    pytest.importorskip("torch")
    if _load_slot_model() is None:
        pytest.skip("no slot-assignment checkpoint available in this environment")

    from gchat.card_builder.slot_assignment import reassign_supply_map

    supply = _misrouted_supply_map()
    out = reassign_supply_map(
        supply,
        {"ButtonList": 2, "TextParagraph": 2},
        domain_config=GCHAT_DOMAIN,
    )
    return supply, out


def test_always_mode_leaves_misrouted_content_in_place():
    """Documents the legacy behaviour: counts match demand, so nothing moves."""
    supply, out = _reassign()
    assert out == supply


def test_confidence_mode_reroutes_misplaced_items(monkeypatch):
    monkeypatch.setenv("SLOT_PIN_MODE", "confidence")
    supply, out = _reassign()

    assert out != supply
    assert "Deploy to Production" in _texts(out["buttons"])
    assert "View Logs" in _texts(out["buttons"])
    assert "All systems operational." in _texts(out["content_texts"])
    assert "The deployment pipeline completed without errors." in _texts(
        out["content_texts"]
    )


def test_confidence_mode_preserves_pool_counts(monkeypatch):
    """Rerouting must not starve a pool the DSL asked for."""
    monkeypatch.setenv("SLOT_PIN_MODE", "confidence")
    supply, out = _reassign()

    for pool in ("buttons", "content_texts"):
        assert len(out[pool]) == len(supply[pool]) == 2

    total_before = sum(len(v) for v in supply.values())
    total_after = sum(len(v) for v in out.values())
    assert total_after == total_before


def test_unreachable_threshold_pins_everything(monkeypatch):
    """pool_head probs top out around 0.96, so 0.999 must release nothing."""
    monkeypatch.setenv("SLOT_PIN_MODE", "confidence")
    monkeypatch.setenv("SLOT_REROUTE_CONFIDENCE", "0.999")
    supply, out = _reassign()
    assert out == supply
