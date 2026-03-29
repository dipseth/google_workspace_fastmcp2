"""Session-aware sampling handler — routes per-user LLM config when available.

Wraps the server-default sampling handler and checks for per-session
overrides stored via the OAuth success page. When a user has configured
their own LLM provider (model, api_key, api_base), their sampling calls
are routed through that provider instead of the server default.

Also provides `create_sampling_handler()` factory that creates the
server-default handler (LiteLLM or Anthropic) and wraps it in a
SessionAwareSamplingHandler.
"""

from typing import Any, Optional

from mcp.types import CreateMessageRequestParams as SamplingParams
from mcp.types import (
    CreateMessageResult,
    CreateMessageResultWithTools,
    SamplingMessage,
)

from config.enhanced_logging import setup_logger

logger = setup_logger()

class SessionAwareSamplingHandler:
    """Sampling handler that checks per-session config before falling back to default.

    Session resolution: iterates active sessions in reverse order looking for
    a SAMPLING_CONFIG entry. If found, creates (or reuses) a LiteLLMSamplingHandler
    configured with the user's provider details.

    Handler cache: keyed by (model, api_key, api_base) tuple to avoid re-creating
    handler instances on every call.
    """

    def __init__(self, default_handler: Any = None):
        self.default_handler = default_handler
        # Cache handlers by config tuple to avoid recreation
        self._handler_cache: dict[tuple, Any] = {}

    async def __call__(
        self,
        messages: list[SamplingMessage],
        params: SamplingParams,
        context: Any,
    ) -> CreateMessageResult | CreateMessageResultWithTools:
        config = self._get_session_sampling_config()
        if config:
            handler = self._get_or_create_handler(config)
            if handler:
                logger.debug(
                    "Routing sampling through per-user config: model=%s",
                    config.get("model", "?"),
                )
                return await handler(messages, params, context)

        # Fall through to server default
        if self.default_handler is None:
            raise RuntimeError("No sampling handler configured")
        return await self.default_handler(messages, params, context)

    def _get_session_sampling_config(self) -> Optional[dict]:
        """Find sampling config from any active session.

        Walks sessions in reverse order (most recent first) looking for
        a SAMPLING_CONFIG entry. If not in session cache, attempts to
        lazy-load from encrypted disk.
        """
        try:
            from auth.context import get_session_data, list_sessions
            from auth.types import SessionKey

            for sid in reversed(list_sessions()):
                # Check in-memory session cache first
                config = get_session_data(sid, SessionKey.SAMPLING_CONFIG, default=None)
                if config:
                    return config

                # Lazy-load from disk if user email is known
                user_email = get_session_data(sid, SessionKey.USER_EMAIL, default=None)
                if not user_email:
                    continue

                per_user_key = get_session_data(
                    sid, SessionKey.PER_USER_ENCRYPTION_KEY, default=None
                )
                google_sub = get_session_data(sid, SessionKey.GOOGLE_SUB, default=None)

                try:
                    from auth.context import get_auth_middleware

                    auth_mw = get_auth_middleware()
                    if auth_mw:
                        loaded = auth_mw.load_sampling_config(
                            user_email,
                            per_user_key=per_user_key,
                            google_sub=google_sub,
                        )
                        if loaded:
                            # Cache back to session for fast lookup next time
                            from auth.context import store_session_data

                            store_session_data(sid, SessionKey.SAMPLING_CONFIG, loaded)
                            return loaded
                except Exception as e:
                    logger.debug("Failed to lazy-load sampling config: %s", e)

        except Exception as e:
            logger.debug("Session sampling config lookup failed: %s", e)

        return None

    def _get_or_create_handler(self, config: dict) -> Optional[Any]:
        """Get or create a LiteLLMSamplingHandler for the given config."""
        model = config.get("model")
        api_key = config.get("api_key")
        api_base = config.get("api_base")

        if not model:
            return None

        cache_key = (model, api_key or "", api_base or "")
        if cache_key in self._handler_cache:
            return self._handler_cache[cache_key]

        try:
            from middleware.litellm_sampling_handler import LiteLLMSamplingHandler

            handler = LiteLLMSamplingHandler(
                default_model=model,
                api_key=api_key,
                api_base=api_base,
            )
            self._handler_cache[cache_key] = handler
            logger.info(
                "Created per-user sampling handler: model=%s, has_key=%s, base=%s",
                model,
                bool(api_key),
                api_base or "default",
            )
            return handler
        except Exception as e:
            logger.warning("Failed to create per-user sampling handler: %s", e)
            return None


# ---------------------------------------------------------------------------
# Factory: create the server-default sampling handler
# ---------------------------------------------------------------------------


