"""search_hybrid_learned's domain guard keys on domain_id, not domain_label."""

from types import SimpleNamespace

import pytest

pytest.importorskip("torch")

from adapters.module_wrapper.search_mixin._hybrid_learned import (  # noqa: E402
    search_hybrid_learned,
)


class _Fake:
    _learned_model_domain = "gchat"

    def __init__(self, domain_id):
        self.domain_config = SimpleNamespace(
            domain_label="Google Chat Cards", domain_id=domain_id
        )
        self.fell_back = False
        self.loaded_domain = "unset"

    def _require_qdrant(self, *a, **k):
        return True

    def _load_learned_model(self, domain=None):
        self.loaded_domain = domain
        return object()

    def search_hybrid_multidim(self, **kw):
        self.fell_back = True
        return [], [], []

    def _embed_with_colbert(self, *a, **k):
        return None  # stop right after the guard

    def _embed_with_minilm(self, *a, **k):
        return None


def test_matching_domain_id_uses_model():
    w = _Fake("gchat")
    search_hybrid_learned(w, "a card with a button")
    assert w.loaded_domain == "gchat"
    assert not w.fell_back


def test_other_domain_falls_back():
    w = _Fake("email")
    search_hybrid_learned(w, "a card with a button")
    assert w.fell_back
