"""Session-aware sampling handler — routes per-user LLM config when available.

Wraps the server-default sampling handler and checks for a per-user override
(saved through the OAuth intro screen or ``/api/sampling-config``). When a user
has configured their own LLM provider (model, api_key, api_base), their
sampling calls are routed through that provider instead of the server default.
The lookup is keyed by the calling principal, so it works identically for
handshake-era connections and for 2026-07-28 clients whose every request is a
fresh transport session.

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


# Decrypted per-user configs by bucket principal segment. The bucket itself
# holds only the non-secret part (model, api_base) so no provider key lands in
# the disk or Redis state store; the key comes from the encrypted per-user file
# and is cached here for the life of the process.
_decrypted_configs: dict[str, dict] = {}


def forget_sampling_config(email: str) -> None:
    """Drop the in-process decrypted config for ``email`` (after save/clear)."""
    from auth.user_state import UserBucket, principal_for_email

    _decrypted_configs.pop(UserBucket(principal_for_email(email)).segment, None)


def public_sampling_config(config: Optional[dict]) -> Optional[dict]:
    """The part of a sampling config that may be written to the state store."""
    if not config or not config.get("model"):
        return None
    public = {"model": config["model"], "has_api_key": bool(config.get("api_key"))}
    if config.get("api_base"):
        public["api_base"] = config["api_base"]
    return public


class SessionAwareSamplingHandler:
    """Sampling handler that checks per-user config before falling back to default.

    Resolution order for the calling principal (auth/user_state.py):

    1. The in-process decrypted config for this principal.
    2. The encrypted per-user file, decrypted with key material the current
       request carries (the per-user API key bearer, or the OAuth ``sub``), then
       cached in-process.
    3. The bucket's public record (model, api_base) when the file cannot be
       decrypted on this request — the provider then relies on server-side
       credentials for that model.

    Never another user's config: the principal comes from the request's token.

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
        config = (
            self._get_request_override_config()
            or await self._get_session_sampling_config()
        )
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

    def _get_request_override_config(self) -> Optional[dict]:
        """Per-request override from X-Sampling-* headers (opt-in via settings).

        FastMCP 4 removed client-fulfilled sampling, so a caller that wants a
        specific model (the evals harness comparing providers) names it on the
        request instead. Disabled unless ``SAMPLING_ALLOW_HEADER_OVERRIDE=true``.
        """
        try:
            from config.settings import settings

            if not getattr(settings, "sampling_allow_header_override", False):
                return None
            # get_http_headers() (not get_http_request()) so the override also
            # reaches background-task workers, which restore the submitting
            # request's headers but never fabricate a live Request object.
            from fastmcp.server.dependencies import get_http_headers

            headers = {
                k.lower(): v for k, v in get_http_headers(include_all=True).items()
            }
            model = (headers.get("x-sampling-model") or "").strip()
            if not model:
                return None
            config = {"model": model}
            api_base = (headers.get("x-sampling-api-base") or "").strip()
            api_key = (headers.get("x-sampling-api-key") or "").strip()
            if api_base:
                config["api_base"] = api_base
            if api_key:
                config["api_key"] = api_key
            return config
        except Exception:
            return None

    async def _get_session_sampling_config(self) -> Optional[dict]:
        """Find the sampling config for the *calling principal*.

        See the class docstring for the resolution order. Outside a request,
        or for a principal with no config, returns None so the server default
        handler is used.
        """
        try:
            from auth.context import (
                get_auth_middleware,
                get_session_context_sync,
                get_session_data,
            )
            from auth.types import SessionKey
            from auth.user_state import (
                SAMPLING_CONFIG_KEY,
                bucket_get,
                bucket_set,
                principal_email,
                principal_sub,
                user_bucket,
            )

            bucket = user_bucket()
            cached = _decrypted_configs.get(bucket.segment)
            if cached:
                return cached

            public = await bucket_get(SAMPLING_CONFIG_KEY)
            if public is not None and not public:
                # Explicitly cleared: skip the file read.
                return None

            sid = get_session_context_sync()
            user_email = principal_email() or (
                get_session_data(sid, SessionKey.USER_EMAIL, default=None)
                if sid
                else None
            )
            if user_email:
                per_user_key = (
                    get_session_data(
                        sid, SessionKey.PER_USER_ENCRYPTION_KEY, default=None
                    )
                    if sid
                    else None
                )
                google_sub = principal_sub() or (
                    get_session_data(sid, SessionKey.GOOGLE_SUB, default=None)
                    if sid
                    else None
                )
                auth_mw = get_auth_middleware()
                if auth_mw:
                    loaded = auth_mw.load_sampling_config(
                        user_email, per_user_key=per_user_key, google_sub=google_sub
                    )
                    if loaded:
                        _decrypted_configs[bucket.segment] = loaded
                        if public != public_sampling_config(loaded):
                            await bucket_set(
                                SAMPLING_CONFIG_KEY, public_sampling_config(loaded)
                            )
                        return loaded

            if public and public.get("model"):
                # Could not decrypt the key on this request; route by model and
                # let the provider pick up server-side credentials.
                return {k: v for k, v in public.items() if k in ("model", "api_base")}

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

    # Load persisted monthly cost tracking so budget gates work from startup
    try:
        from middleware.payment.cost_tracker import load_monthly_costs

        load_monthly_costs()
        budget = settings.sampling_monthly_budget_usd
        if budget > 0:
            from middleware.payment.cost_tracker import get_monthly_cost

            logger.info(
                "Sampling budget: $%.2f / $%.2f this month",
                get_monthly_cost(),
                budget,
            )
    except Exception:
        pass

    # Wrap with session-aware handler for per-user LLM provider configuration
    return SessionAwareSamplingHandler(raw_handler)