def _create_litellm_handler(settings):
    """Create a LiteLLM sampling handler from settings."""
    from middleware.litellm_sampling_handler import LiteLLMSamplingHandler

    # Resolve API key: explicit LITELLM_API_KEY > VENICE_INFERENCE_KEY > None (litellm env var fallback)
    # For anthropic/ models, let LiteLLM use ANTHROPIC_API_KEY env var directly
    # (don't pass Venice key/base which would override the correct provider auth)
    model = settings.litellm_model
    if model.startswith("anthropic/"):
        api_key = settings.litellm_api_key  # Only use explicit override, not Venice
        api_base = settings.litellm_api_base
    else:
        api_key = settings.litellm_api_key or settings.venice_inference_key
        api_base = settings.litellm_api_base
        if (
            not api_base
            and settings.venice_inference_key
            and not settings.litellm_api_key
        ):
            api_base = "https://api.venice.ai/api/v1"
    return LiteLLMSamplingHandler(
        default_model=settings.litellm_model,
        api_key=api_key,
        api_base=api_base,
    )


def _create_anthropic_handler(settings):
    """Create an Anthropic sampling handler with cost tracking and Langfuse tracing."""
    from anthropic import AsyncAnthropic
    from fastmcp.client.sampling.handlers.anthropic import AnthropicSamplingHandler

    handler = AnthropicSamplingHandler(
        default_model="claude-sonnet-4-6",
        client=AsyncAnthropic(api_key=settings.anthropic_api_key),
    )

    # Wrap handler to track sampling costs
    async def _tracking_wrapper(messages, params, context):
        result = await handler(messages, params, context)
        try:
            from middleware.payment.cost_tracker import track_sample_call

            # Estimate from text since Anthropic handler doesn't expose usage
            input_text = " ".join(
                getattr(m.content, "text", "")
                for m in messages
                if hasattr(m, "content") and hasattr(m.content, "text")
            )
            output_text = ""
            if hasattr(result, "content"):
                c = result.content
                if hasattr(c, "text"):
                    output_text = c.text
                elif isinstance(c, list):
                    output_text = " ".join(
                        getattr(b, "text", "") for b in c if hasattr(b, "text")
                    )
            track_sample_call(
                input_text=input_text,
                output_text=output_text,
                model=getattr(result, "model", "claude-sonnet-4-6")
                or "claude-sonnet-4-6",
            )
        except Exception:
            pass
        return result

    # Wrap with Langfuse @observe tracing if configured
    try:
        from middleware.langfuse_integration import wrap_anthropic_handler_with_langfuse

        wrapped = wrap_anthropic_handler_with_langfuse(_tracking_wrapper)
        return wrapped
    except Exception:
        return _tracking_wrapper


def create_sampling_handler(settings) -> Optional["SessionAwareSamplingHandler"]:
    """Create the server-default sampling handler and wrap in SessionAwareSamplingHandler.

    Selects provider based on ``settings.sampling_provider`` (litellm / anthropic / auto).
    Registers the raw handler with the cache-keepalive lifespan, then wraps in
    SessionAwareSamplingHandler for per-user config routing.

    Returns a SessionAwareSamplingHandler (which may wrap None if no provider is available).
    """
    raw_handler = None
    provider = settings.sampling_provider.lower().strip()

    if provider == "litellm":
        try:
            raw_handler = _create_litellm_handler(settings)
            logger.info(
                "🤖 LiteLLM sampling handler configured (model: %s)",
                settings.litellm_model,
            )
        except Exception as e:
            logger.warning("⚠️ Failed to configure LiteLLM handler: %s", e)

    elif provider == "anthropic":
        if settings.anthropic_api_key:
            try:
                raw_handler = _create_anthropic_handler(settings)
                logger.info("🤖 Anthropic sampling handler configured")
            except Exception as e:
                logger.warning("⚠️ Failed to configure Anthropic handler: %s", e)

    else:  # "auto"
        # Try LiteLLM first (if venice key or litellm key set), then Anthropic
        _has_litellm_key = settings.litellm_api_key or settings.venice_inference_key
        if _has_litellm_key:
            try:
                raw_handler = _create_litellm_handler(settings)
                logger.info(
                    "🤖 LiteLLM sampling handler configured as default (model: %s)",
                    settings.litellm_model,
                )
            except Exception as e:
                logger.warning("⚠️ LiteLLM handler failed, trying Anthropic: %s", e)

        if raw_handler is None and settings.anthropic_api_key:
            try:
                raw_handler = _create_anthropic_handler(settings)
                logger.info("🤖 Anthropic sampling handler configured (fallback)")
            except Exception as e:
                logger.warning("⚠️ Failed to configure Anthropic handler: %s", e)

    if raw_handler is None:
        logger.warning(
            "⚠️ No sampling handler — set VENICE_INFERENCE_KEY, LITELLM_API_KEY, or ANTHROPIC_API_KEY"
        )

    # Register raw handler for cache keepalive lifespan access
    from lifespans.server_lifespans import register_litellm_handler

    register_litellm_handler(raw_handler)

    # Wrap with session-aware handler for per-user LLM provider configuration
    return SessionAwareSamplingHandler(raw_handler)
