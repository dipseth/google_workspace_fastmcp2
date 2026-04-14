"""Cross-domain generalization tests for the TRM pipeline.

Tests that the training data generation, model architecture, and domain config
system work correctly across multiple domains (gchat, email) without Qdrant.
"""

import pytest
import torch

from research.trm.h2.domain_config import (
    EMAIL_DOMAIN,
    GCHAT_DOMAIN,
    DomainConfig,
    get_domain,
    get_domain_or_default,
    list_domains,
    register_domain,
    resolve_domain,
)
from research.trm.h2.unified_trn import (
    CONTENT_DIM,
    DEFAULT_N_POOLS,
    FEATURE_NAMES_V5,
    STRUCTURAL_DIM,
    UnifiedTRN,
    get_domain_defaults,
)

# ── Domain Config Content Knowledge ──────────────────────────────────


class TestDomainContentKnowledge:
    """Verify content_affinity, content_templates, confusion_pairs for all domains."""

    @pytest.mark.parametrize("domain_id", ["gchat", "email"])
    def test_domain_has_content_knowledge(self, domain_id):
        domain = get_domain(domain_id)
        assert domain.has_content_knowledge, f"{domain_id} missing content knowledge"

    @pytest.mark.parametrize("domain_id", ["gchat", "email"])
    def test_content_affinity_entries_correspond_to_real_components(self, domain_id):
        """Content affinity keys with non-empty patterns should be pool-mapped components.

        Some components (like SelectionInput, TextInput) may have affinity entries
        for training data diversity but don't need pool mappings — they're just
        extra context, not routing targets. We only check non-structural types.
        """
        domain = get_domain(domain_id)
        all_components = set(domain.component_to_pool.keys())
        unmapped = []
        for comp_name, affinity in domain.content_affinity.items():
            if comp_name not in all_components and affinity.get("type") not in (
                "structural",
                "input",
                "temporal",
                "toggle",
            ):
                unmapped.append(comp_name)
        # Allow some unmapped — they're used for content generation, not pool routing
        assert len(unmapped) <= 5, (
            f"{domain_id}: too many unmapped affinity keys: {unmapped}"
        )

    @pytest.mark.parametrize("domain_id", ["gchat", "email"])
    def test_pool_mapped_components_have_affinity_or_templates(self, domain_id):
        """Components with pool mappings should ideally have content knowledge."""
        domain = get_domain(domain_id)
        # Check that at least some pool-mapped components have content
        mapped_with_content = sum(
            1
            for comp in domain.component_to_pool
            if comp in domain.content_affinity or comp in domain.content_templates
        )
        total_mapped = len(domain.component_to_pool)
        coverage = mapped_with_content / total_mapped if total_mapped > 0 else 0
        assert coverage > 0.3, (
            f"{domain_id}: only {coverage:.0%} of components have content knowledge"
        )

    @pytest.mark.parametrize("domain_id", ["gchat", "email"])
    def test_content_affinity_entries_have_patterns_and_type(self, domain_id):
        domain = get_domain(domain_id)
        for comp_name, affinity in domain.content_affinity.items():
            assert "patterns" in affinity, f"{comp_name} missing 'patterns'"
            assert "type" in affinity, f"{comp_name} missing 'type'"
            assert isinstance(affinity["patterns"], list)

    @pytest.mark.parametrize("domain_id", ["gchat", "email"])
    def test_content_templates_are_nonempty_lists(self, domain_id):
        domain = get_domain(domain_id)
        for comp_name, templates in domain.content_templates.items():
            assert isinstance(templates, list)
            assert len(templates) > 0, f"{comp_name} has empty templates list"

    @pytest.mark.parametrize("domain_id", ["gchat", "email"])
    def test_confusion_pairs_reference_valid_pools(self, domain_id):
        domain = get_domain(domain_id)
        valid_pools = set(domain.pool_vocab.keys())
        for text, wrong_pool in domain.confusion_pairs:
            assert wrong_pool in valid_pools, (
                f"{domain_id}: confusion pair pool '{wrong_pool}' not in pool_vocab"
            )

    def test_checkpoint_round_trip_preserves_content(self):
        """from_checkpoint should preserve content_affinity, templates, confusion_pairs."""
        domain = GCHAT_DOMAIN
        ckpt = {
            "domain_id": domain.domain_id,
            "pool_vocab": dict(domain.pool_vocab),
            "component_to_pool": dict(domain.component_to_pool),
            "specificity_order": list(domain.specificity_order),
            "rewrap_rules": dict(domain.rewrap_rules),
            "content_affinity": dict(domain.content_affinity),
            "content_templates": dict(domain.content_templates),
            "confusion_pairs": [list(p) for p in domain.confusion_pairs],
        }
        restored = DomainConfig.from_checkpoint(ckpt)
        assert restored is not None
        assert restored.domain_id == "gchat"
        assert len(restored.content_affinity) == len(domain.content_affinity)
        assert len(restored.content_templates) == len(domain.content_templates)
        assert len(restored.confusion_pairs) == len(domain.confusion_pairs)


