"""Tests for OTel initialization consolidation in langfuse_integration."""

from unittest.mock import MagicMock, patch


class TestConfigureLangfuseNoOtel:
    """Verify configure_langfuse() no longer calls configure_otel_for_langfuse."""

    def test_no_otel_call(self):
        """configure_langfuse should NOT invoke configure_otel_for_langfuse."""
        mock_settings = MagicMock()
        mock_settings.langfuse_enabled = True
        mock_settings.langfuse_public_key = "pk-test"
        mock_settings.langfuse_secret_key = "sk-test"
        mock_settings.langfuse_host = "https://langfuse.test"

        # Reset module state
        import middleware.langfuse_integration as mod
        mod._langfuse_initialized = False

        with (
            patch.object(mod, "configure_otel_for_langfuse", create=True) as mock_otel,
            patch("config.settings.settings", mock_settings),
        ):
            # Patch the import inside configure_langfuse
            with patch.dict("sys.modules", {"middleware.otel_setup": MagicMock()}):
                result = mod.configure_langfuse()

            assert result is True
            # The key assertion: otel should NOT be called from here
            mock_otel.assert_not_called()

        # Clean up
        mod._langfuse_initialized = False

    def test_enable_litellm_langfuse_adds_callback(self):
        """enable_litellm_langfuse adds 'langfuse_otel' to litellm.callbacks."""
        import middleware.langfuse_integration as mod

        mock_litellm = MagicMock()
        mock_litellm.callbacks = []

        # Pretend langfuse is already configured
        mod._langfuse_initialized = True
        try:
            with patch.dict("sys.modules", {"litellm": mock_litellm}):
                result = mod.enable_litellm_langfuse()
            assert result is True
            assert "langfuse_otel" in mock_litellm.callbacks
        finally:
            mod._langfuse_initialized = False
