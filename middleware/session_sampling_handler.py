"""Session-aware sampling handler — routes per-user LLM config when available.

Wraps the server-default sampling handler and checks for per-session
overrides stored via the OAuth success page. When a user has configured
their own LLM provider (model, api_key, api_base), their sampling calls
are routed through that provider instead of the server default.
"""

import logging
from typing import Any, Optional

from mcp.types import CreateMessageRequestParams as SamplingParams
from mcp.types import (
    CreateMessageResult,
    CreateMessageResultWithTools,
    SamplingMessage,
)

logger = logging.getLogger(__name__)


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