# ── Domain Content Switching ─────────────────────────────────────────


class TestDomainContentSwitching:
    """Test that generate_training_data content loads correctly per domain."""

    def test_gchat_content_loads_by_default(self):
        from research.trm.h2 import generate_training_data as gtd

        # Module import triggers gchat init
        assert len(gtd.CONTENT_AFFINITY) > 0
        assert "ButtonList" in gtd.CONTENT_AFFINITY

    def test_switch_to_email_loads_email_content(self):
        from research.trm.h2 import generate_training_data as gtd

        gtd._init_domain_content("email")
        try:
            assert "HeroBlock" in gtd.CONTENT_AFFINITY
            assert "TextBlock" in gtd.CONTENT_TEXT_TEMPLATES
            assert "ButtonList" not in gtd.CONTENT_AFFINITY
            assert gtd._active_domain_config.domain_id == "email"
        finally:
            # Restore gchat default
            gtd._init_domain_content("gchat")

    def test_switch_back_to_gchat_restores(self):
        from research.trm.h2 import generate_training_data as gtd

        gtd._init_domain_content("email")
        gtd._init_domain_content("gchat")
        assert "ButtonList" in gtd.CONTENT_AFFINITY
        assert "HeroBlock" not in gtd.CONTENT_AFFINITY

    def test_content_text_generation_uses_active_domain(self):
        from research.trm.h2 import generate_training_data as gtd

        gtd._init_domain_content("email")
        try:
            text = gtd._generate_content_text_for_components(["HeroBlock", "TextBlock"])
            assert len(text) > 0, "Email content text should not be empty"
        finally:
            gtd._init_domain_content("gchat")

    def test_unknown_domain_falls_back_to_gchat(self):
        """Unknown domain falls back to gchat via get_domain_or_default."""
        from research.trm.h2 import generate_training_data as gtd

        gtd._init_domain_content("nonexistent_domain")
        try:
            # get_domain_or_default returns gchat for unknown domains
            assert gtd._active_domain_config.domain_id == "gchat"
            assert len(gtd.CONTENT_AFFINITY) > 0
        finally:
            gtd._init_domain_content("gchat")


# ── Cross-Domain Model Architecture ─────────────────────────────────


class TestCrossDomainModel:
    """Verify UnifiedTRN works correctly with different domain pool counts."""

    @pytest.mark.parametrize("domain_id", ["gchat", "email"])
    def test_model_with_domain_pool_count(self, domain_id):
        domain = get_domain(domain_id)
        model = UnifiedTRN(n_pools=domain.n_pools)
        assert model.n_pools == domain.n_pools

        # Search mode
        out = model(
            torch.randn(3, STRUCTURAL_DIM),
            torch.randn(3, CONTENT_DIM),
            mode="search",
        )
        assert out["form_score"].shape == (3, 1)
        assert out["content_score"].shape == (3, 1)

        # Build mode — pool_logits should match domain's pool count
        out = model(
            torch.zeros(3, STRUCTURAL_DIM),
            torch.randn(3, CONTENT_DIM),
            mode="build",
        )
        assert out["pool_logits"].shape == (3, domain.n_pools)

    def test_gchat_and_email_models_are_distinct(self):
        """Models for different domains have different pool head dimensions."""
        gchat_model = UnifiedTRN(n_pools=GCHAT_DOMAIN.n_pools)
        email_model = UnifiedTRN(n_pools=EMAIL_DOMAIN.n_pools)

        # Both should have same backbone but different pool heads
        assert gchat_model.structural_dim == email_model.structural_dim
        assert gchat_model.content_dim == email_model.content_dim
        # Pool head output differs if n_pools differs
        gchat_pool_out = gchat_model.pool_head[-1].out_features
        email_pool_out = email_model.pool_head[-1].out_features
        assert gchat_pool_out == GCHAT_DOMAIN.n_pools
        assert email_pool_out == EMAIL_DOMAIN.n_pools

    def test_get_domain_defaults_returns_correct_values(self):
        gchat = get_domain_defaults("gchat")
        email = get_domain_defaults("email")
        assert gchat["n_pools"] == 5
        assert email["n_pools"] == 5  # Both happen to be 5 now
        assert "ButtonList" in gchat["component_to_pool"]
        assert "HeroBlock" in email["component_to_pool"]

    def test_model_handles_zero_structural_features(self):
        """Build mode uses zeros for structural — must not produce NaN."""
        for domain_id in ["gchat", "email"]:
            domain = get_domain(domain_id)
            model = UnifiedTRN(n_pools=domain.n_pools)
            model.eval()
            out = model(
                torch.zeros(5, STRUCTURAL_DIM),
                torch.randn(5, CONTENT_DIM),
                mode="build",
            )
            assert not torch.isnan(out["pool_logits"]).any()
            assert not torch.isinf(out["pool_logits"]).any()


