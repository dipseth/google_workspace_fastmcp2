"""Unit tests for the Anthropic prompt cache keepalive engine."""

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from middleware.cache_keepalive import (
    GCHAT_EXPLORATION_PROMPTS,
    CacheKeepaliveEngine,
    KeepaliveModuleConfig,
    register_default_modules,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass
class _FakeSettings:
    """Minimal settings stub for keepalive tests."""

    litellm_model: str = "anthropic/claude-sonnet-4-6"
    litellm_api_key: str = "test-key"
    litellm_api_base: str = ""
    cache_keepalive_enabled: bool = True
    cache_keepalive_interval_seconds: int = 2700
    cache_keepalive_jitter_seconds: int = 300
    cache_keepalive_modules: str = "gchat,email"
    cache_keepalive_mode: str = "explore"
    cache_keepalive_max_tokens: int = 100
    cache_keepalive_index_results: bool = False
    sampling_input_token_rate: float = 0.000003
    sampling_output_token_rate: float = 0.000015
    sampling_cost_persistence_file: str = ""


@pytest.fixture
def settings():
    return _FakeSettings()


@pytest.fixture
def engine(settings):
    return CacheKeepaliveEngine(settings=settings)


def _make_litellm_response(
    cached_tokens: int = 500, prompt_tokens: int = 1000, completion_tokens: int = 50
):
    """Build a fake litellm response with usage stats."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="OK — valid DSL pattern generated.")
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            prompt_tokens_details=SimpleNamespace(cached_tokens=cached_tokens),
        ),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestKeepaliveModuleConfig:
    def test_defaults(self):
        cfg = KeepaliveModuleConfig(
            module_name="test",
            get_system_prompt_fn=lambda: "prompt",
        )
        assert cfg.total_keepalive_calls == 0
        assert cfg.total_cached_tokens == 0
        assert cfg.total_cost_usd == 0.0
        assert cfg.last_keepalive_at == 0.0


class TestRegisterDefaultModules:
    def test_registers_known_modules(self, engine, settings):
        register_default_modules(engine, settings)
        assert "gchat" in engine._modules
        assert "email" in engine._modules
        assert len(engine._modules) == 2

    def test_unknown_module_skipped(self, engine, settings):
        settings.cache_keepalive_modules = "gchat,unknown_service"
        register_default_modules(engine, settings)
        assert "gchat" in engine._modules
        assert "unknown_service" not in engine._modules

    def test_empty_modules(self, engine, settings):
        settings.cache_keepalive_modules = ""
        register_default_modules(engine, settings)
        assert len(engine._modules) == 0

    def test_exploration_prompts_assigned(self, engine, settings):
        register_default_modules(engine, settings)
        gchat_mod = engine._modules["gchat"]
        assert len(gchat_mod.exploration_prompts) > 0
        assert gchat_mod.exploration_prompts == GCHAT_EXPLORATION_PROMPTS


class TestCacheKeepaliveEngine:
    def test_register_module(self, engine):
        cfg = KeepaliveModuleConfig(
            module_name="test",
            get_system_prompt_fn=lambda: "test prompt",
            exploration_prompts=["Generate something"],
            dsl_type_label="test",
        )
        engine.register_module(cfg)
        assert "test" in engine._modules

    @pytest.mark.asyncio
    async def test_send_keepalive_explore_mode(self, engine, settings):
        """Verify explore mode sends varied prompts with cache control."""
        cfg = KeepaliveModuleConfig(
            module_name="gchat",
            get_system_prompt_fn=lambda: "You are a DSL expert.",
            exploration_prompts=["Prompt A", "Prompt B", "Prompt C"],
            dsl_type_label="card",
        )
        engine.register_module(cfg)

        fake_response = _make_litellm_response(cached_tokens=800)

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=fake_response) as mock_acompletion:

            result = await engine._send_keepalive(cfg)

            # Verify litellm was called with correct kwargs
            call_kwargs = mock_acompletion.call_args[1]
            assert call_kwargs["model"] == "anthropic/claude-sonnet-4-6"
            assert call_kwargs["max_tokens"] == 100
            assert call_kwargs["temperature"] == 0.7
            assert call_kwargs["cache_control_injection_points"] == [
                {"location": "message", "role": "system"}
            ]
            assert call_kwargs["api_key"] == "test-key"

            # Verify messages structure
            messages = call_kwargs["messages"]
            assert messages[0]["role"] == "system"
            assert messages[0]["content"] == "You are a DSL expert."
            assert messages[1]["role"] == "user"
            assert messages[1]["content"] == "Prompt A"  # First in rotation

            # Verify result
            assert result["cached_tokens"] == 800
            assert result["input_tokens"] == 1000
            assert result["output_tokens"] == 50

    @pytest.mark.asyncio
    async def test_send_keepalive_ping_mode(self, engine, settings):
        """Verify ping mode sends minimal ack request."""
        settings.cache_keepalive_mode = "ping"
        cfg = KeepaliveModuleConfig(
            module_name="email",
            get_system_prompt_fn=lambda: "Email DSL reference.",
            exploration_prompts=["Explore!"],
            dsl_type_label="email",
        )
        engine.register_module(cfg)

        fake_response = _make_litellm_response(cached_tokens=600)

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=fake_response) as mock_acompletion:

            await engine._send_keepalive(cfg)

            call_kwargs = mock_acompletion.call_args[1]
            assert call_kwargs["temperature"] == 0.0
            assert "Acknowledge" in call_kwargs["messages"][1]["content"]

    @pytest.mark.asyncio
    async def test_exploration_prompt_rotation(self, engine, settings):
        """Verify prompts rotate through the pool."""
        prompts = ["P1", "P2", "P3"]
        cfg = KeepaliveModuleConfig(
            module_name="gchat",
            get_system_prompt_fn=lambda: "DSL ref",
            exploration_prompts=prompts,
            dsl_type_label="card",
        )
        engine.register_module(cfg)

        fake_response = _make_litellm_response()
        sent_prompts = []

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=fake_response) as mock_acompletion:

            for _ in range(5):
                await engine._send_keepalive(cfg)
                call_kwargs = mock_acompletion.call_args[1]
                sent_prompts.append(call_kwargs["messages"][1]["content"])

        assert sent_prompts == ["P1", "P2", "P3", "P1", "P2"]

    @pytest.mark.asyncio
    async def test_stats_accumulate(self, engine, settings):
        """Verify stats accumulate across multiple calls."""
        cfg = KeepaliveModuleConfig(
            module_name="gchat",
            get_system_prompt_fn=lambda: "DSL ref",
            exploration_prompts=["Explore"],
            dsl_type_label="card",
        )
        engine.register_module(cfg)

        fake_response = _make_litellm_response(cached_tokens=500)

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=fake_response) as mock_acompletion:

            await engine._send_keepalive(cfg)
            await engine._send_keepalive(cfg)

        stats = engine.get_stats()
        assert stats["total_calls"] == 2
        assert stats["total_cached_tokens"] == 1000
        assert stats["modules"]["gchat"]["total_calls"] == 2
        assert cfg.last_keepalive_at > 0

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self, engine, settings):
        """Verify start creates task and stop cancels it."""
        cfg = KeepaliveModuleConfig(
            module_name="gchat",
            get_system_prompt_fn=lambda: "DSL ref",
            exploration_prompts=["Explore"],
            dsl_type_label="card",
        )
        engine.register_module(cfg)

        with patch(
            "litellm.acompletion",
            new_callable=AsyncMock,
            return_value=_make_litellm_response(),
        ):
            await engine.start()
            assert engine._task is not None
            assert not engine._task.done()

            await engine.stop()
            assert engine._task is None

    def test_get_stats_empty(self, engine):
        stats = engine.get_stats()
        assert stats["total_calls"] == 0
        assert stats["total_cached_tokens"] == 0
        assert stats["total_cost_usd"] == 0.0
        assert stats["modules"] == {}

    @pytest.mark.asyncio
    async def test_extract_text(self, engine):
        response = _make_litellm_response()
        text = engine._extract_text(response)
        assert "valid DSL" in text

    @pytest.mark.asyncio
    async def test_extract_text_empty_response(self, engine):
        response = SimpleNamespace(choices=[])
        text = engine._extract_text(response)
        assert text == ""

    @pytest.mark.asyncio
    async def test_cost_calculation(self, engine, settings):
        """Verify cached tokens get 90% discount in cost calc."""
        cfg = KeepaliveModuleConfig(
            module_name="gchat",
            get_system_prompt_fn=lambda: "DSL ref",
            exploration_prompts=["Explore"],
            dsl_type_label="card",
        )
        engine.register_module(cfg)

        # 1000 prompt tokens, 800 cached, 50 output
        fake_response = _make_litellm_response(
            cached_tokens=800, prompt_tokens=1000, completion_tokens=50
        )

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=fake_response) as mock_acompletion:
            result = await engine._send_keepalive(cfg)

        # Expected cost:
        # uncached_input = 1000 - 800 = 200 tokens @ $0.000003 = $0.0006
        # cached_input = 800 tokens @ $0.000003 * 0.1 = $0.00024
        # output = 50 tokens @ $0.000015 = $0.00075
        expected = 200 * 0.000003 + 800 * 0.000003 * 0.1 + 50 * 0.000015
        assert abs(result["cost_usd"] - expected) < 1e-9

    def test_get_stats_includes_validation_costs(self, engine):
        """Verify get_stats includes validation agent cost fields."""
        engine._validation_total_cost_usd = 0.005
        engine._validation_total_calls = 3
        stats = engine.get_stats()
        assert stats["validation_total_cost_usd"] == 0.005
        assert stats["validation_total_calls"] == 3

    @pytest.mark.asyncio
    async def test_jitter_applied_to_interval(self, engine, settings):
        """Verify jittered sleep stays within [interval-jitter, interval+jitter]."""
        import random

        interval = settings.cache_keepalive_interval_seconds
        jitter = settings.cache_keepalive_jitter_seconds
        # Simulate what the loop does
        samples = [
            max(60, interval + random.uniform(-jitter, jitter))
            for _ in range(100)
        ]
        for s in samples:
            assert s >= max(60, interval - jitter)
            assert s <= interval + jitter

    @pytest.mark.asyncio
    async def test_persistence_save_load_cycle(self, settings, tmp_path):
        """Verify stats survive a save/load cycle."""
        cost_file = tmp_path / "costs.json"
        settings.sampling_cost_persistence_file = str(cost_file)

        engine1 = CacheKeepaliveEngine(settings=settings)
        cfg = KeepaliveModuleConfig(
            module_name="gchat",
            get_system_prompt_fn=lambda: "DSL ref",
            exploration_prompts=["Explore"],
            dsl_type_label="card",
        )
        engine1.register_module(cfg)

        # Simulate some stats
        cfg.total_keepalive_calls = 5
        cfg.total_cost_usd = 0.01
        cfg.total_savings_usd = 0.05
        engine1._validation_total_cost_usd = 0.002
        engine1._validation_total_calls = 2

        engine1._save_persisted_stats()
        assert cost_file.exists()

        # New engine loads the same file
        engine2 = CacheKeepaliveEngine(settings=settings)
        cfg2 = KeepaliveModuleConfig(
            module_name="gchat",
            get_system_prompt_fn=lambda: "DSL ref",
        )
        engine2.register_module(cfg2)
        engine2._load_persisted_stats()

        assert cfg2.total_keepalive_calls == 5
        assert cfg2.total_cost_usd == 0.01
        assert cfg2.total_savings_usd == 0.05
        assert engine2._validation_total_cost_usd == 0.002
        assert engine2._validation_total_calls == 2

    @pytest.mark.asyncio
    async def test_exploration_output_logged(self, engine, settings, caplog):
        """Verify exploration outputs are always logged."""
        import logging

        cfg = KeepaliveModuleConfig(
            module_name="gchat",
            get_system_prompt_fn=lambda: "DSL ref",
            exploration_prompts=["Explore"],
            dsl_type_label="card",
        )
        engine.register_module(cfg)

        fake_response = _make_litellm_response()

        with patch(
            "litellm.acompletion",
            new_callable=AsyncMock,
            return_value=fake_response,
        ):
            with caplog.at_level(logging.INFO):
                await engine._send_keepalive(cfg)

        assert any("exploration output" in r.message for r in caplog.records)


class TestExecuteKeepaliveModule:
    def test_register_execute_module(self, engine, settings):
        """Verify execute module registers when included in modules list."""
        settings.cache_keepalive_modules = "gchat,email,execute"
        register_default_modules(engine, settings)
        assert "execute" in engine._modules
        assert len(engine._modules) == 3

    def test_execute_system_prompt_exceeds_cache_minimum(self):
        """Verify the execute system prompt exceeds Anthropic's 1024-token min.

        Rough estimate: 4 chars per token, so need >4096 chars.
        """
        from middleware.cache_keepalive import _build_execute_system_prompt

        prompt = _build_execute_system_prompt()
        assert len(prompt) > 4096, (
            f"Execute system prompt too short for caching: {len(prompt)} chars"
        )

    def test_execute_system_prompt_contains_key_sections(self):
        """Verify the prompt includes sandbox ref, tool catalog, and conventions."""
        from middleware.cache_keepalive import _build_execute_system_prompt

        prompt = _build_execute_system_prompt()
        assert "argument correction agent" in prompt
        assert "search_gmail_messages" in prompt
        assert "page_size" in prompt
        assert "Parameter Naming Conventions" in prompt
        assert "Common Validation Errors" in prompt

    def test_execute_exploration_prompts_exist(self):
        """Verify exploration prompts cover varied error scenarios."""
        from middleware.cache_keepalive import EXECUTE_EXPLORATION_PROMPTS

        assert len(EXECUTE_EXPLORATION_PROMPTS) == 10
        # Each prompt should mention a tool and an error
        for prompt in EXECUTE_EXPLORATION_PROMPTS:
            assert "Tool:" in prompt
            assert "Unexpected keyword argument" in prompt
