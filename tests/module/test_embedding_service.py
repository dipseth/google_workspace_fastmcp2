"""Tests for the centralized EmbeddingService singleton."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from config.embedding_service import (
    _SLOT_DEFAULTS,
    EmbeddingService,
    close_embedding_service,
    get_embedding_service,
)


class TestEmbeddingServiceInit:
    """Test initialization and config loading."""

    def test_singleton_returns_same_instance(self):
        svc1 = get_embedding_service()
        svc2 = get_embedding_service()
        assert svc1 is svc2

    def test_valid_slots(self):
        svc = EmbeddingService()
        assert set(svc._locks.keys()) == {"minilm", "colbert", "bge-small"}

    def test_model_names_from_defaults(self):
        svc = EmbeddingService()
        assert svc._model_names["minilm"] == "sentence-transformers/all-MiniLM-L6-v2"
        assert svc._model_names["colbert"] == "colbert-ir/colbertv2.0"
        assert svc._model_names["bge-small"] == "BAAI/bge-small-en-v1.5"

    def test_status_empty_on_init(self):
        svc = EmbeddingService()
        status = svc.get_status()
        assert status["loaded_slots"] == []
        assert status["dimensions"] == {}


class TestGetModel:
    """Test model loading behavior."""

    def test_invalid_slot_raises(self):
        svc = EmbeddingService()
        with pytest.raises(ValueError, match="Unknown embedding slot"):
            asyncio.get_event_loop().run_until_complete(svc.get_model("invalid"))

    def test_get_model_sync_caches(self):
        """Test that get_model_sync caches the model and returns same instance."""
        svc = EmbeddingService()

        mock_model = MagicMock()
        with patch.object(svc, "_load_model_sync", return_value=mock_model):
            with patch.object(svc, "_detect_dimension", return_value=384):
                result1 = svc.get_model_sync("minilm")
                result2 = svc.get_model_sync("minilm")

        assert result1 is result2
        assert result1 is mock_model

    def test_get_dimension_defaults(self):
        svc = EmbeddingService()
        assert svc.get_dimension("minilm") == 384
        assert svc.get_dimension("colbert") == 128
        assert svc.get_dimension("bge-small") == 384


class TestAsyncGetModel:
    """Test async model loading."""

    @pytest.mark.asyncio
    async def test_async_get_model_caches(self):
        svc = EmbeddingService()
        mock_model = MagicMock()

        with patch.object(svc, "_load_model_sync", return_value=mock_model):
            with patch.object(svc, "_detect_dimension", return_value=384):
                result1 = await svc.get_model("minilm")
                result2 = await svc.get_model("minilm")

        assert result1 is result2
        assert result1 is mock_model

    @pytest.mark.asyncio
    async def test_concurrent_get_model_loads_once(self):
        """Test that concurrent calls only load the model once."""
        svc = EmbeddingService()
        mock_model = MagicMock()
        load_count = 0

        original_load = svc._load_model_sync

        def counting_load(slot):
            nonlocal load_count
            load_count += 1
            return mock_model

        with patch.object(svc, "_load_model_sync", side_effect=counting_load):
            with patch.object(svc, "_detect_dimension", return_value=384):
                results = await asyncio.gather(
                    svc.get_model("minilm"),
                    svc.get_model("minilm"),
                    svc.get_model("minilm"),
                )

        # All should get the same instance
        assert all(r is mock_model for r in results)
        # Should only load once due to lock
        assert load_count == 1


class TestPreloadAndShutdown:
    """Test preload and shutdown lifecycle."""

    @pytest.mark.asyncio
    async def test_preload_loads_specified_slots(self):
        svc = EmbeddingService()
        mock_model = MagicMock()

        with patch.object(svc, "_load_model_sync", return_value=mock_model):
            with patch.object(svc, "_detect_dimension", return_value=384):
                await svc.preload("minilm")

        assert "minilm" in svc._models
        assert "colbert" not in svc._models

    @pytest.mark.asyncio
    async def test_shutdown_clears_models(self):
        svc = EmbeddingService()
        svc._models["minilm"] = MagicMock()
        svc._dimensions["minilm"] = 384

        await svc.shutdown()

        assert svc._models == {}
        assert svc._dimensions == {}

    @pytest.mark.asyncio
    async def test_preload_ignores_invalid_slots(self):
        svc = EmbeddingService()
        # Should not raise
        await svc.preload("invalid", "")
        assert svc._models == {}