# ── Domain Checkpoint Matching ───────────────────────────────────────


class TestCheckpointDomainMatching:
    """Test that checkpoints carry domain metadata and resolve correctly."""

    def _make_checkpoint(self, domain: DomainConfig) -> dict:
        """Create a minimal checkpoint dict with domain metadata."""
        model = UnifiedTRN(n_pools=domain.n_pools)
        return {
            "model_state_dict": model.state_dict(),
            "model_type": "unified_trn",
            "structural_dim": STRUCTURAL_DIM,
            "content_dim": CONTENT_DIM,
            "hidden": 64,
            "n_pools": domain.n_pools,
            "dropout": 0.15,
            "feature_version": 5,
            "domain_id": domain.domain_id,
            "pool_vocab": dict(domain.pool_vocab),
            "component_to_pool": dict(domain.component_to_pool),
            "specificity_order": list(domain.specificity_order),
            "rewrap_rules": dict(domain.rewrap_rules),
            "content_affinity": dict(domain.content_affinity),
            "content_templates": dict(domain.content_templates),
            "confusion_pairs": [list(p) for p in domain.confusion_pairs],
        }

    def test_gchat_checkpoint_resolves_to_gchat(self):
        ckpt = self._make_checkpoint(GCHAT_DOMAIN)
        resolved = resolve_domain(checkpoint=ckpt)
        assert resolved.domain_id == "gchat"
        assert resolved.n_pools == GCHAT_DOMAIN.n_pools

    def test_email_checkpoint_resolves_to_email(self):
        ckpt = self._make_checkpoint(EMAIL_DOMAIN)
        resolved = resolve_domain(checkpoint=ckpt)
        assert resolved.domain_id == "email"
        assert resolved.n_pools == EMAIL_DOMAIN.n_pools
        assert "HeroBlock" in resolved.component_to_pool

    def test_checkpoint_domain_overrides_explicit(self):
        """Checkpoint metadata should take priority over --domain arg."""
        ckpt = self._make_checkpoint(EMAIL_DOMAIN)
        resolved = resolve_domain(checkpoint=ckpt, domain_id="gchat")
        assert resolved.domain_id == "email"

    def test_checkpoint_preserves_content_knowledge(self):
        ckpt = self._make_checkpoint(EMAIL_DOMAIN)
        restored = DomainConfig.from_checkpoint(ckpt)
        assert restored.has_content_knowledge
        assert "HeroBlock" in restored.content_affinity
        assert "TextBlock" in restored.content_templates

    def test_model_loads_with_checkpoint_domain(self):
        """Model constructed from checkpoint metadata should have correct n_pools."""
        for domain in [GCHAT_DOMAIN, EMAIL_DOMAIN]:
            ckpt = self._make_checkpoint(domain)
            restored = DomainConfig.from_checkpoint(ckpt)
            model = UnifiedTRN(
                structural_dim=ckpt["structural_dim"],
                content_dim=ckpt["content_dim"],
                hidden=ckpt["hidden"],
                n_pools=restored.n_pools,
            )
            model.load_state_dict(ckpt["model_state_dict"])
            assert model.n_pools == domain.n_pools


# ── Feature Dimension Consistency ────────────────────────────────────


