"""Guard: a domain must never be served another domain's checkpoint.

Background — this test exists because of a real misconfiguration. MODEL_ARTIFACT_URI
mapped both "gchat" and "email" to a `best_model_unified.pt`, but the file published
under the email prefix was a byte-identical copy of the gchat model (its own
`domain_id` said "gchat"). Anything resolving the email domain silently loaded a
gchat-trained scorer, carrying gchat's pool vocabulary and component mapping.

Removing the bad entry alone would not have fixed it: `_resolve_checkpoint_path`
ended each lookup with a "first available" loop that returned *any* artifact
regardless of the domain asked for, so an email request fell straight back onto
the gchat model. These tests pin the corrected behaviour:

  1. An explicit domain never falls back to a different domain's artifact.
  2. Domain-less lookups keep the old first-available convenience.
  3. An exact domain match still wins.
  4. A checkpoint whose own domain_id disagrees with the request warns loudly.
"""

from __future__ import annotations

import json

import pytest

from adapters.module_wrapper.search_mixin._learned_model import (
    _resolve_checkpoint_path,
)


class _Resolver:
    """Minimal stand-in for the class `_resolve_checkpoint_path` binds to."""


def _resolve(domain=None):
    return _resolve_checkpoint_path.__func__(_Resolver, domain=domain)


@pytest.fixture
def gchat_only(tmp_path, monkeypatch):
    """A registry that knows about gchat but not email."""
    ckpt = tmp_path / "gchat.pt"
    ckpt.write_bytes(b"not-a-real-checkpoint")
    monkeypatch.setenv("LEARNED_SCORER_REGISTRY", json.dumps({"gchat": str(ckpt)}))
    monkeypatch.delenv("LEARNED_SCORER_CHECKPOINT", raising=False)
    return str(ckpt)


def test_exact_domain_match_resolves(gchat_only):
    assert _resolve(domain="gchat") == gchat_only


def test_missing_domain_does_not_borrow_another_domains_model(gchat_only):
    """The bug: email used to resolve to the gchat checkpoint."""
    assert _resolve(domain="email") != gchat_only


def test_domainless_lookup_still_uses_first_available(gchat_only):
    """Single-model deployments must keep working."""
    assert _resolve(domain=None) == gchat_only


def test_refusal_is_logged(gchat_only, caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        _resolve(domain="email")
    assert any(
        "refusing to fall back" in r.message.lower()
        or "refusing to fall back" in str(r.args).lower()
        for r in caplog.records
    ), f"expected a refusal warning, got: {[r.message for r in caplog.records]}"


def test_explicit_checkpoint_still_honoured(tmp_path, monkeypatch):
    """A single LEARNED_SCORER_CHECKPOINT is domain-agnostic by construction."""
    ckpt = tmp_path / "single.pt"
    ckpt.write_bytes(b"not-a-real-checkpoint")
    monkeypatch.delenv("LEARNED_SCORER_REGISTRY", raising=False)
    monkeypatch.setenv("LEARNED_SCORER_CHECKPOINT", str(ckpt))
    assert _resolve(domain="email") == str(ckpt)


def test_checkpoint_domain_mismatch_warns(tmp_path, monkeypatch, caplog):
    """A correctly-resolved path can still hold the wrong model."""
    import logging

    torch = pytest.importorskip("torch")

    ckpt_path = tmp_path / "mislabelled.pt"
    torch.save(
        {
            "model_state_dict": {},
            "model_type": "similarity_mw",
            "domain_id": "gchat",
            "input_dim": 9,
        },
        ckpt_path,
    )
    monkeypatch.delenv("LEARNED_SCORER_REGISTRY", raising=False)
    monkeypatch.setenv("LEARNED_SCORER_CHECKPOINT", str(ckpt_path))

    from adapters.module_wrapper.search_mixin._learned_model import _load_learned_model

    class _Loader:
        _learned_model = None
        _learned_feature_version = None
        _learned_model_domain = None
        _learned_model_type = None
        _resolve_checkpoint_path = _resolve_checkpoint_path

    with caplog.at_level(logging.WARNING):
        _load_learned_model.__func__(_Loader, domain="email")

    assert any("domain" in r.message.lower() for r in caplog.records), (
        f"expected a domain-mismatch warning, got: {[r.message for r in caplog.records]}"
    )