class TestFeatureDimensionConsistency:
    """Verify feature dimensions are consistent across the system."""

    def test_v5_features_have_17_dimensions(self):
        assert len(FEATURE_NAMES_V5) == 17

    def test_structural_dim_matches_features(self):
        assert STRUCTURAL_DIM == len(FEATURE_NAMES_V5)

    def test_content_dim_is_384(self):
        assert CONTENT_DIM == 384

    def test_default_n_pools_is_5(self):
        assert DEFAULT_N_POOLS == 5

    def test_model_structural_input_matches_features(self):
        model = UnifiedTRN()
        # First layer of structural_enc should accept STRUCTURAL_DIM
        first_layer = model.structural_enc[0]
        assert first_layer.in_features == STRUCTURAL_DIM

    def test_model_content_input_matches_dim(self):
        model = UnifiedTRN()
        first_layer = model.content_enc[0]
        assert first_layer.in_features == CONTENT_DIM

    @pytest.mark.parametrize("domain_id", ["gchat", "email"])
    def test_domain_pool_count_matches_model_output(self, domain_id):
        """Pool head output dimension must match domain's pool count."""
        domain = get_domain(domain_id)
        model = UnifiedTRN(n_pools=domain.n_pools)
        pool_out_dim = model.pool_head[-1].out_features
        assert pool_out_dim == domain.n_pools


# ── Slot Training Data Domain Integration ────────────────────────────


class TestSlotTrainingDomainIntegration:
    """Test generate_slot_training_data domain-aware initialization."""

    def test_slot_domain_init_gchat(self):
        from research.trm.h2.generate_slot_training_data import (
            COMPONENT_TO_POOL,
            POOL_VOCAB,
            _init_slot_domain,
        )

        _init_slot_domain("gchat")
        assert "buttons" in POOL_VOCAB
        assert "Button" in COMPONENT_TO_POOL

    def test_slot_domain_init_email(self):
        from research.trm.h2 import generate_slot_training_data as gstd

        gstd._init_slot_domain("email")
        try:
            # Access via module to get updated globals
            assert "content" in gstd.POOL_VOCAB
            assert "HeroBlock" in gstd.COMPONENT_TO_POOL
            assert "Button" not in gstd.COMPONENT_TO_POOL
        finally:
            gstd._init_slot_domain("gchat")


# ── Email Domain Specifics ───────────────────────────────────────────


class TestEmailDomainSpecifics:
    """Validate EMAIL_DOMAIN matches the real MJML wrapper components."""

    EXPECTED_MJML_COMPONENTS = {
        "EmailSpec",
        "HeroBlock",
        "TextBlock",
        "ButtonBlock",
        "ImageBlock",
        "ColumnsBlock",
        "Column",
        "SpacerBlock",
        "DividerBlock",
        "HeaderBlock",
        "FooterBlock",
        "SocialBlock",
        "TableBlock",
        "AccordionBlock",
        "CarouselBlock",
    }

    def test_all_mjml_components_mapped(self):
        """Every known MJML component should be in component_to_pool."""
        mapped = set(EMAIL_DOMAIN.component_to_pool.keys())
        missing = self.EXPECTED_MJML_COMPONENTS - mapped
        assert not missing, f"Missing MJML components: {missing}"

    def test_no_phantom_components(self):
        """No components in the mapping that don't exist in MJML."""
        mapped = set(EMAIL_DOMAIN.component_to_pool.keys())
        extra = mapped - self.EXPECTED_MJML_COMPONENTS
        assert not extra, f"Phantom components: {extra}"

    def test_pool_categories_match_dsl_categories(self):
        """Pool structure should mirror DSL categories from email_wrapper_setup.py."""
        expected_pools = {"content", "layout", "chrome", "structure", "interactive"}
        actual_pools = set(EMAIL_DOMAIN.pool_vocab.keys())
        assert actual_pools == expected_pools

    def test_content_pool_has_main_blocks(self):
        """Core content blocks should be in the 'content' pool."""
        for comp in ["HeroBlock", "TextBlock", "ButtonBlock", "ImageBlock"]:
            assert EMAIL_DOMAIN.component_to_pool[comp] == "content"

    def test_layout_pool_has_columns(self):
        assert EMAIL_DOMAIN.component_to_pool["ColumnsBlock"] == "layout"
        assert EMAIL_DOMAIN.component_to_pool["Column"] == "layout"

    def test_chrome_pool_has_header_footer(self):
        assert EMAIL_DOMAIN.component_to_pool["HeaderBlock"] == "chrome"
        assert EMAIL_DOMAIN.component_to_pool["FooterBlock"] == "chrome"
        assert EMAIL_DOMAIN.component_to_pool["SocialBlock"] == "chrome"

    def test_interactive_pool_has_accordion_carousel(self):
        assert EMAIL_DOMAIN.component_to_pool["AccordionBlock"] == "interactive"
        assert EMAIL_DOMAIN.component_to_pool["CarouselBlock"] == "interactive"
